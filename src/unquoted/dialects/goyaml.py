"""go-yaml v3's resolver, as used by Kubernetes, Helm, Docker Compose and friends.

Transcribed from `gopkg.in/yaml.v3` `resolve.go`: the `resolveMapList` table,
`resolveTable`, `yamlStyleFloat`, `allowedTimestampFormats` and the body of
`resolve()`.

go-yaml v3 is usually described as a YAML 1.2 parser, and on booleans it is:
`yes`, `no`, `on` and `off` are strings. On integers it is not. `resolve()`
hands the text to Go's own `strconv.ParseInt(s, 0, 64)`, which reads a leading
zero as octal — so `012` is 10 here as well as under PyYAML, and the source
says so in as many words:

    // Octals from the 1.1 spec, spelled as 0777, are still
    // decoded by default in v3 as well for compatibility.
    // May be dropped in v4 depending on how usage evolves.

The consequence worth knowing: go-yaml agrees with PyYAML that `012` is 10,
and js-yaml reads the same three characters as 12.
"""

from __future__ import annotations

import re

from . import (
    BOOL,
    FLOAT,
    INT,
    NULL,
    STR,
    TIMESTAMP,
    Resolution,
    render_float,
    render_int,
    render_timestamp,
    zone_minutes,
)

# resolveTable: the first byte decides whether resolve() even tries.
_HINT_SIGN = set("+-")
_HINT_DIGIT = set("0123456789")
_HINT_MAP = set("yYnNtTfFoO~")

# resolveMapList. Note what is *not* here: no yes/no/on/off, and no `<<`.
# `<<` is missing from resolveTable too, so it never reaches resolveMap; merge
# keys are handled later, in decode.go, and a bare `<<` scalar stays a string.
_MAP: dict[str, Resolution] = {}
for _text in ("true", "True", "TRUE"):
    _MAP[_text] = Resolution(BOOL, "true")
for _text in ("false", "False", "FALSE"):
    _MAP[_text] = Resolution(BOOL, "false")
for _text in ("", "~", "null", "Null", "NULL"):
    _MAP[_text] = Resolution(NULL, "null")
for _text in (".nan", ".NaN", ".NAN"):
    _MAP[_text] = Resolution(FLOAT, "nan")
for _text in (".inf", ".Inf", ".INF", "+.inf", "+.Inf", "+.INF"):
    _MAP[_text] = Resolution(FLOAT, "inf")
for _text in ("-.inf", "-.Inf", "-.INF"):
    _MAP[_text] = Resolution(FLOAT, "-inf")

_YAML_STYLE_FLOAT = re.compile(r"^[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?$")

_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_UINT64_MAX = 2**64 - 1

# allowedTimestampFormats, as regexes. Go's layouts use non-padded field
# specifiers ("1", "2", "4", "5", "15"), which time.Parse reads as one digit
# or two. "Z07:00" is not optional in the layouts that have it, so a T-separated
# timestamp with no zone is not a timestamp to go-yaml — PyYAML and js-yaml
# both take it.
_TS_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_TS_ZONED = re.compile(
    r"^(\d{4})-(\d{1,2})-(\d{1,2})[Tt](\d{1,2}):(\d{1,2}):(\d{1,2})(?:\.(\d*))?"
    r"(Z|[-+]\d{2}:\d{2})$"
)
_TS_SPACED = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2}):(\d{1,2})(?:\.(\d*))?$")

_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _valid_date(year: int, month: int, day: int) -> bool:
    """time.Parse validates calendar ranges and rejects what does not exist.

    This is the difference that makes `2026-02-31` a three-way split: go-yaml
    declines it and leaves a string, PyYAML's regex accepts it and its
    constructor then raises, and js-yaml rolls it forward to 3 March.
    """
    if not 1 <= month <= 12:
        return False
    days = _DAYS[month - 1]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        days = 29
    return 1 <= day <= days


def _parse_timestamp(text: str) -> Resolution | None:
    match = _TS_DATE.match(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        if _valid_date(year, month, day):
            return Resolution(TIMESTAMP, render_timestamp(year, month, day))
        return None
    for pattern, zoned in ((_TS_ZONED, True), (_TS_SPACED, False)):
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groups()
        year, month, day, hour, minute, second = (int(g) for g in groups[:6])
        if not _valid_date(year, month, day) or hour > 23 or minute > 59 or second > 59:
            continue
        # Go's layouts spell the fraction ".999999999": nanoseconds, and
        # anything finer is dropped rather than refused.
        fraction = (groups[6] or "").ljust(9, "0")[:9] if groups[6] else ""
        offset = zone_minutes(groups[7]) if zoned else 0
        return Resolution(
            TIMESTAMP,
            render_timestamp(year, month, day, hour, minute, second, fraction, offset),
        )
    return None


def _parse_int(plain: str) -> int | None:
    """strconv.ParseInt(plain, 0, 64), then ParseUint on overflow.

    Base 0 means "read it as a Go literal": 0x hex, 0o octal, 0b binary, a bare
    leading zero octal, otherwise decimal. That last clause is the whole story
    for `012`.
    """
    body = plain
    sign = 1
    if body[:1] in ("+", "-"):
        sign = -1 if body[0] == "-" else 1
        body = body[1:]
    if not body:
        return None
    base = 10
    if len(body) > 1 and body[0] == "0":
        prefix = body[1].lower()
        if prefix in ("x", "o", "b"):
            base = {"x": 16, "o": 8, "b": 2}[prefix]
            body = body[2:]
        else:
            base = 8
            body = body[1:]
    if not body:
        return None
    digits = "0123456789abcdef"[:base]
    if any(character.lower() not in digits for character in body):
        return None
    value = sign * int(body, base)
    if _INT64_MIN <= value <= _INT64_MAX:
        return value
    if 0 <= value <= _UINT64_MAX:  # ParseUint takes over above MaxInt64
        return value
    return None


_FLOAT_CHARS = set("0123456789.eE+-_")


def _parse_float(text: str) -> float | None:
    """strconv.ParseFloat(text, 64), to the extent Python's float() differs.

    Two things to keep them apart. Python's float() takes the spellings "inf",
    "nan" and surrounding whitespace, which arrive here only as something
    go-yaml would have left alone; and where Go returns ErrRange for a literal
    too large to represent, `resolve()` checks `err == nil` and so does *not*
    treat it as a float at all. `1e999` is a string to go-yaml and +Inf to
    Python, so overflow has to be refused rather than passed on.
    """
    if not text or any(character not in _FLOAT_CHARS for character in text):
        return None
    try:
        value = float(text)
    except (ValueError, OverflowError):
        return None
    if value in (float("inf"), float("-inf")) or value != value:
        return None
    return value


class GoYamlV3:
    name = "go-yaml-v3"
    label = "gopkg.in/yaml.v3"

    @staticmethod
    def resolve(text: str) -> Resolution:
        first = text[0] if text else "N"
        if text and first not in _HINT_SIGN | _HINT_DIGIT | _HINT_MAP | {"."}:
            return Resolution(STR, text)
        if text in _MAP:
            return _MAP[text]
        if first in _HINT_MAP:
            # "We've already checked the map above" — nothing else is tried,
            # which is why `yes` and `off` come out as strings.
            return Resolution(STR, text)
        if first == ".":
            number = _parse_float(text)
            if number is not None:
                return Resolution(FLOAT, render_float(number))
            return Resolution(STR, text)
        if first in _HINT_DIGIT | _HINT_SIGN:
            stamp = _parse_timestamp(text)
            if stamp is not None:
                return stamp
            plain = text.replace("_", "")
            if not plain:
                return Resolution(STR, text)
            number = _parse_int(plain)
            if number is not None:
                return Resolution(INT, render_int(number))
            if _YAML_STYLE_FLOAT.match(plain):
                number = _parse_float(plain)
                if number is not None:
                    return Resolution(FLOAT, render_float(number))
        return Resolution(STR, text)
