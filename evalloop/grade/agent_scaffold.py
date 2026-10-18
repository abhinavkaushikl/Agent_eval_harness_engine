"""Write a STARTER agent eval scaffold for a file the classifier flagged as an agent.

An agent eval cannot be authored the way a unit test is (``AGENT.md`` §3.6: author from the
signature only, in isolation). Verifying an agent means checking the real **end state** it leaves
behind — a row written, a file produced — which only the developer knows the shape of. So rather
than silently ignore an agent file, the session drops a *scaffold* beside it: a valid-shaped
``agent`` spec (:mod:`evalloop.grade.specs`) with every end-state check **stubbed** and a ``TODO``,
plus instructions to fill it in.

Inert by construction. The file is named ``<stem>.agent.eval.json.scaffold``. The poller tracks
only ``*.py`` and ``*.eval.json`` (:mod:`evalloop.session.poller`), so a ``.scaffold`` is never
graded — it cannot produce a misleading verdict from its stubs. Activating it is one gesture the
file itself states: drop the ``.scaffold`` suffix, and the watcher grades it like any other spec.

Pure and deterministic: the same source yields the same bytes. This module writes nothing; the
caller owns the file. The scaffold is a template for a human, never ground truth and never run as-is.
"""

from __future__ import annotations

import ast
import json
import warnings
from dataclasses import dataclass
from pathlib import PurePosixPath

__all__ = ["SCAFFOLD_SUFFIX", "scaffold_name", "scaffold_agent_eval"]

#: Suffix that keeps the scaffold out of the graded set until the developer removes it.
SCAFFOLD_SUFFIX = ".agent.eval.json.scaffold"

#: The name the developer renames the scaffold to, to activate it.
_ACTIVE_SUFFIX = ".agent.eval.json"


def _stem(artifact_rel: str) -> str:
    name = PurePosixPath(artifact_rel).name
    return name[:-3] if name.endswith(".py") else name


def scaffold_name(artifact_rel: str) -> str:
    """The scaffold filename for an agent source file, e.g. ``agent.py`` -> ``agent.agent.eval.json.scaffold``."""
    return f"{_stem(artifact_rel)}{SCAFFOLD_SUFFIX}"


@dataclass(frozen=True, slots=True)
class _Hints:
    """What the source suggests the agent touches, used only to pick which stub checks to offer."""

    touches_db: bool
    touches_files: bool
    tables: tuple[str, ...]
    entry: str
    tools: tuple[str, ...]


def _string_literals(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _tables_from_sql(literals: list[str]) -> tuple[str, ...]:
    """Table names after FROM / INTO / UPDATE / TABLE in any string literal. Best-effort, for hints only."""
    found: list[str] = []
    keywords = {"from", "into", "update", "table"}
    for text in literals:
        words = text.replace("(", " ").replace(")", " ").replace(",", " ").split()
        for i, word in enumerate(words[:-1]):
            if word.lower() in keywords:
                candidate = words[i + 1].strip('`"[];')
                if candidate.isidentifier() and candidate.lower() not in keywords and candidate not in found:
                    found.append(candidate)
    return tuple(found[:3])


_LLM_CALL_HINT = ("messages.create", "chat.completions.create", "completions.create", "responses.create")


def _dotted(expr: ast.expr) -> str:
    parts: list[str] = []
    node: ast.expr = expr
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    parts.reverse()
    return ".".join(parts)


def _entry_guess(tree: ast.Module) -> str:
    """The top-level function that drives the agent loop — a loop containing an LLM-ish call. Else 'chat'."""
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for loop in ast.walk(node):
            if not isinstance(loop, (ast.For, ast.AsyncFor, ast.While)):
                continue
            for call in ast.walk(loop):
                if isinstance(call, ast.Call) and (
                    any(_dotted(call.func).endswith(s) for s in _LLM_CALL_HINT)
                    or any(kw.arg in {"tools", "tool_choice"} for kw in call.keywords if kw.arg)
                ):
                    return node.name
    return "chat"


def _tool_names(tree: ast.Module) -> tuple[str, ...]:
    """Keys of a top-level ``TOOLS = {...}`` dict, which is the common tool registry shape."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in node.targets):
                return tuple(
                    k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
                )
    return ()


def _hints(source: str) -> _Hints:
    """Read the source to decide which stub checks are worth offering. Never executes it."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return _Hints(False, False, (), "chat", ())
    literals = _string_literals(tree)
    touches_db = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"execute", "executemany", "executescript"}
        for n in ast.walk(tree)
    ) or any("sqlite" in lit.lower() for lit in literals)
    touches_files = any(
        (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open")
        or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"write_text", "write_bytes"})
        for n in ast.walk(tree)
    )
    return _Hints(touches_db, touches_files, _tables_from_sql(literals), _entry_guess(tree), _tool_names(tree))


def _db_checks(tables: tuple[str, ...]) -> list[dict[str, object]]:
    table = tables[0] if tables else "TODO_table"
    return [
        {
            "type": "rows_equal",
            "name": "the record the agent was asked to create exists",
            "sql": f"SELECT * FROM {table} WHERE id = 'TODO'",
            "expected": [["TODO"]],
            "_todo": "replace sql + expected with the exact row(s) the agent should have written",
        },
        {
            "type": "no_rows",
            "name": "nothing the agent should not have touched",
            "sql": f"SELECT * FROM {table} WHERE TODO",
            "_todo": "a query that must return zero rows if the agent behaved; delete if not needed",
        },
    ]


def _file_checks() -> list[dict[str, object]]:
    return [
        {
            "type": "file_exists",
            "name": "an output the agent should produce",
            "path": "TODO/output.txt",
            "_todo": "path, relative to 'root', the agent must create",
        },
        {
            "type": "file_contains",
            "name": "that output has the expected content",
            "path": "TODO/output.txt",
            "text": "TODO",
            "_todo": "a substring the produced file must contain; delete if not needed",
        },
    ]


def scaffold_agent_eval(artifact_rel: str, source: str) -> str:
    """The text of a starter eval for an agent at ``artifact_rel``. Stubbed, inert, deterministic.

    Picks the honest shape from what the file touches: an agent with a DB/file side effect gets an
    **end-state** ``agent`` spec; a side-effect-free chat/tool agent gets a **behavioural**
    ``agent_behavior`` spec (graded by its trajectory against a scripted stand-in LLM — no API key).
    Either way it is written with a ``.scaffold`` suffix so it is never graded until activated.
    """
    hints = _hints(source)
    if hints.touches_db or hints.touches_files:
        return _end_state_scaffold(artifact_rel, hints)
    return _behaviour_scaffold(artifact_rel, hints)


def _activate_note(artifact_rel: str) -> str:
    return (
        f"Fill in every TODO below, then rename this file to drop the '.scaffold' suffix "
        f"(to '{_stem(artifact_rel)}{_ACTIVE_SUFFIX}'); the watcher then grades it."
    )


def _end_state_scaffold(artifact_rel: str, hints: _Hints) -> str:
    checks: list[dict[str, object]] = _db_checks(hints.tables) if hints.touches_db else []
    if hints.touches_files:
        checks += _file_checks()
    spec: dict[str, object] = {
        "kind": "agent",
        "_scaffold": True,
        "_generated_for": artifact_rel,
        "_what_this_is": (
            "EvalLoop flagged this file as an agent that changes external state (a DB row / a file). "
            "Agents like this are graded by their real END STATE, not their claim — which only you can "
            "specify. Nothing here runs until you activate it."
        ),
        "_how_to_activate": _activate_note(artifact_rel),
        "_check_types": {
            "rows_equal": "a SELECT whose rows must equal 'expected'",
            "no_rows": "a SELECT that must return nothing",
            "file_exists": "a path under 'root' that must exist",
            "file_absent": "a path that must NOT exist",
            "file_contains": "a path that must contain 'text'",
        },
        "root": ".",
        "claim": {
            "done": True,
            "message": "TODO: what the agent reported when it finished (optional — a false claim is caught)",
        },
    }
    if hints.touches_db:
        spec["sqlite_setup"] = "-- TODO: SQL to build the scratch DB the agent acts on, or delete this field"
    spec["checks"] = checks
    return json.dumps(spec, indent=2) + "\n"


def _behaviour_scaffold(artifact_rel: str, hints: _Hints) -> str:
    tool = hints.tools[0] if hints.tools else "TODO_tool_name"
    script: list[dict[str, object]] = [
        {"tool": tool, "arguments": "{}"},
        {"text": "TODO: the assistant's final reply the agent should return"},
    ]
    checks: list[dict[str, object]] = [
        {"type": "reached_answer"},
        {"type": "max_steps", "limit": 5},
        {"type": "reply_contains", "text": "TODO: a word the final reply must contain"},
    ]
    if hints.tools:
        checks.append({"type": "tool_called", "name": tool})
        checks.append({"type": "only_known_tools", "known": list(hints.tools)})
    spec: dict[str, object] = {
        "kind": "agent_behavior",
        "_scaffold": True,
        "_generated_for": artifact_rel,
        "_what_this_is": (
            "EvalLoop flagged this file as an agent with no external side effects (a chat/tool agent), "
            "so there is no end state to verify. It is graded by its BEHAVIOUR (trajectory): the agent's "
            "own loop is run against a scripted stand-in LLM — no API key, deterministic — and these "
            "checks assert what it did. Nothing runs until you activate it."
        ),
        "_how_to_activate": _activate_note(artifact_rel),
        "_check_types": {
            "reached_answer": "the agent returned a final reply (did not give up or hang)",
            "reply_contains": "the final reply contains 'text'",
            "tool_called": "the scenario exercised tool 'name' and the loop handled it",
            "max_steps": "at most 'limit' model calls",
            "only_known_tools": "the agent only dispatched tools in 'known'",
        },
        "module": PurePosixPath(artifact_rel).name,
        "entry": hints.entry,
        "_entry_note": f"the function to run; detected {hints.entry!r} — must take (client, messages)",
        "system": "",
        "user": "hi",
        "script": script,
        "_script_note": "the stand-in LLM's turns, in order: a tool request then a final answer; edit to match your agent",
        "checks": checks,
    }
    return json.dumps(spec, indent=2) + "\n"
