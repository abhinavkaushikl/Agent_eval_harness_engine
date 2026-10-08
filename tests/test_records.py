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
from tests.conftest import MASTER_LOOKUP, SECTION_FILES, require_corpus_files
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


#: Sections whose records have been enriched from their deep dive, so their
#: ``source_ref`` names the deep-dive subsection rather than the master lookup.
#: One stage adds one or two letters: S13 added A and B, S14 added C and D, and
#: so on. **S17 added I and J, which completes it** -- all ten sections are
#: here, so the master-lookup branch below is now unreachable. It is kept
#: rather than deleted, because it is what would catch a record regressing to
#: a section-level citation, and because the assertion after it derives the set
#: from the records and so cannot silently go stale either way.
ENRICHED_SECTIONS: frozenset[str] = frozenset("ABCDEFGHIJ")

#: A deep-dive subsection heading, e.g. ``# I1 – CI REGRESSION GATE: ...``.
#: The corpus separates the id from the title with an en dash; the pattern
#: accepts any non-word separator so a later hyphen edit does not break the
#: sweep, and anchors on the id so ``# I1`` never matches ``# I10``.
_DEEP_DIVE_SUBSECTION = "^#+\\s*{record_number}\\b"


def test_every_record_cites_its_source(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """Skeleton records cite the lookup; enriched ones cite their own subsection.

    S10 to S12 extracted from the master lookup only, so every record cited
    ``<lookup> § <letter>``. The enrichment stages read the deep dives and
    upgrade the citation to ``<deep dive> § <id number>``, which is the whole
    point of the field: a threshold's provenance has to be precise enough to
    re-check by hand, and "section B" is not, while "§ B3" is.
    """
    for record in records:
        if record.section in ENRICHED_SECTIONS:
            expected = f"{SECTION_FILES[record.section]} § {record.id.split('_')[0]}"
        else:
            expected = f"{MASTER_LOOKUP} § {record.section}"
        assert record.source_ref == expected, record.id


def test_enriched_sections_are_the_ones_that_left_the_lookup(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """``ENRICHED_SECTIONS`` is derived from the records, so it cannot go stale.

    Without this, forgetting to add a letter after an enrichment stage would
    leave the test above asserting the *old* citation for a section that had
    moved on, and forgetting to remove one would assert a citation nobody
    wrote. Either way the guard would silently stop guarding.
    """
    moved = {
        record.section
        for record in records
        if record.source_ref != f"{MASTER_LOOKUP} § {record.section}"
    }
    assert moved == set(ENRICHED_SECTIONS)


def test_every_source_ref_resolves_in_the_corpus(
    corpus_dir: Path, records: tuple[TechniqueRecord, ...]
) -> None:
    """Every citation names a file that exists and a heading inside it.

    ``test_every_record_cites_its_source`` checks the *shape* of the string --
    that it is spelled the way the stage agreed. That is not the same as the
    citation being true. This resolves it: the file is opened, and the
    subsection heading is found in it. ``AGENT.md`` §5 is the rule being
    enforced -- "every threshold traces to a ``source_ref`` that resolves in
    ``knowledge rules/``", because an unresolvable citation is an invented
    number with extra steps.

    What this catches that nothing else does: a renamed or deleted deep-dive
    heading, a record citing ``§ I10`` when the file stops at I9, and a whole
    section file disappearing while the records keep pointing into it. All
    three leave the registry loading cleanly and every other test green.

    Reported for every record at once rather than failing on the first, the
    same reason the loader aggregates: with 73 citations, one at a time is a
    week of round trips.
    """
    require_corpus_files(corpus_dir)
    problems: list[str] = []
    text_cache: dict[str, str] = {}
    for record in records:
        filename, separator, subsection = record.source_ref.partition(" § ")
        if not separator:
            problems.append(
                f"{record.id}: source_ref {record.source_ref!r} is not "
                "'<filename> § <subsection>'"
            )
            continue
        path = corpus_dir / filename
        if not path.is_file():
            problems.append(
                f"{record.id}: source_ref names {filename!r}, which is not a file in "
                f"{corpus_dir}. Corpus filenames are declared in tests/conftest.py"
            )
            continue
        if filename not in text_cache:
            text_cache[filename] = path.read_text(encoding="utf-8")
        pattern = _DEEP_DIVE_SUBSECTION.format(record_number=re.escape(subsection))
        if not re.search(pattern, text_cache[filename], re.MULTILINE):
            problems.append(
                f"{record.id}: {filename} has no heading for {subsection!r}. The "
                "citation points at a subsection that does not exist, so the "
                "record's thresholds cannot be re-checked by hand"
            )
    assert not problems, "\n".join(problems)
