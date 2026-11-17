"""Event buffer and debouncer for the Intent Bus (T19, ARCHITECTURE.md §3).

Events from every sensor -- filesystem, git, transcript -- flow into a single
in-process queue.  The debouncer collapses bursts of events (a flurry of file
saves while the developer types) into a single *change unit* by waiting for a
quiet window: when no new event arrives within ``quiet_seconds``, the buffered
events close as one unit.

Nothing here is persisted.  The episodic store (T8) owns history; this is the
in-flight queue only.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from evalloop._compat import StrEnum

__all__ = [
    "EventKind",
    "Event",
    "ChangeUnit",
    "EventBuffer",
    "Debouncer",
]


class EventKind(StrEnum):
    """The kind of observation a sensor produced."""

    file_changed = "file_changed"
    file_created = "file_created"
    file_deleted = "file_deleted"
    git_commit = "git_commit"
    git_branch = "git_branch"
    git_stage = "git_stage"
    transcript_message = "transcript_message"
    transcript_intent = "transcript_intent"
    command_run = "command_run"


@dataclass(frozen=True, slots=True)
class Event:
    """One observation from any sensor, normalised onto a common shape.

    ``payload`` is kind-specific: a ``file_changed`` carries ``{"path": "..."}``; a
    ``transcript_intent`` carries ``{"intent": "..."}``.  Keys are free-form strings so
    sensors can evolve without a schema change here.
    """

    kind: EventKind
    ts: float
    payload: Mapping[str, object]
    provenance: str  # which sensor produced this, e.g. "poller", "git", "transcript"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


_FILE_KINDS = frozenset({EventKind.file_changed, EventKind.file_created, EventKind.file_deleted})


@dataclass(frozen=True, slots=True)
class ChangeUnit:
    """A burst of events collapsed into one evaluable unit by the debouncer."""

    events: tuple[Event, ...]
    opened_at: float
    closed_at: float
    files_touched: frozenset[str]
    intent: str | None  # from transcript, if any

    @property
    def duration(self) -> float:
        return self.closed_at - self.opened_at


class EventBuffer:
    """Thread-safe, append-only event queue with deduplication.

    Deduplication: a ``file_changed`` event for a path that already has a
    ``file_changed`` in the current buffer is replaced (the latest timestamp and
    payload win).  Other kinds accumulate.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._file_index: dict[str, int] = {}  # path -> index in _events
        self._lock = threading.Lock()

    def push(self, event: Event) -> None:
        with self._lock:
            if event.kind in _FILE_KINDS:
                path = str(event.payload.get("path", ""))
                if path and path in self._file_index:
                    # Replace the earlier event for this path (dedupe).
                    self._events[self._file_index[path]] = event
                    return
                if path:
                    self._file_index[path] = len(self._events)
            self._events.append(event)

    def drain(self) -> tuple[Event, ...]:
        """Return and clear all buffered events, in arrival order."""
        with self._lock:
            events = tuple(self._events)
            self._events.clear()
            self._file_index.clear()
        return events

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    @property
    def empty(self) -> bool:
        with self._lock:
            return len(self._events) == 0

    @property
    def last_ts(self) -> float | None:
        """Timestamp of the most recent event, or None if the buffer is empty."""
        with self._lock:
            return self._events[-1].ts if self._events else None


class Debouncer:
    """Collapse a stream of events into change units using a quiet window.

    Call :meth:`push` for every event.  Call :meth:`poll` on a timer; it returns
    a :class:`ChangeUnit` when the quiet window has elapsed, or ``None`` if events
    are still arriving.

    The quiet window resets on every push: a burst of ten saves in one second
    becomes one unit closed ``quiet_seconds`` after the last save.
    """

    def __init__(
        self,
        quiet_seconds: float = 2.0,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if quiet_seconds <= 0:
            raise ValueError(f"quiet_seconds must be positive, got {quiet_seconds}")
        self._quiet = quiet_seconds
        self._clock = clock
        self._buffer = EventBuffer()
        self._opened_at: float | None = None

    @property
    def quiet_seconds(self) -> float:
        return self._quiet

    @property
    def pending(self) -> int:
        """Number of events waiting in the buffer."""
        return len(self._buffer)

    def push(self, event: Event) -> None:
        """Add an event.  The quiet window restarts from this event's timestamp."""
        if self._opened_at is None:
            self._opened_at = event.ts
        self._buffer.push(event)

    def poll(self) -> ChangeUnit | None:
        """Check whether the quiet window has elapsed.  Returns a unit or None."""
        last = self._buffer.last_ts
        if last is None:
            return None
        if self._clock() - last < self._quiet:
            return None
        return self.flush()

    def flush(self) -> ChangeUnit | None:
        """Force-close the current buffer into a change unit, even if the quiet window has not elapsed."""
        events = self._buffer.drain()
        if not events:
            return None
        files = frozenset(
            str(e.payload.get("path", ""))
            for e in events
            if e.kind in _FILE_KINDS and e.payload.get("path")
        )
        intents = [
            str(e.payload.get("intent", ""))
            for e in events
            if e.kind == EventKind.transcript_intent and e.payload.get("intent")
        ]
        unit = ChangeUnit(
            events=events,
            opened_at=self._opened_at or events[0].ts,
            closed_at=events[-1].ts,
            files_touched=files,
            intent=intents[-1] if intents else None,
        )
        self._opened_at = None
        return unit
