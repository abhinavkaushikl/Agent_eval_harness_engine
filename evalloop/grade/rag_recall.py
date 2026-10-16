"""Measure retrieval recall@k, and make faithfulness unable to run until recall@k has been measured.

Corpus G1: compute recall@k **at the k you actually pass to the generator** — recall@20 is irrelevant
if the prompt receives 5. The build order is recall@k → gold-context ceiling → attribution →
faithfulness, because "end-to-end accuracy is about recall@k times generator-given-gold, so fix the
lower factor first." A recall number is meaningless without the embedding model it was measured
against (G1), so this module names both the model and the k in every result.

The gate, and the trap (F8)
---------------------------
Faithfulness must refuse to run before recall@k. The registry *looks* like it encodes this —
``G1`` ``unlocks`` ``G3_faithfulness`` — but **``unlocks`` is read by no planner step**, so that edge
gates nothing. The gate that works is ``G3_faithfulness``'s ``requires: {recall_at_k_measured:
true}``, checked by :func:`evaluate_readiness`. EL-213 already turns an unmet requirement into a
PENDING reason. So:

  * this module sets ``recall_at_k_measured: true`` **only after** :func:`measure_recall_at_k` has
    actually run (it is a property of the result object, which cannot exist beforehand);
  * :func:`faithfulness_readiness` evaluates ``G3``'s ``requires`` against the evidence, so before the
    measurement it is PENDING "needs recall_at_k_measured: true, have false", and after it the recall
    gate is cleared.

**The mechanism used is readiness via ``requires``, not ``unlocks``** — relying on ``unlocks`` would
let faithfulness run first and make the gate a lie.

recall@k is computed against an injected index (a `Retriever`), so a fixture index needs no live
vector store. Faithfulness itself, the oracle-context ceiling, attribution, robustness and
unanswerables are EL-313.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from evalloop.plan.readiness import Readiness, evaluate_readiness
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.registry.schema import TechniqueRecord
from evalloop.stats.proportions import DEFAULT_CONFIDENCE, Interval, wilson_interval

__all__ = [
    "RECALL_RECORD_ID",
    "FAITHFULNESS_RECORD_ID",
    "RECALL_FACT",
    "RecallQuery",
    "RecallAtK",
    "Retriever",
    "measure_recall_at_k",
    "faithfulness_record",
    "faithfulness_readiness",
    "evidence_after",
]

RECALL_RECORD_ID = "G1_component_wise_eval"
FAITHFULNESS_RECORD_ID = "G3_faithfulness"
RECALL_FACT = "recall_at_k_measured"  # the session fact G3 requires; set true only once recall@k runs


@dataclass(frozen=True, slots=True)
class RecallQuery:
    """One retrieval query: its id, optional text, and the gold passage ids that should be retrieved."""

    query_id: str
    gold_ids: tuple[str, ...]
    text: str = ""


@runtime_checkable
class Retriever(Protocol):
    """Whatever returns ranked passage ids for a query at a given k — a fixture index, or a live store."""

    def retrieve(self, query: RecallQuery, k: int) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class RecallAtK:
    """recall@k at the real k, with its Wilson interval and the embedding model it was measured against.

    recall is micro-averaged over gold passages: a trial per (query, gold passage), success when that
    gold passage is in the query's top-k. ``session_fact`` exists only because this object does — i.e.
    because the measurement ran.
    """

    k: int
    embedding_model: str
    retrieved_gold: int
    total_gold: int
    interval: Interval

    @property
    def recall(self) -> float:
        return self.interval.estimate

    @property
    def session_fact(self) -> dict[str, bool]:
        """The fact that clears G3's recall gate — produced only after recall@k has been measured."""
        return {RECALL_FACT: True}

    def describe(self) -> str:
        return (
            f"recall@{self.k} = {self.recall:.3f} "
            f"[{self.interval.lower:.3f}, {self.interval.upper:.3f}] "
            f"(embedding: {self.embedding_model}; {self.retrieved_gold}/{self.total_gold} gold passages, "
            f"{self.interval.confidence:.0%} {self.interval.method.value})"
        )


def measure_recall_at_k(
    queries: Sequence[RecallQuery],
    *,
    k: int,
    embedding_model: str,
    retriever: Retriever,
    confidence: float = DEFAULT_CONFIDENCE,
) -> RecallAtK:
    """recall@k at the real k, over an injected retriever. Names the embedding model; carries a Wilson CI."""
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    if not embedding_model.strip():
        raise ValueError("recall@k must name the embedding model it was measured against (G1)")
    retrieved_gold = 0
    total_gold = 0
    for query in queries:
        top_k = list(retriever.retrieve(query, k))[:k]
        got = set(top_k)
        for gold in query.gold_ids:
            total_gold += 1
            if gold in got:
                retrieved_gold += 1
    if total_gold == 0:
        raise ValueError("no gold passages to measure recall against; every query must carry a gold id")
    interval = wilson_interval(retrieved_gold, total_gold, confidence)
    return RecallAtK(k, embedding_model, retrieved_gold, total_gold, interval)


# -- the faithfulness gate, enforced through readiness (requires), not unlocks ----------


def faithfulness_record() -> TechniqueRecord:
    """The G3_faithfulness record from the registry, whose ``requires`` is the real gate."""
    for record in load_records(RECORDS_DIR):
        if record.id == FAITHFULNESS_RECORD_ID:
            return record
    raise LookupError(f"{FAITHFULNESS_RECORD_ID} is not in the registry")


def faithfulness_readiness(evidence: Mapping[str, object]) -> Readiness:
    """Is faithfulness allowed to run, given the evidence? PENDING until recall@k has been measured."""
    return evaluate_readiness(faithfulness_record(), evidence)


def evidence_after(recall: RecallAtK | None, *, extra: Mapping[str, object] | None = None) -> dict[str, object]:
    """Build the evidence mapping readiness reads: the recall fact is present only if recall@k ran."""
    evidence: dict[str, object] = dict(extra or {})
    if recall is not None:
        evidence.update(recall.session_fact)
    return evidence
