"""The corpus is present, complete, and shaped the way the registry expects.

These tests are the tripwire for decision EL-001: if a corpus file is renamed,
moved, or dropped, the suite fails here and names the file, rather than
skipping and letting every downstream extraction stage read nothing.
"""

from pathlib import Path

import pytest

from tests.conftest import (
    CORPUS_FILES,
    INDEX_FILE,
    MASTER_LOOKUP,
    SECTION_FILES,
    deep_dive_header,
    master_lookup_header,
    require_corpus_files,
)


def test_corpus_is_complete(corpus_dir: Path) -> None:
    """Every file named in the mapping exists; the failure names all of them."""
    require_corpus_files(corpus_dir)


def test_corpus_mapping_covers_every_section() -> None:
    assert tuple(SECTION_FILES) == tuple("ABCDEFGHIJ")
    assert len(CORPUS_FILES) == 12
    assert len(set(CORPUS_FILES)) == len(CORPUS_FILES)


def test_master_lookup_has_every_section_header(corpus_dir: Path) -> None:
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    text = (corpus_dir / MASTER_LOOKUP).read_text(encoding="utf-8")
    missing = [
        master_lookup_header(section)
        for section in SECTION_FILES
        if master_lookup_header(section) not in text
    ]
    assert not missing, f"{MASTER_LOOKUP} is missing headers: {missing}"


@pytest.mark.parametrize("section", sorted(SECTION_FILES))
def test_deep_dive_has_its_section_header(corpus_dir: Path, section: str) -> None:
    filename = SECTION_FILES[section]
    require_corpus_files(corpus_dir, (filename,))
    text = (corpus_dir / filename).read_text(encoding="utf-8")
    header = deep_dive_header(section)
    assert header in text, f"{filename} does not contain {header!r}"


def test_index_is_readable(corpus_dir: Path) -> None:
    require_corpus_files(corpus_dir, (INDEX_FILE,))
    text = (corpus_dir / INDEX_FILE).read_text(encoding="utf-8")
    assert "# EVALS – SECTION DEEP DIVES" in text
