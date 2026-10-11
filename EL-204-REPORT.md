# EL-204 — Classifier heuristics (stage S33)

**⚠ Depends on Gate 0, which is not signed off.** I built it ahead of the gate, as EL-201 was.
None of the five asks in `GATE0-REVIEW-PACKET.md` §5 changes what a classifier emits. F2, F8,
fixtures 11/14/20, `PLAN.md` §5 and the interpreted thresholds all concern what the planner does
*with* a situation. The one classifier-facing item, the six dead situations, is handled here (§4).

**Status: done.** `pytest` passes 1026 tests (40 new) on 3.12. `mypy --strict evalloop/` is clean
on 31 files, pinned to 3.10. Standard library only. **Not re-run on 3.10:** no 3.10 interpreter
is on this machine. The module uses nothing newer than 3.9 (`ast.unparse`).

---

## 1. What exists

| File | Contents |
|---|---|
| `tests/fixtures/classify/01…10_*.py` | The ten samples, **written before the classifier**. Each first line reads `# expect: <labels or abstain:kind> -- <why>` |
| `evalloop/classify/heuristics.py` | `classify_file`, `classify_source`, `ClassifierResult`, `Finding`, `Abstention`, and the `EMITTABLE` / `WITHHELD` / `UNDETECTED` sets |
| `evalloop/classify/__init__.py` | Re-exports |
| `tests/test_classifier.py` | 40 tests. The fixture test reads each `# expect:` line as the specification |
| `tests/conftest.py` | `CLASSIFY_FIXTURES_DIR`, declared once alongside the other fixture trees |

`ClassifierResult.labels` is the ticket's `tuple[tuple[Situation, float], ...]`. Each `Finding`
also carries its reasoning, because `EpisodicStore.record_classification` refuses a label without
one. An abstention's `reason` maps directly onto that method's `abstention=` argument.

## 2. The ten samples

All ten matched on the first run. **No fixture was edited.**

| Sample | Expected | Exercises |
|---|---|---|
| 01 plain function | `code_generation` | the fallback label for a unit with no specific signal |
| 02 Flask routes | `api_endpoint` | `@app.get("/…")` / `@app.post` |
| 03 SQL builder | `sql_generation` | an upper-case `SELECT … FROM` literal |
| 04 FastAPI route + SQL | `api_endpoint`, `sql_generation` | **multi-label** (fixture 18's pair); a route's pydantic return is *not* an extraction; lower-case SQL corroborated by `.execute()` |
| 05 pydantic return | `structured_extraction` | `BaseModel` schema |
| 06 TypedDict return | `structured_extraction` | `TypedDict` schema |
| 07 half-written | abstain: `syntax_error` | unclassifiable, not misclassified |
| 08 stubs only | abstain: `no_gradeable_unit` | `…`, `pass`, `raise NotImplementedError` and docstrings are not code |
| 09 torch loop | abstain: `dead_end` | `model_training` is detected and refused (§4) |
| 10 mixed module | `code_generation` 0.75, `sql_generation` 0.25 | confidence and ordering; docstring SQL and the lower-case English "update … delete from …" are ignored |

## 3. The seven requirements

| # | Requirement | How it is met |
|---|---|---|
| 1 | Ten hand-written samples, each with a reason | As above. The test asserts there are exactly ten, and that each has an `# expect:` line with a `--` reason |
| 2 | `ast` only; a parse failure is unclassifiable | No `re` import, and a test scans the source for one. `SyntaxError`, 3.10's NUL-byte `ValueError`, and `RecursionError` all abstain as `syntax_error` |
| 3 | Multi-label | Sample 04 gives `api_endpoint` 1.0 and `sql_generation` 1.0. Sample 10 gives two labels with different confidences |
| 4 | Confidence reproducible and documented, not a constant per branch | One formula for every label: **units carrying the signal ÷ gradeable units**. See §5.1 |
| 5 | Abstain with a reason, never a default label | Five kinds, each with a sentence: `not_python`, `unreadable`, `syntax_error`, `dead_end`, `no_gradeable_unit`. `ClassifierResult` refuses to exist with both labels and an abstention, with neither, or with a blank reason |
| 6 | Deterministic | Each sample is classified twice, and once from `str` instead of bytes: the results are equal. Ties break by `Situation` declaration order. Parse warnings are suppressed, so `-W error` cannot turn a valid file into a `syntax_error` (tested) |
| 7 | The six dead situations | **Refused, and said why.** §4 |

**Mutation-checked.** I removed four guarantees one at a time; each made the suite fail:
- route precedence over schema return (3 failures);
- the stub filter;
- the upper-case corroboration for SQL;
- training dead-end detection.

## 4. The six dead situations: refused, and the dead end is surfaced as an abstention

The classifier **never emits** any of the six. It handles them in two groups:

- **`model_training` and `data_pipeline` are detected** (`WITHHELD`), so the file can *abstain*
  with the dead end named. Otherwise it would fall through to `code_generation` and get a
  confident A1 plan. A training file is one that imports a training framework **and** calls
  `.fit()` or `.backward()`; an import alone stays `code_generation` (tested). A pipeline file is
  one that imports an orchestrator.
- **`classification`, `phi_present`, `contamination_risk` and `distribution_mismatch` are not
  detected** (`UNDETECTED`). The first would need to know what the code's output means. The other
  three are properties of data, which a source file doesn't show.

**A test recomputes the dead set from the live registry** and requires it to equal `WITHHELD ∪
UNDETECTED`. It also requires every `EMITTABLE` member to reach a record. So once a record starts
covering, say, `model_training`, the suite fails here, and the refusal can be lifted on purpose
rather than by accident.

## 5. Calls I made — please check these

1. **Confidence is coverage, not probability.** "0.25 `sql_generation`" means a quarter of the
   file's units carry SQL. It does not mean "25% sure there is SQL": when the signal fires, the
   SQL is certainly there. A calibrated probability needs labelled files and an agreement study
   (section F), and none exist, so I would rather name the quantity than invent one that looks
   like a probability. **Consequence for the LLM-fallback ticket:** its "heuristics are unclear"
   trigger must not treat this number as certainty.
2. **The route takes precedence over the schema return.** A FastAPI handler returning a pydantic
   model is serialising a response, not extracting fields from free text. Labelling it
   `structured_extraction` would bring in A5 field scoring for an endpoint.
3. **`code_generation` means a unit with no specific signal**, not "any code". So a file of one
   route plus three helpers gets `api_endpoint` 0.25 and `code_generation` 0.75. Fixture 18's
   pair, with no `code_generation`, is the precedent.
4. **The parse grammar is the running interpreter's.** A file using syntax newer than the runtime
   abstains rather than being parsed under a pinned older grammar. The trade-off: the same file
   can abstain on 3.10 and classify on 3.12.
5. **Only `.py` is Python.** `.pyi` and `.pyw` abstain as `not_python`.

## 6. Known limits, written down rather than discovered later

- **Schema classes must be defined in the same file.** An extractor returning an imported
  `Invoice` falls back to `code_generation`.
- **A pydantic return is not always extraction.** A non-route factory such as
  `make_default() -> Settings` is labelled `structured_extraction`. Requiring a `str` parameter
  would narrow this, but the ticket's signal is the return type alone, so I left the rule as
  specified.
- **Django URLconfs, class-based views and `TypedDict("X", {...})` are not detected.**
- **SQL built from concatenated fragments** (`"SELECT " + cols + " FROM t"`) is not detected. Only
  single literals and f-strings are.

## 7. Something the classifier cannot fix

**Three of the four emittable labels reach the same single record.** `code_generation`,
`sql_generation` and `api_endpoint` all trigger only `A1_execution_based`, which S19-REPORT §4 and
fixture 18's header already point out. Telling them apart changes nothing in today's plan. The
distinctions that do change a plan are extraction versus non-extraction (A5 versus A1) and
abstention versus a dead end. That's where the conservatism above is spent. Until section A's
records separate these three, a correct `sql_generation` label buys no SQL-specific technique.

## 8. Rulings I need

1. **Accept or reject building ahead of Gate 0** (as for EL-201).
2. **Coverage as the meaning of confidence** (§5.1), before the LLM-fallback ticket reads it.
3. **Should `api_endpoint` / `sql_generation` reach more than A1?** That's a registry question (§7).
