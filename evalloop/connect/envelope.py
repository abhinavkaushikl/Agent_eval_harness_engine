"""The read-only envelope: three independent layers that make untrusted, AI-written SQL safe to run.

The SQL that reaches a real database here was written by a model and **not read by the developer**.
``ARCHITECTURE.md`` §9: "Generated SQL contains DROP → AST reject before transmission, plus read-only
transaction, plus caps. Three INDEPENDENT layers." A live connection is not an excuse to skip this —
it is the reason for it.

The three layers, and why they are independent
----------------------------------------------
1. **Static rejection (before a byte is sent).** :func:`reject_writes` splits the SQL into
   statements and classifies each. The policy is *default-deny*: a statement runs only if its
   effective leading keyword is a read (``SELECT`` / ``VALUES`` / ``WITH…SELECT`` / non-executing
   ``EXPLAIN`` / ``SHOW`` / ``TABLE``), and a backstop scan rejects any DML/DDL keyword
   (``DROP``/``DELETE``/``UPDATE``/``INSERT``/``ALTER``/``TRUNCATE``/``GRANT``…) anywhere a string
   literal is not hiding it. A ``DROP TABLE`` never reaches :meth:`Executor.run`.
2. **Read-only transaction.** The envelope refuses to run a read against an executor that is not in
   read-only mode (:attr:`Executor.read_only`). The database enforces it too, so a write that slips
   layer 1 still fails at the wire — proven by the independence test, which disables layer 1 and
   watches layer 2 block the write.
3. **Row / byte caps.** From the grant (:class:`~evalloop.capability.broker.Caps`, decision EL-006).
   Enforced on the result and recorded with it.

**Layer 4 — writes never touch the live schema.** A statement that must write is rejected outright
unless a :class:`WriteScope` names a scratch schema or a restored snapshot. There is no "live" scope
to construct, and destructive DDL is rejected even then.

**Layer 5 — an append-only, redacted audit log.** Every statement sent, its endpoint, the caps in
force, and the result shape are recorded with :class:`AuditLog`. The SQL is redacted (string and
numeric literals → ``?``) *before* it is stored, so nothing unredacted is ever persisted.

No SQL parser library is used (``CLAUDE.md`` §1, no PyYAML-style deps): layer 1 is a minimal
statement classifier over masked tokens. It is deliberately conservative — an ambiguous statement is
rejected, never waved through. This module opens no connection and imports no database driver
(decision EL-006); the concrete executor is EL-306.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from evalloop.capability.broker import Caps

__all__ = [
    "StatementKind",
    "Statement",
    "classify_statements",
    "reject_writes",
    "WriteScope",
    "Executor",
    "Caps",
    "ResultShape",
    "Result",
    "AuditEntry",
    "AuditLog",
    "ReadOnlyEnvelope",
    "EnvelopeError",
    "ReadOnlyViolation",
    "NotReadOnly",
    "redact_sql",
]

# -- the keyword policy ----------------------------------------------------------------

# A statement runs only if its effective leading keyword is one of these.
_READ_LEADERS = frozenset({"SELECT", "VALUES", "WITH", "EXPLAIN", "SHOW", "TABLE", "DESCRIBE", "DESC"})
# Writes to data. Allowed only under a WriteScope (scratch schema / snapshot), never on the live schema.
_DML = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "REPLACE"})
# Changes to schema or permissions. Rejected always — untrusted SQL never issues these.
_DDL = frozenset(
    {
        "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE", "RENAME", "COMMENT",
        "ATTACH", "DETACH", "VACUUM", "REINDEX", "CLUSTER", "COPY", "IMPORT", "LOAD",
        "CALL", "EXEC", "EXECUTE", "DO", "LOCK", "PRAGMA", "COMMIT",
        "ROLLBACK", "SAVEPOINT",
    }
)
# Write-intent clauses that can appear inside an otherwise read-shaped statement.
_WRITE_INTENT = (("FOR", "UPDATE"), ("FOR", "SHARE"), ("INTO",))

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class StatementKind:
    """The three verdicts layer 1 can reach for one statement."""

    READ = "read"
    DML = "dml"
    DDL = "ddl"


@dataclass(frozen=True, slots=True)
class Statement:
    """One classified statement: what it is, and the keyword that decided it."""

    index: int
    kind: str  # StatementKind.*
    keyword: str
    text: str  # original, un-redacted — never persisted; redacted at the audit boundary


class EnvelopeError(Exception):
    """Base class for an envelope refusal."""


class ReadOnlyViolation(EnvelopeError):
    """Layer 1: a statement would write and is not allowed to reach the wire."""

    def __init__(self, statement: Statement, reason: str) -> None:
        self.statement = statement
        super().__init__(reason)


class NotReadOnly(EnvelopeError):
    """Layer 2: the executor is not in a read-only transaction and no write scope was given."""


# -- layer 4: the only legitimate place a write may land -------------------------------


@dataclass(frozen=True, slots=True)
class WriteScope:
    """Where a write is permitted to go. A scratch schema or a restored snapshot — never the live schema."""

    kind: str  # "scratch_schema" | "snapshot"
    name: str

    _KINDS = ("scratch_schema", "snapshot")

    def __post_init__(self) -> None:
        if self.kind not in self._KINDS:
            raise ValueError(
                f"a write scope is a scratch schema or a snapshot, never {self.kind!r} — "
                "the live schema is not a writable target"
            )
        if not self.name:
            raise ValueError("a write scope must name its scratch schema or snapshot")

    @classmethod
    def scratch_schema(cls, name: str) -> WriteScope:
        return cls("scratch_schema", name)

    @classmethod
    def snapshot(cls, name: str) -> WriteScope:
        return cls("snapshot", name)


# -- layer 1: static classification ----------------------------------------------------


def _strip_comments(sql: str) -> str:
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", sql))


def _split_statements(sql: str) -> list[str]:
    """Split on top-level ``;``, ignoring semicolons inside string literals."""
    masked = _STRING.sub(lambda m: " " * len(m.group()), _strip_comments(sql))
    parts: list[str] = []
    start = 0
    for i, ch in enumerate(masked):
        if ch == ";":
            parts.append(sql[start:i])
            start = i + 1
    parts.append(sql[start:])
    return [p for p in parts if p.strip()]


def _words(statement: str) -> list[str]:
    """Upper-cased identifier tokens with string literals masked out, so keywords in strings don't count."""
    masked = _STRING.sub(" ", _strip_comments(statement))
    return [m.group().upper() for m in _WORD.finditer(masked)]


def _has_sequence(tokens: Sequence[str], seq: tuple[str, ...]) -> bool:
    n = len(seq)
    return any(tuple(tokens[i : i + n]) == seq for i in range(len(tokens) - n + 1))


def _classify_one(index: int, text: str) -> Statement:
    tokens = _words(text)
    if not tokens:
        return Statement(index, StatementKind.READ, "", text)  # a bare comment / whitespace
    leader = tokens[0]

    # Backstop first: a DDL keyword anywhere is a hard reject, whatever the leader looked like.
    ddl = next((t for t in tokens if t in _DDL), None)
    if ddl is not None:
        return Statement(index, StatementKind.DDL, ddl, text)
    dml = next((t for t in tokens if t in _DML), None)
    if dml is not None:
        return Statement(index, StatementKind.DML, dml, text)
    if any(_has_sequence(tokens, seq) for seq in _WRITE_INTENT):
        return Statement(index, StatementKind.DML, "INTO/FOR UPDATE", text)

    # Default-deny: only a read leader survives. (WITH…SELECT and EXPLAIN without a write reach here
    # precisely because no DML/DDL token was found above.)
    if leader in _READ_LEADERS:
        return Statement(index, StatementKind.READ, leader, text)
    return Statement(index, StatementKind.DDL, leader, text)


def classify_statements(sql: str) -> tuple[Statement, ...]:
    """Split ``sql`` and classify each statement. Pure; opens nothing."""
    return tuple(_classify_one(i, text) for i, text in enumerate(_split_statements(sql)))


def reject_writes(sql: str, write_scope: WriteScope | None = None) -> tuple[Statement, ...]:
    """Layer 1. Return the statements if all are allowed; raise :class:`ReadOnlyViolation` otherwise.

    Reads are always allowed. DML is allowed only under a ``write_scope``. DDL is never allowed.
    """
    statements = classify_statements(sql)
    for st in statements:
        if st.kind == StatementKind.READ:
            continue
        if st.kind == StatementKind.DML and write_scope is not None:
            continue
        if st.kind == StatementKind.DDL:
            raise ReadOnlyViolation(
                st, f"statement {st.index} is schema/permission-changing ({st.keyword}); it never reaches the wire"
            )
        raise ReadOnlyViolation(
            st,
            f"statement {st.index} writes data ({st.keyword}) and no scratch-schema/snapshot scope was given; "
            "it never reaches the wire",
        )
    return statements


# -- layer 2 + 3 plumbing --------------------------------------------------------------


@runtime_checkable
class Executor(Protocol):
    """The thing that actually reaches the database. Supplied by EL-306; the envelope never connects."""

    read_only: bool

    def run(self, sql: str, *, max_rows: int | None) -> Sequence[Sequence[object]]: ...


@dataclass(frozen=True, slots=True)
class ResultShape:
    """What came back, by shape only — never the values."""

    row_count: int
    byte_count: int
    truncated: bool


def _enforce_caps(rows: Sequence[Sequence[object]], caps: Caps) -> tuple[list[Sequence[object]], ResultShape]:
    """Layer 3. Cap rows and bytes, reporting whether the result was truncated."""
    truncated = False
    capped: list[Sequence[object]] = list(rows)
    if caps.max_rows is not None and len(capped) > caps.max_rows:
        capped = capped[: caps.max_rows]
        truncated = True
    byte_count = 0
    for i, row in enumerate(capped):
        row_bytes = len(str(tuple(row)).encode("utf-8"))
        if caps.max_bytes is not None and byte_count + row_bytes > caps.max_bytes:
            capped = capped[:i]
            truncated = True
            break
        byte_count += row_bytes
    return capped, ResultShape(len(capped), byte_count, truncated)


# -- layer 5: the audit log ------------------------------------------------------------


def redact_sql(sql: str) -> str:
    """Replace every string and numeric literal with ``?``. The structure survives; no value does."""
    redacted = _STRING.sub("?", sql)
    return _NUMBER.sub("?", redacted)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One line of the append-only log. Holds no un-redacted SQL and no credential."""

    endpoint: str
    redacted_sql: str
    statement_kinds: tuple[str, ...]
    caps: Caps
    write_scope: str | None
    result: ResultShape | None
    error: str | None


@dataclass
class AuditLog:
    """Append-only. Entries can be added and read; there is no method to mutate or remove one.

    An optional ``sink`` path is opened in append mode and one redacted line is written per entry.
    """

    sink: str | None = None
    _entries: list[AuditEntry] = field(default_factory=list)

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)
        if self.sink is not None:
            line = f"{entry.endpoint}\t{'|'.join(entry.statement_kinds)}\t{entry.redacted_sql}\t{entry.error or 'ok'}\n"
            with open(self.sink, "a", encoding="utf-8") as fh:
                fh.write(line)

    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# -- the envelope ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Result:
    """A capped, audited read result. Rows are returned to the caller but never persisted."""

    rows: tuple[Sequence[object], ...]
    shape: ResultShape
    statements: tuple[Statement, ...]


class ReadOnlyEnvelope:
    """Runs untrusted SQL through all three layers and records every attempt in the audit log.

    ``static_guard`` is injectable so a test can disable layer 1 and watch layer 2 hold on its own;
    in production it is always :func:`reject_writes`.
    """

    def __init__(
        self,
        audit: AuditLog,
        *,
        static_guard: Callable[[str, WriteScope | None], Sequence[Statement]] = reject_writes,
    ) -> None:
        self._audit = audit
        self._static_guard = static_guard

    @property
    def audit(self) -> AuditLog:
        """The append-only log this envelope writes to — so a connector can record probe/describe too."""
        return self._audit

    def execute(
        self,
        sql: str,
        *,
        endpoint: str,
        caps: Caps,
        executor: Executor,
        write_scope: WriteScope | None = None,
    ) -> Result:
        # Layer 1 — reject writes before a byte is sent.
        statements = tuple(self._static_guard(sql, write_scope))

        # Layer 2 — a read must run in a read-only transaction. A write must name a scratch scope.
        if write_scope is None and not executor.read_only:
            raise NotReadOnly(
                f"refusing to run against {endpoint!r}: the transaction is not read-only and no write scope was given"
            )

        kinds = tuple(st.kind for st in statements)
        try:
            raw = executor.run(sql, max_rows=caps.max_rows)
        except Exception as exc:  # the DB (layer 2, enforced at the wire) rejected it — audit, then surface
            self._audit.append(
                AuditEntry(endpoint, redact_sql(sql), kinds, caps, _scope_label(write_scope), None, repr(exc))
            )
            raise

        # Layer 3 — cap rows and bytes, record the shape.
        capped, shape = _enforce_caps(raw, caps)
        self._audit.append(
            AuditEntry(endpoint, redact_sql(sql), kinds, caps, _scope_label(write_scope), shape, None)
        )
        return Result(tuple(capped), shape, statements)


def _scope_label(scope: WriteScope | None) -> str | None:
    return None if scope is None else f"{scope.kind}:{scope.name}"
