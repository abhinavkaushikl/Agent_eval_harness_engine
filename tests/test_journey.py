"""Tests for the journey ledger and trend tracking (T31)."""

from __future__ import annotations

from evalloop.memory.journey import (
    JourneyLedger,
    Trend,
    TrendResult,
)


class TestJourneyLedger:
    def test_record_and_retrieve(self) -> None:
        ledger = JourneyLedger()
        ledger.record("pass_rate", "", run_id="run-1", value=0.72, ts=1000.0)
        entries = ledger.entries("pass_rate", "")
        assert len(entries) == 1
        assert entries[0].run_id == "run-1"
        assert entries[0].value == 0.72

    def test_metrics_and_slices(self) -> None:
        ledger = JourneyLedger()
        ledger.record("pass_rate", "", run_id="r1", value=0.7, ts=1.0)
        ledger.record("pass_rate", "api", run_id="r1", value=0.8, ts=1.0)
        ledger.record("latency", "", run_id="r1", value=100.0, ts=1.0)
        assert ledger.metrics() == frozenset({"pass_rate", "latency"})
        assert ledger.slices("pass_rate") == frozenset({"", "api"})


class TestTrend:
    def test_insufficient_data(self) -> None:
        ledger = JourneyLedger()
        ledger.record("x", "", run_id="r1", value=1.0, ts=1.0)
        ledger.record("x", "", run_id="r2", value=2.0, ts=2.0)
        result = ledger.trend("x", "")
        assert result.trend == Trend.insufficient
        assert result.n == 2

    def test_trending_up(self) -> None:
        """T31: per-field trend lines over runs — detects upward trend."""
        ledger = JourneyLedger()
        ledger.record("score", "", run_id="r1", value=0.60, ts=1.0)
        ledger.record("score", "", run_id="r2", value=0.65, ts=2.0)
        ledger.record("score", "", run_id="r3", value=0.70, ts=3.0)
        ledger.record("score", "", run_id="r4", value=0.95, ts=4.0)
        result = ledger.trend("score", "")
        assert result.trend == Trend.up

    def test_trending_down(self) -> None:
        ledger = JourneyLedger()
        ledger.record("score", "", run_id="r1", value=0.90, ts=1.0)
        ledger.record("score", "", run_id="r2", value=0.85, ts=2.0)
        ledger.record("score", "", run_id="r3", value=0.80, ts=3.0)
        ledger.record("score", "", run_id="r4", value=0.40, ts=4.0)
        result = ledger.trend("score", "")
        assert result.trend == Trend.down

    def test_flat_trend(self) -> None:
        ledger = JourneyLedger()
        for i in range(5):
            ledger.record("score", "", run_id=f"r{i}", value=0.75, ts=float(i))
        result = ledger.trend("score", "")
        assert result.trend == Trend.flat
        assert "identical" in result.reason

    def test_per_slice_trends(self) -> None:
        """T31: per-slice trend lines."""
        ledger = JourneyLedger()
        for i, v in enumerate([0.5, 0.6, 0.7, 0.9]):
            ledger.record("pass_rate", "api_slice", run_id=f"r{i}", value=v, ts=float(i))
        for i, v in enumerate([0.9, 0.8, 0.7, 0.3]):
            ledger.record("pass_rate", "db_slice", run_id=f"r{i}", value=v, ts=float(i))
        api_trend = ledger.trend("pass_rate", "api_slice")
        db_trend = ledger.trend("pass_rate", "db_slice")
        assert api_trend.trend == Trend.up
        assert db_trend.trend == Trend.down

    def test_all_trends(self) -> None:
        ledger = JourneyLedger()
        for i in range(4):
            ledger.record("a", "", run_id=f"r{i}", value=float(i), ts=float(i))
            ledger.record("b", "", run_id=f"r{i}", value=10.0 - float(i), ts=float(i))
        all_t = ledger.all_trends()
        assert len(all_t) == 2
        assert all_t[("a", "")].trend == Trend.up
        assert all_t[("b", "")].trend == Trend.down

    def test_no_entries(self) -> None:
        ledger = JourneyLedger()
        result = ledger.trend("nonexistent", "")
        assert result.trend == Trend.insufficient
        assert result.n == 0


class TestSerialization:
    def test_roundtrip(self) -> None:
        ledger = JourneyLedger()
        ledger.record("score", "", run_id="r1", value=0.7, ts=1.0)
        ledger.record("score", "api", run_id="r1", value=0.8, ts=1.0)
        data = ledger.to_json()
        restored = JourneyLedger.from_json(data)
        assert restored.entries("score", "") == ledger.entries("score", "")
        assert restored.entries("score", "api") == ledger.entries("score", "api")

    def test_empty_roundtrip(self) -> None:
        ledger = JourneyLedger()
        data = ledger.to_json()
        restored = JourneyLedger.from_json(data)
        assert restored.metrics() == frozenset()
