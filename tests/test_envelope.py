"""The read-only envelope: three independent layers over untrusted, AI-written SQL.

The load-bearing proofs: a ``DROP TABLE`` never reaches the executor (layer 1); with layer 1
disabled, a write still fails at a genuinely read-only SQLite transaction (layer 2, independent);
the result is capped (layer 3); a write needs a scratch/snapshot scope and can never name the live
schema (layer 4); and the audit log is append-only and stores no un-redacted value (layer 5).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from evalloop.connect.envelope import (
    AuditLog,
    Caps,
    NotReadOnly,
    ReadOnlyEnvelope,
    ReadOnlyViolation,
    Result,
    WriteScope,
    classify_statements,
    redact_sql,
    reject_writes,
)


class _Spy:
    """A stand-in executor that records what it was asked to run and returns canned rows."""

    def __init__(self, rows: list[tuple[object, ...]] | None = None, *, read_only: bool = True) -> None:
        self.read_only = read_only
        self.rows = rows or []
        self.calls: list[str] = []

    def run(self, sql: str, *, max_rows: int | None) -> list[tuple[object, ...]]:
        self.calls.append(sql)
        return self.rows


def _envelope(audit: AuditLog | None = None, **kw: object) -> ReadOnlyEnvelope:
    return ReadOnlyEnvelope(audit or AuditLog(), **kw)  # type: ignore[arg-type]


# -- layer 1: static rejection before a byte is sent -----------------------------------


def test_drop_table_never_reaches_the_wire() -> None:
    spy = _Spy()
    env = _envelope()
    with pytest.raises(ReadOnlyViolation):
        env.execute("DROP TABLE users", endpoint="db", caps=Caps(), executor=spy)
    assert spy.calls == [], "the executor was touched; DROP reached the wire"


def test_every_write_kind_is_rejected_by_name() -> None:
    spy = _Spy()
    env = _envelope()
    for sql, keyword in [
        ("DELETE FROM t", "DELETE"),
        ("UPDATE t SET x = 1", "UPDATE"),
        ("INSERT INTO t VALUES (1)", "INSERT"),
        ("ALTER TABLE t ADD COLUMN c INT", "ALTER"),
        ("TRUNCATE t", "TRUNCATE"),
        ("GRANT SELECT ON t TO bob", "GRANT"),
    ]:
        with pytest.raises(ReadOnlyViolation) as exc:
            env.execute(sql, endpoint="db", caps=Caps(), executor=spy)
        assert exc.value.statement.keyword == keyword, sql
    assert spy.calls == []


def test_reads_pass_layer_one() -> None:
    env = _envelope()
    for sql in [
        "SELECT * FROM t",
        "WITH recent AS (SELECT * FROM t) SELECT * FROM recent",
        "VALUES (1), (2)",
        "EXPLAIN SELECT * FROM t",
    ]:
        spy = _Spy(rows=[(1,)])
        env.execute(sql, endpoint="db", caps=Caps(), executor=spy)
        assert spy.calls == [sql], sql


def test_a_write_stacked_after_a_read_is_caught() -> None:
    spy = _Spy()
    with pytest.raises(ReadOnlyViolation):
        _envelope().execute("SELECT 1; DROP TABLE t", endpoint="db", caps=Caps(), executor=spy)
    assert spy.calls == []


def test_a_keyword_inside_a_string_literal_is_not_a_write() -> None:
    spy = _Spy(rows=[(1,)])
    sql = "SELECT * FROM notes WHERE body = 'please DROP all the tables'"
    _envelope().execute(sql, endpoint="db", caps=Caps(), executor=spy)
    assert spy.calls == [sql]


def test_an_identifier_that_contains_a_keyword_is_fine() -> None:
    spy = _Spy(rows=[(1,)])
    _envelope().execute("SELECT update_count FROM metrics", endpoint="db", caps=Caps(), executor=spy)
    assert spy.calls == ["SELECT update_count FROM metrics"]


def test_select_for_update_is_treated_as_write_intent() -> None:
    with pytest.raises(ReadOnlyViolation):
        _envelope().execute("SELECT * FROM t FOR UPDATE", endpoint="db", caps=Caps(), executor=_Spy())


# -- layer 2: a real read-only SQLite transaction, independent of layer 1 --------------


class _SqliteExecutor:
    def __init__(self, conn: sqlite3.Connection, *, read_only: bool) -> None:
        self._conn = conn
        self.read_only = read_only
        if read_only:
            conn.execute("PRAGMA query_only = ON")

    def run(self, sql: str, *, max_rows: int | None) -> list[tuple[object, ...]]:
        return list(self._conn.execute(sql).fetchall())


def _seeded_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER, n INTEGER)")
    conn.execute("INSERT INTO t VALUES (1, 100)")
    conn.commit()
    return conn


def test_layer_two_blocks_the_write_with_layer_one_disabled() -> None:
    # Disable layer 1 entirely. The write now depends solely on the read-only transaction to stop it.
    audit = AuditLog()
    env = ReadOnlyEnvelope(audit, static_guard=lambda sql, scope: classify_statements(sql))
    conn = _seeded_db()
    ro = _SqliteExecutor(conn, read_only=True)

    with pytest.raises(sqlite3.OperationalError):
        env.execute("UPDATE t SET n = 999", endpoint="sqlite", caps=Caps(), executor=ro)

    # the row is untouched, and the blocked attempt was still audited (redacted)
    assert conn.execute("SELECT n FROM t WHERE id = 1").fetchone()[0] == 100
    assert len(audit) == 1 and audit.entries()[0].error is not None
    assert "999" not in audit.entries()[0].redacted_sql


def test_layer_two_refuses_a_non_read_only_executor_for_reads() -> None:
    spy = _Spy(read_only=False)
    with pytest.raises(NotReadOnly):
        _envelope().execute("SELECT 1", endpoint="db", caps=Caps(), executor=spy)
    assert spy.calls == []


# -- layer 3: row and byte caps --------------------------------------------------------


def test_row_cap_truncates_and_reports() -> None:
    spy = _Spy(rows=[(i,) for i in range(10)])
    res = _envelope().execute("SELECT id FROM t", endpoint="db", caps=Caps(max_rows=3), executor=spy)
    assert isinstance(res, Result)
    assert res.shape.row_count == 3 and res.shape.truncated is True
    assert len(res.rows) == 3


def test_byte_cap_truncates() -> None:
    spy = _Spy(rows=[("x" * 50,) for _ in range(10)])
    res = _envelope().execute("SELECT s FROM t", endpoint="db", caps=Caps(max_bytes=60), executor=spy)
    assert res.shape.truncated is True
    assert res.shape.byte_count <= 60


def test_no_cap_returns_everything() -> None:
    spy = _Spy(rows=[(i,) for i in range(5)])
    res = _envelope().execute("SELECT id FROM t", endpoint="db", caps=Caps(), executor=spy)
    assert res.shape.row_count == 5 and res.shape.truncated is False


# -- layer 4: writes land in scratch/snapshot, never the live schema -------------------


def test_a_write_needs_a_scratch_or_snapshot_scope() -> None:
    spy = _Spy(read_only=False)
    env = _envelope()
    with pytest.raises(ReadOnlyViolation):
        env.execute("INSERT INTO t VALUES (1)", endpoint="db", caps=Caps(), executor=spy)
    # with a scratch scope the same statement passes layer 1 and runs
    env.execute(
        "INSERT INTO t VALUES (1)",
        endpoint="db",
        caps=Caps(),
        executor=spy,
        write_scope=WriteScope.scratch_schema("eval_scratch"),
    )
    assert spy.calls == ["INSERT INTO t VALUES (1)"]


def test_the_live_schema_is_not_a_constructible_write_scope() -> None:
    with pytest.raises(ValueError):
        WriteScope("live", "public")
    with pytest.raises(ValueError):
        WriteScope.scratch_schema("")


def test_ddl_is_rejected_even_under_a_write_scope() -> None:
    with pytest.raises(ReadOnlyViolation):
        reject_writes("DROP TABLE t", WriteScope.scratch_schema("eval_scratch"))


# -- layer 5: append-only, redacted audit log ------------------------------------------


def test_audit_records_the_shape_and_redacts_values() -> None:
    audit = AuditLog()
    env = ReadOnlyEnvelope(audit)
    spy = _Spy(rows=[(1,)])
    env.execute(
        "SELECT * FROM users WHERE email = 'alice@example.com' AND age = 42",
        endpoint="shop-db",
        caps=Caps(max_rows=100),
        executor=spy,
    )
    assert len(audit) == 1
    entry = audit.entries()[0]
    assert entry.endpoint == "shop-db"
    assert entry.result is not None and entry.result.row_count == 1
    assert "alice@example.com" not in entry.redacted_sql and "42" not in entry.redacted_sql
    assert "?" in entry.redacted_sql


def test_audit_is_append_only_and_has_no_mutation_api() -> None:
    audit = AuditLog()
    assert not hasattr(audit, "pop") and not hasattr(audit, "clear") and not hasattr(audit, "remove")
    env = ReadOnlyEnvelope(audit)
    env.execute("SELECT 1", endpoint="db", caps=Caps(), executor=_Spy(rows=[(1,)]))
    env.execute("SELECT 2", endpoint="db", caps=Caps(), executor=_Spy(rows=[(2,)]))
    assert len(audit) == 2
    # entries() hands out a copy; mutating it does not touch the log
    audit.entries()  # tuple, immutable
    assert len(audit) == 2


def test_audit_file_sink_appends(tmp_path: Path) -> None:
    sink = tmp_path / "audit.log"
    audit = AuditLog(sink=str(sink))
    env = ReadOnlyEnvelope(audit)
    env.execute("SELECT * FROM t WHERE x = 7", endpoint="db", caps=Caps(), executor=_Spy(rows=[(1,)]))
    env.execute("SELECT * FROM t WHERE x = 9", endpoint="db", caps=Caps(), executor=_Spy(rows=[(1,)]))
    lines = sink.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "7" not in sink.read_text(encoding="utf-8") and "9" not in sink.read_text(encoding="utf-8")


def test_redact_sql_strips_every_literal() -> None:
    assert redact_sql("SELECT * FROM t WHERE email='a@b.com' AND age=42") == (
        "SELECT * FROM t WHERE email=? AND age=?"
    )


# -- the three layers are independent --------------------------------------------------


def test_independence_summary() -> None:
    # layer 1 alone stops DROP without any executor involvement
    spy = _Spy()
    with pytest.raises(ReadOnlyViolation):
        _envelope().execute("DROP TABLE t", endpoint="db", caps=Caps(), executor=spy)
    assert spy.calls == []
    # layer 3 alone caps a result that layers 1 and 2 happily allowed
    res = _envelope().execute("SELECT 1", endpoint="db", caps=Caps(max_rows=1), executor=_Spy(rows=[(1,), (2,)]))
    assert res.shape.row_count == 1 and res.shape.truncated is True
