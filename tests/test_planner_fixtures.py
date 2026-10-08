"""The 20 planner fixtures: they load, they validate, and they wait for a planner.

The fixtures are written **before** the planner (``CLAUDE.md`` §7.3) and are
derived from the records, which were derived from the corpus. Nothing here
compares a fixture against a ``Plan``; that comparison lives in
``tests/test_planner.py``, which did not exist when these were written --
``CLAUDE.md`` §7.3, fixtures before the planner.

What *is* asserted now is everything that can be: the files parse under the
record format parser, their shape is exactly the five-key ``expect`` block
``TASKS.md`` group 6 fixes, every record id in every bucket resolves to a real
record, every situation and tool name is real vocabulary, and no id appears in
two buckets at once. That is the whole class of defect that would otherwise
surface as a confusing planner failure at ``EL-123`` -- a typo'd id, a
hand-written tool name, a fixture asserting a record into two buckets.

Three fixtures are **blocked** on a human ruling and carry a ``.BLOCKED.yaml``
suffix, which keeps them out of ``FIXTURE_GLOB``. They are not skipped tests;
they are files holding a question, with the options written out. ``S19-REPORT.md``
has the write-ups. ``test_blocked_fixtures_are_accounted_for`` asserts they stay
visible rather than quietly becoming three missing numbers in a sequence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.conftest import require_fixture_dir

from tests.planner_fixture import (
    EXPECT_KEYS,
    GIVEN_KEYS,
    FixtureError,
    load_fixture,
)

from evalloop.registry.format import load
from evalloop.registry.loader import RECORDS_DIR, TechniqueRecord, load_records
from evalloop.registry.query import sort_key

PLANNER_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "planner"

#: Live fixtures. ``.BLOCKED.yaml`` files are deliberately excluded -- see the
#: module docstring and ``BLOCKED_GLOB``.
FIXTURE_GLOB = "[0-9][0-9]_*.yaml"
BLOCKED_GLOB = "[0-9][0-9]_*.BLOCKED.yaml"

#: The 20 the plan budgets for: 17 live plus 3 blocked.
EXPECTED_TOTAL_FIXTURES = 20
EXPECTED_BLOCKED = 3

_FIXTURE_NUMBER = re.compile(r"^(\d\d)_")


def _live_paths() -> list[Path]:
    require_fixture_dir(PLANNER_FIXTURES_DIR)
    blocked = set(PLANNER_FIXTURES_DIR.glob(BLOCKED_GLOB))
    return sorted(p for p in PLANNER_FIXTURES_DIR.glob(FIXTURE_GLOB) if p not in blocked)


def _blocked_paths() -> list[Path]:
    require_fixture_dir(PLANNER_FIXTURES_DIR)
    return sorted(PLANNER_FIXTURES_DIR.glob(BLOCKED_GLOB))


#: Collected at import time so each fixture is its own test case and a failure
#: names the file.
LIVE_PATHS = _live_paths()
BLOCKED_PATHS = _blocked_paths()


@pytest.fixture(scope="module")
def records() -> tuple[TechniqueRecord, ...]:
    return load_records(RECORDS_DIR)


@pytest.fixture(scope="module")
def known_ids(records: tuple[TechniqueRecord, ...]) -> frozenset[str]:
    return frozenset(record.id for record in records)


def _raw(path: Path) -> dict[str, object]:
    """Parse without validating -- for the blocked fixtures, which have no ``expect``.

    Every live fixture goes through ``load_fixture`` instead. This exists only
    because a blocked fixture is deliberately incomplete and must still be
    inspectable.
    """
    return dict(load(path.read_text(encoding="utf-8")))


def test_the_fixture_set_is_complete() -> None:
    """17 live + 3 blocked = the 20 ``TASKS.md`` group 6 budgets for."""
    total = len(LIVE_PATHS) + len(BLOCKED_PATHS)
    assert total == EXPECTED_TOTAL_FIXTURES, (
        f"{len(LIVE_PATHS)} live + {len(BLOCKED_PATHS)} blocked = {total}, "
        f"expected {EXPECTED_TOTAL_FIXTURES}"
    )


def test_fixture_numbers_are_unique_and_contiguous() -> None:
    """1..20 with no gap and no repeat, so a missing fixture cannot hide."""
    numbers = sorted(
        int(match.group(1))
        for path in (*LIVE_PATHS, *BLOCKED_PATHS)
        if (match := _FIXTURE_NUMBER.match(path.name))
    )
    assert numbers == list(range(1, EXPECTED_TOTAL_FIXTURES + 1))


def test_blocked_fixtures_are_accounted_for() -> None:
    """The three blocked ones stay visible, and each says why in its own file.

    Without this they are three numbers missing from a sequence, which is
    exactly how a flagged question becomes a forgotten one.
    """
    assert len(BLOCKED_PATHS) == EXPECTED_BLOCKED
    for path in BLOCKED_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "BLOCKED" in text, path.name
        assert "THE OPTIONS" in text, (
            f"{path.name}: a blocked fixture must write out the options for the ruling"
        )
        document = _raw(path)
        assert "given" in document, f"{path.name}: keeps its `given` block for when it lands"
        assert "expect" not in document, (
            f"{path.name}: must NOT carry an `expect` block -- asserting either reading "
            "pre-empts the ruling it is waiting for"
        )


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_fixture_loads(path: Path, known_ids: frozenset[str]) -> None:
    """Every live fixture passes the loader: shape, vocabulary and ids.

    The three checks the ticket singles out -- unknown record id, unknown
    situation, unknown tool -- are the loader's, so they happen for every
    consumer rather than only for whoever remembers to call a helper. That the
    loader actually *refuses* each of them is asserted by the
    ``test_loader_rejects_*`` tests below, against deliberately broken text.
    """
    fixture = load_fixture(path, known_ids)
    assert fixture.name, path.name
    assert fixture.situations, f"{path.name}: at least one situation"
    assert fixture.path == path


def test_the_loader_owns_the_schema() -> None:
    """A tripwire: the key sets are the loader's, and this test reads them.

    If someone adds a sixth ``expect`` bucket without deciding what it means,
    this fails rather than the fixtures silently accepting it.
    """
    assert GIVEN_KEYS == ("situations", "available_tools", "evidence")
    assert EXPECT_KEYS == ("ready", "pending", "unavailable", "companions", "prohibited")


# -- the loader refuses what the ticket says it must ----------------------

#: A minimal fixture that loads, as the base for each deliberate defect.
_GOOD = """name: a_valid_fixture
given:
  situations: [code_generation]
  available_tools: [sandbox]
  evidence: {samples: 1}
expect:
  ready: [A1_execution_based]
  pending: {}
  unavailable: {}
  companions: {}
  prohibited: []
"""


def _written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "99_candidate.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_base_text_for_these_tests_actually_loads(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """Otherwise every test below would pass for the wrong reason."""
    fixture = load_fixture(_written(tmp_path, _GOOD), known_ids)
    assert fixture.name == "a_valid_fixture"
    assert fixture.ready == ("A1_execution_based",)


def test_loader_rejects_an_unknown_record_id(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """One character wrong in an id makes an expectation unsatisfiable."""
    broken = _GOOD.replace("A1_execution_based", "A1_executlon_based")
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    assert any("A1_executlon_based" in problem for problem in caught.value.problems)


def test_loader_rejects_an_unknown_id_inside_a_companions_value(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """The easiest place for a bad id to hide: a value, not a key."""
    broken = _GOOD.replace(
        "  companions: {}", "  companions:\n    A1_execution_based: [C1_wilson_c1]"
    )
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    assert any("C1_wilson_c1" in problem for problem in caught.value.problems)


def test_loader_rejects_an_unknown_situation(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """``summarisation`` for ``summarization`` would select nothing, silently."""
    broken = _GOOD.replace("[code_generation]", "[summarisation]")
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    assert any("summarisation" in problem for problem in caught.value.problems)


def test_loader_rejects_an_unknown_tool(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    broken = _GOOD.replace("[sandbox]", "[sandboxx]")
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    assert any("sandboxx" in problem for problem in caught.value.problems)


def test_loader_rejects_a_missing_bucket(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """A fixture omitting ``prohibited`` would assert nothing about it."""
    broken = _GOOD.replace("  prohibited: []\n", "")
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    assert any("prohibited" in problem for problem in caught.value.problems)


def test_loader_rejects_a_list_where_a_map_belongs(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """``unavailable: []`` is the slip in TASKS.md's own example."""
    broken = _GOOD.replace("  unavailable: {}", "  unavailable: []")
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    assert any("unavailable" in problem for problem in caught.value.problems)


def test_loader_reports_every_problem_at_once(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """Three defects, one raise, naming all three.

    The record loader aggregates for the same reason: fixing a file one
    exception at a time is a round trip per defect.
    """
    broken = (
        _GOOD.replace("[code_generation]", "[summarisation]")
        .replace("[sandbox]", "[sandboxx]")
        .replace("A1_execution_based", "A1_executlon_based")
    )
    with pytest.raises(FixtureError) as caught:
        load_fixture(_written(tmp_path, broken), known_ids)
    problems = "\n".join(caught.value.problems)
    assert len(caught.value.problems) >= 3, caught.value.problems
    for needle in ("summarisation", "sandboxx", "A1_executlon_based"):
        assert needle in problems


def test_a_loaded_fixture_cannot_be_edited_in_place(
    tmp_path: Path, known_ids: frozenset[str]
) -> None:
    """``CLAUDE.md`` §7.4 enforced by the type, not by discipline."""
    fixture = load_fixture(_written(tmp_path, _GOOD), known_ids)
    with pytest.raises(TypeError):
        fixture.pending["A1_execution_based"] = "invented"  # type: ignore[index]
    with pytest.raises(Exception):
        fixture.ready = ()  # type: ignore[misc]


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_fixture_buckets_are_disjoint(path: Path, known_ids: frozenset[str]) -> None:
    """A record is ready, or pending, or unavailable -- never two of the three.

    ``prohibited`` is deliberately **excluded** from this check. ``D1`` in
    fixture 12 is both ``ready`` and ``prohibited``, because it is the
    prohibition *and* the measurement and step 2 runs before step 4. That
    overlap is real and is awaiting a ruling (``S17-REPORT.md`` §4, Q4), so the
    test must not assert it away.
    """
    fixture = load_fixture(path, known_ids)
    ready = set(fixture.ready)
    pending = set(fixture.pending)
    unavailable = set(fixture.unavailable)
    for left, right, left_name, right_name in (
        (ready, pending, "ready", "pending"),
        (ready, unavailable, "ready", "unavailable"),
        (pending, unavailable, "pending", "unavailable"),
    ):
        overlap = sorted(left & right)
        assert not overlap, f"{path.name}: {overlap} is in both {left_name} and {right_name}"


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_companions_are_declared_by_the_record_that_names_them(
    path: Path, records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    """A fixture cannot invent a companion edge the registry does not hold.

    This is the check that keeps the fixtures honest about *why* a companion
    appears: the registry's ``companion_checks`` is the source, and a fixture
    asserting ``X: [Y]`` where the record X never names Y would be describing a
    planner nobody is going to build.
    """
    by_id = {record.id: record for record in records}
    for host, listed in load_fixture(path, known_ids).companions.items():
        declared = set(by_id[host].companion_checks)
        invented = sorted(set(listed) - declared)
        assert not invented, (
            f"{path.name}: {host} is asserted to pull in {invented}, but its "
            f"companion_checks is {sorted(declared)}"
        )


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_pending_reasons_name_a_real_requirement(
    path: Path, records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    """Each pending reason names a key that the record's ``requires`` holds.

    The exact sentence is ``EL-121``'s to render; what a fixture can pin now is
    that the *reason* is about a real requirement. A fixture saying
    ``"needs paired_runs: 2"`` for a record whose key is ``discordant_pairs``
    is the failure this catches -- and it is not hypothetical, it is what
    ``TASKS.md``'s own illustrative example said before S17 corrected it.
    """
    by_id = {record.id: record for record in records}
    for record_id, reason in load_fixture(path, known_ids).pending.items():
        keys = set(by_id[record_id].requires)
        assert keys, (
            f"{path.name}: {record_id} is asserted pending but its requires is empty, "
            "so nothing could hold it back"
        )
        named = [key for key in keys if key in reason]
        assert named, (
            f"{path.name}: {record_id}'s reason {reason!r} names none of its "
            f"requirement keys {sorted(keys)}"
        )


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_unavailable_lists_tools_the_record_actually_requires(
    path: Path, records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    """A record is unavailable for tools it requires, and that the fixture withholds."""
    by_id = {record.id: record for record in records}
    document = _raw(path)
    given, expect = document["given"], document["expect"]
    assert isinstance(given, dict) and isinstance(expect, dict)
    granted = {str(name) for name in given["available_tools"]}  # type: ignore[union-attr]
    unavailable = expect["unavailable"]
    assert isinstance(unavailable, dict)
    for record_id, missing in unavailable.items():
        assert isinstance(missing, list) and missing, (
            f"{path.name}: {record_id} is unavailable for no stated tool"
        )
        required = {tool.value for tool in by_id[record_id].required_tools}
        for tool_name in missing:
            assert tool_name in required, (
                f"{path.name}: {record_id} is said to be missing {tool_name!r}, which it "
                f"does not require (it requires {sorted(required)})"
            )
            assert tool_name not in granted, (
                f"{path.name}: {record_id} is said to be missing {tool_name!r}, but the "
                "fixture grants it"
            )


@pytest.mark.parametrize("path", LIVE_PATHS, ids=lambda p: p.stem)
def test_ready_is_in_step_seven_order(
    path: Path, records: tuple[TechniqueRecord, ...], known_ids: frozenset[str]
) -> None:
    """A fixture's ``ready`` list is ordered by the one rule, not by hand.

    ``ready`` asserts order (``TASKS.md`` group 6: "# order matters"), so the
    fixtures are the specification for the tie-breaking rules and this is where
    they and ``query.sort_key`` are held to each other. If a fixture is ever
    edited into an order the rule does not produce, that is a question for a
    human -- either the rule or the fixture is wrong -- and ``CLAUDE.md`` §7.4
    says not to resolve it by editing the fixture.

    Note that ``ready`` can hold records ``match`` never selected: a companion
    is pulled in at step 6 from outside the situation's own set, as
    ``C1_wilson_ci`` is in most fixtures. The *order* is still step 7's, which
    is why this checks the sort key rather than re-running ``match``.
    """
    by_id = {record.id: record for record in records}
    ready = load_fixture(path, known_ids).ready
    keys = [sort_key(by_id[record_id]) for record_id in ready]
    assert keys == sorted(keys), (
        f"{path.name}: ready is not in step-7 order. Asserted {ready}, "
        f"the rule gives {sorted(ready, key=lambda i: sort_key(by_id[i]))}"
    )


# The real comparison -- ``plan()`` against every ``expect`` block -- is live in
# ``tests/test_planner.py::test_fixture`` as of EL-124. It was parked here with a
# skip while ``evalloop/plan`` did not exist; the skip is gone rather than kept,
# because a skipped test that has been superseded is just noise in the summary.
