"""What the bot's chat understands, decided without a window.

Clicking the pet opens a small chat (:mod:`evalloop.session.chat_popup`) that asks what to watch.
This module turns what was typed into a :class:`Command`, and turns ``status.json`` into the plain
replies the chat shows. It is a fixed command set, not a language model, so nothing typed here ever
leaves the machine:

* a folder path (``~/code/shop``, ``/Users/me/app``, ``.``), alone or in a sentence such as
  ``watch ~/code/shop`` or ``please watch "/Users/me/my repo"`` → watch it;
* ``status`` / ``what are you watching`` → what it watches and how the last check went;
* ``report`` / ``results`` / ``what did you find`` → the latest findings, failures first;
* ``stop`` / ``pause`` → stop watching until told a folder again;
* ``permissions`` → open the Permissions view;
* ``install packages`` → allow (and remember) installing what this project's tests need;
* a character or a dance (``mira``, ``dance salsa``, ``make luz do the moonwalk``, ``next dance``,
  ``next character``; close spellings such as ``bhartnatayam`` count) → change the desktop pet;
  ``characters`` lists who can dance what;
* ``help`` → the list above.

"Watch this repo" with no path cannot be resolved (the bot does not know which folder the editor
has open), so it asks for the path and says how to copy it from VS Code.
"""

from __future__ import annotations

import difflib
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from evalloop._compat import StrEnum
from evalloop.session import avatars

__all__ = [
    "Action", "Command", "GREETING_IDLE", "HELP", "apply_avatar", "avatar_reply", "cast_text", "greeting",
    "interpret", "report_text", "status_text",
]


class Action(StrEnum):
    watch = "watch"
    status = "status"
    report = "report"
    stop = "stop"
    permissions = "permissions"
    help = "help"
    ask_path = "ask_path"
    avatar = "avatar"
    cast = "cast"
    install = "install"


@dataclass(frozen=True, slots=True)
class Command:
    """What a line of chat asks for. ``path`` is set (resolved) for ``watch``; ``error`` if unusable."""

    action: Action
    path: str | None = None
    error: str | None = None
    character: str | None = None  # for ``avatar``: a character id, or "+" for the next one
    dance: str | None = None      # for ``avatar``: a dance id, or "+" for the next one


HELP = (
    "Tell me a folder to watch, e.g.  ~/code/my-app  (or press Browse).\n"
    "Then: 'status', 'report', 'stop', 'permissions', 'install packages', or 'help'.\n"
    "Dancers: 'characters', a name ('mira'), a dance ('dance salsa'), 'next dance'."
)
GREETING_IDLE = "Hi! What do you want me to watch? Paste a folder path, or press Browse."
_COPY_PATH = "In VS Code: right-click the folder in the Explorer → Copy Path, then paste it here."

_KEYWORDS: tuple[tuple[Action, tuple[str, ...]], ...] = (
    (Action.help, ("help", "?", "commands", "what can you do")),
    (Action.stop, ("stop", "pause", "stop watching", "quit watching", "unwatch")),
    (Action.permissions, ("permissions", "permission", "perms", "consents", "approvals")),
    (Action.report, ("report", "results", "findings", "what did you find", "show report", "show results")),
    (Action.status, ("status", "what are you watching", "where are you", "what are you doing", "state")),
    (Action.cast, ("characters", "avatars", "dances", "dancers", "who can dance", "cast")),
    (Action.install, ("install", "install packages", "install them", "install the packages", "install deps",
                      "install dependencies", "install requirements", "allow install", "allow installs")),
)
_WATCH_WORDS = re.compile(r"\b(watch|monitor|track|look at|observe|check|follow)\b", re.IGNORECASE)
_FILLER = {"please", "can", "you", "could", "start", "watching", "watch", "my", "the", "this", "repo",
           "repository", "folder", "project", "directory", "dir", "at", "in", "on", "of", "and", "now", "i",
           "am", "working", "work", "me", "for", "monitor", "track", "look", "observe", "check", "follow", "to"}


def _normalise(text: str) -> str:
    return re.sub(r"[\s!.?]+$", "", text.strip().lower())


def _candidates(text: str) -> list[str]:
    try:
        tokens = shlex.split(text)
    except ValueError:  # an unbalanced quote: fall back to whitespace
        tokens = text.split()
    out: list[str] = []
    for token in tokens:
        token = token.strip().strip(",;")
        if not token:
            continue
        if token.startswith(("/", "~", "./", "../")) or token in (".", "..") or "/" in token or "\\" in token:
            out.append(token)
    if out:
        return out
    rest = [t for t in tokens if t.lower().strip(",;.!?") not in _FILLER]
    return rest[:1] if len(rest) == 1 else []


def interpret(text: str, *, cwd: Path | None = None) -> Command:
    """Turn one line of chat into a command. Pure apart from checking that a folder exists."""
    said = _normalise(text)
    if not said:
        return Command(Action.help)
    for action, words in _KEYWORDS:
        if said in words:
            return Command(action)
    base = cwd if cwd is not None else Path.cwd()
    for raw in _candidates(text.strip()):
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = base / path
        if path.is_dir():
            return Command(Action.watch, path=str(path.resolve()))
        if path.exists():
            return Command(Action.watch, path=str(path), error=f"{path} is a file; give me the folder that holds it.")
        if raw.startswith(("/", "~", ".")) or "/" in raw:
            return Command(Action.watch, path=str(path), error=f"I can't find a folder at {path}.")
    dancer = _avatar_command(said)
    if dancer is not None:
        return dancer
    if _WATCH_WORDS.search(said):
        return Command(Action.ask_path, error=f"Which folder? {_COPY_PATH}")
    return Command(Action.help, error=f"I didn't catch that. {HELP}")


# -- the dancers ------------------------------------------------------------------------------------


def _avatar_command(said: str) -> Command | None:
    """A character and/or a dance named in ``said`` (close spellings count), or None."""
    if said in ("next dance", "another dance", "change dance"):
        return Command(Action.avatar, dance="+")
    if said in ("next character", "next avatar", "next dancer", "change character", "someone else"):
        return Command(Action.avatar, character="+")
    cat = avatars.catalog()
    words = re.findall(r"[a-z]+", said)
    names = {cat["characters"][cid]["name"].lower(): cid for cid in cat["order"]}
    dances = {**{did: did for did in cat["dance_order"]},
              **{cat["dances"][did]["name"].lower(): did for did in cat["dance_order"]}}
    character = next((names[w] for w in words if w in names), None)
    dance = None
    for word in words:
        match = difflib.get_close_matches(word, list(dances), n=1, cutoff=0.75)
        if match:
            dance = dances[match[0]]
            break
    if character is None and dance is None:
        return None
    return Command(Action.avatar, character=character, dance=dance)


def apply_avatar(raw: object, command: Command) -> dict[str, object]:
    """The avatar choice after ``command``: the named (or next) character becomes the desktop pet and
    joins the dance floor; a named (or next) dance is given to that character."""
    cat = avatars.catalog()
    choice = avatars.normalize_choice(raw)
    if command.character == "+":
        choice = avatars.cycle(choice, "character")
    elif command.character is not None:
        choice["pet"] = command.character
    if command.dance == "+":
        choice = avatars.cycle(choice, "dance")
    elif command.dance is not None:
        choice["chars"][choice["pet"]]["dance"] = command.dance
    if choice["pet"] not in choice["stage"]:
        on = set(choice["stage"]) | {choice["pet"]}
        choice["stage"] = [cid for cid in cat["order"] if cid in on]
    return choice


def avatar_reply(choice: Mapping[str, object]) -> str:
    character, dance, _, _ = avatars.pet_of(choice)
    cat = avatars.catalog()
    return f"{cat['characters'][character]['name']} is your desktop pet now, dancing {cat['dances'][dance]['name']}."


def cast_text() -> str:
    cat = avatars.catalog()
    lines = ["Who can dance (any of them can do any dance):"]
    for cid in cat["order"]:
        c = cat["characters"][cid]
        lines.append(f"• {c['name']} — signature: {cat['dances'][c['dance']]['name']}")
    lines.append("Dances: " + ", ".join(cat["dances"][d]["name"] for d in cat["dance_order"]) + ".")
    lines.append("Try 'mira', 'dance salsa', or 'make luz do the moonwalk'. The page has the full dance floor.")
    return "\n".join(lines)


# -- replies built from status.json ---------------------------------------------------------------


def _runs(data: dict[str, object]) -> list[dict[str, object]]:
    raw = data.get("runs")
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


_NO_TEST = re.compile(r"^(?P<file>.+?)::(?P<func>[\w.]+): no (?:test )?oracle")


def untested(run: Mapping[str, object]) -> list[str]:
    """The functions a run found but had no test for (from its notes), in order."""
    notes = run.get("notes")
    found: list[str] = []
    for note in notes if isinstance(notes, list) else []:
        match = _NO_TEST.match(str(note))
        if match:
            found.append(match.group("func"))
    return found


def _root(data: dict[str, object]) -> str:
    return str(data.get("root") or "")


def greeting(data: dict[str, object]) -> str:
    """The first line the chat shows: ask for a folder, or say what is being watched."""
    root = _root(data)
    if not root or data.get("watching") is False:
        return GREETING_IDLE
    return f"I'm watching {root}.\nType another folder to switch, or 'status', 'report', 'stop', 'help'."


def status_text(data: dict[str, object]) -> str:
    """One short paragraph: what is watched, what it is doing, and the last result."""
    switching = data.get("switching_to")
    if switching:
        return f"Switching to {switching} — I'll start as soon as the current check finishes."
    root = _root(data)
    if not root:
        return "I'm not watching anything yet. " + GREETING_IDLE
    if data.get("watching") is False:
        return f"Paused (last folder: {root}). Give me a folder to start again."
    runs = _runs(data)
    mood = str(data.get("mascot", "idle"))
    lines = [f"Watching {root}."]
    if mood == "evaluating":
        current = data.get("current")
        what = ", ".join(str(c) for c in current) if isinstance(current, list) and current else "your changes"
        lines.append(f"Checking {what} right now.")
    if not runs:
        lines.append("Nothing checked yet — save a file and I'll test it.")
    else:
        latest = runs[0]
        trigger = latest.get("trigger")
        on = ", ".join(str(t) for t in trigger) if isinstance(trigger, list) and trigger else "the repository"
        lines.append(f"Last check: {str(latest.get('outcome', '?')).upper()} on {on}. {len(runs)} check(s) so far.")
        cases = latest.get("cases")
        missing = untested(latest)
        if not cases and missing:
            lines.append(
                f"Nothing was actually tested: I found {', '.join(missing)} but no tests for them, and I'm not "
                "allowed to write tests. Add a test file, or start me with --author to write them."
            )
    consent = data.get("consent")
    pending = consent.get("pending") if isinstance(consent, dict) else None
    if isinstance(pending, list) and pending:
        lines.append(f"{len(pending)} permission request(s) waiting for you.")
    return " ".join(lines)


_ORDER = {"failed": 0, "inconclusive": 1, "passed": 2}


def report_text(data: dict[str, object], *, limit: int = 8) -> str:
    """The latest findings, failures first, one line each, with why it failed."""
    runs = _runs(data)
    if not runs:
        return "No findings yet — save a file in the folder I'm watching."
    cases: list[tuple[int, str]] = []
    for run in runs[:5]:
        raw = run.get("cases")
        for case in raw if isinstance(raw, list) else []:
            if not isinstance(case, dict):
                continue
            verdict = str(case.get("verdict", ""))
            where = str(case.get("artifact", "")).split("::")[0].split("/")[-1]
            line = f"{verdict.upper():<12} {where} — {case.get('name', '')}"
            detail = str(case.get("detail", "")).strip()
            if verdict == "failed" and detail:
                line += f"\n               {detail[:160]}"
            cases.append((_ORDER.get(verdict, 1), line))
        if run.get("error"):
            cases.append((0, f"ERRORED      the check itself failed: {run.get('error')}"))
    if not cases:
        latest = runs[0]
        return f"The last check was {str(latest.get('outcome', '?')).upper()} but graded no individual cases."
    cases.sort(key=lambda c: c[0])
    shown = [line for _, line in cases[:limit]]
    failed = sum(1 for rank, _ in cases if rank == 0)
    passed = sum(1 for rank, _ in cases if rank == 2)
    head = f"{failed} failing, {passed} passing, {len(cases) - failed - passed} undecided:"
    more = f"\n… and {len(cases) - limit} more (press r on the pet for the full panel)." if len(cases) > limit else ""
    return head + "\n" + "\n".join(shown) + more
