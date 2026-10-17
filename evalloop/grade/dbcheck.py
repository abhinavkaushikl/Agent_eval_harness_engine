"""Automatic, no-oracle validation of a data-access file's SQL against a read-only snapshot.

When you save a ``.py`` that talks to a database, EvalLoop does **not** run your Python (hard to do
safely) and does **not** need a spec. It extracts the SQL your file issues and runs the layers that
need nothing from you, through the EL-305 read-only envelope against a SQLite snapshot:

* **read-only safety** — a data-fetch path must only READ; an ``INSERT``/``UPDATE``/``DELETE``/DDL is
  flagged (and the envelope would reject it before the wire anyway);
* **schema grounding** — the query references real tables/columns (a hallucinated one hard-fails with
  the database's own error);
* **executes** — the statement actually runs (no syntax error);
* **shape** — how many rows come back.

Correctness — are the rows *right* — is deliberately NOT here: nothing can know your intended result
for free, so that stays an opt-in reference query (the ``sql`` eval spec). This module only reads,
through a read-only connection, so it can never change your data.
"""

from __future__ import annotations

import ast
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from evalloop.connect.envelope import StatementKind, classify_statements
from evalloop.grade.sql_execution import Snapshot

__all__ = ["DbCase", "extract_queries", "check_file", "find_sqlite", "SQL_LEADERS"]

SQL_LEADERS = ("select", "with", "insert", "update", "delete", "create", "drop", "alter", "replace", "truncate")
_LEADS = re.compile(r"^\s*(" + "|".join(SQL_LEADERS) + r")\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DbCase:
    """One extracted query and how it fared on the no-oracle layers."""

    name: str        # a short label (the query, flattened and truncated)
    verdict: str     # "passed" | "failed"
    detail: str
    category: str    # read_only | schema | executes | shape
    query: str


def extract_queries(source: str) -> list[str]:
    """Every SQL string literal in a Python file — whether in ``.execute(...)`` or assigned to a name.

    Pure AST: a string constant whose first keyword is SQL is treated as a query. A non-parseable
    file yields nothing (never executed).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _LEADS.match(node.value):
            q = node.value.strip()
            if q not in seen:
                seen.add(q)
                out.append(q)
    return out


def _label(query: str) -> str:
    flat = " ".join(query.split())
    return flat[:52] + ("…" if len(flat) > 52 else "")


def find_sqlite(root: str | os.PathLike[str]) -> Path | None:
    """The first SQLite database file under ``root`` (``*.db`` / ``*.sqlite`` / ``*.sqlite3``)."""
    base = Path(root)
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        for path in sorted(base.rglob(pattern)):
            if path.is_file() and ".evalloop" not in path.parts:
                return path
    return None


def check_file(py_path: str | os.PathLike[str], db_path: str | os.PathLike[str]) -> list[DbCase]:
    """Run the no-oracle layers on every query in ``py_path`` against the read-only ``db_path``."""
    try:
        source = Path(py_path).read_text(encoding="utf-8")
    except OSError:
        return []
    queries = extract_queries(source)
    if not queries:
        return []
    snapshot = Snapshot(Path(db_path))  # read-only (mode=ro, query_only) via the envelope + connector
    cases: list[DbCase] = []
    try:
        for query in queries:
            label = _label(query)
            statements = classify_statements(query)
            writes = [s for s in statements if s.kind != StatementKind.READ]
            if writes:
                cases.append(DbCase(
                    label, "failed", f"issues a {writes[0].keyword} — a data-fetch path must only read",
                    "read_only", query))
                continue
            try:
                rows = snapshot.rows(query)
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                category = "schema" if ("no such column" in msg or "no such table" in msg) else "executes"
                cases.append(DbCase(label, "failed", str(exc), category, query))
                continue
            except sqlite3.DatabaseError as exc:
                cases.append(DbCase(label, "failed", f"{type(exc).__name__}: {exc}", "executes", query))
                continue
            cases.append(DbCase(
                label, "passed", f"read-only, schema-grounded, returned {len(rows)} row(s)", "shape", query))
    finally:
        snapshot.close()
    return cases
