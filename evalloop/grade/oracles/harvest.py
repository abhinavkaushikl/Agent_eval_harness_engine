"""Harvest the oracles a repository already has: tests, schemas and type hints.

``AGENT.md`` §3.6: "Harvest existing (HIGH confidence): existing tests, schemas,
type hints in the repo." Every oracle returned here was written by a person, so
every one is tagged ``OracleConfidence.high`` -- :class:`Oracle` refuses any
other value -- and nothing in this module ever produces LOW. Authoring LOW
oracles is EL-210.

Nothing in the repository runs
------------------------------
Harvesting reads untrusted source, so it **never imports or executes repository
code**. Files are read as bytes, decoded by their PEP 263 cookie and handed to
``ast.parse``; that is the only thing done with them. A ``conftest.py`` or a
package ``__init__.py`` with side effects is parsed like any other file (tested
with a conftest that writes a file and raises if imported). The walk skips
symlinks, dot directories, ``__pycache__``, ``node_modules``,
``site-packages``, ``dist-packages`` and any directory holding a
``pyvenv.cfg``: this repository's own ``.venv`` carries some forty of mypy's
``test_*.py`` files, and they are not its tests.

The three kinds
---------------
**Tests.** Test files are ``test_*.py`` and ``*_test.py``. Tests in them are
found the way pytest's defaults find them: ``test``-prefixed functions, and
``test``-prefixed methods of ``Test``-prefixed classes without an ``__init__``
or of ``unittest.TestCase`` subclasses. A test is the artifact's oracle only if
it **references the artifact's own symbol**, resolved statically through
imports, package re-exports, relative imports and attribute chains:

* for a function, the test names the function;
* for a method ``C.m``, the test names ``C.m``, or it references ``C`` (a
  parameter annotation counts) and accesses ``.m``.

"The test" means the test function with the test-side code it pulls in: the
fixtures it requests, looked up in its class, its module, then each
``conftest.py`` from its directory up to the root, as pytest does; and the
helpers and constants it uses, followed into other test-side modules (test
files, ``conftest.py``, anything under a ``tests`` or ``test`` directory).
**Product code is never followed.** A test of ``plan()`` is not an oracle for
``match()`` just because ``plan`` calls it. Autouse fixtures,
``usefixtures``, ``setUp``-style methods and marks are part of the test's
content, but they can only supply the class half of a method link, never the
link itself: an autouse fixture that patches a function would otherwise link
every test in its scope.

**Schemas.** Classes named in the artifact's signature (``list[X]``,
``X | None`` and quoted annotations included) that are dataclasses,
``TypedDict`` subclasses or pydantic-shaped (``BaseModel`` subclasses),
directly or through another such class in the repository. Also JSON Schema
files -- a ``.json`` file whose ``$schema`` names json-schema, or any
``*.schema.json`` -- referenced by a string literal in the artifact's module or
in a linked test, resolved inside the repository only.

**Type hints** on the artifact's own signature: one oracle holding the
annotated parameters and the return, with ``self``/``cls`` left out.

Provenance and identity
-----------------------
Each oracle carries a :class:`Provenance`: the repository-relative POSIX path,
the line of the ``def`` or ``class`` (line 1 for a JSON file), the end line and
the kind. It also has an ``oracle_id``:

* a test's is its pytest node id, ``tests/test_x.py::TestC::test_m``, so it can
  be run as named;
* ``schema:<path>::<Class>``, or ``schema:<path>`` for a JSON file;
* ``type_hints:<path>::<qualname>``.

What M3 can answer from this
----------------------------
``oracle_hash`` is the field EL-201's ``CaseResult`` stores and documents as
"read by M3's reward-hack check". Here it is the SHA-256 (``case.content_hash``)
of the oracle's **closure**. Every component above -- the test with its
decorators, each fixture, helper and constant it pulls in, autouse fixtures,
setup methods, class and module marks -- is hashed from its own source text,
with line endings normalised and the text dedented. Components are keyed by
path and name, never by line, and any fixture name that could not be resolved
is included too. So:

* **it answers "did this test change between runs?"**: a weakened assertion, a
  loosened fixture, an added ``xfail`` or a trimmed ``parametrize`` list all
  change it;
* code moving down the file, or an unrelated test added beside it, does not;
* :attr:`Oracle.components` keeps each piece's own hash, so M3 can say *which*
  piece changed;
* it **cannot** see data a test reads at run time (``tests/fixtures/*.yaml``),
  fixtures supplied by plugins (they are listed in :attr:`Oracle.unresolved`),
  or pytest configuration.

A test that was already failing
-------------------------------
Whether a test failed before the developer's change is a fact about running it,
and this module runs nothing. It reports the evidence that exists without
running, and does not guess past it.

* **Declared.** An unconditional ``pytest.mark.xfail`` or
  ``unittest.expectedFailure`` -- on the test, its class, or a ``pytestmark`` --
  is an expected failure. ``skipif``, ``skipIf``, ``skipUnless`` and a
  conditional ``xfail`` are recorded as conditional, because evaluating the
  condition would mean running code. An unconditional skip is **excluded**: a
  test that never runs decides nothing. It is listed in
  :attr:`Harvest.excluded` with its marker.
* **Recorded.** ``baseline`` is a metric-store :class:`Run` judged on the code
  before the change. Each oracle is looked up by ``oracle_id``, and the
  baseline's verdict counts only when its ``oracle_hash`` matches: a test that
  changed since then is reported as changed, never as passing or failing.

:attr:`Oracle.already_failing` is ``True`` on either kind of evidence,
``False`` only when the baseline saw the same content pass, and ``None`` --
unknown -- otherwise. Unknown is never rounded to "passing": while it is
``None``, a grader must not credit a failure to the change (EL-207).

Nothing is an answer
--------------------
An artifact with no oracle gets an empty :class:`Harvest` whose ``reason`` says
why, kind by kind, and :meth:`Harvest.render` carries it into the report.
``ARCHITECTURE.md`` §9: "if nothing can decide, it says so ... It does not
invent an oracle." A file that could not be parsed is listed in
:attr:`Harvest.unsearched`, never skipped silently.

Determinism
-----------
The walk is sorted, closures are keyed by path and name, and oracles are
ordered by kind (tests, schemas, type hints), then path, line and id.
"""

from __future__ import annotations

import ast
import io
import json
import os
import textwrap
import tokenize
import warnings
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from evalloop._compat import StrEnum
from evalloop.memory.case import OracleConfidence, Verdict, content_hash
from evalloop.memory.metric_store import Run

__all__ = [
    "Artifact",
    "BaselineStatus",
    "Component",
    "Excluded",
    "Expectation",
    "Gap",
    "Harvest",
    "HarvestError",
    "Oracle",
    "OracleKind",
    "Provenance",
    "Unsearched",
    "harvest",
]


class HarvestError(Exception):
    """The artifact cannot be harvested for: outside the repository, missing, unparseable, or not a function."""


class OracleKind(StrEnum):
    """The three kinds ``AGENT.md`` §3.6 names, in the order oracles are returned."""

    test = "test"
    schema = "schema"
    type_hints = "type_hints"


_KIND_RANK = {kind: rank for rank, kind in enumerate(OracleKind)}


class Expectation(StrEnum):
    """What a test's own marks declare about it, read without evaluating anything."""

    none = "none"
    expected_failure = "expected_failure"
    conditional = "conditional"


class BaselineStatus(StrEnum):
    """What the baseline run recorded for this oracle, if one was given."""

    no_baseline = "no_baseline"
    not_in_baseline = "not_in_baseline"
    changed = "changed"
    passed = "passed"
    failed = "failed"
    inconclusive = "inconclusive"
    conflicting = "conflicting"


@dataclass(frozen=True, slots=True)
class Artifact:
    """A function or method: its repository-relative POSIX path and its qualified name."""

    path: str
    qualname: str

    @property
    def artifact_id(self) -> str:
        return f"{self.path}::{self.qualname}"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where an oracle is: a real ``file:line``, its extent, and its kind."""

    path: str
    line: int
    end_line: int
    kind: OracleKind

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True, slots=True)
class Component:
    """One piece of source an oracle's content includes, with that piece's own hash."""

    path: str
    name: str
    line: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class Oracle:
    """A harvested oracle: always HIGH, with where it is, what it covers, and why it is this artifact's."""

    oracle_id: str
    provenance: Provenance
    confidence: OracleConfidence
    oracle_hash: str
    components: tuple[Component, ...]
    unresolved: tuple[str, ...]
    evidence: str
    expectation: Expectation
    markers: tuple[str, ...]
    baseline: BaselineStatus
    baseline_note: str

    def __post_init__(self) -> None:
        if self.confidence is not OracleConfidence.high:
            raise ValueError("a harvested oracle is HIGH: a human wrote it (AGENT.md §3.6)")

    @property
    def kind(self) -> OracleKind:
        return self.provenance.kind

    @property
    def already_failing(self) -> bool | None:
        """``True`` if declared or recorded failing before the change, ``False`` if seen passing, else unknown."""
        if self.expectation is Expectation.expected_failure or self.baseline is BaselineStatus.failed:
            return True
        if self.baseline is BaselineStatus.passed:
            return False
        return None


@dataclass(frozen=True, slots=True)
class Gap:
    """Why a kind of oracle was not found."""

    kind: OracleKind
    reason: str


@dataclass(frozen=True, slots=True)
class Excluded:
    """A linked test that is not an oracle, and why: it is skipped unconditionally."""

    oracle_id: str
    path: str
    line: int
    reason: str


@dataclass(frozen=True, slots=True)
class Unsearched:
    """A file the harvest needed but could not read or parse."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Harvest:
    """Everything harvested for one artifact, and an account of everything that was not."""

    artifact: Artifact
    oracles: tuple[Oracle, ...]
    gaps: tuple[Gap, ...]
    excluded: tuple[Excluded, ...]
    unsearched: tuple[Unsearched, ...]
    test_files: int
    baseline_run: str | None

    @property
    def reason(self) -> str | None:
        """Why nothing was found, or ``None`` when something was."""
        if self.oracles:
            return None
        because = "; ".join(gap.reason for gap in self.gaps)
        return (
            f"no oracle available for {self.artifact.artifact_id}: {because}. Nothing was invented: "
            "the ladder descends, and if nothing can decide it says so (ARCHITECTURE.md §9)"
        )

    def of_kind(self, kind: OracleKind) -> tuple[Oracle, ...]:
        return tuple(oracle for oracle in self.oracles if oracle.kind is kind)

    def render(self) -> str:
        """Plain text for the report: every oracle, every gap, every exclusion, and the reason."""
        baseline = f"baseline run {self.baseline_run}" if self.baseline_run else "no baseline run"
        lines = [f"Oracles for {self.artifact.artifact_id}: {len(self.oracles)} HIGH ({baseline})"]
        for oracle in self.oracles:
            lines.append(f"  HIGH {oracle.kind.value:<10} {oracle.provenance}  {oracle.oracle_id}")
            lines.append(f"       {oracle.evidence}")
            if oracle.markers:
                lines.append(f"       marked: {', '.join(oracle.markers)}")
            if self.baseline_run is not None or oracle.already_failing:
                state = {True: "ALREADY FAILING", False: "passing before", None: "unknown before"}
                lines.append(f"       {state[oracle.already_failing]}: {oracle.baseline_note}")
        lines.extend(f"  no {gap.kind.value}: {gap.reason}" for gap in self.gaps)
        lines.extend(f"  excluded {item.oracle_id}: {item.reason}" for item in self.excluded)
        lines.extend(f"  not searched {item.path}: {item.reason}" for item in self.unsearched)
        if self.reason is not None:
            lines.append(self.reason)
        return "\n".join(lines)


# -- reading the repository ------------------------------------------------------

_SKIPPED_DIRS = frozenset({"__pycache__", "node_modules", "site-packages", "dist-packages"})
_VENV_MARKER = "pyvenv.cfg"
_TEST_DIRS = frozenset({"tests", "test"})
_CLASS_SETUP = frozenset(
    {
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
        "asyncSetUp",
        "asyncTearDown",
        "setup_method",
        "teardown_method",
        "setup_class",
        "teardown_class",
    }
)
_MODULE_SETUP = frozenset({"setup_module", "teardown_module", "setup_function", "teardown_function"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

_Function = ast.FunctionDef | ast.AsyncFunctionDef
_Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
_Target = tuple[str, "str | None"]  # (path, symbol); a None symbol is the module itself
_Key = tuple[str, int, int, str]


def _is_test_file(name: str) -> bool:
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def _is_test_side(path: str) -> bool:
    """Test files, conftest files, and anything under a tests/ or test/ directory: never product code."""
    posix = PurePosixPath(path)
    return _is_test_file(posix.name) or posix.name == "conftest.py" or bool(_TEST_DIRS & set(posix.parts[:-1]))


def _walk(root: Path) -> list[str]:
    found: list[str] = []
    for directory, dirnames, filenames in os.walk(root):
        if _VENV_MARKER in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and name not in _SKIPPED_DIRS
            and not os.path.islink(os.path.join(directory, name))
        )
        for name in sorted(filenames):
            full = os.path.join(directory, name)
            if name.endswith(".py") and not os.path.islink(full):
                found.append(Path(full).relative_to(root).as_posix())
    return sorted(found)


def _chain(node: ast.expr) -> list[str] | None:
    """``a.b.c`` as ``["a", "b", "c"]``, or ``None`` when the base is not a name."""
    names: list[str] = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    names.append(node.id)
    names.reverse()
    return names


def _absolute(module: str | None, level: int, package: str) -> str | None:
    """The absolute module an import names; ``None`` for a relative import that leaves the package."""
    if level == 0:
        return module
    parts = package.split(".") if package else []
    if level - 1 > len(parts):
        return None
    base = parts[: len(parts) - (level - 1)]
    if module:
        base.extend(module.split("."))
    return ".".join(base) or None


def _target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _target_names(element)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _bound_names(statement: ast.stmt) -> list[str]:
    if isinstance(statement, ast.Assign):
        return [name for target in statement.targets for name in _target_names(target)]
    if isinstance(statement, ast.AnnAssign):
        return _target_names(statement.target)
    return []


@dataclass(frozen=True, slots=True)
class _Import:
    module: str
    name: str | None  # None: the binding is the module itself


_Binding = ast.stmt | _Import


@dataclass(eq=False)
class _Module:
    path: str
    dotted: str
    import_root: str
    is_package: bool
    tree: ast.Module
    source: str
    lines: list[str]
    bindings: dict[str, _Binding]
    stars: list[str]

    @property
    def package(self) -> str:
        return self.dotted if self.is_package else self.dotted.rpartition(".")[0]

    def segment(self, start: int, end: int) -> str:
        return textwrap.dedent("\n".join(self.lines[start - 1 : end]))

    def text_of(self, node: ast.expr) -> str:
        """An expression's own source, whitespace collapsed: never ``ast.unparse``, whose output varies by version."""
        segment = ast.get_source_segment(self.source, node)
        return " ".join(segment.split()) if segment else "?"


def _bindings(tree: ast.Module, package: str) -> tuple[dict[str, _Binding], list[str]]:
    bindings: dict[str, _Binding] = {}
    stars: list[str] = []

    def visit(body: Sequence[ast.stmt]) -> None:
        for statement in body:
            if isinstance(statement, _DEFINITIONS):
                bindings[statement.name] = statement
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                if isinstance(statement, ast.AnnAssign) and statement.value is None:
                    continue
                for name in _bound_names(statement):
                    bindings[name] = statement
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    if alias.asname:
                        bindings[alias.asname] = _Import(alias.name, None)
                    else:
                        top = alias.name.split(".")[0]
                        bindings[top] = _Import(top, None)
            elif isinstance(statement, ast.ImportFrom):
                base = _absolute(statement.module, statement.level, package)
                if base is None:
                    continue
                for alias in statement.names:
                    if alias.name == "*":
                        stars.append(base)
                    else:
                        bindings[alias.asname or alias.name] = _Import(base, alias.name)
            elif isinstance(statement, ast.If):
                visit(statement.body)
                visit(statement.orelse)
            elif isinstance(statement, ast.Try):
                visit(statement.body)
                for handler in statement.handlers:
                    visit(handler.body)
                visit(statement.orelse)
                visit(statement.finalbody)
            elif isinstance(statement, ast.With):
                visit(statement.body)

    visit(tree.body)
    return bindings, stars


def _parse_text(text: str, filename: str, mode: str = "exec") -> ast.AST:
    """``ast.parse`` with warnings silenced: under ``-W error`` an invalid escape would become a SyntaxError."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(text, filename=filename, mode=mode)


def _quoted(text: str) -> list[ast.expr]:
    """The outermost names and attribute chains in a quoted annotation."""
    try:
        tree = _parse_text(text, "<annotation>", "eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    if not isinstance(tree, ast.Expression):
        return []
    nodes = list(ast.walk(tree.body))
    inner = {id(node.value) for node in nodes if isinstance(node, ast.Attribute)}
    return [node for node in nodes if isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in inner]


@dataclass(frozen=True)
class _Scope:
    local: frozenset[str]
    imports: dict[str, _Import]


_MODULE_SCOPE = _Scope(frozenset(), {})


def _scope_of(module: _Module, roots: Sequence[ast.AST]) -> _Scope:
    """Names bound inside these nodes, which therefore shadow module-level ones, and imports made locally."""
    local: set[str] = set()
    imports: dict[str, _Import] = {}
    for root in roots:
        for node in ast.walk(root):
            if isinstance(node, ast.arg):
                local.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                local.add(node.id)
            elif isinstance(node, _DEFINITIONS) and node is not root:
                local.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        imports[alias.asname] = _Import(alias.name, None)
                    else:
                        top = alias.name.split(".")[0]
                        imports[top] = _Import(top, None)
            elif isinstance(node, ast.ImportFrom):
                base = _absolute(node.module, node.level, module.package)
                if base is not None:
                    for alias in node.names:
                        if alias.name != "*":
                            imports[alias.asname or alias.name] = _Import(base, alias.name)
    return _Scope(frozenset(local - imports.keys()), imports)


def _fixture_spec(node: _Function) -> tuple[str, bool] | None:
    """``(fixture name, autouse)`` if the function is a pytest fixture."""
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        chain = _chain(call.func if call is not None else decorator)
        if not chain or chain[-1] != "fixture":
            continue
        name, autouse = node.name, False
        for keyword in call.keywords if call is not None else ():
            value = keyword.value
            if keyword.arg == "name" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                name = value.value
            if keyword.arg == "autouse" and isinstance(value, ast.Constant) and value.value is True:
                autouse = True
        return name, autouse
    return None


def _fixtures_in(body: Sequence[ast.stmt]) -> list[tuple[str, bool, _Function]]:
    found: list[tuple[str, bool, _Function]] = []
    for statement in body:
        if isinstance(statement, _FUNCTIONS):
            spec = _fixture_spec(statement)
            if spec is not None:
                found.append((spec[0], spec[1], statement))
    return found


def _pytestmark(body: Sequence[ast.stmt]) -> list[ast.Assign]:
    return [
        statement
        for statement in body
        if isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in statement.targets)
    ]


def _mark_values(statements: Sequence[ast.Assign]) -> list[ast.expr]:
    marks: list[ast.expr] = []
    for statement in statements:
        value = statement.value
        marks.extend(value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value])
    return marks


def _string_args(call: ast.Call) -> list[str]:
    return [arg.value for arg in call.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]


def _parametrized(marks: Sequence[ast.expr]) -> set[str]:
    """Argument names a ``parametrize`` supplies directly: those are not fixture requests."""
    names: set[str] = set()
    for mark in marks:
        if not isinstance(mark, ast.Call):
            continue
        chain = _chain(mark.func)
        if not chain or chain[-1] != "parametrize":
            continue
        spec = mark.args[0] if mark.args else next((k.value for k in mark.keywords if k.arg == "argnames"), None)
        given: list[str] = []
        if isinstance(spec, ast.Constant) and isinstance(spec.value, str):
            given = [name.strip() for name in spec.value.split(",") if name.strip()]
        elif isinstance(spec, (ast.Tuple, ast.List)):
            given = [e.value for e in spec.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        indirect = next((k.value for k in mark.keywords if k.arg == "indirect"), None)
        if isinstance(indirect, ast.Constant) and indirect.value is True:
            continue
        if isinstance(indirect, (ast.List, ast.Tuple)):
            routed = {e.value for e in indirect.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            given = [name for name in given if name not in routed]
        names.update(given)
    return names


def _usefixtures(marks: Sequence[ast.expr]) -> list[str]:
    names: list[str] = []
    for mark in marks:
        if isinstance(mark, ast.Call):
            chain = _chain(mark.func)
            if chain and chain[-1] == "usefixtures":
                names.extend(_string_args(mark))
    return names


def _is_staticmethod(node: _Function) -> bool:
    return any(_chain(d) == ["staticmethod"] for d in node.decorator_list)


def _requests(node: _Function, is_method: bool, parametrized: set[str]) -> list[str]:
    """Fixture requests: parameters without defaults, minus ``self`` and parametrized names (pytest's rules)."""
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    first_default = len(positional) - len(args.defaults)
    names = [arg.arg for index, arg in enumerate(positional) if index < first_default]
    if is_method and positional and not _is_staticmethod(node) and names[:1] == [positional[0].arg]:
        names = names[1:]
    names.extend(arg.arg for arg, default in zip(args.kwonlyargs, args.kw_defaults) if default is None)
    return [name for name in names if name not in parametrized]


def _definition_start(node: _Definition) -> int:
    return min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])


def _closure_hash(components: Iterable[Component], unresolved: Iterable[str]) -> str:
    document = {
        "components": sorted([c.path, c.name, c.content_hash] for c in components),
        "unresolved": sorted(unresolved),
    }
    return content_hash(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _text_hash(text: str) -> str:
    return content_hash(text.encode("utf-8"))


# -- one test's closure ---------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _Item:
    module: _Module
    key: _Key
    label: str
    line: int
    segment: str
    roots: tuple[ast.AST, ...]
    owner: ast.ClassDef | None
    function: _Function | None  # set when this item's fixture requests are followed
    parametrized: frozenset[str]
    setup: bool
    via: str | None


@dataclass(frozen=True, slots=True)
class _Ref:
    target: tuple[str, str]
    path: str
    line: int
    via: str | None


def _ref_order(ref: _Ref) -> tuple[bool, str, int]:
    return (ref.via is not None, ref.path, ref.line)


@dataclass
class _Closure:
    components: dict[_Key, Component] = field(default_factory=dict)
    link: list[_Ref] = field(default_factory=list)
    setup: list[_Ref] = field(default_factory=list)
    attributes: list[tuple[str, str, int, str | None]] = field(default_factory=list)
    json_literals: list[tuple[str, str, int]] = field(default_factory=list)
    unresolved: set[str] = field(default_factory=set)


# -- the repository -------------------------------------------------------------------


class _Repo:
    """One harvest's view of a repository: every file read at most once, nothing executed."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = _walk(root)
        self.file_set = frozenset(self.files)
        package_dirs = {
            PurePosixPath(path).parent.as_posix() for path in self.files if PurePosixPath(path).name == "__init__.py"
        }
        self.index: dict[str, list[tuple[str, str]]] = {}
        self.names: dict[str, tuple[str, str, bool]] = {}
        for path in self.files:
            posix = PurePosixPath(path)
            dirs = list(posix.parts[:-1])
            names = [] if posix.stem == "__init__" else [posix.stem]
            while dirs and "/".join(dirs) in package_dirs:
                names.insert(0, dirs.pop())
            if names:
                dotted, import_root = ".".join(names), "/".join(dirs)
                self.names[path] = (dotted, import_root, posix.stem == "__init__")
                self.index.setdefault(dotted, []).append((import_root, path))
        self.modules: dict[str, _Module | None] = {}
        self.failures: dict[str, str] = {}
        self._resolved: dict[tuple[str, str], _Target | None] = {}

    # -- files and modules ----------------------------------------------------------

    def load(self, path: str) -> _Module | None:
        if path in self.modules:
            return self.modules[path]
        module: _Module | None = None
        dotted, import_root, is_package = self.names.get(path, (PurePosixPath(path).stem, "", False))
        try:
            data = (self.root / path).read_bytes()
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
            source = data.decode(encoding)
            tree = _parse_text(source, path)
        except SyntaxError as error:
            self.failures[path] = f"does not parse (line {error.lineno}: {error.msg})"
        except OSError as error:
            self.failures[path] = f"could not be read ({error.strerror or error})"
        except (ValueError, LookupError, RecursionError, MemoryError) as error:
            self.failures[path] = f"could not be decoded or parsed ({type(error).__name__})"
        else:
            if isinstance(tree, ast.Module):
                package = dotted if is_package else dotted.rpartition(".")[0]
                bindings, stars = _bindings(tree, package)
                lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                module = _Module(path, dotted, import_root, is_package, tree, source, lines, bindings, stars)
        self.modules[path] = module
        return module

    def module_path(self, dotted: str, importer: _Module) -> str | None:
        """The file a dotted name means to this importer; ``None`` if external or ambiguous."""
        candidates = self.index.get(dotted, [])
        if len(candidates) == 1:
            return candidates[0][1]
        same_root = [path for root, path in candidates if root == importer.import_root]
        return same_root[0] if len(same_root) == 1 else None

    # -- name resolution ------------------------------------------------------------

    def resolve_name(self, module: _Module, name: str) -> _Target | None:
        key = (module.path, name)
        if key not in self._resolved:
            self._resolved[key] = self._resolve_name(module, name, frozenset())
        return self._resolved[key]

    def _resolve_name(self, module: _Module, name: str, seen: frozenset[tuple[str, str]]) -> _Target | None:
        key = (module.path, name)
        if key in seen:
            return None
        seen = seen | {key}
        bound = module.bindings.get(name)
        if isinstance(bound, _Import):
            return self._resolve_import(module, bound, seen)
        if bound is not None:
            return (module.path, name)
        for star in module.stars:
            star_path = self.module_path(star, module)
            star_module = self.load(star_path) if star_path else None
            if star_module is not None:
                found = self._resolve_name(star_module, name, seen)
                if found is not None:
                    return found
        if module.is_package:
            submodule = self.module_path(f"{module.dotted}.{name}", module)
            if submodule is not None:
                return (submodule, None)
        return None

    def _resolve_import(self, module: _Module, bound: _Import, seen: frozenset[tuple[str, str]]) -> _Target | None:
        if bound.name is None:
            path = self.module_path(bound.module, module)
            return None if path is None else (path, None)
        source_path = self.module_path(bound.module, module)
        source = self.load(source_path) if source_path else None
        if source is not None:
            found = self._resolve_name(source, bound.name, seen)
            if found is not None:
                return found
        submodule = self.module_path(f"{bound.module}.{bound.name}", module)
        return None if submodule is None else (submodule, None)

    def resolve_expr(self, module: _Module, node: ast.expr, scope: _Scope) -> _Target | None:
        """What a name or attribute chain refers to: a module, a top-level symbol, or ``Class.member``."""
        chain = _chain(node)
        if chain is None:
            return None
        base, attributes = chain[0], chain[1:]
        target: _Target | None
        if base in scope.imports:
            target = self._resolve_import(module, scope.imports[base], frozenset())
        elif base in scope.local:
            return None
        else:
            target = self.resolve_name(module, base)
        for attribute in attributes:
            if target is None:
                return None
            path, symbol = target
            if symbol is None:
                inner = self.load(path)
                target = None if inner is None else self.resolve_name(inner, attribute)
            elif "." not in symbol:
                target = (path, f"{symbol}.{attribute}")
            else:
                return target
        return target

    def definition(self, path: str, symbol: str) -> tuple[_Module, ast.stmt] | None:
        module = self.load(path)
        if module is None:
            return None
        bound = module.bindings.get(symbol.split(".")[0])
        if bound is None or isinstance(bound, _Import):
            return None
        return module, bound

    def class_def(self, target: _Target | None) -> tuple[_Module, ast.ClassDef] | None:
        if target is None or target[1] is None or "." in target[1]:
            return None
        found = self.definition(target[0], target[1])
        if found is None or not isinstance(found[1], ast.ClassDef):
            return None
        return found[0], found[1]

    # -- closure items ----------------------------------------------------------------

    def def_item(
        self,
        module: _Module,
        node: _Definition,
        owner: ast.ClassDef | None,
        *,
        setup: bool,
        via: str | None,
        requests: bool = False,
        parametrized: frozenset[str] = frozenset(),
    ) -> _Item:
        start = _definition_start(node)
        label = f"{owner.name}.{node.name}" if owner is not None else node.name
        return _Item(
            module,
            (module.path, start, node.col_offset, ""),
            label,
            node.lineno,
            module.segment(start, node.end_lineno or node.lineno),
            (node,),
            owner,
            node if requests and isinstance(node, _FUNCTIONS) else None,
            parametrized,
            setup,
            via,
        )

    def statement_item(self, module: _Module, statement: ast.stmt, *, setup: bool, via: str | None) -> _Item:
        label = ", ".join(_bound_names(statement)) or "<statement>"
        return _Item(
            module,
            (module.path, statement.lineno, statement.col_offset, ""),
            label,
            statement.lineno,
            module.segment(statement.lineno, statement.end_lineno or statement.lineno),
            (statement,),
            None,
            None,
            frozenset(),
            setup,
            via,
        )

    def header_item(self, module: _Module, cls: ast.ClassDef) -> _Item:
        """A test class's decorators, bases and class-level assignments: the part every method inherits."""
        start = _definition_start(cls)
        header_end = max(cls.lineno, cls.body[0].lineno - 1)
        parts = [module.segment(start, header_end)]
        roots: list[ast.AST] = [*cls.decorator_list, *cls.bases, *(keyword.value for keyword in cls.keywords)]
        for statement in cls.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                parts.append(module.segment(statement.lineno, statement.end_lineno or statement.lineno))
                roots.append(statement)
        return _Item(
            module,
            (module.path, cls.lineno, cls.col_offset, "header"),
            f"{cls.name} (class)",
            cls.lineno,
            "\n".join(parts),
            tuple(roots),
            None,
            None,
            frozenset(),
            True,
            None,
        )

    # -- fixtures ---------------------------------------------------------------------

    def conftests(self, path: str) -> list[_Module]:
        """``conftest.py`` from the test's directory up to the root, nearest first."""
        found: list[_Module] = []
        parts = list(PurePosixPath(path).parts[:-1])
        while True:
            candidate = "/".join([*parts, "conftest.py"])
            if candidate in self.file_set and candidate != path:
                module = self.load(candidate)
                if module is not None:
                    found.append(module)
            if not parts:
                return found
            parts.pop()

    def containers(
        self, module: _Module, owner: ast.ClassDef | None
    ) -> list[tuple[_Module, Sequence[ast.stmt], ast.ClassDef | None]]:
        found: list[tuple[_Module, Sequence[ast.stmt], ast.ClassDef | None]] = []
        if owner is not None:
            found.append((module, owner.body, owner))
        found.append((module, module.tree.body, None))
        found.extend((conftest, conftest.tree.body, None) for conftest in self.conftests(module.path))
        return found

    def fixture(
        self, name: str, module: _Module, owner: ast.ClassDef | None, exclude: _Function | None
    ) -> tuple[_Module, _Function, ast.ClassDef | None] | None:
        """The definition pytest would use for ``name``, seen from a test in ``module``/``owner``."""
        for container, body, cls in self.containers(module, owner):
            for fixture_name, _, node in reversed(_fixtures_in(body)):
                if fixture_name == name and node is not exclude:
                    return container, node, cls
        return None

    def autouse(self, module: _Module, owner: ast.ClassDef | None) -> list[tuple[str, _Module, _Function, ast.ClassDef | None]]:
        found: list[tuple[str, _Module, _Function, ast.ClassDef | None]] = []
        for container, body, cls in self.containers(module, owner):
            found.extend((name, container, node, cls) for name, autouse, node in _fixtures_in(body) if autouse)
        return found

    # -- marks ------------------------------------------------------------------------

    def marks(self, module: _Module, node: _Function, owner: ast.ClassDef | None) -> list[ast.expr]:
        marks = list(node.decorator_list)
        if owner is not None:
            marks.extend(owner.decorator_list)
            marks.extend(_mark_values(_pytestmark(owner.body)))
        marks.extend(_mark_values(_pytestmark(module.tree.body)))
        return marks

    def _from_unittest(self, module: _Module, name: str) -> bool:
        bound = module.bindings.get(name)
        return isinstance(bound, _Import) and (bound.module == "unittest" or bound.module.startswith("unittest."))

    def expectation(self, module: _Module, marks: Sequence[ast.expr]) -> tuple[Expectation, bool, list[str]]:
        """What the marks declare: ``(expectation, unconditionally skipped, matching marks' source)``."""
        expected, conditional, skipped = False, False, False
        texts: list[str] = []
        for mark in marks:
            call = mark if isinstance(mark, ast.Call) else None
            chain = _chain(call.func if call is not None else mark)
            if not chain:
                continue
            last = chain[-1]
            pytest_mark = len(chain) >= 2 and chain[-2] == "mark"
            unittest_mark = chain[0] == "unittest" or (len(chain) == 1 and self._from_unittest(module, last))
            if pytest_mark and last == "xfail":
                has_condition = call is not None and (
                    bool(call.args) or any(k.arg == "condition" for k in call.keywords)
                )
                conditional, expected = conditional or has_condition, expected or not has_condition
            elif unittest_mark and last == "expectedFailure":
                expected = True
            elif (pytest_mark or unittest_mark) and last == "skip":
                skipped = True
            elif (pytest_mark and last == "skipif") or (unittest_mark and last in ("skipIf", "skipUnless")):
                conditional = True
            else:
                continue
            texts.append(module.text_of(mark))
        if expected:
            return Expectation.expected_failure, skipped, texts
        return (Expectation.conditional if conditional else Expectation.none), skipped, texts

    # -- tests ------------------------------------------------------------------------

    def _is_test_class(self, module: _Module, cls: ast.ClassDef) -> bool:
        for base in cls.bases:
            chain = _chain(base)
            if chain and chain[-1].endswith("TestCase"):
                return True
        return cls.name.startswith("Test") and not any(
            isinstance(member, _FUNCTIONS) and member.name == "__init__" for member in cls.body
        )

    def tests(self, module: _Module) -> list[tuple[_Function, ast.ClassDef | None]]:
        found: dict[tuple[str, str], tuple[_Function, ast.ClassDef | None]] = {}
        for statement in module.tree.body:
            if isinstance(statement, _FUNCTIONS) and statement.name.startswith("test"):
                if _fixture_spec(statement) is None:
                    found[("", statement.name)] = (statement, None)
            elif isinstance(statement, ast.ClassDef) and self._is_test_class(module, statement):
                for member in statement.body:
                    if isinstance(member, _FUNCTIONS) and member.name.startswith("test"):
                        found[(statement.name, member.name)] = (member, statement)
        return sorted(found.values(), key=lambda pair: (pair[0].lineno, pair[0].col_offset))

    def close_test(self, module: _Module, node: _Function, owner: ast.ClassDef | None) -> _Closure:
        marks = self.marks(module, node, owner)
        parametrized = frozenset(_parametrized(marks))
        start = [self.def_item(module, node, owner, setup=False, via=None, requests=True, parametrized=parametrized)]
        for mark_statement in _pytestmark(module.tree.body):
            start.append(self.statement_item(module, mark_statement, setup=True, via=None))
        for statement in module.tree.body:
            if isinstance(statement, _FUNCTIONS) and statement.name in _MODULE_SETUP:
                start.append(self.def_item(module, statement, None, setup=True, via=f"setup {statement.name}"))
        if owner is not None:
            start.append(self.header_item(module, owner))
            for member in owner.body:
                if isinstance(member, _FUNCTIONS) and member.name in _CLASS_SETUP:
                    start.append(self.def_item(module, member, owner, setup=True, via=f"setup {member.name}"))
        for name, container, fixture, cls in self.autouse(module, owner):
            start.append(
                self.def_item(container, fixture, cls, setup=True, via=f"autouse fixture {name}", requests=True)
            )
        closure = _Closure()
        for name in _usefixtures(marks):
            found = self.fixture(name, module, owner, None)
            if found is None:
                closure.unresolved.add(name)
            else:
                start.append(self.def_item(found[0], found[1], found[2], setup=True, via=f"fixture {name}", requests=True))
        self._close(start, module, owner, closure)
        return closure

    def _close(self, start: list[_Item], module: _Module, owner: ast.ClassDef | None, closure: _Closure) -> None:
        queue = deque(start)
        seen: set[tuple[_Key, bool]] = set()
        while queue:
            item = queue.popleft()
            if (item.key, item.setup) in seen:
                continue
            seen.add((item.key, item.setup))
            closure.components.setdefault(
                item.key, Component(item.module.path, item.label, item.line, _text_hash(item.segment))
            )
            self._walk(item, closure, queue)
            if item.function is None:
                continue
            for name in _requests(item.function, item.owner is not None, set(item.parametrized)):
                found = self.fixture(name, module, owner, item.function)
                if found is None:
                    closure.unresolved.add(name)
                    continue
                queue.append(
                    self.def_item(
                        found[0], found[1], found[2], setup=item.setup, via=item.via or f"fixture {name}", requests=True
                    )
                )

    def _walk(self, item: _Item, closure: _Closure, queue: deque[_Item]) -> None:
        scope = _scope_of(item.module, item.roots)
        nodes = [node for root in item.roots for node in ast.walk(root)]
        inner = {id(node.value) for node in nodes if isinstance(node, ast.Attribute)}
        for node in nodes:
            if isinstance(node, ast.Attribute) and not item.setup:
                closure.attributes.append((node.attr, item.module.path, node.lineno, item.via))
            if isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in inner:
                if isinstance(node.ctx, ast.Load):
                    self._reference(item, node, node.lineno, scope, closure, queue)
            elif isinstance(node, ast.arg) and isinstance(node.annotation, ast.Constant):
                if isinstance(node.annotation.value, str):
                    for quoted in _quoted(node.annotation.value):
                        self._reference(item, quoted, node.lineno, scope, closure, queue)
            elif isinstance(node, _FUNCTIONS) and isinstance(node.returns, ast.Constant):
                if isinstance(node.returns.value, str):
                    for quoted in _quoted(node.returns.value):
                        self._reference(item, quoted, node.lineno, scope, closure, queue)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and not item.setup:
                if node.value.lower().endswith(".json"):
                    closure.json_literals.append((node.value, item.module.path, node.lineno))

    def _reference(
        self, item: _Item, node: ast.expr, line: int, scope: _Scope, closure: _Closure, queue: deque[_Item]
    ) -> None:
        target = self.resolve_expr(item.module, node, scope)
        if target is None:
            return
        path, symbol = target
        if symbol is None:
            return  # a module is not a symbol
        (closure.setup if item.setup else closure.link).append(_Ref((path, symbol), item.module.path, line, item.via))
        if not _is_test_side(path):
            return  # product code is what the test checks, never part of the test
        found = self.definition(path, symbol)
        if found is None:
            return
        module, statement = found
        if isinstance(statement, _DEFINITIONS):
            queue.append(
                self.def_item(module, statement, None, setup=item.setup, via=item.via or f"helper {statement.name}")
            )
        else:
            queue.append(self.statement_item(module, statement, setup=item.setup, via=item.via))

    # -- JSON Schema files --------------------------------------------------------------

    def inside(self, literal: str, referenced_from: str) -> str | None:
        """A relative path literal resolved inside the repository, or ``None``. Absolute paths are never read."""
        if not literal or "\\" in literal or PurePosixPath(literal).is_absolute():
            return None
        for base in (self.root, (self.root / referenced_from).parent):
            try:
                resolved = (base / literal).resolve()
                relative = resolved.relative_to(self.root)
            except (OSError, RuntimeError, ValueError):
                continue
            if resolved.is_file():
                return relative.as_posix()
        return None


# -- the harvest -------------------------------------------------------------------------


def _locate(repo: _Repo, artifact: Artifact) -> tuple[_Module, _Function, ast.ClassDef | None]:
    posix = PurePosixPath(artifact.path)
    if posix.is_absolute() or ".." in posix.parts or posix.as_posix() != artifact.path:
        raise HarvestError(f"{artifact.path!r} must be a normalised path relative to the repository root")
    if artifact.path not in repo.file_set:
        raise HarvestError(f"{artifact.path} is not a Python file in the repository")
    module = repo.load(artifact.path)
    if module is None:
        raise HarvestError(f"{artifact.path} {repo.failures.get(artifact.path, 'could not be parsed')}")
    parts = artifact.qualname.split(".")
    bound = module.bindings.get(parts[0])
    if len(parts) == 1 and isinstance(bound, _FUNCTIONS):
        return module, bound, None
    if len(parts) == 2 and isinstance(bound, ast.ClassDef):
        members = [m for m in bound.body if isinstance(m, _FUNCTIONS) and m.name == parts[1]]
        if members:
            return module, members[-1], bound
    raise HarvestError(f"{artifact.artifact_id} is not a top-level function or a method of a top-level class")


def _baseline(run: Run | None, oracle_id: str, oracle_hash: str) -> tuple[BaselineStatus, str]:
    if run is None:
        return BaselineStatus.no_baseline, "no baseline run was given, so a failure is neither excused nor attributed"
    cases = [case for case in run.cases if case.oracle_id == oracle_id]
    if not cases:
        return BaselineStatus.not_in_baseline, f"run {run.run_id} did not judge this oracle"
    same = [case for case in cases if case.oracle_hash == oracle_hash]
    if not same:
        return (
            BaselineStatus.changed,
            f"run {run.run_id} judged a different version of this oracle, so its verdict does not carry over",
        )
    verdicts = {case.verdict for case in same}
    if verdicts == {Verdict.failed}:
        classes = sorted({case.failure_class.value for case in same if case.failure_class is not None})
        return BaselineStatus.failed, f"failed in run {run.run_id} with identical content ({', '.join(classes)})"
    if verdicts == {Verdict.passed}:
        return BaselineStatus.passed, f"passed in run {run.run_id} with identical content"
    if verdicts == {Verdict.inconclusive}:
        return BaselineStatus.inconclusive, f"run {run.run_id} could not decide it (inconclusive)"
    named = ", ".join(sorted(verdict.value for verdict in verdicts))
    return BaselineStatus.conflicting, f"run {run.run_id} recorded conflicting verdicts for it: {named}"


def _evidence(closure: _Closure, artifact: Artifact) -> str | None:
    """Why this test is the artifact's oracle, or ``None`` if it is not."""
    wanted = (artifact.path, artifact.qualname)
    direct = sorted((ref for ref in closure.link if ref.target == wanted), key=_ref_order)
    if direct:
        ref = direct[0]
        via = f", via {ref.via}" if ref.via else ""
        return f"references {artifact.qualname} at {ref.path}:{ref.line}{via}"
    if "." not in artifact.qualname:
        return None
    cls, _, method = artifact.qualname.partition(".")
    classes = sorted(
        (
            ref
            for ref in [*closure.link, *closure.setup]
            if ref.target[0] == artifact.path and (ref.target[1] == cls or ref.target[1].startswith(cls + "."))
        ),
        key=_ref_order,
    )
    accesses = sorted(
        ((via is not None, path, line, via) for name, path, line, via in closure.attributes if name == method)
    )
    if not classes or not accesses:
        return None
    holder, (_, access_path, access_line, access_through) = classes[0], accesses[0]
    holder_via = f" via {holder.via}" if holder.via else ""
    access_via = f" via {access_through}" if access_through else ""
    return (
        f"references {cls} at {holder.path}:{holder.line}{holder_via} "
        f"and accesses .{method} at {access_path}:{access_line}{access_via}"
    )


def _annotations(fn: _Function, is_method: bool) -> list[tuple[str, ast.expr]]:
    args = fn.args
    positional = [*args.posonlyargs, *args.args]
    if is_method and positional and not _is_staticmethod(fn):
        positional = positional[1:]
    every = [*positional, *([args.vararg] if args.vararg else []), *args.kwonlyargs, *([args.kwarg] if args.kwarg else [])]
    found = [(f"parameter {arg.arg}", arg.annotation) for arg in every if arg.annotation is not None]
    if fn.returns is not None:
        found.append(("return", fn.returns))
    return found


def _signature(module: _Module, fn: _Function, is_method: bool) -> tuple[str, int, int, bool]:
    """The signature's annotated shape as text, from each annotation's own source; and how much is annotated."""
    args = fn.args
    positional = [*args.posonlyargs, *args.args]
    skip = 1 if is_method and positional and not _is_staticmethod(fn) else 0
    rendered: list[str] = []
    total = annotated = 0

    def show(arg: ast.arg, prefix: str = "") -> None:
        nonlocal total, annotated
        total += 1
        if arg.annotation is None:
            rendered.append(f"{prefix}{arg.arg}")
        else:
            annotated += 1
            rendered.append(f"{prefix}{arg.arg}: {module.text_of(arg.annotation)}")

    for index, arg in enumerate(positional):
        if index >= skip:
            show(arg)
        if args.posonlyargs and index == len(args.posonlyargs) - 1 and index >= skip:
            rendered.append("/")
    if args.vararg is not None:
        show(args.vararg, "*")
    elif args.kwonlyargs:
        rendered.append("*")
    for arg in args.kwonlyargs:
        show(arg)
    if args.kwarg is not None:
        show(args.kwarg, "**")
    returns = f" -> {module.text_of(fn.returns)}" if fn.returns is not None else ""
    return f"({', '.join(rendered)}){returns}", annotated, total, fn.returns is not None


def _schema_kind(repo: _Repo, module: _Module, cls: ast.ClassDef, seen: frozenset[tuple[str, str]]) -> str | None:
    for decorator in cls.decorator_list:
        chain = _chain(decorator.func if isinstance(decorator, ast.Call) else decorator)
        if chain and chain[-1] == "dataclass":
            return "dataclass"
    for base in cls.bases:
        node = base.value if isinstance(base, ast.Subscript) else base
        chain = _chain(node)
        if not chain:
            continue
        if chain[-1] == "TypedDict":
            return "TypedDict"
        if chain[-1] == "BaseModel":
            return "pydantic-shaped"
        found = repo.class_def(repo.resolve_expr(module, node, _MODULE_SCOPE))
        if found is not None and (found[0].path, found[1].name) not in seen:
            kind = _schema_kind(repo, found[0], found[1], seen | {(found[0].path, found[1].name)})
            if kind is not None:
                return kind
    return None


def _annotation_classes(repo: _Repo, module: _Module, annotation: ast.expr) -> list[tuple[_Module, ast.ClassDef]]:
    """In-repository classes an annotation names, quoted names included, in source order."""
    nodes: list[ast.expr] = []
    walked = list(ast.walk(annotation))
    inner = {id(node.value) for node in walked if isinstance(node, ast.Attribute)}
    for node in walked:
        if isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in inner:
            nodes.append(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            nodes.extend(_quoted(node.value))
    found: list[tuple[_Module, ast.ClassDef]] = []
    for node in nodes:
        located = repo.class_def(repo.resolve_expr(module, node, _MODULE_SCOPE))
        if located is not None:
            found.append(located)
    return found


def _schema_components(repo: _Repo, module: _Module, cls: ast.ClassDef, into: dict[tuple[str, str], Component]) -> None:
    """The schema class, its schema bases, and the schema classes its fields name, transitively."""
    key = (module.path, cls.name)
    if key in into:
        return
    start = _definition_start(cls)
    into[key] = Component(module.path, cls.name, cls.lineno, _text_hash(module.segment(start, cls.end_lineno or cls.lineno)))
    related = [node.value if isinstance(node, ast.Subscript) else node for node in cls.bases]
    related.extend(s.annotation for s in cls.body if isinstance(s, ast.AnnAssign))
    for node in related:
        for found_module, found in _annotation_classes(repo, module, node):
            if _schema_kind(repo, found_module, found, frozenset()) is not None:
                _schema_components(repo, found_module, found, into)


def _oracle(
    oracle_id: str,
    provenance: Provenance,
    components: Iterable[Component],
    unresolved: Iterable[str],
    evidence: str,
    baseline: Run | None,
    expectation: Expectation = Expectation.none,
    markers: Sequence[str] = (),
) -> Oracle:
    ordered = tuple(sorted(components, key=lambda c: (c.path, c.line, c.name)))
    missing = tuple(sorted(set(unresolved)))
    oracle_hash = _closure_hash(ordered, missing)
    status, note = _baseline(baseline, oracle_id, oracle_hash)
    return Oracle(
        oracle_id,
        provenance,
        OracleConfidence.high,
        oracle_hash,
        ordered,
        missing,
        evidence,
        expectation,
        tuple(markers),
        status,
        note,
    )


def harvest(root: str | os.PathLike[str], artifact: Artifact, *, baseline: Run | None = None) -> Harvest:
    """Every oracle the repository at ``root`` already holds for ``artifact``, each tagged HIGH.

    ``baseline`` is a metric-store run judged on the code before the change; without it, whether a
    test was already failing is reported only as far as its own marks declare it. Nothing in the
    repository is imported or executed.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        raise HarvestError(f"{root_path} is not a directory")
    repo = _Repo(root_path.resolve())
    module, fn, owner = _locate(repo, artifact)
    is_method = owner is not None
    oracles: list[Oracle] = []
    excluded: list[Excluded] = []
    json_refs: list[tuple[str, str, int]] = []

    test_files = [path for path in repo.files if _is_test_file(PurePosixPath(path).name)]
    for path in test_files:
        test_module = repo.load(path)
        if test_module is None:
            continue
        for node, cls in repo.tests(test_module):
            closure = repo.close_test(test_module, node, cls)
            evidence = _evidence(closure, artifact)
            if evidence is None:
                continue
            node_id = f"{path}::{cls.name}::{node.name}" if cls is not None else f"{path}::{node.name}"
            expectation, skipped, markers = repo.expectation(test_module, repo.marks(test_module, node, cls))
            if skipped:
                excluded.append(
                    Excluded(node_id, path, node.lineno, f"skipped unconditionally ({', '.join(markers)}): it never runs")
                )
                continue
            json_refs.extend(closure.json_literals)
            provenance = Provenance(path, node.lineno, node.end_lineno or node.lineno, OracleKind.test)
            oracles.append(
                _oracle(
                    node_id,
                    provenance,
                    closure.components.values(),
                    closure.unresolved,
                    evidence,
                    baseline,
                    expectation,
                    markers,
                )
            )

    # schemas named by the signature
    roles: dict[tuple[str, str], list[str]] = {}
    located: dict[tuple[str, str], tuple[_Module, ast.ClassDef, str]] = {}
    for role, annotation in _annotations(fn, is_method):
        for class_module, cls in _annotation_classes(repo, module, annotation):
            kind = _schema_kind(repo, class_module, cls, frozenset())
            if kind is None:
                continue
            key = (class_module.path, cls.name)
            located.setdefault(key, (class_module, cls, kind))
            if role not in roles.setdefault(key, []):
                roles[key].append(role)
    for key, (class_module, cls, kind) in located.items():
        components: dict[tuple[str, str], Component] = {}
        _schema_components(repo, class_module, cls, components)
        provenance = Provenance(class_module.path, cls.lineno, cls.end_lineno or cls.lineno, OracleKind.schema)
        evidence = f"{kind} class named by the {' and '.join(roles[key])} annotation of {artifact.qualname}"
        oracles.append(_oracle(f"schema:{key[0]}::{key[1]}", provenance, components.values(), (), evidence, baseline))

    # JSON Schema files referenced by the artifact's module or a linked test
    for literal_node in ast.walk(module.tree):
        if (
            isinstance(literal_node, ast.Constant)
            and isinstance(literal_node.value, str)
            and literal_node.value.lower().endswith(".json")
        ):
            json_refs.append((literal_node.value, module.path, literal_node.lineno))
    seen_json: set[str] = set()
    for literal, referenced_from, line in sorted(set(json_refs), key=lambda ref: (ref[1], ref[2], ref[0])):
        relative = repo.inside(literal, referenced_from)
        if relative is None or relative in seen_json:
            continue
        seen_json.add(relative)
        try:
            data = (repo.root / relative).read_bytes()
            document = json.loads(data)
            text = data.decode("utf-8")
        except (OSError, ValueError) as error:
            repo.failures[relative] = f"referenced as JSON at {referenced_from}:{line} but unreadable ({type(error).__name__})"
            continue
        declared = document.get("$schema") if isinstance(document, dict) else None
        if not isinstance(document, dict) or not (
            (isinstance(declared, str) and "json-schema" in declared) or relative.endswith(".schema.json")
        ):
            continue
        normalised = text.replace("\r\n", "\n").replace("\r", "\n")
        provenance = Provenance(relative, 1, max(1, len(normalised.rstrip("\n").split("\n"))), OracleKind.schema)
        component = Component(relative, PurePosixPath(relative).name, 1, _text_hash(normalised))
        evidence = f"JSON Schema referenced at {referenced_from}:{line}"
        oracles.append(_oracle(f"schema:{relative}", provenance, [component], (), evidence, baseline))

    # type hints on the artifact's own signature
    text, annotated, total, has_return = _signature(module, fn, is_method)
    if annotated or has_return:
        end = max(fn.lineno, fn.body[0].lineno - 1)
        provenance = Provenance(artifact.path, fn.lineno, end, OracleKind.type_hints)
        component = Component(artifact.path, f"{artifact.qualname} (signature)", fn.lineno, _text_hash(text))
        returned = "the return annotated" if has_return else "no return annotation"
        evidence = f"{text}: {annotated} of {total} parameters annotated, {returned}"
        oracles.append(
            _oracle(f"type_hints:{artifact.artifact_id}", provenance, [component], (), evidence, baseline)
        )

    oracles.sort(key=lambda o: (_KIND_RANK[o.kind], o.provenance.path, o.provenance.line, o.oracle_id))
    unsearched = tuple(Unsearched(path, reason) for path, reason in sorted(repo.failures.items()))
    unparsed_tests = sum(1 for item in unsearched if _is_test_file(PurePosixPath(item.path).name))
    gaps: list[Gap] = []
    kinds = {oracle.kind for oracle in oracles}
    if OracleKind.test not in kinds:
        if not test_files:
            because = "the repository has no test_*.py or *_test.py file"
        else:
            because = (
                f"no test in the {len(test_files) - unparsed_tests} test file(s) searched references "
                f"{artifact.qualname} from {artifact.path}"
            )
        if excluded:
            because += f"; {len(excluded)} linked test(s) are skipped unconditionally and decide nothing"
        if unparsed_tests:
            because += f"; {unparsed_tests} test file(s) could not be parsed and were not searched"
        gaps.append(Gap(OracleKind.test, because))
    if OracleKind.schema not in kinds:
        gaps.append(
            Gap(
                OracleKind.schema,
                f"the signature of {artifact.qualname} names no dataclass, TypedDict or pydantic-shaped class in the "
                "repository, and no referenced .json file is a JSON Schema",
            )
        )
    if OracleKind.type_hints not in kinds:
        gaps.append(Gap(OracleKind.type_hints, f"the signature of {artifact.qualname} has no annotations"))
    return Harvest(
        artifact,
        tuple(oracles),
        tuple(gaps),
        tuple(sorted(excluded, key=lambda item: (item.path, item.line))),
        unsearched,
        len(test_files),
        None if baseline is None else baseline.run_id,
    )
