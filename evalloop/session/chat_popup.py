"""The bot's chat window: click the pet, tell it what to watch.

What a line means is decided in :mod:`evalloop.session.chat`. This module only draws the window,
shows the conversation, and sends the result to the session (``/watch``, ``/pause``) on a daemon
thread, so the pet keeps animating. Two ways in, as with the permission popup:

* the Tk pet opens a :class:`ChatWindow` on its own root;
* the Qt pet launches ``python -m evalloop.session.chat_popup --port N`` (Tk cannot share a process
  with Qt), which shows the chat until it is closed.

**Browse…** opens the system folder picker. That dialog is modal, so while it is open the Tk pet's
animation pauses. The Qt pet runs the chat in its own process and is unaffected.
"""

from __future__ import annotations

import argparse
import threading
import tkinter as tk
import urllib.error
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import filedialog

from evalloop.session.chat import (
    HELP,
    Action,
    apply_avatar,
    avatar_reply,
    cast_text,
    greeting,
    interpret,
    report_text,
    status_text,
)
from evalloop.session.consent_popup import Async, BotClient, ConsentUI

__all__ = ["ChatWindow", "main"]

_BG = "#15171d"
_CARD = "#1b1e26"
_TEXT = "#f3f3f5"
_DIM = "#8a8f9b"
_ACCENT = "#5e5ce6"
_FONT = "Helvetica Neue"

Json = dict[str, object]


class ChatWindow:
    """One chat window. ``data`` returns the latest ``status.json``; ``on_permissions`` opens that view."""

    def __init__(
        self,
        master: tk.Misc,
        client: BotClient,
        *,
        data: Callable[[], Json],
        on_permissions: Callable[[], None],
        on_close: Callable[[], None] | None = None,
        near: tuple[int, int] | None = None,
    ) -> None:
        self._client = client
        self._data = data
        self._on_permissions = on_permissions
        self._on_close = on_close
        self._async = Async(master)
        self.closed = False

        win = tk.Toplevel(master)
        self.win = win
        win.title("EvalLoop")
        win.configure(bg=_BG)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda _e: self.close())

        tk.Label(win, text="EvalLoop", bg=_BG, fg=_TEXT, font=(_FONT, 14, "bold"), anchor="w",
                 padx=16, pady=10).pack(fill="x")
        self._log = tk.Text(win, width=58, height=14, bg=_CARD, fg=_TEXT, insertbackground=_TEXT,
                            relief="flat", wrap="word", font=(_FONT, 11), padx=10, pady=8, highlightthickness=0)
        self._log.tag_configure("bot", foreground=_TEXT)
        self._log.tag_configure("you", foreground="#9fa3ff")
        self._log.tag_configure("dim", foreground=_DIM)
        self._log.pack(fill="both", expand=True, padx=16)
        self._log.configure(state="disabled")

        bar = tk.Frame(win, bg=_BG, padx=16, pady=10)
        bar.pack(fill="x")
        self._entry = tk.Entry(bar, font=(_FONT, 12), width=40)
        self._entry.pack(side="left", fill="x", expand=True)
        self._entry.bind("<Return>", lambda _e: self._send())
        tk.Button(bar, text="Send", command=self._send).pack(side="left", padx=(6, 0))
        tk.Button(bar, text="Browse…", command=self._browse).pack(side="left", padx=(6, 0))

        self._say(greeting(self._data()))
        win.update_idletasks()
        if near is not None:
            x, y = near
            win.geometry(f"+{max(10, x - win.winfo_reqwidth() - 14)}+{max(10, y)}")
        win.lift()
        self._entry.focus_set()

    # -- the transcript ---------------------------------------------------------------------

    def _append(self, who: str, text: str, tag: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", f"{who}  ", "dim")
        self._log.insert("end", text + "\n\n", tag)
        self._log.configure(state="disabled")
        self._log.see("end")

    def _say(self, text: str) -> None:
        if not self.closed:
            self._append("bot", text, "bot")

    # -- input --------------------------------------------------------------------------------

    def _send(self, text: str | None = None) -> None:
        said = (text if text is not None else self._entry.get()).strip()
        self._entry.delete(0, "end")
        if not said:
            return
        self._append("you", said, "you")
        self.handle(said)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(parent=self.win, initialdir=str(Path.home()), title="What should I watch?")
        if chosen:
            self._send(chosen)

    def handle(self, said: str) -> None:
        """Act on one line: say something, and maybe tell the session to watch or pause."""
        command = interpret(said, cwd=Path.home())
        if command.error is not None:
            self._say(command.error)
            return
        if command.action is Action.watch and command.path is not None:
            path = command.path
            self._say(f"On it — switching to {path}…")
            self._async.run(lambda: self._client.watch(path), self._watched)
        elif command.action is Action.stop:
            self._async.run(self._client.pause, lambda r: self._say(
                "Stopped watching. Give me a folder to start again." if isinstance(r, dict) else f"Couldn't reach the session: {r}"))
        elif command.action is Action.status:
            self._say(status_text(self._data()))
        elif command.action is Action.report:
            self._say(report_text(self._data()))
        elif command.action is Action.avatar:
            choice = apply_avatar(self._data().get("avatar"), command)
            self._async.run(lambda: self._client.set_avatar(choice), lambda r: self._say(
                avatar_reply(choice) if isinstance(r, dict) else f"Couldn't reach the session: {r}"))
        elif command.action is Action.cast:
            self._say(cast_text())
        elif command.action is Action.install:
            consent = self._data().get("consent")
            pending = consent.get("pending") if isinstance(consent, dict) else None
            item = next((p for p in pending if isinstance(p, dict) and p.get("tool") == "install"), None) if isinstance(pending, list) else None
            if item is None:
                self._say("Nothing needs installing right now. When a test can't run because a package is missing, I'll ask.")
            else:
                key = str(item.get("key"))
                self._async.run(lambda: self._client.decide(key, "allow_remember", ""), lambda r: self._say(
                    "Installing the packages now (into EvalLoop's own environment), then I'll re-run the checks. "
                    "I'll do this for this project from now on." if isinstance(r, dict) and r.get("accepted")
                    else f"That didn't work: {r.get('message') if isinstance(r, dict) else r}"))
        elif command.action is Action.permissions:
            self._on_permissions()
            self._say("Opened the Permissions view.")
        else:
            self._say(HELP)

    def _watched(self, result: object) -> None:
        if not isinstance(result, dict):
            self._say(f"Couldn't reach the session: {result}")
            return
        if not result.get("ok"):
            self._say(str(result.get("message", "That didn't work.")))
            return
        self._say(f"Watching {result.get('root')} now. Save a file and I'll test it.")
        # the first look runs on the next tick; report it once it has had a moment
        self.win.after(4000, lambda: self._say(status_text(self._data())))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self._on_close is not None:
            self._on_close()


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone chat process (for the Qt pet). Exits when the window is closed."""
    parser = argparse.ArgumentParser(prog="python -m evalloop.session.chat_popup")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7420)
    parser.add_argument("--x", type=int, default=None, help="screen x of the pet, to open beside it")
    parser.add_argument("--y", type=int, default=None)
    args = parser.parse_args(argv)

    client = BotClient(args.host, args.port)
    root = tk.Tk()
    root.withdraw()
    latest: dict[str, Json] = {"data": {}}
    permissions = ConsentUI(root, client, prompt=False)  # the pet shows popups; this only hosts the view

    def fetch() -> None:
        try:
            latest["data"] = client.status()
        except (OSError, urllib.error.URLError, ValueError):
            pass

    def refresh() -> None:
        threading.Thread(target=fetch, daemon=True).start()
        permissions.update(latest["data"])
        root.after(1000, refresh)

    fetch()
    near = (args.x, args.y) if args.x is not None and args.y is not None else None
    ChatWindow(root, client, data=lambda: latest["data"], on_permissions=permissions.open_permissions,
               on_close=root.destroy, near=near)
    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
