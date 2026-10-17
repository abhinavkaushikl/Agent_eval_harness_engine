# EL-213 — Evidence assembler (stage S41)

**⚠ Depends on Gate 0, and inherits F2 directly.** The stated dependencies, EL-201 and EL-203, are
done; but populating readiness is exactly what F2 is about, so this is the first code to confront
that open ruling, and it sits behind Gate 0. Built ahead of sign-off, like the other Group-2/3
work. §6 is the F2 finding, surfaced rather than routed around.

**Status: done.** `pytest` passes 1138 + 1 skipped on 3.12 (16 new tests; the skip is the
Linux-only sandbox memory test). `mypy --strict evalloop/` clean on 38 files. Standard library only.
Not re-run on 3.10 (no 3.10 interpreter here).

---

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/memory/evidence.py` | `assemble_evidence(store, run_id, session_facts) -> Mapping[str, object]`, plus `assemble_report` (the full accounting), `EvidenceReport`, `EvidenceItem`, `EvidenceGroup`, `Bar`, `SESSION_FACT_KEYS` |
| `evalloop/memory/__init__.py` | Re-exports |
| `tests/test_evidence.py` | 16 tests, the coverage test built from the registry at test time |

`assemble_evidence` returns only the keys M1 can honestly answer; `assemble_report` returns an
`EvidenceItem` for all 34 keys (present or absent, each with a reason), for the report and the
coverage test.

## 2. The grouping, checked against the records myself

I confirmed **34 distinct `requires` keys** and placed every one in exactly one group. The grouping
matches the ticket's five lists key-for-key:

| Group | Count | Keys |
|---|---|---|
| **countable** (metric store) | 4 | `runs`, `trials`, `failures`, `discordant_pairs` |
| **session fact** | 7 | `environment_resets_per_run`, `cluster_id_recorded`, `paired_ci_available`, `sample_size_stated`, `recall_at_k_measured`, `requires_pre_instrumentation`, `judgment_orders` |
| **store field absent** | 5 | `positives`, `attempts_per_category`, `candidates`, `smoke_items`, `benchmarks` |
| **process fact absent** | 3 | `pre_registration_filed`, `release_history_available`, `baseline_days` |
| **judge trust absent** (M4) | 15 | the κ, α, annotator and label-count bars |

**I agree with every placement.** One correction to the ticket, though: it says "six records carry
a boolean AND a numeric bound." It is **three** — `G3_faithfulness` (`recall_at_k_measured` +
`claim_labels`), `H3_pass_hat_k` and `H8_flaky_classification` (both `environment_resets_per_run` +
`trials`). The "17 records carry a boolean requirement" figure is right. The coverage test encodes
the group sizes (4/7/5/3/15 = 34), so this is checked, not asserted.

## 3. The eight results you asked for

| # | Result | How it is met |
|---|---|---|
| 1 | Counts the countable, never estimates | `runs`/`trials` = runs in the store; `failures` = failed cases in the named run; `discordant_pairs` from `diff_runs` when a comparison run is given. Every other key is absent — `test_only_the_countable_keys_are_produced_without_session_facts` proves the mapping is exactly `{runs, trials, failures}` with no defaults |
| 2 | Booleans and numerics distinct | `_KEY_PLAN` records each key's kind; a session fact of the wrong kind is **refused**, not coerced (tested three ways) |
| 3 | Coverage test from the registry **at test time** | `test_every_requires_key_is_accounted_for` rebuilds the key set from `load_records(...)` and asserts `set(_KEY_PLAN) == registry` and that each kind matches. A key added, removed or retyped in any record fails here — the mutation that drops one key fails it (verified) |
| 4 | Absent and zero read differently | A measured `failures: 0` is **present** with "counted 0…"; `positives` is **absent** with "absent: …". The distinction survives into the mapping: `failures` is there as `0`, `positives` is not (tested) |
| 5 | Round-trip, verbatim pending queue | Real evidence → `plan()` → `"needs runs: 5, have 1"` (C3), `"needs environment_resets_per_run: true, have false; trials: 5, have 1"` (H8), and `"needs failures: 100, have 3"` (I3) — AGENT.md §3.5's format, character for character |
| 6 | F2 classification per produced key | §6 |
| 7–8 | (not in this ticket's result list) | — |

**Mutation-checked.** Dropping a key from the plan fails the coverage test; estimating an absent
key as 0 fails the honest-state tests; feeding a boolean as a count fails the kind check.

## 4. The rule that matters most — absent, not zero

`evaluate_readiness` reads a missing key as unmet (never "assume satisfied"), so **absent is the
honest state and no key is ever given a plausible default.** A key is produced only when it is
counted from real data or stated as a session fact; otherwise it is left out of the mapping, and
`assemble_report` records *why*, naming the milestone that will answer it. I confirmed the count the
ticket asked me to: 34 distinct non-empty `requires` keys.

**One thing worth flagging about readiness's reasons:** `evaluate_readiness` renders an absent
numeric key and a measured `0` **identically** (`have 0`), because it coerces a missing key to 0
before rendering. So the absent/zero distinction is real in the *assembler's* accounting
(`EvidenceItem.present` and its reason), but it is **not visible in the planner's pending reason**.
That is a property of the readiness renderer, which this ticket must not change; I note it so the M3
pending-queue renderer (T27) can decide whether "absent" and "measured 0" should read differently to
the user.

## 5. `discordant_pairs` needs two candidates (an interpretation to check)

The ticket lists `discordant_pairs` as countable, but McNemar's discordant pairs are a disagreement
between **two** candidates, and the assembler is given one `run_id`. So I made it countable only when
a second run is supplied, via a keyword-only `comparison_run`, and **absent** otherwise — never
guessed at 0, which would be a false "we observed no disagreements". The keyword is additive and does
not change the stated `(store, run_id, session_facts)` signature. If you intended `discordant_pairs`
to come from somewhere else, this is the interpretation to correct.

## 6. F2 — the finding this is the first code to hit

Classifying the produced keys forced a **third** kind of bar into the open, which is the finding, not
a routing-around:

| Bar | Produced keys |
|---|---|
| **evidence** ("enough evidence yet") | `runs`, `trials`, `failures`, `discordant_pairs`, `judgment_orders` |
| **precondition** (neither — a methodological precondition that must hold) | `environment_resets_per_run`, `cluster_id_recorded`, `paired_ci_available`, `sample_size_stated`, `recall_at_k_measured`, `requires_pre_instrumentation` |
| **trust** ("trustworthy enough to use") | **none that M1 produces** |

**Every "trust" bar is a judge-kappa / agreement key, and all of them are absent (M4).** So among
the keys M1 can answer, F2's two-way split does not even arise: the numerics are evidence bars and
the boolean session facts are preconditions. The trust bars live entirely in the unanswerable set.

This says something useful for the ruling: F2's "trustworthy enough to use" meaning is **separable
from readiness entirely** in M1 — it never touches a key M1 produces. And `recall_at_k_measured`
shows the overlap with F8: it encodes G's build order (recall before faithfulness) *as a readiness
precondition*, so if F8 moves that ordering to `unlocks`, this key's reason for existing changes.
I did not act on either; this is evidence for the rulings.

## 7. Calls I made — please check

1. **`runs` and `trials` both count runs in the store** (one trial per run). The corpus uses two
   words; at the session granularity the planner consumes, they measure the same repeat count. "One
   trial = one run that contains the case" is per-case, but `plan()` takes a flat mapping with no
   case dimension, so I count at run granularity and say so in the reason.
2. **`failures` is counted in the named run**, not cumulatively across the store, so a reused result
   is not double-counted. If you want accumulation across runs, that is a one-line change and a
   dedupe by case key.
3. **`session_facts` may carry only the 7 session keys.** A countable key or an unanswerable key
   passed there is refused — hand-feeding `positives` or overriding `runs` is exactly the dishonesty
   the ticket targets, so it raises rather than silently accepting.
4. **Milestones on absent keys are my best mapping** (store v2 / M3 / M4 / Track V), from which
   record uses each key. Correct any you read differently.

## 8. Scope held
I did not change the planner, any record, `requires`, or `evaluate_readiness`; I did not build the
M3 pending-queue renderer (T27); and I produced no judge-trust key (all M4, all absent).

## 9. Warnings touched (M0 preamble)
- **#1 (Gate 0):** depended on; flagged at the top.
- **#2 (F2):** this is the first code to confront it — §6 is the finding.
- **#3 (F8):** `recall_at_k_measured` is the one key where F2 and F8 overlap — §6.
- **#6 (six dead situations):** not relevant — those situations reach no record, so no `requires`.
- **#7 (EL-014):** `failures` counts `Verdict.failed`, which now includes timeouts (EL-014) — correct by construction, since the store already applies EL-014.

## 10. Rulings I need
1. **Accept building ahead of Gate 0** (as for EL-201/204/205).
2. **`discordant_pairs` via `comparison_run`** (§5) — confirm or redirect.
3. **F2 (§6):** the produced keys are evidence + precondition, never trust. Does the ruling want a
   `Bar`-like field made explicit on the record (schema), or is classifying at the producer enough?
4. **Should "absent" and "measured 0" read differently in the pending queue** (§4)? That is T27's,
   but the data to tell them apart now exists on `EvidenceItem`.
