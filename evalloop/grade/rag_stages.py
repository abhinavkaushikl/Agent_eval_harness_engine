"""The rest of the RAG ladder — each stage reported SEPARATELY, each number with its interval.

Why separate stages (G1/G2): "without attribution, every fix is a guess." The corpus's own cases —
a team that rewrote prompts for three weeks when the fix was re-chunking a table (a *retrieval*
problem), and another that cancelled a six-week vector-DB migration when the fix was a prompt (a
*generation* problem) — are why one blended RAG number is useless. So this module produces one line
per stage and **no single blended RAG score**; there is no function here that averages across stages.

The stages:
  * **Oracle-context ceiling (G2)** — feed the generator gold passages and measure its ceiling.
  * **Per-failure attribution (G2)** — every failure tagged ``not_retrieved`` / ``ranked_beyond_k`` /
    ``misread``, reported as SHARES of actual failures so the backlog ranks by impact.
  * **Faithfulness (G3)** — atomic claims against the context, judged for entailment; reports BOTH
    mean faithfulness AND the % of answers with ≥1 unsupported claim (the second is what users feel).
  * **Distractor robustness (G7)**, **unanswerables (G6 — false-answer rate AND over-abstention)**,
    **citation precision/recall (G8)**.

The faithfulness judge is CROSS-FAMILY and calibrated. Building that judge and its κ gate is **M4**;
this module *consumes* them. If M4 has not landed (no judge), faithfulness is PENDING with that
reason — never silently skipped, never a bare number. A judge whose agreement κ is below the gate is
reported but **does not gate** (G3/F). Every rate carries a Wilson interval (C1).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from evalloop._compat import StrEnum
from evalloop.stats.proportions import DEFAULT_CONFIDENCE, Interval, wilson_interval

__all__ = [
    "Stage",
    "FailureStage",
    "Metric",
    "StageResult",
    "FaithfulnessJudge",
    "FaithfulnessAnswer",
    "CitationItem",
    "oracle_context_ceiling",
    "failure_attribution",
    "faithfulness",
    "distractor_robustness",
    "unanswerable_handling",
    "citation_quality",
    "render",
]


class Stage(StrEnum):
    oracle_ceiling = "oracle_ceiling"
    attribution = "attribution"
    faithfulness = "faithfulness"
    distractor_robustness = "distractor_robustness"
    unanswerable = "unanswerable"
    citation = "citation"


class FailureStage(StrEnum):
    """Where a RAG failure actually happened — the three buckets attribution splits failures into."""

    not_retrieved = "not_retrieved"
    ranked_beyond_k = "ranked_beyond_k"
    misread = "misread"


@dataclass(frozen=True, slots=True)
class Metric:
    """One named number with its interval. A stage reports one or more; never a number without its CI."""

    name: str
    interval: Interval


@dataclass(frozen=True, slots=True)
class StageResult:
    """One stage's line: its metrics (each with an interval), or a pending reason — never blended away."""

    stage: Stage
    status: str  # "measured" | "measured_nongating" | "pending"
    metrics: tuple[Metric, ...]
    detail: str
    pending_reason: str | None = None

    @property
    def gates(self) -> bool:
        return self.status == "measured"


def _measured(stage: Stage, metrics: tuple[Metric, ...], detail: str) -> StageResult:
    return StageResult(stage, "measured", metrics, detail)


def _pending(stage: Stage, reason: str) -> StageResult:
    return StageResult(stage, "pending", (), reason, pending_reason=reason)


# -- G2: oracle-context ceiling --------------------------------------------------------


def oracle_context_ceiling(correct_given_gold: Sequence[bool], *, confidence: float = DEFAULT_CONFIDENCE) -> StageResult:
    """The generator's ceiling when fed gold passages: how high end-to-end accuracy could ever reach."""
    n = len(correct_given_gold)
    if n == 0:
        return _measured(Stage.oracle_ceiling, (), "no items fed with gold context")
    successes = sum(1 for ok in correct_given_gold if ok)
    metric = Metric("generation_accuracy_given_gold", wilson_interval(successes, n, confidence))
    return _measured(Stage.oracle_ceiling, (metric,), f"ceiling over {n} gold-fed items")


# -- G2: per-failure attribution -------------------------------------------------------


def failure_attribution(failures: Sequence[FailureStage], *, confidence: float = DEFAULT_CONFIDENCE) -> StageResult:
    """Each failure tagged not_retrieved / ranked_beyond_k / misread, as SHARES of actual failures."""
    n = len(failures)
    if n == 0:
        return _measured(Stage.attribution, (), "no failures to attribute")
    counts = Counter(failures)
    metrics = tuple(
        Metric(stage.value, wilson_interval(counts.get(stage, 0), n, confidence))
        for stage in FailureStage  # a stable, exhaustive order, including zero-share buckets
    )
    return _measured(Stage.attribution, metrics, f"shares of {n} failures")


# -- G3: faithfulness (consumes M4's cross-family, calibrated judge) -------------------


@runtime_checkable
class FaithfulnessJudge(Protocol):
    """An M4 judge: its model family, its calibration agreement κ, and a claim/context entailment call."""

    family: str
    kappa: float

    def entails(self, claim: str, context: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class FaithfulnessAnswer:
    """One answer decomposed into atomic claims, with the retrieved context they are checked against."""

    claims: tuple[str, ...]
    context: str


def faithfulness(
    answers: Sequence[FaithfulnessAnswer],
    *,
    judge: FaithfulnessJudge | None,
    kappa_gate: float,
    generator_family: str | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
) -> StageResult:
    """Mean faithfulness AND the % of answers with ≥1 unsupported claim. PENDING without M4's judge.

    ``kappa_gate`` is supplied by the caller (M4's calibration policy); it is not defaulted here,
    because inventing a trust threshold is exactly what EvalLoop must not do.
    """
    if judge is None:
        return _pending(Stage.faithfulness, "needs M4's cross-family calibrated judge; M4 has not landed, so faithfulness is unavailable")
    if generator_family is not None and judge.family == generator_family:
        return _pending(Stage.faithfulness, f"the judge family {judge.family!r} matches the generator's; faithfulness needs a CROSS-family judge (self-preference risk)")

    total_claims = sum(len(a.claims) for a in answers)
    if total_claims == 0:
        return _measured(Stage.faithfulness, (), "no claims to check")
    entailed = 0
    answers_with_unsupported = 0
    for answer in answers:
        any_unsupported = False
        for claim in answer.claims:
            if judge.entails(claim, answer.context):
                entailed += 1
            else:
                any_unsupported = True
        if any_unsupported:
            answers_with_unsupported += 1

    metrics = (
        Metric("mean_faithfulness", wilson_interval(entailed, total_claims, confidence)),
        Metric("answers_with_unsupported_claim", wilson_interval(answers_with_unsupported, len(answers), confidence)),
    )
    if judge.kappa < kappa_gate:
        reason = f"judge agreement κ={judge.kappa:.2f} is below the gate {kappa_gate:.2f}; measured but does NOT gate"
        return StageResult(Stage.faithfulness, "measured_nongating", metrics, reason, pending_reason=None)
    return _measured(Stage.faithfulness, metrics, f"cross-family judge {judge.family} (κ={judge.kappa:.2f} ≥ {kappa_gate:.2f})")


# -- G7: distractor robustness ---------------------------------------------------------


def distractor_robustness(correct_with_distractors: Sequence[bool], *, confidence: float = DEFAULT_CONFIDENCE) -> StageResult:
    """How often the answer stays correct when distractor passages are injected into the context."""
    n = len(correct_with_distractors)
    if n == 0:
        return _measured(Stage.distractor_robustness, (), "no items run with distractors")
    successes = sum(1 for ok in correct_with_distractors if ok)
    metric = Metric("accuracy_with_distractors", wilson_interval(successes, n, confidence))
    return _measured(Stage.distractor_robustness, (metric,), f"over {n} distractor-injected items")


# -- G6: unanswerables (false-answer rate AND over-abstention) -------------------------


def unanswerable_handling(
    answered_when_unanswerable: Sequence[bool],
    abstained_when_answerable: Sequence[bool],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
) -> StageResult:
    """Two separate rates: answering an unanswerable question, and abstaining on an answerable one."""
    metrics: list[Metric] = []
    detail_parts: list[str] = []
    if answered_when_unanswerable:
        n = len(answered_when_unanswerable)
        hits = sum(1 for answered in answered_when_unanswerable if answered)
        metrics.append(Metric("false_answer_rate", wilson_interval(hits, n, confidence)))
        detail_parts.append(f"{n} unanswerable")
    if abstained_when_answerable:
        n = len(abstained_when_answerable)
        hits = sum(1 for abstained in abstained_when_answerable if abstained)
        metrics.append(Metric("over_abstention_rate", wilson_interval(hits, n, confidence)))
        detail_parts.append(f"{n} answerable")
    detail = "; ".join(detail_parts) if detail_parts else "no unanswerable/answerable items"
    return _measured(Stage.unanswerable, tuple(metrics), detail)


# -- G8: citation precision / recall ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class CitationItem:
    """One answer's citations: the passage ids it cited, and the passage ids that actually support it."""

    cited_ids: tuple[str, ...]
    supporting_ids: tuple[str, ...]


def citation_quality(items: Sequence[CitationItem], *, confidence: float = DEFAULT_CONFIDENCE) -> StageResult:
    """Micro precision (cited that support / cited) and recall (supporting that were cited / supporting)."""
    cited_total = 0
    supporting_total = 0
    correct_citations = 0  # cited ∩ supporting, for precision
    recalled_support = 0  # supporting ∩ cited, for recall
    for item in items:
        cited = set(item.cited_ids)
        supporting = set(item.supporting_ids)
        overlap = cited & supporting
        cited_total += len(cited)
        supporting_total += len(supporting)
        correct_citations += len(overlap)
        recalled_support += len(overlap)
    metrics: list[Metric] = []
    if cited_total:
        metrics.append(Metric("citation_precision", wilson_interval(correct_citations, cited_total, confidence)))
    if supporting_total:
        metrics.append(Metric("citation_recall", wilson_interval(recalled_support, supporting_total, confidence)))
    detail = f"{cited_total} citations, {supporting_total} supporting passages"
    return _measured(Stage.citation, tuple(metrics), detail)


# -- rendering: one line per stage, never blended --------------------------------------


def render(stages: Sequence[StageResult]) -> str:
    """Each stage on its own line with its numbers and intervals. There is deliberately no total."""
    lines: list[str] = []
    for result in stages:
        if result.status == "pending":
            lines.append(f"PENDING   {result.stage.value}: {result.pending_reason}")
            continue
        flag = " (non-gating)" if result.status == "measured_nongating" else ""
        if result.metrics:
            numbers = ", ".join(
                f"{m.name}={m.interval.estimate:.3f} [{m.interval.lower:.3f}, {m.interval.upper:.3f}]"
                for m in result.metrics
            )
        else:
            numbers = result.detail
        lines.append(f"MEASURED  {result.stage.value}{flag}: {numbers}")
    return "\n".join(lines)
