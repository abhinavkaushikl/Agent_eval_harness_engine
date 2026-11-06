"""The Python a project's tests run with, and the packages they need: found, or installed when allowed.

EvalLoop used to run every test with its own interpreter, so a project importing fastapi, sqlalchemy,
pandas… came back undecided: the test could not even import. :func:`choose` picks the interpreter:

1. **The project's own environment**, when it has one: ``.venv/``, ``venv/``, ``env/`` or ``.env/`` (a
   directory holding ``pyvenv.cfg``) whose Python can import pytest. Nothing is installed or changed
   in it.
2. **An environment EvalLoop owns** for the project, ``~/.evalloop/envs/<project>-<hash>/``, built with
   the standard library's ``venv`` and filled by ``pip``: pytest, everything the project declares
   (``requirements*.txt``, ``requirements/*.txt``, ``pyproject.toml``), and every third-party module
   its code imports that it does not declare (``import dotenv`` → ``python-dotenv``). If the one
   ``pip install`` fails, each package is installed on its own, so one bad pin never stops the
   run; whatever still fails is named. Built once, reused until the requirements change, and
   reused later without asking again, since it is already on disk.
3. **EvalLoop's own Python**, as before, when installing is not allowed. The missing packages are
   named, so the bot can ask.

Installing downloads code from PyPI and runs its build steps **outside** the sandbox, so it happens
only when allowed: ``--install`` (operator clearance, like ``--author``) or the bot's permission
popup. The project folder and the user's own Python are never written to. Test runs themselves still
happen inside the sandbox (writes confined, network denied); only the interpreter changes. Standard
library only (``venv``, ``subprocess``); ``pip`` is the environment's own.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Interpreter",
    "choose",
    "declared_requirements",
    "ensure_env",
    "inferred_requirements",
    "missing_modules",
    "needs_build",
    "owned_env_dir",
    "project_python",
    "requirements",
    "third_party_imports",
]

_VENV_DIRS = (".venv", "venv", "env", ".env")
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "site-packages", "dist-packages", "build", "dist"})
_REQUIREMENT_FILES = ("requirements.txt", "requirements-dev.txt", "requirements_dev.txt", "dev-requirements.txt",
                      "requirements-test.txt", "requirements_test.txt", "test-requirements.txt")
#: Where an import name and its PyPI distribution differ. Anything not here installs by its own name.
_DISTRIBUTION = {
    "yaml": "PyYAML", "sklearn": "scikit-learn", "cv2": "opencv-python", "PIL": "Pillow", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "dateutil": "python-dateutil", "jwt": "PyJWT", "attr": "attrs", "docx": "python-docx",
    "pptx": "python-pptx", "serial": "pyserial", "zmq": "pyzmq", "skimage": "scikit-image", "Bio": "biopython",
    "github": "PyGithub", "telegram": "python-telegram-bot", "socketio": "python-socketio", "multipart": "python-multipart",
    "jose": "python-jose", "psycopg2": "psycopg2-binary", "MySQLdb": "mysqlclient", "fitz": "PyMuPDF",
    "Crypto": "pycryptodome", "OpenSSL": "pyOpenSSL", "magic": "python-magic", "slugify": "python-slugify",
    "sentencepiece": "sentencepiece", "faiss": "faiss-cpu", "tensorflow": "tensorflow", "sqlalchemy": "SQLAlchemy",
}
#: Imports too ambiguous to guess a distribution for (several projects share the namespace).
_AMBIGUOUS = frozenset({"google", "azure", "win32api", "win32con", "pywintypes"})
#: Packages that need another to be testable: FastAPI's / Starlette's TestClient needs httpx.
_IMPLIED = {"fastapi": ("httpx",), "starlette": ("httpx",)}
_INSTALL_TIMEOUT = 900.0   # the one bulk install
_EACH_TIMEOUT = 300.0      # each package when the bulk install failed
_MARKER = "evalloop-env.json"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _norm(name: str) -> str:
    """A distribution name normalised the way pip compares them (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(line: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
    return _norm(match.group(1)) if match else ""


# -- finding the project's own environment -------------------------------------------------------


def _venv_python(directory: Path) -> Path | None:
    if not (directory / "pyvenv.cfg").is_file():
        return None
    for candidate in (directory / "bin" / "python", directory / "bin" / "python3", directory / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


def project_python(root: Path) -> Path | None:
    """The interpreter of the project's own virtual environment, if it has one."""
    for name in _VENV_DIRS:
        python = _venv_python(root / name)
        if python is not None:
            return python
    return None


def missing_modules(python: str | os.PathLike[str], modules: Iterable[str], *, runner: Runner = subprocess.run) -> list[str]:
    """Which of ``modules`` (top-level names) ``python`` cannot import. Asks the interpreter; imports nothing."""
    names = sorted(set(modules))
    if not names:
        return []
    code = "import importlib.util,sys\nprint('\\n'.join(m for m in sys.argv[1:] if importlib.util.find_spec(m) is None))"
    try:
        done = runner([os.fspath(python), "-c", code, *names], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return names
    if done.returncode != 0:
        return names
    return [line for line in done.stdout.splitlines() if line.strip()]


# -- what the project needs ------------------------------------------------------------------------


def _requirement_lines(path: Path, root: Path, seen: set[Path]) -> list[str]:
    resolved = path.resolve()
    if resolved in seen or not path.is_file():
        return []
    seen.add(resolved)
    out: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    for raw in text.splitlines():
        line = raw.split(" #")[0].strip()
        if not line or line.startswith("#"):
            continue
        include = re.match(r"^(?:-r|--requirement)\s*=?\s*(.+)$", line)
        if include:
            target = (path.parent / include.group(1).strip()).resolve()
            if root.resolve() in (target, *target.parents):
                out += _requirement_lines(target, root, seen)
            continue
        if line.startswith("-") or line.startswith((".", "/")) or line.startswith("file:"):
            continue  # pip options, editable or local installs: not packages to fetch
        out.append(line)
    return out


def _pyproject_requirements(path: Path) -> list[str]:
    """``[project] dependencies``, every ``[project.optional-dependencies]`` group, and Poetry's deps.

    A minimal reader for these arrays (``tomllib`` is newer than the 3.10 floor), so the trade-off is
    stated: inline tables and multi-line strings inside the arrays are not supported.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[str] = []
    section = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        header = re.match(r"^\[([^\]]+)\]$", line)
        if header:
            section = header.group(1).strip()
            i += 1
            continue
        array = re.match(r'^([A-Za-z0-9_."-]+)\s*=\s*\[(.*)$', line)
        if array and (section == "project" and array.group(1) == "dependencies"
                      or section == "project.optional-dependencies"):
            body = array.group(2)
            while "]" not in body and i + 1 < len(lines):
                i += 1
                body += " " + lines[i]
            quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', body.split("]")[0])
            out += [a or b for a, b in quoted]
        elif section in ("tool.poetry.dependencies", "tool.poetry.dev-dependencies") or (
                section.startswith("tool.poetry.group.") and section.endswith(".dependencies")):
            pair = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=", line)
            if pair and pair.group(1).lower() != "python":
                out.append(pair.group(1))
        i += 1
    return out


def declared_requirements(root: Path) -> list[str]:
    """What the project says it needs, as pip requirement strings, in file order."""
    seen: set[Path] = set()
    out: list[str] = []
    for name in _REQUIREMENT_FILES:
        out += _requirement_lines(root / name, root, seen)
    folder = root / "requirements"
    if folder.is_dir():
        for path in sorted(folder.glob("*.txt")):
            out += _requirement_lines(path, root, seen)
    out += _pyproject_requirements(root / "pyproject.toml")
    return out


def _python_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        if "pyvenv.cfg" in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS)
        found += [Path(directory) / f for f in sorted(filenames) if f.endswith(".py")]
    return found


def _imports(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def third_party_imports(root: Path) -> list[str]:
    """Top-level modules the project's code imports that are neither standard library nor its own."""
    files = _python_files(root)
    local = {p.stem for p in files} | {p.parent.name for p in files}
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    names: set[str] = set()
    for path in files:
        try:
            names |= _imports(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return sorted(n for n in names if n not in stdlib and n not in local and not n.startswith("_"))


def inferred_requirements(root: Path, declared: Sequence[str] = ()) -> list[str]:
    """Distributions for imports the project does not declare, plus what those imply (httpx for FastAPI)."""
    have = {_requirement_name(r) for r in declared}
    out: list[str] = []
    for module in third_party_imports(root):
        if module in _AMBIGUOUS:
            continue
        dist = _DISTRIBUTION.get(module, module)
        for name in (dist, *_IMPLIED.get(module, ())):
            if _norm(name) not in have:
                have.add(_norm(name))
                out.append(name)
    for requirement in list(declared):
        for implied in _IMPLIED.get(_requirement_name(requirement), ()):
            if _norm(implied) not in have:
                have.add(_norm(implied))
                out.append(implied)
    return out


def requirements(root: Path) -> list[str]:
    """Everything a test run needs installed: pytest, the declared requirements, and the inferred ones."""
    declared = declared_requirements(root)
    out = ["pytest"] if "pytest" not in {_requirement_name(r) for r in declared} else []
    return out + declared + inferred_requirements(root, declared)


# -- the environment EvalLoop owns -----------------------------------------------------------------


def owned_env_dir(root: Path, home: Path | None = None) -> Path:
    resolved = root.resolve()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", resolved.name).strip("-").lower() or "project"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:10]
    return (home if home is not None else Path.home()) / ".evalloop" / "envs" / f"{slug}-{digest}"


def _want(packages: Sequence[str]) -> str:
    return hashlib.sha256("\n".join([sys.version, *packages]).encode("utf-8")).hexdigest()


def _env_python(env: Path) -> Path:
    return env / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def _names(value: object) -> tuple[str, ...]:
    return tuple(str(v) for v in value) if isinstance(value, list) else ()


def _read_marker(env: Path) -> dict[str, object]:
    try:
        data = json.loads((env / _MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def needs_build(root: Path, packages: Sequence[str], home: Path | None = None) -> bool:
    """Whether the owned environment is missing or was built for different requirements."""
    env = owned_env_dir(root, home)
    return not _env_python(env).exists() or _read_marker(env).get("want") != _want(packages)


@dataclass(frozen=True, slots=True)
class EnvBuild:
    python: Path
    installed: tuple[str, ...]
    failed: tuple[str, ...]
    reused: bool
    log: Path


def ensure_env(
    root: Path,
    packages: Sequence[str],
    *,
    home: Path | None = None,
    runner: Runner = subprocess.run,
) -> EnvBuild:
    """Build (or reuse) the owned environment with ``packages``. Installs what it can; names the rest."""
    env = owned_env_dir(root, home)
    python, log = _env_python(env), env / "install.log"
    want = _want(packages)
    marker = _read_marker(env)
    if python.exists() and marker.get("want") == want:
        return EnvBuild(python, _names(marker.get("installed")), _names(marker.get("failed")), True, log)
    env.parent.mkdir(parents=True, exist_ok=True)
    transcript: list[str] = []

    def run(argv: list[str], timeout: float) -> bool:
        transcript.append("$ " + " ".join(argv))
        try:
            done = runner(argv, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            transcript.append(f"  failed: {error}")
            return False
        transcript.append((done.stdout or "") + (done.stderr or ""))
        return done.returncode == 0

    if not python.exists() and not run([sys.executable, "-m", "venv", str(env)], 180.0):
        env.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(transcript), encoding="utf-8")
        return EnvBuild(python, (), tuple(packages), False, log)
    pip = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-q"]
    installed: list[str] = []
    failed: list[str] = []
    if run(pip + list(packages), _INSTALL_TIMEOUT):
        installed = list(packages)
    else:
        for package in packages:  # one bad pin must not stop the rest
            (installed if run(pip + [package], _EACH_TIMEOUT) else failed).append(package)
    (env / _MARKER).write_text(json.dumps({"want": want, "installed": installed, "failed": failed}, indent=2),
                               encoding="utf-8")
    log.write_text("\n".join(transcript), encoding="utf-8")
    return EnvBuild(python, tuple(installed), tuple(failed), False, log)


# -- the choice ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Interpreter:
    """The Python to run this project's tests with, where it came from, and what it still lacks."""

    python: str
    origin: str
    missing: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    packages: tuple[str, ...] = field(default=())


def choose(
    root: Path,
    *,
    allow_install: bool,
    home: Path | None = None,
    runner: Runner = subprocess.run,
) -> Interpreter:
    """The best interpreter for ``root``'s tests: its own venv, EvalLoop's env for it, or EvalLoop's Python."""
    modules = third_party_imports(root)
    packages = tuple(requirements(root))
    own = project_python(root)
    if own is not None and not missing_modules(own, ["pytest"], runner=runner):
        return Interpreter(str(own), f"the project's own environment ({own.parent.parent.name})",
                           tuple(missing_modules(own, modules, runner=runner)), (), packages)
    env_python = _env_python(owned_env_dir(root, home))
    if allow_install and needs_build(root, list(packages), home):
        build = ensure_env(root, list(packages), home=home, runner=runner)
        if build.python.exists():
            return Interpreter(str(build.python), "EvalLoop's environment for this project",
                               tuple(missing_modules(build.python, modules, runner=runner)), build.failed, packages)
    elif env_python.exists():  # built earlier (with permission): reuse it, no network needed
        failed = _names(_read_marker(owned_env_dir(root, home)).get("failed"))
        return Interpreter(str(env_python), "EvalLoop's environment for this project",
                           tuple(missing_modules(env_python, modules, runner=runner)), failed, packages)
    return Interpreter(sys.executable, "EvalLoop's own Python",
                       tuple(missing_modules(sys.executable, modules, runner=runner)), (), packages)
