# E2-M1-TICKETS-AND-PROMPTS.md — one ticket + one prompt per M1 build item

Run-ready work items for epic **E2 — M1 First Grading** (`DEVELOPMENT_PLAN.md §3`; `PLAN.md`
T7–T17). Companion to `E0-DECISION-PROMPTS.md` and `E1-M0-TICKETS-AND-PROMPTS.md`, same format,
same rules.

Each block has three parts:
- the **story** — one line in the developer's voice, so the ticket can be read without the epic;
- the **ticket** — for the board: files, subtasks, acceptance criteria, out-of-scope, gotchas;
- the **prompt** — paste-ready for one working session. Self-contained on purpose: it repeats
  the ticket, because it is pasted without it.

**Epic story.** *As a developer who has just written a function, I want EvalLoop to work out that
I wrote code, find or write something that can judge it, run it somewhere safe, and tell me the
truth about whether it works — without my writing an eval, configuring anything, or being told a
number it cannot support.*

**How to use:** paste §0 (the shared preamble) and §0.1 (the inherited-ruling warnings), followed
by exactly one ticket's prompt block. One session per ticket.

**Order:** by group. Group 1 is genuinely parallel and can start before Gate 0 clears; everything
from Group 2 on is sequential within its group, and the critical path is
`EL-201 → EL-206 → EL-207 → EL-214 → 🔒G1`.

**Do not batch.** EL-206 → EL-208 all write `evalloop/grade/`, and EL-207's partial-credit logic is
the one place in M1 where a wrong default produces a plausible-looking score. Batched, the
per-ticket verdict tests never run, and M1's whole claim is that its verdicts are honest.

---

## 1. Board

**Status is `Blocked` for everything that depends on Gate 0, because 🔒 Gate 0 has not been signed
off.** See §3.

| Key | Title | Type | Est | Depends on | Blocks | Status |
|---|---|---|---|---|---|---|
| EL-014 | Timeout: INCONCLUSIVE or logged failure? | Decision | 0.25 | — | EL-206 | **Ready** |
| EL-015 | Where the comparator numbers live | Decision | 0.25 | — | EL-207, EL-208 | **Ready** |
| EL-203 | T16 Statistics module | Story | 1 | — | EL-213 | **Ready** |
| EL-202 | T8 Episodic store (SQLite) | Story | 1 | — | — | **Ready** |
| EL-209 | T14 LLM client + router | Story | 1 | *fixture-20 ruling* | EL-210 | **Ready\*** |
| EL-201 | T7 Metric store (JSONL) | Story | 1 | 🔒G0 | EL-206, EL-213 | Blocked |
| EL-204 | T9 Classifier heuristics | Story | 1.5 | 🔒G0 | EL-205, EL-214 | Blocked |
| EL-205 | T10 Oracle harvester | Story | 1.5 | EL-204 | EL-207, EL-210 | Blocked |
| EL-206 | T11 Sandbox runner | Story | 1.5 | EL-201, **EL-014** | EL-207, EL-208 | Blocked |
| EL-207 | T12 Execution grader | Story | 2 | EL-206, EL-205, **EL-015** | EL-211 | Blocked |
| EL-208 | T13 Deterministic grader | Story | 1 | EL-206, **EL-015** | EL-214 | Blocked |
| EL-210 | T15 Test author (signature-only) | Story | 2 | EL-209, EL-205 | EL-214 | Blocked |
| EL-213 | Evidence assembler **(new)** | Story | 0.5 | EL-201, EL-203 | EL-214 | Blocked |
| EL-211 | T17 `summary.md` renderer | Task | 0.5 | EL-207, EL-213 | EL-214 | Blocked |
| EL-214 | One-shot run driver **(new)** | Story | 1 | EL-204→EL-211, EL-213 | EL-212 | Blocked |
| EL-212 | 🔒 Gate 1: toy repo, broken function | Gate | 0.5 | EL-214 | E3 (Track V) | Blocked |

**\* EL-209 is Ready only if M1 makes no outbound call on an unredacted artifact.** See §4.3.

**Total 16.5 d** — 14.5 as scoped in `DEVELOPMENT_PLAN.md`, plus 2.0 for the two new stories and
the two decisions. The window (19 Oct – 6 Nov) is **15 working days**, so this is **1.5 d over**.
§5 says what to cut, and why that is a ruling rather than a trim.

| Group | Tickets | Days | Can start |
|---|---|---|---|
| 0 Decisions | EL-014, EL-015 | 0.5 | now, in parallel |
| 1 Memory + statistics *(off the critical path)* | EL-203, EL-202, EL-209 | 3.0 | now |
| 2 Situation + oracles | EL-201, EL-204, EL-205 | 4.0 | after 🔒G0 |
| 3 Execution | EL-206, EL-207, EL-208 | 4.5 | after EL-201/205 |
| 4 Authoring | EL-210 | 2.0 | after EL-209/205 |
| 5 Wiring + output | EL-213, EL-211, EL-214 | 2.0 | after Group 3 |
| 6 Gate | EL-212 | 0.5 | after EL-214 |

---

## 2. What changed from `DEVELOPMENT_PLAN.md §3 E2`, and why

Four changes. Each is a gap found while reading M0's finished code against E2's twelve rows, not
a preference.

| # | Change | Why |
|---|---|---|
| 1 | **Added EL-213, evidence assembler (0.5 d)** | `plan()` takes `evidence: Mapping[str, object]` and **nothing in E2 as scoped produces it.** 33 distinct `requires` keys exist across the 73 records. Without a producer, every readiness bar in M1 is fed by hand, which means the pending queue — the honesty claim — is a literal. |
| 2 | **Added EL-214, one-shot run driver (1 d)** | Gate 1 is "point it at a toy repo and the bug is caught with zero instruction." Nothing in E2 walks classify → plan → harvest → grade → store → render. The session orchestrator is M2 (T23), so M1 needs a one-shot entry point or Gate 1 is run by hand, which is not the gate. |
| 3 | **Added decisions EL-014 and EL-015 (0.25 d each)** | Both are corpus-vs-doc conflicts that land in code in this epic, not opinions. §4.1 and §4.2. |
| 4 | **Re-pointed EL-212's dependency** | `DEVELOPMENT_PLAN.md` has Gate 1 depending on EL-211 alone. The gate needs the classifier, the oracles, the sandbox and the grader too; EL-211 only renders. Now via EL-214. |

**Unchanged on purpose.** `EL-206 depends on EL-201` reads oddly — a sandbox needs nothing from a
metric store — but it is kept, because the sandbox's result type is what the store persists, and
defining that type in EL-201 and consuming it in EL-206 is the cheaper order. Noted once, not
argued twice.

---

## 3. 🔒 Gate 0 has not passed, and E2 starts at it

`DEVELOPMENT_PLAN.md §3` makes EL-201 and EL-204 depend on **EL-124 — Gate 0**, which is a human
reading 20 rendered plans. That review is open. `GATE0-REVIEW-PACKET.md §5` asks for five things
and records **fifteen open rulings, twelve of them decisions rather than work.**

**What that means for scheduling:** three E2 tickets — **EL-202, EL-203, EL-209** — are off the
critical path by `DEVELOPMENT_PLAN.md §4`'s own statement and can start today. The other nine
cannot honestly start, because two of the open rulings change what the planner emits, and M1 is
the first code to consume that output.

**The two that matter most** (`GATE0-REVIEW-PACKET.md §2.1, §2.2`, `S23-REPORT.md §3`):

- **F2 — `requires` is carrying two different kinds of bar.** "Enough evidence yet" and
  "trustworthy enough to use" are both written as readiness thresholds, which is why a
  summarization session currently produces an **empty plan**. EL-213 has to populate exactly this
  field, so it inherits the ambiguity directly.
- **F8 — `unlocks` is read by no step.** D's pipeline, F's calibration stack and `B5 → B1` are
  documentation, not gating. EL-213 and EL-211 will both appear to be wrong if this is fixed after
  they are built.

**Recommendation:** rule on F2 and F8, and on the three blocked fixtures (11, 14, 20), before
EL-201. Fixture 20's ruling additionally gates EL-209 — see §4.3.

---

## 4. Four findings this epic has to carry

### 4.1 The timeout conflict → decision **EL-014**

Every one of our own documents says a timeout is **INCONCLUSIVE, never pass or fail**:
`AGENT.md §3.7` and `§5`, `ARCHITECTURE.md §9`, and EL-206's own "Done when" line.

The corpus says the opposite, in A1's step 4:

> `A-choosing-how-to-grade.md:37` — "**Set resource limits.** Use a 10-second timeout and a row
> cap. **Count a timeout as a failure but log it separately**, because a slow correct query is a
> different bug from a wrong one."

These are not reconcilable by wording. One of them decides what EL-206 returns, what EL-207
scores, and whether a slow-but-correct function lowers a reported pass rate. `CLAUDE.md §3` says
the corpus wins where a doc disagrees; `E6_oracle_run`'s own worked example
(`E-when-a-number-looks-wrong.md:219`, a 30-second timeout against a 90-second booking, 0% that
was really 34%) is the strongest argument for INCONCLUSIVE being right in spirit. **Rule before
EL-206 writes a verdict enum.** A defensible answer is "both": a `TIMEOUT` outcome that is counted
as a failure in the headline rate and reported separately, which satisfies A:37 literally and
`AGENT.md §5` in effect. That is a decision, not a compromise to be made silently in code.

### 4.2 Six homeless numbers now have a home → decision **EL-015**

M0 raised these as schema findings because `requires` holds readiness thresholds and `gates` is a
three-valued enum, so neither could hold a comparator setting
(`GATE0-REVIEW-PACKET.md §4.3`, `S13-REPORT.md`):

| Number | Source | Which ticket needs it |
|---|---|---|
| float tolerance `1e-6`, ₹ rounded to the paisa | `A-choosing-how-to-grade.md:35` | EL-207 |
| 10-second timeout, row cap | `A-choosing-how-to-grade.md:37` | EL-206 |
| mutant still passes > **5%** → fixtures not discriminating | `A-choosing-how-to-grade.md:38` | EL-207 |
| token-F1 ≥ **0.8**, hand-audit the 50 items closest | `A-choosing-how-to-grade.md:111` | EL-208 |
| sample 50 failures, > **10%** actually correct → fix the normaliser | `A-choosing-how-to-grade.md:112` | EL-208 |
| mismatch rate above **2%** blocks launch | `A-choosing-how-to-grade.md:77` | M4 (A2) |

They are all grader configuration. The decision is **where** the configuration lives, so that it
is traceable to a `source_ref` the way a record's thresholds are, rather than becoming six
literals in three modules. Do not let EL-206 and EL-207 each invent a place.

### 4.3 M1 opens the first egress, and the thing that should police it is M2

EL-209 is the first code in the project that sends anything to an external API. The guard for that
is the PHI gate, which is **fixture 20 — blocked, with no record behind it.** Its own ruling text
recommends option **D: treat redaction-before-egress as a capability-broker concern** — and the
capability broker is `ARCHITECTURE.md §7` component 11, **milestone M2**.

So in E2 the egress exists one milestone before its policy. `ARCHITECTURE.md §4.3` is explicit that
"redaction is a boundary, not a filter", and `§9` requires "no outbound LLM call on PHI without an
explicit grant". **Either EL-209 carries a minimal redaction boundary at the client, or M1 runs
with no outbound call on any artifact that has not been cleared.** Pick one in the fixture-20
ruling; EL-209's prompt refuses to guess.

### 4.4 Gate 1 has two readings, and they move 2 days

> `PLAN.md`: "Point at a toy repo with a deliberately broken function. It gets caught, with zero
> instruction from you."

- **Reading A — the repo has tests.** `EL-205` harvests a HIGH-confidence oracle, `EL-207` runs it,
  the bug is caught. **EL-210 is off the critical path.**
- **Reading B — the repo has no tests.** The system must author a test from the signature alone
  (`EL-210`), tag it LOW, and still catch the bug. **EL-210 is load-bearing, and the gate is a much
  stronger claim.**

Reading B is the one that matches "zero instruction" and the product promise that the developer
never writes an eval. Reading A is the one that fits in 15 days. **This is the single highest-value
ruling in E2**, because it decides both the gate's meaning and whether the epic fits its window.

---

## 5. If it has to fit 15 days

16.5 d of work, 15 d of window, no buffer. Three options, in the order I would take them:

1. **Rule Gate 1 as Reading A and defer EL-210 to E6** (M4 already owns judge authoring). → 14.5 d,
   fits, and Gate 1 becomes a weaker claim. Say so out loud if you take it.
2. **Defer EL-202, the episodic store, to E4.** Nothing in Gate 1 reads it, and `AGENT.md §3.9`'s
   "situation decisions and the reasoning persisted" first matters when a session has a timeline
   (M2). → 15.5 d. Still half a day over.
3. **Keep all 16.5 d and move the gate to 9 Nov**, taking the slip out of E3's 18.5 d window.

**What I would not cut:** EL-213 and EL-214. Without them M1 has parts and no loop, and Gate 1 is
a human driving the parts by hand — which is exactly the instruction the gate says must not be
needed.

---

## 6. Definition of done — every ticket, no exceptions

- [ ] `pytest` exit 0
- [ ] `mypy --strict evalloop/` exit 0
- [ ] Standard library only in shipped code. `pytest` and `mypy` are dev-only
- [ ] No invented numbers: every threshold verbatim from the corpus with a `source_ref`, or `null`
- [ ] No later-milestone code: no sensors, no poller, no dashboard, no SSE, no MCP, no connectors
- [ ] No corpus filename typed anywhere but `tests/conftest.py`
- [ ] No absolute user path anywhere
- [ ] No test or fixture edited to make code pass
- [ ] Determinism: same inputs → same verdicts, same ordering, same rendered bytes
- [ ] Report-back: what was done · what the corpus would not support · every threshold interpreted
      from prose (flagged for human review) · every doc line found stale · every ruling needed

---

## 7. Inherited state — every ticket inherits these

1. **M0 is code-complete and its output is a frozen `Plan`.** `plan(records, situations,
   available_tools, evidence) -> Plan`, pure, no I/O, five states keyed by record id. M1 consumes
   it; **M1 does not change it.** A planner change is a reported finding, not a commit.
2. **73 records, 57 situations, 15 tools, 33 distinct `requires` keys.** Record ids are
   `<SECTION><N>_<snake_name>` and are the vocabulary M1's stores, reports and logs use.
3. **Six situation members reach no record** (`classification`, `data_pipeline`, `model_training`,
   `contamination_risk`, `distribution_mismatch`, `phi_present`). EL-204 can classify a session
   into one of them and get an empty plan with no explanation. Handle it visibly or report it.
4. **All eight RAG rows collapse onto `rag_answer`.** Not M1's problem, but EL-204 should not be
   built as if more discrimination exists than does.
5. **Fifteen open rulings**, `S17-REPORT.md §9`, `S19-REPORT.md §7`, `S23-REPORT.md §6`. F2 and F8
   are the two that change what M1 displays.
6. **`PLAN.md §5`'s six sanity queries: three of six diverge** from what the registry actually
   produces (`S23-REPORT.md §3`). Do not treat `PLAN.md §5` as a specification of behaviour.
7. **Directories M1 creates:** `evalloop/memory/`, `evalloop/stats/`, `evalloop/grade/`,
   `evalloop/classify/`, `evalloop/capability/`, `evalloop/report/`. Per `ARCHITECTURE.md §7`.
   Nothing else.

---

## 8. Stage map for `TASKS.md` (append after Gate 0 clears)

M0 ran as 23 stages, S1–S23. M1 is **18 stages, S24–S41**, same granularity: one sitting, one
"Done when". Append this block to `TASKS.md` under `# MILESTONE 1 — First Grading (18 stages)`
once Gate 0 is signed off, not before — `CLAUDE.md §2`'s "do NOT build" list is still in force
until it is.

| Stage | Ticket | Deliverable |
|---|---|---|
| S24 | EL-014 | `decisions/EL-014-timeout-semantics.md` |
| S25 | EL-015 | `decisions/EL-015-grader-config-home.md` |
| S26 | EL-203 | `evalloop/stats/proportions.py` — Wilson, Clopper–Pearson, rule of three |
| S27 | EL-203 | `evalloop/stats/compare.py` — McNemar + exact binomial, permutation |
| S28 | EL-203 | `evalloop/stats/resample.py` — bootstrap, cluster bootstrap, design effect |
| S29 | EL-203 | `evalloop/stats/power.py` — unpaired n, paired n, MDE, noise floor |
| S30 | EL-201 | `evalloop/memory/case.py` + `metric_store.py` (JSONL, append-only) |
| S31 | EL-201 | `diff_runs()` — two runs, per case |
| S32 | EL-202 | `evalloop/memory/episodic.py` (SQLite, decisions + reasoning) |
| S33 | EL-204 | `evalloop/classify/heuristics.py` + the 10-file sample set |
| S34 | EL-205 | `evalloop/grade/oracles/harvest.py` — tests, schemas, type hints |
| S35 | EL-206 | `evalloop/grade/verdict.py` + `sandbox.py` |
| S36 | EL-207 | `evalloop/grade/execution.py` — isolation, partial credit, compile/logic split |
| S37 | EL-207 | mutation self-test against A:38's 5% bar |
| S38 | EL-208 | `evalloop/grade/deterministic.py` + cascade hook |
| S39 | EL-209 | `evalloop/capability/llm.py` + `router.py` |
| S40 | EL-210 | `evalloop/grade/oracles/author.py` — signature-only, HIGH/LOW tagging |
| S41 | EL-213, EL-211, EL-214 | `memory/evidence.py`, `report/summary.py`, `run.py` |

---

## 0. Shared preamble (paste before every ticket block)

````text
You are working in the EvalLoop repo at /Users/abhinav/Eval-harness-Engine.
Read CLAUDE.md first and obey it. Milestone 1 changes what section 2 allows, and ONLY
these things change:
  - Execution, sandboxing, graders, statistics, storage and LLM calls are now IN scope.
  - You may create exactly these directories: evalloop/memory/, evalloop/stats/,
    evalloop/grade/, evalloop/classify/, evalloop/capability/, evalloop/report/.
    (ARCHITECTURE.md section 7.) Nothing else.
  - Still OUT of scope, and a scope violation if you write it: file watching or polling,
    the event bus, the coherence detector, the session orchestrator, the local API, the
    dashboard or SSE, MCP anything, connectors, and every M3 diagnostic. If a ticket
    seems to need one, that is a finding to report, not a thing to build.

Everything else in CLAUDE.md still holds, unchanged:
  - Standard library only in shipped code. pytest and mypy are dev-only. NumPy is the
    only external dependency that may EVER be permitted and it is not needed here:
    write the statistics in the stdlib (math, statistics, random, fractions).
  - Python 3.10+ (EL-012). Type hints everywhere. mypy --strict clean, pinned to
    python_version = 3.10, so no stdlib API newer than 3.10. StrEnum comes from
    evalloop/_compat, never from enum.
  - Never invent a number. A threshold is copied verbatim from the corpus with a
    source_ref, or it is null. "Reasonable default" is not a thing in this repo. This
    applies to timeouts, tolerances, resample counts and sample sizes exactly as it
    applies to records.
  - Never hardcode an absolute user path. Corpus filenames are declared once, in
    tests/conftest.py. Import them. Never retype one.
  - Never edit a test or a fixture to make code pass. If one looks wrong, stop and flag
    it for human review.
  - Deterministic everything. Same inputs, same verdicts, same ordering, same bytes.
    Seed every random draw and record the seed.
  - Raise schema and design problems, do not work around them.

What M0 built, and what you must not change:
  - evalloop/registry/ holds 73 TechniqueRecords loaded from YAML, with an aggregating
    loader and a seven-rule integrity checker.
  - evalloop/plan/planner.py: plan(records, situations, available_tools, evidence) -> Plan.
    Pure, total, no I/O. Plan has five states keyed by record id and a render().
  - M1 CONSUMES the planner. M1 does not modify it. If you believe the planner is wrong,
    that is a report item and a ruling for me, not a commit.

The corpus is read-only input: "knowledge rules/" holds the master lookup and ten deep
dives. It is read at AUTHORING time. Nothing in evalloop/ parses Markdown at runtime --
including your new modules. A number you take from the corpus is cited in a docstring or
a config entry, not re-read from disk.

This is a BUILD ticket. The deliverable is working, typed, tested code plus a report.

Scope rules for this session:
  - Do exactly the ticket. If you see something else wrong, report it, do not fix it.
  - If the ticket conflicts with the corpus, the corpus wins and the conflict goes in
    the report.
  - If you cannot do something honestly, that is a finding, not a thing to route around.

Finish with: pytest exit 0; mypy --strict evalloop/ exit 0; and a report-back covering
what you did, what the corpus would not support, every threshold you interpreted from
prose (flag each for human review), every doc line you found stale, and every ruling you
need from me.
````

---

## 0.1 Inherited-ruling warnings (paste after §0, before every ticket block)

````text
Seven things are known-open or known-stale coming out of M0. Trust this list over the doc
text, and when a ticket touches one, say in the report which way you went and why.

1. GATE 0 IS NOT SIGNED OFF. Fifteen rulings are open; twelve are decisions, not work.
   GATE0-REVIEW-PACKET.md section 5 lists what is being asked. If your ticket depends on
   Gate 0 (every ticket except EL-202, EL-203, EL-209 and the two decisions), say so at
   the top of your report.
2. F2 -- `requires` carries two different kinds of bar: "enough evidence yet" and
   "trustworthy enough to use". This is why a summarization session currently produces an
   EMPTY plan. Anything that populates or renders readiness inherits this.
3. F8 -- `unlocks` is read by no planner step, so the orderings recorded there (D's
   pipeline, F's calibration stack, B5 -> B1) gate nothing. B1 fires on a single pair.
4. THREE FIXTURES ARE BLOCKED on rulings: 11 (judge kappa vs label count), 14
   (small_sample -> B5), 20 (PHI gate). Fixture 20 is the one that touches M1: it is the
   guard on the first outbound LLM call, and its recommended option puts redaction in the
   M2 capability broker -- one milestone after the egress exists.
5. PLAN.md section 5's six sanity queries: THREE OF SIX DIVERGE from what the registry
   actually produces (S23-REPORT.md section 3). Do not read PLAN.md section 5 as a spec.
6. SIX SITUATION MEMBERS REACH NO RECORD: classification, data_pipeline, model_training,
   contamination_risk, distribution_mismatch, phi_present. A session classified into one
   gets an empty plan with no explanation.
7. TIMEOUT SEMANTICS ARE CONTESTED. Our docs say INCONCLUSIVE; the corpus
   (A-choosing-how-to-grade.md:37) says count it as a failure and log it separately.
   EL-014 settles it. Do not pick one quietly.

Where two of our own docs disagree on a number, NEITHER decides -- the corpus file does.
Open it, copy verbatim, and report which doc was wrong.
````

---

## Group 0 — Decisions that block code

> Both are half-day decisions whose answers become literals in `evalloop/grade/`. Taking them
> after the code exists means rewriting verdicts, which means re-reviewing every number M1 reports.

### EL-014 — Timeout: INCONCLUSIVE, or a logged failure?

**Type:** Decision · **Est:** 0.25 · **Depends:** — · **Blocks:** EL-206 ·
**Done when:** `decisions/EL-014-timeout-semantics.md` exists and EL-206 can write a verdict enum

**Story.** *As a developer whose function is correct but slow, I want to know whether EvalLoop is
about to call it broken, because those are different bugs and I will fix them differently.*

**The conflict, verbatim**
- `AGENT.md §3.7`, `§5`, `ARCHITECTURE.md §9`, `PLAN.md` T11: timeout → **INCONCLUSIVE**, "not a
  failure, not a pass".
- `A-choosing-how-to-grade.md:37`: "Use a 10-second timeout and a row cap. **Count a timeout as a
  failure but log it separately**, because a slow correct query is a different bug from a wrong one."

**Files** → `decisions/EL-014-timeout-semantics.md` (no code)

**Subtasks**
- [ ] State both positions with their citations
- [ ] Decide the verdict enum's members, exactly
- [ ] Decide whether a timeout enters the denominator of a reported pass rate
- [ ] Decide what `summary.md` shows, since `USER_EXPERIENCE.md §3.2` requires INCONCLUSIVE to be
      "shown distinctly from fail"
- [ ] Amend whichever of `AGENT.md` / `ARCHITECTURE.md` / `PLAN.md` the decision makes stale

**Acceptance criteria**
- [ ] A reader can implement the enum from the decision without asking a follow-up question
- [ ] The headline-rate question is answered in one sentence, not left to the grader
- [ ] `E-when-a-number-looks-wrong.md:219` (the 30s-timeout-vs-90s-booking case, where 0% was
      really 34%) is addressed, because it is the strongest evidence a timeout must stay visible
- [ ] The stale doc lines are edited in the same commit

**Out of scope** Writing the enum. Choosing the timeout *value* — that is EL-015's table.

**Gotchas** A third answer may be the right one: a `TIMEOUT` outcome counted in the failure rate
*and* reported separately satisfies A:37 literally and `AGENT.md §5` in effect. If you take it, say
that you are taking it, rather than letting it look like the docs agreed all along.

````text
WHAT I WANT
A decision document at decisions/EL-014-timeout-semantics.md. No code.

THE CONFLICT
Our own docs and the corpus disagree about what a timeout is, and the disagreement reaches
code in the next ticket (EL-206, the sandbox runner), whose "Done when" line is literally
"Timeout -> INCONCLUSIVE".

  - AGENT.md section 3.7 and section 5, ARCHITECTURE.md section 9, and PLAN.md T11 all say
    a timeout is INCONCLUSIVE: "not a failure, not a pass".
  - knowledge rules/A-choosing-how-to-grade.md:37 says the opposite, in A1's step 4:
    "Set resource limits. Use a 10-second timeout and a row cap. Count a timeout as a
    failure but log it separately, because a slow correct query is a different bug from a
    wrong one."

CLAUDE.md section 3 says the corpus wins where a doc disagrees. But E6's worked example cuts
the other way: knowledge rules/E-when-a-number-looks-wrong.md:219 describes a harness with a
30-second timeout against a sandbox portal that took 90 seconds to confirm a booking. The eval
read 0/50. With the timeout raised to 180 seconds the same model scored 34%. A week had been
spent comparing larger models. If that 0% had been reported as "failure, logged separately",
the logging is the only thing that saved it.

WHAT I NEED DECIDED
  1. The verdict enum's exact members, as EL-206 will write them.
  2. Whether a timeout enters the denominator of a reported pass rate.
  3. What summary.md shows -- USER_EXPERIENCE.md section 3.2 requires INCONCLUSIVE to be
     "shown distinctly from fail", which constrains the answer.
  4. Which of AGENT.md / ARCHITECTURE.md / PLAN.md becomes stale, edited in the same commit.

Read both sources before writing. Quote them. A third answer may be the right one -- a TIMEOUT
outcome counted in the failure rate AND reported separately satisfies A:37 literally and
AGENT.md section 5 in effect. If that is your recommendation, say so explicitly rather than
presenting it as though the two documents had agreed.

DO NOT, in this session: write the enum, create evalloop/grade/, or choose the timeout VALUE.
The value is EL-015's table.
````

---

### EL-015 — Where the comparator numbers live

**Type:** Decision · **Est:** 0.25 · **Depends:** — · **Blocks:** EL-207, EL-208 ·
**Done when:** every number in the table below has one home and one citation

**Story.** *As the person who will be asked "where did 1e-6 come from?", I want every comparator
constant to point at a corpus line, the same way every record threshold does.*

**Why.** M0 raised these six as schema findings and left them in prose, because `requires` holds
readiness thresholds and `gates` is a three-valued enum, so neither could hold a comparator setting
(`GATE0-REVIEW-PACKET.md §4.3`, `S13-REPORT.md`). M1 is the first code that needs them. Unhomed,
they become literals in three modules and the "no invented numbers" rule quietly stops meaning
anything.

| Number | Source | Needed by |
|---|---|---|
| float tolerance `1e-6`; ₹ rounded to the paisa | `A-choosing-how-to-grade.md:35` | EL-207 |
| 10-second timeout; row cap | `A-choosing-how-to-grade.md:37` | EL-206 |
| mutant passes > **5%** → fixtures not discriminating | `A-choosing-how-to-grade.md:38` | EL-207 |
| token-F1 ≥ **0.8**; hand-audit the 50 nearest items | `A-choosing-how-to-grade.md:111` | EL-208 |
| 50 failures sampled; > **10%** actually correct → fix the normaliser | `A-choosing-how-to-grade.md:112` | EL-208 |
| mismatch rate above **2%** blocks launch | `A-choosing-how-to-grade.md:77` | M4 (A2) |

**Files** → `decisions/EL-015-grader-config-home.md` (no code)

**Subtasks**
- [ ] Choose one home. Candidates: a new `TechniqueRecord` field; a sibling `grader_config` keyed by
      record id; module-level frozen config in `evalloop/grade/`; or the existing `requires` with a
      documented second meaning
- [ ] State the trade-off for each, including what breaks in the loader and the integrity checker
- [ ] Require a `source_ref` per entry, resolvable the way record citations are
- [ ] Say where the row cap's *value* comes from, given the corpus states none
- [ ] Say what happens to A2's 2% launch bar, which belongs to a milestone that does not exist yet

**Acceptance criteria**
- [ ] Each of the six numbers has exactly one home and one citation
- [ ] A seventh number arriving in M4 has an obvious place to go
- [ ] If the answer touches `TechniqueRecord`, the schema change is written out and the cost of
      re-running the loader over 73 records is stated
- [ ] "The row cap has no corpus value" is answered with `null` or with an explicit, flagged
      interpretation — not with a number

**Out of scope** Implementing the config. Changing the registry.

**Gotchas** The tempting answer — "a dict in `evalloop/grade/config.py`" — is fine, but only if it
carries citations and is tested for resolution. An uncited config is six invented numbers with a
nicer filename.

````text
WHAT I WANT
A decision document at decisions/EL-015-grader-config-home.md. No code.

THE PROBLEM
Six numbers in section A are comparator settings, not readiness thresholds. M0 could not place
them: `requires` holds readiness thresholds and `gates` is a three-valued enum. They were raised
as schema findings (GATE0-REVIEW-PACKET.md section 4.3) and left in prose. M1 is the first code
that needs them, and if they are not placed they become literals in three modules, which ends
the "never invent a number" rule in practice while keeping it on paper.

THE SIX, with their lines in knowledge rules/A-choosing-how-to-grade.md:
  A:35  float tolerance of 1e-6; round rupee amounts to the paisa      -> EL-207
  A:37  10-second timeout and a row cap                               -> EL-206
  A:38  if the mutant still passes more than 5% of the time, the
        fixtures are not discriminating enough                         -> EL-207
  A:111 fix the threshold (token-F1 >= 0.8) and hand-audit the 50
        items closest to it                                           -> EL-208
  A:112 sample 50 failures; if more than 10% are actually correct,
        fix the normaliser                                            -> EL-208
  A:77  a mismatch rate above 2% blocks launch, whatever the success
        rate                                                          -> M4, record A2

Open each line and read it in context before deciding. Several are steps in a procedure, and
whether a procedure step is configuration is part of what you are deciding.

WHAT I NEED DECIDED
  1. One home. Candidates, and I want the trade-offs, not just a pick: a new TechniqueRecord
     field; a sibling grader_config file keyed by record id; frozen module config in
     evalloop/grade/; or the existing `requires` with a documented second meaning.
  2. How a source_ref travels with each entry, so it resolves the way record citations do --
     S17 built a resolution sweep for exactly this and it should cover these too.
  3. Where the row cap's VALUE comes from. The corpus states a row cap but no number. The
     answer is null or an explicitly flagged interpretation. It is not a number you choose.
  4. What happens to A:77's 2% launch bar, which belongs to A2 and to a milestone that does
     not exist yet. It should not be homeless again in M4.
  5. If the answer touches TechniqueRecord: write the schema change out, and state what it
     costs to re-run the loader and the integrity checker over 73 records.

A dict in evalloop/grade/config.py is an acceptable answer ONLY if it carries citations and a
test that they resolve. An uncited config file is six invented numbers with a nicer filename.

DO NOT, in this session: implement the config, create evalloop/grade/, or change the registry.
````

---

## Group 1 — Off the critical path, start now

> `DEVELOPMENT_PLAN.md §4`: "Off the critical path, start any time: EL-202 episodic store,
> EL-203 statistics, EL-209 LLM client." These three are the only E2 work that does not wait on
> 🔒 Gate 0.

### EL-203 — T16 Statistics module

**Type:** Story · **Est:** 1 · **Depends:** — · **Blocks:** EL-213 ·
**Done when:** every corpus worked example reproduces to the digit printed in the corpus

**Story.** *As a developer being shown "82%", I want the interval next to it, computed the way the
methodology says, so that I can tell whether my 3-point gain is a result or a draw.*

**Files** → `evalloop/stats/__init__.py`, `proportions.py`, `compare.py`, `resample.py`, `power.py`
· `tests/test_stats_corpus_examples.py`

**Subtasks**
- [ ] `proportions.py` — Wilson score interval, Clopper–Pearson, rule of three
- [ ] `compare.py` — McNemar with the χ²/exact-binomial switch, paired permutation test
- [ ] `resample.py` — bootstrap CI, cluster bootstrap, design-effect calculation
- [ ] `power.py` — unpaired n, paired n, MDE, noise floor from k runs
- [ ] One test per corpus worked example, each naming its `file:line`
- [ ] Every default (resample count, shuffle count, α) carries its citation or is a required argument

**The acceptance tests, verbatim from the corpus.** These are the ticket's real specification.

| # | Input | Expected | Source |
|---|---|---|---|
| 1 | Wilson, 82/100 | `[73.3%, 88.3%]` | `C:31` |
| 2 | Wilson, 198/200 | `[96.4%, 99.7%]` | `C:135` |
| 3 | Wald, 198/200 (must reproduce the broken answer) | `[97.6%, 100.4%]` | `C:135` |
| 4 | Wilson, 47/50 and 43/50 | `[83.8, 97.9]`, `[73.8, 93.0]` | `C:49` |
| 5 | Rule of three, 0 in 300 | `≤ 1.0%` at 95% | `C:132`, `C:159` |
| 6 | Rule of three inverted, claim ≤ 0.1% | `3,000` clean items; ≤ 0.01% → `30,000` | `C:139` |
| 7 | Unpaired n, 80% → 85% | `≈ 920` per arm | `C:19`, `C:65` |
| 8 | Paired n, same effect, 12% discordant | `≈ 375` | `C:65` |
| 9 | Paired n, 2-point effect, 10% discordant | `≈ 1,960` | `C:84` |
| 10 | Power at n = 150/arm for a 5-point gain | `21%` | `C:79` |
| 11 | Noise floor, runs `76.1, 79.4, 77.8, 74.9, 78.2` | mean `77.3`, SD `1.8` | `C:100` |
| 12 | Family-wise error, k = 20 at α = 0.05 | `1 − 0.95²⁰ = 64%` | `C:21`, `C:169` |
| 13 | Family-wise error, k = 12 | `46%` | `C:188` |
| 14 | Margin from n, n = 500, p = 0.85 | SE `1.6`, margin `±3.1` | `B:172` |
| 15 | Margin from n, n = 120, p ≈ 0.8 | `±7.2`; at n = 600 → `±3.2` | `B:190` |
| 16 | `100/√n` shortcut at n = 100 / 400 / 2,500 | `±10` / `±5` / `±2` | `B:22` |
| 17 | McNemar, b = 3, c = 11 | uncorrected χ² `= 4.57`, p `= 0.033`; **b + c = 14 < 25**, exact binomial p `= 0.057` | `B:107`, `B:120–121` |
| 18 | McNemar, b = 8, c = 21 | p `= 0.03` | `B:121` |
| 19 | Design effect, m = 10, ρ = 0.4, n = 1,000 | effective n `= 217` | `B:243` |
| 20 | Cluster bootstrap vs item CI | `±5.1` vs `±2.4`, a `2.1×` widening at ρ = 0.4 | `B:257` |
| 21 | Permutation, 10,000 shuffles | smallest reportable p = `1/10,000`; 180 of 10,000 → p `= 0.018` | `C:209`, `C:217` |

**Acceptance criteria**
- [ ] Every row above has a test that names its `file:line` in the test id or docstring
- [ ] Wilson is the default for a proportion; Wald exists **only** so test 3 can prove it is wrong,
      and is documented as not for use (`C:35`)
- [ ] `b + c ≥ 25` switches to the exact binomial, as `B:107` states, and test 17 proves both branches
- [ ] Bootstrap and permutation are seeded; the seed is a required argument or a recorded default
- [ ] A rounding convention is stated once, in the package docstring, and every expected value is
      reproduced under it. If a corpus figure cannot be reproduced, it is **reported, not rounded to**
- [ ] Rows 7, 8 and 9 are stated in the corpus with `≈` and are satisfied by the exact value, not by
      matching the rounded one: `16·0.825·0.175/0.05² = 924`, which the corpus prints as "≈ 920".
      Rows 1–6, 11–16 and 19–21 are exact — all of them were verified against the formulas while this
      ticket was written, so a mismatch there is a bug in the implementation, not in the table
- [ ] No NumPy. `math`, `statistics`, `random`, `fractions` only

**Out of scope** Diagnostics (M3). Bradley–Terry (B4) unless free — the corpus specifies a fit plus a
1,000× bootstrap (`B:143`) and that is a day on its own. nDCG/MRR (G) belong to Track V.

**Gotchas** Several corpus figures are rounded in the prose. Decide the convention first and state
it; do not tune a formula until a printed number appears. A failure to reproduce is the most
valuable output this ticket can produce, because it means one of us is wrong about a number that is
already in 73 records.

````text
WHAT I WANT
evalloop/stats/ -- Wilson, Clopper-Pearson, rule of three, McNemar with the exact-binomial
switch, paired permutation, bootstrap, cluster bootstrap, design effect, power and noise floor.
Four modules: proportions.py, compare.py, resample.py, power.py.

WHAT IS IN THE TICKET
The "Done when" line is "Matches the corpus worked examples", and that is the entire
specification. Twenty-one worked examples exist in sections B and C with printed figures. Your
job is to reproduce each one to the digit the corpus prints, and to write one test per example
naming its file:line.

THE ACCEPTANCE TESTS, with their sources. Open each line and read it in context.
  knowledge rules/C-deciding-whether-a-result-is-real.md
    C:31   Wilson 82/100 -> [73.3%, 88.3%]
    C:135  Wilson 198/200 -> [96.4%, 99.7%]; and Wald on the same data -> [97.6%, 100.4%],
           which is impossible and is WHY Wald is in this ticket
    C:49   Wilson 47/50 -> [83.8, 97.9] and 43/50 -> [73.8, 93.0]
    C:132, C:159  rule of three: 0 in 300 -> <= 1.0% at 95%
    C:139  inverted: to claim <= 0.1% you need 3,000 clean items; <= 0.01% needs 30,000
    C:19, C:65  unpaired n ~ 16*p(1-p)/delta^2; 80% -> 85% needs ~920 per arm
    C:65   paired, 12% discordant, same effect -> ~375
    C:84   paired, 2-point effect at 10% discordance -> ~1,960
    C:79   power at n = 150 per arm for a real 5-point gain -> 21%
    C:100  five runs 76.1, 79.4, 77.8, 74.9, 78.2 -> mean 77.3, SD 1.8
    C:21, C:169  k = 20 slices at alpha = 0.05 -> 1 - 0.95^20 = 64%
    C:188  k = 12 -> 46%
    C:209  10,000 shuffles; the smallest p you can report is 1/10,000
    C:217  180 of 10,000 shuffles as extreme -> p = 0.018
  knowledge rules/B-comparing-two-things.md
    B:22   margin ~ 100/sqrt(n): +-10 at n=100, +-5 at 400, +-2 at 2,500
    B:172  n = 500, p = 0.85 -> SE = 1.6, margin = +-3.1
    B:190  n = 120, p ~ 0.8 -> +-7.2; at n = 600 -> +-3.2
    B:107  McNemar needs b + c >= 25 for the chi-square approximation; below that, exact
           binomial on b against b + c at p = 0.5
    B:120-121  b = 3, c = 11: uncorrected chi-square = 4.57, p = 0.033, BUT b + c = 14 < 25,
           so the exact binomial applies and gives p = 0.057 -- a different conclusion.
           Then b = 8, c = 21 -> p = 0.03
    B:243  design effect: effective n ~ n / (1 + (m-1)*rho); m = 10, rho = 0.4, n = 1,000 -> 217
    B:257  cluster CI +-5.1 against item CI +-2.4, the 2.1x widening the formula predicts
           at rho = 0.4

THE RESULT I WANT TO SEE
1. The four modules, stdlib only. NO NumPy -- math, statistics, random and fractions are enough
   and NumPy is not needed in M1.
2. One test per example above, each naming its file:line so a reader can check the number
   against the source without searching.
3. Wilson as the default for any proportion. Wald exists ONLY so the 198/200 test can
   demonstrate the impossible [97.6%, 100.4%] interval, and its docstring says it is not for
   use, citing C:35.
4. The b + c >= 25 switch implemented as B:107 states, with test 17 proving BOTH branches --
   that example is in the corpus precisely because the two branches disagree about shipping.
5. Every default cited or required: the 10,000 shuffles come from C:209, the 1,000-10,000
   bootstrap resamples from B:203, alpha = 0.05 from C:19. A default with no citation is an
   invented number.
6. Every random draw seeded, with the seed recorded, so two runs of the same input give the same
   interval. Determinism is a CLAUDE.md rule and it binds statistics hardest.
7. A rounding convention stated ONCE in the package docstring, with every expected value
   reproduced under it.
8. Report: any corpus figure you could NOT reproduce. Do not tune a formula until a printed
   number appears, and do not round an expectation to meet your output. A number that will not
   reproduce is the most valuable thing this ticket can find, because the same figures are
   already cited in 73 records.

OUT OF SCOPE: the M3 diagnostics; Bradley-Terry (B4 needs a fit plus a 1,000x bootstrap, B:143,
and that is a ticket of its own); nDCG and MRR, which belong to Track V.
````

---

### EL-202 — T8 Episodic store (SQLite)

**Type:** Story · **Est:** 1 · **Depends:** — · **Blocks:** — ·
**Done when:** a situation decision **and its reasoning** can be read back

**Story.** *As a developer who disagrees with EvalLoop's conclusion, I want to see why it decided
what it decided, three days later, without re-running anything.*

**Files** → `evalloop/memory/episodic.py` · `tests/test_episodic_store.py`

**Subtasks**
- [ ] Schema: session, episode, classification (situation + confidence), plan snapshot, verdict,
      and the **reasoning text** for each decision
- [ ] `sqlite3` only, with explicit schema versioning from the first commit
- [ ] Write + query API, typed, no ORM, no SQL string interpolation
- [ ] Persist the five `Plan` states per episode, keyed by record id
- [ ] A query that answers "why was `A1_execution_based` chosen here?" in one call
- [ ] Round-trip test: write a decision, reopen the file, read the reasoning back unchanged

**Acceptance criteria**
- [ ] `AGENT.md §3.9`'s exact bar met: "situation decisions **and the reasoning**", not just verdicts
- [ ] Schema version recorded in-file; a migration path exists before there is anything to migrate
- [ ] Multi-label classifications stored as multiple rows with confidences, not a joined string
- [ ] Every write parameterised; a test proves a record id containing a quote is stored intact
- [ ] Concurrent-write behaviour stated and tested, even if the answer is "one writer, by design"
- [ ] No absolute path: the DB location is an argument, with the default documented

**Out of scope** The journey ledger and trend lines (M3, T31). The session timeline (M2). Anything
that reads this store to make a decision — M1 only writes it.

**Gotchas** `sqlite3` defaults change between Python versions; pin behaviour explicitly rather than
inheriting it, since `mypy` is pinned at 3.10 and the runtime may be newer. And `USER_EXPERIENCE.md
§6` has not decided where session data lives (`.evalloop/` vs user home) — take an argument, do not
pick for the user.

````text
WHAT I WANT
evalloop/memory/episodic.py: a SQLite episodic store. Stdlib sqlite3, no ORM.

WHAT IS IN THE TICKET
AGENT.md section 3.9: "Episodic store: SQLite. Situation decisions AND THE REASONING are
persisted." The "and the reasoning" is the whole point of the ticket -- a store of verdicts
without reasoning cannot answer the question this component exists for, which is a developer
asking three days later why EvalLoop concluded what it did.

WHAT IT MUST HOLD
  - session, episode, and per-episode classification: (situation, confidence) rows, MULTI-LABEL,
    which means multiple rows, not a joined string.
  - the plan snapshot: all five Plan states keyed by record id, as the planner produced them.
  - the verdict per artifact.
  - the REASONING TEXT behind each decision, readable back verbatim.

THE RESULT I WANT TO SEE
1. An explicit schema with a version recorded IN THE FILE from the first commit, and a stated
   migration path before there is anything to migrate.
2. A typed write + query API. Every statement parameterised -- include a test that stores a
   record id containing a quote and reads it back intact.
3. One query that answers "why was A1_execution_based chosen for this episode?" in a single
   call, returning the reasoning. If that takes three queries, the schema is wrong.
4. A round-trip test: write, close, reopen the file, read the reasoning back unchanged.
5. Concurrency behaviour stated and tested, even if the answer is "one writer by design" -- say
   it in the module docstring rather than discovering it in M2.
6. The database location as an ARGUMENT with a documented default. USER_EXPERIENCE.md section 6
   has not decided between .evalloop/ in the repo and the user's home directory, so do not
   decide it here. Never an absolute user path.
7. sqlite3 defaults differ across Python versions and mypy is pinned at 3.10 while the runtime
   may be newer. Pin the behaviour you rely on explicitly; do not inherit it.

OUT OF SCOPE: the journey ledger and trend lines (M3 T31), the session timeline (M2), and
anything that READS this store to make a decision. M1 only writes it.
````

---

### EL-209 — T14 LLM client + router (stdlib HTTP)

**Type:** Story · **Est:** 1 · **Depends:** *the fixture-20 ruling* · **Blocks:** EL-210 ·
**Done when:** one call works, the router selects by job, and cost is counted

**Story.** *As a developer who has not granted anything, I want to know that EvalLoop will not send
my code anywhere until I say so — and when it does, what it cost.*

⚠ **This is the first code in the project that can send a developer's artifact to an external
service.** §4.3: the guard for that is fixture 20, which is blocked, and whose recommended ruling
puts redaction in the M2 capability broker — one milestone after this ticket. **Do not resolve that
by writing a redactor you were not asked for, and do not resolve it by sending the artifact.**
Report which of the two M1 is running under.

**Files** → `evalloop/capability/__init__.py`, `llm.py`, `router.py` · `tests/test_llm_router.py`

**Subtasks**
- [ ] `urllib.request`-based client: retry with backoff, timeout, typed error taxonomy
- [ ] Router keyed by job: `classify` / `author` / `judge` / `diagnose` (`AGENT.md §4`)
- [ ] **Hard assertion:** a `judge` job may not use the generator's model family. Raise, never warn
- [ ] Cost accounting per call and per session, with a session budget and a hard stop
- [ ] Credentials read only here. No other module may hold one
- [ ] Offline by default in tests: a fake transport, zero network in CI
- [ ] Record model id, parameters and seed with every response, for reproducibility

**Acceptance criteria**
- [ ] `mypy --strict` clean with no `Any` on the response path
- [ ] The cross-family assertion has a test that proves it **raises**, naming both families
- [ ] Retry is bounded, jittered and total-time capped; a test proves it gives up
- [ ] Budget exhaustion stops the session with a stated reason, and is tested
- [ ] **No test touches the network.** The suite passes with no credentials present
- [ ] Model ids are configuration, not literals in logic, and are current — read the `claude-api`
      skill before writing one; do not type one from memory
- [ ] Temperature/seed handling recorded per `ARCHITECTURE.md §9`: "fixed seed/temperature where
      possible; otherwise repeat and report variance, never a single number"
- [ ] The egress question from §4.3 is answered in the report, not in the code

**Out of scope** The judge grader itself (M4, T33). Calibration and κ gating (M4, T36). The full
capability broker — consent UI, grants, rate-limit policy (M2). This ticket is the client and the
router, nothing more.

**Gotchas** The cross-family rule is in `AGENT.md §5` as a non-negotiable *and* in the corpus as
`F5_cross_family_panel`. Implemented as a warning it is worthless: the whole point is that the
router makes self-preference bias impossible rather than discouraged.

````text
WHAT I WANT
evalloop/capability/llm.py and router.py: a stdlib-HTTP LLM client with retry and backoff, and a
router that selects by job and counts cost.

READ THIS FIRST -- THE SAFETY QUESTION THIS TICKET OPENS
This is the first code in EvalLoop that can send a developer's artifact to an external service.
The guard for that is the PHI gate, which is fixture 20 in tests/fixtures/planner/ -- and
fixture 20 is BLOCKED. Read its header. Its recommended option (D) makes redaction-before-egress
a capability-broker concern, and the capability broker is ARCHITECTURE.md section 7 component 11,
which is M2. So the egress arrives one milestone before the policy that governs it.
ARCHITECTURE.md section 4.3 says "redaction is a boundary, not a filter", and section 9 requires
no outbound LLM call on PHI without an explicit grant.

You have two honest options and you must REPORT which one M1 is running under:
  (a) this client carries a minimal redaction boundary, in which case say exactly what it
      redacts and what it cannot; or
  (b) M1 makes no outbound call on an artifact that has not been cleared, in which case the
      client is built and tested against a fake transport only.
Do not resolve this by writing an unrequested redactor, and do not resolve it by sending the
artifact. It is a ruling, and it is mine.

WHAT IS IN THE TICKET
AGENT.md section 4: the capability layer owns LLM routing by job -- classify / author / judge /
diagnose -- plus credentials, cost tracking and rate limits. "LLM client is stdlib HTTP with
retry + backoff. No SDK wrappers."
AGENT.md section 5, non-negotiable: "Never same-family judging." The corpus backs it as
F5_cross_family_panel, and the Tool enum has a separate llm_api_cross_family member for it.

THE RESULT I WANT TO SEE
1. A urllib.request client with bounded retry, jittered backoff, a total-time cap and a typed
   error taxonomy. mypy --strict clean with no Any on the response path.
2. A router keyed by job. For the judge job, a HARD ASSERTION that the model family differs
   from the generator's -- it RAISES, naming both families. A warning is worthless here: the
   point is that self-preference bias is impossible, not discouraged. Test that it raises.
3. Cost accounted per call and per session, with a session budget and a hard stop.
   ARCHITECTURE.md section 9 lists cost runaway as a corner case. Test the stop.
4. Credentials read ONLY in this module. No other module may hold one -- ARCHITECTURE.md
   section 9: "Credentials in a grader: impossible by construction."
5. NO TEST TOUCHES THE NETWORK. A fake transport, and the suite passes with no credentials
   present. CI must never need a key.
6. Model ids as configuration, never literals in logic, and CURRENT: read the claude-api skill
   before writing a model id. Do not type one from memory.
7. Model id, parameters and seed recorded with every response. ARCHITECTURE.md section 9: fixed
   seed and temperature where possible, otherwise repeat and report variance, never a single
   number.

OUT OF SCOPE: the judge grader (M4 T33), calibration and the kappa gate (M4 T36), and the rest
of the capability broker -- consent, grants, rate-limit policy (M2). Client and router only.
````

---

## Group 2 — Memory, situation and oracles *(after 🔒 Gate 0)*

### EL-201 — T7 Metric store (JSONL)

**Type:** Story · **Est:** 1 · **Depends:** 🔒 Gate 0 · **Blocks:** EL-206, EL-213 ·
**Done when:** two runs can be diffed case by case

**Story.** *As a developer who just changed one function, I want to see which specific cases flipped
— in both directions — not a score that moved two points.*

**Files** → `evalloop/memory/__init__.py`, `case.py`, `metric_store.py` · `tests/test_metric_store.py`

**Subtasks**
- [ ] **Full schema on day one** (`PLAN.md` T7). Decide every field now; adding one later invalidates
      every stored run
- [ ] Per-case record: case id, artifact id, oracle + oracle confidence (HIGH/LOW), record id
      (`A1_execution_based`), verdict, score, duration, failure class, seed, run id
- [ ] `case_kind`: `generated` vs `permanent` (`AGENT.md §3.9`; `I-production.md:273`'s flywheel)
- [ ] Append-only JSONL writer; typed reader; stable field order so a diff of the file is readable
- [ ] `diff_runs(run_a, run_b)` → per-case flips **in both directions**, never a net delta
- [ ] Content-hash per case, so EL-214 can skip an unchanged artifact (`AGENT.md §3.9`)
- [ ] Failure-class field per `A-choosing-how-to-grade.md:39`: syntax error / unknown column /
      runtime error / wrong result

**Acceptance criteria**
- [ ] Two runs written and diffed per case, with regressions listed separately from improvements
- [ ] A diff of the raw JSONL file is human-readable: one case per line, stable key order
- [ ] Round-trip is lossless, and a reader rejects an unknown schema version loudly
- [ ] `permanent` cases survive a run that does not re-generate them
- [ ] The verdict type is the one EL-014 settles. If EL-014 is open, this ticket **stops** and says so
- [ ] Every field is used by something, or documented as reserved with the ticket that will use it
- [ ] No absolute path; store location is an argument

**Out of scope** Trend lines across many runs (M3, T31). The episodic store (EL-202). Any
statistics over the stored cases — `evalloop/stats/` owns that, and this store does not import it.

**Gotchas** "Full schema day one" and "never invent a number" pull against each other: a field you
cannot fill yet is fine, a field you fill with a guessed default is not. Null it and name the ticket
that fills it. The field list above is the floor — read `USER_EXPERIENCE.md §3.4`'s six report
sections and check nothing it needs is missing, because EL-211 renders from this store alone.

````text
WHAT I WANT
evalloop/memory/case.py and metric_store.py: an append-only JSONL metric store with the FULL
schema on day one, and diff_runs() that compares two runs case by case.

WHAT IS IN THE TICKET
PLAN.md T7: "Metric store: JSONL writer/reader, full schema day one. Done when: two runs
written, diffed per-case." The "full schema day one" is deliberate: adding a field later
invalidates every run already stored, so decide the whole schema now.
AGENT.md section 3.9 adds two requirements: cases are `generated` (ephemeral) or `permanent`
(promoted, e.g. failures-as-tests), and a content-hash cache means an unchanged diff is never
re-evaluated.

THE SCHEMA FLOOR -- per case, at minimum:
  case id · artifact id · oracle id and oracle confidence (HIGH or LOW) · the registry record id
  that produced this judgement (e.g. A1_execution_based) · verdict · score · duration · failure
  class · seed · run id · case_kind (generated | permanent) · content hash.

The failure class comes from the corpus, not from you: knowledge rules/A-choosing-how-to-grade.md:39
says "Tag each failure as a syntax error, unknown column, runtime error or wrong result. That
gives you error analysis for free." Use those four.

THE RESULT I WANT TO SEE
1. The store, append-only, with a schema version in the file and a reader that rejects an
   unknown version loudly rather than guessing.
2. Stable field order, so `diff` on the raw JSONL is readable by a human. One case per line.
3. diff_runs(run_a, run_b) reporting PER-CASE FLIPS IN BOTH DIRECTIONS -- improvements and
   regressions listed separately. Never a net delta. AGENT.md section 3.8 and
   USER_EXPERIENCE.md section 3.4 both require both directions, because a +2 that hides six
   regressions is the failure mode this store exists to prevent.
4. A test that writes two runs and diffs them, asserting both lists.
5. `permanent` cases surviving a run that does not regenerate them.
6. Lossless round-trip, and no absolute path -- the store location is an argument.
7. Before you finalise the field list, read USER_EXPERIENCE.md section 3.4's six report
   sections. EL-211 renders summary.md FROM THIS STORE ALONE, so a field it needs and you did
   not store cannot be recovered.
8. Report: any field you had to leave null, and the ticket that will fill it. "Full schema day
   one" and "never invent a number" pull against each other -- a field you cannot fill yet is
   fine, a field you fill with a guessed default is not.

BLOCKING NOTE: the verdict type is what EL-014 settles (timeout = INCONCLUSIVE, or a failure
logged separately). If EL-014 is still open when you start, STOP and say so. Do not pick one.

OUT OF SCOPE: trend lines across runs (M3 T31), the episodic store (EL-202), and any statistics
over the stored cases -- evalloop/stats/ owns those and this module must not import it.
````

---

### EL-204 — T9 Classifier heuristics

**Type:** Story · **Est:** 1.5 · **Depends:** 🔒 Gate 0 · **Blocks:** EL-205, EL-214 ·
**Done when:** 10 sample files are labelled correctly

**Story.** *As a developer who wrote a function and said nothing about it, I want EvalLoop to work
out what kind of thing I built, so that I never have to tell it.*

**Files** → `evalloop/classify/__init__.py`, `heuristics.py` · `tests/fixtures/classify/` (10 files)
· `tests/test_classifier.py`

**Subtasks**
- [ ] Heuristics over a Python file: `ast` only, never regex over source
- [ ] Output `tuple[tuple[Situation, float], ...]` — **multi-label with confidence** (`AGENT.md §3.4`)
- [ ] Hand-write the 10 sample files **before** the classifier, and never edit one to pass
- [ ] Signals: SQL strings → `sql_generation`; a route decorator → `api_endpoint`; a Pydantic-style
      or `TypedDict` return → `structured_extraction`; plain function → `code_generation`
- [ ] Abstain explicitly. Low confidence is a stated outcome, not a guessed label
- [ ] Handle the six dead situations (§7.3): if a classification reaches one, say so rather than
      emitting an empty plan silently
- [ ] No LLM call in this ticket (`AGENT.md §3.4`: "an LLM is called **only if** heuristics are unclear")

**Acceptance criteria**
- [ ] 10 hand-written samples, each labelled correctly, each with a one-line justification in the
      fixture itself
- [ ] Multi-label proven: at least one sample yields two situations (fixture 18's `api_endpoint +
      sql_generation` pair is the registry's own precedent)
- [ ] Confidence is reproducible, documented, and not a magic constant per branch
- [ ] An unclassifiable file returns **empty with a reason**, never a default label
- [ ] `ast.parse` failure is handled: a half-written file is unclassifiable, not misclassified
- [ ] Python only (`PLAN.md` T9 says "Python only"); another language abstains, loudly
- [ ] Deterministic: same file, same labels, same confidences, same order

**Out of scope** The LLM fallback. The coherence detector (M2) — this ticket assumes it is handed a
file worth looking at. Non-Python languages (T40).

**Gotchas** The classifier is the front door, and `GATE0-REVIEW-PACKET.md §5` names it the weakest
link: "`match()` is only as good as the situation mapping." A wrong label produces a confident,
well-rendered, entirely wrong plan — which is worse than an empty one. Prefer abstention over reach.

````text
WHAT I WANT
evalloop/classify/heuristics.py: heuristics that look at a Python file and return
tuple[tuple[Situation, float], ...] -- multi-label, with confidence.

WHAT IS IN THE TICKET
AGENT.md section 3.4: heuristics first, Python-only at M1, an LLM called ONLY if heuristics are
unclear (not this ticket), output multi-label with confidence. Done-when: correctly labels 10
sample files.

WHY THIS TICKET IS THE RISKIEST IN M1
GATE0-REVIEW-PACKET.md section 5 names this the weakest link in the whole system: "match() is
only as good as the situation mapping, and that mapping is where the corpus and the enum fit
worst." A wrong label produces a confident, well-ordered, fully-rendered, entirely wrong plan.
That is strictly worse than an empty plan. Prefer abstaining over reaching.

THE RESULT I WANT TO SEE
1. Ten sample Python files in tests/fixtures/classify/, HAND-WRITTEN BEFORE THE CLASSIFIER, each
   carrying a one-line comment saying which Situation members it should produce and why. Never
   edit one to make the classifier pass -- CLAUDE.md section 7 rule 4.
2. Heuristics over `ast` ONLY. No regex over source text. A file that fails ast.parse is
   unclassifiable, not misclassified -- half-written code is the normal case here.
3. Multi-label proven by at least one sample producing two situations. The registry's own
   precedent is fixture 18: api_endpoint + sql_generation.
4. Confidence that is reproducible and documented. Not a magic constant per branch.
5. Explicit abstention: an unclassifiable file returns EMPTY WITH A REASON, never a default
   label. A non-Python file abstains loudly -- PLAN.md T9 scopes this to Python.
6. Determinism: same file, same labels, same confidences, same order.
7. SIX SITUATION MEMBERS REACH NO RECORD: classification, data_pipeline, model_training,
   contamination_risk, distribution_mismatch, phi_present. If a classification lands on one of
   them the planner returns an empty plan with no explanation. Either refuse to emit those
   members and say why, or emit them and surface the dead end. Report which you chose.

Read evalloop/vocab/situations.py before you start -- it carries the corpus citation for every
member, and the artifact family is the one you are classifying into.

OUT OF SCOPE: the LLM fallback, the coherence detector (M2 -- assume you are handed a file worth
looking at), and non-Python languages (T40).
````

---

### EL-205 — T10 Oracle harvester

**Type:** Story · **Est:** 1.5 · **Depends:** EL-204 · **Blocks:** EL-207, EL-210 ·
**Done when:** HIGH-confidence oracles come back from a real repo

**Story.** *As a developer whose repo already has tests and type hints, I want EvalLoop to use what
I already wrote rather than inventing something weaker and calling it ground truth.*

**Files** → `evalloop/grade/__init__.py`, `oracles/__init__.py`, `oracles/harvest.py` ·
`tests/test_oracle_harvest.py`

**Subtasks**
- [ ] Find existing tests for an artifact: `test_*.py` / `*_test.py`, and the test functions that
      reference the artifact's symbols
- [ ] Find schemas: `TypedDict`, dataclasses, JSON Schema files, `pydantic`-shaped classes
- [ ] Find type hints on the artifact's own signature
- [ ] Tag each harvested oracle **HIGH** (`AGENT.md §3.6`) with its provenance (file, line, kind)
- [ ] Return nothing rather than something weak. No oracle is a valid, reportable answer
- [ ] `ast` only. Do not import or execute repo code to discover an oracle
- [ ] Run against this repo as the "real repo" in the done-when, and report what came back

**Acceptance criteria**
- [ ] Runs against `/Users/abhinav/Eval-harness-Engine` itself and returns HIGH oracles for named
      functions, with provenance that resolves to a real `file:line`
- [ ] **Never imports or runs repo code.** A malicious `conftest.py` cannot execute during harvest
- [ ] An artifact with no oracle returns empty with a reason, and that reason reaches the report
- [ ] HIGH is reserved for things a human wrote. Nothing this ticket produces is ever LOW
- [ ] A test that was already failing before the change is identified as such, not credited to the
      developer's change
- [ ] Deterministic ordering of returned oracles

**Out of scope** Authoring oracles (EL-210). Running them (EL-206/EL-207). Non-Python. Oracle
*diffing* for reward-hack detection (M3) — but store enough provenance that M3 can do it.

**Gotchas** `ARCHITECTURE.md §9` names the reward-hack case: "Diff the oracle, not just the code.
Oracle change + score rise = reward-hacking flag." M3 implements it; M1 must record enough for M3 to
be able to. If the provenance you store cannot answer "did this test change?", M3 has to re-harvest
history and the flag arrives a milestone late.

````text
WHAT I WANT
evalloop/grade/oracles/harvest.py: find oracles that already exist in a repo -- tests, schemas,
type hints -- and return them tagged HIGH with their provenance.

WHAT IS IN THE TICKET
AGENT.md section 3.6: "Harvest existing (HIGH confidence): existing tests, schemas, type hints in
the repo." PLAN.md T10's done-when: "Returns HIGH-confidence oracles from a real repo."
The HIGH/LOW split is load-bearing: HIGH means a human wrote this, LOW means we generated it and
it is never ground truth. Nothing this ticket produces is ever LOW.

THE RESULT I WANT TO SEE
1. Harvesting of three kinds, via `ast` only:
     - existing tests: test_*.py and *_test.py, and specifically the test functions that
       reference the artifact's own symbols;
     - schemas: TypedDict, dataclasses, JSON Schema files, pydantic-shaped classes;
     - type hints on the artifact's own signature.
2. NEVER import or execute repo code to discover an oracle. Harvesting runs against untrusted
   source: a repo's conftest.py must not get to run during discovery. ast.parse only.
3. Every oracle tagged HIGH, with provenance -- file, line, kind -- that resolves to a real
   location.
4. Returning NOTHING when there is nothing. "No oracle available" is a valid answer and
   ARCHITECTURE.md section 9 requires it: "the ladder descends; if nothing can decide, it says so
   and queues a human review item. It does not invent an oracle." The reason must reach the
   report.
5. A test that was ALREADY FAILING before the developer's change identified as such. Crediting a
   pre-existing failure to the current change is a false finding, and a tool that cries wolf is
   the one thing USER_EXPERIENCE.md section 1 says the developer will not tolerate.
6. Deterministic ordering.
7. Run it against this repo -- /Users/abhinav/Eval-harness-Engine, which has 16 test modules --
   as the "real repo" in the done-when, and report what came back for three named functions.

CARRY FOR M3: ARCHITECTURE.md section 9 says "Diff the oracle, not just the code. Oracle change
+ score rise = reward-hacking flag." M3 implements that. Store enough provenance that it CAN --
if what you record cannot answer "did this test change between runs?", the flag arrives a
milestone late. Say in your report whether it can.

OUT OF SCOPE: authoring oracles (EL-210), running them (EL-206, EL-207), non-Python, and the
reward-hack diff itself (M3).
````

---

## Group 3 — Execution *(the critical path)*

> These three write `evalloop/grade/`. **Do not batch them.** EL-207's partial-credit rule is the one
> place in M1 where a wrong default produces a plausible-looking score, and a batched session is a
> session where no one looked at it.

### EL-206 — T11 Sandbox runner

**Type:** Story · **Est:** 1.5 · **Depends:** EL-201, **EL-014** · **Blocks:** EL-207, EL-208 ·
**Done when:** a timeout produces the outcome EL-014 specifies, and nothing escapes the tempdir

**Story.** *As a developer whose code might loop forever or delete a file, I want EvalLoop to run it
somewhere it cannot hurt me, and to tell me plainly when it could not get an answer.*

**Files** → `evalloop/grade/verdict.py`, `evalloop/grade/sandbox.py`, `evalloop/grade/config.py`
(per EL-015) · `tests/test_sandbox.py`

**Subtasks**
- [ ] `verdict.py`: the outcome enum EL-014 settled, plus a result record carrying stdout, stderr,
      exit code, duration and the resource limits that were in force
- [ ] `subprocess` + `resource.setrlimit` + wall-clock timeout + `tempfile` working directory
- [ ] Limits: CPU, address space, file size, open files, **and no network** (`ARCHITECTURE.md §9`:
      "Egress denied in the sandbox by default")
- [ ] The 10-second timeout and row cap come from `A:37` via EL-015's config, not from this module
- [ ] Clean teardown even on timeout, signal or exception. No orphan processes, no leftover tempdirs
- [ ] Env scrubbed: no credentials reach the child (`ARCHITECTURE.md §9`)
- [ ] Record the exact command, limits and seed in the result, so a run is reproducible

**Acceptance criteria**
- [ ] An infinite loop is killed at the wall-clock cap and produces EL-014's outcome, **tested**
- [ ] A child writing outside its tempdir fails; a test proves it
- [ ] A network call from inside fails closed, and the failure is distinguishable from a logic failure
- [ ] A child reading `os.environ` finds no credential; a test proves it
- [ ] No orphan process after a timeout; a test proves it
- [ ] The same command run twice gives byte-identical results, or the nondeterminism is recorded
- [ ] Limits are inspectable in the result, so a report can say *which* cap was hit
- [ ] Platform assumptions stated: `resource.setrlimit` behaves differently on macOS and Linux, and
      the ticket says what is enforced where rather than assuming

**Out of scope** Grading. Hidden-test isolation (EL-207). Containers or VMs — `PLAN.md` T11 says
"subprocess + rlimits + timeout + tempdir", and that is the whole brief.

**Gotchas** This runs code written by an AI assistant that the developer has not read. It is the
single most security-relevant module in M1. `ARCHITECTURE.md §9` lists its requirements in two
tables; read both before writing, and state honestly what a subprocess sandbox cannot contain.

````text
WHAT I WANT
evalloop/grade/sandbox.py and verdict.py: run a command safely and return a typed result.
subprocess + resource.setrlimit + wall-clock timeout + tempfile working directory.

WHY THIS IS THE MODULE TO BE CAREFUL IN
It executes code that an AI assistant wrote and the developer has not read. ARCHITECTURE.md
section 9 spells out the requirements across two tables -- read both before writing a line:
  - "Timeout / infinite loop: wall-clock cap -> INCONCLUSIVE, distinct from fail"
  - "Network-dependent code: egress denied in the sandbox by default; network need is a declared
    capability"
  - "A grader could mutate real state: writes only in a scratch schema or restored snapshot"
  - "Credentials in a grader: impossible by construction -- only the capability broker holds them"

BLOCKING DEPENDENCY -- EL-014
The outcome enum is what EL-014 settles. Our docs say a timeout is INCONCLUSIVE, never pass or
fail. The corpus, at knowledge rules/A-choosing-how-to-grade.md:37, says "Count a timeout as a
failure but log it separately". If EL-014 is not decided when you start, STOP. Do not pick one
and do not define a placeholder -- EL-201 already persists this type.

BLOCKING DEPENDENCY -- EL-015
The 10-second timeout and the row cap are corpus values from A:37 and they live wherever EL-015
put them. Import them. Do not write `timeout=10` in this module.

THE RESULT I WANT TO SEE
1. verdict.py: EL-014's outcome enum, plus a result record carrying stdout, stderr, exit code,
   duration, the limits in force, the exact command, and the seed.
2. sandbox.py enforcing CPU, address space, file size, open files, no network, and a wall-clock
   cap, in a tempfile working directory, with the child's environment scrubbed of credentials.
3. Tests that PROVE each of these, not that assume them:
     - an infinite loop is killed at the cap and produces EL-014's outcome;
     - a child writing outside its tempdir fails;
     - a network call from inside fails closed, DISTINGUISHABLY from a logic failure -- a grader
       that scores "no internet" as "wrong answer" is a liar;
     - a child reading os.environ finds no credential;
     - no orphan process survives a timeout.
4. Clean teardown on timeout, on signal and on exception. No orphans, no leftover tempdirs.
5. The limits inspectable in the result, so a report can say WHICH cap was hit. "It failed" and
   "it ran out of memory" are different findings.
6. Byte-identical results across two runs of the same command, or the nondeterminism recorded.
7. A stated platform section: resource.setrlimit behaves differently on macOS and Linux. Say what
   is actually enforced on each rather than assuming. Then say plainly, in the module docstring,
   what a subprocess sandbox CANNOT contain. An honest limit is worth more than a confident one.

OUT OF SCOPE: grading, hidden-test isolation (EL-207), and containers or VMs. PLAN.md T11 scopes
this to subprocess + rlimits + timeout + tempdir.
````

---

### EL-207 — T12 Execution grader

**Type:** Story · **Est:** 2 · **Depends:** EL-206, EL-205, **EL-015** · **Blocks:** EL-211 ·
**Done when:** a deliberately broken function is caught

**Story.** *As a developer who wrote a function with an off-by-one in it, I want EvalLoop to run it
and tell me it is broken — not read it and tell me it looks good.*

**Files** → `evalloop/grade/execution.py` · `tests/test_execution_grader.py`,
`tests/test_mutation_selfcheck.py`

**Subtasks**
- [ ] Grade an artifact against a harvested oracle by **running** it, never by reading it
- [ ] **Hidden-test isolation:** the artifact must not see the test that grades it
- [ ] **Partial credit:** per-case, aggregated; the headline is the full-pass rate (`H:170`: "give
      partial credit for internal tracking only. The headline metric is still full-task success")
- [ ] **Compile-vs-logic split:** a syntax error and a wrong answer are different findings (`A:39`)
- [ ] Result comparison per `A:35`: ignore row order unless ordering was asked for, ignore aliases,
      float tolerance `1e-6` from EL-015's config
- [ ] Failure classes from `A:39`: syntax error / unknown column / runtime error / wrong result
- [ ] **Mutation self-check** per `A:38`: mutate the reference, and if the mutant passes more than
      **5%** of the time, report that the fixtures are not discriminating
- [ ] Implements `A1_execution_based`; carries that record id into every stored case

**Acceptance criteria**
- [ ] Catches a deliberately broken function — the toy fixture, not the Gate 1 repo
- [ ] A test proves the artifact **cannot read** its hidden tests
- [ ] The headline number is the full-pass rate; partial credit is present but never promoted
- [ ] A syntax error and a wrong answer produce different failure classes, and both are stored
- [ ] The mutation self-check runs and reports against `A:38`'s 5% bar, with the bar cited
- [ ] `A1`'s `companion_checks: [C1_wilson_ci]` is honoured: no pass rate is reported without its
      interval. The planner already says so; this is where it becomes true
- [ ] A pre-existing failure is never attributed to the current change (from EL-205)
- [ ] Equivalent-but-different output is **not** marked wrong — `A1`'s own anti-pattern

**Out of scope** SQL and API grading (Track V needs `db_connection`). Judging (M4). The reward-hack
oracle diff (M3). Non-Python.

**Gotchas** `A1`'s worked example is the ticket's own warning: on 200 text-to-SQL items, exact match
scored 41%, execution match 68%, and a judge 79% — "which means it passed 22 queries that returned
the wrong rows" (`A:31`). A grader built to agree with a plausible reading of the code reproduces the
79%. The 68% is the number that is true.

````text
WHAT I WANT
evalloop/grade/execution.py: grade an artifact by RUNNING it against a harvested oracle. This is
rung 1 of the ladder and the record it implements is A1_execution_based.

WHAT IS IN THE TICKET
PLAN.md T12: "Execution grader: hidden-test isolation, partial credit, compile/logic split. Done
when: catches a deliberately broken function."
The corpus section is knowledge rules/A-choosing-how-to-grade.md, A1, lines 28-41. READ ALL SIX
OF ITS "How to do it properly" STEPS before writing. Four of them are this ticket:
  A:35  compare results, not formatting -- ignore row order unless ordering was asked for,
        ignore aliases, float tolerance 1e-6 (comes from EL-015's config, not a literal here)
  A:37  resource limits (EL-206 owns these)
  A:38  test your tests -- mutate the reference solution; if the mutant still passes more than
        5% of the time, the fixtures are not discriminating enough
  A:39  log the failure class: syntax error, unknown column, runtime error, wrong result

THE WARNING THIS TICKET SHOULD BE BUILT AROUND
A:31, A1's own evidence: on 200 text-to-SQL items, exact match scored 41%, execution match 68%,
and an LLM judge 79% -- "which means it passed 22 queries that returned the wrong rows." A grader
that is built to agree with a plausible reading of the code reproduces the 79%. The 68% is the
number that is true. Every design choice in this module should be checked against that.

THE RESULT I WANT TO SEE
1. Grading by execution, through EL-206's sandbox. Never by reading the artifact.
2. HIDDEN-TEST ISOLATION, with a test that PROVES the artifact cannot read the tests that grade
   it. Not a convention -- a proof.
3. PARTIAL CREDIT per case, aggregated, with the HEADLINE being the full-pass rate.
   knowledge rules/H-agents.md:170 states the rule: "Give partial credit for internal tracking
   only. The headline metric is still full-task success." Partial credit that gets promoted to
   the headline is how a broken function scores 80%.
4. COMPILE-VS-LOGIC SPLIT: a syntax error and a wrong answer are different findings, stored as
   different failure classes from A:39's four.
5. A MUTATION SELF-CHECK: mutate the reference (flip a comparator, drop a condition) and report
   against A:38's 5% bar. Cite the bar. This is the grader grading itself, and it is the only
   thing standing between us and fixtures that pass wrong answers by coincidence.
6. A1's companion_checks is [C1_wilson_ci]. The planner already says a pass rate travels with its
   interval; THIS is where that becomes true. Use evalloop/stats/ from EL-203 -- do not compute an
   interval here.
7. A deliberately broken function caught, in a small fixture of your own. NOT the Gate 1 toy repo
   -- EL-212 owns that, and a grader tested on the gate's own fixture tests nothing.
8. Equivalent-but-different output NOT marked wrong. A1's anti-pattern is "string match marks
   correct-but-different SQL as wrong".
9. A pre-existing failure never attributed to the current change -- EL-205 identifies those.

OUT OF SCOPE: SQL and API grading (Track V, needs db_connection), judging (M4), the reward-hack
oracle diff (M3), and non-Python.
````

---

### EL-208 — T13 Deterministic grader

**Type:** Story · **Est:** 1 · **Depends:** EL-206, **EL-015** · **Blocks:** EL-214 ·
**Done when:** schema, regex and exact checks work, with the cascade hook in place

**Story.** *As a developer extracting fields into a schema, I want the shape checked by code rather
than by a model, because code is free, instant and does not have an opinion about numbers.*

**Files** → `evalloop/grade/deterministic.py` · `tests/test_deterministic_grader.py`

**Subtasks**
- [ ] Schema validation (rung 3's `A5_schema_field_scoring`), regex, exact match and normalised
      exact match (`A3_normalised_exact_match`)
- [ ] Normalisation rules from `A3`'s own `required_signals`: case, whitespace, unit and number
      formats normalised deterministically
- [ ] **Identifier fields excluded from normalisation** — IFSC, GSTIN, PAN, policy number, PIN code
      matched exactly, with a format or checksum check (`A3`'s signal, verbatim)
- [ ] Token-F1 for multi-word answers, with `A:111`'s threshold from EL-015's config
- [ ] Per-field scoring, not per-record pass/fail, for `A5`
- [ ] A cascade hook: a stub boundary where a cheap check hands off to a more expensive rung
- [ ] Accepted alternatives listed **per item**, not handled by a looser normaliser (`A3`'s signal)

**Acceptance criteria**
- [ ] `"₹1,50,000"`, `"150000"` and `"1.5 lakh"` all normalise to `150000` — `A3`'s worked example
      verbatim (`A:` A3 `worked_example`)
- [ ] `"HDFC0001234"` is matched **exactly**, never normalised — `A3`'s domain scenario: "one wrong
      character routes money to the wrong branch"
- [ ] Token-F1 uses `A:111`'s stated threshold from config, with its citation
- [ ] The cascade hook is a typed boundary with a test, not a `TODO` comment
- [ ] `A3` and `A5` both `conflict_with A4_judge_binary_criteria`; nothing here ever calls an LLM
- [ ] Per-field results stored, so `A5`'s field-level scoring survives into the report
- [ ] Both records' `companion_checks: [C1_wilson_ci]` honoured

**Out of scope** The judge the cascade hands off to (M4). The normaliser's monthly audit procedure
(`A:112`) — EL-015 homes the number; the procedure is M3's error analysis.

**Gotchas** `A3`'s anti-pattern is precisely the temptation here: "Switching to an LLM judge because
exact match is 'too strict'. The fix is a better normaliser. A judge adds leniency where you least
want it: on numbers" (`A:127`). If a case feels like it needs a judge, that is a normalisation bug or
a missing per-item alternative — report it as one.

````text
WHAT I WANT
evalloop/grade/deterministic.py: schema validation, regex, exact and normalised-exact matching,
token-F1, and a cascade hook. Ladder rung 3. It implements two records:
A3_normalised_exact_match and A5_schema_field_scoring.

WHAT IS IN THE TICKET
PLAN.md T13: "Deterministic grader: schema/regex/exact + cascade hook. Done when: validates
output shape; cascade stub in place."
Read both records in evalloop/registry/records/A_grading.yaml before writing -- their
required_signals ARE the specification, and three of A3's four signals are rules you would
otherwise get wrong:
  - case, whitespace, unit and number formats normalised deterministically;
  - IDENTIFIER FIELDS EXCLUDED FROM NORMALISATION -- IFSC, GSTIN, PAN, policy number, PIN code
    matched exactly, with a format or checksum check;
  - accepted alternatives listed PER ITEM rather than handled by a looser normaliser.

THE TWO WORKED EXAMPLES THAT ARE YOUR ACCEPTANCE TESTS, from A3:
  "₹1,50,000", "150000" and "1.5 lakh" all normalise to 150000.
  "HDFC0001234" must match EXACTLY, because one wrong character routes money to the wrong branch.
Those two pull in opposite directions, and holding both at once is the ticket.

THE ANTI-PATTERN TO BUILD AGAINST
A3's own, at knowledge rules/A-choosing-how-to-grade.md:127: "Switching to an LLM judge because
exact match is 'too strict'. The fix is a better normaliser. A judge adds leniency where you
least want it: on numbers." If a case feels like it needs a judge, it is a normalisation bug or a
missing per-item alternative. Report it as one; do not reach for rung 4. Both A3 and A5 declare
conflicts_with A4_judge_binary_criteria, so nothing in this module may call an LLM.

THE RESULT I WANT TO SEE
1. Schema validation, regex, exact match, normalised exact match, and token-F1 for multi-word
   answers -- with A:111's threshold taken from EL-015's config, cited, not typed as a literal.
2. PER-FIELD scoring for A5, not per-record pass/fail, stored per field so the report can show
   which field failed.
3. A cascade hook that is a TYPED BOUNDARY WITH A TEST -- the place a cheap check hands off to a
   more expensive rung. A TODO comment is not a hook. CLAUDE.md section 3 forbids stub bodies.
4. Both records' companion_checks: [C1_wilson_ci] honoured, using evalloop/stats/ from EL-203.
5. Tests for both worked examples above, each citing its source line.

OUT OF SCOPE: the judge the cascade hands off to (M4), and A:112's monthly normaliser audit
procedure -- EL-015 homes that number, and the procedure belongs to M3's error analysis.
````

---

## Group 4 — Authoring an oracle where none exists

### EL-210 — T15 Test author (signature-only)

**Type:** Story · **Est:** 2 · **Depends:** EL-209, EL-205 · **Blocks:** EL-214 ·
**Done when:** tests are generated from the signature alone and tagged HIGH/LOW correctly

**Story.** *As a developer who wrote a function and no test for it, I want EvalLoop to work out what
the function is supposed to do from its name, signature and docstring — not from the body, which is
where my bug is.*

⚠ **Whether this ticket is on the critical path is an open ruling.** §4.4: under Gate 1 Reading A
(the toy repo has tests) EL-205 is enough and this can defer to E6; under Reading B (no tests) this
is the ticket that makes Gate 1 mean what it says.

**Files** → `evalloop/grade/oracles/author.py` · `tests/test_test_author.py`

**Subtasks**
- [ ] Generate a test from **signature, name, docstring and type hints only**
- [ ] **Hard isolation from the implementation body.** Structurally impossible, not merely avoided
- [ ] Tag every generated oracle **LOW** (`AGENT.md §3.6`), never HIGH, with no override
- [ ] Confidence reasoning recorded: *why* this is LOW, and what would make it HIGH
- [ ] Route through EL-209's router with job `author`
- [ ] Reject a generated test that does not run, or that passes against an empty stub
- [ ] Generated tests are `case_kind: generated` in the metric store (EL-201), never `permanent`

**Acceptance criteria**
- [ ] A test proves the implementation body is **not** in the prompt — by construction, with an
      assertion over the assembled request, not by reviewer discipline
- [ ] A generated test that passes against an empty stub is discarded, and that is tested
- [ ] A generated oracle can never be tagged HIGH; the type system or a raise prevents it
- [ ] The generated test catches a deliberately broken implementation it never saw
- [ ] Cost per authored test recorded, via EL-209
- [ ] Reproducible: same signature + same seed → same test, or the variance is recorded and reported
- [ ] No test in the suite touches the network

**Out of scope** Judging (M4). Promoting a generated case to `permanent` — that is the
failures-as-tests flywheel (`I-production.md:273`), and it is M3/M5. Authoring from a natural-language
intent (needs the M2 transcript reader).

**Gotchas** This is the only module in M1 where the system invents its own ground truth, and
`ARCHITECTURE.md §9` has two guards pointed at it: "Test weakened to pass — diff the oracle, not just
the code" and "No oracle available — it does not invent an oracle." The resolution is the LOW tag,
honestly carried everywhere. A LOW oracle presented to the developer as evidence is the most
damaging single thing M1 could do, because it is a confident number with nothing underneath it.

````text
WHAT I WANT
evalloop/grade/oracles/author.py: generate a test for an artifact from its SIGNATURE ONLY, in
isolation from the implementation, tagged LOW.

WHY ISOLATION IS THE WHOLE TICKET
AGENT.md section 3.6: "Author new (LOW confidence): tests generated from signature only, in
isolation from the implementation. These are tagged LOW so they are never confused with ground
truth."
The reason is mechanical, not stylistic. If the model sees the implementation, it writes a test
that agrees with the bug, and the broken function passes. The test's only value comes from its
never having seen the body. So isolation must be STRUCTURAL -- provable by an assertion over the
assembled request -- not a thing the prompt politely avoids.

WHAT THE AUTHOR MAY SEE: the function name, its signature, its type hints, its docstring, and
the module's public imports. NOT the body. NOT the file.

THE RESULT I WANT TO SEE
1. Generation from signature, name, docstring and type hints, routed through EL-209's router with
   job `author`.
2. A TEST THAT PROVES THE BODY IS NOT IN THE REQUEST -- assert over the assembled payload. This is
   the acceptance criterion that matters; everything else is secondary to it.
3. Every generated oracle tagged LOW, with no override. Make it impossible, through the type or a
   raise -- not a convention. AGENT.md section 3.6 and ARCHITECTURE.md section 9 both treat a
   generated oracle presented as ground truth as a correctness failure, not a labelling slip.
4. The confidence REASONING recorded: why this is LOW, and what would make it HIGH.
5. Rejection of a generated test that does not run, or that PASSES AGAINST AN EMPTY STUB. A test
   that an empty function satisfies asserts nothing. Test that rejection.
6. Proof that a generated test catches a deliberately broken implementation it never saw. That is
   this ticket's version of "catches the broken function", and it is the stronger claim.
7. case_kind: generated in the metric store. Never permanent -- promotion is the
   failures-as-tests flywheel (knowledge rules/I-production.md:273) and belongs to a later
   milestone.
8. Cost per authored test recorded through EL-209, and reproducibility: same signature and same
   seed give the same test, or the variance is recorded and reported rather than hidden.
9. NO TEST IN THE SUITE TOUCHES THE NETWORK. Use EL-209's fake transport.

OPEN RULING YOU SHOULD KNOW ABOUT: whether this ticket is on Gate 1's critical path depends on
whether the Gate 1 toy repo has existing tests. If it does, EL-205's harvesting is enough and this
could have deferred. Note in your report whether anything you built assumes one reading.

OUT OF SCOPE: judging (M4), promoting a case to permanent (M3/M5), and authoring from a stated
natural-language intent, which needs M2's transcript reader.
````

---

## Group 5 — Wiring and output

> The two new tickets are here. Without them M1 is a set of parts and Gate 1 is a human driving
> them by hand, which is the one thing the gate says must not be necessary.

### EL-213 — Evidence assembler **(new)**

**Type:** Story · **Est:** 0.5 · **Depends:** EL-201, EL-203 · **Blocks:** EL-214 ·
**Done when:** `plan()` can be called with evidence derived from what was actually stored

**Story.** *As a developer who has run one test once, I want to be told "needs 25 discordant pairs,
have 8" — with the 8 counted from my actual runs, not typed in by someone.*

**Why this ticket exists.** `plan()`'s fourth argument is `evidence: Mapping[str, object]`, and
**nothing in E2 as originally scoped produces it.** The 73 records declare **33 distinct `requires`
keys**. Without a producer, every readiness bar in M1 is fed by hand — which means the pending queue,
the system's entire honesty claim, is a literal.

**The 33 keys, grouped by who can answer them**

| Group | Keys | Answerable in M1? |
|---|---|---|
| Counted from the metric store | `runs`, `items`, `trials`, `positives`, `failures`, `fail_cases`, `candidates`, `discordant_pairs`, `attempts_per_category`, `smoke_items`, `calibration_items`, `majority_samples` | **Yes** — EL-201 holds them |
| Session or harness facts | `environment_resets_per_run`, `cluster_id_recorded`, `paired_ci_available`, `sample_size_stated`, `recall_at_k_measured`, `requires_pre_instrumentation`, `judgment_orders` | **Partly** — some are M1 config, some are M2/Track V |
| Process facts | `pre_registration_filed`, `release_history_available`, `baseline_days` | **No** — no M1 component knows them |
| Judge trust | `judge_human_kappa_to_trust`, `judge_human_kappa_to_gate`, `judge_labelled_items`, `judge_families`, `expert_kappa`, `target_agreement`, `annotators`, `human_pairwise_judgments`, `alpha_tentative`, `alpha_reliable`, `claim_labels` | **No** — M4 |

**Files** → `evalloop/memory/evidence.py` · `tests/test_evidence_assembler.py`

**Subtasks**
- [ ] `assemble_evidence(store, run_id, session_facts) -> Mapping[str, object]`
- [ ] Count the countable keys from the metric store; never estimate one
- [ ] A key no M1 component can answer is **absent**, not zero — `evaluate_readiness` already treats
      missing as absent, and that is the honest behaviour
- [ ] A coverage test over all 33 keys: each is produced, or declared unanswerable with the milestone
      that will answer it
- [ ] Booleans and numerics kept distinct, as `evaluate_readiness` requires
- [ ] Round-trip against the real registry: assemble, call `plan()`, assert the pending reasons read
      as `"needs <key>: <threshold>, have <actual>"`

**Acceptance criteria**
- [ ] All 33 keys enumerated **from the registry at test time**, not from a list in the test — a key
      added to a record later must fail this test, not pass silently
- [ ] A key with no answer is absent; a test proves absent and zero behave differently in a reason string
- [ ] No key is ever filled with a plausible default. `CLAUDE.md §3` applies here hardest, because a
      guessed `runs: 5` turns a pending check into a false claim
- [ ] `plan()` is called with real assembled evidence in a test, and the rendered pending queue is
      asserted verbatim
- [ ] Report says which of F2's two kinds of bar each produced key is feeding

**Out of scope** Changing the planner, a record, or `requires`. The M3 pending-queue renderer (T27).
Judge-trust keys (M4).

**Gotchas** F2 is open (§3): `requires` holds both "enough evidence yet" and "trustworthy enough to
use", and this ticket is the first code that has to tell them apart. If a key cannot be classified,
that is the finding — it is evidence for the F2 ruling, not a blocker to route around.

````text
WHAT I WANT
evalloop/memory/evidence.py: assemble_evidence(store, run_id, session_facts) -> Mapping[str, object],
the thing that feeds plan()'s fourth argument from what was actually measured.

WHY THIS TICKET EXISTS
plan() takes evidence: Mapping[str, object], and NOTHING in M1 as originally scoped produces it.
The 73 records declare 33 distinct `requires` keys. Without a producer, every readiness bar is fed
by hand, which makes the pending queue -- the system's whole honesty claim -- a literal.
Confirm the count yourself:
  grep -h '^  requires: ' evalloop/registry/records/*.yaml | grep -v 'requires: {}'

THE RULE THAT MATTERS MOST
A key no M1 component can honestly answer is ABSENT, not zero. evaluate_readiness already treats
missing evidence as absent, and absent is the honest state. A guessed `runs: 5` turns a pending
check into a false claim, which is the exact failure CLAUDE.md section 3 and AGENT.md section 5
exist to prevent. Never fill a key with a plausible default.

WHAT CAN AND CANNOT BE ANSWERED IN M1
  Countable from EL-201's metric store: runs, items, trials, positives, failures, fail_cases,
    candidates, discordant_pairs, attempts_per_category, smoke_items, calibration_items,
    majority_samples.
  Session or harness facts, partly answerable: environment_resets_per_run, cluster_id_recorded,
    paired_ci_available, sample_size_stated, recall_at_k_measured, requires_pre_instrumentation,
    judgment_orders.
  Process facts no M1 component knows: pre_registration_filed, release_history_available,
    baseline_days.
  Judge trust, all M4: judge_human_kappa_to_trust, judge_human_kappa_to_gate,
    judge_labelled_items, judge_families, expert_kappa, target_agreement, annotators,
    human_pairwise_judgments, alpha_tentative, alpha_reliable, claim_labels.
Check that grouping against the records yourself. If I have put a key in the wrong group, say so.

THE RESULT I WANT TO SEE
1. The assembler, counting the countable keys from the metric store and never estimating one.
2. Booleans and numerics kept distinct -- evaluate_readiness handles them differently, and 17
   records carry a boolean requirement while six carry a boolean AND a numeric bound.
3. A COVERAGE TEST THAT ENUMERATES THE KEYS FROM THE REGISTRY AT TEST TIME, not from a list
   written into the test. Each key is either produced, or declared unanswerable with the milestone
   that will answer it. A key added to a record next month must FAIL this test, not pass silently.
4. A test proving absent and zero produce different reason strings.
5. A round-trip: assemble real evidence, call plan() with the real registry, and assert the
   rendered pending queue verbatim -- the reasons should read "needs <key>: <threshold>, have
   <actual>" as AGENT.md section 3.5 specifies.
6. Report: which of F2's two kinds of bar each produced key is feeding. F2 is an OPEN RULING --
   `requires` currently holds both "enough evidence yet" and "trustworthy enough to use", and this
   is the first code that has to tell them apart. If a key cannot be classified, that is the
   finding. It is evidence for the ruling, not something to route around.

DO NOT, in this session: change the planner, change a record, change `requires`, build the M3
pending-queue renderer (T27), or produce a judge-trust key (M4).
````

---

### EL-211 — T17 `summary.md` renderer

**Type:** Task · **Est:** 0.5 · **Depends:** EL-207, EL-213 · **Blocks:** EL-214 ·
**Done when:** a readable report per run

**Story.** *As a developer at the end of a run, I want one page that tells me what was checked, what
broke, what could not be answered yet, and what it cost — in that order, without jargon.*

**Files** → `evalloop/report/__init__.py`, `summary.py` · `tests/test_summary_renderer.py`

**Subtasks**
- [ ] Render `USER_EXPERIENCE.md §3.4`'s **six sections, in its order**: what you built · what was
      evaluated and how (rung, oracle confidence HIGH/LOW) · findings including per-item flips **in
      both directions** · what is not yet answerable and what would unlock it · what was prohibited
      and why · cost
- [ ] Reuse `Plan.render()`'s four states rather than reimplementing them
- [ ] Oracle confidence shown per finding, never omitted — a LOW oracle must look LOW on the page
- [ ] Interval next to every rate (`00-INDEX.md:35`, "put a confidence interval on every number")
- [ ] INCONCLUSIVE displayed distinctly from fail (`USER_EXPERIENCE.md §3.2`)
- [ ] Byte-stable output for identical input, so two runs can be `diff`ed

**Acceptance criteria**
- [ ] All six sections present, in order, named as `USER_EXPERIENCE.md §3.4` names them
- [ ] A rate without an interval cannot be rendered — the renderer raises rather than printing a bare
      percentage
- [ ] Flips shown in both directions, with regressions not buried under a net figure
- [ ] "What would unlock it" is the readiness reason from EL-213, not a restatement of the threshold
- [ ] Byte-identical for identical input; a golden-file test proves it
- [ ] No jargon that `USER_EXPERIENCE.md §4.3` would fail: every "no" states why in plain language
- [ ] Renders correctly when **everything** is pending, and when nothing was found — the empty and
      all-pending cases are the common ones on day one, not the edge cases

**Out of scope** The dashboard, SSE and the live timeline (M2). Trend lines (M3). The PR comment (M5).

**Gotchas** `S23-REPORT.md §3` found that a summarization session currently produces an **empty
plan**. So "renders correctly when everything is pending" is not a defensive nicety — it is what the
first real run will look like until F2 is ruled on.

````text
WHAT I WANT
evalloop/report/summary.py: render one run as a readable summary.md.

WHAT IS IN THE TICKET
USER_EXPERIENCE.md section 3.4 names the six sections and their order. Use them, in that order,
with those names:
  1. What you built (situations inferred, with stated intent where available)
  2. What was evaluated and how (rung, oracle confidence HIGH/LOW)
  3. Findings, including per-item flips IN BOTH DIRECTIONS
  4. What is NOT yet answerable, and what would unlock it
  5. What was prohibited, and why
  6. Cost
Section 4 is the one that makes this a summary of an honest system rather than a scoreboard.
Its content comes from EL-213's readiness reasons -- the actual "needs 25, have 8" -- not a
restatement of the threshold.

THE HARD RULES
  - Reuse Plan.render()'s four states. Do not reimplement READY / PENDING / UNAVAILABLE /
    PROHIBITED; the planner already renders them deterministically.
  - A RATE WITHOUT AN INTERVAL CANNOT BE RENDERED. Make the renderer RAISE rather than print a
    bare percentage. knowledge rules/00-INDEX.md:35 is cross-cutting principle: put a confidence
    interval on every number. This is the one place a developer sees the numbers, so it is the
    one place the rule has teeth.
  - Oracle confidence shown per finding, never omitted. A LOW oracle must LOOK low on the page.
  - INCONCLUSIVE displayed distinctly from fail -- USER_EXPERIENCE.md section 3.2.
  - Byte-stable output for identical input, proven by a golden-file test, so two runs can be
    diffed. CLAUDE.md requires determinism and this is where a user would notice its absence.

THE CASE TO BUILD FOR FIRST
S23-REPORT.md section 3 found that a summarization session currently produces an EMPTY PLAN, and
six situation members reach no record at all. So "everything is pending" and "nothing was found"
are the COMMON cases on day one, not edge cases. A renderer that only looks good when there are
findings will mostly look broken. Write those two cases first and make them read well.

Also check USER_EXPERIENCE.md section 4.3: every "no" states why, in plain language. No jargon a
developer would have to look up.

OUT OF SCOPE: the dashboard, SSE and the live timeline (M2); trend lines (M3); the PR comment (M5).
````

---

### EL-214 — One-shot run driver **(new)**

**Type:** Story · **Est:** 1 · **Depends:** EL-204 … EL-211, EL-213 · **Blocks:** EL-212 ·
**Done when:** `evalloop check <path>` walks the whole loop and writes `summary.md`

**Story.** *As a developer with a repo and a bug in it, I want to run one command and get the truth,
having configured nothing.*

**Why this ticket exists.** Gate 1 is "point at a toy repo … caught **with zero instruction from
you**." Nothing in E2 as scoped joins classify → plan → harvest → grade → store → render. The session
orchestrator is M2 (T23), so without this, Gate 1 is run by hand — which is the instruction the gate
forbids.

**Files** → `evalloop/run.py`, `evalloop/__main__.py` · `tests/test_run_driver.py`

**Subtasks**
- [ ] `check(path) -> RunResult`: classify → `plan()` → harvest/author → grade → store → render
- [ ] **One shot, no watching.** No poller, no debouncer, no event loop. It is given a path and returns
- [ ] Capability wiring: `Plan.unavailable` becomes a printed, actionable permission request, never a
      silent skip (`AGENT.md §3.5`)
- [ ] Content-hash skip, via EL-201's hash: an unchanged artifact is not re-graded
- [ ] Honest exit codes: found-a-problem, clean, and **could-not-decide** are three different codes
- [ ] Writes both stores — metric (EL-201) and episodic (EL-202) — if EL-202 landed
- [ ] `--no-llm` runs the whole loop with harvested oracles only, no egress

**Acceptance criteria**
- [ ] One command, no configuration file, no flags required
- [ ] A run where the plan is entirely pending exits cleanly and says what is missing
- [ ] `unavailable` is surfaced as a permission request naming the missing tools in the record's own
      order — `check_capability` already provides that ordering
- [ ] Re-running on an unchanged repo re-grades nothing and says so
- [ ] Exit codes distinguish "a problem was found" from "nothing could be decided"
- [ ] `--no-llm` is proven by a test that asserts zero outbound calls
- [ ] Deterministic: same repo, same seed, same `summary.md` bytes
- [ ] No sensors, no polling, no server. A scope violation here is the easiest mistake in M1 to make

**Out of scope** `evalloop start` / `stop`, the session orchestrator, the worker pool, the queue, the
dashboard, the API (all M2, T23–T26).

**Gotchas** This ticket will feel like it wants to be the M2 orchestrator. It is not: one path in, one
report out, no loop. If it needs to watch for changes to be useful, that is a finding for M2's ticket,
not a thing to add here.

````text
WHAT I WANT
evalloop/run.py and __main__.py: `evalloop check <path>` -- one command that walks the whole M1 loop
on a path and writes summary.md.

WHY THIS TICKET EXISTS
Gate 1 is "point at a toy repo with a deliberately broken function. It gets caught, WITH ZERO
INSTRUCTION FROM YOU." Nothing else in M1 joins the parts: classify -> plan -> harvest or author
-> grade -> store -> render. The session orchestrator is M2 (T23). Without this, Gate 1 is a human
driving six modules by hand, which is precisely the instruction the gate says must not be needed.

WHAT IT IS NOT
It is ONE SHOT. A path in, a report out, and it returns. No poller, no debouncer, no event loop, no
worker pool, no server, no dashboard. All of that is M2 and building any of it here is a scope
violation -- the easiest one to commit in this epic, because this ticket will FEEL like it wants to
be the orchestrator. If it seems to need to watch for changes to be useful, that is a finding for
M2's ticket, not a thing to add here.

THE RESULT I WANT TO SEE
1. check(path) -> RunResult, running the loop in order and writing summary.md.
2. Plan.unavailable turned into a PRINTED, ACTIONABLE PERMISSION REQUEST, never a silent skip.
   AGENT.md section 3.5: "When a tool is missing, the session-level agent turns it into a
   permission request to the user. It does not silently skip." check_capability already names the
   missing tools in the record's declared order, so the text needs no further work.
3. The content-hash skip from EL-201: an unchanged artifact is not re-graded, and the run SAYS it
   skipped. AGENT.md section 3.9.
4. HONEST EXIT CODES -- three of them, not two: a problem was found; everything checked out;
   nothing could be decided. Collapsing the third into either of the others is the dishonesty this
   whole milestone is built against.
5. --no-llm running the entire loop on harvested oracles with zero egress, proven by a test that
   asserts no outbound call. This is also the flag that makes Gate 1 reproducible without a key.
6. Determinism: same repo, same seed, same summary.md bytes.
7. A run whose plan is ENTIRELY PENDING exiting cleanly and saying what is missing. Given that six
   situation members reach no record and a summarization session currently produces an empty plan,
   this is a normal outcome, not an edge case.

OUT OF SCOPE: evalloop start / stop, the session orchestrator, the async worker pool, the queue,
the local API, the dashboard and SSE. All M2, tickets T23 to T26.
````

---

## Group 6 — The gate

### EL-212 — 🔒 Gate 1: toy repo with a broken function

**Type:** Gate · **Est:** 0.5 · **Depends:** EL-214 · **Blocks:** E3 (Track V) ·
**Done when:** the bug is caught with zero instruction, and the harness proves it was not luck

**Story.** *As the person deciding whether this project continues, I want to put a bug in front of it
and watch it get caught without my helping — and then be shown why that was not a coincidence.*

**Why.** `PLAN.md`: "Point at a toy repo with a deliberately broken function. It gets caught, with
zero instruction from you." `USER_EXPERIENCE.md §5` makes it a user-visible acceptance moment. The
deliverable is a document a human reads, plus the toy repo, not more product code.

**⚠ Read §4.4 first.** Which reading of "caught" applies — harvested oracle or authored oracle — is an
open ruling, and it decides what this gate actually certifies.

**Files** → `tests/fixtures/toyrepo/` · `GATE1-REVIEW-PACKET.md` (no new product code)

**Subtasks**
- [ ] A toy repo with one deliberately broken function, written so the bug is **real** — a wrong
      boundary or an off-by-one, not a syntax error
- [ ] **The oracle run (`E6_oracle_run`) first:** push a known-correct implementation through the same
      pipeline. If the oracle does not score 100%, the harness is broken and the gate is void
- [ ] The actual transcript of `evalloop check <toyrepo>`, verbatim
- [ ] The rendered `summary.md`, verbatim
- [ ] A negative control: a correct implementation, which must **not** be flagged
- [ ] The mutation self-check's result from EL-207, against `A:38`'s 5% bar
- [ ] Cost of the run, and whether `--no-llm` could have caught it
- [ ] A findings ledger consolidated from EL-014 → EL-214
- [ ] One paragraph: does M1 catch real bugs, and where is it weakest

**Acceptance criteria**
- [ ] **The oracle run passes before any other claim is made.** `E-when-a-number-looks-wrong.md:219`
      is the reason: a harness with a 30-second timeout against a 90-second operation reported 0%,
      and a week was spent comparing larger models before anyone ran the oracle
- [ ] Zero instruction: no config file, no flag, no hint about what to check. The transcript proves it
- [ ] The negative control is not flagged — a tool that cries wolf fails `USER_EXPERIENCE.md §1`
- [ ] Every number in the packet carries its interval
- [ ] A **false**-positive and a **false**-negative are each shown, or their absence is explained
- [ ] The ledger covers: thresholds left null · thresholds interpreted from prose · what the corpus
      would not support · every stale doc line found · every ruling still open
- [ ] **A human signs off.** Gate 1 passing on a catch the reviewer did not understand is worse than
      Gate 1 failing

**Out of scope** Writing product code. Fixing a finding the packet raises — report it, let the
reviewer rule. Making the toy repo easier so the gate passes.

**Gotchas** The strongest way to fail this gate is to pass it for the wrong reason: a toy repo whose
broken function fails an existing test that EvalLoop merely re-ran. That demonstrates a test runner,
not an evaluation system. Say which of §4.4's two readings the gate ran under, in the first paragraph.

````text
WHAT I WANT
The Gate 1 review packet, plus the toy repo it was run against. This is not a code ticket: the
deliverable is something I read and either agree with or send back.

WHAT GATE 1 IS
PLAN.md: "Point at a toy repo with a deliberately broken function. It gets caught, with zero
instruction from you." USER_EXPERIENCE.md section 5 makes it a user-visible acceptance moment.

THE THING THAT COMES BEFORE THE CLAIM
Run the ORACLE first -- E6_oracle_run, which is already a record in the registry. Push a
known-correct implementation through the same pipeline. If the oracle does not score 100%, the
harness is broken and the gate is void, whatever it says about the broken function.
The reason is knowledge rules/E-when-a-number-looks-wrong.md:219: a team saw 0/50, assumed the
model was weak, and spent a week comparing larger models. The scripted oracle also scored 0/50 --
the harness had a 30-second timeout and the sandbox portal took 90 seconds. With the timeout
raised, the original model scored 34%. Report the oracle run FIRST, before any claim about the
broken function.

THE RESULT I WANT TO SEE
A single markdown document, GATE1-REVIEW-PACKET.md, readable in one sitting, containing:
1. WHICH READING OF "CAUGHT" THIS GATE RAN UNDER, in the first paragraph. If the toy repo has an
   existing test that the broken function fails, EvalLoop re-ran someone else's test and that
   demonstrates a test runner, not an evaluation system. If it has no test and EvalLoop authored
   one from the signature and caught the bug, that is the real claim. Say which, plainly.
2. The oracle run's result.
3. The verbatim transcript of `evalloop check <toyrepo>` -- no editing, no tidying.
4. The verbatim summary.md it produced.
5. A NEGATIVE CONTROL: a correct implementation that must NOT be flagged. USER_EXPERIENCE.md
   section 1 says the developer "will not tolerate a tool that cries wolf", so a gate without a
   negative control proves half of what it claims.
6. The mutation self-check result from EL-207 against A:38's 5% bar -- the evidence that the catch
   was not a coincidence.
7. A false positive and a false negative, each shown, or their absence explained.
8. The run's cost, and whether --no-llm could have caught it.
9. The findings ledger from EL-014 to EL-214, in one table: thresholds left null and why;
   thresholds interpreted from prose (the human-review queue); what the corpus would not support;
   every stale doc line found; every ruling still open.
10. One paragraph answering M1's actual question: does this catch real bugs, and where is it
    weakest? Gate 1 passing on a catch I did not understand is worse than Gate 1 failing.

Every number in the packet carries its interval. There is no exception for a gate document.

DO NOT, in this session: write product code, fix a finding the packet raises (report it and let me
rule), or make the toy repo easier so the gate passes.
````

---

## Tracking

| Key | Deliverable | Doc change in this ticket? | Blocks |
|---|---|---|---|
| EL-014 | `decisions/EL-014-timeout-semantics.md` | Yes — whichever of `AGENT.md` §3.7/§5, `ARCHITECTURE.md` §9, `PLAN.md` T11 loses | EL-206 |
| EL-015 | `decisions/EL-015-grader-config-home.md` | Possibly — `CLAUDE.md §6` if `TechniqueRecord` gains a field | EL-207, EL-208 |
| EL-203 | `evalloop/stats/{proportions,compare,resample,power}.py` | No | EL-213 |
| EL-202 | `evalloop/memory/episodic.py` | No | — |
| EL-209 | `evalloop/capability/{llm,router}.py` | Yes — `ARCHITECTURE.md §7` component 11 starts in M1, not M2 | EL-210 |
| EL-201 | `evalloop/memory/{case,metric_store}.py` | No | EL-206, EL-213 |
| EL-204 | `evalloop/classify/heuristics.py` + 10 samples | No | EL-205, EL-214 |
| EL-205 | `evalloop/grade/oracles/harvest.py` | No | EL-207, EL-210 |
| EL-206 | `evalloop/grade/{verdict,sandbox}.py`, `config.py` | Yes — the losing timeout doc, if EL-014 did not already | EL-207, EL-208 |
| EL-207 | `evalloop/grade/execution.py` + mutation self-check | No | EL-211 |
| EL-208 | `evalloop/grade/deterministic.py` | No | EL-214 |
| EL-210 | `evalloop/grade/oracles/author.py` | No | EL-214 |
| EL-213 | `evalloop/memory/evidence.py` | Yes — `CLAUDE.md §5` and `ARCHITECTURE.md §7` gain the component | EL-214 |
| EL-211 | `evalloop/report/summary.py` | No | EL-214 |
| EL-214 | `evalloop/run.py`, `evalloop/__main__.py` | Yes — `CLAUDE.md §5` target layout, `USER_EXPERIENCE.md §2` gains `check` | EL-212 |
| EL-212 | `GATE1-REVIEW-PACKET.md`, `tests/fixtures/toyrepo/` | Yes — `TASKS.md` M1 stages ticked | E3 |

**`CLAUDE.md` needs an M1 edit before EL-201 starts.** §2 currently says "Milestone 0 — registry and
planner only" and lists execution, storage, LLM calls and statistics under "do NOT build". That is
correct today and wrong the moment Gate 0 clears. The §0 preamble in this document carries the
replacement text; move it into `CLAUDE.md` as the first commit of this epic.

---

## Open questions for the product owner

In the order I would want them answered.

| # | Question | Blocks | Where |
|---|---|---|---|
| 1 | **Is Gate 0 signed off?** Nine of sixteen E2 tickets depend on it, and F2/F8 change what M1 displays | EL-201, EL-204 | `GATE0-REVIEW-PACKET.md §5` |
| 2 | **Which reading of Gate 1 applies** — harvested oracle, or authored oracle? It decides whether EL-210 is on the critical path, and whether the gate certifies a test runner or an eval system | EL-210, EL-212 | §4.4 |
| 3 | **Timeout: INCONCLUSIVE, a logged failure, or both?** Our docs and the corpus disagree | EL-206, EL-201 | §4.1, EL-014 |
| 4 | **Where do the six comparator numbers live?** | EL-207, EL-208 | §4.2, EL-015 |
| 5 | **Does M1 make an outbound call on an unredacted artifact?** The egress arrives one milestone before the broker that fixture 20's ruling makes responsible for it | EL-209, EL-210 | §4.3 |
| 6 | **F2 — are the two kinds of bar in `requires` separated?** EL-213 is the first code that has to tell them apart | EL-213, EL-211 | `GATE0-REVIEW-PACKET.md §2.1` |
| 7 | **F8 — is `unlocks` made load-bearing, or documented as advisory?** EL-213 and EL-211 both look wrong if this is answered after they are built | EL-213 | `GATE0-REVIEW-PACKET.md §2.2` |
| 8 | **16.5 d into a 15 d window — which of §5's three options?** Defer EL-210, defer EL-202, or move the gate to 9 Nov and take it out of E3 | the whole epic | §5 |
| 9 | **Do the six dead situation members get fixed in M1 or recorded as known-empty?** `contamination_risk` is the cheap one: `E7_contamination_check` exists and triggers on the wrong member | EL-204 | fixture 20's header, `S19-REPORT.md §3` |
| 10 | **Where does session data live** — `.evalloop/` in the repo, or the user's home? Both stores and the renderer need a default | EL-201, EL-202, EL-211 | `USER_EXPERIENCE.md §6` |
| 11 | **Is `evalloop check <path>` the name?** It becomes the first public CLI surface and `USER_EXPERIENCE.md §2` only documents `start`/`stop` | EL-214 | §2, change 2 |
| 12 | **Does EL-202 need to be read by anything in M1, or is write-only acceptable?** If write-only, it is the cheapest thing to defer | EL-202 | §5 option 2 |
