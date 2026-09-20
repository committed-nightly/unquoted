"""The scanner: what counts as a plain scalar, and where it is."""

from __future__ import annotations

import pytest

from unquoted.scan import ScanError, scan


def texts(source: str) -> list[str]:
    return [scalar.text for scalar in scan(source)]


def test_quoted_scalars_are_not_reported():
    """Quoting is the fix this tool exists to recommend, so it has to see it."""
    found = texts("a: '012'\nb: \"no\"\nc: 012\n")
    assert found == ["a", "b", "c", "012"]


def test_explicitly_tagged_scalars_are_left_alone():
    """`!!str 012` is someone who has already decided. Nothing to report."""
    assert "012" not in texts("a: !!str 012\n")


def test_block_scalars_are_not_plain():
    assert texts("a: |\n  no\nb: >\n  012\n") == ["a", "b"]


def test_keys_are_scanned_too():
    scalars = {scalar.text: scalar for scalar in scan("on:\n  push: 1\n")}
    assert scalars["on"].is_key is True
    assert scalars["push"].is_key is True


def test_empty_values_are_skipped():
    """`foo:` is null everywhere, but there is no text anyone wrote."""
    assert texts("foo:\nbar: 1\n") == ["foo", "bar", "1"]


def test_positions_are_one_based():
    scalar = next(s for s in scan("a: 1\nb: 012\n") if s.text == "012")
    assert (scalar.line, scalar.column) == (2, 4)


def test_path_of_a_key_is_not_its_previous_sibling():
    """A mapping frame holds the key of the pair it is on, which for a key
    scalar is still the last one. `on` after `name` must not be `name.on`."""
    scalars = {s.text: s for s in scan("name: CI\non:\n  push: 1\n") if s.is_key}
    assert scalars["on"].path == "on"
    assert scalars["push"].path == "on.push"


def test_sequence_indexes_do_not_run_ahead_inside_an_item():
    source = "steps:\n  - uses: a\n  - uses: b\n"
    paths = [s.path for s in scan(source) if s.text in ("a", "b")]
    assert paths == ["steps[0].uses", "steps[1].uses"]


def test_flow_collections_are_walked():
    scalars = {s.text: s.path for s in scan("a: {b: [1, 2]}\n")}
    assert scalars["1"] == "a.b[0]"
    assert scalars["2"] == "a.b[1]"


def test_multiple_documents():
    assert texts("a: 1\n---\nb: 2\n") == ["a", "1", "b", "2"]


def test_broken_yaml_raises_scan_error():
    with pytest.raises(ScanError):
        scan("a: [1,\nb: 2\n")


def test_a_document_pyyaml_cannot_load_is_still_scanned():
    """The point of scanning rather than loading.

    `yaml.safe_load` of this raises ValueError and hands back nothing at all,
    which is exactly when a person most wants to be told which scalar did it.
    """
    import yaml

    source = "released: 2026-02-31\n"
    with pytest.raises(ValueError):
        yaml.safe_load(source)
    assert "2026-02-31" in texts(source)
