# EL-210 — Test author, signature-only (stage S40)

**⚠ Depends on Gate 0 transitively.** EL-210's stated dependencies, EL-209 and EL-205, are both
done; EL-205 depends on EL-204, which depends on Gate 0. So this sits behind Gate 0 by one hop, and
was built ahead of sign-off as EL-204/205 were. Nothing in Gate 0's open rulings changes how a test
is authored from a signature.

**Status: done.** `pytest` passes 1117 + 1 skipped on 3.12 (19 new author tests, plus 2 new sandbox
tests for the `input_files` extension; the skip is the Linux-only memory test). `mypy --strict
evalloop/` clean on 37 files. Standard library only. **The suite touches no network and needs no
credentials** (§3). Not re-run on 3.10 (no 3.10 interpreter here).

---

## 1. What exists

| File | Contents |
|---|---|
| `evalloop/grade/oracles/author.py` | `signature_view`, `render_messages`, `author_test`, and the value types `SignatureView`, `AuthoredOracle`, `AuthoringOutcome`, `Attempt`, plus `WHY_LOW` |
| `evalloop/grade/oracles/__init__.py` | Re-exports authored alongside harvested oracles |
| `evalloop/grade/sandbox.py` | **Extended** with `run_sandboxed(..., input_files=...)` — §6 |
| `tests/test_oracle_author.py` | 19 tests, offline against a fake transport |
| `tests/test_sandbox.py` | +2 tests for `input_files` |

## 2. The nine results you asked for

| # | Result | How it is met |
|---|---|---|
| 1 | Generate from signature/name/docstring/type-hints, via EL-209's router, job `author` | `author_test` builds a `SignatureView` with `ast`, renders messages from it, and calls `Router.complete(Job.author, ...)` |
| 2 | **A test that proves the body is not in the request** | `test_the_body_never_reaches_the_request`: a sentinel in the function body is absent from the view, from the rendered prompt, **and from the bytes actually sent**. §4 |
| 3 | Every oracle LOW, impossible to override | `AuthoredOracle.confidence` is a **property** returning `low`; there is no field. Setting it raises; a mutation flipping it to `high` fails the suite |
| 4 | The confidence reasoning recorded: why LOW, what makes it HIGH | `WHY_LOW`, stored on every oracle and asserted |
| 5 | Reject a test that does not run, or passes an empty stub | Validated in EL-206's sandbox against a `raise NotImplementedError` stub: pytest exit 0 → vacuous (reject), exit 5 / collection error → doesn't run (reject), exit 1 → has teeth (accept). All three tested |
| 6 | Catches a deliberately broken impl it never saw | `test_an_authored_test_catches_a_broken_implementation_it_never_saw`: the authored test passes a correct body, **fails a wrong body**, and fails the empty stub |
| 7 | `case_kind: generated`, never permanent | `AuthoredOracle.case_kind` is a property returning `generated`; a mutation to `permanent` fails the suite |
| 8 | Cost recorded; reproducibility or recorded variance | Each `Attempt` records the request, served model, jitter seed and cost; the session ledger accumulates. The API has no seed (EL-209), so determinism is only guaranteed against the fake transport — recorded, not hidden (§5) |
| 9 | No test touches the network | A fake in-process transport plus a socket guard; the suite runs with no credentials |

**Mutation-checked.** Four guarantees broken one at a time, each caught: LOW→HIGH, generated→permanent,
accepting a vacuous test, and leaking the body by sending the function's full source instead of its
docstring (11 failures — the isolation test and others).

## 3. The egress boundary — option (b), and warning #4 (fixture 20)

EL-210 is the authoring half of "the first code that can send a developer's artifact to a model".
It inherits EL-209's **option (b)**: the client refuses egress without a `Clearance`, and
**nothing in EvalLoop issues one**. This module **never constructs a `Clearance`** (a source scan
asserts it, and EL-209's own repo-wide scan still holds); it takes one from its caller and passes
it through. `test_authoring_fails_closed_without_a_clearance` proves that a transport which would
leave the machine, with no clearance, raises `EgressRefused` before any call. So in M1 the author
runs only against a fake transport — which is exactly why the suite is offline.

**It sends less than the harvester-vs-model risk implies:** only the signature, docstring and the
module's import lines — never the body. But that is still developer content, so the gate is the
same, and fixture 20's PHI ruling (M2's capability broker) will govern it when a real call is ever
made. Nothing here presumes that ruling.

## 4. Isolation is structural, not polite

The request is assembled by `render_messages(view)`, a pure function of a `SignatureView` whose
fields are the qualname, the signature text, the docstring and the module's imports — built by
`ast` **without ever reading the function's statements** (only `ast.get_docstring`, which is the
contract). So the body cannot reach the model whatever the prompt says. The proof is an assertion
over the assembled request, in three layers: the view carries no body, the rendered prompt carries
no body, and the bytes actually posted carry no body. The mutation that sends the function's full
source segment instead of its docstring is caught here.

## 5. EL-015, and determinism

- **No corpus number is hard-coded.** `author_test` takes `sandbox_limits: Limits` (whose
  `wall_seconds` bounds the validation run) and `max_output_tokens` as required arguments. Both are
  the caller's — from the record's `parameters` once EL-015 lands. **EL-015 is still unimplemented**
  (no `parameters` field), so M1 callers pass them explicitly, as for EL-206.
- **Reproducibility is as good as the API allows.** The Anthropic API has no seed (EL-209:
  `LLMResponse.seed` is always `None`), so two real generations of one signature can differ.
  Rather than hide that, each attempt records the exact request, the served model, the jitter seed
  and the cost, so variance can be measured by repetition (`ARCHITECTURE.md` §9). Against the fake
  transport the output is fixed and the suite is deterministic (tested).

## 6. The sandbox extension I made (please check)

EL-206's `run_sandboxed` created an empty workdir with no way to put files in it, but a grader must
place the code under test and its oracle *inside* the sandbox. I added
`run_sandboxed(..., input_files=Mapping[str, str])`: it writes each workdir-relative path before the
command runs, and refuses any path that is absolute, empty or escapes the workdir (tested, including
`a/../../b.py`). **EL-207 needs this too** for hidden-test isolation, so it belongs on the sandbox,
not in the author. It does not change any existing behaviour.

## 7. Calls I made — please check

1. **The generated test imports the function by the file stem** (`from pricing import total`), and
   validation writes the stub at `pricing.py`. When EL-207 grades the *real* artifact with this
   test, it must expose the real function under that import name. That handoff is EL-207/EL-214's;
   I recorded `import_module` on the oracle so it is explicit, not guessed.
2. **M1 authors for top-level functions only.** A method (`C.m`) is refused with a reason: a
   signature-only test for a method needs the class constructed, which authoring from a signature
   cannot do. The harvester handles methods; authoring does not, yet.
3. **The empty stub raises `NotImplementedError`.** A behavioural test then errors against it (not a
   pass) → accepted; a vacuous test (`assert callable(f)`) passes → rejected. The edge case — a
   function whose real contract *is* to raise `NotImplementedError` — would be mislabelled vacuous;
   rare, and documented.
4. **Rejection is an outcome, not an exception.** `AuthoringOutcome.oracle is None` with a `reason`,
   the way the harvester reports "no oracle available". A caller mistake (method, missing symbol,
   bad path) raises `AuthorError` instead.
5. **`max_attempts` defaults to 1.** The ticket did not ask for retries; the caller may raise it.
   With the fake transport, repeated attempts return the same text, so retries help only a real
   (varying) model.

## 8. The open ruling in the ticket — Gate 1's critical path

Whether EL-210 is on Gate 1's critical path depends on whether the Gate 1 toy repo already has
tests: if it does, EL-205's harvesting is enough and authoring could have deferred.

**Nothing I built assumes one reading.** The author is independent of the harvester — different
entry point, different oracle type (`AuthoredOracle`, always LOW), no shared state. If the toy repo
has tests, EL-214 can grade with harvested HIGH oracles alone and EL-210 is not on the path; if it
does not, EL-210 supplies LOW oracles. Both compose through the metric store's `oracle_confidence`
field. The decision is EL-212/EL-214's to make; EL-210 does not force it.

## 9. Warnings touched (from the M0 preamble)
- **#1 (Gate 0):** depended on transitively; flagged at the top.
- **#4 (fixture 20 / option b):** inherited and enforced — §3.
- The rest (F2, F8, PLAN §5, the six dead situations, EL-014) are not touched by authoring.

## 10. Rulings I need
1. **Accept building ahead of Gate 0** (as for EL-204/205).
2. **Accept the `input_files` addition to EL-206's sandbox** (§6), or ask for it to live elsewhere.
3. **The import-name handoff to EL-207** (§7.1): confirm the grader will expose the real artifact
   under the recorded `import_module`.
4. **EL-015 must land** before a caller can read `max_output_tokens`/validation timeout off a record.
