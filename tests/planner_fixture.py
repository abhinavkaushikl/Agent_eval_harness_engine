"""The planner-fixture schema, and a loader that fails loudly.

Not a test module -- a helper that ``test_planner_fixtures.py`` and (from
EL-123) the planner comparison both import, so the schema is stated once.

The schema, from ``TASKS.md`` group 6
------------------------------------
::

    name: code_generation_first_run
    given:
      situations: [code_generation]            # >= 1, every one a Situation value
      available_tools: [sandbox, test_runner]  # may be empty; every one a Tool value
      evidence: {samples: 1, runs: 1}          # minimal: only what the fixture tests
    expect:
      ready: [A1_execution_based, C1_wilson_ci]   # ORDERED, per AGENT.md 3.5 step 7
      pending:
        B3_mcnemar: "needs discordant_pairs: 25, have 0"
      unavailable:
        A1_execution_based: [sandbox]
      companions:
        A1_execution_based: [C1_wilson_ci]
      prohibited: []

Two deviations from the example in ``TASKS.md``, both because ``AGENT.md`` §3.5
types the ``Plan`` fields and the example does not:

* ``unavailable`` and ``companions`` are **maps** keyed by record id, not lists.
  ``Plan.unavailable`` is ``Mapping[str, tuple[Tool, ...]]`` and
  ``Plan.companions`` is ``Mapping[str, tuple[str, ...]]``. An empty one is
  ``{}``; the example writes ``unavailable: []``.
* ``ready`` and ``prohibited`` stay lists, because ``Plan.ready`` is ordered and
  ``Plan.prohibited`` is a tuple of ids.

What the loader refuses, and why it aggregates
----------------------------------------------
``load_fixture`` raises ``FixtureError`` naming **every** problem in the file at
once, not the first. A fixture has five buckets and three ``given`` keys, and
fixing them one exception at a time is the round-trip the record loader already
refuses to inflict on an author.

The three the ticket singles out are the three that would otherwise pass
silently into a planner comparison and look like a planner bug:

* **an unknown record id**, in any bucket, including inside ``companions``
  values. Ids are the registry's primary key; ``C1_wilson_c1`` for
  ``C1_wilson_ci`` is a one-character defect that makes an expectation
  unsatisfiable.
* **an unknown situation** -- ``summarisation`` for ``summarization`` selects
  nothing, which ``CLAUDE.md`` §6 calls the most important correctness decision
  in M0.
* **an unknown tool** -- ``llm_api_crossfamily`` is granted to nothing, so every
  record needing it reads as unavailable for a reason the author did not mean.

Parsing goes through ``parse_situation`` and ``parse_tool``, never a string
compare, so the fixtures and the records share one spelling authority.

What the loader deliberately does **not** check
-----------------------------------------------
Anything needing the records' *content* rather than their ids: whether a
``pending`` reason names a requirement the record actually has, whether a
``companions`` edge is one the registry declares, whether ``ready`` is in
step-7 order. Those live in ``test_planner_fixtures.py`` as their own named
tests, because each is a distinct claim about the methodology and deserves to
fail by name. The loader's job is the file; the tests' job is the meaning.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from evalloop.registry.format import FormatError, Node, load
from evalloop.vocab import Situation, Tool, parse_situation, parse_tool

__all__ = [
    "EXPECT_KEYS",
    "GIVEN_KEYS",
    "FixtureError",
    "PlannerFixture",
    "load_fixture",
]

#: ``TASKS.md`` group 6 fixes both key sets. Every key is required: a fixture
#: that omits ``prohibited`` would otherwise silently assert nothing about it,
#: which is the failure the format exists to catch.
GIVEN_KEYS = ("situations", "available_tools", "evidence")
EXPECT_KEYS = ("ready", "pending", "unavailable", "companions", "prohibited")

_TOP_LEVEL_KEYS = ("name", "given", "expect")


class FixtureError(Exception):
    """A fixture that does not load, naming the file and every problem in it."""

    def __init__(self, path: Path, problems: Sequence[str]) -> None:
        self.path = path
        self.problems = tuple(problems)
        joined = "\n  - ".join(self.problems)
        super().__init__(f"{path.name}: {len(self.problems)} problem(s):\n  - {joined}")


@dataclass(frozen=True)
class PlannerFixture:
    """One fixture, parsed and vocabulary-checked.

    The sequence fields are tuples and the mappings are read-only, so a test
    cannot edit a fixture in memory and then assert against its own edit --
    which is ``CLAUDE.md`` §7.4 ("never edit a fixture to make a test pass")
    enforced by the type rather than by discipline.
    """

    path: Path
    name: str
    situations: tuple[Situation, ...]
    available_tools: tuple[Tool, ...]
    evidence: Mapping[str, int | float | bool]
    ready: tuple[str, ...]
    pending: Mapping[str, str]
    unavailable: Mapping[str, tuple[str, ...]]
    companions: Mapping[str, tuple[str, ...]]
    prohibited: tuple[str, ...]

    def record_ids(self) -> tuple[str, ...]:
        """Every record id the ``expect`` block mentions, companions included.

        Deduplicated, in first-seen order over the buckets in schema order, so
        an error message lists them the way the file reads.
        """
        seen: dict[str, None] = {}
        for record_id in (*self.ready, *self.prohibited):
            seen.setdefault(record_id, None)
        for mapping in (self.pending, self.unavailable, self.companions):
            for key in mapping:
                seen.setdefault(key, None)
        for listed in self.companions.values():
            for record_id in listed:
                seen.setdefault(record_id, None)
        return tuple(seen)


def _require_keys(
    where: str, mapping: Mapping[str, Node], expected: Sequence[str], problems: list[str]
) -> bool:
    missing = [key for key in expected if key not in mapping]
    for key in missing:
        problems.append(f"{where}: missing required key {key!r}")
    for key in mapping:
        if key not in expected:
            problems.append(
                f"{where}: unknown key {key!r}; the schema is {', '.join(expected)}"
            )
    return not missing


def _str_list(where: str, value: Node, problems: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        problems.append(f"{where}: must be a list, not {type(value).__name__}")
        return ()
    return tuple(str(item) for item in value)


def _str_map(where: str, value: Node, problems: list[str]) -> Mapping[str, Node]:
    if not isinstance(value, dict):
        problems.append(
            f"{where}: must be a map keyed by record id -- write {{}} when empty, not []"
        )
        return {}
    return value


def load_fixture(path: Path, known_ids: Iterable[str]) -> PlannerFixture:
    """Parse and validate one fixture file, or raise ``FixtureError``.

    ``known_ids`` is the set of real record ids, normally
    ``{record.id for record in load_records(RECORDS_DIR)}``. It is a parameter
    rather than a module-level load so a test can hand in a hand-built
    registry, and so this module does no I/O beyond reading ``path``.
    """
    known = frozenset(known_ids)
    problems: list[str] = []

    try:
        document = load(path.read_text(encoding="utf-8"))
    except FormatError as error:
        raise FixtureError(path, [f"does not parse: {error}"]) from error

    if not _require_keys("top level", document, _TOP_LEVEL_KEYS, problems):
        raise FixtureError(path, problems)

    raw_name = document["name"]
    name = raw_name if isinstance(raw_name, str) and raw_name else ""
    if not name:
        problems.append("name: must be a non-empty string")

    raw_given = document["given"]
    raw_expect = document["expect"]
    given: Mapping[str, Node] = {}
    expect: Mapping[str, Node] = {}
    if isinstance(raw_given, dict):
        given = raw_given
    else:
        problems.append("given: must be a block map")
    if isinstance(raw_expect, dict):
        expect = raw_expect
    else:
        problems.append("expect: must be a block map")

    given_ok = _require_keys("given", given, GIVEN_KEYS, problems)
    expect_ok = _require_keys("expect", expect, EXPECT_KEYS, problems)
    if not (given_ok and expect_ok):
        raise FixtureError(path, problems)

    situations: list[Situation] = []
    raw_situations = _str_list("given.situations", given["situations"], problems)
    if not raw_situations:
        problems.append("given.situations: must name at least one situation")
    for raw in raw_situations:
        try:
            situations.append(parse_situation(raw))
        except ValueError as error:
            problems.append(f"given.situations: {error}")

    tools: list[Tool] = []
    for raw in _str_list("given.available_tools", given["available_tools"], problems):
        try:
            tools.append(parse_tool(raw))
        except ValueError as error:
            problems.append(f"given.available_tools: {error}")

    evidence: dict[str, int | float | bool] = {}
    raw_evidence = given["evidence"]
    if not isinstance(raw_evidence, dict):
        problems.append("given.evidence: must be a map, for example {samples: 1}")
    else:
        for key, value in raw_evidence.items():
            if isinstance(value, (bool, int, float)):
                evidence[key] = value
            else:
                problems.append(
                    f"given.evidence[{key!r}]: must be a number or true/false, "
                    f"not {type(value).__name__}"
                )

    ready = _str_list("expect.ready", expect["ready"], problems)
    prohibited = _str_list("expect.prohibited", expect["prohibited"], problems)
    pending_raw = _str_map("expect.pending", expect["pending"], problems)
    unavailable_raw = _str_map("expect.unavailable", expect["unavailable"], problems)
    companions_raw = _str_map("expect.companions", expect["companions"], problems)

    pending: dict[str, str] = {}
    for key, value in pending_raw.items():
        if isinstance(value, str) and value:
            pending[key] = value
        else:
            problems.append(
                f"expect.pending[{key!r}]: must be the unmet requirement as prose, "
                'in the form "needs <key>: <threshold>, have <actual>"'
            )

    unavailable: dict[str, tuple[str, ...]] = {}
    for key, value in unavailable_raw.items():
        missing = _str_list(f"expect.unavailable[{key!r}]", value, problems)
        if not missing:
            problems.append(
                f"expect.unavailable[{key!r}]: must name at least one missing tool"
            )
        for raw in missing:
            try:
                parse_tool(raw)
            except ValueError as error:
                problems.append(f"expect.unavailable[{key!r}]: {error}")
        unavailable[key] = missing

    companions: dict[str, tuple[str, ...]] = {}
    for key, value in companions_raw.items():
        listed = _str_list(f"expect.companions[{key!r}]", value, problems)
        if not listed:
            problems.append(
                f"expect.companions[{key!r}]: must name at least one companion"
            )
        companions[key] = listed

    fixture = PlannerFixture(
        path=path,
        name=name,
        situations=tuple(situations),
        available_tools=tuple(tools),
        evidence=MappingProxyType(evidence),
        ready=ready,
        pending=MappingProxyType(pending),
        unavailable=MappingProxyType(unavailable),
        companions=MappingProxyType(companions),
        prohibited=prohibited,
    )

    for record_id in fixture.record_ids():
        if record_id not in known:
            problems.append(
                f"{record_id!r} is not a record id. Record ids are the registry's "
                "primary key; check the spelling against evalloop/registry/records/"
            )

    if problems:
        raise FixtureError(path, problems)
    return fixture
