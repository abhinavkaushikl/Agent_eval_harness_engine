"""The sandbox: proofs, not assumptions, that untrusted code is actually contained.

Each guarantee the ticket names is exercised against a real child process, on
this machine, rather than asserted in prose. The confinement checks are the
ordinary way to test a sandbox: ask a child to do the thing that must be stopped,
and prove it was stopped.

Some proofs are platform-specific and say so: Seatbelt network and file-write
confinement are macOS-only, and ``resource.setrlimit`` enforces different caps on
macOS and Linux (see the module docstring's table). Those tests skip where the
mechanism does not apply rather than claim a guarantee the platform does not give.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from evalloop.grade import sandbox
from evalloop.grade.sandbox import SandboxError, run_sandboxed
from evalloop.grade.verdict import Limits, Outcome, SandboxResult
from evalloop.memory.case import FailureClass, Timeout, TimeoutCap, Verdict

_PY = sys.executable
_MACOS = sys.platform == "darwin"
_LINUX = sys.platform.startswith("linux")


def _run(code: str, limits: Limits, root: Path, **kw: object) -> SandboxResult:
    return run_sandboxed([_PY, "-c", code], limits=limits, workdir_root=str(root), **kw)  # type: ignore[arg-type]


# -- EL-014's outcome for a timeout (the done-when) --------------------------------


def test_an_infinite_loop_is_killed_at_the_wall_clock_cap(tmp_path: Path) -> None:
    result = _run("import time\nwhile True: time.sleep(0.05)", Limits(wall_seconds=1.0), tmp_path)
    assert result.timed_out and result.timeout_cap is TimeoutCap.wall_clock
    assert result.duration_seconds < 10.0  # it did not run to some larger bound
    outcome = result.classify()
    assert outcome == Outcome(Verdict.failed, FailureClass.timeout, Timeout(TimeoutCap.wall_clock, 1.0))
    assert result.killing_cap == "wall_clock"


def test_a_cpu_bomb_is_killed_at_the_cpu_cap_and_is_a_timeout(tmp_path: Path) -> None:
    # Wall cap is generous so the CPU cap, not the clock, is what fires.
    result = _run("while True: pass", Limits(wall_seconds=30.0, cpu_seconds=1), tmp_path)
    assert result.timed_out and result.timeout_cap is TimeoutCap.cpu_time
    assert result.term_signal == int(signal.SIGXCPU)
    outcome = result.classify()
    assert outcome.verdict is Verdict.failed and outcome.failure_class is FailureClass.timeout
    assert outcome.timeout == Timeout(TimeoutCap.cpu_time, 1.0)


def test_a_clean_or_failing_exit_is_left_for_the_grader(tmp_path: Path) -> None:
    ok = _run("print('done')", Limits(wall_seconds=10.0), tmp_path)
    assert ok.exit_code == 0 and ok.term_signal is None and ok.classify().verdict is None
    assert ok.stdout == "done\n"
    bad = _run("import sys; sys.exit(3)", Limits(wall_seconds=10.0), tmp_path)
    assert bad.exit_code == 3 and bad.classify().verdict is None  # the grader reads the test framework


# -- nothing escapes the tempdir (the done-when) -----------------------------------


@pytest.mark.skipif(not _MACOS, reason="file-write confinement is Seatbelt, macOS only")
def test_a_write_outside_the_workdir_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "must_not_be_written.txt"
    result = _run(f"open({str(target)!r}, 'w').write('x'); print('WROTE')", Limits(wall_seconds=10.0), tmp_path)
    assert "WROTE" not in result.stdout
    assert result.exit_code not in (0, None)  # the write raised in the child
    assert not target.exists(), "the sandbox let a child write outside its working directory"


def test_a_write_inside_the_workdir_is_allowed(tmp_path: Path) -> None:
    result = _run(
        "import os; p = os.path.join(os.environ['TMPDIR'], 'inside.txt')\n"
        "open(p, 'w').write('ok'); print('WROTE', os.path.exists(p))",
        Limits(wall_seconds=10.0),
        tmp_path,
    )
    assert result.exit_code == 0 and "WROTE True" in result.stdout


# -- a network call fails closed, distinguishably from a logic failure -------------


@pytest.mark.skipif(not _MACOS, reason="network containment is Seatbelt, macOS only")
@pytest.mark.parametrize(
    "code",
    [
        "import socket; socket.create_connection(('1.1.1.1', 80), timeout=5)",
        "import socket; socket.create_connection(('127.0.0.1', 9), timeout=5)",
        "import socket; socket.getaddrinfo('example.com', 80)",
    ],
    ids=["connect-external", "connect-local", "dns"],
)
def test_a_network_call_fails_closed_and_is_inconclusive(tmp_path: Path, code: str) -> None:
    result = _run(code, Limits(wall_seconds=10.0), tmp_path)
    assert result.network_denied and not result.timed_out
    outcome = result.classify()
    assert outcome.verdict is Verdict.inconclusive
    assert "network egress was refused" in (outcome.inconclusive_reason or "")


def test_a_logic_failure_is_not_mistaken_for_a_denied_network(tmp_path: Path) -> None:
    """The liar's error: scoring 'no internet' as a wrong answer. A logic failure must look different."""
    result = _run("assert 1 == 2, 'wrong'", Limits(wall_seconds=10.0), tmp_path)
    assert not result.network_denied and not result.timed_out
    assert result.exit_code == 1 and result.classify().verdict is None  # grader's call, not inconclusive


@pytest.mark.skipif(not _MACOS, reason="Seatbelt only")
def test_network_is_only_denied_when_asked(tmp_path: Path) -> None:
    code = (
        "import socket\n"
        "try: socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
        "except OSError: pass\n"
        "print('ran')"
    )
    result = _run(code, Limits(wall_seconds=8.0, deny_network=False), tmp_path)
    assert not result.network_denied and result.exit_code == 0 and "ran" in result.stdout


def test_fails_closed_when_the_platform_cannot_contain_the_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force an environment with no containment mechanism, network denial still requested.
    monkeypatch.setattr(sandbox, "_IS_MACOS", False)
    monkeypatch.setattr(sandbox, "_IS_LINUX", False)
    result = _run("print('should not run')", Limits(wall_seconds=10.0, deny_network=True), tmp_path)
    assert result.start_error is not None and "cannot be contained" in result.start_error
    assert "should not run" not in result.stdout
    assert result.classify().verdict is Verdict.inconclusive
    assert result.network_containment == "unavailable"


# -- no credential reaches the child -----------------------------------------------


def test_the_child_environment_holds_no_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-leak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "also-secret")
    monkeypatch.setenv("LC_CTYPE", "parent-locale-xyz")  # a non-secret var, to prove nothing is copied
    result = _run("import os, json; print(json.dumps(dict(os.environ)))", Limits(wall_seconds=10.0), tmp_path)
    child_env = json.loads(result.stdout)
    assert "sk-should-never-leak" not in result.stdout
    assert "ANTHROPIC_API_KEY" not in child_env and "AWS_SECRET_ACCESS_KEY" not in child_env
    assert child_env.get("LC_CTYPE") != "parent-locale-xyz"  # the parent's value was not copied in
    # Built from scratch: exactly the fixed set the sandbox sets, plus two the macOS wrapper injects
    # itself (sandbox-exec/CoreFoundation adds __CF_USER_TEXT_ENCODING and a fixed C.UTF-8 LC_CTYPE --
    # locale hints, not copied from the parent, not credentials).
    set_by_us = {"PATH", "HOME", "TMPDIR", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING", "PYTHONUTF8"}
    os_injected = {"__CF_USER_TEXT_ENCODING", "LC_CTYPE"}
    assert set(child_env) <= set_by_us | os_injected, f"unexpected vars: {set(child_env) - set_by_us - os_injected}"


def test_the_seed_is_fixed_in_the_child_and_recorded(tmp_path: Path) -> None:
    result = _run("import os; print(os.environ['PYTHONHASHSEED'])", Limits(wall_seconds=10.0), tmp_path, seed=7)
    assert result.seed == 7 and result.stdout.strip() == "7"


# -- no orphan survives a timeout --------------------------------------------------


def test_a_grandchild_does_not_survive_the_group_kill(tmp_path: Path) -> None:
    """A child that spawns another process, then hangs: the whole group must die on timeout."""
    code = (
        "import subprocess, sys, time\n"
        f"g = subprocess.Popen([{_PY!r}, '-c', 'import time; time.sleep(60)'])\n"
        "print(g.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    result = _run(code, Limits(wall_seconds=1.0), tmp_path)
    assert result.timed_out
    grandchild = int(result.stdout.strip())
    try:
        alive = True
        for _ in range(40):  # the reparent-and-reap after SIGKILL is not instant
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                alive = False
                break
            time.sleep(0.1)
        assert not alive, f"grandchild {grandchild} outlived the timeout: the process group was not reaped"
    finally:
        try:
            os.kill(grandchild, signal.SIGKILL)
        except ProcessLookupError:
            pass


# -- determinism -------------------------------------------------------------------


def test_the_same_command_twice_gives_the_same_result_bar_duration(tmp_path: Path) -> None:
    code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(2)"
    first = _run(code, Limits(wall_seconds=10.0), tmp_path)
    second = _run(code, Limits(wall_seconds=10.0), tmp_path)
    assert (first.stdout, first.stderr, first.exit_code, first.term_signal) == (
        second.stdout,
        second.stderr,
        second.exit_code,
        second.term_signal,
    )
    assert first.classify() == second.classify()


# -- the limits are inspectable (a report can say which cap, and what was enforced) -


def test_the_result_records_the_command_limits_and_what_was_enforced(tmp_path: Path) -> None:
    limits = Limits(wall_seconds=5.0, cpu_seconds=3, open_files=64)
    result = _run("print('hi')", limits, tmp_path)
    assert result.command == (_PY, "-c", "print('hi')")
    assert result.limits is limits
    assert "wall_seconds" in result.enforced_limits
    assert "cpu_seconds" in result.enforced_limits and "open_files" in result.enforced_limits
    assert result.killing_cap is None  # nothing killed a clean run


@pytest.mark.skipif(not _MACOS, reason="address space is unenforceable specifically on macOS")
def test_on_macos_a_memory_limit_is_reported_as_unenforceable(tmp_path: Path) -> None:
    result = _run("print('x')", Limits(wall_seconds=10.0, memory_bytes=256 * 1024 * 1024), tmp_path)
    assert "memory_bytes" in result.unenforceable_limits
    assert "memory_bytes" not in result.enforced_limits


@pytest.mark.skipif(not _LINUX, reason="address space is enforced on Linux")
def test_on_linux_a_memory_limit_is_enforced(tmp_path: Path) -> None:
    result = _run(
        "b = bytearray(2 * 1024**3)\nfor i in range(0, len(b), 4096): b[i] = 1\nprint('ALLOCATED')",
        Limits(wall_seconds=20.0, memory_bytes=128 * 1024 * 1024),
        tmp_path,
    )
    assert "memory_bytes" in result.enforced_limits
    assert "ALLOCATED" not in result.stdout  # the allocation was refused


def test_the_open_files_cap_bites(tmp_path: Path) -> None:
    code = "fs = [open('/dev/null') for _ in range(500)]; print('OPENED', len(fs))"
    result = _run(code, Limits(wall_seconds=10.0, open_files=32), tmp_path)
    assert "OPENED" not in result.stdout and result.exit_code not in (0, None)


# -- output capture ----------------------------------------------------------------


def test_output_is_captured_and_truncated_to_the_cap(tmp_path: Path) -> None:
    result = _run("print('A' * 100000)", Limits(wall_seconds=10.0), tmp_path, max_output_bytes=1000)
    assert result.stdout_truncated and len(result.stdout) <= 1000


# -- refusals for a caller's own mistakes ------------------------------------------


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: run_sandboxed([], limits=Limits(wall_seconds=1.0)), "command is empty"),
        (lambda: run_sandboxed([_PY], limits=Limits(wall_seconds=1.0), seed=-1), "seed"),
        (lambda: run_sandboxed([_PY], limits=Limits(wall_seconds=1.0), workdir_root="/no/such/dir"), "not a directory"),
    ],
)
def test_a_caller_mistake_raises_sandbox_error(call: object, match: str) -> None:
    assert callable(call)
    with pytest.raises(SandboxError, match=match):
        call()


def test_env_extra_cannot_override_the_seed(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="PYTHONHASHSEED"):
        run_sandboxed([_PY, "-c", "pass"], limits=Limits(wall_seconds=1.0), env_extra={"PYTHONHASHSEED": "9"})


# -- input files (how a grader places code under test into the sandbox) -------------


def test_input_files_are_written_into_the_workdir(tmp_path: Path) -> None:
    result = run_sandboxed(
        [_PY, "-c", "import mod; print(mod.value); open('pkg/out.txt')"],
        limits=Limits(wall_seconds=10.0),
        workdir_root=str(tmp_path),
        input_files={"mod.py": "value = 99\n", "pkg/out.txt": "present"},
    )
    assert result.exit_code == 0 and result.stdout.strip() == "99"


@pytest.mark.parametrize("bad", ["../escape.py", "/etc/evil", "a/../../b.py", ""])
def test_input_files_cannot_escape_the_workdir(tmp_path: Path, bad: str) -> None:
    with pytest.raises(SandboxError, match="workdir|relative"):
        run_sandboxed([_PY, "-c", "pass"], limits=Limits(wall_seconds=5.0), input_files={bad: "x"})


# -- verdict.py value types --------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"wall_seconds": 0}, "positive"),
        ({"wall_seconds": -1.0}, "positive"),
        ({"wall_seconds": True}, "number"),
        ({"wall_seconds": 1.0, "cpu_seconds": 0}, "cpu_seconds"),
        ({"wall_seconds": 1.0, "memory_bytes": -5}, "memory_bytes"),
        ({"wall_seconds": 1.0, "open_files": True}, "open_files"),
        ({"wall_seconds": 1.0, "deny_network": "yes"}, "deny_network"),
    ],
)
def test_limits_validation(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Limits(**kwargs)  # type: ignore[arg-type]


def test_limits_enforced_names() -> None:
    assert Limits(wall_seconds=10.0).enforced() == ("wall_seconds", "deny_network")
    full = Limits(wall_seconds=10.0, cpu_seconds=1, memory_bytes=1, file_size_bytes=1, open_files=1, deny_network=False)
    assert full.enforced() == ("wall_seconds", "cpu_seconds", "memory_bytes", "file_size_bytes", "open_files")


def test_classify_is_pure_from_the_recorded_fields() -> None:
    """``classify`` reads only the stored fields, so a stored run reclassifies identically."""
    base = dict(
        command=("x",),
        workdir="/tmp/x",
        limits=Limits(wall_seconds=10.0, cpu_seconds=5),
        seed=0,
        stdout="",
        stderr="",
        duration_seconds=0.0,
        network_containment="seatbelt",
        enforced_limits=("wall_seconds",),
        unenforceable_limits=(),
        start_error=None,
    )
    hung = SandboxResult(exit_code=None, term_signal=9, timed_out=True, timeout_cap=TimeoutCap.wall_clock, network_denied=False, **base)  # type: ignore[arg-type]
    assert hung.classify() == Outcome(Verdict.failed, FailureClass.timeout, Timeout(TimeoutCap.wall_clock, 10.0))
    denied = SandboxResult(exit_code=None, term_signal=9, timed_out=False, timeout_cap=None, network_denied=True, **base)  # type: ignore[arg-type]
    assert denied.classify().verdict is Verdict.inconclusive
    started_bad = {**base, "start_error": "boom"}
    failed_start = SandboxResult(exit_code=None, term_signal=None, timed_out=False, timeout_cap=None, network_denied=False, **started_bad)  # type: ignore[arg-type]
    assert failed_start.classify().verdict is Verdict.inconclusive and "boom" in (failed_start.classify().inconclusive_reason or "")
