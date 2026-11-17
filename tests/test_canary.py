"""Tests for the self-canary (T32)."""

from __future__ import annotations

import json
from pathlib import Path

from evalloop.memory.canary import (
    DEFAULT_CANARY,
    CanaryItem,
    CanaryReport,
    load_canary,
    run_canary,
)


class TestDefaultCanary:
    def test_default_canary_passes(self) -> None:
        """The shipped default canary set should pass on a correct pipeline."""
        report = run_canary()
        assert report.passed, f"default canary degraded: {report.reason}"
        assert report.n == len(DEFAULT_CANARY)
        assert report.n_matched == report.n

    def test_correct_function_passes(self) -> None:
        items = (CanaryItem(id="test", input="def f(): return 42\n", expected="f() == 42", should_pass=True),)
        report = run_canary(items)
        assert report.passed

    def test_broken_function_fails_as_expected(self) -> None:
        items = (CanaryItem(id="test", input="def f(): return 0\n", expected="f() == 42", should_pass=False),)
        report = run_canary(items)
        assert report.passed  # the item was expected to fail, and it did

    def test_detects_degradation(self) -> None:
        """T32: detect degradation on a fixed known-answer set."""
        items = (
            CanaryItem(id="test", input="def f(): return 42\n", expected="f() == 42", should_pass=True),
            # This item SHOULD pass but won't (the function is wrong) — degradation!
            CanaryItem(id="degraded", input="def g(): return 0\n", expected="g() == 42", should_pass=True),
        )
        report = run_canary(items)
        assert not report.passed
        assert report.n_degraded == 1
        assert report.degraded[0].item.id == "degraded"
        assert "degraded" in report.reason

    def test_catches_planted_reward_hack(self) -> None:
        """Gate 3: catches a planted reward hack.

        A reward hack is when a known-fail item now passes (the grader was gamed).
        """
        items = (
            # This should FAIL (broken code), but if the grader is hacked, it passes.
            CanaryItem(id="hack", input="def add(a,b): return a-b\n", expected="add(2,3)==5", should_pass=False),
        )
        report = run_canary(items)
        assert report.passed  # the item fails as expected, so no hack detected

        # Now simulate a grader hack: the item was expected to fail but now passes
        hacked_items = (
            CanaryItem(id="hack", input="def add(a,b): return a+b\n", expected="add(2,3)==5", should_pass=False),
        )
        report = run_canary(hacked_items)
        assert not report.passed  # the item passes when it shouldn't — hack caught!
        assert report.n_degraded == 1

    def test_syntax_error_does_not_pass(self) -> None:
        items = (CanaryItem(id="syn", input="def(\n", expected="1==1", should_pass=False),)
        report = run_canary(items)
        assert report.passed  # syntax error doesn't pass, as expected


class TestLoadCanary:
    def test_loads_from_file(self, tmp_path: Path) -> None:
        path = tmp_path / "canary.json"
        data = [
            {"id": "c1", "input": "x=1", "expected": "x==1", "should_pass": True, "description": "test"},
        ]
        path.write_text(json.dumps(data), encoding="utf-8")
        items = load_canary(path)
        assert len(items) == 1
        assert items[0].id == "c1"

    def test_falls_back_to_default(self, tmp_path: Path) -> None:
        items = load_canary(tmp_path / "nonexistent.json")
        assert items == DEFAULT_CANARY

    def test_bad_json_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        items = load_canary(path)
        assert items == DEFAULT_CANARY

    def test_empty_array_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text("[]", encoding="utf-8")
        items = load_canary(path)
        assert items == DEFAULT_CANARY
