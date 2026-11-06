"""The on-screen character: a tiny vector dancer who thinks out loud, chats, and opens a panel.

No window chrome anywhere — a frameless, transparent, always-on-top Tkinter window that draws:

* **the dancer** you picked (:mod:`evalloop.session.avatars`): Smooth the moonwalking minifigure,
  Zuri, Mira or Luz, each in any of the dances, drawn from flat vector shapes on a skeleton. The
  mood sets how hard they dance. ``c`` switches character and ``d`` switches dance (the page can
  change both too);
* **a thought cloud above his head** naming what he is testing right now, while he is active;
* **a chat**, opened by clicking him, that asks what to watch (:mod:`evalloop.session.chat_popup`);
* **a panel**, toggled with ``r``, that fades in beside him with the live eval report — drawn
  natively in Tk, never a browser;
* **the permission popup** (:mod:`evalloop.session.consent_popup`, EL-018) whenever the session is
  waiting to be allowed to open an endpoint, and the **Permissions view** on right-click or ``p``.

Tkinter must run on the main thread and needs a display, so the poll runs in a daemon thread and
hands the main thread plain data. The geometry (the avatar engine) is pure and testable without
ever opening a window.
"""

from __future__ import annotations

import json
import threading
import time
import tkinter as tk  # importing is display-free; only tk.Tk() needs a display (guarded in run_overlay)
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from evalloop.session.avatars import FIGURE_HEIGHT, PALETTE, Animator, Pose, catalog, cycle, pet_of, pose, pose_prims

__all__ = ["MOOD", "PALETTE", "Pose", "pose", "FIGURE_HEIGHT", "draw_prims", "run_overlay", "signal_line"]


MOOD = {
    "idle": "watching",
    "evaluating": "evaluating",
    "happy": "all clean",
    "alarmed": "problem found",
    "unsure": "undecided",
    "errored": "run errored",
}

_ACCENT = {
    "idle": "#5e5ce6", "evaluating": "#5e5ce6", "happy": "#30d158",
    "alarmed": "#ff453a", "unsure": "#ff9f0a", "errored": "#ff453a",
}

_FONT = "Helvetica Neue"

Point = tuple[float, float]


def _rrect_pts(x0: float, y0: float, x1: float, y1: float, r: float) -> list[Point]:
    """Corner-duplicated points that Tk's ``smooth=True`` renders as a rounded rectangle."""
    return [(x0 + r, y0), (x1 - r, y0), (x1, y0), (x1, y0 + r), (x1, y1 - r), (x1, y1),
            (x1 - r, y1), (x0 + r, y1), (x0, y1), (x0, y1 - r), (x0, y0 + r), (x0, y0)]


def draw_prims(canvas: tk.Canvas, prims: Sequence[Mapping[str, Any]], ox: float, oy: float, s: float) -> None:
    """Draw avatar prims (figure space, y up; :func:`~evalloop.session.avatars.pose_prims`) with the
    feet at (``ox``, ``oy``), scaled by ``s``."""
    for prim in prims:
        pts = prim["p"]
        flat: list[float] = []
        for i in range(0, len(pts), 2):
            flat += [ox + pts[i] * s, oy - pts[i + 1] * s]
        if prim["k"] == "poly":
            outline = prim["o"] or ""
            canvas.create_polygon(flat, fill=prim["f"] or "", outline=outline,
                                  width=max(0.6, prim["w"] * s) if outline else 0)
        else:
            canvas.create_line(*flat, fill=prim["c"], width=max(0.5, prim["w"] * s),
                               capstyle="round" if prim["r"] else "butt")


class _Poller:
    """Polls ``/status.json`` in a daemon thread; the main thread reads :attr:`state` / :attr:`data`."""

    def __init__(self, url: str, *, interval: float) -> None:
        self._url = url
        self._interval = interval
        self._stop = threading.Event()
        self.state = "idle"
        self.data: dict[str, object] = {}

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with urllib.request.urlopen(self._url, timeout=3) as response:
                    self.data = json.loads(response.read().decode("utf-8"))
                self.state = str(self.data.get("mascot", "idle"))
            except Exception:
                self.state = "idle"
            self._stop.wait(min(self._interval, 0.8))


def _str_list(value: object) -> list[str]:
    """A JSON field coerced to a list of strings, defensively (it came off the wire)."""
    return [str(x) for x in value] if isinstance(value, list) else []


def _runs(data: dict[str, object]) -> list[dict[str, object]]:
    raw = data.get("runs")
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def _testing_now(data: dict[str, object]) -> str:
    """What he is testing this instant — the session's in-flight target, not a finished run."""
    current = _str_list(data.get("current"))
    if not current:
        return ""
    head = current[0].split("/")[-1]
    return head if len(current) == 1 else f"{head} +{len(current) - 1}"


#: A one-character status glyph per outcome, for the always-on bubble. Colour carries the rest.
_OUTCOME_GLYPH = {"clean": "✓", "problem": "⚠", "undecided": "?", "errored": "×"}
_OUTCOME_ACCENT = {
    "clean": "#30d158", "problem": "#ff453a", "undecided": "#ff9f0a", "errored": "#ff453a",
}

#: The outcome each resting mood stands for, so the bubble names the SAME card the face reflects.
#: The mascot is the worst outcome of the latest tick, so the bubble must pick the run matching it
#: (the file that caused the mood), not merely the most recently recorded one — otherwise the pet
#: looks alarmed while its bubble names a file that was fine.
_MOOD_OUTCOME = {"happy": "clean", "alarmed": "problem", "unsure": "undecided", "errored": "errored"}


def _files_label(trigger: list[str]) -> str:
    """The lead filename of a trigger, with a ``+n`` when several files changed. '' if none."""
    if not trigger:
        return ""
    head = trigger[0].split("/")[-1].split("\\")[-1]
    return head if len(trigger) == 1 else f"{head} +{len(trigger) - 1}"


def signal_line(data: dict[str, object], state: str) -> tuple[str, str]:
    """The always-on bubble text + its accent colour: what he is testing *now*, or last tested + result.

    The in-flight target (``current`` + the ``evaluating`` mood) lasts only the few milliseconds a
    tick runs, so a ~1s poll almost never catches it — which is why the bubble looked dead. This
    derives a signal that is *always* truthful instead: "testing X" while a run is genuinely in
    flight, otherwise the last file graded and how it went, and "watching <project>" before the
    first run. Pure, so it is unit-tested without opening a window.
    """
    now = _testing_now(data)
    if state == "evaluating" and now:
        return f"testing {now}", _ACCENT["evaluating"]
    triggered = [r for r in _runs(data) if _str_list(r.get("trigger"))]
    if triggered:
        want = _MOOD_OUTCOME.get(state)
        # the run that caused the current mood (the worst one), else just the most recent file graded
        latest = next((r for r in triggered if str(r.get("outcome", "")) == want), triggered[0])
        label = _files_label(_str_list(latest.get("trigger")))
        outcome = str(latest.get("outcome", ""))
        glyph = _OUTCOME_GLYPH.get(outcome, "•")
        return f"{glyph} {label}", _OUTCOME_ACCENT.get(outcome, _ACCENT["idle"])
    project = str(data.get("root", "")).rstrip("/\\").replace("\\", "/").split("/")[-1]
    return f"watching {project or 'your repo'}", _ACCENT["idle"]


def _round_rect(
    canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, r: float, *, fill: str, outline: str = ""
) -> None:
    """A rounded rectangle, smoothed from a point list (Tk has no native rounded rect)."""
    pts = _rrect_pts(x0, y0, x1, y1, r)
    flat: list[float] = []
    for x, y in pts:
        flat += [x, y]
    canvas.create_polygon(flat, smooth=True, fill=fill, outline=outline)


def _make_transparent(win: "tk.Tk | tk.Toplevel", canvas: tk.Canvas) -> bool:
    """Make a window frameless AND actually transparent on macOS. Returns whether it took.

    The reliable path on Aqua is the native *plain* window style (no title bar, no close/min/max
    buttons, and it composites alpha) rather than ``overrideredirect``, plus ``-transparent`` and a
    ``systemTransparent`` background on the toplevel *and* the canvas — a canvas with any other
    background paints an opaque box over the hole.
    """
    try:
        win.tk.call("::tk::unsupported::MacWindowStyle", "style", str(win), "plain", "none")
        win.wm_attributes("-transparent", True)
        win["bg"] = "systemTransparent"
        canvas["bg"] = "systemTransparent"
        win.update_idletasks()
        return True
    except tk.TclError:
        win["bg"] = "#0e0f13"
        canvas["bg"] = "#0e0f13"
        return False


def run_overlay(*, host: str = "127.0.0.1", port: int = 7420, poll: float = 1.5, scale: float = 0.62) -> None:
    """Open the frameless, transparent figure. Blocks on the Tk main loop until dismissed (Esc).

    Constructs the window only here, so importing this module (and the geometry tests) stay headless.
    """
    poller = _Poller(f"http://{host}:{port}/status.json", interval=poll)
    poller.start()

    cloud_h = 40
    w = 132
    h = int(cloud_h + FIGURE_HEIGHT * scale + 10)
    ox, oy = w / 2.0, h - 6.0

    root = tk.Tk()
    root.attributes("-topmost", True)
    sw = root.winfo_screenwidth()
    root.geometry(f"{w}x{h}+{sw - w - 40}+120")
    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0, bd=0)
    canvas.pack()
    root.update()
    transparent = _make_transparent(root, canvas)

    panel = _Panel(poller, transparent=transparent)
    from evalloop.session.consent_popup import BotClient, ConsentUI  # Tk too; same main loop, never blocks

    client = BotClient(host, port)
    consent = ConsentUI(root, client)
    from evalloop.session.chat_popup import ChatWindow

    chat: dict[str, ChatWindow | None] = {"win": None}

    def toggle_chat() -> None:
        open_chat = chat["win"]
        if open_chat is not None and not open_chat.closed:
            open_chat.close()
            return
        chat["win"] = ChatWindow(root, client, data=lambda: poller.data, on_permissions=consent.open_permissions,
                                 near=(root.winfo_x(), root.winfo_y()))
    drag = {"x": 0, "y": 0, "moved": False}

    def press(e: "tk.Event[tk.Misc]") -> None:
        drag.update(x=e.x, y=e.y, moved=False)

    def motion(e: "tk.Event[tk.Misc]") -> None:
        if abs(e.x - drag["x"]) + abs(e.y - drag["y"]) > 3:
            drag["moved"] = True
        root.geometry(f"+{root.winfo_x() + e.x - drag['x']}+{root.winfo_y() + e.y - drag['y']}")
        panel.reposition(root)

    def release(_e: "tk.Event[tk.Misc]") -> None:
        if not drag["moved"]:
            toggle_chat()                    # a click (not a drag) opens the chat: "what should I watch?"

    def shutdown() -> None:
        poller.stop()
        panel.close()
        root.destroy()

    canvas.bind("<Button-1>", press)
    canvas.bind("<B1-Motion>", motion)
    canvas.bind("<ButtonRelease-1>", release)
    for button in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):  # right-click on macOS / elsewhere
        canvas.bind(button, lambda _e: consent.open_permissions())
    root.bind("<Escape>", lambda _e: shutdown())
    root.bind("p", lambda _e: consent.open_permissions())
    root.bind("r", lambda _e: panel.toggle(root))

    def switch(what: str) -> None:
        """c / d: the next character or dance for the pet, saved by the session so the page follows."""
        choice = cycle(poller.data.get("avatar"), what)
        threading.Thread(target=lambda: _quietly(lambda: client.set_avatar(choice)), daemon=True).start()
        poller.data = {**poller.data, "avatar": choice}  # show it now; the next poll confirms

    root.bind("c", lambda _e: switch("character"))
    root.bind("d", lambda _e: switch("dance"))

    frame = {"n": 0}
    animator = Animator()
    clock = {"last": time.monotonic()}

    def draw_cloud(state: str, accent: str) -> None:
        """A thought cloud above his head, always on: what he is testing now, or last tested + result."""
        text, accent = signal_line(poller.data, state)
        if state == "evaluating":
            text += "." * (1 + frame["n"] // 8 % 3)
        width = min(w - 8.0, max(86.0, 6.6 * len(text) + 22))
        x0, x1 = (w - width) / 2, (w + width) / 2
        _round_rect(canvas, x0, 5, x1, 29, 11, fill="#1b1e26", outline=accent)
        canvas.create_text((x0 + x1) / 2, 17, text=text, fill="#f3f3f5", font=(_FONT, 9, "bold"))
        canvas.create_oval(w / 2 - 4, 30, w / 2 + 2, 36, fill="#1b1e26", outline=accent)
        canvas.create_oval(w / 2 - 1, 37, w / 2 + 3, 41, fill="#1b1e26", outline="")

    def draw() -> None:
        state = poller.state
        accent = _ACCENT.get(state, "#5e5ce6")
        now = time.monotonic()
        dt, clock["last"] = now - clock["last"], now
        character, dance, skin, outfit = pet_of(poller.data.get("avatar"))
        channels = animator.advance(dt, catalog()["dances"][dance], state)
        canvas.delete("all")
        draw_cloud(state, accent)
        draw_prims(canvas, pose_prims(character, channels, skin=skin, outfit=outfit), ox, oy, scale)
        if frame["n"] % 15 == 0:                   # twice a second: a permission waiting? show it
            consent.update(poller.data)
        frame["n"] += 1
        panel.refresh()
        root.after(33, draw)

    draw()
    root.mainloop()


def _quietly(call: Callable[[], object]) -> None:
    try:
        call()
    except Exception:  # the session may be gone; the pet keeps dancing
        pass


class _Panel:
    """A frameless native panel (no browser) that fades in with the live eval report."""

    W, H = 360, 340

    def __init__(self, poller: _Poller, *, transparent: bool) -> None:
        self._poller = poller
        self._transparent = transparent
        self._win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None

    def toggle(self, anchor: tk.Misc) -> None:
        if self._win is not None:
            self.close()
        else:
            self._open(anchor)

    def close(self) -> None:
        win = self._win
        if win is None:
            return
        self._win = None     # stop refresh() drawing into a window that is fading out
        self._canvas = None
        self._fade(win, 0.0, -0.2, win.destroy)

    @staticmethod
    def _fade(win: tk.Toplevel, target: float, step: float, done: "Callable[[], None] | None" = None) -> None:
        try:
            current = float(win.attributes("-alpha"))
        except (tk.TclError, ValueError):
            if done is not None:
                done()
            return
        nxt = current + step
        reached = nxt >= target if step > 0 else nxt <= target
        try:
            win.attributes("-alpha", target if reached else nxt)
        except tk.TclError:
            pass
        if reached:
            if done is not None:
                done()
        else:
            win.after(16, lambda: _Panel._fade(win, target, step, done))

    def reposition(self, anchor: tk.Misc) -> None:
        if self._win is not None:
            self._place(anchor)

    def _place(self, anchor: tk.Misc) -> None:
        if self._win is None:
            return
        self._win.geometry(f"{self.W}x{self.H}+{max(10, anchor.winfo_x() - self.W - 14)}+{anchor.winfo_y()}")

    def _open(self, anchor: tk.Misc) -> None:
        win = tk.Toplevel()
        win.attributes("-topmost", True)
        canvas = tk.Canvas(win, width=self.W, height=self.H, highlightthickness=0, bd=0)
        canvas.pack()
        win.update()
        _make_transparent(win, canvas)   # native plain style: no chrome, rounded card shows through
        win.bind("<Escape>", lambda _e: self.close())
        self._win, self._canvas = win, canvas
        self._place(anchor)
        self._render()
        try:
            win.attributes("-alpha", 0.0)
            self._fade(win, 0.98, 0.2)   # fluid fade-in
        except tk.TclError:
            pass

    def refresh(self) -> None:
        if self._win is not None:
            self._render()

    def _render(self) -> None:
        c = self._canvas
        if c is None:
            return
        data = self._poller.data
        state = self._poller.state
        accent = _ACCENT.get(state, "#5e5ce6")
        W, H = self.W, self.H
        c.delete("all")
        _round_rect(c, 3, 3, W - 3, H - 3, 26, fill="#15171d", outline="#2b2f3a")

        def text(
            x: float, y: float, s: str, color: str, size: int, *,
            bold: bool = False, anchor: Literal["w", "e", "center"] = "w",
        ) -> None:
            c.create_text(x, y, text=s, anchor=anchor, fill=color,
                          font=(_FONT, size, "bold" if bold else "normal"))

        c.create_oval(26, 28, 36, 38, fill=accent, outline="")
        text(46, 33, "EvalLoop", "#f3f3f5", 15, bold=True)
        text(W - 26, 33, MOOD.get(state, state), accent, 10, bold=True, anchor="e")
        text(26, 56, (str(data.get("root", "")) or "…")[-42:], "#7d828e", 10)
        c.create_line(26, 72, W - 26, 72, fill="#242832")

        y = 94.0
        now = _testing_now(data)
        if state == "evaluating" and now:
            _round_rect(c, 26, y - 16, W - 26, y + 18, 12, fill="#1b1f2b", outline=accent)
            text(40, y + 1, f"testing  {now}", "#f3f3f5", 11, bold=True)
            y += 50
        else:
            y += 10

        runs = _runs(data)
        p = f = i = 0
        for r in runs:
            cases = r.get("cases")
            for cs in (cases if isinstance(cases, list) else []):
                v = cs.get("verdict") if isinstance(cs, dict) else None
                p += v == "passed"
                f += v == "failed"
                i += v not in ("passed", "failed")
        for dx, (n, lab, col) in enumerate((
            (len(runs), "runs", "#f3f3f5"), (p, "passed", "#30d158"),
            (f, "failed", "#ff453a"), (i, "pending", "#ff9f0a"),
        )):
            x = 30 + dx * ((W - 56) / 4)
            text(x, y, str(n), col, 19, bold=True)
            text(x, y + 18, lab, "#7d828e", 9)
        y += 44
        c.create_line(26, y, W - 26, y, fill="#242832")
        y += 20

        for r in runs[:4]:
            outcome = str(r.get("outcome", ""))
            col = {"clean": "#30d158", "problem": "#ff453a", "undecided": "#ff9f0a",
                   "errored": "#ff453a"}.get(outcome, "#7d828e")
            _round_rect(c, 26, y - 13, W - 26, y + 25, 12, fill="#191c24")
            c.create_rectangle(26, y - 13, 30, y + 25, fill=col, outline="")
            text(42, y - 1, outcome.upper(), col, 10, bold=True)
            trig = ", ".join(_str_list(r.get("trigger"))) or "first look"
            text(42, y + 15, f"on {trig}"[:40], "#7d828e", 9)
            cases = r.get("cases")
            n_cases = len(cases) if isinstance(cases, list) else 0
            if n_cases:
                text(W - 42, y + 6, f"{n_cases} case{'s' if n_cases != 1 else ''}", "#7d828e", 9, anchor="e")
            y += 48
        if not runs:
            text(W / 2, y + 20, "Nothing evaluated yet", "#7d828e", 11, anchor="center")
            text(W / 2, y + 40, "edit a file — he'll get to work", "#5b5e68", 10, anchor="center")

        text(W / 2, H - 22, "r: close  ·  click: chat  ·  p: permissions  ·  drag", "#4e525c", 9, anchor="center")
