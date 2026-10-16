# EL-304 — V3 Production-suspected classification

**⚠ Depends on EL-303 (done) and, transitively, Gate 1 (awaiting sign-off).** Built ahead; flagged.

**Status: done.** `pytest tests/test_endpoint_classification.py` 14 passed; `mypy --strict evalloop/`
clean on 51 files; standard library only (`ipaddress`, `dataclasses`). Full-suite note in §4.

## 1. What exists
| File | Contents |
|---|---|
| `evalloop/connect/classify_endpoint.py` | `classify(candidate) -> Classification`, `Classification`, `Posture` |
| `tests/test_endpoint_classification.py` | 14 tests; all candidates hand-built (no repo scan, nothing committed) |

`classify` reads one discovered `Candidate` and decides posture. It **opens nothing** — connecting
and probing are EL-305/EL-306. `Classification` carries `posture`, a plain-language `rationale`,
`default_deny`, `require_typed_confirmation`, and `endpoint_name` (what the user types to confirm).

## 2. The acceptance criteria
| # | Result | How |
|---|---|---|
| 1 | prod / non-RFC1918 / secrets-manager → `production_suspected`, deny, typed name | three independent checks, each sufficient; all set `default_deny=True`, `require_typed_confirmation=True` |
| 2 | localhost / RFC1918 → `local`, no type-to-confirm | `ipaddress.is_private`/`is_loopback`/`is_link_local` + the literal `localhost`; `require_typed_confirmation=False` |
| 3 | Each classification states the heuristic in plain language | `rationale`, e.g. *"its name contains 'prod', which usually means production"* |

`Classification.confirms(typed)` gates the grant: for `production_suspected` it requires the exact
`endpoint_name` (trimmed); for every other posture it returns `True` without typing.

## 3. The heuristics, and the one rule that orders them
The fail-safe direction is toward **production-suspected**, so the production checks run first and
any one is enough:
1. **Secrets-manager credential** — `credential_source` is a vault / AWS-SM / GCP-SM / SSM /
   1Password / Key Vault rather than a plain `.env` → production-suspected.
2. **A `prod` / `live` / `www` token** in host, detail, credential key, or kind → production-suspected.
   This fires even on `localhost`: a local `prod_db` costs one keystroke, which is cheaper than a
   false "local."
3. **A public (non-RFC1918) host IP** → production-suspected.

Only then: a **private / loopback** host → `local`; a `staging`/`stage`/`dev`/`test`/`uat`/`qa`
token → `staging`; **no signal → `unknown`, which also defaults to deny** ("no idea" is not "safe").

## 4. Calls I made
1. **A bare hostname is never assumed private.** This module does not resolve DNS (a network op), so
   a hostname that is not an IP literal and carries no token lands in `unknown`, not `local` — it
   does not silently become "safe."
2. **`unknown` defaults to deny but does not demand the typed name.** The ticket mandates
   type-to-confirm only for `production_suspected` and "no typing" for `local`. For `unknown` I chose
   deny-by-default (fail-safe) without the typed-name gate, since there is no name we are confident
   enough in to make the user retype. `staging` defaults to allow with no typing.
3. **The non-RFC1918 check is IP-literal only.** For a hostname it is the token checks that decide;
   the public-IP rule applies to literal addresses, where RFC1918 membership is knowable without a
   lookup. `is_link_local` (169.254/16) counts as non-public, i.e. local.
4. **`preprod` and `preview` cut toward production.** `preprod` contains `prod`, so it classifies
   production-suspected (pre-prod is prod-like); `preview` is in the staging token set.

## 5. Full-suite note (not an EL-304 regression)
`pytest` reports 1241 passed, 1 skipped, 1 failed — the F-G1a finding from the `testcases running/`
demo folders, unrelated to EL-304. Relocating those folders to a dot-dir clears it.

## 6. Rulings I need
1. Accept building ahead of Gate 1.
2. **`unknown` consent posture** (§4.2): deny-by-default with no typed-name gate — right for the
   consent UI, or should `unknown` also require the typed name?
3. **Secrets-manager detection is prefix/marker-based** (§3.1). EL-303 discovery only emits `.env`
   sources today, so this path is exercised by hand-built candidates; confirm the marker list
   (vault / aws-secret / ssm / gcp-secret / 1password / op:// / keyvault) is the set you expect when
   discovery grows secrets-manager sources.
