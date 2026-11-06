"""The on-screen character: a tiny vector minifigure who leans, thinks out loud, and opens a panel.

No window chrome anywhere — a frameless, transparent, always-on-top Tkinter window that draws:

* **the figure**, built from smooth vector shapes (not pixels): white fedora with a black band,
  black side locks, a printed face, a white suit over a blue shirt with a white tie, LEGO hands, and
  white legs with black shoes. He is authored once in *figure space* (origin between the feet, y
  up) and every pose is a **shear anchored at the shoes**, so the whole body tilts as one rigid
  plank — the Smooth Criminal lean — continuously rather than in steps;
* **a thought cloud above his head** naming what he is testing right now, while he is active;
* **a panel**, toggled by clicking him, that fades in beside him with the live eval report — drawn
  natively in Tk, never a browser;
* **the permission popup** (:mod:`evalloop.session.consent_popup`, EL-018) whenever the session is
  waiting to be allowed to open an endpoint, and the **Permissions view** on right-click or ``p``.

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

__all__ = ["MOOD", "PALETTE", "Pose", "pose", "FIGURE_HEIGHT", "run_overlay", "signal_line"]


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
    """One instant of the dance. Secondary-motion fields default to 0 so simpler callers stay valid."""

    lean: float          # figure units the TOP of the body travels; the shoes never move
    bob: float           # vertical lift
    arm: float           # 0 = glove hand down, 1 = raised
    hat_lag: float = 0.0  # extra lean on the hat+head only — follow-through, it trails the body
    swing: float = 0.0    # the free (hanging) arm's counter-swing
    squash: float = 0.0   # 0..1 vertical squash-and-stretch on the landing beat
    glide: float = 0.0    # horizontal moonwalk slide, in figure units; the whole figure (feet too) slides
    step: float = 0.0     # -1..1 leg beat: >0 lifts the left knee, <0 the right — the alternating step


def pose(state: str, t: float) -> Pose:
    """The pose for ``state`` at time ``t`` seconds. He MOONWALKS — a fast sideways glide with the
    signature forward lean — in every mood, hardest while evaluating and gentlest while idle, so he
    is always dancing. Continuous and eased. Pure."""
    # The moonwalk glide: a fast, smooth sideways slide the whole figure rides, phase-shifted a hair
    # behind the lean so the body tips the way it came from — the backslide illusion.
    def glide(amp: float, speed: float) -> float:
        return amp * math.sin(speed * t - 0.5)

    if state == "evaluating":
        w = 8.4  # the dance — fast, deep lean with follow-through, big backslide, pumping legs
        lean = 12.0 * math.sin(w * t)
        return Pose(
            lean=lean,
            bob=2.2 * abs(math.sin(w * t)),
            arm=0.55 + 0.45 * math.sin(2 * w * t),            # the glove pumps twice per lean
            hat_lag=4.2 * math.sin(w * (t - 0.09)) - lean * 0.35,  # trails the body
            swing=-0.6 * lean,                                 # free arm counter-swings
            squash=0.08 * abs(math.sin(2 * w * t)),
            glide=15.0 * math.sin(0.5 * w * t - 0.5),          # slides right across as he dances
            step=math.sin(w * t),                              # legs pump in time with the lean
        )
    if state == "happy":
        hop = max(0.0, math.sin(4.0 * t))                      # little hops while sliding
        return Pose(lean=1.6 * math.sin(4.0 * t), bob=4.5 * hop,
                    arm=0.5 + 0.5 * math.sin(8.0 * t),         # both hands pump
                    swing=3.0 * math.sin(4.0 * t), squash=0.12 * hop,
                    glide=glide(12.0, 4.0), step=math.sin(4.0 * t))
    if state in ("alarmed", "errored"):                        # an agitated, fast shuffle with quick feet
        return Pose(lean=-1.8 + 1.2 * math.sin(6.0 * t), bob=0.6 * abs(math.sin(6.0 * t)),
                    arm=0.3 + 0.3 * math.sin(12.0 * t), swing=2.0 * math.sin(6.0 * t),
                    hat_lag=0.7 * math.sin(6.0 * t), glide=glide(11.0, 6.0), step=math.sin(6.0 * t))
    if state == "unsure":                                      # a slower, questioning slide with a sway
        return Pose(lean=1.0 * math.sin(3.0 * t), bob=0.0,
                    arm=0.25 + 0.2 * math.sin(3.0 * t), swing=2.2 * math.sin(3.0 * t),
                    hat_lag=2.6 * math.sin(1.1 * t), glide=glide(10.0, 3.0), step=0.7 * math.sin(3.0 * t))
    # idle: a steady, gentle moonwalk — small lean (he never looks still), sliding feet, swinging arms
    return Pose(lean=2.4 * math.sin(3.2 * t), bob=0.4 * abs(math.sin(3.2 * t)),
                arm=0.2 + 0.2 * math.sin(3.2 * t), swing=2.0 * math.sin(3.2 * t),
                hat_lag=0.6 * math.sin(3.2 * t - 0.3), squash=0.03 + 0.02 * math.sin(1.3 * t),
                glide=glide(9.0, 3.2), step=0.8 * math.sin(3.2 * t))


def _ellipse_pts(cx: float, cy: float, rx: float, ry: float, n: int = 22) -> list[Point]:
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _rrect_pts(x0: float, y0: float, x1: float, y1: float, r: float) -> list[Point]:
    """Corner-duplicated points that Tk's ``smooth=True`` renders as a rounded rectangle."""
    return [(x0 + r, y0), (x1 - r, y0), (x1, y0), (x1, y0 + r), (x1, y1 - r), (x1, y1),
            (x1 - r, y1), (x0 + r, y1), (x0, y1), (x0, y1 - r), (x0, y0 + r), (x0, y0)]


def draw_figure(canvas: tk.Canvas, ox: float, oy: float, s: float, p: Pose, accent: str) -> None:
    """Draw the minifigure, feet centred at (``ox``, ``oy``), scaled by ``s``, posed by ``p``.

    Only the figure is drawn — no backdrop, no ring. Form comes from a soft second tone on his left
    (shaded) side; life comes from the pose's lean, squash and follow-through.
    """
    suit, hair, skin = PALETTE["suit"], PALETTE["hair"], PALETTE["skin"]
    shirt, tie, ink = PALETTE["shirt"], PALETTE["tie"], PALETTE["ink"]
    shade = "#dedede"   # a soft shadow tone for his left side — subtle dimension, not a hard line

    def at(x: float, y: float, extra: float = 0.0) -> Point:
        """Figure space -> canvas: squash the height, shear the lean (+``extra``), slide the glide."""
        ys = y * (1.0 - p.squash)
        xs = x * (1.0 + 0.4 * p.squash)
        dx = (p.lean + extra) * (ys / FIGURE_HEIGHT)
        return (ox + (xs + dx + p.glide) * s, oy - (ys + p.bob) * s)

    def poly(pts: Sequence[Point], fill: str, outline: str = "", width: float = 1.0,
             smooth: bool = False, extra: float = 0.0) -> None:
        flat: list[float] = []
        for x, y in pts:
            cx, cy = at(x, y, extra)
            flat += [cx, cy]
        canvas.create_polygon(flat, fill=fill, outline=outline, width=width, smooth=smooth)

    def limb(a: Point, b: Point, w: float, fill: str) -> None:
        ax, ay = at(*a)
        bx, by = at(*b)
        canvas.create_line(ax, ay, bx, by, fill=ink, width=(w + 1.3) * s, capstyle="round")
        canvas.create_line(ax, ay, bx, by, fill=fill, width=w * s, capstyle="round")

    # --- legs: white trousers (left leg shaded), black shoes + ankle band ---
    # Each leg lifts (knee bends, foot rises) on its beat, with a small sideways kick — the dance step.
    _LIFT = 7.0
    for sx in (-1, 1):
        inner, outer = sx * 1.4, sx * 12.8
        x0, x1 = min(inner, outer), max(inner, outer)
        lift = max(0.0, (p.step if sx < 0 else -p.step)) * _LIFT
        kick = lift * 0.35 * sx
        x0 += kick
        x1 += kick
        poly([(x0, 5 + lift), (x1, 5 + lift), (x1, 36), (x0, 36)], fill=shade if sx < 0 else suit, outline=ink, width=0.8)
        poly([(x0, 0 + lift), (x1, 0 + lift), (x1, 5 + lift), (x0, 5 + lift)], fill=hair, outline=ink, width=0.8)  # shoe
        poly([(x0, 8 + lift), (x1, 8 + lift), (x1, 11 + lift), (x0, 11 + lift)], fill=hair)                        # ankle band

    # --- the free (right) arm, hanging, with its counter-swing ---
    limb((-13.0, 63.0), (-18.5 + p.swing, 43.0), 5.0, suit)
    poly(_ellipse_pts(-18.5 + p.swing, 41.0, 2.7, 2.7, 14), fill=skin, outline=ink, width=0.7, smooth=True)

    # --- torso: white jacket (left side shaded), blue shirt V, white tie, belt ---
    poly([(-14.0, 36), (14.0, 36), (16.0, 64), (-16.0, 64)], fill=suit, outline=ink, width=0.9)
    poly([(-16.0, 64), (-14.0, 36), (0, 36), (0, 64)], fill=shade)                            # left-side shadow
    poly([(-6.8, 64), (6.8, 64), (0, 44)], fill=shirt)                                        # shirt V
    poly([(-2.1, 63), (2.1, 63), (1.3, 45), (-1.3, 45)], fill=tie, outline=ink, width=0.6)    # tie
    for sx in (-1, 1):                                                                         # lapel lines
        a0, a1 = at(sx * 6.8, 64), at(sx * 1.8, 45)
        canvas.create_line(*a0, *a1, fill=ink, width=0.8 * s)
    b0, b1 = at(-14.4, 39.5), at(14.4, 39.5)
    canvas.create_line(*b0, *b1, fill=ink, width=0.9 * s)                                      # belt

    # --- the glove arm, raising with the dance ---
    rx = 17.5 + 2.0 * (1 - p.arm)
    ry = 43.0 + (77.0 - 43.0) * p.arm
    limb((13.0, 63.0), (rx, ry), 5.0, suit)
    poly(_ellipse_pts(rx, ry - 1.5, 2.9, 2.9, 14), fill="#ffffff", outline=ink, width=0.7, smooth=True)

    # --- head (follows the lean with a slight lag) ---
    hat_extra = p.hat_lag
    poly([(-3.4, 63), (3.4, 63), (3.4, 67), (-3.4, 67)], fill=skin, outline=ink, width=0.6, extra=hat_extra)
    poly(_rrect_pts(-8.6, 66.5, 8.6, 85.0, 3.2), fill=skin, outline=ink, width=0.8, smooth=True, extra=hat_extra)
    poly(_rrect_pts(-8.6, 66.5, -1.0, 85.0, 3.2), fill="#e3c6a2", smooth=True, extra=hat_extra)  # cheek shade
    for sx in (-1, 1):                                                                         # eyes + brows
        poly(_ellipse_pts(sx * 3.3, 77.5, 1.05, 1.3, 12), fill=ink, smooth=True, extra=hat_extra)
        e0, e1 = at(sx * 5.0, 80.4, hat_extra), at(sx * 1.9, 81.1, hat_extra)
        canvas.create_line(*e0, *e1, fill=ink, width=1.0 * s)
    m0, m1 = at(-2.3, 72.6, hat_extra), at(2.3, 72.6, hat_extra)
    canvas.create_line(*m0, *m1, fill=ink, width=0.9 * s)                                      # mouth

    # --- hair: fringe + a lock down each side ---
    poly([(-8.7, 82.0), (8.7, 82.0), (8.7, 85.2), (-8.7, 85.2)], fill=hair, extra=hat_extra)
    poly([(-8.5, 84.5), (-11.4, 81.0), (-12.0, 73.0), (-9.6, 68.5), (-7.8, 71.0), (-8.5, 77.0)],
         fill=hair, smooth=True, extra=hat_extra)
    poly([(8.5, 84.5), (11.4, 81.0), (12.0, 74.0), (10.0, 70.0), (8.0, 72.5), (8.5, 78.0)],
         fill=hair, smooth=True, extra=hat_extra)

    # --- fedora: wide brim, black band, pinched crown ---
    poly(_ellipse_pts(0, 85.4, 21.0, 3.6, 26), fill=suit, outline=ink, width=0.8, smooth=True, extra=hat_extra)
    poly(_ellipse_pts(0, 85.6, 21.0, 2.0, 26), fill=shade, smooth=True, extra=hat_extra)       # brim underside
    poly([(-11.0, 85.6), (11.0, 85.6), (11.0, 89.0), (-11.0, 89.0)], fill=hair, extra=hat_extra)  # band
    poly([(-11.0, 88.8), (-9.6, 95.2), (-5.4, 97.4), (-1.9, 95.8), (2.0, 97.6), (5.8, 97.4),
          (9.8, 95.0), (11.0, 88.8)], fill=suit, outline=ink, width=0.8, smooth=True, extra=hat_extra)
    poly([(-11.0, 88.8), (-9.6, 95.2), (-5.4, 97.4), (-2.0, 96.2), (-2.0, 88.8)],
         fill=shade, smooth=True, extra=hat_extra)                                             # crown shadow side


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

    consent = ConsentUI(root, BotClient(host, port))
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
    for button in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):  # right-click on macOS / elsewhere
        canvas.bind(button, lambda _e: consent.open_permissions())
    root.bind("<Escape>", lambda _e: shutdown())
    root.bind("p", lambda _e: consent.open_permissions())

    frame = {"n": 0}

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
        t = frame["n"] / 30.0                      # 30 fps, so the motion is smooth
        canvas.delete("all")
        draw_cloud(state, accent)
        draw_figure(canvas, ox, oy, scale, pose(state, t), accent)
        if frame["n"] % 15 == 0:                   # twice a second: a permission waiting? show it
            consent.update(poller.data)
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

        text(W / 2, H - 22, "click: close  ·  right-click: permissions  ·  drag", "#4e525c", 9, anchor="center")
