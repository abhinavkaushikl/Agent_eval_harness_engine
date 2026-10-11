# EvalLoop session summary

Run `run-003`.

## 1. What you built

- `code_generation` (confidence 0.90)
- `rare_class` (confidence 0.55)

Stated intent: add a discount helper

## 2. What was evaluated and how

The plan:

```
READY        A1_execution_based · C1_wilson_ci
PENDING      C3_repeat_runs              needs runs: 5, have 0
             D1_pr_curve_never_accuracy  needs positives: 100, have 0
UNAVAILABLE  H8_flaky_classification     missing: snapshot_restore
PROHIBITED   D1_pr_curve_never_accuracy  rare_class: Predicting "all good" scores 97% accuracy with 0% recall, and ROC-AUC also looks flattering under imbalance
```

Evaluated:

| Technique | Rung | Oracle |
|---|---|---|
| A1_execution_based | 1 (execution) | HIGH |

## 3. Findings

**A1_execution_based**
- 50.0% [15.0, 85.0]  n=4 · failed 2: wrong_result 1, timeout 1 (wall_clock) · inconclusive 1 · [HIGH oracle]
    - inconclusive: src/pricing.py — network egress was refused

Per-item changes since run `run-prev`:

Regressions (1):
- src/pricing.py [c3] (A1_execution_based): passed → failed/wrong_result
Improvements (1):
- src/pricing.py [c2] (A1_execution_based): failed/wrong_result → passed

## 4. What is not yet answerable, and what would unlock it

Not enough evidence yet (the bar is the methodology's, the count is this run's):

- `C3_repeat_runs` needs runs: 5, have 0
- `D1_pr_curve_never_accuracy` needs positives: 100, have 0

Needs a tool or permission not available here:

- `H8_flaky_classification` needs a restorable environment snapshot

## 5. What was prohibited, and why

The methodology forbids these here, with the reason:

- `D1_pr_curve_never_accuracy` rare_class: Predicting "all good" scores 97% accuracy with 0% recall, and ROC-AUC also looks flattering under imbalance

## 6. Cost

LLM spend: $0.0123.
