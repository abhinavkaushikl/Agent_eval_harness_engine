"""The seven cross-record rules, one test each, each violating only its own rule.

``check_integrity`` is the gate every authoring stage from EL-110 to EL-117
runs, and the only thing that catches a one-character typo in a 73-record
cross-reference graph. So each rule here gets a hand-built record set that
violates **exactly** that rule -- ``_only`` asserts a single problem, which
fails both when a rule misses its defect and when it reports a second one it
should not. The clean-set test is the other half: it fails if any rule fires on
a correct registry.

Records are built in code rather than loaded from fixture files: these are
defects in the *graph*, and several of them (a duplicate id, a section the
loader's own regex would allow) are clearer as two objects than as two files.
"""

from __future__ import annotations

import pytest

from evalloop.registry.integrity import CROSS_REFERENCE_FIELDS, SECTIONS, check_integrity
from evalloop.registry.loader import RECORDS_DIR, RECORD_SUFFIX, load_records
from evalloop.registry.schema import Cost, Gate, RecordType, TechniqueRecord
from evalloop.vocab import Situation, Tool


def _record(
    record_id: str = "A1_execution_based",
    *,
    section: str | None = None,
    record_type: RecordType = RecordType.grader,
    ladder_priority: int | None = 1,
    companion_checks: tuple[str, ...] = (),
    unlocks: tuple[str, ...] = (),
    conflicts_with: tuple[str, ...] = (),
    name: str | None = None,
) -> TechniqueRecord:
    """A record that violates nothing, so a test's override is the only defect.

    ``section`` defaults to the id's own section letter and ``name`` to the id,
    so rules 2 and 3 stay quiet unless a test is about them.
    """
    return TechniqueRecord(
        id=record_id,
        section=record_id[0] if section is None else section,
        name=record_id if name is None else name,
        type=record_type,
        triggers_on_situation=(Situation.code_generation,),
        required_signals=("the output runs",),
        required_tools=(Tool.sandbox,),
        ladder_priority=ladder_priority,
        requires={},
        produces=("execution_match",),
        gates=Gate.absolute,
        companion_checks=companion_checks,
        unlocks=unlocks,
        conflicts_with=conflicts_with,
        analysis_cost=Cost.low,
        capture_cost=Cost.medium,
        anti_pattern="String match marks correct-but-different SQL as wrong",
        worked_example="200 items: exact-match 41%, execution-match 68%",
        domain_scenario=None,
        rule_of_thumb=None,
        source_ref="A-choosing-how-to-grade.md § A1",
        extraction_notes=None,
    )


def _non_grader(
    record_id: str = "C1_wilson_ci",
    *,
    record_type: RecordType = RecordType.statistic,
    section: str | None = None,
    companion_checks: tuple[str, ...] = (),
    unlocks: tuple[str, ...] = (),
    conflicts_with: tuple[str, ...] = (),
    name: str | None = None,
) -> TechniqueRecord:
    """A non-grader, which therefore carries no rung. Also clean by default."""
    return _record(
        record_id,
        section=section,
        record_type=record_type,
        ladder_priority=None,
        companion_checks=companion_checks,
        unlocks=unlocks,
        conflicts_with=conflicts_with,
        name=name,
    )


def _referring(field: str, *values: str, record_id: str = "A1_execution_based") -> TechniqueRecord:
    """A record whose ``field`` holds ``values``, so one test covers all three.

    Written as a dispatch rather than ``**{field: values}`` because the keyword
    names are typed on ``_record`` and a dict unpacking throws that away.
    """
    if field == "companion_checks":
        return _record(record_id, companion_checks=values)
    if field == "unlocks":
        return _record(record_id, unlocks=values)
    if field == "conflicts_with":
        return _record(record_id, conflicts_with=values)
    raise AssertionError(f"not a cross-reference field: {field!r}")


def _only(*records: TechniqueRecord) -> str:
    """The single problem these records must produce."""
    problems = check_integrity(records)
    assert len(problems) == 1, f"expected exactly one problem, got {problems}"
    return problems[0]


# -- rule 0: a clean registry is silent -----------------------------------


def _clean_registry() -> tuple[TechniqueRecord, ...]:
    """Five records, every cross-reference field exercised and all resolving."""
    return (
        _record("A1_execution_based", companion_checks=("C1_wilson_ci",), unlocks=("E1_per_item_diff",)),
        _record("A2_end_state_verification", ladder_priority=2, conflicts_with=("A4_judge_binary",)),
        _record("A4_judge_binary", ladder_priority=4, companion_checks=("C1_wilson_ci",)),
        _non_grader("C1_wilson_ci"),
        _non_grader("E1_per_item_diff", record_type=RecordType.diagnostic),
    )


def test_a_clean_registry_has_no_problems() -> None:
    assert check_integrity(_clean_registry()) == []


def test_no_records_at_all_is_clean() -> None:
    """Vacuously true, and the state the shipped registry is in until EL-110."""
    assert check_integrity(()) == []


def test_an_iterator_is_accepted() -> None:
    """The records are consumed twice internally, so a generator must survive."""
    assert check_integrity(record for record in _clean_registry()) == []


# -- rule 1: duplicate ids -------------------------------------------------


def test_duplicate_ids_are_reported() -> None:
    problem = _only(
        _record("A1_execution_based", name="Execution-based grading"),
        _record("A1_execution_based", name="Execution match"),
    )
    assert problem.startswith("A1_execution_based: duplicate id: ")
    assert "2 records share it" in problem
    assert "'Execution-based grading'" in problem
    assert "'Execution match'" in problem


def test_a_duplicated_id_is_reported_once_not_once_per_copy() -> None:
    """Three copies, one line: the defect is the id, not each record."""
    problem = _only(*(_record("A1_execution_based") for _ in range(3)))
    assert "3 records share it" in problem


def test_two_separate_duplicate_ids_are_two_problems() -> None:
    problems = check_integrity(
        (
            _record("A1_execution_based"),
            _record("A1_execution_based"),
            _non_grader("C1_wilson_ci"),
            _non_grader("C1_wilson_ci"),
        )
    )
    assert len(problems) == 2
    assert problems[0].startswith("A1_execution_based: duplicate id")
    assert problems[1].startswith("C1_wilson_ci: duplicate id")


def test_a_duplicated_id_still_resolves_as_a_reference() -> None:
    """Only the duplicate is reported -- the reference to it is not also dangling."""
    problem = _only(
        _record("A1_execution_based"),
        _record("A1_execution_based"),
        _non_grader("C1_wilson_ci", companion_checks=("A1_execution_based",)),
    )
    assert "duplicate id" in problem


# -- rule 2: section outside A-J -------------------------------------------


def test_a_section_outside_a_to_j_is_reported() -> None:
    problem = _only(_record("A1_execution_based", section="K"))
    assert problem.startswith("A1_execution_based: section: 'K' is not a section letter")
    assert ", ".join(SECTIONS) in problem


def test_an_empty_section_is_reported() -> None:
    """``'' in 'ABCDEFGHIJ'`` is true, which is why the check is not a substring test."""
    assert "section: '' is not a section letter" in _only(_record(section=""))


def test_a_two_letter_section_is_reported() -> None:
    """``'AB' in 'ABCDEFGHIJ'`` is true for the same reason."""
    assert "section: 'AB' is not a section letter" in _only(_record(section="AB"))


def test_a_lowercase_section_is_reported() -> None:
    assert "section: 'a' is not a section letter" in _only(_record(section="a"))


@pytest.mark.parametrize("section", SECTIONS)
def test_every_section_letter_is_accepted(section: str) -> None:
    assert check_integrity((_record(f"{section}1_a_technique"),)) == []


# -- rule 3: id prefix disagreeing with the section field ------------------


def test_an_id_prefix_disagreeing_with_the_section_is_reported() -> None:
    problem = _only(_record("A1_execution_based", section="B"))
    assert problem.startswith("A1_execution_based: section: 'B' disagrees with")
    assert "'A'" in problem
    assert "source_ref" in problem, "the message must say which of the two to trust"


def test_an_out_of_range_section_is_not_also_reported_as_a_prefix_clash() -> None:
    """One defect, one line. Rule 2's message already says what to set."""
    assert "disagrees with" not in _only(_record("A1_execution_based", section="K"))


# -- rules 4 and 5: the ladder rung ----------------------------------------


def test_a_grader_without_a_rung_is_reported_once_the_ladder_has_started() -> None:
    """All-or-nothing: A2 carries a rung, so A1's null is now a half-built ladder."""
    problem = _only(
        _record("A1_execution_based", ladder_priority=None),
        _record("A2_end_state_verification", ladder_priority=2),
    )
    assert problem.startswith("A1_execution_based: ladder_priority: is null but other graders")
    assert "1 execution" in problem and "5 human" in problem


def test_no_grader_runged_at_all_is_silent() -> None:
    """The EL-110 state: sections A-C authored, the ladder deferred to EL-113.

    The strict form of this rule ("every grader has a rung") made EL-110's two
    requirements -- ``ladder_priority: null`` throughout *and* an empty
    ``check_integrity()`` -- impossible to satisfy at once, and asserted
    something ``CLAUDE.md`` section 6 never says. See the module docstring.
    """
    assert check_integrity(
        (
            _record("A1_execution_based", ladder_priority=None),
            _record("A2_end_state_verification", ladder_priority=None),
            _record("A4_judge_binary", ladder_priority=None),
            _non_grader("C1_wilson_ci"),
        )
    ) == []


def test_a_non_grader_rung_does_not_start_the_ladder() -> None:
    """Only a *grader* carrying a rung counts, and rule 5 owns the other case."""
    record = _record("C1_wilson_ci", record_type=RecordType.grader, ladder_priority=3)
    object.__setattr__(record, "type", RecordType.statistic)
    problems = check_integrity((record, _record("A1_execution_based", ladder_priority=None)))
    assert len(problems) == 1
    assert problems[0].startswith("C1_wilson_ci: ladder_priority:")


def test_every_grader_unrunged_but_one_reports_all_the_others() -> None:
    problems = check_integrity(
        (
            _record("A1_execution_based", ladder_priority=1),
            _record("A2_end_state_verification", ladder_priority=None),
            _record("A3_normalised_exact_match", ladder_priority=None),
        )
    )
    assert len(problems) == 2
    assert problems[0].startswith("A2_end_state_verification: ladder_priority:")
    assert problems[1].startswith("A3_normalised_exact_match: ladder_priority:")


def test_a_non_grader_with_a_ladder_priority_is_reported() -> None:
    """The schema already blocks this, so the test has to reach past it.

    ``schema._check_ladder_priority`` raises on a non-grader carrying a rung,
    so no record file can express this defect. The rule is defence in depth,
    and ``object.__setattr__`` on the frozen dataclass is the only way to build
    a violating record -- which is itself the evidence that EL-107 covers it.
    """
    record = _record("C1_wilson_ci", record_type=RecordType.grader, ladder_priority=3)
    object.__setattr__(record, "type", RecordType.statistic)
    problem = _only(record)
    assert problem.startswith("C1_wilson_ci: ladder_priority: is 3 but type is statistic")
    assert "Clear it to null" in problem


@pytest.mark.parametrize(
    "record_type",
    [kind for kind in RecordType if kind is not RecordType.grader],
)
def test_a_non_grader_without_a_rung_is_clean(record_type: RecordType) -> None:
    assert check_integrity((_non_grader("C1_wilson_ci", record_type=record_type),)) == []


@pytest.mark.parametrize("rung", [1, 2, 3, 4, 5])
def test_a_grader_on_any_rung_is_clean(rung: int) -> None:
    assert check_integrity((_record("A1_execution_based", ladder_priority=rung),)) == []


# -- rule 6: self-reference ------------------------------------------------


@pytest.mark.parametrize(
    ("field", "clause"),
    [
        ("companion_checks", "cannot be its own companion"),
        ("unlocks", "cannot unlock itself"),
        ("conflicts_with", "cannot conflict with itself"),
    ],
)
def test_a_self_reference_is_reported(field: str, clause: str) -> None:
    problem = _only(_referring(field, "A1_execution_based"))
    assert problem.startswith(f"A1_execution_based: {field}: lists its own id")
    assert clause in problem
    assert "'A1_execution_based'" in problem


def test_the_three_fields_are_the_schema_fields() -> None:
    """If a fourth cross-reference field is ever added, this test names it."""
    assert CROSS_REFERENCE_FIELDS == ("companion_checks", "unlocks", "conflicts_with")


def test_a_self_reference_is_not_also_an_unknown_reference() -> None:
    problem = _only(_record("A1_execution_based", unlocks=("A1_execution_based",)))
    assert "is not a record id" not in problem


# -- rule 7: unknown reference ---------------------------------------------


@pytest.mark.parametrize(
    ("field", "consequence"),
    [
        ("companion_checks", "the companion is silently never reported"),
        ("unlocks", "nothing is unlocked"),
        ("conflicts_with", "the conflict never fires"),
    ],
)
def test_an_unknown_reference_is_reported(field: str, consequence: str) -> None:
    problem = _only(_referring(field, "Z9_nonexistent"))
    assert problem.startswith(f"A1_execution_based: {field}: 'Z9_nonexistent' is not a record id")
    assert consequence in problem, "the message must say what the dangling edge costs"


def test_an_unknown_reference_suggests_the_closest_loaded_id() -> None:
    """The typo this rule exists to catch is one character."""
    problem = _only(
        _record("A1_execution_based", companion_checks=("C1_wilson_c1",)),
        _non_grader("C1_wilson_ci"),
    )
    assert "Closest loaded id: C1_wilson_ci" in problem


def test_an_unknown_reference_with_nothing_close_says_so() -> None:
    problem = _only(
        _record("A1_execution_based", companion_checks=("J5_vendor_claims",)),
        _non_grader("C1_wilson_ci"),
    )
    assert "No loaded id is close to it" in problem
    assert "section file" in problem, "the likely cause is an unextracted section"


def test_several_unknown_references_in_one_field_are_all_reported() -> None:
    problems = check_integrity(
        (_record("A1_execution_based", companion_checks=("Z9_one", "Z8_two")),)
    )
    assert len(problems) == 2
    assert "'Z9_one'" in problems[0]
    assert "'Z8_two'" in problems[1], "within one field, the record's own order is kept"


def test_a_dangling_reference_is_found_in_every_field_at_once() -> None:
    problems = check_integrity(
        (
            _record(
                "A1_execution_based",
                companion_checks=("Z9_a",),
                unlocks=("Z9_b",),
                conflicts_with=("Z9_c",),
            ),
        )
    )
    assert len(problems) == 3
    assert "companion_checks" in problems[0]
    assert "unlocks" in problems[1]
    assert "conflicts_with" in problems[2], "fields are reported in schema order"


# -- ordering and determinism (CLAUDE.md 7.8) ------------------------------


def _messy_registry() -> tuple[TechniqueRecord, ...]:
    return (
        _non_grader("C1_wilson_ci", companion_checks=("Z9_missing",)),
        # B1 below carries rung 1, which starts the ladder and makes A1's null a defect.
        _record("A1_execution_based", ladder_priority=None, unlocks=("A1_execution_based",)),
        # Only one copy has the bad section, so B1 shows rule 1 then rule 2 --
        # two records sharing an id are still checked independently.
        _record("B1_paired_evaluation", section="K"),
        _record("B1_paired_evaluation"),
    )


def test_problems_are_sorted_by_record_id_then_rule() -> None:
    problems = check_integrity(_messy_registry())
    assert [problem.split(":")[0] for problem in problems] == [
        "A1_execution_based",
        "A1_execution_based",
        "B1_paired_evaluation",
        "B1_paired_evaluation",
        "C1_wilson_ci",
    ]
    assert "ladder_priority" in problems[0], "rule 4 before rule 6 within one record"
    assert "lists its own id" in problems[1]
    assert "duplicate id" in problems[2], "rule 1 before rule 2 within one record"
    assert "is not a section letter" in problems[3]


def test_the_result_does_not_depend_on_the_input_order() -> None:
    records = _messy_registry()
    expected = check_integrity(records)
    assert check_integrity(tuple(reversed(records))) == expected
    assert check_integrity(records[2:] + records[:2]) == expected


def test_checking_twice_gives_the_same_list() -> None:
    records = _messy_registry()
    assert check_integrity(records) == check_integrity(records)


def test_every_problem_names_the_record_it_belongs_to() -> None:
    for problem in check_integrity(_messy_registry()):
        record_id, _, detail = problem.partition(": ")
        assert record_id
        assert detail.strip()


# -- the shipped registry --------------------------------------------------


def test_the_shipped_registry_directory_exists() -> None:
    """Checked separately so a vanished directory fails loudly, not trivially.

    ``test_the_shipped_registry_is_clean`` passes on an empty directory,
    because the records are not authored until EL-110. That tolerance would
    also swallow the directory being deleted *after* the 73 records land -- the
    silent pass ``conftest.require_fixture_dir`` exists to stop. The directory
    is therefore tracked (``records/.gitkeep``) and its absence is its own
    failure.
    """
    assert RECORDS_DIR.is_dir(), (
        f"the shipped registry directory is missing: {RECORDS_DIR}. It is tracked by "
        "evalloop/registry/records/.gitkeep; restore it rather than re-pointing the test."
    )


def test_the_shipped_registry_is_clean() -> None:
    """Trivially true today; the real gate from EL-110 onward.

    ``RECORDS_DIR`` holds no record file yet -- EL-110 to EL-112 author the 73
    records into it -- so today this asserts the empty registry is clean. Once
    a single section file lands, the same test loads it and checks the graph,
    with no edit here.
    """
    if not any(RECORDS_DIR.glob(f"*{RECORD_SUFFIX}")):
        assert check_integrity(()) == []
        return
    assert check_integrity(load_records(RECORDS_DIR)) == []
