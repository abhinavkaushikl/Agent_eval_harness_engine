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
The driver evaluates **top-level functions**. A flat module is placed under its file stem and graded
against a harvested test that imports it by that stem (Gate 1's shape). A module inside a package
(every directory up to the top one has an ``__init__.py``) is placed with its whole top-level package
and imported by its dotted path, so ``from pkg.mod import f`` resolves.

Multi-file code: the artifact, its package and its test(s) are read for ``import`` statements, and
every **local** module they name is placed beside it, transitively: a sibling ``helpers.py`` that
``pricing.py`` imports, another top-level package (``from util.money import tax``), a namespace
package, or a data-free helper module a test imports. Names are looked up next to the artifact
first, then at the repository root, the way running from the project would find them; anything
not in the repository (the standard library, installed packages) is left to the interpreter.
Test-side files (``tests/``, ``test_*.py``, ``*_test.py``, ``conftest.py``) are never placed beside the
artifact, so code under test still cannot read its tests. The closure is capped (``_CONTEXT_MAX_FILES``,
``_CONTEXT_MAX_BYTES``, engineering limits); past the cap, or for imports this does not reconstruct
(test-suite fixtures, repo data files), a test that cannot import comes back inconclusive with
pytest's reason, never a silent skip. Methods, SQL and API artifacts, and authored oracles are out of M1's grading scope.
"""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path, PurePosixPath

from evalloop._compat import StrEnum
from evalloop.classify import Abstention, classify_file
from evalloop.grade.execution import grade_execution
from evalloop.grade import project_env
from evalloop.grade.native import NativeRun, run_native
from evalloop.grade.specs import SPEC_SUFFIX, SpecError, SpecResult, grade_spec_file
from evalloop.capability.llm import Clearance
from evalloop.capability.router import Router
from evalloop.grade.oracles import Artifact, AuthoredOracle, OracleKind, author_test, harvest
from evalloop.grade.verdict import Limits
from evalloop.memory.case import CaseResult, OracleConfidence, Verdict, content_hash
from evalloop.memory.evidence import SESSION_FACT_KEYS, assemble_evidence
from evalloop.memory.metric_store import MetricStore, Run
from evalloop.capability import CapabilityBroker
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
    specs: tuple[tuple[str, SpecResult], ...] = ()
    cost_usd: Decimal = Decimal(0)
    #: The Python-function path's outcome without the specs, for a caller (the session) that grades
    #: the specs as cards of its own. ``None`` means no specs were folded in, so ``outcome`` is it.
    code_outcome: RunOutcome | None = None
    #: Third-party modules the code imports that the test interpreter does not have (so tests that
    #: need them cannot import). The session offers to install them (:mod:`evalloop.grade.project_env`).
    missing_packages: tuple[str, ...] = ()

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
    specs: list[tuple[str, SpecResult]] = field(default_factory=list)
    cost_usd: Decimal = Decimal(0)


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


@dataclass(frozen=True, slots=True)
class Author:
    """The grant that lets the driver WRITE a test when none exists: a router and a clearance.

    Both are supplied by the caller. This module never constructs a :class:`Clearance` (EL-209), so
    authoring — and the egress it implies — is always something the operator switched on.
    """

    router: Router
    clearance: Clearance
    max_output_tokens: int = 1200
    max_attempts: int = 2


def _author_one(
    *,
    artifact: Artifact,
    root: Path,
    rel: str,
    func: str,
    author: Author | None,
    limits: Limits,
    workdir_root: str | None,
    acc: _Accumulator,
) -> AuthoredOracle | None:
    """Author a test for one function, or explain in the notes why there is none. Never raises."""
    if author is None:
        return None
    try:
        outcome = author_test(
            artifact,
            root=root,
            router=author.router,
            clearance=author.clearance,
            sandbox_limits=limits,
            max_output_tokens=author.max_output_tokens,
            max_attempts=author.max_attempts,
            workdir_root=workdir_root,
        )
    except Exception as exc:  # a provider outage must not take the whole run down
        acc.notes.append(f"{rel}::{func}: authoring failed — {type(exc).__name__}: {exc}")
        return None
    acc.cost_usd += Decimal(outcome.total_cost_usd)  # a rejected attempt was still paid for
    if outcome.oracle is None:
        acc.notes.append(f"{rel}::{func}: {outcome.reason}")
        return None
    acc.notes.append(
        f"{rel}::{func}: authored a LOW test with {outcome.oracle.served_model} "
        f"(cost ${outcome.total_cost_usd})"
    )
    return outcome.oracle


@dataclass(frozen=True, slots=True)
class _Package:
    """A packaged artifact's sandbox context: its dotted import path and its top package's files."""

    import_name: str
    files: Mapping[str, str]


def _package_context(root: Path, file: Path, source: str) -> _Package | None:
    """The package ``file`` sits in, read from disk, or None for a flat module.

    The top package is the highest directory, still inside ``root``, that every directory down to the
    file marks with ``__init__.py``. Its text files go in at paths relative to its parent, with the
    artifact's current ``source``; caches, hidden files and non-UTF-8 files stay out.
    """
    top: Path | None = None
    current = file.parent
    while current != root.parent and (current / "__init__.py").is_file() and root in (current, *current.parents):
        top = current
        current = current.parent
    if top is None:
        return None
    base = top.parent
    parts = list(file.relative_to(base).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not all(part.isidentifier() for part in parts):
        return None
    files: dict[str, str] = {}
    for path in sorted(top.rglob("*")):
        rel = path.relative_to(base)
        if not path.is_file() or any(part == "__pycache__" or part.startswith(".") for part in rel.parts):
            continue
        try:
            files[rel.as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    files[file.relative_to(base).as_posix()] = source
    return _Package(".".join(parts), files)


_CONTEXT_MAX_FILES = 400
_CONTEXT_MAX_BYTES = 4_000_000
_UNPLACED_DIRS = frozenset({"__pycache__", "node_modules", "site-packages", "dist-packages", "tests", "test"})


def _is_test_side(rel: PurePosixPath) -> bool:
    """A test-suite file, which must never sit beside the code under test (hidden-test isolation)."""
    name = rel.name
    return (
        any(part in ("tests", "test") for part in rel.parts[:-1])
        or name == "conftest.py"
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
    )


def _local_imports(text: str) -> set[str]:
    """The top-level names a module imports absolutely (``import a.b`` and ``from a.b import c`` give ``a``)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _local_module(name: str, search: Sequence[Path]) -> dict[str, str] | None:
    """The repository files that make up the importable ``name`` (a module or a package), or None."""
    if name in _UNPLACED_DIRS or not name.isidentifier():
        return None
    for directory in search:
        module = directory / f"{name}.py"
        if module.is_file() and not module.is_symlink() and not _is_test_side(PurePosixPath(module.name)):
            try:
                return {f"{name}.py": module.read_text(encoding="utf-8")}
            except (OSError, UnicodeDecodeError):
                return None
        package = directory / name
        if package.is_dir() and not package.is_symlink() and not (package / "pyvenv.cfg").exists():
            files: dict[str, str] = {}
            for path in sorted(package.rglob("*")):
                rel = PurePosixPath(name, *path.relative_to(package).parts)
                if (not path.is_file() or path.is_symlink() or _is_test_side(rel)
                        or any(part in _UNPLACED_DIRS or part.startswith(".") for part in rel.parts)):
                    continue
                try:
                    files[rel.as_posix()] = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
            if any(rel.endswith(".py") for rel in files):
                return files
    return None


def _sandbox_context(root: Path, file: Path, source: str, oracle_sources: Sequence[str]) -> _Package | None:
    """Everything the artifact needs beside it in the sandbox: its package (if any) plus the local
    modules that it, its package and its tests import, transitively. None for a flat module that
    imports nothing local (the artifact alone is placed, as before)."""
    package = _package_context(root, file, source)
    if package is not None:
        parts = package.import_name.split(".")
        base = file.parents[len(parts) - (0 if file.name == "__init__.py" else 1)]
        files, import_name = dict(package.files), package.import_name
    else:
        base = file.parent
        files, import_name = {f"{file.stem}.py": source}, file.stem
    search = [base] if base == root else [base, root]
    seen = {import_name.split(".")[0]}
    queue = [source, *oracle_sources, *files.values()]
    total = sum(len(text) for text in files.values())
    added = False
    while queue:
        for name in sorted(_local_imports(queue.pop()) - seen):
            seen.add(name)
            found = _local_module(name, search)
            if found is None:
                continue
            for rel, text in found.items():
                if rel in files or len(files) >= _CONTEXT_MAX_FILES or total + len(text) > _CONTEXT_MAX_BYTES:
                    continue
                files[rel] = text
                total += len(text)
                added = True
                if rel.endswith(".py"):
                    queue.append(text)
    if not added:
        return package
    return _Package(import_name, files)


def _oracle_hash(oracle_source: str, package: _Package | None, env_tag: str = "") -> str:
    """The oracle's hash, widened to the package it runs against and the interpreter it runs with:
    editing a sibling module, or installing what the tests lacked, must re-grade, not reuse, a
    verdict (EL-201's content-hash skip). ``env_tag`` is empty for EvalLoop's own, complete Python,
    so those hashes are exactly what they were before interpreters were chosen."""
    if package is None and not env_tag:
        return content_hash(oracle_source.encode("utf-8"))
    parts = [oracle_source]
    if package is not None:
        parts.append("\n".join(f"{rel}:{content_hash(text.encode('utf-8'))}" for rel, text in sorted(package.files.items())))
    if env_tag:
        parts.append(f"env:{env_tag}")
    return content_hash("\n".join(parts).encode("utf-8"))


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
    confidence: OracleConfidence = OracleConfidence.high,
    limits: Limits,
    seed: int,
    workdir_root: str | None,
    acc: _Accumulator,
    package: _Package | None = None,
    python: str | None = None,
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
        oracle_confidence=confidence,
        oracle_hash=oracle_hash,
        run_id=run_id,
        sandbox_limits=limits,
        float_tolerance=1e-6,
        seed=seed,
        workdir_root=workdir_root,
        package_files=package.files if package is not None else None,
        python=python,
    )
    # Two oracles for one artifact can share a test name (two functions' authored tests, or two test
    # files), and the store keeps one case per id. On a clash the id names the oracle too, which is unique.
    taken = {c.case_id for c in acc.cases}
    for case in report.cases:
        acc.cases.append(replace(case, case_id=f"{artifact_rel}::{case.oracle_id}") if case.case_id in taken else case)
    acc.graded.append(f"{artifact_rel} vs {oracle_id}")


# -- the loop -----------------------------------------------------------------------


def _second_opinion(
    acc: _Accumulator,
    first: int,
    *,
    artifact: Artifact,
    root: Path,
    rel: str,
    func: str,
    source: str,
    import_name: str,
    author: Author | None,
    run_id: str,
    limits: Limits,
    seed: int,
    workdir_root: str | None,
    package: _Package | None = None,
    python: str | None = None,
    env_tag: str = "",
) -> None:
    """Corroborate a generated test's failure with a second, independently written test.

    A generated test sees only the signature, so when it fails, either the code is wrong or the test
    expected something the spec never said. The corpus's answer to one grader's unchecked verdict is
    a second, independent one (A:211, "two qualified experts independently grade ... a third resolves
    their disagreements"). So a fresh test is written from the same isolated view and run. If it fails
    too, the failure stands. If it passes everything, the two tests disagree about the code, and
    the first test's failures are withheld as inconclusive, never turned into passes. The second test
    only adjudicates: its cases are not added, so the two tests' case ids never collide.
    """
    failed = [i for i in range(first, len(acc.cases)) if acc.cases[i].verdict is Verdict.failed and acc.cases[i].reused_from is None]
    if not failed or author is None:
        return
    second = _author_one(
        artifact=artifact, root=root, rel=rel, func=func, author=author, limits=limits,
        workdir_root=workdir_root, acc=acc,
    )
    if second is None:
        acc.notes.append(f"{rel}::{func}: no second test could be written, so the generated test's failure is uncorroborated")
        return
    scratch = _Accumulator()
    _grade_one(
        artifact_rel=rel, artifact_source=source,
        import_name=package.import_name if package is not None else import_name, oracle_id=second.oracle_id,
        oracle_source=second.test_code, oracle_hash=_oracle_hash(second.test_code, package, env_tag),
        run_id=run_id, prior=None, confidence=second.confidence, limits=limits, seed=seed,
        workdir_root=workdir_root, acc=scratch, package=package, python=python,
    )
    passed = sum(1 for c in scratch.cases if c.verdict is Verdict.passed)
    if any(c.verdict is Verdict.failed for c in scratch.cases) or passed == 0:
        acc.notes.append(f"{rel}::{func}: a second, independent generated test also failed or could not decide; the failure stands")
        return
    reason = (
        f"a generated test failed, but a second test written independently from the same signature passed "
        f"all {passed} of its checks: the two disagree, so this may be the test's mistake, not the code's"
    )
    for i in failed:
        acc.cases[i] = replace(
            acc.cases[i], verdict=Verdict.inconclusive, failure_class=None, timeout=None, inconclusive_reason=reason
        )
    acc.notes.append(f"{rel}::{func}: {len(failed)} generated failure(s) withheld: an independent second test disagreed")


def _calibrated(case: CaseResult, native: NativeRun) -> CaseResult:
    """A sandbox failure whose test passes in the repo's own environment is the sandbox's, not the code's."""
    if case.verdict is not Verdict.failed or native.outcome_of(case.oracle_id) != "passed":
        return case
    return replace(
        case,
        verdict=Verdict.inconclusive,
        failure_class=None,
        timeout=None,
        inconclusive_reason=(
            "fails in the sandbox but passes in the repo's own environment (native pytest), so the sandbox "
            "lacks something this test needs; not charged to the code"
        ),
    )


def _grade_specs(root: Path, acc: _Accumulator) -> None:
    """Grade every ``*.eval.json`` under ``root``; a spec that cannot run is a note, never a skip."""
    for spec_path in sorted(root.rglob(f"*{SPEC_SUFFIX}")):
        rel = spec_path.relative_to(root).as_posix()
        if any(part.startswith(".") for part in PurePosixPath(rel).parts):
            continue
        try:
            acc.specs.append((rel, grade_spec_file(spec_path)))
        except SpecError as exc:
            acc.notes.append(f"{rel}: spec not graded — {exc}")
        except Exception as exc:  # a broken spec must not take the code path's verdicts down with it
            acc.notes.append(f"{rel}: spec not graded — {type(exc).__name__}: {exc}")


def _run_id(artifact_hashes: Sequence[str], seed: int) -> str:
    digest = content_hash(("|".join(sorted(artifact_hashes)) + f"|seed={seed}").encode("utf-8"))
    return f"run-{digest[:16]}"


def _outcome(acc: _Accumulator, *, with_specs: bool = True) -> tuple[RunOutcome, list[str]]:
    notes: list[str] = []
    conclusive = [c for c in acc.cases if c.verdict is not Verdict.inconclusive]
    failed = [c for c in acc.cases if c.verdict is Verdict.failed]
    spec_outcomes = {spec.outcome for _, spec in acc.specs} if with_specs else set()
    if failed or "problem" in spec_outcomes:
        return RunOutcome.problem, notes
    if conclusive or "clean" in spec_outcomes:
        return RunOutcome.clean, notes
    if acc.specs and with_specs:
        notes.append("every spec check was inconclusive: the fixtures, not the code, could not decide")
    elif acc.cases:
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
    author: Author | None = None,
    specs: bool = True,
    calibrate_native: bool = False,
    native_seconds: float = 300.0,
    install: bool = False,
) -> RunResult:
    """Run the whole M1 loop on ``path`` and write ``summary.md``. One shot; returns a :class:`RunResult`.

    ``store_dir`` is where the metric store lives (``USER_EXPERIENCE.md`` §6 has not chosen between
    the repo's ``.evalloop/`` and the user's home, so the caller passes it). ``no_llm`` is the
    default and the guarantee of zero egress. ``wall_seconds`` bounds each grading run (A1's
    ``timeout`` parameter once EL-015 lands; supplied here, never a literal in grader logic).
    ``specs`` also grades every ``*.eval.json`` (SQL / RAG / agent) under ``path`` into the report.
    ``calibrate_native`` runs the repo's own pytest once, unsandboxed, and withholds the verdict on any
    sandbox failure that passes there (:mod:`evalloop.grade.native`); ``native_seconds`` bounds it.
    Tests run with the project's own environment when it has one, else with an environment EvalLoop
    builds for it when ``install`` allows (operator clearance: it downloads from PyPI), else with
    EvalLoop's own Python (:mod:`evalloop.grade.project_env`).
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
    # The interpreter the tests run with: the project's own environment, the one EvalLoop builds for
    # it (when allowed), or EvalLoop's own. Its identity joins the run id and the oracle hashes only
    # when it is not EvalLoop's complete own Python, so installing what was missing re-grades.
    project = root if root.is_dir() else root.parent
    interp = (project_env.choose(project, allow_install=install)
              if any(rel.endswith(".py") for _, rel, _ in sources) else None)
    python = interp.python if interp is not None else None
    env_tag = "" if interp is None or (interp.python == sys.executable and not interp.missing) else (
        f"{interp.python}|missing={','.join(interp.missing)}")
    if interp is not None and interp.python != sys.executable:
        acc.notes.append(f"tests run with {interp.origin}: {interp.python}")
    if interp is not None and interp.failed:
        acc.notes.append(f"could not install: {', '.join(interp.failed)}")
    if interp is not None and interp.missing:
        acc.notes.append(f"needs packages: {', '.join(interp.missing)}")
    hashes = [content_hash(src.encode("utf-8")) for _, _, src in sources]
    run_id = _run_id(hashes + ([content_hash(env_tag.encode("utf-8"))] if env_tag else []), seed)
    # The run id is the repository's content plus the seed, so an unchanged repository produces the
    # same id. If that id is already stored, nothing changed: reuse every verdict and grade nothing
    # (AGENT.md §3.9's content-hash skip, at the whole-repo level). Classification and planning still
    # run, so the report is complete, but the sandbox is never entered.
    already_run = run_id in set(store.runs())

    # The capability broker owns what is granted; the planner's available tools come from it, not a
    # private list. In M1 the real capabilities are the local sandbox and test runner (plus reading
    # the repo and its docs); the LLM tools are deliberately not granted (option (b)).
    broker = CapabilityBroker()
    for tool in _M1_TOOLS:
        broker.grant(tool, granted_by="evalloop (M1 defaults)", reason="M1 runs a sandbox and a test runner locally")
    granted_tools = tuple(sorted(broker.available_tools(), key=lambda t: t.value))

    for file, rel, source in sources:
        result = classify_file(file)
        if result.abstention is not None:
            acc.notes.append(f"{rel}: not classified ({result.abstention.value}) — {result.reason}")
            continue
        situations = tuple(s for s, _ in result.labels)
        for situation, conf in result.labels:
            situations_seen[situation] = max(situations_seen.get(situation, 0.0), conf)

        plan_result = plan(all_records, situations, granted_tools, evidence)
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
                # Nothing to grade against. With an author granted (a router AND a clearance, both
                # supplied by the caller — this module never issues one), write a LOW test from the
                # signature alone and grade that. Without one, say so; never invent a verdict.
                authored = _author_one(
                    artifact=Artifact(harvest_path, func), root=harvest_root, rel=rel, func=func,
                    author=author, limits=limits, workdir_root=workdir_str, acc=acc,
                )
                if authored is not None:
                    first = len(acc.cases)
                    context = _sandbox_context(root, file, source, [authored.test_code]) if root.is_dir() else None
                    _grade_one(
                        artifact_rel=rel, artifact_source=source,
                        import_name=context.import_name if context is not None else import_name,
                        oracle_id=authored.oracle_id, oracle_source=authored.test_code,
                        oracle_hash=_oracle_hash(authored.test_code, context, env_tag),
                        run_id=run_id, prior=prior, confidence=authored.confidence,
                        limits=limits, seed=seed,
                        workdir_root=workdir_str, acc=acc, package=context, python=python,
                    )
                    _second_opinion(
                        acc, first, artifact=Artifact(harvest_path, func), root=harvest_root, rel=rel,
                        func=func, source=source, import_name=import_name, author=author, run_id=run_id,
                        limits=limits, seed=seed, workdir_root=workdir_str, package=context,
                        python=python, env_tag=env_tag,
                    )
                    continue
                acc.notes.append(f"{rel}::{func}: {found.reason or 'no test oracle'}")
                continue
            for oracle in tests:
                oracle_files.setdefault(oracle.provenance.path, harvest_root / oracle.provenance.path)
        oracle_texts: dict[str, str] = {}
        for test_rel, oracle_abs in sorted(oracle_files.items()):
            try:
                oracle_texts[test_rel] = oracle_abs.read_text(encoding="utf-8")
            except OSError:
                continue
        package = (
            _sandbox_context(root, file, source, list(oracle_texts.values())) if root.is_dir() and oracle_texts else None
        )
        for test_rel, oracle_source in oracle_texts.items():
            _grade_one(
                artifact_rel=rel, artifact_source=source,
                import_name=package.import_name if package is not None else import_name,
                oracle_id=test_rel, oracle_source=oracle_source, oracle_hash=_oracle_hash(oracle_source, package, env_tag),
                run_id=run_id, prior=prior, limits=limits, seed=seed, workdir_root=workdir_str, acc=acc,
                package=package, python=python,
            )

    if specs and root.is_dir():
        _grade_specs(root, acc)

    if already_run:
        existing = store.read_run(run_id)
        acc.cases.extend(existing.cases)
        acc.skipped.append(
            f"repository unchanged since run {run_id}: reused all {len(existing.cases)} verdict(s), graded nothing"
        )
    elif acc.cases:
        if calibrate_native and root.is_dir() and any(c.verdict is Verdict.failed for c in acc.cases):
            native = run_native(root, timeout_seconds=native_seconds, python=python)
            acc.notes.append(native.note)
            acc.cases[:] = [_calibrated(c, native) for c in acc.cases]
        store.write_run(run_id, acc.cases)

    outcome, outcome_notes = _outcome(acc)
    acc.notes.extend(outcome_notes)
    ordered_situations = tuple(sorted(situations_seen.items(), key=lambda kv: (-kv[1], kv[0].value)))
    summary_plan = last_plan if last_plan is not None else plan(all_records, (), granted_tools, evidence)
    session = Session(
        run_id=run_id,
        situations=ordered_situations,
        plan=summary_plan,
        cases=tuple(acc.cases),
        cost_usd=acc.cost_usd,
        specs=tuple(acc.specs),
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
        specs=tuple(acc.specs),
        cost_usd=acc.cost_usd,
        code_outcome=_outcome(acc, with_specs=False)[0] if acc.specs else None,
        missing_packages=interp.missing if interp is not None else (),
    )
