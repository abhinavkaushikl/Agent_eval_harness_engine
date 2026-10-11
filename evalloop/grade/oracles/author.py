"""Author a test for an artifact from its SIGNATURE ONLY, in isolation, tagged LOW.

``AGENT.md`` §3.6: "Author new (LOW confidence): tests generated from signature
only, in isolation from the implementation. These are tagged LOW so they are
never confused with ground truth."

Isolation is the whole ticket, and it is **structural**, not a polite request in
a prompt. The model never sees the body, because the request is assembled from a
:class:`SignatureView` -- a frozen record of the name, the signature, the
docstring and the module's imports, and *nothing else*. The body is never read
into any field the view carries, so it cannot reach the request whatever the
prompt says. ``tests/test_oracle_author.py`` proves it by putting a unique
sentinel in a function's body and asserting it never appears in the assembled
request. The reason is mechanical: a model that sees the implementation writes a
test that agrees with the bug, and the broken function passes
(``A1`` / ``E`` in the corpus). A test's only value is that it never saw the body.

What the author may see: the function name, its signature and type hints, its
docstring, and the module's top-level imports. Not the body. Not the file.

LOW, and nothing can make it HIGH
---------------------------------
:class:`AuthoredOracle` has **no settable confidence**: ``confidence`` is a
property that returns ``OracleConfidence.low``, and ``case_kind`` a property that
returns ``CaseKind.generated``. There is no field to override and no argument to
pass, so a generated oracle cannot be stored as ground truth or promoted to
permanent by a caller's slip (``ARCHITECTURE.md`` §9 treats that as a correctness
failure, not a labelling one). Promotion to permanent is the failures-as-tests
flywheel (``I-production.md`` §273), a later milestone.

A test is kept only if it has teeth
-----------------------------------
A generated test is validated in EL-206's sandbox before it is accepted, against
an **empty stub** -- the same signature with a body of ``raise
NotImplementedError``:

* if pytest cannot collect or import it, it **does not run** -> rejected;
* if it **passes** against the stub, it asserts nothing an empty function does
  not already satisfy -> rejected ("vacuous");
* if it **fails** against the stub, it tests real behaviour the stub lacks ->
  accepted.

The stronger claim -- that an accepted test catches a *wrong* implementation it
never saw -- is proved in the test suite, by running an authored test against a
deliberately broken body and watching it fail.

The egress boundary (option (b)), and why the suite is offline
--------------------------------------------------------------
This is LLM-facing, so it inherits EL-209's option (b): the client refuses to
send anything off the machine without a ``Clearance``, and **nothing in
EvalLoop issues one**. This module never constructs a ``Clearance``; it takes one
from its caller and passes it through. In M1 there is no issuer, so every test
here runs against a fake in-process transport and touches no network.

Determinism and cost
--------------------
The Anthropic API has no seed (EL-209: ``LLMResponse.seed`` is always ``None``),
so two real generations of the same signature can differ. Rather than hide that,
each attempt records the exact request sent, the model that served it, the jitter
seed and the cost, so a run is reproducible as far as the API allows and its
variance can be measured by repetition (``ARCHITECTURE.md`` §9: "otherwise repeat
and report variance, never a single number"). Against the fake transport the
output is fixed, so the suite is deterministic. Cost is charged to EL-209's
session ledger and recorded per attempt.

Scope
-----
M1 authors for **top-level functions** only; a method or a missing symbol is
refused with a reason. Authoring from a natural-language intent needs M2's
transcript reader and is out of scope.
"""

from __future__ import annotations

import ast
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from evalloop.capability.llm import Clearance, LLMRequest, Message
from evalloop.capability.router import Job, Router
from evalloop.grade.oracles.harvest import Artifact
from evalloop.grade.sandbox import run_sandboxed
from evalloop.grade.verdict import Limits
from evalloop.memory.case import CaseKind, OracleConfidence

__all__ = [
    "AuthorError",
    "AuthoredOracle",
    "AuthoringOutcome",
    "Attempt",
    "SignatureView",
    "WHY_LOW",
    "author_test",
    "signature_view",
]

#: The confidence reasoning stored on every authored oracle: why LOW, and what would make it HIGH.
WHY_LOW = (
    "LOW: generated from the signature, name, type hints and docstring alone, in isolation from the "
    "implementation (AGENT.md 3.6). It encodes the author's expectation of the contract, not verified "
    "behaviour, so it is never ground truth. It would be HIGH only if a human wrote or reviewed it."
)

_TEST_FILENAME = "test_authored.py"
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class AuthorError(Exception):
    """The author was called wrongly -- a method, a missing symbol, an unreadable file.

    A model that produces a bad test is not this: that is a *rejection*, recorded on the
    :class:`AuthoringOutcome`. This is only a caller's mistake.
    """


# -- what the author may see --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SignatureView:
    """Everything the author may see, and nothing else. The body is not a field here.

    Built by :func:`signature_view`, which extracts only these parts with ``ast`` and never reads
    the function's statements (other than the docstring, which is the contract). ``import_module``
    is the name the generated test imports the function by.
    """

    qualname: str
    signature: str
    docstring: str | None
    imports: tuple[str, ...]
    import_module: str

    @property
    def name(self) -> str:
        return self.qualname

    def stub_source(self) -> str:
        """A module with the same signature and an unimplemented body: the vacuity check runs on this."""
        doc = f'    """{self.docstring}"""\n' if self.docstring else ""
        return f"from __future__ import annotations\n\n\ndef {self.qualname}{self.signature}:\n{doc}    raise NotImplementedError\n"


def _text_of(source: str, node: ast.expr) -> str:
    segment = ast.get_source_segment(source, node)
    return " ".join(segment.split()) if segment else "object"


def _signature_text(source: str, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The signature as text, built from each annotation's own source -- never the body."""
    args = fn.args
    rendered: list[str] = []

    def show(arg: ast.arg, prefix: str = "") -> None:
        if arg.annotation is None:
            rendered.append(f"{prefix}{arg.arg}")
        else:
            rendered.append(f"{prefix}{arg.arg}: {_text_of(source, arg.annotation)}")

    positional = [*args.posonlyargs, *args.args]
    defaults_start = len(positional) - len(args.defaults)
    for index, arg in enumerate(positional):
        show(arg)
        if index >= defaults_start:
            rendered[-1] += f" = {_text_of(source, args.defaults[index - defaults_start])}"
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            rendered.append("/")
    if args.vararg is not None:
        show(args.vararg, "*")
    elif args.kwonlyargs:
        rendered.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        show(arg)
        if default is not None:
            rendered[-1] += f" = {_text_of(source, default)}"
    if args.kwarg is not None:
        show(args.kwarg, "**")
    returns = f" -> {_text_of(source, fn.returns)}" if fn.returns is not None else ""
    return f"({', '.join(rendered)}){returns}"


def _imports(tree: ast.Module, source: str) -> tuple[str, ...]:
    """The module's top-level import statements, verbatim. Not other code, never the artifact's body."""
    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                lines.append(" ".join(segment.split()))
    return tuple(lines)


def signature_view(artifact: Artifact, *, root: str | os.PathLike[str]) -> SignatureView:
    """Build the signature-only view of ``artifact``. Reads the file but never its function body."""
    posix = PurePosixPath(artifact.path)
    if posix.is_absolute() or ".." in posix.parts or posix.as_posix() != artifact.path:
        raise AuthorError(f"{artifact.path!r} must be a normalised path relative to the repository root")
    if "." in artifact.qualname:
        raise AuthorError(
            f"{artifact.artifact_id} is a method; M1 authors for top-level functions only "
            "(a method needs its class constructed, which signature-only authoring cannot do)"
        )
    file = Path(root) / artifact.path
    try:
        source = file.read_text(encoding="utf-8")
    except OSError as error:
        raise AuthorError(f"{artifact.path}: could not be read ({error.strerror or error})") from error
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(source, filename=artifact.path)
    except (SyntaxError, ValueError) as error:
        raise AuthorError(f"{artifact.path}: does not parse ({error})") from error
    matches = [node for node in tree.body if isinstance(node, _FUNCTIONS) and node.name == artifact.qualname]
    if not matches:
        raise AuthorError(f"{artifact.artifact_id} is not a top-level function in {artifact.path}")
    fn = matches[-1]
    return SignatureView(
        qualname=artifact.qualname,
        signature=_signature_text(source, fn),
        docstring=ast.get_docstring(fn),
        imports=_imports(tree, source),
        import_module=posix.stem,
    )


# -- the prompt, assembled only from the view ---------------------------------------

_SYSTEM = (
    "You write a single pytest test module for a Python function you can see only the signature of. "
    "You have NOT seen its body, and you must not guess at bugs in it. Test the behaviour the "
    "signature, type hints and docstring promise. Import the function exactly as instructed. "
    "Return only the Python source of the test module, with no prose."
)


def render_messages(view: SignatureView) -> tuple[str, tuple[Message, ...]]:
    """The (system, messages) sent to the model -- a pure function of the view, so the body cannot leak."""
    parts = [
        f"Write a pytest test module for the function `{view.qualname}`.",
        f"Import it with: from {view.import_module} import {view.qualname}",
        "",
        "Its signature is:",
        f"    def {view.qualname}{view.signature}: ...",
    ]
    if view.docstring:
        parts += ["", "Its docstring is:", *(f"    {line}" for line in view.docstring.splitlines())]
    if view.imports:
        parts += ["", "The module these names come from imports:", *(f"    {line}" for line in view.imports)]
    parts += [
        "",
        "Write at least one test that would FAIL if the function were an empty stub, so the test "
        "actually asserts behaviour. Return only the test module source.",
    ]
    return _SYSTEM, (Message("user", "\n".join(parts)),)


def _extract_code(text: str) -> str:
    """The Python source from a model reply: the first fenced block if present, else the whole reply."""
    fence = "```"
    if fence in text:
        after = text.split(fence, 1)[1]
        after = after[after.index("\n") + 1 :] if "\n" in after.split(fence, 1)[0] else after
        body = after.split(fence, 1)[0]
        return body.strip() + "\n"
    return text.strip() + "\n"


# -- the result types ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Attempt:
    """One generation and its verdict: what was sent, what came back, and why it was kept or not."""

    request: LLMRequest
    served_model: str
    jitter_seed: int
    cost_usd: str
    test_code: str
    accepted: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AuthoredOracle:
    """A generated test. Always LOW, always a ``generated`` case -- neither can be overridden."""

    artifact: Artifact
    test_filename: str
    import_module: str
    test_code: str
    confidence_reasoning: str
    served_model: str
    jitter_seed: int
    cost_usd: str

    @property
    def confidence(self) -> OracleConfidence:
        """LOW, with no way to set it otherwise (AGENT.md 3.6)."""
        return OracleConfidence.low

    @property
    def case_kind(self) -> CaseKind:
        """``generated``: never permanent -- promotion is the flywheel, a later milestone."""
        return CaseKind.generated

    @property
    def oracle_id(self) -> str:
        return f"authored:{self.artifact.artifact_id}::{self.test_filename}"


@dataclass(frozen=True, slots=True)
class AuthoringOutcome:
    """The author's answer: an oracle if one earned acceptance, with every attempt and the total cost."""

    artifact: Artifact
    oracle: AuthoredOracle | None
    attempts: tuple[Attempt, ...]
    total_cost_usd: str

    @property
    def reason(self) -> str | None:
        """Why there is no oracle, kept honest the way the harvester keeps 'no oracle available'."""
        if self.oracle is not None:
            return None
        if not self.attempts:
            return f"no test authored for {self.artifact.artifact_id}: no generation was attempted"
        details = "; ".join(f"attempt {i + 1}: {a.detail}" for i, a in enumerate(self.attempts))
        return (
            f"no usable test authored for {self.artifact.artifact_id} in {len(self.attempts)} attempt(s): "
            f"{details}. A generated test is kept only if it runs and fails against an empty stub"
        )


# -- validation in the sandbox ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Check:
    accepted: bool
    detail: str


def _validate_against_stub(view: SignatureView, test_code: str, limits: Limits, workdir_root: str | None) -> _Check:
    """Run the test against an unimplemented stub in the sandbox: keep it only if it fails there."""
    try:
        ast.parse(test_code)
    except SyntaxError as error:
        return _Check(False, f"does not run: the generated test is not valid Python ({error.msg})")
    files = {f"{view.import_module}.py": view.stub_source(), _TEST_FILENAME: test_code}
    result = run_sandboxed(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", _TEST_FILENAME],
        limits=limits,
        workdir_root=workdir_root,
        input_files=files,
    )
    outcome = result.classify()
    if outcome.verdict is not None and outcome.verdict.value == "inconclusive":
        return _Check(False, f"does not run: {outcome.inconclusive_reason}")
    if result.timed_out:
        return _Check(False, "does not run: the test timed out against the stub")
    code = result.exit_code
    if code == 1:
        return _Check(True, "fails against the empty stub, so it asserts real behaviour")
    if code == 0:
        return _Check(False, "passes against an empty stub, so it asserts nothing (vacuous)")
    if code == 5:
        return _Check(False, "does not run: pytest collected no tests")
    return _Check(False, f"does not run: pytest exited {code} (not a clean pass/fail)")


# -- the author ---------------------------------------------------------------------


def author_test(
    artifact: Artifact,
    *,
    root: str | os.PathLike[str],
    router: Router,
    clearance: Clearance | None,
    sandbox_limits: Limits,
    max_output_tokens: int,
    max_attempts: int = 1,
    workdir_root: str | os.PathLike[str] | None = None,
) -> AuthoringOutcome:
    """Author a LOW test for ``artifact`` from its signature alone, validated in the sandbox.

    The request is built only from :func:`signature_view`, so the body cannot reach the model.
    ``router`` routes the ``author`` job (EL-209); ``clearance`` is passed through, never created
    here. ``sandbox_limits`` bounds the validation run (EL-206); its ``wall_seconds`` is the
    caller's -- from the record's ``parameters`` once EL-015 lands. Returns an oracle only if a
    generation runs and fails against an empty stub.
    """
    if max_attempts < 1:
        raise AuthorError("max_attempts must be at least 1")
    if max_output_tokens < 1:
        raise AuthorError("max_output_tokens must be at least 1")
    view = signature_view(artifact, root=root)
    system, messages = render_messages(view)

    attempts: list[Attempt] = []
    accepted: AuthoredOracle | None = None
    root_str = os.fspath(workdir_root) if workdir_root is not None else None
    for _ in range(max_attempts):
        routed = router.complete(
            Job.author,
            messages=messages,
            system=system,
            max_tokens=max_output_tokens,
            generator_family=None,
            clearance=clearance,
        )
        code = _extract_code(routed.response.text)
        check = _validate_against_stub(view, code, sandbox_limits, root_str)
        attempts.append(
            Attempt(
                request=routed.response.request,
                served_model=routed.response.served_model,
                jitter_seed=routed.response.jitter_seed,
                cost_usd=str(routed.cost_usd),
                test_code=code,
                accepted=check.accepted,
                detail=check.detail,
            )
        )
        if check.accepted:
            accepted = AuthoredOracle(
                artifact=artifact,
                test_filename=_TEST_FILENAME,
                import_module=view.import_module,
                test_code=code,
                confidence_reasoning=WHY_LOW,
                served_model=routed.response.served_model,
                jitter_seed=routed.response.jitter_seed,
                cost_usd=str(routed.cost_usd),
            )
            break
    total = str(router.ledger.spent_usd)
    return AuthoringOutcome(artifact=artifact, oracle=accepted, attempts=tuple(attempts), total_cost_usd=total)
