"""Behavioural agent evaluation: capture a trajectory against a scripted LLM and grade what it did.

These pin the honest scope — with a scripted stand-in model (no key, no egress) EvalLoop grades the
agent's *own loop*: that it reaches an answer, handles a tool round-trip, stays within a step budget,
and only dispatches known tools. The model's intelligence is not under test; the agent's behaviour is.
"""

from __future__ import annotations

import json
from pathlib import Path

from evalloop.grade.specs import grade_spec_file
from evalloop.grade.trajectory import (
    MaxSteps,
    OnlyKnownTools,
    ReachedAnswer,
    ReplyContains,
    ToolCalled,
    capture_chat,
    grade_behaviour,
    run_agent_chat,
)
from evalloop.memory.case import Verdict

# A minimal agent with agent.py's shape: it imports a provider SDK (shimmed under test), loops over
# the model, dispatches a tool, and feeds the result back until the model answers.
_AGENT_MODULE = '''
import groq  # not installed in the test env -> run_agent_chat shims it so the import succeeds
TOOLS = {"now": lambda: "NOON"}
SCHEMAS = [{"type": "function", "function": {"name": "now"}}]

def chat(client, messages, limit=5):
    for _ in range(limit):
        msg = client.chat.completions.create(
            model="m", messages=messages, tools=SCHEMAS, tool_choice="auto"
        ).choices[0].message
        turn = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            turn["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in msg.tool_calls
            ]
        messages.append(turn)
        if not msg.tool_calls:
            return (msg.content or "").strip()
        for c in msg.tool_calls:
            fn = TOOLS.get(c.function.name)
            out = str(fn()) if fn else "no such tool"
            messages.append({"role": "tool", "tool_call_id": c.id, "content": out})
    return "[gave up after too many tool calls]"
'''


def _chat(client: object, messages: list[dict[str, object]], limit: int = 5) -> str:
    """An inline agent loop for the unit tests (same shape, no module import)."""
    for _ in range(limit):
        msg = client.chat.completions.create(model="m", messages=messages, tools=[], tool_choice="auto").choices[0].message  # type: ignore[attr-defined]
        turn: dict[str, object] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            turn["tool_calls"] = [{"id": c.id, "function": {"name": c.function.name}} for c in msg.tool_calls]
        messages.append(turn)
        if not msg.tool_calls:
            return (msg.content or "").strip()
        for c in msg.tool_calls:
            messages.append({"role": "tool", "tool_call_id": c.id, "content": "ok"})
    return "[gave up after too many tool calls]"


def test_capture_records_the_agents_real_loop() -> None:
    traj = capture_chat(
        _chat, user="hi", script=[{"tool": "now", "arguments": "{}"}, {"text": "Hello there!"}]
    )
    assert traj.final_reply == "Hello there!"
    assert traj.tools_called == ("now",)
    assert traj.llm_calls == 2 and traj.reached_answer


def test_grade_passes_a_well_behaved_agent() -> None:
    traj = capture_chat(_chat, user="hi", script=[{"tool": "now"}, {"text": "Hello!"}])
    grade = grade_behaviour(
        traj, [ReachedAnswer(), ReplyContains("hello"), ToolCalled("now"), MaxSteps(5), OnlyKnownTools(("now",))]
    )
    assert grade.verdict is Verdict.passed, grade.detail


def test_grade_fails_when_the_reply_is_wrong() -> None:
    traj = capture_chat(_chat, user="hi", script=[{"text": "Goodbye"}])
    grade = grade_behaviour(traj, [ReachedAnswer(), ReplyContains("hello")])
    assert grade.verdict is Verdict.failed
    assert any(not c.ok and "hello" in c.detail for c in grade.checks)


def test_grade_catches_an_unknown_tool() -> None:
    traj = capture_chat(_chat, user="hi", script=[{"tool": "danger"}, {"text": "done"}])
    grade = grade_behaviour(traj, [OnlyKnownTools(("now",))])
    assert grade.verdict is Verdict.failed
    assert "danger" in grade.checks[0].detail


def test_giving_up_is_not_reaching_an_answer() -> None:
    # the model keeps asking for a tool, so the agent exhausts its limit and gives up
    traj = capture_chat(_chat, user="hi", script=[{"tool": "now"}] * 10, system=None)
    grade = grade_behaviour(traj, [ReachedAnswer()])
    assert grade.verdict is Verdict.failed, traj.final_reply


def test_run_agent_chat_imports_and_runs_a_module_with_an_absent_sdk(tmp_path: Path) -> None:
    mod = tmp_path / "myagent.py"
    mod.write_text(_AGENT_MODULE, encoding="utf-8")
    traj = run_agent_chat(mod, "chat", user="hi", script=[{"tool": "now"}, {"text": "Hey! It is NOON."}])
    assert traj.reached_answer and traj.final_reply == "Hey! It is NOON."
    assert traj.tools_called == ("now",)


def test_editing_the_agent_regrades_its_behaviour_spec(tmp_path: Path) -> None:
    """Editing an agent's code must re-run the spec that points at it, not just the undecidable py-path."""
    from evalloop.session.orchestrator import Session

    (tmp_path / "myagent.py").write_text(_AGENT_MODULE, encoding="utf-8")
    spec = {
        "kind": "agent_behavior", "module": "myagent.py", "entry": "chat", "user": "hi",
        "script": [{"tool": "now"}, {"text": "Hello! It is NOON."}],
        "checks": [{"type": "reached_answer"}, {"type": "reply_contains", "text": "hello"}],
    }
    (tmp_path / "myagent.agent.eval.json").write_text(json.dumps(spec), encoding="utf-8")
    session = Session(tmp_path, store_dir=tmp_path / "store", clock=lambda: 1.0)
    session.tick()  # first look grades everything -> clean

    # break the agent: it now returns an empty reply instead of the model's answer (no crash)
    broken = _AGENT_MODULE.replace('return (msg.content or "").strip()', 'return ""')
    assert broken != _AGENT_MODULE
    (tmp_path / "myagent.py").write_text(broken, encoding="utf-8")
    card = session.tick()  # a change to the CODE must re-grade the spec

    # newest-first: the most recent behaviour grade must exist and be failed (the broken loop)
    behaviour = [c for r in session.state.runs for c in r.cases if c.record == "agent_behavior"]
    assert behaviour, "editing the agent must re-grade its behaviour spec"
    assert behaviour[0].verdict == "failed", "the broken agent's latest behaviour grade must be failed"
    assert card is not None and card.outcome == "problem", "a broken loop must fail the eval, not read undecided"
    # the empty "function path" UNDECIDED card must not sit on top of the real verdict
    assert session.state.runs[0].outcome == "problem", "the real FAIL, not an empty undecided, must be newest"


def test_a_crashing_agent_reads_as_a_failure_naming_the_exception(tmp_path: Path) -> None:
    """An agent whose own code raises is a behavioural FAIL (not an EvalLoop error), with the cause named."""
    (tmp_path / "boom.py").write_text(_AGENT_MODULE.replace("messages.append(turn)", "messages.append(turnf)"), encoding="utf-8")
    spec = {
        "kind": "agent_behavior", "module": "boom.py", "entry": "chat", "user": "hi",
        "script": [{"tool": "now"}, {"text": "hello"}], "checks": [{"type": "reached_answer"}],
    }
    path = tmp_path / "boom.agent.eval.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    result = grade_spec_file(path)
    assert result.outcome == "problem"
    assert result.cases and result.cases[0].verdict == "failed"
    assert "NameError" in result.cases[0].detail and "turnf" in result.cases[0].detail


def test_behaviour_spec_grades_a_real_agent_green(tmp_path: Path) -> None:
    (tmp_path / "myagent.py").write_text(_AGENT_MODULE, encoding="utf-8")
    spec = {
        "kind": "agent_behavior",
        "module": "myagent.py",
        "entry": "chat",
        "user": "hi, what time is it?",
        "script": [{"tool": "now", "arguments": "{}"}, {"text": "Hello! It is NOON."}],
        "checks": [
            {"type": "reached_answer"},
            {"type": "reply_contains", "text": "hello"},
            {"type": "tool_called", "name": "now"},
            {"type": "max_steps", "limit": 5},
            {"type": "only_known_tools", "known": ["now"]},
        ],
    }
    path = tmp_path / "myagent.agent.eval.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    result = grade_spec_file(path)
    assert result.kind == "agent_behavior" and result.situation == "agent_action"
    assert result.outcome == "clean", [(c.name, c.verdict) for c in result.cases]
