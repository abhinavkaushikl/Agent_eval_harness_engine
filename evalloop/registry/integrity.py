"""Cross-record checks: the defects no single record can see about itself.

``TechniqueRecord.__post_init__`` validates a record in isolation -- its id
shape, its ladder rung, a digit in its worked example. It cannot see the other
72. Seven defects live only in the graph, and every one of them loads cleanly,
passes the schema and then quietly changes a plan:

``AGENT.md`` section 3.5 is why that matters. The planner's resolution order
reads ``conflicts_with`` at step 5 to suppress a lower grader, and
``companion_checks`` at step 6 to force a companion into the plan. A reference
that does not resolve is not a cosmetic typo: step 5 suppresses nothing and the
weaker grader survives, or step 6 drops a companion the methodology requires --
"any judge score is reported with output length" (``AGENT.md`` section 5) stops
being true, with no error anywhere. ``check_integrity`` is the only thing
standing between a one-character typo and a silently wrong plan, which is why
every stage from EL-110 to EL-117 runs it as its done-when.

The seven rules
---------------
In the order they are reported for any one record -- identity first, then its
placement, then its edges:

1. **duplicate id** -- two records share an id. Ids are the registry's primary
   key: ``companion_checks`` and the planner's output both key on them.
2. **section outside A-J** -- there are ten sections and no eleventh.
3. **id prefix disagreeing with ``section``** -- ``A1_...`` declaring section
   ``B``. Skipped when rule 2 already fired, so one defect is reported once.
4. **grader without a ``ladder_priority``, once any grader has one** -- an
   unrunged grader cannot be ordered against the others at step 7. The rule is
   *all-or-nothing*: it stays silent while no grader in the registry carries a
   rung, and fires for every unrunged grader as soon as one does. A
   half-assigned ladder is the defect; an unassigned one is a stage that has
   not happened yet.
5. **non-grader carrying a ``ladder_priority``**.
6. **self-reference** -- a record naming its own id in ``companion_checks``,
   ``unlocks`` or ``conflicts_with``.
7. **unknown reference** -- any of those three naming an id no record has.

Why rule 4 is all-or-nothing (EL-110)
-------------------------------------
It was first written as "every grader has a rung", and the first 20 real
records contradicted it twice. EL-110 authors sections A-C with
``ladder_priority: null`` throughout, because the ladder is EL-113's stage, and
it also requires ``check_integrity()`` to be empty -- which the strict form
made impossible. Worse, two records are *permanently* unrunged graders:
``B2_pairwise_preference`` renders a verdict but sits nowhere on section A's
ladder, and ``A7_tiered_online_scoring`` wraps the ladder, with its rung an
open question for S6 per ``CLAUDE.md`` section 6. And section 6 only ever
states the one-way rule -- ``ladder_priority`` is "None unless type is grader"
-- which the schema already enforces; the converse was this module's own
over-reach. All-or-nothing keeps the gate that matters (EL-113 assigning five
rungs out of six) without asserting something the corpus denies.

Rule 5 is already unreachable
-----------------------------
``schema._check_ladder_priority`` raises on a non-grader with a rung, so a
record violating rule 5 cannot be constructed through the normal path. The rule
is kept as defence in depth -- ``check_integrity`` is handed records, not
files, and is the stated gate for eight authoring stages -- and the overlap is
reported rather than resolved by deleting a rule the ticket asks for. Its test
has to reach past the frozen dataclass to build a violating record, which is
the evidence that the schema already covers it.

What is deliberately **not** checked
------------------------------------
Named here because they are real and unguarded, not added: a ``conflicts_with``
edge that is not reciprocated (step 5 is directional, so which record the
planner reads decides the outcome); an id appearing in both
``companion_checks`` and ``conflicts_with`` for the same record, where step 5
removes what step 6 demands; cycles in ``unlocks``; two graders in one section
sharing a ``ladder_priority``, which makes step 7's ordering a tie broken by id
rather than by the methodology; and a companion that can never be ready, so a
mandated companion silently never appears. Each needs a decision about intent,
not a loop, and none is in this ticket's seven.

Determinism (``CLAUDE.md`` section 7.8)
---------------------------------------
Problems are sorted by record id, then by rule, so two runs over the same
records give the same list and a diff between them is meaningful. Within one
rule the order is the order the record itself declares, and the close-match
suggestion for rule 7 is computed against a sorted id list so ties never depend
on input order.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import get_close_matches
from enum import IntEnum
from types import MappingProxyType

from evalloop.registry.schema import RecordType, TechniqueRecord

__all__ = ["CROSS_REFERENCE_FIELDS", "SECTIONS", "check_integrity"]

#: The ten section letters, as a tuple. Deliberately not the string
#: ``"ABCDEFGHIJ"``: ``"" in "ABCDEFGHIJ"`` and ``"AB" in "ABCDEFGHIJ"`` are
#: both true, so a string would pass an empty and a two-letter section.
SECTIONS: tuple[str, ...] = tuple("ABCDEFGHIJ")

_SECTION_SET = frozenset(SECTIONS)

#: The three fields holding record ids, in schema order. Every one is read by
#: the planner (``AGENT.md`` section 3.5, steps 5 and 6).
CROSS_REFERENCE_FIELDS: tuple[str, ...] = ("companion_checks", "unlocks", "conflicts_with")

#: How a self-reference reads for each field, so the message is an instruction
#: rather than a restatement of the field name.
_SELF_REFERENCE: Mapping[str, str] = MappingProxyType(
    {
        "companion_checks": "cannot be its own companion",
        "unlocks": "cannot unlock itself",
        "conflicts_with": "cannot conflict with itself",
    }
)

#: What an unresolved reference costs, per field, from ``AGENT.md`` section 3.5.
_DANGLING: Mapping[str, str] = MappingProxyType(
    {
        "companion_checks": "the companion is silently never reported",
        "unlocks": "nothing is unlocked",
        "conflicts_with": "the conflict never fires and both records stay in the plan",
    }
)

#: ``get_close_matches`` tuning for rule 7. A reference typo is a character or
#: two (``C1_wilson_c1`` for ``C1_wilson_ci``), so the bar is high enough that a
#: merely same-section id is not offered as the fix.
_SUGGESTION_CUTOFF = 0.7
_SUGGESTION_COUNT = 3


class _Rule(IntEnum):
    """Report order within one record id. The values are the sort key."""

    duplicate_id = 1
    section_range = 2
    section_prefix = 3
    grader_without_priority = 4
    non_grader_with_priority = 5
    self_reference = 6
    unknown_reference = 7


@dataclass(frozen=True)
class _Finding:
    record_id: str
    rule: _Rule
    message: str


def check_integrity(records: Iterable[TechniqueRecord]) -> list[str]:
    """Every cross-record problem, sorted by record id then rule.

    An empty list means the registry is internally consistent. Each message
    names the record id, the field and the offending value, and says what to do
    about it.
    """
    all_records = tuple(records)
    known_ids = sorted({record.id for record in all_records})
    known_id_set = frozenset(known_ids)

    ladder_started = any(
        record.ladder_priority is not None
        for record in all_records
        if record.type is RecordType.grader
    )

    findings: list[_Finding] = []
    _check_duplicate_ids(all_records, findings)
    for record in all_records:
        _check_section(record, findings)
        _check_ladder_priority(record, ladder_started, findings)
        _check_references(record, known_id_set, known_ids, findings)

    findings.sort(key=lambda finding: (finding.record_id, finding.rule))
    return [f"{finding.record_id}: {finding.message}" for finding in findings]


def _check_duplicate_ids(
    records: tuple[TechniqueRecord, ...], findings: list[_Finding]
) -> None:
    """Rule 1. Reported once per duplicated id, not once per copy."""
    by_id: dict[str, list[TechniqueRecord]] = {}
    for record in records:
        by_id.setdefault(record.id, []).append(record)
    for record_id, group in by_id.items():
        if len(group) == 1:
            continue
        names = ", ".join(repr(record.name) for record in group)
        findings.append(
            _Finding(
                record_id,
                _Rule.duplicate_id,
                f"duplicate id: {len(group)} records share it ({names}). The id is the "
                "registry's primary key and every cross-reference resolves through it; "
                "rename the extras or merge them into one record",
            )
        )


def _check_section(record: TechniqueRecord, findings: list[_Finding]) -> None:
    """Rules 2 and 3. Rule 3 is skipped when rule 2 fires: one defect, one line."""
    if record.section not in _SECTION_SET:
        findings.append(
            _Finding(
                record.id,
                _Rule.section_range,
                f"section: {record.section!r} is not a section letter. The ten sections "
                f"are {', '.join(SECTIONS)}; set it to the letter of the deep dive this "
                "record was extracted from",
            )
        )
        return
    prefix = record.id[0]
    if prefix != record.section:
        findings.append(
            _Finding(
                record.id,
                _Rule.section_prefix,
                f"section: {record.section!r} disagrees with the id's section letter "
                f"{prefix!r}. One of the two is a copy-paste from another section -- fix "
                "whichever does not match the source_ref",
            )
        )


def _check_ladder_priority(
    record: TechniqueRecord, ladder_started: bool, findings: list[_Finding]
) -> None:
    """Rules 4 and 5. Rule 4 is all-or-nothing -- see the module docstring."""
    is_grader = record.type is RecordType.grader
    if is_grader and record.ladder_priority is None and ladder_started:
        findings.append(
            _Finding(
                record.id,
                _Rule.grader_without_priority,
                "ladder_priority: is null but other graders in the registry carry a "
                "rung, so this grader cannot be ordered against them. Set it to "
                "1 execution, 2 end-state, 3 deterministic, 4 judge or 5 human -- or, "
                "if it does not belong on section A's ladder at all, retype it",
            )
        )
    elif not is_grader and record.ladder_priority is not None:
        findings.append(
            _Finding(
                record.id,
                _Rule.non_grader_with_priority,
                f"ladder_priority: is {record.ladder_priority} but type is "
                f"{record.type.value}; only a grader has a rung on the ladder. Clear it "
                "to null, or change type to grader",
            )
        )


def _check_references(
    record: TechniqueRecord,
    known_id_set: frozenset[str],
    known_ids: list[str],
    findings: list[_Finding],
) -> None:
    """Rules 6 and 7, over all three cross-reference fields in schema order."""
    for field in CROSS_REFERENCE_FIELDS:
        values: tuple[str, ...] = getattr(record, field)
        for value in values:
            if value == record.id:
                findings.append(
                    _Finding(
                        record.id,
                        _Rule.self_reference,
                        f"{field}: lists its own id. A record "
                        f"{_SELF_REFERENCE[field]} -- remove {value!r} from the list",
                    )
                )
            elif value not in known_id_set:
                findings.append(
                    _Finding(
                        record.id,
                        _Rule.unknown_reference,
                        f"{field}: {value!r} is not a record id, so {_DANGLING[field]}. "
                        f"{_suggest(value, known_ids)}",
                    )
                )


def _suggest(value: str, known_ids: list[str]) -> str:
    """The closest known ids, or an instruction when nothing is close.

    ``known_ids`` is sorted by the caller, so ``get_close_matches`` breaks
    equal-ratio ties the same way on every run.
    """
    matches = get_close_matches(
        value, known_ids, n=_SUGGESTION_COUNT, cutoff=_SUGGESTION_CUTOFF
    )
    if not matches:
        return (
            "No loaded id is close to it; check that the record it names was "
            "extracted at all, and that its section file is in the directory"
        )
    return f"Closest loaded id{'' if len(matches) == 1 else 's'}: {', '.join(matches)}"
