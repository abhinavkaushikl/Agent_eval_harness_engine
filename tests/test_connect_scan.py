"""The `connect` / `probe` binding: discover + classify a repo, and open a local SQLite read-only.

The load-bearing proofs: a scan reports a repo's databases and vector stores with a plain-language
"what it still needs" and never claims to have opened them; and `inspect_sqlite` opens a real local
file, describes it, and the only thing it ever does is read (the audit proves it).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from evalloop.connect.discover import DATABASE, VECTOR_STORE
from evalloop.connect.scan import inspect_sqlite, render_scan, scan


def _repo(root: Path) -> Path:
    (root / ".env").write_text("DATABASE_URL=postgres://u:p@prod-db.example.com/app\nQDRANT_URL=http://localhost:6333\n")
    (root / "docker-compose.yml").write_text("services:\n  db:\n    image: postgres:16\n")
    return root


def test_scan_finds_and_classifies_without_opening(tmp_path: Path) -> None:
    report = scan(_repo(tmp_path))
    assert report.findings, "a repo with a DB and a vector store should produce findings"
    assert {f.candidate.category for f in report.findings} == {DATABASE, VECTOR_STORE}
    # Every finding must say what it still needs; discovery never learns a live host or credential.
    for finding in report.findings:
        assert "credentials" in finding.requirement
        assert finding.candidate.host is None


def test_scan_separates_databases_from_vector_stores(tmp_path: Path) -> None:
    report = scan(_repo(tmp_path))
    assert len(report.databases) >= 1
    assert len(report.vector_stores) == 1


def test_render_is_deterministic(tmp_path: Path) -> None:
    report = scan(_repo(tmp_path))
    assert render_scan(report) == render_scan(report)


def test_empty_repo_scans_clean(tmp_path: Path) -> None:
    report = scan(tmp_path)
    assert report.findings == ()
    assert "no databases or vector stores" in render_scan(report)


def _sqlite_file(root: Path) -> Path:
    path = root / "shop.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO customers VALUES (1, 'alice')")
    conn.commit()
    conn.close()
    return path


def test_inspect_sqlite_opens_read_only_and_describes(tmp_path: Path) -> None:
    inspection = inspect_sqlite(_sqlite_file(tmp_path))
    assert inspection.probe.reachable
    assert inspection.probe.read_only
    assert inspection.read_only
    assert [t.name for t in inspection.schema.tables] == ["customers"]
    assert [c.name for c in inspection.schema.tables[0].columns] == ["id", "name"]


def test_inspect_sqlite_audit_is_reads_only(tmp_path: Path) -> None:
    inspection = inspect_sqlite(_sqlite_file(tmp_path))
    kinds = {kind for entry in inspection.audit for kind in entry.statement_kinds}
    assert kinds <= {"probe", "describe", "read"}
    assert kinds, "probe + describe should both be audited"
