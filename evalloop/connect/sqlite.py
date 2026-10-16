"""The first :class:`~evalloop.connect.protocol.Connector`: SQLite, driverless and local.

SQLite ships in the standard library (``sqlite3``), so it needs no driver and no network — decision
EL-006's "no-driver case", and the clean place to pin the protocol before the CLI backends (EL-308)
and vector stores (EL-309). Every call is authorised through the capability broker (EL-302) first,
and the untrusted ``read(sql)`` path runs through the read-only envelope (EL-305).

The safety is the envelope's, not SQLite's. ``read()`` refuses a write at the envelope's first layer
**before** the backend sees it — provably, even when the connector is opened over a *writable*
SQLite connection that would have run the write. Opening read-only (``mode=ro`` + ``PRAGMA
query_only``) is a second, independent belt; ``backend_read_only=False`` exists only so a test can
strip that belt and watch the envelope hold on its own. Production uses the default.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from evalloop.capability.broker import CapabilityBroker
from evalloop.connect.envelope import AuditEntry, AuditLog, Caps, ReadOnlyEnvelope, Result
from evalloop.connect.protocol import Column, NotAuthorized, ProbeResult, Schema, Table
from evalloop.vocab import Tool

__all__ = ["SqliteConnector"]


class _SqliteExecutor:
    """Adapts a SQLite connection to the envelope's ``Executor`` protocol."""

    def __init__(self, conn: sqlite3.Connection, *, read_only: bool) -> None:
        self._conn = conn
        self.read_only = read_only

    def run(self, sql: str, *, max_rows: int | None) -> Sequence[Sequence[object]]:
        return list(self._conn.execute(sql).fetchall())


class SqliteConnector:
    """probe / describe / read on a local SQLite file, through the broker and the envelope."""

    def __init__(
        self,
        path: str | Path,
        *,
        broker: CapabilityBroker,
        endpoint: str,
        envelope: ReadOnlyEnvelope | None = None,
        tool: Tool = Tool.db_connection,
        backend_read_only: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self._path = str(path)
        self._broker = broker
        self._tool = tool
        self._envelope = envelope if envelope is not None else ReadOnlyEnvelope(AuditLog())
        self._backend_read_only = backend_read_only
        if backend_read_only:
            self._conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
            self._conn.execute("PRAGMA query_only = ON")
        else:
            self._conn = sqlite3.connect(self._path)
        self._executor = _SqliteExecutor(self._conn, read_only=backend_read_only)

    # -- authorisation: the broker, before anything touches the backend -----------------

    def _authorize(self) -> Caps:
        decision = self._broker.check(self._tool, endpoint=self.endpoint)
        if not decision.granted or decision.grant is None:
            raise NotAuthorized(decision.reason or f"{self._tool.value} is not granted for {self.endpoint!r}")
        return decision.grant.caps

    # -- the three operations -----------------------------------------------------------

    def probe(self) -> ProbeResult:
        """Reachable, and read-only? Authorised, then a trivial query; reads no user rows."""
        self._authorize()
        try:
            self._conn.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            self._log("probe", error=repr(exc))
            return ProbeResult(reachable=False, read_only=self._query_only(), detail=f"unreachable: {exc}")
        read_only = self._query_only()
        self._log("probe")
        return ProbeResult(
            reachable=True,
            read_only=read_only,
            detail=f"sqlite file reachable, query_only={'on' if read_only else 'off'}",
        )

    def describe(self) -> Schema:
        """Tables and columns, from the catalog. Authorised; reads no rows from any user table."""
        self._authorize()
        names = [
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        tables: list[Table] = []
        for name in names:
            # PRAGMA table_info reads the schema, not the table's rows.
            cols = tuple(
                Column(name=str(info[1]), type=str(info[2]))
                for info in self._conn.execute(f"PRAGMA table_info({_quote_ident(name)})").fetchall()
            )
            tables.append(Table(name=name, columns=cols))
        self._log("describe")
        return Schema(tables=tuple(tables))

    def read(self, sql: str) -> Result:
        """Run an untrusted read query through the envelope's three layers, under the granted caps."""
        caps = self._authorize()
        return self._envelope.execute(sql, endpoint=self.endpoint, caps=caps, executor=self._executor)

    # -- helpers ------------------------------------------------------------------------

    def _query_only(self) -> bool:
        row = self._conn.execute("PRAGMA query_only").fetchone()
        return bool(row[0]) if row is not None else False

    def _log(self, operation: str, *, error: str | None = None) -> None:
        self._envelope.audit.append(
            AuditEntry(
                endpoint=self.endpoint,
                redacted_sql=f"<{operation}>",
                statement_kinds=(operation,),
                caps=Caps(),
                write_scope=None,
                result=None,
                error=error,
            )
        )

    def close(self) -> None:
        self._conn.close()


def _quote_ident(name: str) -> str:
    """Double-quote a SQLite identifier for use in a PRAGMA, escaping embedded quotes."""
    return '"' + name.replace('"', '""') + '"'
