# EL-011 — Sixth column: where `Real-world domain scenario` goes

## Decision

The master lookup's sixth column gets its own field, `domain_scenario: str | None`, copied verbatim at extraction time and read by no planner code.

## Status

Accepted — 2026-10-07.

The recommendation on the ticket (option A) is adopted, but **the reason given for it does not survive checking** and is not the reason recorded here. The ticket argues the column is "exactly the seed material M1's case author (T15) and the classifier's situation examples (T9) will need". It is not: `TASKS.md:305` specifies T15.1 as "Generate tests from signature only (isolated from implementation)", and isolation is the whole point of that subtask; `TASKS.md:264-265` specifies the T9 classifier as signal extractors over code ("imports, file type, function signatures, SQL strings, HTTP routes") feeding rules to `(Situation, confidence)`. Neither reads corpus prose, so neither is unblocked by storing this column.

What does justify the field is the asymmetry of the two mistakes, set out under Consequences: storing it costs one nullable field inside a pass that is already reading the row, and dropping it costs re-opening all 73 rows and re-editing every record file. A decision that is cheap to reverse in one direction and expensive in the other is made in the cheap direction.

## Context

`decisions/EL-001-corpus-location.md:74` raised this and explicitly refused to settle it, calling it "a field-mapping decision, not a path decision". The master lookup's header row is six columns (`evals-situation-to-technique.md:11`):

```
| Situation | Use | What it technically is | Why this one | Example | Real-world domain scenario |
```

Two docs describe five. `CLAUDE.md:84` lists "columns `Situation | Use | What it technically is | Why this one | Example`", and the `TASKS.md:103` field mapping maps exactly those five. `TechniqueRecord` (`CLAUDE.md:167-190`) has no destination for the sixth.

The repo already contradicts itself on this. `tests/test_corpus_shape.py:24` pins `EXPECTED_COLUMNS = 6` and `tests/test_corpus_shape.py:90` carried the comment "Six, not the five CLAUDE.md s4 describes -- see the open sixth-column question" (its wording before this ticket). So the test suite asserts the column exists while the schema has nowhere to put it, and the extraction stages (EL-110 → EL-112) are the point at which that contradiction gets resolved one way or the other — silently, if nobody rules.

The column is populated on **all 73 rows**, and uniformly: every cell matches `**<Domain>**: <scenario>`, across ten domain labels (E-commerce 12, Insurance 11, Fintech 10, Telecom 9, Healthcare 8, Legal 7, Logistics 6, HR 5, Banking 4, Content moderation 1).

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **A. New field `domain_scenario: str \| None`** *(chosen)* | One schema field; one more column copied per record during a pass already reading the row; `TechniqueRecord` goes from 20 fields to 21 | The whole source row is retained, so extraction completeness is checkable rather than assumed. Keeps `worked_example` narrow. Preserves material like A1's `**Fintech**: NL-to-SQL over a UPI transaction warehouse. For "total refunds above ₹5,000 in Q2", compare result sets on a frozen snapshot` (`:13`), which no other field in the schema can hold | Nothing in M0 reads it, so it is inert data for at least one milestone. Accepted: three fields already are (see Consequences) |
| **B. Fold into `worked_example`** | Nothing now | No schema change | Breaks two contracts at once. `CLAUDE.md:186` defines `worked_example` as "concrete figures from source — **must contain a digit**", and **26 of 73** scenarios contain a digit, so the digit rule would start passing on narrative text: I1's cell is `**Fintech**: an EMI calculator bot, where one must-pass is "₹5 lakh at 10.5% for 36 months = ₹16,251/month"` (`:128`), which satisfies the rule while carrying no measurement. It also breaks rendering: `TASKS.md:238` prints source prose inline on one PROHIBITED line, and scenarios run to 165 characters against a 96-character median `Example` |
| **C. Record a deliberate drop** | A test and a note | Cheapest; honest if nothing wants the column | The ticket's own standard — "defensible only if nothing downstream wants it" — is not met. `ARCHITECTURE.md:300` specifies a Teach mode where "Every verdict shows which technique fired, why it was chosen, and what the alternative would have missed", and this column is the corpus's only domain-grounded illustration of a technique in use: F9's cell is `**Content moderation**: Hinglish hate-speech labelling, where sarcasm and reclaimed slurs split annotators` (`:90`). That surface is marked *(proposed)*, so the case is suggestive rather than conclusive — which is why the decision rests on reversibility cost, not on this |
| **D. Sidecar file per section** (`records/A_domain_scenarios.*`) | A second file per section and a join on record id | Keeps `TechniqueRecord` at 20 fields | Splits one source row across two files, so the two can drift, and `check_integrity()` would have to police a join that exists for no reason but field-count tidiness |
| **E. Two fields: `domain` + `scenario`** | Two fields and a parse at extraction | A sliceable domain label | Invents structure the corpus does not commit to. The `**<Domain>**:` prefix is uniform on all 73 rows today, so a future ticket can derive a domain vocabulary from the stored strings deterministically, without re-reading the corpus. Storing verbatim keeps that option open at zero cost; splitting now closes it the wrong way |

## Consequences

**Easy.** Extraction becomes verifiable: with the column stored, `check_integrity()` can assert that every record sourced from the master lookup carries its scenario, which is the only mechanical check that extraction read the whole row. `worked_example` keeps its narrow contract, so the digit rule keeps meaning "this record carries a measurement" and `render()` keeps fitting on one line. If Teach mode (`ARCHITECTURE.md:300`) or `summary.md` (`USER_EXPERIENCE.md:75-80`) later wants domain-grounded prose, it is already in the records.

**Hard.** 73 records each carry one more hand-copied field, up to 165 characters. `TechniqueRecord` reaches 21 fields, which makes EL-107's dataclass and its `__post_init__` tests longer to read.

**What it forecloses: nothing in M0.** The field commits to *retaining* the column, not to using it. That is consistent with how the schema already works: `rule_of_thumb`, `extraction_notes` and (pending EL-123's render) `anti_pattern` are not read by any planner step in `TASKS.md` S20–S23 either. `TechniqueRecord` is a faithful transcription of a source row that the planner reads *parts* of, not a minimal planner input — the house rule that thresholds are "copied verbatim from the source or set to `null`" (`CLAUDE.md:49`) is the same instinct applied to numbers.

**What it does not create.** No `Domain` enum, no vocabulary member, no parse. Decision EL-002's standing rule — a vocabulary member needs a technique that requires it — is not met by a domain label, and EL-003 applied the same rule to reject three `Situation` candidates.

## Evidence

- `evals-situation-to-technique.md:11` — header row, verbatim: `| Situation | Use | What it technically is | Why this one | Example | Real-world domain scenario |`.
- Measured over the 73 technique rows (sections A–J, excluding the trailing cheat-sheet): **73/73** sixth cells non-empty; **73/73** match `**<Domain>**: `; **26/73** contain a digit; **73/73** `Example` cells contain a digit; longest sixth cell 165 characters against a 96-character median `Example`.
- Three cells quoted verbatim, beyond the three in the Options table:
  - `:14` — `**Insurance**: the policy-servicing agent says "nominee updated". Read the nominee field in the policy admin system`
  - `:17` — `**E-commerce**: GST invoice extraction. Validate the GSTIN against a 15-char regex and check HSN code, taxable value, and CGST/SGST vs IGST split`
  - `:46` — `**Logistics**: delivery-ETA error in minutes. A few 6-hour misses dominate the mean`
- `CLAUDE.md:186` — `| worked_example | str | concrete figures from source — **must contain a digit** |`.
- `CLAUDE.md:84` — the five-column description, corrected by this ticket.
- `TASKS.md:103` — the five-way field mapping, corrected by this ticket.
- `tests/test_corpus_shape.py:24-25` — `EXPECTED_COLUMNS = 6`, `EXPECTED_TOTAL = 73`; `:90` — the comment naming this open question.
- `decisions/EL-001-corpus-location.md:74` — "the master lookup's table has **six** columns … This is a field-mapping decision, not a path decision, so EL-001 does not settle it."
- `ARCHITECTURE.md:472` — "**Still open:** the master lookup has a sixth column … Needs its own decision before T3 extraction." Closed by this ticket.
- `ARCHITECTURE.md:300` — Teach mode, verbatim: "Every verdict shows which technique fired, why it was chosen, and what the alternative would have missed". Section 8.2 is headed "Three modes (proposed)", so this consumer is proposed, not committed.
- `TASKS.md:305` — T15.1, verbatim: "Generate tests from signature only (isolated from implementation)". `TASKS.md:264-265` — T9.1/T9.2, verbatim: "Signal extractors: imports, file type, function signatures, SQL strings, HTTP routes" → "Rules → `(Situation, confidence)` multi-label". **This is the evidence that contradicts the ticket's stated rationale**; neither subtask consumes corpus prose.
- Not found, and therefore not claimed: no reference to `worked_example`, `domain_scenario` or an equivalent anywhere in `AGENT.md`, `PLAN.md`, `DEVELOPMENT_PLAN.md` or `USER_EXPERIENCE.md`. `ARCHITECTURE.md:300` is the only downstream surface in the docs that would read this column.

## Follow-up

**Unblocks:** EL-110, and therefore all extraction (EL-110 → EL-112) and enrichment (EL-113 → EL-117).

**The exact change EL-107 (S7) makes, and nothing more:**

| | |
|---|---|
| Field name | `domain_scenario` |
| Type | `str \| None` |
| Default | **none — the field is explicitly passed.** Record authors write `domain_scenario=None` to omit it, because silence is the failure this decision exists to prevent. If EL-107 gives the other nullable fields defaults, this one is ordered with them, but it does not acquire a default that lets an extraction pass skip it unnoticed |
| Position | Immediately after `worked_example`, keeping the source-transcription fields together |
| `__post_init__` | **No rule.** No digit requirement, no non-empty requirement. The digit contract stays on `worked_example` alone, which is the point of option A over option B |

**EL-109 (S9 integrity) gains one rule**, which is what makes the nullability safe: every record whose `source_ref` resolves to a master-lookup row must carry a non-null, non-empty `domain_scenario`. All 73 rows are populated, so a null there means the extractor skipped a cell, not that the corpus is silent. Null stays legal in the type so that a record authored only from a deep dive is not forced to invent one.

**EL-110 → EL-112 (skeleton extraction)** fill `domain_scenario` alongside the other ten fields, **verbatim, including the `**<Domain>**:` prefix and without re-wrapping**. An extractor will be tempted to strip the bold or split off the domain; both are renderer concerns, and option E above is the reason not to do it at authoring time.

**Doc changes made by this ticket:**

- `CLAUDE.md:84` — the master-lookup column list now names all six columns.
- `CLAUDE.md` §6 field table — one row added for `domain_scenario`, after `worked_example`.
- `TASKS.md:101` — `domain_scenario` added to the fields the skeleton-extraction stages fill. Without this the field mapping alone would still leave EL-110 dropping the column, which is the failure this ticket exists to prevent.
- `TASKS.md:103` — the field mapping now maps `Real-world domain scenario` → `domain_scenario`, six columns in, six accounted for.
- `ARCHITECTURE.md:472` — the "Still open" sixth-column note closed, pointing here.
- `tests/test_corpus_shape.py:90` — the docstring pointing at "the open sixth-column question" now names `domain_scenario` and this decision. Comment only: no assertion changed, and `EXPECTED_COLUMNS = 6` was already correct. Context above quotes its prior wording.

**No schema code was written, and `evalloop/` is untouched.** Per the ticket, that is EL-107's work.

## Related

- `decisions/EL-001-corpus-location.md` — raised this and deferred it; corpus line numbers above are against that in-repo copy.
- `decisions/EL-002-mcp-tools-in-enum.md` — the standing rule that a vocabulary member needs a technique requiring it, applied here to reject a `Domain` enum.
- `decisions/EL-003-new-situations.md` — same rule applied to three `Situation` candidates.
