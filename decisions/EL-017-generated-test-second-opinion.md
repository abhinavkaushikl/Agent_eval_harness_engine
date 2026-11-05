# EL-017 — A generated test's failure needs a second, independent test to stand

## Decision

When a generated (LOW) test fails against the code, EvalLoop writes a **second test independently**,
from the same signature-only view, and runs it:

| Second test | First test's failures |
|---|---|
| also fails, or decides nothing | stand (`failed`) |
| passes every check | withheld (`inconclusive`): "the two disagree, so this may be the test's mistake" |
| could not be written | stand, noted as uncorroborated |

The second test only adjudicates. Its cases are not added to the run.

## Why

A generated test sees only the signature (AGENT.md §3.6), so its failure has two explanations: the
code is wrong, or the test expected something the spec never said. In a live Groq run, 2–4 of every
~50 generated tests failed for the second reason, for example asserting `isinstance(add(1, 2), float)`
or `nan == nan`, and each one made the run read PROBLEM. The corpus's answer to a single unchecked
grader is an independent second one, with disagreements resolved before anything counts
(A:211: "Two qualified experts independently grade ... and a third resolves their disagreements").

## Limits, stated

- **Withhold only.** Disagreement turns a failure into *inconclusive*, never into a pass, so a
  wrong second test can hide a finding but cannot certify code.
- **Agreement is corroboration, not proof.** Both tests come from the same model and the same view,
  so they can share a mistake. Run 3 of the live check kept one such failure: both tests read
  `-> float` as "must return a float". `tests/test_run_driver.py` asserts this limit explicitly.
- **A passing second test may not cover the same behaviour.** Its pass is weaker evidence than a
  direct contradiction, which is one reason disagreement is a withhold and not a reversal.
- **Cost.** One extra generation per function with a generated failure, counted in the session's
  spend and capped by `--budget`.
- A cross-family second author (F5) would weaken the shared-mistake problem. It needs a second
  provider's credential and is not done.
