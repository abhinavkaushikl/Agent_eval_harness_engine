"""recall@k, and the faithfulness gate enforced through readiness (requires), not unlocks (F8 trap).

The load-bearing proofs: recall@k is measured at the real k against a fixture index (no live store),
reported with its Wilson interval and naming the embedding model; G3_faithfulness is PENDING on
`recall_at_k_measured: true` before recall@k runs; and once recall@k runs, that gate clears. The gate
rides on `requires`, not on G1's `unlocks` — which the registry has but which gates nothing.
"""

from __future__ import annotations

from evalloop.grade.rag_recall import (
    FAITHFULNESS_RECORD_ID,
    RECALL_FACT,
    RecallAtK,
    RecallQuery,
    evidence_after,
    faithfulness_readiness,
    faithfulness_record,
    measure_recall_at_k,
)


class _FixtureIndex:
    """A read-only fixture index: a prebuilt ranked list per query. No vector store, no network."""

    def __init__(self, ranked: dict[str, list[str]]) -> None:
        self._ranked = ranked

    def retrieve(self, query: RecallQuery, k: int) -> list[str]:
        return self._ranked.get(query.query_id, [])[:k]


_QUERIES = [
    RecallQuery("q1", gold_ids=("p1",), text="first"),
    RecallQuery("q2", gold_ids=("p2",), text="second"),
    RecallQuery("q3", gold_ids=("p3",), text="third"),
    RecallQuery("q4", gold_ids=("p4",), text="fourth"),
]

# q4's gold (p4) is ranked 6th, so it is missed at k=5: recall@5 = 3/4.
_RANKED = {
    "q1": ["p1", "x", "y", "z", "w"],
    "q2": ["a", "p2", "b", "c", "d"],
    "q3": ["e", "f", "p3", "g", "h"],
    "q4": ["i", "j", "k", "l", "m", "p4"],
}


def _measure(k: int = 5) -> RecallAtK:
    return measure_recall_at_k(_QUERIES, k=k, embedding_model="text-embedding-3-small", retriever=_FixtureIndex(_RANKED))


# -- recall@k at the real k, with its interval and model -------------------------------


def test_recall_at_k_is_measured_at_the_real_k() -> None:
    result = _measure(k=5)
    assert result.k == 5
    assert (result.retrieved_gold, result.total_gold) == (3, 4)
    assert abs(result.recall - 0.75) < 1e-9


def test_recall_changes_with_k() -> None:
    # at k=6, q4's gold (ranked 6th) is now retrieved: recall@6 = 4/4
    assert _measure(k=6).recall == 1.0
    assert _measure(k=5).recall == 0.75


def test_recall_names_the_embedding_model_and_carries_a_wilson_interval() -> None:
    result = _measure()
    assert result.embedding_model == "text-embedding-3-small"
    assert result.interval.method.value == "wilson"
    assert result.interval.lower <= result.recall <= result.interval.upper
    assert "text-embedding-3-small" in result.describe() and "recall@5" in result.describe()


def test_recall_requires_an_embedding_model_and_gold() -> None:
    import pytest

    with pytest.raises(ValueError):
        measure_recall_at_k(_QUERIES, k=5, embedding_model="  ", retriever=_FixtureIndex(_RANKED))
    with pytest.raises(ValueError):
        measure_recall_at_k([RecallQuery("q", gold_ids=())], k=5, embedding_model="m", retriever=_FixtureIndex({}))


# -- the gate: faithfulness is PENDING until recall@k is measured ----------------------


def test_faithfulness_is_pending_before_recall_at_k() -> None:
    readiness = faithfulness_readiness(evidence_after(None))
    assert readiness.met is False
    assert readiness.reason is not None
    assert f"{RECALL_FACT}: true, have false" in readiness.reason


def test_recall_at_k_clears_the_gate() -> None:
    result = _measure()
    before = faithfulness_readiness(evidence_after(None))
    after = faithfulness_readiness(evidence_after(result))
    # before: blocked on recall; after: that clause is gone (claim_labels may still be pending)
    assert before.reason is not None and RECALL_FACT in before.reason
    assert after.reason is None or RECALL_FACT not in after.reason


def test_the_fact_exists_only_after_the_measurement() -> None:
    # The fact is a property of the result object, which cannot exist before recall@k runs.
    result = _measure()
    assert result.session_fact == {RECALL_FACT: True}
    assert evidence_after(None) == {}  # no measurement → no fact


# -- F8: the gate is requires, not unlocks ---------------------------------------------


def test_the_gate_is_requires_not_unlocks() -> None:
    record = faithfulness_record()
    assert record.id == FAITHFULNESS_RECORD_ID
    # the real gate lives in requires ...
    assert record.requires.get(RECALL_FACT) is True
    # ... and evaluate_readiness (which reads requires) is what blocks it — proven above. unlocks on
    # G1 is not consulted here at all: we never read G1.unlocks to decide faithfulness.
