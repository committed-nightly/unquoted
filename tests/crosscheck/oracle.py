"""Run a list of scalars through the real parsers and report what they said.

The dialect modules in `unquoted/dialects/` are hand transcriptions of three
implementations' source. A transcription is a claim, and this is what checks
it: the same scalars go through PyYAML, `gopkg.in/yaml.v3` and js-yaml for
real, and their answers are compared against what the transcription predicted.

Every scalar is first put into a document and read back with our own scanner.
If it does not come back as a plain scalar with exactly the text we put in, it
is not a plain scalar in that position — `- x` or `#` or `a: b` — and it is
skipped rather than quietly tested as something else.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass(frozen=True)
class Answer:
    tag: str
    value: str


def build_document(scalars: list[str]) -> tuple[str, dict[str, str]]:
    """A document with one key per scalar, and the key -> text mapping."""
    keys = {f"k{index}": text for index, text in enumerate(scalars)}
    lines = [f"{key}: {text}" for key, text in keys.items()]
    return "\n".join(lines) + "\n", keys


def usable(scalars: list[str]) -> tuple[str, dict[str, str]]:
    """Drop anything that is not a plain scalar when written as a value."""
    from unquoted.scan import ScanError, scan

    keep: list[str] = []
    for text in scalars:
        source = f"v: {text}\n"
        try:
            found = scan(source)
        except ScanError:
            continue
        values = [s for s in found if not s.is_key]
        if len(values) == 1 and values[0].text == text:
            keep.append(text)
    return build_document(keep)


def _canonical(tag: str, raw: str) -> Answer:
    """Put an oracle's answer into the same shape the dialects produce."""
    from unquoted.dialects import render_float

    if tag == "float":
        if raw in ("inf", "-inf", "nan"):
            return Answer("float", raw)
        return Answer("float", render_float(float(raw)))
    if tag == "timestamp":
        # JavaScript's toISOString always prints exactly three fraction digits,
        # Go prints as few as it can and PyYAML prints six. Trailing zeros are
        # a formatter's business, not the parser's.
        if "." in raw:
            head, _, tail = raw.rstrip("Z").partition(".")
            tail = tail.rstrip("0")
            raw = f"{head}.{tail}Z" if tail else f"{head}Z"
        # An oracle cannot tell us whether the input was date-only; Go and
        # js-yaml both hand back a full instant either way. Midnight UTC and a
        # bare date are treated as the same answer, which is what they are.
        if raw.endswith("T00:00:00Z"):
            return Answer("timestamp", raw[: -len("T00:00:00Z")])
        return Answer("timestamp", raw)
    return Answer(tag, raw)


def ask_pyyaml(scalars: list[str]) -> dict[str, Answer]:
    """PyYAML, composed rather than loaded.

    `safe_load` cannot be used on the whole document: one bad date in it raises
    and takes every other answer with it. Composing gives the resolved tag for
    every node, and each value is then constructed on its own so that the one
    that raises is recorded as raising instead of hiding the rest.
    """
    import datetime

    import yaml

    source, keys = usable(scalars)
    root = yaml.compose(source)
    constructor = yaml.constructor.SafeConstructor()
    answers: dict[str, Answer] = {}
    for key_node, value_node in root.value:
        text = keys[key_node.value]
        tag = value_node.tag.rsplit(":", 1)[-1]
        try:
            built = constructor.construct_object(value_node, deep=True)
        except (yaml.YAMLError, ValueError, OverflowError):
            # Not just YAMLError: construct_yaml_timestamp calls datetime.date()
            # and lets the bare ValueError out, so a `try: yaml.safe_load(f)
            # except yaml.YAMLError` around a real load does not catch this one.
            answers[text] = Answer(tag, "<invalid>")
            continue
        if isinstance(built, bool):
            answers[text] = Answer(tag, "true" if built else "false")
        elif built is None:
            answers[text] = Answer(tag, "null")
        elif isinstance(built, int):
            answers[text] = Answer(tag, str(built))
        elif isinstance(built, float):
            answers[text] = _canonical("float", repr(built))
        elif isinstance(built, datetime.datetime):
            answers[text] = _canonical("timestamp", _iso(built))
        elif isinstance(built, datetime.date):
            answers[text] = Answer(tag, built.isoformat())
        else:
            answers[text] = Answer(tag, str(built))
    return answers


def _iso(moment) -> str:
    import datetime

    if moment.tzinfo is not None:
        moment = moment.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    out = moment.strftime("%Y-%m-%dT%H:%M:%S")
    if moment.microsecond:
        out += f".{moment.microsecond:06d}".rstrip("0")
    return out + "Z"


def _run(command: list[str], source: str, cwd: Path | None = None) -> dict[str, str]:
    result = subprocess.run(
        command,
        input=source,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} failed: {result.stderr[:2000]}")
    return json.loads(result.stdout)


def ask_go(scalars: list[str]) -> dict[str, Answer]:
    source, keys = usable(scalars)
    raw = _run(["go", "run", "."], source, cwd=HERE / "oracle_go")
    return {keys[key]: _canonical(*value) for key, value in raw.items()}


def ask_js(scalars: list[str]) -> dict[str, Answer]:
    """js-yaml, via its own implicit types rather than via `load`.

    The texts are still filtered through `usable()` first, so nothing is asked
    about a string that would not have been a plain scalar in a real document.
    """
    _, keys = usable(scalars)
    texts = list(keys.values())
    raw = _run(["node", str(HERE / "oracle_js.mjs")], json.dumps(texts), cwd=HERE)
    return {text: _canonical(*answer) for text, answer in zip(texts, raw)}


def have_go() -> bool:
    return shutil.which("go") is not None and (HERE / "oracle_go" / "go.sum").exists()


def have_node() -> bool:
    return shutil.which("node") is not None and (HERE / "node_modules").is_dir()


if __name__ == "__main__":  # pragma: no cover - a hand tool for poking at one scalar
    sys.path.insert(0, str(HERE.parent.parent / "src"))
    from corpus import all_scalars

    which = sys.argv[1] if len(sys.argv) > 1 else "pyyaml"
    texts = sys.argv[2:] or all_scalars()
    asker = {"pyyaml": ask_pyyaml, "go": ask_go, "js": ask_js}[which]
    for text, answer in asker(texts).items():
        print(f"{text!r:<24} {answer.tag:<10} {answer.value}")
