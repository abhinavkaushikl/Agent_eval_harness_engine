"""``plan`` and ``Plan``: the seven steps assembled, and what a human reads.

``AGENT.md`` §3.5 fixes the signature and the order. The order **is** the
behaviour, and three places in it are load-bearing rather than arbitrary:

* **Step 2 before 3 and 4.** A constraint fires on the situation alone, so a
  prohibition does not wait for a tool grant or for evidence. "Never accuracy on
  a rare class" is true on the first observation.
* **Step 3 before 4.** A record missing a tool lands in ``unavailable`` and
  never reaches the readiness check, so it never shows a pending reason.
  ``G3_faithfulness`` without ``llm_api`` is unavailable, not "pending on
  recall@k" -- which is why fixture 4 grants ``llm_api`` at all.
* **Step 5 before 6.** Conflicts are resolved among the records the situation
  selected, *then* companions are pulled in. A suppressed record does not get
  to drag its companions into the plan.

The companion loop
------------------
Step 6 is iterative, and ``rules.py``'s ruling 2b is why: a companion edge is
followed only from a record that is itself **ready**. ``resolve_companions``
expands one level, this function buckets what came back, and it calls again with
the newly ready records until a round adds nothing. Without the loop, fixture
10 would offer to bootstrap a confidence interval around a κ that does not
exist, and fixtures 7 to 9 would add a pending A/A baseline for a diff that
cannot be computed yet.

The loop terminates: the ready set only grows, it is bounded by the registry,
and a round that adds nothing ends it. ``MAX_COMPANION_ROUNDS`` is a guard
against a future registry, not against this one -- the deepest chain today
settles in two rounds.

What ``prohibited`` can and cannot say
--------------------------------------
``Plan.prohibited`` holds the ids of the ``constraint`` records the situation
selected, which is ``AGENT.md`` §3.5's "constraint records that fired". It does
**not** remove anything from ``ready``, and that is not an oversight: what
``D1_pr_curve_never_accuracy`` forbids is *accuracy*, and **no field names the
forbidden metric** (``S14-REPORT.md`` finding F5, which ``TASKS.md`` S23 also
records). There is no accuracy record to remove, so step 2's "anything they
prohibit leaves ready" is a no-op against this registry, and will stay one until
F5 is resolved.

A constraint record therefore appears in ``prohibited`` and, if it also carries
a measurement, in ``ready`` as well. ``D1`` is both "never accuracy" and the
PR-curve measurement, so fixture 12 has it in both. That overlap is real,
awaiting a ruling (``S17-REPORT.md`` §4, Q4), and is not asserted away here.

``prohibition_reasons`` is a sixth field beyond §3.5's five. It is needed
because ``USER_EXPERIENCE.md`` §3.1 renders a reason on the PROHIBITED line and
§4 principle 3 requires one -- "every 'no' has a reason" -- and the five-field
shape cannot carry it. The reason is built from the fields that do exist: the
situations that selected the record, and its ``anti_pattern``, which is where
the corpus's own figure lives. The *subject* of the prohibition is still
missing, so the line reads ``D1_pr_curve_never_accuracy  rare_class: Predicting
"all good" scores 97% accuracy…`` where the mock wants ``accuracy  rare_class:
…``. Reported rather than invented.

Purity
------
``plan`` reads its four arguments and nothing else: no file, no clock, no
global, no mutation of anything passed in. Same inputs, same plan, same render
-- ``USER_EXPERIENCE.md`` §4 principle 7, so a user can trust a diff.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from evalloop.plan.capability import check_capability
from evalloop.plan.readiness import evaluate_readiness
from evalloop.plan.rules import apply_conflicts, resolve_companions
from evalloop.registry.query import match, sort_key
from evalloop.registry.schema import RecordType, TechniqueRecord
from evalloop.vocab import Situation, Tool

__all__ = ["MAX_COMPANION_ROUNDS", "Plan", "plan"]

#: A guard against a future registry, not against this one. The deepest
#: companion chain today settles in two rounds; a runaway would mean a cycle
#: that grows the ready set, which the fixed point cannot produce.
MAX_COMPANION_ROUNDS = 16

#: ``READY`` is a single line of ids. ``USER_EXPERIENCE.md`` §3.1 and
#: ``TASKS.md`` S23 both separate them with a middle dot.
_READY_SEPARATOR = " · "

#: The four state labels, always printed, in this order. Width is fixed so the
#: reason column lines up across all four rows.
_STATES = ("READY", "PENDING", "UNAVAILABLE", "PROHIBITED")
_LABEL_WIDTH = max(len(state) for state in _STATES) + 2

#: Minimum width of the id column, from §3.1's mock. A plan with longer ids
#: widens it; the width is computed from the ids the plan actually shows, so it
#: is a function of the plan and a re-render of the same plan is identical.
_MIN_ID_WIDTH = 18

#: What an empty state prints. Not blank: §3.1 says all four states are always
#: visible, because "nothing is pending" is information.
_NONE = "(none)"


@dataclass(frozen=True)
class Plan:
    """What applies here, what does not yet, and why not -- the four states.

    ``ready`` holds records, in step-7 order. The other four are keyed by
    record id, because a caller that has a reason wants to look it up rather
    than scan.
    """

    ready: tuple[TechniqueRecord, ...]
    pending: Mapping[str, str]
    unavailable: Mapping[str, tuple[Tool, ...]]
    companions: Mapping[str, tuple[str, ...]]
    prohibited: tuple[str, ...]
    prohibition_reasons: Mapping[str, str]

    def __post_init__(self) -> None:
        for record_id in self.prohibited:
            if record_id not in self.prohibition_reasons:
                raise ValueError(
                    f"{record_id} is prohibited with no reason; "
                    "USER_EXPERIENCE.md section 4 principle 3 requires one"
                )

    def render(self) -> str:
        """The four states, as ``USER_EXPERIENCE.md`` §3.1 prints them.

        Deterministic and diffable: every sequence is already ordered by the
        time it gets here, and nothing is sorted by a hash or a set.
        """
        # +2 so the reason column clears the longest id, as §3.1's mock does
        width = max(_MIN_ID_WIDTH, *(len(name) + 2 for name in self._named_ids()))
        lines = [
            self._state_line(
                "READY",
                [_READY_SEPARATOR.join(record.id for record in self.ready)]
                if self.ready
                else [],
            )
        ]
        lines.append(
            self._state_line(
                "PENDING",
                [f"{key.ljust(width)}{self.pending[key]}" for key in self.pending],
            )
        )
        lines.append(
            self._state_line(
                "UNAVAILABLE",
                [
                    f"{key.ljust(width)}missing: "
                    + ", ".join(tool.value for tool in self.unavailable[key])
                    for key in self.unavailable
                ],
            )
        )
        lines.append(
            self._state_line(
                "PROHIBITED",
                [
                    f"{key.ljust(width)}{self.prohibition_reasons[key]}"
                    for key in self.prohibited
                ],
            )
        )
        return "\n".join(lines)

    def _named_ids(self) -> tuple[str, ...]:
        """Every id the render shows in a column, for the column width."""
        return (
            *self.pending,
            *self.unavailable,
            *self.prohibited,
            "",  # so ``max`` has an argument even when all three are empty
        )

    def _state_line(self, state: str, rows: list[str]) -> str:
        label = state.ljust(_LABEL_WIDTH)
        if not rows:
            return f"{label}{_NONE}"
        continuation = " " * _LABEL_WIDTH
        return "\n".join(
            f"{label if index == 0 else continuation}{row}"
            for index, row in enumerate(rows)
        )


def _prohibition_reason(
    record: TechniqueRecord, situations: frozenset[Situation]
) -> str:
    """``<the situations that selected it>: <its anti_pattern>``.

    The closest the schema allows to §3.1's PROHIBITED line. The subject of the
    prohibition is not in any field (finding F5), so the line names the record
    and the harm instead of the forbidden metric.
    """
    fired_on = sorted(
        situation.value for situation in record.triggers_on_situation if situation in situations
    )
    return f"{', '.join(fired_on)}: {record.anti_pattern}"


def plan(
    records: Iterable[TechniqueRecord],
    situations: Iterable[Situation],
    available_tools: Iterable[Tool],
    evidence: Mapping[str, object],
) -> Plan:
    """``AGENT.md`` §3.5's seven steps, in that order. Pure.

    ``records`` is normally the whole registry; ``match`` selects from it. The
    three iterables are consumed once each, so generators work.
    """
    all_records = tuple(records)
    wanted = frozenset(situations)
    granted = tuple(available_tools)

    # 1. match -- multi-label, no duplication, already in step-7 order
    matched = match(all_records, wanted)

    # 2. constraints -> prohibited, with the reason
    prohibited = tuple(
        record.id for record in matched if record.type is RecordType.constraint
    )
    prohibition_reasons = {
        record.id: _prohibition_reason(record, wanted)
        for record in matched
        if record.type is RecordType.constraint
    }

    pending: dict[str, str] = {}
    unavailable: dict[str, tuple[Tool, ...]] = {}
    ready: list[TechniqueRecord] = []

    def bucket(record: TechniqueRecord) -> None:
        """Steps 3 then 4, in that order, for one record."""
        capability = check_capability(record, granted)
        if not capability.available:
            unavailable[record.id] = capability.missing
            return
        readiness = evaluate_readiness(record, evidence)
        if readiness.met:
            ready.append(record)
        else:
            assert readiness.reason is not None  # the type guarantees it
            pending[record.id] = readiness.reason

    for record in matched:
        bucket(record)

    # 5. conflicts, among what the situation selected and what survived 3 and 4
    ready = list(apply_conflicts(ready).kept)

    # 6. companions, one level at a time, following edges only out of ready
    companions: dict[str, tuple[str, ...]] = {}
    for _ in range(MAX_COMPANION_ROUNDS):
        step = resolve_companions(ready, all_records)
        companions.update(step.demanded)
        fresh = [
            record
            for record in step.added
            if record.id not in pending and record.id not in unavailable
        ]
        if not fresh:
            break
        before = len(ready)
        for record in fresh:
            bucket(record)
        if len(ready) == before:
            break  # everything new went to pending or unavailable

    # 7. deterministic order
    ready.sort(key=sort_key)

    return Plan(
        ready=tuple(ready),
        pending=MappingProxyType(pending),
        unavailable=MappingProxyType(unavailable),
        companions=MappingProxyType(companions),
        prohibited=prohibited,
        prohibition_reasons=MappingProxyType(prohibition_reasons),
    )
