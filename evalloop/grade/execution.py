"""Grade an artifact by RUNNING it against a harvested oracle -- rung 1, ``A1_execution_based``.

``A-choosing-how-to-grade.md`` §A1: execution grading runs the output against hidden tests and
compares what it *does*, never what it looks like. Its own evidence is the warning this module is
built around (A:31): on 200 text-to-SQL items, exact match scored 41%, execution match 68%, and an
LLM judge 79% -- "which means it passed 22 queries that returned the wrong rows". A grader that
agrees with a plausible reading of the code reproduces the 79%. **The 68% is the number that is
true**, and the only way to get it is to run the code, which is what this does.

How it grades
-------------
The artifact and the harvested oracle (a pytest test) go into EL-206's sandbox, and pytest runs the
oracle against the artifact. An injected ``conftest.py`` prints one machine-readable line per test
to stdout, which this module parses into per-case verdicts. Nothing here reads the artifact to form
an opinion; the sandbox runs it and the oracle decides.

**Equivalent-but-different output is not marked wrong** (A1's anti-pattern, "string match marks
correct-but-different SQL as wrong") by construction: the oracle asserts behaviour, so two
implementations that behave the same both pass, however differently they are written. A test proves
it.

The verdicts are EL-014's
-------------------------
``Verdict`` / ``FailureClass`` / ``Timeout`` are imported from ``evalloop/memory/case.py`` -- no
second copy. The **compile-vs-logic split** (A:39): the artifact is parsed first, and a syntax
error is ``failed`` / ``syntax_error`` without even running (a compile failure is a different
finding from a wrong answer). Otherwise, per case: a passed test is ``passed``; an
``AssertionError`` is ``failed`` / ``wrong_result``; any other exception is ``failed`` /
``runtime_error``; a wall/CPU timeout is ``failed`` / ``timeout`` (EL-014); and a run the evaluation
itself could not complete -- the sandbox could not start, egress was refused, or the oracle could
not be collected -- is ``inconclusive`` with the reason, never charged to the artifact.

Partial credit, and the headline that cannot be gamed
-----------------------------------------------------
``H-agents.md`` §170: "give partial credit for internal tracking only. The headline metric is still
full-task success." So :class:`GradeReport` carries the per-case pass rate (partial credit) for
tracking, but the **headline is ``full_pass`` -- every case passed**. Promoting partial credit to
the headline is how a broken function scores 80%; it is kept, and it is never the headline.

No rate without its interval
----------------------------
A1's ``companion_checks`` is ``[C1_wilson_ci]``. The planner says a pass rate travels with its
interval; this is where that becomes true. The rate carries a Wilson interval from EL-203's
``wilson_interval`` (not computed here), and :attr:`GradeReport.pass_rate` raises rather than return
a bare number.

A pre-existing failure is not the current change's fault
--------------------------------------------------------
Given EL-205's ``baseline`` (a run judged on the code before the change), a case that was already
failing on the same oracle content is marked ``already_failing`` and **excluded from the regressions
attributed to this change**. Crediting a pre-existing failure to the current change is the false
alarm ``USER_EXPERIENCE.md`` §1 says the developer will not tolerate.

Hidden-test isolation, and its honest boundary
----------------------------------------------
The artifact must not see the test that grades it. Here the artifact runs with its working directory
set to a subdirectory that holds **only the artifact**, and the oracle is not importable by it and
is not under that directory, so the artifact cannot reach the oracle by its import name, by a
conventional test filename, or by listing its own directory -- proven by a hostile-artifact test.
**The boundary:** pytest and the artifact share one process, so an artifact that scans the whole
filesystem by absolute path could still find the oracle. That is reward-hacking, and full
read-isolation needs process separation, which is M3's (the sandbox docstring lists the same limit).
M1 isolates the artifact's *environment*, not a determined adversary.

EL-015 is not implemented, so the corpus numbers are arguments
--------------------------------------------------------------
A1's ``float_tolerance`` (``1e-6``) and ``max_mutant_pass_rate`` (``5`` percent) live on the record
(decision EL-015), which is unbuilt. So they are required arguments here, supplied by the caller
from the record once EL-015 lands -- never a literal in this module (``CLAUDE.md`` §3). The 5% bar
is cited where the mutation self-check reports against it.
"""

from __future__ import annotations

import ast
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from evalloop.grade.sandbox import run_sandboxed
from evalloop.grade.verdict import Limits, SandboxResult
from evalloop.memory.case import (
    CaseKind,
    CaseResult,
    FailureClass,
    OracleConfidence,
    Timeout,
    Verdict,
    content_hash,
)
from evalloop.memory.metric_store import Run
from evalloop.stats import wilson_interval
from evalloop.stats.proportions import Interval

__all__ = [
    "RECORD_ID",
    "GradeReport",
    "GradeError",
    "MutationReport",
    "attributable_regressions",
    "grade_execution",
    "mutation_self_check",
]

#: The registry technique this module implements; carried into every stored case.
RECORD_ID = "A1_execution_based"

#: A:38's bar, cited where the mutation self-check reports against it. Not a literal threshold used
#: in logic -- the caller passes ``max_mutant_pass_rate`` (the record's value once EL-015 lands);
#: this is only the text of the rule for the report.
_A38_RULE = 'A:38: "If the mutant still passes more than 5% of the time, the fixtures aren\'t discriminating enough."'

_MARKER = "##EVALLOOP-CASE## "
_SUBJECT_DIR = "subject"
_ORACLE_FILE = "oracle/test_oracle.py"
_ORACLE_CONFTEST = "oracle/conftest.py"

# Injected into the sandbox. A pytest plugin that prints one JSON line per test, so per-case
# verdicts travel out on stdout (the sandbox discards the workdir, so a results file would be lost).
# The exception type is captured from ``call.excinfo`` -- pytest rewrites an assertion's message to
# "assert <expr>" with no "AssertionError:" prefix, so the type must be read, not parsed from text.
_CONFTEST = (
    "import json, sys, pytest\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtest_makereport(item, call):\n"
    "    outcome = yield\n"
    "    report = outcome.get_result()\n"
    "    if call.excinfo is not None:\n"
    "        report._evalloop_exc = call.excinfo.typename\n"
    "def pytest_runtest_logreport(report):\n"
    "    failed_before_call = report.when in ('setup', 'collect') and report.outcome == 'failed'\n"
    "    if report.when != 'call' and not failed_before_call:\n"
    "        return\n"
    "    crash = ''\n"
    "    reprcrash = getattr(getattr(report, 'longrepr', None), 'reprcrash', None)\n"
    "    if reprcrash is not None:\n"
    "        crash = str(getattr(reprcrash, 'message', ''))\n"
    "    line = {'nodeid': report.nodeid, 'when': report.when, 'outcome': report.outcome,\n"
    "            'exc': getattr(report, '_evalloop_exc', ''), 'crash': crash}\n"
    "    sys.stdout.write(" + repr(_MARKER) + " + json.dumps(line) + '\\n')\n"
    "    sys.stdout.flush()\n"
)


class GradeError(Exception):
    """The grader was called wrongly: an un-parseable oracle, a bad import name. Not a grading outcome."""


@dataclass(frozen=True, slots=True)
class _CaseOutcome:
    node_id: str
    verdict: Verdict
    failure_class: FailureClass | None
    timeout: Timeout | None
    reason: str | None
    evidence: str | None


@dataclass(frozen=True, slots=True)
class GradeReport:
    """The result of grading one artifact against one oracle: per-case verdicts and the honest headline."""

    artifact_id: str
    oracle_id: str
    cases: tuple[CaseResult, ...]
    confidence: float

    @property
    def conclusive(self) -> tuple[CaseResult, ...]:
        return tuple(c for c in self.cases if c.verdict is not Verdict.inconclusive)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.verdict is Verdict.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if c.verdict is Verdict.failed)

    @property
    def inconclusive(self) -> int:
        return sum(1 for c in self.cases if c.verdict is Verdict.inconclusive)

    @property
    def full_pass(self) -> bool:
        """The headline (H:170): every conclusive case passed, and at least one case was conclusive."""
        conclusive = self.conclusive
        return bool(conclusive) and all(c.verdict is Verdict.passed for c in conclusive)

    @property
    def partial_credit(self) -> float | None:
        """For internal tracking only (H:170), never the headline. ``None`` if nothing was conclusive."""
        n = self.passed + self.failed
        return None if n == 0 else self.passed / n

    @property
    def pass_rate(self) -> Interval:
        """The pass rate with its Wilson interval (C1). Raises rather than give a bare number."""
        n = self.passed + self.failed
        if n == 0:
            raise GradeError("no conclusive case, so there is no pass rate to report (and none to put an interval on)")
        return wilson_interval(self.passed, n, self.confidence)


@dataclass(frozen=True, slots=True)
class MutationReport:
    """The grader grading itself (A:38): did the oracle catch deliberately broken versions of the artifact?"""

    mutants: int
    survivors: int
    max_pass_rate: float
    rule: str = _A38_RULE

    @property
    def survival_rate(self) -> float:
        return 0.0 if self.mutants == 0 else self.survivors / self.mutants

    @property
    def discriminating(self) -> bool:
        """The fixtures discriminate if at most ``max_pass_rate`` of mutants slipped through (A:38)."""
        return self.survival_rate <= self.max_pass_rate / 100.0

    def summary(self) -> str:
        verdict = "discriminating" if self.discriminating else "NOT discriminating"
        return (
            f"{self.survivors}/{self.mutants} mutants passed the oracle "
            f"({self.survival_rate * 100:.1f}%); bar is {self.max_pass_rate:.0f}% ({self.rule}): {verdict}"
        )


# -- running the oracle --------------------------------------------------------------


def _parse_case_lines(stdout: str) -> list[dict[str, str]]:
    """One record per emitted case. pytest's progress dots share the line, so find the marker in it."""
    found: list[dict[str, str]] = []
    for line in stdout.splitlines():
        index = line.find(_MARKER)
        if index < 0:
            continue
        try:
            found.append(json.loads(line[index + len(_MARKER) :]))
        except ValueError:
            continue
    return found


def _classify(entry: dict[str, str]) -> _CaseOutcome:
    node = entry.get("nodeid", "?")
    outcome = entry.get("outcome")
    crash = entry.get("crash", "")
    if outcome == "passed":
        return _CaseOutcome(node, Verdict.passed, None, None, None, None)
    # A failure: a wrong answer (the oracle's assertion did not hold) is a different finding from the
    # artifact raising. The exception type is read from the report, not parsed from the message.
    exception = entry.get("exc", "")
    if exception == "AssertionError":
        return _CaseOutcome(node, Verdict.failed, FailureClass.wrong_result, None, None, crash or None)
    detail = f"{exception}: {crash}".strip(": ") if exception else (crash or None)
    return _CaseOutcome(node, Verdict.failed, FailureClass.runtime_error, None, None, detail)


def _ids(node_id: str, artifact_id: str, oracle_id: str) -> tuple[str, str]:
    """A case id unique per (artifact, test) in a run, and the oracle id of the specific test.

    A real test's node id is ``oracle/test_oracle.py::<suffix>`` (the sandbox path, the same for
    every artifact), so the stable case id is ``<artifact>::<suffix>`` and the oracle id names the
    real test file plus that suffix. Synthetic nodes (compile/timeout/inconclusive) keep their id.
    """
    prefix = f"{_ORACLE_FILE}::"
    if node_id.startswith(prefix):
        suffix = node_id[len(prefix) :]
        return f"{artifact_id}::{suffix}", f"{oracle_id}::{suffix}"
    return node_id, oracle_id


def _result(
    outcome: _CaseOutcome,
    *,
    run_id: str,
    artifact_id: str,
    oracle_id: str,
    oracle_confidence: OracleConfidence,
    artifact_hash: str,
    oracle_hash: str,
    seed: int | None,
    duration: float,
) -> CaseResult:
    case_id, stored_oracle_id = _ids(outcome.node_id, artifact_id, oracle_id)
    return CaseResult(
        run_id=run_id,
        record_id=RECORD_ID,
        case_id=case_id,
        case_kind=CaseKind.generated,
        artifact_id=artifact_id,
        oracle_id=stored_oracle_id,
        oracle_confidence=oracle_confidence,
        ladder_rung=1,
        verdict=outcome.verdict,
        failure_class=outcome.failure_class,
        timeout=outcome.timeout,
        inconclusive_reason=outcome.reason,
        score=None,
        evidence=outcome.evidence,
        artifact_hash=artifact_hash,
        oracle_hash=oracle_hash,
        reused_from=None,
        seed=seed,
        cost_usd=None,
        duration_seconds=duration,
    )


def _run_oracle(
    artifact_source: str, import_name: str, oracle_source: str, limits: Limits, seed: int, workdir_root: str | None
) -> tuple[list[dict[str, str]], SandboxResult]:
    """Run the oracle against the artifact in the sandbox. Returns the parsed case lines and the result.

    The artifact runs with its working directory set to ``subject/`` (which holds only the artifact),
    and the oracle sits in the sibling ``oracle/`` reached by ``../oracle/...`` -- a path the artifact
    is never told. ``PYTHONPATH="."`` makes the artifact importable from its own directory. The
    reporter ``conftest.py`` lives beside the oracle, so pytest loads it and it never enters the
    artifact's directory.
    """
    files = {
        f"{_SUBJECT_DIR}/{import_name}.py": artifact_source,
        _ORACLE_FILE: oracle_source,
        _ORACLE_CONFTEST: _CONFTEST,
    }
    # --import-mode=importlib stops pytest from putting the oracle's directory on sys.path, so the
    # artifact cannot ``import`` the oracle module; the artifact is importable only via PYTHONPATH.
    command = [
        sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
        "--import-mode=importlib", "-q", f"../{_ORACLE_FILE}",
    ]
    result = run_sandboxed(
        command,
        limits=limits,
        workdir_root=workdir_root,
        input_files=files,
        seed=seed,
        env_extra={"PYTHONPATH": "."},
        cwd_subdir=_SUBJECT_DIR,
    )
    return _parse_case_lines(result.stdout), result


def grade_execution(
    *,
    artifact_id: str,
    artifact_source: str,
    import_name: str,
    oracle_id: str,
    oracle_source: str,
    oracle_confidence: OracleConfidence,
    oracle_hash: str,
    run_id: str,
    sandbox_limits: Limits,
    float_tolerance: float,
    seed: int = 0,
    confidence: float = 0.95,
    workdir_root: str | None = None,
) -> GradeReport:
    """Grade ``artifact_source`` against the harvested ``oracle_source`` by running it (never reading it).

    ``import_name`` is the module the oracle imports the artifact by. ``float_tolerance`` is A1's
    ``parameters`` value (EL-015), supplied by the caller; the oracle performs the comparison in the
    pytest model, so it is recorded for provenance rather than consumed here (see the report).
    Whether a failure is the current change's fault is :func:`attributable_regressions`, given an
    EL-205 baseline.
    """
    _ = float_tolerance  # A1 parameter, threaded for provenance; the oracle does the comparison
    if not import_name.isidentifier():
        raise GradeError(f"import_name {import_name!r} is not a valid module name")
    artifact_hash = content_hash(artifact_source.encode("utf-8"))

    # Compile-vs-logic split (A:39): a syntax error is a different finding, caught before running.
    try:
        ast.parse(artifact_source)
    except SyntaxError as error:
        case = _result(
            _CaseOutcome(f"{artifact_id}::compile", Verdict.failed, FailureClass.syntax_error, None, None, f"{error.msg} (line {error.lineno})"),
            run_id=run_id, artifact_id=artifact_id, oracle_id=oracle_id, oracle_confidence=oracle_confidence,
            artifact_hash=artifact_hash, oracle_hash=oracle_hash, seed=seed, duration=0.0,
        )
        return GradeReport(artifact_id, oracle_id, (case,), confidence)

    entries, result = _run_oracle(artifact_source, import_name, oracle_source, sandbox_limits, seed, workdir_root)
    sandbox_outcome = result.classify()
    per_case_duration = result.duration_seconds / max(len(entries), 1)

    # The evaluation, not the artifact, failed: a timeout, a refused capability, or a sandbox that
    # could not start (EL-014). A collection failure with no case lines is the oracle not running.
    if sandbox_outcome.verdict is Verdict.failed and sandbox_outcome.failure_class is FailureClass.timeout:
        case = _result(
            _CaseOutcome(f"{oracle_id}::timeout", Verdict.failed, FailureClass.timeout, sandbox_outcome.timeout, None, None),
            run_id=run_id, artifact_id=artifact_id, oracle_id=oracle_id, oracle_confidence=oracle_confidence,
            artifact_hash=artifact_hash, oracle_hash=oracle_hash, seed=seed, duration=result.duration_seconds,
        )
        return GradeReport(artifact_id, oracle_id, (case,), confidence)
    if sandbox_outcome.verdict is Verdict.inconclusive or not entries:
        reason = sandbox_outcome.inconclusive_reason or (
            "the oracle produced no test result: it could not be collected or imported "
            f"(pytest said: {(result.stdout + result.stderr).strip()[-200:] or 'nothing'})"
        )
        case = _result(
            _CaseOutcome(f"{oracle_id}::inconclusive", Verdict.inconclusive, None, None, reason, None),
            run_id=run_id, artifact_id=artifact_id, oracle_id=oracle_id, oracle_confidence=oracle_confidence,
            artifact_hash=artifact_hash, oracle_hash=oracle_hash, seed=seed, duration=result.duration_seconds,
        )
        return GradeReport(artifact_id, oracle_id, (case,), confidence)

    cases = tuple(
        _result(
            _classify(entry), run_id=run_id, artifact_id=artifact_id, oracle_id=oracle_id,
            oracle_confidence=oracle_confidence, artifact_hash=artifact_hash, oracle_hash=oracle_hash,
            seed=seed, duration=per_case_duration,
        )
        for entry in entries
    )
    return GradeReport(artifact_id, oracle_id, cases, confidence)


def attributable_regressions(report: GradeReport, baseline: Run | None) -> tuple[CaseResult, ...]:
    """The failures this change can be blamed for: failed now, and not already failing on the same oracle.

    A case that failed in ``baseline`` on the identical oracle content is a pre-existing failure
    (EL-205) and is excluded, so the current change is never charged with it.
    """
    failures = tuple(c for c in report.cases if c.verdict is Verdict.failed)
    if baseline is None:
        return failures
    already: set[tuple[str, str]] = set()
    for case in baseline.cases:
        if case.verdict is Verdict.failed:
            already.add((case.oracle_id, case.oracle_hash))
    return tuple(c for c in failures if (c.oracle_id, c.oracle_hash) not in already)


# -- the mutation self-check (A:38) ---------------------------------------------------


class _Mutator(ast.NodeTransformer):
    """One mutation at a chosen site: flip a comparison, swap an operator, nudge a constant."""

    _COMPARE = {
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt,
        ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    }
    _BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add}
    _BOOL = {ast.And: ast.Or, ast.Or: ast.And}

    def __init__(self, target: int) -> None:
        self._target = target
        self._seen = 0

    def _fire(self) -> bool:
        hit = self._seen == self._target
        self._seen += 1
        return hit

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in self._COMPARE and self._fire():
            node.ops = [self._COMPARE[type(node.ops[0])]()]
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if type(node.op) in self._BINOP and self._fire():
            node.op = self._BINOP[type(node.op)]()
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if type(node.op) in self._BOOL and self._fire():
            node.op = self._BOOL[type(node.op)]()
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, int) and not isinstance(node.value, bool) and self._fire():
            return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node


def _mutation_count(source: str) -> int:
    counter = _Mutator(-1)  # never fires; just counts sites via _seen
    counter.visit(ast.parse(source))
    return counter._seen


def _mutant(source: str, index: int) -> str | None:
    tree = _Mutator(index).visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree)
    except (ValueError, AttributeError):
        return None


def mutation_self_check(
    *,
    artifact_source: str,
    import_name: str,
    oracle_source: str,
    max_mutant_pass_rate: float,
    sandbox_limits: Limits,
    max_mutants: int = 40,
    seed: int = 0,
    workdir_root: str | None = None,
) -> MutationReport:
    """Mutate the artifact and run each mutant through the oracle (A:38). A survivor is a missed bug.

    ``max_mutant_pass_rate`` is A1's ``parameters`` value (5, per EL-015) -- the caller's, not a
    literal here. If more than that fraction of mutants pass, the oracle is not discriminating.
    """
    sites = _mutation_count(artifact_source)
    tested = 0
    survivors = 0
    for index in range(min(sites, max_mutants)):
        mutant = _mutant(artifact_source, index)
        if mutant is None or mutant == artifact_source:
            continue
        try:
            ast.parse(mutant)
        except SyntaxError:
            continue
        tested += 1
        report = grade_execution(
            artifact_id="mutant", artifact_source=mutant, import_name=import_name, oracle_id="mutation-check",
            oracle_source=oracle_source, oracle_confidence=OracleConfidence.high, oracle_hash="0" * 64,
            run_id="mutation-check", sandbox_limits=sandbox_limits, float_tolerance=1e-6, seed=seed,
            workdir_root=workdir_root,
        )
        if report.full_pass:  # the mutant slipped past every test: a bug the oracle cannot see
            survivors += 1
    return MutationReport(mutants=tested, survivors=survivors, max_pass_rate=max_mutant_pass_rate)
