# EL-010 — Track X (screen sensor) scope

## Decision

**Out of scope.** Track X is not built. E9 (EL-901 to EL-905) is not scheduled, and the soft escape hatch "unless G2 shows gaps in intent capture" is replaced by the measurable trip-wire below.

The trip-wire has two halves, and **both** must fire before Track X is reconsidered: a named metric (**Residual Intent Gap**) must exceed a stated threshold at G2, **and** six cheaper remedies must be exhausted first. Even then, only EL-901 (window titles) returns; pixel capture stays out until EL-905 earns it.

My own view is stronger than "deferred" — I think the track should be struck outright — and the argument is in `## A stronger view` for you to accept or reject. The decision above is the one requested.

## Status

Decided — out of scope, with a defined trip-wire — 2026-10-06. No code, no new directory.

`DEVELOPMENT_PLAN.md:95` currently reads "Out, unless G2 shows gaps in intent capture". That clause is the problem this record fixes: nobody can compute "shows gaps" at G2, and a soft escape hatch evaluated by people who have just spent two weeks wanting the feature is not a gate. The trip-wire is defined now, before G2, while nobody has an interest in the answer.

## The trip-wire, part one: Residual Intent Gap

**Name:** Residual Intent Gap (RIG).

**What it counts.** An episode counts toward the numerator when **both** hold:

1. EL-415 classified it `unclear`, or below its confidence bar, so nothing was planned for it; **and**
2. **every cheaper sensor was silent on it** — no stated intent from a coding-agent adapter (EL-406, EL-412), no command evidence (EL-413), and the file-change signal alone did not disambiguate.

**Denominator.** Every episode closed by EL-414's episode builder in the same session.

$$\mathrm{RIG} = \frac{\text{episodes unclear } \textbf{and} \text{ unexplained by any cheaper sensor}}{\text{episodes closed in the session}}$$

**Measured on:** the G2 one-hour real session (EL-421), from the session record — not a curated fixture. A fixture cannot produce this number, because the whole point is what a real hour of work leaves unexplained.

Condition 2 is what makes the metric answer the right question. A bare `unclear` rate measures the classifier's difficulty, which has many causes a screen sensor cannot fix: an adapter that failed to parse, a shell hook never installed, a developer who stated no intent. RIG isolates the residue — the episodes where a screen sensor is the only remaining candidate — which is exactly the set Track X would have to justify itself on.

**A second, confirming measurement**, needed because RIG still does not prove a *screen* sensor would help. For each residual episode, the developer reviewing the session report marks where the intent actually was: in a GUI application with no disk artifact, nowhere at all, or in a file EvalLoop misread. This attribution is manual and that is acceptable, because the residual set should be small; if it is large enough to make manual review painful, that is itself the finding. Call this **RIG-GUI**: the share of residual episodes attributed to off-disk GUI work.

Note the circularity this avoids. Measuring "how many episodes would a window title have resolved" requires the window-title sensor, so it cannot be a precondition for building it. Human attribution over a small residual set is the only honest substitute.

### Does EL-415 as specified produce these numbers? No.

`DEVELOPMENT_PLAN.md:181` gives EL-415's done-when as "10 episodes classified; `unclear` plans nothing". That is a **correctness check on ten hand-labelled episodes**, plus a behavioural assertion. It yields neither term of RIG:

- **No denominator.** Ten curated episodes are not the episodes of a real session.
- **No persisted numerator.** Nothing requires the `unclear` verdict to be *recorded* per episode in the session artifact; the done-when is satisfied by the classifier behaving correctly in a test.
- **No cheaper-sensor silence flag.** Condition 2 needs, per episode, whether any agent adapter produced intent and whether any command evidence existed. Nothing in EL-415 records that.

**What EL-415 must additionally record**, one line per episode in the session artifact: the classification outcome including `unclear`, the confidence, and which evidence sources contributed — `agent_intent`, `command`, `file_change`, each present or absent. That is enough to compute RIG without any new sensor, and it is useful independently: it is the provenance a developer needs to understand why an episode planned nothing. The amendment is in `## Follow-up`.

## The trip-wire, part two: the threshold

Both numbers below are **product choices made by me in this record. Neither is from `knowledge rules/`, neither carries a `source_ref`, and neither may ever be presented as corpus-sourced.** `CLAUDE.md:49` forbids inventing *methodology* thresholds, which are copied verbatim from the corpus or set to `null`; a product trip-wire is a different kind of number — a decision about when to spend engineering effort — and it is labelled as such here precisely so the distinction survives.

**RIG ≥ 20% — product choice, chosen because** G2's bar at `DEVELOPMENT_PLAN.md:187` is "accurate timeline + useful report". One episode in five unaccounted for, with no cheaper remedy available, is where "accurate account of what you did" stops being imperfect and becomes false. Below that the session report still describes the great majority of the work; above it the developer can see a fifth of their hour missing.

**RIG-GUI ≥ 50% of the residual — product choice, chosen because** below half, the dominant cause of the residue is something other than off-disk GUI work, and Track X would be paying the product's highest privacy cost to fix the minority case.

**A statistical condition on firing, which is methodology rather than product choice.** A one-hour session closes a modest number of episodes, so RIG is a proportion at small *n* and its interval is wide — exactly the situation `C-deciding-whether-a-result-is-real.md:25` (C1, Wilson) and `:129` (C4, near the bounds) exist for. The trip-wire therefore fires only when the **lower bound of the Wilson 95% CI on RIG exceeds 20%**, which at small *n* requires either a clearly high rate or several sessions pooled. EvalLoop refusing to act on noise about its own behaviour is the minimum consistency this project owes itself, and it is the rule at `AGENT.md:198` applied inward.

## The trip-wire, part three: cheaper fixes first

RIG firing means intent capture has a real gap. It does not mean screen capture is the fix. **Track X returns only after all six of these are exhausted**, in this order, cheapest first:

| # | Remedy | Why it is likely to be the actual cause |
|---|---|---|
| 1 | **EL-406** — Claude Code transcript adapter | If the transcript format drifted or failed to parse, intent vanishes for reasons that have nothing to do with GUIs. `ARCHITECTURE.md:166` already anticipates this with weak-intent degradation |
| 2 | **EL-412** — second agent adapter + graceful degradation | The most likely single cause: the developer uses Cursor or Codex and no adapter exists. Building one is a day |
| 3 | **EL-413** — command sensor | If the shell hook is not installed, commands are invisible. Per `decisions/EL-009-shell-capture.md` the sensor announces this rather than failing silently, so it is cheap to detect and cheap to fix |
| 4 | **EL-422** — `report_intent` via the read-only MCP subset | The strongest cheaper fix. `ARCHITECTURE.md:177` calls it "Perfect intent, zero inference" — the agent simply *states* what it is building, and no sensor is needed. Already proposed for E4 in `decisions/EL-008-mcp-server-timing.md` |
| 5 | **EL-303** — connector discovery with provenance | Resolves two of Track X's four flagship examples from disk. A Qdrant dashboard in a window title says "a vector store exists"; `ARCHITECTURE.md:197` already discovers that from `.env` and `docker-compose.yml`, for free, with a file-and-line citation |
| 6 | **EL-809** — GitHub + Databricks connectors | Resolves Track X's headline example directly. The Databricks notebook that "nobody can read from disk" has a first-class read-only connector planned at `DEVELOPMENT_PLAN.md:241` |

The ordering matters more than the list. Each of these is between one and two days and carries no privacy cost; Track X is roughly two weeks and carries the largest privacy cost in the product.

## The deletion criterion

If the trip-wire never fires, **delete EL-901 to EL-905 and remove E9 from `DEVELOPMENT_PLAN.md:37` and `:60`.** No review, no further decision — absence of the trip-wire is the deletion condition.

If it does fire and remedies 1–6 are exhausted, EL-901 (window titles only) may be built, and then EL-905 must show all three of the following for the track to live:

1. **S4 corrects a classification that no cheaper sensor could** — `ARCHITECTURE.md:455`'s Gate X bar, unchanged.
2. **The correction changes the plan.** This is a tightening of Gate X and the most important of the three: a label that becomes more accurate while the same techniques are planned is worth nothing. The measurement is which `TechniqueRecord` ids were planned before and after.
3. **It does so on more than one episode,** so the track is not justified by a single anecdote.

If EL-905 cannot show all three, **delete EL-901 to EL-904**, as `DEVELOPMENT_PLAN.md:256` already instructs, and strike the track permanently rather than leaving it optional again.

Two things that must survive deletion, because a naive sweep would take them out: the `ocr` and `vision_model` members of the `Tool` enum are **not** Track X artefacts. They serve document extraction — scanned invoices, handwriting, regional scripts — which `DEVELOPMENT_PLAN.md:243` schedules as EL-811. `ARCHITECTURE.md:130` notes they are already in the enum; they stay.

## The trust cost

*One paragraph, for `USER_EXPERIENCE.md`.*

> Asking for screen access changes what kind of tool EvalLoop is, in a way no other permission in the product does. Every other request is scoped to a thing the developer can picture — this database, this repository, this model API — and `USER_EXPERIENCE.md:95` frames them as opt-in grants with a stated reason. Screen recording is not scoped: macOS presents it as "EvalLoop will be able to record the contents of your screen", which is both true and unbounded, and the dialog arrives with no way to say "only the window titles" even when that is all we want. The cost is also paid at the moment of *asking*, not of granting: a developer who declines has still learned that this tool wanted their screen, and that is not forgotten. Against a pitch of "two clicks per session" and a persona that `USER_EXPERIENCE.md:14` describes as unwilling to tolerate a tool that cries wolf, the ask is expensive in the one currency the product cannot rebuild. No trip-wire outcome justifies pixel capture; at most, a fired trip-wire justifies reading window titles, which is a smaller ask that still carries the same OS permission dialog — and that asymmetry, a modest benefit behind a maximal-sounding consent prompt, is the real reason this track does not pay for itself.

## A stronger view: strike it rather than defer it

The decision above is the one requested, and I would go further. Three arguments.

**Its own flagship examples are already covered.** `ARCHITECTURE.md:125-128` justifies the track with four cases. A Databricks notebook — EL-809's connector. A production DB open in TablePlus — EL-304 already defaults `production-suspected` hosts to deny from repository discovery, and EL-413 sees the `psql` invocation. A Qdrant dashboard — EL-303 finds it in `docker-compose.yml`. A Postman request against `/v1/extract` — the API artifact is in the repo. The "90/1 insight" at `ARCHITECTURE.md:121` is a good argument that window titles beat pixels; it is not an argument that window titles beat reading the repository, which is cheaper still and already planned.

**An optional track is not free.** Carrying E9 keeps S4 wired into designs that then assume it: `ARCHITECTURE.md:197` and `:419` both list "S4 titles" among connector-discovery sources, so V2 is specified partly against a sensor that does not exist and may never. Optional work in a plan is also a standing invitation to build it during a slow week, which is exactly when the trip-wire's discipline is weakest.

**The cost is a one-way door.** The engineering is two weeks and recoverable; the trust is not, and it is spent at the ask.

**What would make me wrong.** If EvalLoop's target user does their real work inside a GUI that produces no disk artifact at all — a data scientist living in a hosted notebook that never syncs to a repository — then S0, S1 and S2 see nothing, `report_intent` helps only if they use an MCP-capable agent, and Track X is not an enhancement but the only sensor that works. That is a real persona, and if it is the market, this decision is wrong. But notice that even then the answer is probably not screen capture: it is a connector to the notebook platform, which is EL-809's shape. The question is therefore about persona rather than technology, and it is answerable by asking who the first ten users are — which is worth settling before G2 regardless of this record.

## Consequences

- E9 is unscheduled. `DEVELOPMENT_PLAN.md:60` places it after 9 Apr 2027 and outside the 27-week plan, so nothing on the critical path changes.
- **EL-415 gains a recording requirement** it does not currently have. This is the only new work this decision creates, it is small, and it is independently useful as plan provenance.
- **G2 gains a measurement**, so EL-421's done-when should include computing RIG. Without that, the trip-wire is defined but never evaluated, which would reproduce the problem this record exists to fix.
- The `ocr` and `vision_model` enum members are unaffected and must not be removed with the track.
- `ARCHITECTURE.md:197` and `:419` reference S4 as a connector-discovery source and should be amended, so V2 is not specified against a sensor that is out of scope.

## Follow-up — proposed, not applied

1. **`DEVELOPMENT_PLAN.md:95`** — update the EL-010 row to "✅ Decided **Out of scope**: trip-wire is Residual Intent Gap ≥ 20% (Wilson lower bound) **and** RIG-GUI ≥ 50% **and** remedies EL-406/412/413/422/303/809 exhausted — `decisions/EL-010-track-x-scope.md`".
2. **`DEVELOPMENT_PLAN.md:181`** — one-line amendment to EL-415: "…; per-episode record of classification, confidence and which evidence sources contributed (`agent_intent` / `command` / `file_change`), so Residual Intent Gap is computable at G2".
3. **`DEVELOPMENT_PLAN.md:187`** — extend EL-421's done-when: "…; Residual Intent Gap computed and recorded".
4. **`DEVELOPMENT_PLAN.md:256`** — extend EL-905's done-when with the three-part criterion, in particular "the corrected classification changes which techniques are planned".
5. **`USER_EXPERIENCE.md`** — add the trust-cost paragraph above, and record in §6 that the screen-sensor question is answered.
6. **`ARCHITECTURE.md:197` and `:419`** — remove "window titles from S4" / "S4 titles" from the connector-discovery sources.
7. **If you accept `## A stronger view`** — delete E9 and EL-901–905 now rather than leaving them optional, and strike `DEVELOPMENT_PLAN.md:37` and `:60`.

## Related

- `ARCHITECTURE.md:109-134` — the sensor tier table, the "why not screen recorder first" argument, the 90/1 insight and the redaction boundary. `ARCHITECTURE.md:445-455` — Track X's stages and Gate X, whose bar this record tightens.
- `C-deciding-whether-a-result-is-real.md:25` and `:129` — the Wilson interval and small-*n* reasoning behind the firing condition. These are the only corpus-sourced elements here; the thresholds are not.
- `decisions/EL-008-mcp-server-timing.md` — proposes EL-422, remedy 4 and the strongest cheaper fix.
- `decisions/EL-009-shell-capture.md` — remedy 3, and the precedent for a sensor that announces rather than silently capturing nothing.
