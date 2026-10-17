"""The automatic data-access validator: extract a file's SQL and check it read-only against a DB.

The load-bearing proofs: SQL is extracted from a Python file whether in ``.execute(...)`` or assigned
to a name; a read query that is schema-grounded passes; a write is flagged as a read-only violation;
a hallucinated column or missing table hard-fails with the DB's own error; and the database is only
ever read (the check cannot change data).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from evalloop.grade.dbcheck import check_file, extract_queries, find_sqlite


def _db(tmp: Path) -> Path:
    path = tmp / "app.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users(id INTEGER, name TEXT, country TEXT)")
    conn.executemany("INSERT INTO users VALUES (?,?,?)", [(1, "ada", "US"), (2, "bob", "GB")])
    conn.commit()
    conn.close()
    return path


_SRC = """
GET_US = "SELECT id, name FROM users WHERE country = 'US'"
def fetch_us(conn): return conn.execute(GET_US).fetchall()
def bad_col(conn): return conn.execute("SELECT id, nope FROM users").fetchall()
def bad_tbl(conn): return conn.execute("SELECT * FROM orders").fetchall()
def wipes(conn): conn.execute("DELETE FROM users WHERE id = 1")
"""


def test_extracts_sql_from_execute_and_assignment() -> None:
    qs = extract_queries(_SRC)
    assert any(q.startswith("SELECT id, name") for q in qs)   # assigned to a name
    assert any("DELETE" in q for q in qs)                      # inline in .execute(...)
    assert len(qs) == 4


def test_find_sqlite(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert find_sqlite(tmp_path) == db
    assert find_sqlite(tmp_path / "nope") is None


def test_the_layers_pass_read_fail_write_and_fail_bad_schema(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "repo.py").write_text(_SRC)
    by_cat = {c.category: c for c in check_file(tmp_path / "repo.py", db)}
    assert by_cat["shape"].verdict == "passed" and "1 row" in by_cat["shape"].detail
    assert by_cat["read_only"].verdict == "failed" and "DELETE" in by_cat["read_only"].detail
    # both the bad column and the missing table are schema failures (last one wins the dict key)
    schema_fails = [c for c in check_file(tmp_path / "repo.py", db) if c.category == "schema"]
    assert {c.verdict for c in schema_fails} == {"failed"}
    assert any("no such column" in c.detail for c in schema_fails)
    assert any("no such table" in c.detail for c in schema_fails)


def test_the_database_is_never_written(tmp_path: Path) -> None:
    db = _db(tmp_path)
    (tmp_path / "repo.py").write_text(_SRC)
    check_file(tmp_path / "repo.py", db)   # includes a DELETE query
    conn = sqlite3.connect(db)
    remaining = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    assert remaining == 2, "the DELETE must never have run — validation is read-only"


def test_a_file_without_sql_yields_nothing(tmp_path: Path) -> None:
    (tmp_path / "plain.py").write_text("def add(a, b):\n    return a + b\n")
    assert check_file(tmp_path / "plain.py", _db(tmp_path)) == []
