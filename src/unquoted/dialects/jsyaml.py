"""js-yaml 4's resolver, as used by anything that reads YAML in Node.

Transcribed from js-yaml 4.x `lib/type/{int,float,bool,null,timestamp}.js`:
`resolveYamlInteger` / `parseYamlInteger`, `YAML_FLOAT_PATTERN`,
`resolveYamlBoolean`, `resolveYamlNull`, and the two timestamp regexes with
`constructYamlTimestamp`.

This is the strictest 1.2 reading of the three, and the odd one out in both
directions:

* `012` is **12**. `resolveYamlInteger` special-cases only `0b`, `0x` and `0o`
  after a leading zero and otherwise falls through to base 10, so the same
  three characters are 10 to PyYAML and go-yaml and 12 here. Nothing warns.
* `1_000` is the string `1_000`, because the digit loop rejects `_`. The other
  two both strip underscores and give 1000.
* `2026-02-31` becomes 3 March 2026. The date is built with `Date.UTC`, which
  rolls overflowing fields forward rather than refusing them.
"""

from __future__ import annotations

import re

from . import (
    BOOL,
    FLOAT,
    INT,
    MERGE,
    NULL,
    STR,
    TIMESTAMP,
    Resolution,
    render_float,
    render_int,
    render_timestamp,
)

_BOOLS = {
    "true": "true",
    "True": "true",
    "TRUE": "true",
    "false": "false",
    "False": "false",
    "FALSE": "false",
}

_NULLS = {"~", "null", "Null", "NULL"}

_FLOAT_PATTERN = re.compile(
    r"^(?:[-+]?(?:[0-9]+)(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?"
    r"|\.[0-9]+(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)"
    r"|\.(?:nan|NaN|NAN))$"
)
_FLOAT_SPECIAL = re.compile(r"^(?:[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$")

_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIMESTAMP = re.compile(
    r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[Tt]|[ \t]+)(\d{1,2}):(\d{2}):(\d{2})"
    r"(?:\.(\d*))?(?:[ \t]*(Z|([-+])(\d{1,2})(?::(\d{2}))?))?$"
)


def _resolve_integer(text: str) -> int | None:
    """resolveYamlInteger, then parseYamlInteger for the value.

    Written as the original's character walk rather than as a regex, because
    the fall-through after the `0b`/`0x`/`0o` checks is the entire reason `012`
    is 12 here, and a regex hides it.
    """
    if not text:
        return None
    index = 0
    if text[index] in "-+":
        index += 1
        if index >= len(text):
            return None
    if text[index] == "0":
        if index + 1 == len(text):
            return 0
        index += 1
        prefix = text[index]
        if prefix in "bxo":
            base = {"b": 2, "x": 16, "o": 8}[prefix]
            digits = text[index + 1 :]
            allowed = "01" if base == 2 else ("01234567" if base == 8 else "0123456789abcdefABCDEF")
            if not digits or any(character not in allowed for character in digits):
                return None
            sign = -1 if text[0] == "-" else 1
            return _as_double(sign * int(digits, base))
        # No prefix match: index is left pointing *past* the leading zero and
        # the base-10 loop takes it from there. "012" -> parseInt("012", 10).
    digits = text[index:]
    if not digits or any(character not in "0123456789" for character in digits):
        return None
    sign = -1 if text[0] == "-" else 1
    return _as_double(sign * int(text.lstrip("-+"), 10))


def _as_double(value: int) -> int | None:
    """JavaScript has one number type, and `parseInt` returns a double.

    Past 2^53 the exact integer is not representable and the result is the
    nearest double, so `99999999999999999999` comes back as
    100000000000000000000 — a different integer, from a parser that reported no
    problem. `resolveYamlInteger` also ends in `isFinite(...)`, so a literal
    that overflows to Infinity is not an integer at all, and stays a string.
    """
    if abs(value) <= 2**53:
        return value
    try:
        wide = float(value)
    except OverflowError:
        return None
    if wide in (float("inf"), float("-inf")):
        return None
    return int(wide)


def _construct_timestamp(text: str) -> str | None:
    match = _DATE.match(text)
    if match:
        year, month, day = (int(group) for group in match.groups())
        return _roll(year, month, day)
    match = _TIMESTAMP.match(text)
    if not match:
        return None
    groups = match.groups()
    year, month, day, hour, minute, second = (int(group) for group in groups[:6])
    # constructYamlTimestamp keeps three digits and pads: the fraction becomes
    # whole milliseconds, so anything finer than a millisecond is dropped here
    # and kept by the other two.
    fraction = (groups[6] or "")[:3].ljust(3, "0") if groups[6] else ""
    offset = 0
    if groups[7] and groups[7] != "Z":
        sign = -1 if groups[8] == "-" else 1
        offset = sign * (int(groups[9]) * 60 + int(groups[10] or 0))
    return _roll(year, month, day, hour, minute, second, fraction, offset)


def _roll(
    year: int,
    month: int,
    day: int,
    hour: int | None = None,
    minute: int = 0,
    second: int = 0,
    fraction: str = "",
    offset: int = 0,
) -> str:
    """Date.UTC semantics: out-of-range fields carry into the next unit.

    `new Date(Date.UTC(2026, 1, 31))` is 3 March. js-yaml does not check first,
    so a typo'd day silently becomes a different, valid date.
    """
    import datetime

    month_index = month - 1
    year += month_index // 12
    month_index %= 12
    base = datetime.datetime(year, month_index + 1, 1)
    base += datetime.timedelta(days=day - 1, hours=hour or 0, minutes=minute, seconds=second)
    if hour is None:
        return render_timestamp(base.year, base.month, base.day)
    return render_timestamp(
        base.year,
        base.month,
        base.day,
        base.hour,
        base.minute,
        base.second,
        fraction,
        offset,
    )


class JsYaml:
    name = "js-yaml"
    label = "js-yaml 4"

    @staticmethod
    def resolve(text: str) -> Resolution:
        if text == "<<":
            # The merge type is last in DEFAULT_SCHEMA's implicit list and has
            # no construct, so js-yaml tags `<<` and hands the text back
            # unchanged. PyYAML tags it too; go-yaml leaves it a plain string.
            return Resolution(MERGE, "<<")
        if text in _BOOLS:
            return Resolution(BOOL, _BOOLS[text])
        if text == "" or text in _NULLS:
            return Resolution(NULL, "null")
        stamp = _construct_timestamp(text)
        if stamp is not None:
            return Resolution(TIMESTAMP, stamp)
        number = _resolve_integer(text)
        if number is not None:
            return Resolution(INT, render_int(number))
        if _FLOAT_PATTERN.match(text):
            lowered = text.lower().lstrip("+-")
            if lowered == ".inf":
                return Resolution(FLOAT, "-inf" if text[0] == "-" else "inf")
            if lowered == ".nan":
                return Resolution(FLOAT, "nan")
            try:
                value = float(text)
            except (ValueError, OverflowError):
                return Resolution(STR, text)
            # resolveYamlFloat requires isFinite(parseFloat(data)) unless the
            # text is one of the .inf/.nan spellings, so an overflowing literal
            # is not a float. JavaScript has no integer overflow to match, but
            # it does have this.
            if value in (float("inf"), float("-inf")):
                return Resolution(STR, text)
            return Resolution(FLOAT, render_float(value))
        return Resolution(STR, text)
