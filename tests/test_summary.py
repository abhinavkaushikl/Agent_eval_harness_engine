"""The summary renderer: the two common cases read well, and the numbers obey the rules.

Three scenarios are built from the real planner and committed as golden files, so a byte change in
the rendered output is caught and can be diffed. The empty-plan and clean-run cases come first,
because on day one they are the common outcomes (S23-REPORT §3), not the edge cases.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.memory.case import (
    CaseKind,
    CaseResult,
    FailureClass,
    OracleConfidence,
    Timeout,
    TimeoutCap,
    Verdict,
)
from evalloop.plan.planner import plan
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.report.summary import Session, format_rate, render_summary
from evalloop.vocab import Situation, Tool
from tests.conftest import REPORT_FIXTURES_DIR, require_fixture_dir

RECORDS = load_records(RECORDS_DIR)
GOLDEN = REPORT_FIXTURES_DIR
_H = "a" * 64


def _case(
    case_id: str,
    verdict: Verdict = Verdict.passed,
    failure: FailureClass | None = None,
    *,
    confidence: OracleConfidence = OracleConfidence.high,
    reason: str | None = None,
    timeout: Timeout | None = None,
    run: str = "run-003",
) -> CaseResult:
    return CaseResult(
        run_id=run,
        record_id="A1_execution_based",
        case_id=case_id,
        case_kind=CaseKind.generated,
        artifact_id="src/pricing.py",
        oracle_id=f"tests/test_pricing.py::{case_id}",
        oracle_confidence=confidence,
        ladder_rung=1,
        verdict=verdict,
        failure_class=failure,
        timeout=timeout,
        inconclusive_reason=reason,
        score=None,
        evidence=None,
        artifact_hash=_H,
        oracle_hash=_H,
        reused_from=None,
        seed=None,
        cost_usd=None,
        duration_seconds=0.1,
    )


def _empty() -> Session:
    """A dead situation (``classification`` reaches no record): the empty-plan common case."""
    return Session(
        run_id="run-001",
        situations=((Situation.classification, 0.80),),
        plan=plan(RECORDS, [Situation.classification], [], {}),
    )


def _clean() -> Session:
    """Ready techniques, every case passed: the nothing-found common case."""
    return Session(
        run_id="run-002",
        situations=((Situation.code_generation, 0.90),),
        plan=plan(RECORDS, [Situation.code_generation], [Tool.sandbox, Tool.test_runner], {}),
        cases=(_case("c1"), _case("c2"), _case("c3")),
    )


def _rich() -> Session:
    """Mixed verdicts, a pending queue, a prohibition, and flips in both directions."""
    hung = Timeout(TimeoutCap.wall_clock, 10.0)
    cases = (
        _case("c1"),
        _case("c2"),
        _case("c3", Verdict.failed, FailureClass.wrong_result),
        _case("c4", Verdict.failed, FailureClass.timeout, timeout=hung),
        _case("c5", Verdict.inconclusive, reason="network egress was refused"),
    )
    prior = (
        _case("c3", run="run-prev"),  # passed before, failed now -> regression
        _case("c2", Verdict.failed, FailureClass.wrong_result, run="run-prev"),  # failed before, passed now -> improvement
    )
    return Session(
        run_id="run-003",
        situations=((Situation.code_generation, 0.90), (Situation.rare_class, 0.55)),
        plan=plan(
            RECORDS,
            [Situation.code_generation, Situation.stochastic_system, Situation.rare_class],
            [Tool.sandbox, Tool.test_runner],
            {},
        ),
        cases=cases,
        prior_run_id="run-prev",
        prior_cases=prior,
        cost_usd=Decimal("0.0123"),
        intent="add a discount helper",
    )


SCENARIOS = {"empty": _empty, "clean": _clean, "rich": _rich}


# -- golden files ----------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_matches_its_golden_file(name: str) -> None:
    rendered = render_summary(SCENARIOS[name]())
    golden = require_fixture_dir(GOLDEN) / f"{name}.md"
    assert golden.is_file(), f"missing golden {golden}; regenerate with scripts, then inspect before committing"
    assert rendered == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_is_byte_stable(name: str) -> None:
    session = SCENARIOS[name]()
    assert render_summary(session) == render_summary(session)


# -- the six sections, in order, always present ----------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_six_sections_are_present_in_order(name: str) -> None:
    rendered = render_summary(SCENARIOS[name]())
    headers = [
        "## 1. What you built",
        "## 2. What was evaluated and how",
        "## 3. Findings",
        "## 4. What is not yet answerable, and what would unlock it",
        "## 5. What was prohibited, and why",
        "## 6. Cost",
    ]
    positions = [rendered.index(h) for h in headers]
    assert positions == sorted(positions)


# -- the empty-plan case reads well, not as a broken scoreboard -------------------------


def test_the_empty_plan_reads_as_an_honest_account() -> None:
    rendered = render_summary(_empty())
    assert "No technique applied to the inferred situation(s), so nothing was evaluated." in rendered
    assert "Nothing was evaluated, so there are no findings." in rendered
    assert "Nothing is waiting on more evidence or a missing tool." in rendered
    assert "Nothing was prohibited here." in rendered
    assert "%" not in rendered  # no rate at all, so certainly no bare one


# -- a rate never appears without its interval -----------------------------------------


def test_format_rate_raises_without_a_conclusive_case() -> None:
    with pytest.raises(ValueError, match="conclusive case"):
        format_rate(0, 0)


def test_format_rate_always_carries_the_interval() -> None:
    assert format_rate(7, 5) == "58.3% [32.0, 80.7]"  # matches EL-014's own illustration
    assert format_rate(3, 0) == "100.0% [43.9, 100.0]"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_no_rendered_rate_is_shown_without_its_interval(name: str) -> None:
    rendered = render_summary(SCENARIOS[name]())
    if "## 3. Findings" not in rendered:
        return
    findings = rendered.split("## 3. Findings", 1)[1].split("\n## ", 1)[0]
    # A rendered rate is a finding line that begins "- <number>%"; prose quotes (e.g. a prohibition
    # reason that says "97% accuracy") are not rates the renderer produced, and are not in §3.
    for line in findings.splitlines():
        if line.startswith("- ") and "%" in line:
            assert "[" in line and "]" in line, f"a bare percentage leaked: {line!r}"


# -- oracle confidence, and inconclusive apart from failed -----------------------------


def test_a_low_oracle_looks_low() -> None:
    session = Session(
        run_id="run-low",
        situations=((Situation.code_generation, 0.9),),
        plan=plan(RECORDS, [Situation.code_generation], [Tool.sandbox, Tool.test_runner], {}),
        cases=(_case("c1", confidence=OracleConfidence.low),),
    )
    rendered = render_summary(session)
    assert "LOW oracle — generated, not ground truth" in rendered
    assert "| A1_execution_based | 1 (execution) | LOW |" in rendered


def test_inconclusive_is_shown_apart_from_failed() -> None:
    rendered = render_summary(_rich())
    findings = rendered.split("## 3. Findings")[1].split("## 4.")[0]
    # The failure breakdown lists classes, and a timeout among them (EL-014), but never 'inconclusive'.
    assert "failed 2: wrong_result 1, timeout 1 (wall_clock)" in findings
    assert "· inconclusive 1" in findings
    assert "inconclusive: src/pricing.py — network egress was refused" in findings


def test_the_inconclusive_count_is_shown_even_when_zero() -> None:
    assert "· inconclusive 0" in render_summary(_clean())


# -- flips in both directions ----------------------------------------------------------


def test_per_item_flips_are_shown_in_both_directions() -> None:
    findings = render_summary(_rich()).split("## 3. Findings")[1]
    assert "Regressions (1):" in findings and "[c3] (A1_execution_based): passed → failed/wrong_result" in findings
    assert "Improvements (1):" in findings and "[c2] (A1_execution_based): failed/wrong_result → passed" in findings


# -- section 4 reuses the planner's own reason strings ---------------------------------


def test_section_four_shows_the_planners_reasons_verbatim() -> None:
    session = _rich()
    rendered = render_summary(session)
    for rid, reason in session.plan.pending.items():
        assert reason in rendered  # the exact "needs <key>: <threshold>, have <actual>" string, not a restatement


def test_an_unavailable_tool_is_glossed_in_plain_language() -> None:
    rendered = render_summary(_rich())
    assert "needs a restorable environment snapshot" in rendered  # not the bare 'snapshot_restore'


# -- cost ------------------------------------------------------------------------------


def test_cost_is_zero_with_an_explanation_when_nothing_called_a_model() -> None:
    assert "LLM spend: $0.0000. M1 grades by execution, which makes no model call." in render_summary(_clean())


def test_cost_is_shown_when_there_was_spend() -> None:
    assert "LLM spend: $0.0123." in render_summary(_rich())
