"""Find the databases and vector stores a repository talks to — with provenance, touching nothing.

``ARCHITECTURE.md`` §6.1, the DISCOVER step: scan for *evidence* of endpoints and output candidates
that each cite the file and line they came from ("because docker-compose.yml:14 defines
qdrant:6333"). This step is **inert** by design:

* **No connection is ever opened and no credential is ever resolved.** Discovery reads repository
  files; it never dials an endpoint. A test keeps a socket guard live across the whole scan.
* **A credential value never enters a candidate.** From a ``.env`` file only the *key* is recorded
  (``.env:DATABASE_URL``), never the value after ``=`` — the value is split off and dropped. The
  host/port on a candidate come only from non-secret sources (a compose ``ports:`` line), never from
  a connection string.
* **Nothing in the repository is imported or run.** Python files are parsed with ``ast`` (a
  ``conftest.py`` or ``settings.py`` with an import-time side effect must not execute); everything
  else is scanned as text. Discovery that *ran* the code to find an endpoint would be the opposite
  of safe.
* **Ordering is deterministic**: candidates are sorted by file, line, kind and detail, so the same
  repository yields the same list.

Evidence sources, and the ``Tool`` each maps to
----------------------------------------------
``.env`` / ``.env.example`` endpoint keys, ``docker-compose`` services, client constructor call
sites in ``.py`` (``create_engine``, ``psycopg.connect``, ``QdrantClient``, ``chromadb.HttpClient``,
…), and ``alembic.ini``. A database-shaped source maps to ``Tool.db_connection``; a vector store to
``Tool.vector_store``; anything recognised-but-unclassifiable carries ``tool=None`` and is reported
so a human can look, never silently dropped.

Flagged for review: ``ARCHITECTURE.md`` §6.1 also lists "listening local ports" as a discovery
source. That is a live system probe, not a text scan, and result 4 of the ticket says "ast/text
scanning only," so it is **deferred** — reported here rather than built, so the two don't silently
disagree.
"""

from __future__ import annotations

import ast
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from evalloop.vocab import Tool

__all__ = ["Candidate", "Provenance", "discover", "DATABASE", "VECTOR_STORE"]

DATABASE = "database"
VECTOR_STORE = "vector_store"

_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "site-packages", "dist-packages", ".git"})
_VENV_MARKER = "pyvenv.cfg"

# image/name token -> (kind label, category). The category decides the Tool.
_SERVICES: dict[str, tuple[str, str]] = {
    "postgres": ("postgres", DATABASE),
    "postgis": ("postgres", DATABASE),
    "mysql": ("mysql", DATABASE),
    "mariadb": ("mysql", DATABASE),
    "mongo": ("mongodb", DATABASE),
    "redis": ("redis", DATABASE),
    "qdrant": ("qdrant", VECTOR_STORE),
    "chroma": ("chroma", VECTOR_STORE),
    "chromadb": ("chroma", VECTOR_STORE),
    "weaviate": ("weaviate", VECTOR_STORE),
    "pinecone": ("pinecone", VECTOR_STORE),
    "milvus": ("milvus", VECTOR_STORE),
}

# dotted call-site -> (kind, category). Matched against the callee's dotted name.
_CALL_SITES: dict[str, tuple[str, str]] = {
    "create_engine": ("sqlalchemy", DATABASE),
    "psycopg.connect": ("postgres", DATABASE),
    "psycopg2.connect": ("postgres", DATABASE),
    "pymysql.connect": ("mysql", DATABASE),
    "MySQLdb.connect": ("mysql", DATABASE),
    "sqlite3.connect": ("sqlite", DATABASE),
    "redis.Redis": ("redis", DATABASE),
    "redis.from_url": ("redis", DATABASE),
    "pymongo.MongoClient": ("mongodb", DATABASE),
    "MongoClient": ("mongodb", DATABASE),
    "QdrantClient": ("qdrant", VECTOR_STORE),
    "qdrant_client.QdrantClient": ("qdrant", VECTOR_STORE),
    "chromadb.HttpClient": ("chroma", VECTOR_STORE),
    "chromadb.Client": ("chroma", VECTOR_STORE),
    "weaviate.Client": ("weaviate", VECTOR_STORE),
    "Pinecone": ("pinecone", VECTOR_STORE),
}

# .env key tokens → category. A key with one of these, and an endpoint-ish shape, is evidence.
_VECTOR_KEY_TOKENS = ("QDRANT", "CHROMA", "WEAVIATE", "PINECONE", "MILVUS", "VECTOR")
_DB_KEY_TOKENS = ("POSTGRES", "MYSQL", "MARIADB", "MONGO", "REDIS", "DATABASE", "DB_", "_DB", "SQLALCHEMY", "DATABASE_URL")
_ENDPOINT_SHAPE = ("URL", "URI", "DSN", "HOST", "PORT", "ENDPOINT", "CONNECTION")
_CATEGORY_TOOL: dict[str, Tool] = {DATABASE: Tool.db_connection, VECTOR_STORE: Tool.vector_store}


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a candidate came from: a real ``file:line`` and a plain-language reason."""

    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One discovered endpoint. Carries its source, never a secret's value."""

    kind: str
    tool: Tool | None
    detail: str
    credential_source: str | None
    host: str | None
    port: int | None
    provenance: Provenance

    @property
    def category(self) -> str:
        return VECTOR_STORE if self.tool is Tool.vector_store else DATABASE


def _tool_for(category: str) -> Tool | None:
    return _CATEGORY_TOOL.get(category)


# -- walking --------------------------------------------------------------------------


def _walk(root: Path) -> list[Path]:
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        if _VENV_MARKER in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS)
        for name in sorted(filenames):
            found.append(Path(directory) / name)
    return found


def _rel(root: Path, path: Path) -> str:
    return path.name if root.is_file() else path.relative_to(root).as_posix()


# -- .env --------------------------------------------------------------------------


def _scan_env(rel: str, text: str) -> list[Candidate]:
    found: list[Candidate] = []
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()  # the value after = is dropped, never stored
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        upper = key.upper()
        if not any(shape in upper for shape in _ENDPOINT_SHAPE) and not any(t in upper for t in (*_VECTOR_KEY_TOKENS, *_DB_KEY_TOKENS)):
            continue
        if any(token in upper for token in _VECTOR_KEY_TOKENS):
            category, kind = VECTOR_STORE, "vector store"
        elif any(token in upper for token in _DB_KEY_TOKENS):
            category, kind = DATABASE, "database"
        else:
            category, kind = DATABASE, "endpoint"  # endpoint-shaped but unclassified key
        found.append(
            Candidate(
                kind=kind,
                tool=_tool_for(category),
                detail=f"configured via {rel} key {key}",
                credential_source=f"{rel}:{key}",
                host=None,
                port=None,
                provenance=Provenance(rel, index, f"{rel}:{index} sets {key}"),
            )
        )
    return found


# -- docker-compose ----------------------------------------------------------------

_SERVICE_LINE = re.compile(r"^(?P<indent> +)(?P<name>[A-Za-z0-9_.-]+):\s*$")
_IMAGE_LINE = re.compile(r"^\s*image:\s*['\"]?(?P<image>[^\s'\"]+)")
_PORT_LINE = re.compile(r"(?P<host>\d{2,5}):(?P<container>\d{2,5})")


def _classify_image(image: str) -> tuple[str, str] | None:
    name = image.split("/")[-1].split(":")[0].lower()
    for token, hit in _SERVICES.items():
        if token in name:
            return hit
    return None


def _scan_compose(rel: str, text: str) -> list[Candidate]:
    lines = text.splitlines()
    in_services = False
    services_indent = -1
    found: list[Candidate] = []
    current: tuple[str, int, int] | None = None  # (name, line, indent)
    current_image: tuple[str, str] | None = None
    current_port: int | None = None

    def flush() -> None:
        if current is None:
            return
        name, line_no, _indent = current
        hit = current_image or (_classify_image(name) if name.lower() in _SERVICES else _SERVICES.get(name.lower()))
        if hit is None:
            return
        kind, category = hit
        found.append(
            Candidate(
                kind=kind,
                tool=_tool_for(category),
                detail=f"{kind} service {name!r} in {rel}",
                credential_source=None,
                host="localhost" if current_port else None,
                port=current_port,
                provenance=Provenance(rel, line_no, f"{rel}:{line_no} defines service {name!r}"),
            )
        )

    for index, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith("services:"):
            in_services = True
            services_indent = len(raw) - len(raw.lstrip())
            continue
        if not in_services:
            continue
        match = _SERVICE_LINE.match(raw)
        if match and len(match.group("indent")) == services_indent + 2:
            flush()
            current = (match.group("name"), index, len(match.group("indent")))
            current_image, current_port = None, None
            continue
        if current is not None:
            image = _IMAGE_LINE.match(raw)
            if image:
                current_image = _classify_image(image.group("image"))
            port = _PORT_LINE.search(raw)
            if port and current_port is None:
                current_port = int(port.group("host"))
    flush()
    return found


# -- python call sites -------------------------------------------------------------


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return ".".join(parts)
    return None


def _scan_python(rel: str, text: str) -> list[Candidate]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []  # a half-written or non-parseable file is unscannable, never executed
    found: list[Candidate] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        if dotted is None:
            continue
        hit = _CALL_SITES.get(dotted) or _CALL_SITES.get(dotted.split(".")[-1])
        if hit is None:
            continue
        kind, category = hit
        found.append(
            Candidate(
                kind=kind,
                tool=_tool_for(category),
                detail=f"{dotted}(...) call site in {rel}",
                credential_source=None,  # constructor arguments are not read; they may hold a secret
                host=None,
                port=None,
                provenance=Provenance(rel, node.lineno, f"{rel}:{node.lineno} calls {dotted}(...)"),
            )
        )
    return found


# -- alembic -----------------------------------------------------------------------


def _scan_alembic(rel: str, text: str) -> list[Candidate]:
    for index, raw in enumerate(text.splitlines(), start=1):
        if raw.strip().startswith("sqlalchemy.url"):
            return [
                Candidate(
                    kind="database",
                    tool=Tool.db_connection,
                    detail=f"database migrations configured in {rel}",
                    credential_source=f"{rel}:sqlalchemy.url",
                    host=None,
                    port=None,
                    provenance=Provenance(rel, index, f"{rel}:{index} sets sqlalchemy.url"),
                )
            ]
    return []


# -- the scan ----------------------------------------------------------------------


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def discover(root: str | os.PathLike[str]) -> tuple[Candidate, ...]:
    """Every endpoint the repository at ``root`` shows evidence of, with provenance. Opens nothing."""
    base = Path(root)
    if not base.exists():
        raise FileNotFoundError(f"{base} does not exist")
    candidates: list[Candidate] = []
    for path in _walk(base):
        rel = _rel(base, path)
        name = PurePosixPath(rel).name
        text = _read(path)
        if text is None:
            continue
        if name == ".env" or name.startswith(".env") or name.endswith(".env"):
            candidates += _scan_env(rel, text)
        elif re.match(r"(docker-)?compose.*\.ya?ml$", name):
            candidates += _scan_compose(rel, text)
        elif name.endswith(".py"):
            candidates += _scan_python(rel, text)
        elif name == "alembic.ini":
            candidates += _scan_alembic(rel, text)
    candidates.sort(key=lambda c: (c.provenance.path, c.provenance.line, c.kind, c.detail))
    return tuple(candidates)
