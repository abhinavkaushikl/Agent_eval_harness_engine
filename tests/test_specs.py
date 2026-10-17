"""Eval specs: SQL / RAG / agent evals reach the live loop as ``*.eval.json`` and grade correctly.

The load-bearing proofs: a correct SQL query passes and a wrong one fails by execution match; recall@k
is gated against the spec's own threshold and carries its interval; the agent grader reads the real
end state and ignores the agent's claim; and an unknown or malformed spec is a stated error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalloop.grade.specs import SpecError, grade_spec_file


def _write(tmp: Path, name: str, spec: dict[str, object]) -> Path:
    path = tmp / name
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


_SETUP = "CREATE TABLE o(id INT, total INT, c TEXT); INSERT INTO o VALUES (1,120,'US'),(2,90,'US'),(3,300,'GB');"


def test_sql_spec_passes_correct_and_fails_wrong(tmp_path: Path) -> None:
    path = _write(tmp_path, "s.eval.json", {
        "kind": "sql", "sqlite_setup": _SETUP,
        "queries": [
            {"name": "ok", "reference": "SELECT id FROM o WHERE c='US'", "generated": "SELECT id FROM o WHERE c = 'US'"},
            {"name": "bad", "reference": "SELECT id FROM o WHERE c='US'", "generated": "SELECT id FROM o WHERE total>100"},
        ]})
    result = grade_spec_file(path)
    assert result.kind == "sql" and result.situation == "sql_generation"
    assert [c.verdict for c in result.cases] == ["passed", "failed"]
    assert result.outcome == "problem"


def test_sql_spec_hallucinated_column_hard_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, "s.eval.json", {
        "kind": "sql", "sqlite_setup": _SETUP,
        "queries": [{"name": "halluc", "reference": "SELECT id FROM o", "generated": "SELECT nope FROM o"}]})
    (case,) = grade_spec_file(path).cases
    assert case.verdict == "failed" and "no such column" in case.detail


def test_rag_spec_gates_recall_against_the_specs_threshold(tmp_path: Path) -> None:
    spec = {"kind": "rag", "k": 2, "embedding_model": "bge-small", "min_recall": 0.9,
            "queries": [
                {"query_id": "q1", "gold_ids": ["p1"], "retrieved": ["p1", "p9"]},
                {"query_id": "q2", "gold_ids": ["p4"], "retrieved": ["p7", "p4"]},
                {"query_id": "q3", "gold_ids": ["p2"], "retrieved": ["p9", "p8"]}]}
    (case,) = grade_spec_file(_write(tmp_path, "r.eval.json", spec)).cases
    assert case.verdict == "failed"               # 2/3 gold recalled = 0.667 < 0.9
    assert "recall@2" in case.detail and "[" in case.detail  # carries its interval


def test_rag_spec_without_threshold_is_measured_not_gated(tmp_path: Path) -> None:
    spec = {"kind": "rag", "k": 1, "embedding_model": "m",
            "queries": [{"query_id": "q1", "gold_ids": ["p1"], "retrieved": ["p1"]}]}
    (case,) = grade_spec_file(_write(tmp_path, "r.eval.json", spec)).cases
    assert case.verdict == "inconclusive" and "no 'min_recall'" in case.detail


def test_agent_spec_reads_real_state_and_ignores_the_claim(tmp_path: Path) -> None:
    spec = {"kind": "agent",
            "sqlite_setup": "CREATE TABLE orders(id INT, status TEXT); INSERT INTO orders VALUES (1,'shipped'),(2,'open');",
            "claim": {"done": True, "message": "all orders shipped"},
            "checks": [{"type": "no_rows", "name": "no open orders", "sql": "SELECT id FROM orders WHERE status='open'"}]}
    result = grade_spec_file(_write(tmp_path, "a.eval.json", spec))
    assert result.situation == "agent_action"
    (case,) = result.cases
    assert case.verdict == "failed"               # the claim said done; the real state says otherwise


def test_agent_spec_passes_when_the_state_is_actually_right(tmp_path: Path) -> None:
    spec = {"kind": "agent",
            "sqlite_setup": "CREATE TABLE orders(id INT, status TEXT); INSERT INTO orders VALUES (1,'shipped');",
            "checks": [{"type": "rows_equal", "name": "one shipped", "sql": "SELECT count(*) FROM orders", "expected": [[1]]}]}
    (case,) = grade_spec_file(_write(tmp_path, "a.eval.json", spec)).cases
    assert case.verdict == "passed"


def test_unknown_kind_is_a_stated_error(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="unknown kind"):
        grade_spec_file(_write(tmp_path, "x.eval.json", {"kind": "mystery"}))


def test_missing_live_sqlite_is_a_stated_error(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="does not exist"):
        grade_spec_file(_write(tmp_path, "s.eval.json", {
            "kind": "sql", "sqlite": "no_such.db",
            "queries": [{"generated": "SELECT 1", "reference": "SELECT 1"}]}))
