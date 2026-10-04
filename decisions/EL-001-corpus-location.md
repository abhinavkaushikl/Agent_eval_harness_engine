# EL-001 — Corpus location and file names

## Decision

The in-repo `knowledge rules/` directory is the canonical methodology corpus, referred to everywhere by its real filenames, and a missing or misnamed corpus file fails the test suite instead of skipping it.

## Status

Accepted — 2026-10-04.

## Context

`CLAUDE.md` §4 described a corpus that does not exist. It claimed a master lookup at `$EVALLOOP_CORPUS/Evals-Situation-to-Technique.md` and ten deep dives under a `files (3)/` subdirectory with Title-Case names (`CLAUDE.md:59-71`, pre-change). The real corpus is committed to this repository in one flat directory, with lowercase names after the section letter, no subdirectory, and a different title for section C.

Three mismatches, each sufficient on its own to make a corpus read return nothing:

| CLAUDE.md claimed | Reality |
|---|---|
| `$EVALLOOP_CORPUS` default `~/Downloads` | corpus is in the repo at `knowledge rules/` |
| `files (3)/` subdirectory | one flat directory |
| `Evals-Situation-to-Technique.md`, `C-Is-The-Result-Real.md` | `evals-situation-to-technique.md`, `C-deciding-whether-a-result-is-real.md` |

The cost of leaving this was not hypothetical. `tests/conftest.py:13` hardcoded `MASTER_LOOKUP = "Evals-Situation-to-Technique.md"` and `tests/conftest.py:18` defaulted `corpus_dir` to `~/Downloads`. `tests/test_corpus.py` skipped when that file was absent. It was always absent, so the only corpus test in the suite had never asserted anything — it reported `1 passed, 1 skipped` while silently verifying nothing. Every corpus-reading stage from EL-103 onward would have read an empty directory and, under the old skip-based test, reported success.

`TASKS.md` compounded it by fixing the `source_ref` convention to filenames that do not exist, so every record authored by EL-113 onward would have cited an unresolvable source.

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **Make `knowledge rules/` canonical (chosen)** | Corpus is versioned with the code; a prose edit shows up as a code diff and lands in review | Zero-setup clone-and-test; corpus and extraction code cannot drift apart; CI needs no fixture provisioning | — |
| Keep the corpus external, fix the names | Every contributor and CI job must provision the corpus out of band | Keeps prose edits out of code diffs | Nothing guarantees the external copy matches what the records were extracted from. Reintroduces the silent-skip failure as the normal state for anyone who hasn't set the var |
| Move the corpus out to a git submodule | Submodule tooling, a second repo, pinned-SHA churn | Versioned *and* separable | Disproportionate for 12 Markdown files that change rarely; adds a clone step that breaks the same way `~/Downloads` did |
| Copy the corpus into `evalloop/` as package data | Ships ~290 KB of prose in the wheel | Importable at runtime | M0 shipped code does not read the corpus; extraction is an authoring-time activity. Would bloat the package for no runtime gain |

## Consequences

**What it costs to keep the corpus in the repo.** The corpus is now versioned with the code. A methodology edit is a code diff: it shows up in `git log`, goes through review, triggers CI, and inflates the diffstat of any PR that touches both prose and extraction logic. A non-engineer editing the methodology must now use git. The repo carries ~290 KB of prose forever, and the corpus cannot be versioned independently of the code or shared across repos without copying.

**What leaving it external would have cost instead.** Every clone and every CI job needs a provisioning step, and when it is missing the suite does not fail — it skips, which is how this defect survived. There is no guarantee that one developer's corpus matches the one the records were extracted from, and `source_ref` becomes unverifiable.

The costs are not symmetric. In-repo costs noisier diffs; external costs correctness, and already did.

**Made easy.** Clone and `pytest` with no setup. `source_ref` strings resolve against a file in the tree. A corpus rename breaks the build immediately, naming the file.

**Made hard.** Editing the methodology without touching the repo. Sharing one corpus across several repos.

**Foreclosed.** Nothing permanently: `EVALLOOP_CORPUS` still overrides the directory (`tests/conftest.py:111-116`), so an external corpus remains usable for a one-off, and an override that points at an incomplete corpus skips rather than fails, naming the missing file and the directory searched.

## Evidence

- `ls "knowledge rules/"` returns exactly 12 files: `00-INDEX.md`, `A-choosing-how-to-grade.md`, `B-comparing-two-things.md`, `C-deciding-whether-a-result-is-real.md`, `D-rare-events.md`, `E-when-a-number-looks-wrong.md`, `F-trusting-your-grader.md`, `G-rag-systems.md`, `H-agents.md`, `I-production.md`, `J-choosing-a-model.md`, `evals-situation-to-technique.md`.
- `CLAUDE.md:59-71` (pre-change) listed `$EVALLOOP_CORPUS/files (3)/...` with Title-Case names; verbatim: `$EVALLOOP_CORPUS/files (3)/C-Is-The-Result-Real.md`. No such file or directory exists.
- `tests/conftest.py:13` (pre-change): `MASTER_LOOKUP = "Evals-Situation-to-Technique.md"` — wrong case.
- `tests/conftest.py:18` (pre-change): `return Path(os.environ.get("EVALLOOP_CORPUS", "~/Downloads")).expanduser()`.
- **Confirmed:** `~/Downloads` contains neither the master lookup nor a `files (3)` directory. Baseline run, before any change: `SKIPPED [1] tests/test_corpus.py:11: corpus not found: /Users/abhinav/Downloads/Evals-Situation-to-Technique.md does not exist` — `1 passed, 1 skipped`. The assertion `"## A. CHOOSING HOW TO GRADE" in text` had never executed.
- `TASKS.md:103` (pre-change): `source_ref` → `Evals-Situation-to-Technique.md § <letter>`; `TASKS.md:123` (pre-change): `e.g. A-Choosing-How-To-Grade.md § A1`. Both name non-existent files.
- Header forms verified against the files: the master lookup uses `## A. CHOOSING HOW TO GRADE` (`evals-situation-to-technique.md:9`) and each deep dive uses `# SECTION A – CHOOSING HOW TO GRADE` (`A-choosing-how-to-grade.md:1`) with an en dash (U+2013, bytes `e2 80 93`, confirmed by hexdump). The ten section titles are identical between the two forms, so one `SECTION_TITLES` mapping generates both.

## Follow-up

**Unblocks:** EL-103 (corpus reading) and EL-113 (enrichment, which now cites filenames that resolve).

**Code and doc changes made by this ticket:**

- `tests/conftest.py` — now the single source of truth for corpus filenames: `MASTER_LOOKUP`, `INDEX_FILE`, `SECTION_FILES` (letter → filename), `SECTION_TITLES`, `CORPUS_FILES`. `corpus_dir` defaults to `REPO_ROOT / "knowledge rules"`, computed from `Path(__file__)`, with no absolute user path; `EVALLOOP_CORPUS` still overrides. `require_corpus_files()` fails loudly under the default and skips only under an override.
- `tests/test_corpus.py` — asserts the section header of all ten deep dives plus all ten master-lookup headers, plus the index, plus corpus completeness.
- `CLAUDE.md` §3 (Paths row), §4 (rewritten to the real layout), §8 (commands).
- `TASKS.md` — S2 description, and the `source_ref` convention for S10–S12 and the enrichment stages.
- `README.md`, `DEVELOPMENT_PLAN.md` (EL-001 marked decided).
- `AGENT.md` §3.5 — states where `records` come from: the corpus is read at authoring time, not at runtime; the agent loads records from `evalloop/registry/records/`, and each `source_ref` resolves into `knowledge rules/`. §5 gains a matching non-negotiable: a `source_ref` that does not resolve is an invented number with extra steps.
- `ARCHITECTURE.md` §11 — open question 2 ("Corpus location") closed, pointing here.

**Raised, not resolved here (per `CLAUDE.md` §7.5, raise schema problems rather than work around them):** the master lookup's table has **six** columns — `Situation | Use | What it technically is | Why this one | Example | Real-world domain scenario` (`evals-situation-to-technique.md:11`). `CLAUDE.md` §4 and the `TASKS.md:103` field mapping both describe only five; `Real-world domain scenario` has no destination field in `TechniqueRecord`. This is a field-mapping decision, not a path decision, so EL-001 does not settle it. It needs an answer before T3 extraction, or ~70 records will silently drop a populated source column. Options: a new `domain_scenario` field, fold it into `worked_example`, or record deliberately dropping it.

**Not changed, deliberately:** `E0-DECISION-PROMPTS.md` and the `DEVELOPMENT_PLAN.md` ticket register still quote the old names. They are the record of why this ticket existed; rewriting them would erase the problem statement. See the grep note in the report.
