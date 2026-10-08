"""``GATE0-RENDERED-PLANS.md`` is current, and holds all 20 plans.

``PLAN.md`` §5 makes the human review of the 20 rendered plans **the gate**, so
the artifact a human reads has to be the one the code produces. Without this
test it would be a snapshot that silently went stale the first time a record or
the renderer changed, and the gate would be reviewing something that no longer
runs.
"""

from __future__ import annotations

import pytest

from tests.render_gate0 import ARTIFACT, build_artifact
from tests.test_planner_fixtures import BLOCKED_PATHS, LIVE_PATHS

EXPECTED_PLANS = 20


def test_the_artifact_exists() -> None:
    assert ARTIFACT.is_file(), (
        f"{ARTIFACT.name} is missing. Generate it with: python -m tests.render_gate0"
    )


def test_the_artifact_is_current() -> None:
    """The committed file equals what the planner renders now."""
    committed = ARTIFACT.read_text(encoding="utf-8")
    fresh = build_artifact()
    if committed == fresh:
        return
    committed_lines = committed.splitlines()
    fresh_lines = fresh.splitlines()
    first_diff = next(
        (
            index
            for index, (left, right) in enumerate(zip(committed_lines, fresh_lines))
            if left != right
        ),
        min(len(committed_lines), len(fresh_lines)),
    )
    pytest.fail(
        f"{ARTIFACT.name} is stale from line {first_diff + 1}.\n"
        f"  committed: {committed_lines[first_diff:first_diff + 1]}\n"
        f"  rendered:  {fresh_lines[first_diff:first_diff + 1]}\n"
        "Regenerate with: python -m tests.render_gate0"
    )


def test_the_artifact_holds_all_twenty_plans() -> None:
    """Seventeen asserted by a fixture, three blocked -- none quietly missing."""
    text = ARTIFACT.read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert len(headings) == EXPECTED_PLANS, headings
    assert len(LIVE_PATHS) + len(BLOCKED_PATHS) == EXPECTED_PLANS


def test_every_blocked_plan_is_marked_as_blocked() -> None:
    """A reader must not mistake a question for a reviewed plan."""
    text = ARTIFACT.read_text(encoding="utf-8")
    assert text.count("⚠ **BLOCKED ON A RULING**") == len(BLOCKED_PATHS)
    for path in BLOCKED_PATHS:
        assert path.name in text, f"{path.name} is not pointed at from the artifact"


def test_every_plan_shows_all_four_states() -> None:
    """§3.1: four states, always visible, on every one of the 20."""
    text = ARTIFACT.read_text(encoding="utf-8")
    for state in ("READY", "PENDING", "UNAVAILABLE", "PROHIBITED"):
        assert text.count(f"{state}  ") >= EXPECTED_PLANS, state
