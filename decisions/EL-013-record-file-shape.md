# EL-013 — Record file shape: one file per section, records keyed by id

## Decision

A record file holds **many records: one file per section, ten files for ten sections**, and
this holds for all 73 records. A record file is a block map whose top-level keys are record
ids, and the id is **not** repeated as a field inside the body:

```yaml
A1_execution_based:
  section: A
  name: Execution-based grading
  ...
A2_end_state_verification:
  ...
```

The extension is `.yaml` (`loader.RECORD_SUFFIX`), which resolves the `A_grading.*` in
`CLAUDE.md` section 5 now that `EL-106` has chosen the format. Files with any other
extension in `evalloop/registry/records/` are not read.

## Status

Accepted — 2026-10-07. Closes open question 7.

## Context

`CLAUDE.md` section 5 names the layout as `records/A_grading.*` through
`records/J_model_selection.*`, and `TASKS.md` S10 names three of those files directly
(`A_grading`, `B_comparison`, `C_statistics`). Both read as one file per section, but
neither says so, and neither says how several records share one file given that
`format.load()` takes one document and rejects the `---` multi-document marker. `EL-108`
had to answer it, because the loader's iteration shape depends on it, and `EL-110` onward
cannot author a single record until it is answered.

73 records are authored by hand over six stages (S10–S12 skeleton, S13–S15 enrichment).
The shape is therefore chosen for the authoring and reviewing experience across those six
stages, not for the loader, which is indifferent — `_load_file()` is nine lines either way.

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **A. One file per section, records keyed by id** ✅ | A parse error costs a whole section's records in that run | Agrees with the published layout; cross-record fields are visible in one buffer; duplicate ids inside a section are caught by the format parser for free; ten reviewable diffs | Chosen. |
| B. One record per file (73 files) | 73 files, 73 diffs | A record is greppable by filename; a parse error costs one record; no merge conflicts between two authors in one section | Contradicts `CLAUDE.md` section 5 and `TASKS.md` S10 for a convenience, which is a decision ticket in its own right. And it hides the thing most likely to be wrong — see "Why many per file" below. |
| C. One file per section, wrapped in a `records:` key | One extra indent level on all 73 | A file could carry section-level metadata beside its records | Nothing wants section-level metadata. Section A's own ladder is a property of the records, not the file, and `source_ref` already cites the corpus. An indent level that buys nothing costs 73 records' readability. |
| D. One file per section, repeating `id` inside each body | A redundant field on all 73 | A record body is self-describing when copied out of its file | Two spellings of one id that can disagree, which is the silent-mismatch failure mode `CLAUDE.md` section 4 and section 6 both single out. The loader **rejects** a body carrying `id` rather than reconciling the two. |

## Why many per file

The deciding argument is not file count. It is that **the fields most likely to be wrong
are the ones that have to agree across records in the same section**, and option A puts
exactly those in one buffer:

- `ladder_priority` in section A is not a per-record property, it is an *ordering* of A1–A6.
  Authoring it one file at a time means holding five numbers in your head.
- `conflicts_with` in A, C and D points sideways within a section ("if there is any way to
  execute, execute" — `TASKS.md` S13).
- `companion_checks` chains run within a section before they run across sections.
- `source_ref` repeats one filename down the whole file, so a drifted citation is visible
  as an odd line rather than invisible in a file of its own. A wrong `source_ref` is the
  defect `CLAUDE.md` section 3's "never invent a number" rule cannot catch, because the
  number is real and the citation is not.

And one failure mode is caught for nothing: **duplicate ids inside a section are a parse
error**, because `format.py` rejects duplicate keys. That is the likeliest authoring typo
of all — copy a record, forget to rename it — and under option A it fails before the schema
or integrity checker ever runs. Under option B the filesystem catches only an exact
filename collision, and `B3_mcnemar.yaml` holding `id: B3_mcnemars` passes until `EL-109`.

## Consequences

**Easy:** `EL-110` onward author one file per stage-section. Reviewing S10 is three file
diffs. `check_integrity()` over `records/` reads ten files.

**Harder, accepted rather than mitigated:**

- A parse error in one file costs that whole section's records *for that run*. Mitigated
  only partly, and deliberately: `loader._load_file()` reports the parse error with its
  line number and moves to the next file, so one broken section never hides the other
  nine. It does not attempt partial recovery inside a broken file — a half-parsed record
  is worse than an absent one.
- Two people authoring the same section conflict in one file. That is branch hygiene, not
  a format problem, and the stages in `TASKS.md` are sequential and single-author.
- A record is not greppable by filename. `grep -rn 'B3_mcnemar' evalloop/registry/records/`
  finds it, and the id prefix names the file.

**Forecloses:** nothing. A later move to one record per file would be a mechanical split,
and the loader would need one line changed (iterate files, not keys). The reverse — merging
73 files — is the same mechanical work. Neither direction is locked.

## Evidence

- `CLAUDE.md` section 5: `records/   A_grading.*, B_comparison.*, … J_model_selection.*`.
- `TASKS.md` S10: "into `evalloop/registry/records/` (`A_grading`, `B_comparison`,
  `C_statistics`). ~20 records" — three files, twenty records.
- `evalloop/registry/format.py`: block maps nest to any depth, so ids-as-keys is inside the
  subset with no new construct; duplicate keys raise `FormatError`; `---` is rejected, so
  multi-document files were never an option.
- `tests/fixtures/registry/good/A_grading.yaml` holds two records, declared out of id
  order, which is what `test_records_come_back_sorted_by_id` uses to prove the sort.

## Follow-up

**Unblocks:** `EL-110` to `EL-117` (`TASKS.md` S10–S15) — author ten files under
`evalloop/registry/records/`, named `<LETTER>_<slug>.yaml`, each a block map of record ids.

**Code and doc changes made by this ticket:**
- `evalloop/registry/loader.py` (new): `RECORD_SUFFIX`, `BODY_FIELDS`, and the module
  docstring stating this decision.
- `tests/fixtures/registry/{good,broken}/` (new): the shape, exercised both ways.
- `CLAUDE.md` section 5: `A_grading.*` → `A_grading.yaml`.
- `TASKS.md` S8, S10 and the next-action line.
- `E1-M0-TICKETS-AND-PROMPTS.md`: EL-108 status, open question 7 closed.

**Open, and deliberately not closed here:** whether `evalloop/registry/records/` should
also carry a non-record file (a README stating the ten filenames, say). The loader reads
only `*.yaml`, so such a file is already harmless, but nothing needs it yet.
