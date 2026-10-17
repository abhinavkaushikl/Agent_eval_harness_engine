# E0-DECISION-PROMPTS.md — one prompt per decision ticket

Run-ready prompts for the ten E0 decision tickets in `DEVELOPMENT_PLAN.md` §3.
Each one states **what I want**, **what is in the ticket**, **the input**, and **the result I want to see**.

**How to use:** paste §0 (the shared preamble) followed by exactly one ticket block.
One session per ticket. Do not batch EL-001 to EL-004 — each one edits the same files
(`CLAUDE.md`, `evalloop/vocab/`) and they will collide.

**Order:** EL-001 → EL-004 first and this week; they block `EL-103` / `EL-113`, which is
the head of the M0 critical path. EL-005 to EL-010 are forward-looking and can run in any
order, in parallel, by anyone.

---

## 0. Shared preamble (paste before every ticket block)

````text
You are working in the EvalLoop repo at /Users/abhinav/Eval-harness-Engine.
Read CLAUDE.md first and obey it, especially:
  - Milestone 0 only: registry + planner. No execution, no sandbox, no file watching,
    no LLM calls, no statistics, no storage, no dashboard, no MCP code.
  - Standard library only. Python 3.10+ (EL-012). Type hints everywhere.
  - Never invent a number. A threshold is copied verbatim from the corpus or is null.
  - Never hardcode an absolute user path. The corpus path comes from EVALLOOP_CORPUS.
  - Do not edit a test fixture to make a test pass.

This is a DECISION ticket. The deliverable is a written decision, not a feature.

Write the decision to decisions/EL-0NN-<slug>.md with exactly these headings:
  # EL-0NN — <title>
  ## Decision          (one sentence, present tense, no hedging)
  ## Status            (Accepted | Rejected | Deferred, plus today's date)
  ## Context           (what forced the decision; cite file and line)
  ## Options considered (a table: option | cost | what it buys | why not)
  ## Consequences      (what this makes easy, what it makes hard, what it forecloses)
  ## Evidence          (every claim cited as file:line or a verbatim quote)
  ## Follow-up         (the tickets this unblocks, and any code change this ticket itself makes)

Rules for this session:
  - Verify every claim against the repo or the corpus before you write it. If you cannot
    find evidence for something the ticket asserts, say so in ## Evidence and mark the
    decision Deferred rather than guessing.
  - If the recommendation on the table is wrong, say so plainly and argue the alternative.
    I want the decision to be right, not ratified.
  - If the ticket calls for a code change, make only the change named in its
    "Result I want to see" and nothing else.
  - Finish with: pytest exit 0, mypy --strict evalloop/ exit 0, and a report-back covering
    what you changed, what you could not represent, and anything you had to interpret.
````

---

## EL-001 — Corpus location and file names

**Blocks:** EL-103, EL-113 · **Recommendation:** make `knowledge rules/` canonical, using the real names

````text
WHAT I WANT
Make the in-repo directory "knowledge rules/" the canonical corpus, referred to everywhere
by its real filenames, and make a missing or misnamed corpus file fail loudly instead of
skipping. Then purge every stale path and filename from the docs and the tests.

WHAT IS IN THE TICKET
CLAUDE.md §4 describes the corpus as living at $EVALLOOP_CORPUS (default ~/Downloads) in
two locations: a master lookup at the root, and ten deep dives under a "files (3)/"
subdirectory, with Title-Case names. The real corpus is in the repo, in one flat directory,
with lowercase names, no "files (3)" subdirectory, and a different name for section C.
Until this is reconciled, every corpus-reading stage from EL-103 onward reads nothing.

THE INPUT
Read, and treat as the ground truth:
  - ls "knowledge rules/"   — the 12 real files. Note: evals-situation-to-technique.md
    (lowercase), and C-deciding-whether-a-result-is-real.md, which CLAUDE.md calls
    C-Is-The-Result-Real.md.
  - CLAUDE.md §4            — the claimed paths, which are wrong.
  - tests/conftest.py       — MASTER_LOOKUP = "Evals-Situation-to-Technique.md",
                              corpus_dir defaults to ~/Downloads.
  - tests/test_corpus.py    — skips when the file is absent.
  - TASKS.md line 123       — the enrichment stages hardcode "A-Choosing-How-To-Grade.md"
                              as the source_ref format.
Verified fact you do not need to re-derive, but should confirm: ~/Downloads holds neither
the master lookup nor a "files (3)" directory, so the single corpus test skips today and
test_corpus.py has never actually asserted anything.

THE RESULT I WANT TO SEE
1. decisions/EL-001-corpus-location.md per the shared preamble. In ## Consequences, state
   explicitly what it costs to keep the corpus inside the repo (it is now versioned with
   the code, and a corpus edit shows up as a code diff) versus leaving it external.
2. One single source of truth in code for corpus filenames — a module-level mapping of
   section letter -> filename, plus the master lookup — defined once and imported by the
   tests. No filename literal anywhere else.
3. tests/conftest.py: the default is the repo's "knowledge rules" directory, resolved
   relative to the repo root, not ~/Downloads, and not an absolute path. EVALLOOP_CORPUS
   still overrides it.
4. A test that FAILS, naming each missing file, when a corpus file named in the mapping is
   absent. Keep a skip only for the case where EVALLOOP_CORPUS points somewhere else
   entirely, and say in the skip message which file was missing and where it looked.
5. tests/test_corpus.py asserts the section header of all ten deep dives plus the master
   lookup, not just "## A. CHOOSING HOW TO GRADE".
6. CLAUDE.md §4 rewritten to the real layout, and the source_ref convention in TASKS.md
   line 123 updated to the real filename so EL-113 onward cites something that exists.
7. The output of a grep proving no stale name survives anywhere in the repo:
   grep -rn "files (3)\|Evals-Situation-to-Technique\|C-Is-The-Result-Real\|Downloads" \
     --include=*.md --include=*.py .
   An empty result, or every remaining hit explained.
8. pytest and mypy --strict green, and the corpus test now PASSING rather than skipping.
   Say so in the report, and say which it was before.
````

---

## EL-002 — MCP tools in the `Tool` enum

**Blocks:** EL-104 · **Recommendation:** yes, while the enum is still cheap to change

````text
WHAT I WANT
Decide whether mcp_gateway and mcp_client become Tool members now, in M0. I am not asking
for any MCP code: EL-301 is four months out and CLAUDE.md forbids it in this phase. I am
asking whether the vocabulary reserves the words today, and I want the abstraction
question answered before the answer gets cheap-and-wrong.

WHAT IS IN THE TICKET
The recommendation is yes, on the grounds that an enum is cheap to change now and
expensive once 70 records cite it. The counter-argument I want tested: every existing Tool
member is a capability a technique needs in order to run — sandbox, db_connection,
human_labels, trace_capture. mcp_gateway and mcp_client are transport. A technique record
requires "a database I can read", not "the wire protocol used to reach it". If that is
right, then MCP belongs to the capability broker (EL-302) and the gateway (EL-408), not to
the Tool enum, and adding it here lets a transport leak into the methodology layer.

THE INPUT
  - CLAUDE.md §6, the Tool enum: the 15 current members. Judge whether each is a
    capability or a transport, and say which category MCP falls into.
  - CLAUDE.md §6, the standing rule: add members only if genuinely missing, and justify
    each addition in a module docstring note.
  - DEVELOPMENT_PLAN.md §3: EL-307 makes any MCP server a read-only Connector, and EL-408
    proxies agent tool calls. Both sit behind existing concepts.
  - The corpus in "knowledge rules/". Search it for anything that would make an MCP
    transport a precondition of a technique. I expect zero hits; report what you find.

THE RESULT I WANT TO SEE
1. decisions/EL-002-mcp-tools-in-enum.md. The ## Decision line must answer yes or no, not
   "it depends".
2. In ## Evidence, the capability-versus-transport classification of all 15 current members
   as a table, and the count of corpus hits that would require an MCP transport.
3. The decisive test, answered with a named technique: is there any record in sections A-J
   that can run with mcp_client and cannot run without it? If there is, name it and the
   answer is yes. If there is not, the answer is no, and say which layer owns MCP instead.
4. If the answer is yes: the two members added to evalloop/vocab/tools.py, each with the
   docstring justification CLAUDE.md requires, plus parser round-trip tests, and nothing
   else touched.
5. If the answer is no: no code change, and a one-line note in the decision record stating
   where the words will live instead and which ticket introduces them.
6. Either way, state in ## Consequences what it actually costs to add a Tool member after
   70 records exist, concretely. The recommendation rests on that cost being high; check
   whether it is, given that required_tools is a per-record tuple and the integrity checker
   validates it.
````

---

## EL-003 — New situations

**Blocks:** EL-103 · **:** add them in M0

````text
WHAT I WANT
For each of claim_unverified, live_endpoint_available and agent_tool_call: either corpus
evidence that the situation exists in the methodology, with a family to put it in, or a
decision to defer it. Treated one at a time. I expect them to get different answers.

WHAT IS IN THE TICKET
The recommendation is to add all three in M0, while the enum is cheap. But CLAUDE.md is
emphatic that the Situation vocabulary is the most important correctness decision in M0,
that members may be added only if genuinely missing, and that each addition needs a
docstring justification. A Situation that no technique triggers on is dead vocabulary that
makes match() look complete while planning nothing. Note that all three of these smell
like they come from the post-M0 tracks, not from the corpus: claim_unverified is the input
to EL-701/EL-702 claim verification, live_endpoint_available is a connector condition from
Track V, and agent_tool_call is what the EL-409 gateway recorder emits.

THE INPUT
  - CLAUDE.md §6: the five Situation families and their current members, as the shape to
    match.
  - "knowledge rules/evals-situation-to-technique.md": the master lookup, one row per
    technique, with a Situation column. This is the authority on what situations exist.
  - The ten deep dives, for situations the master lookup phrases differently.
  - DEVELOPMENT_PLAN.md: EL-701, EL-702, EL-307, EL-409, so you can see which post-M0
    ticket each candidate actually serves.

THE RESULT I WANT TO SEE
1. decisions/EL-003-new-situations.md with one table row per candidate:
   candidate | corpus evidence (file:line + verbatim quote, or NONE) | family | which
   technique record would trigger on it | verdict (Add | Defer to <ticket>)
2. For every Add: the family it joins, and at least one named section A-J technique that
   triggers on it. A new Situation with no triggering technique is not an Add; it is a
   Defer. Hold that line even if it means rejecting all three.
3. For every Defer: the ticket that will introduce it and why M0 is the wrong time, in one
   sentence.
4. If anything is added: the members in evalloop/vocab/situations.py in the right
   comment-grouped family, the docstring note justifying each, and parser tests. Value
   equals lowercase member name, as CLAUDE.md requires.
5. A separate section listing any situation you found in the master lookup that is NOT in
   CLAUDE.md §6 and is NOT one of these three candidates. That is the real risk here — a
   missing situation makes matching fail silently — and I would rather find those now than
   at EL-120.
````

---

## EL-004 — Topics in CLAUDE.md that the corpus does not cover

**Blocks:** EL-113 · **Recommendation:** add them to the knowledge files or drop them from CLAUDE.md

````text
WHAT I WANT
Reconcile CLAUDE.md's section-coverage claims with what the corpus actually contains, in
the honest direction. Where CLAUDE.md promises a technique the corpus does not teach, the
default is to delete the promise, not to write the technique. I will not have invented
methodology in the registry.

WHAT IS IN THE TICKET
CLAUDE.md §4 "Section coverage" and §6 name techniques that appear nowhere in the corpus.
EL-113 enriches sections A and B against the deep dives and is the first stage that would
trip over this. The ticket offers two outs: add the topics to the knowledge files, or drop
them from CLAUDE.md. Adding them means authoring methodology, including thresholds, which
collides head-on with "never invent a number". So the bar for Add is: the concept is
already in the corpus under a different name, and the edit is a rename. Anything else is a
Drop.

THE INPUT
Verified by grep over "knowledge rules/" — re-confirm each, do not take my word for it:
  - "reward hack"  -> zero hits. CLAUDE.md §4 lists it first under section E.
  - "Fleiss"       -> zero hits. CLAUDE.md §4 lists it under F, and §6 names it again.
  - "distill"      -> zero hits. CLAUDE.md §4 and the ladder in §6 both end in a
                      "distilled" rung, and ladder_priority 6 is reserved for it.
  - "Goodhart"     -> zero hits. CLAUDE.md §4 lists it under E.
  - "over-refus" / "overrefus" -> zero hits, though bare "refusal" appears in
                      D-rare-events.md and I-production.md. CLAUDE.md §4 lists
                      "violation + over-refusal" under D. Check whether the concept is
                      there under another name before you drop it.
  - "hacking"      -> one file, C-deciding-whether-a-result-is-real.md, not E. So the
                      concept may exist but be mis-assigned to a section in CLAUDE.md.
  - "Krippendorff" -> present in F. Also check Cohen's kappa, which §4 pairs with Fleiss'.
Then check every other technique named in the §4 coverage table the same way. The six above
are the ones I already know about; I want the whole table audited.

THE RESULT I WANT TO SEE
1. decisions/EL-004-claude-md-corpus-gaps.md with one row per technique named in the §4
   coverage table:
   claimed topic | claimed section | corpus hits (file:line, or NONE) | verdict
   where verdict is: Present | Present-but-mis-sectioned | Rename (corpus name -> our
   name) | Drop from CLAUDE.md.
2. Every Add or Rename justified by a verbatim corpus quote. No verdict of "add it to the
   knowledge files" unless you can quote the content being renamed. If a topic is genuinely
   absent, it is a Drop. Say so even where it is awkward — a missing distilled rung changes
   the ladder in §6 and the ladder_priority 6 slot.
3. The edits applied: CLAUDE.md §4 and §6 made true, and ladder_priority adjusted if the
   distilled rung goes. If the ladder changes, flag it as a schema-affecting change per
   CLAUDE.md §7 rule 5 rather than quietly renumbering.
4. An explicit statement of what the registry will therefore NOT be able to plan, as a
   short list. That is the output EL-113 needs most: knowing that section E has no reward
   hacking record is fine, whereas discovering it mid-enrichment is not.
5. Zero new numbers introduced anywhere. Confirm that in the report.
````

---

## EL-005 — Order of Track V and Track O after G1

**Blocks:** E3, E4 · **Recommendation:** V first (enterprise plug-ins)

````text
WHAT I WANT
Fix the order of Track V (connectors + MCP client) and Track O (observe + MCP gateway)
after Gate 1, with the real dependency graph checked rather than assumed, and with the one
condition that would flip it written down now so a flip later is a decision and not a
drift.

WHAT IS IN THE TICKET
DEVELOPMENT_PLAN.md §1 already asserts V before O, "so enterprise data sources plug in
early", and notes the order can be flipped. The thing I actually want checked: Track O is
the product. The pitch in CLAUDE.md §1 is two clicks and an agent that observes you.
Track V is enterprise reach. Shipping V first means six months in with no observer, and
G2 — the one-hour session that proves the core claim — slips to 15 Jan. That may still be
right, but I want it argued, not inherited.

THE INPUT
  - DEVELOPMENT_PLAN.md §1 (the stated rationale), §2 (the dates), §3 (the E3 and E4
    ticket tables with their Depends-on columns), §4 (the critical path).
  - Check the dependency columns yourself. My reading is that only EL-301 and EL-403 cross
    between the tracks, and that EL-408's dependency on EL-301 is the single real
    constraint. Verify it and say whether the tracks are otherwise independent.
  - ARCHITECTURE.md on Tracks V and O, for what each gate actually proves.
  - CLAUDE.md §1, for what the product is supposed to be.

THE RESULT I WANT TO SEE
1. decisions/EL-005-track-order.md.
2. A dependency finding stated flatly: which E4 tickets truly depend on an E3 ticket, and
   which do not. If the only cross-track edge is EL-301, say that the tracks are
   independent after it and that the order is therefore a priority call, not a technical
   one. That reframes the whole decision and I want it stated in one line.
3. Both orders costed from the §2 dates: what moves, and by how many weeks, under V-first
   versus O-first. Include where G2 lands in each case.
4. The flip condition, as a single testable sentence, naming who observes it and when.
   Something I can hold up at Gate 1 and check.
5. A recommendation, including disagreement with the table if that is where the evidence
   points, and the one thing that would make you wrong.
6. No code. No timeline edit to DEVELOPMENT_PLAN.md in this ticket — propose the edit in
   ## Follow-up and let me apply it.
````

---

## EL-006 — DB driver policy

**Blocks:** EL-308 · **Recommendation:** subprocess CLI, with no driver dependencies

````text
WHAT I WANT
Pin how EvalLoop reaches Postgres and MySQL, given that CLAUDE.md allows standard library
only and psycopg and mysqlclient are therefore both out. Write the policy now, four months
before EL-308, including an honest account of what the chosen approach cannot do. No
implementation — that is EL-308's job, and MCP-era code is out of scope in M0.

WHAT IS IN THE TICKET
The recommendation is to shell out to the psql and mysql CLIs and ship no drivers. sqlite3
is in the standard library, so EL-306 is unaffected. The things I want pinned, because
EL-308's "done when" says a missing CLI must yield UNAVAILABLE rather than a crash:
how absence is detected, how read-only is enforced, and how results are parsed.

THE INPUT
  - CLAUDE.md §3: standard library only in shipped code; NumPy is the only external
    dependency ever permitted.
  - DEVELOPMENT_PLAN.md §3 E3: EL-305 (read-only envelope + audit log, "DROP TABLE
    rejected before it is sent"), EL-306 (Connector protocol with probe / describe / read),
    EL-308 (Postgres + MySQL via CLI), EL-304 (production-suspected hosts default to deny).
  - ARCHITECTURE.md on the connector layer and the capability broker, for where the
    envelope sits relative to the driver.

THE RESULT I WANT TO SEE
1. decisions/EL-006-db-driver-policy.md.
2. A table of the three options — subprocess CLI, bundled pure-Python wire protocol,
   permit a driver as a second external dependency — with what each costs and what it buys.
   Include the honest third option; I want to see it rejected on the record, not omitted.
3. For the chosen option, these five answered concretely, each in two or three sentences:
   - how a missing CLI is detected, and the exact UNAVAILABLE message shape, naming the
     binary and how to install it;
   - how read-only is enforced, and at which layer — the envelope (EL-305), the connection
     string, a server-side read-only transaction, or all three. Say which one is the real
     guarantee and which are defence in depth;
   - how identifiers and values reach the CLI without shell injection, given there are no
     prepared statements;
   - the output format parsed, and what breaks on NULL versus empty string, on embedded
     delimiters, and on types that arrive as text;
   - how credentials reach the subprocess without landing in a process listing or in the
     EL-402 redactor's path.
4. A "what this forecloses" list: typed results, prepared statements, connection pooling,
   streaming large results, and anything else the CLI route gives up. EL-311's SQL
   validator depends on execution match, so say plainly whether text-formatted CLI output
   is good enough to compare two result sets, and how.
5. The trigger that would reopen this decision, in one sentence.
6. No code, no new dependency in pyproject.toml.
````

---

## EL-007 — MCP implementation

**Blocks:** EL-301 · **Recommendation:** standard-library JSON-RPC, no SDK

````text
WHAT I WANT
Pin the MCP approach and, more importantly, the isolation boundary, so that the risk named
in DEVELOPMENT_PLAN.md §5 — the spec changing mid-build — costs one module and not three
tracks. A design note and a decision, not an implementation. M0 forbids MCP code.

WHAT IS IN THE TICKET
The recommendation is JSON-RPC 2.0 over stdio and HTTP, written against the standard
library, with no SDK, which CLAUDE.md §3 makes mandatory rather than optional ("no
third-party frameworks or wrappers anywhere"). So the open questions are not whether, but:
which spec version, which subset of methods, and where the seam is. EL-301 feeds EL-307
(MCP client connector), EL-408 (gateway) and EL-703 (server), which is three consumers of
one module across three tracks.

THE INPUT
  - CLAUDE.md §3: no frameworks, standard library only.
  - DEVELOPMENT_PLAN.md §3: EL-301 ("handshake, tool listing and calls work against a
    reference MCP server"), EL-307, EL-408, EL-703 (the five server methods:
    report_intent, plan, evaluate, verify_claim, findings).
  - DEVELOPMENT_PLAN.md §5: "MCP spec changes during the build -> isolate the protocol in
    EL-301."
  - ARCHITECTURE.md on the MCP gateway and the coding-agent integration.
  - The MCP specification itself, for the current revision and the method names. Cite the
    revision you read and its date; do not write method names from memory.

THE RESULT I WANT TO SEE
1. decisions/EL-007-mcp-implementation.md.
2. The spec revision pinned by date or version string, with the source cited. Then the
   method subset we implement, as a table: method | client, server, or both | which ticket
   needs it. Anything in the spec not in that table is explicitly out, listed under a
   "deliberately not implemented" heading.
3. The seam, described in one paragraph plus a signature sketch: the names and types of the
   boundary that EL-307, EL-408 and EL-703 are allowed to touch, and the statement that
   nothing outside evalloop's protocol module may know the wire format. The test of this
   design is one sentence: if the spec revs, which files change? Answer it.
4. Both transports addressed: stdio framing, and the HTTP transport including whether we
   need streaming. If only one is needed before Gate V, say which, and defer the other to a
   named ticket.
5. A statement of what writing this ourselves costs, honestly: spec drift, auth,
   capability negotiation, and the error taxonomy. The decision is forced by CLAUDE.md, so
   the point of this section is to size the work for EL-301's 2-day estimate and say
   whether that estimate survives.
6. No code in evalloop/. The signature sketch lives in the decision record.
````

---

## EL-008 — MCP server timing

**Blocks:** EL-703 · **Recommendation:** after G3

````text
WHAT I WANT
Confirm or reject gating the MCP server (EL-703) behind Gate 3, and turn the reasoning into
a precondition list I can check at G3 instead of a principle I have to re-argue.

WHAT IS IN THE TICKET
DEVELOPMENT_PLAN.md §1 gives the reason in one line: "An agent iterating against a noisy
grader learns to game it." EL-703 is already placed in E7, after G3 and after G4. So the
decision is nearly made by the plan's structure. What is missing is the checklist: what,
specifically, must G3 have demonstrated before an external agent is allowed to call
evaluate and verify_claim in a loop. I also want the cost of waiting stated, because
EL-704's agent-fixes-code-unprompted moment is the most compelling thing in the plan and it
sits behind this.

THE INPUT
  - DEVELOPMENT_PLAN.md §1 (the rationale), §3 E5 (what G3 consists of: EL-501 readiness
    gate, EL-502 noise floor, EL-503 per-item diff, EL-504 diagnostics, EL-506 self-canary,
    EL-507 the gate itself), §3 E7 (EL-703, EL-704, EL-705 anti-Goodhart guards).
  - AGENT.md, for the pipeline the server exposes.
  - CLAUDE.md §1, for the two-clicks promise and whether an MCP server is even on the
    critical path to it.

THE RESULT I WANT TO SEE
1. decisions/EL-008-mcp-server-timing.md.
2. A precondition checklist, each item a yes/no question answerable at G3 from evidence,
   naming the EL ticket that satisfies it. Four to six items. Example of the shape I want,
   not the content: "Does the noise floor from EL-502 refuse a within-noise delta on a
   real run? EL-502, EL-507." This list is the actual deliverable.
3. The failure mode spelled out concretely: what gaming looks like if the server ships
   early, how it would appear in the results, and why EL-705's guards are not sufficient on
   their own to allow it sooner.
4. The cost of waiting: what we do not learn between G1 and G3 that only an agent in the
   loop teaches us. Then say whether any slice of EL-703 — read-only methods such as plan
   and findings, which cannot be gamed because they grade nothing — could ship earlier
   behind a flag. If yes, name the subset and the ticket; that is the useful half of this
   decision.
5. A decision line that is Accepted or Rejected, not Deferred.
6. No code.
````

---

## EL-009 — Shell capture mechanism

**Blocks:** EL-413 · **Recommendation:** zsh precmd hook plus commands the agent reports

````text
WHAT I WANT
Pin how the command sensor sees what the developer ran, with the privacy boundary and the
degradation path written down before anyone installs a hook into my shell. A decision and
an install design, no code: EL-413 is in Track O and CLAUDE.md bans sensors in M0.

WHAT IS IN THE TICKET
The recommendation is a zsh precmd hook plus whatever commands the coding agent reports
through its own channel, the two together covering both the human's terminal and the
agent's. EL-413's "done when" is that a failing pytest lands on the bus with its exit code.
What the recommendation does not yet settle: what a shell hook is allowed to capture, what
happens on bash or fish, and what happens when the hook is not installed. A sensor that
silently captures nothing is worse than one that refuses to start.

THE INPUT
  - DEVELOPMENT_PLAN.md §3 E4: EL-401 (Event + Sensor protocols), EL-402 (redactor:
    secrets, PII, .env, "planted secrets replaced with stable placeholders"), EL-403
    (intent bus with spool, dedupe, crash-resume), EL-413 (command sensor), EL-420 (Trust
    Center: toggles, grants, spend, pause, "pause stops all sensors within one tick").
  - ARCHITECTURE.md on the sensor layer and the intent bus.
  - USER_EXPERIENCE.md, for what the developer is told is being captured. The two-clicks
    promise and a shell hook are in tension; say how it is resolved in the UI.
  - The environment: this is a zsh machine on darwin. State the assumption explicitly
    rather than relying on it.

THE RESULT I WANT TO SEE
1. decisions/EL-009-shell-capture.md.
2. The mechanism, concretely: which zsh hooks, and the exact field list captured per
   command — command string, exit code, cwd, start time, duration, and anything else —
   with a one-line reason for each field. A field with no eval use case does not get
   captured.
3. The never-captured list, and where it is enforced: environment variables, anything
   matching a secret pattern, anything under a path the Trust Center excluded, and stdout
   and stderr unless you argue otherwise. Say whether redaction happens in the hook, before
   the bus, or in EL-402, and which of those is the real guarantee if the others fail.
4. The install and uninstall story: what is written to which rc file, how the user sees
   that it was installed, how pause (EL-420) actually stops capture within one tick given
   that the hook lives outside our process, and how uninstall leaves the rc file clean.
5. The degradation matrix: zsh with hook, zsh without hook, bash, fish, a non-interactive
   shell, and a shell started before EvalLoop. For each, what the sensor does. The rule to
   apply: never silently capture nothing — either capture, or announce that it is not
   capturing.
6. How the agent-reported half is reconciled with the hook half: the same pytest run seen
   by both must not become two episodes. Name the dedupe key and say which source wins.
7. No code, and nothing written to any rc file in this session.
````

---

## EL-010 — Is Track X in scope?

**Blocks:** E9 · **Recommendation:** out, unless G2 shows gaps in intent capture

````text
WHAT I WANT
Put Track X (the screen sensor) out of scope, and replace the soft escape hatch "unless G2
shows gaps" with a measurable trip-wire defined now — before G2, while nobody has an
interest in the answer — plus the deletion criterion for the track.

WHAT IS IN THE TICKET
E9 is already marked optional and gated on EL-010. EL-905 is a spike whose done-when is
"yes/no with numbers. If no, delete the track", which is the right instinct but has no
number attached and no baseline to compare against. "Shows gaps in intent capture" is not
yet a thing anyone can measure at G2. That is what I want fixed. Note the constraint that
makes this easy to get wrong: CLAUDE.md forbids inventing numbers. That rule is about
methodology thresholds copied from the corpus; a product trip-wire is a choice I am making,
so if you propose a number, label it as a product choice with its reasoning, and never
present it as corpus-sourced.

THE INPUT
  - DEVELOPMENT_PLAN.md §3 E9 (EL-901 to EL-905) and §2 (E9 sits after 9 Apr 2027).
  - DEVELOPMENT_PLAN.md §3 E4: EL-415 classifier upgrade ("10 episodes classified;
    'unclear' plans nothing") and EL-421 Gate 2 ("accurate timeline + useful report, zero
    config"). The 'unclear' rate at EL-415 is the obvious candidate metric; check whether
    it is measurable as specified.
  - ARCHITECTURE.md on Track X and on what the other sensors already capture.
  - USER_EXPERIENCE.md and CLAUDE.md §1, for how a screen sensor reads against a tool whose
    whole pitch is two clicks and trust.

THE RESULT I WANT TO SEE
1. decisions/EL-010-track-x-scope.md, with ## Decision reading as out of scope.
2. The trip-wire, as a named metric with a definition I can compute at G2: what is counted,
   over what denominator, measured on which artifact. If it is the 'unclear' episode rate
   from EL-415, define numerator and denominator exactly and confirm EL-415 as specified
   actually produces them; if it does not, say what EL-415 must additionally record, and
   put that in ## Follow-up as a one-line amendment to that ticket.
3. The threshold, with its status stated: either a number labelled "product choice, chosen
   because X", or "to be set at G2 from the observed baseline, by this rule". Both are
   acceptable; an unlabelled number is not.
4. The second half of the trip-wire, which matters more: even if intent capture has gaps,
   screen capture must be the cheapest fix. So state what else would be tried first —
   EL-412's second agent adapter, EL-406's transcript adapter, EL-413's command sensor —
   and say Track X comes back only after those are exhausted. Name them.
5. The deletion criterion, written now: what EL-905 must show for the track to live, and
   the explicit instruction to delete EL-901 to EL-904 otherwise.
6. One short paragraph on the trust cost, for USER_EXPERIENCE.md: what asking for screen
   access does to a tool asking for two clicks, and whether any trip-wire outcome justifies
   it. If your view is that the track should be struck entirely rather than deferred, say
   so and argue it.
7. No code. No new directory.
````

---

## Tracking

| Key | Deliverable | Code change in this ticket? | Blocks |
|---|---|---|---|
| EL-001 | `decisions/EL-001-corpus-location.md` | Yes — conftest, tests, CLAUDE.md §4, TASKS.md | EL-103, EL-113 |
| EL-002 | `decisions/EL-002-mcp-tools-in-enum.md` | Only if the answer is yes — `vocab/tools.py` | EL-104 |
| EL-003 | `decisions/EL-003-new-situations.md` | Only for candidates that pass — `vocab/situations.py` | EL-103 |
| EL-004 | `decisions/EL-004-claude-md-corpus-gaps.md` | Yes — CLAUDE.md §4 and §6 | EL-113 |
| EL-005 | `decisions/EL-005-track-order.md` | No | E3, E4 |
| EL-006 | `decisions/EL-006-db-driver-policy.md` | No | EL-308 |
| EL-007 | `decisions/EL-007-mcp-implementation.md` | No | EL-301 |
| EL-008 | `decisions/EL-008-mcp-server-timing.md` | No | EL-703 |
| EL-009 | `decisions/EL-009-shell-capture.md` | No | EL-413 |
| EL-010 | `decisions/EL-010-track-x-scope.md` | No | E9 |
