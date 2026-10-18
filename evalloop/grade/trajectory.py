"""Behavioural agent evaluation: grade what an agent DID, not its claim, when it has no end state.

An agent with external side effects (a DB row, a file) is graded by its end state
(:mod:`evalloop.grade.end_state`). An agent with **no** side effects — a "say hi → hello" chat/tool
agent — leaves nothing to inspect, so the honest eval is **behavioural**: did it call the right tool,
reach a final answer, stay within a step budget, keep off unknown tools. This is H7 (trajectory)
territory, narrowed to a handful of assertions a developer can actually write.

Capturing a trajectory with no model and no egress
--------------------------------------------------
The agent's own loop is run against a **scripted stand-in LLM** — a test double that returns a fixed
sequence of assistant turns (a final message, or a request to call a named tool). The agent's real
control flow executes (its loop, its tool dispatch, its message handling); only the model is stubbed.
Each LLM call, each tool the model asked for, and the final reply are recorded as the trajectory.
Deterministic, no API key — the same stand-in that exercises the agent by hand becomes its harness.

Running the agent's code
------------------------
Grading a real agent means running it, exactly as execution grading already runs a repo's functions.
The entry point takes the client as an argument (``chat(client, messages)``), so the scripted client
is injected without monkey-patching. :func:`run_agent_chat` imports the agent module by path (shimming
an absent provider SDK so the import succeeds, since the real client is supplied), and calls the entry.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from evalloop.grade.end_state import CheckResult
from evalloop.memory.case import FailureClass, Verdict

__all__ = [
    "RECORD_ID",
    "Step",
    "Trajectory",
    "ScriptedClient",
    "BehaviourCheck",
    "ReachedAnswer",
    "ReplyContains",
    "ToolCalled",
    "MaxSteps",
    "OnlyKnownTools",
    "BehaviourGrade",
    "capture_chat",
    "run_agent_chat",
    "grade_behaviour",
]

RECORD_ID = "H7_trajectory_taxonomy"

#: What the agent's loop gives up with, so "reached an answer" is not fooled by it.
_GIVE_UP = "[gave up after too many tool calls]"


@dataclass(frozen=True, slots=True)
class Step:
    """One recorded moment of the run: an LLM call, a tool the model asked for, or the final answer."""

    kind: str  # "llm_call" | "tool_call" | "final_answer"
    name: str = ""  # the tool name, for a tool_call
    tools_offered: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Trajectory:
    """What the agent did: the ordered steps and the final reply it returned."""

    steps: tuple[Step, ...]
    final_reply: str

    @property
    def tools_called(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.steps if s.kind == "tool_call")

    @property
    def llm_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "llm_call")

    @property
    def reached_answer(self) -> bool:
        reply = self.final_reply.strip()
        return bool(reply) and reply != _GIVE_UP


# -- the scripted stand-in LLM (groq / openai chat-completions shape) ------------------


@dataclass(frozen=True, slots=True)
class _Fn:
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class _ToolCall:
    id: str
    function: _Fn
    type: str = "function"


class _Message:
    def __init__(self, content: str | None, tool_calls: list[_ToolCall] | None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Response:
    def __init__(self, message: _Message) -> None:
        self.choices = [_Choice(message)]


class _Completions:
    def __init__(self, script: Sequence[dict[str, object]], steps: list[Step]) -> None:
        self._script = list(script)
        self._steps = steps
        self._i = 0

    def create(
        self, *, model: object = None, messages: object = None, tools: object = None, tool_choice: object = None
    ) -> _Response:
        offered: list[str] = []
        if isinstance(tools, (list, tuple)):
            for t in tools:
                fn = t.get("function") if isinstance(t, dict) else None
                if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                    offered.append(str(fn["name"]))
        self._steps.append(Step("llm_call", tools_offered=tuple(offered)))
        turn = self._script[self._i] if self._i < len(self._script) else {"text": ""}
        self._i += 1
        if "tool" in turn:
            name = str(turn["tool"])
            args = str(turn.get("arguments", "{}"))
            self._steps.append(Step("tool_call", name=name))
            return _Response(_Message(None, [_ToolCall("call_%d" % self._i, _Fn(name, args))]))
        self._steps.append(Step("final_answer"))
        return _Response(_Message(str(turn.get("text", "")), None))


class ScriptedClient:
    """A stand-in LLM with the chat-completions surface an agent uses. Records what it was asked and told."""

    def __init__(self, script: Sequence[dict[str, object]]) -> None:
        self.steps: list[Step] = []
        self.chat = types.SimpleNamespace(completions=_Completions(script, self.steps))


# -- behavioural checks ----------------------------------------------------------------


class BehaviourCheck:
    """A single assertion about the trajectory. Subclasses set ``name`` and implement ``verify``."""

    name: str

    def verify(self, trajectory: Trajectory) -> CheckResult:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ReachedAnswer(BehaviourCheck):
    name: str = "reached a final answer"

    def verify(self, trajectory: Trajectory) -> CheckResult:
        ok = trajectory.reached_answer
        return CheckResult(self.name, ok, "returned a final reply" if ok else "never produced a final answer")


@dataclass(frozen=True, slots=True)
class ReplyContains(BehaviourCheck):
    text: str
    name: str = ""

    def verify(self, trajectory: Trajectory) -> CheckResult:
        label = self.name or f"the reply mentions {self.text!r}"
        ok = self.text.lower() in trajectory.final_reply.lower()
        detail = f"reply {'contains' if ok else 'does not contain'} {self.text!r}"
        return CheckResult(label, ok, detail)


@dataclass(frozen=True, slots=True)
class ToolCalled(BehaviourCheck):
    tool: str
    name: str = ""

    def verify(self, trajectory: Trajectory) -> CheckResult:
        label = self.name or f"called the {self.tool!r} tool"
        ok = self.tool in trajectory.tools_called
        called = ", ".join(trajectory.tools_called) or "none"
        return CheckResult(label, ok, f"tools called: {called}")


@dataclass(frozen=True, slots=True)
class MaxSteps(BehaviourCheck):
    limit: int
    name: str = ""

    def verify(self, trajectory: Trajectory) -> CheckResult:
        label = self.name or f"took at most {self.limit} model call(s)"
        ok = trajectory.llm_calls <= self.limit
        return CheckResult(label, ok, f"{trajectory.llm_calls} model call(s); limit {self.limit}")


@dataclass(frozen=True, slots=True)
class OnlyKnownTools(BehaviourCheck):
    known: tuple[str, ...]
    name: str = "called only known tools"

    def verify(self, trajectory: Trajectory) -> CheckResult:
        unknown = sorted({t for t in trajectory.tools_called if t not in self.known})
        ok = not unknown
        return CheckResult(self.name, ok, "no unknown tools" if ok else f"called unknown tool(s): {', '.join(unknown)}")


# -- the grade -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BehaviourGrade:
    """A verdict from the trajectory alone — behaviour, not a claim and not an end state."""

    record_id: str
    verdict: Verdict
    failure_class: FailureClass | None
    checks: tuple[CheckResult, ...]
    detail: str
    trajectory: Trajectory


def grade_behaviour(trajectory: Trajectory, checks: Sequence[BehaviourCheck]) -> BehaviourGrade:
    """Grade a trajectory against behavioural checks. All must hold to pass."""
    if not checks:
        return BehaviourGrade(
            RECORD_ID, Verdict.inconclusive, None, (), "no behavioural checks to grade against", trajectory
        )
    results = tuple(c.verify(trajectory) for c in checks)
    failed = [r for r in results if not r.ok]
    if failed:
        detail = f"behaviour wrong: {len(failed)} of {len(results)} checks failed ({', '.join(r.name for r in failed)})"
        return BehaviourGrade(RECORD_ID, Verdict.failed, FailureClass.wrong_result, results, detail, trajectory)
    return BehaviourGrade(
        RECORD_ID, Verdict.passed, None, results, f"behaviour verified: all {len(results)} checks passed", trajectory
    )


# -- running the agent -----------------------------------------------------------------


def capture_chat(
    chat_fn: Callable[..., object],
    *,
    user: str,
    script: Sequence[dict[str, object]],
    system: str | None = None,
) -> Trajectory:
    """Run ``chat_fn(client, messages)`` against a scripted stand-in LLM and record its trajectory."""
    client = ScriptedClient(script)
    messages: list[dict[str, object]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    reply = chat_fn(client, messages)
    return Trajectory(tuple(client.steps), "" if reply is None else str(reply))


_SHIMMED_SDKS = ("groq", "openai", "anthropic")


def _shim_absent_sdks() -> None:
    """Let an agent module import its provider SDK even when it isn't installed: the real client is
    injected at call time, so only the import needs to succeed."""
    for name in _SHIMMED_SDKS:
        if name not in sys.modules and importlib.util.find_spec(name) is None:
            module = types.ModuleType(name)

            class _Unavailable:  # a placeholder the agent never actually constructs under test
                def __init__(self, *_a: object, **_k: object) -> None:
                    raise RuntimeError(f"{name} is a test shim; inject a client instead of constructing one")

            for attr in ("Groq", "OpenAI", "Anthropic", "Client"):
                setattr(module, attr, _Unavailable)
            sys.modules[name] = module


def run_agent_chat(
    module_path: str | Path,
    entry: str,
    *,
    user: str,
    script: Sequence[dict[str, object]],
    system: str | None = None,
) -> Trajectory:
    """Import the agent module at ``module_path`` and run its ``entry`` against the scripted LLM.

    Runs the agent's real code (as execution grading already does), so point it only at a repo you
    trust. The provider SDK is shimmed for import; the scripted client is what the entry actually uses.
    """
    path = Path(module_path)
    _shim_absent_sdks()
    spec = importlib.util.spec_from_file_location(f"_evalloop_agent_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import agent module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chat_fn = getattr(module, entry, None)
    if not callable(chat_fn):
        raise AttributeError(f"{path.name} has no callable {entry!r} to run")
    return capture_chat(chat_fn, user=user, script=script, system=system)
