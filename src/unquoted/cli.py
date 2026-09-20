"""`unquoted` on the command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .dialects import DIALECTS
from .report import ORDER, PLAIN, QUIET, REPORTABLE, Finding, judge, judge_all
from .scan import PlainScalar, ScanError, scan_file

SUFFIXES = (".yml", ".yaml")

_COLOURS = {
    "split": "\033[31m",
    "retyped": "\033[33m",
    "rewritten": "\033[36m",
    "quiet": "\033[90m",
    "plain": "\033[90m",
}
_RESET = "\033[0m"
_DIM = "\033[90m"


def _use_colour(choice: str) -> bool:
    if choice == "always":
        return True
    if choice == "never":
        return False
    # https://no-color.org - respected because a tool that ignores it ends up
    # pasted into an issue as a screenful of escape codes.
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _paint(text: str, colour: str, enabled: bool) -> str:
    return f"{colour}{text}{_RESET}" if enabled else text


def _collect(targets: list[str]) -> list[Path]:
    """Files to scan. A directory means every .yml/.yaml under it."""
    paths: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            for suffix in SUFFIXES:
                paths.extend(sorted(path.rglob(f"*{suffix}")))
        else:
            paths.append(path)
    return paths


def _format_text(findings: list[Finding], colour: bool, show_path: bool) -> list[str]:
    lines: list[str] = []
    width = max(len(dialect.name) for dialect in DIALECTS)
    for finding in findings:
        scalar = finding.scalar
        where = f"{scalar.source}:{scalar.location}" if show_path else scalar.location
        role = "key" if scalar.is_key else "value"
        lines.append(
            f"{where}  {_paint(finding.verdict, _COLOURS[finding.verdict], colour)}"
            f"  {scalar.text}"
            f"{_paint(f'   ({role} at {scalar.path})', _DIM, colour)}"
        )
        for dialect in DIALECTS:
            resolution = finding.resolutions[dialect.name]
            lines.append(
                f"    {dialect.name:<{width}}  {resolution.tag:<9}  {resolution.value}"
            )
        lines.append("")
    return lines


def _to_json(findings: list[Finding]) -> str:
    payload = [
        {
            "file": finding.scalar.source,
            "line": finding.scalar.line,
            "column": finding.scalar.column,
            "path": finding.scalar.path,
            "role": "key" if finding.scalar.is_key else "value",
            "text": finding.scalar.text,
            "verdict": finding.verdict,
            "reason": finding.reason(),
            "resolutions": {
                name: {"tag": resolution.tag, "value": resolution.value}
                for name, resolution in finding.resolutions.items()
            },
        }
        for finding in findings
    ]
    return json.dumps(payload, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unquoted",
        description=(
            "Show what YAML's plain scalars actually become, and where PyYAML, "
            "go-yaml and js-yaml disagree."
        ),
        epilog=(
            "Exit status is 1 when anything was reported and 0 when nothing was, "
            "so this works as a CI check without a separate --check flag."
        ),
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="YAML files, or directories to search for .yml/.yaml. Default: the current directory.",
    )
    parser.add_argument(
        "-e",
        "--explain",
        metavar="TEXT",
        help="Resolve one scalar given on the command line and exit. No file needed.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Report every plain scalar, including the unsurprising ones.",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=list(ORDER),
        metavar="VERDICT",
        help=f"Report only this verdict. Repeatable. One of: {', '.join(ORDER)}.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--color",
        "--colour",
        dest="colour",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colour the verdicts (default: auto).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    colour = _use_colour(args.colour)

    if args.explain is not None:
        scalar = PlainScalar(
            text=args.explain,
            line=1,
            column=1,
            is_key=False,
            path=".",
            source="<argument>",
        )
        finding = judge(scalar)
        if args.format == "json":
            print(_to_json([finding]))
        else:
            print("\n".join(_format_text([finding], colour, show_path=False)).rstrip())
        return 1 if finding.verdict in REPORTABLE else 0

    paths = _collect(args.targets or ["."])
    findings: list[Finding] = []
    failed = False
    for path in paths:
        try:
            scalars = scan_file(path)
        except ScanError as error:
            print(f"unquoted: {path}: {error}", file=sys.stderr)
            failed = True
            continue
        findings.extend(judge_all(scalars, everything=args.all or bool(args.only)))

    if args.only:
        findings = [f for f in findings if f.verdict in args.only]
    elif not args.all:
        findings = [f for f in findings if f.verdict not in (QUIET, PLAIN)]

    if args.format == "json":
        print(_to_json(findings))
    elif findings:
        print("\n".join(_format_text(findings, colour, show_path=True)).rstrip())

    if failed:
        return 2
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
