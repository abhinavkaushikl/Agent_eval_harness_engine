"""``apply_conflicts`` and ``resolve_companions``: steps 5 and 6 of §3.5.

Step 5 removes a record another record replaces. Step 6 adds the records that
must be reported alongside a ready one. Both are pure, both read the frozen
registry, and both are deliberately *small*, because each one encodes a ruling
the corpus only half-states and the rulings are what the docstrings are for.

---------------------------------------------------------------------------
RULING 1 -- what suppresses what, when neither record has a rung
---------------------------------------------------------------------------
``AGENT.md`` §3.5 step 5 says "a higher-priority grader suppresses a conflicting
lower one (execution suppresses judging the same property)". That covers four
of the registry's five conflict edges -- ``A1``, ``A2``, ``A3`` and ``A5`` each
declaring ``conflicts_with: [A4_judge_binary_criteria]``, with rungs 1, 2, 3 and
3 against A4's 4 -- and says nothing about the fifth.

The fifth is ``B7_cluster_bootstrap -> B6_bootstrap_ci``. Both are
``statistic``, so **neither has a ``ladder_priority``** (the schema permits a
rung only on a grader). Priority cannot decide it.

**The edge direction decides it.** ``CLAUDE.md`` §6 defines the field as
"record ids this **replaces/invalidates**" -- a directed claim made *by* the
declaring record *about* the one it names. B7 says it replaces B6, and the
corpus is why: a bootstrap that resamples items when the items come in groups
understates the interval, so the cluster form is not an alternative to it but a
correction of it. Reading the edge in the other direction would keep the number
the methodology says is wrong.

So the rule, in full:

* **Both records graders with a rung** -> suppress only when the declaring
  record's rung is strictly better (lower). This is §3.5's sentence, and it
  means a *lower* grader cannot suppress a higher one even if it claims to --
  an edge like that is a defect, and it is left unapplied and reported rather
  than honoured.
* **Anything else** -> the declaring record replaces the one it names. One
  rung, no rungs, or a mixed pair: the direction of the edge is the whole
  answer, because that is what the field means.

Chains are not resolved, and none exists. Suppression is computed in one pass
over the input set, so a hypothetical ``R -> T -> U`` would drop both T and U.
No record in the registry is both a conflict source and a conflict target
(``A4`` and ``B6`` declare nothing), so the question is not live; if a later
stage authors a chain, the iterative-versus-single-pass choice needs a decision
rather than this comment.

---------------------------------------------------------------------------
RULING 2 -- a companion that is not itself ready
---------------------------------------------------------------------------
The question: a record is ready and names a companion; the companion cannot be
ready. Does the companion join ``ready`` anyway, does the **parent** become
pending, or does the companion land in whatever bucket it belongs to?

**Rejected outright: forcing the companion into ``ready``.** It would report a
number that has not met its own bar, which is the one thing the project exists
to prevent (``USER_EXPERIENCE.md`` §4 principle 2, "pending beats a fake
number"). A mandated companion is mandated so the parent is not read alone; it
is not mandated to be fabricated.

That leaves a real methodological choice, and **the corpus argues both ways
depending on the pair**:

* ``AGENT.md`` §5 states two never-alone rules in the imperative -- "any judge
  score is reported with output length" and "violation rate always reported
  with over-refusal rate". ``G6``'s ``G:195`` is "Refusing everything scores 0%
  on the first and fails on the second": the pair *is* the measurement. By that
  reading an unready companion must make the **parent pending**, because
  reporting the parent alone is forbidden.
* But ``I1_ci_regression_gate`` names ``E4_aa_baseline`` for a different
  reason: ``I:41`` takes the gate's *tolerance* from E4's A/A noise band. E4 is
  a **parameter supplier**, and I1's other half -- the must-pass golden set --
  needs no tolerance at all. Holding I1 back for want of E4 would suppress the
  must-pass gate, which is the thing ``I:33`` exists to guarantee and the
  failure ``I:58`` describes ("Gating only on the average, which is exactly
  where a single critical failure disappears").

**Both edges are spelled ``companion_checks`` and the schema cannot tell them
apart.** A mandatory never-alone pairing and a supporting parameter supplier
are the same field.

**The ruling: the companion joins the plan and is bucketed on its own merits;
the parent stays ready.** Reasons, in order of weight:

1. It is the only reading that is right for *both* kinds of edge. The strict
   reading is wrong for ``I1 -> E4`` -- demonstrably, against ``I:33`` -- and a
   rule that is wrong for a real edge is not a rule.
2. Nothing is hidden. The companion appears in ``pending`` or ``unavailable``
   with its own reason, beside the parent, so a reader sees both the number and
   that its companion is not available yet. The never-alone rule's *purpose* --
   that the pair is read together -- survives; the stronger claim that the
   parent must be suppressed does not.
3. It is what the 20 fixtures assert. Fixture 19 has ``I1`` and ``I9`` ready
   with ``E4`` pending, derived from the records before this module existed.

---------------------------------------------------------------------------
RULING 2b -- and expansion STOPS at a companion that is not ready
---------------------------------------------------------------------------
Ruling 2 leaves a second question, which is sharper and which **the fixtures
answered before this module existed**: does an unready companion contribute
*its own* companions?

No. Consider the live case, fixture 10. ``F7_one_call_per_criterion`` is ready
and names ``F2_cohens_kappa``. F2 is pending -- no human agreement has been
measured. F2 in turn names ``B6_bootstrap_ci``, from ``F:74``: "Bootstrap κ
(Section B6). A κ of 0.65 on 150 items can have a CI running from 0.52 to
0.77." B6 needs no tool and carries no threshold, so **a blind fixed point puts
B6 in ``ready``** -- offering to bootstrap a confidence interval around a κ that
does not exist. That is a plan entry about nothing, and it is exactly the
"impressive over honest" failure §4 principle 2 forbids.

The same shape appears three more times: in fixtures 7, 8 and 9,
``B1_paired_evaluation`` is ready and names ``E1_per_item_diff``, which is
pending for want of a second run; E1 names ``E4_aa_baseline``, and a blind
closure would add E4 as a second pending entry about a diff that cannot be
computed yet.

**So a companion edge is only followed from a record that is itself ready.** The
fixtures encode this: fixture 19's ``E1 -> E4`` edge *is* present, because there
E1 is ready at two runs; in fixtures 7-9 the same edge is absent, because there
E1 is pending. One rule, and the fixtures distinguish the two cases by E1's own
readiness.

**Which is why this function expands one level and the planner loops.**
``resolve_companions(ready, records)`` returns what the records it was given
demand -- it has neither the evidence nor the grants, so it cannot know what is
ready and must not guess. ``EL-123``'s planner buckets the additions and calls
again with the newly *ready* ones, until nothing new appears. An unready
companion simply never enters the next round's ``ready`` argument, so its own
edges are never followed, and the rule falls out of the composition rather than
being special-cased here.

That loop terminates: each round's ``ready`` set only grows, it is bounded by
the registry, and a round that adds nothing ends it. The registry's one mutual
pair -- ``H2_outcome_based_success`` names ``H4_cost_per_success`` (``H:73``)
and H4 names H2 (``H:139``), because the two numbers are read together --
settles in two rounds rather than recursing forever.

**What this costs, stated plainly:** for the judge and safety pairs, the
registry cannot *enforce* the never-alone rule -- it can only place both records
side by side and rely on the render. Making it enforceable needs a field that
distinguishes a mandatory pairing from a supporting one. Raised as a finding
rather than resolved, and it is the same gap, from the other side, that
``S16-REPORT.md`` finding F9 raises for two numbers produced by one record.

Note the asymmetry with step 6's own scope, which is not this module's to fix:
companions are resolved for records that are **ready**, so a *pending* parent
takes its mandated companion out of the plan with it. That is fixture 3 --
``A4`` pending on its κ bars, and no length check anywhere -- and it is
``S17-REPORT.md`` §4 (Q1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from evalloop.registry.query import sort_key
from evalloop.registry.schema import RecordType, TechniqueRecord

__all__ = [
    "CompanionResolution",
    "ConflictResolution",
    "apply_conflicts",
    "resolve_companions",
]


@dataclass(frozen=True)
class ConflictResolution:
    """What survived step 5, and what replaced what.

    ``suppressed`` maps a dropped record's id to the id that replaced it.
    A record vanishing from a plan with no explanation is the silent skip this
    project refuses everywhere else, so the reason is carried rather than
    discarded -- the render can then say *"B6 replaced by B7"* instead of
    simply not mentioning B6.

    ``unapplied`` holds edges that were **not** honoured: a grader claiming to
    replace one at a better rung. Reported for the same reason -- an edge the
    methodology states and the planner declines is a thing a human should see.
    """

    kept: tuple[TechniqueRecord, ...]
    suppressed: Mapping[str, str]
    unapplied: Mapping[str, str]


@dataclass(frozen=True)
class CompanionResolution:
    """What step 6 demands, and which records are new to the plan.

    ``demanded`` maps each given host id to the companion ids it names, which
    is what ``Plan.companions`` holds. ``added`` is the companions not already
    among the given records, in step-7 order.

    ``added`` records are **not** classified here: this function has neither
    the evidence nor the granted tools, so it cannot know whether a companion
    is ready, pending or unavailable, and guessing would be the one error the
    plan cannot afford. The planner buckets them and calls again with the newly
    ready ones -- rulings 2 and 2b.
    """

    demanded: Mapping[str, tuple[str, ...]]
    added: tuple[TechniqueRecord, ...]


def _is_runged_grader(record: TechniqueRecord) -> bool:
    return record.type is RecordType.grader and record.ladder_priority is not None


def apply_conflicts(ready: Sequence[TechniqueRecord]) -> ConflictResolution:
    """Drop every record that a record beside it replaces. See ruling 1.

    Pure, and independent of the order of ``ready``: suppression is computed
    from the whole input before anything is removed, and the survivors keep
    their incoming order (which step 7 already fixed).
    """
    by_id = {record.id: record for record in ready}
    suppressed: dict[str, str] = {}
    unapplied: dict[str, str] = {}

    for record in sorted(ready, key=sort_key):
        for target_id in record.conflicts_with:
            target = by_id.get(target_id)
            if target is None:
                continue  # not in this plan, so there is nothing to replace
            if _is_runged_grader(record) and _is_runged_grader(target):
                assert record.ladder_priority is not None  # narrowed by the guard
                assert target.ladder_priority is not None
                if record.ladder_priority >= target.ladder_priority:
                    unapplied.setdefault(
                        target_id,
                        f"{record.id} claims to replace it but sits at rung "
                        f"{record.ladder_priority}, not above rung "
                        f"{target.ladder_priority}",
                    )
                    continue
            suppressed.setdefault(target_id, f"replaced by {record.id}")

    kept = tuple(record for record in ready if record.id not in suppressed)
    return ConflictResolution(
        kept=kept,
        suppressed=MappingProxyType(suppressed),
        unapplied=MappingProxyType(unapplied),
    )


def resolve_companions(
    ready: Sequence[TechniqueRecord], records: Iterable[TechniqueRecord]
) -> CompanionResolution:
    """What the given records demand be reported alongside them. See ruling 2b.

    **One level, deliberately.** This returns the companions of the records it
    was handed, not a transitive closure: following an edge out of a record
    that is not itself ready would add plan entries about numbers that cannot
    be computed -- fixture 10's "bootstrap a κ that does not exist". The caller
    buckets the additions and calls again with the newly *ready* ones, and the
    rule falls out of that composition. See ruling 2b for why, and for why the
    loop terminates even on the registry's mutual ``H2``/``H4`` pair.

    A companion id that no record has is skipped rather than raised on:
    ``check_integrity`` rule 7 reports a dangling reference by name, and this
    is not the place to re-litigate a defect the registry already guards. It
    still appears in ``demanded``, so the edge stays visible.

    Pure, and independent of the order of either argument.
    """
    by_id = {record.id: record for record in records}
    present = {record.id for record in ready}

    demanded = {
        record.id: tuple(record.companion_checks)
        for record in sorted(ready, key=sort_key)
        if record.companion_checks
    }
    additions = {
        companion_id: by_id[companion_id]
        for record in ready
        for companion_id in record.companion_checks
        if companion_id not in present and companion_id in by_id
    }
    added = tuple(sorted(additions.values(), key=sort_key))
    return CompanionResolution(demanded=MappingProxyType(demanded), added=added)
