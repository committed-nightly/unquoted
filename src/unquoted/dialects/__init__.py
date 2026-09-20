"""How each YAML implementation resolves a plain scalar.

Every dialect here is a transcription of one real implementation's resolver,
not of the YAML spec. No implementation is treated as the reference, because
on the cases that matter they do not agree and the spec does not settle it:
`012` is 10 under PyYAML and go-yaml and 12 under js-yaml, and all three are
behaving as documented.

Each module cites the source file and function it was transcribed from.
`tests/crosscheck/` runs the same inputs through the real parsers and asserts
these agree; that, rather than this docstring, is what makes them trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tags, short form. `merge` is the `<<` key; it is not a value type but it is
#: resolved out of a plain scalar like everything else here, so it gets a name.
STR = "str"
INT = "int"
FLOAT = "float"
BOOL = "bool"
NULL = "null"
TIMESTAMP = "timestamp"
MERGE = "merge"
#: `=`, the "default value" key. Like `merge`, PyYAML resolves it to a tag of
#: its own and `safe_load` then refuses to construct it; the other two read both
#: as ordinary strings.
VALUE = "value"


@dataclass(frozen=True)
class Resolution:
    """What one implementation makes of one plain scalar.

    `value` is a canonical rendering chosen by *this package*, not by the
    implementation, so that two dialects agreeing on a number agree on the
    string too. Go prints 1.0 as "1" and Python as "1.0"; that is a difference
    between two languages' formatters and not a difference in what the YAML
    said, so it must not show up as a disagreement.
    """

    tag: str
    value: str

    @property
    def is_str(self) -> bool:
        return self.tag == STR


def render_int(n: int) -> str:
    return str(n)


def render_float(f: float) -> str:
    if f != f:
        return "nan"
    if f == float("inf"):
        return "inf"
    if f == float("-inf"):
        return "-inf"
    # repr() gives the shortest string that round-trips, which is the most
    # useful canonical form here: it keeps 1.1 as "1.1" rather than showing
    # the reader 1.1000000000000001 and starting an argument about floats.
    return repr(f)


#: The value used when an implementation resolves a scalar to a type it then
#: refuses to build — `2026-02-31` is a well-formed timestamp to PyYAML's
#: resolver and an exception to its constructor. Loading that file raises.
INVALID = "<invalid>"


def render_timestamp(
    year: int,
    month: int,
    day: int,
    hour: int | None = None,
    minute: int = 0,
    second: int = 0,
    micro: int = 0,
    zone: str = "",
) -> str:
    """Normalise a timestamp to one spelling so dialects can be compared.

    Two implementations that accept `2026-9-19` and `2026-09-19` have read the
    same date, and should not be reported as disagreeing about it.

    The spelling is normalised; the instant is not. An offset is kept as
    written rather than shifted to UTC, because PyYAML converts to UTC and
    drops the offset while go-yaml keeps it, and that is a difference in what
    the two hand back rather than in what the document said.
    """
    out = f"{year:04d}-{month:02d}-{day:02d}"
    if hour is None:
        return out
    out += f"T{hour:02d}:{minute:02d}:{second:02d}"
    if micro:
        out += f".{micro:06d}".rstrip("0")
    return out + zone


from .goyaml import GoYamlV3  # noqa: E402
from .jsyaml import JsYaml  # noqa: E402
from .pyyaml import PyYAML  # noqa: E402

#: Order is the order they are printed in. Oldest-behaviour first.
DIALECTS = (PyYAML, GoYamlV3, JsYaml)

BY_NAME = {d.name: d for d in DIALECTS}

__all__ = [
    "BOOL",
    "BY_NAME",
    "INVALID",
    "render_timestamp",
    "DIALECTS",
    "FLOAT",
    "INT",
    "MERGE",
    "NULL",
    "STR",
    "TIMESTAMP",
    "VALUE",
    "GoYamlV3",
    "JsYaml",
    "PyYAML",
    "Resolution",
    "render_float",
    "render_int",
]
