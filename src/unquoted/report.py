"""Deciding which plain scalars are worth telling someone about.

The rule this tool is built around: **a number that stays a number and reads
back identically is not a finding.** `port: 8080` is an integer in all three
implementations, it is an integer on the way out, and nobody was surprised. A
tool that reports it has no point of view; it is just listing the file back.

What is left after that is small and is almost always worth a look.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dialects import (
    BOOL,
    DIALECTS,
    MERGE,
    NULL,
    STR,
    TIMESTAMP,
    VALUE,
    Resolution,
)
from .scan import PlainScalar

#: The implementations disagree about the type or the value. Worst case: they
#: disagree about the value and both carry on, so the two halves of your system
#: are working from different numbers and neither has anything to report.
SPLIT = "split"

#: Every implementation agrees this is not a string, and there is no spelling
#: of the result that would give you the text back. A date is the case that
#: matters: `2026-09-19` is a `date` object in Python, a `time.Time` in Go and
#: a `Date` in JavaScript, and none of those is the string you wrote.
RETYPED = "retyped"

#: Every implementation agrees on a number, but the number does not spell the
#: same way you wrote it. `1.10` is the version that becomes 1.1.
REWRITTEN = "rewritten"

#: Reported only with --all: agreed, unremarkable, round-trips.
QUIET = "quiet"

#: A plain string everywhere. Reported only with --all.
PLAIN = "plain"

ORDER = (SPLIT, RETYPED, REWRITTEN, QUIET, PLAIN)
REPORTABLE = (SPLIT, RETYPED, REWRITTEN)

#: Types with no string-shaped identity: seeing one at all is the news.
_NO_WAY_BACK = frozenset({TIMESTAMP, MERGE, VALUE})

#: Types where all three agreeing is enough to mean it was intended.
#:
#: There are six spellings of a boolean the three implementations agree on and
#: everybody knows all of them. Every boolean spelling that *is* a surprise --
#: `yes`, `no`, `on`, `off` -- is one PyYAML alone reads as a boolean, so it
#: already comes out as a split and does not need this rule. Reporting the rest
#: cost 6,908 findings across four real repositories, and every single one of
#: them said `true` or `false`.
#:
#: Numbers do not get this, because a number's spelling carries information
#: that its value does not: `1.10` and `0644` and `08` all mean something to
#: the person who typed them and nothing to the parser.
_AGREEMENT_IS_ENOUGH = frozenset({BOOL, NULL})


@dataclass(frozen=True)
class Finding:
    scalar: PlainScalar
    verdict: str
    resolutions: dict[str, Resolution]

    @property
    def tags(self) -> list[str]:
        return [self.resolutions[dialect.name].tag for dialect in DIALECTS]

    def reason(self) -> str:
        """One line a person can act on, not a restatement of the verdict."""
        if self.verdict == SPLIT:
            groups: dict[tuple[str, str], list[str]] = {}
            for name, resolution in self.resolutions.items():
                groups.setdefault((resolution.tag, resolution.value), []).append(name)
            parts = [
                f"{', '.join(names)} read it as {tag} {value}"
                for (tag, value), names in groups.items()
            ]
            return "; ".join(parts)
        sample = self.resolutions[DIALECTS[0].name]
        if self.verdict == RETYPED:
            return f"not a string anywhere: {sample.tag} {sample.value}"
        return f"{sample.tag}, and writing it back gives {sample.value}, not {self.scalar.text}"


def judge(scalar: PlainScalar) -> Finding:
    resolutions = {dialect.name: dialect.resolve(scalar.text) for dialect in DIALECTS}
    distinct = {(r.tag, r.value) for r in resolutions.values()}

    if len(distinct) > 1:
        return Finding(scalar, SPLIT, resolutions)

    agreed = next(iter(resolutions.values()))
    if agreed.tag == STR:
        return Finding(scalar, PLAIN, resolutions)
    if agreed.tag in _NO_WAY_BACK:
        return Finding(scalar, RETYPED, resolutions)
    if agreed.tag in _AGREEMENT_IS_ENOUGH:
        return Finding(scalar, QUIET, resolutions)
    # A number. The question is whether the text survives the round trip.
    if agreed.value != scalar.text:
        return Finding(scalar, REWRITTEN, resolutions)
    return Finding(scalar, QUIET, resolutions)


def judge_all(scalars: list[PlainScalar], *, everything: bool = False) -> list[Finding]:
    findings = [judge(scalar) for scalar in scalars]
    if everything:
        return findings
    return [finding for finding in findings if finding.verdict in REPORTABLE]
