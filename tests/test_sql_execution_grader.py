"""Grading generated SQL by running it: execution match, not string match.

The load-bearing proofs: a hallucinated column is a HARD FAIL classed unknown_column, separate from a
wrong-rows failure; reordered joins / renamed aliases that return the same rows PASS; a plausible
wrong query is caught *because* the snapshot seeds a distinguishing row (the 5,000 refund that
separates > from >=); with no reference, a judge is the lowest rung and never the only one; the pass
rate carries a Wilson interval; and nothing in the module compares query text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evalloop.grade.sql_execution import (
    RECORD_ID,
    Snapshot,
    SqlJudge,
    build_snapshot,
    grade_sql,
    summarize,
)
from evalloop.memory.case import FailureClass, Verdict

# A snapshot with a DISTINGUISHING row: a refund of exactly 5000, so `> 5000` and `>= 5000` differ.
_SETUP = """
CREATE TABLE refunds (id INTEGER PRIMARY KEY, customer TEXT, amount INTEGER);
INSERT INTO refunds VALUES (1, 'alice', 6000);
INSERT INTO refunds VALUES (2, 'bob',   5000);
INSERT INTO refunds VALUES (3, 'carol', 3000);
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
INSERT INTO customers VALUES (1, 'alice', 'berlin');
INSERT INTO customers VALUES (2, 'bob',   'munich');
"""


@pytest.fixture
def snapshot(tmp_path: Path) -> Snapshot:
    return build_snapshot(tmp_path / "snap.db", _SETUP)


# -- schema-grounding is a hard fail, classed separately from wrong rows ---------------


def test_a_hallucinated_column_is_unknown_column_not_wrong_result(snapshot: Snapshot) -> None:
    grade = grade_sql("SELECT refund_total FROM refunds", snapshot=snapshot, reference="SELECT amount FROM refunds")
    assert grade.verdict is Verdict.failed
    assert grade.failure_class is FailureClass.unknown_column
    assert grade.rung == "schema"


def test_a_hallucinated_table_is_unknown_column(snapshot: Snapshot) -> None:
    grade = grade_sql("SELECT * FROM invoices", snapshot=snapshot, reference="SELECT * FROM refunds")
    assert grade.failure_class is FailureClass.unknown_column


def test_a_syntax_error_is_syntax_error(snapshot: Snapshot) -> None:
    grade = grade_sql("SELCT amount FROM refunds", snapshot=snapshot, reference="SELECT amount FROM refunds")
    assert grade.verdict is Verdict.failed and grade.failure_class is FailureClass.syntax_error


# -- correctness is result sets: equivalent-but-different passes, wrong rows fail -------


def test_reordered_joins_and_renamed_aliases_pass(snapshot: Snapshot) -> None:
    # Both queries express the same join differently (order swapped, aliases renamed) → same rows → PASS.
    ref = "SELECT customers.name, refunds.amount FROM refunds JOIN customers ON customers.id = refunds.id"
    gen = "SELECT c.name, r.amount FROM customers AS c JOIN refunds AS r ON r.id = c.id"
    grade = grade_sql(gen, snapshot=snapshot, reference=ref)
    assert grade.verdict is Verdict.passed and grade.rung == "result_set"


def test_a_plausible_wrong_query_is_caught_by_the_distinguishing_row(snapshot: Snapshot) -> None:
    # The 5000 refund separates these: >= includes bob, > does not.
    reference = "SELECT customer FROM refunds WHERE amount >= 5000"
    generated = "SELECT customer FROM refunds WHERE amount > 5000"
    grade = grade_sql(generated, snapshot=snapshot, reference=reference)
    assert grade.verdict is Verdict.failed and grade.failure_class is FailureClass.wrong_result
    assert grade.rung == "result_set"


def test_multiset_comparison_is_order_insensitive_without_order_by(snapshot: Snapshot) -> None:
    ref = "SELECT customer FROM refunds"
    gen = "SELECT customer FROM refunds ORDER BY amount DESC"  # same rows, different order; ref has no ORDER BY
    assert grade_sql(gen, snapshot=snapshot, reference=ref).verdict is Verdict.passed


def test_order_sensitive_when_the_reference_has_order_by(snapshot: Snapshot) -> None:
    ref = "SELECT customer FROM refunds ORDER BY amount ASC"
    gen = "SELECT customer FROM refunds ORDER BY amount DESC"  # same rows, wrong order
    grade = grade_sql(gen, snapshot=snapshot, reference=ref)
    assert grade.verdict is Verdict.failed and grade.failure_class is FailureClass.wrong_result


# -- no reference: structural gates, then the judge as the lowest rung -----------------


def test_no_reference_no_judge_is_inconclusive_not_a_pass(snapshot: Snapshot) -> None:
    grade = grade_sql("SELECT amount FROM refunds", snapshot=snapshot, question="refund amounts?")
    assert grade.verdict is Verdict.inconclusive and grade.rung == "judge"


def test_no_reference_empty_result_is_inconclusive(snapshot: Snapshot) -> None:
    grade = grade_sql("SELECT amount FROM refunds WHERE amount > 999999", snapshot=snapshot)
    assert grade.verdict is Verdict.inconclusive and grade.rung == "structural"


def test_the_judge_is_the_lowest_rung_only_after_structural_gates(snapshot: Snapshot) -> None:
    class _Judge:
        family = "cross-family-model-Z"

        def __init__(self, verdict: bool) -> None:
            self._verdict = verdict
            self.calls = 0

        def accepts(self, question: str, rows: object) -> bool:
            self.calls += 1
            return self._verdict

    # schema failure: the judge is NEVER consulted (structural gate fails first)
    rejecting = _Judge(True)
    bad = grade_sql("SELECT nope FROM refunds", snapshot=snapshot, judge=rejecting)
    assert bad.failure_class is FailureClass.unknown_column and rejecting.calls == 0

    # gates pass: the judge rules, and it is the lowest rung
    accepting = _Judge(True)
    good = grade_sql("SELECT amount FROM refunds", snapshot=snapshot, question="amounts?", judge=accepting)
    assert good.verdict is Verdict.passed and good.rung == "judge" and accepting.calls == 1
    assert isinstance(accepting, SqlJudge)


# -- every case carries A1, and the pass rate has a Wilson interval --------------------


def test_every_grade_carries_the_execution_record(snapshot: Snapshot) -> None:
    grade = grade_sql("SELECT amount FROM refunds", snapshot=snapshot, reference="SELECT amount FROM refunds")
    assert grade.record_id == RECORD_ID and grade.ladder_rung == 1


def test_summary_pass_rate_has_a_wilson_interval(snapshot: Snapshot) -> None:
    ref = "SELECT customer FROM refunds WHERE amount >= 5000"
    grades = [
        grade_sql("SELECT customer FROM refunds WHERE amount >= 5000", snapshot=snapshot, reference=ref),  # pass
        grade_sql("SELECT customer FROM refunds WHERE amount > 5000", snapshot=snapshot, reference=ref),   # fail
        grade_sql("SELECT amount FROM refunds", snapshot=snapshot),  # inconclusive (no ref/judge)
    ]
    summary = summarize(grades)
    assert summary.passed == 1 and summary.failed == 1 and summary.inconclusive == 1
    assert summary.decided == 2
    assert summary.interval is not None
    assert summary.interval.lower <= summary.interval.estimate <= summary.interval.upper
    assert summary.interval.method.value == "wilson"


# -- NEVER compare query text --------------------------------------------------------


def test_no_string_similarity_path_in_the_module() -> None:
    source = (Path(__file__).resolve().parent.parent / "evalloop" / "grade" / "sql_execution.py").read_text(encoding="utf-8")
    low = source.lower()
    for needle in ("difflib", "sequencematcher", "levenshtein", "jaccard", ".ratio(", "fuzz", "edit_distance"):
        assert needle not in low, f"a string-similarity path appears in the SQL grader: {needle}"
