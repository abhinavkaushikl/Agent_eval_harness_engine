"""`evalloop check <path>`: one command that walks the whole M1 loop and writes `summary.md`.

Gate 1 is "point at a toy repo with a deliberately broken function; it gets caught, with zero
instruction from you." Nothing else in M1 joins the parts, so this does, in order:

    classify (EL-204) -> plan (EL-213 evidence + the planner) -> harvest (EL-205)
      -> grade (EL-207, in EL-206's sandbox) -> store (EL-201/EL-202) -> render (EL-211)

It is **one shot**: a path in, a report out, and it returns. There is no poller, debouncer, event
loop, worker pool, server or dashboard here -- all of that is M2 (T23–T26), and adding any of it is
the scope violation this ticket is most likely to invite. If it seems to need to watch for changes
to be useful, that is a finding for M2, not a thing to add here.

Honest exit codes, three of them
--------------------------------
``RunOutcome`` and the process exit code distinguish three results, never two:

* ``PROBLEM`` (1) — at least one failure the current state is answerable for.
* ``CLEAN`` (0) — something was graded and nothing failed.
* ``UNDECIDED`` (2) — nothing could be decided: no oracle, every result inconclusive, or an
  entirely pending/empty plan. Collapsing this into "clean" or "problem" is the dishonesty the
  milestone is built against, so it is its own code.

A missing tool is a request, not a skip
----------------------------------------
``Plan.unavailable`` becomes a printed, actionable permission request naming the missing tools in
the record's own order (``AGENT.md`` §3.5: "it does not silently skip"). ``check_capability``
already ordered them; the driver only prints them.

Harvested only, with zero egress
--------------------------------
M1 runs under EL-209's option (b): no outbound call without a ``Clearance``, and nothing issues one.
So the driver grades against **harvested** oracles (EL-205), never authored ones, and ``no_llm``
(the default) makes that a guarantee: the loop touches no network, which a test proves. Authoring
(EL-210) needs a clearance M1 does not have, so it is out of this driver's reach until M2.

Determinism
-----------
The ``run_id`` is derived from the artifacts' content hashes and the seed, so the same repository
and seed give the same id and the same ``summary.md`` bytes; a changed repository gives a new id,
so a new run never collides with an old one. Re-running on an unchanged artifact reuses the stored
verdict (EL-201's content-hash skip) and says it skipped, rather than grading it again.

M1 scope and limits
-------------------
The driver evaluates **top-level functions in flat modules**: the artifact is placed under its file
stem and graded against a harvested test that imports it by that stem (Gate 1's shape). A packaged
import path (``from pkg.mod import f``) is not reconstructed here — a stated limit, not a silent
skip. Methods, SQL and API artifacts, and authored oracles are out of M1's grading scope.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path, PurePosixPath

from evalloop._compat import StrEnum
from evalloop.classify import Abstention, classify_file
from evalloop.grade.execution import grade_execution
from evalloop.grade.oracles import Artifact, OracleKind, harvest
from evalloop.grade.verdict import Limits
from evalloop.memory.case import CaseResult, OracleConfidence, Verdict, content_hash
from evalloop.memory.evidence import SESSION_FACT_KEYS, assemble_evidence
from evalloop.memory.metric_store import MetricStore, Run
from evalloop.plan.planner import Plan, plan
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.registry.schema import TechniqueRecord
from evalloop.report.summary import Session, render_summary
from evalloop.vocab import Situation, Tool

__all__ = ["RunOutcome", "RunResult", "check"]

_SUMMARY_NAME = "summary.md"
# Tools M1 actually has. The LLM tools are absent by design (option (b)); the sandbox and a test
# runner are the real capabilities EL-206/EL-207 provide.
_M1_TOOLS: tuple[Tool, ...] = (Tool.sandbox, Tool.test_runner, Tool.repo_read, Tool.source_doc_read)
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "site-packages", "dist-packages", "build", "dist"})
_VENV_MARKER = "pyvenv.cfg"


class RunOutcome(StrEnum):
    """The three honest results. The value is the thing a developer reads; the code is the exit status."""

    clean = "clean"
    problem = "problem"
    undecided = "undecided"

    @property
    def exit_code(self) -> int:
        return {RunOutcome.clean: 0, RunOutcome.problem: 1, RunOutcome.undecided: 2}[self]


@dataclass(frozen=True, slots=True)
class RunResult:
    """What one ``check`` produced: where the report is, the outcome, and the accounting behind it."""

    run_id: str
    summary_path: Path
    outcome: RunOutcome
    cases: tuple[CaseResult, ...]
    graded_artifacts: tuple[str, ...]
    skipped: tuple[str, ...]
    permission_requests: tuple[str, ...]
    situations: tuple[tuple[Situation, float], ...]
    notes: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return self.outcome.exit_code


@dataclass
class _Accumulator:
    cases: list[CaseResult] = field(default_factory=list)
    graded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# -- discovering what to evaluate ---------------------------------------------------


def _candidate_files(root: Path) -> list[Path]:
    """The repository's own Python source files: not tests, not vendored, not virtualenvs."""
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        if _VENV_MARKER in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py") and not name.startswith("test_") and not name.endswith("_test.py"):
                found.append(Path(directory) / name)
    return found


def _top_level_functions(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")]


# -- the plan for one classified file -----------------------------------------------


def _evidence_for_planning(store: MetricStore, session_facts: Mapping[str, object]) -> Mapping[str, object]:
    """Evidence accumulated BEFORE this run. A first run has none, so evidence-gated checks are pending."""
    runs = store.runs()
    if not runs:
        return dict(session_facts)
    evidence = dict(assemble_evidence(store, runs[-1], {k: v for k, v in session_facts.items() if k in SESSION_FACT_KEYS}))
    return evidence


def _permission_request(plan_result: Plan) -> list[str]:
    """``Plan.unavailable`` as actionable lines, tools in the record's declared order (AGENT.md §3.5)."""
    lines: list[str] = []
    for record_id, tools in plan_result.unavailable.items():
        names = ", ".join(tool.value for tool in tools)
        lines.append(f"{record_id} needs: {names} — grant it, or this technique stays unavailable")
    return lines


# -- grading one artifact against its harvested oracles -----------------------------


def _ready_grader_ids(plan_result: Plan, records: Mapping[str, TechniqueRecord]) -> list[str]:
    return [r.id for r in plan_result.ready if records[r.id].ladder_priority == 1]


def _grade_one(
    *,
    artifact_rel: str,
    artifact_source: str,
    import_name: str,
    oracle_id: str,
    oracle_source: str,
    oracle_hash: str,
    run_id: str,
    prior: Run | None,
    limits: Limits,
    seed: int,
    workdir_root: str | None,
    acc: _Accumulator,
) -> None:
    artifact_hash = content_hash(artifact_source.encode("utf-8"))
    # Content-hash skip (EL-201): an unchanged artifact + oracle already judged conclusively is reused.
    if prior is not None:
        hit = prior.lookup(record_id="A1_execution_based", oracle_id=oracle_id, artifact_hash=artifact_hash, oracle_hash=oracle_hash)
        if hit is not None:
            acc.cases.append(hit.reused_in(run_id))
            acc.skipped.append(f"{artifact_rel} vs {oracle_id}: unchanged since run {hit.run_id}, reused (not re-graded)")
            return
    report = grade_execution(
        artifact_id=artifact_rel,
        artifact_source=artifact_source,
        import_name=import_name,
        oracle_id=oracle_id,
        oracle_source=oracle_source,
        oracle_confidence=OracleConfidence.high,
        oracle_hash=oracle_hash,
        run_id=run_id,
        sandbox_limits=limits,
        float_tolerance=1e-6,
        seed=seed,
        workdir_root=workdir_root,
    )
    acc.cases.extend(report.cases)
    acc.graded.append(f"{artifact_rel} vs {oracle_id}")


# -- the loop -----------------------------------------------------------------------


def _run_id(artifact_hashes: Sequence[str], seed: int) -> str:
    digest = content_hash(("|".join(sorted(artifact_hashes)) + f"|seed={seed}").encode("utf-8"))
    return f"run-{digest[:16]}"


def _outcome(acc: _Accumulator) -> tuple[RunOutcome, list[str]]:
    notes: list[str] = []
    conclusive = [c for c in acc.cases if c.verdict is not Verdict.inconclusive]
    failed = [c for c in acc.cases if c.verdict is Verdict.failed]
    if failed:
        return RunOutcome.problem, notes
    if conclusive:
        return RunOutcome.clean, notes
    if acc.cases:
        notes.append("every result was inconclusive: the evaluation, not the code, could not decide")
    else:
        notes.append("nothing could be graded: no applicable technique had a runnable oracle")
    return RunOutcome.undecided, notes


def check(
    path: str | os.PathLike[str],
    *,
    store_dir: str | os.PathLike[str],
    out_path: str | os.PathLike[str] | None = None,
    no_llm: bool = True,
    seed: int = 0,
    wall_seconds: float = 30.0,
    workdir_root: str | os.PathLike[str] | None = None,
) -> RunResult:
    """Run the whole M1 loop on ``path`` and write ``summary.md``. One shot; returns a :class:`RunResult`.

    ``store_dir`` is where the metric store lives (``USER_EXPERIENCE.md`` §6 has not chosen between
    the repo's ``.evalloop/`` and the user's home, so the caller passes it). ``no_llm`` is the
    default and the guarantee of zero egress. ``wall_seconds`` bounds each grading run (A1's
    ``timeout`` parameter once EL-015 lands; supplied here, never a literal in grader logic).
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"{root} does not exist")
    store_path = Path(store_dir)
    store_path.mkdir(parents=True, exist_ok=True)
    store = MetricStore(store_path)
    records = {r.id: r for r in load_records(RECORDS_DIR)}
    all_records = tuple(records.values())
    limits = Limits(wall_seconds=wall_seconds)
    workdir_str = os.fspath(workdir_root) if workdir_root is not None else None

    files = [root] if root.is_file() else _candidate_files(root)
    acc = _Accumulator()
    situations_seen: dict[Situation, float] = {}
    last_plan: Plan | None = None

    # The sandbox gives every grading run a fresh working directory, so the environment resets per run.
    session_facts: Mapping[str, object] = {"environment_resets_per_run": True}
    evidence = _evidence_for_planning(store, session_facts)
    prior = store.read_run(store.runs()[-1]) if store.runs() else None

    # First pass: hash the artifacts so the run id is deterministic from content + seed.
    sources: list[tuple[Path, str, str]] = []  # (file, relpath, source)
    for file in files:
        try:
            source = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = file.name if root.is_file() else file.relative_to(root).as_posix()
        sources.append((file, rel, source))
    run_id = _run_id([content_hash(src.encode("utf-8")) for _, _, src in sources], seed)
    # The run id is the repository's content plus the seed, so an unchanged repository produces the
    # same id. If that id is already stored, nothing changed: reuse every verdict and grade nothing
    # (AGENT.md §3.9's content-hash skip, at the whole-repo level). Classification and planning still
    # run, so the report is complete, but the sandbox is never entered.
    already_run = run_id in set(store.runs())

    for file, rel, source in sources:
        result = classify_file(file)
        if result.abstention is not None:
            acc.notes.append(f"{rel}: not classified ({result.abstention.value}) — {result.reason}")
            continue
        situations = tuple(s for s, _ in result.labels)
        for situation, conf in result.labels:
            situations_seen[situation] = max(situations_seen.get(situation, 0.0), conf)

        plan_result = plan(all_records, situations, _M1_TOOLS, evidence)
        last_plan = plan_result
        for line in _permission_request(plan_result):
            if line not in acc.permissions:
                acc.permissions.append(line)

        grader_ids = _ready_grader_ids(plan_result, records)
        if not grader_ids:
            acc.notes.append(f"{rel}: no execution grader is ready for {', '.join(s.value for s in situations)}")
            continue
        if already_run:
            continue  # the repo is unchanged; verdicts are reused below, nothing is graded

        import_name = PurePosixPath(rel).stem
        if not import_name.isidentifier():
            acc.notes.append(f"{rel}: module name is not importable, skipped")
            continue
        harvest_root = root if root.is_dir() else root.parent
        harvest_path = rel if root.is_dir() else file.name
        # Harvest per function (the harvester links a test to the symbol it references), then grade
        # each distinct test file once against the whole artifact file -- so a test file is not
        # re-run per function, and every case id is unique.
        oracle_files: dict[str, Path] = {}
        for func in _top_level_functions(source):
            found = harvest(harvest_root, Artifact(harvest_path, func))
            tests = found.of_kind(OracleKind.test)
            if not tests:
                acc.notes.append(f"{rel}::{func}: {found.reason or 'no test oracle'}")
                continue
            for oracle in tests:
                oracle_files.setdefault(oracle.provenance.path, harvest_root / oracle.provenance.path)
        for test_rel, oracle_abs in sorted(oracle_files.items()):
            try:
                oracle_source = oracle_abs.read_text(encoding="utf-8")
            except OSError:
                continue
            _grade_one(
                artifact_rel=rel, artifact_source=source, import_name=import_name,
                oracle_id=test_rel, oracle_source=oracle_source, oracle_hash=content_hash(oracle_source.encode("utf-8")),
                run_id=run_id, prior=prior, limits=limits, seed=seed, workdir_root=workdir_str, acc=acc,
            )

    if already_run:
        existing = store.read_run(run_id)
        acc.cases.extend(existing.cases)
        acc.skipped.append(
            f"repository unchanged since run {run_id}: reused all {len(existing.cases)} verdict(s), graded nothing"
        )
    elif acc.cases:
        store.write_run(run_id, acc.cases)

    outcome, outcome_notes = _outcome(acc)
    acc.notes.extend(outcome_notes)
    ordered_situations = tuple(sorted(situations_seen.items(), key=lambda kv: (-kv[1], kv[0].value)))
    summary_plan = last_plan if last_plan is not None else plan(all_records, (), _M1_TOOLS, evidence)
    session = Session(
        run_id=run_id,
        situations=ordered_situations,
        plan=summary_plan,
        cases=tuple(acc.cases),
        cost_usd=Decimal(0),
    )
    summary = render_summary(session)
    summary_path = Path(out_path) if out_path is not None else store_path / _SUMMARY_NAME
    summary_path.write_text(summary, encoding="utf-8")

    return RunResult(
        run_id=run_id,
        summary_path=summary_path,
        outcome=outcome,
        cases=tuple(acc.cases),
        graded_artifacts=tuple(acc.graded),
        skipped=tuple(acc.skipped),
        permission_requests=tuple(acc.permissions),
        situations=ordered_situations,
        notes=tuple(acc.notes),
    )
