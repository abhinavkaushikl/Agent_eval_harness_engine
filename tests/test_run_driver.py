"""The one-shot run driver: the whole M1 loop on a path, and the three honest outcomes.

Gate 1 is the headline test here: point at a toy repo with a deliberately broken function and it is
caught, with nothing configured. The driver is one shot -- a path in, a report out -- so there is
no poller, server or loop to test, only that the pieces join and the exit codes are honest.
"""

from __future__ import annotations

import json
import socket
import textwrap
from decimal import Decimal
from pathlib import Path

import pytest

from evalloop.plan.planner import plan
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.capability.llm import Clearance, HTTPReply, LLMClient, RetryPolicy
from evalloop.capability.router import CostLedger, Job, ModelConfig, Router
from evalloop.run import Author, RunOutcome, _permission_request, check
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


def test_one_test_file_that_cannot_import_two_artifacts_does_not_collide(tmp_path: Path) -> None:
    """Regression: the synthetic ``::inconclusive`` case id named only the oracle, so a test file
    harvested for two artifacts wrote the same case twice and the metric store refused the run."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "b.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    (repo / "tests" / "test_both.py").write_text(
        "from a import f\nfrom b import g\n\ndef test_f():\n    assert f() == 1\n\ndef test_g():\n    assert g() == 2\n",
        encoding="utf-8",
    )
    result = check(repo, store_dir=tmp_path / "store")  # used to raise MetricStoreError
    assert len({c.case_id for c in result.cases}) == len(result.cases)


def test_specs_are_graded_into_the_report_and_the_outcome(tmp_path: Path) -> None:
    repo = _repo(tmp_path, CORRECT)
    (repo / "tickets.eval.json").write_text(
        '{"kind": "agent", "sqlite_setup": "CREATE TABLE t(id INT, state TEXT); INSERT INTO t VALUES (1, \'open\');",'
        ' "claim": {"done": true, "message": "closed them all"},'
        ' "checks": [{"type": "no_rows", "name": "no open tickets", "sql": "SELECT id FROM t WHERE state=\'open\'"}]}',
        encoding="utf-8",
    )
    result = check(repo, store_dir=tmp_path / "store")
    assert result.outcome is RunOutcome.problem  # the spec failed, even though the code is clean
    assert result.code_outcome is RunOutcome.clean  # what the session's code card shows
    summary = result.summary_path.read_text(encoding="utf-8")
    assert "**Spec checks**" in summary and "failed: no open tickets" in summary


@pytest.mark.parametrize(("body", "outcome"), [("return a + b", RunOutcome.clean), ("return a - b", RunOutcome.problem)])
def test_a_module_inside_a_package_is_graded_by_its_dotted_import(tmp_path: Path, body: str, outcome: RunOutcome) -> None:
    """`from shop.pricing.calc import add` resolves in the sandbox, and a sibling module it imports comes too."""
    repo = tmp_path / "repo"
    (repo / "shop" / "pricing").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "shop" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "shop" / "pricing" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "shop" / "money.py").write_text("ZERO = 0\n", encoding="utf-8")
    (repo / "shop" / "pricing" / "calc.py").write_text(
        f"from shop.money import ZERO\n\ndef add(a, b):\n    {body}\n", encoding="utf-8"
    )
    (repo / "tests" / "test_calc.py").write_text(
        "from shop.pricing.calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8"
    )
    result = check(repo, store_dir=tmp_path / "store")
    graded = [c for c in result.cases if c.artifact_id == "shop/pricing/calc.py"]
    assert graded and all(c.verdict.value != "inconclusive" for c in graded)
    assert result.outcome is outcome


def _env_dependent_repo(tmp_path: Path, body: str) -> Path:
    """A test that reads a data file beside itself: present natively, absent in the sandbox."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "scale.py").write_text(f"def scale(x, k):\n    {body}\n", encoding="utf-8")
    (repo / "tests" / "factor.txt").write_text("3\n", encoding="utf-8")
    (repo / "tests" / "test_scale.py").write_text(
        "from pathlib import Path\nfrom scale import scale\n\n"
        "def test_uses_data_beside_it():\n"
        "    k = int((Path(__file__).parent / 'factor.txt').read_text())\n"
        "    assert scale(2, k) == 6\n\n"
        "def test_plain():\n    assert scale(1, 4) == 4\n",
        encoding="utf-8",
    )
    return repo


def test_native_calibration_withholds_a_failure_only_the_sandbox_causes(tmp_path: Path) -> None:
    repo = _env_dependent_repo(tmp_path, "return x * k")
    plain = check(repo, store_dir=tmp_path / "s1")
    assert plain.outcome is RunOutcome.problem  # without the flag the sandbox's missing file is charged
    calibrated = check(repo, store_dir=tmp_path / "s2", calibrate_native=True)
    (env_case,) = [c for c in calibrated.cases if c.case_id.endswith("test_uses_data_beside_it")]
    assert env_case.verdict.value == "inconclusive" and "native pytest" in (env_case.inconclusive_reason or "")
    assert calibrated.outcome is RunOutcome.clean
    assert any("native pytest ran" in note for note in calibrated.notes)


def test_native_calibration_never_excuses_a_real_bug(tmp_path: Path) -> None:
    repo = _env_dependent_repo(tmp_path, "return x + k")  # wrong everywhere, natively too
    result = check(repo, store_dir=tmp_path / "store", calibrate_native=True)
    (plain_case,) = [c for c in result.cases if c.case_id.endswith("test_plain")]
    assert plain_case.verdict.value == "failed" and result.outcome is RunOutcome.problem


# -- a second, independent generated test corroborates a generated failure (A:211) ----------------


class _ScriptedModel:
    """An offline transport that replies with scripted test files in order."""

    def __init__(self, *texts: str) -> None:
        self._texts, self._i = list(texts), 0

    @property
    def leaves_machine(self) -> bool:
        return False

    def post(self, body: bytes, *, timeout: float) -> "HTTPReply":
        text = self._texts[min(self._i, len(self._texts) - 1)]
        self._i += 1
        document = {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_details": None,
            "usage": {"input_tokens": 50, "output_tokens": 30},
        }
        return HTTPReply(200, {"request-id": "req_1"}, json.dumps(document).encode())


def _author(*texts: str) -> Author:
    model = ModelConfig("claude-opus-5-5", "claude", "anthropic", Decimal("4"), Decimal("20"), False, "test catalog")
    client = LLMClient(
        _ScriptedModel(*texts),
        RetryPolicy(max_attempts=1, base_delay=0.0, max_delay=0.0, request_timeout=5.0, total_timeout=10.0),
        jitter_seed=1,
    )
    router = Router(routes={Job.author: model}, client=client, ledger=CostLedger(Decimal("1.00")))
    return Author(router=router, clearance=Clearance(granted_by="tests", reason="scripted offline model"), max_attempts=1)


_RIGHT_TEST = "from adder import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
_WRONG_TEST = "from adder import add\n\ndef test_add_is_float():\n    assert isinstance(add(1, 2), float)\n"


def _adder_repo(tmp_path: Path, body: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "adder.py").write_text(f"def add(a: float, b: float) -> float:\n    {body}\n", encoding="utf-8")
    return repo


def test_a_generated_failure_an_independent_test_disagrees_with_is_withheld(tmp_path: Path) -> None:
    result = check(_adder_repo(tmp_path, "return a + b"), store_dir=tmp_path / "s", author=_author(_WRONG_TEST, _RIGHT_TEST))
    (case,) = result.cases
    assert case.verdict.value == "inconclusive" and "independently" in (case.inconclusive_reason or "")
    assert result.outcome is RunOutcome.undecided  # withheld, never promoted to a pass


def test_a_real_bug_both_independent_tests_catch_stands(tmp_path: Path) -> None:
    result = check(_adder_repo(tmp_path, "return a - b"), store_dir=tmp_path / "s", author=_author(_RIGHT_TEST, _RIGHT_TEST))
    assert [c.verdict.value for c in result.cases] == ["failed"] and result.outcome is RunOutcome.problem


def test_two_tests_wrong_the_same_way_still_count_as_a_failure(tmp_path: Path) -> None:
    """The stated limit: agreement is corroboration, not proof. Two tests sharing a mistake still fail it."""
    result = check(_adder_repo(tmp_path, "return a + b"), store_dir=tmp_path / "s", author=_author(_WRONG_TEST, _WRONG_TEST))
    assert result.outcome is RunOutcome.problem


def test_two_functions_whose_generated_tests_share_a_name_do_not_collide(tmp_path: Path) -> None:
    """Regression: both authored tests are named `test_it`, so `adder.py::test_it` appeared twice."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "adder.py").write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n", encoding="utf-8")
    tests = (
        "from adder import add\n\ndef test_it():\n    assert add(1, 2) == 3\n",
        "from adder import sub\n\ndef test_it():\n    assert sub(3, 2) == 1\n",
    )
    result = check(repo, store_dir=tmp_path / "s", author=_author(*tests))  # used to raise MetricStoreError
    assert [c.verdict.value for c in result.cases] == ["passed", "passed"]
    assert len({c.case_id for c in result.cases}) == 2
