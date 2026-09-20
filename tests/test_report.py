"""The verdicts: which scalars are worth telling someone about, and which are not."""

from __future__ import annotations

import pytest

from unquoted.report import PLAIN, QUIET, RETYPED, REWRITTEN, SPLIT, judge, judge_all
from unquoted.scan import scan


def verdict(text: str) -> str:
    scalars = scan(f"v: {text}\n")
    scalar = next(s for s in scalars if not s.is_key)
    assert scalar.text == text, "the corpus entry is not a plain scalar here"
    return judge(scalar).verdict


@pytest.mark.parametrize(
    "text",
    [
        "no",  # PyYAML says false, the other two say "no"
        "on",
        "012",  # 10, 10, 12 -- the one where two numbers disagree
        "1_000",
        "1e3",
        "08",
        "12:30",
        "2026-02-31",
        "2026-9-19",
        "0o12",
        "99999999999999999999",
    ],
)
def test_implementations_disagree(text):
    assert verdict(text) == SPLIT


@pytest.mark.parametrize("text", ["2026-09-19", "2026-09-19T10:30:00Z"])
def test_agreed_but_not_a_string(text):
    """A date is the case with no way back: none of `date`, `time.Time` or
    `Date` is the string that was written."""
    assert verdict(text) == RETYPED


@pytest.mark.parametrize("text", ["true", "False", "TRUE", "null", "~", "NULL"])
def test_agreed_booleans_and_nulls_are_left_alone(text):
    """Every boolean spelling that surprises anyone is a split instead --
    `yes`, `no`, `on` and `off` are PyYAML-only booleans. What is left is the
    handful everybody means, and reporting those buries everything else."""
    assert verdict(text) == QUIET


@pytest.mark.parametrize("text", ["1.10", "1.", ".5", "+1", "00", "0x1f"])
def test_agreed_number_that_does_not_read_back_the_same(text):
    assert verdict(text) == REWRITTEN


@pytest.mark.parametrize("text", ["8080", "0", "-1", "1.5", "42", "1.0"])
def test_a_number_that_stays_itself_is_not_a_finding(text):
    """The rule the tool is built on. If these start being reported, the
    output becomes a copy of the file and nobody reads it."""
    assert verdict(text) == QUIET


@pytest.mark.parametrize("text", ["Norway", "NO_PROXY", "latest", "v1.2.3", "hello"])
def test_ordinary_strings_are_silent(text):
    assert verdict(text) == PLAIN


def test_default_filter_keeps_only_the_three_reportable_verdicts():
    source = "a: 8080\nb: Norway\nc: no\nd: 1.10\ne: true\n"
    findings = judge_all(scan(source))
    assert [f.scalar.text for f in findings] == ["no", "1.10"]


def test_everything_keeps_the_quiet_ones():
    findings = judge_all(scan("a: 8080\n"), everything=True)
    assert {f.scalar.text for f in findings} == {"a", "8080"}


def test_reason_names_who_disagreed_and_what_they_said():
    scalar = next(s for s in scan("v: 012\n") if not s.is_key)
    reason = judge(scalar).reason()
    assert "pyyaml, go-yaml-v3 read it as int 10" in reason
    assert "js-yaml read it as int 12" in reason


def test_reason_for_a_rewrite_shows_both_spellings():
    scalar = next(s for s in scan("v: 1.10\n") if not s.is_key)
    assert judge(scalar).reason() == "float, and writing it back gives 1.1, not 1.10"


def test_a_key_is_judged_like_any_other_scalar():
    """`on:` in a workflow is the canonical case: a key that is a bool in
    PyYAML and a string in the other two."""
    scalar = next(s for s in scan("on:\n  push: 1\n") if s.is_key and s.text == "on")
    finding = judge(scalar)
    assert finding.verdict == SPLIT
    assert finding.resolutions["pyyaml"].tag == "bool"
    assert finding.resolutions["js-yaml"].tag == "str"
