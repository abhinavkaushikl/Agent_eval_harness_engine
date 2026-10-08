"""The episodic store: what EvalLoop decided about each episode, and why, in SQLite.

``AGENT.md`` §3.9: "Episodic store: SQLite. Situation decisions *and the
reasoning* are persisted." The reasoning is the point. A store of verdicts
cannot answer the question this one exists for -- a developer, days later,
asking why EvalLoop concluded what it did -- so **every decision is refused
without its reasoning**, the way the planner refuses a "no" without a reason.

Three decisions per episode, in pipeline order
----------------------------------------------
1. **Classification** -- the situations, each with a confidence and the reason
   for it (``AGENT.md`` §3.4's multi-label output, one row per situation), or
   an abstention with the reason nothing could be said.
2. **Plan** -- the planner's output as it produced it: all four states keyed by
   record id, the companion edges, the missing tools, its own reasons verbatim,
   and its ``render()`` text, plus the situations it was computed from.
3. **Verdicts** -- per artifact, per ready technique, with the reasoning.

Each decision is linked to the one before it, by foreign key, so the chain
holds by construction: a plan may only use situations the classification
recorded, and a verdict may only come from a technique the plan made ready.
:meth:`EpisodicStore.why` walks that chain in **one SQL statement**: why a
record is in the plan, which situations selected it, and why each of those
situations was believed.

Why "ready" has a reason here when it has none in the plan
-----------------------------------------------------------
``Plan`` carries a reason for every "no" -- pending, unavailable, prohibited --
and none for a "yes". The ticket asks why ``A1_execution_based`` was *chosen*,
so the store records the **selection basis**, derived from the plan rather than
by re-running any of it: the planned situations the record triggers on, and the
ready records that named it as a companion. Every entry in every state has at
least one of the two -- that is how the planner put it there -- so an entry with
neither means the plan was not computed from the situations it was recorded
with, and :meth:`~EpisodicStore.record_plan` refuses it.

What cannot be recorded, because the plan does not carry it
-----------------------------------------------------------
* **A record replaced by a conflict.** ``rules.apply_conflicts`` returns
  ``suppressed`` ("replaced by A1_execution_based") and ``unapplied``, and its
  own docstring calls a record vanishing without explanation "the silent skip
  this project refuses everywhere else". ``plan()`` keeps only ``.kept``, so
  ``Plan`` has no field for either, and "why was A4 not chosen?" has no answer
  to persist. Fixture 13's only record of B6 being replaced by B7 is a YAML
  comment. Raised as a ruling; the planner is not M1's to change.
* **The verdict vocabulary.** What a timeout is -- INCONCLUSIVE, or a failure
  logged separately -- is decision EL-014, still open. A verdict is stored as
  the non-empty text the grader gives, unvalidated, so this module does not
  pick a side. When EL-206 settles the enum, a schema migration can constrain it.

Append-only
-----------
Nothing is ever updated or deleted. A decision, once recorded, is history: the
API has no method that rewrites one, and each of the three is recorded at most
once per episode. Even an abstention is its own row rather than a column
filled in later.

Schema versions and the migration path
--------------------------------------
The version lives in the file, in SQLite's ``user_version`` header field.
``_MIGRATIONS[i]`` holds the statements that take a file from version ``i`` to
``i + 1``; version 1 is the first, so creating a store *is* migrating an empty
file. :meth:`~EpisodicStore.open` applies every missing step in one
transaction (a failed step leaves the file at its old version), refuses a file
from a newer EvalLoop, and refuses a version-0 file that already holds tables,
because that file is not an episodic store. A change to the ``Situation`` or
``Tool`` vocabulary is a migration too: reads parse stored terms back into the
enums, so a removed member makes old episodes unreadable until a step rewrites
it -- loudly, rather than as a silently wrong label.

Concurrency: one writer, by design
----------------------------------
A write takes SQLite's write lock with ``BEGIN IMMEDIATE``, and the busy
timeout is **zero**: a second writer, or a commit that collides with a reader,
fails at once with :class:`EpisodicStoreBusy` instead of waiting for an amount
of time this module would have to invent. In M1 the one-shot run driver is the
only writer. M2's orchestrator is meant to stay the only writer too, but a live
dashboard reading during a commit will collide in SQLite's default journal
mode; WAL mode is the usual answer and is M2's call, not this module's. Each
store object belongs to one thread (``check_same_thread``), enforced by
``sqlite3`` itself.

SQLite and ``sqlite3`` behaviour, pinned rather than inherited
--------------------------------------------------------------
The floor is 3.10 and the runtime may be newer, and several defaults have moved
between versions, so every one this module relies on is set or checked:

* ``isolation_level=None`` with explicit ``BEGIN``/``COMMIT``. The legacy
  implicit transactions differ across versions and 3.12 added a separate
  ``autocommit`` switch. ``executescript`` is never used, because it commits
  whatever is open.
* ``detect_types=0`` -- no converters. 3.12 deprecated the default date adapters,
  and nothing here stores a date.
* ``timeout=0.0``, ``check_same_thread=True`` and ``uri=False``, all explicit.
* ``PRAGMA foreign_keys = ON`` on every connection, then read back. SQLite's
  default is off, and a build without foreign-key support is refused.
* ``PRAGMA synchronous = FULL``. The journal mode is checked to be ``delete``
  (``memory`` for an in-memory store), and the encoding to be UTF-8.
* No ``STRICT`` tables and no ``RETURNING``. Python 3.10 builds link SQLite
  versions too old for them, so types are enforced with ``CHECK (typeof(...))``.

Every statement that carries a value takes it as a parameter. The one
exception is ``PRAGMA user_version = n``, which cannot take parameters; its
operand is an integer this module computes, never caller data.

Where the file lives
--------------------
The location is a required argument, with no default. ``USER_EXPERIENCE.md``
§6 has not decided between the repo's ``.evalloop/`` and the user's home, so
this module does not decide it either. Directories are not created.

Determinism
-----------
The store never reads a clock and never generates an id; everything in it is
what the caller passed. Every read has an explicit ``ORDER BY``, so the same
writes give the same reads, and the same logical dump (``iterdump``). The
file's binary layout is SQLite's business and is not promised.
"""

from __future__ import annotations

import math
import os
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from types import TracebackType

from evalloop._compat import StrEnum
from evalloop.plan.planner import Plan
from evalloop.registry.schema import RECORD_ID, TechniqueRecord
from evalloop.vocab import Situation, Tool, parse_situation, parse_tool

__all__ = [
    "SCHEMA_VERSION",
    "Classification",
    "Episode",
    "EpisodicStore",
    "EpisodicStoreBusy",
    "EpisodicStoreError",
    "Label",
    "PlanEntry",
    "PlanSnapshot",
    "PlanState",
    "Trigger",
    "Verdict",
    "Why",
]


class EpisodicStoreError(Exception):
    """A rule of the store was broken -- an unknown episode, a decision recorded
    twice, a plan that does not fit its classification, or a file this version
    cannot read. Malformed arguments raise ``ValueError`` instead."""


class EpisodicStoreBusy(EpisodicStoreError):
    """Another connection holds SQLite's lock. One writer, by design: see the module docstring."""


class PlanState(StrEnum):
    """The four states a plan entry can be in, in ``Plan.render()``'s order."""

    ready = "ready"
    pending = "pending"
    unavailable = "unavailable"
    prohibited = "prohibited"


_STATE_RANK = {state: rank for rank, state in enumerate(PlanState)}


@dataclass(frozen=True, slots=True)
class Label:
    """One classified situation: ``AGENT.md`` §3.4's ``(Situation, confidence)``, with its reason."""

    situation: Situation
    confidence: float
    reasoning: str


@dataclass(frozen=True, slots=True)
class Classification:
    """An episode's classification: its labels, or why there are none."""

    labels: tuple[Label, ...]
    abstention: str | None


@dataclass(frozen=True, slots=True)
class Episode:
    """A unit of work, keyed by the artifacts it covers (``ARCHITECTURE.md`` §9)."""

    episode_id: str
    session_id: str
    artifacts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlanEntry:
    """A record's state in a plan. ``reasoning`` is the planner's reason, or the selection basis for ``ready``."""

    record_id: str
    state: PlanState
    reasoning: str


@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    """A plan as the planner produced it, in an order-preserving, comparable form.

    The mappings of :class:`~evalloop.plan.planner.Plan` become tuples of pairs,
    so two snapshots compare equal only if their order matches too.
    """

    situations: tuple[Situation, ...]
    ready: tuple[str, ...]
    pending: tuple[tuple[str, str], ...]
    unavailable: tuple[tuple[str, tuple[Tool, ...]], ...]
    companions: tuple[tuple[str, tuple[str, ...]], ...]
    prohibited: tuple[tuple[str, str], ...]
    rendered: str

    @classmethod
    def of(cls, plan: Plan, situations: Iterable[Situation]) -> PlanSnapshot:
        """The snapshot of ``plan``, computed from ``situations``, exactly as it is stored."""
        return cls(
            situations=tuple(situations),
            ready=tuple(record.id for record in plan.ready),
            pending=tuple(plan.pending.items()),
            unavailable=tuple((key, tuple(tools)) for key, tools in plan.unavailable.items()),
            companions=tuple((key, tuple(ids)) for key, ids in plan.companions.items()),
            prohibited=tuple((key, plan.prohibition_reasons[key]) for key in plan.prohibited),
            rendered=plan.render(),
        )


@dataclass(frozen=True, slots=True)
class Trigger:
    """A planned situation that selected a record, with the classification's reason for believing it."""

    situation: Situation
    confidence: float
    reasoning: str


@dataclass(frozen=True, slots=True)
class Why:
    """Why a record is in an episode's plan: its entries, what selected it, and who named it.

    ``entries`` is empty when the record is not in the plan. It has two members
    when the record is in two states -- ``D1_pr_curve_never_accuracy`` is both
    ready and prohibited in fixture 12.
    """

    episode_id: str
    record_id: str
    entries: tuple[PlanEntry, ...]
    triggers: tuple[Trigger, ...]
    hosts: tuple[str, ...]

    def render(self) -> str:
        """Plain text for a human. Confidences print as ``repr``, so nothing is re-rounded."""
        if not self.entries:
            return f"{self.record_id}: not in the plan for episode {self.episode_id}"
        lines = [f"{self.record_id}  {entry.state.upper()}  {entry.reasoning}" for entry in self.entries]
        lines.extend(
            f"  {trigger.situation.value} (confidence {trigger.confidence!r}): {trigger.reasoning}"
            for trigger in self.triggers
        )
        lines.extend(f"  companion of {host}" for host in self.hosts)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Verdict:
    """A grader's verdict on one artifact by one ready technique, with its reasoning."""

    artifact: str
    record_id: str
    verdict: str
    reasoning: str


# -- schema ------------------------------------------------------------------

_V1: tuple[str, ...] = (
    """CREATE TABLE session (
        session_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(session_id) = 'text' AND length(session_id) > 0),
        position INTEGER NOT NULL UNIQUE
            CHECK (typeof(position) = 'integer' AND position >= 0)
    )""",
    """CREATE TABLE episode (
        episode_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(episode_id) = 'text' AND length(episode_id) > 0),
        session_id TEXT NOT NULL REFERENCES session (session_id),
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        UNIQUE (session_id, position)
    )""",
    """CREATE TABLE episode_artifact (
        episode_id TEXT NOT NULL REFERENCES episode (episode_id),
        artifact TEXT NOT NULL CHECK (typeof(artifact) = 'text' AND length(artifact) > 0),
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, artifact),
        UNIQUE (episode_id, position)
    )""",
    """CREATE TABLE classification (
        episode_id TEXT NOT NULL REFERENCES episode (episode_id),
        situation TEXT NOT NULL CHECK (typeof(situation) = 'text' AND length(situation) > 0),
        confidence REAL NOT NULL
            CHECK (typeof(confidence) = 'real' AND confidence >= 0.0 AND confidence <= 1.0),
        reasoning TEXT NOT NULL CHECK (typeof(reasoning) = 'text' AND length(reasoning) > 0),
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, situation),
        UNIQUE (episode_id, position)
    )""",
    """CREATE TABLE abstention (
        episode_id TEXT NOT NULL PRIMARY KEY REFERENCES episode (episode_id),
        reasoning TEXT NOT NULL CHECK (typeof(reasoning) = 'text' AND length(reasoning) > 0)
    )""",
    """CREATE TABLE plan (
        episode_id TEXT NOT NULL PRIMARY KEY REFERENCES episode (episode_id),
        rendered TEXT NOT NULL CHECK (typeof(rendered) = 'text')
    )""",
    """CREATE TABLE plan_situation (
        episode_id TEXT NOT NULL REFERENCES plan (episode_id),
        situation TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, situation),
        UNIQUE (episode_id, position),
        FOREIGN KEY (episode_id, situation) REFERENCES classification (episode_id, situation)
    )""",
    """CREATE TABLE plan_entry (
        episode_id TEXT NOT NULL REFERENCES plan (episode_id),
        record_id TEXT NOT NULL CHECK (typeof(record_id) = 'text' AND length(record_id) > 0),
        state TEXT NOT NULL CHECK (state IN ('ready', 'pending', 'unavailable', 'prohibited')),
        reasoning TEXT NOT NULL CHECK (typeof(reasoning) = 'text' AND length(reasoning) > 0),
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, record_id, state),
        UNIQUE (episode_id, state, position)
    )""",
    """CREATE TABLE plan_trigger (
        episode_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        situation TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, record_id, situation),
        FOREIGN KEY (episode_id, situation) REFERENCES plan_situation (episode_id, situation)
    )""",
    """CREATE TABLE plan_missing_tool (
        episode_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'unavailable' CHECK (state = 'unavailable'),
        tool TEXT NOT NULL CHECK (typeof(tool) = 'text' AND length(tool) > 0),
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, record_id, tool),
        UNIQUE (episode_id, record_id, position),
        FOREIGN KEY (episode_id, record_id, state)
            REFERENCES plan_entry (episode_id, record_id, state)
    )""",
    """CREATE TABLE plan_companion (
        episode_id TEXT NOT NULL REFERENCES plan (episode_id),
        host_id TEXT NOT NULL,
        companion_id TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, host_id, companion_id),
        UNIQUE (episode_id, position)
    )""",
    """CREATE INDEX plan_companion_by_companion ON plan_companion (episode_id, companion_id)""",
    # A verdict may only come from a technique the plan made ready: the constant
    # state column lets a foreign key say so.
    """CREATE TABLE verdict (
        episode_id TEXT NOT NULL,
        artifact TEXT NOT NULL,
        record_id TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'ready' CHECK (state = 'ready'),
        verdict TEXT NOT NULL CHECK (typeof(verdict) = 'text' AND length(verdict) > 0),
        reasoning TEXT NOT NULL CHECK (typeof(reasoning) = 'text' AND length(reasoning) > 0),
        position INTEGER NOT NULL CHECK (typeof(position) = 'integer' AND position >= 0),
        PRIMARY KEY (episode_id, artifact, record_id),
        UNIQUE (episode_id, position),
        FOREIGN KEY (episode_id, artifact) REFERENCES episode_artifact (episode_id, artifact),
        FOREIGN KEY (episode_id, record_id, state)
            REFERENCES plan_entry (episode_id, record_id, state)
    )""",
)

#: Step ``i`` takes a file from schema version ``i`` to ``i + 1``.
_MIGRATIONS: tuple[tuple[str, ...], ...] = (_V1,)

#: The schema version this module writes. A file at a higher version is refused.
SCHEMA_VERSION = len(_MIGRATIONS)

#: One statement answers "why": the record's entries, the planned situations
#: that triggered it joined to the classification's reasons for them, the
#: records that named it as a companion, and whether the episode has a plan.
_WHY = """
SELECT 0 AS part, e.state AS name, e.reasoning AS reasoning, NULL AS confidence,
       CASE e.state WHEN 'ready' THEN 0 WHEN 'pending' THEN 1
                    WHEN 'unavailable' THEN 2 ELSE 3 END AS rank,
       e.position AS position
  FROM plan_entry AS e
 WHERE e.episode_id = :episode AND e.record_id = :record
UNION ALL
SELECT 1, t.situation, c.reasoning, c.confidence, t.position, 0
  FROM plan_trigger AS t
  JOIN classification AS c ON c.episode_id = t.episode_id AND c.situation = t.situation
 WHERE t.episode_id = :episode AND t.record_id = :record
UNION ALL
SELECT 2, h.host_id, NULL, NULL, h.position, 0
  FROM plan_companion AS h
 WHERE h.episode_id = :episode AND h.companion_id = :record
UNION ALL
SELECT 3, NULL, NULL, NULL, 0, 0
  FROM plan AS p
 WHERE p.episode_id = :episode
ORDER BY part, rank, position
"""


# -- argument checks -----------------------------------------------------------


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value


def _reasoning(name: str, value: object) -> str:
    """Non-blank, and kept exactly as given -- including the whitespace."""
    text = _text(name, value)
    if not text.strip():
        raise ValueError(f"{name} is blank: a decision without its reasoning is what this store refuses")
    return text


def _record_id(name: str, value: object) -> str:
    """A registry id, matched in full -- ``fullmatch``, so a trailing newline does not slip through."""
    if not isinstance(value, str) or not RECORD_ID.fullmatch(value):
        raise ValueError(f"{name} {value!r} is not a technique record id")
    return value


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"confidence must be a number, got {value!r}")
    if not (math.isfinite(value) and 0.0 <= value <= 1.0):
        raise ValueError(f"confidence must be in [0, 1], got {value!r}")
    return float(value)


def _stored_text(value: object) -> str:
    if not isinstance(value, str):
        raise EpisodicStoreError(f"expected text in the store, found {value!r}")
    return value


def _stored_float(value: object) -> float:
    if not isinstance(value, float):
        raise EpisodicStoreError(f"expected a real number in the store, found {value!r}")
    return value


def _is_busy(error: sqlite3.OperationalError) -> bool:
    return getattr(error, "sqlite_errorname", None) == "SQLITE_BUSY" or str(error).startswith(
        "database is locked"
    )


@contextmanager
def _busy_as_error() -> Iterator[None]:
    try:
        yield
    except sqlite3.OperationalError as error:
        if _is_busy(error):
            raise EpisodicStoreBusy(
                "another connection holds the episodic store's lock; it has one writer, by design"
            ) from error
        raise


@contextmanager
def _writing(connection: sqlite3.Connection) -> Iterator[None]:
    """One write transaction. A failed COMMIT leaves SQLite's transaction open, so roll it back."""
    with _busy_as_error():
        connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        with _busy_as_error():
            connection.execute("COMMIT")
    finally:
        if connection.in_transaction:
            connection.execute("ROLLBACK")


@contextmanager
def _reading(connection: sqlite3.Connection) -> Iterator[None]:
    """One read transaction, so a multi-statement read sees one consistent state."""
    connection.execute("BEGIN")
    try:
        with _busy_as_error():
            yield
    finally:
        connection.execute("COMMIT")


def _configure(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
        raise EpisodicStoreError("this SQLite build does not enforce foreign keys, and the store relies on them")
    connection.execute("PRAGMA synchronous = FULL")
    (encoding,) = connection.execute("PRAGMA encoding").fetchone()
    if encoding != "UTF-8":
        raise EpisodicStoreError(f"the store is UTF-8; this file is {encoding}")
    (mode,) = connection.execute("PRAGMA journal_mode").fetchone()
    if mode not in ("delete", "memory"):
        raise EpisodicStoreError(f"journal mode {mode!r} is not one this store was written for")


def _version(connection: sqlite3.Connection) -> int:
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    if not isinstance(version, int):
        raise EpisodicStoreError(f"unreadable schema version {version!r}")
    return version


def _migrate(connection: sqlite3.Connection) -> None:
    target = len(_MIGRATIONS)
    with _busy_as_error():
        current = _version(connection)
    if current > target:
        raise EpisodicStoreError(
            f"this store is at schema version {current}, written by a newer EvalLoop; "
            f"this one reads up to version {target}"
        )
    if current == target:
        return
    with _writing(connection):
        current = _version(connection)  # re-read under the lock
        if current == 0:
            (objects,) = connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            if objects:
                raise EpisodicStoreError(
                    f"not an episodic store: schema version 0 with {objects} existing schema objects"
                )
        for step in range(current, target):
            for statement in _MIGRATIONS[step]:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {int(step + 1)}")


# -- deriving the plan's rows --------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Row:
    record_id: str
    state: PlanState
    reasoning: str
    position: int
    triggers: tuple[Situation, ...]
    missing: tuple[Tool, ...]


def _selection_basis(triggers: Sequence[Situation], hosts: Sequence[str]) -> str:
    parts = []
    if triggers:
        parts.append("triggered by " + ", ".join(situation.value for situation in triggers))
    if hosts:
        parts.append("companion of " + ", ".join(hosts))
    return "; ".join(parts)


def _plan_rows(
    plan: Plan, planned: tuple[Situation, ...], records: dict[str, TechniqueRecord]
) -> list[_Row]:
    hosts_of: dict[str, list[str]] = {}
    for host, companions in plan.companions.items():
        for companion in companions:
            hosts_of.setdefault(companion, []).append(host)

    rows: list[_Row] = []

    def add(
        record_id: str,
        state: PlanState,
        reason: str | None,
        position: int,
        missing: tuple[Tool, ...] = (),
    ) -> None:
        record = records.get(record_id)
        if record is None:
            raise EpisodicStoreError(
                f"{record_id} is in the plan but not in the records it was recorded with"
            )
        triggers = tuple(s for s in planned if s in record.triggers_on_situation)
        hosts = tuple(hosts_of.get(record_id, ()))
        if not triggers and not hosts:
            planned_text = ", ".join(s.value for s in planned) or "none"
            raise EpisodicStoreError(
                f"{record_id} is {state.value}, but no planned situation ({planned_text}) "
                "triggers it and no record names it as a companion: the plan was not "
                "computed from these situations"
            )
        reasoning = reason if reason is not None else _selection_basis(triggers, hosts)
        rows.append(_Row(record_id, state, reasoning, position, triggers, missing))

    for position, record in enumerate(plan.ready):
        add(record.id, PlanState.ready, None, position)
    for position, (record_id, reason) in enumerate(plan.pending.items()):
        add(record_id, PlanState.pending, reason, position)
    for position, (record_id, tools) in enumerate(plan.unavailable.items()):
        tools = tuple(tools)
        reason = "missing: " + ", ".join(tool.value for tool in tools)
        add(record_id, PlanState.unavailable, reason, position, tools)
    for position, record_id in enumerate(plan.prohibited):
        add(record_id, PlanState.prohibited, plan.prohibition_reasons[record_id], position)
    return rows


# -- the store -------------------------------------------------------------------


class EpisodicStore:
    """Sessions, episodes, and each episode's three decisions with their reasoning.

    Open with :meth:`open` and close with :meth:`close`, or use the store as a
    context manager. Every write method is one transaction.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Use :meth:`open`, which configures and migrates the connection first."""
        self._connection = connection

    @classmethod
    def open(cls, location: str | os.PathLike[str]) -> EpisodicStore:
        """Open, or create, the store at ``location``. There is no default location.

        ``":memory:"`` gives a store that lives only as long as the object.
        The parent directory must already exist.
        """
        connection = sqlite3.connect(
            os.fspath(location),
            timeout=0.0,
            detect_types=0,
            isolation_level=None,
            check_same_thread=True,
            uri=False,
        )
        try:
            _configure(connection)
            _migrate(connection)
        except BaseException:
            connection.close()
            raise
        return cls(connection)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> EpisodicStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # -- checks shared by the writes -------------------------------------------

    def _episode_exists(self, episode_id: str) -> None:
        found = self._connection.execute(
            "SELECT 1 FROM episode WHERE episode_id = ?", (episode_id,)
        ).fetchone()
        if found is None:
            raise EpisodicStoreError(f"no episode {episode_id!r}")

    def _classified(self, episode_id: str) -> bool:
        (count,) = self._connection.execute(
            "SELECT (SELECT count(*) FROM classification WHERE episode_id = :e)"
            " + (SELECT count(*) FROM abstention WHERE episode_id = :e)",
            {"e": episode_id},
        ).fetchone()
        return bool(count)

    def _planned(self, episode_id: str) -> bool:
        found = self._connection.execute(
            "SELECT 1 FROM plan WHERE episode_id = ?", (episode_id,)
        ).fetchone()
        return found is not None

    # -- writes ------------------------------------------------------------------

    def open_session(self, session_id: str) -> None:
        """Start a session. Sessions are kept in the order they were opened."""
        session_id = _text("session_id", session_id)
        with _writing(self._connection):
            if self._connection.execute(
                "SELECT 1 FROM session WHERE session_id = ?", (session_id,)
            ).fetchone():
                raise EpisodicStoreError(f"session {session_id!r} already exists")
            (position,) = self._connection.execute("SELECT count(*) FROM session").fetchone()
            self._connection.execute(
                "INSERT INTO session (session_id, position) VALUES (?, ?)", (session_id, position)
            )

    def open_episode(self, episode_id: str, *, session_id: str, artifacts: Sequence[str]) -> None:
        """Start an episode in a session, covering one or more distinct artifacts."""
        episode_id = _text("episode_id", episode_id)
        session_id = _text("session_id", session_id)
        if isinstance(artifacts, str):
            raise ValueError("artifacts must be a sequence of strings, not one string")
        names = tuple(_text("artifact", artifact) for artifact in artifacts)
        if not names:
            raise ValueError("an episode covers at least one artifact")
        if len(set(names)) != len(names):
            raise ValueError(f"artifacts repeat: {names!r}")
        with _writing(self._connection):
            if self._connection.execute(
                "SELECT 1 FROM session WHERE session_id = ?", (session_id,)
            ).fetchone() is None:
                raise EpisodicStoreError(f"no session {session_id!r}")
            if self._connection.execute(
                "SELECT 1 FROM episode WHERE episode_id = ?", (episode_id,)
            ).fetchone():
                raise EpisodicStoreError(f"episode {episode_id!r} already exists")
            (position,) = self._connection.execute(
                "SELECT count(*) FROM episode WHERE session_id = ?", (session_id,)
            ).fetchone()
            self._connection.execute(
                "INSERT INTO episode (episode_id, session_id, position) VALUES (?, ?, ?)",
                (episode_id, session_id, position),
            )
            self._connection.executemany(
                "INSERT INTO episode_artifact (episode_id, artifact, position) VALUES (?, ?, ?)",
                [(episode_id, name, index) for index, name in enumerate(names)],
            )

    def record_classification(
        self,
        episode_id: str,
        labels: Sequence[Label],
        *,
        abstention: str | None = None,
    ) -> None:
        """Record what the episode was classified as, or why it could not be.

        Labels are multi-label, one row each, kept in the given order. With no
        labels, ``abstention`` must say why; with labels, it must be ``None``.
        """
        episode_id = _text("episode_id", episode_id)
        given = tuple(labels)
        for label in given:
            if not isinstance(label.situation, Situation):
                raise ValueError(f"{label.situation!r} is not a Situation")
        checked = [
            (label.situation.value, _confidence(label.confidence), _reasoning("label reasoning", label.reasoning))
            for label in given
        ]
        situations = [situation for situation, _, _ in checked]
        if len(set(situations)) != len(situations):
            raise ValueError(f"situations repeat: {situations!r}")
        if given and abstention is not None:
            raise ValueError("an episode with labels did not abstain")
        if not given:
            if abstention is None:
                raise ValueError("no labels and no abstention: say why nothing could be classified")
            abstention = _reasoning("abstention", abstention)
        with _writing(self._connection):
            self._episode_exists(episode_id)
            if self._classified(episode_id):
                raise EpisodicStoreError(f"episode {episode_id!r} is already classified")
            if abstention is not None:
                self._connection.execute(
                    "INSERT INTO abstention (episode_id, reasoning) VALUES (?, ?)",
                    (episode_id, abstention),
                )
            self._connection.executemany(
                "INSERT INTO classification (episode_id, situation, confidence, reasoning, position)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (episode_id, situation, confidence, reasoning, index)
                    for index, (situation, confidence, reasoning) in enumerate(checked)
                ],
            )

    def record_plan(
        self,
        episode_id: str,
        plan: Plan,
        *,
        situations: Iterable[Situation],
        records: Iterable[TechniqueRecord],
    ) -> None:
        """Record the plan, computed from ``situations`` over ``records``, as the planner produced it.

        ``situations`` must be the exact situations passed to ``plan()``, and
        each must be one this episode's classification recorded. ``records``
        must hold every record the plan names (normally the whole registry).
        """
        episode_id = _text("episode_id", episode_id)
        planned = tuple(situations)
        for situation in planned:
            if not isinstance(situation, Situation):
                raise ValueError(f"{situation!r} is not a Situation")
        if len(set(planned)) != len(planned):
            raise ValueError(f"planned situations repeat: {[s.value for s in planned]!r}")
        known = {record.id: record for record in records}
        for record in plan.ready:
            known.setdefault(record.id, record)
        rows = _plan_rows(plan, planned, known)
        edges = [
            (_record_id("companion host", host), _record_id("companion", companion))
            for host, companions in plan.companions.items()
            for companion in companions
        ]
        for row in rows:
            _record_id("plan entry", row.record_id)
        triggers: dict[str, tuple[Situation, ...]] = {}
        for row in rows:
            triggers.setdefault(row.record_id, row.triggers)
        position_of = {situation: index for index, situation in enumerate(planned)}

        with _writing(self._connection):
            self._episode_exists(episode_id)
            if not self._classified(episode_id):
                raise EpisodicStoreError(f"episode {episode_id!r} has no classification to plan from")
            if self._planned(episode_id):
                raise EpisodicStoreError(f"episode {episode_id!r} already has a plan")
            labelled = {
                row[0]
                for row in self._connection.execute(
                    "SELECT situation FROM classification WHERE episode_id = ?", (episode_id,)
                )
            }
            unlabelled = [s.value for s in planned if s.value not in labelled]
            if unlabelled:
                raise EpisodicStoreError(
                    f"the plan uses {unlabelled!r}, which episode {episode_id!r} was not classified as"
                )
            self._connection.execute(
                "INSERT INTO plan (episode_id, rendered) VALUES (?, ?)", (episode_id, plan.render())
            )
            self._connection.executemany(
                "INSERT INTO plan_situation (episode_id, situation, position) VALUES (?, ?, ?)",
                [(episode_id, situation.value, index) for index, situation in enumerate(planned)],
            )
            self._connection.executemany(
                "INSERT INTO plan_entry (episode_id, record_id, state, reasoning, position)"
                " VALUES (?, ?, ?, ?, ?)",
                [(episode_id, r.record_id, r.state.value, r.reasoning, r.position) for r in rows],
            )
            self._connection.executemany(
                "INSERT INTO plan_trigger (episode_id, record_id, situation, position) VALUES (?, ?, ?, ?)",
                [
                    (episode_id, record_id, situation.value, position_of[situation])
                    for record_id, selected in triggers.items()
                    for situation in selected
                ],
            )
            self._connection.executemany(
                "INSERT INTO plan_missing_tool (episode_id, record_id, tool, position) VALUES (?, ?, ?, ?)",
                [
                    (episode_id, r.record_id, tool.value, index)
                    for r in rows
                    for index, tool in enumerate(r.missing)
                ],
            )
            self._connection.executemany(
                "INSERT INTO plan_companion (episode_id, host_id, companion_id, position) VALUES (?, ?, ?, ?)",
                [(episode_id, host, companion, index) for index, (host, companion) in enumerate(edges)],
            )

    def record_verdict(
        self, episode_id: str, *, artifact: str, record_id: str, verdict: str, reasoning: str
    ) -> None:
        """Record a grader's verdict on one of the episode's artifacts by a technique the plan made ready.

        ``verdict`` is stored as given: its vocabulary is EL-014's decision.
        """
        episode_id = _text("episode_id", episode_id)
        artifact = _text("artifact", artifact)
        record_id = _record_id("record_id", record_id)
        verdict = _text("verdict", verdict)
        reasoning = _reasoning("verdict reasoning", reasoning)
        with _writing(self._connection):
            self._episode_exists(episode_id)
            if not self._planned(episode_id):
                raise EpisodicStoreError(f"episode {episode_id!r} has no plan, so nothing was ready to grade")
            if self._connection.execute(
                "SELECT 1 FROM episode_artifact WHERE episode_id = ? AND artifact = ?",
                (episode_id, artifact),
            ).fetchone() is None:
                raise EpisodicStoreError(f"{artifact!r} is not an artifact of episode {episode_id!r}")
            if self._connection.execute(
                "SELECT 1 FROM plan_entry WHERE episode_id = ? AND record_id = ? AND state = 'ready'",
                (episode_id, record_id),
            ).fetchone() is None:
                raise EpisodicStoreError(
                    f"{record_id} is not ready in episode {episode_id!r}'s plan, so it cannot have graded anything"
                )
            if self._connection.execute(
                "SELECT 1 FROM verdict WHERE episode_id = ? AND artifact = ? AND record_id = ?",
                (episode_id, artifact, record_id),
            ).fetchone():
                raise EpisodicStoreError(f"{record_id} already has a verdict on {artifact!r}")
            (position,) = self._connection.execute(
                "SELECT count(*) FROM verdict WHERE episode_id = ?", (episode_id,)
            ).fetchone()
            self._connection.execute(
                "INSERT INTO verdict (episode_id, artifact, record_id, verdict, reasoning, position)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (episode_id, artifact, record_id, verdict, reasoning, position),
            )

    # -- reads, for a human asking later ------------------------------------------

    def sessions(self) -> tuple[str, ...]:
        with _busy_as_error():
            rows = self._connection.execute("SELECT session_id FROM session ORDER BY position").fetchall()
        return tuple(_stored_text(session_id) for (session_id,) in rows)

    def episodes(self, session_id: str) -> tuple[Episode, ...]:
        session_id = _text("session_id", session_id)
        with _busy_as_error():
            rows = self._connection.execute(
                "SELECT e.episode_id, a.artifact FROM episode AS e"
                " JOIN episode_artifact AS a ON a.episode_id = e.episode_id"
                " WHERE e.session_id = ? ORDER BY e.position, a.position",
                (session_id,),
            ).fetchall()
        grouped: dict[str, list[str]] = {}
        for episode_id, artifact in rows:
            grouped.setdefault(_stored_text(episode_id), []).append(_stored_text(artifact))
        return tuple(Episode(key, session_id, tuple(names)) for key, names in grouped.items())

    def classification(self, episode_id: str) -> Classification:
        episode_id = _text("episode_id", episode_id)
        with _reading(self._connection):
            self._episode_exists(episode_id)
            rows = self._connection.execute(
                "SELECT situation, confidence, reasoning FROM classification"
                " WHERE episode_id = ? ORDER BY position",
                (episode_id,),
            ).fetchall()
            abstained = self._connection.execute(
                "SELECT reasoning FROM abstention WHERE episode_id = ?", (episode_id,)
            ).fetchone()
        labels = tuple(
            Label(parse_situation(_stored_text(s)), _stored_float(c), _stored_text(r)) for s, c, r in rows
        )
        return Classification(labels, None if abstained is None else _stored_text(abstained[0]))

    def plan_snapshot(self, episode_id: str) -> PlanSnapshot:
        """The plan as recorded, in the same form :meth:`PlanSnapshot.of` gives a live ``Plan``."""
        episode_id = _text("episode_id", episode_id)
        with _reading(self._connection):
            found = self._connection.execute(
                "SELECT rendered FROM plan WHERE episode_id = ?", (episode_id,)
            ).fetchone()
            if found is None:
                raise EpisodicStoreError(f"episode {episode_id!r} has no recorded plan")
            situations = self._connection.execute(
                "SELECT situation FROM plan_situation WHERE episode_id = ? ORDER BY position", (episode_id,)
            ).fetchall()
            entries = self._connection.execute(
                "SELECT record_id, state, reasoning FROM plan_entry WHERE episode_id = ?"
                " ORDER BY CASE state WHEN 'ready' THEN 0 WHEN 'pending' THEN 1"
                " WHEN 'unavailable' THEN 2 ELSE 3 END, position",
                (episode_id,),
            ).fetchall()
            missing = self._connection.execute(
                "SELECT record_id, tool FROM plan_missing_tool WHERE episode_id = ? ORDER BY record_id, position",
                (episode_id,),
            ).fetchall()
            edges = self._connection.execute(
                "SELECT host_id, companion_id FROM plan_companion WHERE episode_id = ? ORDER BY position",
                (episode_id,),
            ).fetchall()
        tools: dict[str, list[Tool]] = {}
        for record_id, tool in missing:
            tools.setdefault(_stored_text(record_id), []).append(parse_tool(_stored_text(tool)))
        companions: dict[str, list[str]] = {}
        for host, companion in edges:
            companions.setdefault(_stored_text(host), []).append(_stored_text(companion))
        by_state: dict[PlanState, list[tuple[str, str]]] = {state: [] for state in PlanState}
        for record_id, state, reasoning in entries:
            by_state[PlanState(_stored_text(state))].append((_stored_text(record_id), _stored_text(reasoning)))
        return PlanSnapshot(
            situations=tuple(parse_situation(_stored_text(s)) for (s,) in situations),
            ready=tuple(record_id for record_id, _ in by_state[PlanState.ready]),
            pending=tuple(by_state[PlanState.pending]),
            unavailable=tuple(
                (record_id, tuple(tools.get(record_id, ()))) for record_id, _ in by_state[PlanState.unavailable]
            ),
            companions=tuple((host, tuple(ids)) for host, ids in companions.items()),
            prohibited=tuple(by_state[PlanState.prohibited]),
            rendered=_stored_text(found[0]),
        )

    def why(self, episode_id: str, record_id: str) -> Why:
        """Why ``record_id`` is in ``episode_id``'s plan -- one call, one SQL statement.

        The entries say what state it is in and the reason; the triggers say
        which classified situations selected it and why each was believed; the
        hosts say which ready records named it as a companion.
        """
        episode_id = _text("episode_id", episode_id)
        record_id = _record_id("record_id", record_id)
        with _busy_as_error():
            rows = self._connection.execute(_WHY, {"episode": episode_id, "record": record_id}).fetchall()
        entries: list[PlanEntry] = []
        triggers: list[Trigger] = []
        hosts: list[str] = []
        planned = False
        for part, name, reasoning, confidence, _rank, _position in rows:
            if part == 0:
                entries.append(
                    PlanEntry(record_id, PlanState(_stored_text(name)), _stored_text(reasoning))
                )
            elif part == 1:
                triggers.append(
                    Trigger(
                        parse_situation(_stored_text(name)),
                        _stored_float(confidence),
                        _stored_text(reasoning),
                    )
                )
            elif part == 2:
                hosts.append(_stored_text(name))
            else:
                planned = True
        if not planned:
            raise EpisodicStoreError(f"episode {episode_id!r} has no recorded plan")
        return Why(episode_id, record_id, tuple(entries), tuple(triggers), tuple(hosts))

    def rendered_plan(self, episode_id: str) -> str:
        """The plan exactly as ``Plan.render()`` printed it when it was recorded."""
        return self.plan_snapshot(episode_id).rendered

    def verdicts(self, episode_id: str) -> tuple[Verdict, ...]:
        episode_id = _text("episode_id", episode_id)
        with _busy_as_error():
            rows = self._connection.execute(
                "SELECT artifact, record_id, verdict, reasoning FROM verdict"
                " WHERE episode_id = ? ORDER BY position",
                (episode_id,),
            ).fetchall()
        return tuple(
            Verdict(_stored_text(a), _stored_text(r), _stored_text(v), _stored_text(why))
            for a, r, v, why in rows
        )
