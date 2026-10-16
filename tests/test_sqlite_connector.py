"""The SQLite connector: probe / describe / read, driverless, through the broker and the envelope.

The load-bearing proofs: all three operations succeed and are read-only against a fixture DB;
describe returns structure and reads no rows; an ungranted endpoint is refused before the backend is
touched; and a write through read() is stopped by the *envelope* even when the connector is opened
over a writable SQLite connection that would have run it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.envelope import AuditLog, ReadOnlyEnvelope, ReadOnlyViolation
from evalloop.connect.protocol import Connector, NotAuthorized, ProbeResult, Schema
from evalloop.connect.sqlite import SqliteConnector
from evalloop.vocab import Tool

_ENDPOINT = "sqlite:///shop"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "shop.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, balance INTEGER)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total INTEGER)")
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", [(1, "alice", 100), (2, "bob", 50)])
    conn.execute("INSERT INTO orders VALUES (1, 1, 999)")
    conn.commit()
    conn.close()
    return path


def _granted_broker() -> CapabilityBroker:
    broker = CapabilityBroker()
    broker.grant(
        Tool.db_connection,
        granted_by="test",
        reason="fixture read-only access",
        endpoint=_ENDPOINT,
        caps=Caps(max_rows=100),
    )
    return broker


def _connector(db_path: Path, *, broker: CapabilityBroker | None = None, backend_read_only: bool = True) -> SqliteConnector:
    audit = AuditLog()
    return SqliteConnector(
        db_path,
        broker=broker or _granted_broker(),
        endpoint=_ENDPOINT,
        envelope=ReadOnlyEnvelope(audit),
        backend_read_only=backend_read_only,
    )


# -- the connector satisfies the backend-agnostic contract -----------------------------


def test_sqlite_connector_is_a_connector(db_path: Path) -> None:
    assert isinstance(_connector(db_path), Connector)


# -- probe / describe / read all succeed, and are read-only ----------------------------


def test_probe_reports_reachable_and_read_only(db_path: Path) -> None:
    result = _connector(db_path).probe()
    assert isinstance(result, ProbeResult)
    assert result.reachable is True and result.read_only is True


def test_describe_returns_tables_and_columns(db_path: Path) -> None:
    schema = _connector(db_path).describe()
    assert isinstance(schema, Schema)
    by_name = {t.name: t for t in schema.tables}
    assert set(by_name) == {"customers", "orders"}
    cols = [c.name for c in by_name["customers"].columns]
    assert cols == ["id", "name", "balance"]


def test_describe_reads_no_rows(db_path: Path) -> None:
    # If describe touched table data, these secret values would show up somewhere in the schema.
    schema = _connector(db_path).describe()
    blob = repr(schema)
    assert "alice" not in blob and "bob" not in blob and "999" not in blob


def test_read_returns_rows_under_the_cap(db_path: Path) -> None:
    res = _connector(db_path).read("SELECT name FROM customers ORDER BY id")
    assert [tuple(r) for r in res.rows] == [("alice",), ("bob",)]
    assert res.shape.row_count == 2 and res.shape.truncated is False


def test_read_respects_the_granted_cap(db_path: Path) -> None:
    broker = CapabilityBroker()
    broker.grant(Tool.db_connection, granted_by="t", reason="r", endpoint=_ENDPOINT, caps=Caps(max_rows=1))
    res = _connector(db_path, broker=broker).read("SELECT name FROM customers ORDER BY id")
    assert res.shape.row_count == 1 and res.shape.truncated is True


# -- the broker gates every call -------------------------------------------------------


def test_an_ungranted_endpoint_is_refused_before_the_backend(db_path: Path) -> None:
    empty = CapabilityBroker()  # nothing granted
    conn = _connector(db_path, broker=empty)
    with pytest.raises(NotAuthorized):
        conn.read("SELECT 1")
    with pytest.raises(NotAuthorized):
        conn.describe()
    with pytest.raises(NotAuthorized):
        conn.probe()


# -- the safety is the ENVELOPE's, not SQLite's ----------------------------------------


def test_a_write_through_read_is_rejected_by_the_envelope_even_on_a_writable_backend(db_path: Path) -> None:
    # First show SQLite itself would run the write on this file.
    probe = sqlite3.connect(db_path)
    probe.execute("UPDATE customers SET balance = 0 WHERE id = 1")
    assert probe.execute("SELECT balance FROM customers WHERE id = 1").fetchone()[0] == 0
    probe.execute("UPDATE customers SET balance = 100 WHERE id = 1")  # put it back
    probe.commit()
    probe.close()

    # Now a connector opened over a WRITABLE backend. read() must still refuse the write — at the
    # envelope's first layer, before the backend is touched.
    conn = _connector(db_path, backend_read_only=False)
    with pytest.raises(ReadOnlyViolation):
        conn.read("UPDATE customers SET balance = 0 WHERE id = 1")

    after = sqlite3.connect(db_path)
    assert after.execute("SELECT balance FROM customers WHERE id = 1").fetchone()[0] == 100
    after.close()


def test_read_only_backend_blocks_a_write_that_bypasses_layer_one(db_path: Path) -> None:
    # Belt and suspenders: with layer 1 disabled, the read-only SQLite backend still refuses the write.
    audit = AuditLog()
    envelope = ReadOnlyEnvelope(audit, static_guard=lambda sql, scope: ())
    conn = SqliteConnector(db_path, broker=_granted_broker(), endpoint=_ENDPOINT, envelope=envelope)
    with pytest.raises(sqlite3.Error):
        conn.read("UPDATE customers SET balance = 0 WHERE id = 1")


# -- every call is recorded ------------------------------------------------------------


def test_every_call_is_audited(db_path: Path) -> None:
    audit = AuditLog()
    conn = SqliteConnector(db_path, broker=_granted_broker(), endpoint=_ENDPOINT, envelope=ReadOnlyEnvelope(audit))
    conn.probe()
    conn.describe()
    conn.read("SELECT name FROM customers WHERE name = 'alice'")
    kinds = [e.statement_kinds for e in audit.entries()]
    assert ("probe",) in kinds and ("describe",) in kinds
    # the read's literal value is redacted in the audit
    reads = [e for e in audit.entries() if e.redacted_sql.startswith("SELECT")]
    assert reads and "alice" not in reads[0].redacted_sql
