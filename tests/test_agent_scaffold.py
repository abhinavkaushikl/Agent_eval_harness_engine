"""The agent eval scaffold: a stubbed, inert starter spec, and the session dropping one beside an agent.

An agent cannot be auto-graded (no resettable env / trajectory capture) and the classifier can only
flag one. These tests pin the promised behaviour: the scaffold is valid-shaped, stubbed, inert until
activated, deterministic, written once (never over a developer's edits), and surfaced rather than
silently ignored.
"""

from __future__ import annotations

import json
from pathlib import Path

from evalloop.grade.agent_scaffold import SCAFFOLD_SUFFIX, scaffold_agent_eval, scaffold_name
from evalloop.grade.specs import SPEC_SUFFIX, grade_spec_file
from evalloop.session.orchestrator import Session

_AGENT_SRC = (
    "def run(client, tools, task):\n"
    "    messages = [{'role': 'user', 'content': task}]\n"
    "    while True:\n"
    "        reply = client.messages.create(model='m', messages=messages, tools=tools)\n"
    "        if reply.stop_reason != 'tool_use':\n"
    "            return reply\n"
    "        for call in reply.tool_calls:\n"
    "            messages.append(TOOLS[call.name](**call.args))\n"
)

# an agent that DOES change external state -> the end-state scaffold shape
_DB_AGENT_SRC = (
    "import sqlite3\n"
    "TOOLS = {}\n"
    "def run(client, tools, task):\n"
    "    conn = sqlite3.connect('app.db')\n"
    "    messages = [{'role': 'user', 'content': task}]\n"
    "    while True:\n"
    "        reply = client.messages.create(model='m', messages=messages, tools=tools)\n"
    "        if reply.stop_reason != 'tool_use':\n"
    "            return reply\n"
    "        for call in reply.tool_calls:\n"
    "            conn.execute('INSERT INTO orders VALUES (?)', (call.name,))\n"
)


def test_a_side_effect_free_agent_gets_a_behavioural_scaffold() -> None:
    spec = json.loads(scaffold_agent_eval("agent.py", _AGENT_SRC))
    assert spec["kind"] == "agent_behavior"  # no DB/file writes -> graded by behaviour
    assert spec["_scaffold"] is True
    assert spec["module"] == "agent.py" and spec["entry"] == "run"  # entry auto-detected
    assert spec["checks"] and all("type" in c for c in spec["checks"])
    assert any(c["type"] == "reached_answer" for c in spec["checks"])


def test_a_db_agent_gets_an_end_state_scaffold() -> None:
    spec = json.loads(scaffold_agent_eval("worker.py", _DB_AGENT_SRC))
    assert spec["kind"] == "agent"  # it changes external state -> end-state verification
    assert "sqlite_setup" in spec
    assert spec["checks"] and all("type" in c for c in spec["checks"])
    assert "TODO" in json.dumps(spec) and "_how_to_activate" in spec


def test_scaffold_is_deterministic() -> None:
    assert scaffold_agent_eval("a.py", _AGENT_SRC) == scaffold_agent_eval("a.py", _AGENT_SRC)


def test_scaffold_name_is_inert_until_activated() -> None:
    name = scaffold_name("sub/dir/myagent.py")
    assert name == "myagent" + SCAFFOLD_SUFFIX
    # inert: the poller tracks *.eval.json, and the scaffold name is not that until the suffix is dropped
    assert not name.endswith(SPEC_SUFFIX)
    activated = name[: -len(".scaffold")]  # the one gesture the file asks for: drop '.scaffold'
    assert activated == "myagent.agent" + SPEC_SUFFIX and activated.endswith(SPEC_SUFFIX)


def test_filled_end_state_scaffold_parses_as_a_real_agent_spec(tmp_path: Path) -> None:
    """Once the TODOs are a real DB check, the activated end-state spec grades through the spec path."""
    spec = json.loads(scaffold_agent_eval("worker.py", _DB_AGENT_SRC))
    spec["sqlite_setup"] = "CREATE TABLE t (id TEXT); INSERT INTO t VALUES ('x');"
    spec["checks"] = [{"type": "rows_equal", "name": "row exists", "sql": "SELECT id FROM t", "expected": [["x"]]}]
    active = tmp_path / ("worker.agent" + SPEC_SUFFIX)
    active.write_text(json.dumps(spec), encoding="utf-8")
    result = grade_spec_file(active)
    assert result.kind == "agent" and result.situation == "agent_action"
    assert result.outcome == "clean"


def test_session_drops_a_scaffold_beside_an_agent_and_surfaces_it(tmp_path: Path) -> None:
    (tmp_path / "bot.py").write_text(_AGENT_SRC, encoding="utf-8")
    session = Session(tmp_path, store_dir=tmp_path / "store", clock=lambda: 1.0)
    session.tick()

    scaffold = tmp_path / ("bot" + SCAFFOLD_SUFFIX)
    assert scaffold.exists(), "an agent file must get a scaffold dropped beside it"
    json.loads(scaffold.read_text(encoding="utf-8"))  # it is valid JSON

    agent_cards = [c for r in session.state.runs for c in r.cases if c.record == "agent_scaffold"]
    assert agent_cards and agent_cards[0].oracle == "bot" + SCAFFOLD_SUFFIX
    assert "fill in the end-state checks" in agent_cards[0].detail


def test_session_never_overwrites_an_edited_scaffold(tmp_path: Path) -> None:
    (tmp_path / "bot.py").write_text(_AGENT_SRC, encoding="utf-8")
    session = Session(tmp_path, store_dir=tmp_path / "store", clock=lambda: 1.0)
    session.tick()

    scaffold = tmp_path / ("bot" + SCAFFOLD_SUFFIX)
    scaffold.write_text('{"kind": "agent", "my": "edits"}', encoding="utf-8")  # the developer edits it
    (tmp_path / "bot.py").write_text(_AGENT_SRC + "\n# touch\n", encoding="utf-8")  # a change re-ticks
    session.tick()
    assert json.loads(scaffold.read_text(encoding="utf-8")) == {"kind": "agent", "my": "edits"}


def test_no_scaffold_once_a_real_spec_exists(tmp_path: Path) -> None:
    """A developer who has written a real agent spec gets no scaffold and no scaffold card."""
    (tmp_path / "bot.py").write_text(_AGENT_SRC, encoding="utf-8")
    (tmp_path / ("bot.agent" + SPEC_SUFFIX)).write_text(
        '{"kind": "agent", "checks": [{"type": "file_exists", "path": "x"}]}', encoding="utf-8"
    )
    session = Session(tmp_path, store_dir=tmp_path / "store", clock=lambda: 1.0)
    assert session._agent_scaffold("bot.py") is None
    assert not (tmp_path / ("bot" + SCAFFOLD_SUFFIX)).exists()
