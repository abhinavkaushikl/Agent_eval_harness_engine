"""The resettable environment harness: a clean baseline, an exact reset, and honest pass^k.

These pin the promises H1/H3/H8 rest on: the environment restores to an identical baseline so an
agent's writes are fully undone, an end-state verdict only runs because the environment is resettable,
and pass^k is all-or-nothing — a flaky agent that passes only sometimes is not reliable.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.capability.broker import CapabilityBroker
from evalloop.grade.end_state import FileExists, RowsEqual
from evalloop.grade.resettable_env import ResettableEnv, grant_snapshot_restore, run_trials
from evalloop.memory.case import Verdict
from evalloop.vocab import Tool

_SEED = "CREATE TABLE todo (id TEXT PRIMARY KEY, done INTEGER); INSERT INTO todo VALUES ('seed', 0);"


def _env(tmp_path: Path, **kw: object) -> ResettableEnv:
    return ResettableEnv.build(tmp_path / "work", **kw)  # type: ignore[arg-type]


def test_reset_undoes_every_write_files_and_db(tmp_path: Path) -> None:
    env = ResettableEnv.build(
        tmp_path / "work", files={"readme.txt": "seed"}, db_name="app.db", sqlite_setup=_SEED
    )
    # the "agent" writes a file and a row
    (env.root / "created_by_agent.txt").write_text("hi", encoding="utf-8")
    import sqlite3

    conn = sqlite3.connect(env.root / "app.db")
    conn.execute("INSERT INTO todo VALUES ('agent', 1)")
    conn.commit()
    conn.close()

    env.reset()

    assert not (env.root / "created_by_agent.txt").exists(), "a reset must remove files the agent wrote"
    assert (env.root / "readme.txt").read_text(encoding="utf-8") == "seed", "baseline files come back"
    db = env.open_db()
    assert db is not None
    rows = db.rows("SELECT id FROM todo")
    db.close()
    assert [r[0] for r in rows] == ["seed"], "the agent's row is gone; the seed row is back"
    env.dispose()


def test_end_state_verifies_because_the_env_is_resettable(tmp_path: Path) -> None:
    env = ResettableEnv.build(tmp_path / "work", db_name="app.db", sqlite_setup=_SEED)
    env.reset()
    import sqlite3

    conn = sqlite3.connect(env.root / "app.db")
    conn.execute("UPDATE todo SET done = 1 WHERE id = 'seed'")
    conn.commit()
    conn.close()

    grade = env.verify([RowsEqual("seed is done", "SELECT done FROM todo WHERE id='seed'", [[1]])])
    assert grade.verdict is Verdict.passed, grade.detail
    assert grade.pending_reason is None  # not inconclusive: the resettable precondition is satisfied
    env.dispose()


def test_pass_hat_k_is_all_or_nothing(tmp_path: Path) -> None:
    env = ResettableEnv.build(tmp_path / "work", db_name="app.db", sqlite_setup=_SEED)
    check = [FileExists("the agent produced its output", "out.txt")]

    import sqlite3  # noqa: F401  (kept parallel with the other trials)

    def reliable(e: ResettableEnv) -> None:
        (e.root / "out.txt").write_text("done", encoding="utf-8")

    result = run_trials(env, reliable, check, k=5)
    assert result.pass_hat_k is True and result.passes == 5
    assert "pass^5 = True" in result.describe()

    # a flaky agent that only produces the output on some runs is NOT reliable
    calls = {"n": 0}

    def flaky(e: ResettableEnv) -> None:
        calls["n"] += 1
        if calls["n"] % 2 == 0:  # only every other run leaves the right end state
            (e.root / "out.txt").write_text("done", encoding="utf-8")

    flaky_result = run_trials(env, flaky, check, k=5)
    assert flaky_result.pass_hat_k is False
    assert 0 < flaky_result.passes < 5, flaky_result.describe()
    env.dispose()


def test_each_trial_starts_clean(tmp_path: Path) -> None:
    """An agent that only appends must not accumulate across trials — the reset isolates each run."""
    env = ResettableEnv.build(tmp_path / "work", db_name="app.db", sqlite_setup=_SEED)

    import sqlite3

    def append_one(e: ResettableEnv) -> None:
        conn = sqlite3.connect(e.root / "app.db")
        conn.execute("INSERT INTO todo VALUES ('x', 1)")
        conn.commit()
        conn.close()

    # after each clean run there are exactly 2 rows (seed + the one appended), never 3+
    result = run_trials(
        env, append_one, [RowsEqual("exactly two rows", "SELECT id FROM todo", [["seed"], ["x"]])], k=3
    )
    assert result.pass_hat_k is True, result.describe()
    env.dispose()


def test_a_template_file_cannot_escape_the_workdir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes the workdir"):
        ResettableEnv.build(tmp_path / "work", files={"../evil.txt": "x"})


def test_db_name_and_setup_must_come_together(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sqlite_setup"):
        ResettableEnv.build(tmp_path / "work", db_name="app.db")
    with pytest.raises(ValueError, match="db_name"):
        ResettableEnv.build(tmp_path / "work", sqlite_setup=_SEED)


def test_grant_snapshot_restore_makes_the_tool_available(tmp_path: Path) -> None:
    broker = CapabilityBroker(budget_usd=Decimal("1.00"))
    assert not broker.check(Tool.snapshot_restore).granted
    grant_snapshot_restore(broker, granted_by="test", reason="a resettable env exists")
    assert broker.check(Tool.snapshot_restore).granted
    assert Tool.snapshot_restore in broker.available_tools()
