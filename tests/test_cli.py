"""The command line: exit codes, filters and output shapes."""

from __future__ import annotations

import json

import pytest

from unquoted.cli import main

CLEAN = "name: CI\nport: 8080\nhost: example.com\n"
DIRTY = "on:\n  push: 1\nversion: 1.10\n"


@pytest.fixture
def write(tmp_path):
    def _write(source: str, name: str = "sample.yml"):
        path = tmp_path / name
        path.write_text(source)
        return path

    return _write


def test_clean_file_exits_zero_and_says_nothing(write, capsys):
    assert main([str(write(CLEAN))]) == 0
    assert capsys.readouterr().out == ""


def test_findings_exit_one(write):
    """No --check flag: the exit code is the check. A tool that needs a flag
    to be useful in CI has put the flag in the wrong place."""
    assert main([str(write(DIRTY))]) == 1


def test_unreadable_file_exits_two(write, capsys):
    assert main([str(write("a: [1,\nb: 2\n"))]) == 2
    assert "unquoted:" in capsys.readouterr().err


def test_a_broken_file_does_not_stop_the_others(write, capsys, tmp_path):
    write("a: [1,\n", "broken.yml")
    write(DIRTY, "fine.yml")
    assert main([str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "1.10" in captured.out, "the readable file should still be reported"


def test_directories_are_searched_for_yaml(write, tmp_path):
    write(DIRTY, "a.yml")
    write(DIRTY, "b.yaml")
    write("not: yaml", "c.txt")
    assert main([str(tmp_path)]) == 1


def test_json_output_is_json(write, capsys):
    main([str(write(DIRTY)), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert {item["text"] for item in payload} == {"on", "1.10"}
    assert payload[0]["resolutions"]["pyyaml"]["tag"] == "bool"
    assert payload[0]["role"] == "key"


def test_explain_needs_no_file(capsys):
    assert main(["--explain", "012"]) == 1
    out = capsys.readouterr().out
    assert "split" in out
    assert "12" in out and "10" in out


def test_explain_of_something_dull_exits_zero(capsys):
    assert main(["-e", "8080"]) == 0


def test_only_filters_to_one_verdict(write, capsys):
    main([str(write(DIRTY)), "--only", "rewritten"])
    out = capsys.readouterr().out
    assert "1.10" in out
    assert "split" not in out


def test_all_includes_the_quiet_ones(write, capsys):
    main([str(write(CLEAN)), "--all"])
    assert "8080" in capsys.readouterr().out


def test_colour_is_off_when_not_a_tty(write, capsys):
    main([str(write(DIRTY))])
    assert "\033[" not in capsys.readouterr().out


def test_colour_can_be_forced(write, capsys):
    main([str(write(DIRTY)), "--color", "always"])
    assert "\033[" in capsys.readouterr().out
