# EL-009 — Shell capture mechanism for the command sensor

## Decision

**Accepted with two corrections to the recommendation.**

Command capture is a **paired `preexec` + `precmd` zsh hook**, not `precmd` alone, plus the agent-reported channel. Six fields are captured per command and nothing else. **The hook captures no stdout or stderr at all** — which the recommendation left open and `ARCHITECTURE.md:406` currently implies otherwise.

The hook is **opt-in, one-time, and never required**: EvalLoop works without it, so it is offered through the existing permission-request flow when a technique would benefit, not demanded at setup. Where it is absent or unsupported, the sensor **announces** itself as UNAVAILABLE with a reason in the Plan view. It never silently captures nothing.

## Status

Accepted — decision and install design, no code — 2026-10-06. Nothing was written to any rc file in this session, and `~/.zshrc` was neither read nor modified.

EL-413 is in Track O and `CLAUDE.md §2` bans sensors in M0, so this is design-ahead only.

### Environment assumption, stated rather than relied on

This decision was written for **zsh on macOS (darwin)**, which is the machine it was written on: the session reports `Shell: zsh`, `Platform: darwin`, `Darwin 25.6.0`. zsh has been the macOS default login shell since Catalina, which is why it is the first and only shell EL-413 supports.

Two consequences of making the assumption explicit. The matrix below gives bash, fish and non-interactive shells real answers rather than treating them as edge cases. And `preexec`'s argument semantics and the availability of `zsh/datetime` must be **verified against the zsh version on the target machine at EL-413**, not taken from this document — they determine exactly what the command-string field contains.

## The mechanism

### Why `precmd` alone is not enough

`precmd` runs before each prompt, so it can read the exit code of the command that just finished, but it cannot see **what that command was**. Recovering it from history is fragile and wrong in a specific way: history records what was *entered*, including lines that were never executed, and it is subject to `HIST_IGNORE_SPACE` and friends. `preexec` runs after a command is read and before it executes, and receives the command line as an argument.

So the mechanism is the pair: `preexec` records the command and a start timestamp into shell-local variables; `precmd` reads `$?` immediately, computes the duration, and emits one event. Both are registered through the supported API (`autoload -Uz add-zsh-hook`), never by assigning to the hook functions directly, so EvalLoop composes with any other tool the developer already has in those hooks — a prompt theme, `direnv`, anything.

`precmd` must read `$?` as its very first action, before any other command in the hook body overwrites it. That is the single most common way an implementation of this silently reports zero for everything.

### The captured fields

Six, each with a use. A field with no eval use case is not captured.

| Field | Why it exists |
|---|---|
| `command` (string, truncated, redacted downstream) | Identifies the command *class* — a test run, a build, a migration — which is what the EL-415 classifier and the `test_runner` evidence path consume |
| `exit_code` | EL-413's done-when, and the cheapest "it's broken" truth in the system |
| `cwd` (realpath) | Associates the command with a repo or sub-project; without it a `pytest` in an unrelated checkout pollutes the episode |
| `started_at` (session clock) | Causal ordering against file edits and prompts — the Intent Bus exists to order prompt ↔ edit ↔ command, per `ARCHITECTURE.md:18` |
| `duration_ms` | Separates a 0.2 s collection error from a 90 s real run, and feeds the `Timeout = INCONCLUSIVE` rule at `AGENT.md:199` |
| `shell_id` (per-shell, random at source time) | Two terminals running `pytest` are two events, not one; also the dedupe key's scope |

Deliberately not captured, each because it has no eval use case: hostname and username; TTY; the full `argv` array, since the string is what classification needs; git HEAD, which EL-405's git sensor already owns and which would cost a subprocess on every prompt; and command history from before the session started.

### Why the hook captures no output

`ARCHITECTURE.md:406` describes O9 as "shell wrapper / hook capturing command, exit code, **truncated output**". Output is the right thing to want and the wrong place to take it.

A `preexec`/`precmd` hook cannot see stdout or stderr. Obtaining them requires wrapping or tee-ing the user's command, which changes its behaviour: it breaks TTY detection, so programs disable colour and progress bars; it interferes with pagers and interactive prompts; and it makes EvalLoop a participant in every command the developer runs rather than an observer of them. `ARCHITECTURE.md:113` sets the boundary for S2 as "a shell wrapper or hook, **not a keylogger**", and reading the output of everything the developer runs is nearer the second than the first.

It is also unnecessary, because EvalLoop has two better paths to the same information. It runs tests itself in the sandbox (M1), where it owns the process and captures output legitimately. And the agent-reported channel already carries results the agent has in hand. So output arrives through sources that do not require instrumenting the human's terminal, and `ARCHITECTURE.md:406` should be amended to say so.

## What is never captured, and where that is enforced

| Never captured | Enforced where |
|---|---|
| Environment variables | **The hook**, by never reading them. There is no code path that touches `environ` |
| stdout / stderr | **The hook**, by construction — see above |
| Any command run while no session is active | **The hook**: it checks for the session sentinel first and returns immediately if absent |
| Any command whose `cwd` is outside the watched root | **The hook**: an inclusion test on realpath, before anything is written |
| Any command under a path the Trust Center excluded | **The hook** reads the exclusion list from the session sentinel directory |
| Secrets inside the command string (`--password=…`, an inline API key) | **EL-402**, the redactor |

### Which layer is the real guarantee

The two layers guard different things, and conflating them is how privacy designs fail.

**For anything that must never be collected, the hook is the only guarantee**, because nothing downstream can redact what it never received. Environment variables, output, and commands typed outside the watched repo are protected by *not leaving the shell*. That is the stronger form of protection and it is why the inclusion test lives at the source rather than at the bus.

**For data that must be transmitted, EL-402 is the real guarantee.** The command string has to cross the boundary to be useful, and it may contain a secret inline. The hook cannot be trusted to find it: entropy analysis in a shell function would be slow on every prompt, fragile, and would create a false sense of safety. So the hook performs **no content inspection at all** — only inclusion by session and path, plus a length truncation so a pasted blob is not shipped — and all content redaction is EL-402's, which `ARCHITECTURE.md:134` already places "before anything is buffered or persisted", producing the stable `<SECRET:hash>` placeholders.

The residual risk is an unredacted command string in flight between hook and redactor. It is bounded by the transport never leaving the machine: the hook appends to a local spool file at mode `0600`, with no network and no remote endpoint, so "in flight" means "in a file owned by the user, for milliseconds".

### The transport, because it constrains the privacy story

The hook appends one JSON line to a per-session spool under `~/.evalloop/run/<session>/commands.jsonl`, using zsh builtins only. This matters for three reasons beyond privacy: it **forks no process**, so it cannot slow or hang the developer's prompt, which is the fastest way to get a shell hook uninstalled in anger; it cannot block if EvalLoop is not running; and an append-only JSONL spool is exactly what EL-403 already specifies for dedupe, offset commit and crash-resume, so the sensor inherits that machinery instead of duplicating it.

## Install and uninstall

### What is written, and where

One block, in `${ZDOTDIR:-$HOME}/.zshrc` — respecting `ZDOTDIR`, since writing to `$HOME/.zshrc` on a machine that sets it would silently do nothing:

```zsh
# >>> evalloop >>>
[ -f "$HOME/.evalloop/shell/evalloop.zsh" ] && source "$HOME/.evalloop/shell/evalloop.zsh"
# <<< evalloop <<<
```

Three lines, never more. All logic lives in `~/.evalloop/shell/evalloop.zsh`, so every subsequent update ships by replacing that file and **the rc file is written exactly once, ever**. The sentinel comments make the block machine-removable, and the `[ -f ]` guard means a deleted EvalLoop leaves a shell that still starts cleanly rather than printing an error on every new terminal.

Before editing, the rc file is copied to `.zshrc.evalloop-backup-<timestamp>` in the same directory.

### How the user sees it

Installation is never silent and never implicit in `evalloop start`. `evalloop shell install` prints the target path, the exact three lines, and the backup location, then asks for confirmation. This is the product's most invasive action and it should read like one.

Afterwards it is visible in three places: the Trust Center (EL-420) lists "Command capture — on · zsh hook in `~/.zshrc` · [uninstall]"; the Plan view shows a one-time note on the first session after install; and the session report records that the command sensor was active.

The offer itself goes through the existing flow rather than a new one. `USER_EXPERIENCE.md:34` already has permission requests appearing "only when a technique needs a tool the agent doesn't have", with one click to allow or deny and "Denied → technique moves to UNAVAILABLE with the reason". A shell hook is that, with a higher stake, so it is requested when a technique would actually use it and declined cleanly if not wanted.

### Pause, within one tick, from outside our process

The hook runs in the developer's shell, so EvalLoop cannot signal it. Pause therefore has to be enforced **on the shell side**, and the mechanism is the sentinel the hook already checks: `precmd` reads the session sentinel directory before emitting, and pause removes it. The hook **fails closed** — no sentinel, no event — so the next command after pause is not captured.

One honest nuance, because "within one tick" needs a definition for an out-of-process sensor. A command already executing when pause is pressed has been seen by `preexec` but not yet reported, and `precmd` re-checks the sentinel before emitting, so that command is **dropped rather than reported**. EvalLoop also discards events arriving for a paused session, as a second layer. So pause takes effect before the next capture *and* suppresses the one in flight, which is the strongest available reading of EL-420's "pause stops all sensors within one tick" — and EL-420's done-when should say this rather than leave it to be discovered.

### Uninstall

`evalloop shell uninstall` removes the sentinel block and deletes `~/.evalloop/shell/`, and is idempotent. If the sentinels are missing or the block has been edited by hand, it **does not guess**: it prints the lines it expected and the file to edit, and exits non-zero. Silently rewriting a developer's rc file on a fuzzy match is worse than asking.

## The degradation matrix

The governing rule: never silently capture nothing. The mechanism that enforces it is a **`shell_attached` heartbeat** — the hook emits one event on its first prompt in a session. If the bus has not seen a heartbeat, the command sensor declares itself UNAVAILABLE rather than appearing to work. This reuses the Plan view's existing four states (`USER_EXPERIENCE.md:51`) and principle 3, "Every 'no' has a reason" (`USER_EXPERIENCE.md:92`).

| Situation | What the sensor does |
|---|---|
| **zsh, hook installed, session active** | Full capture of the six fields. Heartbeat on first prompt |
| **zsh, hook not installed** | No capture. Plan view: `UNAVAILABLE  command_sensor  missing: shell hook — run 'evalloop shell install'`. EvalLoop's own sandbox runs still supply test evidence, so the session degrades rather than fails |
| **bash** | Not supported by EL-413, and said so by name: `UNAVAILABLE  command_sensor  bash not supported yet (EL-423)`. bash has no `preexec`; the equivalent is `trap DEBUG` plus `PROMPT_COMMAND`, which fires per pipeline element and needs its own design. Deferred to **EL-423**, not bodged in |
| **fish** | Not supported: `UNAVAILABLE  command_sensor  fish not supported yet (EL-424)`. fish has no POSIX rc file and uses `fish_preexec`/`fish_postexec` events, so it is a separate install path. Deferred to **EL-424** |
| **non-interactive shell** (script, CI, `sh -c`) | `preexec`/`precmd` never fire, and nothing *should* be captured: there is no human terminal to observe. Reported as **not applicable** rather than unavailable, which is a different message and a different meaning — the evidence comes from EvalLoop's own runs |
| **shell started before the hook was installed** | That shell never sourced the hook, so no heartbeat arrives and the sensor announces: `UNAVAILABLE  command_sensor  no shell attached — open a new terminal, or run 'source ~/.evalloop/shell/evalloop.zsh'`. A shell opened *before `evalloop start`* but *after install* works normally, because it finds the session sentinel when the session begins |

The distinction in the last two rows is the point of the matrix. "Unavailable" means *something is wrong and here is the fix*; "not applicable" means *there is nothing here to capture*. Collapsing them would either cry wolf in CI, which `USER_EXPERIENCE.md:14` warns is fatal for this persona, or stay quiet about a broken install.

## Reconciling the hook and the agent-reported halves

The same `pytest` run can be seen twice: once by the hook, once by the agent reporting through EL-409's gateway recorder. It must become one episode.

**Dedupe key:** `(session_id, cwd_realpath, normalised_command, exit_code, started_at within a bounded window)`.

Normalisation strips leading and trailing whitespace and collapses runs of internal whitespace; it does **not** reorder arguments, because order changes meaning. The time window is left unnumbered on purpose: it must exceed the measured clock skew between the agent's reported timestamp and the shell's, and EL-413 should set it from that measurement rather than from a guess here.

**Which source wins: neither, on everything — they are authoritative for different fields.**

- **The hook is authoritative for `exit_code`, `duration_ms` and timing.** It observes actual process completion in the real shell. The agent reports what it believes happened, and the corpus's A2 row exists precisely because that is not the same thing — `A-choosing-how-to-grade.md:77` makes claim–state mismatch a tracked metric with a launch-blocking threshold.
- **The agent is authoritative for intent linkage,** and may supply output. It knows *why* it ran the command and which artifacts the run relates to, which the hook cannot know.

The merged event keeps both provenances, which `ARCHITECTURE.md:398` already provides for, since `Event` carries `provenance` and `confidence`.

**The important rule: dedupe must not erase disagreement.** If the agent reports a passing suite and the hook's exit code is non-zero, that conflict is not a reconciliation problem — it is evidence, and it is exactly the material EL-702's claim verifier exists to act on. The dedupe path must therefore emit a conflict marker rather than let the agent's version win by arriving first. A deduplicator that quietly prefers one source would destroy the signal the whole of Track L is built to detect.

## Consequences

- **`ARCHITECTURE.md:406` needs amending.** "Capturing command, exit code, truncated output" is not achievable from a shell hook without wrapping the developer's commands; output comes from EvalLoop's own runs and the agent channel instead.
- **EL-420's done-when needs the pause semantics spelled out.** "Pause stops all sensors within one tick" is satisfied by a fail-closed sentinel check plus dropping the in-flight command, and that is worth stating because an out-of-process sensor cannot be stopped any other way.
- **Two new tickets** are named so the matrix has no silent gaps: EL-423 (bash) and EL-424 (fish). Both are genuinely deferred, not implied.
- **No `Tool` enum member is needed.** A shell hook is a transport for observing commands, not a capability a technique requires — the same test `decisions/EL-002-mcp-tools-in-enum.md` applied to MCP. The command sensor's availability is sensor state surfaced in the Plan view, not a `required_tools` entry.
- **The two-clicks promise survives, but only because capture is optional.** Install is one-time setup, not per-session, so it does not add a click to any session. The real resolution of the tension with `USER_EXPERIENCE.md:90` ("Invisible by default. No config files") is that EvalLoop must remain useful *without* the hook — filesystem, git, transcripts and its own sandbox runs — so the hook is an enhancement offered on demand. If any technique ever hard-requires it, this decision should be revisited, because at that point the product does require editing a developer's rc file.
- **`USER_EXPERIENCE.md:113` (§6, open UX questions) should gain this one and record its answer,** since "do we edit the user's shell config, and how is that disclosed" is a larger UX question than any currently listed there.

## Reopen trigger

> **This decision reopens if a technique's evidence cannot be obtained without the hook — making optional capture a fiction — or if the `preexec`/`precmd` pair proves unable to attribute commands reliably on the target zsh version, observed by the engineer at EL-413 and reported at Gate 2.**

## Follow-up — proposed, not applied

1. **`DEVELOPMENT_PLAN.md:94`** — update the EL-009 row to "✅ Decided: paired `preexec`+`precmd` zsh hook (not `precmd` alone) + agent-reported channel; no output capture; opt-in with announced degradation — `decisions/EL-009-shell-capture.md`".
2. **`DEVELOPMENT_PLAN.md:179`** — extend EL-413's done-when: "Failing `pytest` lands on the bus with its exit code; with no hook installed the sensor reports UNAVAILABLE with the install command, never silence".
3. **`DEVELOPMENT_PLAN.md:186`** — extend EL-420's done-when with the pause semantics above.
4. **New rows in E4** — EL-423 "Command sensor: bash (`trap DEBUG` + `PROMPT_COMMAND`)" and EL-424 "Command sensor: fish (`fish_preexec`/`fish_postexec`)", both depending on EL-413.
5. **`ARCHITECTURE.md:406`** — strike "truncated output" from O9 and note where output actually comes from.
6. **`USER_EXPERIENCE.md:113`** — add the shell-hook disclosure question and record this decision as its answer.

## Related

- `ARCHITECTURE.md:113` — the S2 row that sets the boundary ("a shell wrapper or hook, not a keylogger") and `ARCHITECTURE.md:484` — "Keylogging. S2 captures commands, not keystrokes", which is the non-goal this design is measured against.
- `ARCHITECTURE.md:134` — the redactor at the sensor boundary, which is why content inspection is not the hook's job.
- `USER_EXPERIENCE.md:34, 51, 90-95` — the permission-request flow, the Plan view's UNAVAILABLE state, and the UX principles the degradation matrix is built on.
- `decisions/EL-002-mcp-tools-in-enum.md` — the capability-versus-transport test applied here to keep the shell hook out of the `Tool` enum.
