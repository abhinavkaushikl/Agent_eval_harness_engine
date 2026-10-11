"""The sandbox's result record, and how it maps onto EL-014's verdict vocabulary.

A :class:`SandboxResult` is the whole of what one sandboxed run produced: the
exact command, the working directory, the limits that were in force, the seed,
stdout/stderr, how the process ended, and the derived facts the sandbox alone
can know -- whether it was timed out, which cap was hit, and whether a network
egress was refused.

The outcome vocabulary is **not redefined here.** ``Verdict``, ``FailureClass``,
``TimeoutCap`` and ``Timeout`` are EL-014's, defined in
``evalloop/memory/case.py`` and persisted by the metric store. This module
imports them. Two look-alike enums would let the sandbox and the store disagree
with nothing to catch it (the ticket's own warning), so there is exactly one
definition and it lives with the store.

What the sandbox classifies, and what it leaves to the grader
-------------------------------------------------------------
:meth:`SandboxResult.classify` returns an :class:`Outcome` only for the things
a sandbox can determine on its own, from EL-014's table:

* wall-clock or CPU cap hit        -> ``failed`` / ``timeout`` (with the cap)
* killed at the file-size or open-files limit -> ``failed`` / ``runtime_error``
* network egress refused, or the sandbox could not start -> ``inconclusive``

For a process that simply **exited** -- cleanly or with an ordinary non-zero
code -- the sandbox returns ``Outcome(verdict=None)``: "it ran, you decide."
Whether exit 1 from pytest means a failed assertion (``wrong_result``) or an
import error (``syntax_error``) is the grader's reading of the test framework
(EL-207), not the sandbox's. The sandbox refuses to guess a pass/fail it cannot
see, which is the same honesty EL-014 asks of every rung.

Why a refused network call is ``inconclusive`` and not a failure
----------------------------------------------------------------
``ARCHITECTURE.md`` §9: "egress denied in the sandbox by default; network need
is a declared capability." A run that needed the network it was not granted was
not *run* as intended, so the evaluation -- not the artifact -- is what could
not decide. EL-014's table maps "a capability the run needs was denied
(network)" to ``inconclusive`` with that reason, precisely so a missing grant is
never charged to the artifact as a ``runtime_error``. The sandbox's job is to
make that case *detectable*; see ``sandbox.py`` for how, and its honest limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evalloop.memory.case import FailureClass, Timeout, TimeoutCap, Verdict

__all__ = ["Limits", "Outcome", "SandboxResult"]


@dataclass(frozen=True, slots=True)
class Limits:
    """The caps a run is held to. ``None`` means *not enforced*, reported as unset.

    ``wall_seconds`` is the one required cap: every run has a wall-clock bound, and
    its value is A1's ``timeout`` parameter (``A-choosing-how-to-grade.md`` §A1,
    "Use a 10-second timeout"), read from the record by the caller once EL-015's
    ``parameters`` field exists. It is **not** written as a literal here or in the
    caller's logic -- see the sandbox docstring's note on EL-015.

    The rest are the sandbox capability's own grant parameters (decision EL-015,
    "the sandbox's own safety limits ... are grant parameters ... null until
    granted; never defaulted; reported as unset when absent"). Until the M2
    capability broker supplies them they are ``None``, and the sandbox enforces
    only the ones that have a value. ``deny_network`` is the exception: egress is
    denied **by default** (``ARCHITECTURE.md`` §9), so it defaults to ``True``.
    """

    wall_seconds: float
    cpu_seconds: int | None = None
    memory_bytes: int | None = None
    file_size_bytes: int | None = None
    open_files: int | None = None
    deny_network: bool = True

    def __post_init__(self) -> None:
        if not (isinstance(self.wall_seconds, (int, float)) and not isinstance(self.wall_seconds, bool)):
            raise ValueError(f"wall_seconds must be a number of seconds, got {self.wall_seconds!r}")
        if not (self.wall_seconds > 0):
            raise ValueError(f"wall_seconds must be positive, got {self.wall_seconds!r}")
        for name in ("cpu_seconds", "memory_bytes", "file_size_bytes", "open_files"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive int or None, got {value!r}")
        if not isinstance(self.deny_network, bool):
            raise ValueError(f"deny_network must be a bool, got {self.deny_network!r}")

    def enforced(self) -> tuple[str, ...]:
        """The names of the caps that are actually applied, for the record and the report."""
        names = ["wall_seconds"]
        names += [n for n in ("cpu_seconds", "memory_bytes", "file_size_bytes", "open_files") if getattr(self, n) is not None]
        if self.deny_network:
            names.append("deny_network")
        return tuple(names)


@dataclass(frozen=True, slots=True)
class Outcome:
    """What the sandbox could conclude. ``verdict is None`` means "it exited; the grader decides"."""

    verdict: Verdict | None
    failure_class: FailureClass | None = None
    timeout: Timeout | None = None
    inconclusive_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Everything one sandboxed run produced. Frozen, so a stored run is exactly what happened."""

    command: tuple[str, ...]
    workdir: str
    limits: Limits
    seed: int
    stdout: str
    stderr: str
    exit_code: int | None
    term_signal: int | None
    duration_seconds: float
    timed_out: bool
    timeout_cap: TimeoutCap | None
    network_denied: bool
    network_containment: str
    enforced_limits: tuple[str, ...]
    unenforceable_limits: tuple[str, ...]
    start_error: str | None
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def classify(self) -> Outcome:
        """The EL-014 outcome for the cases the sandbox owns; ``verdict=None`` for an ordinary exit."""
        if self.start_error is not None:
            return Outcome(Verdict.inconclusive, inconclusive_reason=f"the sandbox could not run: {self.start_error}")
        if self.network_denied:
            return Outcome(
                Verdict.inconclusive,
                inconclusive_reason=(
                    "network egress was refused: this capability was not granted "
                    "(ARCHITECTURE.md §9). The run could not be evaluated, so it is "
                    "inconclusive rather than a failure of the artifact"
                ),
            )
        if self.timed_out:
            cap = self.timeout_cap or TimeoutCap.wall_clock
            limit = self.limits.wall_seconds if cap is TimeoutCap.wall_clock else self.limits.cpu_seconds
            assert limit is not None  # a cap cannot fire without a value
            return Outcome(Verdict.failed, FailureClass.timeout, Timeout(cap, float(limit)))
        if self.term_signal is not None and self._is_resource_kill():
            return Outcome(
                Verdict.failed,
                FailureClass.runtime_error,
                inconclusive_reason=None,
            )
        return Outcome(verdict=None)

    def _is_resource_kill(self) -> bool:
        """SIGXFSZ (file-size) is a resource kill the sandbox attributes; SIGXCPU is handled as a timeout."""
        import signal as _signal

        return self.term_signal == int(getattr(_signal, "SIGXFSZ", -1))

    @property
    def killing_cap(self) -> str | None:
        """Which cap stopped the run, for a report that must say *which*. ``None`` if none did."""
        if self.timed_out:
            return (self.timeout_cap or TimeoutCap.wall_clock).value
        if self.term_signal is not None and self._is_resource_kill():
            return "file_size_bytes"
        return None
