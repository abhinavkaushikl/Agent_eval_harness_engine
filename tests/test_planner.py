"""``plan`` against all 20 fixtures, and ``PLAN.md`` §5's six sanity queries.

The fixture runner reports **which fixture and which field**, because an
assertion error on five mappings at once is unreadable and because
``CLAUDE.md`` §7.4 means a failure here is a question, not a licence to edit a
fixture.

The six sanity-query tests assert **what the planner actually does**, with each
docstring naming what ``PLAN.md`` §5 expects and where the two diverge. Three of
the six diverge, all three were reported by S17 before this module existed, and
none is papered over: a test that asserted the aspiration would fail, and the
only ways to make it pass are to change a record or a fixture, which §7.4 and
§3 forbid.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evalloop.plan.planner import Plan, plan
from evalloop.registry.loader import RECORDS_DIR, TechniqueRecord, load_records
from evalloop.registry.schema import RecordType
from evalloop.vocab import Situation, Tool
from tests.planner_fixture import PlannerFixture, load_fixture
from tests.test_planner_fixtures import BLOCKED_PATHS, LIVE_PATHS


@pytest.fixture(scope="module")
def records() -> tuple[TechniqueRecord, ...]:
    return load_records(RECORDS_DIR)


@pytest.fixture(scope="module")
def known_ids(records: tuple[TechniqueRecord, ...]) -> frozenset[str]:
    return frozenset(record.id for record in records)


def _plan_for(
    fixture: PlannerFixture, records: tuple[TechniqueRecord, ...]
) -> Plan:
    return plan(records, fixture.situations, fixture.available_tools, fixture.evidence)


def _mismatches(fixture: PlannerFixture, result: Plan) -> list[str]:
    """Every field that disagrees, named, with both sides printed."""
    problems: list[str] = []
    got_ready = [record.id for record in result.ready]
    if got_ready != list(fixture.ready):
        problems.append(
            f"ready (ORDER MATTERS)\n      planner:  {got_ready}\n"
            f"      fixture:  {list(fixture.ready)}"
        )
    for field, got, want in (
        ("pending", dict(result.pending), dict(fixture.pending)),
        (
            "unavailable",
            {key: tuple(tool.value for tool in value) for key, value in result.unavailable.items()},
            {key: tuple(value) for key, value in fixture.unavailable.items()},
        ),
        (
            "companions",
            dict(result.companions),
            {key: tuple(value) for key, value in fixture.companions.items()},
        ),
    ):
        if got == want:
            continue
        only_planner = {k: v for k, v in got.items() if k not in want}
        only_fixture = {k: v for k, v in want.items() if k not in got}
        differing = {
            k: (got[k], want[k]) for k in got.keys() & want.keys() if got[k] != want[k]
        }
        detail = []
        if only_planner:
            detail.append(f"only in planner: {only_planner}")
        if only_fixture:
            detail.append(f"only in fixture: {only_fixture}")
        if differing:
            detail.append(f"differing (planner, fixture): {differing}")
        problems.append(f"{field}\n      " + "\n      ".join(detail))
    if list(result.prohibited) != list(fixture.prohibited):
        problems.append(
            f"prohibited\n      planner:  {list(result.prohibited)}\n"
            f"      fixture:  {list(fixture.prohibited)}"
        )
    return problems


# == the fixtures are the specification ===================================


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_fixture(
    path: Path, records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    """One test per fixture, naming the field that disagrees.

    If this fails, the planner is wrong until proven otherwise. If the
    *fixture* is wrong, that is a finding for a human -- ``CLAUDE.md`` §7.4 --
    and editing it to go green is forbidden.
    """
    fixture = load_fixture(path, known_ids)
    result = _plan_for(fixture, records)
    problems = _mismatches(fixture, result)
    assert not problems, (
        f"\n{path.name} ({fixture.name}) disagrees on {len(problems)} field(s):\n\n  "
        + "\n\n  ".join(problems)
        + f"\n\nRendered plan:\n{result.render()}\n"
    )


def test_every_live_fixture_was_actually_run() -> None:
    """A guard against the glob silently matching nothing."""
    assert len(LIVE_PATHS) == 17, [path.name for path in LIVE_PATHS]


def test_a_plan_is_reproducible(
    records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    """``USER_EXPERIENCE.md`` §4 principle 7: same inputs, same plan, same render."""
    fixture = load_fixture(LIVE_PATHS[3], known_ids)
    first = _plan_for(fixture, records)
    second = _plan_for(fixture, records)
    assert first == second
    assert first.render() == second.render()


def test_plan_does_not_mutate_its_arguments(
    records: tuple[TechniqueRecord, ...],
) -> None:
    situations = [Situation.rag_answer]
    tools = [Tool.vector_store]
    evidence = {"recall_at_k_measured": True}
    plan(records, situations, tools, evidence)
    assert situations == [Situation.rag_answer]
    assert tools == [Tool.vector_store]
    assert evidence == {"recall_at_k_measured": True}


def test_a_prohibited_record_must_carry_a_reason() -> None:
    with pytest.raises(ValueError, match="prohibited with no reason"):
        Plan(
            ready=(),
            pending={},
            unavailable={},
            companions={},
            prohibited=("D1_pr_curve_never_accuracy",),
            prohibition_reasons={},
        )


# == render ===============================================================


def test_render_always_shows_all_four_states(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """§3.1: four states, always visible. "Nothing is pending" is information."""
    rendered = plan(records, [Situation.code_generation], [], {}).render()
    for state in ("READY", "PENDING", "UNAVAILABLE", "PROHIBITED"):
        assert state in rendered, rendered
    assert rendered.count("(none)") == 3, rendered


def test_render_matches_the_documented_shape(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """``TASKS.md`` S23's mock, line for line, on a plan that exercises three states."""
    rendered = plan(
        records, [Situation.two_candidates], [], {"paired_runs": 2, "discordant_pairs": 8}
    ).render()
    assert rendered == (
        "READY        B1_paired_evaluation\n"
        "PENDING      B3_mcnemar              needs discordant_pairs: 25, have 8\n"
        "             E1_per_item_diff        needs runs: 2, have 0\n"
        "UNAVAILABLE  B2_pairwise_preference  missing: llm_api\n"
        "             H4_cost_per_success     missing: cost_api\n"
        "PROHIBITED   (none)"
    )


def test_render_separates_ready_ids_with_a_middle_dot(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """Both ``USER_EXPERIENCE.md`` §3.1 and ``TASKS.md`` S23 use ``·``."""
    rendered = plan(
        records, [Situation.code_generation], [Tool.sandbox, Tool.test_runner], {}
    ).render()
    assert rendered.startswith("READY        A1_execution_based · C1_wilson_ci")


def test_render_of_every_fixture_is_stable(
    records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    for path in LIVE_PATHS:
        fixture = load_fixture(path, known_ids)
        result = _plan_for(fixture, records)
        assert result.render() == result.render(), path.name


# == PLAN.md section 5's six sanity queries ===============================
#
# Each test asserts what the planner DOES. Where that diverges from what
# PLAN.md says it should, the docstring says so and names the finding. Nothing
# below was adjusted to make a query pass.


def test_sanity_1_summarization(records: tuple[TechniqueRecord, ...]) -> None:
    """❌ ``PLAN.md``: "faithfulness, with the length check attached". NEITHER.

    Two independent reasons, both reported in ``S17-REPORT.md`` §4 (Q1):

    1. **Faithfulness is unreachable.** ``G3_faithfulness`` triggers on
       ``rag_answer`` only. The corpus scopes claim-decomposition faithfulness
       to section G, where it is entailment against *retrieved context*; no row
       of the master lookup covers entailment against a *source document*.
    2. **The length check cannot attach**, because its host is not ready. The
       ``A4 -> E3`` edge exists and is correct, but step 6 follows edges only
       out of ready records, and A4 is pending on the κ bars ``F:20`` and
       ``F:72`` state in the imperative.

    So a summarization session on a fresh repo offers nothing, which is finding
    **F2**: trust bars placed in ``requires`` read as "not enough data yet" and
    suppress the record along with its mandated companion.
    """
    result = plan(
        records,
        [Situation.summarization],
        [Tool.llm_api, Tool.llm_api_cross_family, Tool.source_doc_read],
        {},
    )
    assert result.ready == ()
    assert set(result.pending) == {"A4_judge_binary_criteria"}
    assert "judge_human_kappa_to_trust" in result.pending["A4_judge_binary_criteria"]
    assert "G3_faithfulness" not in result.pending
    assert "E3_length_controlled_win_rate" not in {r.id for r in result.ready}


def test_sanity_2_code_generation(records: tuple[TechniqueRecord, ...]) -> None:
    """✅ "execution first, judging deprioritised or excluded" -- but vacuously.

    A1 is rung 1 and first. It carries ``conflicts_with:
    [A4_judge_binary_criteria]``, so judging *would* be suppressed -- but
    **A4 never matches ``code_generation``**, so the edge never fires. Judging
    is excluded by not being selected, not by being suppressed, and the
    mechanism the query tests is never exercised.

    ``A:15`` is why: the ladder routes only open-ended text to A4.
    """
    result = plan(records, [Situation.code_generation], [Tool.sandbox, Tool.test_runner], {})
    assert [record.id for record in result.ready] == ["A1_execution_based", "C1_wilson_ci"]
    assert result.ready[0].ladder_priority == 1, "execution is the top rung"
    assert "A4_judge_binary_criteria" not in result.pending
    assert "A4_judge_binary_criteria" not in result.unavailable


def test_sanity_2b_code_generation_without_a_sandbox(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """⚠ And with no sandbox, **nothing remains** -- fixture 2's finding.

    Not "the next rung down": exactly one record triggers on
    ``code_generation``. The plan's entire content is one permission request.
    """
    result = plan(records, [Situation.code_generation], [Tool.test_runner], {})
    assert result.ready == ()
    assert dict(result.unavailable) == {"A1_execution_based": (Tool.sandbox,)}


def test_sanity_3_rag_orders_recall_before_faithfulness(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """✅ ``G:292`` and ``AGENT.md`` §5, and the only one of the six fully met."""
    result = plan(records, [Situation.rag_answer], [Tool.vector_store, Tool.llm_api], {})
    assert [record.id for record in result.ready] == [
        "G1_component_wise_eval",
        "C1_wilson_ci",
    ]
    assert "recall_at_k_measured" in result.pending["G3_faithfulness"]

    # and once recall@k is measured, faithfulness stops being blocked on it
    after = plan(
        records,
        [Situation.rag_answer],
        [Tool.vector_store, Tool.llm_api],
        {"recall_at_k_measured": True},
    )
    assert "recall_at_k_measured" not in after.pending["G3_faithfulness"]
    assert "claim_labels" in after.pending["G3_faithfulness"], "G:102's 150+ labels remain"


def test_sanity_4_rare_class(records: tuple[TechniqueRecord, ...]) -> None:
    """⚠ ``PLAN.md``: "recall ready, accuracy prohibited". Half.

    * ``D1`` is in ``prohibited`` ✅ -- but **the word "accuracy" appears
      nowhere**, because no field names what a constraint forbids (finding
      **F5**). The reason line names the record and the harm instead.
    * "recall ready" is **false at low n**: ``D1`` carries ``positives: 100``
      from ``D:34``, so recall becomes available at 100 positives, not at n=1.
    * ``D1`` lands in ``prohibited`` *and* ``ready``, because step 2 runs before
      step 4 and one record is both the prohibition and the PR-curve
      measurement. Awaiting a ruling (``S17-REPORT.md`` §4, Q4).
    """
    thin = plan(records, [Situation.rare_class], [], {})
    assert thin.prohibited == ("D1_pr_curve_never_accuracy",)
    assert thin.ready == (), "recall is NOT ready below 100 positives"
    assert "positives: 100" in thin.pending["D1_pr_curve_never_accuracy"]

    enough = plan(records, [Situation.rare_class], [], {"positives": 100})
    assert "D1_pr_curve_never_accuracy" in {record.id for record in enough.ready}
    assert enough.prohibited == ("D1_pr_curve_never_accuracy",)
    reason = enough.prohibition_reasons["D1_pr_curve_never_accuracy"]
    assert reason.startswith("rare_class: ")
    assert "97% accuracy" in reason, "D:32's own figure"
    # Finding F5, stated precisely: the PROHIBITED line's subject column holds a
    # RECORD ID where TASKS.md S23's mock holds the forbidden metric ("accuracy").
    prohibited_line = next(
        line for line in enough.render().splitlines() if line.startswith("PROHIBITED")
    )
    subject = prohibited_line[len("PROHIBITED") :].strip().split()[0]
    assert subject == "D1_pr_curve_never_accuracy"
    assert subject != "accuracy", "the mock's subject is unreachable from the schema"


def test_sanity_5_a_single_observation(records: tuple[TechniqueRecord, ...]) -> None:
    """❌ ``PLAN.md``: "only facts". Two statistics fire at n = 1.

    ``B1_paired_evaluation`` produces a paired difference over a single pair,
    and ``C6_permutation_test`` a permutation test with one permutation.
    Neither is a fact.

    **The cause is finding F8**: ``B5_ci_from_n`` carries
    ``{sample_size_stated: true}`` and **unlocks B1** -- the ordering exists, in
    ``unlocks``, which ``AGENT.md`` §3.5 never reads. So the registry knows B1
    should follow B5 and the planner fires B1 anyway.
    """
    at_n_1 = plan(records, [Situation.two_candidates], [], {"runs": 1})
    fired = {record.id for record in at_n_1.ready}
    assert "B1_paired_evaluation" in fired, (
        "asserted as the defect it is, not as the behaviour we want"
    )
    assert "B3_mcnemar" in at_n_1.pending, "the one with a threshold is held back"

    # the honest half: everything with a stated bound is pending at n = 1
    for situation in (Situation.stochastic_system, Situation.benchmark_too_good):
        thin = plan(records, [situation], [], {})
        for record in thin.ready:
            assert not record.requires, f"{record.id} fired with {dict(record.requires)}"


def test_sanity_6_techniques_needing_200_samples_are_pending_at_low_n(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """⚠ True as asked, but not what ``PLAN.md`` means by it.

    The weaker claim holds: every record carrying a ≥200 bar is pending at low
    n. ``A6_expert_human_review`` (``items: 200``) is the live case.

    ``PLAN.md`` §5 expects the answer to be "significance tests, judge
    agreement", and **those are not where the 200s are**: the only records with
    a ≥200 threshold are ``A6`` and ``A7`` (``judge_labelled_items: 5000``).
    Significance is stated as a *formula* (``C2``'s ``n ≈ 16·p(1−p)/δ²``, in
    ``rule_of_thumb``) and judge agreement as a *range* (F1's 150-200, left
    null by the range policy). So the query cannot be answered by reading
    ``requires`` at all -- ``S17-REPORT.md`` §4 (Q6).
    """
    big_bars = [
        record
        for record in records
        for value in record.requires.values()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 200
    ]
    assert {record.id for record in big_bars} == {
        "A6_expert_human_review",
        "A7_tiered_online_scoring",
    }
    for record in big_bars:
        result = plan(records, record.triggers_on_situation, list(Tool), {"items": 5})
        assert record.id in result.pending, f"{record.id} should be pending at n=5"
        assert record.id not in {ready.id for ready in result.ready}


# == the constraint records, which step 2 can only half-apply =============


def test_every_constraint_record_reaches_prohibited_when_its_situation_fires(
    records: tuple[TechniqueRecord, ...],
) -> None:
    """All three, and none of them removes anything from ``ready``.

    Step 2's "anything they prohibit leaves ready" is a **no-op against this
    registry**: what a constraint forbids is a metric, and no field names it
    (finding F5). There is nothing to remove.
    """
    constraints = [
        record for record in records if record.type is RecordType.constraint
    ]
    assert {record.id for record in constraints} == {
        "D1_pr_curve_never_accuracy",
        "D6_upper_bound_no_safe_headline",
        "F5_cross_family_panel",
    }
    for record in constraints:
        result = plan(records, record.triggers_on_situation, list(Tool), {})
        assert record.id in result.prohibited, record.id
        assert result.prohibition_reasons[record.id].endswith(record.anti_pattern)
