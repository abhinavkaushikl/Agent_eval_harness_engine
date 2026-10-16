# EL-312 — RAG recall@k + the faithfulness gate

**⚠ Depends on EL-309 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_rag_recall.py` 8 passed; `mypy --strict evalloop/` clean on 59
files; standard library only. Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/grade/rag_recall.py` | `measure_recall_at_k`, `RecallAtK`, `RecallQuery`, `Retriever`, `faithfulness_readiness`, `faithfulness_record`, `evidence_after` |
| `tests/test_rag_recall.py` | 8 tests against a fixture index built in-process (no vector store) |

## 2. The result — four requirements
| # | Requirement | How |
|---|---|---|
| 1 | recall@k at the real k, with its CI, naming the embedding model and k | `measure_recall_at_k(queries, k=…, embedding_model=…, retriever=…)` micro-averages over gold passages (a trial per (query, gold)), returns `RecallAtK(k, embedding_model, retrieved_gold, total_gold, interval=wilson)`. `describe()` renders `recall@5 = 0.750 [.., ..] (embedding: …)`. A blank model or no gold raises |
| 2 | G3_faithfulness is PENDING on `recall_at_k_measured` before recall@k runs | `faithfulness_readiness({})` → not met, reason `needs recall_at_k_measured: true, have false` (tested) |
| 3 | After recall@k runs, the fact is set and faithfulness is no longer blocked on it | `evidence_after(result)` carries `{recall_at_k_measured: True}`; `faithfulness_readiness` no longer names the recall clause (claim_labels may still be pending — a different bar) |
| 4 | recall@k against a fixture index, no live store | the test's `_FixtureIndex` returns a prebuilt ranked list per query |

## 3. The mechanism — readiness via `requires`, NOT `unlocks` (F8)
**I used readiness.** The registry has `G1 unlocks [… G3_faithfulness …]`, but **`unlocks` is read by no
planner step**, so that edge gates nothing — the F8 trap. The gate that works is
`G3_faithfulness.requires = {recall_at_k_measured: true, claim_labels: 150}`, evaluated by
`evaluate_readiness` (EL-213's PENDING renderer reads the same unmet requirement).

- `recall_at_k_measured` is a **session fact**, exposed only as `RecallAtK.session_fact` — a property
  of the result object, which cannot exist until `measure_recall_at_k` has actually run. So the fact
  is set true *only after* recall@k runs, as the ticket demands.
- A test (`test_the_gate_is_requires_not_unlocks`) asserts the gate lives in `record.requires`, and
  the blocking is done by `evaluate_readiness`; G1's `unlocks` is never read to decide faithfulness.

Had I relied on `unlocks`, faithfulness would run first and the gate would be a lie.

## 4. Full-suite note
`pytest` 1331 passed, 2 skipped, 1 failed — the F-G1a `testcases running/` demo-folder finding,
unrelated to EL-312.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **Micro-averaged recall** (§2.1): recall@k is retrieved-gold / total-gold across queries (a trial
   per gold passage), which gives a clean proportion for Wilson. If you want per-query hit@k
   (success = any gold in top-k, one trial per query) instead, say so — it changes what the interval
   is over. The independence caveat (multiple gold passages per query are not independent trials) is
   noted.
3. **`claim_labels: 150`** remains a second gate on G3 (F1 gold-label validation); EL-312 only clears
   the recall clause. Confirm that split is what you expect.
