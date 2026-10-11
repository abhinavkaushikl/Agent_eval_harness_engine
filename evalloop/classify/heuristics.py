"""Heuristic classification of a Python file into artifact situations.

``AGENT.md`` §3.4: heuristics first, Python only at M1, an LLM only when the
heuristics are unclear (not here), and the output is multi-label with a
confidence per label. ``GATE0-REVIEW-PACKET.md`` §5 names this the weakest link
in the system: a wrong label yields a confident, well-ordered, entirely wrong
plan, which is worse than an empty one. So every rule below leans towards
abstaining, and an abstention is a stated outcome with a reason, never a
default label.

What is read
------------
The file's ``ast``, and nothing else: no regular expression ever runs over
source text, and nothing is imported or executed. A file that ``ast.parse``
rejects is **unclassifiable**, not misclassified -- half-written code is the
normal case while a developer is typing. The grammar is the running
interpreter's, so a file using syntax newer than the interpreter abstains.
Warnings raised while parsing (an invalid escape such as ``"\\d"``) are
suppressed, because under ``-W error`` they would otherwise turn a valid file
into a parse failure.

Units, signals and labels
-------------------------
A **unit** is a top-level function, or a method of a top-level class, that has
a body. A body of only a docstring, ``pass``, ``...`` or ``raise
NotImplementedError`` is a stub and is not a unit: there is nothing to grade
yet. Methods of schema classes (below) are part of the schema, not units.
Nested functions belong to the unit that contains them.

Each unit is checked for three signals, the ones the EL-204 ticket lists:

* **route** -> ``api_endpoint``: a decorator call such as ``@app.get("/x")`` or
  ``@router.route("/x")`` -- an attribute named for an HTTP method or
  ``route``/``api_route``/``websocket``, whose first argument is a string
  starting with ``/``. Flask, FastAPI and Starlette all take this form.
  Django's ``urlpatterns`` does not, and is not detected.
* **SQL** -> ``sql_generation``: a string literal in the unit (an f-string's
  literal parts count) that is shaped like a statement -- ``SELECT ... FROM``,
  ``INSERT INTO``, ``UPDATE ... SET``, ``DELETE FROM``, ``WITH ... AS ...
  SELECT``, or ``CREATE``/``ALTER``/``DROP`` followed by ``TABLE``/``VIEW``/
  ``INDEX`` -- **and** corroborated: either its leading keyword is written in
  upper case, or it is passed straight to ``execute``/``executemany``/
  ``executescript``/``read_sql``/``read_sql_query``/``text``. Shape alone would
  accept "delete from the list below". Docstrings and other bare string
  statements are ignored.
* **schema return** -> ``structured_extraction``: the return annotation names a
  schema class defined in the same file -- a subclass of ``BaseModel`` or
  ``TypedDict``, directly or through another schema class here. ``list[X]``,
  ``X | None`` and string annotations count. A **route's** return annotation is
  its response schema, not an extraction, so a route never carries this signal.
  A schema class imported from another module is invisible.

A unit with none of the three is a plain function -> ``code_generation``. A
unit may carry route and SQL together, which is how a file earns both
``api_endpoint`` and ``sql_generation`` (planner fixture 18's pair).

Confidence
----------
One formula, for every label::

    confidence(label) = units carrying the label's signal / gradeable units

It is the share of the file the label describes, reproducible to the bit from
the file alone. It is **not** a calibrated probability: calibrating one needs
labelled files and an agreement study (corpus section F), and none exist, so
no per-branch constant is invented to look like one. Labels are ordered by
confidence, highest first, then by ``Situation`` declaration order.

The six situations that reach no record
---------------------------------------
``classification``, ``data_pipeline``, ``model_training``,
``contamination_risk``, ``distribution_mismatch`` and ``phi_present`` trigger
no technique record, so a classification that lands on one gets an empty plan
with no explanation. **This classifier never emits them**, and says why:

* ``model_training`` and ``data_pipeline`` are detected (``WITHHELD``) only so
  the file can **abstain** with the dead end named, rather than fall through to
  ``code_generation``, which would be a reach. Training: an import of a
  training framework *and* a ``.fit()`` or ``.backward()`` call. Pipeline: an
  import of an orchestrator.
* ``classification`` would need to know what the code's output means;
  ``phi_present``, ``contamination_risk`` and ``distribution_mismatch`` are
  properties of data, which a source file does not show. None is detected.

``tests/test_classifier.py`` recomputes the dead set from the registry, so a
record that later reaches one of these members fails the suite here until
this module is revisited.
"""

from __future__ import annotations

import ast
import os
import warnings
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType

from evalloop._compat import StrEnum
from evalloop.vocab import Situation

__all__ = [
    "EMITTABLE",
    "UNDETECTED",
    "WITHHELD",
    "Abstention",
    "ClassifierResult",
    "Finding",
    "classify_file",
    "classify_source",
]


#: Every situation this classifier can emit. Each reaches at least one record.
EMITTABLE: tuple[Situation, ...] = (
    Situation.api_endpoint,
    Situation.code_generation,
    Situation.sql_generation,
    Situation.structured_extraction,
)

#: Dead-end situations that are detected only so the file can abstain, with why.
WITHHELD: Mapping[Situation, str] = MappingProxyType(
    {
        Situation.model_training: "a training-framework import and a .fit() or .backward() call",
        Situation.data_pipeline: "an orchestrator import",
    }
)

#: Dead-end situations a source file cannot show, so nothing looks for them.
UNDETECTED: Mapping[Situation, str] = MappingProxyType(
    {
        Situation.classification: "needs the meaning of the code's output, not its shape",
        Situation.contamination_risk: "a property of the evaluation data",
        Situation.distribution_mismatch: "a property of the evaluation data",
        Situation.phi_present: "a property of the data the code handles",
    }
)

_ROUTE_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "route", "api_route", "websocket"}
)
_SQL_EXECUTORS = frozenset({"execute", "executemany", "executescript", "read_sql", "read_sql_query", "text"})
_SCHEMA_BASES = frozenset({"BaseModel", "TypedDict"})
_TRAINING_PACKAGES = frozenset(
    {"catboost", "flax", "jax", "keras", "lightgbm", "sklearn", "tensorflow", "torch", "xgboost"}
)
_TRAINING_CALLS = frozenset({"backward", "fit"})
_PIPELINE_PACKAGES = frozenset({"airflow", "apache_beam", "dagster", "kedro", "luigi", "prefect"})
_SITUATION_RANK = {situation: rank for rank, situation in enumerate(Situation)}


class Abstention(StrEnum):
    """Why a file got no labels."""

    not_python = "not_python"
    unreadable = "unreadable"
    syntax_error = "syntax_error"
    dead_end = "dead_end"
    no_gradeable_unit = "no_gradeable_unit"


@dataclass(frozen=True, slots=True)
class Finding:
    """One label, its confidence, and the units that earned it."""

    situation: Situation
    confidence: float
    reasoning: str


@dataclass(frozen=True, slots=True)
class ClassifierResult:
    """Labels with reasons, or an abstention with one -- never both, never neither."""

    findings: tuple[Finding, ...]
    abstention: Abstention | None
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("a classifier result always carries a reason")
        if (self.abstention is None) == (not self.findings):
            raise ValueError("a result has labels or an abstention, exactly one of the two")

    @property
    def labels(self) -> tuple[tuple[Situation, float], ...]:
        """``AGENT.md`` §3.4's ``[(Situation, confidence), ...]``, in order."""
        return tuple((finding.situation, finding.confidence) for finding in self.findings)


def _abstain(kind: Abstention, reason: str) -> ClassifierResult:
    return ClassifierResult((), kind, reason)


# -- reading the tree -----------------------------------------------------------

_Function = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, slots=True)
class _Unit:
    name: str
    node: _Function


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _schema_classes(tree: ast.Module) -> frozenset[str]:
    """Top-level classes based on BaseModel or TypedDict, directly or through each other."""
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for cls in classes:
            if cls.name in found:
                continue
            bases = {_base_name(base) for base in cls.bases}
            if bases & _SCHEMA_BASES or bases & found:
                found.add(cls.name)
                changed = True
    return frozenset(found)


def _is_stub(node: _Function) -> bool:
    for statement in node.body:
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue  # a docstring or a bare ...
        if isinstance(statement, ast.Raise) and statement.exc is not None:
            raised = statement.exc.func if isinstance(statement.exc, ast.Call) else statement.exc
            if isinstance(raised, ast.Name) and raised.id == "NotImplementedError":
                continue
        return False
    return True


def _units(tree: ast.Module, schemas: frozenset[str]) -> list[_Unit]:
    found: list[_Unit] = []
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(_Unit(statement.name, statement))
        elif isinstance(statement, ast.ClassDef) and statement.name not in schemas:
            for member in statement.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append(_Unit(f"{statement.name}.{member.name}", member))
    return [unit for unit in found if not _is_stub(unit.node)]


def _route(node: _Function) -> str | None:
    for decorator in node.decorator_list:
        if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
            continue
        if decorator.func.attr not in _ROUTE_METHODS or not decorator.args:
            continue
        path = decorator.args[0]
        if isinstance(path, ast.Constant) and isinstance(path.value, str) and path.value.startswith("/"):
            return "@" + ast.unparse(decorator)
    return None


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _sql_shaped(text: str) -> bool:
    words = [word for word in (raw.strip("(),;").lower() for raw in text.split()) if word]
    if len(words) < 2:
        return False
    verb, rest = words[0], words[1:]
    if verb == "select":
        return "from" in rest
    if verb == "insert":
        return rest[0] == "into"
    if verb == "update":
        return "set" in rest
    if verb == "delete":
        return rest[0] == "from"
    if verb == "with":
        return "as" in rest and "select" in rest
    if verb in ("create", "alter", "drop"):
        return rest[0] in ("table", "view", "index")
    return False


def _strings(node: _Function) -> Iterator[tuple[ast.expr, str]]:
    """String literals in the unit, f-strings flattened, bare string statements skipped."""
    skipped: set[int] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Expr) and isinstance(child.value, (ast.Constant, ast.JoinedStr)):
            skipped.add(id(child.value))
        if isinstance(child, ast.JoinedStr):
            skipped.update(id(part) for part in child.values)
    for child in ast.walk(node):
        if id(child) in skipped:
            continue
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child, child.value
        elif isinstance(child, ast.JoinedStr):
            parts = [
                part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else " _ "
                for part in child.values
            ]
            yield child, "".join(parts)


def _sql(node: _Function) -> str | None:
    executed = {
        id(call.args[0])
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and call.args and _called_name(call) in _SQL_EXECUTORS
    }
    for literal, text in _strings(node):
        if not _sql_shaped(text):
            continue
        verb = text.split()[0].strip("(")
        if id(literal) in executed:
            return f"{verb.upper()} statement passed to an executor"
        if verb.isupper():
            return f"{verb} statement literal"
    return None


def _annotation_names(annotation: ast.expr) -> Iterator[str]:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                quoted = ast.parse(node.value, mode="eval")
            except SyntaxError:
                continue
            yield from _annotation_names(quoted.body)


def _schema_return(node: _Function, schemas: frozenset[str]) -> str | None:
    if node.returns is None:
        return None
    for name in _annotation_names(node.returns):
        if name in schemas:
            return f"returns schema {name}"
    return None


def _dead_ends(tree: ast.Module) -> list[tuple[Situation, str]]:
    packages: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            packages.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            packages.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    found: list[tuple[Situation, str]] = []
    training, training_calls = sorted(packages & _TRAINING_PACKAGES), sorted(calls & _TRAINING_CALLS)
    if training and training_calls:
        found.append(
            (
                Situation.model_training,
                f"imports {', '.join(training)}; calls {', '.join('.' + c + '()' for c in training_calls)}",
            )
        )
    pipeline = sorted(packages & _PIPELINE_PACKAGES)
    if pipeline:
        found.append((Situation.data_pipeline, f"imports {', '.join(pipeline)}"))
    return found


# -- classifying ------------------------------------------------------------------


def _units_phrase(count: int) -> str:
    return f"{count} gradeable unit" + ("" if count == 1 else "s")


def _label(
    situation: Situation, earned: Sequence[tuple[str, str]], total: int
) -> Finding:
    detail = "; ".join(f"{name} ({evidence})" for name, evidence in earned)
    return Finding(
        situation,
        float(Fraction(len(earned), total)),
        f"{len(earned)} of {_units_phrase(total)}: {detail}",
    )


def classify_source(source: str | bytes, *, name: str) -> ClassifierResult:
    """Classify Python source. ``name`` is used only in reasons. Never raises on bad input."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(source, filename=name)
    except SyntaxError as error:
        return _abstain(
            Abstention.syntax_error,
            f"{name}: does not parse (line {error.lineno}: {error.msg}); "
            "a half-written file is unclassifiable, not misclassified",
        )
    except ValueError as error:  # 3.10 rejects a NUL byte with ValueError, 3.12 with SyntaxError
        return _abstain(Abstention.syntax_error, f"{name}: does not parse ({error})")
    except (RecursionError, MemoryError):
        return _abstain(Abstention.syntax_error, f"{name}: too deeply nested to parse")

    dead = _dead_ends(tree)
    if dead:
        described = "; ".join(f"{situation.value} ({evidence})" for situation, evidence in dead)
        return _abstain(
            Abstention.dead_end,
            f"{name}: looks like {described}. No technique record triggers on "
            f"{' or '.join(situation.value for situation, _ in dead)}, so the label would give an "
            "empty plan with no explanation, and code_generation in its place would be a reach",
        )

    schemas = _schema_classes(tree)
    units = _units(tree, schemas)
    if not units:
        return _abstain(
            Abstention.no_gradeable_unit,
            f"{name}: no top-level function or method with a body (stubs do not count); nothing to grade yet",
        )

    earned: dict[Situation, list[tuple[str, str]]] = {situation: [] for situation in EMITTABLE}
    for unit in units:
        route = _route(unit.node)
        sql = _sql(unit.node)
        schema = None if route else _schema_return(unit.node, schemas)
        if route:
            earned[Situation.api_endpoint].append((unit.name, f"route {route}"))
        if sql:
            earned[Situation.sql_generation].append((unit.name, sql))
        if schema:
            earned[Situation.structured_extraction].append((unit.name, schema))
        if not (route or sql or schema):
            earned[Situation.code_generation].append((unit.name, "no route, SQL or schema return"))

    findings = sorted(
        (_label(situation, hits, len(units)) for situation, hits in earned.items() if hits),
        key=lambda finding: (-finding.confidence, _SITUATION_RANK[finding.situation]),
    )
    summary = ", ".join(f"{finding.situation.value} {finding.confidence!r}" for finding in findings)
    return ClassifierResult(tuple(findings), None, f"{name}: {_units_phrase(len(units))}; {summary}")


def classify_file(path: str | os.PathLike[str]) -> ClassifierResult:
    """Classify one file. Anything but ``.py`` abstains: M1 is Python only (``PLAN.md`` T9)."""
    file = Path(path)
    if file.suffix != ".py":
        return _abstain(
            Abstention.not_python,
            f"{file.name}: not a Python file (suffix {file.suffix or 'none'!r}); "
            "M1 classifies Python only (PLAN.md T9), other languages are T40",
        )
    try:
        source = file.read_bytes()
    except OSError as error:
        return _abstain(Abstention.unreadable, f"{file.name}: could not be read ({error.strerror or error})")
    return classify_source(source, name=file.name)
