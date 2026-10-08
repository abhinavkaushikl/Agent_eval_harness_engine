"""``match``: which records a situation selects, in the order a plan reads them.

This is step 1 of ``AGENT.md`` §3.5's resolution order ("match records whose
``triggers_on_situation`` intersects the input") carrying step 7's ordering
("graders by ``ladder_priority`` ascending, then non-graders grouped by
``type``, then ``id`` alphabetically") so that a caller never sees an unordered
intermediate. Steps 2 to 6 -- constraints, capability, readiness,
``conflicts_with``, ``companion_checks`` -- belong to ``evalloop/plan`` and are
deliberately **not** here. ``match`` does not know what tools you have or how
much data you have collected; it answers one question, "what is this situation
about", and answers it the same way every time.

Purity
------
``match`` reads its arguments and nothing else: no file, no clock, no global.
It does not mutate the records (they are frozen) nor the iterables it is
given, and it consumes each exactly once, so a generator works. Two calls with
the same records and situations return equal tuples, and **shuffling either
argument changes nothing** -- the output order comes entirely from the sort key
below. That last property is what makes a fixture's ``ready`` list a meaningful
assertion: if input order leaked into output order, every fixture would be
asserting the order its author happened to type.

The order of the type groups, and why it is this one
---------------------------------------------------
``AGENT.md`` §3.5 fixes "graders first, then non-graders grouped by type", and
leaves the order *of the groups* open. ``TYPE_GROUP_ORDER`` fixes it as:

    grader -> metric -> statistic -> diagnostic -> procedure -> constraint

**The reason is the data flow between the types.** Each group consumes what the
one before it produces, which is the same chain ``schema.RecordType``'s own
docstring uses to tell them apart:

1. a **grader** renders a verdict on an artifact;
2. a **metric** aggregates verdicts into a number;
3. a **statistic** says whether that number is real;
4. a **diagnostic** explains the number when it looks wrong;
5. a **procedure** changes how you work as a result;
6. a **constraint** forbids something.

So a rendered plan reads top to bottom in the order the work actually happens:
grade, measure, test, explain, change the process. Nothing is ordered before
the thing it depends on, which is the property that makes the order *mean*
something rather than merely being fixed.

``constraint`` is last for a second reason: a constraint's content is a
prohibition, and the planner reports that in ``Plan.prohibited``. When a
constraint record also appears in ``ready`` -- as ``D1_pr_curve_never_accuracy``
does, being both "never accuracy on a rare class" and the PR-curve measurement
-- its presence there is incidental to its prohibition, so it sorts after the
techniques a reader is meant to act on.

The order deliberately matches ``RecordType``'s declaration order, and
``test_query.py`` asserts that ``TYPE_GROUP_ORDER`` covers every member, so
adding a seventh type fails a test until someone decides where it belongs
rather than silently sorting it first or last.

Graders, and the ones with no rung
----------------------------------
Within the grader group the key is ``ladder_priority`` ascending: 1 execution,
2 end-state, 3 deterministic, 4 judge, 5 human
(``A-choosing-how-to-grade.md:11-18``). Two graders may legitimately share a
rung -- ``A3_normalised_exact_match`` and ``A5_schema_field_scoring`` both carry
3, because the corpus gives them the identical "deterministic, zero cost"
annotation and reaches them from mutually exclusive branches -- and that tie is
broken by ``id``, which is a presentation choice and not a claim about the
methodology.

A grader with ``ladder_priority: None`` sorts **after** every runged grader,
not at a guessed rung. ``B2_pairwise_preference`` is the live case: it is a
grader in section B that the corpus never places on section A's ladder, and
EL-113 declined to invent a rung for it rather than silence a checker. Sorting
it last among graders is the same refusal expressed as an ordering: it is still
a grader, and it still cannot be compared with the ladder.
"""

from __future__ import annotations

from collections.abc import Iterable

from evalloop.registry.schema import RecordType, TechniqueRecord
from evalloop.vocab import Situation

__all__ = ["TYPE_GROUP_ORDER", "match", "sort_key"]

#: The fixed order of the type groups. See the module docstring for the
#: derivation; ``test_query.py`` asserts it covers every ``RecordType``.
TYPE_GROUP_ORDER: tuple[RecordType, ...] = (
    RecordType.grader,
    RecordType.metric,
    RecordType.statistic,
    RecordType.diagnostic,
    RecordType.procedure,
    RecordType.constraint,
)

_TYPE_RANK: dict[RecordType, int] = {
    record_type: rank for rank, record_type in enumerate(TYPE_GROUP_ORDER)
}

#: Sorts an unrunged grader after every runged one. Not a rung: the two
#: elements of the key stay separate so ``None`` never compares as a number.
_UNRUNGED = (True, 0)


def sort_key(record: TechniqueRecord) -> tuple[int, bool, int, str]:
    """``AGENT.md`` §3.5 step 7, as a sort key.

    Exposed because ``evalloop/plan`` orders ``Plan.ready`` the same way after
    steps 2 to 6 have added companions and removed conflicts, and two
    implementations of one rule would drift. Tests also use it to assert that a
    fixture's ``ready`` list is in step-7 order.
    """
    rung_is_absent, rung = (
        _UNRUNGED if record.ladder_priority is None else (False, record.ladder_priority)
    )
    return (_TYPE_RANK[record.type], rung_is_absent, rung, record.id)


def match(
    records: Iterable[TechniqueRecord], situations: Iterable[Situation]
) -> tuple[TechniqueRecord, ...]:
    """Every record at least one of ``situations`` triggers, in step-7 order.

    Multi-label input **merges without duplication**: a record triggered by two
    of the input situations appears once, because the records are walked once
    and tested against the whole situation set rather than once per situation.

    An empty ``situations`` selects nothing. That is the honest answer -- no
    situation has been inferred, so no technique has been shown to apply -- and
    not "everything", which would be a plan the methodology never justifies.

    What this deliberately does not do: resolve two *distinct* records sharing
    an ``id``. That is an integrity defect, ``check_integrity`` reports it by
    name, and both copies are returned here so the defect stays visible instead
    of being silently halved.
    """
    wanted = frozenset(situations)
    if not wanted:
        return ()
    selected = [
        record for record in records if not wanted.isdisjoint(record.triggers_on_situation)
    ]
    return tuple(sorted(selected, key=sort_key))
