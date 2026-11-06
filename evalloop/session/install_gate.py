"""Permission to install a project's packages: asked once in the bot, then remembered if you like.

When a run's tests need third-party packages the test interpreter lacks
(:attr:`evalloop.run.RunResult.missing_packages`), the session does not just stop at "undecided".
It queues an install request, shown in the same permission popup as database requests (the popup
model below has the same shape as :class:`evalloop.session.consent.PopupModel`):

* **Allow once**: build EvalLoop's environment for this project and re-run now; ask again next session.
* **Allow and remember**: the same, and never ask again for this project. The approval is saved in
  ``<project>/.evalloop/install.json`` (that directory ignores itself in git). It can be revoked in
  the Permissions view.
* **Deny**: keep using what is installed, and don't ask again this session.

``evalloop start --install`` is the operator's blanket clearance, so nothing is asked. Installing
downloads from PyPI and runs build steps outside the sandbox (:mod:`evalloop.grade.project_env`),
which is why it is asked once rather than done silently. The environment lives in
``~/.evalloop/envs/``; the project and the user's own Python are never written to.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from evalloop.capability.consent_store import CONSENT_DIR
from evalloop.grade import project_env
from evalloop.session.consent import Choice, Resolution

__all__ = ["INSTALL_FILE", "InstallGate", "InstallRequest"]

INSTALL_FILE = "install.json"
_PREFIX = "install|"
_LABEL = {Choice.allow_once: "Allow once", Choice.allow_remember: "Allow and remember", Choice.deny: "Deny"}


def _file(root: str) -> Path:
    return Path(root) / CONSENT_DIR / INSTALL_FILE


def _remembered(root: str) -> bool:
    try:
        return bool(json.loads(_file(root).read_text(encoding="utf-8")).get("allowed"))
    except (OSError, ValueError, AttributeError):
        return False


@dataclass(frozen=True, slots=True)
class InstallRequest:
    """One project's packages waiting for permission to install."""

    root: str
    missing: tuple[str, ...]
    packages: tuple[str, ...]

    @property
    def key(self) -> str:
        return _PREFIX + self.root

    def to_json(self) -> dict[str, object]:
        """A pending item in the shape the permission popup renders."""
        shown = ", ".join(self.packages[:14]) + (f" and {len(self.packages) - 14} more" if len(self.packages) > 14 else "")
        rows = [
            ["project", self.root],
            ["why", f"the tests import {', '.join(self.missing)}, which {'is' if len(self.missing) == 1 else 'are'} not installed"],
            ["packages", shown or "pytest"],
            ["where", str(project_env.owned_env_dir(Path(self.root)))],
            ["from", "PyPI, with pip; install steps run outside the sandbox"],
            ["your files", "untouched: your project and your own Python are not changed"],
        ]
        buttons = [{"choice": c.value, "label": _LABEL[c]} for c in (Choice.allow_once, Choice.allow_remember, Choice.deny)]
        return {
            "key": self.key,
            "tool": "install",
            "endpoint": self.root,
            "posture": "local",
            "popup": {
                "title": "Install this project's packages?",
                "rows": rows,
                "warning": "Installing downloads code from the internet and runs its install steps. "
                           "Allow it for projects you trust.",
                "buttons": buttons,
                "default": Choice.allow_once.value,
                "needs_typed_name": False,
                "typed_hint": None,
            },
        }


class InstallGate:
    """Which projects may have packages installed, and the requests waiting for an answer."""

    def __init__(self, *, always: bool = False) -> None:
        self.always = always
        self._session: set[str] = set()
        self._denied: set[str] = set()
        self._pending: dict[str, InstallRequest] = {}

    @staticmethod
    def is_key(key: str) -> bool:
        return key.startswith(_PREFIX)

    def allowed(self, root: str) -> bool:
        return self.always or root in self._session or _remembered(root)

    def note_missing(self, root: str, missing: tuple[str, ...]) -> None:
        """A run lacked ``missing``: ask, unless installing is already allowed or was refused."""
        if not missing or self.allowed(root) or root in self._denied:
            self._pending.pop(root, None)
            return
        packages = tuple(project_env.requirements(Path(root)))
        self._pending[root] = InstallRequest(root, missing, packages)

    def pending(self) -> tuple[InstallRequest, ...]:
        return tuple(self._pending.values())

    def resolve(self, key: str, choice: Choice) -> Resolution:
        root = key[len(_PREFIX):]
        if root not in self._pending:
            return Resolution(False, False, False, "nothing is waiting to be installed for that project")
        del self._pending[root]
        if choice is Choice.deny:
            self._denied.add(root)
            return Resolution(True, False, False, "won't install anything for this project this session")
        self._session.add(root)
        if choice is Choice.allow_remember:
            path = _file(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            ignore = path.parent / ".gitignore"
            if not ignore.exists():
                ignore.write_text("# EvalLoop's local state: approvals are per-machine, never committed.\n*\n", encoding="utf-8")
            path.write_text(json.dumps({"allowed": True, "granted_at": time.time()}, indent=2) + "\n", encoding="utf-8")
            return Resolution(True, True, True, "installing now, and I'll install for this project from now on")
        return Resolution(True, True, False, "installing now, for this session")

    def forget(self, key: str) -> bool:
        """Revoke a project's install approval (session and remembered). Returns whether there was one."""
        root = key[len(_PREFIX):]
        had = root in self._session or _remembered(root)
        self._session.discard(root)
        try:
            _file(root).unlink()
        except OSError:
            pass
        self._denied.add(root)
        return had

    def approvals(self, root: str) -> list[dict[str, object]]:
        """The current project's install approval, for the Permissions view."""
        if not root or not (root in self._session or _remembered(root)) or self.always:
            return []
        return [{"key": _PREFIX + root, "tool": "install", "endpoint": f"install packages for {Path(root).name}",
                 "remembered": _remembered(root), "granted_by": "you", "reason": "packages the tests need",
                 "credential_source": None, "posture": "local"}]
