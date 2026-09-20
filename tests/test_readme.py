"""Run every ```console block in the README and check it prints what it says.

A README is a claim about behaviour like any other. These blocks are the first
thing anyone reads, and they are exactly the thing that rots first.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

README = Path(__file__).parent.parent / "README.md"
BLOCK = re.compile(r"```console\n(.*?)```", re.S)


def blocks() -> list[str]:
    return BLOCK.findall(README.read_text())


def split_commands(block: str) -> list[tuple[str, str]]:
    """A console block into (command, expected output) pairs."""
    pairs: list[tuple[str, str]] = []
    command: str | None = None
    output: list[str] = []
    for line in block.splitlines():
        if line.startswith("$ "):
            if command is not None:
                pairs.append((command, "\n".join(output).strip("\n")))
            command = line[2:]
            output = []
        elif command is not None:
            output.append(line)
    if command is not None:
        pairs.append((command, "\n".join(output).strip("\n")))
    return pairs


def test_the_readme_has_console_blocks():
    assert len(blocks()) >= 3, "the README examples have gone missing"


@pytest.mark.parametrize("index", range(len(blocks())))
def test_readme_block(index, tmp_path):
    """`cat foo` in a block writes the file the next command reads.

    That is how the release.yml example stays honest: the file in the README is
    the file the tool is run against, not a separate copy that drifted.
    """
    for command, expected in split_commands(blocks()[index]):
        argv = shlex.split(command)
        if argv[0] == "cat":
            (tmp_path / argv[1]).write_text(expected + "\n")
            continue
        assert argv[0] == "unquoted", f"unexpected command in README: {command}"
        result = subprocess.run(
            [sys.executable, "-m", "unquoted", *argv[1:]],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        actual = result.stdout.strip("\n")
        assert actual == expected, (
            f"README block {index} is out of date.\n"
            f"  $ {command}\n--- README says ---\n{expected}\n"
            f"--- actually prints ---\n{actual}"
        )
