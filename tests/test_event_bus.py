"""Tests for the event buffer and debouncer (T19)."""

from __future__ import annotations

from evalloop.session.event_bus import (
    ChangeUnit,
    Debouncer,
    Event,
    EventBuffer,
    EventKind,
)


def _file_event(path: str, ts: float) -> Event:
    return Event(kind=EventKind.file_changed, ts=ts, payload={"path": path}, provenance="test")


def _intent_event(intent: str, ts: float) -> Event:
    return Event(kind=EventKind.transcript_intent, ts=ts, payload={"intent": intent}, provenance="test")


class TestEvent:
    def test_event_construction(self) -> None:
        e = Event(kind=EventKind.file_changed, ts=1.0, payload={"path": "a.py"}, provenance="poller")
        assert e.kind == EventKind.file_changed
        assert e.ts == 1.0
        assert e.confidence == 1.0

    def test_confidence_validation(self) -> None:
        try:
            Event(kind=EventKind.file_changed, ts=1.0, payload={}, provenance="x", confidence=1.5)
            assert False, "should have raised"
        except ValueError:
            pass

    def test_event_kind_values(self) -> None:
        assert EventKind.file_changed == "file_changed"
        assert EventKind.git_commit == "git_commit"
        assert EventKind.transcript_intent == "transcript_intent"


class TestEventBuffer:
    def test_push_and_drain(self) -> None:
        buf = EventBuffer()
        assert buf.empty
        e1 = _file_event("a.py", 1.0)
        e2 = _file_event("b.py", 2.0)
        buf.push(e1)
        buf.push(e2)
        assert len(buf) == 2
        assert not buf.empty
        events = buf.drain()
        assert events == (e1, e2)
        assert buf.empty

    def test_deduplicate_same_path(self) -> None:
        buf = EventBuffer()
        buf.push(_file_event("a.py", 1.0))
        buf.push(_file_event("a.py", 2.0))
        events = buf.drain()
        assert len(events) == 1
        assert events[0].ts == 2.0  # the later event replaces the earlier

    def test_different_paths_not_deduped(self) -> None:
        buf = EventBuffer()
        buf.push(_file_event("a.py", 1.0))
        buf.push(_file_event("b.py", 2.0))
        assert len(buf) == 2

    def test_non_file_events_accumulate(self) -> None:
        buf = EventBuffer()
        buf.push(Event(kind=EventKind.git_commit, ts=1.0, payload={}, provenance="git"))
        buf.push(Event(kind=EventKind.git_commit, ts=2.0, payload={}, provenance="git"))
        assert len(buf) == 2

    def test_last_ts(self) -> None:
        buf = EventBuffer()
        assert buf.last_ts is None
        buf.push(_file_event("a.py", 5.0))
        assert buf.last_ts == 5.0
        buf.push(_file_event("b.py", 3.0))
        assert buf.last_ts == 3.0  # last pushed, not highest


class TestDebouncer:
    def test_empty_poll_returns_none(self) -> None:
        d = Debouncer(quiet_seconds=1.0)
        assert d.poll() is None

    def test_bursts_collapse_into_one_unit(self) -> None:
        """T19 done-when: bursts collapse into single change units."""
        clock = [0.0]
        d = Debouncer(quiet_seconds=1.0, clock=lambda: clock[0])
        # Rapid burst of three events within the quiet window.
        d.push(_file_event("a.py", 0.1))
        d.push(_file_event("b.py", 0.2))
        d.push(_file_event("c.py", 0.3))
        clock[0] = 0.5
        assert d.poll() is None  # still within quiet window
        clock[0] = 1.4  # 1.1s after last event (0.3), past the 1.0s quiet window
        unit = d.poll()
        assert unit is not None
        assert isinstance(unit, ChangeUnit)
        assert len(unit.events) == 3
        assert unit.files_touched == frozenset({"a.py", "b.py", "c.py"})
        assert unit.intent is None

    def test_quiet_window_resets_on_new_event(self) -> None:
        clock = [0.0]
        d = Debouncer(quiet_seconds=2.0, clock=lambda: clock[0])
        d.push(_file_event("a.py", 1.0))
        clock[0] = 2.5  # 1.5s since last event, not past 2.0
        assert d.poll() is None
        d.push(_file_event("b.py", 2.5))  # resets the window
        clock[0] = 4.0  # 1.5s since 2.5
        assert d.poll() is None
        clock[0] = 5.0  # 2.5s since 2.5 -> past quiet window
        unit = d.poll()
        assert unit is not None
        assert len(unit.events) == 2

    def test_intent_is_captured(self) -> None:
        clock = [0.0]
        d = Debouncer(quiet_seconds=0.5, clock=lambda: clock[0])
        d.push(_file_event("a.py", 0.1))
        d.push(_intent_event("fix the login bug", 0.2))
        clock[0] = 1.0
        unit = d.poll()
        assert unit is not None
        assert unit.intent == "fix the login bug"

    def test_latest_intent_wins(self) -> None:
        clock = [0.0]
        d = Debouncer(quiet_seconds=0.5, clock=lambda: clock[0])
        d.push(_intent_event("first task", 0.1))
        d.push(_intent_event("actually, do this instead", 0.2))
        clock[0] = 1.0
        unit = d.poll()
        assert unit is not None
        assert unit.intent == "actually, do this instead"

    def test_flush_forces_close(self) -> None:
        d = Debouncer(quiet_seconds=100.0)
        d.push(_file_event("a.py", 1.0))
        assert d.pending == 1
        unit = d.flush()
        assert unit is not None
        assert len(unit.events) == 1
        assert d.pending == 0

    def test_flush_empty_returns_none(self) -> None:
        d = Debouncer(quiet_seconds=1.0)
        assert d.flush() is None

    def test_change_unit_duration(self) -> None:
        clock = [0.0]
        d = Debouncer(quiet_seconds=0.1, clock=lambda: clock[0])
        d.push(_file_event("a.py", 1.0))
        d.push(_file_event("b.py", 3.0))
        clock[0] = 4.0
        unit = d.poll()
        assert unit is not None
        assert unit.opened_at == 1.0
        assert unit.closed_at == 3.0
        assert unit.duration == 2.0

    def test_deduplication_in_debouncer(self) -> None:
        """Same file saved multiple times in a burst -> one event in the unit."""
        clock = [0.0]
        d = Debouncer(quiet_seconds=1.0, clock=lambda: clock[0])
        d.push(_file_event("a.py", 0.1))
        d.push(_file_event("a.py", 0.2))
        d.push(_file_event("a.py", 0.3))
        clock[0] = 2.0
        unit = d.poll()
        assert unit is not None
        assert len(unit.events) == 1  # deduped to one event
        assert unit.files_touched == frozenset({"a.py"})

    def test_invalid_quiet_seconds(self) -> None:
        try:
            Debouncer(quiet_seconds=0.0)
            assert False, "should have raised"
        except ValueError:
            pass
