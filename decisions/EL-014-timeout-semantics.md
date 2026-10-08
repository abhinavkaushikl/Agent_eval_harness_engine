# EL-014 — Timeout semantics: a failure, logged separately

## Decision

A timeout is a failure of the artifact — verdict `failed`, failure class `timeout` — that
counts in every pass rate and is always reported apart from wrong answers, and
`inconclusive` is reserved for runs in which the evaluation, not the artifact, failed.

The ticket's four questions, answered:

**1. The members, as EL-206 writes them.** There are two enums, both `evalloop._compat.StrEnum`.
Like every vocabulary in the repo, each member's value equals its lowercase name.

| Enum | Members | Note |
|---|---|---|
| `Verdict` | `passed` · `failed` · `inconclusive` | Not `pass`/`fail`: `pass` is a Python keyword, so it cannot be a member name |
| `FailureClass` | `syntax_error` · `unknown_column` · `runtime_error` · `wrong_result` · `timeout` | A:39's four classes verbatim, plus A:37's timeout. A run has a class **if and only if** its verdict is `failed` |

An `inconclusive` verdict carries a required, non-empty reason and no failure class. A `timeout`
records which cap was hit and the value in force. Choosing that value is EL-015's job.

How an M1 run maps onto them (Python; EL-206 runs, EL-207 grades):

| What happened | Verdict · class |
|---|---|
| The tests ran and passed | `passed` |
| The wall-clock cap **or the CPU-time cap** was hit | `failed` · `timeout` |
| The artifact did not import or compile | `failed` · `syntax_error` — `PLAN.md` T12's "compile/logic split" |
| An uncaught exception, including a kill at the memory, file-size or open-files limit | `failed` · `runtime_error`, naming the limit |
| The tests ran and an assertion failed | `failed` · `wrong_result` |
| The sandbox could not start, a capability the run needs was denied (network — `ARCHITECTURE.md:379`), or the oracle itself could not run | `inconclusive`, with that reason |

`unknown_column` is SQL's. It first occurs in Track V.

**2. The denominator.** Pass rate = `passed / (passed + failed)`. A timeout is always in the
denominator and never in the numerator. An `inconclusive` run is in neither, and its count is
printed beside every number it was left out of.

The same rule holds wherever a verdict is counted:
- **C1's Wilson n** includes timeouts.
- **B3's discordant pairs:** an item that timed out under one version and passed under the
  other is discordant.
- **H3's pass^k:** a timed-out trial is a failed trial.
- **H8's buckets:** a task that times out in some trials is flaky, exactly as at H:274.

A paired comparison drops an item that is `inconclusive` on either side, and says how many it
dropped.

**3. What `summary.md` shows.** `USER_EXPERIENCE.md:66` asks for INCONCLUSIVE to be "shown
distinctly from fail", but that line sits in §3.2, the dashboard. The `summary.md` section,
§3.4, says nothing either way. This decision applies the rule to `summary.md` and extends it
to timeouts:

- every rate prints its n, which includes timeouts, and its inconclusive count, even when
  that count is zero;
- failures are listed by class, and `timeout` is never folded into another class — it is
  printed with the cap that was in force;
- every `inconclusive` run is listed with its reason.

An illustration, not a layout (EL-211 owns the layout). Twelve tests, of which 7 passed, 3
gave wrong results and 2 hung:

```
A1_execution_based   58.3% [32.0, 80.7]  n=12 · failed 5: wrong_result 3, timeout 2 (<cap>) · inconclusive 0
```

Under the rule this replaces, the same run reads 7 of 10. The two hangs simply vanish.

**4. Which docs become stale.** All three docs the ticket names do, in four lines:
`AGENT.md:150` (§3.7), `AGENT.md:199` (§5), `ARCHITECTURE.md:378` (§9) and `PLAN.md:44`
(T11).

Three more lines state the same rule and would have sent EL-206 the wrong way:
`DEVELOPMENT_PLAN.md:135`, `TASKS.md:356` and `TASKS.md:358`.

All seven are edited in this ticket. `USER_EXPERIENCE.md:66` is not stale.

## Status

Accepted — 2026-10-09.

**This decision overrules our docs; it does not reconcile them.** `AGENT.md:199` says a
timeout is "Not a failure, not a pass". This decision says it *is* a failure, of a named
kind. It is the ticket's "third answer", and it is adopted for what it is:

- **Kept from the corpus, to the letter:** A:37's rule — count a timeout as a failure, and
  log it separately.
- **Kept from the docs:** how a timeout is *presented*. It is never a pass, never shown as a
  wrong answer, and never hidden.
- **Dropped from the docs:** what a timeout *means*. "Not a failure" does not survive.

`USER_EXPERIENCE.md:66` survives intact, because `inconclusive` still exists, with the
narrower meaning above.

Two claims made in the ticket do not survive checking. The decision rests on neither.

1. *"CLAUDE.md section 3 says the corpus wins where a doc disagrees."* **It does not.** The
   nearest row in §3 is "Never invent a number. Thresholds are copied verbatim from the source
   or set to `null`" (`CLAUDE.md:49`).

   Corpus precedence is stated elsewhere: in the E1 ticket set ("Where two docs disagree on a
   number, neither decides — the corpus file does", `E1-M0-TICKETS-AND-PROMPTS.md:82`) and in
   this session's preamble. Both apply to *numbers*. Whether a timeout counts as a failure is
   not a number, so no precedence rule decides it. The merits decide it, set out below, and
   they come out where the corpus is.
2. *"E6's worked example cuts the other way … the logging is the only thing that saved it."*
   **It cuts the same way.** The corpus itself scores that run "0/50" (E:218): its 50 timeouts
   counted as 50 failures. And what found the bug was not a log but the oracle: "The scripted
   oracle also scored 0/50" (E:219).

   E6 sends you to the harness logs *after* the oracle has failed (E:211). E6 is an argument
   for running the oracle before believing a 0%, not for taking timeouts out of the score.

## Context

The verdict reaches code in this epic:
- EL-206 writes `verdict.py`;
- EL-201 persists the verdict;
- EL-207 scores it;
- EL-211 renders it.

Until this is settled, the episodic store from EL-202 keeps verdicts as unvalidated text
(`evalloop/memory/episodic.py`, module docstring). EL-206's own done-when line,
`DEVELOPMENT_PLAN.md:135` — "Timeout → INCONCLUSIVE" — is the whole conflict in miniature.

**Before this ticket, our docs said one thing, seven times, and cited nothing:** `AGENT.md:150`, `AGENT.md:199`,
`ARCHITECTURE.md:378`, `PLAN.md:44`, `DEVELOPMENT_PLAN.md:135`, `TASKS.md:356` and
`TASKS.md:358`. None named a corpus section, although the rows on either side of
`ARCHITECTURE.md:378` each do. The rule was ours.

**The corpus says the opposite, in three places, consistently:**

- **A1 states it as a rule** (A:37), next to the failure classes a timeout sits beside (A:39).
- **E6 shows it in practice.** A run of timeouts is scored as failures (E:218), diagnosed with
  the oracle (E:219), and only then are the harness logs read (E:211). E6 also says a 0% "is
  usually a timeout, tool-schema or environment bug" (E:206).
- **H8 depends on it.** H8 buckets tasks by pass count, and its worked example works only
  because timed-out trials count as failures. 27 tasks came out flaky because a pagination API
  "timed out 2% of the time per page" (H:274). Had those trials been inconclusive, the 27 tasks
  would have bucketed as "always", and the pagination-retry fix would never have been found.

The corpus separates a broken harness from a broken artifact with a check of its own, the
oracle run (E:203, H:267, H:301). It never does it by relabelling outcomes.

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **A. The docs as written: timeout → `inconclusive`, left out of every rate** | Nothing today; seven doc lines already say it | A slow-but-correct artifact, or a broken harness, is never scored as the artifact's failure | Any one of four reasons is enough:<br>1. It contradicts A:37.<br>2. **Hanging scores better than answering.** On an item the artifact cannot solve, a wrong answer lowers the rate, but a hang leaves it untouched. An agent that iterates against the grader learns to hang. That is the failure `DEVELOPMENT_PLAN.md:43` puts the MCP server last to avoid: "An agent iterating against a noisy grader learns to game it".<br>3. It hides exactly what H8 exists to find (H:274).<br>4. It under-reports the evidence. A run that did not finish inside its budget has shown a defect — A:37 calls it "a different bug" — and `AGENT.md:13`'s "Never claim more than the evidence supports" is not served by claiming less |
| **B. Timeout → `failed`, folded into `runtime_error` or `wrong_result`** | Nothing beyond A:39's four classes | One denominator | It breaks the second half of A:37, "log it separately", and its reason: "a slow correct query is a different bug from a wrong one". It would also turn E6's 50 timeouts into 50 wrong answers — the misreading E6 was written to prevent |
| **C. Timeout → `failed`, class `timeout`, in every rate, always shown apart** ✅ | One class; seven doc lines edited | A:37 to the letter. H8 and pass^k work unchanged. Nothing rewards hanging. E6's pattern shows up as a count of timeouts at a named cap | A timeout caused by the harness scores as the artifact's failure until an oracle runs (see Consequences). It overrules `AGENT.md:199`, as stated under Status |
| **D. `timeout` as a fourth verdict, counted as a failure by rule** | A flat enum | Simpler rendering | Every consumer must remember that `timeout` is a failure. One forgotten branch — in a rate, a McNemar count or an H8 bucket — silently brings back option A. As a failure *class*, a timeout cannot be counted at all without being counted as a failure |
| **E. Attribute each timeout: `failed` if a known-correct solution finishes under the cap, `inconclusive` if it times out too** | A known-correct solution for every item | E6, applied per item | M1 rarely has such a solution: harvested tests are oracles of behaviour, not solutions. And when the oracle fails, E6 does not relabel items. It says the harness is broken — "If the oracle doesn't score 100%, the harness is broken" (E:203) — and the score is not read until the harness is fixed. Relabelling item by item would report a score from a harness E6 calls broken |

## Consequences

**Easy:**
- EL-206 can write both enums without asking a follow-up question.
- Every rate has one denominator.
- McNemar, pass^k and the H8 buckets need no special case for timeouts.
- **Gate 1 catches a hang.** A deliberately broken function that loops forever comes out
  `failed`/`timeout`, which counts as caught (`PLAN.md:52`). Under the old rule it would have
  been `inconclusive`, which does not.

**Hard, and accepted:**

- **A timeout caused by the harness scores as the artifact's failure until the oracle runs.**
  E6's case is the example: a 30-second cap against a 90-second portal. The oracle run is M3's
  diagnostic (`PLAN.md:75`, T30 "E6 floor"); until then, Gate 1 runs it by hand (EL-212).
  Meanwhile the display rule keeps the case visible: a 0% made of timeouts reads as "timeout ×50
  at <cap>", not as a bare 0%.
- **A slow but correct artifact fails.** This is intended. A:37 calls slowness a bug, just "a
  different bug", and the failure class says which kind.
- **`inconclusive` has to be earned.** EL-206 and EL-207 may use it only when they can show the
  failure was the evaluation's.

  In particular, a network call that the sandbox refuses must be detectable as such. EL-206's
  ticket already requires it to fail "distinguishably from a logic failure"; otherwise it will
  surface as `runtime_error` and blame the artifact for a grant that was never given.

**Forecloses:** reading a timeout as "no evidence". Reversing this later means re-scoring every
stored run, because a rate computed under one rule cannot be compared with a rate computed under
the other.

## Evidence

From the corpus:

- **A:37** — "4. **Set resource limits.** Use a 10-second timeout and a row cap. Count a timeout
  as a failure but log it separately, because a slow correct query is a different bug from a
  wrong one."
- **A:39** — "6. **Log the failure class.** Tag each failure as a syntax error, unknown column,
  runtime error or wrong result. That gives you error analysis for free."
- **E:203** — "You feed a known-correct solution (a scripted perfect agent, the reference answers
  or a gold trajectory) through the same pipeline. If the oracle doesn't score 100%, the harness
  is broken."
- **E:206** — "A 0% score is usually a timeout, tool-schema or environment bug, and it gives you
  nothing to learn from."
- **E:211** — "3. **When it fails, read the harness logs:** timeouts, schema mismatches, missing
  environment state, grader parse errors."
- **E:218** — "**Output:** **0/50.** The team had started comparing larger models."
- **E:219** — "**Verdict:** The scripted oracle also scored 0/50. The harness had a **30-second
  timeout**, and the sandbox portal took **90 seconds** to confirm a booking. With the timeout
  raised to 180 seconds, the original model scored **34%**. The week spent comparing larger
  models had been spent on a timeout setting."
- **E:314** — "oracle fails → harness bug (timeout, schema, env)"
- **Master lookup :72** — "0/50 tasks. The oracle also fails 50/50 because of a 30 s timeout
  when tasks need 90 s."
- **H:261** — "Flaky tasks hide inside averages, where environment bugs look like model weakness."
- **H:267** — "4. **For "never" tasks, run the oracle** (E6) to separate harness bugs from real
  capability gaps."
- **H:274** — "58 always, **27 flaky**, 15 never. **All 27 flaky tasks called a carrier's
  pagination API**, which timed out 2% of the time per page, and those tasks needed 10–30 pages.
  Adding a retry on pagination moved 24 of the 27 to "always". The model hadn't been the cause."
- **H:328** — "Tool schemas, retries and timeouts often move success more than the model does, so
  version them, test them, and read the traces."

From our docs, as they read before this ticket edited them:

- **`AGENT.md:150`** — "Sandbox: subprocess + rlimits + timeout + tempdir, where timeout →
  **INCONCLUSIVE** (never pass/fail)." *(stale)*
- **`AGENT.md:199`** — "| Timeout = INCONCLUSIVE | Not a failure, not a pass |" *(stale)*
- **`ARCHITECTURE.md:378`** — "| Timeout / infinite loop | Wall-clock cap → **INCONCLUSIVE**,
  distinct from fail |" *(stale)*
- **`PLAN.md:44`** — "Runs a command safely; timeout → INCONCLUSIVE" *(stale)*
- **`DEVELOPMENT_PLAN.md:135`** — "| EL-206 | T11 Sandbox runner | … | Timeout → INCONCLUSIVE |"
  *(stale)*
- **`TASKS.md:356`** — "T11.3 Wall-clock timeout → `INCONCLUSIVE`" *(stale)*
- **`TASKS.md:358`** — "**Done when:** runs a command safely; timeout → INCONCLUSIVE." *(stale)*
- **`USER_EXPERIENCE.md:66`** — "Results: per-artifact verdicts by grader rung; INCONCLUSIVE shown
  distinctly from fail." *(not stale)*
- **`CLAUDE.md:49`** — "**Never invent a number.** Thresholds are copied verbatim from the source
  or set to `null`." *(the ticket's precedence claim; see Status)*

**Interpretations, flagged for review:**

1. **The CPU-time cap counts as a timeout.** A:37 says "timeout"; reading a CPU budget as one is
   this decision's call.
2. **Kills at the memory, file-size and open-files limits are `runtime_error`.** A:39 has no class
   for resource limits, and this decision does not invent one.
3. **`inconclusive` is not a corpus concept.** Its definition here — the evaluation failed, not the
   artifact — comes from the harness-versus-capability split that E6 and H8 draw (E:203, H:267).
4. **The display rule now covers `summary.md`,** although `USER_EXPERIENCE.md:66` states it only for
   the dashboard.

**Not decided here, deliberately:**

- **The cap values** — A:37's 10 seconds, and E6's 30 and 180 — belong to EL-015.
- **A:37's row cap.** The corpus does not say how a breach of it is counted. It first matters for
  SQL, in Track V.

## Follow-up

**Unblocks:**
- EL-206 — the two enums and the record of which cap was hit;
- EL-201 — the verdict and failure-class fields;
- EL-207 — the class mapping above;
- EL-211 — the display rule;
- EL-212 — a hang now counts as a catch.

**Doc changes made by this ticket (no code changes):**

- `AGENT.md:150` and `:199`, `ARCHITECTURE.md:378` and `PLAN.md:44` — the four lines the ticket
  names.
- `DEVELOPMENT_PLAN.md:135`, `TASKS.md:356` and `TASKS.md:358` — the same rule, which would have
  sent EL-206 the wrong way.
- `E2-M1-TICKETS-AND-PROMPTS.md`:
  - EL-014 marked decided;
  - §0.1 warning 7 restated as settled;
  - the tracking row filled in;
  - open question 3 closed.

**Left alone, on purpose:**

- **`decisions/EL-009-shell-capture.md:43`** cites "the `Timeout = INCONCLUSIVE` rule at
  `AGENT.md:199`". A decision record is history and is not rewritten. Its point still holds under
  this rule: duration separates a 0.2-second collection error from a 90-second run.
- **`evalloop/memory/episodic.py`**'s docstring still calls EL-014 open. This ticket writes no
  code. The docstring should be updated by the next change to the store: the schema migration that
  can restrict its verdict column to `Verdict`.
