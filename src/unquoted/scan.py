"""Find the plain scalars in a YAML document, with their positions.

Uses PyYAML's *event* stream rather than `safe_load`, for three reasons:

* `safe_load` gives back a dict, and by then the thing this tool is about has
  already happened. The events still carry the text as written.
* A ScalarEvent says whether it was plain or quoted (`style`) and whether the
  tag was implicit, so `"012"` and `!!str 012` can be left alone.
* Events carry marks, so a finding can name a line and column.

The document is scanned, not loaded, so a file PyYAML would refuse to *build*
is still reported on — which matters, because `2026-02-31` is exactly such a
file and is one of the more interesting things to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PlainScalar:
    """One unquoted, untagged scalar, as written."""

    text: str
    line: int  # 1-based
    column: int  # 1-based
    is_key: bool
    path: str  # dotted-ish route to the node, for orientation
    source: str = "<string>"  # the file it came from

    @property
    def location(self) -> str:
        return f"{self.line}:{self.column}"


class ScanError(Exception):
    """The file is not YAML we can walk at all."""


def scan(source: str, name: str = "<string>") -> list[PlainScalar]:
    """Every plain untagged scalar in every document in `source`."""
    found: list[PlainScalar] = []
    # A stack of frames describing where we are. Each is either a list index
    # counter or a mapping's "is the next scalar a key" flag.
    stack: list[list] = []

    try:
        events = list(yaml.parse(source))
    except yaml.YAMLError as error:
        raise ScanError(str(error)) from error

    for event in events:
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            kind = "map" if isinstance(event, yaml.MappingStartEvent) else "seq"
            stack.append([kind, True if kind == "map" else 0, None])
            continue
        if isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            if stack:
                stack.pop()
            # The parent only advances once the whole collection is closed.
            # Advancing at the start instead would leave a sequence's index one
            # ahead for everything nested inside its own items.
            _consume(stack, key_name=None)
            continue
        if not isinstance(event, yaml.ScalarEvent):
            continue

        is_key = bool(stack) and stack[-1][0] == "map" and stack[-1][1] is True
        plain = event.style is None and event.tag is None and event.implicit[0]
        if plain and event.value != "":
            found.append(
                PlainScalar(
                    text=event.value,
                    line=event.start_mark.line + 1,
                    column=event.start_mark.column + 1,
                    is_key=is_key,
                    path=_path(stack, event.value if is_key else None, is_key),
                    source=name,
                )
            )
        _consume(stack, key_name=event.value if is_key else None)

    return found


def _consume(stack: list[list], key_name: str | None) -> None:
    """Advance the innermost frame past one node."""
    if not stack:
        return
    frame = stack[-1]
    if frame[0] == "map":
        if frame[1] is True:
            frame[2] = key_name
            frame[1] = False
        else:
            frame[1] = True
    else:
        frame[1] += 1


def _path(stack: list[list], key: str | None, is_key: bool) -> str:
    parts: list[str] = []
    for depth, frame in enumerate(stack):
        if frame[0] == "map":
            # A mapping frame holds the key of the pair it is *currently* on.
            # For a key scalar that pair has not started yet, so the innermost
            # frame is still holding the previous sibling's key -- `on:` after
            # `name:` would otherwise come out as `name.on`.
            if is_key and depth == len(stack) - 1:
                continue
            if frame[2] is not None:
                parts.append(str(frame[2]))
        else:
            parts.append(f"[{frame[1]}]")
    if key is not None:
        parts.append(key)
    route = ""
    for part in parts:
        if part.startswith("["):
            route += part
        else:
            route = f"{route}.{part}" if route else part
    return route or "."


def scan_file(path: Path) -> list[PlainScalar]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ScanError(str(error)) from error
    return scan(source, str(path))
