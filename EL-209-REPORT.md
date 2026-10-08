# EL-209 — LLM client and router (stage S39)

**Status: done, under option (b).** `pytest` passes: 931 tests on 3.12, and 930 plus one skip on
3.10. The skip is the existing 3.11-only `StrEnum` check. `mypy --strict evalloop/` is clean on
27 files. **The capability package has zero `Any` expressions**: `mypy --strict
--disallow-any-expr evalloop/capability/` passes, which is stricter than the ticket's "no Any on
the response path". The package uses the standard library only.

**Gate 0:** EL-209 does not depend on it (§0.1, warning 1).

---

## 1. Which option M1 runs under: (b), enforced in code

**M1 makes no outbound call on an artifact that has not been cleared.** This is enforced in the
code, not left as a convention.

- **The gate.** Every call through a transport that leaves the machine needs a `Clearance`, an
  explicit grant that names who granted it and why. Without one, `LLMClient.complete` raises
  `EgressRefused` *before a byte is sent*. A test proves the HTTP opener is never called.
- **No issuer.** Nothing in M1 issues a clearance. `test_nothing_in_evalloop_issues_a_clearance`
  fails if any module under `evalloop/` constructs one.
- **No redaction.** The client redacts nothing. That was never asked for, and it isn't my call.
- **The real transport is built but never reaches a network.** `AnthropicHTTPTransport` exists and
  is tested only against a fake opener and a patched `urlopen`.

**What (b) costs, which you should weigh when you rule.** Under (b), EL-210 (the test author) can
run only against a fake transport in M1. Gate 1 therefore cannot use an oracle EvalLoop authored
itself. Only Gate 1's "Reading A", which harvests existing tests, is available
(`E2-M1-TICKETS-AND-PROMPTS.md` §4.4). Moving to (a), or naming who may issue clearances in M1,
changes that.

---

## 2. What exists

| File | Contents |
|---|---|
| `evalloop/capability/llm.py` | The `urllib.request` client: retries, the egress gate, credentials, the request and response records, the HTTP transport |
| `evalloop/capability/router.py` | The `Job` enum, `ModelConfig`, the router, the cross-family assertion, `CostLedger` and `call_cost` |
| `evalloop/capability/models.py` | **Not in the ticket's file list.** It exists for requirement 6: the model catalog as configuration, with every id and price taken from the claude-api skill |
| `evalloop/capability/__init__.py` | Re-exports |
| `tests/test_llm_router.py` | 55 tests |

---

## 3. The seven requirements

| # | Requirement | How it is met |
|---|---|---|
| 1 | `urllib` client: bounded retry, jittered backoff, total-time cap, typed errors, no `Any` | Retries stop after `max_attempts`. Backoff is full jitter under a doubling ceiling, and `retry-after` is honoured. Both each wait and each attempt's timeout are bounded by `total_timeout`. Errors are typed: `RateLimited` (429), `Overloaded` (529), `ServerError` (5xx, 408, 409), `RejectedRequest` and `AuthenticationFailed` (4xx, not retried), `TransportError`, `MalformedResponse`, `RetriesExhausted` and `TotalTimeExceeded`. There are zero `Any` expressions |
| 2 | Router keyed by job; a judge must not share the generator's model family, and must raise | `Router.select` raises `SameFamilyJudge`, naming the judge's family and the generator's. It raises `UnknownGeneratorFamily` when the generator's family is unknown, rather than assume the families differ. Tested |
| 3 | Cost per call and per session, a session budget and a hard stop | Money is `Decimal`. The cost is recorded on every `RoutedResponse` and accumulated in `CostLedger`. Before each call, the call is refused if the budget is spent or the call's worst-case output would cross it. Tested at both points |
| 4 | Credentials read only in this module | `AnthropicHTTPTransport.from_environment` is the only environment read in `evalloop/`, and a source scan enforces that. The key never appears in `repr` or in an error message, which is tested with a planted key |
| 5 | No test touches the network; the suite passes with no credentials | Autouse fixtures make sockets and `urlopen` raise, and remove `ANTHROPIC_API_KEY`. A test confirms the guard is live |
| 6 | Model ids as configuration, current, from the claude-api skill | All 11 ids live in `models.py`, copied exactly from the skill's table (cached 2026-09-25). A source scan fails if a model id appears in any other module |
| 7 | Model id, parameters and seed recorded with every response | `LLMResponse.request` is the request exactly as sent. `seed` is always `None`, because the API has no seed. Also recorded: `served_model`, the request id, attempts, the jitter seed and the clearance |

**Mutation-checked.** I broke six guarantees in the source, one at a time: the egress gate, the
same-family check, the budget reservation, the non-retryable split, `retry-after`, and the
per-attempt time cap. A test caught every break, and every source was restored byte for byte.

---

## 4. Findings

1. **Temperature cannot be pinned on the current flagship models.** Per the skill's thinking/effort
   table, `temperature` returns a **400** on Opus 5.5, Sonnet 5.5, Fable 5 and 5.1, Opus 5, and
   Opus 4.7 and 4.8. Only Haiku 4.5, Sonnet 4.6 and Opus 4.6 accept it, and **no model offers a
   seed**.

   So the corpus's judge advice — A:147, "Pin the judge. Use an exact model version and
   temperature 0" — cannot be followed on a flagship model. The router refuses `temperature` up
   front for those models.

   For M4's judge, this leaves `ARCHITECTURE.md` §9's fallback, "repeat and report variance",
   unless judges are routed to a model that accepts sampling. That is a ruling for M4.
2. **With the catalog alone, judging Claude-written code always raises.** Every Anthropic model is
   family `claude`. A cross-family judge needs a second provider's transport, which is
   `Tool.llm_api_cross_family`'s job, and it arrives with the judge in M4.
3. **The skill's default server-side refusal fallbacks are not enabled.** The skill says to enable
   them by default for Opus 5.5 and Sonnet 5.5, and to tell you. I didn't enable them: in an eval
   harness, a fallback answers with a different model than the one configured, in the middle of a
   run. Refusals instead come back visibly, as `stop_reason == "refusal"` with the category. The
   choice is yours; see §7.
4. **No retry number, budget or routing ships.**
   - `RetryPolicy`, the session budget and the job-to-model routes have no defaults. These are
     operational policy that the corpus doesn't state, which under EL-015 makes them grant
     parameters.
   - For reference only, the SDKs' documented defaults are 2 retries and a 10-minute timeout.
   - Before any real call, someone has to supply these values.
5. **The budget can be overshot.** Input tokens can't be priced before a call without a second API
   request. So a session can end above its budget by at most its **last call's input cost**. The
   module docstring says so.
6. **Only `ANTHROPIC_API_KEY` is supported.** The skill lists other real credential sources:
   `ANTHROPIC_AUTH_TOKEN`, `ant auth` profiles and workload identity. Those belong to the M2
   broker.
7. **The skill contradicts itself on consecutive same-role messages.** Its Python README says they
   are allowed and combined; its error table says they return a 400. The client checks only that
   the first message is from the user, which both sources agree on.

---

## 5. Interpretations, flagged for review

- **Sonnet 5.5** is recorded as not accepting temperature. Its row says "Non-default values —
  400", and a parameter that can only be sent at its default pins nothing.
- **408 and 409 are retried.** The skill says the SDKs retry them, but its error table doesn't list
  them.
- **Jitter is "full jitter":** a uniform draw in `[0, ceiling)`. The skill's example adds
  `random.uniform(0, 1)` instead, which would have shipped an invented one-second figure.
- **The client always waits at least `retry-after`,** even when that exceeds `max_delay`. The
  total-time cap still applies.
- **Every Anthropic model is treated as one family, `claude`.**

---

## 6. Doc lines found stale, and edited

| Where | Change |
|---|---|
| `ARCHITECTURE.md` §7, component 11 | Was "M2". Now: the client, router, cross-family rule and session cost exist in M1, and grants, consent and rate-limit policy remain M2. This is the doc change the E2 tracking row planned |
| `PLAN.md` T34 | The cross-family router assertion was scheduled for M4; it is now marked done in M1 |
| `E2-M1-TICKETS-AND-PROMPTS.md` | The board marks EL-209 done under option (b) |

---

## 7. Rulings I need

1. **Egress.** Choose one:
   - stay on (b);
   - choose (a), a minimal redaction boundary;
   - name who may issue clearances in M1.

   This decides whether EL-210 can call a real model, and which reading Gate 1 can use.
2. **Policy values.** The retry policy, the session budget, and which model serves which job. None
   ships with a default.
3. **Refusal fallbacks.** Off, which is what I'd recommend for an eval harness, or on.
4. **M4 judges.** Either accept "repeat and report variance", or route judges to a model that
   accepts sampling. Pinning temperature on flagship models isn't possible.
