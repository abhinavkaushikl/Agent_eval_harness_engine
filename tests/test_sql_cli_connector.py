"""Postgres/MySQL connectors that shell out: no driver, clean UNAVAILABLE, config inherited for free.

The load-bearing proofs: a missing CLI is a named UNAVAILABLE (not a traceback); no driver is
imported anywhere under evalloop/connect/; a write is stopped by the envelope before any subprocess
starts; the subprocess inherits the developer's environment; and a real local Postgres read returns
rows when a server is present, skipping cleanly when it is not (so CI needs no database).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from evalloop.capability.broker import CapabilityBroker, Caps
from evalloop.connect.envelope import ReadOnlyViolation
from evalloop.connect.protocol import Connector, NotAuthorized
from evalloop.connect.sql_cli import MechanismUnavailable, MySQLConnector, PostgresConnector
from evalloop.vocab import Tool

_PG = "postgres://localhost/shop"


def _granted(endpoint: str) -> CapabilityBroker:
    broker = CapabilityBroker()
    broker.grant(Tool.db_connection, granted_by="test", reason="read-only", endpoint=endpoint, caps=Caps(max_rows=100))
    return broker


def _pg(**kw: object) -> PostgresConnector:
    return PostgresConnector(broker=_granted(_PG), endpoint=_PG, **kw)  # type: ignore[arg-type]


# -- both satisfy the Connector contract -----------------------------------------------


def test_both_are_connectors() -> None:
    assert isinstance(_pg(), Connector)
    assert isinstance(MySQLConnector(broker=_granted("mysql://localhost/shop"), endpoint="mysql://localhost/shop"), Connector)


# -- a missing CLI is a clean, named UNAVAILABLE ---------------------------------------


def test_missing_psql_is_unavailable_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    conn = _pg()

    # probe() reports it cleanly
    result = conn.probe()
    assert result.reachable is False
    assert "psql" in result.detail and "PATH" in result.detail

    # read() raises a typed, named error — caught here, never a bare subprocess traceback
    with pytest.raises(MechanismUnavailable) as exc:
        conn.read("SELECT 1")
    assert exc.value.mechanism == "psql"
    assert "install" in exc.value.remedy.lower()


# -- EL-006: no driver is ever imported ------------------------------------------------


def test_no_database_driver_imported_under_connect() -> None:
    root = Path(__file__).resolve().parent.parent / "evalloop" / "connect"
    forbidden = ("psycopg", "psycopg2", "mysqlclient", "pymysql", "mysqldb", "sqlalchemy")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        low = path.read_text(encoding="utf-8").lower()
        for driver in forbidden:
            if f"import {driver}" in low or f"from {driver}" in low:
                offenders.append(f"{path.name}: {driver}")
    assert offenders == [], f"a database driver is imported under evalloop/connect/: {offenders}"


# -- a write is rejected by the envelope before any subprocess starts ------------------


def test_a_write_is_rejected_before_any_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a subprocess was started for a write-shaped query")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(ReadOnlyViolation):
        _pg().read("DROP TABLE users")


# -- the developer's environment is inherited for free ---------------------------------


def test_the_subprocess_inherits_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # "For free" means: the connector does not build or override an environment at all, so the child
    # inherits the parent's (TLS/Kerberos/SSH config and all). We prove it by watching the call.
    captured: dict[str, object] = {}

    def record(argv: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs.get("env", "NOT PASSED")
        captured["argv"] = argv
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="1\n", stderr="")

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/psql")
    monkeypatch.setattr(subprocess, "run", record)
    _pg().read("SELECT 1")
    # env is never passed, so subprocess inherits the developer's environment untouched
    assert captured["env"] == "NOT PASSED"
    # and read-only is forced in the argv, not via a scrubbed environment
    assert "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY" in captured["argv"]  # type: ignore[operator]


# -- the broker gates every call -------------------------------------------------------


def test_an_ungranted_endpoint_is_refused() -> None:
    conn = PostgresConnector(broker=CapabilityBroker(), endpoint=_PG)
    with pytest.raises(NotAuthorized):
        conn.read("SELECT 1")


# -- parsing --------------------------------------------------------------------------


def test_postgres_parse_splits_on_the_unit_separator() -> None:
    from evalloop.connect.sql_cli import _SEP

    rows = _pg()._parse(f"1{_SEP}alice\n2{_SEP}bob\n")
    assert rows == [("1", "alice"), ("2", "bob")]


def test_mysql_parse_splits_on_tabs() -> None:
    conn = MySQLConnector(broker=_granted("mysql://localhost/shop"), endpoint="mysql://localhost/shop")
    assert conn._parse("1\talice\n2\tbob\n") == [("1", "alice"), ("2", "bob")]


# -- a real local Postgres, when one is present (skips cleanly otherwise) ---------------


def test_read_against_a_local_postgres_if_present() -> None:
    if shutil.which("psql") is None:
        pytest.skip("psql not on PATH; CLI read is exercised only when a client is installed")
    dsn = os.environ.get("EVALLOOP_PG_DSN", "")
    conn = PostgresConnector(
        broker=_granted(_PG), endpoint=_PG, connect_args=(dsn,) if dsn else ()
    )
    if not conn.probe().reachable:
        pytest.skip("no reachable local Postgres; set EVALLOOP_PG_DSN to run this against a server")
    res = conn.read("SELECT 1")
    assert [tuple(r) for r in res.rows] == [("1",)]
