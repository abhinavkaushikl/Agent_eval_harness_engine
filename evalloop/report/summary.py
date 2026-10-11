"""Render one run as a readable ``summary.md`` -- the one place a developer sees the numbers.

``USER_EXPERIENCE.md`` §3.4 fixes six sections, in this order and with these names:

1. What you built
2. What was evaluated and how
3. Findings, with per-item flips **in both directions**
4. What is not yet answerable, and what would unlock it
5. What was prohibited, and why
6. Cost

Section 4 is what makes this a summary of an honest system rather than a scoreboard, and its
content is EL-213's readiness reasons -- the actual ``needs discordant_pairs: 25, have 8`` -- which
are exactly the strings the planner already put in ``Plan.pending``. This renderer shows them
verbatim, never a restatement of the threshold.

The rules with teeth
--------------------
* **A rate is never shown without its interval.** ``00-INDEX.md`` principle 2 ("put a confidence
  interval on every number") is cross-cutting, and this is the one place it is seen, so it is the
  one place it bites: :func:`format_rate` computes the Wilson interval (EL-203) from the counts and
  **raises** if asked for a rate with no conclusive cases. There is no code path that prints a bare
  percentage.
* **The four states are the planner's.** ``Plan.render()`` is reused verbatim for the at-a-glance
  plan block, and sections 4 and 5 reuse the planner's own reason strings (``Plan.pending``,
  ``Plan.unavailable``, ``Plan.prohibition_reasons``). Nothing re-derives which record is ready,
  pending, unavailable or prohibited, or why.
* **Oracle confidence is shown on every finding**, and a LOW oracle is marked so it *looks* low:
  a generated test is never allowed to read as ground truth (``AGENT.md`` §3.6).
* **INCONCLUSIVE is shown apart from a failure** (``USER_EXPERIENCE.md`` §3.2, decision EL-014): a
  timeout is a failure of class ``timeout``, counted in the rate and listed among the failures; an
  inconclusive case is the evaluation failing, counted in neither and listed on its own line.
* **Byte-stable.** Identical input renders identical bytes, proven by a golden-file test, so two
  runs diff cleanly. Every ordering here is explicit; nothing is sorted by a hash or a set.

The two common cases, written first
-----------------------------------
On day one an empty plan ("nothing applies here") and a clean run ("nothing was found") are the
*common* outcomes, not the edge cases -- a summarization session plans nothing, and six situations
reach no record at all (S23-REPORT §3). So those two are rendered deliberately and read as an
honest account, not as a broken scoreboard with blank tables. Every "no" states its reason in plain
language (``USER_EXPERIENCE.md`` §4.3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from evalloop.memory.case import CaseResult, FailureClass, OracleConfidence, Verdict
from evalloop.memory.metric_store import Flip, Run, diff_runs
from evalloop.plan.planner import Plan
from evalloop.stats import wilson_interval
from evalloop.vocab import Situation

__all__ = ["Session", "format_rate", "render_summary"]

_RUNG_NAMES: Mapping[int, str] = {1: "execution", 2: "end-state", 3: "deterministic", 4: "judge", 5: "human"}

#: The order failure classes are listed in: A:39's four, then EL-014's timeout last.
_CLASS_ORDER: tuple[FailureClass, ...] = (
    FailureClass.syntax_error,
    FailureClass.unknown_column,
    FailureClass.runtime_error,
    FailureClass.wrong_result,
    FailureClass.timeout,
)

#: Plain-language gloss for a missing tool, so UNAVAILABLE reads without jargon (§4.3).
_TOOL_GLOSS: Mapping[str, str] = {
    "sandbox": "a sandbox to run the artifact in",
    "test_runner": "a test runner",
    "repo_read": "permission to read the repository",
    "source_doc_read": "permission to read the source documents",
    "llm_api": "a model API",
    "llm_api_cross_family": "a second model from a different family",
    "vector_store": "access to the vector store",
    "db_connection": "a database connection",
    "ocr": "an OCR tool",
    "vision_model": "a vision model",
    "trace_capture": "captured agent traces",
    "snapshot_restore": "a restorable environment snapshot",
    "cost_api": "the model-cost API",
    "human_labels": "human labels",
    "production_logs": "production logs",
}


@dataclass(frozen=True)
class Session:
    """Everything one run's summary is rendered from. All of it is already-stored fact.

    ``cases`` are this run's judged cases (EL-201); ``prior_cases`` are a baseline run's, for the
    both-directions flips. ``plan`` is the planner's output, computed from the assembled evidence
    (EL-213), so its ``pending`` reasons already read ``needs <key>: <threshold>, have <actual>``.
    """

    run_id: str
    situations: tuple[tuple[Situation, float], ...]
    plan: Plan
    cases: tuple[CaseResult, ...] = ()
    cost_usd: Decimal = Decimal(0)
    intent: str | None = None
    prior_run_id: str | None = None
    prior_cases: tuple[CaseResult, ...] = ()
    confidence: float = 0.95


def format_rate(passed: int, failed: int, *, confidence: float = 0.95) -> str:
    """``P% [lo, hi]`` with the Wilson interval. Raises if there is no rate to put an interval on.

    This is the only way the renderer turns counts into a percentage, so a bare rate cannot be
    printed: a rate needs at least one conclusive case, and then it travels with its interval.
    """
    n = passed + failed
    if n < 1:
        raise ValueError("a rate needs at least one conclusive case; without one there is no number to show")
    interval = wilson_interval(passed, n, confidence)
    return f"{interval.estimate * 100:.1f}% [{interval.lower * 100:.1f}, {interval.upper * 100:.1f}]"


def _for_record(cases: Sequence[CaseResult]) -> dict[str, list[CaseResult]]:
    grouped: dict[str, list[CaseResult]] = {}
    for case in cases:
        grouped.setdefault(case.record_id, []).append(case)
    return grouped


def _confidence_tag(cases: Sequence[CaseResult]) -> str:
    kinds = {case.oracle_confidence for case in cases}
    if kinds == {OracleConfidence.high}:
        return "HIGH oracle"
    if kinds == {OracleConfidence.low}:
        return "LOW oracle — generated, not ground truth"
    return "mixed oracles (some LOW — generated, not ground truth)"


def _failure_breakdown(failed: Sequence[CaseResult]) -> str:
    counts: dict[FailureClass, int] = {}
    caps: dict[FailureClass, set[str]] = {}
    for case in failed:
        if case.failure_class is None:
            continue
        counts[case.failure_class] = counts.get(case.failure_class, 0) + 1
        if case.failure_class is FailureClass.timeout and case.timeout is not None:
            caps.setdefault(FailureClass.timeout, set()).add(case.timeout.cap.value)
    parts: list[str] = []
    for cls in _CLASS_ORDER:
        if cls not in counts:
            continue
        label = f"{cls.value} {counts[cls]}"
        if cls is FailureClass.timeout and len(caps.get(cls, set())) == 1:
            label += f" ({next(iter(caps[cls]))})"
        parts.append(label)
    return ", ".join(parts)


def _finding_lines(cases: Sequence[CaseResult]) -> list[str]:
    passed = [c for c in cases if c.verdict is Verdict.passed]
    failed = [c for c in cases if c.verdict is Verdict.failed]
    inconclusive = [c for c in cases if c.verdict is Verdict.inconclusive]
    n = len(passed) + len(failed)
    tag = _confidence_tag(cases)
    lines: list[str] = []
    if n == 0:
        lines.append(f"- no conclusive result · inconclusive {len(inconclusive)} · [{tag}]")
    else:
        rate = format_rate(len(passed), len(failed))
        detail = f"n={n}"
        if failed:
            detail += f" · failed {len(failed)}: {_failure_breakdown(failed)}"
        detail += f" · inconclusive {len(inconclusive)}"
        lines.append(f"- {rate}  {detail} · [{tag}]")
    for case in inconclusive:
        reason = case.inconclusive_reason or "the evaluation could not run"
        lines.append(f"    - inconclusive: {case.artifact_id} — {reason}")
    return lines


def _flip_line(flip: Flip) -> str:
    return f"- {flip.artifact_id} [{flip.case_id}] ({flip.record_id}): {flip.before} → {flip.after}"


def _section(title: str, body: Sequence[str]) -> str:
    return "\n".join([f"## {title}", "", *body])


def _s1_built(session: Session) -> str:
    body: list[str]
    if session.situations:
        body = [f"- `{situation.value}` (confidence {conf:.2f})" for situation, conf in session.situations]
    else:
        body = ["Nothing was classified for this run, so there is nothing to evaluate."]
    if session.intent:
        body.append("")
        body.append(f"Stated intent: {session.intent}")
    else:
        body.append("")
        body.append("No stated intent (M1 does not read transcripts).")
    return _section("1. What you built", body)


def _s2_evaluated(session: Session) -> str:
    plan = session.plan
    body = ["The plan:", "", "```", plan.render(), "```", ""]
    grouped = _for_record(session.cases)
    if not plan.ready:
        body.append("No technique applied to the inferred situation(s), so nothing was evaluated.")
        return _section("2. What was evaluated and how", body)
    ran = [record.id for record in plan.ready if record.id in grouped]
    if not ran:
        body.append("The techniques above are ready, but no case has been judged yet this run.")
        return _section("2. What was evaluated and how", body)
    body.append("Evaluated:")
    body.append("")
    body.append("| Technique | Rung | Oracle |")
    body.append("|---|---|---|")
    for rid in ran:
        cases = grouped[rid]
        rung = cases[0].ladder_rung
        rung_text = f"{rung} ({_RUNG_NAMES[rung]})" if rung is not None and rung in _RUNG_NAMES else "—"
        tag = "HIGH" if {c.oracle_confidence for c in cases} == {OracleConfidence.high} else "LOW"
        body.append(f"| {rid} | {rung_text} | {tag} |")
    return _section("2. What was evaluated and how", body)


def _s3_findings(session: Session) -> str:
    grouped = _for_record(session.cases)
    if not grouped:
        return _section("3. Findings", ["Nothing was evaluated, so there are no findings."])
    body: list[str] = []
    for rid in sorted(grouped):
        body.append(f"**{rid}**")
        body.extend(_finding_lines(grouped[rid]))
        body.append("")
    if session.prior_cases:
        prior = Run(session.prior_run_id or "previous", tuple(session.prior_cases))
        current = Run(session.run_id, tuple(session.cases))
        diff = diff_runs(prior, current)
        body.append(f"Per-item changes since run `{prior.run_id}`:")
        body.append("")
        if diff.regressions:
            body.append(f"Regressions ({len(diff.regressions)}):")
            body.extend(_flip_line(f) for f in diff.regressions)
        if diff.improvements:
            body.append(f"Improvements ({len(diff.improvements)}):")
            body.extend(_flip_line(f) for f in diff.improvements)
        if diff.failure_changed:
            body.append(f"Failure kind changed ({len(diff.failure_changed)}):")
            body.extend(_flip_line(f) for f in diff.failure_changed)
        if diff.became_inconclusive:
            body.append(f"Became inconclusive ({len(diff.became_inconclusive)}):")
            body.extend(_flip_line(f) for f in diff.became_inconclusive)
        if diff.became_conclusive:
            body.append(f"Became conclusive ({len(diff.became_conclusive)}):")
            body.extend(_flip_line(f) for f in diff.became_conclusive)
        if not any(
            (diff.regressions, diff.improvements, diff.failure_changed, diff.became_inconclusive, diff.became_conclusive)
        ):
            body.append("No per-item outcome changed since the previous run.")
    return _section("3. Findings", body).rstrip()


def _s4_pending(session: Session) -> str:
    plan = session.plan
    body: list[str] = []
    if plan.pending:
        body.append("Not enough evidence yet (the bar is the methodology's, the count is this run's):")
        body.append("")
        body.extend(f"- `{rid}` {plan.pending[rid]}" for rid in plan.pending)
        body.append("")
    if plan.unavailable:
        body.append("Needs a tool or permission not available here:")
        body.append("")
        for rid in plan.unavailable:
            tools = ", ".join(_TOOL_GLOSS.get(tool.value, tool.value) for tool in plan.unavailable[rid])
            body.append(f"- `{rid}` needs {tools}")
        body.append("")
    if not body:
        body.append("Nothing is waiting on more evidence or a missing tool.")
    return _section("4. What is not yet answerable, and what would unlock it", [line.rstrip() for line in body]).rstrip()


def _s5_prohibited(session: Session) -> str:
    plan = session.plan
    if not plan.prohibited:
        body = ["Nothing was prohibited here."]
    else:
        body = ["The methodology forbids these here, with the reason:", ""]
        body.extend(f"- `{rid}` {plan.prohibition_reasons[rid]}" for rid in plan.prohibited)
    return _section("5. What was prohibited, and why", body)


def _s6_cost(session: Session) -> str:
    if session.cost_usd == 0:
        body = ["LLM spend: $0.0000. M1 grades by execution, which makes no model call."]
    else:
        body = [f"LLM spend: ${session.cost_usd:.4f}."]
    return _section("6. Cost", body)


def render_summary(session: Session) -> str:
    """The six-section ``summary.md`` for one run, byte-stable for identical input."""
    sections = [
        f"# EvalLoop session summary\n\nRun `{session.run_id}`.",
        _s1_built(session),
        _s2_evaluated(session),
        _s3_findings(session),
        _s4_pending(session),
        _s5_prohibited(session),
        _s6_cost(session),
    ]
    return "\n\n".join(sections).rstrip() + "\n"
