"""Check the transcribed dialects against the implementations they describe.

If one of these fails, the dialect module is wrong and the tool is lying about
a real parser. That is the only kind of bug in here that matters, because
everything the tool prints rests on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "crosscheck"))

from corpus import NAMED, all_scalars  # noqa: E402
from oracle import (  # noqa: E402
    ask_go,
    ask_js,
    ask_pyyaml,
    have_go,
    have_node,
)

from unquoted.dialects import GoYamlV3, JsYaml, PyYAML  # noqa: E402

#: `<<` and `=` are resolved to tags whose constructors PyYAML's safe loader
#: does not have, so there is no value to compare — only the tag. They are
#: kept in the corpus because the tag itself is the disagreement.
TAG_ONLY = {"merge", "value"}


def _compare(dialect, answers: dict) -> list[str]:
    wrong = []
    for text, actual in answers.items():
        predicted = dialect.resolve(text)
        if predicted.tag != actual.tag:
            wrong.append(f"{text!r}: tag {predicted.tag} predicted, {actual.tag} actual")
        elif actual.tag not in TAG_ONLY and predicted.value != actual.value:
            wrong.append(
                f"{text!r}: value {predicted.value!r} predicted, {actual.value!r} actual"
            )
    return wrong


def _report(wrong: list[str], total: int) -> None:
    if wrong:
        shown = "\n".join(f"  {line}" for line in wrong[:40])
        more = f"\n  ... and {len(wrong) - 40} more" if len(wrong) > 40 else ""
        pytest.fail(f"{len(wrong)} of {total} scalars mismatched:\n{shown}{more}")


def test_pyyaml_dialect_matches_pyyaml():
    scalars = all_scalars()
    answers = ask_pyyaml(scalars)
    assert len(answers) > 2000, "corpus collapsed; the scanner filter is too strict"
    _report(_compare(PyYAML, answers), len(answers))


@pytest.mark.skipif(not have_go(), reason="go toolchain or module cache unavailable")
def test_go_dialect_matches_go_yaml_v3():
    answers = ask_go(all_scalars())
    _report(_compare(GoYamlV3, answers), len(answers))


@pytest.mark.skipif(not have_node(), reason="node or js-yaml unavailable")
def test_js_dialect_matches_js_yaml():
    answers = ask_js(all_scalars())
    _report(_compare(JsYaml, answers), len(answers))


def test_named_cases_survive_the_scalar_filter():
    """The handwritten corpus is the part that pins the docstrings' claims.

    It is easy for `usable()` to quietly drop one and leave a claim untested,
    so the ones that must be there are named.
    """
    answers = ask_pyyaml(NAMED)
    for text in ("no", "012", "1_000", "12:30", "2026-02-31", "1e3", "08", "<<"):
        assert text in answers, f"{text!r} was filtered out of the corpus"
