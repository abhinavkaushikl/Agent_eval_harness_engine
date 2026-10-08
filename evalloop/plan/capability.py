"""``check_capability``: which tools a record needs that the session has not got.

Step 3 of ``AGENT.md`` §3.5, and it runs **before** readiness (step 4). The
order matters and is visible in every plan: a record missing a tool lands in
``unavailable`` and never reaches the readiness check, so it never shows a
pending reason. ``G3_faithfulness`` without ``llm_api`` is unavailable, not
"pending on recall@k", and fixture 4 grants ``llm_api`` precisely so the build
order it exists to test is reachable at all.

A missing tool is a question, never a skip
------------------------------------------
``AGENT.md`` §5: "Missing tool -> ask permission, don't skip silently."
``USER_EXPERIENCE.md`` §2 says the session interrupts for a permission request
"only when a technique needs a tool you haven't granted", and §4 principle 6 is
"user controls access -- tools, credentials and connectors are opt-in via
permission requests".

So **this function's whole job is to name what is missing**, well enough for the
session layer to ask for it. It does not decide whether to ask, does not rank
the request, and does not know what a grant costs. It answers one question
about one record, which is why it needs no state.

Why ``missing`` is ordered, and in this order
---------------------------------------------
``missing`` is rendered -- ``USER_EXPERIENCE.md`` §3.1 shows
``UNAVAILABLE  H7_trajectory  missing: trace_capture`` -- and a rendered
sequence that varies between runs breaks §4 principle 7, "same inputs, same
plan, same render, so users can trust diffs". A ``set`` difference would do
exactly that.

The order kept is **the record's own ``required_tools`` order**, filtered. Two
alternatives were considered and rejected:

* *alphabetical* -- deterministic, but it discards information. ``H1`` requires
  ``sandbox``, ``snapshot_restore``, ``trace_capture`` in the order ``H:36-38``
  introduces them ("Snapshot the environment", then "Mock external APIs", then
  "Log everything"), so the record's order is the source's order of mention.
* *``Tool`` declaration order* -- also deterministic, but it imposes the
  vocabulary's order on a record that has its own.

Keeping the record's order means a permission request lists what the technique
needs in the order its own method describes needing it.

What counts as granted
----------------------
Exact membership, and nothing clever. There is deliberately **no subsumption**:
``llm_api_cross_family`` does not satisfy ``llm_api``, although a cross-family
API is an LLM API. That is a real gap and it is not papered over here --
``AGENT.md`` §4 puts routing and grant kinds in the capability *layer* (decision
``EL-002``), which is where an implication like that belongs, because deciding
that one grant covers another is a policy question about what the user agreed
to. A record asks for a capability; this function reports whether that exact
capability was granted. Reported as a finding in ``S19-REPORT.md`` §5.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from evalloop.registry.schema import TechniqueRecord
from evalloop.vocab import Tool

__all__ = ["Capability", "check_capability"]


@dataclass(frozen=True)
class Capability:
    """Whether a record can run at all, and what to ask for if not.

    ``missing`` is empty exactly when ``available`` is true, so a caller cannot
    render a permission request for a record that needs nothing.
    """

    available: bool
    missing: tuple[Tool, ...]

    def __post_init__(self) -> None:
        if self.available and self.missing:
            raise ValueError(
                f"available capability lists missing tools: "
                f"{[tool.value for tool in self.missing]}"
            )
        if not self.available and not self.missing:
            raise ValueError("unavailable capability must name the missing tools")

    def render(self) -> str:
        """``missing: trace_capture``, as ``USER_EXPERIENCE.md`` §3.1 prints it."""
        return "missing: " + ", ".join(tool.value for tool in self.missing)


#: The available result, shared because it carries no per-record information.
_AVAILABLE = Capability(available=True, missing=())


def check_capability(
    record: TechniqueRecord, available_tools: Iterable[Tool]
) -> Capability:
    """Which of ``record``'s required tools are not in ``available_tools``.

    Pure: reads both arguments, mutates neither, and consumes
    ``available_tools`` once, so a generator works. A record requiring no tool
    is always available -- 25 of the 73 are, which is why a plan can say
    something useful before the user has granted anything.
    """
    granted = frozenset(available_tools)
    missing = tuple(tool for tool in record.required_tools if tool not in granted)
    if not missing:
        return _AVAILABLE
    return Capability(available=False, missing=missing)
