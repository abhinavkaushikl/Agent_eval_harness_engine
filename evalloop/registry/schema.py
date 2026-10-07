"""``TechniqueRecord``: one row of the methodology, typed and validated.

The 22 fields are ``CLAUDE.md`` section 6's table, in its order, with
``domain_scenario`` after ``worked_example`` per
``decisions/EL-011-sixth-column-mapping.md``. Every field is required: there are
no defaults, so a record file missing a field fails at construction instead of
silently acquiring a value nobody wrote. That is the same reason EL-011 gives
for ``domain_scenario`` having no default -- silence is the failure this schema
exists to prevent.

Immutability
------------
The dataclass is ``frozen``, and the sequence fields are ``tuple``, so a loaded
registry cannot be edited by a planner that reads it. ``requires`` needs more
care: a frozen dataclass holding a ``dict`` is still mutable *through* that
dict, and if the caller keeps a reference it can change the record afterwards.
So ``__post_init__`` copies it and wraps the copy in ``MappingProxyType``,
which is read-only and does not alias the caller's dict.

The cost of that: ``MappingProxyType`` is unhashable, so ``TechniqueRecord`` is
unhashable too -- ``hash(record)`` raises ``TypeError``, as it would for any
frozen dataclass holding a ``dict`` or ``list``. Nothing in M0 needs it:
records are identified by ``id``, which ``check_integrity()`` keeps unique, and
the planner keys on ``id``. Raised in this ticket's report rather than solved
by inventing a hash.

``requires`` holds floats, which ``CLAUDE.md`` section 6 does not
--------------------------------------------------------------------
Section 6 types ``requires`` as ``Mapping[str, int | bool]``. The corpus has
float thresholds, verbatim: ``κ ≥ 0.6`` and ``κ ≥ 0.8``
(``A-choosing-how-to-grade.md:146``, ``F-trusting-your-grader.md:21``),
``α < 0.667`` (``F-trusting-your-grader.md:333``), ``token-F1 ≥ 0.8``
(``A-choosing-how-to-grade.md:302``), ``BH q = 0.10``
(``C-deciding-whether-a-result-is-real.md:174``) and a ``±2.5 pt`` tolerance
band (the master lookup, section I, "CI keeps flaking"). A schema that could
not hold ``0.6`` would force an author to write ``60`` instead, which is the
invented number ``CLAUDE.md`` section 3 forbids. The type here is therefore
``Mapping[str, int | float | bool]``, and the conflict with section 6 is in the
report. ``bool`` is listed separately from ``int`` although Python makes it a
subclass, because a boolean requirement (``requires_pre_instrumentation``) is
checked differently from a numeric threshold -- EL-121's readiness rule.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from types import MappingProxyType

from evalloop._compat import StrEnum
from evalloop.vocab import Situation, Tool

__all__ = ["FIELD_NAMES", "Cost", "Gate", "RecordType", "SchemaError", "TechniqueRecord"]

#: ``<SECTION><N>_<snake_name>``, e.g. ``A1_execution_based``. The section
#: letter is A-J because that is what a section is; whether it agrees with the
#: ``section`` field is EL-109's integrity check, not a shape question.
RECORD_ID = re.compile(r"^[A-J][1-9][0-9]*_[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

#: 1 execution, 2 end-state, 3 deterministic, 4 judge, 5 human. Five is the
#: maximum: ``decisions/EL-004-claude-md-corpus-gaps.md`` removed the distilled
#: rung, so there is no rung 6 to assign.
LADDER_MIN = 1
LADDER_MAX = 5

#: Fields that must be tuples, so a loaded record cannot be mutated in place.
_SEQUENCE_FIELDS = (
    "triggers_on_situation",
    "required_signals",
    "required_tools",
    "produces",
    "companion_checks",
    "unlocks",
    "conflicts_with",
)


class RecordType(StrEnum):
    """What kind of thing a record is. **Most records are not graders.**

    This is the assignment people get wrong, and it drifts silently: a
    mis-typed record still loads, still passes integrity, and then the planner
    ranks a confidence interval on the grading ladder.

    * ``grader`` -- renders a verdict on an artifact. Section A's rungs, and
      little else. Execution-based grading, end-state verification, normalised
      exact match, the binary-criteria judge, field-level scoring, expert
      review.
    * ``metric`` -- a number computed from verdicts or retrievals: recall@k,
      nDCG, MRR, faithfulness, ASR, cost per successful task, pass^k.
    * ``statistic`` -- an inference about whether a number is real. **Wilson,
      McNemar and bootstrap are statistics, not graders.** Power analysis,
      permutation, Bradley-Terry, multiple-comparison correction.
    * ``diagnostic`` -- explains a surprising number. **Section E is almost
      entirely diagnostics:** per-item diff, A/A baseline, length-controlled
      win rate, oracle run, contamination check, ceiling and floor.
    * ``procedure`` -- a repeatable process rather than a measurement:
      calibration rounds, the failures-as-tests flywheel, error analysis,
      shadow mode, building the eval set.
    * ``constraint`` -- forbids something. "Never accuracy on a rare class",
      "never let a model judge its own family", "no '% safe' headline".

    A record's type decides how the planner treats it, so when in doubt ask
    what the record *produces*: a verdict (grader), a number (metric), a
    p-value or interval (statistic), an explanation (diagnostic), a changed
    process (procedure), or a prohibition (constraint).
    """

    grader = "grader"
    metric = "metric"
    statistic = "statistic"
    diagnostic = "diagnostic"
    procedure = "procedure"
    constraint = "constraint"


class Gate(StrEnum):
    """Whether, and how, a record can block a change.

    ``absolute`` blocks on any failure (safety, schema, a must-pass item).
    ``statistical`` blocks only when the result clears a statistical bar.
    ``false`` never blocks and is reported only.

    Note that ``Gate.false`` is a non-empty string and therefore **truthy**:
    write ``record.gates is Gate.false``, never ``if not record.gates``.
    """

    absolute = "absolute"
    statistical = "statistical"
    false = "false"


class Cost(StrEnum):
    """Relative expense, as the corpus frames it -- never an absolute figure."""

    low = "low"
    medium = "medium"
    high = "high"


class SchemaError(ValueError):
    """A record that violates the schema, naming the record and the field.

    Carries ``record_id`` and ``field`` so EL-108's loader can aggregate
    problems across all 73 records without re-reading the message, the same
    contract ``FormatError`` offers for parse problems.
    """

    def __init__(self, record_id: str, field: str, detail: str) -> None:
        self.record_id = record_id
        self.field = field
        self.detail = detail
        super().__init__(f"{record_id or '<no id>'}: {field}: {detail}")


@dataclass(frozen=True)
class TechniqueRecord:
    """One technique from the corpus: when it applies, what it needs, what it costs."""

    id: str
    section: str
    name: str
    type: RecordType
    triggers_on_situation: tuple[Situation, ...]
    required_signals: tuple[str, ...]
    required_tools: tuple[Tool, ...]
    ladder_priority: int | None
    requires: Mapping[str, int | float | bool]
    produces: tuple[str, ...]
    gates: Gate
    companion_checks: tuple[str, ...]
    unlocks: tuple[str, ...]
    conflicts_with: tuple[str, ...]
    analysis_cost: Cost
    capture_cost: Cost | None
    anti_pattern: str
    worked_example: str
    domain_scenario: str | None
    rule_of_thumb: str | None
    source_ref: str
    extraction_notes: str | None

    def __post_init__(self) -> None:
        self._freeze_requires()
        self._check_id()
        self._check_sequences_are_tuples()
        self._check_triggers()
        self._check_ladder_priority()
        self._check_worked_example()
        self._check_source_ref()

    # -- normalisation ----------------------------------------------------

    def _freeze_requires(self) -> None:
        """Copy and wrap, so neither we nor the caller can mutate it later."""
        object.__setattr__(self, "requires", MappingProxyType(dict(self.requires)))

    # -- validation -------------------------------------------------------

    def _check_id(self) -> None:
        if not RECORD_ID.match(self.id):
            raise SchemaError(
                self.id,
                "id",
                "must be <SECTION><N>_<snake_name> with a section letter A-J, "
                "e.g. 'A1_execution_based'",
            )

    def _check_sequences_are_tuples(self) -> None:
        for name in _SEQUENCE_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise SchemaError(
                    self.id,
                    name,
                    f"must be a tuple so the record stays immutable, "
                    f"not {value.__class__.__name__}",
                )

    def _check_triggers(self) -> None:
        if not self.triggers_on_situation:
            raise SchemaError(
                self.id,
                "triggers_on_situation",
                "is empty, so no situation could ever select this record",
            )

    def _check_ladder_priority(self) -> None:
        if self.type is not RecordType.grader:
            if self.ladder_priority is not None:
                raise SchemaError(
                    self.id,
                    "ladder_priority",
                    f"is set to {self.ladder_priority} but type is {self.type}; "
                    "only a grader has a rung on the ladder",
                )
            return
        if self.ladder_priority is None:
            return
        if not LADDER_MIN <= self.ladder_priority <= LADDER_MAX:
            raise SchemaError(
                self.id,
                "ladder_priority",
                f"is {self.ladder_priority}, outside {LADDER_MIN}-{LADDER_MAX} "
                "(1 execution, 2 end-state, 3 deterministic, 4 judge, 5 human; "
                "EL-004 removed the distilled rung)",
            )

    def _check_worked_example(self) -> None:
        if not any(character.isdigit() for character in self.worked_example):
            raise SchemaError(
                self.id,
                "worked_example",
                "contains no digit; it must carry the concrete figures from the source",
            )

    def _check_source_ref(self) -> None:
        if not self.source_ref.strip():
            raise SchemaError(
                self.id,
                "source_ref",
                "is empty; a record with no citation is an invented number with extra steps",
            )


#: The field names, in schema order. Useful to the loader and to tests that
#: assert every section 6 field is present.
FIELD_NAMES: tuple[str, ...] = tuple(field.name for field in fields(TechniqueRecord))
