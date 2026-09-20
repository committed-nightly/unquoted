"""PyYAML's resolver: YAML 1.1, as used by Python, and by SnakeYAML's defaults.

Transcribed from PyYAML 6.x `yaml/resolver.py`, the `Resolver.add_implicit_resolver`
calls at the bottom of the file, plus the `construct_yaml_int` / `construct_yaml_float`
constructors in `yaml/constructor.py` for the values.

The two rules worth knowing before reading the regexes:

* `on`, `off`, `yes` and `no` are booleans. This is the one everybody has
  heard of, and the reason every GitHub workflow has a `True` key in it.
* The int pattern has an `0[0-7_]+` branch *before* the decimal branch, so
  `012` is octal 10 — and a `(:[0-5]?[0-9])+` branch, so `12:30` is 750.
  Base-60 was dropped in YAML 1.2; PyYAML still has it.
"""

from __future__ import annotations

import re

from . import (
    BOOL,
    FLOAT,
    INT,
    INVALID,
    MERGE,
    NULL,
    STR,
    TIMESTAMP,
    VALUE,
    Resolution,
    render_float,
    render_int,
    render_timestamp,
    zone_minutes,
)

# resolver.py, verbatim.
_BOOL = re.compile(
    r"""^(?:yes|Yes|YES|no|No|NO
    |true|True|TRUE|false|False|FALSE
    |on|On|ON|off|Off|OFF)$""",
    re.X,
)

_FLOAT = re.compile(
    r"""^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?
    |\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?
    |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*
    |[-+]?\.(?:inf|Inf|INF)
    |\.(?:nan|NaN|NAN))$""",
    re.X,
)

_INT = re.compile(
    r"""^(?:[-+]?0b[0-1_]+
    |[-+]?0[0-7_]+
    |[-+]?(?:0|[1-9][0-9_]*)
    |[-+]?0x[0-9a-fA-F_]+
    |[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$""",
    re.X,
)

_MERGE = re.compile(r"^(?:<<)$")

_NULL = re.compile(
    r"""^(?: ~
    |null|Null|NULL
    | )$""",
    re.X,
)

_TIMESTAMP = re.compile(
    r"""^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]
    |[0-9][0-9][0-9][0-9] -[0-9][0-9]? -[0-9][0-9]?
     (?:[Tt]|[ \t]+)[0-9][0-9]?
     :[0-9][0-9] :[0-9][0-9] (?:\.[0-9]*)?
     (?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$""",
    re.X,
)

_VALUE = re.compile(r"^(?:=)$")

_TRUTHY = {"yes", "true", "on"}

# PyYAML dispatches on the scalar's first character before trying any pattern
# (`yaml_implicit_resolvers` is keyed by it), so a pattern whose first character
# is not registered can never fire even if it would match. The registrations are
# the third argument to each add_implicit_resolver call. Transcribed so that
# adding a pattern here without its first characters cannot silently widen it.
_FIRST_CHARS = {
    _BOOL: set("yYnNtTfFoO"),
    _FLOAT: set("-+0123456789."),
    _INT: set("-+0123456789"),
    _MERGE: set("<"),
    _NULL: {"~", "n", "N", ""},
    _TIMESTAMP: set("0123456789"),
    _VALUE: set("="),
}

# resolver.py registers these in this order, and resolve() takes the first match.
_ORDER = (_BOOL, _FLOAT, _INT, _MERGE, _NULL, _TIMESTAMP, _VALUE)


def _int_value(text: str) -> int:
    """constructor.py `construct_yaml_int`."""
    value = text.replace("_", "")
    sign = -1 if value[0] == "-" else 1
    if value[0] in "+-":
        value = value[1:]
    if value == "0":
        return 0
    if value.startswith("0b"):
        return sign * int(value[2:], 2)
    if value.startswith("0x"):
        return sign * int(value[2:], 16)
    if value[0] == "0":
        return sign * int(value, 8)
    if ":" in value:
        digits = [int(part) for part in value.split(":")]
        digits.reverse()
        total = 0
        base = 1
        for digit in digits:
            total += digit * base
            base *= 60
        return sign * total
    return sign * int(value)


def _float_value(text: str) -> float:
    """constructor.py `construct_yaml_float`."""
    value = text.replace("_", "").lower()
    sign = -1 if value[0] == "-" else 1
    if value[0] in "+-":
        value = value[1:]
    if value == ".inf":
        return sign * float("inf")
    if value == ".nan":
        return float("nan")
    if ":" in value:
        digits = [float(part) for part in value.split(":")]
        digits.reverse()
        total = 0.0
        base = 1
        for digit in digits:
            total += digit * base
            base *= 60
        return sign * total
    return sign * float(value)


def _guarded(parse, render, text: str) -> str:
    """Resolve to the tag, then survive the constructor raising.

    `0x_` matches the int pattern -- `[-+]?0x[0-9a-fA-F_]+`, and `_` is in that
    class -- and `construct_yaml_int` then strips the underscores and calls
    `int("", 16)`. So `yaml.safe_load("0x_")` raises ValueError. It is a real
    one-line document that crashes PyYAML, and the same shape of bug as
    `2026-02-31`: the resolver says yes and the constructor cannot deliver.
    """
    try:
        return render(parse(text))
    except (ValueError, OverflowError):
        return INVALID


_TIMESTAMP_PARTS = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:(?:[Tt]|[ \t]+)(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.(?P<fraction>\d*))?"
    r"(?:[ \t]*(?P<zone>Z|[-+]\d{1,2}(?::\d{2})?))?)?$"
)


def _timestamp_value(text: str) -> str:
    """constructor.py `construct_yaml_timestamp`.

    The regex in the resolver only checks the *shape*; the constructor then
    calls `datetime.date(...)`, which is where a day that does not exist stops
    being a formatting question. `2026-02-31` passes the resolver and raises on
    load, so the whole document fails to parse — reported here as `<invalid>`.
    """
    import datetime

    match = _TIMESTAMP_PARTS.match(text)
    if match is None:  # pragma: no cover - the resolver pattern has matched
        return INVALID
    parts = match.groupdict()
    year, month, day = (int(parts[name]) for name in ("year", "month", "day"))
    if parts["hour"] is None:
        try:
            datetime.date(year, month, day)
        except ValueError:
            return INVALID
        return render_timestamp(year, month, day)
    hour, minute, second = (int(parts[name]) for name in ("hour", "minute", "second"))
    fraction = parts["fraction"] or ""
    micro = int(fraction.ljust(6, "0")[:6]) if fraction else 0
    try:
        datetime.datetime(year, month, day, hour, minute, second, micro)
    except ValueError:
        return INVALID
    return render_timestamp(
        year, month, day, hour, minute, second, micro, zone_minutes(parts["zone"] or "")
    )


class PyYAML:
    name = "pyyaml"
    label = "PyYAML 6"

    @staticmethod
    def resolve(text: str) -> Resolution:
        first = text[0] if text else ""
        for pattern in _ORDER:
            if first not in _FIRST_CHARS[pattern]:
                continue
            if not pattern.match(text):
                continue
            if pattern is _BOOL:
                return Resolution(BOOL, "true" if text.lower() in _TRUTHY else "false")
            if pattern is _FLOAT:
                return Resolution(FLOAT, _guarded(_float_value, render_float, text))
            if pattern is _INT:
                return Resolution(INT, _guarded(_int_value, render_int, text))
            if pattern is _MERGE:
                return Resolution(MERGE, "<<")
            if pattern is _VALUE:
                return Resolution(VALUE, "=")
            if pattern is _NULL:
                return Resolution(NULL, "null")
            return Resolution(TIMESTAMP, _timestamp_value(text))
        return Resolution(STR, text)
