"""Eval-spec files: how SQL, RAG and agent evals reach the live loop without being Python functions.

The watcher grades Python functions by saving them. SQL queries, retrieval sets and agent tasks are
not functions you save, so they arrive instead as a small JSON **spec** dropped in the watched
folder — ``*.eval.json`` with a ``kind``:

* ``sql``   — run generated queries against a SQLite database (a path you point at, or inline setup)
              and compare result sets to a reference query (EL-311's execution-match grader);
* ``rag``   — recall@k over the passages each query actually retrieved, with a Wilson CI (EL-312);
* ``agent`` — verify the real end state of a scratch database against checks, ignoring the agent's
              own claim (EL-314);
* ``agent_behavior`` — for an agent with no external end state (a chat/tool agent), run its loop
              against a scripted stand-in LLM and grade its *behaviour* — reached an answer, called a
              tool, stayed within a step budget (trajectory; no API key needed).

Each kind calls the already-built grader; this module only parses the spec and shapes the result.
It writes nothing to the metric store — the session renders the cases straight onto the bot. A live
Postgres/MySQL connection slots in where ``sqlite`` is read today (the connectors exist, EL-308);
until then a SQLite file is the "live connection", and a missing or malformed spec is a stated error,
never a silent skip.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from evalloop.grade.end_state import (
    AgentClaim,
    FileAbsent,
    FileContains,
    FileExists,
    NoRows,
    RESETTABLE_FACT,
    RowsEqual,
    StateCheck,
    verify_end_state,
)
from evalloop.grade.rag_recall import RecallQuery, measure_recall_at_k
from evalloop.grade.sql_execution import Snapshot, build_snapshot, grade_sql
from evalloop.grade.trajectory import (
    BehaviourCheck,
    MaxSteps,
    OnlyKnownTools,
    ReachedAnswer,
    ReplyContains,
    ToolCalled,
    grade_behaviour,
    run_agent_chat,
)

__all__ = ["SpecCase", "SpecResult", "SpecError", "SPEC_SUFFIX", "grade_spec_file"]

SPEC_SUFFIX = ".eval.json"


class SpecError(Exception):
    """A spec that cannot be run, with a reason the driver prints. Never a silent skip."""


@dataclass(frozen=True, slots=True)
class SpecCase:
    """One graded item inside a spec: a name, a verdict, and the detail behind it."""

    name: str
    verdict: str   # "passed" | "failed" | "inconclusive"
    detail: str


@dataclass(frozen=True, slots=True)
class SpecResult:
    """The outcome of one spec file: which kind, which situation, and the per-item verdicts."""

    kind: str
    situation: str
    cases: tuple[SpecCase, ...]

    @property
    def outcome(self) -> str:
        if any(c.verdict == "failed" for c in self.cases):
            return "problem"
        if any(c.verdict == "passed" for c in self.cases):
            return "clean"
        return "undecided"


def _require(data: dict[str, object], key: str, where: str) -> object:
    if key not in data:
        raise SpecError(f"{where} spec needs a {key!r} field")
    return data[key]


def grade_spec_file(path: str | Path) -> SpecResult:
    """Parse and grade one ``*.eval.json`` spec. Dispatches on ``kind``."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"{p.name}: not readable JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise SpecError(f"{p.name}: a spec must be a JSON object")
    kind = raw.get("kind")
    if kind == "sql":
        return _grade_sql_spec(raw, base=p.parent)
    if kind == "rag":
        return _grade_rag_spec(raw)
    if kind == "agent":
        return _grade_agent_spec(raw)
    if kind == "agent_behavior":
        return _grade_agent_behaviour_spec(raw, base=p.parent)
    raise SpecError(f"{p.name}: unknown kind {kind!r}; expected 'sql', 'rag', 'agent' or 'agent_behavior'")


# -- SQL -------------------------------------------------------------------------------

def _open_sqlite(data: dict[str, object], base: Path) -> Snapshot:
    """A read-only snapshot from a live SQLite file (``sqlite``) or inline setup (``sqlite_setup``)."""
    if "sqlite" in data:
        path = base / str(data["sqlite"])
        if not path.exists():
            raise SpecError(f"sqlite database {path} does not exist")
        return Snapshot(path)
    if "sqlite_setup" in data:
        scratch = Path(tempfile.mkdtemp()) / "spec.sqlite"
        return build_snapshot(scratch, str(data["sqlite_setup"]))
    raise SpecError("sql spec needs 'sqlite' (a path to a live DB) or 'sqlite_setup' (inline SQL)")


def _grade_sql_spec(data: dict[str, object], *, base: Path) -> SpecResult:
    queries = _require(data, "queries", "sql")
    if not isinstance(queries, list) or not queries:
        raise SpecError("sql spec 'queries' must be a non-empty list")
    snapshot = _open_sqlite(data, base)
    cases: list[SpecCase] = []
    try:
        for i, item in enumerate(queries):
            if not isinstance(item, dict) or "generated" not in item:
                raise SpecError(f"sql query {i} needs a 'generated' field")
            grade = grade_sql(
                str(item["generated"]),
                snapshot=snapshot,
                reference=str(item["reference"]) if item.get("reference") is not None else None,
                question=str(item["question"]) if item.get("question") is not None else None,
            )
            verdict, detail = grade.verdict.value, grade.detail
            reference = item.get("reference")
            if verdict == "passed" and reference is not None:
                blind = _undistinguished_boundaries(str(reference), snapshot)
                if blind:
                    verdict = "inconclusive"
                    detail = (
                        f"{detail}, but the data cannot tell the boundary apart: the reference with "
                        f"{', '.join(blind)} returns the same rows, so a wrong boundary would pass too. "
                        "Seed a row exactly on the boundary (A:36: \"wrong queries pass by coincidence\")"
                    )
            cases.append(SpecCase(str(item.get("name", f"query {i + 1}")), verdict, detail))
    finally:
        snapshot.close()
    return SpecResult("sql", "sql_generation", tuple(cases))


#: Comparison operators and the off-by-one neighbour a plausible wrong query uses instead (A:36's
#: ``>`` vs ``>=``). ``<>`` is not-equal, not a boundary, so it is matched first and left alone.
_BOUNDARY_SWAP = {">": ">=", ">=": ">", "<": "<=", "<=": "<"}
_COMPARISON = re.compile(r"<>|>=|<=|>|<")
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def _boundary_mutants(sql: str) -> list[tuple[str, str]]:
    """Every single-operator boundary swap of ``sql`` outside string literals: ``(label, mutant)``."""
    literals = [(m.start(), m.end()) for m in _STRING_LITERAL.finditer(sql)]
    mutants: list[tuple[str, str]] = []
    for match in _COMPARISON.finditer(sql):
        op = match.group()
        if op == "<>" or any(start <= match.start() < end for start, end in literals):
            continue
        swapped = _BOUNDARY_SWAP[op]
        mutants.append((f"`{op}` swapped for `{swapped}`", sql[: match.start()] + swapped + sql[match.end() :]))
    return mutants


def _undistinguished_boundaries(reference: str, snapshot: Snapshot) -> list[str]:
    """The boundary swaps of ``reference`` that the seeded data cannot tell from the reference itself.

    A pass on execution match is only as strong as the rows seeded (A:36). If moving a boundary by
    one (``>`` to ``>=``) returns the same result set, then a generated query with that very mistake
    passes too, so the pass shows nothing about the boundary.
    """
    return [
        label
        for label, mutant in _boundary_mutants(reference)
        if grade_sql(mutant, snapshot=snapshot, reference=reference).verdict.value == "passed"
    ]


# -- RAG -------------------------------------------------------------------------------

class _FixedRetriever:
    """Returns the passages each query *actually* retrieved, as recorded in the spec."""

    def __init__(self, table: dict[str, list[str]]) -> None:
        self._table = table

    def retrieve(self, query: RecallQuery, k: int) -> Sequence[str]:
        return self._table.get(query.query_id, [])[:k]


def _grade_rag_spec(data: dict[str, object]) -> SpecResult:
    raw_queries = _require(data, "queries", "rag")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise SpecError("rag spec 'queries' must be a non-empty list")
    k = int(str(_require(data, "k", "rag")))
    model = str(data.get("embedding_model", "")) or "unspecified"
    queries: list[RecallQuery] = []
    table: dict[str, list[str]] = {}
    for i, q in enumerate(raw_queries):
        if not isinstance(q, dict) or "query_id" not in q or "gold_ids" not in q:
            raise SpecError(f"rag query {i} needs 'query_id' and 'gold_ids'")
        qid = str(q["query_id"])
        queries.append(RecallQuery(qid, tuple(str(g) for g in q["gold_ids"]), str(q.get("text", ""))))
        table[qid] = [str(r) for r in q.get("retrieved", [])]
    recall = measure_recall_at_k(queries, k=k, embedding_model=model, retriever=_FixedRetriever(table))

    min_recall = data.get("min_recall")
    if min_recall is None:
        verdict, detail = "inconclusive", f"{recall.describe()} — no 'min_recall' set, so measured not gated"
    else:
        # Gate on the interval, not the point estimate: when the interval contains the bar, the data has
        # not shown which side recall is on (C:49: overlapping intervals mean "no gap had been demonstrated").
        bar = float(str(min_recall))
        if recall.interval.lower >= bar:
            verdict, detail = "passed", f"{recall.describe()} vs min_recall {min_recall}: the whole interval clears it"
        elif recall.interval.upper < bar:
            verdict, detail = "failed", f"{recall.describe()} vs min_recall {min_recall}: the whole interval is below it"
        else:
            verdict = "inconclusive"
            detail = (
                f"{recall.describe()} vs min_recall {min_recall}: the interval contains the bar, so these "
                f"{recall.total_gold} gold passages cannot say which side recall is on; add labelled queries"
            )
    return SpecResult("rag", "rag_answer", (SpecCase(f"recall@{k}", verdict, detail),))


# -- agent -----------------------------------------------------------------------------

def _build_check(i: int, ch: object) -> StateCheck:
    if not isinstance(ch, dict) or "type" not in ch:
        raise SpecError(f"agent check {i} needs a 'type'")
    kind = str(ch["type"])
    name = str(ch.get("name", f"check {i + 1}"))
    if kind == "no_rows":
        return NoRows(name, str(_require(ch, "sql", "no_rows check")))
    if kind == "rows_equal":
        expected = _require(ch, "expected", "rows_equal check")
        if not isinstance(expected, list):
            raise SpecError("rows_equal 'expected' must be a list of rows")
        rows = [tuple(r) for r in expected if isinstance(r, list)]
        return RowsEqual(name, str(_require(ch, "sql", "rows_equal check")), rows, bool(ch.get("ordered", False)))
    if kind == "file_exists":
        return FileExists(name, str(_require(ch, "path", "file_exists check")))
    if kind == "file_absent":
        return FileAbsent(name, str(_require(ch, "path", "file_absent check")))
    if kind == "file_contains":
        return FileContains(name, str(_require(ch, "path", "file_contains check")), str(_require(ch, "text", "file_contains check")))
    raise SpecError(f"agent check {i}: unknown type {kind!r}")


def _grade_agent_spec(data: dict[str, object]) -> SpecResult:
    raw_checks = _require(data, "checks", "agent")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise SpecError("agent spec 'checks' must be a non-empty list")
    checks = [_build_check(i, ch) for i, ch in enumerate(raw_checks)]

    snapshot: Snapshot | None = None
    root = Path(str(data["root"])) if data.get("root") else None
    if "sqlite_setup" in data:
        scratch = Path(tempfile.mkdtemp()) / "agent.sqlite"
        snapshot = build_snapshot(scratch, str(data["sqlite_setup"]))

    claim_raw = data.get("claim")
    claim = None
    if isinstance(claim_raw, dict):
        claim = AgentClaim(bool(claim_raw.get("done", False)), str(claim_raw.get("message", "")))
    try:
        grade = verify_end_state(
            checks,
            db=snapshot,
            root=root,
            claim=claim,
            session_facts={RESETTABLE_FACT: True},  # the scratch snapshot IS a clean reset
            require_resettable=True,
        )
    finally:
        if snapshot is not None:
            snapshot.close()
    cases = tuple(SpecCase(r.name, "passed" if r.ok else "failed", r.detail) for r in grade.checks)
    if not cases:
        cases = (SpecCase("end_state", grade.verdict.value, grade.detail),)
    return SpecResult("agent", "agent_action", cases)


# -- agent behaviour (trajectory, no end state) ----------------------------------------

def _build_behaviour_check(i: int, ch: object) -> BehaviourCheck:
    if not isinstance(ch, dict) or "type" not in ch:
        raise SpecError(f"behaviour check {i} needs a 'type'")
    kind = str(ch["type"])
    if kind == "reached_answer":
        return ReachedAnswer()
    if kind == "reply_contains":
        return ReplyContains(str(_require(ch, "text", "reply_contains check")))
    if kind == "tool_called":
        return ToolCalled(str(_require(ch, "name", "tool_called check")))
    if kind == "max_steps":
        return MaxSteps(int(str(_require(ch, "limit", "max_steps check"))))
    if kind == "only_known_tools":
        known = _require(ch, "known", "only_known_tools check")
        if not isinstance(known, list):
            raise SpecError("only_known_tools 'known' must be a list of tool names")
        return OnlyKnownTools(tuple(str(t) for t in known))
    raise SpecError(f"behaviour check {i}: unknown type {kind!r}")


def _grade_agent_behaviour_spec(data: dict[str, object], *, base: Path) -> SpecResult:
    module = base / str(_require(data, "module", "agent_behavior"))
    if not module.exists():
        raise SpecError(f"agent module {module} does not exist")
    entry = str(data.get("entry", "chat"))
    user = str(_require(data, "user", "agent_behavior"))
    system = str(data["system"]) if data.get("system") else None
    raw_script = data.get("script")
    if raw_script is not None and not isinstance(raw_script, list):
        raise SpecError("agent_behavior 'script' must be a list of turns")
    script = [t for t in (raw_script or []) if isinstance(t, dict)]
    raw_checks = _require(data, "checks", "agent_behavior")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise SpecError("agent_behavior spec 'checks' must be a non-empty list")
    checks = [_build_behaviour_check(i, ch) for i, ch in enumerate(raw_checks)]
    try:
        trajectory = run_agent_chat(module, entry, user=user, script=script, system=system)
    except (ImportError, AttributeError) as exc:  # a spec that names the wrong module/entry: config error
        raise SpecError(f"cannot run agent {module.name}::{entry} — {type(exc).__name__}: {exc}") from exc
    except Exception as exc:  # the AGENT's own code raised — that is the agent failing, not EvalLoop
        detail = f"the agent raised {type(exc).__name__}: {exc}"
        return SpecResult("agent_behavior", "agent_action", (SpecCase("the agent ran without crashing", "failed", detail),))
    grade = grade_behaviour(trajectory, checks)
    cases = tuple(SpecCase(r.name, "passed" if r.ok else "failed", r.detail) for r in grade.checks)
    return SpecResult("agent_behavior", "agent_action", cases)
