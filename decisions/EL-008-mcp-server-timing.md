# EL-008 — MCP server timing: gating EL-703 behind Gate 3

## Decision

**Accepted.** EL-703 stays gated behind Gate 3, and its placement in E7 after Gate 4 is correct. An external agent may not call `evaluate` or `verify_claim` in a loop until the six preconditions below are answered yes.

**With one carve-out, which is the useful half of this decision:** the two tools that return no verdict — `report_intent` and `plan` — are not gameable, because there is nothing in their output for an agent to optimise. They ship early, behind a server-side flag, as proposed ticket **EL-422** in E4. `evaluate`, `verify_claim` and `findings` stay in E7.

## Status

Accepted — 2026-10-06. No code.

The plan's one-line rationale at `DEVELOPMENT_PLAN.md:43` — "An agent iterating against a noisy grader learns to game it" — is correct, and this record converts it into a checklist so it does not have to be re-argued at G3. The structure of the plan had nearly settled the question already; what was missing was the evidence list and the cost of waiting, both below.

## The precondition checklist

Six yes/no questions, each answerable from evidence produced at the gate named. All six must be yes before EL-703 exposes `evaluate` or `verify_claim`.

| # | Question | Satisfied by | Checked at |
|---|---|---|---|
| 1 | On a real multi-run comparison, does a within-noise delta get refused as an improvement — not flagged, *refused*? | EL-502, EL-507 | G3 |
| 2 | On a situation with insufficient evidence, does the pipeline return "need X, have Y" instead of a number? | EL-501, EL-507 | G3 |
| 3 | Does a planted reward hack get flagged on a real run, rather than only in a unit test? | EL-504, EL-507 | G3 |
| 4 | Does the self-canary detect a deliberately degraded grader on its fixed known-answer set, within one session? | EL-506, EL-507 | G3 |
| 5 | For every reported improvement, are regressed items listed alongside improved ones? | EL-503 | G3 |
| 6 | Is an uncalibrated judge actually prevented from gating, with κ reported? | EL-604, EL-611 | **G4** |

Items 1–5 are the Gate 3 set and map onto `DEVELOPMENT_PLAN.md:193-199`, whose gate row (EL-507) already depends on EL-504–506. Item 6 is a Gate 4 item, included because E7's placement gives it to us anyway and because it is a genuine precondition: if `evaluate` can return a judge score from an uncalibrated judge, an agent optimising that score is optimising noise with extra steps. Keeping it on the list makes the checklist complete rather than merely gate-aligned.

Two notes on how to run the checklist. Each question says "on a real run" deliberately — a passing unit test is not evidence here, because the failure being guarded against is the system behaving differently under an agent's access pattern than under a fixture's. And EL-505 (journey ledger) is not a precondition but is a prerequisite for *diagnosing* a breach after the fact; if item 1 or 3 later proves wrong in production, the ledger is what makes the episode reconstructible, so it should exist before EL-703 even though it gates nothing.

## The failure mode, concretely

### Mechanism 1 — the agent chases noise, at machine speed

Suppose EL-703 shipped once its stated dependencies were met (EL-301 and this decision), which could be shortly after G1. At that point M1 exists — sandbox, graders, statistics — but none of M3 does: no noise floor, no readiness gate, no reward-hack diagnostic, no self-canary, no per-item diff.

The agent is building text-to-SQL. It calls `evaluate()` and receives 68%. It edits the prompt, calls again, receives 71%, and keeps the change. On an eval set of 40 cases, a 3-point move is well inside the interval — the corpus's own rule of thumb puts the worst-case margin near `100/√n`, so at n = 40 the number is not distinguishable from where it started. The agent cannot know this, because `evaluate` returned a bare number and nothing refused it. With EL-704's feedback channel making the loop automatic, it repeats twenty times in an hour, keeping every change that moved the number up.

**How it appears in the results:** the reported score climbs smoothly — 68, 71, 74, 79 — and the dashboard trend line looks excellent, while held-out performance is flat or worse. Each "win" quietly traded one set of items for another, which is invisible without EL-503's per-item diff; the sequence is unreconstructible without EL-505's ledger; and none of it is separable from signal without EL-502. The eval set has become a training set, and the mechanism was not dishonesty but an honest optimiser given an unreliable number.

The irony is exact and worth naming: this is `E-when-a-number-looks-wrong.md`'s E2 ("score improved but users didn't notice") and E5 (ceiling) happening to EvalLoop itself, and the diagnostics that catch it are precisely the M3 work not yet built.

### Mechanism 2 — the agent weakens the oracle

`verify_claim` is the sharper risk. The agent claims "all tests pass"; `verify_claim` re-runs independently and contradicts it. An agent in a loop with a contradicting oracle has two paths: fix the code, or make the oracle agree. The second is cheaper — relax an assertion, widen a tolerance, mark a case skipped, narrow a fixture. The claim then verifies honestly, and the artifact is worse than before.

This is what EL-705's anti-Goodhart guards (held-out cases, oracle-change detection) exist to catch, and `DEVELOPMENT_PLAN.md:225` sizes them accordingly.

### Why EL-705's guards are not sufficient to allow it sooner

Three reasons, and the first is decisive.

**Ordering makes them unavailable in time.** EL-705 depends on EL-704, which depends on EL-703 (`DEVELOPMENT_PLAN.md:223-225`). By the time the guards exist, the agent has already been in the loop. This is not a scheduling inconvenience — a held-out set is only held out if it was withheld *before* the agent had access, so a guard retrofitted onto cases the agent has already optimised against is not a guard. The one asset EL-705 depends on is the one thing shipping early destroys.

**Their scope is the wrong half of the problem.** EL-705 catches artifact-side gaming: a weakened test, a changed oracle. It does not catch Mechanism 1 at all, because in that scenario nothing was weakened and no oracle changed — the agent optimised a number that was never real. That is a measurement-integrity failure, and only EL-501 and EL-502 address it. Guards detect cheating; they do not make an honest measurement trustworthy.

**They rest on the thing they are meant to protect.** EL-705's own guards are evaluated by the same pipeline. A degraded grader — the condition EL-506's self-canary exists to detect — makes the guards unreliable in exactly the way it makes everything else unreliable. Guards presuppose a sound measurement; they cannot establish one.

## The cost of waiting

### What we do not learn between G1 and G3

Real, and worth stating plainly rather than minimising. Only an agent in the loop teaches:

- **Whether the five tool signatures are the right ones.** Does an agent actually call `plan()` before writing code, or ignore it? Does it call `report_intent`, or skip straight to editing? No amount of design settles this.
- **Whether the loop closes at all ergonomically.** If `evaluate()` takes two minutes, the agent moves on and the loop never forms. Latency is a design constraint we are currently guessing at.
- **Whether `findings` output is actionable to a model** — phrasing, verbosity, whether it leads to a correct fix or a plausible wrong one.
- **Call volume and cost,** which bears on budgets in EL-302.
- **Whether an agent's declared intent beats EvalLoop's inference,** which bears directly on Track O's classifier and on EL-010.

And the demo cost, which is the real one: EL-704's "agent fixes code unprompted" is the most compelling moment in the plan, and `ARCHITECTURE.md:183` says so in as many words — "the eval result becomes an **input** to code generation, not a report nobody opens. This is the strongest argument for the whole product." Under the current schedule that moment arrives in late February.

### What waiting does *not* cost

The two-clicks promise is not on this path. `CLAUDE.md:11-14` promises that you "click **start** and work however you normally work, in any editor and with any AI assistant", with "a backend agent [that] observes what you're building". That is Track O — sensors, transcripts, hooks — and it is proved at G2, not by an MCP server. `ARCHITECTURE.md:167` calls EvalLoop's MCP server "the portable path" for agents that have no other adapter: an alternative route to intent, not the product. So delaying EL-703 delays loop closure and a demo; it does not delay the core promise by a day.

It is also worth reading the promise's last clause as part of this decision. `CLAUDE.md:11` ends: "Each statistical check fires **only when there is enough data to be honest**." Shipping `evaluate` before EL-501 would break that sentence for the system's most demanding consumer first.

### The slice that can ship earlier

**Yes — `report_intent` and `plan`.** The dividing line is not read versus write; it is **whether the agent gets back a number it can iterate against**. Checked against `ARCHITECTURE.md:177-181`:

| Tool | Returns a verdict? | Verdict |
|---|---|---|
| `evalloop.plan()` | No — returns which techniques apply and what evidence is missing | **Ship early.** Nothing to optimise |
| `evalloop.report_intent(text, artifacts)` | No — the agent supplies input; nothing is returned to game | **Ship early** |
| `evalloop.findings(since)` | **Yes** — returns computed verdicts | Hold. See below |
| `evalloop.evaluate(artifacts?)` | Yes, on demand, fast | Hold to E7 |
| `evalloop.verify_claim(claim)` | Yes, and it is the oracle | Hold to E7 |

`findings` is the borderline case and I would hold it, having argued both sides. The case for shipping it: it returns verdicts EvalLoop computed on its own schedule from the developer's own work, which the human already sees in the dashboard, so exposing it to the agent adds no information that is not already trusted. The case against, which wins: `findings` plus a tight loop approximates `evaluate` closely enough that Mechanism 1 reappears, only slower, and the readiness state that would make it safe is EL-501 — a G3 item. If `findings` is wanted earlier, the condition is precondition 2, not a flag.

**`report_intent` is worth shipping early for a second reason that has nothing to do with the MCP surface.** `ARCHITECTURE.md:177` describes it as "Perfect intent, zero inference." The riskiest component in the whole plan is intent classification — EL-415's bar is "10 episodes classified; `unclear` plans nothing", which is an empirical result no design review can clear. An agent that declares its intent directly substitutes for the component most likely to disappoint. So the early subset is not only a safe interface probe; it de-risks Track O.

**Proposed ticket: EL-422, in E4.** "MCP server, read-only subset (`report_intent`, `plan`), flag-gated", depending on EL-301 and EL-416 (`plan()` needs a session to describe). It belongs in E4 rather than E3 because the transport (EL-301) and the session orchestrator both land by then and the gateway work is already in flight.

Two constraints on the flag, because "behind a flag" is only as good as its enforcement. The subset must be enforced **server-side by omission from `tools/list`**, not by convention or by rejecting calls — an agent cannot call a tool that is never advertised, and per `decisions/EL-007-mcp-implementation.md` `tools/list` is the whole discovery surface. And the flag must default to off, with a single switch that cannot be set to expose `evaluate` or `verify_claim` before EL-703; the two tool sets should not share a configuration key.

## Consequences

- EL-703 stays in E7 as scheduled; `DEVELOPMENT_PLAN.md:93` is confirmed rather than overturned, which is the first E0 decision in this series to come out that way.
- **The checklist is the deliverable and should be attached to EL-507**, not held in this file alone. A gate whose criteria live in a decision record gets passed on vibes.
- **EL-422 is new work in E4,** roughly half a day on top of EL-301, and it adds a flag whose default must be verified at G2.
- Precondition 6 means EL-703 cannot in fact start the moment G3 passes if judge calibration is incomplete; E7's position after G4 already handles this, but the dependency is on EL-611 as well as EL-507, and `DEVELOPMENT_PLAN.md:223` names neither.
- **A defect found while reading the input, outside this ticket's scope but worth fixing in the same pass:** `AGENT.md:153` lists the power formula as `n ≈ 16/gap²` under the heading "Rules of thumb **kept verbatim**". The corpus says `n ≈ 16·p(1−p)/δ²` (`C-deciding-whether-a-result-is-real.md:19`), and the two differ by 4× at p = 0.5. This is the same defect `decisions/EL-004-claude-md-corpus-gaps.md` corrected in `CLAUDE.md §4`; AGENT.md was not in that ticket's scope and still carries it, with a "verbatim" claim attached. It should be corrected the same way.

## Follow-up — proposed, not applied

1. **`DEVELOPMENT_PLAN.md:93`** — update the EL-008 row to "✅ Decided **Accepted**: after G3, with a flag-gated read-only subset (`report_intent`, `plan`) in E4 as EL-422 — `decisions/EL-008-mcp-server-timing.md`".
2. **`DEVELOPMENT_PLAN.md:199`** — extend EL-507's done-when to reference the six-item checklist, so the gate is checked against it: "Noise refused; reward hack caught; EL-008 preconditions 1–5 answered yes".
3. **New row in E4** — EL-422 "MCP server, read-only subset (`report_intent`, `plan`), flag-gated", Est. 0.5, depends on EL-301, EL-416.
4. **`DEVELOPMENT_PLAN.md:223`** — add EL-611 to EL-703's `Depends on` (precondition 6), and note that `findings` ships with EL-703 while `report_intent` and `plan` arrive at EL-422.
5. **`AGENT.md:153`** — correct `n ≈ 16/gap²` to `n ≈ 16·p(1−p)/δ²`, per the Consequences note.

## Related

- `AGENT.md:183-199` — the non-negotiable agent behaviours, several of which are the preconditions above stated as rules: "Below readiness → `pending` with 'need X, have Y'" and "Within-noise delta is never an 'improvement'". The checklist is the evidence that those two rules actually hold.
- `ARCHITECTURE.md:171-183` — §5.3, the five tools and the Goodhart ordering argument this decision confirms.
- `decisions/EL-007-mcp-implementation.md` — the protocol EL-703 and EL-422 are built on, and why `tools/list` omission is the right enforcement point for the subset.
- `decisions/EL-005-track-order.md` — sets when G2, G3 and therefore EL-422 and EL-703 land.
