"""The native calibration run: the repo's own test suite, once, outside the sandbox.

The sandbox carries an artifact and its top-level package, never the whole environment a test may
lean on: the repo's ``conftest.py`` fixtures, data beside the package, subprocesses, nested sandboxes.
A test that fails only for want of those is charged to the code unless something separates it from a
real bug. Re-grading against the committed code cannot: on a clean tree it *is* the committed code.
The one discriminating signal is the same test run in the repo's own environment. If it passes
there and fails in the sandbox, the sandbox is what failed.

This run is **opt-in** (``evalloop check --calibrate-native``) because it is unsandboxed: the repo's
tests run as plain ``pytest`` does, with the caller's environment, filesystem and network. It is used
only to *withhold* a verdict, never to issue one. A native pass turns a sandbox failure into
inconclusive and nothing else, so a native run can never make code look better than "not decided".

Results are read from pytest's own ``--junitxml`` report (stdlib ``xml.etree``), so nothing is
written into the repo.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = ["NativeRun", "run_native", "junit_key"]


@dataclass(frozen=True, slots=True)
class NativeRun:
    """Per-test outcomes of one native pytest run, keyed by :func:`junit_key`. ``note`` says how it went."""

    outcomes: dict[tuple[str, str], str]
    note: str

    def outcome_of(self, test_id: str) -> str | None:
        """``passed`` / ``failed`` / ``skipped`` for a repo test id (``tests/test_a.py::test_x[1]``), or None."""
        key = junit_key(test_id)
        return None if key is None else self.outcomes.get(key)


def junit_key(test_id: str) -> tuple[str, str] | None:
    """A pytest node id as JUnit names it: ``(classname, name)``.

    ``tests/test_a.py::TestK::test_m[1]`` is ``("tests.test_a.TestK", "test_m[1]")``.
    """
    parts = test_id.split("::")
    if len(parts) < 2 or not parts[0].endswith(".py"):
        return None
    module = ".".join(PurePosixPath(parts[0]).with_suffix("").parts)
    return ".".join([module, *parts[1:-1]]), parts[-1]


def run_native(root: Path, *, timeout_seconds: float) -> NativeRun:
    """Run ``pytest`` in ``root`` with this interpreter and read every test's outcome. Never raises."""
    with tempfile.TemporaryDirectory(prefix="evalloop-native-") as scratch:
        report = Path(scratch) / "junit.xml"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={report}"]
        try:
            subprocess.run(command, cwd=root, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired:
            return NativeRun({}, f"native pytest did not finish within {timeout_seconds:g}s, so nothing was calibrated")
        except OSError as exc:
            return NativeRun({}, f"native pytest could not start ({exc}), so nothing was calibrated")
        if not report.is_file():
            return NativeRun({}, "native pytest wrote no report (it could not collect), so nothing was calibrated")
        try:
            tree = ET.parse(report)
        except ET.ParseError as exc:
            return NativeRun({}, f"native pytest's report did not parse ({exc}), so nothing was calibrated")
    outcomes: dict[tuple[str, str], str] = {}
    for case in tree.iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "failed"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        outcomes[(case.get("classname", ""), case.get("name", ""))] = outcome
    passed = sum(1 for o in outcomes.values() if o == "passed")
    return NativeRun(outcomes, f"native pytest ran {len(outcomes)} test(s) in the repo's own environment, {passed} passed")
