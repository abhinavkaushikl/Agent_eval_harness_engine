# EL-015 — Where the grader's corpus numbers live: a `parameters` field on each record

## Decision

The numbers the corpus gives for running and judging a technique live on that technique's own
record, in a new required `TechniqueRecord` field, `parameters`. Each entry holds:

- the figure as the corpus prints it, and its unit;
- its role;
- a `source_ref`, and a verbatim quote that the S17 sweep verifies.

A setting the corpus names without a number holds `value: null` and names who supplies the value.

The ticket's five questions, plus the one it embeds about procedure steps, are answered below.

**1. One home: the record.** A grader is handed `TechniqueRecord`s by the plan (`Plan.ready`), so
it reads its numbers from the record it was given, with nothing else to load or keep in step.
The other three candidates, and a fifth, are weighed under Options considered.

**Is a procedure step configuration? Yes, if EvalLoop will execute it.** `role` records which kind
of number a step contributes:

| Role | Meaning | Examples |
|---|---|---|
| `setting` | Applied every time the technique runs | a tolerance, a cap, a pass threshold, a pattern |
| `audit` | How the technique checks itself | a sample size, a cadence |
| `bar` | A bound on a metric the technique produces. Past it, the result is not to be trusted, or a launch is blocked | the mutant, mismatch and false-negative limits below |

Some steps have no value to store:

- Prose-only steps carry no number, so there is nothing to home: A:34 "Freeze a snapshot" and
  A:110 "Use alias lists".
- Worked examples inside a procedure are illustrations, not values a grader applies: A:36's
  "₹5,000" and "23:59", and A:73's `share == 100`.

**A record's `parameters` is either `null` or complete.**

- `null` means the record has not been inventoried yet.
- A map is the record's whole inventory, and `{}` means the procedure states nothing.
- A partial map is not allowed, because it would read as complete.

M1 inventories the four records that M1 code, or this ticket, needs: **A1, A2, A3 and A5, 16
entries**. The other 69 records stay `null` until their first reader is built. A4, A6 and A7 alone
hold at least fifteen more figures (A:143–147, A:217–222, A:256–260).

**The ticket listed six lines; the same four records hold six more values a grader needs.**

- A:76 — the idempotency re-run share.
- A:109 — the IFSC pattern.
- A:112 — the audit cadence.
- A:183, all three in A5, the other record EL-208 implements:
  - "within ₹1";
  - "token-F1 ≥ 0.9";
  - "normalised to ISO".

A5's own extraction notes already call these "comparator settings, not readiness thresholds". They
went unlisted only because those notes never used the words "has no field". Left out, they would
have become exactly the literals this ticket exists to prevent.

The M1 inventory, as the implementing story will write it:

| Record | Name | Value | Unit | Role | Bound · metric | Verbatim quote | First reader |
|---|---|---|---|---|---|---|---|
| A1 | `float_tolerance` | `0.000001` | absolute | setting | max | "Use a float tolerance of 1e-6" | EL-207 |
| A1 | `rupee_rounding` | `"paisa"` | rounding | setting | — | "round ₹ amounts to the paisa" | EL-207 |
| A1 | `timeout` | `10` | second | setting | max | "Use a 10-second timeout" | EL-206 |
| A1 | `row_cap` | `null` · grant | row | setting | max | "and a row cap" | Track V |
| A1 | `max_mutant_pass_rate` | `5` | percent | bar | max · `mutant_pass_rate` | "If the mutant still passes more than 5% of the time, the fixtures aren't discriminating enough" | EL-207 |
| A2 | `idempotency_rerun_share` | `10` | percent | audit | — | "Re-run 10% of tasks twice" | M4 / Track V |
| A2 | `max_claim_state_mismatch_rate` | `2` | percent | bar | max · `claim_state_mismatch_rate` | "For customer-facing agents, a mismatch rate above 2% blocks launch" | M4 / Track V |
| A3 | `ifsc_pattern` | `'^[A-Z]{4}0[A-Z0-9]{6}$'` | regex | setting | — | "IFSC: \`^[A-Z]{4}0[A-Z0-9]{6}$\`" | EL-208 |
| A3 | `min_token_f1` | `0.8` | f1 | setting | min | "fix the threshold (F1 ≥ 0.8)" | EL-208 |
| A3 | `threshold_audit_size` | `50` | item | audit | — | "hand-audit the 50 items closest to it" | M3 |
| A3 | `false_negative_audit_cadence` | `"month"` | cadence | audit | — | "Audit the false negatives every month" | M3 |
| A3 | `false_negative_audit_size` | `50` | item | audit | — | "Sample 50 failures" | M3 |
| A3 | `max_false_negative_rate` | `10` | percent | bar | max · `normaliser_false_negative_rate` | "If more than 10% are actually correct, fix the normaliser" | M3 |
| A5 | `amount_tolerance` | `1` | rupee | setting | max | "Amounts get numeric match within ₹1" | EL-208 |
| A5 | `date_format` | `"ISO"` | format | setting | — | "Dates are normalised to ISO" | EL-208 |
| A5 | `min_name_token_f1` | `0.9` | f1 | setting | min | "Names get token-F1 ≥ 0.9" | EL-208 |

Figures are stored in the units the corpus prints them in: `5` percent, not `0.05`. A consumer
converts; the data never does. Bounds include their acceptable edge, and every quote in the table
reads that way: "more than 5%" fails only above 5, and "F1 ≥ 0.8" passes at 0.8.

**2. How a citation travels.** Each entry carries its own `source_ref`, in exactly the record format
(`'<file> § <subsection>'`), and a `quote`, copied verbatim from that subsection with emphasis
markers stripped, as M0 does for `rule_of_thumb`.

The S17 sweep (`tests/test_records.py:182`) is extended inside the same loop. For every entry it
checks three things:

1. The `source_ref` resolves exactly as a record's does: the file exists, and the `§` heading is in
   it.
2. The quote occurs in that subsection's text, from its heading to the next heading of the same
   level, once both sides have their emphasis markers stripped.
3. The value occurs in the quote:
   - a number must equal one of the quote's figures as parsed, so `0.000001` matches "1e-6" and
     `10` matches "10-second". **A figure is a number not attached to a letter.** The "1" in
     "F1" is not a figure; under a naive digit match, a wrong `min_token_f1` of `1` passes
     against "F1 ≥ 0.8" (checked). The sweep is therefore tested with wrong values as well as
     right ones;
   - a range must find both of its ends;
   - a string must be a substring;
   - a `null` passes only with `supplied_by: grant`.

No line numbers are stored. They drift with every corpus edit, while a subsection plus a verbatim
quote survives edits — which is why records already cite by `§`. Nothing in `evalloop/` reads
Markdown: the sweep is a test, as S17's is.

**3. The row cap's value comes from the user, and is `null` in the registry.** A:37 names a row cap
and gives no number, so the entry records that A1 uses one (`value: null`) and who supplies the
value (`supplied_by: grant`).

This is not an interpretation and not a choice. `decisions/EL-006-db-driver-policy.md:160` already
rules that "row/byte caps are … grant parameters owned by EL-302 and EL-305". The value arrives
with a database grant, and only SQL execution reads it — Track V, never M1.

**4. A:77's 2% lands on A2 now,** as `max_claim_state_mismatch_rate`:

- `role: bar`, bound `max`;
- `metric: claim_state_mismatch_rate`;
- `scope: "customer-facing agents"` — the corpus restricts the bar to them, and without the scope a
  consumer would apply it to every agent.

A2's `produces` gains `claim_state_mismatch_rate`, because the corpus asks for that metric by name:
"Track claim–state mismatch as its own metric" (A:77). In M4, the end-state grader finds the number
on the record it is handed. It is never homeless again.

**5. The schema change,** written out:

```python
class ParameterRole(StrEnum):   # evalloop._compat.StrEnum, value == lowercase name
    setting = "setting"
    audit = "audit"
    bar = "bar"

class Bound(StrEnum):
    min = "min"   # values at or above are acceptable
    max = "max"   # values at or below are acceptable

class Supplier(StrEnum):
    corpus = "corpus"   # copied from the corpus
    grant = "grant"     # named by the corpus with no number; supplied at grant time

@dataclass(frozen=True)
class Parameter:
    value: int | float | str | tuple[int | float, int | float] | None
    unit: str
    role: ParameterRole
    bound: Bound | None
    metric: str | None      # role bar only: a name in the record's own `produces`
    scope: str | None       # the corpus's condition, verbatim, or None when unconditional
    supplied_by: Supplier
    source_ref: str         # '<file> § <subsection>', as records cite
    quote: str              # verbatim from that subsection, emphasis markers stripped

# TechniqueRecord gains one field, between rule_of_thumb and source_ref (22 -> 23):
    parameters: Mapping[str, Parameter] | None
```

The loader enforces these rules, with errors aggregated as for every other field:

- every entry has all nine keys, with no defaults, as for records;
- `value` is `null` if and only if `supplied_by` is `grant`;
- a range has two numbers, the low one first;
- a `bar` has a `bound` and a `metric`, and that `metric` is in the same record's `produces`;
- `metric` is null for every other role;
- an `audit` has no `bound`;
- names are snake_case;
- the map is frozen with `MappingProxyType`, exactly as `requires` is.

These are all intra-record rules, so they belong in the schema, not `check_integrity()`.

**The cost of re-running the loader and the integrity checker over 73 records is nothing:**
11 ms a pass, measured. The cost is in authoring and review:

| What | Change |
|---|---|
| `schema.py` | three enums, `Parameter`, and the rules above |
| `loader.py` | builds `Parameter`s from the nested map |
| Ten record files | every field is required (`schema.py:5-9`), so all 73 records gain the line, 69 of them as `parameters: null`; A1, A2, A3 and A5 gain the 16 entries; three `produces` names are added |
| Eight hand-written registry fixture records | gain the field. The broken set's deliberate problems must still number thirteen: this is a schema change, not an edit made to pass a test |
| Tests | schema, loader errors, and the sweep extension |
| `CLAUDE.md` §6 | one row |

About 0.75 day in all. The change is plan-neutral: the planner reads neither `parameters` nor
`produces`, so the 20 fixtures and `GATE0-RENDERED-PLANS.md` do not move.

## Status

Accepted — 2026-10-09.

**It ends up where the ticket asked it not to stop: at a schema change.** The tempting answer, a
cited `evalloop/grade/config.py`, meets the ticket's floor — "ONLY if it carries citations and a
test that they resolve". It is still the wrong home, for reasons that show up the first time a
number arrives from outside section A; see option C.

**This decision gives F2 a home without ruling on F2.** F2 is the open Gate 0 finding that
`requires` holds both "enough evidence yet" and "trustworthy enough" bars, which is why plan 03 is
empty. Moving A4's κ bars out of `requires` and into A4's `parameters` with `role: bar` would
change plan 03, so that move belongs to Gate 0. What this decision does is turn that ruling, if
Gate 0 makes it, from a schema design into a data move.

## Context

Section A's procedures give numbers that are neither readiness thresholds nor a gate's
three-valued enum. M0 recorded them faithfully and could not place them:

- **A1's extraction notes:** "THREE NUMBERS FROM THIS RECORD HAVE NO FIELD … None is a readiness
  threshold, so none belongs in requires; all three are raised as schema findings in the S13
  report".
- **A3's notes:** "ONE NUMBER HAS NO FIELD: A:112".
- **A2's notes** left A:76 "in prose".
- **A5's notes** classified A:183's bounds as "comparator settings, not readiness thresholds, so
  requires stays empty".

S13 grouped the numbers into two findings:

- **F2:** "No field for a trust bar on a *produced* metric". It lists A:38, A:77, A:112, A:146,
  A:220, A:260, B:73 and B:248, and suggests `invalidated_when: Mapping[str, Threshold]`, "keyed by
  a name that appears in the record's own `produces`".
- **F3:** `requires` "cannot express a direction, a range, or two bounds on one metric". It
  suggests a `Threshold(op, low, high)`.

`GATE0-REVIEW-PACKET.md` §4.3 carries both forward as open.

M1 is the first code that needs the numbers:

- EL-206 needs A:37's timeout;
- EL-207 needs A:35 and A:38;
- EL-208 needs A:111, and — the ticket missed this — A:109 and A:183.

The rule they collide with is `AGENT.md:188`: "Every threshold traces to a `source_ref` that
resolves in `knowledge rules/` … An unresolvable citation is an invented number with extra steps."

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **A. A new required field, `parameters`, on `TechniqueRecord`** ✅ | One schema field (22 → 23). All 73 records and 8 fixture records touched, because every field is required. About 0.75 day | A grader reads its numbers off the record the plan hands it. One citation discipline and one sweep for every number in the system. F3 fixed for these entries by construction: `bound` gives direction, a tuple gives a range, two entries give two bounds. F2's bars get the home S13 asked for | It touches the registry while Gate 0 is reviewing it. That change is plan-neutral and can land after sign-off, which is when its first reader (EL-206) can start anyway. 69 records carry an explicit `null` backlog, which is the honest state, but visible noise |
| **B. A sibling file keyed by record id** (`evalloop/registry/parameters/A_grading.yaml`) | A second loader path, plus a cross-file integrity rule that every id exists | Leaves the reviewed schema and the 73 record files untouched | It splits a technique's codification across two files that can drift — the reason EL-011 rejected a sidecar for `domain_scenario`. Every grader must load and join a second registry, and can be handed a record whose parameters came from another version. And absence from the file cannot tell "none" from "not yet looked" without a convention the record field gets for free from `null` |
| **C. Frozen config in `evalloop/grade/config.py`, cited, with a resolution test** | One module and one test. The cheapest option, and `1e-6` is spelled natively | No registry change at all | It puts methodology in code, so a corpus figure changes through code review instead of extraction. It serves graders only: the bars outside section A that S13 and EL-203 listed (B:73 flip rate, B:248 width ratio, C:107 "about 2× the run-to-run SD") would each need a `stats/config.py` or a `honesty/config.py`, so "a seventh number in M4" has no obvious place. It is tied to record ids only by naming convention, and the S17 sweep cannot see it |
| **D. `requires`, with a documented second meaning** | No schema change | No new structure | **It breaks plans.** Run on fixture 1 with A1's tolerance and mutant bar in `requires`, the planner renders `PENDING  A1_execution_based  needs float_tolerance: 1e-06, have 0; mutant_pass_percent_max: 5, have 0` and nothing is ready. The upper bound reads as a floor (F3), and C1 vanishes with its host. It would also double down on F2, the finding Gate 0 is being asked to rule on |
| **E. Two fields: `parameters` for settings and `invalidated_when` for bars** (S13's F2 shape) | Two fields, two validation paths, two sweep branches | Bars kept physically apart from settings | The citation and verification machinery is identical for both, so splitting it doubles the code for no gain in checking. `role: bar` with a `metric` keeps S13's shape — a bar keyed to a produced metric — inside one field |

## Consequences

**Easy:**

- **One read path.** EL-206, EL-207 and EL-208 take every corpus number from `record.parameters` and
  none from a literal. From here on, a grader that hard-codes a corpus figure fails review.
- **F2 becomes a data move**, if Gate 0 rules the κ bars out of `requires`.
- **Homeless thresholds get a home.** The decision thresholds that EL-203's report found homeless,
  and the eight bars in S13's F2 table, each land on their own record when that record's first
  reader is built.
- **A seventh number in M4 has an obvious place:** the record it belongs to.

**Hard, and accepted:**

- **A 73-line diff in a registry under review.** It is plan-neutral, verified: the planner reads
  neither `parameters` nor `produces` (grep `evalloop/plan/` and `evalloop/registry/query.py`).
- **Three `produces` names are added:**
  - `mutant_pass_rate` (A1);
  - `claim_state_mismatch_rate` (A2);
  - `normaliser_false_negative_rate` (A3).

  The procedures compute these metrics but the records never declared them, and a bar must bound
  something the record produces.
- **The parser rejects exponent notation** (`format.py:99`; it calls `1e-6` an "ambiguous scalar").
  The value is therefore written `0.000001`: the same number, with the corpus's spelling kept in
  the quote. This is why the sweep compares values, not spellings.
- **A `scope` is text, not data.** No vocabulary distinguishes customer-facing agents, so A2's
  bar's consumer must implement and test that condition by hand.
- **The sandbox's own safety limits are not methodology,** so they are not here: CPU time, memory,
  file size and open files, which EL-206 enforces. No record's procedure states them. By the same
  logic as the row cap (EL-006:160), they are grant parameters of the sandbox capability:
  - `null` until granted;
  - never defaulted;
  - reported as unset when absent.

  Until the M2 capability broker exists, M1's sandbox enforces only what has a value.

**Forecloses:** corpus figures as module literals or per-package config files.

## Evidence

From the corpus, `A-choosing-how-to-grade.md`. Emphasis markers are kept here, where the source has
them:

- **A:35** — "2. **Compare results, not formatting.** … Use a float tolerance of 1e-6 and round ₹
  amounts to the paisa."
- **A:37** — "4. **Set resource limits.** Use a 10-second timeout and a row cap."
- **A:38** — "5. **Test your tests.** … If the mutant still passes more than 5% of the time, the
  fixtures aren't discriminating enough."
- **A:76** — "4. **Test idempotency.** Re-run 10% of tasks twice."
- **A:77** — "5. **Track claim–state mismatch as its own metric.** … For customer-facing agents,
  **a mismatch rate above 2% blocks launch**, whatever the success rate."
- **A:109** — "… exact match plus format validation (IFSC: `^[A-Z]{4}0[A-Z0-9]{6}$`)."
- **A:111** — "4. **For token-F1, fix the threshold (F1 ≥ 0.8) and hand-audit the 50 items closest
  to it.**"
- **A:112** — "5. **Audit the false negatives every month.** Sample 50 failures. If more than 10%
  are actually correct, fix the normaliser."
- **A:183** — "… Amounts get numeric match within ₹1. Dates are normalised to ISO. Names get
  token-F1 ≥ 0.9. …"

From the repo:

- **`evalloop/registry/schema.py:5-9`** — "Every field is required: there are no defaults, so a
  record file missing a field fails at construction instead of silently acquiring a value nobody
  wrote."
- **`evalloop/registry/format.py:99`** — `_FLOAT = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]+$")`.
  Decimal only; `load("x: 1e-6")` raises `FormatError` "ambiguous scalar".
- **`decisions/EL-006-db-driver-policy.md:160`** — "Statement timeouts and row/byte caps are
  deliberately left unnumbered: they are grant parameters owned by EL-302 and EL-305, and inventing
  values here would violate `CLAUDE.md:49`."
- **`tests/test_records.py:182`** — `test_every_source_ref_resolves_in_the_corpus`: file exists,
  subsection heading found (`_DEEP_DIVE_SUBSECTION`, `:142`). It checks no content.
- **`S13-REPORT.md` §5, findings F2 and F3** — quoted under Context.
- **`AGENT.md:188`** — "Every threshold traces to a `source_ref` that resolves in
  `knowledge rules/`".
- **Measured:**
  - `load_records` twice plus `check_integrity` once over 73 records: 22.3 ms, best of five;
  - registry fixtures: 3 records in `good/`, 5 in `broken/`;
  - option D's render on fixture 1, as quoted under Options.

**Interpretations, flagged for review:**

1. `"paisa"` is stored as a word, not as `0.01`. A paisa is ₹0.01 by definition; the consumer
   converts, so the data holds only what the corpus printed. The same goes for `"month"` and
   `"ISO"`.
2. The role of each of the 16 entries is this decision's classification.
3. Each bound's direction comes from the quote's wording.
4. Applying EL-006's grant rule, written for database connections, to A1's row cap.
5. Treating A:36's "₹5,000" and "23:59", and A:73's `share == 100`, as examples, not parameters.

## Follow-up

**Unblocks:** a story implementing this decision, of about 0.75 day. It should land **after Gate 0
sign-off and before EL-206**: it touches the registry, and EL-206 is its first reader. Then:

- **EL-206** reads `A1.timeout`;
- **EL-207** reads A1's other entries;
- **EL-208** reads A3's and A5's.

**Doc changes made by this ticket**, all in `E2-M1-TICKETS-AND-PROMPTS.md`:

- EL-015 is marked decided, with its implementation pending.
- EL-206's file list no longer names a `grade/config.py`.
- The prompts' "EL-015's config" now names the record's `parameters`.
- The tracking rows are filled in, and open question 4 is closed.

No other doc described a config home, so no other doc is stale.

**Not changed now, on purpose:** `CLAUDE.md` §6. The field does not exist until the implementing
story lands, and documenting it first would make §6 wrong in the other direction.

**Raised after this decision (2026-10-09), ruling pending.** The EL-203 audit found that
`evalloop/stats`, which was built before this decision, keeps five cited corpus defaults as module
constants:

- confidence 0.95 (C1);
- α 0.05 (C2, C5);
- 10,000 shuffles (C6);
- 5,000 resamples (B6);
- 25 discordant pairs (B3).

This decision's "Forecloses" line covers them. Two other kinds of constant in that module are out
of scope:

- **The formula constants — 16, 1.96, 0.84 and 3.** They *are* the corpus's printed formulas, not
  settings.
- **Its numerical constants.** They are not corpus figures at all.

The recommendation, in `EL-203-REPORT.md` §10, is to keep the library free of registry I/O. Once
those five records are inventoried, add one test per default asserting that it equals the record's
parameter — the pattern `test_the_planner_and_mcnemar_read_the_same_bound` already uses for B3.
The alternative is to make the five arguments required and have every caller pass the record's
value.
