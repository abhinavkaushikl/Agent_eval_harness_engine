"""Read a directory of record files into ``TechniqueRecord``s, reporting everything.

``CLAUDE.md`` section 7.7: errors aggregate, because 73 records are authored by
hand. A loader that stops at the first bad file turns one authoring session into
73 round trips. One run therefore produces the whole list, and
``RegistryError.problems`` is that list -- one ``Problem`` per defect, each
naming the file, the record id and the specific thing that is wrong.

File shape: one file per section, records keyed by id
----------------------------------------------------
Open question 7 (``E1-M0-TICKETS-AND-PROMPTS.md``) asked whether a record file
holds one record or many. **It holds many: one file per section, ten files, and
this holds for all 73 records.** A record file is a block map whose top-level
keys are record ids:

.. code-block:: yaml

    A1_execution_based:
      section: A
      name: Execution-based grading
      ...
    A2_end_state_verification:
      ...

The id is the key and is **not** repeated as a field inside the body, so the
two can never disagree; a body carrying ``id`` is rejected rather than
reconciled.

Why many per file:

* ``CLAUDE.md`` section 5 already names the layout -- ``records/A_grading.*``
  through ``records/J_model_selection.*``, ten files for ten sections. One
  record per file would contradict a published layout for a convenience, which
  is a decision ticket, not a loader's choice.
* A section is extracted from one deep dive in one sitting, and the fields that
  have to agree *across* records agree *within* a section: section A's
  ``ladder_priority`` is an ordering of A1-A6, section C's ``conflicts_with``
  points sideways, and ``source_ref`` repeats one filename. All of that is
  visible in one buffer. Across 73 files it is invisible, and ``source_ref``
  drift is exactly the silent failure ``CLAUDE.md`` section 4 warns about.
* Duplicate ids inside a section become a *parse* error for free: the format
  parser rejects duplicate keys. That is the likeliest authoring typo -- copy a
  record, forget to rename it -- and it is caught before the schema sees it.
  With one record per file the filesystem catches only exact name collisions.
* Ten files make a reviewable diff. Seventy-three do not.

What it costs, accepted rather than mitigated: a parse error takes out a whole
section's records in that run, and two people authoring the same section
conflict in one file. The first is why ``_load_file`` reports the parse error
and moves to the next file instead of raising -- one broken section never hides
the other nine. The second is a branch-hygiene problem, not a format problem.

Determinism (``CLAUDE.md`` section 7.8)
---------------------------------------
The returned tuple is sorted by ``id``, so it never depends on directory order,
which no filesystem guarantees. Problems are ordered to be *read*, not sorted:
file-name order, then document order within the file, then schema field order
within a record, so the list can be worked through top to bottom. Both orders
are stable across runs and filesystems.

How much is aggregated, honestly
--------------------------------
Everything this module checks is aggregated: every file is read, every record
in it is built, and within a record every one of the 21 body fields is checked
for presence, type and vocabulary before anything is reported. What is *not*
aggregated is the semantic layer: ``TechniqueRecord.__post_init__`` raises on
the first rule it fails, so a record with two semantic violations (say an empty
``triggers_on_situation`` *and* a digitless ``worked_example``) reports one, and
the second appears on the next run. Aggregating those would mean either
duplicating the six rules here -- where they would drift from the schema -- or
reopening EL-107. Raised in this ticket's report instead.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from evalloop._compat import StrEnum
from evalloop.registry import format as record_format
from evalloop.registry.format import FormatError, Node
from evalloop.registry.schema import (
    FIELD_NAMES,
    RECORD_ID,
    Cost,
    Gate,
    RecordType,
    SchemaError,
    TechniqueRecord,
)
from evalloop.vocab import Situation, Tool, parse_situation, parse_tool

__all__ = [
    "BODY_FIELDS",
    "RECORDS_DIR",
    "RECORD_SUFFIX",
    "Problem",
    "RegistryError",
    "load_records",
]

#: The extension a record file must have. The format is the YAML subset of
#: ``format.py`` (EL-106), and the planner fixtures already use ``.yaml``.
RECORD_SUFFIX = ".yaml"

#: The shipped registry: the ten section files the 73 records are authored
#: into (EL-110 onward), resolved relative to this package so it is never an
#: absolute user path (``CLAUDE.md`` section 3). Empty until EL-110.
RECORDS_DIR = Path(__file__).resolve().parent / "records"

#: The 21 fields a record *body* must carry: schema order, minus ``id``, which
#: is the top-level key. Derived from the schema so the two cannot drift.
BODY_FIELDS: tuple[str, ...] = tuple(name for name in FIELD_NAMES if name != "id")

_RECORD_TYPES: Mapping[str, RecordType] = MappingProxyType(
    {member.value: member for member in RecordType}
)
_GATES: Mapping[str, Gate] = MappingProxyType({member.value: member for member in Gate})
_COSTS: Mapping[str, Cost] = MappingProxyType({member.value: member for member in Cost})

_EnumT = TypeVar("_EnumT", bound=StrEnum)
_VocabT = TypeVar("_VocabT", Situation, Tool)


@dataclass(frozen=True)
class Problem:
    """One defect, located precisely enough to fix without a traceback.

    ``file`` is the record file's name relative to the loaded directory, or the
    directory itself for a problem with the directory as a whole. ``record_id``
    is the top-level key the defect sits under, and is ``None`` for a
    file-level problem such as a parse error. ``line`` is set only when the
    source reports one, which today means ``FormatError``.
    """

    file: str
    record_id: str | None
    detail: str
    line: int | None = None

    def __str__(self) -> str:
        where = self.file if self.line is None else f"{self.file}:{self.line}"
        if self.record_id is None:
            return f"{where}: {self.detail}"
        return f"{where}: {self.record_id}: {self.detail}"


class RegistryError(ValueError):
    """Every problem found in one load, in one message.

    ``problems`` is the structured list, so a caller (and the tests) can assert
    on fields rather than on prose. The rendered message is the same list, one
    problem per line, for the human reading a failed test run.
    """

    def __init__(self, directory: Path, problems: Sequence[Problem]) -> None:
        self.directory = directory
        self.problems: tuple[Problem, ...] = tuple(problems)
        count = len(self.problems)
        listing = "\n".join(f"  {problem}" for problem in self.problems)
        super().__init__(
            f"{count} problem{'' if count == 1 else 's'} loading records from "
            f"{str(directory)!r}:\n{listing}"
        )


def load_records(directory: str | os.PathLike[str]) -> tuple[TechniqueRecord, ...]:
    """Load every ``*.yaml`` record file under ``directory``, sorted by id.

    Raises ``RegistryError`` carrying *every* problem found across every file:
    parse errors, missing or unknown fields, wrong types, unknown vocabulary
    and schema violations. Returns only when the whole directory is clean.
    """
    root = Path(directory)
    if not root.is_dir():
        raise RegistryError(
            root,
            [
                Problem(
                    str(root),
                    None,
                    "is not a directory; load_records() takes the directory holding "
                    f"the {RECORD_SUFFIX} record files",
                )
            ],
        )

    paths = sorted(
        (path for path in root.glob(f"*{RECORD_SUFFIX}") if path.is_file()),
        key=lambda path: path.name,
    )
    if not paths:
        raise RegistryError(
            root,
            [
                Problem(
                    str(root),
                    None,
                    f"holds no {RECORD_SUFFIX} record file. Loading zero records "
                    "silently is the failure this error exists to prevent",
                )
            ],
        )

    problems: list[Problem] = []
    records: list[TechniqueRecord] = []
    for path in paths:
        records.extend(_load_file(path, problems))
    if problems:
        raise RegistryError(root, problems)
    # Stable sort over a filename-ordered list: duplicate ids (EL-109's check,
    # not this module's) still come out in the same order on every run.
    return tuple(sorted(records, key=lambda record: record.id))


def _load_file(path: Path, problems: list[Problem]) -> list[TechniqueRecord]:
    """Every record in one file. Appends problems; never raises."""
    name = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        problems.append(Problem(name, None, f"is not valid UTF-8: {error}"))
        return []
    except OSError as error:
        problems.append(Problem(name, None, f"cannot be read: {error.strerror or error}"))
        return []

    try:
        document = record_format.load(text)
    except FormatError as error:
        # The file is unparseable, so it yields no records -- but the remaining
        # files are still read, which is the point of aggregating.
        problems.append(Problem(name, None, f"{error.construct}: {error.detail}", error.line))
        return []

    loaded: list[TechniqueRecord] = []
    for key, value in document.items():
        record = _build_record(name, key, value, problems)
        if record is not None:
            loaded.append(record)
    return loaded


@dataclass(frozen=True)
class _Field:
    """Where a field problem happened, and how to report it."""

    file: str
    record_id: str
    name: str
    problems: list[Problem]

    def fail(self, detail: str) -> None:
        self.problems.append(Problem(self.file, self.record_id, f"{self.name}: {detail}"))


def _build_record(
    file: str, key: str, raw: Node, problems: list[Problem]
) -> TechniqueRecord | None:
    """One record, or ``None`` with its problems appended.

    Every body field is checked before anything is reported, so one pass names
    all of a record's shape and vocabulary problems rather than the first.
    """
    if RECORD_ID.match(key) is None:
        problems.append(
            Problem(
                file,
                key,
                "is not a record id. Every top-level key in a record file is a "
                "<SECTION><N>_<snake_name> id, e.g. 'A1_execution_based'",
            )
        )
        return None
    if not isinstance(raw, dict):
        problems.append(
            Problem(file, key, f"must be an indented block of fields, not {_describe(raw)}")
        )
        return None

    before = len(problems)
    if "id" in raw:
        problems.append(
            Problem(
                file,
                key,
                "must not carry an 'id' field: the record id is the top-level key, "
                "and writing it twice invites the two to disagree",
            )
        )
    for unknown in sorted(set(raw) - set(FIELD_NAMES)):
        problems.append(
            Problem(
                file,
                key,
                f"unknown field {unknown!r}; a record body carries exactly the "
                f"{len(BODY_FIELDS)} fields of CLAUDE.md section 6, minus 'id'",
            )
        )
    missing = [name for name in BODY_FIELDS if name not in raw]
    for name in missing:
        problems.append(Problem(file, key, f"{name}: missing; every field is required"))

    values: dict[str, Any] = {"id": key}
    for name in BODY_FIELDS:
        if name in missing:
            continue
        values[name] = _convert(_Field(file, key, name, problems), raw[name])

    if len(problems) > before:
        return None
    try:
        return TechniqueRecord(**values)
    except SchemaError as error:
        problems.append(Problem(file, key, f"{error.field}: {error.detail}"))
        return None


def _convert(field: _Field, value: Node) -> Any:
    """One body field, from parsed scalar to the type the schema wants.

    On failure a problem is appended and a harmless placeholder returned:
    ``_build_record`` has already decided not to construct anything once the
    problem count has grown, so the placeholder is never seen by a record.
    """
    if field.name in ("section", "name", "anti_pattern", "worked_example", "source_ref"):
        return _as_text(field, value)
    if field.name in ("domain_scenario", "rule_of_thumb", "extraction_notes"):
        return None if value is None else _as_text(field, value)
    if field.name in ("required_signals", "produces", "companion_checks", "unlocks", "conflicts_with"):
        return _as_text_tuple(field, value)
    if field.name == "type":
        return _as_member(field, value, _RECORD_TYPES, "record type")
    if field.name == "triggers_on_situation":
        return _as_vocab_tuple(field, value, parse_situation)
    if field.name == "required_tools":
        return _as_vocab_tuple(field, value, parse_tool)
    if field.name == "ladder_priority":
        return _as_optional_int(field, value)
    if field.name == "requires":
        return _as_requires(field, value)
    if field.name == "gates":
        return _as_gate(field, value)
    if field.name == "analysis_cost":
        return _as_member(field, value, _COSTS, "cost")
    if field.name == "capture_cost":
        return None if value is None else _as_member(field, value, _COSTS, "cost")
    # Unreachable while BODY_FIELDS is derived from the schema; a new field with
    # no conversion rule must say so rather than arrive as a raw scalar.
    field.fail("has no conversion rule in loader._convert(); EL-108 needs updating")
    return None


def _as_text(field: _Field, value: Node) -> str:
    if isinstance(value, str):
        return value
    field.fail(f"must be text, not {_describe(value)}")
    return ""


def _as_text_tuple(field: _Field, value: Node) -> tuple[str, ...]:
    if not isinstance(value, list):
        field.fail(f"must be a flow list, e.g. [a, b] or [], not {_describe(value)}")
        return ()
    out: list[str] = []
    for position, item in enumerate(value):
        if isinstance(item, str):
            out.append(item)
        else:
            field.fail(f"item {position} must be text, not {_describe(item)}")
    return tuple(out)


def _as_vocab_tuple(
    field: _Field, value: Node, parse: Callable[[str], _VocabT]
) -> tuple[_VocabT, ...]:
    """``parse`` is ``parse_situation`` or ``parse_tool``.

    Their ``ValueError`` already names the bad value and every valid option --
    the message ``CLAUDE.md`` section 6 calls the most important correctness
    decision in M0 -- so it is surfaced verbatim with the file, record id and
    field attached, never re-worded.
    """
    if not isinstance(value, list):
        field.fail(f"must be a flow list, e.g. [a, b] or [], not {_describe(value)}")
        return ()
    out: list[_VocabT] = []
    for position, item in enumerate(value):
        if not isinstance(item, str):
            field.fail(f"item {position} must be text, not {_describe(item)}")
            continue
        try:
            out.append(parse(item))
        except ValueError as error:
            field.fail(str(error))
    return tuple(out)


def _as_member(
    field: _Field, value: Node, members: Mapping[str, _EnumT], kind: str
) -> _EnumT | None:
    if not isinstance(value, str):
        field.fail(f"must be text, not {_describe(value)}")
        return None
    member = members.get(value)
    if member is None:
        options = ", ".join(sorted(members))
        field.fail(f"unknown {kind} {value!r}. The valid {kind} values are: {options}")
        return None
    return member


def _as_gate(field: _Field, value: Node) -> Gate | None:
    """``gates`` is the one field YAML's own type inference gets in the way of.

    ``Gate.false`` is spelled ``false``, and a YAML parser reads a bare
    ``false`` as the boolean -- so ``gates: false``, which is the natural thing
    to write, arrives here as ``False`` rather than ``"false"``. Mapping it
    back is less surprising than making authors remember to quote one field.
    ``true`` is not a gate and says so.
    """
    if value is False:
        return Gate.false
    if value is True:
        field.fail(
            "'true' is not a gate; write absolute, statistical or false "
            "(false meaning 'never blocks, reported only')"
        )
        return None
    return _as_member(field, value, _GATES, "gate")


def _as_optional_int(field: _Field, value: Node) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        field.fail(f"must be a whole number or null, not {_describe(value)}")
        return None
    return value


def _as_requires(field: _Field, value: Node) -> Mapping[str, int | float | bool]:
    if not isinstance(value, dict):
        field.fail(
            f"must be a flow map of thresholds, e.g. {{samples: 30}} or {{}}, "
            f"not {_describe(value)}"
        )
        return {}
    out: dict[str, int | float | bool] = {}
    for name, threshold in value.items():
        # bool is an int subclass, and the schema wants it listed: a boolean
        # requirement is a different readiness branch from a numeric threshold.
        if isinstance(threshold, (bool, int, float)):
            out[name] = threshold
        else:
            field.fail(
                f"threshold {name!r} must be a number or a boolean, not "
                f"{_describe(threshold)}. A threshold with no number in the source "
                "is null in the source field, never a guess"
            )
    return out


def _describe(value: object) -> str:
    """What a wrong value *is*, in the words a record author would use."""
    if value is None:
        return "null"
    if value is True or value is False:
        return f"the boolean {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"the number {value}"
    if isinstance(value, str):
        return f"text ({value!r})"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an indented block or flow map"
    return type(value).__name__
