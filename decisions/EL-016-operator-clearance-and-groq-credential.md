# EL-016 — The operator's `--author` flag issues the one Clearance; `grok.py` is the second credential reader

## Decision

Two M1 invariants in `tests/test_llm_router.py` are narrowed from "none / one" to **one named
exception each**, and the tests now assert that exact list:

| Invariant | Was | Now |
|---|---|---|
| Modules that construct a `Clearance` | none | `__main__.py` only, inside the `start --author` branch |
| Modules that read the environment for a credential or price | `capability/llm.py` | `capability/llm.py`, `capability/grok.py` |

## Why

- **A Clearance is consent, and consent belongs to the operator.** M1's rule (option (b): nothing
  issues a Clearance, so nothing leaves the machine) held while no feature needed egress. Test
  authoring (`evalloop start --author`) does: it sends source code to a model. The flag is typed by
  the person running the session, and its help text says "sends code off this machine". That flag is
  the grant, so the CLI branch that handles it is the only honest place to build the `Clearance`.
  Moving the construction into a helper would hide the issuer, not remove it.
- **Groq is a second provider with its own key.** `OpenAICompatibleTransport.from_environment` reads
  `GROQ_API_KEY`, and `_price` reads `EVALLOOP_GROQ_PRICE_IN` / `_OUT` (the engine never invents a
  price, so the operator supplies it). This follows the same rule as `llm.py`: one function per
  credential, and nothing in a grader reads the environment.

## What still holds

- No grader, connector or session module constructs a Clearance or reads a credential. Any third
  issuer or reader fails the tests and has to come with a decision of its own.
- Without `--author`, nothing leaves the machine. `check --no-llm` and plain `start` make no model
  call.
- The capability broker (M2) is still the intended long-term issuer. When it lands, it replaces the
  CLI branch, and this exception is removed.
