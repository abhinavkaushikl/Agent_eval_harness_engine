"""Choosing the Python a project's tests run with, and installing what they need when allowed.

Unit tests drive :mod:`evalloop.grade.project_env` with a fake command runner, so nothing is
downloaded. One integration test builds a real virtual environment offline (pytest reached through a
``.pth`` file) and proves the driver runs a project's tests with the project's own ``.venv``, packages
included. The session tests cover the permission popup: ask once, install and re-run, remember.
"""

from __future__ import annotations

import json
import subprocess
import sys
import sysconfig
from collections.abc import Sequence
from pathlib import Path

import pytest

from evalloop.grade import project_env as pe
from evalloop.memory.case import CaseKind, CaseResult, OracleConfidence, Verdict
from evalloop.run import RunOutcome, RunResult, check
from evalloop.session.chat import Action, interpret
from evalloop.session.consent import Choice
from evalloop.session.orchestrator import Session


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


# -- what a project needs --------------------------------------------------------------------------


def test_declared_requirements_from_requirements_files(tmp_path: Path) -> None:
    root = _write(tmp_path, {
        "requirements.txt": "# web\nfastapi>=0.110  # the app\n-r requirements/base.txt\n-e .\n--index-url https://x\n./local_pkg\n\n",
        "requirements/base.txt": "SQLAlchemy==2.0.*\npsycopg[binary]; python_version >= '3.8'\n",
        "requirements-dev.txt": "pytest\n",
    })
    assert pe.declared_requirements(root) == [
        "fastapi>=0.110", "SQLAlchemy==2.0.*", "psycopg[binary]; python_version >= '3.8'", "pytest"]


def test_declared_requirements_from_pyproject(tmp_path: Path) -> None:
    root = _write(tmp_path, {"pyproject.toml": (
        '[project]\nname = "app"\ndependencies = [\n  "requests>=2",\n  \'rich\',\n]\n\n'
        '[project.optional-dependencies]\ntest = ["pytest-asyncio"]\n\n'
        '[tool.poetry.dependencies]\npython = "^3.10"\nflask = "^3"\n'
    )})
    assert pe.declared_requirements(root) == ["requests>=2", "rich", "pytest-asyncio", "flask"]


def test_imports_the_code_makes_but_does_not_declare_are_inferred(tmp_path: Path) -> None:
    root = _write(tmp_path, {
        "app.py": "import os, json\nfrom __future__ import annotations\nimport yaml\nfrom dotenv import load_dotenv\n"
                  "from fastapi import FastAPI\nimport helpers\nimport psycopg\nfrom google.cloud import storage\n",
        "helpers.py": "import numpy as np\n",
        ".venv/pyvenv.cfg": "", ".venv/lib/site.py": "import should_not_be_seen\n",
        "requirements.txt": "psycopg[binary]\n",
    })
    assert pe.third_party_imports(root) == ["dotenv", "fastapi", "google", "numpy", "psycopg", "yaml"]
    inferred = pe.inferred_requirements(root, pe.declared_requirements(root))
    # mapped names, declared ones not repeated, ambiguous namespaces skipped, FastAPI's TestClient needs httpx
    assert inferred == ["python-dotenv", "fastapi", "httpx", "numpy", "PyYAML"]
    assert pe.requirements(root)[0] == "pytest"


# -- the project's own environment ---------------------------------------------------------------


def _fake_runner(missing_in: dict[str, set[str]], calls: list[list[str]], *, failing: Sequence[str] = ()):  # type: ignore[no-untyped-def]
    def run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if argv[1:3] == ["-m", "venv"]:
            env = Path(argv[3])
            (env / "bin").mkdir(parents=True, exist_ok=True)
            (env / "bin" / "python").write_text("", encoding="utf-8")
            (env / "pyvenv.cfg").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "pip" in argv:
            wanted = argv[argv.index("-q") + 1:]
            ok = not any(w in failing for w in wanted)
            if ok:
                missing_in.setdefault(argv[0], set()).difference_update({w.split("[")[0].lower() for w in wanted})
            return subprocess.CompletedProcess(argv, 0 if ok else 1, "", "" if ok else "no matching distribution")
        if argv[1] == "-c":  # which modules are missing
            gone = missing_in.get(argv[0], set())
            return subprocess.CompletedProcess(argv, 0, "\n".join(m for m in argv[3:] if m.lower() in gone), "")
        raise AssertionError(argv)
    return run


def test_the_projects_own_venv_is_used_when_it_can_run_pytest(tmp_path: Path) -> None:
    root = _write(tmp_path / "proj", {".venv/pyvenv.cfg": "home = /usr\n", ".venv/bin/python": "", "app.py": "import tabulate\n"})
    calls: list[list[str]] = []
    chosen = pe.choose(root, allow_install=False, home=tmp_path / "home", runner=_fake_runner({}, calls))
    assert chosen.python == str(root / ".venv" / "bin" / "python") and "own environment (.venv)" in chosen.origin
    assert chosen.missing == () and not any("pip" in c for c in calls)  # nothing installed into it


def test_without_permission_the_missing_packages_are_named_not_installed(tmp_path: Path) -> None:
    root = _write(tmp_path / "proj", {"app.py": "import tabulate\nimport rich\n"})
    calls: list[list[str]] = []
    runner = _fake_runner({sys.executable: {"tabulate", "rich"}}, calls)
    chosen = pe.choose(root, allow_install=False, home=tmp_path / "home", runner=runner)
    assert chosen.python == sys.executable and chosen.missing == ("rich", "tabulate")
    assert not any("pip" in c or "venv" in c for c in calls)


def test_with_permission_an_owned_env_is_built_once_and_reused(tmp_path: Path) -> None:
    root = _write(tmp_path / "proj", {"app.py": "import tabulate\n", "requirements.txt": "tabulate\n"})
    home = tmp_path / "home"
    env_python = str(pe.owned_env_dir(root, home) / "bin" / "python")
    calls: list[list[str]] = []
    runner = _fake_runner({sys.executable: {"tabulate"}, env_python: {"tabulate", "pytest"}}, calls)
    chosen = pe.choose(root, allow_install=True, home=home, runner=runner)
    assert chosen.python == env_python and chosen.missing == () and chosen.origin == "EvalLoop's environment for this project"
    assert pe.owned_env_dir(root, home).parent == home / ".evalloop" / "envs"
    pip_calls = [c for c in calls if "pip" in c]
    assert len(pip_calls) == 1 and pip_calls[0][-2:] == ["pytest", "tabulate"]
    calls.clear()
    again = pe.choose(root, allow_install=False, home=home, runner=runner)  # already built: reused, no network
    assert again.python == env_python and not any("pip" in c for c in calls)
    assert not any(p.name == "app.py" for p in (pe.owned_env_dir(root, home)).rglob("*"))  # the project isn't copied


def test_one_bad_package_does_not_stop_the_rest(tmp_path: Path) -> None:
    root = _write(tmp_path / "proj", {"requirements.txt": "tabulate\nnot-a-real-pkg==9\nrich\n"})
    calls: list[list[str]] = []
    build = pe.ensure_env(root, pe.requirements(root), home=tmp_path / "home",
                          runner=_fake_runner({}, calls, failing=["not-a-real-pkg==9"]))
    assert build.failed == ("not-a-real-pkg==9",) and set(build.installed) == {"pytest", "tabulate", "rich"}
    marker = json.loads((pe.owned_env_dir(root, tmp_path / "home") / "evalloop-env.json").read_text())
    assert marker["failed"] == ["not-a-real-pkg==9"]
    assert "not-a-real-pkg" in build.log.read_text()


def test_changed_requirements_rebuild_the_env(tmp_path: Path) -> None:
    root = _write(tmp_path / "proj", {"requirements.txt": "tabulate\n"})
    home = tmp_path / "home"
    calls: list[list[str]] = []
    runner = _fake_runner({}, calls)
    pe.ensure_env(root, pe.requirements(root), home=home, runner=runner)
    assert not pe.needs_build(root, pe.requirements(root), home)
    (root / "requirements.txt").write_text("tabulate\nrich\n", encoding="utf-8")
    assert pe.needs_build(root, pe.requirements(root), home)


def test_a_real_project_venv_runs_the_tests_with_its_own_packages(tmp_path: Path) -> None:
    """Offline and real: a venv whose site-packages holds a package EvalLoop doesn't have, and pytest
    reached through a .pth file. The project's test imports that package and passes."""
    proj = tmp_path / "proj"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(proj / ".venv")], check=True, capture_output=True)
    venv_python = proj / ".venv" / "bin" / "python"
    site = subprocess.run([str(venv_python), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"],
                          check=True, capture_output=True, text=True).stdout.strip()
    Path(site, "evalloop_test_pytest.pth").write_text(sysconfig.get_paths()["purelib"] + "\n", encoding="utf-8")
    Path(site, "onlyinvenv.py").write_text("def double(x):\n    return 2 * x\n", encoding="utf-8")
    _write(proj, {
        "calc.py": "from onlyinvenv import double\n\ndef quad(x):\n    return double(double(x))\n",
        "tests/test_calc.py": "from calc import quad\n\ndef test_quad():\n    assert quad(3) == 12\n",
    })
    result = check(proj, store_dir=tmp_path / "store")
    assert result.outcome is RunOutcome.clean, [(c.verdict, c.inconclusive_reason) for c in result.cases]
    assert any("project's own environment (.venv)" in n for n in result.notes)
    assert result.missing_packages == ()


# -- the bot asks once, installs, re-runs, remembers ----------------------------------------------------


def _blocked_result(path: str, missing: tuple[str, ...], verdict: Verdict = Verdict.inconclusive) -> RunResult:
    case = CaseResult(
        run_id="r", record_id="A1_execution_based", case_id="app.py::tests/test_app.py::test_x",
        case_kind=CaseKind.permanent, artifact_id="app.py", oracle_id="tests/test_app.py",
        oracle_confidence=OracleConfidence.high, ladder_rung=1, verdict=verdict, failure_class=None, timeout=None,
        inconclusive_reason=("No module named 'fastapi'" if missing else "could not decide") if verdict is Verdict.inconclusive else None,
        score=None, evidence=None, artifact_hash="a" * 64, oracle_hash="b" * 64, reused_from=None, seed=0,
        cost_usd=None, duration_seconds=0.0,
    )
    return RunResult(run_id="r", summary_path=Path("s.md"), outcome=RunOutcome.undecided, cases=(case,),
                     graded_artifacts=(), skipped=(), permission_requests=(), situations=(),
                     notes=(f"needs packages: {', '.join(missing)}",) if missing else (), missing_packages=missing)


def test_the_bot_asks_once_then_installs_reruns_and_remembers(tmp_path: Path) -> None:
    calls: list[str] = []

    def evaluator(path: str, _store: str) -> RunResult:
        calls.append(path)
        return _blocked_result(path, () if session.installs.allowed(path) else ("fastapi",))

    session = Session(tmp_path, store_dir=tmp_path / ".store", evaluator=evaluator)
    session.tick()
    pending = json.loads(session.snapshot_json())["consent"]["pending"]
    install = [p for p in pending if p["tool"] == "install"]
    assert len(install) == 1 and install[0]["popup"]["title"] == "Install this project's packages?"
    assert "fastapi" in dict(install[0]["popup"]["rows"])["why"]

    result = session.decide(install[0]["key"], Choice.allow_remember)
    assert result.granted and result.remembered
    session.tick()  # nothing changed on disk, but the allowed install re-runs the checks
    assert len(calls) == 2 and session.installs.pending() == ()
    assert (tmp_path / ".evalloop" / "install.json").exists()

    later = Session(tmp_path, store_dir=tmp_path / ".store", evaluator=evaluator)
    assert later.installs.allowed(str(tmp_path))  # remembered: never asked again for this project
    approvals = json.loads(later.snapshot_json())["consent"]["approvals"]
    assert any(a["tool"] == "install" for a in approvals)
    assert later.revoke(f"install|{tmp_path}") and not later.installs.allowed(str(tmp_path))


def test_deny_is_respected_and_projects_without_tests_are_not_offered_installs(tmp_path: Path) -> None:
    session = Session(tmp_path, store_dir=tmp_path / ".store", evaluator=lambda p, s: _blocked_result(p, ("fastapi",)))
    session.tick()
    key = session.installs.pending()[0].key
    session.decide(key, Choice.deny)
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    session.tick()
    assert session.installs.pending() == ()  # not asked again this session

    def no_tests(path: str, _store: str) -> RunResult:
        result = _blocked_result(path, ("fastapi",))
        return RunResult(**{**result.__dict__, "cases": ()})

    other = tmp_path / "other"
    other.mkdir()
    quiet = Session(other, store_dir=tmp_path / ".store2", evaluator=no_tests)
    quiet.tick()
    assert quiet.installs.pending() == ()  # installing would still grade nothing


def test_install_everywhere_never_asks(tmp_path: Path) -> None:
    session = Session(tmp_path, store_dir=tmp_path / ".store", evaluator=lambda p, s: _blocked_result(p, ("fastapi",)),
                      install=True)
    session.tick()
    assert session.installs.pending() == () and session.installs.allowed(str(tmp_path))


@pytest.mark.parametrize("said", ["install packages", "install", "Install dependencies", "allow installs"])
def test_the_chat_can_allow_the_install(said: str) -> None:
    assert interpret(said).action is Action.install
