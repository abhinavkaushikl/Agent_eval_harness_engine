"""The mutation self-check (A:38): the grader grading itself.

A:38 — "Test your tests. Mutate the reference solution ... If the mutant still passes more than 5%
of the time, the fixtures aren't discriminating enough." This is the only thing standing between
EvalLoop and fixtures that pass wrong answers by coincidence, so it is checked on both a
discriminating oracle and a weak one.
"""

from __future__ import annotations

from evalloop.grade.execution import MutationReport, mutation_self_check
from evalloop.grade.verdict import Limits

_LIMITS = Limits(wall_seconds=30.0)

ARTIFACT = "def total(prices, discount=0.0):\n    return sum(prices) * (1 - discount)\n"
STRONG_ORACLE = (
    "from pricing import total\n\n"
    "def test_sum():\n    assert total([1.0, 2.0]) == 3.0\n\n"
    "def test_discount():\n    assert total([10.0], 0.5) == 5.0\n\n"
    "def test_empty():\n    assert total([]) == 0.0\n"
)
WEAK_ORACLE = "from pricing import total\n\ndef test_callable():\n    assert callable(total)\n"


def _check(oracle: str) -> MutationReport:
    return mutation_self_check(
        artifact_source=ARTIFACT,
        import_name="pricing",
        oracle_source=oracle,
        max_mutant_pass_rate=5,
        sandbox_limits=_LIMITS,
    )


def test_a_discriminating_oracle_catches_the_mutants() -> None:
    report = _check(STRONG_ORACLE)
    assert report.mutants > 0  # there were mutations to try
    assert report.survival_rate <= 0.05 and report.discriminating


def test_a_weak_oracle_is_reported_as_not_discriminating() -> None:
    report = _check(WEAK_ORACLE)
    assert report.mutants > 0
    assert report.survival_rate > 0.05 and not report.discriminating  # mutants slip past a vacuous oracle


def test_the_report_cites_the_five_percent_bar() -> None:
    report = _check(WEAK_ORACLE)
    assert report.max_pass_rate == 5
    assert "5%" in report.rule and "discriminating" in report.rule
    assert "bar is 5%" in report.summary()


def test_the_summary_states_the_counts_and_the_verdict() -> None:
    strong, weak = _check(STRONG_ORACLE), _check(WEAK_ORACLE)
    assert "discriminating" in strong.summary() and "NOT discriminating" in weak.summary()
    assert f"{strong.survivors}/{strong.mutants}" in strong.summary()


def test_no_mutants_is_vacuously_discriminating() -> None:
    report = MutationReport(mutants=0, survivors=0, max_pass_rate=5)
    assert report.survival_rate == 0.0 and report.discriminating
