# EL-313 — RAG ladder stages, each reported separately

**⚠ Depends on EL-312 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_rag_stages.py` 12 passed; `mypy --strict evalloop/` clean on 60
files; standard library only. Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/grade/rag_stages.py` | `oracle_context_ceiling`, `failure_attribution`, `faithfulness`, `distractor_robustness`, `unanswerable_handling`, `citation_quality`, `render`; types `Stage`, `FailureStage`, `Metric`, `StageResult`, `FaithfulnessJudge`, `FaithfulnessAnswer`, `CitationItem` |
| `tests/test_rag_stages.py` | 12 tests |

## 2. The result — six requirements
| # | Requirement | How |
|---|---|---|
| 1 | Oracle-context ceiling (G2): feed gold, measure the generator's ceiling | `oracle_context_ceiling(correct_given_gold)` → `generation_accuracy_given_gold` rate + Wilson |
| 2 | Per-failure attribution (G2): not_retrieved / ranked_beyond_k / misread, as SHARES of failures | `failure_attribution(failures)` → a share (with interval) for each of the three buckets, over the failure count, so the backlog ranks by impact |
| 3 | Faithfulness (G3): BOTH mean faithfulness AND % of answers with ≥1 unsupported claim | `faithfulness(...)` decomposes answers into claims, judges entailment, reports `mean_faithfulness` (micro over claims) AND `answers_with_unsupported_claim` (over answers) — the second is what users feel |
| 4 | Distractor robustness (G7); unanswerables (G6: false-answer rate AND over-abstention); citation P/R (G8) | `distractor_robustness`; `unanswerable_handling` → `false_answer_rate` AND `over_abstention_rate` as two separate pools/rates; `citation_quality` → `citation_precision` AND `citation_recall` (micro) |
| 5 | Each stage its own line, each number with its interval; no single blended score | every `Metric` carries an `Interval`; `render` prints one line per stage; **there is no aggregate function** — a test asserts no `overall`/`blended`/`rag_score`/`composite` symbol exists |
| 6 | The faithfulness judge is CROSS-FAMILY and calibrated; below the κ gate it does not gate | a same-family judge → PENDING (self-preference); `κ < kappa_gate` → status `measured_nongating` (numbers reported, `gates` is False); `κ ≥ gate` → gating |

## 3. The cross-track dependency, stated honestly (M4)
Faithfulness **consumes** M4's judge and its κ calibration gate; it does not build them (out of scope).

- **No judge (M4 not landed) → PENDING** with the reason "needs M4's cross-family calibrated judge",
  never a bare number, never silently skipped (tested).
- **`kappa_gate` is a required argument**, not defaulted — inventing a trust threshold is exactly the
  dishonesty EvalLoop forbids. The caller (M4's calibration policy) supplies it.
- The `FaithfulnessJudge` protocol carries `family` and `kappa`; this stage reads them, it does not
  compute κ (that is F1/M4).

## 4. Full-suite note
`pytest` 1331 passed, 2 skipped, 1 failed — the F-G1a `testcases running/` demo-folder finding,
unrelated to EL-313.

## 5. Rulings I need
1. Accept building ahead of Gate 1.
2. **`measured_nongating`** (§2 req 6): below the κ gate I still compute and report the numbers but
   flag them non-gating. Confirm that is the behaviour you want (vs. withholding the numbers entirely).
3. **Attribution tags are supplied, not inferred** (§2.2): the caller tags each failure
   not_retrieved / ranked_beyond_k / misread (using recall@k + the oracle ceiling); this module
   aggregates them into shares. If you want EL-313 to *derive* the tag from recall + ceiling evidence,
   that is a larger piece — say so.
4. **Citation precision/recall is micro** across answers. Say if you want macro (mean of per-answer
   P/R) instead.
