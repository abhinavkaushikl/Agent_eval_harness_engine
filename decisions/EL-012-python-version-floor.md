# EL-012 — Python version floor

## Decision

The supported floor is **Python 3.10**, not 3.12. `mypy` is pinned to
`python_version = "3.10"` so that any stdlib API newer than the floor is a type error
rather than a runtime surprise, and `enum.StrEnum` — the one 3.11+ API the M0 design
actually depends on — is replaced by a single back-compatible base class in
`evalloop/_compat.py`.

## Status

Accepted — 2026-10-07.

## Context

`CLAUDE.md` section 3 listed Python **3.12+** as a hard constraint. Nothing in the M0
design needed it. Auditing every version-bearing claim in the repo turned up exactly one
3.11+ API in the specification — `enum.StrEnum`, named in `CLAUDE.md` section 6 and in
`TASKS.md` S3, S4 and S7 — and no 3.12 API at all. The floor was therefore two minor
versions above anything the project used.

The cost of moving it is at its minimum right now. M0 ships four `__init__.py` docstrings;
`evalloop/` contains no executable code. Once EL-103 lands, every vocabulary enum inherits
from whatever base is chosen here, and once EL-110 to EL-117 land, 73 record files depend
on those enums' spelling and rendering. Once M1 and M2 land, the sandbox, poller,
orchestrator and SQLite store will each have reached for a 3.11 or 3.12 convenience unless
something stops them.

Raising a floor later is a version bump. Lowering one later is an audit of every module
written in the meantime.

## Options considered

| Option | Cost | What it buys | Why not |
|---|---|---|---|
| **A. Keep 3.12+** | None today | The newest stdlib: `enum.StrEnum`, `asyncio.TaskGroup`, `hashlib.file_digest`, `sqlite3` autocommit | Excludes 3.10 and 3.11 for no stated reason. A tool meant to be pointed at someone else's repo should not be fussier about its own interpreter than the repos it evaluates. |
| **B. Floor 3.10, branch on `sys.version_info`** | One branch, two code paths | Idiomatic `enum.StrEnum` where available | The vocabulary enums would rest on a *different* base class per interpreter. A behavioural difference between the two shows up as a matching bug on one machine and not another — the exact silent-failure mode `CLAUDE.md` section 6 exists to prevent. Also doubles what the test suite must cover. |
| **C. Floor 3.10, one compat base class** ✅ | One ~15-line class, one test file | 3.10–3.13+ on a single code path; deterministic across versions per `CLAUDE.md` section 7.8 | Chosen. |
| D. Floor 3.9 | Real syntax loss | One more version of reach | 3.10 brought `match`, PEP 604 `X | Y` in evaluated annotations, and `dataclass(slots=True)`. 3.9 would cost working syntax, not just a shim. The floor stops at 3.10. |

## Consequences

**Easy:** the project installs on any interpreter from 3.10. The constraint enforces
itself — `mypy --strict evalloop/` runs against typeshed's 3.10 view, so reaching for a
newer API fails the existing done-when gate with no new tooling.

**Harder:** later milestones must avoid conveniences that do not exist at the floor. The
list below is the whole cost of this decision, and it is why the list is written here
rather than discovered per-ticket:

| API | Added | Use instead | Bites at |
|---|---|---|---|
| `enum.StrEnum` | 3.11 | `evalloop/_compat.StrEnum` | EL-103, EL-104, EL-107 |
| `contextlib.chdir` | 3.11 | `os.chdir` in `try`/`finally` | T11 sandbox (EL-206) |
| `hashlib.file_digest` | 3.11 | read in chunks into `hashlib.sha256()` | T18 poller (EL-404) |
| `asyncio.TaskGroup` | 3.11 | `asyncio.gather` | T23 orchestrator (EL-416) |
| `datetime.UTC` | 3.11 | `datetime.timezone.utc` | anything timestamped |
| `typing.Self` | 3.11 | the class name, or a `TypeVar` | any `classmethod` constructor |
| `except*` / `ExceptionGroup` | 3.11 | the loader's own aggregation | EL-108 |
| `tomllib` | 3.11 | not needed — no TOML is parsed at runtime | — |
| `sqlite3` `Connection.autocommit` | 3.12 | `isolation_level` | T8 episodic store (EL-202) |
| `itertools.batched` | 3.12 | manual slicing | any batching |
| PEP 695 `type` statement and `def f[T]()` | 3.12 | `TypeAlias`, `TypeVar` | anywhere generic |
| `@typing.override` | 3.12 | nothing | — |

**Forecloses:** nothing the design wanted. No record, technique or planner behaviour in
`knowledge rules/` or `AGENT.md` depends on an interpreter version.

**Verified once, not continuously.** The suite was executed on a real CPython **3.10.21**
on 2026-10-07 — **45 passed, 1 skipped** — in a throwaway venv, reproducible with:

```bash
uv venv --python 3.10 /tmp/v310 && uv pip install --python /tmp/v310/bin/python pytest
PYTHONPATH=. /tmp/v310/bin/python -m pytest -q
```

The single skip is `test_matches_the_stdlib_strenum_where_it_exists`, which is gated on
3.11+ by design. On 3.12.14 the same suite is 46 passed.

That is one manual run, not a standing guarantee. There is still no CI, so between runs the
only continuous guard is `mypy --strict evalloop/` against typeshed's 3.10 view, which
catches a too-new stdlib call or too-new syntax but not a runtime behavioural difference.

## Evidence

- `CLAUDE.md` section 3, pre-change: `| Python | **3.12+** |`.
- `pyproject.toml`, pre-change: `requires-python = ">=3.12"`, `python_version = "3.12"`.
- The only 3.11+ API in the specification: `CLAUDE.md` section 6 (`Situation` and `Tool`
  are `StrEnum`), `TASKS.md` S3, S4, S7. No 3.12 API is named anywhere in the design docs.
- `enum.StrEnum` is documented as "New in version 3.11"; `Enum.__format__` for mixed-in
  types changed in 3.11, which is why `evalloop/_compat.StrEnum` pins both `__str__` and
  `__format__` instead of inheriting them.
- Behavioural parity is asserted in `tests/test_compat.py`, including a side-by-side
  comparison against `enum.StrEnum` that runs on 3.11+ and skips at the floor.

## Follow-up

**Unblocks / amends:**
- `EL-103`, `EL-104`, `EL-107` — import `StrEnum` from `evalloop/_compat`, never from `enum`.
- `EL-202`, `EL-206`, `EL-404`, `EL-416` — inherit the banned-API table above.

**Code and doc changes made by this ticket:**
- `pyproject.toml`: `requires-python = ">=3.10"`, `[tool.mypy] python_version = "3.10"`.
- `evalloop/_compat.py` (new) and `tests/test_compat.py` (new).
- `CLAUDE.md` section 3 (floor + the self-enforcing mypy pin), section 5 (`_compat.py` in
  the target layout), section 6 (a note that `StrEnum` means the compat class).
- `TASKS.md` shared-context rules line, S1, S3, S4.
- `README.md`, `E0-DECISION-PROMPTS.md` section 0, `E1-M0-TICKETS-AND-PROMPTS.md` section 0
  and the EL-103 / EL-104 / EL-107 prompts.

**Open, and deliberately not closed here:** no CI exists, so the 3.10 run above has to be
repeated by hand after every change. Before "3.10+" is claimed to anyone outside this repo
it wants a CI matrix over 3.10, 3.11, 3.12 and 3.13 running `pytest` plus
`mypy --strict evalloop/`. That is a ticket, not a line in this decision. Note that 3.11
and 3.13 have never been run at all — only 3.10 and 3.12 have.
