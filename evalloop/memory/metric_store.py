"""The metric store: every judged case, one JSON line each, append-only, one file per run.

``AGENT.md`` §3.9 asks for a "Metric store: JSONL with full schema from day one. Two runs can be
diffed per case." The schema is ``case.py``'s. This module writes it, reads it back unchanged, and
compares two runs.

Layout
------
::

    <store>/runs/<run_id>.jsonl    a header line, then one case per line
    <store>/permanent.jsonl        a header line, then one promoted case per line

The store's directory is an argument, and it must already exist. ``USER_EXPERIENCE.md`` §6 still
asks "Session report location (repo ``.evalloop/`` vs user home)?", so this module does not answer
it either. Inside that directory the store creates only its own ``runs/``.

Append-only, and a version in every file
----------------------------------------
- **A run file is created once.** It is opened in exclusive mode, so an existing run is never
  rewritten, and lines are appended and flushed as cases are judged.
- **A promoted case is appended once** to ``permanent.jsonl``.
- **Each file's first line carries its schema version.** A reader that meets a version other than
  :data:`SCHEMA_VERSION` refuses the whole file and says so, rather than guessing at fields it was
  not written to read.

A damaged file is refused too. Every bad line is reported at once, with its line number, the way
the registry loader aggregates errors (``CLAUDE.md`` §7.7). Damage includes:

- a line that is not UTF-8 or not JSON;
- a key that appears twice on one line, where ``json.loads`` would silently keep the second value;
- an unterminated last line, which means a write was interrupted.

One case per line, keys in a fixed order
----------------------------------------
- **Lines are split on ``b"\\n"`` only, as bytes, then decoded one at a time.** Never use
  ``str.splitlines()`` here: JSON leaves U+2028 unescaped inside strings when ``ensure_ascii`` is
  off, and ``splitlines()`` cuts a line in two there.
- **Keys follow ``case.CASE_FIELDS``.** ``run_id`` is not on each line: it is in the header, so
  identical cases in two runs are identical lines.
- **The result is that ``diff`` of two run files shows exactly the cases that changed.**

``diff_runs``: both directions, never a net delta
-------------------------------------------------
``AGENT.md`` §3.8 and ``USER_EXPERIENCE.md`` §3.4 both require per-item flips "in both
directions". A +2 can hide six regressions, which is the failure this store exists to prevent.
So :class:`RunDiff` has no net or total field at all. It lists:

- regressions;
- improvements;
- failures whose class changed (a wrong answer that became a hang is not a fix);
- cases that became, or stopped being, inconclusive (EL-014: evidence lost or gained, not a flip);
- cases present in only one of the two runs.

Concurrency
-----------
There is one writer per store, by design: the run driver. Two writers appending to the same run
cannot happen, because the run file is created exclusively. Two writers promoting at once could
interleave lines, so promotion belongs to one process.

This module never imports ``evalloop.stats``. Statistics over stored cases belong there, not here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import TracebackType
from typing import IO, cast

from evalloop.memory.case import (
    CASE_FIELDS,
    CaseKind,
    CaseResult,
    FailureClass,
    OracleConfidence,
    PermanentCase,
    Timeout,
    TimeoutCap,
    Verdict,
    check_run_id,
)

__all__ = [
    "SCHEMA_VERSION",
    "Absent",
    "Flip",
    "MetricStore",
    "MetricStoreError",
    "Outcome",
    "Run",
    "RunDiff",
    "RunWriter",
    "diff_runs",
]

#: The schema version written into every file this module creates.
SCHEMA_VERSION = 1

_RUN_TAG = "evalloop.metric_store.run"
_PERMANENT_TAG = "evalloop.metric_store.permanent"
_PERMANENT_FIELDS = (
    "record_id",
    "case_id",
    "artifact_id",
    "oracle_id",
    "oracle_confidence",
    "oracle_hash",
    "promoted_from_run",
    "reason",
)


class MetricStoreError(Exception):
    """A rule of the store was broken, or a file cannot be read faithfully."""


# -- writing ---------------------------------------------------------------------------------------


def _dumps(document: Mapping[str, object]) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(", ", ": "), allow_nan=False)


def _case_document(case: CaseResult) -> dict[str, object]:
    timeout: object = None
    if case.timeout is not None:
        timeout = {"cap": case.timeout.cap.value, "limit_seconds": case.timeout.limit_seconds}
    document: dict[str, object] = {
        "record_id": case.record_id,
        "case_id": case.case_id,
        "case_kind": case.case_kind.value,
        "artifact_id": case.artifact_id,
        "oracle_id": case.oracle_id,
        "oracle_confidence": case.oracle_confidence.value,
        "ladder_rung": case.ladder_rung,
        "verdict": case.verdict.value,
        "failure_class": None if case.failure_class is None else case.failure_class.value,
        "timeout": timeout,
        "inconclusive_reason": case.inconclusive_reason,
        "score": case.score,
        "evidence": case.evidence,
        "artifact_hash": case.artifact_hash,
        "oracle_hash": case.oracle_hash,
        "reused_from": case.reused_from,
        "seed": case.seed,
        "cost_usd": None if case.cost_usd is None else str(case.cost_usd),
        "duration_seconds": case.duration_seconds,
    }
    assert tuple(document) == CASE_FIELDS  # the schema and the writer cannot drift apart
    return document


def _permanent_document(case: PermanentCase) -> dict[str, object]:
    return {
        "record_id": case.record_id,
        "case_id": case.case_id,
        "artifact_id": case.artifact_id,
        "oracle_id": case.oracle_id,
        "oracle_confidence": case.oracle_confidence.value,
        "oracle_hash": case.oracle_hash,
        "promoted_from_run": case.promoted_from_run,
        "reason": case.reason,
    }


class RunWriter:
    """Appends one run's cases to its file as they are judged. Created by :meth:`MetricStore.open_run`."""

    def __init__(self, path: Path, run_id: str) -> None:
        try:
            self._file: IO[str] = path.open("x", encoding="utf-8", newline="\n")
        except FileExistsError:
            raise MetricStoreError(
                f"run {run_id!r} already exists; runs are append-only and never rewritten"
            ) from None
        self._run_id = run_id
        self._keys: set[tuple[str, str]] = set()
        self._write({"schema_version": SCHEMA_VERSION, "store": _RUN_TAG, "run_id": run_id})

    def append(self, case: CaseResult) -> None:
        if self._file.closed:
            raise MetricStoreError(f"run {self._run_id!r} is closed")
        if case.run_id != self._run_id:
            raise MetricStoreError(f"a case from run {case.run_id!r} cannot be written to run {self._run_id!r}")
        if case.key in self._keys:
            raise MetricStoreError(f"{case.key} is already in run {self._run_id!r}; a case appears once per run")
        self._keys.add(case.key)
        self._write(_case_document(case))

    def _write(self, document: Mapping[str, object]) -> None:
        self._file.write(_dumps(document) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> RunWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


# -- reading ---------------------------------------------------------------------------------------


def _object(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} is not a JSON object")
    mapping: dict[object, object] = value
    if not all(isinstance(key, str) for key in mapping):
        raise ValueError(f"{where} has a non-string key")
    return cast("dict[str, object]", mapping)


def _fields(document: Mapping[str, object], expected: tuple[str, ...]) -> None:
    unknown = [key for key in document if key not in expected]
    missing = [key for key in expected if key not in document]
    if unknown or missing:
        raise ValueError(f"unknown fields {unknown} and missing fields {missing}")


def _str(document: Mapping[str, object], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} is not a string")
    return value


def _optional_str(document: Mapping[str, object], key: str) -> str | None:
    value = document[key]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{key} is not a string or null")
    return value


def _optional_int(document: Mapping[str, object], key: str) -> int | None:
    value = document[key]
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{key} is not an integer or null")
    return value


def _optional_number(document: Mapping[str, object], key: str) -> float | None:
    value = document[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} is not a number or null")
    return value


def _case_from(document: Mapping[str, object], run_id: str) -> CaseResult:
    _fields(document, CASE_FIELDS)
    timeout_document = document["timeout"]
    timeout: Timeout | None = None
    if timeout_document is not None:
        raw_timeout = _object(timeout_document, "timeout")
        _fields(raw_timeout, ("cap", "limit_seconds"))
        limit = _optional_number(raw_timeout, "limit_seconds")
        if limit is None:
            raise ValueError("timeout.limit_seconds is null")
        timeout = Timeout(TimeoutCap(_str(raw_timeout, "cap")), limit)
    cost_text = _optional_str(document, "cost_usd")
    try:
        cost = None if cost_text is None else Decimal(cost_text)
    except InvalidOperation:
        raise ValueError(f"cost_usd {cost_text!r} is not a decimal number") from None
    failure_class = _optional_str(document, "failure_class")
    duration = _optional_number(document, "duration_seconds")
    if duration is None:
        raise ValueError("duration_seconds is null")
    return CaseResult(
        run_id=run_id,
        record_id=_str(document, "record_id"),
        case_id=_str(document, "case_id"),
        case_kind=CaseKind(_str(document, "case_kind")),
        artifact_id=_str(document, "artifact_id"),
        oracle_id=_str(document, "oracle_id"),
        oracle_confidence=OracleConfidence(_str(document, "oracle_confidence")),
        ladder_rung=_optional_int(document, "ladder_rung"),
        verdict=Verdict(_str(document, "verdict")),
        failure_class=None if failure_class is None else FailureClass(failure_class),
        timeout=timeout,
        inconclusive_reason=_optional_str(document, "inconclusive_reason"),
        score=_optional_number(document, "score"),
        evidence=_optional_str(document, "evidence"),
        artifact_hash=_str(document, "artifact_hash"),
        oracle_hash=_str(document, "oracle_hash"),
        reused_from=_optional_str(document, "reused_from"),
        seed=_optional_int(document, "seed"),
        cost_usd=cost,
        duration_seconds=duration,
    )


def _permanent_from(document: Mapping[str, object]) -> PermanentCase:
    _fields(document, _PERMANENT_FIELDS)
    return PermanentCase(
        record_id=_str(document, "record_id"),
        case_id=_str(document, "case_id"),
        artifact_id=_str(document, "artifact_id"),
        oracle_id=_str(document, "oracle_id"),
        oracle_confidence=OracleConfidence(_str(document, "oracle_confidence")),
        oracle_hash=_str(document, "oracle_hash"),
        promoted_from_run=_str(document, "promoted_from_run"),
        reason=_str(document, "reason"),
    )


def _no_repeated_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"the key {key!r} appears twice")
        document[key] = value
    return document


def _decode(line: bytes) -> object:
    """One line as JSON. Bytes are split before decoding, so one bad line cannot hide the rest."""
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("not UTF-8") from None
    try:
        return json.loads(text, object_pairs_hook=_no_repeated_keys)
    except json.JSONDecodeError as error:
        raise ValueError(f"not JSON ({error.msg})") from None


def _lines(path: Path) -> tuple[Mapping[str, object], list[tuple[int, object]]]:
    """The header, and every later line decoded. Version and framing are checked here, loudly."""
    data = path.read_bytes()
    if not data.endswith(b"\n"):
        raise MetricStoreError(f"{path.name}: the last line is unterminated; a write was interrupted")
    raw_lines = data[:-1].split(b"\n")
    try:
        header = _object(_decode(raw_lines[0]), "the header")
    except ValueError as error:
        raise MetricStoreError(f"{path.name} line 1 is not a store header: {error}") from None
    version = header.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
        raise MetricStoreError(
            f"{path.name} is schema version {version!r}; this EvalLoop reads version "
            f"{SCHEMA_VERSION} only, and will not guess at fields it was not written to read"
        )
    decoded: list[tuple[int, object]] = []
    for number, line in enumerate(raw_lines[1:], start=2):
        try:
            decoded.append((number, _decode(line)))
        except ValueError as error:
            decoded.append((number, error))
    return header, decoded


@dataclass(frozen=True)
class Run:
    """One run's cases, in the order they were written."""

    run_id: str
    cases: tuple[CaseResult, ...]

    def case(self, record_id: str, case_id: str) -> CaseResult | None:
        return next((c for c in self.cases if c.key == (record_id, case_id)), None)

    def lookup(
        self, *, record_id: str, oracle_id: str, artifact_hash: str, oracle_hash: str
    ) -> CaseResult | None:
        """An earlier conclusive result for the same technique, oracle and contents.

        This is what EL-214's skip-if-unchanged reads (``AGENT.md`` §3.9). An inconclusive result
        is never reused: there the evaluation failed, so it has to run again. A hit goes into the
        new run as ``hit.reused_in(new_run_id)``, so the run records what it did not re-judge.
        """
        for case in self.cases:
            if (
                case.record_id == record_id
                and case.oracle_id == oracle_id
                and case.artifact_hash == artifact_hash
                and case.oracle_hash == oracle_hash
                and case.verdict is not Verdict.inconclusive
            ):
                return case
        return None


class MetricStore:
    """Runs of judged cases, and the cases promoted to run in every future run."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        root = Path(directory)
        if not root.is_dir():
            raise MetricStoreError(f"{root} is not a directory; the store does not create its own location")
        self._runs = root / "runs"
        self._permanent = root / "permanent.jsonl"

    # runs

    def open_run(self, run_id: str) -> RunWriter:
        """Start a run's file. Fails if the run exists: runs are never rewritten."""
        check_run_id(run_id)
        self._runs.mkdir(exist_ok=True)
        return RunWriter(self._runs / f"{run_id}.jsonl", run_id)

    def write_run(self, run_id: str, cases: Iterable[CaseResult]) -> None:
        """Write a whole run. Every case is checked first, so a refused run leaves no file."""
        check_run_id(run_id)
        given = tuple(cases)
        keys: set[tuple[str, str]] = set()
        for case in given:
            if case.run_id != run_id:
                raise MetricStoreError(f"a case from run {case.run_id!r} cannot be written to run {run_id!r}")
            if case.key in keys:
                raise MetricStoreError(f"{case.key} appears twice; a case appears once per run")
            keys.add(case.key)
        with self.open_run(run_id) as writer:
            for case in given:
                writer.append(case)

    def runs(self) -> tuple[str, ...]:
        """Every run id, sorted, so the listing never depends on the filesystem's order."""
        if not self._runs.is_dir():
            return ()
        return tuple(sorted(path.stem for path in self._runs.glob("*.jsonl")))

    def read_run(self, run_id: str) -> Run:
        path = self._runs / f"{check_run_id(run_id)}.jsonl"
        if not path.is_file():
            raise MetricStoreError(f"no run {run_id!r}")
        header, lines = _lines(path)
        if header.get("store") != _RUN_TAG or header.get("run_id") != run_id or len(header) != 3:
            raise MetricStoreError(f"{path.name}: the header is not run {run_id!r}'s")
        cases: list[CaseResult] = []
        problems: list[str] = []
        seen: set[tuple[str, str]] = set()
        for number, value in lines:
            try:
                if isinstance(value, ValueError):
                    raise value
                case = _case_from(_object(value, "the line"), run_id)
                if case.key in seen:
                    raise ValueError(f"{case.key} appears twice")
                seen.add(case.key)
                cases.append(case)
            except ValueError as error:
                problems.append(f"{path.name} line {number}: {error}")
        if problems:
            raise MetricStoreError("\n".join(problems))
        return Run(run_id, tuple(cases))

    # permanent cases

    def permanent_cases(self) -> tuple[PermanentCase, ...]:
        """Every promoted case, in promotion order."""
        if not self._permanent.is_file():
            return ()
        header, lines = _lines(self._permanent)
        if header.get("store") != _PERMANENT_TAG or len(header) != 2:
            raise MetricStoreError(f"{self._permanent.name}: the header is not the permanent store's")
        promoted: list[PermanentCase] = []
        problems: list[str] = []
        for number, value in lines:
            try:
                if isinstance(value, ValueError):
                    raise value
                promoted.append(_permanent_from(_object(value, "the line")))
            except ValueError as error:
                problems.append(f"{self._permanent.name} line {number}: {error}")
        if problems:
            raise MetricStoreError("\n".join(problems))
        return tuple(promoted)

    def promote(self, case: CaseResult, *, reason: str) -> PermanentCase:
        """Keep ``case`` in every future run, e.g. a failure turned into a test. Once per case."""
        permanent = PermanentCase(
            record_id=case.record_id,
            case_id=case.case_id,
            artifact_id=case.artifact_id,
            oracle_id=case.oracle_id,
            oracle_confidence=case.oracle_confidence,
            oracle_hash=case.oracle_hash,
            promoted_from_run=case.run_id,
            reason=reason,
        )
        if any(existing.key == permanent.key for existing in self.permanent_cases()):
            raise MetricStoreError(f"{permanent.key} is already permanent; a case is promoted once")
        try:
            with self._permanent.open("x", encoding="utf-8", newline="\n") as created:
                created.write(_dumps({"schema_version": SCHEMA_VERSION, "store": _PERMANENT_TAG}) + "\n")
        except FileExistsError:
            pass
        with self._permanent.open("a", encoding="utf-8", newline="\n") as appended:
            appended.write(_dumps(_permanent_document(permanent)) + "\n")
        return permanent

    def missing_permanent(self, run: Run) -> tuple[PermanentCase, ...]:
        """Permanent cases this run did not include. They survive it, and the gap is reported."""
        present = {case.key for case in run.cases}
        return tuple(case for case in self.permanent_cases() if case.key not in present)


# -- comparing two runs ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """A case's verdict and, if it failed, how. Rendered ``failed/timeout``."""

    verdict: Verdict
    failure_class: FailureClass | None

    def __str__(self) -> str:
        if self.failure_class is None:
            return self.verdict.value
        return f"{self.verdict.value}/{self.failure_class.value}"


@dataclass(frozen=True)
class Flip:
    """One case whose outcome changed between two runs."""

    record_id: str
    case_id: str
    artifact_id: str
    before: Outcome
    after: Outcome


@dataclass(frozen=True)
class Absent:
    """A case present in one run and not the other."""

    record_id: str
    case_id: str
    artifact_id: str
    case_kind: CaseKind


@dataclass(frozen=True)
class RunDiff:
    """Two runs, compared case by case. There is deliberately no net or total field."""

    run_a: str
    run_b: str
    regressions: tuple[Flip, ...]
    improvements: tuple[Flip, ...]
    failure_changed: tuple[Flip, ...]
    became_inconclusive: tuple[Flip, ...]
    became_conclusive: tuple[Flip, ...]
    only_in_a: tuple[Absent, ...]
    only_in_b: tuple[Absent, ...]


def _outcome(case: CaseResult) -> Outcome:
    return Outcome(case.verdict, case.failure_class)


def _absent(case: CaseResult) -> Absent:
    return Absent(case.record_id, case.case_id, case.artifact_id, case.case_kind)


def diff_runs(run_a: Run, run_b: Run) -> RunDiff:
    """Every case that changed between ``run_a`` and ``run_b``, sorted by technique and case id."""
    before = {case.key: case for case in run_a.cases}
    after = {case.key: case for case in run_b.cases}
    regressions: list[Flip] = []
    improvements: list[Flip] = []
    failure_changed: list[Flip] = []
    became_inconclusive: list[Flip] = []
    became_conclusive: list[Flip] = []
    for key in sorted(before.keys() & after.keys()):
        old, new = before[key], after[key]
        flip = Flip(new.record_id, new.case_id, new.artifact_id, _outcome(old), _outcome(new))
        if old.verdict is Verdict.passed and new.verdict is Verdict.failed:
            regressions.append(flip)
        elif old.verdict is Verdict.failed and new.verdict is Verdict.passed:
            improvements.append(flip)
        elif old.verdict is Verdict.failed and new.verdict is Verdict.failed:
            if old.failure_class is not new.failure_class:
                failure_changed.append(flip)
        elif new.verdict is Verdict.inconclusive and old.verdict is not Verdict.inconclusive:
            became_inconclusive.append(flip)
        elif old.verdict is Verdict.inconclusive and new.verdict is not Verdict.inconclusive:
            became_conclusive.append(flip)
    return RunDiff(
        run_a=run_a.run_id,
        run_b=run_b.run_id,
        regressions=tuple(regressions),
        improvements=tuple(improvements),
        failure_changed=tuple(failure_changed),
        became_inconclusive=tuple(became_inconclusive),
        became_conclusive=tuple(became_conclusive),
        only_in_a=tuple(_absent(before[key]) for key in sorted(before.keys() - after.keys())),
        only_in_b=tuple(_absent(after[key]) for key in sorted(after.keys() - before.keys())),
    )
