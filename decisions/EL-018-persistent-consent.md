# EL-018 — Approvals are remembered per project; production-suspected never is

## Decision

The bot asks before it connects to anything, and the developer can choose to have it **remember** the
answer.

| Choice in the popup | Lasts | Saved |
|---|---|---|
| Allow once | this session | no |
| Allow and remember | until revoked (or its expiry, if one is set) | yes, `<repo>/.evalloop/consents.json` |
| Deny (or closing the popup) | this session: not asked again until the next one | no |

**Production-suspected endpoints** (`classify_endpoint.py`) keep their rules: default Deny, approval
only by typing the endpoint name, and they are **never remembered**, so they ask every session. This
is the operator's decision, recorded here so it isn't asked again.

## Why

The capability broker (EL-302) held grants in memory, so every session started with nothing approved.
A bot that asks the same question every session teaches people to click Allow without reading, which
defeats the consent step (`ARCHITECTURE.md` §6). Remembering a deliberate answer keeps each question
rare enough to read.

Production is the exception because there the cost of a wrong yes is highest. A remembered approval
would turn the type-to-confirm guard into a one-time ceremony.

## Where it is saved

`<repo>/.evalloop/consents.json`: JSON, standard library only, written atomically with mode `0600`.
`.evalloop/` gets its own `.gitignore` of `*`, so approvals are never committed in any watched repo.
Each record holds the tool, endpoint, who approved it, the reason, when, an optional expiry
(wall-clock), the caps and the credential **source**. It never holds a credential **value**. The
store refuses a source that the redactor would change, and it refuses any production-suspected
record. On load it drops expired records, refused records and malformed ones. A corrupt file loads
as empty (so everything is asked again) and is moved aside, not overwritten.

## How approvals are revoked

- **In the bot:** right-click the pet (Tk) or press `p` (both pets) to open the Permissions view, which
  has a Revoke button per approval. A revoked endpoint is not asked again this session.
- **From the CLI:** `evalloop consents list [path]`, `evalloop consents revoke <endpoint> [--path]`,
  and `--all`. A running session re-reads the store every tick, so a CLI revoke applies on the next
  tick.
- Deleting `.evalloop/consents.json` forgets everything.

## Limits, stated

- **Only the SQLite check actually connects.** It is the one connection a session makes, and it now
  waits for consent. Remote endpoints (Postgres, Qdrant, …) are asked about and their approvals
  recorded, but the session cannot resolve credentials for them yet, so an approval makes them
  *available* to the broker and opens nothing.
- **Endpoint identity is textual.** An endpoint found only at a call site is keyed by `file:line`,
  so moving that line asks again. The fail-safe direction, but it can re-ask.
- **The HTTP consent routes are guarded against browsers, not local processes.** They need a JSON body
  and an `X-EvalLoop-Bot` header. A web page cannot send either to this port without a CORS preflight
  that the server never answers. A local process can, but a local process can also edit the store file.
