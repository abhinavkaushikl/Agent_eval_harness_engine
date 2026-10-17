# E1-M0-TICKETS-AND-PROMPTS.md — one ticket + one prompt per M0 build item

Run-ready work items for epic **E1 — M0 The Brain** (`DEVELOPMENT_PLAN.md §3`; stages S3–S23
in `TASKS.md`). Companion to `E0-DECISION-PROMPTS.md`, same format, same rules.

Each block has two halves:
- the **ticket** — for the board: files, subtasks, acceptance criteria, out-of-scope, gotchas;
- the **prompt** — paste-ready for one working session. Self-contained on purpose: it repeats
  the ticket, because it is pasted without it.

**How to use:** paste §0 (the shared preamble) and §0.1 (the stale-doc warnings), followed by
exactly one ticket's prompt block. One session per ticket.

**Order:** strictly top to bottom — the chain is linear and every stage reads what the previous
one wrote. Two exceptions: **EL-011** is a decision and runs in parallel with EL-103 … EL-109,
but must land before EL-110; **EL-113** is expected to force a schema change
(`CLAUDE.md §7.5`) — when it does, stop and report it.

**Do not batch.** EL-110 → EL-112 all write `evalloop/registry/records/`, and EL-113 → EL-117
all rewrite those same files. Batched, they collide and the per-stage integrity check — the
only thing between you and 73 quietly wrong records — never runs.

## Board

| Key | Title | Type | Est | Depends on | Blocks | Status |
|---|---|---|---|---|---|---|
| EL-011 | Sixth column field mapping | Decision | 0.5 | EL-001 ✅ | EL-110 | **Ready** |
| EL-103 | S3 `Situation` enum | Story | 0.25 | EL-001 ✅, EL-003 ✅ | EL-105 | **Ready** |
| EL-104 | S4 `Tool` enum + parsers | Story | 0.15 | EL-002 ✅ | EL-105 | **Ready** |
| EL-105 | S5 Vocab tests | Task | 0.1 | EL-103, EL-104 | EL-106 | Queued |
| EL-106 | S6 Record format + parser | Story | 0.3 | EL-105 | EL-107, EL-118 | Queued |
| EL-107 | S7 `TechniqueRecord` schema | Story | 0.25 | EL-106, EL-011 | EL-108 | Queued |
| EL-108 | S8 Loader, aggregated errors | Story | 0.25 | EL-107 | EL-109 | Done |
| EL-109 | S9 Integrity checker | Story | 0.2 | EL-108 | EL-110 | Done |
| EL-110 | S10 Extract A, B, C (20) | Task | 0.3 | EL-109, **EL-011** | EL-111 | Done |
| EL-111 | S11 Extract D, E, F (23) | Task | 0.3 | EL-110 | EL-112 | Done |
| EL-112 | S12 Extract G, H, I, J (30) | Task | 0.4 | EL-111 | EL-113 | Done |
| EL-113 | S13 Enrich A + B | Task | 0.4 | EL-112, EL-004 ✅ | EL-114 | Queued |
| EL-114 | S14 Enrich C + D | Task | 0.4 | EL-113 | EL-115 | Queued |
| EL-115 | S15 Enrich E + F | Task | 0.4 | EL-114 | EL-116 | Queued |
| EL-116 | S16 Enrich G + H | Task | 0.4 | EL-115 | EL-117 | Queued |
| EL-117 | S17 Enrich I + J | Task | 0.4 | EL-116 | EL-118 | Queued |
| EL-118 | S18 Fixture format + 1–5 | Task | 0.4 | EL-117, EL-106 | EL-119 | Queued |
| EL-119 | S19 Fixtures 6–20 | Task | 0.6 | EL-118 | EL-120 | Queued |
| EL-120 | S20 `match()` | Story | 0.4 | EL-119 | EL-121 | Queued |
| EL-121 | S21 Readiness | Story | 0.4 | EL-120 | EL-122 | Queued |
| EL-122 | S22 Capability, conflicts, companions | Story | 0.5 | EL-121 | EL-123 | Queued |
| EL-123 | S23 Planner + `render()` | Story | 0.7 | EL-122 | EL-124 | Queued |
| EL-124 | 🔒 Gate 0: review 20 plans | Gate | 0.5 | EL-123 | E2 | Queued |

**Total 8.5 d** — 8.0 as scoped, plus 0.5 for `EL-011`.

| Group | Tickets | Days | Can start |
|---|---|---|---|
| 2–3 Vocabulary + schema | EL-103 → EL-109 | 1.75 | now |
| — Open decision | EL-011 | 0.5 | now, in parallel |
| 4–5 Authoring the 73 records | EL-110 → EL-117 | 2.9 | after the above |
| 6–7 Fixtures + planner | EL-118 → EL-123 | 3.0 | after authoring |
| Gate | EL-124 | 0.5 | after the planner |

## Definition of done — every ticket, no exceptions

- [ ] `pytest` exit 0
- [ ] `mypy --strict evalloop/` exit 0
- [ ] No invented numbers: every threshold verbatim from the corpus, or `null`
- [ ] No later-milestone code or directories (`grade/`, `capture/`, `stats/`, `mcp/`)
- [ ] No corpus filename typed anywhere but `tests/conftest.py`
- [ ] No test or fixture edited to make code pass
- [ ] Report-back: what was done · what couldn't be represented · every threshold interpreted
      from prose (flagged for human review) · any vocabulary gap · any schema change needed

## Known-stale docs — every ticket inherits these

1. **`ladder_priority` tops out at 5. No distilled rung** (`EL-004`). `CLAUDE.md §6` correct;
   `TASKS.md` S7 ("1-6") and S13 ("6 distilled") stale.
2. **73 techniques**, not "~70": A 7 · B 7 · C 6 · D 6 · E 8 · F 9 · G 8 · H 8 · I 9 · J 5.
   `tests/test_corpus_shape.py` already pins 73.
3. **`Situation` has six families** (artifact, measurement, comparison, grader_trust, data,
   lifecycle), 48 members, per `CLAUDE.md §6`. `CLAUDE.md §5`'s "(5 …)" is stale.
4. **The master lookup has six columns.** The sixth has no field. `EL-011` settles it.

Where two docs disagree on a number, **neither decides — the corpus file does.** Open it, copy
verbatim, report which doc was wrong.

---

## 0. Shared preamble (paste before every ticket block)

````text
You are working in the EvalLoop repo at /Users/abhinav/Eval-harness-Engine.
Read CLAUDE.md first and obey it, especially:
  - Milestone 0 only: registry + planner. No execution, no sandbox, no file watching,
    no LLM calls, no statistics, no storage, no dashboard, no MCP code. Do not create
    grade/, capture/, stats/ or any later-milestone directory.
  - Standard library only. Python 3.10+ (decision EL-012). Type hints everywhere.
    mypy --strict clean, and mypy is pinned to python_version = 3.10, so no stdlib
    API newer than 3.10. StrEnum comes from evalloop/_compat, never from enum.
  - Never invent a number. A threshold is copied verbatim from the corpus or is null.
    "Reasonable default" is not a thing in this repo.
  - Never hardcode an absolute user path. Corpus filenames are declared once, in
    tests/conftest.py (MASTER_LOOKUP, INDEX_FILE, SECTION_FILES, CORPUS_FILES).
    Import them. Never retype a corpus filename anywhere else.
  - Never edit a test or a fixture to make code pass. If a fixture looks wrong, stop
    and flag it for human review.
  - Deterministic everything: ordering, rendering and ids are stable across runs.
  - Raise schema problems, do not work around them.

The corpus is read-only input: "knowledge rules/" holds the master lookup
(evals-situation-to-technique.md, 73 technique rows in ten sections A-J) and ten deep
dives. Records are authored FROM it at build time; nothing in evalloop/ parses Markdown
at runtime.

This is a BUILD ticket. The deliverable is working, typed, tested code plus a report.

Scope rules for this session:
  - Do exactly the ticket. If you see something else wrong, report it, do not fix it.
  - If the ticket conflicts with the corpus, the corpus wins and the conflict goes in
    the report.
  - If you cannot represent something the source states, that is a finding, not a
    failure to route around.

Finish with: pytest exit 0; mypy --strict evalloop/ exit 0; and a report-back covering
what you did, every source row or field you could not represent, every threshold you had
to interpret from prose (flag each for human review), any vocabulary gap, and any schema
change you believe is needed.
````

---

## 0.1 Stale-doc warnings (paste after §0, before every ticket block)

````text
Four things in the docs are known-stale. Trust this list over the doc text, and when a
ticket touches one, correct the stale line in the same diff and say so in the report.

1. ladder_priority tops out at 5. There is no distilled rung. Decision EL-004 removed it.
   CLAUDE.md §6 is correct. TASKS.md S7 ("outside 1-6") and S13 ("6 distilled") are stale.
2. The corpus holds 73 techniques, not "~70": A 7, B 7, C 6, D 6, E 8, F 9, G 8, H 8,
   I 9, J 5. tests/test_corpus_shape.py already pins the total at 73.
3. Situation has SIX comment-grouped families (artifact, measurement, comparison,
   grader_trust, data, lifecycle) and 48 members, per CLAUDE.md §6. CLAUDE.md §5's
   "(5 comment-grouped families)" is stale.
4. The master lookup table has SIX columns. The sixth, "Real-world domain scenario", has
   no field in TechniqueRecord. Decision EL-011 settles where it goes and must be decided
   before any extraction ticket. Do not silently drop it.

Where a number differs between two docs, neither doc decides it - the corpus file does.
Open the corpus file, copy the figure verbatim, and report which doc was wrong.
````

---

## Group 0 — The one open decision

### EL-011 — Sixth column: where `Real-world domain scenario` goes

**Type:** Decision · **Est:** 0.5 · **Depends:** EL-001 ✅ · **Blocks:** EL-110, and therefore
all extraction and enrichment · **Recommendation:** add a `domain_scenario` field

**Why now.** `EL-001:74` raised this and explicitly did not settle it. The column is populated
on all 73 rows. Extract without a ruling and every record silently drops a source column,
recoverable only by re-extracting all 73.

**Files** → `decisions/EL-011-sixth-column-mapping.md` (new) · `CLAUDE.md §4` and §6 field
table · `TASKS.md:103` field mapping. **No schema code in this ticket.**

**Subtasks**
- [ ] Read the sixth cell of ≥ 10 rows across different sections
- [ ] Check whether M1's test author (T15) and classifier (T9) want this material
- [ ] Write the record in the `E0-DECISION-PROMPTS.md §0` decision format
- [ ] Amend `CLAUDE.md §4` + `TASKS.md:103` to say six columns
- [ ] If accepted: specify the exact field name/type/nullability for `EL-107` in Follow-up

**Acceptance criteria**
- [ ] `decisions/EL-011-sixth-column-mapping.md` exists with all eight standard headings
- [ ] Options table quotes ≥ 3 real sixth-column cells verbatim as evidence
- [ ] `CLAUDE.md §4` and `TASKS.md:103` both say six columns
- [ ] Follow-up names the exact `EL-107` schema change, or (option C) a test asserting the drop
      is deliberate so a future reader can't mistake it for an extraction bug

**Out of scope** Writing the schema field. Touching `evalloop/`.

**Gotchas** `worked_example` already carries a "must contain a digit" contract; domain scenarios
contain currency figures, so folding them in makes that rule pass for the wrong reason.

````text
WHAT I WANT
A written decision on where the master lookup's sixth column lands in TechniqueRecord,
and the schema change it implies, before any record is extracted. Follow the decision-ticket
format in E0-DECISION-PROMPTS.md §0 (Decision / Status / Context / Options considered /
Consequences / Evidence / Follow-up), written to decisions/EL-011-sixth-column-mapping.md.

WHAT IS IN THE TICKET
decisions/EL-001-corpus-location.md:74 raised this and explicitly did not resolve it: the
master lookup's table is "Situation | Use | What it technically is | Why this one | Example |
Real-world domain scenario" (evals-situation-to-technique.md:11), while CLAUDE.md §4 and the
TASKS.md:103 field mapping both describe only five columns. The sixth has no destination
field. tests/test_corpus_shape.py:90 already asserts six columns and carries a comment
pointing at this open question. Extract without deciding and all 73 records drop a populated
source column, which cannot be recovered without re-extracting.

THE INPUT
  - evals-situation-to-technique.md:11 onward - read the sixth cell of at least ten rows
    across different sections before you argue anything. They are concrete, domain-specific
    deployment scenarios (fintech NL-to-SQL over a UPI warehouse; insurance policy-servicing
    nominee field; telecom Hinglish support replies; e-commerce GSTIN extraction).
  - CLAUDE.md §6 - the TechniqueRecord field table, and the existing contract on
    worked_example: "concrete figures from source - must contain a digit".
  - decisions/EL-001-corpus-location.md:74 - the three options as originally framed.
  - PLAN.md T15 / TASKS.md T15 - the M1 test author, which must generate cases from
    something. Ask whether this column is that seed material.

THE OPTIONS, AS I SEE THEM
  A. New field: domain_scenario: str | None. Costs one schema field and one extraction
     column. Keeps worked_example's "figures from source" contract clean.
  B. Fold into worked_example. Costs nothing now, but mixes a statistical figure with a
     deployment narrative in one field, and the digit rule starts passing for the wrong
     reason (scenarios contain currency figures).
  C. Record a deliberate drop. Cheapest, and defensible only if nothing downstream wants it.

My recommendation is A, for one reason I want you to test rather than accept: this column is
the only place in the corpus holding concrete, named, domain-grounded scenarios, which is
exactly the seed material M1's case author (T15) and the classifier's situation examples (T9)
will need. Dropping it in M0 means re-reading the corpus in M1. Argue me out of it if the
evidence says otherwise.

THE RESULT I WANT TO SEE
1. decisions/EL-011-sixth-column-mapping.md, with the Options table quoting at least three
   real sixth-column cells verbatim as evidence.
2. If the decision is A: the exact field name, type and nullability to add in EL-107, written
   into the Follow-up section, plus the one-line amendment to CLAUDE.md §6's field table and
   TASKS.md:103's field mapping. Do NOT write schema code in this session.
3. If the decision is C: a test asserting the drop is deliberate, so that a future reader
   cannot mistake it for an extraction bug.
4. Either way: TASKS.md:103 and CLAUDE.md §4 updated to say six columns, not five.
````

---

## Group 2 — Vocabularies (T1)

### EL-103 — S3 `Situation` enum

**Type:** Story · **Est:** 0.25 · **Depends:** EL-001 ✅, EL-003 ✅ · **Blocks:** EL-105 ·
**Done when:** every source situation maps to exactly one member

**Why.** `CLAUDE.md §6` calls this the most important correctness decision in M0, and the
reason is mechanical: a spelling mismatch (`summarization` vs `text_summary`) makes matching
fail *silently*, after 73 records already depend on it.

**Files** → `evalloop/vocab/situations.py` (new) · `CLAUDE.md §5` (fix 5 → 6 families)

**Subtasks**
- [ ] Transcribe the 48 members / 6 families from `CLAUDE.md §6`
- [ ] Verify against the Situation column of all 73 lookup rows
- [ ] Verify against every "You are here when…" framing in the ten deep dives + `00-INDEX.md`
- [ ] Rule on `items_grouped` (comparison) vs `grouped_items` (data)
- [ ] Module docstring: source · every addition justified by a source line · the ruling above
- [ ] Fix `CLAUDE.md §5`

**Acceptance criteria**
- [ ] `StrEnum Situation`, value == lowercase member name, six comment-grouped families,
      members alphabetical within family
- [ ] No parse helpers in this file (that's `EL-104`)
- [ ] `EL-003`'s three rejected members absent
- [ ] Report lists every source phrasing that does **not** map to exactly one member —
      expected to be non-empty
- [ ] No member added without a cited source line

**Out of scope** `parse_situation`, tests (`EL-105`), any member not forced by the corpus.

**Gotchas** `items_grouped` / `grouped_items` are the same two words reversed — one may be a
typo, and `EL-119` fixture 13 uses `grouped_items`. `CLAUDE.md §5` says five families, §6
lists six.

````text
WHAT I WANT
evalloop/vocab/situations.py: a StrEnum Situation (imported from evalloop/_compat, NOT
from enum -- see EL-012) holding the 48 members in CLAUDE.md §6,
grouped by comment into six families, verified against the corpus. Enum only - no parse
helpers in this session (that is EL-104).

WHAT IS IN THE TICKET
This is the single most important correctness decision in M0. CLAUDE.md §6 says so, and the
reason is mechanical: a spelling mismatch (summarization vs text_summary) makes matching fail
silently rather than loudly, and it fails after 73 records already depend on it. The starting
set is in CLAUDE.md §6. Your job is to verify it against the source and report what does not
fit - not to improve it.

Decision EL-003 is already made: claim_unverified, live_endpoint_available and agent_tool_call
are NOT added. They are deferred to EL-701, EL-307 and EL-409. Do not re-litigate; read the
decision if you are tempted.

THE INPUT
  - CLAUDE.md §6 - the six families and 48 members:
      artifact (12): code_generation, sql_generation, api_endpoint, structured_extraction,
        summarization, qa_answer, rag_answer, agent_action, classification,
        prose_generation, model_training, data_pipeline
      measurement (8): score_jumped, score_up_business_flat, length_increased,
        no_change_score_moved, all_candidates_high, all_candidates_zero,
        benchmark_too_good, single_benchmark_dominance
      comparison (5): two_candidates, many_candidates, external_leaderboard,
        metric_without_formula, items_grouped
      grader_trust (7): new_judge_built, measuring_agreement, multiple_annotators,
        position_bias_risk, self_preference_risk, scale_compressed, annotators_disagree
      data (6): rare_class, small_sample, grouped_items, contamination_risk, phi_present,
        distribution_mismatch
      lifecycle (10): pre_development, shipping_change, ci_flaking, debugging_regression,
        detecting_drift, scoring_live_traffic, measuring_impact, ab_testing,
        building_eval_set, model_selection
  - The Situation column of all 73 rows in evals-situation-to-technique.md.
  - Every "You are here when..." framing in the ten deep dives, and the "Read it when"
    column of 00-INDEX.md.
  - decisions/EL-003-new-situations.md - the three rejected members and why.

TWO THINGS I ALREADY SUSPECT, WHICH I WANT YOU TO RULE ON
  - items_grouped (comparison) and grouped_items (data) are the same two words reversed.
    Either they are genuinely two situations and the docstring must say what distinguishes
    them, or one is a typo that will cost a day in EL-119 (fixture 13 uses grouped_items).
    Decide from the corpus and say which.
  - CLAUDE.md §5 calls this "5 comment-grouped families" while §6 lists six. Fix §5.

THE RESULT I WANT TO SEE
1. evalloop/vocab/situations.py: StrEnum Situation, member value == lowercase member name,
   six comment-grouped families in the order above, members alphabetical within a family.
2. A module docstring that (a) states the corpus is the source, (b) justifies every member
   added beyond CLAUDE.md §6's list with the source line that forced it, and (c) records the
   items_grouped / grouped_items ruling.
3. CLAUDE.md §5 corrected to six families.
4. A report listing every distinct source situation phrasing that does NOT map cleanly to
   exactly one member - I expect this list to be non-empty and I want to see it.
5. No member added just because it "seems useful". Corpus evidence or nothing.
````

---

### EL-104 — S4 `Tool` enum + parsers

**Type:** Story · **Est:** 0.15 · **Depends:** EL-002 ✅ · **Blocks:** EL-105 ·
**Done when:** round-trips every member; rejects unknowns with a helpful message

**Why.** Every member names a **capability** — something that must exist in the world for a
technique to run. No member names a **transport**. That line is what keeps credentials in the
capability broker and out of graders.

**Files** → `evalloop/vocab/tools.py` (new) · `evalloop/vocab/__init__.py` (re-exports +
parsers)

**Subtasks**
- [ ] 15 members from `CLAUDE.md §6`, in that order
- [ ] Docstring: the capability-vs-transport test verbatim + cite `EL-002`
- [ ] `parse_situation` / `parse_tool`, `ValueError` naming the bad value + sorted valid options
- [ ] Re-export `Situation`, `Tool`, both parsers from `vocab/__init__.py`
- [ ] Cross-check the deep dives for a required capability with no member

**Acceptance criteria**
- [ ] Exactly 15 members, value == lowercase name, **no** `mcp_client` / `mcp_gateway`
- [ ] Both parsers round-trip every member
- [ ] Unknown input raises with the offending value **and** the valid options, deterministically
      ordered
- [ ] Any missing-capability finding is reported, not added

**Out of scope** Adding a member. Tests (`EL-105`). Any MCP code.

**Gotchas** `EL-002` is closed and not reopenable. If a deep dive clearly needs a tool with no
member, **stop and report** — that's a decision ticket, not a code change.

````text
WHAT I WANT
evalloop/vocab/tools.py with a StrEnum Tool (from evalloop/_compat, not enum -- EL-012)
of exactly 15 members, and
evalloop/vocab/__init__.py re-exporting Situation, Tool, parse_situation and parse_tool.

WHAT IS IN THE TICKET
Every Tool member names a CAPABILITY: something that must exist in the world for a technique
to be runnable. No member names a TRANSPORT - how the thing is reached. The test for a
candidate, from CLAUDE.md §6: if the delivery mechanism changed but the resource stayed the
same, would any record's requirement change? If not, it is transport, and it belongs to the
capability broker, not here.

Decision EL-002 is made and is not reopenable: mcp_client and mcp_gateway are NOT members,
now or ever. MCP is transport, owned by the broker (EL-302) and the gateway (EL-408). Exactly
15 members, as listed in CLAUDE.md §6.

THE INPUT
  - CLAUDE.md §6, the 15 members: sandbox, test_runner, repo_read, source_doc_read, llm_api,
    llm_api_cross_family, vector_store, db_connection, ocr, vision_model, trace_capture,
    snapshot_restore, cost_api, human_labels, production_logs
  - decisions/EL-002-mcp-tools-in-enum.md - the capability-vs-transport argument.
  - The deep dives' "How to do it properly" sections, for what each technique actually needs
    to exist (H1 wants snapshot_restore and trace_capture; F5 wants llm_api_cross_family and
    human_labels; G wants vector_store and source_doc_read).

THE RESULT I WANT TO SEE
1. evalloop/vocab/tools.py: StrEnum Tool, 15 members, value == lowercase name, in the
   CLAUDE.md §6 order. Module docstring stating the capability-vs-transport test verbatim
   and citing EL-002, so the next person does not re-add mcp_client.
2. evalloop/vocab/__init__.py: re-exports Situation, Tool, parse_situation, parse_tool.
3. parse_situation(str) -> Situation and parse_tool(str) -> Tool, each raising ValueError
   whose message contains the offending value AND the list of valid options in a
   deterministic (sorted) order. The message is read by a human debugging a record file at
   2am; write it for them.
4. Report: any tool a deep dive clearly requires that has no member. If you find one, name
   the file and line and STOP - do not add it. That is a decision ticket, not a code change.
````

---

### EL-105 — S5 Vocab tests

**Type:** Task · **Est:** 0.1 · **Depends:** EL-103, EL-104 · **Blocks:** EL-106 ·
**Done when:** ~20 verbatim source strings map to a member

**Why.** The drift tripwire. After `EL-110` there are 73 records depending on these spellings.

**Files** → `tests/test_vocab.py` (new) · `TASKS.md` S5 (correct the unimplementable line)

**Subtasks**
- [ ] value == lowercase name, both enums
- [ ] no duplicate values, both enums
- [ ] negative test per parser: message contains the offending value
- [ ] coverage mapping: ≥ 20 verbatim lookup phrases → member, from **all ten** sections
- [ ] correct `TASKS.md` S5

**Acceptance criteria**
- [ ] ≥ 20 verbatim phrases mapped, spanning all ten sections (not 20 from A)
- [ ] Phrases copied verbatim — punctuation and `/` separators intact, untidied
- [ ] Each mapping entry reads as evidence: phrase, member, nothing else
- [ ] Report lists every phrase that mapped to zero, or to more than one, member

**Out of scope** Prose normalisation inside `parse_situation`.

**Gotchas** `TASKS.md` S5 says the ~20 verbatim strings should "all parse successfully". They
can't — the Situation cells are prose ("Output is code / SQL / an API call"). Implement the
mapping-table reading and say in the docstring why the literal reading isn't implementable.

````text
WHAT I WANT
tests/test_vocab.py: the tripwire that catches vocabulary drift before 73 records depend on it.

WHAT IS IN THE TICKET
Four test groups, from TASKS.md S5:
  - every member value == lowercase member name, for both enums
  - no duplicate values within either enum
  - parse_situation / parse_tool raise with the offending value in the message
  - a coverage test: ~20 situation strings taken VERBATIM from the master lookup

ONE AMBIGUITY I WANT YOU TO RESOLVE, NOT PAPER OVER
TASKS.md says the ~20 verbatim strings should "all parse successfully". They cannot. The
master lookup's Situation cells are English prose - "Output is code / SQL / an API call",
"Agent claims it did something", "The bad thing is under 5% of traffic". parse_situation()
takes an enum value, not prose. So either:
  A. the test is a hardcoded mapping {verbatim source phrase -> Situation member}, asserted
     to cover at least 20 rows across all ten sections, which IS the real drift tripwire; or
  B. parse_situation() gains prose normalisation, which I do not want in M0 and which would
     be a planner behaviour, not a vocab one.
I believe A is what was meant. Implement A, and say in the module docstring why the literal
reading of TASKS.md S5 is not implementable. Then correct that line in TASKS.md.

THE INPUT
  - The Situation column of evals-situation-to-technique.md, all ten sections. Copy cells
    verbatim, including punctuation and the "/" separators. Do not tidy them.
  - evalloop/vocab/ as built by EL-103 and EL-104.

THE RESULT I WANT TO SEE
1. tests/test_vocab.py with the four groups above, the coverage mapping holding >= 20
   verbatim phrases drawn from ALL ten sections (not 20 from section A).
2. Each mapping entry readable as evidence: the verbatim phrase, the member, and nothing else.
3. A negative test per parser proving the ValueError message names the bad value.
4. TASKS.md S5 corrected to describe the mapping test.
5. Report: any verbatim phrase you could not map to exactly one member. That list is the
   real output of this ticket.
````

---

## Group 3 — Record format & schema (T2)

### EL-106 — S6 Record format + parser

**Type:** Story · **Est:** 0.3 · **Depends:** EL-105 · **Blocks:** EL-107, EL-118 ·
**Done when:** every construct tested; trade-off documented

**Why.** No PyYAML (`CLAUDE.md §3`), so either a minimal YAML subset or JSON — and the choice
is paid for 73 times by hand.

**Files** → `evalloop/registry/format.py` (new) · tests

**Subtasks**
- [ ] Choose JSON or YAML-subset; write the trade-off into the module docstring
- [ ] Enumerate the supported construct set from the `TASKS.md` Group 6 fixture sample
- [ ] Implement `load(text) -> dict`, pure, no file I/O
- [ ] Parse errors naming line number + construct
- [ ] One test per supported construct; one rejection test per unsupported one

**Acceptance criteria**
- [ ] Choice + cost stated in the docstring
- [ ] `load()` handles every construct the fixture sample needs: nested block maps (2 levels),
      flow lists `[a, b]`, flow maps `{samples: 1}`, trailing `#` comments, quoted strings
      containing `": "`, empty collections `[]`, block scalars for prose
- [ ] Anything outside the subset **raises** rather than half-parsing
- [ ] Report names any needed construct deliberately unsupported, and how `EL-118` expresses it
      instead

**Out of scope** Schema validation (`EL-107`). Reading files from disk (`EL-108`).

**Gotchas** One parser serves **both** records and the 20 planner fixtures. The fixture sample
in `TASKS.md` Group 6 already forces flow maps, trailing comments and quoted `": "`. Scope to
exactly that and reject the rest loudly.

````text
WHAT I WANT
A decision on the on-disk record format, and evalloop/registry/format.py implementing it:
load(text) -> dict, with tests covering every construct the records and the planner fixtures
actually use.

WHAT IS IN THE TICKET
CLAUDE.md forbids PyYAML. So either write a minimal YAML-subset parser, or use JSON and
accept that 73 hand-authored records read worse. CLAUDE.md §3 requires the choice and its
trade-off to be stated in the module docstring.

THE CONSTRAINT THAT DECIDES THIS, AND WHICH THE TICKET DOES NOT MENTION
One parser must serve TWO consumers: the record files (EL-110 onward) and the 20 planner
fixtures (EL-118/EL-119). The fixture format is already specified in TASKS.md Group 6, and
that sample alone requires:
  - block maps, nested at least two levels (expect.pending.B3_mcnemar)
  - inline flow lists:  situations: [summarization]
  - inline flow maps:   evidence: {samples: 1, runs: 1}
  - trailing comments:  ready: [...]   # order matters
  - quoted strings containing ": "  ->  "needs paired_runs: 2, have 1"
  - empty collections:  unavailable: []
  - block scalars for long prose (anti_pattern, worked_example)
Scope the subset to exactly that list and refuse anything outside it loudly. A parser that
silently half-understands a construct is worse than one that rejects it.

THE INPUT
  - CLAUDE.md §3 (no PyYAML) and §5 (format.py is "on-disk format parser (minimal YAML
    subset OR JSON)").
  - TASKS.md Group 6's fixture sample - the construct list above comes from it.
  - CLAUDE.md §6 - the 22 TechniqueRecord fields, for what a record file must express:
    tuples of strings, a Mapping[str, int | bool], nullable ints, and multi-line prose.

THE RESULT I WANT TO SEE
1. A stated choice with its cost, in the format.py module docstring. If YAML subset: say
   exactly which constructs are supported and that everything else raises. If JSON: say
   what readability cost 73 hand-authored records pay, and how multi-line prose is handled.
2. evalloop/registry/format.py: load(text) -> dict, pure, no file I/O, deterministic.
3. Parse errors that name the line number and the construct. These messages will be read
   while hand-authoring 73 records; they are a feature of this ticket, not a detail.
4. One test per supported construct, plus a rejection test per unsupported one.
5. Report: any construct the fixture sample needs that you chose not to support, and how
   EL-118 is expected to express it instead.
````

---

### EL-107 — S7 `TechniqueRecord` schema

**Type:** Story · **Est:** 0.25 · **Depends:** EL-106, EL-011 · **Blocks:** EL-108 ·
**Done when:** each validation rule has a positive and a negative test

**Why.** The shape all 73 records are authored into. Type assignment is the part people get
wrong, and a wrong `RecordType` makes the planner present a diagnostic as a grader.

**Files** → `evalloop/registry/schema.py` (new) · `TASKS.md` S7 (1-6 → 1-5) · tests

**Subtasks**
- [ ] `RecordType` / `Gate` / `Cost` StrEnums; `RecordType` docstring states the typing rule
- [ ] Frozen `TechniqueRecord` with all `CLAUDE.md §6` fields (+ `EL-011`'s field if accepted)
- [ ] Six `__post_init__` validations
- [ ] Immutable mapping for `requires`
- [ ] Positive + negative test per rule
- [ ] Fix `TASKS.md` S7

**Acceptance criteria**
- [ ] Tuple fields, not lists; `requires` immutable; record genuinely frozen
- [ ] Raises on: empty `triggers_on_situation` · `ladder_priority` with `type != grader` ·
      `ladder_priority` outside **1–5** · `id` not `<SECTION><N>_<snake>` ·
      `worked_example` with no digit · empty `source_ref`
- [ ] Each rule has one passing and one raising test; errors name record id + field
- [ ] `TASKS.md` S7 corrected with `EL-004` cited

**Out of scope** Cross-record checks (`EL-109`). Loading (`EL-108`). Inventing a rung for A7.

**Gotchas** Ladder is **1–5**; `TASKS.md` says 1–6. A frozen dataclass holding a `dict` is still
mutable through it and unhashable. A7 wraps the ladder — leave `ladder_priority` `None`.

````text
WHAT I WANT
evalloop/registry/schema.py: three StrEnums (from evalloop/_compat) and the frozen
TechniqueRecord dataclass, with
validation that fires in __post_init__ and a test on both sides of every rule.

WHAT IS IN THE TICKET
  - RecordType: grader, metric, statistic, diagnostic, procedure, constraint
  - Gate: absolute, statistical, false
  - Cost: low, medium, high
  - TechniqueRecord: all fields in CLAUDE.md §6's table, frozen, with tuple fields (not list)
    so records stay immutable and deterministic.

__post_init__ raises on:
  - empty triggers_on_situation
  - ladder_priority set when type != grader
  - ladder_priority outside 1..5        <-- FIVE, not six. EL-004 removed the distilled
                                            rung. TASKS.md S7 says 1-6 and is stale; fix it.
  - id not matching <SECTION><N>_<snake_name>, e.g. A1_execution_based
  - worked_example containing no digit
  - empty source_ref

TYPE ASSIGNMENT IS THE PART PEOPLE GET WRONG
Most records are NOT graders. A grader renders a verdict on an artifact. Wilson, McNemar and
bootstrap are statistics. Section E is almost entirely diagnostics. "Never accuracy on a rare
class" and "never same-family judging" are constraints. Calibration and the failures-as-tests
flywheel are procedures. Put that in the RecordType docstring so EL-110 onward cannot drift.

THE INPUT
  - CLAUDE.md §6 - the field table, verbatim. 22 fields, each with its meaning.
  - decisions/EL-004-claude-md-corpus-gaps.md - the ladder tops out at 5, and this is flagged
    there as a schema-affecting change.
  - decisions/EL-011 (this must already be decided) - whether a domain_scenario field exists.
  - evalloop/vocab/ - triggers_on_situation is tuple[Situation, ...], required_tools is
    tuple[Tool, ...]; both are enums, never strings, past the loader boundary.

TWO THINGS TO GET RIGHT
  - requires is Mapping[str, int | bool]. A frozen dataclass holding a dict is still mutable
    through that dict and is unhashable. Use an immutable mapping and say so.
  - ladder_priority is None unless type is grader. A7 (tiered online scoring) wraps the
    ladder rather than ranking within it; CLAUDE.md §6 records its priority as an open
    question. Leave it None for now and do not invent a rung.

THE RESULT I WANT TO SEE
1. evalloop/registry/schema.py with the three enums and the frozen dataclass.
2. Six validation rules, each with a passing positive test and a raising negative test, with
   the error naming the record id and the offending field.
3. TASKS.md S7's "1-6" corrected to "1-5", with EL-004 cited.
4. Report: any field in CLAUDE.md §6 you could not type cleanly, and why.
````

---

### EL-108 — S8 Loader with aggregated errors

**Type:** Story · **Est:** 0.25 · **Depends:** EL-107 · **Blocks:** EL-109 ·
**Done when:** every error in every file reported

**Why.** `CLAUDE.md §7.7`: errors aggregate, because 73 records are authored by hand. A loader
that stops at the first bad file turns one authoring session into 73 round trips.

**Files** → `evalloop/registry/loader.py` (new) · malformed fixture under `tests/` · tests

**Subtasks**
- [ ] `load_records(dir) -> tuple[TechniqueRecord, ...]`, sorted by id
- [ ] Parse via `format.py`, validate via `schema.py`, convert strings via the vocab parsers
- [ ] `RegistryError` aggregating every problem in every record in every file
- [ ] Malformed fixture carrying several problems across several files
- [ ] Decide and record: one record per file, or one file per section

**Acceptance criteria**
- [ ] Result identical across runs and filesystems — no reliance on directory order
- [ ] Every error line names file + record id + the specific problem
- [ ] A multi-problem, multi-file fixture produces **all** problems in one message
- [ ] Unknown situation/tool surfaces the vocab message with the bad value and valid options
- [ ] File-shape choice stated and lived with for all 73

**Out of scope** Cross-record integrity (`EL-109`). Authoring records (`EL-110`).

**Gotchas** Don't swallow and re-word the vocab `ValueError`s — attach record id and file to them.

````text
WHAT I WANT
evalloop/registry/loader.py: load_records(dir) -> tuple[TechniqueRecord, ...], which reports
EVERY problem across EVERY file in one go.

WHAT IS IN THE TICKET
CLAUDE.md §7.7 states the reason plainly: errors aggregate, because 73 records are being
authored by hand. A loader that stops at the first bad file turns one authoring session into
73 round trips. One run must produce the full list.

THE INPUT
  - evalloop/registry/format.py (EL-106) for parsing, schema.py (EL-107) for validation,
    evalloop/vocab/ (EL-103/104) for turning situation and tool STRINGS into enum members.
  - CLAUDE.md §5 - loader.py's signature.
  - The vocab parsers' ValueError messages: the loader must surface them with the record id
    and file attached, not swallow and re-word them.

THE RESULT I WANT TO SEE
1. load_records(dir) -> tuple[TechniqueRecord, ...], sorted by id so the result is identical
   across runs and filesystems. Do not rely on directory order.
2. A RegistryError that aggregates: for every file, for every record, every problem - parse
   errors, schema violations and unknown vocabulary - each line naming file, record id and
   the specific problem.
3. A deliberately malformed fixture record under tests/ carrying SEVERAL distinct problems
   in SEVERAL files at once, and a test asserting all of them appear in one message.
4. A test that a record naming an unknown situation or tool fails with a message containing
   the bad value and the valid options.
5. Report: whether a record file holding multiple records, or one record per file, is the
   better shape for EL-110 onward. State your choice and live with it for all 73.
````

---

### EL-109 — S9 Integrity checker

**Type:** Story · **Est:** 0.2 · **Depends:** EL-108 · **Blocks:** EL-110 ·
**Done when:** every rule tested

**Why.** The done-when for every stage from `EL-110` to `EL-117`. The only thing that catches a
cross-reference typo in a 73-record graph.

**Files** → `evalloop/registry/integrity.py` (new) · tests

**Subtasks**
- [ ] `check_integrity(records) -> list[str]`, deterministic order
- [ ] Seven rules (see criteria)
- [ ] One isolating test per rule + a clean-set test
- [ ] Test that `records/` is clean — trivially true today; the real gate at `EL-110`

**Acceptance criteria**
- [ ] Detects: duplicate ids · `companion_checks`/`unlocks`/`conflicts_with` → unknown id ·
      self-reference · grader missing `ladder_priority` · non-grader carrying one ·
      section outside A–J · id prefix ≠ `section`
- [ ] Empty list means clean; order stable (record id, then rule) so run-to-run diffs mean something
- [ ] Messages name record id, field and offending value, and read as fix instructions
- [ ] Any missing invariant is named in the report, not added

**Out of scope** Adding an eighth rule. Fixing records.

**Gotchas** `AGENT.md §3.5` shows how the planner walks these edges — a dangling reference is a
silent *plan* defect, not a cosmetic one.

````text
WHAT I WANT
evalloop/registry/integrity.py: check_integrity(records) -> list[str], returning
human-readable problems that no single record can detect about itself.

WHAT IS IN THE TICKET
Seven cross-record rules, from TASKS.md S9:
  - duplicate ids
  - companion_checks / unlocks / conflicts_with pointing at an unknown record id
  - self-references (a record listing its own id in any of those three)
  - graders missing ladder_priority
  - non-graders carrying a ladder_priority
  - section outside A-J
  - id prefix disagreeing with the section field (A1_... declaring section B)

This is the function every extraction and enrichment stage from EL-110 to EL-117 runs as its
done-when. It is the only thing that catches a cross-reference typo in a 73-record graph.

THE INPUT
  - CLAUDE.md §5 and §6 - the signature, and the three cross-reference fields
    (companion_checks, unlocks, conflicts_with) whose referents must resolve.
  - TASKS.md S9 - the seven rules.
  - AGENT.md §3.5 - how the planner consumes these edges, which is why a dangling reference
    is a silent plan defect and not a cosmetic one.

THE RESULT I WANT TO SEE
1. check_integrity(records) -> list[str]. Empty list means clean. Deterministic order
   (sort by record id, then rule) so a diff between two runs is meaningful.
2. Messages that name the record id, the field and the offending value, and read as
   instructions to the person who must fix the record.
3. One test per rule, each with a hand-built record set that violates exactly that rule and
   nothing else, plus one test that a clean set returns [].
4. A test asserting check_integrity() over evalloop/registry/records/ is empty. It will pass
   trivially today (the directory is empty) and becomes the real gate at EL-110.
5. Report: any cross-record invariant you think is missing from the seven. Name it; do not
   add it.
````

---

## Group 4 — Skeleton extraction (T3)

> Each stage reads **only** its own sections of the master lookup and fills only `id · section ·
> name · type · triggers_on_situation · anti_pattern · worked_example · source_ref · gates ·
> analysis_cost`. Everything else stays null or empty, with no guessing. The deep dives are
> **not** read for content — that is Group 5.

### EL-110 — S10 Extract A, B, C

**Type:** Task · **Est:** 0.3 · **Depends:** EL-109, **EL-011** · **Blocks:** EL-111 ·
**Done when:** 20 records load; integrity check empty

**Files** → `evalloop/registry/records/{A_grading,B_comparison,C_statistics}.*`

**Subtasks**
- [ ] A 7 rows, B 7 rows, C 6 rows → 20 records, field mapping per `TASKS.md:103`
- [ ] ids from the deep-dive numbering (`grep '^# [A-J][0-9]+ '`)
- [ ] Type each record; `ladder_priority` null throughout this stage
- [ ] Sixth column per `EL-011`
- [ ] Run `load_records()` + `check_integrity()`

**Acceptance criteria**
- [ ] Exactly **20** records load; `check_integrity()` returns `[]`
- [ ] Every `worked_example` carries a digit, straight from the Example cell
- [ ] Every `anti_pattern` phrased as the failure, not a restatement of the technique
- [ ] No merged rows, no cross-section dedupe
- [ ] Report: per-section counts · unmapped Situations · rows where `type` was genuinely arguable

**Out of scope** `requires`, `required_tools`, `ladder_priority`, edges, `rule_of_thumb` — all
`EL-113`/`EL-114`. Reading deep-dive bodies.

**Gotchas** A7 wraps the ladder → `ladder_priority` null, noted in `extraction_notes`. B5
("compute the CI from n") and C5 ("multiple-comparison correction") are the arguable types.

````text
WHAT I WANT
20 skeleton records in evalloop/registry/records/ for sections A (7), B (7) and C (6),
extracted from the master lookup only.

WHAT IS IN THE TICKET
Field mapping, from TASKS.md:103 - follow it exactly:
  Use                     -> name
  Situation               -> triggers_on_situation   (one row may map to several members)
  What it technically is   -> informs type and produces
  Why this one             -> anti_pattern, phrased as the failure that occurs WITHOUT the
                              technique
  Example                  -> worked_example, keeping the concrete numbers
  Real-world domain scenario -> per decision EL-011. Do not drop it silently.
  source_ref               -> "evals-situation-to-technique.md § <letter>"

Rules:
  - Most records are NOT graders. In these three sections, A1-A6 are graders; Wilson (C1),
    McNemar (B3), the bootstraps (B1, B6, B7), power (C2), permutation (C6) and the
    multi-run / correction records are statistics. ladder_priority is null for every
    non-grader, and in this stage it is null for graders too - the ladder is EL-113's job.
  - A7 (tiered online scoring) wraps the ladder rather than sitting on a rung. Type it, leave
    ladder_priority null, and note it in extraction_notes.
  - Do not merge two techniques into one record. Do not deduplicate across sections.
  - ids are <SECTION><N>_<snake_name> matching the deep-dive numbering exactly: A1 is
    A1_execution_based, B3 is B3_mcnemar, C1 is the Wilson CI record. The deep-dive headers
    (# A1 - EXECUTION-BASED GRADING) are the authority on numbering.

THE INPUT
  - evals-situation-to-technique.md, sections A, B and C only. 20 rows: A has 7, B has 7,
    C has 6. Verified counts - if you find a different number, stop and report it.
  - The deep-dive files for ID NUMBERING ONLY (grep '^# [A-J][0-9]+ '). Do not read their
    bodies for content in this stage; that is EL-113/EL-114 and mixing the two makes the
    enrichment stage unverifiable.
  - evalloop/vocab/situations.py - every triggers_on_situation value is a member. A row whose
    Situation you cannot map is a finding, not a licence to add a member.

THE RESULT I WANT TO SEE
1. Record files under evalloop/registry/records/ named A_grading, B_comparison, C_statistics
   (plus the format extension from EL-106).
2. load_records() returns exactly 20 records; check_integrity() returns [].
3. Every worked_example contains a digit, straight from the Example cell.
4. Every anti_pattern phrased as the failure, not as a restatement of the technique.
5. Report: per-section counts; every row whose Situation did not map to exactly one member;
   every row where the "What it technically is" cell made type genuinely ambiguous (I expect
   B5 "compute the CI from n" and C5 "multiple-comparison correction" to be arguable).
````

---

### EL-111 — S11 Extract D, E, F

**Type:** Task · **Est:** 0.3 · **Depends:** EL-110 · **Blocks:** EL-112 ·
**Done when:** 23 records load; integrity check empty

**Files** → `evalloop/registry/records/{D_rare_events,E_diagnostics,F_judge_trust}.*`

**Subtasks**
- [ ] D 6, E 8, F 9 → 23 records, same mapping and rules as `EL-110`
- [ ] Type D's constraints, E's diagnostics, F's procedures/statistics/constraints
- [ ] Map E1–E8 onto the `measurement` family and tabulate it
- [ ] `load_records()` + `check_integrity()`

**Acceptance criteria**
- [ ] 43 records total load; `check_integrity()` returns `[]`
- [ ] Constraint records typed `constraint`, `anti_pattern` carrying the source's own figure
- [ ] Report has one row per E record naming the `measurement` situation it triggers on
- [ ] Report names thresholds seen in lookup rows and deliberately left for enrichment

**Out of scope** Any enrichment field.

**Gotchas** The E1–E8 ↔ `measurement` mapping is the clearest available test of `EL-103`'s work.
If it isn't near one-to-one, report it loudly.

````text
WHAT I WANT
23 skeleton records for sections D (6), E (8) and F (9), same field mapping and same rules as
EL-110.

WHAT IS IN THE TICKET
These three sections are where type assignment stops being obvious, and getting it wrong here
is what makes the planner recommend a diagnostic as if it were a grader:
  - D (rare events) contains at least one CONSTRAINT: "never accuracy on a rare class"
    (D1's title is "PRECISION-RECALL CURVE AND PR-AUC, NEVER ACCURACY"). D6 forbids a
    "% safe" headline. Constraints are what the planner uses to populate PROHIBITED.
  - E (when a number looks wrong) is almost entirely DIAGNOSTICS. All eight records are
    symptom-triggered: E1 score jumped, E2 improved-but-users-did-not-notice, E3 longer
    answers, E4 changed-nothing-score-moved, E5 everything-scores-90%+, E6 nothing-completes,
    E7 benchmark-too-good, E8 one-benchmark-dominance. These map to the measurement family
    of Situation, which exists for exactly this.
  - F (trusting your grader) mixes PROCEDURES (F1 validate against gold labels, F7 one call
    per criterion, F8 few-shot from disagreements, F9 fix the rubric first), STATISTICS
    (F2 Cohen's kappa, F3 Krippendorff's alpha) and CONSTRAINTS (F5 cross-family panel ->
    never same-family judging).

THE INPUT
  - evals-situation-to-technique.md, sections D, E and F only. 23 rows: D 6, E 8, F 9.
  - Deep-dive headers for numbering only. D1-D6, E1-E8, F1-F9.
  - evalloop/vocab/situations.py - the measurement family (score_jumped,
    score_up_business_flat, length_increased, no_change_score_moved, all_candidates_high,
    all_candidates_zero, benchmark_too_good, single_benchmark_dominance) should map almost
    one-to-one onto E1-E8. If it does not, that is a vocabulary finding worth reporting
    loudly, because it is the clearest test of EL-103's work that exists.
  - The grader_trust family for F, and the data family (rare_class) for D.

THE RESULT I WANT TO SEE
1. D_rare_events, E_diagnostics, F_judge_trust record files. 43 records total now load;
   check_integrity() returns [].
2. Constraint records typed constraint, with anti_pattern stating the failure the constraint
   prevents ("flag nothing scores 99.8%" style, with the source's own figure).
3. A report row for each E record saying which measurement situation it triggers on, so the
   E-to-measurement mapping can be eyeballed in one place.
4. Report: thresholds you saw in the lookup rows and deliberately did NOT record because
   enrichment owns them. I want to know you saw them and left them.
````

---

### EL-112 — S12 Extract G, H, I, J

**Type:** Task · **Est:** 0.4 · **Depends:** EL-111 · **Blocks:** EL-113 ·
**Done when:** counts per section reported; 73 total

**Files** → `evalloop/registry/records/{G_rag,H_agents,I_production,J_model_selection}.*`

**Subtasks**
- [ ] G 8, H 8, I 9, J 5 → 30 records, completing the skeleton at 73
- [ ] Type H1 as the precondition it is (procedure/constraint, not metric)
- [ ] `gates` on I: absolute for safety/schema, statistical for quality — as stated, else null
- [ ] Per-section count table against the expected figures

**Acceptance criteria**
- [ ] `load_records()` returns exactly **73**; `check_integrity()` returns `[]`
- [ ] Counts match A 7 · B 7 · C 6 · D 6 · E 8 · F 9 · G 8 · H 8 · I 9 · J 5
- [ ] No `unlocks` / `requires` added here — build order is `EL-116`
- [ ] Report: every unrepresentable row, and every `gates` left null

**Out of scope** G's build order, H's preconditions as edges — both `EL-116`.

**Gotchas** H3 is **pass^k**, not pass@k. If your count exceeds 73 you parsed the trailing
"THE MASTER LOOKUP" cheat-sheet — `tests/test_corpus_shape.py` guards exactly that.

````text
WHAT I WANT
30 skeleton records for sections G (8), H (8), I (9) and J (5), completing the skeleton at 73.

WHAT IS IN THE TICKET
Same mapping and rules. What is specific here:
  - G (RAG): G1 recall@k + gold context, G2 oracle-context + stage attribution,
    G3 faithfulness, G4 nDCG@10, G5 MRR/hit@k, G6 unanswerable set, G7 context precision +
    distractors, G8 citation precision/recall. Mostly metrics. The BUILD ORDER between them
    is EL-116's job, not this stage's - do not add unlocks or requires here.
  - H (agents): H1 sandboxed resettable env + trajectory logging, H2 outcome-based success,
    H3 pass^k (NOT pass@k - the corpus is explicit), H4 cost per successful task,
    H5 milestones + step localisation, H6 prompt-injection ASR alongside utility,
    H7 trajectory review -> failure taxonomy, H8 k>=5 trials -> always/flaky/never.
    H1 is a procedure or constraint, not a metric; it is the precondition for the rest.
  - I (production): I1 CI regression gate, I2 split deterministic from statistical,
    I3 error analysis, I4 pinned versions + daily canary, I5 sampled online eval,
    I6 business metric + guardrails, I7 pre-registered A/B, I8 eval set from logs,
    I9 shadow -> staged canary. Gate matters here: absolute for safety and schema,
    statistical for quality. Record what the source states, null where it does not.
  - J (model selection): J1 constraint filter + 50-item smoke, J2 full domain eval,
    J3 cost-quality Pareto, J4 same harness, J5 replicate vendor claims. These are
    procedures, and they trigger on lifecycle.model_selection and
    comparison.external_leaderboard.

THE INPUT
  - evals-situation-to-technique.md, sections G, H, I and J. 30 rows: G 8, H 8, I 9, J 5.
  - Deep-dive headers for numbering only.
  - The lifecycle family of Situation for I and J; artifact.rag_answer and
    artifact.agent_action for G and H.
  - tests/test_corpus_shape.py - it pins the total at 73 and excludes the trailing
    "THE MASTER LOOKUP" cheat-sheet. If your count disagrees, you parsed the cheat-sheet.

THE RESULT I WANT TO SEE
1. G_rag, H_agents, I_production, J_model_selection record files.
2. load_records() returns exactly 73; check_integrity() returns [].
3. A per-section count table in the report, against the expected A 7, B 7, C 6, D 6, E 8,
   F 9, G 8, H 8, I 9, J 5.
4. Report: every lookup row that could not be represented at all, and every record whose
   gates value you left null because the source did not state one. Null is the correct answer
   and I want the list.
````

---

## Group 5 — Enrichment (T4)

> Each stage reads the **deep dives** and fills what the skeleton left empty: `requires ·
> required_tools · required_signals · ladder_priority · companion_checks · unlocks ·
> conflicts_with · capture_cost · rule_of_thumb`, and upgrades `source_ref` to the deep-dive
> location. Run `check_integrity()` + `pytest` after **each** stage. **If the source states no
> number, use `null`.** Flag every threshold interpreted from prose.

### EL-113 — S13 Enrich A + B

**Type:** Task · **Est:** 0.4 · **Depends:** EL-112, EL-004 ✅ · **Blocks:** EL-114 ·
**Done when:** ladder, conflicts and the McNemar threshold filled

**Files** → `records/A_grading.*`, `records/B_comparison.*` · `TASKS.md` S13 (drop rung 6)

**Subtasks**
- [ ] `ladder_priority` 1–5 on A's graders; rule on A3 vs A5 sharing rung 3
- [ ] A7 left null + reported
- [ ] `conflicts_with` edge for execution-beats-judging
- [ ] B3 discordant-pair threshold **as stated in B3** → `requires`
- [ ] B7 cluster-bootstrap grouping requirement
- [ ] Upgrade `source_ref` to deep-dive granularity
- [ ] Fix `TASKS.md` S13

**Acceptance criteria**
- [ ] `ladder_priority` set on exactly the grader records, 1–5, A7 null and explained
- [ ] ≥ 1 `conflicts_with` edge encoding execution-beats-judging, justifying line in
      `extraction_notes`
- [ ] Every A/B `source_ref` reads `A-choosing-how-to-grade.md § A1` style
- [ ] `check_integrity()` empty; `pytest` green; `TASKS.md` S13 corrected
- [ ] Report: thresholds verbatim (with source line) · left null · interpreted from prose ·
      schema changes needed

**Out of scope** Writing 25 because `TASKS.md` says "~25". Widening a field's type to fit a record.

**Gotchas** `CLAUDE.md §7.5` predicts a schema change after the first two deep dives — **this is
that stage.** Candidates: an ordering constraint `unlocks`/`requires` can't express; a
`rule_of_thumb` that's a formula; a threshold that's a range. Stop and report.

````text
WHAT I WANT
Sections A and B enriched from A-choosing-how-to-grade.md and B-comparing-two-things.md.

WHAT IS IN THE TICKET
  - ladder_priority from A's ladder: 1 execution (A1), 2 end-state (A2), 3 deterministic,
    4 judge (A4), 5 human (A6). FIVE RUNGS. There is no distilled rung - decision EL-004
    removed it, and TASKS.md S13's "6 distilled" is stale. Correct that line in the same
    diff. A3 (normalised exact match) and A5 (schema validation + field-level scoring) are
    both deterministic; decide whether they share rung 3 or whether the source orders them,
    and say which, with the line that decided it.
  - A7 tiered online scoring wraps the ladder rather than ranking among the rungs. Its
    priority is an OPEN QUESTION per CLAUDE.md §6. Leave it null and report it; do not
    invent a rung 0 or 6.
  - conflicts_with where A says execution beats judging. The corpus line is "if there is any
    way to execute, execute" - 00-INDEX.md's first cross-cutting principle says the same.
    Encode it as a real edge, because this is what makes the planner suppress a judge for
    code generation.
  - B3 McNemar's discordant-pair threshold into requires. TASKS.md says "~25". Do NOT write
    25 because TASKS.md says so - open B3 and copy what it states. If it states a range or a
    rule rather than a number, encode the form it states or null, and report the discrepancy.
  - B7 cluster bootstrap's grouping requirement into requires / required_signals.

EXPECT A SCHEMA CHANGE, AND RAISE IT
CLAUDE.md §7.5 predicts the schema will need a change after the first two deep-dive files,
and this is that stage. Candidates I can already see: ordering constraints that
unlocks/requires cannot express; a rule_of_thumb that is a formula rather than a string;
a threshold that is a range. When you hit one, STOP and report it. Do not widen a field's
type quietly to make a record fit.

THE INPUT
  - knowledge rules/A-choosing-how-to-grade.md - all seven techniques, especially "How to do
    it properly" and "When NOT to use it".
  - knowledge rules/B-comparing-two-things.md - B1-B7, especially B3 and B7.
  - 00-INDEX.md's five cross-cutting principles - 1 (execute over judge) and 3 (same items
    both sides) both become edges or required_signals.
  - decisions/EL-004-claude-md-corpus-gaps.md - the ladder's real depth.

THE RESULT I WANT TO SEE
1. A and B records enriched; source_ref upgraded to "A-choosing-how-to-grade.md § A1" form.
2. ladder_priority on exactly the grader records, 1-5, with A7 null and explained.
3. At least one conflicts_with edge encoding execution-beats-judging, and the source line
   that justifies it in extraction_notes.
4. check_integrity() empty; pytest green; TASKS.md S13 corrected.
5. Report: every threshold copied verbatim (with its source line), every threshold left null,
   every threshold you interpreted from prose (flagged for human review), and any schema
   change you believe is now required.
````

---

### EL-114 — S14 Enrich C + D

**Type:** Task · **Est:** 0.4 · **Depends:** EL-113 · **Blocks:** EL-115 ·
**Done when:** verbatim rules of thumb; rare-class constraint encoded

**Why.** The sharpest test of "never invent a number" in all of M0 — three figures appear in
two different forms across our own docs.

**Files** → `records/C_statistics.*`, `records/D_rare_events.*` · `TASKS.md` S14/T16,
`AGENT.md §3.8`, `CLAUDE.md §4` (whichever the corpus proves wrong)

**Subtasks**
- [ ] C2 power formula — copy verbatim, fix the wrong doc
- [ ] C3 noise floor — copy verbatim, fix the wrong doc
- [ ] B5/C CI margin — record where the corpus states it
- [ ] C4 near-boundary + rule of three → `requires`/`required_signals`
- [ ] D companion pairings, both directions if the source demands both
- [ ] Rare-class accuracy prohibition as a constraint's effect
- [ ] D5/D6 per-category count requirements

**Acceptance criteria**
- [ ] `rule_of_thumb` strings character-for-character as the corpus writes them, symbols intact
- [ ] Rare-class prohibition renders under PROHIBITED with a reason (`USER_EXPERIENCE.md §3.1`)
- [ ] D companions present in the required direction(s)
- [ ] `check_integrity()` empty; deep-dive `source_ref`s
- [ ] Report has a three-row table: corpus text · which doc was wrong · fix applied

**Out of scope** Averaging two conflicting doc figures. Implementing any statistic.

**Gotchas** `n ≈ 16/gap²` vs `n ≈ 16·p(1−p)/δ²` are **different formulas**. Noise floor: docs
say 3–5, corpus C3 is titled `k ≥ 5 RUNS PER ITEM`.

````text
WHAT I WANT
Sections C and D enriched from C-deciding-whether-a-result-is-real.md and D-rare-events.md.

WHAT IS IN THE TICKET - AND THREE NUMBERS THE DOCS DISAGREE ON
This ticket is the sharpest test of "never invent a number" in all of M0, because three
figures appear in two forms across our own docs. The corpus file decides; report which doc
was wrong.
  1. POWER. TASKS.md S14 and T16 say "n ~ 16/gap^2". CLAUDE.md §4 says
     "n ~ 16*p(1-p)/delta^2". These are different formulas. Open C2 and copy what it states,
     verbatim, into rule_of_thumb. Then fix whichever doc is wrong.
  2. NOISE FLOOR. TASKS.md S14 says "3-5 runs". AGENT.md §3.8 says "3-5 repeat runs".
     CLAUDE.md §4 says "k >= 5 runs", and the corpus's own C3 heading is
     "k >= 5 RUNS PER ITEM; REPORT MEAN +- SD ACROSS RUNS". Copy C3. Fix the stale docs.
  3. CI MARGIN. "margin ~ 100/sqrt(n)" is attributed to B in CLAUDE.md §4 and belongs to B5.
     If C restates it, record it where the corpus states it and cite both.
Also: C4's near-boundary condition (Wilson / Clopper-Pearson near 0% or 100%, rule of three
at zero) goes into requires or required_signals, verbatim.

D's work:
  - Companion pairings, which are the point of section D: violation rate <-> over-refusal
    rate (never reported alone), and precision <-> a stated recall level. Encode both as
    companion_checks in BOTH directions if the source demands both.
  - "Accuracy is prohibited on a rare class" as the effect of a constraint record, with the
    source's own figure in anti_pattern ("flag nothing scores 99.8%" if that is what it says).
  - D5 red-team ASR per category and D6 upper confidence bound + per-category counts:
    requires per-category counts, so the planner can mark them pending at low n.

THE INPUT
  - knowledge rules/C-deciding-whether-a-result-is-real.md - C1 Wilson, C2 power, C3 k>=5
    runs, C4 near-boundary + rule of three, C5 multiple comparisons, C6 permutation.
  - knowledge rules/D-rare-events.md - D1-D6.
  - CLAUDE.md §4's section table, TASKS.md S14, AGENT.md §3.8 - the three conflicting claims.

THE RESULT I WANT TO SEE
1. C and D enriched, source_ref at deep-dive granularity, check_integrity() empty.
2. rule_of_thumb strings that are character-for-character what the corpus says. If the corpus
   writes a formula with a particular symbol, keep the symbol.
3. The rare-class accuracy prohibition expressed so the planner can render it under
   PROHIBITED with a reason, per USER_EXPERIENCE.md §3.1.
4. Companion pairings for D, in the direction(s) the source requires.
5. Report: a three-row table resolving the power formula, the noise floor and the CI margin -
   corpus text, which doc was wrong, and the fix applied.
````

---

### EL-115 — S15 Enrich E + F

**Type:** Task · **Est:** 0.4 · **Depends:** EL-114 · **Blocks:** EL-116 ·
**Done when:** κ / flip-rate thresholds recorded; cross-family constraint encoded

**Files** → `records/E_diagnostics.*`, `records/F_judge_trust.*` · `TASKS.md` S15/T36 if the
corpus proves them wrong

**Subtasks**
- [ ] Capture each E record's **first action**; if no field fits, report the schema gap
- [ ] `requires` on E records expressing the need for history/baseline
- [ ] Judge-score ↔ E3 length-bias companion edge
- [ ] F1 gold-label count verbatim; resolve against the two stale doc claims
- [ ] F2 κ and F4 flip-rate figures verbatim or null
- [ ] F5 cross-family constraint + `llm_api_cross_family`; `human_labels` on F1/F3/F9

**Acceptance criteria**
- [ ] Length-bias companion and cross-family constraint both present and traceable to a source line
- [ ] First-run plans mark E diagnostics pending with a reason rather than firing them
- [ ] `check_integrity()` empty; `pytest` green
- [ ] Report: F1 resolution (corpus vs the two doc claims) · κ and flip-rate with source lines
      or explicit null · every E "first action" with no schema home

**Out of scope** Averaging 50–100 and 150–200. Implementing κ.

**Gotchas** κ and flip-rate become **runtime gates** in M4 (T36) — a wrong number here ships.
`AGENT.md §5` restates several E/F rules in prose: use it to check for missing edges, never as
a source for a number.

````text
WHAT I WANT
Sections E and F enriched from E-when-a-number-looks-wrong.md and F-trusting-your-grader.md.

WHAT IS IN THE TICKET
E (diagnostics):
  - Every E record has a FIRST ACTION in the source. Capture it - if the schema has no home
    for it, say so rather than losing it (extraction_notes is the fallback, and a missing
    field is a reportable schema gap).
  - Most E diagnostics need HISTORY: a baseline run, or a previous score to have jumped from.
    That belongs in requires (e.g. a run count or a baseline flag), which is what lets the
    planner mark them pending on a first run instead of firing them meaninglessly.
  - The length-bias companion: E3 (length-controlled win rate) pairs with any judge score.
    AGENT.md §5 states the rule as "any judge score is reported with output length". Encode
    the companion_checks edge so a judge record pulls E3 in.

F (judge trust) - AND A NUMBER THE DOCS DISAGREE ON:
  - F1's own heading is "VALIDATE AGAINST 150-200 HUMAN GOLD LABELS BEFORE USE", and
    CLAUDE.md §4 says 150-200. TASKS.md S15 says "calibration 50-100 labels" and TASKS.md
    T36 says "50-100 human labels". Open F1, copy what it states, and report which doc is
    wrong. Do not average them.
  - Cohen's kappa threshold (F2) and the flip-rate ceiling (F4, documented elsewhere as
    "unreliable above 10-15%"): copy verbatim from the corpus or null. These two become
    runtime gates in M4 (T36), so a wrong number here ships.
  - F5 cross-family judge panel -> a CONSTRAINT record: never same-family judging, because
    of self-preference bias. required_tools must include llm_api_cross_family.
  - F1/F3/F9 need human_labels in required_tools. F3 (Krippendorff's alpha) triggers on
    multiple_annotators; F9 (labellers disagree -> fix the rubric first) on annotators_disagree.

THE INPUT
  - knowledge rules/E-when-a-number-looks-wrong.md - E1-E8, each with its symptom and first
    action.
  - knowledge rules/F-trusting-your-grader.md - F1-F9.
  - AGENT.md §5's non-negotiable behaviours - several are F and E records in prose form; use
    them to check you have not missed an edge, never as a source for a number.

THE RESULT I WANT TO SEE
1. E and F enriched; check_integrity() empty; pytest green.
2. The judge-score <-> length-bias companion edge, and the cross-family constraint, both
   present and both traceable to a source line.
3. requires on E records expressing the need for history, so a first-run plan marks them
   pending with a reason rather than running them.
4. Report: the F1 label-count resolution (corpus text vs the two stale doc claims), the
   kappa and flip-rate figures with their source lines or an explicit null, and every E
   "first action" that had no schema home.
````

---

### EL-116 — S16 Enrich G + H

**Type:** Task · **Est:** 0.4 · **Depends:** EL-115 · **Blocks:** EL-117 ·
**Done when:** recall-before-faithfulness and env-before-agent are encoded as data

**Why.** The ticket where **build order becomes machine-readable** — the most visible planner
behaviour in Gate 0, and the one `ARCHITECTURE.md §6.4` says must be "enforced by the registry,
not by hand".

**Files** → `records/G_rag.*`, `records/H_agents.*`

**Subtasks**
- [ ] G1 recall@k → G3 faithfulness edge, direction checked against fixture 4
- [ ] G2 follows G1; G6's two numbers paired if the source pairs them
- [ ] G `required_tools`: `vector_store`, `source_doc_read`
- [ ] H1 as precondition for all of H; `requires_pre_instrumentation: true` as a **boolean**
- [ ] H1/H7 `unlocks` → H4, H5, H7, reward-hacking detection
- [ ] H3 pass^k and H8 k values verbatim; `trace_capture`, `snapshot_restore`
- [ ] Hand-trace two plans and write them into the report

**Acceptance criteria**
- [ ] `check_integrity()` empty — every new `unlocks`/`requires` id resolves (most edges of any stage)
- [ ] Hand-trace for `rag_answer`, `vector_store` granted, no runs: G1 READY, faithfulness
      PENDING. **If faithfulness isn't pending, the edge is wrong.**
- [ ] Hand-trace for `agent_action` without `snapshot_restore`/`trace_capture`
- [ ] `requires_pre_instrumentation: true` present as a boolean on the trajectory records
- [ ] Report names any ordering constraint the schema can't express

**Out of scope** Taking numbers from `ARCHITECTURE.md §6.4` — it describes intent, not source.

**Gotchas** Boolean requirements are why `EL-121` must treat them distinctly from numeric
thresholds. Likeliest place in M0 for a genuine schema gap — look for it rather than forcing a fit.

````text
WHAT I WANT
Sections G and H enriched from G-rag-systems.md and H-agents.md. This is the ticket where
BUILD ORDER becomes machine-readable, which is the single most visible planner behaviour in
Gate 0's fixtures.

WHAT IS IN THE TICKET
G (RAG) - encode the build order as data, not as a comment:
  - recall@k (G1) precedes faithfulness (G3). The corpus is explicit that end-to-end accuracy
    cannot tell you which stage broke. Express it with unlocks and/or requires so that a
    plan for rag_answer on a fresh repo puts G1 in READY and G3 in PENDING with a reason.
    Fixture 4 (EL-118) asserts exactly this, so get the direction of the edge right.
  - G2 oracle-context test and per-failure stage attribution follow G1.
  - required_tools across G: vector_store, source_doc_read.
  - G6's unanswerable set produces TWO numbers (false-answer rate and abstention precision /
    over-abstention). If the source pairs them, they are companion_checks, not one metric.

H (agents) - the precondition is the whole point:
  - H1 (sandboxed, resettable environment + full trajectory logging) precedes ALL agent
    evaluation. AGENT.md §5 states it as "resettable environment before any agent eval".
    Encode it so nothing in H is READY without it.
  - Trajectory capture needs requires_pre_instrumentation: true - a BOOLEAN requirement, not
    a numeric threshold, which is why EL-121 must handle the two kinds distinctly.
  - H1/H7 unlock: H4 cost per successful task, H5 step-level failure localisation,
    H7 trajectory taxonomy, and reward-hacking detection. Encode the unlocks edges.
  - H3 is pass^k (all k trials succeed), NOT pass@k. H8 is k >= 5 trials ->
    always / flaky / never. Copy both k values verbatim.
  - required_tools across H: trace_capture, snapshot_restore.

THE INPUT
  - knowledge rules/G-rag-systems.md - G1-G8, and whatever it says about ordering.
  - knowledge rules/H-agents.md - H1-H8, especially H1's preconditions and H3 vs pass@k.
  - ARCHITECTURE.md §6.4's RAG and agent recipes - they describe the intended planner
    behaviour and say "enforced by the registry, not by hand". Use them to check your edges
    produce that behaviour; do not take numbers from them.
  - TASKS.md Group 6 fixtures 4 and 5 - the two fixtures this ticket must satisfy later.

THE RESULT I WANT TO SEE
1. G and H enriched; check_integrity() empty (every unlocks/requires id must resolve, and
   this stage adds the most edges of any).
2. A written trace in the report: for situation rag_answer with vector_store granted and no
   runs yet, which records would be READY and which PENDING, by hand, from the records as
   now authored. If faithfulness is not pending, the edge is wrong.
3. The same trace for agent_action without snapshot_restore or trace_capture granted.
4. requires_pre_instrumentation: true present on the trajectory records as a boolean.
5. Report: any ordering constraint the schema could not express. This is the likeliest place
   in M0 for a genuine schema gap, so look for it rather than forcing a fit.
````

---

### EL-117 — S17 Enrich I + J

**Type:** Task · **Est:** 0.4 · **Depends:** EL-116 · **Blocks:** EL-118 ·
**Done when:** every record has a resolvable deep-dive `source_ref`

**Why.** Last authoring ticket, so it owns the end-to-end sweep: all 73 records traceable, and
the `PLAN.md §5` sanity queries answered by hand *before* a planner exists.

**Files** → `records/I_production.*`, `records/J_model_selection.*` · a new `source_ref`
resolution test

**Subtasks**
- [ ] I `gates`: absolute for safety/schema, statistical for quality — as stated, else null
- [ ] I4 baseline requirement; `production_logs` on I5/I8; I3's "100 failures" verbatim or null
- [ ] J figures verbatim (50-item smoke, 300–500, 100–200); J2/J3 edges into B/C machinery
- [ ] Automate the `source_ref` resolution check and keep it as a test
- [ ] Answer the six `PLAN.md §5` sanity queries by hand

**Acceptance criteria**
- [ ] All **73** records carry a deep-dive `source_ref`, not a master-lookup one
- [ ] A kept test proves every `source_ref` names a file in `knowledge rules/` **and** a section
      that exists in it
- [ ] `check_integrity()` empty; `pytest` green; `mypy --strict` clean
- [ ] Six sanity queries answered by hand in the report, with any wrong answer flagged **now**
- [ ] Report, per file: unfillable fields · prose-interpreted thresholds · inexpressible ordering

**Out of scope** Fixtures (`EL-118`). Planner code.

**Gotchas** `TASKS.md` S17 says the I/J details "were cut off in the source screenshot" — they
are not cut off in the repo. Read the files: nine I records, five J records. `AGENT.md §5`: an
unresolvable citation is an invented number with extra steps.

````text
WHAT I WANT
Sections I and J enriched, and the whole 73-record registry finished and self-consistent.
This is the last authoring ticket, so it also owns the end-to-end sweep.

WHAT IS IN THE TICKET
I (production):
  - gates is the field that matters here: ABSOLUTE for safety and schema, STATISTICAL for
    quality. I1 (CI regression gate + must-pass golden set) and I2 (split deterministic tests
    from statistical evals; gate on a multi-run mean) are the two that set the pattern.
    Record what the source states and null where it does not.
  - I4 pinned model versions + daily canary with drift alerts: needs history, so requires a
    baseline. required_tools includes production_logs for I5 (sampled online eval,
    reference-free judge + implicit signals) and I8 (eval set from stratified logs).
  - I3 error analysis (sample 100 failures, open-code, count) is a PROCEDURE. So is I8, and
    so is the failures-as-tests flywheel - 00-INDEX.md's fifth cross-cutting principle.
    Copy the "100 failures" figure verbatim or leave null.
  - I6 business outcome metric + guardrails and I7 pre-registered online A/B trigger on the
    lifecycle family (measuring_impact, ab_testing). I9 shadow -> staged canary with
    auto-rollback triggers on shipping_change.
  - TASKS.md S17 notes the I/J details "were cut off in the source screenshot". They are not
    cut off in the repo: read the files. Nine I records, five J records.

J (model selection):
  - J1 hard-constraint filter -> 50-item smoke test; J2 full domain eval (300-500 items) with
    paired stats + human pairwise on the top 2; J3 cost-quality Pareto (cheapest model within
    the best model's CI); J4 same benchmark version / shots / harness, or rerun it yourself;
    J5 replicate vendor claims on your own 100-200 item held-out set. Every one of those
    figures is copied verbatim or left null.
  - J2 and J3 depend on B and C machinery - encode unlocks/requires edges to the paired-stats
    and CI records rather than restating the statistics inside J.

THE RESULT I WANT TO SEE
1. I and J enriched. All 73 records now carry a deep-dive source_ref, not a master-lookup one.
2. A sweep proving it: every record's source_ref names a file that exists in
   "knowledge rules/" and a section that exists in that file. Automate the check and keep it
   as a test - an unresolvable citation is an invented number with extra steps (AGENT.md §5).
3. check_integrity() empty; pytest green; mypy --strict clean.
4. The PLAN.md §5 sanity queries answered BY HAND from the records as authored, before any
   planner exists: summarization -> faithfulness with the length check attached; code
   generation -> execution first, judging deprioritised or excluded; RAG -> recall before
   faithfulness; rare class -> recall ready, accuracy prohibited; "what works on a single
   observation?" -> only facts; "what needs 200+ samples?" -> significance tests and judge
   agreement. If any answer looks wrong, the records are wrong and I want to know now, not
   at EL-123.
5. Report, per file: fields you could not fill; thresholds stated in prose that you had to
   interpret (flagged for human review); any ordering constraint the schema cannot express.
````

---

## Group 6 — Fixtures (T5), written BEFORE the planner

> Derive every expectation from the **source methodology**, not from imagined code. All 20 fail
> until `EL-123`; that is correct. **Never edit a fixture to make a test pass** — if one looks
> wrong, stop and flag it for human review (`CLAUDE.md §7.4`).

### EL-118 — S18 Fixture format + fixtures 1–5

**Type:** Task · **Est:** 0.4 · **Depends:** EL-117, EL-106 · **Blocks:** EL-119 ·
**Done when:** 5 fixtures load

**Files** → `tests/fixtures/planner/*.yaml` (5 new) · fixture loader in the test suite

**Subtasks**
- [ ] Document the fixture schema; load it through the `EL-106` parser
- [ ] Loader rejects unknown record ids, situations and tools
- [ ] Fixtures 1–5 (see prompt), each with the source line that justifies it
- [ ] Hand-derive every expectation from the authored records

**Acceptance criteria**
- [ ] 5 fixtures **load and validate**; their assertions fail only for want of a planner
- [ ] A fixture naming a non-existent record id fails loudly at load
- [ ] `ready` treated as **ordered**; `pending` strings in
      `"needs <key>: <threshold>, have <actual>"` form
- [ ] Fixture 2 asserts what remains **and** that the plan says why
- [ ] Fixture 4 asserts recall@k orders before faithfulness, with faithfulness pending
- [ ] Report names any fixture where the source was ambiguous about ordering or gating

**Out of scope** Planner code. Convenient readings of an ambiguous source.

**Gotchas** `evidence` stays minimal — only the keys the fixture tests. An empty `prohibited` in
a fixture that should prohibit something is exactly the bug this format exists to catch.

````text
WHAT I WANT
The fixture format, parsed by the EL-106 parser, plus the first five fixtures in
tests/fixtures/planner/.

WHAT IS IN THE TICKET
The format is given in TASKS.md Group 6:
  name: summarization_first_run
  given:
    situations: [summarization]
    available_tools: [source_doc_read, llm_api_cross_family]
    evidence: {samples: 1, runs: 1}
  expect:
    ready: [G3_faithfulness, E3_length_bias]   # order matters
    pending:
      B3_mcnemar: "needs paired_runs: 2, have 1"
    unavailable: []
    companions:
      G3_faithfulness: [E3_length_bias]
    prohibited: []

Rules:
  - ready is ORDERED. The order is the planner's deterministic order, so a fixture asserts
    sequence, not just membership.
  - pending values are the human-readable unmet requirement, in the
    "needs <key>: <threshold>, have <actual>" form from AGENT.md §3.5.
  - Where the source PROHIBITS something, assert it explicitly. An empty prohibited list in a
    fixture that should prohibit something is the failure this format exists to catch.
  - evidence is minimal: only the keys the fixture is actually testing.
  - Record ids must be real ids from the registry. A fixture naming a non-existent id should
    fail loudly at load, so add that check.

The five fixtures:
  1. code_generation, first run, sandbox + test_runner available
  2. code_generation, NO sandbox -> execution unavailable; assert what remains, and that the
     plan says why
  3. summarization, first run
  4. rag_answer -> recall@k must order BEFORE faithfulness (and faithfulness pending until
     recall is measured, per EL-116's edges)
  5. agent_action, NO trace capture -> the trajectory family is unavailable, and says so

THE INPUT
  - TASKS.md Group 6 - the format and the fixture list.
  - The 73 authored records - every expectation must be derivable from them BY HAND. If you
    cannot derive it, the fixture is guessing and the record may be wrong.
  - USER_EXPERIENCE.md §3.1 - the four states and what each means to a user.
  - AGENT.md §3.5 - the seven-step resolution order the expectations must be consistent with.

THE RESULT I WANT TO SEE
1. A documented fixture schema and a loader for it in the test suite, with a clear failure
   when a fixture names an unknown record id or an unknown situation or tool.
2. Five fixture files that LOAD and VALIDATE, and whose assertions currently fail for want of
   a planner.
3. For each fixture, a comment or sidecar note naming the source line that justifies the
   expectation - especially fixture 4's ordering.
4. Report: any fixture where the source was ambiguous about ordering or gating. Flag it; do
   not pick the convenient reading.
````

---

### EL-119 — S19 Fixtures 6–20

**Type:** Task · **Est:** 0.6 · **Depends:** EL-118 · **Blocks:** EL-120 ·
**Done when:** 20 fixtures load

**Files** → `tests/fixtures/planner/*.yaml` (15 new)

**Subtasks**
- [ ] Fixtures 6–20 per `TASKS.md` Group 6
- [ ] Straddle B3's **recorded** threshold in fixtures 8 and 9
- [ ] Write up the fixture-11 κ / label-count contradiction for human decision
- [ ] Use `EL-114`'s verbatim margin rule in fixture 14
- [ ] Fixture 20: assert PHI gate **position**, not just presence
- [ ] Fixture 18: assert no duplicates and one deterministic order across both families

**Acceptance criteria**
- [ ] 20 fixtures total load and validate; all fail for want of a planner
- [ ] Fixtures 8/9 straddle whatever `EL-113` recorded — **if that was `null`, stop and say so
      rather than inventing 25**
- [ ] Fixture 11's contradiction with F1 is escalated, with neither fixture nor record quietly
      changed
- [ ] Report: every ambiguous fixture + the full fixture-11 write-up with options

**Out of scope** Resolving fixture 11 yourself. Inventing a threshold to make 8/9 work.

**Gotchas** Fixture 11 ("60 labels, κ 0.71 → judge may gate") contradicts F1's 150–200 if the
corpus figure holds. `CLAUDE.md §7.4` is written for exactly this case: flag, don't fix.

````text
WHAT I WANT
The remaining 15 fixtures, same format, same derive-from-source rule.

WHAT IS IN THE TICKET
From TASKS.md Group 6:
   6. structured_extraction with a schema present
   7. two_candidates, 1 run -> McNemar pending
   8. two_candidates, 2 paired runs, 8 discordant -> STILL pending, threshold not met
   9. two_candidates, 2 paired runs, 40 discordant -> McNemar ready
  10. new_judge_built, 0 labels -> judge cannot gate
  11. new_judge_built, 60 labels, kappa 0.71 -> judge may gate
  12. rare_class -> recall ready, accuracy EXPLICITLY prohibited
  13. grouped_items -> cluster bootstrap REPLACES plain bootstrap (a conflicts_with edge)
  14. small_sample (n=25) -> statistical comparisons pending, with the margin stated
  15. score_jumped -> reward-hacking investigation
  16. all_candidates_high -> ceiling remedy
  17. length_increased + summarization -> length-bias diagnostic
  18. api_endpoint + sql_generation together -> both families, correctly merged (multi-label)
  19. shipping_change -> regression suite + statistical gates
  20. phi_present + structured_extraction -> PHI gate precedes everything

THREE OF THESE ENCODE NUMBERS AND MUST AGREE WITH THE RECORDS
  - 8 and 9 straddle B3's discordant-pair threshold. Whatever EL-113 copied verbatim from B3
    is the threshold these two fixtures must straddle. If EL-113 recorded null, these two
    fixtures cannot be written as specified - say so and stop, rather than inventing 25.
  - 11 uses 60 labels and kappa 0.71. EL-115 resolved F1's gold-label count (150-200 per the
    corpus, against TASKS.md's 50-100). If the real figure is 150-200, fixture 11's "60
    labels -> judge may gate" CONTRADICTS the corpus. Do not quietly change the fixture, and
    do not quietly change the record. Flag the contradiction for human review - this is
    exactly the case CLAUDE.md §7.4 is written for.
  - 14 asserts the margin is stated for n=25. Use the verbatim margin rule EL-114 recorded.

THE RESULT I WANT TO SEE
1. 15 more fixture files; 20 total; all loading and validating; all failing for want of a
   planner.
2. Fixture 20's ordering made explicit: PHI gate precedes everything, so assert position,
   not just presence.
3. Fixture 18 asserting the multi-label merge has no duplicates and a single deterministic
   order across both families.
4. Report: every fixture where the source was ambiguous, and the full write-up of the
   fixture-11 kappa/label-count question with my options. I want to decide that one myself.
````

---

## Group 7 — Planner (T6)

> Make all 20 fixtures pass. **Do not modify a fixture to match the implementation.**

### EL-120 — S20 `match()`

**Type:** Story · **Est:** 0.4 · **Depends:** EL-119 · **Blocks:** EL-121 ·
**Done when:** multi-label merge; deterministic order

**Files** → `evalloop/registry/query.py` (new) · tests

**Subtasks**
- [ ] `match(records, situations) -> tuple[TechniqueRecord, ...]`, pure
- [ ] Multi-label merge without duplication
- [ ] Order: graders by `ladder_priority` asc → non-graders grouped by `type` → `id` alphabetical
- [ ] Decide and document the order of the type groups themselves
- [ ] Unit tests on **hand-built** records

**Acceptance criteria**
- [ ] A record triggered by two input situations appears **once**
- [ ] Order stable under shuffled input; no reliance on input order
- [ ] Explicit tests: multi-label merge · grader-before-non-grader · ladder order · id tie-break
- [ ] Type-group order documented with its reason
- [ ] Any fixture whose `ready` order contradicts the rule is reported, not accommodated

**Out of scope** Readiness, capability, conflicts, companions.

**Gotchas** Test against hand-built records, not the real registry, so the tests *state* the
ordering rules instead of depending on 73 files. Fixture 18 is the multi-label case.

````text
WHAT I WANT
evalloop/registry/query.py: match(records, situations) -> tuple[TechniqueRecord, ...].

WHAT IS IN THE TICKET
  - Selects every record whose triggers_on_situation intersects the input situations.
  - Multi-label input MERGES WITHOUT DUPLICATION: a record triggered by two of the input
    situations appears once.
  - Deterministic order, and this exact order, from AGENT.md §3.5 step 7: graders by
    ladder_priority ascending, then non-graders grouped by type, then id alphabetically
    within a group. Decide and document the order of the type groups themselves - it must be
    fixed, and it must be the same order the fixtures assert.
  - Pure function. No I/O, no mutation, no reliance on input order.

THE INPUT
  - CLAUDE.md §5 (query.py's signature) and AGENT.md §3.5 (the resolution order).
  - The 20 fixtures' ready lists - they assert order, so they are the specification for
    the tie-breaking rules.
  - Fixture 18 (api_endpoint + sql_generation) is the multi-label case.

THE RESULT I WANT TO SEE
1. match() implemented and unit-tested with HAND-BUILT records, not the real registry, so the
   tests state the ordering rules rather than depending on 73 files.
2. Explicit tests for: multi-label merge without duplication; stable order under shuffled
   input; grader-before-non-grader; ladder ordering; alphabetical id tie-break.
3. The type-group order documented in the module docstring, with the reason.
4. Report: whether any fixture's ready order is inconsistent with this ordering rule. If one
   is, STOP. Either the rule or the fixture is wrong, and I decide which.
````

---

### EL-121 — S21 Readiness

**Type:** Story · **Est:** 0.4 · **Depends:** EL-120 · **Blocks:** EL-122 ·
**Done when:** "needs X, have Y" reasons

**Why.** The reason string **is** the product here. `USER_EXPERIENCE.md §4.3`: every "no" has a
reason, in plain language.

**Files** → `evalloop/plan/readiness.py` (new) · tests

**Subtasks**
- [ ] `evaluate_readiness(record, evidence) -> Readiness(met, reason)`, pure, frozen result
- [ ] Empty `requires` → met; missing evidence → zero/absent
- [ ] Numeric vs **boolean** requirement handling, with chosen boolean wording documented
- [ ] Decide the multiple-unmet rule from the fixtures' `pending` strings
- [ ] Unit test per branch

**Acceptance criteria**
- [ ] Reason format exactly `"needs <key>: <threshold>, have <actual>"`
- [ ] Reason strings match ≥ 3 fixtures **character for character**, asserted in a test
- [ ] Branches tested: empty · numeric met · numeric unmet · missing key · boolean met ·
      boolean unmet · multiple unmet
- [ ] Report: boolean wording chosen · multiple-unmet rule chosen · any fixture string you
      couldn't reproduce without changing the fixture

**Out of scope** "Insufficient data" as a reason — that's a failure of this ticket.

**Gotchas** `requires_pre_instrumentation: true` can't be compared with `>=`, and
`"needs requires_pre_instrumentation: True, have 0"` is wrong. `EL-116`'s H records must read
correctly.

````text
WHAT I WANT
evalloop/plan/readiness.py: evaluate_readiness(record, evidence) -> Readiness(met: bool,
reason: str | None).

WHAT IS IN THE TICKET
  - Empty requires -> met. A record with no threshold fires at n=1.
  - Missing evidence counts as zero or absent, never as "assume satisfied".
  - Reason format, verbatim from AGENT.md §3.5: "needs <key>: <threshold>, have <actual>".
    The fixtures assert these strings, so the format is a contract, not a style choice.
  - BOOLEAN requirements are handled DISTINCTLY from numeric thresholds.
    requires_pre_instrumentation: true cannot be compared with >=, and rendering it as
    "needs requires_pre_instrumentation: True, have 0" is wrong. Decide the boolean reason
    wording, document it, and make EL-116's H records read correctly.
  - A record with several unmet requirements: decide whether the reason names the first, the
    worst, or all of them. The fixtures' pending strings decide this; read them first.

THE INPUT
  - AGENT.md §3.5's Readiness paragraph - the four rules and the reason format.
  - USER_EXPERIENCE.md §3.1 and §4.3 - PENDING always states why, in plain language. The
    reason string IS the product here; "insufficient data" is a failure of this ticket.
  - The 20 fixtures' pending maps - every expected string.
  - The requires mappings authored in EL-113 to EL-117.

THE RESULT I WANT TO SEE
1. readiness.py with a frozen Readiness result type and a pure function.
2. A unit test per branch: empty requires; numeric met; numeric unmet; missing key; boolean
   met; boolean unmet; multiple unmet.
3. Reason strings that match the fixtures character for character, and a test asserting that
   against at least three fixtures.
4. Report: the boolean wording you chose; the multiple-unmet rule you chose; any fixture
   whose pending string you could not reproduce without changing the fixture.
````

---

### EL-122 — S22 Capability, conflicts, companions

**Type:** Story · **Est:** 0.5 · **Depends:** EL-121 · **Blocks:** EL-123 ·
**Done when:** each one unit-tested

**Files** → `evalloop/plan/capability.py` (new) · `evalloop/plan/rules.py` (new) · tests

**Subtasks**
- [ ] `check_capability(record, available_tools) -> Capability(available, missing)`, `missing` ordered
- [ ] `apply_conflicts(ready)`: higher-priority grader suppresses a conflicting lower one
- [ ] Rule and document: two conflicting **non-graders** (fixture 13) — edge direction decides,
      not priority
- [ ] `resolve_companions(ready, records)`
- [ ] Rule and document: does an **unready** companion still enter `ready`, or make its parent
      pending?
- [ ] Unit tests on hand-built records

**Acceptance criteria**
- [ ] Three pure functions, individually tested
- [ ] Both rulings documented in the module docstring, each citing the corpus line that settles it
- [ ] Tests: missing-tool naming · grader suppressing grader · non-grader replacing non-grader ·
      companion pulled in · companion itself unready

**Out of scope** Assembling the `Plan` (`EL-123`). Answering the companion question from convenience.

**Gotchas** The companion question is **methodology**, answered from F and D: the corpus says a
judge score is never reported without length. A missing tool is never a silent skip — it becomes
a permission request (`AGENT.md §5`, `USER_EXPERIENCE.md §2`), so naming what's missing is this
function's job.

````text
WHAT I WANT
Three pure pieces: evalloop/plan/capability.py, and apply_conflicts() plus
resolve_companions() in evalloop/plan/rules.py.

WHAT IS IN THE TICKET
  - check_capability(record, available_tools) -> Capability(available: bool,
    missing: tuple[Tool, ...]). missing is ORDERED deterministically, because it is rendered.
    A missing tool is never a silent skip: AGENT.md §5 and USER_EXPERIENCE.md §2 both state
    it becomes a permission request. This function's job is to name what is missing so the
    session layer can ask.
  - apply_conflicts(ready): a higher-priority grader SUPPRESSES a conflicting lower one -
    execution suppresses judging the same property (EL-113's edge). Decide and document:
    what happens when two conflicting records have no ladder_priority (two non-graders, e.g.
    fixture 13's cluster bootstrap replacing plain bootstrap)? The corpus says one REPLACES
    the other, so the edge direction must decide it, not the priority. Make that explicit.
  - resolve_companions(ready, records): a ready record pulls in its companion_checks. Decide
    and document: does a companion that is itself unready get pulled into ready anyway (the
    corpus says a judge score is NEVER reported without length), or does it make the parent
    pending? This is a methodology question - answer it from F and D, not from convenience.

THE INPUT
  - AGENT.md §3.5 steps 3, 5 and 6 - capability, conflicts, companions, in the fixed order.
  - CLAUDE.md §6 - conflicts_with "record ids this replaces/invalidates", companion_checks
    "record ids that must be reported alongside".
  - D's violation-rate / over-refusal pairing and E3's length-bias pairing, as authored, for
    the companion semantics.
  - Fixtures 2, 5, 12, 13 and 17 - the capability, conflict and companion cases.

THE RESULT I WANT TO SEE
1. Three pure, individually unit-tested functions, using hand-built records.
2. A documented ruling on the two questions above, each citing the corpus line that settles
   it, in the module docstring.
3. Tests for: missing-tool naming; a grader suppressing a lower grader; a non-grader
   replacing a non-grader; a companion pulled in; a companion that is itself unready.
4. Report: whether any fixture requires conflict or companion behaviour these two functions
   cannot express.
````

---

### EL-123 — S23 Planner + `render()`

**Type:** Story · **Est:** 0.7 · **Depends:** EL-122 · **Blocks:** EL-124 ·
**Done when:** all 20 fixtures pass

**Files** → `evalloop/plan/planner.py` (new) · fixture runner test · rendered-plans artifact

**Subtasks**
- [ ] Frozen `Plan(ready, pending, unavailable, companions, prohibited)` + pure `plan(...)`
- [ ] The seven resolution steps, in order
- [ ] `render()` in the four-state shape, all states always visible
- [ ] Fixture runner reporting **which** fixture failed on **which** field
- [ ] The six `PLAN.md §5` sanity queries as explicit tests
- [ ] Print + save all 20 rendered plans for `EL-124`

**Acceptance criteria**
- [ ] All **20** fixtures pass, none edited
- [ ] Resolution order exactly: match → constraints → capability → readiness → conflicts →
      companions → order
- [ ] `render()` deterministic and diffable; every "no" carries its reason
- [ ] Six sanity queries asserted in prose terms
- [ ] 20 rendered plans saved as a reviewable artifact
- [ ] `pytest` exit 0 · `mypy --strict evalloop/` exit 0
- [ ] Report: every fixture you suspect is wrong (with the source line) + every surprising result

**Out of scope** Editing a fixture. Any I/O inside `plan()`.

**Gotchas** If a fixture fails, assume the planner is wrong **first**. If you conclude the
fixture is wrong, stop and flag it — `CLAUDE.md §7.4`. A surprise read now beats one at Gate 0.

````text
WHAT I WANT
evalloop/plan/planner.py: the frozen Plan dataclass, plan(...), and render(). All 20 fixtures
passing, and the 20 rendered plans printed for Gate 0.

WHAT IS IN THE TICKET
Signature and shape, from AGENT.md §3.5:
  plan(records, situations, available_tools, evidence) -> Plan
  Plan(ready: tuple[TechniqueRecord, ...],
       pending: Mapping[str, str],                  # id -> unmet-requirement reason
       unavailable: Mapping[str, tuple[Tool, ...]],  # id -> missing tools
       companions: Mapping[str, tuple[str, ...]],
       prohibited: tuple[str, ...])                 # constraint records that fired

Resolution order, FIXED and in this sequence - the order is the behaviour:
  1. match records whose triggers_on_situation intersects the input (multi-label, no dupes)
  2. apply CONSTRAINT records: anything they prohibit leaves ready and is listed in
     prohibited WITH THE REASON
  3. capability check -> unavailable (id -> missing tools)
  4. readiness check -> pending (id -> unmet-requirement reason)
  5. apply conflicts_with
  6. resolve companion_checks
  7. deterministic order

render() output shape, from TASKS.md S23 and USER_EXPERIENCE.md §3.1:
  READY        A1_execution_based - A3_deterministic
  PENDING      B3_mcnemar        needs discordant_pairs: 25, have 8
               C3_noise_floor    needs runs: 3, have 1
  UNAVAILABLE  H7_trajectory     missing: trace_capture
  PROHIBITED   accuracy          rare_class: "flag nothing" scores 99.8%
All four states always visible, even when empty. Every "no" carries its reason -
USER_EXPERIENCE.md §4.3. render() is deterministic and diffable; it is what a human reads at
Gate 0 and what the dashboard shows later.

THE INPUT
  - AGENT.md §3.5 - the signature, the Plan fields, the seven steps.
  - TASKS.md S23 and USER_EXPERIENCE.md §3.1 - the render shape and the four states.
  - PLAN.md §5 - the six sanity queries, which must behave.
  - The 20 fixtures. They are the specification. If one fails, assume the planner is wrong
    first; if you conclude the FIXTURE is wrong, STOP and flag it. Do not edit it.

THE RESULT I WANT TO SEE
1. planner.py with a frozen Plan and a pure plan(). No I/O inside it.
2. All 20 fixtures passing, with a single runner test that reports which fixture failed and
   on which field - not just an assertion error.
3. The six PLAN.md §5 sanity queries as explicit tests, each asserting the behaviour in
   prose terms (summarization pulls faithfulness with the length companion; code generation
   puts execution first and excludes or deprioritises judging; RAG orders recall before
   faithfulness; rare class has recall ready and accuracy prohibited; a single observation
   yields only facts; 200+ sample techniques are pending at low n).
4. All 20 rendered plans printed to stdout and saved as a reviewable artifact for EL-124.
5. pytest exit 0, mypy --strict evalloop/ exit 0.
6. Report: every fixture you suspect is wrong (with the source line that makes you suspect
   it), and every place the fixed resolution order produced a result you find surprising.
   I would rather read a surprise now than at Gate 0.
````

---

## Group 8 — The gate

### EL-124 — 🔒 Gate 0: human review of 20 plans

**Type:** Gate · **Est:** 0.5 · **Depends:** EL-123 · **Blocks:** E2 (M1) ·
**Done when:** every plan agreed

**Why.** `PLAN.md` is blunt: *nothing downstream matters if this is wrong.* The deliverable is a
document a human reads and either agrees with or sends back — not code.

**Files** → one review document (no code)

**Subtasks**
- [ ] Per fixture (20): name, given, verbatim `render()`, one line of plain-English
      justification + corpus citation
- [ ] "Things I would question if I were you" section
- [ ] `PLAN.md §5` definition-of-done checklist, ticked with command output
- [ ] Findings ledger consolidated from `EL-103` → `EL-123`
- [ ] One paragraph: does situation → technique matching work, and where is it weakest

**Acceptance criteria**
- [ ] Readable in one sitting
- [ ] Every justification cites the corpus section that makes the plan right
- [ ] Doubts stated as alternatives with supporting lines — not a defence
- [ ] DoD lines evidenced by command + output, not asserted
- [ ] Ledger covers: nulls and why · prose-interpreted thresholds (the human-review queue) ·
      unrepresentable rows/fields · vocabulary gaps · schema changes raised and how resolved
- [ ] **Human signs off on all 20 plans**

**Out of scope** Writing planner code. Changing a fixture. "Fixing" a plan you think the
reviewer will dislike.

**Gotchas** Gate 0 passing on a plan the reviewer didn't understand is worse than Gate 0 failing.

````text
WHAT I WANT
The Gate 0 review packet. This is not a code ticket: the deliverable is something I read and
either agree with or send back. PLAN.md is blunt about why - nothing downstream matters if
this is wrong.

WHAT IS IN THE TICKET
Gate 0: "Read the 20 generated plans. If you disagree with any, fix before proceeding."
M0's definition of done, from PLAN.md §5: pytest green, mypy --strict clean, 73 records load,
integrity empty, all 20 fixtures pass, the six sanity queries behave, and all 20 rendered
plans printed for human review. That review IS the gate.

THE RESULT I WANT TO SEE
A single markdown document I can read in one sitting, containing:
1. Per fixture (all 20): the name, the given (situations, tools, evidence), the full
   render() output verbatim, and ONE line of plain English saying what the plan claims and
   why that is methodologically right, citing the corpus section that makes it right.
2. A "things I would question if I were you" section: every plan where a defensible
   alternative exists, stated as the alternative and the line that would support it. I want
   your doubts, not a defence.
3. The M0 definition-of-done checklist from PLAN.md §5, each line ticked with the evidence
   (command and output) rather than an assertion.
4. The accumulated findings ledger from EL-103 to EL-123, in one table: every threshold left
   null and why; every threshold interpreted from prose (the human-review queue); every
   source row or field that could not be represented; every vocabulary gap; every schema
   change raised and how it was resolved.
5. A one-paragraph answer to M0's actual question: does situation -> technique matching work?
   Say where it is weakest. Gate 0 passing on a plan I did not understand is worse than
   Gate 0 failing.

DO NOT, in this session: write planner code, change a fixture, or "fix" a plan you think I
will dislike. Report it and let me rule.
````

---

## Tracking

| Key | Deliverable | Doc change in this ticket? | Blocks |
|---|---|---|---|
| EL-011 | `decisions/EL-011-sixth-column-mapping.md` | Yes — `CLAUDE.md §4`/§6, `TASKS.md:103` | EL-110 |
| EL-103 | `evalloop/vocab/situations.py` | Yes — `CLAUDE.md §5` (5 → 6 families) | EL-105 |
| EL-104 | `evalloop/vocab/tools.py`, `vocab/__init__.py` | No | EL-105 |
| EL-105 | `tests/test_vocab.py` | Yes — `TASKS.md` S5 | EL-106 |
| EL-106 | `evalloop/registry/format.py` | No | EL-107, EL-118 |
| EL-107 | `evalloop/registry/schema.py` | Yes — `TASKS.md` S7 (1-6 → 1-5) | EL-108 |
| EL-108 | `evalloop/registry/loader.py` | Yes — `CLAUDE.md` §5 `A_grading.*` → `.yaml`; new decision `EL-013` | EL-109 |
| EL-109 | `evalloop/registry/integrity.py` | No | EL-110 |
| EL-110 | `records/A_grading`, `B_comparison`, `C_statistics` — 20 | No | EL-111 |
| EL-111 | `records/D_rare_events`, `E_diagnostics`, `F_judge_trust` — 23 | No | EL-112 |
| EL-112 | `records/G_rag`, `H_agents`, `I_production`, `J_model_selection` — 30 | No | EL-113 |
| EL-113 | A + B enriched | Yes — `TASKS.md` S13 (drop rung 6) | EL-114 |
| EL-114 | C + D enriched | Yes — whichever of `TASKS.md`/`AGENT.md`/`CLAUDE.md` is wrong | EL-115 |
| EL-115 | E + F enriched | Yes — `TASKS.md` S15/T36 if the corpus disagrees | EL-116 |
| EL-116 | G + H enriched, build-order edges | No | EL-117 |
| EL-117 | I + J enriched, `source_ref` sweep test | No | EL-118 |
| EL-118 | Fixture format + fixtures 1–5 | No | EL-119 |
| EL-119 | Fixtures 6–20 | No | EL-120 |
| EL-120 | `evalloop/registry/query.py` | No | EL-121 |
| EL-121 | `evalloop/plan/readiness.py` | No | EL-122 |
| EL-122 | `evalloop/plan/capability.py`, `plan/rules.py` | No | EL-123 |
| EL-123 | `evalloop/plan/planner.py` + 20 rendered plans | No | EL-124 |
| EL-124 | Gate 0 review document | No | E2 (M1) |

## Open questions for the product owner

| # | Question | Blocks | Ticket |
|---|---|---|---|
| 1 | Sixth column: `domain_scenario` field, fold into `worked_example`, or deliberate drop? | EL-110 | EL-011 |
| 2 | `items_grouped` vs `grouped_items` — two situations or a typo? | EL-119 fixture 13 | EL-103 |
| 3 | Record format: minimal YAML subset or JSON, given one parser serves records *and* fixtures? | EL-118 | EL-106 |
| 4 | Fixture 11 says 60 labels gates a judge; corpus F1 says 150–200. Which gives? | Gate 0 | EL-115 / EL-119 |
| 5 | A7 tiered online scoring — does it get a `ladder_priority` at all? | — | EL-113 |
| 6 | Does an unready companion enter `ready`, or make its parent pending? | — | EL-122 |
| 7 | ~~One record per file, or one file per section?~~ **Closed:** one file per section, records keyed by id, `.yaml`, id not repeated in the body — decision `EL-013` | EL-110 | EL-108 |
