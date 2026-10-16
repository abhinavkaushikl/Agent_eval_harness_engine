"""The RAG ladder's stages, each reported separately with its own interval — never one blended score.

The load-bearing proofs: the oracle ceiling and distractor robustness are rates with intervals;
attribution reports failures as shares of the three buckets; faithfulness reports BOTH mean
faithfulness AND the unsupported-answer rate; unanswerables report false-answer AND over-abstention
separately; citations report precision AND recall; and faithfulness is PENDING when M4's judge is
absent, non-gating when its κ is below the gate, and refuses a same-family judge.
"""

from __future__ import annotations

from evalloop.grade.rag_stages import (
    CitationItem,
    FailureStage,
    FaithfulnessAnswer,
    Stage,
    citation_quality,
    distractor_robustness,
    failure_attribution,
    faithfulness,
    oracle_context_ceiling,
    render,
    unanswerable_handling,
)


class _Judge:
    def __init__(self, family: str, kappa: float, unsupported: set[str] | None = None) -> None:
        self.family = family
        self.kappa = kappa
        self._unsupported = unsupported or set()

    def entails(self, claim: str, context: str) -> bool:
        return claim not in self._unsupported


# -- G2: oracle ceiling + attribution --------------------------------------------------


def test_oracle_ceiling_is_a_rate_with_an_interval() -> None:
    result = oracle_context_ceiling([True, True, True, False])
    assert result.stage is Stage.oracle_ceiling and result.gates
    (metric,) = result.metrics
    assert metric.name == "generation_accuracy_given_gold"
    assert abs(metric.interval.estimate - 0.75) < 1e-9
    assert metric.interval.method.value == "wilson"


def test_attribution_reports_shares_of_the_three_buckets() -> None:
    failures = [FailureStage.not_retrieved] * 5 + [FailureStage.ranked_beyond_k] * 3 + [FailureStage.misread] * 2
    result = failure_attribution(failures)
    shares = {m.name: m.interval.estimate for m in result.metrics}
    assert set(shares) == {"not_retrieved", "ranked_beyond_k", "misread"}
    assert abs(shares["not_retrieved"] - 0.5) < 1e-9
    assert abs(shares["ranked_beyond_k"] - 0.3) < 1e-9


def test_attribution_with_no_failures_is_empty_not_a_crash() -> None:
    result = failure_attribution([])
    assert result.gates and result.metrics == ()


# -- G3: faithfulness, and its M4 dependency -------------------------------------------


def _answers() -> list[FaithfulnessAnswer]:
    return [
        FaithfulnessAnswer(claims=("a", "b"), context="ctx"),
        FaithfulnessAnswer(claims=("c", "bad"), context="ctx"),  # 'bad' is unsupported
    ]


def test_faithfulness_is_pending_without_the_m4_judge() -> None:
    result = faithfulness(_answers(), judge=None, kappa_gate=0.6)
    assert result.status == "pending"
    assert result.pending_reason is not None and "M4" in result.pending_reason
    assert result.metrics == ()


def test_faithfulness_refuses_a_same_family_judge() -> None:
    judge = _Judge(family="model-A", kappa=0.9)
    result = faithfulness(_answers(), judge=judge, kappa_gate=0.6, generator_family="model-A")
    assert result.status == "pending" and "CROSS-family" in (result.pending_reason or "")


def test_faithfulness_reports_both_numbers_when_calibrated() -> None:
    judge = _Judge(family="model-B", kappa=0.8, unsupported={"bad"})
    result = faithfulness(_answers(), judge=judge, kappa_gate=0.6, generator_family="model-A")
    assert result.gates
    names = {m.name: m.interval.estimate for m in result.metrics}
    # 3 of 4 claims entailed -> mean faithfulness 0.75; 1 of 2 answers has an unsupported claim -> 0.5
    assert abs(names["mean_faithfulness"] - 0.75) < 1e-9
    assert abs(names["answers_with_unsupported_claim"] - 0.5) < 1e-9


def test_faithfulness_below_the_kappa_gate_is_measured_but_does_not_gate() -> None:
    judge = _Judge(family="model-B", kappa=0.3, unsupported={"bad"})
    result = faithfulness(_answers(), judge=judge, kappa_gate=0.6)
    assert result.status == "measured_nongating" and result.gates is False
    assert result.metrics  # the numbers are still reported
    assert "does NOT gate" in result.detail


# -- G7 / G6 / G8 ----------------------------------------------------------------------


def test_distractor_robustness_is_a_rate() -> None:
    result = distractor_robustness([True, False, True, True])
    (metric,) = result.metrics
    assert metric.name == "accuracy_with_distractors" and abs(metric.interval.estimate - 0.75) < 1e-9


def test_unanswerables_report_false_answer_and_over_abstention_separately() -> None:
    result = unanswerable_handling(
        answered_when_unanswerable=[True, False, False, False],  # 1/4 hallucinated an answer
        abstained_when_answerable=[True, False],  # 1/2 wrongly abstained
    )
    names = {m.name: m.interval.estimate for m in result.metrics}
    assert abs(names["false_answer_rate"] - 0.25) < 1e-9
    assert abs(names["over_abstention_rate"] - 0.5) < 1e-9


def test_citation_precision_and_recall() -> None:
    items = [
        CitationItem(cited_ids=("p1", "p2"), supporting_ids=("p1", "p3")),  # 1 correct of 2 cited; 1 of 2 supporting
    ]
    result = citation_quality(items)
    names = {m.name: m.interval.estimate for m in result.metrics}
    assert abs(names["citation_precision"] - 0.5) < 1e-9
    assert abs(names["citation_recall"] - 0.5) < 1e-9


# -- no single blended score -----------------------------------------------------------


def test_render_lists_each_stage_separately_with_no_total() -> None:
    judge = _Judge(family="model-B", kappa=0.8)
    stages = [
        oracle_context_ceiling([True, False]),
        failure_attribution([FailureStage.not_retrieved]),
        faithfulness([FaithfulnessAnswer(("a",), "ctx")], judge=None, kappa_gate=0.6),
        distractor_robustness([True]),
    ]
    text = render(stages)
    lines = text.splitlines()
    assert len(lines) == 4
    assert any(line.startswith("PENDING") and "faithfulness" in line for line in lines)
    # there is no blended "overall RAG score" anywhere
    assert "overall" not in text.lower() and "blended" not in text.lower()


def test_there_is_no_blended_score_function() -> None:
    import evalloop.grade.rag_stages as mod

    for forbidden in ("overall", "blended", "rag_score", "composite"):
        assert not hasattr(mod, forbidden)
