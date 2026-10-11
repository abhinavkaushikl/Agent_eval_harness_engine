"""Run a command that an AI assistant wrote and the developer has not read, safely.

This is the single most security-relevant module in M1. It runs untrusted code
with four stdlib mechanisms and nothing heavier (``PLAN.md`` T11 scopes it to
"subprocess + rlimits + timeout + tempdir"):

1. ``subprocess`` in a **new session** (``start_new_session=True``), so the whole
   process group can be killed together -- no orphaned grandchildren;
2. ``resource.setrlimit`` for CPU time, file size, open files and core dumps,
   and address space **where the platform enforces it**;
3. a **wall-clock** cap enforced by the parent, which kills the group on expiry;
4. a fresh ``tempfile`` working directory, removed on the way out;

plus, on macOS, an Apple ``sandbox-exec`` (Seatbelt) profile that **denies
network egress** and confines **file writes** to the working directory.

Every corpus number stays out of this module
---------------------------------------------
The 10-second timeout is A1's ``timeout`` parameter (``A-choosing-how-to-grade.md``
§A1). Decision EL-015 puts it on the record, to be read from
``A1_execution_based.parameters``. **That field does not exist yet** -- EL-015 is
decided but unimplemented (no ``parameters`` on the schema or on A1). So this
module does not read it and does not invent it: every cap is a required argument
on :class:`~evalloop.grade.verdict.Limits`, passed in by the caller. The caller
reads the value from the record once EL-015 lands; until then a test supplies it
explicitly. There is no ``timeout=10`` anywhere here (``CLAUDE.md`` §3, "never
invent a number"). The non-timeout caps are the sandbox capability's own grant
parameters -- ``None`` until a grant supplies them (EL-015), and the sandbox
enforces only the ones that have a value.

EL-014: a timeout is a failure, a denied capability is inconclusive
-------------------------------------------------------------------
The outcome vocabulary is EL-014's, imported from ``evalloop/memory/case.py``
through ``verdict.py``; there is no second copy. A wall-clock or CPU timeout is
``failed`` / ``timeout`` with the cap recorded. A refused network egress is
``inconclusive`` -- the run needed a capability it was not granted, so the
evaluation, not the artifact, is what could not decide (``ARCHITECTURE.md`` §9).
:meth:`SandboxResult.classify` draws the line; see ``verdict.py``.

Platform enforcement, as actually verified on this machine
----------------------------------------------------------
Measured on **macOS 26.6, arm64, CPython 3.12** (this repo's platform). Linux
rows are from documented POSIX/Seatbelt-equivalent behaviour and are **not
verified here**; the module states that rather than claiming it.

====================  =====================================  ==============================
cap                   macOS (verified)                       Linux (documented, unverified)
====================  =====================================  ==============================
wall-clock            parent kills the group on expiry       same
CPU time              ``RLIMIT_CPU`` -> SIGXCPU               same
file size             ``RLIMIT_FSIZE`` -> SIGXFSZ / EFBIG     same
open files            ``RLIMIT_NOFILE`` -> EMFILE            same
core dumps            ``RLIMIT_CORE`` = 0                     same
**address space**     **not enforceable** -- RLIMIT_AS /     ``RLIMIT_AS`` enforced
                      DATA / RSS cannot be lowered below      (so set ``memory_bytes``
                      the current value; the hard limit is    on Linux; it is dropped
                      unlimited. Memory is bounded only by    with a note on macOS)
                      the wall-clock cap
network egress        Seatbelt ``(deny network*                **not contained by this
                      (with send-signal SIGKILL))`` -> the     module** -- needs a network
                      child is killed on any network op        namespace (``unshare``),
                      (connect, bind, DNS), verified           which is not attempted here
file writes           Seatbelt confines writes to the         **not confined** -- only
                      workdir; a write elsewhere -> EPERM      RLIMIT_FSIZE applies
====================  =====================================  ==============================

On a platform where network egress cannot be contained and ``deny_network`` is
set, the sandbox **fails closed**: it does not run, and returns a result whose
outcome is ``inconclusive`` ("cannot guarantee network containment"). It never
runs untrusted code with the network open while claiming it is denied.

What a subprocess sandbox CANNOT contain -- stated plainly
----------------------------------------------------------
This is a best-effort confinement, not a security boundary against a hostile
program. It runs the child **as the current user**, so:

* **It does not stop the child reading the developer's files.** Only *writes*
  are confined (and only on macOS). The child can read anything the user can,
  including files outside the workdir. A secret on disk is not protected. A
  secret in the parent's environment is, because the child's environment is
  built from scratch and never copied (see ``_build_env``).
* **Seatbelt is deprecated by Apple** and is not a guaranteed boundary. There is
  no VM or container isolation here (out of scope, ``PLAN.md`` T11).
* **Kernel or sandbox escapes, privilege escalation and hardware side channels**
  are out of reach of a subprocess.
* **Output volume before the wall-clock cap is only loosely bounded.** stdout is
  read into memory and truncated to ``max_output_bytes``, but a child can emit a
  lot within its wall-clock window; a pathological case is bounded by time, not
  by that cap.
* **On macOS, memory is not capped** (see the table), so a memory bomb is stopped
  only by the wall-clock timeout, not before it allocates.
* **Network attribution has one ambiguous case on macOS.** A network op kills
  the child with SIGKILL; the harness distinguishes that from its own wall-clock
  kill (it knows whether it sent one) and from the CPU/file-size signals. But an
  OS out-of-memory kill is *also* SIGKILL, and -- because macOS cannot cap memory
  here -- is indistinguishable from a network kill. Both are reported as a
  halted run (``inconclusive``), never as a wrong answer, so the ambiguity never
  charges the artifact; it only mislabels a rare OS-OOM as "network denied".
  (The unified sandbox-violation log is *not* used for this: macOS samples those
  reports, so a missing entry would be a false negative.)

Determinism
-----------
``PYTHONHASHSEED`` is pinned to ``seed`` and recorded, and the environment is a
fixed allowlist, so a deterministic command gives identical stdout, exit and
outcome across runs. ``duration_seconds`` is the recorded nondeterminism and is
never compared.
"""

from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath

from evalloop.memory.case import TimeoutCap
from evalloop.grade.verdict import Limits, SandboxResult

__all__ = ["SandboxError", "run_sandboxed"]

_IS_MACOS = sys.platform == "darwin"
_IS_LINUX = sys.platform.startswith("linux")
_SANDBOX_EXEC = "/usr/bin/sandbox-exec"

#: A harness safety cap on captured output, not a corpus number: it stops a
#: chatty child from exhausting the parent's memory. Override per call.
_DEFAULT_MAX_OUTPUT = 10 * 1024 * 1024

#: A fixed PATH for the child. The sandbox never reads the parent's PATH (or any
#: other parent variable), so the value is explicit here. The child's interpreter
#: is invoked by absolute path, so this is only for tools a test itself shells out
#: to; a caller needing more passes it through ``env_extra``.
_BASE_PATH = "/usr/bin:/bin"


class SandboxError(Exception):
    """A programming error in how the sandbox was *called* (bad command, missing workdir root).

    A failure of the *child* -- a timeout, a resource kill, a refused network call -- is never
    this: it is reported in the :class:`SandboxResult`. This is only for a caller's mistake.
    """


def _build_env(workdir: str, seed: int, extra: Mapping[str, str] | None) -> dict[str, str]:
    """The child's whole environment, built from scratch -- the parent's is never read.

    "Credentials in a grader: impossible by construction" (``ARCHITECTURE.md`` §9) is taken
    literally: this module reads no variable from the parent process at all, so no parent secret --
    an ``ANTHROPIC_*`` key or anything else -- can reach the child, whether or not anyone thought
    to exclude it. Encoding is pinned rather than inherited, which also keeps runs deterministic.
    ``HOME`` and ``TMPDIR`` are the throwaway workdir, so a child writing to either stays confined.
    """
    env: dict[str, str] = {
        "PATH": _BASE_PATH,
        "HOME": workdir,
        "TMPDIR": workdir,
        "PYTHONHASHSEED": str(seed),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if extra:
        for key, value in extra.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise SandboxError(f"env_extra must be str->str, got {key!r}: {value!r}")
            if key.startswith("PYTHONHASHSEED"):
                raise SandboxError("PYTHONHASHSEED is set from the seed, not env_extra")
            env[key] = value
    return env


def _memory_rlimit_applies() -> bool:
    """Address-space capping works on Linux and not on macOS (verified); see the module table."""
    return _IS_LINUX


def _plan_limits(limits: Limits) -> tuple[list[tuple[int, int]], list[str], list[str]]:
    """The ``(resource, value)`` pairs to apply, and the names enforced vs. requested-but-not."""
    pairs: list[tuple[int, int]] = []
    enforced: list[str] = ["wall_seconds"]
    unenforceable: list[str] = []
    if limits.cpu_seconds is not None:
        pairs.append((resource.RLIMIT_CPU, limits.cpu_seconds))
        enforced.append("cpu_seconds")
    if limits.file_size_bytes is not None:
        pairs.append((resource.RLIMIT_FSIZE, limits.file_size_bytes))
        enforced.append("file_size_bytes")
    if limits.open_files is not None:
        pairs.append((resource.RLIMIT_NOFILE, limits.open_files))
        enforced.append("open_files")
    if limits.memory_bytes is not None:
        if _memory_rlimit_applies():
            pairs.append((resource.RLIMIT_AS, limits.memory_bytes))
            enforced.append("memory_bytes")
        else:
            unenforceable.append("memory_bytes")
    return pairs, enforced, unenforceable


def _preexec(pairs: Sequence[tuple[int, int]]) -> Callable[[], None]:
    """Child-side: set every planned rlimit, plus a zero core-dump limit. Runs after fork, before exec."""

    def apply() -> None:
        for res, value in pairs:
            resource.setrlimit(res, (value, value))
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, OSError):
            pass

    return apply


def _seatbelt_profile(workdir: str, deny_network: bool) -> str:
    """A Seatbelt profile: default allow, writes confined to the workdir, network denied.

    ``file-read`` is deliberately left allowed -- denying it stops the interpreter from loading
    its own standard library. The module docstring states this limit: reads are not confined.
    """
    literal = workdir.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny file-write*)",
        f'(allow file-write* (subpath "{literal}") (literal "/dev/null") (literal "/dev/dtracehelper") (literal "/dev/tty"))',
    ]
    if deny_network:
        # send-signal SIGKILL: a network op kills the child at once, so a denied egress is
        # distinguishable from an ordinary non-zero test exit. The unified log is unreliable
        # for this (macOS samples violation reports), so the signal is the mechanism.
        lines.append("(deny network* (with send-signal SIGKILL))")
    return "\n".join(lines)


def _wrap_command(command: Sequence[str], workdir: str, deny_network: bool) -> tuple[list[str], str]:
    """Wrap the command for the platform. Returns the argv and the containment description."""
    if _IS_MACOS and Path(_SANDBOX_EXEC).exists():
        profile = _seatbelt_profile(workdir, deny_network)
        return [_SANDBOX_EXEC, "-p", profile, *command], "seatbelt"
    if not deny_network:
        return list(command), "none (network not denied by request)"
    # deny_network requested but no containment available on this platform.
    return list(command), "unavailable"


def _resolve_cwd(workdir: str, cwd_subdir: str | None) -> str:
    """The directory the command runs in: the workdir, or a subdirectory of it. Never outside it."""
    if cwd_subdir is None:
        return workdir
    root = Path(workdir).resolve()
    candidate = PurePosixPath(cwd_subdir)
    if not cwd_subdir or candidate.is_absolute() or ".." in candidate.parts:
        raise SandboxError(f"cwd_subdir {cwd_subdir!r} must be a relative path inside the workdir with no '..'")
    target = (root / Path(cwd_subdir)).resolve()
    if target != root and root not in target.parents:
        raise SandboxError(f"cwd_subdir {cwd_subdir!r} escapes the workdir")
    if not target.is_dir():
        raise SandboxError(f"cwd_subdir {cwd_subdir!r} is not a directory in the workdir (write it via input_files first)")
    return str(target)


def _write_input_files(workdir: str, input_files: Mapping[str, str] | None) -> None:
    """Write caller-supplied files into the workdir, each path confined to it."""
    if not input_files:
        return
    root = Path(workdir).resolve()
    for relative, content in input_files.items():
        if not isinstance(relative, str) or not isinstance(content, str):
            raise SandboxError(f"input_files must be str->str, got {relative!r}: {type(content).__name__}")
        candidate = PurePosixPath(relative)
        if not relative or candidate.is_absolute() or ".." in candidate.parts:
            raise SandboxError(f"input_files path {relative!r} must be relative to the workdir and hold no '..'")
        target = (root / Path(relative)).resolve()
        if target != root and root not in target.parents:
            raise SandboxError(f"input_files path {relative!r} escapes the workdir")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _decode(raw: bytes, cap: int) -> tuple[str, bool]:
    truncated = len(raw) > cap
    return raw[:cap].decode("utf-8", "replace"), truncated


def run_sandboxed(
    command: Sequence[str],
    *,
    limits: Limits,
    workdir_root: str | os.PathLike[str] | None = None,
    seed: int = 0,
    stdin: str = "",
    env_extra: Mapping[str, str] | None = None,
    input_files: Mapping[str, str] | None = None,
    cwd_subdir: str | None = None,
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT,
) -> SandboxResult:
    """Run ``command`` under the sandbox and return everything that happened.

    ``command`` is an argv (never a shell string). ``limits.wall_seconds`` is required; the other
    caps are enforced only where they have a value and the platform supports them. The working
    directory is a fresh tempdir under ``workdir_root`` (the system temp if ``None``), removed
    before this returns. ``input_files`` maps a workdir-relative path to its text content and is
    written into that directory before the command runs -- how a grader places the code under test
    and its oracle inside the sandbox. Nothing in ``command``, the environment or ``input_files``
    is trusted to be benign, but the paths must be inside the workdir.
    """
    argv = [str(part) for part in command]
    if not argv:
        raise SandboxError("command is empty")
    if workdir_root is not None and not Path(workdir_root).is_dir():
        raise SandboxError(f"workdir_root {workdir_root!r} is not a directory")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise SandboxError(f"seed must be a non-negative int, got {seed!r}")

    pairs, enforced, unenforceable = _plan_limits(limits)
    workdir = tempfile.mkdtemp(prefix="evalloop-sbx-", dir=os.fspath(workdir_root) if workdir_root else None)
    real_workdir = os.path.realpath(workdir)
    try:
        _write_input_files(real_workdir, input_files)
        run_cwd = _resolve_cwd(real_workdir, cwd_subdir)
    except SandboxError:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    wrapped, containment = _wrap_command(argv, real_workdir, limits.deny_network)

    # Fail closed: egress was asked to be denied and the platform cannot contain it.
    if limits.deny_network and containment == "unavailable":
        shutil.rmtree(workdir, ignore_errors=True)
        return SandboxResult(
            command=tuple(argv),
            workdir=real_workdir,
            limits=limits,
            seed=seed,
            stdout="",
            stderr="",
            exit_code=None,
            term_signal=None,
            duration_seconds=0.0,
            timed_out=False,
            timeout_cap=None,
            network_denied=False,
            network_containment=containment,
            enforced_limits=tuple(enforced),
            unenforceable_limits=tuple(unenforceable),
            start_error=(
                f"network egress cannot be contained on this platform ({sys.platform}) and "
                "deny_network is set; refusing to run untrusted code with the network open"
            ),
        )

    env = _build_env(real_workdir, seed, env_extra)
    started = time.monotonic()
    timed_out = False
    timeout_cap: TimeoutCap | None = None
    start_error: str | None = None
    out_raw = err_raw = b""
    exit_code: int | None = None
    term_signal: int | None = None
    pid: int | None = None

    try:
        process = subprocess.Popen(
            wrapped,
            cwd=run_cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=_preexec(pairs),
            close_fds=True,
        )
    except OSError as error:
        shutil.rmtree(workdir, ignore_errors=True)
        return SandboxResult(
            command=tuple(argv),
            workdir=real_workdir,
            limits=limits,
            seed=seed,
            stdout="",
            stderr="",
            exit_code=None,
            term_signal=None,
            duration_seconds=time.monotonic() - started,
            timed_out=False,
            timeout_cap=None,
            network_denied=False,
            network_containment=containment,
            enforced_limits=tuple(enforced),
            unenforceable_limits=tuple(unenforceable),
            start_error=f"could not start the child: {error.strerror or error}",
        )

    pid = process.pid
    try:
        try:
            out_raw, err_raw = process.communicate(input=stdin.encode("utf-8"), timeout=limits.wall_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            timeout_cap = TimeoutCap.wall_clock
            _kill_group(pid)
            out_raw, err_raw = process.communicate()
    finally:
        if process.poll() is None:  # never leave the group running
            _kill_group(pid)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                start_error = "the child could not be reaped"

    duration = time.monotonic() - started
    code = process.returncode
    if code is not None and code < 0:
        term_signal = -code
        # A CPU-cap kill is a timeout, not a generic signal (EL-014: either cap is a timeout).
        if not timed_out and term_signal == int(getattr(signal, "SIGXCPU", -1)):
            timed_out = True
            timeout_cap = TimeoutCap.cpu_time
    else:
        exit_code = code

    # A SIGKILL the harness did not send, under a network-denying Seatbelt profile, is a network
    # op the kernel killed (verified). The one ambiguous case -- an OS out-of-memory SIGKILL on
    # macOS, where memory is uncapped -- is documented; both halt the run rather than scoring it.
    network_denied = (
        limits.deny_network
        and containment == "seatbelt"
        and not timed_out
        and term_signal == int(signal.SIGKILL)
    )

    shutil.rmtree(workdir, ignore_errors=True)

    stdout, out_trunc = _decode(out_raw, max_output_bytes)
    stderr, err_trunc = _decode(err_raw, max_output_bytes)
    return SandboxResult(
        command=tuple(argv),
        workdir=real_workdir,
        limits=limits,
        seed=seed,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        term_signal=term_signal,
        duration_seconds=duration,
        timed_out=timed_out,
        timeout_cap=timeout_cap,
        network_denied=network_denied,
        network_containment=containment,
        enforced_limits=tuple(enforced),
        unenforceable_limits=tuple(unenforceable),
        start_error=start_error,
        stdout_truncated=out_trunc,
        stderr_truncated=err_trunc,
    )


def _kill_group(pid: int) -> None:
    """SIGKILL the child's whole process group, so no grandchild is orphaned. Idempotent."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
