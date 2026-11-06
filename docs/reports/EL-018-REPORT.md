# EL-018: Persistent consent in the bot

**Status: done, with the limits in §5.** `pytest tests/test_consent.py` 32 passed; full suite 1496
passed, 2 skipped, 1 failed (the known pre-existing
`test_oracle_harvest.py::test_the_virtualenvs_vendored_tests_are_not_this_repositorys`).
`mypy --strict evalloop/` is clean on 82 files, and the code is standard library only. Decision record:
`decisions/EL-018-persistent-consent.md`.

## 1. What existed before
Neither bot (Tk `overlay.py`, Qt `overlay_qt.py`) had any consent UI. `RunCard.permission_requests`
was a list of strings passed into `status.json` that nothing presented as a question. The session
never ran discovery, and it opened the repo's SQLite file for the automatic DB check **without
asking**. `connect/scan.py` discovered and classified endpoints but had no consent step, and
`inspect_sqlite` granted itself. The broker held grants in memory only. Reused as-is: discovery,
`classify()` (`default_deny`, `require_typed_confirmation`, `endpoint_name`), the broker's
grant/check/expiry, and the redactor from EL-310.

## 2. What exists now
| File | Contents |
|---|---|
| `evalloop/capability/consent_store.py` | `ConsentStore` / `ConsentRecord`: JSON at `.evalloop/consents.json`, atomic, `0600`, self-gitignored. Drops expired, production-suspected and malformed records on load; refuses credential values |
| `evalloop/capability/broker.py` | `store=`: loads saved approvals at start; `grant(remember=True, posture=…)` writes through; `revoke` removes from the store; `sync()` re-reads it; `grants()`; `Grant.remembered` |
| `evalloop/session/consent.py` | The decision logic, with no Tk: `ConsentRequest`, `popup_model`, `decide`, `ConsentGate` (pending queue, session denials), `discovered_requests`, `sqlite_request` |
| `evalloop/session/consent_popup.py` | The Tk popup and Permissions view. Draws the model, posts presses off-thread. Also a standalone process for the Qt pet |
| `evalloop/session/orchestrator.py` | Each tick: `broker.sync()`, discovery into the gate, SQLite check only when allowed, re-run once an approval arrives. `status.json["consent"]`; `POST /consent/decide`, `/consent/revoke` |
| `evalloop/session/overlay.py` / `overlay_qt.py` | Tk pet: popup in its own main loop, Permissions on right-click or `p`. Qt pet: launches the popup process when a request is pending; `p` opens Permissions |
| `evalloop/__main__.py` | `evalloop consents list|revoke [--all]`; `start --max-rows/--max-seconds` (the caps the popup shows) |
| `tests/test_consent.py` | 32 tests |

## 3. The eight requirements
| # | How |
|---|---|
| 1 Saved store | `consent_store.py`. Record fields as asked; the credential source only (a value is refused); expired records dropped on load |
| 2 Broker loads / writes through | `CapabilityBroker(store=…)` loads in `__init__`; `grant(remember=True)` and `revoke` write through; tested across a simulated restart, including expiry across a fresh monotonic clock |
| 3 Tk popup | Shows endpoint, host, database/collection, credential source, operations, caps, risk and provenance, with Allow once / Allow and remember / Deny. Never blocks: a `Toplevel` in the bot's own loop, with HTTP on daemon threads |
| 4 Production rules | Default Deny, typed name required, no remember button; `decide()` refuses to remember even if asked; the store refuses it too, so it is asked every session (tested) |
| 5 Ticks check saved approvals first | `observe()` returns granted endpoints silently and queues only new or expired ones. A denial (or a revoke) is held for the session |
| 6 Revoking | Permissions view in the bot; `evalloop consents list|revoke`; a running session picks up a CLI revoke next tick |
| 7 Tests | Store round trip, expiry, no secret values, restart survival, production never saved and typed name required, popup decisions without a window, session gating, HTTP plus browser-forgery refusal, CLI |
| 8 Docs | The decision record and this report |

## 4. Verification of the popup itself
Screen capture is blocked in this environment, so there is no screenshot. Instead, a driver built the
**real Tk popup widgets** against a **live session** on a demo repo (a production-looking `.env`
key, a compose Postgres, `app.db`) and pressed their buttons with `invoke()`, which is what a click
calls:
- The production popup offered only Deny / Allow once. A wrong typed name was refused and the popup
  stayed open; the right name allowed it for the session only.
- Postgres: Deny was honoured.
- `app.db`: "Allow and remember" saved it, and the DB check ran.
- The Permissions view listed both approvals, and its Revoke emptied the saved file.
- A 30 fps stand-in loop kept advancing during the HTTP round trips.

Separately, `evalloop start … --bot` was run for real. The session queued all three requests and the
Qt pet launched the popup process. Seeing the window on screen and clicking it is the one step a
human has to confirm.

## 5. Skipped, or not verified
1. **Remote endpoints are asked about but never opened.** The session has no credential resolution for
   Postgres/Qdrant/MCP, so approving one records it and makes it available to the broker; nothing
   connects. Only the SQLite check is actually gated, because it is the only thing that connects.
2. **No screenshot or real mouse click** (see §4). The widgets, layout data and button handlers are
   exercised; how the window looks on screen is not checked by me.
3. **The Qt pet's popup runs as a subprocess**, because Tk and Qt cannot share a main thread. It is
   still the same Tk popup.
4. **Endpoint keys are textual** (`file:line` for call-site-only endpoints), so editing that line
   asks again.
5. **HTTP routes are browser-safe, not local-process-safe** (decision record, "Limits").
