# EL-302 — V1 Capability broker

**⚠ Depends on Gate 1 (EL-212, awaiting sign-off).** Built ahead, as the M1 work was built ahead of
Gate 0; flagging per the standing rule. It rests on `ARCHITECTURE.md` §6/§9 and reuses EL-209's
ledger, not on gated rulings.

**Status: done.** `pytest tests/test_capability_broker.py` 13 passed; `mypy --strict evalloop/`
clean on 48 files; standard library only. Full-suite note in §5.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/capability/broker.py` | `CapabilityBroker`, `Grant`, `Caps`, `Availability`, `CapabilityError` |
| `evalloop/capability/__init__.py` | re-exports |
| `evalloop/run.py` | the M1 driver now gets its planner tools from the broker, not a private list (§4) |
| `tests/test_capability_broker.py` | 13 tests |

## 2. Done-when and the guarantees
- **Ungranted → UNAVAILABLE naming the tool.** `check(Tool.db_connection)` →
  `Availability(granted=False, reason="the capability 'db_connection' is not granted; grant it …")`.
  The string matches the planner's UNAVAILABLE state and EL-214's permission request.
- **Nothing granted by default**; `available_tools()` is empty until a grant is made.
- **Consent is explicit and revocable**; a grant records who granted it and why (a blank is refused).
- **Expiry without a restart**: a grant with `expires_in` lapses on the next `check`, reverts to
  UNAVAILABLE, and drops out of `available_tools()` — tested with an injected clock.
- **Endpoint scoping**: a grant can cover one endpoint (`postgres://localhost/shop`) or, blanket,
  all endpoints of a tool.
- **Caps are grant parameters, unset by default** (EL-006): `max_rows`/`max_bytes`/`max_seconds`/
  `budget_usd`, each `None` until supplied, never defaulted.
- **Session budget with a hard stop**, reusing EL-209's `CostLedger`: `spend()` refuses with
  `BudgetExhausted` when the budget can't cover it.

**Mutation-checked:** making an ungranted tool read as granted, and ignoring expiry, each failed the
suite.

## 3. Credentials: only the capability layer
The broker holds the *shape* of a credential — a grant records a `credential_source` (e.g.
`.env:DATABASE_URL`), never a value. The broker reads no environment variable itself (a test
asserts it), and EL-209's repo-wide scan still holds that `capability/llm.py` is the only module
that reads the environment. When `evalloop/connect/` lands, that same scan already covers it, so
"credentials in a grader: impossible by construction" stays true by construction.

## 4. The M1 driver now routes through the broker (the "one broker, not two" acceptance)
`evalloop/run.py` no longer passes a hard-coded tool list to the planner. It builds a
`CapabilityBroker`, grants the capabilities M1 genuinely has (the local sandbox and test runner,
plus reading the repo and its docs), and plans against `broker.available_tools()`. Behaviour is
identical — the same tools are available, so every run-driver test still passes — but the grant now
flows through the one broker, and the LLM tools remain ungranted by design (option (b)).

## 5. Full-suite note (not an EL-302 regression)
`pytest` reports 1218 passed, 1 skipped, 1 failed. The failure is the **F-G1a finding** from the
`testcases running/` demo folders created earlier this session (their `tests/test_*.py` are counted
by the harvester's repo walk); it is unrelated to EL-302 and is resolved by relocating those folders
to a dot-directory, as `.gate1/` was.

## 6. Rulings I need
1. **Accept building ahead of Gate 1** (as for the M1 work).
2. **Confirm the broker supersedes the M1 driver's stand-in** (§4) — done here; flag if you wanted
   it kept separate.
3. **Credential resolution (source → value)** is deliberately not built in V1 — it lands with the
   first connector that needs a secret (EL-308 Postgres/MySQL), inside the capability layer so the
   env-scan invariant holds. Confirm that placement.
