# EVALS – SECTION DEEP DIVES
### Index

[evals-situation-to-technique.md](evals-situation-to-technique.md) is the quick lookup. The ten files below go deeper on each of its sections.

| File | Covers | Read it when |
|---|---|---|
| [A-choosing-how-to-grade.md](A-choosing-how-to-grade.md) | Execution grading, end-state verification, normalised exact match, binary-rubric LLM judge, field-level scoring, expert review, tiered online scoring | You have outputs and are about to write `==` or "ask a model if it's good" |
| [B-comparing-two-things.md](B-comparing-two-things.md) | Paired bootstrap, pairwise judging with swap, McNemar, Bradley–Terry, leaderboard CIs, cluster bootstrap | You need to say whether version B beats version A |
| [C-deciding-whether-a-result-is-real.md](C-deciding-whether-a-result-is-real.md) | Wilson CIs, power analysis, multi-run variance, rule of three, multiple-comparison correction, permutation tests | Someone says "+3 points" and you have to decide whether to believe it |
| [D-rare-events.md](D-rare-events.md) | PR curves and PR-AUC, precision floors, cost-based thresholds, red-team ASR, upper confidence bounds | The bad thing is under 5% of traffic and accuracy says 97% |
| [E-when-a-number-looks-wrong.md](E-when-a-number-looks-wrong.md) | Per-item diffs, distribution checks, length control, A/A baselines, harder sets, oracle runs, contamination checks | A score jumped, fell to 0% or went up with no effect on users |
| [F-trusting-your-grader.md](F-trusting-your-grader.md) | Human gold labels, Cohen's κ, Krippendorff's α, position and self-preference bias, binary criteria, calibrating human raters | You built a judge, or your labellers disagree |
| [G-rag-systems.md](G-rag-systems.md) | Retrieval vs generation split, stage attribution, faithfulness, nDCG and MRR, unanswerable sets, citation precision | Your RAG answers are wrong and you don't know which stage failed |
| [H-agents.md](H-agents.md) | Sandboxed environments, outcome grading, pass^k, cost per success, milestones, prompt-injection testing, trace review | An agent says "done" and you need to know whether it's true, every time |
| [I-production.md](I-production.md) | CI gates, flaky-eval handling, error analysis, canary drift checks, online evals, A/B tests, shadow and canary deployment | You're shipping, or it's live and you need to know it still works |
| [J-choosing-a-model.md](J-choosing-a-model.md) | Constraint filtering, smoke tests, domain evals, cost–quality Pareto frontier, normalising benchmarks, checking vendor claims | You have to pick or replace a model |

---

## Suggested reading order

- **Starting out:** A → C → F. First how to grade, then whether a number is real, then whether the grader can be trusted.
- **Shipping something:** A → B → I. Grade it, compare it with what's live, then gate it and monitor it.
- **Building RAG:** A → G → F. Grade each component, split retrieval from generation, then validate the faithfulness judge.
- **Building agents:** A2 → H → C. Verify the end state, check reliability with pass^k, then measure run-to-run variance.
- **Buying a model:** J → B → E. Shortlist, compare on paired items, then check for contamination and benchmark gaming.
- **Something is broken right now:** E first, organised by symptom. Then F if the grader is the suspect, or I if production has drifted.

---

## The five things that appear in every single section

1. **If you can execute the output or check it against the real world, do that instead of judging it.** Run the SQL, query the database, validate the checksum. A judge is the fallback.
2. **Put a confidence interval on every number.** If two intervals overlap, you haven't shown a difference.
3. **Use the same items on both sides of every comparison.** Pairing removes item-difficulty noise, which gives you statistical power at no extra cost.
4. **Slice the results.** The average always hides the one language, intent or field you actually need to know about.
5. **Turn every production failure into a permanent test case.** That's the flywheel: each incident makes the eval harder to fool next time.
