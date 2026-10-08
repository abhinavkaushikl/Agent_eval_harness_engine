"""The metric store: two runs written and diffed case by case, both directions, never a net delta.

Every file is a real one in ``tmp_path``, because append-only, versioning and interrupted writes
are properties of files on disk, not of objects in memory. Durations, scores, seeds and costs
below are test inputs: the store stores whatever the grader measured, and supplies none itself.
"""

from __future__ import annotations

import ast
import difflib
import inspect
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.memory.case import (
    CASE_FIELDS,
    CaseKind,
    CaseResult,
    FailureClass,
    OracleConfidence,
    Timeout,
    TimeoutCap,
    Verdict,
    content_hash,
)
from evalloop.memory.metric_store import (
    SCHEMA_VERSION,
    Absent,
    Flip,
    MetricStore,
    MetricStoreError,
    Outcome,
    RunDiff,
    diff_runs,
)

REPO = Path(__file__).resolve().parent.parent
EVALLOOP_MEMORY = REPO / "evalloop" / "memory"
ARTIFACT = content_hash(b"def price(amount): return amount * 0.9\n")
ORACLE = content_hash(b"def test_price(): assert price(1000) == 900\n")
WRONG = FailureClass.wrong_result
HUNG = Timeout(TimeoutCap.wall_clock, 10.0)


def case(
    case_id: str,
    verdict: Verdict = Verdict.passed,
    failure: FailureClass | None = None,
    *,
    run: str = "r1",
    kind: CaseKind = CaseKind.generated,
    confidence: OracleConfidence = OracleConfidence.high,
    rung: int | None = 1,
    timeout: Timeout | None = None,
    reason: str | None = None,
    score: float | None = None,
    evidence: str | None = None,
    cost: Decimal | None = None,
    seed: int | None = None,
    duration: float = 0.25,
    reused_from: str | None = None,
) -> CaseResult:
    return CaseResult(
        run_id=run,
        record_id="A1_execution_based",
        case_id=case_id,
        case_kind=kind,
        artifact_id="src/pricing.py",
        oracle_id=f"tests/test_pricing.py::{case_id}",
        oracle_confidence=confidence,
        ladder_rung=rung,
        verdict=verdict,
        failure_class=failure,
        timeout=timeout,
        inconclusive_reason=reason,
        score=score,
        evidence=evidence,
        artifact_hash=ARTIFACT,
        oracle_hash=ORACLE,
        reused_from=reused_from,
        seed=seed,
        cost_usd=cost,
        duration_seconds=duration,
    )


def ids(entries: Sequence[Flip | Absent]) -> list[str]:
    return [entry.case_id for entry in entries]


@pytest.fixture
def store(tmp_path: Path) -> MetricStore:
    return MetricStore(tmp_path)


def run_file(tmp_path: Path, run_id: str) -> Path:
    return tmp_path / "runs" / f"{run_id}.jsonl"


# -- the ticket's test: two runs, diffed case by case ------------------------------------------------


def test_two_runs_diff_case_by_case_in_both_directions(store: MetricStore) -> None:
    store.write_run("r1", [
        case("c1"),
        case("c2", Verdict.failed, WRONG),
        case("c3"),
        case("c4", Verdict.failed, WRONG),
        case("c5", Verdict.inconclusive, reason="the sandbox could not start"),
        case("c6"),
        case("c7"),
    ])
    store.write_run("r2", [
        case("c1", Verdict.failed, WRONG, run="r2"),
        case("c2", run="r2"),
        case("c3", run="r2"),
        case("c4", Verdict.failed, FailureClass.timeout, run="r2", timeout=HUNG),
        case("c5", run="r2"),
        case("c6", Verdict.inconclusive, run="r2", reason="network was required and not granted"),
        case("c8", run="r2"),
    ])
    diff = diff_runs(store.read_run("r1"), store.read_run("r2"))
    assert (diff.run_a, diff.run_b) == ("r1", "r2")
    assert ids(diff.regressions) == ["c1"]
    assert ids(diff.improvements) == ["c2"]
    assert ids(diff.failure_changed) == ["c4"]
    assert [(str(f.before), str(f.after)) for f in diff.failure_changed] == [("failed/wrong_result", "failed/timeout")]
    assert ids(diff.became_conclusive) == ["c5"]
    assert ids(diff.became_inconclusive) == ["c6"]
    assert diff.only_in_a == (Absent("A1_execution_based", "c7", "src/pricing.py", CaseKind.generated),)
    assert ids(diff.only_in_b) == ["c8"]


def test_a_net_gain_cannot_hide_regressions(store: MetricStore) -> None:
    """AGENT.md §3.8: per-item flips in both directions. A +4 here is six improvements and two regressions."""
    store.write_run("before", [case(f"c{i}", Verdict.failed, WRONG, run="before") for i in range(6)]
                    + [case(f"k{i}", run="before") for i in range(2)])
    store.write_run("after", [case(f"c{i}", run="after") for i in range(6)]
                    + [case(f"k{i}", Verdict.failed, WRONG, run="after") for i in range(2)])
    diff = diff_runs(store.read_run("before"), store.read_run("after"))
    assert (ids(diff.improvements), ids(diff.regressions)) == ([f"c{i}" for i in range(6)], ["k0", "k1"])
    assert [field.name for field in fields(RunDiff)] == [
        "run_a", "run_b", "regressions", "improvements", "failure_changed",
        "became_inconclusive", "became_conclusive", "only_in_a", "only_in_b",
    ]  # there is no net, total or delta field to report instead


def test_an_unchanged_outcome_is_not_a_flip(store: MetricStore) -> None:
    store.write_run("r1", [case("c1", Verdict.failed, WRONG), case("c2"), case("c3", Verdict.inconclusive, reason="a")])
    store.write_run("r2", [
        case("c1", Verdict.failed, WRONG, run="r2"),
        case("c2", run="r2", duration=9.0, score=0.5),
        case("c3", Verdict.inconclusive, run="r2", reason="b"),
    ])
    diff = diff_runs(store.read_run("r1"), store.read_run("r2"))
    assert all(getattr(diff, f.name) == () for f in fields(RunDiff) if f.name not in ("run_a", "run_b"))


def test_flips_are_sorted_by_technique_and_case_not_by_file_order(store: MetricStore) -> None:
    store.write_run("r1", [case("c3"), case("c1"), case("c2")])
    store.write_run("r2", [case(c, Verdict.failed, WRONG, run="r2") for c in ("c2", "c3", "c1")])
    assert ids(diff_runs(store.read_run("r1"), store.read_run("r2")).regressions) == ["c1", "c2", "c3"]


# -- the file: one case per line, in a fixed key order ---------------------------------------------------


def test_the_raw_files_diff_to_exactly_the_cases_that_changed(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case("c1"), case("c2"), case("c3")])
    store.write_run("r2", [case("c1", run="r2"), case("c2", Verdict.failed, WRONG, run="r2"), case("c3", run="r2")])
    first = run_file(tmp_path, "r1").read_text(encoding="utf-8").split("\n")[1:]
    second = run_file(tmp_path, "r2").read_text(encoding="utf-8").split("\n")[1:]
    changed = [line for line in difflib.ndiff(first, second) if line.startswith(("- ", "+ "))]
    assert len(changed) == 2 and all('"case_id": "c2"' in line for line in changed)


def test_every_line_has_the_schema_keys_in_the_schema_order(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case("c1"), case("c2", Verdict.failed, FailureClass.timeout, timeout=HUNG)])
    header, *lines = run_file(tmp_path, "r1").read_text(encoding="utf-8").rstrip("\n").split("\n")
    assert json.loads(header) == {"schema_version": SCHEMA_VERSION, "store": "evalloop.metric_store.run", "run_id": "r1"}
    for line in lines:
        assert [key for key, _ in json.loads(line, object_pairs_hook=list)] == list(CASE_FIELDS)
        assert '"run_id"' not in line  # in the header once, so identical cases are identical lines


def test_the_line_format_is_pinned(store: MetricStore, tmp_path: Path) -> None:
    """Reordering a field or changing the format is a schema change: it moves SCHEMA_VERSION with it."""
    assert SCHEMA_VERSION == 1
    store.write_run("r1", [case("c1")])
    assert run_file(tmp_path, "r1").read_text(encoding="utf-8").split("\n")[1] == (
        '{"record_id": "A1_execution_based", "case_id": "c1", "case_kind": "generated", '
        '"artifact_id": "src/pricing.py", "oracle_id": "tests/test_pricing.py::c1", '
        '"oracle_confidence": "high", "ladder_rung": 1, "verdict": "passed", "failure_class": null, '
        '"timeout": null, "inconclusive_reason": null, "score": null, "evidence": null, '
        f'"artifact_hash": "{ARTIFACT}", "oracle_hash": "{ORACLE}", '
        '"reused_from": null, "seed": null, "cost_usd": null, "duration_seconds": 0.25}'
    )


def test_the_round_trip_is_lossless(store: MetricStore, tmp_path: Path) -> None:
    rich = case(
        "c1",
        Verdict.failed,
        FailureClass.timeout,
        kind=CaseKind.permanent,
        confidence=OracleConfidence.low,
        timeout=Timeout(TimeoutCap.cpu_time, 10.0),
        score=0.8333333333333334,
        evidence='expected 900, got 1000 — "₹" line one\nline two   still one case',
        cost=Decimal("0.00128"),
        seed=7,
        duration=0.30000000000000004,
    )
    statistic = case("c2", rung=None)  # a non-grader technique has no rung
    unsure = case("c3", Verdict.inconclusive, reason="the oracle itself could not run")
    carried = case("c4", reused_from="r0")
    store.write_run("r1", [rich, statistic, unsure, carried])
    assert store.read_run("r1").cases == (rich, statistic, unsure, carried)
    assert run_file(tmp_path, "r1").read_bytes().count(b"\n") == 5  # a header and four cases, nothing split


def test_reading_is_deterministic(store: MetricStore) -> None:
    store.write_run("r1", [case("c2"), case("c1")])
    assert store.read_run("r1") == store.read_run("r1")
    assert ids_of_run(store, "r1") == ["c2", "c1"]  # the order written


def ids_of_run(store: MetricStore, run_id: str) -> list[str]:
    return [c.case_id for c in store.read_run(run_id).cases]


# -- refusing what cannot be read faithfully ----------------------------------------------------------


@pytest.mark.parametrize("version", [2, 0, True, 1.0, "1", None])
def test_an_unknown_schema_version_is_refused_loudly(store: MetricStore, tmp_path: Path, version: object) -> None:
    store.write_run("r1", [case("c1")])
    path = run_file(tmp_path, "r1")
    header, rest = path.read_text(encoding="utf-8").split("\n", 1)
    document = json.loads(header)
    document["schema_version"] = version
    path.write_text(json.dumps(document) + "\n" + rest, encoding="utf-8")
    with pytest.raises(MetricStoreError, match=r"is schema version .*reads version 1 only"):
        store.read_run("r1")


def test_a_damaged_run_names_every_bad_line(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case(f"c{i}") for i in range(1, 6)])
    path = run_file(tmp_path, "r1")
    lines = path.read_bytes().split(b"\n")  # the header is line 1, so c1 is line 2
    lines[2] = lines[2].replace(b'"verdict": "passed"', b'"verdict": "pass"')
    lines[3] = b"\xff" + lines[3]
    lines[4] = lines[4].replace(b'"seed": null', b'"seed": null, "seed": 7')
    lines[5] = b"{not json"
    path.write_bytes(b"\n".join(lines))
    with pytest.raises(MetricStoreError) as caught:
        store.read_run("r1")
    report = str(caught.value).split("\n")
    assert [line.split(":")[0] for line in report] == [f"r1.jsonl line {n}" for n in (3, 4, 5, 6)]
    assert "not UTF-8" in report[1] and "'seed' appears twice" in report[2] and "not JSON" in report[3]


def test_unknown_and_missing_fields_are_refused(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case("c1")])
    path = run_file(tmp_path, "r1")
    header, line = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    document = json.loads(line)
    del document["seed"]
    document["extra"] = 1
    path.write_text(header + "\n" + json.dumps(document) + "\n", encoding="utf-8")
    with pytest.raises(MetricStoreError, match=r"unknown fields \['extra'\] and missing fields \['seed'\]"):
        store.read_run("r1")


def test_an_interrupted_write_is_refused(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case("c1"), case("c2")])
    path = run_file(tmp_path, "r1")
    path.write_bytes(path.read_bytes()[:-20])
    with pytest.raises(MetricStoreError, match="unterminated"):
        store.read_run("r1")


def test_a_run_file_answers_only_to_its_own_id(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case("c1")])
    run_file(tmp_path, "r9").write_bytes(run_file(tmp_path, "r1").read_bytes())
    with pytest.raises(MetricStoreError, match="the header is not run 'r9''s"):
        store.read_run("r9")


# -- append-only -----------------------------------------------------------------------------------


def test_a_run_is_never_rewritten(store: MetricStore, tmp_path: Path) -> None:
    store.write_run("r1", [case("c1")])
    before = run_file(tmp_path, "r1").read_bytes()
    with pytest.raises(MetricStoreError, match="already exists"):
        store.write_run("r1", [case("c1", Verdict.failed, WRONG)])
    with pytest.raises(MetricStoreError, match="already exists"):
        store.open_run("r1")
    assert run_file(tmp_path, "r1").read_bytes() == before


def test_cases_are_appended_as_they_are_judged(store: MetricStore) -> None:
    with store.open_run("r1") as writer:
        writer.append(case("c1"))
        assert ids_of_run(store, "r1") == ["c1"]  # flushed: readable while the run is still open
        writer.append(case("c2"))
    assert ids_of_run(store, "r1") == ["c1", "c2"]
    with pytest.raises(MetricStoreError, match="is closed"):
        writer.append(case("c3"))


def test_a_refused_run_leaves_no_file(store: MetricStore) -> None:
    with pytest.raises(MetricStoreError, match="appears twice"):
        store.write_run("r1", [case("c1"), case("c1")])
    with pytest.raises(MetricStoreError, match="cannot be written to run"):
        store.write_run("r1", [case("c1", run="r2")])
    assert store.runs() == ()


def test_a_case_belongs_to_its_run_and_appears_once(store: MetricStore) -> None:
    with store.open_run("r1") as writer:
        with pytest.raises(MetricStoreError, match="cannot be written to run"):
            writer.append(case("c1", run="r2"))
        writer.append(case("c1"))
        with pytest.raises(MetricStoreError, match="already in run"):
            writer.append(case("c1", Verdict.failed, WRONG))


# -- EL-014's rules, held by the case itself ---------------------------------------------------------


def test_the_vocabulary_is_el_014s() -> None:
    """A:39's four failure classes, verbatim, plus EL-014's timeout."""
    assert [c.value for c in FailureClass] == ["syntax_error", "unknown_column", "runtime_error", "wrong_result", "timeout"]
    assert [v.value for v in Verdict] == ["passed", "failed", "inconclusive"]


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"verdict": Verdict.failed}, "if and only if it failed"),
        ({"failure_class": WRONG}, "if and only if it failed"),
        ({"verdict": Verdict.inconclusive}, "inconclusive_reason"),
        ({"inconclusive_reason": "why"}, "only an inconclusive case"),
        ({"verdict": Verdict.failed, "failure_class": FailureClass.timeout}, "cap and limit"),
        ({"verdict": Verdict.failed, "failure_class": WRONG, "timeout": HUNG}, "cap and limit"),
        ({"record_id": "A1_execution_based\n"}, "record id"),
        ({"artifact_hash": "abc"}, "SHA-256"),
        ({"oracle_hash": ARTIFACT.upper()}, "SHA-256"),
        ({"duration_seconds": -1.0}, "negative"),
        ({"score": float("nan")}, "finite"),
        ({"seed": True}, "seed"),
        ({"cost_usd": Decimal("-0.01")}, "cost_usd"),
        ({"cost_usd": 0.01}, "cost_usd"),
        ({"run_id": "../escape"}, "run_id"),
        ({"ladder_rung": 0}, "ladder_rung"),
        ({"case_kind": "permanent"}, "CaseKind"),
        ({"reused_from": "r1"}, "its own run"),
        ({"reused_from": "../r0"}, "run_id"),
        ({"verdict": Verdict.inconclusive, "inconclusive_reason": "why", "reused_from": "r0"}, "never reused"),
    ],
)
def test_a_case_that_breaks_a_rule_is_refused(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        replace(case("c1"), **changes)  # type: ignore[arg-type]  # ill-typed on purpose: the runtime check is under test


# -- permanent cases ----------------------------------------------------------------------------------


def test_permanent_cases_survive_a_run_that_does_not_regenerate_them(store: MetricStore) -> None:
    failing = case("c1", Verdict.failed, WRONG)
    store.write_run("r1", [failing, case("c2")])
    promoted = store.promote(failing, reason="the ₹999 threshold bug, kept as a regression test")
    store.write_run("r2", [case("c2", run="r2")])  # r2 did not regenerate c1
    assert store.permanent_cases() == (promoted,)
    assert store.missing_permanent(store.read_run("r2")) == (promoted,)
    store.write_run("r3", [case("c1", run="r3", kind=CaseKind.permanent), case("c2", run="r3")])
    assert store.missing_permanent(store.read_run("r3")) == ()
    assert store.permanent_cases() == (promoted,)


def test_a_promoted_case_keeps_where_it_came_from_and_its_oracle(store: MetricStore) -> None:
    promoted = store.promote(case("c1", Verdict.failed, WRONG), reason="pinned")
    assert (promoted.promoted_from_run, promoted.oracle_id, promoted.oracle_hash) == ("r1", "tests/test_pricing.py::c1", ORACLE)


def test_a_case_is_promoted_once(store: MetricStore) -> None:
    store.promote(case("c1"), reason="pinned")
    with pytest.raises(MetricStoreError, match="already permanent"):
        store.promote(case("c1", run="r2"), reason="pinned again")


def test_the_permanent_file_is_versioned_too(store: MetricStore, tmp_path: Path) -> None:
    store.promote(case("c1"), reason="pinned")
    path = tmp_path / "permanent.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version": 9', 1), encoding="utf-8")
    with pytest.raises(MetricStoreError, match="schema version 9"):
        store.permanent_cases()
    with pytest.raises(MetricStoreError, match="schema version 9"):
        store.promote(case("c2"), reason="appending past a file it cannot read")


# -- the content-hash lookup -------------------------------------------------------------------------


def test_lookup_reuses_only_conclusive_results_for_unchanged_contents(store: MetricStore) -> None:
    """AGENT.md §3.9: an unchanged artifact is not re-judged. A changed oracle or an inconclusive result is."""
    store.write_run("r1", [case("c1"), case("c2", Verdict.inconclusive, reason="sandbox did not start")])
    run = store.read_run("r1")

    def lookup(oracle_id: str, oracle_hash: str = ORACLE, artifact_hash: str = ARTIFACT) -> CaseResult | None:
        return run.lookup(record_id="A1_execution_based", oracle_id=oracle_id, artifact_hash=artifact_hash, oracle_hash=oracle_hash)

    assert lookup("tests/test_pricing.py::c1") == run.case("A1_execution_based", "c1")
    assert lookup("tests/test_pricing.py::c1", oracle_hash=content_hash(b"assert True\n")) is None
    assert lookup("tests/test_pricing.py::c1", artifact_hash=content_hash(b"changed\n")) is None
    assert lookup("tests/test_pricing.py::c2") is None


def test_a_reused_result_stays_in_its_run_and_names_the_run_that_judged_it(store: MetricStore) -> None:
    """EL-214's skip leaves the run saying what it skipped, and a diff does not call the case gone."""
    judged = case("c1", Verdict.failed, WRONG, duration=2.0)
    store.write_run("r1", [judged, case("c2")])
    hit = store.read_run("r1").lookup(
        record_id="A1_execution_based", oracle_id="tests/test_pricing.py::c1", artifact_hash=ARTIFACT, oracle_hash=ORACLE
    )
    assert hit is not None
    store.write_run("r2", [hit.reused_in("r2"), case("c2", run="r2")])
    store.write_run("r3", [store.read_run("r2").cases[0].reused_in("r3"), case("c2", run="r3")])
    carried = store.read_run("r3").cases[0]
    assert (carried.run_id, carried.reused_from, carried.verdict, carried.duration_seconds) == ("r3", "r1", Verdict.failed, 2.0)
    diff = diff_runs(store.read_run("r1"), store.read_run("r3"))
    assert all(getattr(diff, f.name) == () for f in fields(RunDiff) if f.name not in ("run_a", "run_b"))


# -- location, listing, boundaries ----------------------------------------------------------------------


def test_the_location_is_an_argument_and_is_never_created(tmp_path: Path) -> None:
    with pytest.raises(MetricStoreError, match="not a directory"):
        MetricStore(tmp_path / "not-yet")
    assert not (tmp_path / "not-yet").exists()
    store = MetricStore(str(tmp_path))
    assert not (tmp_path / "runs").exists()  # nothing is created until a run is opened
    store.write_run("r1", [case("c1")])
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == ["runs", "runs/r1.jsonl"]


def test_the_store_has_no_location_of_its_own() -> None:
    """CLAUDE.md §3: never an absolute user path. The caller names the directory, and nothing defaults it."""
    assert inspect.signature(MetricStore).parameters["directory"].default is inspect.Parameter.empty
    names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for module in ("metric_store.py", "case.py")
        for node in ast.walk(ast.parse((EVALLOOP_MEMORY / module).read_text(encoding="utf-8")))
        if isinstance(node, (ast.Attribute, ast.Name))
    }
    assert names.isdisjoint({"home", "expanduser", "environ", "getenv", "cwd", "getcwd", "gettempdir"})


def test_runs_are_listed_in_sorted_order(store: MetricStore) -> None:
    store.write_run("r-b", [case("c1", run="r-b")])
    store.write_run("r-a", [case("c1", run="r-a")])
    assert store.runs() == ("r-a", "r-b")
    with pytest.raises(MetricStoreError, match="no run"):
        store.read_run("r-c")


def test_an_outcome_renders_with_its_class() -> None:
    assert str(Outcome(Verdict.failed, FailureClass.timeout)) == "failed/timeout"
    assert str(Outcome(Verdict.passed, None)) == "passed"


def test_the_memory_package_never_imports_statistics() -> None:
    """The ticket: the store must not import evalloop.stats, directly, lazily, or through another module."""
    imported: list[str] = []
    for path in sorted(EVALLOOP_MEMORY.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                package = "evalloop.memory".rsplit(".", node.level - 1)[0] if node.level else ""
                module = ".".join(part for part in (package, node.module) if part)
                names = [module] + [f"{module}.{alias.name}" for alias in node.names]
            else:
                continue
            if any(name == "evalloop.stats" or name.startswith("evalloop.stats.") for name in names):
                imported.append(f"{path.name}:{node.lineno}")
    loaded = subprocess.run(
        [sys.executable, "-c", "import sys, evalloop.memory; print(sorted(m for m in sys.modules if m.startswith('evalloop.stats')))"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert (imported, loaded) == ([], "[]")
