"""Connector discovery: finds endpoints with provenance, and provably touches nothing.

The sample repo is built in ``tmp_path`` (not committed), so no ``.env`` or stray test file lands in
the project tree. The two load-bearing proofs are that discovery opens no socket and runs no
repository code, and that a planted secret never reaches a candidate.
"""

from __future__ import annotations

import socket
import textwrap
from pathlib import Path

import pytest

from evalloop.connect import Candidate, discover
from evalloop.connect.discover import DATABASE, VECTOR_STORE
from evalloop.vocab import Tool

_SECRET = "SUPERSECRETpassword123"
_SENTINEL = "evalloop_discover_executed_repo_code"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    (root / "app").mkdir(parents=True)
    (root / ".env").write_text(
        f"DATABASE_URL=postgresql://user:{_SECRET}@localhost:5432/shop\n"
        "QDRANT_URL=http://localhost:6333\n"
        "OPENAI_API_KEY=sk-not-an-endpoint\n",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        textwrap.dedent(
            """
            services:
              db:
                image: postgres:16
                ports:
                  - "5432:5432"
              qdrant:
                image: qdrant/qdrant:latest
                ports:
                  - "6333:6333"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (root / "app" / "db.py").write_text(
        "from sqlalchemy import create_engine\n"
        "from qdrant_client import QdrantClient\n\n"
        "engine = create_engine('postgresql://x')\n"
        "client = QdrantClient(url='http://localhost:6333')\n",
        encoding="utf-8",
    )
    # If discovery imported this module, it would write a sentinel and raise. It must do neither.
    (root / "settings.py").write_text(
        f"import pathlib\n"
        f"pathlib.Path({str(tmp_path / _SENTINEL)!r}).write_text('ran')\n"
        f"raise RuntimeError('settings.py was imported during discovery')\n",
        encoding="utf-8",
    )
    (root / "alembic.ini").write_text(
        f"[alembic]\nsqlalchemy.url = postgresql://user:{_SECRET}@localhost/shop\n", encoding="utf-8"
    )
    return root


def _kinds(candidates: tuple[Candidate, ...]) -> set[str]:
    return {c.kind for c in candidates}


# -- it finds the endpoints, with provenance -------------------------------------------


def test_finds_the_database_and_vector_store_from_several_sources(repo: Path) -> None:
    found = discover(repo)
    assert found, "discovery found nothing"
    # postgres shows up from .env, compose, the create_engine call, and alembic; qdrant from .env,
    # compose, and the QdrantClient call.
    assert "postgres" in _kinds(found) and "qdrant" in _kinds(found)
    sources = {(c.kind, c.provenance.path) for c in found}
    assert ("postgres", "docker-compose.yml") in sources
    assert ("qdrant", "docker-compose.yml") in sources
    assert ("sqlalchemy", "app/db.py") in sources
    assert ("qdrant", "app/db.py") in sources


def test_every_candidate_provenance_resolves(repo: Path) -> None:
    for c in discover(repo):
        lines = (repo / c.provenance.path).read_text(encoding="utf-8").splitlines()
        assert 1 <= c.provenance.line <= len(lines)
        assert lines[c.provenance.line - 1].strip() != ""


def test_tools_map_database_and_vector_store(repo: Path) -> None:
    by_kind = {c.kind: c for c in discover(repo)}
    assert by_kind["postgres"].tool is Tool.db_connection
    assert by_kind["qdrant"].tool is Tool.vector_store
    assert by_kind["postgres"].category == DATABASE and by_kind["qdrant"].category == VECTOR_STORE


def test_a_compose_service_carries_its_host_and_port(repo: Path) -> None:
    compose = [c for c in discover(repo) if c.provenance.path == "docker-compose.yml" and c.kind == "qdrant"]
    assert compose and compose[0].host == "localhost" and compose[0].port == 6333


# -- it is inert: no connection, no running of repo code -------------------------------


def test_discovery_opens_no_socket(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("discovery opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert discover(repo)  # completes with the guard live


def test_discovery_does_not_import_or_run_repo_code(repo: Path, tmp_path: Path) -> None:
    discover(repo)  # settings.py would write a sentinel and raise if imported
    assert not (tmp_path / _SENTINEL).exists()


# -- it never leaks a secret -----------------------------------------------------------


def test_a_credential_value_never_appears_in_a_candidate(repo: Path) -> None:
    for c in discover(repo):
        blob = " ".join(
            str(x) for x in (c.detail, c.credential_source, c.host, c.port, c.provenance.reason)
        )
        assert _SECRET not in blob
    # The .env and alembic candidates cite the key/source, not the value.
    env = [c for c in discover(repo) if c.credential_source and c.credential_source.startswith(".env")]
    assert env and all(":" in c.credential_source for c in env if c.credential_source)


def test_a_non_endpoint_key_is_not_reported(repo: Path) -> None:
    # OPENAI_API_KEY is a secret but not a database/vector endpoint; it must not become a candidate.
    assert all("OPENAI" not in (c.credential_source or "") for c in discover(repo))


# -- deterministic ---------------------------------------------------------------------


def test_discovery_is_deterministic(repo: Path) -> None:
    assert discover(repo) == discover(repo)
    paths = [(c.provenance.path, c.provenance.line) for c in discover(repo)]
    assert paths == sorted(paths)
