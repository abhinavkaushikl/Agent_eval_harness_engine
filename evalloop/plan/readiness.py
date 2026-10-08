"""``evaluate_readiness``: is there enough evidence for this record to be honest?

Step 4 of ``AGENT.md`` §3.5. A record whose ``requires`` is satisfied by the
accumulated evidence is ready; one whose is not is **pending, with a reason**.

The reason string is the product
--------------------------------
``USER_EXPERIENCE.md`` §4 principle 3 is "every 'no' has a reason -- PENDING,
UNAVAILABLE and PROHIBITED always state why, **in plain language**", and §3.1
renders the pending queue as::

    PENDING      B3_mcnemar        needs discordant_pairs: 25, have 8
                 C3_repeat_runs    needs runs: 5, have 1

So ``"insufficient data"`` is a failure of this module, not a fallback. The
format is ``AGENT.md`` §3.5's, verbatim:

    ``needs <key>: <threshold>, have <actual>``

and it is a **contract, not a style choice** -- the 20 planner fixtures assert
these strings character for character, so changing the wording breaks them by
design rather than by accident.

The four rules, and what each one is defending against
------------------------------------------------------
1. **Empty ``requires`` -> met.** A record with no threshold fires at n = 1,
   because the methodology states no bound for it. 31 of the 73 records are in
   this state, most of them graders and procedures: a single execution result
   is a fact, and you do not need a sample to run a calibration round.
2. **Missing evidence counts as zero or absent, never as "assume satisfied".**
   The capture layer writes what it has seen; a key it has never written means
   the thing has not been observed.
3. **Booleans are handled distinctly from numeric thresholds** -- see below.
4. **Every unmet requirement is named**, not just the first -- see below.

Where a judgement was needed, it resolves toward **not ready**. A wrongly
pending record costs one line in a queue the user can read; a wrongly ready one
costs a dishonest number, which is the single thing this project exists to
prevent. So a value whose type does not fit its requirement counts as absent
rather than being coerced into satisfying it.

Booleans
--------
``requires_pre_instrumentation: true`` cannot be compared with ``>=``, and
rendering it as ``"needs requires_pre_instrumentation: True, have 0"`` is wrong
twice over: ``True`` is Python's spelling rather than the corpus's, and ``0``
implies a count where there is none.

**The wording chosen keeps §3.5's shape and renders the values in the spelling
the record files use**::

    needs recall_at_k_measured: true, have false
    needs environment_resets_per_run: true, have false
    needs requires_pre_instrumentation: true, have false

Two reasons for keeping the uniform shape rather than inventing a sentence form
for booleans. First, §3.5 states one format and the fixtures assert it, so one
shape means one contract. Second, and more to the point: **the readability was
bought in the keys, not in the renderer.** The boolean keys were deliberately
authored as predicates -- ``recall_at_k_measured``,
``environment_resets_per_run``, ``pre_registration_filed``,
``paired_ci_available`` -- precisely so that this line reads as English without
the renderer having to know anything about the subject. A key like
``flag_7`` would need special-casing here; none of the 17 boolean records has
one.

Only ``True`` satisfies a boolean requirement. A number under a boolean key is
a type error in the caller, and counting it as unmet is the fail-safe
direction.

Several unmet requirements: **all of them**
-------------------------------------------
``A4_judge_binary_criteria`` carries two κ bars and ``G3_faithfulness`` carries
a boolean and a count. The fixtures answer the question::

    "needs judge_human_kappa_to_trust: 0.6, have 0; judge_human_kappa_to_gate: 0.8, have 0"
    "needs recall_at_k_measured: true, have false; claim_labels: 150, have 0"

One leading ``needs``, the clauses joined by ``"; "``, **in the order the
record declares them**. Not the first (which would hide the rest), not the
worst (which would need a comparison between a κ and a count that nothing
defines), and not alphabetical (which would scramble the corpus's own order of
mention). The record format parser preserves key order, so the declaration
order is the order the author wrote reading the deep dive -- for ``G3`` that is
the build-order gate first and the judge-validation bar second, which is the
order ``G:102`` and ``G:292`` come in.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from evalloop.registry.schema import TechniqueRecord

__all__ = ["Readiness", "evaluate_readiness", "render_value"]


@dataclass(frozen=True)
class Readiness:
    """Whether a record has enough evidence, and if not, exactly what is short.

    ``reason`` is ``None`` when ``met`` is true, so a caller cannot render a
    complaint about a satisfied record.
    """

    met: bool
    reason: str | None

    def __post_init__(self) -> None:
        if self.met and self.reason is not None:
            raise ValueError(f"met readiness carries a reason: {self.reason!r}")
        if not self.met and not self.reason:
            raise ValueError("unmet readiness must say what is missing")


#: The met result, shared because it carries no per-record information.
_MET = Readiness(met=True, reason=None)


def render_value(value: int | float | bool) -> str:
    """A threshold or an actual, in the spelling the record files use.

    ``True``/``False`` render as ``true``/``false``: the records are written in
    the YAML subset, and a reason that says ``True`` is quoting Python at the
    user. Numbers render as ``str`` gives them, so ``25`` stays ``25`` and
    ``0.6`` stays ``0.6`` rather than becoming ``0.60``.

    Exported because the planner's render step shows the same values in the
    same spelling, and two renderers would drift.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _actual(need: int | float | bool, observed: object) -> int | float | bool:
    """What the evidence says, normalised to the requirement's own kind.

    Absent evidence is ``false`` for a boolean requirement and ``0`` for a
    numeric one, which is rule 2. A value of the wrong kind is treated as
    absent rather than coerced: a boolean is not a count, and a count is not
    proof that a fact holds.
    """
    if isinstance(need, bool):
        return observed is True
    if isinstance(observed, bool) or not isinstance(observed, (int, float)):
        return 0
    return observed


def _satisfied(need: int | float | bool, actual: int | float | bool) -> bool:
    """A boolean requirement is a fact that holds; a numeric one is a floor."""
    if isinstance(need, bool):
        return not need or actual is True
    return bool(actual >= need)


def evaluate_readiness(
    record: TechniqueRecord, evidence: Mapping[str, object]
) -> Readiness:
    """Whether ``record``'s thresholds are met by ``evidence``.

    Pure: reads both arguments, mutates neither, and returns the same result
    for the same inputs. ``evidence`` is typed ``Mapping[str, object]`` rather
    than narrowly, because it arrives from the capture layer and this function
    is the thing that decides what an off-type value means.
    """
    unmet: list[str] = []
    for key, need in record.requires.items():
        actual = _actual(need, evidence.get(key))
        if _satisfied(need, actual):
            continue
        unmet.append(f"{key}: {render_value(need)}, have {render_value(actual)}")
    if not unmet:
        return _MET
    return Readiness(met=False, reason="needs " + "; ".join(unmet))
