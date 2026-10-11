"""The one-shot run driver: the whole M1 loop on a path, and the three honest outcomes.

Gate 1 is the headline test here: point at a toy repo with a deliberately broken function and it is
caught, with nothing configured. The driver is one shot -- a path in, a report out -- so there is
no poller, server or loop to test, only that the pieces join and the exit codes are honest.
"""

from __future__ import annotations

import socket
import textwrap
from pathlib import Path

import pytest

from evalloop.plan.planner import plan
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.run import RunOutcome, _permission_request, check
from evalloop.vocab import Situation, Tool

RECORDS = tuple(load_records(RECORDS_DIR))

_TEST = textwrap.dedent(
    """
    from pricing import total

    def test_sum():
        assert total([1.0, 2.0]) == 3.0

    def test_discount():
        assert total([10.0], 0.5) == 5.0
    """
).lstrip()

CORRECT = "def total(prices, discount=0.0):\n    return sum(prices) * (1 - discount)\n"
BROKEN = "def total(prices, discount=0.0):\n    return sum(prices) + discount  # a deliberate off-logic bug\n"


def _repo(tmp_path: Path, total_source: str, *, with_test: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "pricing.py").write_text(total_source, encoding="utf-8")
    if with_test:
        (repo / "tests").mkdir()
        (repo / "tests" / "test_pricing.py").write_text(_TEST, encoding="utf-8")
    return repo


def _check(repo: Path, store: Path, **kw: object) -> object:
    return check(repo, store_dir=str(store), no_llm=True, seed=0, **kw)  # type: ignore[arg-type]


# -- the done-when: Gate 1's shape ------------------------------------------------------


def test_a_broken_function_is_caught_with_no_instruction(tmp_path: Path) -> None:
    result = check(_repo(tmp_path, BROKEN), store_dir=str(tmp_path / "store"))  # defaults only
    assert result.outcome is RunOutcome.problem
    assert result.exit_code == 1
    verdicts = {(c.case_id.rsplit("::", 1)[-1], c.verdict.value) for c in result.cases}
    assert ("test_discount", "failed") in verdicts and ("test_sum", "passed") in verdicts
    assert result.summary_path.is_file()


def test_a_correct_function_is_clean(tmp_path: Path) -> None:
    result = _check(_repo(tmp_path, CORRECT), tmp_path / "store")
    assert result.outcome is RunOutcome.clean and result.exit_code == 0
    assert all(c.verdict.value == "passed" for c in result.cases)


# -- the three honest exit codes (req 4), nothing-decided included (req 7) --------------


def test_no_oracle_is_undecided_not_clean(tmp_path: Path) -> None:
    """A function with no test cannot be decided -- exit 2, said plainly, not a false clean pass."""
    result = _check(_repo(tmp_path, CORRECT, with_test=False), tmp_path / "store")
    assert result.outcome is RunOutcome.undecided and result.exit_code == 2
    assert result.cases == ()
    assert any("no" in note.lower() and "oracle" in note.lower() for note in result.notes)
    assert result.summary_path.is_file()  # a report is still written, and it reads as an honest account


def test_the_three_outcomes_have_three_distinct_codes() -> None:
    assert {RunOutcome.clean.exit_code, RunOutcome.problem.exit_code, RunOutcome.undecided.exit_code} == {0, 1, 2}


# -- zero egress under --no-llm (req 5) -------------------------------------------------


def test_the_loop_touches_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the run driver opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    result = _check(_repo(tmp_path, BROKEN), tmp_path / "store")  # completes with the guard live
    assert result.outcome is RunOutcome.problem  # and still catches the bug, harvested-only


# -- determinism (req 6) ----------------------------------------------------------------


def test_same_repo_and_seed_give_the_same_summary_bytes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, BROKEN)
    first = _check(repo, tmp_path / "store-a").summary_path.read_text(encoding="utf-8")
    second = _check(repo, tmp_path / "store-b").summary_path.read_text(encoding="utf-8")
    assert first == second


# -- the content-hash skip (req 3) ------------------------------------------------------


def test_re_running_on_an_unchanged_repo_grades_nothing_and_says_so(tmp_path: Path) -> None:
    repo, store = _repo(tmp_path, BROKEN), tmp_path / "store"
    first = _check(repo, store)
    again = _check(repo, store)
    assert again.outcome is first.outcome  # same verdict
    assert again.graded_artifacts == ()  # nothing was graded the second time
    assert any("unchanged" in line and "graded nothing" in line for line in again.skipped)


def test_changing_the_artifact_grades_a_new_run(tmp_path: Path) -> None:
    repo, store = _repo(tmp_path, BROKEN), tmp_path / "store"
    broken = _check(repo, store)
    (repo / "pricing.py").write_text(CORRECT, encoding="utf-8")  # fix the bug
    fixed = _check(repo, store)
    assert fixed.run_id != broken.run_id and fixed.graded_artifacts  # a new run that actually graded
    assert fixed.outcome is RunOutcome.clean


# -- a missing tool is a request, not a silent skip (req 2) -----------------------------


def test_a_missing_tool_becomes_an_actionable_permission_request() -> None:
    # The classifiable M1 situations need no missing tool, so this exercises the mechanism on a plan
    # that does have one: an agent-action technique needs a snapshot it was not granted.
    unmet = plan(RECORDS, [Situation.agent_action], [Tool.sandbox], {})
    assert unmet.unavailable  # the planner found a tool gap
    lines = _permission_request(unmet)
    assert lines and all("needs:" in line and "grant it" in line for line in lines)
    assert any("snapshot_restore" in line or "trace_capture" in line for line in lines)


# -- the summary reflects the run -------------------------------------------------------


def test_the_summary_has_the_six_sections_and_the_finding(tmp_path: Path) -> None:
    result = _check(_repo(tmp_path, BROKEN), tmp_path / "store")
    summary = result.summary_path.read_text(encoding="utf-8")
    for header in ("## 1. What you built", "## 3. Findings", "## 6. Cost"):
        assert header in summary
    assert "A1_execution_based" in summary and "wrong_result" in summary


# -- the CLI returns the exit code ------------------------------------------------------


def test_the_cli_returns_the_outcome_code(tmp_path: Path) -> None:
    from evalloop.__main__ import main

    repo = _repo(tmp_path, BROKEN)
    code = main(["check", str(repo), "--store", str(tmp_path / "store")])
    assert code == 1  # a problem was found
    clean_repo = _repo(tmp_path / "ok", CORRECT)
    assert main(["check", str(clean_repo), "--store", str(tmp_path / "store2")]) == 0
