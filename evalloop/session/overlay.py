"""The on-screen character: a tiny vector minifigure who leans, thinks out loud, and opens a panel.

No window chrome anywhere — a frameless, transparent, always-on-top Tkinter window that draws:

* **the figure**, built from smooth vector shapes (not pixels): white fedora with a black band,
  black side locks, a printed face, a white suit over a blue shirt with a white tie, LEGO hands, and
  white legs with black shoes. He is authored once in *figure space* (origin between the feet, y
  up) and every pose is a **shear anchored at the shoes**, so the whole body tilts as one rigid
  plank — the Smooth Criminal lean — continuously rather than in steps;
* **a thought cloud above his head** naming what he is testing right now, while he is active;
* **a panel**, toggled by clicking him, that fades in beside him with the live eval report — drawn
  natively in Tk, never a browser.

Tkinter must run on the main thread and needs a display, so the poll runs in a daemon thread and
hands the main thread plain data. The geometry (:func:`pose`, the figure's points) is pure and
testable without ever opening a window.
"""

from __future__ import annotations

import json
import math
import threading
import tkinter as tk  # importing is display-free; only tk.Tk() needs a display (guarded in run_overlay)
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

__all__ = ["MOOD", "PALETTE", "Pose", "pose", "FIGURE_HEIGHT", "run_overlay"]


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

PALETTE = {
    "suit": "#f6f6f3",   # white fedora, jacket, trousers
    "hair": "#121216",   # black hair, hat band, shoes
    "skin": "#eab988",   # face and hands
    "shirt": "#1f8fe0",  # blue shirt
    "tie": "#ffffff",    # white tie
    "ink": "#1b1d23",    # printed outlines
}

_FONT = "Helvetica Neue"

#: The figure is authored in these units, feet at y=0, top of the hat at y=FIGURE_HEIGHT.
FIGURE_HEIGHT = 100.0

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Pose:
    """One instant of the dance: how far he leans, how high he bobs, how high the glove hand is."""

    lean: float   # figure units the TOP of the body travels; the shoes never move
    bob: float    # vertical lift
    arm: float    # 0 = hand down, 1 = hand raised


def pose(state: str, t: float) -> Pose:
    """The pose for ``state`` at time ``t`` seconds — continuous, so the motion is fluid. Pure."""
    if state == "evaluating":
        return Pose(lean=13.0 * math.sin(t * 3.4), bob=1.4 * abs(math.sin(t * 6.8)),
                    arm=0.5 + 0.5 * math.sin(t * 3.4 + 1.0))
    if state == "happy":
        return Pose(lean=5.0 * math.sin(t * 3.0), bob=3.2 * abs(math.sin(t * 5.0)), arm=0.85)
    if state in ("alarmed", "errored"):
        return Pose(lean=3.0 * math.sin(t * 13.0), bob=0.0, arm=0.2)
    if state == "unsure":
        return Pose(lean=5.0 * math.sin(t * 1.3), bob=0.0, arm=0.12)
    return Pose(lean=3.0 * math.sin(t * 1.1), bob=0.5 * math.sin(t * 2.2), arm=0.08)


def _ellipse_pts(cx: float, cy: float, rx: float, ry: float, n: int = 22) -> list[Point]:
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _rrect_pts(x0: float, y0: float, x1: float, y1: float, r: float) -> list[Point]:
    """Corner-duplicated points that Tk's ``smooth=True`` renders as a rounded rectangle."""
    return [(x0 + r, y0), (x1 - r, y0), (x1, y0), (x1, y0 + r), (x1, y1 - r), (x1, y1),
            (x1 - r, y1), (x0 + r, y1), (x0, y1), (x0, y1 - r), (x0, y0 + r), (x0, y0)]


def draw_figure(canvas: tk.Canvas, ox: float, oy: float, s: float, p: Pose, accent: str) -> None:
    """Draw the minifigure, feet centred at (``ox``, ``oy``), scaled by ``s``, posed by ``p``."""
    suit, hair, skin = PALETTE["suit"], PALETTE["hair"], PALETTE["skin"]
    shirt, tie, ink = PALETTE["shirt"], PALETTE["tie"], PALETTE["ink"]

    def at(x: float, y: float) -> Point:
        """Figure space -> canvas, with the lean sheared in proportion to height above the shoes."""
        dx = p.lean * (y / FIGURE_HEIGHT)
        return (ox + (x + dx) * s, oy - (y + p.bob) * s)

    def poly(pts: Sequence[Point], fill: str, outline: str = "", width: float = 1.0, smooth: bool = False) -> None:
        flat: list[float] = []
        for x, y in pts:
            cx, cy = at(x, y)
            flat += [cx, cy]
        canvas.create_polygon(flat, fill=fill, outline=outline, width=width, smooth=smooth)

    def limb(a: Point, b: Point, w: float, fill: str) -> None:
        """A rounded limb: a dark underlay for the printed outline, then the colour on top."""
        ax, ay = at(*a)
        bx, by = at(*b)
        canvas.create_line(ax, ay, bx, by, fill=ink, width=(w + 1.4) * s, capstyle="round")
        canvas.create_line(ax, ay, bx, by, fill=fill, width=w * s, capstyle="round")

    # --- status ring at his feet (the only thing the figure's colours never say) ---
    ring = _ellipse_pts(0, 1.5, 17, 3.2, 20)
    poly(ring, fill="", outline=accent, width=1.3, smooth=True)

    # --- legs: white trousers, black shoes and ankle band ---
    for sx in (-1, 1):
        inner, outer = sx * 1.6, sx * 14.5
        x0, x1 = min(inner, outer), max(inner, outer)
        poly([(x0, 6), (x1, 6), (x1, 35), (x0, 35)], fill=suit, outline=ink, width=0.9)      # trouser
        poly([(x0, 0), (x1, 0), (x1, 6), (x0, 6)], fill=hair, outline=ink, width=0.9)        # shoe
        poly([(x0, 9), (x1, 9), (x1, 12.5), (x0, 12.5)], fill=hair)                          # ankle band

    # --- torso: white jacket, blue shirt V, white tie, belt ---
    poly([(-15.5, 35), (15.5, 35), (17.5, 65), (-17.5, 65)], fill=suit, outline=ink, width=1.0)
    poly([(-7.5, 65), (7.5, 65), (0, 45)], fill=shirt)                                       # shirt V
    poly([(-2.4, 64), (2.4, 64), (1.5, 44), (-1.5, 44)], fill=tie, outline=ink, width=0.7)   # tie
    for sx in (-1, 1):                                                                        # lapels
        ax, ay = at(sx * 7.5, 65)
        bx, by = at(sx * 2.0, 46)
        canvas.create_line(ax, ay, bx, by, fill=ink, width=0.9 * s)
    ax, ay = at(-15.8, 38.5)
    bx, by = at(15.8, 38.5)
    canvas.create_line(ax, ay, bx, by, fill=ink, width=1.0 * s)                               # belt

    # --- arms: one hangs, the glove hand rises with the dance ---
    down, up = (-21.5, 44.0), (-19.0, 77.0)
    rx = down[0] * -1 + (up[0] * -1 - down[0] * -1) * p.arm
    ry = down[1] + (up[1] - down[1]) * p.arm
    limb((-15.0, 63.5), (-21.5, 44.0), 5.4, suit)          # his right arm, hanging
    limb((15.0, 63.5), (rx, ry), 5.4, suit)                # his left arm, raising
    poly(_ellipse_pts(-3.0, 1.0, 2.6, 2.6), fill=shirt)    # the blue armband sits on the hanging arm
    for hx, hy in ((-21.8, 42.0), (rx + 0.3, ry - 2.0)):
        poly(_ellipse_pts(hx, hy, 3.0, 3.0, 14), fill=skin, outline=ink, width=0.8, smooth=True)

    # --- head ---
    poly([(-4.0, 64), (4.0, 64), (4.0, 68), (-4.0, 68)], fill=skin, outline=ink, width=0.7)  # neck
    poly(_rrect_pts(-9.5, 67.5, 9.5, 86.0, 3.4), fill=skin, outline=ink, width=0.9, smooth=True)
    for sx in (-1, 1):                                                                        # eyes
        poly(_ellipse_pts(sx * 3.7, 78.6, 1.15, 1.35, 12), fill=ink, smooth=True)
        ex0, ey0 = at(sx * 5.4, 81.6)
        ex1, ey1 = at(sx * 2.1, 82.3)
        canvas.create_line(ex0, ey0, ex1, ey1, fill=ink, width=1.1 * s)                       # brow
    mx0, my0 = at(-2.6, 73.4)
    mx1, my1 = at(2.6, 73.4)
    canvas.create_line(mx0, my0, mx1, my1, fill=ink, width=1.0 * s)                           # mouth

    # --- hair: a fringe under the brim and a lock down each side ---
    poly([(-9.6, 83.0), (9.6, 83.0), (9.6, 86.2), (-9.6, 86.2)], fill=hair)
    poly([(-9.4, 85.5), (-12.6, 82.0), (-13.2, 74.0), (-10.6, 69.5), (-8.6, 72.0), (-9.4, 78.0)],
         fill=hair, smooth=True)
    poly([(9.4, 85.5), (12.6, 82.0), (13.2, 75.0), (11.0, 71.0), (8.8, 73.5), (9.4, 79.0)],
         fill=hair, smooth=True)

    # --- fedora: wide brim, black band, pinched crown ---
    poly(_ellipse_pts(0, 86.4, 23.5, 4.0, 26), fill=suit, outline=ink, width=0.9, smooth=True)
    poly([(-12.4, 86.6), (12.4, 86.6), (12.4, 90.2), (-12.4, 90.2)], fill=hair)
    poly([(-12.4, 90.0), (-11.0, 96.4), (-6.2, 98.6), (-2.2, 96.8), (2.2, 98.8), (6.6, 98.6),
          (11.0, 96.2), (12.4, 90.0)], fill=suit, outline=ink, width=0.9, smooth=True)


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


def _round_rect(
    canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, r: float, *, fill: str, outline: str = ""
) -> None:
    """A rounded rectangle, smoothed from a point list (Tk has no native rounded rect)."""
    pts = _rrect_pts(x0, y0, x1, y1, r)
    flat: list[float] = []
    for x, y in pts:
        flat += [x, y]
    canvas.create_polygon(flat, smooth=True, fill=fill, outline=outline)


def run_overlay(*, host: str = "127.0.0.1", port: int = 7420, poll: float = 1.5, scale: float = 0.78) -> None:
    """Open the frameless figure. Blocks on the Tk main loop until dismissed (Esc).

    Constructs the window only here, so importing this module (and the geometry tests) stay headless.
    """
    poller = _Poller(f"http://{host}:{port}/status.json", interval=poll)
    poller.start()

    cloud_h = 44
    w = 150
    h = int(cloud_h + FIGURE_HEIGHT * scale + 14)
    ox, oy = w / 2.0, h - 8.0

    root = tk.Tk()
    root.overrideredirect(True)              # NO title bar, NO close/min/max buttons
    root.attributes("-topmost", True)
    sw = root.winfo_screenwidth()
    root.geometry(f"{w}x{h}+{sw - w - 40}+120")
    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0, bd=0)
    canvas.pack()

    # macOS: the window must be MAPPED before -transparent takes, and every widget stacked over it
    # (here the canvas) must carry the same systemTransparent background or it paints an opaque box.
    root.update()
    transparent = True
    try:
        root.wm_attributes("-transparent", True)
        root.configure(bg="systemTransparent")
        canvas.configure(bg="systemTransparent")
        root.update_idletasks()
    except tk.TclError:
        transparent = False
        root.configure(bg="#0e0f13")
        canvas.configure(bg="#0e0f13")

    panel = _Panel(poller, transparent=transparent)
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
            panel.toggle(root)               # a click (not a drag) toggles the on-screen panel

    def shutdown() -> None:
        poller.stop()
        panel.close()
        root.destroy()

    canvas.bind("<Button-1>", press)
    canvas.bind("<B1-Motion>", motion)
    canvas.bind("<ButtonRelease-1>", release)
    root.bind("<Escape>", lambda _e: shutdown())

    frame = {"n": 0}

    def draw_cloud(state: str, accent: str) -> None:
        """A thought cloud above his head naming what he is testing, while he is active."""
        label = _testing_now(poller.data)
        if state != "evaluating" or not label:
            return
        dots = "." * (1 + frame["n"] // 8 % 3)
        text = f"testing {label}{dots}"
        width = min(w - 8.0, max(86.0, 6.6 * len(text) + 22))
        x0, x1 = (w - width) / 2, (w + width) / 2
        _round_rect(canvas, x0, 5, x1, 29, 11, fill="#1b1e26", outline=accent)
        canvas.create_text((x0 + x1) / 2, 17, text=text, fill="#f3f3f5", font=(_FONT, 9, "bold"))
        canvas.create_oval(w / 2 - 4, 30, w / 2 + 2, 36, fill="#1b1e26", outline=accent)
        canvas.create_oval(w / 2 - 1, 37, w / 2 + 3, 41, fill="#1b1e26", outline="")

    def draw() -> None:
        state = poller.state
        accent = _ACCENT.get(state, "#5e5ce6")
        t = frame["n"] / 30.0                      # 30 fps, so the motion is smooth
        canvas.delete("all")
        draw_cloud(state, accent)
        draw_figure(canvas, ox, oy, scale, pose(state, t), accent)
        frame["n"] += 1
        panel.refresh()
        root.after(33, draw)

    draw()
    root.mainloop()


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
        win.overrideredirect(True)   # the panel has no chrome either
        win.attributes("-topmost", True)
        bg = "#0e0f13"
        if self._transparent:
            try:
                win.attributes("-transparent", True)
                bg = "systemTransparent"
            except tk.TclError:
                pass
        canvas = tk.Canvas(win, width=self.W, height=self.H, bg=bg, highlightthickness=0, bd=0)
        canvas.pack()
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

        text(W / 2, H - 22, "click him to close  ·  drag to move", "#4e525c", 9, anchor="center")
