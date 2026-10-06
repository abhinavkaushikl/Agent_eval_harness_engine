# EL-003 — Three proposed `Situation` members

## Decision

None of the three is added. `claim_unverified`, `live_endpoint_available` and `agent_tool_call` are deferred to EL-701, EL-307 and EL-409 respectively.

Each fails the same test for a different reason, and the reasons matter more than the shared verdict:

- **`claim_unverified`** — the corpus notion exists, but it is already routed by an existing member (`agent_action`), and the name collides with three unrelated corpus meanings.
- **`live_endpoint_available`** — the corpus states the opposite, and the words describe a capability, not a situation.
- **`agent_tool_call`** — the corpus mentions tool calls only as logged detail *inside* a technique, never as the condition that selects one.

## Status

Deferred — no enum members added, no code changed — 2026-10-06.

This overturns the recommendation to add all three in M0 "while the enum is cheap." That premise was already examined and rejected for the `Tool` enum in `decisions/EL-002-mcp-tools-in-enum.md`, and the same arithmetic holds here: enum widening is monotone, so a member added at S3 and a member added after 70 records exist cost the same one line plus one docstring note. Cheapness is not a reason to add; a technique that needs the member is.

Note that `evalloop/vocab/situations.py` does not exist yet — `TASKS.md:37` (S3) creates it. "Adding the members now" would mean pre-committing S3's content, not editing existing code.

## Candidates

| Candidate | Corpus evidence (file:line + verbatim) | Family | Which record would trigger on it | Verdict |
|---|---|---|---|---|
| `claim_unverified` | **Present but already routed.** `evals-situation-to-technique.md:14` — "Agent claims it did something"; `A-choosing-how-to-grade.md:77` — "**Track claim–state mismatch as its own metric.** Count runs where the agent said \"done\" and the state disagrees." | would be ARTIFACT | **None that is not already served.** A2 `end_state_verification` is the record for an unverified agent claim, and its trigger is `agent_action` | **Defer to EL-701** |
| `live_endpoint_available` | **NONE — the corpus states the opposite.** `evals-situation-to-technique.md:113` — "Live systems carry state between runs, so results are not reproducible and runs corrupt each other"; `H-agents.md:55` — "Running agent evals against shared staging" is listed under "The mistake people make" | would be DATA | **None.** H1 fires when the environment is *not* resettable; a live endpoint is the hazard it removes | **Defer to EL-307** |
| `agent_tool_call` | **Present only as logged detail, never as a trigger.** `H-agents.md:30` — "reset to a fixed snapshot before every run, with every tool call, argument, response and timing logged"; `evals-situation-to-technique.md:113` situation cell reads "Any agent evaluation", not "a tool call happened" | would be ARTIFACT | **None.** H1 and H7 are triggered by `agent_action` and require the `trace_capture` tool | **Defer to EL-409** |

Per the standing rule, a new `Situation` with no triggering technique is not an Add. All three have none.

## Candidate 1 — `claim_unverified`

This is the one with real corpus support, and it is still a defer.

The corpus talks about claims in three distinct places, and they are not the same thing:

1. **An agent's claim about its own action.** `evals-situation-to-technique.md:14`, "Agent claims it did something" → A2 end-state verification, whose instruction is to "Ignore the transcript." The situation that selects A2 is the artifact under evaluation — an agent action — which `CLAUDE.md:145` already names `agent_action`. `A-choosing-how-to-grade.md:77` makes claim–state mismatch a *metric* A2 produces, with a threshold ("a mismatch rate above 2% blocks launch"), not a precondition for running it.
2. **An unsupported claim inside a generated answer.** `evals-situation-to-technique.md:100`, "Answer contains invented facts" → G3, which `G-rag-systems.md:93` defines as "split each answer into atomic claims, then check whether the retrieved context **entails** each claim." This *is* a corpus situation with no `§6` member — see the audit below — but its subject is a RAG answer's faithfulness, and `claim_unverified` is the wrong name for it.
3. **A vendor's published claim.** `J-choosing-a-model.md:183`, "A vendor number is a claim, and your eval is how you check it" → J5.

One member cannot serve all three without making `match()` route an invented fact in a RAG answer to an end-state verifier. That ambiguity is precisely the silent-matching failure `CLAUDE.md:157` warns about, and it is a reason to add *nothing* under this name rather than to add it early.

What EL-701 actually needs is narrower than any of the three. `DEVELOPMENT_PLAN.md:221-222` defines it as "L1 Claim extractor" → "L2 Claim verifier (clean re-run, transcript never used as evidence)", gated on "Mocked \"passing\" suite caught". That is A2 turned on the coding assistant itself: a typed claim extracted from an assistant transcript. The typed claim does not exist as an object until EL-701 builds the extractor, so the situation cannot be matched on before then.

**Why M0 is the wrong time:** the record that would serve it (A2) already triggers on `agent_action`, so the member would plan nothing until EL-701 creates the claim objects it describes.

## Candidate 2 — `live_endpoint_available`

The clearest defer of the three, on two independent grounds.

**The corpus argues against it.** H1's "Why this one" column is a warning about live systems: "Live systems carry state between runs, so results are not reproducible and runs corrupt each other" (`evals-situation-to-technique.md:113`). `H-agents.md:55` lists "Running agent evals against shared staging" as the mistake people make, and `H-agents.md` decision flow opens with "Is the environment sandboxed and reset per run? └─ NO → build it first." A live endpoint does not select a technique; it is the condition H1 exists to eliminate. A member named `..._available` would read, to a record author scanning the enum as a menu, as a licence to do the thing the section forbids.

**The words name a capability, not a situation.** "A live endpoint is reachable" answers *what must exist in the world for this to be runnable* — which `decisions/EL-002-mcp-tools-in-enum.md` establishes as the meaning of `Tool`, not `Situation`. `CLAUDE.md:153` already carries `db_connection` and `snapshot_restore` for the resources involved. Applying EL-002's own test: if the delivery mechanism changed but the resource stayed the same, no record's requirement would change — so this is transport/capability, and it belongs to the capability broker.

**Why M0 is the wrong time:** it is a Track V connector-discovery condition (`DEVELOPMENT_PLAN.md:54`, gate GV "discovers DB + vector store"), owned by EL-307's MCP client connector, and it is a capability question that the broker answers rather than a situation `match()` keys on.

## Candidate 3 — `agent_tool_call`

Tool calls appear in the corpus only as data recorded *during* a technique, never as the trigger for one. H1 is "A containerised mock of the real systems …, with every tool call, argument, response and timing logged" (`H-agents.md:30`); the situation cell that selects it reads "Any agent evaluation" (`evals-situation-to-technique.md:113`). H7's trajectory taxonomy reads those logs afterwards — `H-agents.md:229`, "You only find them by reading traces."

So the split is already clean in the existing vocabulary: the situation is `agent_action`, and the ability to see the calls is the `trace_capture` tool (`CLAUDE.md:153`). A single tool call is one observation inside a trajectory, at a finer grain than any `triggers_on_situation` value — no record fires because one tool call occurred.

**Why M0 is the wrong time:** it is the output of the EL-409 gateway recorder ("every tool call (name, args, result, latency, cost) → bus", `DEVELOPMENT_PLAN.md:175`), which is an observation emitted four months after M0 by machinery that does not exist; the records that consume traces are already routed by `agent_action` plus `trace_capture`.

## Master-lookup situations absent from `CLAUDE.md §6`

This is the larger finding, and it is not about the three candidates.

Scope of the audit: `evals-situation-to-technique.md` lines 13–148 hold the 70 technique rows across sections A–J. Lines 154–172 ("THE MASTER LOOKUP" recap) restate section rows in shorthand and introduce nothing new; lines 182–195 are the domain → costlier-error table, whose first column is a domain, not a situation. Both were checked and excluded. Each row's phrasing was cross-read against its section's decision flow, which states the branch condition more precisely than the table cell.

`§6`'s 48 members cover sections A, B, E, F and I almost exactly. Coverage of **C, D, G, H and J is partial**, and in two places a whole technique would never fire.

### Group 1 — no existing member would route these at all

These need a member at S3, or the named record is unreachable.

| Row | Situation (verbatim) | Decision-flow condition | Record left unreachable | Suggested family |
|---|---|---|---|---|
| `:18` | "High-stakes final decision" | "Is a wrong answer high-stakes (health, legal, money, regulator)?" (`A:309`) | A6 domain-expert human review | LIFECYCLE (stakes) |
| `:41` | "Any score, ever" | "Otherwise → Wilson 95% CI on every score and slice" | C1 Wilson CI | — see note |
| `:43` | "Stochastic system" | "Is the system stochastic (temp > 0, agents, retrieval)?" | C3 k ≥ 5 runs, mean ± SD | DATA |
| `:44` | "Score near 0% or 100%" | "Is the score near 0% or 100%, or n < 100?" | C4 Wilson / Clopper–Pearson, rule of three | MEASUREMENT |
| `:45` | "Checking many metrics or slices" | "Did you check many slices / metrics / variants?" | C5 Holm–Bonferroni / BH | MEASUREMENT |
| `:46` | "You don't trust the test's assumptions" | "Is the metric heavy-tailed (latency, ₹, ETA)?" | C6 permutation test | DATA |
| `:55` | "False alarms are expensive" | "Is a false alarm expensive (blocks, suspensions, denials)?" | D2 precision at a fixed floor | DATA |
| `:56` | "You haven't picked a threshold yet" | "Choosing between models, no threshold agreed?" | D3 average precision / PR-AUC | LIFECYCLE |
| `:57` | "Setting the threshold" | "Can you price both errors in ₹?" | D4 cost-based threshold | LIFECYCLE |
| `:58` | "Measuring safety" | "Is this a safety / abuse / manipulation risk?" | D5 red-team set + ASR per category | LIFECYCLE |
| `:59` | "Reporting safety numbers" | "Reporting the result? → upper bound + per-category counts" | D6 upper confidence bound | LIFECYCLE |
| `:146` | "Balancing quality and money" | "cheapest model inside the best model's CI" (`J:243`) | J3 cost–quality Pareto frontier | LIFECYCLE |

Two of these are worth calling out specifically.

**Safety has no trigger at all.** `§6` contains nothing that means "this output can harm someone." `rare_class` is the nearest member and it is not a substitute: D5 is about *deliberately constructing* an adversarial set precisely because, as `:58` puts it, "Random production samples contain almost no attacks, so \"0 failures on 1,000 random chats\" proves little." Without a member here, D5 and D6 — an entire subsection, including the ASR metric and the no-"% safe"-headline constraint — are dead records.

**Thresholds and error costs have no trigger.** D2, D3 and D4 all branch on properties `§6` cannot express: whether a threshold has been chosen, and whether the two error types have different prices. These are the rows most likely to be mistaken for `required_signals`; the decision flow treats them as branch conditions, which is what a `Situation` is.

**`"Any score, ever"` is a representation problem, not a missing member.** C1 applies universally, and enumerating all 48 members in its `triggers_on_situation` would be both unstable and meaningless. This wants a planner rule (C1 always reported) or an explicit sentinel. Flagging it under `CLAUDE.md §7.5` as a schema question rather than guessing: `triggers_on_situation` is specified non-empty, so a universal record has no honest encoding today.

### Group 2 — coverable by an existing member plus `required_signals`

Listed so S3 and EL-120 do not rediscover them. Each is a real distinction the corpus draws; none needs its own member, because an existing member routes it and the remaining discrimination is a precondition on the artifact.

| Row | Situation (verbatim) | Routed by | Discriminating signal |
|---|---|---|---|
| `:88` | "Judge grades the wrong dimension" | `new_judge_built` | one prompt judging many criteria (F7) |
| `:89` | "Want better judge accuracy" | `new_judge_built` | validated but below the κ bar (F8) |
| `:99` | "Isolating which stage broke" | `rag_answer` + `debugging_regression` | gold passage labels exist (G1/G2) |
| `:100` | "Answer contains invented facts" | `rag_answer` | unsupported claims observed (G3) |
| `:101` | "Ranking quality matters" | `rag_answer` | graded relevance labels (G4, nDCG) |
| `:102` | "Only one right document exists" | `rag_answer` | exactly one relevant doc (G5, MRR) |
| `:103` | "System invents answers to unknowns" | `rag_answer` | corpus has coverage gaps (G6) |
| `:104` | "Retrieval sometimes returns junk" | `rag_answer` | distractors in context (G7) |
| `:105` | "Citations shown to users" | `rag_answer` | citations surfaced to end users (G8) |
| `:115` | "Quoting reliability to a customer" | `agent_action` | reliability quoted externally (H3, pass^k) |
| `:116` | "Comparing agent costs" | `agent_action` + `two_candidates` | cost per successful task (H4) |
| `:117` | "Long multi-step tasks" | `agent_action` | > 10 steps (H5) |
| `:118` | "Agent reads external content" | `agent_action` | agent ingests untrusted content (H6) |
| `:119` | "Agent behaves erratically" | `agent_action` + `debugging_regression` | traces available (H7) |
| `:120` | "Runs fail inconsistently" | `ci_flaking` | always / flaky / never buckets (H8) |
| `:136` | "Deploying a new model" | `shipping_change` | rollout is staged (I4 canary, I9 shadow) |
| `:148` | "Reading a vendor claim" | `external_leaderboard` | claim is a vendor's, held-out set exists (J5) |

Group 2 rests on one reading of the schema that should be confirmed at S3: that `triggers_on_situation` is deliberately coarse and `required_signals` carries the fine discrimination (`CLAUDE.md:167`, "free-text preconditions on artifact/data"). If that reading is wrong, most of Group 2 becomes Group 1 and sections G and H need roughly a dozen members between them.

### One naming hazard found while auditing

`§6` contains both `items_grouped` (comparison) and `grouped_items` (data) — the same two words, reversed, in two families. The master lookup has one row, `:33` "Items come in groups" → B7 cluster bootstrap. Two near-identical members for one source row is the exact spelling-mismatch failure `CLAUDE.md:157` describes, and a record author will cite the wrong one. S3 should either collapse them or document what distinguishes them.

## Consequences

- No `Situation` member is added and no code changes. `evalloop/vocab/situations.py` is still created by S3 (`TASKS.md:37`), which now inherits the Group 1 list as input.
- `CLAUDE.md §6` stands as written. `TASKS.md:39` already calls it "the starting set" and `TASKS.md:38` asks for "five-plus" families, so the gaps above are expected S3 work, not a defect in `§6`.
- The three deferred names are not reserved. Nothing competes for them, and widening the enum later is monotone: one line plus one docstring note, with no existing record invalidated (the argument is set out in `decisions/EL-002-mcp-tools-in-enum.md`).
- Two items are escalated rather than decided here, per `CLAUDE.md §7.5`: how a universal record such as C1 encodes `triggers_on_situation` when the field is specified non-empty, and whether `items_grouped`/`grouped_items` is one member or two.
- If Group 1 is not resolved at S3, the planner will silently under-plan sections C and D. D5 and D6 in particular would load, pass integrity checks, and never match — `match()` would look complete while planning nothing, which is the failure this decision was asked to prevent.

## Related

- `decisions/EL-001-corpus-location.md` — corpus lives in-repo; audit line numbers above are against that copy.
- `decisions/EL-002-mcp-tools-in-enum.md` — the capability-vs-transport test applied to `live_endpoint_available`, and the monotone-widening cost argument.
