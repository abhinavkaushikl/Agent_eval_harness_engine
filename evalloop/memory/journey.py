"""Journey ledger and trend tracking (T31).

The journey is the history of a metric (or a slice of a metric) across runs.
It answers "is this getting better?" by recording every data point and computing
a simple trend.  The trend is not a forecast; it is a direction: up, down, flat,
or insufficient data.

Per-field, per-slice
--------------------
A ledger key is ``(metric_name, slice_id)``.  ``slice_id`` is an arbitrary string
that the caller defines (e.g. a data partition, an artifact path, a category).
When no slicing is needed, ``slice_id`` is ``""`` (the whole-run aggregate).

What a trend is
---------------
* **up** -- the last value is above the mean of the prior values.
* **down** -- the last value is below the mean of the prior values.
* **flat** -- the last value is within one SD of the mean (or SD is zero).
* **insufficient** -- fewer than 3 data points; no trend can be stated.

The threshold (1 SD) is not invented: it corresponds to the noise-floor
principle (C3) that a change within the run-to-run SD is noise.  The noise floor
itself uses the sample SD (n-1); we do the same here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from evalloop._compat import StrEnum

__all__ = [
    "Trend",
    "TrendResult",
    "JourneyEntry",
    "JourneyLedger",
]


class Trend(StrEnum):
    """The direction of a metric over time."""

    up = "up"
    down = "down"
    flat = "flat"
    insufficient = "insufficient"


@dataclass(frozen=True, slots=True)
class TrendResult:
    """The trend of a metric: direction, the values, and the statistics behind it."""

    trend: Trend
    n: int
    latest: float
    mean: float  # mean of all values (including latest)
    sd: float  # sample SD (n-1) of all values; 0.0 when n < 2
    reason: str


@dataclass(frozen=True, slots=True)
class JourneyEntry:
    """One data point in a journey: a value at a run."""

    run_id: str
    value: float
    ts: float  # epoch seconds


class JourneyLedger:
    """Accumulates journey data and computes trends per (metric, slice) key.

    Usage::

        ledger = JourneyLedger()
        ledger.record("pass_rate", "", run_id="run-1", value=0.72, ts=1000.0)
        ledger.record("pass_rate", "", run_id="run-2", value=0.78, ts=2000.0)
        ledger.record("pass_rate", "", run_id="run-3", value=0.80, ts=3000.0)
        trend = ledger.trend("pass_rate", "")
        assert trend.trend == Trend.up
    """

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], list[JourneyEntry]] = {}

    def record(self, metric: str, slice_id: str, *, run_id: str, value: float, ts: float) -> None:
        """Append a data point for ``(metric, slice_id)``."""
        key = (metric, slice_id)
        self._data.setdefault(key, []).append(JourneyEntry(run_id=run_id, value=value, ts=ts))

    def entries(self, metric: str, slice_id: str) -> tuple[JourneyEntry, ...]:
        """All entries for a key, in recording order."""
        return tuple(self._data.get((metric, slice_id), []))

    def metrics(self) -> frozenset[str]:
        """All metric names that have at least one entry."""
        return frozenset(k[0] for k in self._data)

    def slices(self, metric: str) -> frozenset[str]:
        """All slice ids for a metric."""
        return frozenset(k[1] for k in self._data if k[0] == metric)

    def trend(self, metric: str, slice_id: str) -> TrendResult:
        """Compute the trend for ``(metric, slice_id)``."""
        entries = self._data.get((metric, slice_id), [])
        values = [e.value for e in entries]
        n = len(values)
        if n < 3:
            return TrendResult(
                trend=Trend.insufficient,
                n=n,
                latest=values[-1] if values else 0.0,
                mean=_mean(values) if values else 0.0,
                sd=0.0,
                reason=f"only {n} data point(s); need at least 3 to state a trend",
            )
        mean = _mean(values)
        sd = _sd(values, mean)
        latest = values[-1]
        if sd == 0.0:
            direction = Trend.flat
            reason = "all values are identical"
        elif latest > mean + sd:
            direction = Trend.up
            reason = f"latest ({latest:.4f}) is above mean + 1 SD ({mean + sd:.4f})"
        elif latest < mean - sd:
            direction = Trend.down
            reason = f"latest ({latest:.4f}) is below mean - 1 SD ({mean - sd:.4f})"
        else:
            direction = Trend.flat
            reason = f"latest ({latest:.4f}) is within 1 SD of the mean ({mean:.4f} ± {sd:.4f})"
        return TrendResult(trend=direction, n=n, latest=latest, mean=mean, sd=sd, reason=reason)

    def all_trends(self) -> Mapping[tuple[str, str], TrendResult]:
        """Trends for every recorded (metric, slice) key."""
        return {key: self.trend(key[0], key[1]) for key in sorted(self._data)}

    def to_json(self) -> dict[str, object]:
        """Serialise the ledger to a JSON-compatible dict."""
        result: dict[str, object] = {}
        for (metric, slice_id), entries in sorted(self._data.items()):
            key = f"{metric}:{slice_id}" if slice_id else metric
            result[key] = [
                {"run_id": e.run_id, "value": e.value, "ts": e.ts}
                for e in entries
            ]
        return result

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> JourneyLedger:
        """Restore a ledger from :meth:`to_json` output."""
        ledger = cls()
        for composite_key, entries_raw in data.items():
            if ":" in composite_key:
                metric, slice_id = composite_key.split(":", 1)
            else:
                metric, slice_id = composite_key, ""
            if not isinstance(entries_raw, list):
                continue
            for entry in entries_raw:
                if not isinstance(entry, dict):
                    continue
                ledger.record(
                    metric,
                    slice_id,
                    run_id=str(entry.get("run_id", "")),
                    value=float(entry.get("value", 0)),
                    ts=float(entry.get("ts", 0)),
                )
        return ledger


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _sd(values: Sequence[float], mean: float) -> float:
    """Sample SD (n-1), matching the noise floor's convention."""
    n = len(values)
    if n < 2:
        return 0.0
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))
