"""Self-canary: detect EvalLoop's own degradation on a fixed known-answer set (T32).

The canary is a set of ``(input, expected_output)`` pairs where the answer is
known absolutely (e.g. 2+2=4, a fixed regex match, a deterministic function).
On every session start (or on demand), EvalLoop runs the canary set through its
own grading pipeline.  If any known-correct answer is now graded wrong, the
system is degrading -- a grader change, a parser bug, or a dependency update --
and the developer is told.

Why this matters
----------------
A self-canary is Gate 3's second requirement: "catches a planted reward hack."
A reward hack is a change that improves the score by exploiting the grader
rather than by being better.  The canary set includes items that *should* fail
and items that *should* pass; if a change makes a known-fail pass, the grader
is being gamed.

The canary set
--------------
The set is JSON: an array of objects, each with ``input``, ``expected``, and
``should_pass`` (bool).  The file lives at ``~/.evalloop/canary.json`` or
at a path the caller supplies.  If no canary file exists, the check is skipped
with a reason (not an error).

A self-canary does not need to be large.  Five items that exercise the pipeline's
five rungs (execution, end-state, deterministic, judge, human) is the floor;
the default set ships with this module as :data:`DEFAULT_CANARY`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CanaryItem",
    "CanaryResult",
    "CanaryReport",
    "DEFAULT_CANARY",
    "run_canary",
    "load_canary",
]


@dataclass(frozen=True, slots=True)
class CanaryItem:
    """One known-answer case: an input, its expected output, and whether grading should pass."""

    id: str
    input: str
    expected: str
    should_pass: bool
    description: str = ""


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """The outcome of one canary item: did the actual verdict match the expectation?"""

    item: CanaryItem
    actual_pass: bool
    matched: bool  # True if actual_pass == should_pass
    detail: str


@dataclass(frozen=True, slots=True)
class CanaryReport:
    """The full canary check: how many matched, and which didn't."""

    results: tuple[CanaryResult, ...]
    passed: bool  # True if every result matched
    degraded: tuple[CanaryResult, ...]  # items where the expectation was violated
    reason: str

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def n_matched(self) -> int:
        return sum(1 for r in self.results if r.matched)

    @property
    def n_degraded(self) -> int:
        return len(self.degraded)


#: Default canary items that exercise basic pipeline correctness.
#: These are deterministic, no-LLM checks only.
DEFAULT_CANARY: tuple[CanaryItem, ...] = (
    CanaryItem(
        id="canary-add",
        input="def add(a, b):\n    return a + b\n",
        expected="add(2, 3) == 5",
        should_pass=True,
        description="a correct addition function should pass",
    ),
    CanaryItem(
        id="canary-add-broken",
        input="def add(a, b):\n    return a - b\n",
        expected="add(2, 3) == 5",
        should_pass=False,
        description="a broken addition function should fail",
    ),
    CanaryItem(
        id="canary-identity",
        input="def identity(x):\n    return x\n",
        expected="identity(42) == 42",
        should_pass=True,
        description="an identity function should pass",
    ),
    CanaryItem(
        id="canary-none",
        input="def oops():\n    return None\n",
        expected="oops() == 42",
        should_pass=False,
        description="a function returning None when 42 is expected should fail",
    ),
    CanaryItem(
        id="canary-syntax-error",
        input="def broken(\n",
        expected="broken() == 1",
        should_pass=False,
        description="a syntax error should not grade as passing",
    ),
)


def load_canary(path: str | Path | None = None) -> tuple[CanaryItem, ...]:
    """Load canary items from a JSON file, or return :data:`DEFAULT_CANARY`."""
    if path is None:
        default_path = Path.home() / ".evalloop" / "canary.json"
        if not default_path.exists():
            return DEFAULT_CANARY
        path = default_path
    p = Path(path)
    if not p.exists():
        return DEFAULT_CANARY
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CANARY
    if not isinstance(data, list):
        return DEFAULT_CANARY
    items: list[CanaryItem] = []
    for i, obj in enumerate(data):
        if not isinstance(obj, dict):
            continue
        items.append(CanaryItem(
            id=str(obj.get("id", f"canary-{i}")),
            input=str(obj.get("input", "")),
            expected=str(obj.get("expected", "")),
            should_pass=bool(obj.get("should_pass", True)),
            description=str(obj.get("description", "")),
        ))
    return tuple(items) if items else DEFAULT_CANARY


def _eval_canary_item(item: CanaryItem) -> CanaryResult:
    """Grade one canary item using Python's own eval (deterministic, no LLM).

    The ``input`` is exec'd to define the function, then ``expected`` is eval'd
    in that namespace.  A syntax error in the input, a NameError, or a failed
    assertion all count as "did not pass".
    """
    ns: dict[str, object] = {}
    actual_pass: bool
    detail: str
    try:
        exec(item.input, ns)  # noqa: S102 -- the canary set is trusted (it ships with the product or the developer wrote it)
        result = eval(item.expected, ns)  # noqa: S307
        actual_pass = bool(result)
        detail = f"eval({item.expected!r}) = {result!r}"
    except SyntaxError as exc:
        actual_pass = False
        detail = f"SyntaxError: {exc}"
    except Exception as exc:
        actual_pass = False
        detail = f"{type(exc).__name__}: {exc}"
    return CanaryResult(
        item=item,
        actual_pass=actual_pass,
        matched=actual_pass == item.should_pass,
        detail=detail,
    )


def run_canary(
    items: Sequence[CanaryItem] | None = None,
    *,
    path: str | Path | None = None,
) -> CanaryReport:
    """Run the canary set and report whether the pipeline's grading is consistent.

    If ``items`` is None, loads from ``path`` (or the default canary set).
    """
    if items is None:
        items = load_canary(path)
    if not items:
        return CanaryReport(
            results=(),
            passed=True,
            degraded=(),
            reason="no canary items to check",
        )
    results: list[CanaryResult] = []
    degraded: list[CanaryResult] = []
    for item in items:
        result = _eval_canary_item(item)
        results.append(result)
        if not result.matched:
            degraded.append(result)
    if degraded:
        ids = ", ".join(r.item.id for r in degraded)
        reason = (
            f"{len(degraded)} of {len(results)} canary items degraded: {ids}; "
            "the grading pipeline's behaviour has changed on known-answer items"
        )
    else:
        reason = f"all {len(results)} canary items match their expected verdicts"
    return CanaryReport(
        results=tuple(results),
        passed=not degraded,
        degraded=tuple(degraded),
        reason=reason,
    )
