# EL-005 — Order of Track V and Track O after Gate 1

## Decision

**Track O runs first.** This overturns the `DEVELOPMENT_PLAN.md:90` recommendation ("V first (enterprise plug-ins)").

Track O needs exactly one ticket from Track V — EL-301, two engineer-days — and Track V needs nothing at all from Track O. **After EL-301 the two tracks are technically independent, so the order is a priority call, not a technical one.**

Ordering O first moves Gate 2 from 15 Jan 2027 to 16 Dec 2026, about 4.3 calendar weeks earlier, and moves Gate V from 4 Dec 2026 to about 14 Jan 2027. It changes no other gate date, breaks no dependency, and leaves the beta date untouched at 9 Apr 2027.

## Status

Recommended — awaiting the product lead's call at Gate 1 (6 Nov 2026) — 2026-10-06.

No code and no timeline edit were made. The `DEVELOPMENT_PLAN.md` changes this implies are proposed in `## Follow-up` for you to apply.

## The dependency finding

Stated flatly, since it reframes the decision.

**Every `Depends on` cell in the E3 and E4 tables (`DEVELOPMENT_PLAN.md:147-161` and `:167-187`) was read. There are exactly two edges from Track O into Track V, and zero edges from Track V into Track O.**

| Edge | Real? | Weight |
|---|---|---|
| EL-408 (MCP gateway) → **EL-301** (MCP protocol core) | **Yes.** The gateway proxies JSON-RPC; it cannot exist without the protocol core | 2 days |
| EL-401 (`Event` + `Sensor` protocols) → **EL-315** (🔒 Gate V) | **No.** EL-315 is a gate, not a component. EL-401's done-when is "Two fake sensors, one deterministic bus" — no connector, DB, vector store or validator appears in it | 0 days of real content |

Two corrections to the reading in the ticket:

1. **EL-403 is not a cross-track edge.** EL-408 depends on `EL-301, EL-403`, but EL-403 is the Intent Bus — an E4 ticket (`:169`). That half of the dependency is internal to Track O.
2. **EL-401 → EL-315 was missed, and it is the edge that actually matters.** EL-408's dependency on EL-301 constrains one ticket. EL-401's dependency on Gate V constrains *the root of Track O*, and is therefore what serialises the whole of V ahead of the whole of O. It is also the one with no technical justification.

So the conclusion in the ticket is right, and stronger than stated: the tracks are independent after EL-301, which is 2 days of the 18.5 in Track V.

`ARCHITECTURE.md` already says so in as many words. `ARCHITECTURE.md:414` — "Track V — Verify against live systems. Starts after 🔒 GATE 1 (needs the sandbox + execution grader). **Independent of Track O.**" Its ordering diagram at `ARCHITECTURE.md:460-461` forks the two tracks off Gate 1 in parallel and routes M3 downstream of **Gate O only**, with Track V hanging off to the side. `DEVELOPMENT_PLAN.md`'s serial V → O chain is a scheduling choice laid on top of that, not something the architecture requires.

### What the rest of Track V is actually needed for

Decomposing E3's 18.5 days by who consumes the output:

| Part of Track V | Days | Needed by | When |
|---|---|---|---|
| EL-301 MCP protocol core | 2 | EL-408 (O), EL-703 (L) | early, in either order |
| EL-302 → 303 → 304 → 305 → 306 → EL-314 (broker, discovery, prod classification, read-only envelope, `Connector`, end-state verification) | 7.5 | **EL-606** (E6, resettable environment) | E6 starts 1 Feb 2027 |
| EL-307, 308, 309, 310, 311, 312, 313 (MCP client connector, Postgres/MySQL, vector store, file/prompt registry, SQL validator, RAG stages 1–2) | 8.5 | **nothing outside Gate V** | — |
| EL-315 Gate V | 0.5 | EL-401 (artificially) | — |

The third row is the finding that decides this. **8.5 of Track V's 18.5 days — the enterprise-reach half — have no downstream consumer anywhere in the plan except their own gate.** Their first real consumer is the E8 pilot, which starts 8 Mar 2027. Building them in November rather than January buys nothing that any later ticket is waiting on.

## Both orders costed

From the `DEVELOPMENT_PLAN.md:51-60` dates. Working days computed from a 5-day week; the plan's E4 carries 4 days of year-end allowance beyond its 26 engineer-days (7 Dec + 26 working days is 11 Jan, but E4 is stated to end 15 Jan), and that allowance is assigned below to whichever track spans the holidays.

| | V-first (as planned) | O-first (recommended) | Change |
|---|---|---|---|
| EL-301 | 9 Nov (inside E3) | 9–10 Nov | — |
| Track O | 7 Dec – 15 Jan | 11 Nov – 16 Dec | |
| **🔒 G2 / Gate O** | **15 Jan 2027** | **16 Dec 2026** | **22 working days / 4.3 calendar weeks earlier** |
| Track V | 9 Nov – 4 Dec | 17 Dec – ~14 Jan | |
| **🔒 Gate V** | **4 Dec 2026** | **~14 Jan 2027** | **29 working days / 5.9 calendar weeks later** |
| 🔒 G3 (M3 honesty) | 29 Jan 2027 | 29 Jan 2027 | unchanged |
| 🔒 G4, 🔒 GL | 19 Feb, 5 Mar | 19 Feb, 5 Mar | unchanged |
| 🔒 Beta | 9 Apr 2027 | 9 Apr 2027 | unchanged |

Three things make the downstream dates hold:

- **Total work is identical.** G1 → G3 is 18.5 + 26 + 7 = 51.5 engineer-days under V-first and 2 + 26 + 16.5 + 7 = 51.5 under O-first. Reordering moves no work; it only changes which gate is reached first.
- **Gate V's one hard deadline is still met with slack.** The latest thing that needs Track V is EL-314, consumed by EL-606 in E6. E6 starts 1 Feb 2027. Gate V at ~14 Jan leaves **12 working days of slack**. (The true deadline is later still: EL-606 → EL-607 → Gate 4 on 19 Feb needs only 2.5 days, so EL-314 is not strictly required until mid-February. 1 Feb is the conservative figure.)
- **E5 still fits.** Seven days from ~15 Jan completes 25 Jan, inside the stated G3 of 29 Jan.

The year-end holidays move off Track O and onto Track V, which is a secondary gain: the plan currently spends a week of holiday buffer inside the track that proves the product claim, and O-first spends it inside the track that nothing is waiting on.

One further effect, from `DEVELOPMENT_PLAN.md:95`: **EL-010 ("Is Track X in scope?") resolves to "Out, unless G2 shows gaps in intent capture."** G2 is the observation that settles a scope decision worth about two weeks. V-first cannot answer it until 15 Jan; O-first answers it on 16 Dec.

## Options considered

| Option | What it buys | Why not |
|---|---|---|
| **O first (chosen)** | G2 4.3 weeks earlier; the core product claim is tested in December; EL-010 resolves a month sooner; holiday buffer falls on the track with no dependents | Loses the December live-DB demo. Gate V slips ~5.9 weeks, with 12 days of slack remaining |
| V first (the table's recommendation) | The sharpest early demo — `ARCHITECTURE.md:465` calls text-to-SQL validation against a live DB "the most convincing thing this system can do early" | Spends 16.5 days before the product's central claim is tested at all, and 8.5 of those on work nothing downstream is waiting for. Six months in with no observer |
| Both in parallel | G2 and GV both early | Ruled out by the plan's own staffing assumption (`:7`, one engineer). `:7` and `:280` both note that a second engineer on Track O cuts ~4 weeks — the same gain O-first produces with no new headcount |
| Split V: EL-301 + broker chain now, connectors later | Keeps EL-314 early for E6; defers only the 8.5 unneeded days | A real option, and the best fallback if the flip condition fires. Rejected as the default because it still puts 9.5 days ahead of G2 for no downstream need, and it fragments a track mid-stream |

## Recommendation, and the argument against the table

The `DEVELOPMENT_PLAN.md:42` rationale is *"so enterprise data sources (DB, prompts, files) plug in early."* Early relative to what, though — nothing consumes them until E8 on 8 Mar 2027, and Gate V at 14 Jan still precedes that by seven weeks. The rationale names a benefit with no deadline attached to it.

It is also not the trade-off `ARCHITECTURE.md` frames. `ARCHITECTURE.md:465`: *"Build O first if intent inference is the bigger worry; build V first if you want the sharpest demo."* The architecture's criterion is risk versus demo. "Enterprise data sources plug in early" is a third thing, and it is the weakest of the three, because it is the only one with no date behind it.

On the architecture's own criterion, O wins. Intent inference is the larger unknown:

- It is the product. `CLAUDE.md §1`: *"A backend agent observes what you're building, infers the situation … Two clicks per session. Everything else is the agent. The developer never writes an eval."* Track V is reach; Track O is whether the thing works at all.
- It is the part that might not work. EL-415's done-when (`:181`) is "10 episodes classified; `unclear` plans nothing" — inference quality on real sessions, which no amount of design settles in advance. Track V is demanding engineering against known techniques: JSON-RPC, SQL AST rejection, HTTP to Qdrant. Hard, but not conceptually unproven.
- G2 is the only gate that tests the pitch. `ARCHITECTURE.md:412` — "Work for an hour in your normal editor with your normal agent. The timeline is an accurate account of what you did, with no eval written and no configuration touched." If that fails, much of what follows is mis-specified, and under V-first that is discovered on 15 Jan with 10 weeks already spent.

The cost of O-first is real and worth naming: no live-DB demo until mid-January. If the next three months need a convincing artifact for anyone outside the team, V-first supplies a much better one. That is a persuasion argument, not an engineering one, and it is what the flip condition below is for.

### The one thing that would make me wrong

If intent inference turns out to be the *settled* part and connector safety the genuinely scary part, V-first is correct and this recommendation is backwards. The tickets that could cause an actual incident are EL-304 (production-suspected classification, "`prod` host → default deny + type-to-confirm") and EL-305 (read-only envelope, "`DROP TABLE` rejected before it's sent"). Those touch customer production databases; nothing in Track O can do comparable damage, since the gateway proxies calls the agent was already making and the redactor only removes data. If the product lead's honest read at Gate 1 is that O11's classifier is a thin wrapper over a stable transcript format while the envelope is where the unknown risk sits, then front-loading V buys more risk reduction than G2 buys information, and O-first is the wrong call.

I do not think that is the case — EL-415's "10 episodes classified" is an empirical bar that no design review can clear in advance — but it is the reading that would overturn this, and it is a judgement about the team's own confidence that I cannot make from the documents.

## The flip condition

One sentence, to be held up at Gate 1:

> **At Gate 1 (6 Nov 2026), the product lead confirms in writing whether a named design partner or pilot team has committed to evaluating EvalLoop before 15 January 2027 on a workload whose evaluation requires a live DB or vector-store connector; if yes, Track V runs first, otherwise Track O runs first.**

It is testable (a named party and a written commitment, or not), it names the observer (the product lead), and it names the moment (Gate 1, 6 Nov 2026). It turns on a commitment rather than an intention, because "we might want a demo" is what produced the current order.

If it fires, prefer the split option over a full V-first: build EL-301 plus the EL-302–306 + EL-314 chain (9.5 days), take Gate V's SQL half, and defer EL-309/EL-312/EL-313 (the RAG chain, 3.5 days) until after G2 unless the partner's workload is RAG.

## Consequences

- EL-005 is answered against its own recommendation. `DEVELOPMENT_PLAN.md:90` should record the overturn, as EL-002 did.
- **EL-401's dependency on EL-315 is wrong in either order** and should be corrected regardless of this decision. It states a sequencing preference as a technical dependency, which is why the critical path at `:264` routes through Gate V to reach EL-408 when EL-408's own `Depends on` cell names only EL-301 and EL-403. Left as it is, it will keep re-deriving V-first whoever reads the table next.
- Track V becomes the holiday-spanning track, so E4's 1 week of year-end buffer (`:62`) should move to E3.
- The risk-table line "Only one engineer → 27 weeks, a second engineer on Track O cuts about 4 weeks" (`:280`) is worth re-reading after this: O-first delivers a comparable pull-in of the *gate that matters* without the headcount, though it does not shorten the 27 weeks to beta.
- Nothing about M0 changes. This decision affects no code, and E1/E2 are untouched.

## Follow-up — proposed `DEVELOPMENT_PLAN.md` edits, not applied

For you to apply if you accept the recommendation.

1. **`:42`** — replace the "Why this order" bullet:
   *"**Connectors (V) come before Observe (O)** so enterprise data sources (DB, prompts, files) plug in early. This is decision D5 below and can be flipped."*
   with:
   *"**Observe (O) comes before Connectors (V)** because Track O is the product claim and Gate 2 is the only gate that tests it. The tracks are independent after EL-301 (2 days), so this is a priority call — see `decisions/EL-005-track-order.md` for the flip condition."*
2. **`:23-26`** — swap the E3 and E4 blocks in the flow diagram so Track O precedes Track V.
3. **`:54-55`** — swap the two timeline rows and redate: E4 Track O weeks 6–10, 9 Nov – 16 Dec, 🔒 G2 16 Dec; E3 Track V weeks 11–15, 17 Dec – 14 Jan, 🔒 GV 14 Jan. Move the 1 week of year-end buffer from E4's note to E3's.
4. **`:68-69`** — redraw the Gantt rows for E3 and E4.
5. **`:90`** — update the EL-005 row to "✅ Decided **O first**, overturning 'V first (enterprise plug-ins)' — `decisions/EL-005-track-order.md`".
6. **`:167`** — change EL-401's `Depends on` from `EL-315` to `EL-207` (Gate 1). **Do this one whichever order you choose**: it is a correction, not a reordering.
7. **`:264`** — redraw the critical path as `… → 🔒G1 → EL-301 → EL-408 → EL-409 → EL-415 → EL-416 → 🔒G2 → EL-501 → 🔒G3 → …`, with Track V off the critical path, and add EL-314 to the "off the critical path" line at `:268` with its 1 Feb need-by.

Edit 6 is the one I would apply even if you keep V-first.

## Related

- `ARCHITECTURE.md:394-453` — what Gate O and Gate V each prove; `ARCHITECTURE.md:460-461` — the parallel-track ordering diagram; `ARCHITECTURE.md:465` — the risk-versus-demo framing this decision turns on.
- `CLAUDE.md §1` — the two-clicks-and-an-observer pitch that Gate 2 tests.
- `decisions/EL-002-mcp-tools-in-enum.md` — the earlier decision that overturned a `DEVELOPMENT_PLAN.md` recommendation, and the format used for recording that.
