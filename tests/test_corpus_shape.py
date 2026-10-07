"""Structural invariants of the corpus that T3 extraction depends on.

These are not tests of our code -- there is no extraction code yet. They pin
the shape of the source so that a corpus edit which would silently corrupt
~73 records fails here instead, before EL-103 reads it.

The master lookup ends with a trailing two-column "THE MASTER LOOKUP"
cheat-sheet that belongs to no section. A section parser that does not stop at
it swallows 31 non-technique rows into J, which is exactly the extraction bug
these tests exist to catch.
"""

import re
from pathlib import Path

import pytest

from tests.conftest import MASTER_LOOKUP, SECTION_FILES, require_corpus_files

SECTION_HEADER = re.compile(r"^## ([A-J])\. ")
CHEAT_SHEET_HEADER = "## THE MASTER LOOKUP"
SEPARATOR_ROW = re.compile(r"^\|[\s:|-]+\|$")
TECHNIQUE_ID = re.compile(r"^# ([A-J]\d+) ", re.MULTILINE)
EXPECTED_COLUMNS = 6
EXPECTED_TOTAL = 73


def _lookup_rows(corpus_dir: Path) -> dict[str, list[list[str]]]:
    """Technique rows per section, excluding the trailing cheat-sheet."""
    text = (corpus_dir / MASTER_LOOKUP).read_text(encoding="utf-8")
    rows: dict[str, list[list[str]]] = {}
    section: str | None = None
    for line in text.splitlines():
        header = SECTION_HEADER.match(line)
        if header:
            section = header.group(1)
            rows[section] = []
            continue
        if line.startswith(CHEAT_SHEET_HEADER):
            section = None
            continue
        if section is None or not line.startswith("|"):
            continue
        if SEPARATOR_ROW.match(line):
            continue
        cells = line.split("|")[1:-1]
        if cells and cells[0].strip() == "Situation":
            continue
        rows[section].append(cells)
    return rows


def _technique_ids(corpus_dir: Path, section: str) -> list[str]:
    text = (corpus_dir / SECTION_FILES[section]).read_text(encoding="utf-8")
    return [i for i in TECHNIQUE_ID.findall(text) if i.startswith(section)]


@pytest.mark.parametrize("section", sorted(SECTION_FILES))
def test_lookup_row_count_matches_deep_dive(corpus_dir: Path, section: str) -> None:
    """Each section's lookup rows and deep-dive techniques agree one-to-one."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP, SECTION_FILES[section]))
    rows = _lookup_rows(corpus_dir)[section]
    ids = _technique_ids(corpus_dir, section)
    assert len(rows) == len(ids), (
        f"section {section}: {len(rows)} lookup rows but {len(ids)} deep-dive "
        f"techniques ({', '.join(ids)})"
    )


@pytest.mark.parametrize("section", sorted(SECTION_FILES))
def test_deep_dive_ids_are_sequential(corpus_dir: Path, section: str) -> None:
    require_corpus_files(corpus_dir, (SECTION_FILES[section],))
    ids = _technique_ids(corpus_dir, section)
    assert [int(i[1:]) for i in ids] == list(range(1, len(ids) + 1)), (
        f"section {section} ids are not 1..n in order: {ids}"
    )


def test_total_technique_count(corpus_dir: Path) -> None:
    require_corpus_files(corpus_dir)
    rows = _lookup_rows(corpus_dir)
    total = sum(len(r) for r in rows.values())
    assert total == EXPECTED_TOTAL, (
        f"expected {EXPECTED_TOTAL} technique rows, found {total}: "
        f"{ {s: len(r) for s, r in rows.items()} }"
    )


def test_every_row_has_six_columns(corpus_dir: Path) -> None:
    """Six columns, the sixth being `domain_scenario` per decision EL-011."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    bad = [
        (section, cells[1].strip()[:50], len(cells))
        for section, rows in _lookup_rows(corpus_dir).items()
        for cells in rows
        if len(cells) != EXPECTED_COLUMNS
    ]
    assert not bad, f"rows without exactly {EXPECTED_COLUMNS} columns: {bad}"


def test_every_example_cell_contains_a_digit(corpus_dir: Path) -> None:
    """`worked_example` must contain a digit, so every source Example must too."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    bare = [
        (section, cells[1].strip()[:50])
        for section, rows in _lookup_rows(corpus_dir).items()
        for cells in rows
        if not re.search(r"\d", cells[4])
    ]
    assert not bare, f"Example cells with no digit: {bare}"


def test_cheat_sheet_is_not_counted_as_section_j(corpus_dir: Path) -> None:
    """Regression guard: the trailing cheat-sheet must not leak into J."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    text = (corpus_dir / MASTER_LOOKUP).read_text(encoding="utf-8")
    assert CHEAT_SHEET_HEADER in text, "cheat-sheet header gone; revisit the parser"
    assert len(_lookup_rows(corpus_dir)["J"]) == len(_technique_ids(corpus_dir, "J"))
