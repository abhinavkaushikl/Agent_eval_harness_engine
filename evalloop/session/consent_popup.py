"""The bot's permission popup and Permissions view, in Tkinter.

Decision ``EL-018``. Everything this module shows was decided in :mod:`evalloop.session.consent`: the
session publishes each pending request with its :class:`~evalloop.session.consent.PopupModel` in
``status.json``, and this code only draws that model and posts the button press back to the
session (``/consent/decide``, ``/consent/revoke``). There is no decision logic here to test.

It never freezes the bot. The popup is a ``Toplevel`` inside the bot's own Tk main loop, and every
HTTP call runs on a daemon thread that hands its reply back through a queue the main loop drains
with ``after``. Tk is touched only on the main thread.

Two ways in:

* the Tk pet (:mod:`evalloop.session.overlay`) builds a :class:`ConsentUI` on its own root;
* the Qt pet cannot share a process with Tk, so it launches this module as a small subprocess,
  ``python -m evalloop.session.consent_popup --port N [--permissions]``, which works through the
  pending queue (or shows the Permissions view) and exits.

Closing a popup counts as **Deny**: the fail-safe answer, and the one that stops the bot asking
again this session.
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

__all__ = ["Async", "BotClient", "ConsentUI", "main"]

_BG = "#15171d"
_CARD = "#1b1e26"
_TEXT = "#f3f3f5"
_DIM = "#8a8f9b"
_WARN = "#ff9f0a"
_DANGER = "#ff453a"
_FONT = "Helvetica Neue"

Json = dict[str, object]


class BotClient:
    """The session's HTTP surface, as the bot uses it. Blocking; call it off the Tk thread."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7420) -> None:
        self.base = f"http://{host}:{port}"

    def status(self) -> Json:
        with urllib.request.urlopen(f"{self.base}/status.json", timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _post(self, path: str, body: Json) -> Json:
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-EvalLoop-Bot": "1"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def decide(self, key: str, choice: str, typed: str = "") -> Json:
        return self._post("/consent/decide", {"key": key, "choice": choice, "typed": typed})

    def revoke(self, key: str) -> Json:
        return self._post("/consent/revoke", {"key": key})

    def watch(self, path: str) -> Json:
        return self._post("/watch", {"path": path})

    def pause(self) -> Json:
        return self._post("/pause", {})

    def set_avatar(self, avatar: Json) -> Json:
        return self._post("/avatar", {"avatar": avatar})


def _consent(data: Json) -> Json:
    raw = data.get("consent")
    return raw if isinstance(raw, dict) else {}


def _items(value: object) -> list[Json]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


class Async:
    """Runs blocking calls off the Tk thread and delivers their results on it."""

    def __init__(self, master: tk.Misc) -> None:
        self._master = master
        self._results: queue.Queue[tuple[Callable[[object], None], object]] = queue.Queue()
        self._drain()

    def run(self, work: Callable[[], object], done: Callable[[object], None]) -> None:
        def target() -> None:
            try:
                result: object = work()
            except (OSError, urllib.error.URLError, ValueError) as error:
                result = error
            self._results.put((done, result))

        threading.Thread(target=target, daemon=True).start()

    def _drain(self) -> None:
        try:
            while True:
                done, result = self._results.get_nowait()
                done(result)
        except queue.Empty:
            pass
        try:
            self._master.after(50, self._drain)
        except tk.TclError:
            pass  # the master was destroyed


class _Popup:
    """One permission window, drawn from a request's popup model."""

    def __init__(self, master: tk.Misc, request: Json, submit: Callable[[str, str, str], None], pending: int) -> None:
        self.key = str(request.get("key", ""))
        popup = request.get("popup")
        model: Json = popup if isinstance(popup, dict) else {}
        self._submit = submit
        self._closed = False
        self._needs_typed = bool(model.get("needs_typed_name"))

        win = tk.Toplevel(master)
        self.win = win
        win.title("EvalLoop — permission")
        win.configure(bg=_BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", lambda: self._press("deny"))

        body = tk.Frame(win, bg=_BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        production = self._needs_typed
        tk.Label(body, text=str(model.get("title", "Permission")), bg=_BG, fg=_DANGER if production else _TEXT,
                 font=(_FONT, 15, "bold"), anchor="w").pack(fill="x")
        if pending > 1:
            tk.Label(body, text=f"{pending - 1} more waiting after this one", bg=_BG, fg=_DIM,
                     font=(_FONT, 10), anchor="w").pack(fill="x")

        grid = tk.Frame(body, bg=_CARD, padx=12, pady=10)
        grid.pack(fill="x", pady=(10, 8))
        rows = model.get("rows")
        for i, row in enumerate(rows if isinstance(rows, list) else []):
            if not (isinstance(row, list) and len(row) == 2):
                continue
            tk.Label(grid, text=str(row[0]), bg=_CARD, fg=_DIM, font=(_FONT, 10), anchor="nw").grid(
                row=i, column=0, sticky="nw", padx=(0, 12), pady=2)
            tk.Label(grid, text=str(row[1]), bg=_CARD, fg=_TEXT, font=(_FONT, 11), anchor="w", justify="left",
                     wraplength=380).grid(row=i, column=1, sticky="w", pady=2)

        warning = model.get("warning")
        if warning:
            tk.Label(body, text=str(warning), bg=_BG, fg=_DANGER if production else _WARN, font=(_FONT, 10),
                     wraplength=470, justify="left", anchor="w").pack(fill="x", pady=(0, 6))

        self._typed = tk.StringVar(win)
        if self._needs_typed:
            hint = str(model.get("typed_hint") or "")
            tk.Label(body, text=f"Type {hint} to allow:", bg=_BG, fg=_TEXT, font=(_FONT, 10),
                     anchor="w").pack(fill="x")
            entry = tk.Entry(body, textvariable=self._typed, font=(_FONT, 12), width=40)
            entry.pack(fill="x", pady=(2, 6))
            entry.focus_set()

        self._message = tk.Label(body, text="", bg=_BG, fg=_DANGER, font=(_FONT, 10), anchor="w",
                                 wraplength=470, justify="left")
        self._message.pack(fill="x")

        bar = tk.Frame(body, bg=_BG)
        bar.pack(fill="x", pady=(8, 0))
        default = str(model.get("default", "deny"))
        self._buttons: list[tk.Button] = []
        buttons = model.get("buttons")
        for spec in reversed(_items(buttons)):
            choice = str(spec.get("choice", ""))
            button = tk.Button(bar, text=str(spec.get("label", choice)), command=self._presser(choice),
                               default="active" if choice == default else "normal")
            button.pack(side="right", padx=(6, 0))
            self._buttons.append(button)
        win.bind("<Return>", lambda _e: self._press(default))
        win.bind("<Escape>", lambda _e: self._press("deny"))
        win.update_idletasks()
        x = win.winfo_screenwidth() // 2 - win.winfo_reqwidth() // 2
        win.geometry(f"+{max(20, x)}+140")
        win.lift()

    def _presser(self, choice: str) -> Callable[[], None]:
        return lambda: self._press(choice)

    def _press(self, choice: str) -> None:
        if self._closed:
            return
        for button in self._buttons:
            button.configure(state="disabled")
        self._message.configure(text="…", fg=_DIM)
        self._submit(self.key, choice, self._typed.get())

    def answered(self, reply: Json) -> None:
        """The session's verdict on the press: close if accepted, else say why and let them retry."""
        if reply.get("accepted"):
            self.close()
            return
        for button in self._buttons:
            button.configure(state="normal")
        self._message.configure(text=str(reply.get("message", "not accepted")), fg=_DANGER)

    def failed(self, error: object) -> None:
        for button in self._buttons:
            button.configure(state="normal")
        self._message.configure(text=f"could not reach the session: {error}", fg=_DANGER)

    def close(self) -> None:
        self._closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class _PermissionsWindow:
    """Lists the live approvals (remembered and this-session) with a Revoke button each."""

    def __init__(self, master: tk.Misc, ui: ConsentUI) -> None:
        self._ui = ui
        win = tk.Toplevel(master)
        self.win = win
        win.title("EvalLoop — permissions")
        win.configure(bg=_BG)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.close)
        win.bind("<Escape>", lambda _e: self.close())
        self.closed = False
        tk.Label(win, text="Permissions", bg=_BG, fg=_TEXT, font=(_FONT, 15, "bold"), anchor="w",
                 padx=20, pady=12).pack(fill="x")
        self._body = tk.Frame(win, bg=_BG, padx=20)
        self._body.pack(fill="both", expand=True)
        tk.Label(win, text="Remembered approvals are saved in .evalloop/consents.json. "
                 "Also: evalloop consents list | revoke", bg=_BG, fg=_DIM, font=(_FONT, 9),
                 padx=20, pady=10, anchor="w").pack(fill="x")
        self._signature: object = None
        win.geometry("+120+160")

    def show(self, consent: Json) -> None:
        approvals, denied = _items(consent.get("approvals")), _items(consent.get("denied"))
        signature = json.dumps([approvals, denied], sort_keys=True)
        if signature == self._signature:
            return
        self._signature = signature
        for child in self._body.winfo_children():
            child.destroy()
        if not approvals:
            tk.Label(self._body, text="Nothing is approved.", bg=_BG, fg=_DIM, font=(_FONT, 11),
                     anchor="w").pack(fill="x", pady=4)
        for item in approvals:
            row = tk.Frame(self._body, bg=_CARD, padx=12, pady=8)
            row.pack(fill="x", pady=3)
            how = "remembered" if item.get("remembered") else "this session only"
            tk.Label(row, text=str(item.get("endpoint") or "(any endpoint)"), bg=_CARD, fg=_TEXT,
                     font=(_FONT, 11, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
            detail = f"{item.get('tool')} · {how}"
            if item.get("credential_source"):
                detail += f" · credential from {item.get('credential_source')}"
            tk.Label(row, text=detail, bg=_CARD, fg=_DIM, font=(_FONT, 10), anchor="w").grid(
                row=1, column=0, sticky="w")
            key = str(item.get("key", ""))
            tk.Button(row, text="Revoke", command=self._revoker(key)).grid(
                row=0, column=1, rowspan=2, padx=(16, 0))
            row.columnconfigure(0, weight=1)
        if denied:
            tk.Label(self._body, text="Denied this session (asked again next session): "
                     + ", ".join(str(d.get("endpoint")) for d in denied), bg=_BG, fg=_DIM, font=(_FONT, 10),
                     wraplength=440, justify="left", anchor="w").pack(fill="x", pady=(8, 0))

    def _revoker(self, key: str) -> Callable[[], None]:
        return lambda: self._ui.revoke(key)

    def close(self) -> None:
        self.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class ConsentUI:
    """Shows the head of the pending queue as a popup and hosts the Permissions view, on ``master``."""

    def __init__(self, master: tk.Misc, client: BotClient, *, prompt: bool = True) -> None:
        # prompt=False: host the Permissions view only (the chat process does this, so it never
        # duplicates the popups the pet already shows)
        self._prompt = prompt
        self._master = master
        self._client = client
        self._async = Async(master)
        self._popup: _Popup | None = None
        self._permissions: _PermissionsWindow | None = None
        self._answered: set[str] = set()  # pressed, reply not yet reflected in status.json
        self.last: Json = {}

    @property
    def busy(self) -> bool:
        """Whether a popup or the Permissions view is open."""
        return self._popup is not None or (self._permissions is not None and not self._permissions.closed)

    def update(self, data: Json) -> None:
        """Feed the latest ``status.json``. Opens the next popup if one is due. Main thread only."""
        self.last = data
        consent = _consent(data)
        pending = _items(consent.get("pending"))
        keys = {str(p.get("key")) for p in pending}
        self._answered &= keys
        if self._popup is not None and self._popup.key not in keys and self._popup.key not in self._answered:
            self._popup.close()  # resolved elsewhere (another bot, or the CLI)
            self._popup = None
        if self._popup is None and self._prompt:
            waiting = [p for p in pending if str(p.get("key")) not in self._answered]
            if waiting:
                self._popup = _Popup(self._master, waiting[0], self._submit, len(waiting))
        if self._permissions is not None:
            if self._permissions.closed:
                self._permissions = None
            else:
                self._permissions.show(consent)

    def open_permissions(self) -> None:
        if self._permissions is None or self._permissions.closed:
            self._permissions = _PermissionsWindow(self._master, self)
        self._permissions.show(_consent(self.last))
        self._permissions.win.lift()

    def revoke(self, key: str) -> None:
        self._async.run(lambda: self._client.revoke(key), lambda _result: None)

    def _submit(self, key: str, choice: str, typed: str) -> None:
        popup = self._popup

        def done(result: object) -> None:
            if popup is None or popup is not self._popup:
                return
            if isinstance(result, dict) and result.get("accepted"):
                self._answered.add(key)
                popup.answered(result)
                self._popup = None
            elif isinstance(result, dict):
                popup.answered(result)
            else:
                popup.failed(result)

        self._async.run(lambda: self._client.decide(key, choice, typed), done)


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone popup process (for the Qt pet): work through the pending queue, or show Permissions."""
    parser = argparse.ArgumentParser(prog="python -m evalloop.session.consent_popup")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7420)
    parser.add_argument("--permissions", action="store_true", help="show the Permissions view instead")
    args = parser.parse_args(argv)

    client = BotClient(args.host, args.port)
    root = tk.Tk()
    root.withdraw()
    ui = ConsentUI(root, client)
    status: dict[str, Json] = {"data": {}}
    idle = {"ticks": 0}

    def fetch() -> None:
        try:
            status["data"] = client.status()
        except (OSError, urllib.error.URLError, ValueError):
            status["data"] = {}

    def loop() -> None:
        ui.update(status["data"])
        threading.Thread(target=fetch, daemon=True).start()
        idle["ticks"] = 0 if ui.busy else idle["ticks"] + 1
        if idle["ticks"] > 8:  # nothing open for ~4 s: the queue is done (or the view closed)
            root.destroy()
            return
        root.after(500, loop)

    fetch()
    if args.permissions:
        ui.update(status["data"])
        ui.open_permissions()
    loop()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
