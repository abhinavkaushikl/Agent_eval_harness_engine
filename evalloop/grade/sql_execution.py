"""Grade generated SQL by RUNNING it against a frozen snapshot and comparing result sets.

Never by comparing query text. The warning this module is built around (``A:31`` /
``ARCHITECTURE.md`` §6.4): on 200 text-to-SQL items, exact string match scored 41%, execution match
68%, and an LLM judge 79% — and the judge "passed 22 queries that returned the wrong rows." **68% is
the number that is true.** String similarity to a reference query is the exact failure the corpus
row exists to prevent, so there is no string-similarity path anywhere in this file; a source check
proves it.

What a grade means here
-----------------------
1. **Schema-grounding is separate from logic.** Every table and column the query names must exist. A
   hallucinated column is a HARD FAIL with class ``unknown_column`` (A:39), reported *separately*
   from a wrong-rows failure (``wrong_result``). We get this for free and precisely by executing on
   the snapshot and reading the database's own error — SQLite says ``no such column`` — rather than
   guessing from the text.
2. **Correctness is result-set equality.** Execute the generated *and* the reference SQL on the same
   frozen snapshot and compare the rows as a **multiset**, order-insensitive, *unless* the reference
   has an ``ORDER BY`` — then order is part of the answer and the comparison is ordered. Reordered
   joins and renamed aliases that return the same rows therefore PASS: equivalent-but-different is
   not wrong.
3. **No reference query?** The query must parse, execute, be schema-grounded, return a non-empty and
   type-consistent result, and only then a CROSS-FAMILY judge rules on question-vs-rows — as the
   **lowest** rung, never the only one. With no judge available (M4), the case is ``inconclusive``
   with that reason, never a bare pass.

Every case carries ``A1_execution_based`` (ladder rung 1); :func:`summarize` reports the pass rate
with its Wilson interval (C1). Everything runs under EL-305's read-only envelope on a snapshot, never
live data (EL-305/EL-306). Writes and end-state checks are EL-314; RAG is EL-312/313.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.envelope import ReadOnlyEnvelope, ReadOnlyViolation
from evalloop.connect.sqlite import SqliteConnector
from evalloop.memory.case import FailureClass, Verdict
from evalloop.stats.proportions import DEFAULT_CONFIDENCE, Interval, wilson_interval
from evalloop.vocab import Tool

__all__ = [
    "RECORD_ID",
    "LADDER_RUNG",
    "SqlGrade",
    "SqlExecutionSummary",
    "Snapshot",
    "SqlJudge",
    "build_snapshot",
    "grade_sql",
    "summarize",
]

RECORD_ID = "A1_execution_based"  # carried into every case: this is execution-based grading
LADDER_RUNG = 1  # A:execution is rung 1 of the grading ladder

_ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)
_STRING = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")

# Genuine write verbs. The read-only envelope rejects any non-read leader; when that leader is one of
# these, the generated SQL is a write (not a read answer); otherwise the leader is just malformed.
_WRITE_VERBS = frozenset(
    {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE", "MERGE",
     "REPLACE", "UPSERT", "ATTACH", "DETACH", "VACUUM", "REINDEX", "LOCK", "PRAGMA", "COMMIT", "ROLLBACK"}
)


@dataclass(frozen=True, slots=True)
class SqlGrade:
    """One graded SQL item. Always tagged with the execution-based record; the rung names what decided."""

    record_id: str
    ladder_rung: int
    verdict: Verdict
    failure_class: FailureClass | None
    rung: str  # "schema" | "execution" | "result_set" | "structural" | "judge"
    detail: str
    row_count: int | None


@runtime_checkable
class SqlJudge(Protocol):
    """A cross-family judge of last resort: does the result answer the question? Never the only rung."""

    family: str

    def accepts(self, question: str, rows: Sequence[Sequence[object]]) -> bool: ...


# -- the frozen snapshot ---------------------------------------------------------------


class Snapshot:
    """A read-only SQLite snapshot, reached through the EL-305 envelope and the EL-306 connector."""

    def __init__(self, path: str | Path, *, envelope: ReadOnlyEnvelope | None = None) -> None:
        self._endpoint = f"sqlite://{path}"
        broker = CapabilityBroker()
        broker.grant(
            Tool.db_connection,
            granted_by="sql_execution grader",
            reason="read-only grading snapshot",
            endpoint=self._endpoint,
            caps=Caps(),  # no row cap: a truncated result would be a false mismatch when comparing sets
        )
        self._conn = SqliteConnector(path, broker=broker, endpoint=self._endpoint, envelope=envelope)

    def rows(self, sql: str) -> list[tuple[object, ...]]:
        return [tuple(row) for row in self._conn.read(sql).rows]

    def close(self) -> None:
        self._conn.close()


def build_snapshot(path: str | Path, setup_sql: str) -> Snapshot:
    """Create and seed a frozen snapshot, then open it read-only.

    The caller seeds **distinguishing rows** (A:36 — a refund of exactly 5,000 to separate ``>`` from
    ``>=``); without them a plausible wrong query passes by coincidence. This function only builds the
    DB; the distinguishing rows are the caller's to provide.
    """
    writer = sqlite3.connect(str(path))
    try:
        writer.executescript(setup_sql)
        writer.commit()
    finally:
        writer.close()
    return Snapshot(path)


# -- helpers ---------------------------------------------------------------------------


def _grade(verdict: Verdict, failure: FailureClass | None, rung: str, detail: str, row_count: int | None) -> SqlGrade:
    return SqlGrade(RECORD_ID, LADDER_RUNG, verdict, failure, rung, detail, row_count)


def _execute(snapshot: Snapshot, sql: str) -> tuple[list[tuple[object, ...]] | None, SqlGrade | None]:
    """Run one query; return its rows, or a classified failure (schema-grounding read from the DB error)."""
    try:
        return snapshot.rows(sql), None
    except ReadOnlyViolation as exc:
        keyword = exc.statement.keyword.upper()
        if keyword in _WRITE_VERBS:
            return None, _grade(Verdict.failed, FailureClass.runtime_error, "execution", f"generated SQL is a write, not a read-only query ({keyword})", None)
        return None, _grade(Verdict.failed, FailureClass.syntax_error, "execution", f"generated SQL is not a valid read statement ({keyword}): {exc}", None)
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "no such column" in message:
            return None, _grade(Verdict.failed, FailureClass.unknown_column, "schema", f"hallucinated column: {exc}", None)
        if "no such table" in message:
            return None, _grade(Verdict.failed, FailureClass.unknown_column, "schema", f"hallucinated table: {exc}", None)
        if "syntax error" in message or "near " in message:
            return None, _grade(Verdict.failed, FailureClass.syntax_error, "execution", f"SQL did not parse: {exc}", None)
        return None, _grade(Verdict.failed, FailureClass.runtime_error, "execution", f"SQL failed to run: {exc}", None)
    except sqlite3.DatabaseError as exc:
        return None, _grade(Verdict.failed, FailureClass.runtime_error, "execution", f"SQL failed to run: {exc}", None)


def _has_order_by(sql: str) -> bool:
    return bool(_ORDER_BY.search(_STRING.sub(" ", sql)))


def _result_sets_equal(generated: list[tuple[object, ...]], reference: list[tuple[object, ...]], ordered: bool) -> bool:
    if ordered:
        return generated == reference
    return Counter(generated) == Counter(reference)


def _cell_type(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"  # SQLite freely mixes INTEGER and REAL in one column; both are numeric
    if isinstance(value, str):
        return "str"
    if isinstance(value, (bytes, bytearray)):
        return "bytes"
    return type(value).__name__


def _type_consistent(rows: list[tuple[object, ...]]) -> bool:
    if not rows:
        return True
    width = len(rows[0])
    for col in range(width):
        kinds = {t for t in (_cell_type(row[col]) for row in rows if col < len(row)) if t is not None}
        if len(kinds) > 1:
            return False
    return True


# -- the grader ------------------------------------------------------------------------


def grade_sql(
    generated: str,
    *,
    snapshot: Snapshot,
    reference: str | None = None,
    question: str | None = None,
    judge: SqlJudge | None = None,
) -> SqlGrade:
    """Grade one generated query by running it on ``snapshot``. Correctness is result sets, never text."""
    rows, failure = _execute(snapshot, generated)
    if failure is not None:
        return failure  # a syntax / schema-grounding / execution failure, reported with its own class
    assert rows is not None

    if reference is not None:
        ref_rows, ref_failure = _execute(snapshot, reference)
        if ref_failure is not None or ref_rows is None:
            # the reference is trusted; if it will not run, that is a harness fault, not the artifact's
            return _grade(Verdict.inconclusive, None, "result_set", f"reference query did not run: {ref_failure.detail if ref_failure else 'unknown'}", len(rows))
        ordered = _has_order_by(reference)
        if _result_sets_equal(rows, ref_rows, ordered):
            shape = "ordered" if ordered else "multiset"
            return _grade(Verdict.passed, None, "result_set", f"result set matches reference ({len(rows)} rows, {shape})", len(rows))
        return _grade(
            Verdict.failed,
            FailureClass.wrong_result,
            "result_set",
            f"wrong rows: generated returned {len(rows)}, reference {len(ref_rows)} ({'ordered' if ordered else 'multiset'} comparison)",
            len(rows),
        )

    # No reference: structural gates, then a cross-family judge as the lowest rung (never the only one).
    if not rows:
        return _grade(Verdict.inconclusive, None, "structural", "no reference, and the query returned no rows; cannot confirm correctness", 0)
    if not _type_consistent(rows):
        return _grade(Verdict.failed, FailureClass.wrong_result, "structural", "a result column is not type-consistent across rows", len(rows))
    if judge is None:
        return _grade(
            Verdict.inconclusive,
            None,
            "judge",
            "parses, executes, schema-grounded, non-empty, type-consistent — but correctness needs a "
            "cross-family judge (M4) or a reference query; not scored as a pass",
            len(rows),
        )
    if judge.accepts(question or "", rows):
        return _grade(Verdict.passed, None, "judge", f"cross-family judge ({judge.family}) accepted the rows (lowest rung)", len(rows))
    return _grade(Verdict.failed, FailureClass.wrong_result, "judge", f"cross-family judge ({judge.family}) rejected the rows", len(rows))


# -- the pass rate, with its interval --------------------------------------------------


@dataclass(frozen=True, slots=True)
class SqlExecutionSummary:
    """The execution pass rate with its Wilson interval. Inconclusive cases are reported, not failed."""

    passed: int
    failed: int
    inconclusive: int
    interval: Interval | None  # None when no case was decided (passed + failed == 0)

    @property
    def decided(self) -> int:
        return self.passed + self.failed


def summarize(grades: Sequence[SqlGrade], *, confidence: float = DEFAULT_CONFIDENCE) -> SqlExecutionSummary:
    """Pass rate over *decided* cases, with a Wilson interval (C1). Inconclusive never counts as failed."""
    passed = sum(1 for g in grades if g.verdict is Verdict.passed)
    failed = sum(1 for g in grades if g.verdict is Verdict.failed)
    inconclusive = sum(1 for g in grades if g.verdict is Verdict.inconclusive)
    decided = passed + failed
    interval = wilson_interval(passed, decided, confidence) if decided else None
    return SqlExecutionSummary(passed, failed, inconclusive, interval)
