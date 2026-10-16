"""Postgres and MySQL connectors that shell out to ``psql`` / ``mysql`` and never import a driver.

Decision EL-006: connectors shell out; they do not import a database driver. The broker resolves the
*mechanism* — a native driver if one is already importable, else a CLI on ``PATH``, else an offer to
install one into an EvalLoop-owned runtime. This file is the **CLI case**: it invokes ``psql`` /
``mysql`` as subprocesses, through the broker (EL-302) and the read-only envelope (EL-305). The
driver-auto-install path is the broker's, not ours (out of scope).

Two properties fall out of shelling out:
  * **A missing mechanism is UNAVAILABLE, never a crash.** When the CLI is not on ``PATH`` the
    connector reports it by name and says how to supply it — :class:`MechanismUnavailable`, and a
    ``reachable=False`` probe — rather than raising a subprocess traceback.
  * **The developer's TLS / Kerberos / SSH config comes for free.** The subprocess inherits the full
    environment automatically (``subprocess`` passes the parent's environment when ``env`` is not
    overridden), so ``PGSSLMODE``, ``~/.pgpass``, a Kerberos ticket cache, SSH agent sockets and the
    rest are exactly what the developer's own ``psql`` / ``mysql`` would use. This connector never
    reads the process environment itself — credentials never pass through EvalLoop code
    (ARCHITECTURE.md §9; only ``capability/llm.py`` reads the environment).

No ``psycopg`` / ``mysqlclient`` / ``PyMySQL`` import appears anywhere under ``evalloop/connect/`` — a
source scan proves it. Read-only is enforced three ways: the envelope rejects a write before the
subprocess starts (layer 1), the session is opened read-only (layer 2), and the result is capped
(layer 3).
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import ClassVar

from evalloop.capability.broker import CapabilityBroker
from evalloop.connect.envelope import AuditEntry, AuditLog, Caps, ReadOnlyEnvelope, Result
from evalloop.connect.protocol import Column, ConnectorError, NotAuthorized, ProbeResult, Schema, Table
from evalloop.vocab import Tool

__all__ = ["PostgresConnector", "MySQLConnector", "MechanismUnavailable"]

_SEP = "\x1f"  # ASCII unit separator: a field separator that will not occur in ordinary data
_DEFAULT_TIMEOUT = 30.0


class MechanismUnavailable(ConnectorError):
    """The CLI the connector needs is not on PATH. Names the binary and how to supply it; never a crash."""

    def __init__(self, mechanism: str, remedy: str) -> None:
        self.mechanism = mechanism
        self.remedy = remedy
        super().__init__(f"the {mechanism!r} CLI is not on PATH; {remedy}")


class _CliExecutor:
    """Adapts a connector's subprocess runner to the envelope's ``Executor`` protocol."""

    read_only = True

    def __init__(self, runner: Callable[[str], Sequence[Sequence[object]]]) -> None:
        self._runner = runner

    def run(self, sql: str, *, max_rows: int | None) -> Sequence[Sequence[object]]:
        return self._runner(sql)  # the envelope caps rows/bytes; the CLI need not


class _SqlCliConnector:
    """Shared orchestration for a SQL connector that reaches its backend through a command-line client."""

    binary: ClassVar[str]
    remedy: ClassVar[str]

    def __init__(
        self,
        *,
        broker: CapabilityBroker,
        endpoint: str,
        connect_args: Sequence[str] = (),
        envelope: ReadOnlyEnvelope | None = None,
        tool: Tool = Tool.db_connection,
    ) -> None:
        self.endpoint = endpoint
        self._broker = broker
        self._tool = tool
        self._connect_args = tuple(connect_args)
        self._envelope = envelope if envelope is not None else ReadOnlyEnvelope(AuditLog())
        self._executor = _CliExecutor(self._run_cli)
        self._timeout: float | None = _DEFAULT_TIMEOUT

    # -- per-dialect hooks --------------------------------------------------------------

    def _query_argv(self, path: str, sql: str) -> list[str]:
        raise NotImplementedError

    def _introspect_sql(self) -> str:
        raise NotImplementedError

    def _parse(self, stdout: str) -> list[tuple[str, ...]]:
        raise NotImplementedError

    # -- mechanism resolution -----------------------------------------------------------

    def _require_cli(self) -> str:
        path = shutil.which(self.binary)
        if path is None:
            raise MechanismUnavailable(self.binary, self.remedy)
        return path

    def _run_cli(self, sql: str) -> list[tuple[str, ...]]:
        path = self._require_cli()
        # No env= override: the child inherits the developer's environment (TLS/Kerberos/SSH) for free,
        # and EvalLoop code never reads the process environment. Read-only is set via SQL in the argv.
        proc = subprocess.run(
            self._query_argv(path, sql),
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if proc.returncode != 0:
            raise ConnectorError(f"{self.binary} exited {proc.returncode}: {proc.stderr.strip()}")
        return self._parse(proc.stdout)

    # -- authorisation ------------------------------------------------------------------

    def _authorize(self) -> Caps:
        decision = self._broker.check(self._tool, endpoint=self.endpoint)
        if not decision.granted or decision.grant is None:
            raise NotAuthorized(decision.reason or f"{self._tool.value} is not granted for {self.endpoint!r}")
        return decision.grant.caps

    # -- the three operations -----------------------------------------------------------

    def probe(self) -> ProbeResult:
        """Reachable, and read-only? A missing CLI or an unreachable server is a clean, named result."""
        self._authorize()
        try:
            self._run_cli("SELECT 1")
        except MechanismUnavailable as exc:
            self._log("probe", error=str(exc))
            return ProbeResult(reachable=False, read_only=True, detail=str(exc))
        except (ConnectorError, OSError, subprocess.SubprocessError) as exc:
            self._log("probe", error=str(exc))
            return ProbeResult(reachable=False, read_only=True, detail=f"{self.binary} could not reach {self.endpoint!r}: {exc}")
        self._log("probe")
        return ProbeResult(reachable=True, read_only=True, detail=f"{self.binary} reached {self.endpoint!r}, read-only session")

    def describe(self) -> Schema:
        """Tables and columns from information_schema (catalog, not row data). Authorised first."""
        self._authorize()
        rows = self._run_cli(self._introspect_sql())
        by_table: dict[str, list[Column]] = {}
        for row in rows:
            if len(row) < 3:
                continue
            table, column, dtype = str(row[0]), str(row[1]), str(row[2])
            by_table.setdefault(table, []).append(Column(name=column, type=dtype))
        self._log("describe")
        return Schema(tables=tuple(Table(name=t, columns=tuple(cols)) for t, cols in by_table.items()))

    def read(self, sql: str) -> Result:
        """Run a read-only query through the envelope, which rejects a write before the subprocess starts."""
        caps = self._authorize()
        self._timeout = caps.max_seconds if caps.max_seconds is not None else _DEFAULT_TIMEOUT
        return self._envelope.execute(sql, endpoint=self.endpoint, caps=caps, executor=self._executor)

    # -- helper -------------------------------------------------------------------------

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


class PostgresConnector(_SqlCliConnector):
    """Postgres over ``psql``. The session is read-only via ``PGOPTIONS``; credentials via env/``~/.pgpass``."""

    binary = "psql"
    remedy = "install the PostgreSQL client (e.g. `brew install libpq` or `apt-get install postgresql-client`) or add psql to PATH"

    def _query_argv(self, path: str, sql: str) -> list[str]:
        # Two --command flags run in one session: the first makes every following transaction
        # read-only (envelope layer 2 at the server), the second runs the query.
        return [
            path,
            "--no-psqlrc",
            "--no-align",
            "--tuples-only",
            "--quiet",
            f"--field-separator={_SEP}",
            "--command",
            "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
            "--command",
            sql,
            *self._connect_args,
        ]

    def _introspect_sql(self) -> str:
        return (
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
        )

    def _parse(self, stdout: str) -> list[tuple[str, ...]]:
        return [tuple(line.split(_SEP)) for line in stdout.splitlines() if line != ""]


class MySQLConnector(_SqlCliConnector):
    """MySQL over ``mysql``. The session opens read-only; credentials via env/``~/.my.cnf``."""

    binary = "mysql"
    remedy = "install the MySQL client (e.g. `brew install mysql-client` or `apt-get install default-mysql-client`) or add mysql to PATH"

    def _query_argv(self, path: str, sql: str) -> list[str]:
        return [
            path,
            "--batch",  # tab-separated, no table framing
            "--skip-column-names",
            "--execute",
            f"SET SESSION TRANSACTION READ ONLY; {sql}",
            *self._connect_args,
        ]

    def _introspect_sql(self) -> str:
        return (
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = DATABASE() ORDER BY table_name, ordinal_position"
        )

    def _parse(self, stdout: str) -> list[tuple[str, ...]]:
        return [tuple(line.split("\t")) for line in stdout.splitlines() if line != ""]
