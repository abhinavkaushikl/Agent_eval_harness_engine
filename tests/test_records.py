"""The shipped registry: 73 records that still say what the corpus says.

``test_loader.py`` proves the loader reads files; this proves the *content* is
the corpus. The central test is ``test_verbatim_fields_match_the_lookup_row``,
which diffs every record's three copied-prose fields against its own
master-lookup row. CLAUDE.md section 3 forbids inventing a number, and a
record whose ``worked_example`` has drifted from its source is exactly that --
an invented figure with a citation attached. Nothing else in the suite would
notice.

The lookup row order is the authority for pairing: records sort by id, the
lookup rows run in section order, and EL-110 to EL-112 authored them one row
per record in that order. So a row inserted, deleted or reordered in the corpus
fails here by name rather than drifting silently into the wrong record.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.conftest import MASTER_LOOKUP, require_corpus_files
from tests.test_corpus_shape import EXPECTED_TOTAL, _lookup_rows

from evalloop.registry.integrity import SECTIONS, check_integrity
from evalloop.registry.loader import RECORDS_DIR, TechniqueRecord, load_records

#: The lookup's six columns, by index, for the three fields copied verbatim.
VERBATIM_COLUMNS: tuple[tuple[str, int], ...] = (
    ("anti_pattern", 3),
    ("worked_example", 4),
    ("domain_scenario", 5),
)

_ID_NUMBER = re.compile(r"^[A-J](\d+)_")


def _normalise(text: str) -> str:
    """Collapse whitespace, so a folded block scalar compares to a table cell."""
    return re.sub(r"\s+", " ", text).strip()


@pytest.fixture(scope="module")
def records() -> tuple[TechniqueRecord, ...]:
    return load_records(RECORDS_DIR)


@pytest.fixture(scope="module")
def by_section(
    records: tuple[TechniqueRecord, ...],
) -> dict[str, list[TechniqueRecord]]:
    """Records grouped by section, ordered by their id's number."""
    grouped: dict[str, list[TechniqueRecord]] = {}
    for record in records:
        grouped.setdefault(record.section, []).append(record)
    for group in grouped.values():
        group.sort(key=lambda record: int(_ID_NUMBER.match(record.id).group(1)))  # type: ignore[union-attr]
    return grouped


def test_the_skeleton_is_complete(records: tuple[TechniqueRecord, ...]) -> None:
    assert len(records) == EXPECTED_TOTAL


def test_the_registry_is_internally_consistent(
    records: tuple[TechniqueRecord, ...],
) -> None:
    assert check_integrity(records) == []


def test_every_section_is_present(by_section: dict[str, list[TechniqueRecord]]) -> None:
    assert sorted(by_section) == list(SECTIONS)


@pytest.mark.parametrize("section", SECTIONS)
def test_section_count_matches_the_lookup(
    corpus_dir: Path, by_section: dict[str, list[TechniqueRecord]], section: str
) -> None:
    """Counted against the corpus, not a hardcoded table, so neither can drift."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    rows = _lookup_rows(corpus_dir)[section]
    got = by_section[section]
    assert len(got) == len(rows), (
        f"section {section}: {len(got)} records for {len(rows)} lookup rows "
        f"({', '.join(record.id for record in got)})"
    )


@pytest.mark.parametrize("section", SECTIONS)
def test_ids_are_sequential_from_one(
    by_section: dict[str, list[TechniqueRecord]], section: str
) -> None:
    """<SECTION><N> with no gaps, matching the deep-dive numbering."""
    numbers = [
        int(_ID_NUMBER.match(record.id).group(1))  # type: ignore[union-attr]
        for record in by_section[section]
    ]
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("section", SECTIONS)
def test_verbatim_fields_match_the_lookup_row(
    corpus_dir: Path, by_section: dict[str, list[TechniqueRecord]], section: str
) -> None:
    """Why -> anti_pattern, Example -> worked_example, Domain -> domain_scenario."""
    require_corpus_files(corpus_dir, (MASTER_LOOKUP,))
    rows = _lookup_rows(corpus_dir)[section]
    for record, row in zip(by_section[section], rows, strict=True):
        for field, column in VERBATIM_COLUMNS:
            value = getattr(record, field)
            assert value is not None, f"{record.id}: {field} is null"
            assert _normalise(value) == _normalise(row[column]), (
                f"{record.id}: {field} has drifted from "
                f"{MASTER_LOOKUP} § {section}, column {column}"
            )


def test_every_domain_scenario_keeps_its_domain_prefix(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """Decision EL-011: the sixth column is copied verbatim, prefix included."""
    for record in records:
        assert record.domain_scenario is not None, f"{record.id}: domain_scenario is null"
        assert record.domain_scenario.startswith("**"), record.id


def test_every_record_cites_the_master_lookup(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """EL-110 to EL-112 extract from the lookup only; deep dives are EL-113's."""
    for record in records:
        assert record.source_ref == f"{MASTER_LOOKUP} § {record.section}", record.id
