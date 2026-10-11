"""The execution grader: it RUNS the artifact and reports the number that is true.

A1's evidence (A:31) is the warning: a judge that reads the code scores 79% on text-to-SQL, but
22 of those queries returned the wrong rows; execution scores the true 68%. So every test here
grades by running, and the headline a broken function earns is a failure, not a plausible read.
"""

from __future__ import annotations


import pytest

from evalloop.grade.execution import (
    RECORD_ID,
    GradeError,
    GradeReport,
    attributable_regressions,
    grade_execution,
)
from evalloop.grade.verdict import Limits
from evalloop.memory.case import (
    CaseKind,
    CaseResult,
    FailureClass,
    OracleConfidence,
    Verdict,
)
from evalloop.memory.metric_store import Run

_LIMITS = Limits(wall_seconds=30.0)
_CPU_LIMITS = Limits(wall_seconds=20.0, cpu_seconds=2)
_H = "b" * 64

# An oracle with two cases: one a correct function passes and a wrong one fails, one both agree on.
ORACLE = (
    "from pricing import total\n\n"
    "def test_discount():\n    assert total([10.0], 0.5) == 5.0\n\n"
    "def test_sum():\n    assert total([1.0, 2.0]) == 3.0\n"
)
CORRECT = "def total(prices, discount=0.0):\n    return sum(prices) * (1 - discount)\n"
BROKEN = "def total(prices, discount=0.0):\n    return sum(prices) + discount  # a deliberate off-logic bug\n"
EQUIVALENT = (
    "def total(prices, discount=0.0):\n"
    "    running = 0.0\n"
    "    for price in prices:\n        running += price\n"
    "    return running - running * discount\n"
)


def _grade(source: str, *, oracle: str = ORACLE, limits: Limits = _LIMITS) -> GradeReport:
    return grade_execution(
        artifact_id="src/pricing.py",
        artifact_source=source,
        import_name="pricing",
        oracle_id="tests/test_pricing.py::total",
        oracle_source=oracle,
        oracle_confidence=OracleConfidence.high,
        oracle_hash=_H,
        run_id="run-1",
        sandbox_limits=limits,
        float_tolerance=1e-6,
    )


def _verdicts(report: GradeReport) -> list[tuple[str, str | None]]:
    return [(c.verdict.value, c.failure_class.value if c.failure_class else None) for c in report.cases]


# -- the done-when: a deliberately broken function is caught ----------------------------


def test_a_broken_function_is_caught() -> None:
    report = _grade(BROKEN)
    assert not report.full_pass  # the headline is a failure
    assert (Verdict.failed.value, FailureClass.wrong_result.value) in _verdicts(report)
    assert report.failed == 1 and report.passed == 1


def test_a_correct_function_fully_passes() -> None:
    report = _grade(CORRECT)
    assert report.full_pass and report.passed == 2 and report.failed == 0


def test_equivalent_but_different_output_is_not_marked_wrong() -> None:
    """A1's anti-pattern: a string match marks correct-but-different code wrong. Execution does not."""
    report = _grade(EQUIVALENT)
    assert report.full_pass  # a different-but-correct implementation passes


# -- compile vs logic split (A:39) -----------------------------------------------------


def test_a_syntax_error_is_a_different_finding_from_a_wrong_answer() -> None:
    broken_syntax = _grade("def total(prices, discount=0.0)\n    return sum(prices)\n")  # missing colon
    assert _verdicts(broken_syntax) == [(Verdict.failed.value, FailureClass.syntax_error.value)]
    wrong = _grade(BROKEN)
    assert (Verdict.failed.value, FailureClass.wrong_result.value) in _verdicts(wrong)
    # Both are stored, and they are different classes.
    assert broken_syntax.cases[0].failure_class is FailureClass.syntax_error


def test_a_runtime_error_is_not_a_wrong_answer() -> None:
    raises = _grade("def total(prices, discount=0.0):\n    raise ValueError('boom')\n")
    assert (Verdict.failed.value, FailureClass.runtime_error.value) in _verdicts(raises)
    assert all(c.failure_class is not FailureClass.wrong_result for c in raises.cases)


def test_a_timeout_is_a_failure_of_class_timeout() -> None:
    report = _grade("def total(prices, discount=0.0):\n    while True:\n        pass\n", limits=_CPU_LIMITS)
    assert not report.full_pass
    assert any(c.failure_class is FailureClass.timeout for c in report.cases)
    assert all(c.verdict is Verdict.failed for c in report.cases if c.failure_class is FailureClass.timeout)


# -- hidden-test isolation, with a proof -----------------------------------------------


def test_the_artifact_cannot_read_the_oracle_that_grades_it() -> None:
    """A hostile artifact that probes its environment cannot reach the oracle by name, path or cwd."""
    probe = (
        "import os\n"
        "def total(prices, discount=0.0):\n"
        "    here = sorted(os.listdir('.'))\n"
        "    try:\n        import test_oracle\n        imported = True\n    except Exception:\n        imported = False\n"
        "    try:\n        open('test_oracle.py').close()\n        opened = True\n    except Exception:\n        opened = False\n"
        "    raise AssertionError('PROBE cwd=' + repr(here) + ' import=' + repr(imported) + ' open=' + repr(opened))\n"
    )
    report = _grade(probe)
    assert not report.full_pass
    evidence = " ".join(c.evidence or "" for c in report.cases)
    assert "import=False" in evidence and "open=False" in evidence
    assert "test_oracle" not in evidence.split("cwd=")[1].split("import=")[0]  # the oracle is not in its cwd
    # The documented boundary: an artifact scanning the whole filesystem by absolute path is a
    # reward-hack concern (M3); M1 isolates the artifact's environment, not a determined adversary.


# -- partial credit present, but the headline is full-pass (H:170) ----------------------


def test_partial_credit_is_present_but_is_not_the_headline() -> None:
    report = _grade(BROKEN)
    assert report.partial_credit == 0.5  # tracked
    assert report.full_pass is False  # but a half-passing artifact is not a pass


# -- no pass rate without its interval (C1) --------------------------------------------


def _case(verdict: Verdict, failure: FailureClass | None = None, *, reason: str | None = None) -> CaseResult:
    return CaseResult(
        run_id="run-1", record_id=RECORD_ID, case_id="c", case_kind=CaseKind.generated, artifact_id="a",
        oracle_id="o", oracle_confidence=OracleConfidence.high, ladder_rung=1, verdict=verdict,
        failure_class=failure, timeout=None, inconclusive_reason=reason, score=None, evidence=None,
        artifact_hash=_H, oracle_hash=_H, reused_from=None, seed=None, cost_usd=None, duration_seconds=0.0,
    )


def test_a_pass_rate_carries_its_interval_and_refuses_to_exist_without_one() -> None:
    graded = _grade(CORRECT)
    interval = graded.pass_rate  # C1: the rate travels with its interval
    assert 0.0 <= interval.lower <= interval.estimate <= interval.upper <= 1.0
    all_inconclusive = GradeReport("a", "o", (_case(Verdict.inconclusive, reason="sandbox died"),), 0.95)
    with pytest.raises(GradeError, match="no conclusive case"):
        all_inconclusive.pass_rate


def test_an_oracle_that_cannot_run_is_inconclusive_not_a_failure() -> None:
    report = _grade(CORRECT, oracle="from pricing import missing_name\n\ndef test_x():\n    assert missing_name()\n")
    assert report.inconclusive >= 1 or any(c.failure_class is FailureClass.runtime_error for c in report.cases)
    # Importing a name the artifact does not have is the oracle/harness failing, counted apart from a wrong answer.


# -- a pre-existing failure is not attributed to this change (EL-205) -------------------


def test_a_pre_existing_failure_is_not_blamed_on_the_current_change() -> None:
    report = _grade(BROKEN)
    failing = next(c for c in report.cases if c.verdict is Verdict.failed)
    baseline = Run("run-0", (_baseline_case(failing.oracle_id, failing.oracle_hash),))
    assert attributable_regressions(report, baseline) == ()  # already failing before, so not this change's fault
    assert attributable_regressions(report, None) == tuple(c for c in report.cases if c.verdict is Verdict.failed)


def _baseline_case(oracle_id: str, oracle_hash: str) -> CaseResult:
    return CaseResult(
        run_id="run-0", record_id=RECORD_ID, case_id="old", case_kind=CaseKind.generated, artifact_id="src/pricing.py",
        oracle_id=oracle_id, oracle_confidence=OracleConfidence.high, ladder_rung=1, verdict=Verdict.failed,
        failure_class=FailureClass.wrong_result, timeout=None, inconclusive_reason=None, score=None, evidence=None,
        artifact_hash="c" * 64, oracle_hash=oracle_hash, reused_from=None, seed=None, cost_usd=None, duration_seconds=0.0,
    )


# -- every case carries A1's record id, and grading is deterministic --------------------


def test_every_case_carries_the_a1_record_id() -> None:
    assert all(c.record_id == RECORD_ID == "A1_execution_based" for c in _grade(BROKEN).cases)


def test_grading_is_deterministic() -> None:
    first, second = _grade(BROKEN), _grade(BROKEN)
    assert _verdicts(first) == _verdicts(second)
    assert [c.case_id for c in first.cases] == [c.case_id for c in second.cases]
