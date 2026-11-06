"""Dancing avatars: original characters, their dances, and one renderer that every surface shares.

The desktop pets (Tk and Qt) and the dashboard page draw the same characters doing the same dances.
Everything here is data plus a small engine, and the page's JavaScript port runs the same numbers on
the same data (a test runs both and compares them):

* **A skeleton** in figure space (y up, feet at y=0, about 100 units tall): hips, torso, head, and on
  each side an upper arm, forearm and hand, plus legs solved by two-bone IK, so a squat keeps the
  feet on the floor. There are two body types: the classic minifigure (``fig``) and a taller
  ``dancer``.
* **Characters** are lists of flat shapes pinned to bones, plus a palette. Skin tone and outfit
  colour can be changed per character.
* **Dances** are keyframes of named channels (hip drop, shoulder raise, foot lift, gaze, a spin…),
  sampled with a looping Catmull–Rom spline. The bot's mood sets the tempo and how fully the dance
  is performed: full while evaluating, gentle while idle, a jittery half-dance when alarmed.
* **The renderer** turns a character and a pose into plain polygons and lines in figure space; each
  surface only maps those to pixels.

The characters are original: Smooth (the classic moonwalking minifigure), Zuri (twerk), Mira
(Bharatanatyam: the aramandi half-sit, tatta and natta adavus, pataka and alapadma mudras, ghungroo
and the pleated fan that opens as the knees bend), and Luz (salsa: the basic step with Cuban hip
motion and a turn that flares the skirt). Any character can do any dance.

The choice (which character is the desktop pet, who is on the page's stage, and each one's dance
and look) is normalised by :func:`normalize_choice` and kept by the session.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "FIGURE_HEIGHT",
    "PALETTE",
    "Animator",
    "Pose",
    "catalog",
    "channels",
    "cycle",
    "default_choice",
    "load_choice",
    "normalize_choice",
    "pet_of",
    "pose",
    "pose_prims",
    "save_choice",
]

#: The figure is authored in these units, feet at y=0, top of the head at about FIGURE_HEIGHT.
FIGURE_HEIGHT = 100.0

J = dict[str, Any]
Prim = dict[str, Any]

# -- the classic moonwalk, as it was first written (its keyframes are sampled from this) -------------

#: Smooth's colours, as the classic figure named them.
PALETTE = {
    "suit": "#f6f6f3",   # white fedora, jacket, trousers
    "hair": "#121216",   # black hair, hat band, shoes
    "skin": "#eab988",   # face and hands
    "shirt": "#1f8fe0",  # blue shirt
    "tie": "#ffffff",    # white tie
    "ink": "#1b1d23",    # printed outlines
}


@dataclass(frozen=True, slots=True)
class Pose:
    """One instant of the classic moonwalk. Secondary-motion fields default to 0."""

    lean: float          # figure units the TOP of the body travels; the shoes never move
    bob: float           # vertical lift
    arm: float           # 0 = glove hand down, 1 = raised
    hat_lag: float = 0.0  # extra lean on the hat+head only: follow-through, it trails the body
    swing: float = 0.0    # the free (hanging) arm's counter-swing
    squash: float = 0.0   # 0..1 vertical squash-and-stretch on the landing beat
    glide: float = 0.0    # horizontal moonwalk slide, in figure units
    step: float = 0.0     # -1..1 leg beat: >0 lifts the left knee, <0 the right


def pose(state: str, t: float) -> Pose:
    """The classic moonwalk for ``state`` at time ``t`` seconds. Continuous and pure."""
    def glide(amp: float, speed: float) -> float:
        return amp * math.sin(speed * t - 0.5)

    if state == "evaluating":
        w = 8.4
        lean = 12.0 * math.sin(w * t)
        return Pose(
            lean=lean,
            bob=2.2 * abs(math.sin(w * t)),
            arm=0.55 + 0.45 * math.sin(2 * w * t),
            hat_lag=4.2 * math.sin(w * (t - 0.09)) - lean * 0.35,
            swing=-0.6 * lean,
            squash=0.08 * abs(math.sin(2 * w * t)),
            glide=15.0 * math.sin(0.5 * w * t - 0.5),
            step=math.sin(w * t),
        )
    if state == "happy":
        hop = max(0.0, math.sin(4.0 * t))
        return Pose(lean=1.6 * math.sin(4.0 * t), bob=4.5 * hop, arm=0.5 + 0.5 * math.sin(8.0 * t),
                    swing=3.0 * math.sin(4.0 * t), squash=0.12 * hop, glide=glide(12.0, 4.0), step=math.sin(4.0 * t))
    if state in ("alarmed", "errored"):
        return Pose(lean=-1.8 + 1.2 * math.sin(6.0 * t), bob=0.6 * abs(math.sin(6.0 * t)),
                    arm=0.3 + 0.3 * math.sin(12.0 * t), swing=2.0 * math.sin(6.0 * t),
                    hat_lag=0.7 * math.sin(6.0 * t), glide=glide(11.0, 6.0), step=math.sin(6.0 * t))
    if state == "unsure":
        return Pose(lean=1.0 * math.sin(3.0 * t), bob=0.0, arm=0.25 + 0.2 * math.sin(3.0 * t),
                    swing=2.2 * math.sin(3.0 * t), hat_lag=2.6 * math.sin(1.1 * t), glide=glide(10.0, 3.0),
                    step=0.7 * math.sin(3.0 * t))
    return Pose(lean=2.4 * math.sin(3.2 * t), bob=0.4 * abs(math.sin(3.2 * t)), arm=0.2 + 0.2 * math.sin(3.2 * t),
                swing=2.0 * math.sin(3.2 * t), hat_lag=0.6 * math.sin(3.2 * t - 0.3),
                squash=0.03 + 0.02 * math.sin(1.3 * t), glide=glide(9.0, 3.2), step=0.8 * math.sin(3.2 * t))


# -- the skeleton -------------------------------------------------------------------------------------

BODIES: dict[str, dict[str, float]] = {
    "fig": {"hip_y": 36.0, "hip_x": 7.1, "thigh": 18.0, "shin": 16.0, "ankle_y": 2.0,
            "shoulder_x": 13.0, "shoulder_y": 27.0, "neck_y": 27.0, "upper": 10.0, "fore": 10.0},
    "dancer": {"hip_y": 46.0, "hip_x": 6.5, "thigh": 23.0, "shin": 21.0, "ankle_y": 2.0,
               "shoulder_x": 11.5, "shoulder_y": 23.0, "neck_y": 23.5, "upper": 12.5, "fore": 12.0},
}

#: Every channel a dance can drive, at rest. Angles are degrees; ``drop`` is a fraction of the leg.
REST: dict[str, float] = {
    "x": 0.0, "bob": 0.0, "sx": 1.0, "squash": 0.0,
    "drop": 0.0, "hip_x": 0.0, "pelvis": 0.0, "torso": 0.0, "pitch": 0.0, "head": 0.0, "head_x": 0.0,
    "sh_l": 6.0, "sh_r": 6.0, "el_l": 0.0, "el_r": 0.0, "wr_l": 0.0, "wr_r": 0.0,
    "ft_l_x": 0.0, "ft_r_x": 0.0, "ft_l_y": 0.0, "ft_r_y": 0.0, "knee_out": 0.6, "toe_l": 0.0, "toe_r": 0.0,
    "gaze": 0.0, "flare": 0.0, "mouth": 0.0, "mudra_l": 0.0, "mudra_r": 0.0,
}
#: Channels that switch rather than glide (a hand shape, a mouth shape).
DISCRETE = ("mouth", "mudra_l", "mudra_r")

#: How the mood performs a dance: (tempo, amplitude).
TEMPO: dict[str, list[float]] = {
    "evaluating": [1.0, 1.0], "happy": [1.08, 1.0], "idle": [0.55, 0.5],
    "unsure": [0.6, 0.55], "alarmed": [1.35, 0.45], "errored": [1.35, 0.45],
}


def _catmull(a: float, b: float, c: float, d: float, u: float) -> float:
    return 0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u * u + (-a + 3 * b - 3 * c + d) * u * u * u)


def channels(dance: Mapping[str, Any], phase: float, amp: float) -> dict[str, float]:
    """The pose channels of ``dance`` at ``phase`` (in keyframes), performed at ``amp`` (0..1)."""
    keys: Sequence[Mapping[str, float]] = dance["keys"]
    base: Mapping[str, float] = dance.get("base", {})
    n = len(keys)
    p = phase % n
    i = int(p)
    u = p - i
    out: dict[str, float] = {}
    for name, rest in REST.items():
        def at(k: int) -> float:
            return float(keys[k % n].get(name, base.get(name, rest)))

        if name in DISCRETE:
            out[name] = at(i)
            continue
        v = _catmull(at(i - 1), at(i), at(i + 1), at(i + 2), u)
        if name == "sx":
            spin = min(1.0, max(0.0, (amp - 0.8) / 0.2))
            out[name] = 1.0 + spin * (v - 1.0)
        else:
            out[name] = rest + amp * (v - rest)
    out["drop"] = max(0.0, out["drop"])
    out["ft_l_y"] = max(0.0, out["ft_l_y"])
    out["ft_r_y"] = max(0.0, out["ft_r_y"])
    out["flare"] = min(1.0, max(0.0, out["flare"]))
    out["knee_out"] = min(1.0, max(0.0, out["knee_out"]))
    out["sx"] = min(1.0, max(-1.0, out["sx"]))
    return out


class Animator:
    """Plays a dance over real time: phase advances with the mood's tempo, amplitude eases between moods.

    Stateful so a change of mood never jumps the pose: the phase is integrated, not recomputed from
    the clock, and amplitude, alarm and doubt ease towards their targets.
    """

    def __init__(self) -> None:
        self.phase = 0.0
        self.amp = 0.5
        self.alarm = 0.0
        self.doubt = 0.0
        self.t = 0.0

    def advance(self, dt: float, dance: Mapping[str, Any], state: str) -> dict[str, float]:
        tempo, amp = TEMPO.get(state, TEMPO["idle"])
        dt = min(0.25, max(0.0, dt))
        self.t += dt
        n = len(dance["keys"])
        self.phase = (self.phase + dt * tempo / float(dance["key_seconds"])) % n
        ease = min(1.0, dt * 3.0)
        self.amp += (amp - self.amp) * ease
        self.alarm += ((1.0 if state in ("alarmed", "errored") else 0.0) - self.alarm) * ease
        self.doubt += ((1.0 if state == "unsure" else 0.0) - self.doubt) * ease
        ch = channels(dance, self.phase, self.amp)
        ch["x"] += 1.3 * self.alarm * math.sin(self.t * 38.0)
        ch["head"] += 9.0 * self.doubt * math.sin(self.t * 1.4)
        if self.alarm > 0.5:
            ch["mouth"] = 2.0
        return ch


@dataclass(frozen=True, slots=True)
class _Frame:
    ox: float
    oy: float
    ang: float
    sy: float = 1.0

    def at(self, x: float, y: float) -> tuple[float, float]:
        r = self.ang * math.pi / 180.0
        c, s = math.cos(r), math.sin(r)
        y = y * self.sy
        return (self.ox + x * c - y * s, self.oy + x * s + y * c)


Point = tuple[float, float]


def _knee(h: Point, f: Point, l1: float, l2: float, sign: float, out: float) -> Point:
    """Two-bone IK: the knee for a hip ``h`` and ankle ``f``, bending outward by ``out`` (0..1)."""
    dx, dy = f[0] - h[0], f[1] - h[1]
    d = math.sqrt(dx * dx + dy * dy)
    if d >= l1 + l2 or d < 1e-6:
        k = l1 / (l1 + l2)
        return (h[0] + dx * k, h[1] + dy * k)
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d)
    alpha = math.acos(min(1.0, max(-1.0, cos_a)))
    theta = math.atan2(dy, dx) + sign * alpha
    full = (h[0] + l1 * math.cos(theta), h[1] + l1 * math.sin(theta))
    t = ((full[0] - h[0]) * dx + (full[1] - h[1]) * dy) / (d * d)
    px, py = h[0] + t * dx, h[1] + t * dy
    return (px + out * (full[0] - px), py + out * (full[1] - py))


def _skeleton(body: Mapping[str, float], ch: Mapping[str, float]) -> tuple[dict[str, _Frame], dict[str, tuple[Point, Point, Point]]]:
    leg = body["thigh"] + body["shin"]
    hx, hy = ch["hip_x"], body["hip_y"] - ch["drop"] * leg
    pelvis = _Frame(hx, hy, ch["pelvis"])
    torso = _Frame(hx, hy, ch["pelvis"] + ch["torso"], math.cos(ch["pitch"] * math.pi / 180.0))
    nx, ny = torso.at(ch["head_x"], body["neck_y"])
    frames = {"pelvis": pelvis, "torso": torso, "head": _Frame(nx, ny, torso.ang + ch["head"])}
    legs: dict[str, tuple[Point, Point, Point]] = {}
    for side, sign in (("r", 1.0), ("l", -1.0)):
        sx, sy = torso.at(sign * body["shoulder_x"], body["shoulder_y"])
        upper = _Frame(sx, sy, torso.ang + sign * ch["sh_" + side])
        ex, ey = upper.at(0.0, -body["upper"])
        fore = _Frame(ex, ey, upper.ang + sign * ch["el_" + side])
        wx, wy = fore.at(0.0, -body["fore"])
        frames["upper_" + side] = upper
        frames["fore_" + side] = fore
        frames["hand_" + side] = _Frame(wx, wy, fore.ang + sign * ch["wr_" + side])
        hip = pelvis.at(sign * body["hip_x"], 0.0)
        foot = (sign * (body["hip_x"] + ch["ft_" + side + "_x"]), body["ankle_y"] + ch["ft_" + side + "_y"])
        knee = _knee(hip, foot, body["thigh"], body["shin"], sign, ch["knee_out"])
        legs[side] = (hip, knee, foot)
        frames["ankle_" + side] = _Frame(foot[0], foot[1], sign * ch["toe_" + side])
    return frames, legs


# -- the renderer ---------------------------------------------------------------------------------------

_SIDE_BONES = ("upper", "fore", "hand", "ankle")


def _copies(part: Mapping[str, Any]) -> list[tuple[str, float]]:
    """(bone, mirror sign) for each copy of a part. Side bones get both sides unless ``side`` limits it."""
    on = str(part.get("on", ""))
    if on in _SIDE_BONES:
        sides = [part["side"]] if part.get("side") else ["r", "l"]
        return [(f"{on}_{s}", 1.0 if s == "r" else -1.0) for s in sides]
    return [(on, 1.0)] + ([(on, -1.0)] if part.get("both") else [])


def _color(palette: Mapping[str, str], name: object, hand: str | None = None) -> str | None:
    if name is None:
        return None
    key = str(name)
    if key == "$":
        return hand
    if key.startswith("#"):
        return key
    return palette.get(key, "#ff00ff")


def _visible(part: Mapping[str, Any], ch: Mapping[str, float]) -> bool:
    face = part.get("face")
    if face is not None and (ch["sx"] >= 0.0) != (face == "front"):
        return False
    when = part.get("when")
    if when is not None and int(ch[str(when[0])] + 0.5) != int(when[1]):
        return False
    return True


def pose_prims(char_id: str, ch: Mapping[str, float], *, skin: int | None = None, outfit: int | None = None) -> list[Prim]:
    """Draw ``char_id`` in pose ``ch``: polygons and lines in figure space (y up, feet at y=0).

    A ``poly`` prim is ``{"k": "poly", "p": [x0, y0, ...], "f": fill or None, "o": outline or None,
    "w": outline width}``; a ``line`` prim is ``{"k": "line", "p": [x0, y0, x1, y1], "c": colour,
    "w": width, "r": round caps}``. Widths are in figure units.
    """
    cat = catalog()
    char = cat["characters"][char_id]
    palette = look_palette(char_id, skin, outfit)
    frames, legs = _skeleton(cat["bodies"][char["body"]], ch)
    ink = palette["ink"]
    spin = ch["sx"] * (1.0 + 0.4 * ch["squash"])
    squash = 1.0 - ch["squash"]

    def world(x: float, y: float) -> Point:
        return (ch["x"] + x * spin, y * squash + ch["bob"])

    def flat(points: Sequence[Point]) -> list[float]:
        out: list[float] = []
        for x, y in points:
            wx, wy = world(x, y)
            out += [wx, wy]
        return out

    prims: list[Prim] = []

    def emit_local(part: Mapping[str, Any], frame: _Frame, sign: float, hand: str | None = None) -> None:
        shift = part.get("shift")
        dx = dy = 0.0
        if shift is not None:
            dx, dy = ch[str(shift[0])] * float(shift[1]), ch[str(shift[0])] * float(shift[2])
        raw: Sequence[float] = part["p"]
        pts = [frame.at(sign * raw[j] + dx, raw[j + 1] + dy) for j in range(0, len(raw), 2)]
        fill = _color(palette, part.get("fl") if sign < 0 and part.get("fl") else part.get("f"), hand)
        kind = part["t"]
        if kind == "poly":
            prims.append({"k": "poly", "p": flat(pts), "f": fill, "o": _color(palette, part.get("o"), hand),
                          "w": float(part.get("w", 1.0))})
        elif kind == "line":
            prims.append({"k": "line", "p": flat(pts), "c": _color(palette, part.get("c"), hand) or ink,
                          "w": float(part.get("w", 1.0)), "r": bool(part.get("r", True))})
        elif kind == "limb":
            w = float(part["w"])
            prims.append({"k": "line", "p": flat(pts), "c": ink, "w": w + 1.3, "r": True})
            prims.append({"k": "line", "p": flat(pts), "c": fill or ink, "w": w, "r": True})

    for part in char["parts"]:
        if not _visible(part, ch):
            continue
        kind = part["t"]
        if kind == "seg":
            for side in ([part["side"]] if part.get("side") else ["r", "l"]):
                hip, knee, foot = legs[side]
                upper, lower = (hip, knee) if part["seg"] == "thigh" else (knee, foot)
                band = part.get("band")
                if band is not None:
                    a, b = float(band[0]), float(band[1])
                    upper, lower = ((lower[0] + b * (upper[0] - lower[0]), lower[1] + b * (upper[1] - lower[1])),
                                    (lower[0] + a * (upper[0] - lower[0]), lower[1] + a * (upper[1] - lower[1])))
                fill = _color(palette, part.get("fl") if side == "l" and part.get("fl") else part.get("f"))
                w = float(part["w"])
                if part.get("box"):
                    ux, uy = lower[0] - upper[0], lower[1] - upper[1]
                    length = math.sqrt(ux * ux + uy * uy) or 1.0
                    nx_, ny_ = -uy / length * w / 2.0, ux / length * w / 2.0
                    quad = [(upper[0] + nx_, upper[1] + ny_), (lower[0] + nx_, lower[1] + ny_),
                            (lower[0] - nx_, lower[1] - ny_), (upper[0] - nx_, upper[1] - ny_)]
                    prims.append({"k": "poly", "p": flat(quad), "f": fill,
                                  "o": _color(palette, part.get("o")), "w": float(part.get("ow", 0.8))})
                else:
                    seg = flat([upper, lower])
                    if band is None:
                        prims.append({"k": "line", "p": seg, "c": ink, "w": w + 1.3, "r": True})
                    prims.append({"k": "line", "p": seg, "c": fill or ink, "w": w, "r": band is None})
        elif kind == "fan":
            crotch = frames["pelvis"].at(0.0, -2.5)
            kl, kr = legs["l"][1], legs["r"][1]
            bottom = ((kl[0] + kr[0]) / 2.0, (kl[1] + kr[1]) / 2.0 - float(part["depth"]))
            prims.append({"k": "poly", "p": flat([crotch, kl, bottom, kr]), "f": _color(palette, part["f"]),
                          "o": _color(palette, part.get("o")), "w": float(part.get("w", 0.8))})
            n = int(part["n"])
            for j in range(1, n):
                u = j / n
                if u <= 0.5:
                    v = u * 2.0
                    tip = (kl[0] + v * (bottom[0] - kl[0]), kl[1] + v * (bottom[1] - kl[1]))
                else:
                    v = (u - 0.5) * 2.0
                    tip = (bottom[0] + v * (kr[0] - bottom[0]), bottom[1] + v * (kr[1] - bottom[1]))
                prims.append({"k": "line", "p": flat([crotch, tip]), "c": _color(palette, part["pleat"]) or ink,
                              "w": 0.45, "r": False})
        elif kind == "skirt":
            pelvis = frames["pelvis"]
            flare = ch["flare"]
            half_hem = (float(part["hw"]) + float(part["fw"]) * flare) / 2.0
            half_waist = float(part["ww"]) / 2.0
            wy, hy = float(part["wy"]), float(part["hy"]) + 4.0 * flare
            n = int(part["n"])
            for tier, (inset, color) in enumerate(((0.0, part["f"]), (2.6, part["trim"]))):
                y0 = hy + inset
                pts: list[Point] = [(-half_waist, wy), (half_waist, wy)] if tier == 0 else [
                    (-half_hem + 0.4, y0 + 2.2), (half_hem - 0.4, y0 + 2.2)]
                for j in range(n * 2, -1, -1):
                    x = -half_hem + (2.0 * half_hem) * j / (n * 2)
                    dip = 1.6 if j % 2 == 1 else 0.0
                    pts.append((x, y0 - dip))
                world_pts = [pelvis.at(x, y) for x, y in pts]
                prims.append({"k": "poly", "p": flat(world_pts), "f": _color(palette, color),
                              "o": _color(palette, part.get("o")), "w": float(part.get("w", 0.7))})
        elif kind == "hand":
            for bone, sign in _copies({"on": "hand", "side": part.get("side")}):
                side = bone[-1]
                fill = _color(palette, part.get("fl") if side == "l" and part.get("fl") else part.get("f"))
                for shape in cat["mudras"][str(int(ch["mudra_" + side] + 0.5))]:
                    emit_local(shape, frames[bone], sign, fill)
        else:
            for bone, sign in _copies(part):
                emit_local(part, frames[bone], sign)
    return prims


# -- building the characters ------------------------------------------------------------------------


def _chaikin(points: list[Point], rounds: int) -> list[Point]:
    for _ in range(rounds):
        out: list[Point] = []
        for i, (x0, y0) in enumerate(points):
            x1, y1 = points[(i + 1) % len(points)]
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        points = out
    return points


def _flat(points: Sequence[Point]) -> list[float]:
    return [round(v, 4) for p in points for v in p]


def _poly(on: str, points: Sequence[Point], f: str | None, o: str | None = None, w: float = 0.8,
          smooth: int = 0, **mods: Any) -> J:
    pts = _chaikin(list(points), smooth) if smooth else list(points)
    return {"t": "poly", "on": on, "p": _flat(pts), "f": f, "o": o, "w": w, **mods}


def _ellipse(on: str, cx: float, cy: float, rx: float, ry: float, f: str | None, o: str | None = None,
             w: float = 0.8, n: int = 18, **mods: Any) -> J:
    pts = [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return _poly(on, pts, f, o, w, **mods)


def _rrect(on: str, x0: float, y0: float, x1: float, y1: float, r: float, f: str | None, o: str | None = None,
           w: float = 0.8, **mods: Any) -> J:
    pts: list[Point] = []
    for cx, cy, start in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        for k in range(5):
            a = (start + 22.5 * k) * math.pi / 180.0
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return _poly(on, pts, f, o, w, **mods)


def _line(on: str, a: Point, b: Point, c: str = "ink", w: float = 0.8, r: bool = True, **mods: Any) -> J:
    return {"t": "line", "on": on, "p": _flat([a, b]), "c": c, "w": w, "r": r, **mods}


def _limb(on: str, a: Point, b: Point, f: str, w: float, **mods: Any) -> J:
    return {"t": "limb", "on": on, "p": _flat([a, b]), "f": f, "w": w, **mods}


def _seg(seg: str, f: str, w: float, **mods: Any) -> J:
    return {"t": "seg", "seg": seg, "f": f, "w": w, **mods}


def _eyes_and_mouth(lip: str, *, eye_y: float = 12.6, lashes: bool = True) -> list[J]:
    parts = [
        _ellipse("head", 3.2, eye_y, 1.25, 1.6, "ink", both=True, face="front", shift=["gaze", 0.8, 0.0], n=14),
        _ellipse("head", 3.55, eye_y + 0.65, 0.42, 0.42, "#ffffff", both=True, face="front", shift=["gaze", 0.8, 0.0], n=8),
        _line("head", (1.7, eye_y + 4.4), (4.9, eye_y + 3.9), w=0.9, both=True, face="front"),
        _line("head", (-2.2, 7.4), (2.2, 7.4), w=0.9, face="front", when=["mouth", 0]),
        _poly("head", [(-2.6, 8.2), (-1.3, 6.9), (0.0, 6.6), (1.3, 6.9), (2.6, 8.2), (1.3, 7.7), (0.0, 7.5), (-1.3, 7.7)],
              lip, face="front", when=["mouth", 1]),
        _ellipse("head", 0.0, 7.2, 1.5, 1.8, lip, "ink", 0.5, face="front", when=["mouth", 2], n=12),
    ]
    if lashes:
        parts.insert(2, _line("head", (4.3, eye_y + 1.3), (5.4, eye_y + 2.3), w=0.7, both=True, face="front"))
    return parts


def _smooth_parts() -> list[J]:
    """The classic minifigure, shape for shape, on the fig skeleton (torso from the hips, head from the neck)."""
    return [
        _seg("shin", "outfit", 11.4, box=True, o="ink", fl="outfit2"),
        _seg("thigh", "outfit", 11.4, box=True, o="ink", fl="outfit2"),
        _seg("shin", "hair", 11.4, box=True, band=[0.375, 0.5625]),
        _rrect("ankle", -5.7, -2.0, 5.7, 3.0, 0.6, "hair", "ink", 0.8),
        # the free arm hangs behind the jacket; the glove arm is drawn in front
        _limb("upper", (0, 0), (0, -10.0), "outfit", 5.0, side="l"),
        _limb("fore", (0, 0), (0, -10.0), "outfit", 5.0, side="l"),
        {"t": "hand", "f": "skin", "side": "l"},
        _poly("torso", [(-14.0, 0), (14.0, 0), (16.0, 28), (-16.0, 28)], "outfit", "ink", 0.9),
        _poly("torso", [(-16.0, 28), (-14.0, 0), (0, 0), (0, 28)], "outfit2"),
        _poly("torso", [(-6.8, 28), (6.8, 28), (0, 8)], "shirt"),
        _poly("torso", [(-2.1, 27), (2.1, 27), (1.3, 9), (-1.3, 9)], "tie", "ink", 0.6),
        _line("torso", (6.8, 28), (1.8, 9), w=0.8, both=True),
        _line("torso", (-14.4, 3.5), (14.4, 3.5), w=0.9),
        _limb("upper", (0, 0), (0, -10.0), "outfit", 5.0, side="r"),
        _limb("fore", (0, 0), (0, -10.0), "outfit", 5.0, side="r"),
        {"t": "hand", "f": "glove", "side": "r"},
        _poly("head", [(-3.4, 0), (3.4, 0), (3.4, 4), (-3.4, 4)], "skin", "ink", 0.6),
        _rrect("head", -8.6, 3.5, 8.6, 22.0, 3.2, "skin", "ink", 0.8),
        _rrect("head", -8.6, 3.5, -1.0, 22.0, 3.2, "skin2", face="front"),
        _rrect("head", -8.6, 3.5, 8.6, 22.0, 3.2, "hair", face="back"),
        _ellipse("head", 3.3, 14.5, 1.05, 1.3, "ink", both=True, face="front", shift=["gaze", 0.7, 0.0], n=12),
        _line("head", (5.0, 17.4), (1.9, 18.1), w=1.0, both=True, face="front"),
        _line("head", (-2.3, 9.6), (2.3, 9.6), w=0.9, face="front", when=["mouth", 0]),
        _poly("head", [(-2.4, 10.2), (0.0, 8.6), (2.4, 10.2), (0.0, 9.4)], "ink", face="front", when=["mouth", 1]),
        _ellipse("head", 0.0, 9.6, 1.3, 1.6, "#8a2b2b", "ink", 0.5, face="front", when=["mouth", 2], n=10),
        _poly("head", [(-8.7, 19.0), (8.7, 19.0), (8.7, 22.2), (-8.7, 22.2)], "hair"),
        _poly("head", [(-8.5, 21.5), (-11.4, 18.0), (-12.0, 10.0), (-9.6, 5.5), (-7.8, 8.0), (-8.5, 14.0)],
              "hair", smooth=2, both=True),
        _ellipse("head", 0, 22.4, 21.0, 3.6, "outfit", "ink", 0.8, n=26),
        _ellipse("head", 0, 22.6, 21.0, 2.0, "outfit2", n=26),
        _poly("head", [(-11.0, 22.6), (11.0, 22.6), (11.0, 26.0), (-11.0, 26.0)], "hair"),
        _poly("head", [(-11.0, 25.8), (-9.6, 32.2), (-5.4, 34.4), (-1.9, 32.8), (2.0, 34.6), (5.8, 34.4),
                       (9.8, 32.0), (11.0, 25.8)], "outfit", "ink", 0.8, smooth=2),
        _poly("head", [(-11.0, 25.8), (-9.6, 32.2), (-5.4, 34.4), (-2.0, 33.2), (-2.0, 25.8)], "outfit2", smooth=2),
    ]


def _dancer_head(*, hair: list[J], extras: list[J], back: list[J], lip: str) -> list[J]:
    return [
        _rrect("head", -2.9, -1.0, 2.9, 4.0, 1.0, "skin", "ink", 0.6),
        _rrect("head", -8.4, 2.6, 8.4, 21.0, 4.2, "skin", "ink", 0.8),
        _rrect("head", -8.4, 2.6, -1.6, 21.0, 4.2, "skin2", face="front"),
        *_eyes_and_mouth(lip),
        _ellipse("head", 5.7, 9.4, 1.4, 0.8, "blush", both=True, face="front", n=10),
        *hair,
        *extras,
        _rrect("head", -8.4, 2.6, 8.4, 21.0, 4.2, "hair", face="back"),
        *back,
    ]


def _zuri_parts() -> list[J]:
    return [
        _seg("thigh", "pants", 10.0, fl="pants2"),
        _seg("shin", "pants", 9.0, fl="pants2"),
        _seg("shin", "pants2", 9.4, band=[0.0, 0.12]),
        _rrect("ankle", -3.6, -2.2, 5.8, 2.8, 1.6, "shoe", "ink", 0.7),
        _rrect("ankle", -3.8, -2.4, 6.0, -0.9, 0.7, "sole"),
        _poly("ankle", [(-1.0, 0.2), (3.6, 0.2), (4.6, 1.7), (0.0, 1.7)], "outfit"),
        _rrect("torso", -8.6, -1.5, 8.6, 3.2, 1.2, "pants2", "ink", 0.7),
        _rrect("torso", -7.4, 2.6, 7.4, 8.4, 2.0, "skin", "ink", 0.6),
        _ellipse("torso", 0.0, 22.6, 7.6, 3.2, "outfit2", "ink", 0.6),
        _poly("torso", [(-9.4, 7.6), (9.4, 7.6), (11.6, 22.8), (-11.6, 22.8)], "outfit", "ink", 0.9),
        _rrect("torso", -9.6, 7.2, 9.6, 9.8, 1.0, "outfit2"),
        _poly("torso", [(-5.5, 9.8), (5.5, 9.8), (4.2, 14.6), (-4.2, 14.6)], "outfit2"),
        _line("torso", (2.0, 21.6), (2.4, 16.0), c="#ffffff", w=0.7, both=True),
        _limb("upper", (0, 0), (0, -12.5), "outfit", 5.6),
        _limb("fore", (0, 0), (0, -12.0), "outfit", 5.0),
        _line("fore", (0, -10.6), (0, -12.0), c="outfit2", w=5.2, r=False),
        {"t": "hand", "f": "skin"},
        *_dancer_head(
            lip="lip",
            hair=[
                _poly("head", [(-8.9, 15.0), (-8.5, 20.6), (-5.0, 23.4), (0.0, 24.2), (5.0, 23.4), (8.5, 20.6),
                               (8.9, 15.0), (6.6, 19.2), (0.0, 20.4), (-6.6, 19.2)], "hair", smooth=2),
                _ellipse("head", 0.0, 28.4, 8.6, 6.6, "hair", "ink", 0.6, n=22),
                _ellipse("head", -2.6, 30.4, 2.6, 1.6, "hair2", n=12),
                _rrect("head", -3.8, 22.4, 3.8, 24.6, 0.8, "outfit"),
            ],
            extras=[_ellipse("head", 9.0, 8.4, 1.9, 2.4, None, "gold", 0.9, both=True, n=14)],
            back=[],
        ),
    ]


def _mira_parts() -> list[J]:
    return [
        _seg("thigh", "outfit", 10.5, fl="outfit2"),
        _seg("shin", "outfit", 9.0, fl="outfit2"),
        _seg("shin", "gold", 9.4, band=[0.0, 0.14]),
        {"t": "fan", "f": "outfit2", "o": "gold", "w": 0.8, "pleat": "gold2", "depth": 6.0, "n": 6},
        _poly("ankle", [(-3.0, -2.0), (4.6, -2.0), (5.0, -0.6), (3.2, 1.4), (-1.8, 1.8), (-3.0, 0.2)],
              "skin", "ink", 0.6, smooth=1),
        _line("ankle", (-2.6, -2.0), (4.4, -2.0), c="alta", w=0.9),
        *[_ellipse("ankle", x, 3.4, 0.85, 0.85, "gold", "gold2", 0.3, n=8) for x in (-2.6, -1.0, 0.6, 2.2)],
        _poly("torso", [(-9.4, -1.0), (9.4, -1.0), (8.6, 6.0), (-8.6, 6.0)], "outfit", "ink", 0.7),
        _rrect("torso", -7.6, 6.0, 7.6, 9.6, 1.5, "skin"),
        _rrect("torso", -9.0, 4.4, 9.0, 7.2, 1.3, "gold", "gold2", 0.6),
        _ellipse("torso", 0.0, 5.8, 2.1, 1.9, "gold", "gold2", 0.5, n=12),
        _ellipse("torso", 0.0, 5.8, 0.8, 0.8, "alta", n=8),
        _poly("torso", [(-8.4, 9.4), (8.4, 9.4), (10.6, 22.6), (-10.6, 22.6)], "outfit", "ink", 0.8),
        _rrect("torso", -8.6, 9.2, 8.6, 10.6, 0.5, "gold"),
        _poly("torso", [(6.4, 9.6), (9.6, 9.6), (-6.5, 23.2), (-10.4, 22.4)], "outfit2"),
        _line("torso", (9.6, 9.6), (-6.5, 23.2), c="gold", w=0.9),
        _poly("torso", [(-5.0, 23.0), (-3.2, 19.6), (0.0, 18.6), (3.2, 19.6), (5.0, 23.0), (3.6, 20.6), (0.0, 19.8),
                        (-3.6, 20.6)], "gold", smooth=1),
        _ellipse("torso", 0.0, 18.8, 1.2, 1.4, "gold", "gold2", 0.4, n=10),
        _limb("upper", (0, 0), (0, -12.5), "skin", 4.8),
        _limb("upper", (0, 0), (0, -3.4), "outfit", 5.4),
        _line("upper", (-2.6, -6.2), (2.6, -6.6), c="gold", w=1.1, r=False),
        _limb("fore", (0, 0), (0, -12.0), "skin", 4.2),
        _line("fore", (-2.3, -9.0), (2.3, -9.0), c="gold", w=0.9, r=False),
        _line("fore", (-2.3, -10.4), (2.3, -10.4), c="gold", w=0.9, r=False),
        {"t": "hand", "f": "skin"},
        _ellipse("head", 0.0, 23.6, 6.4, 2.8, "jasmine", "#cfcfc2", 0.5, n=18),
        *_dancer_head(
            lip="lip",
            hair=[
                _poly("head", [(-8.9, 9.0), (-9.4, 16.0), (-8.2, 21.2), (-4.5, 23.6), (0.0, 24.2), (4.5, 23.6),
                               (8.2, 21.2), (9.4, 16.0), (8.9, 9.0), (8.0, 13.5), (6.6, 19.0), (2.0, 20.6),
                               (0.0, 19.6), (-2.0, 20.6), (-6.6, 19.0), (-8.0, 13.5)], "hair", smooth=2),
            ],
            extras=[
                _line("head", (0.0, 19.6), (0.0, 17.4), c="gold", w=0.8, face="front"),
                _ellipse("head", 0.0, 16.8, 1.0, 1.2, "gold", "gold2", 0.3, face="front", n=10),
                _ellipse("head", 0.0, 15.0, 0.55, 0.55, "alta", face="front", n=8),
                _ellipse("head", -6.4, 21.0, 1.7, 1.7, "gold", "gold2", 0.4, face="front", n=12),
                _poly("head", [(5.0, 22.4), (6.6, 19.4), (8.0, 22.2), (6.6, 20.8)], "silver", smooth=1, face="front"),
                _ellipse("head", 1.5, 9.6, 0.9, 0.9, None, "gold", 0.5, face="front", n=10),
                _ellipse("head", 8.8, 8.6, 1.2, 1.2, "gold", both=True, n=10),
                _poly("head", [(7.8, 7.4), (9.8, 7.4), (10.4, 5.2), (7.2, 5.2)], "gold", "gold2", 0.3, both=True),
            ],
            back=[
                _poly("head", [(-2.0, 4.0), (2.0, 4.0), (1.6, -27.0), (0.0, -29.0), (-1.6, -27.0)], "hair", face="back"),
                *[_ellipse("head", 0.0, y, 1.1, 1.1, "jasmine", face="back", n=8) for y in (0.0, -6.0, -12.0, -18.0)],
            ],
        ),
    ]


def _scallops(x0: float, x1: float, y: float, n: int, depth: float) -> list[Point]:
    pts: list[Point] = [(x0, y + depth), (x1, y + depth)]
    for j in range(n * 2, -1, -1):
        pts.append((x0 + (x1 - x0) * j / (n * 2), y - (depth if j % 2 == 1 else 0.0)))
    return pts


def _luz_parts() -> list[J]:
    return [
        _seg("thigh", "skin", 6.8, fl="skin2"),
        _seg("shin", "skin", 6.0, fl="skin2"),
        _poly("ankle", [(-1.6, -0.6), (4.4, -2.0), (5.0, -1.2), (3.6, 1.6), (-0.6, 2.0)], "heel", "ink", 0.5),
        _line("ankle", (-1.3, -0.4), (-1.6, -2.2), c="heel", w=1.1),
        _line("ankle", (-1.2, 2.6), (3.4, 2.6), c="heel", w=0.8),
        {"t": "skirt", "f": "outfit", "trim": "outfit2", "o": "ink", "w": 0.7,
         "wy": 7.0, "hy": -15.0, "ww": 17.0, "hw": 26.0, "fw": 16.0, "n": 7},
        _poly("torso", [(-7.6, 5.0), (7.6, 5.0), (9.4, 16.0), (10.4, 21.4), (-10.4, 21.4), (-9.4, 16.0)],
              "outfit", "ink", 0.8),
        _rrect("torso", -8.0, 5.0, 8.0, 7.6, 1.0, "outfit2"),
        _poly("torso", [(-10.6, 21.0), (10.6, 21.0), (11.6, 23.6), (-11.6, 23.6)], "skin", "ink", 0.5),
        _poly("torso", _scallops(-11.0, 11.0, 21.4, 6, 1.2), "outfit", "ink", 0.5),
        _limb("upper", (0, 0), (0, -12.5), "skin", 4.4),
        _limb("fore", (0, 0), (0, -12.0), "skin", 3.9),
        _line("fore", (-2.0, -10.6), (2.0, -10.6), c="gold", w=1.0, r=False),
        {"t": "hand", "f": "skin"},
        *_dancer_head(
            lip="lip",
            hair=[
                _poly("head", [(-8.8, 12.0), (-8.6, 19.5), (-6.0, 23.0), (-1.0, 24.4), (4.0, 23.6), (8.0, 21.0),
                               (8.9, 15.0), (8.6, 12.0), (6.5, 18.6), (2.0, 20.2), (-3.0, 20.0), (-7.2, 17.4)],
                      "hair", smooth=2),
                _ellipse("head", 8.8, 21.4, 4.2, 4.0, "hair", "ink", 0.5, n=18),
                *[_ellipse("head", -7.4 + 2.0 * math.cos(a * math.pi / 180.0), 21.6 + 2.0 * math.sin(a * math.pi / 180.0),
                           1.7, 1.7, "flower", "ink", 0.3, n=10) for a in (90, 162, 234, 306, 18)],
                _ellipse("head", -7.4, 21.6, 1.2, 1.2, "flower2", n=10),
            ],
            extras=[_ellipse("head", 9.0, 8.0, 1.7, 2.2, None, "gold", 0.9, both=True, n=14)],
            back=[_ellipse("head", 8.8, 21.4, 4.2, 4.0, "hair", "ink", 0.5, face="back", n=18)],
        ),
    ]


# -- dances -------------------------------------------------------------------------------------------


def _moonwalk() -> J:
    """The classic moonwalk, sampled into keyframes from :func:`pose` (one glide period, 16 keys)."""
    period = 4.0 * math.pi / 8.4
    n = 16
    keys: list[dict[str, float]] = []
    for i in range(n):
        p = pose("evaluating", period * i / n)
        lift_l, lift_r = max(0.0, p.step) * 7.0, max(0.0, -p.step) * 7.0
        keys.append({
            "x": round(p.glide, 3), "bob": round(p.bob, 3), "squash": round(p.squash, 4),
            "hip_x": round(0.36 * p.lean, 3), "pelvis": round(-math.atan(p.lean / 100.0) * 180.0 / math.pi, 3),
            "head": round(-1.1 * p.hat_lag, 3),
            "sh_r": round(18.0 + 144.0 * p.arm, 3), "sh_l": round(math.atan2(5.5 - p.swing, 20.0) * 180.0 / math.pi, 3),
            "ft_l_y": round(lift_l, 3), "ft_l_x": round(0.35 * lift_l, 3),
            "ft_r_y": round(lift_r, 3), "ft_r_x": round(0.35 * lift_r, 3),
        })
    return {"name": "Moonwalk", "key_seconds": round(period / n, 5), "base": {"knee_out": 0.25}, "keys": keys}


def _twerk() -> J:
    squat = {"pitch": 34.0, "ft_l_x": 6.0, "ft_r_x": 6.0, "knee_out": 1.0, "sh_l": 12.0, "sh_r": 12.0,
             "el_l": -26.0, "el_r": -26.0, "wr_l": -20.0, "wr_r": -20.0, "mouth": 1.0, "gaze": 0.0}
    keys: list[dict[str, float]] = []
    for i in range(8):                       # hands on thighs, the bounce
        down = i % 2 == 0
        tilt = -7.0 if (i // 2) % 2 == 0 else 7.0
        keys.append({**squat, "drop": 0.27 if down else 0.17, "pelvis": tilt, "torso": -0.6 * tilt,
                     "hip_x": tilt * 0.25, "head": -0.5 * tilt, "bob": 0.0 if down else 0.6})
    # rising out of the squat, arms on the way up
    keys.append({"drop": 0.16, "pitch": 14.0, "ft_l_x": 5.5, "ft_r_x": 5.5, "knee_out": 0.95, "sh_l": 80.0, "sh_r": 80.0,
                 "el_l": 20.0, "el_r": 20.0, "mouth": 1.0})
    sway = [-14.0, -6.0, 8.0, 14.0, 6.0, -8.0, -12.0, 0.0]
    for i, tilt in enumerate(sway):          # stand up, hips sweep, arms up: the hype
        keys.append({"drop": 0.12 if i % 2 == 0 else 0.07, "pelvis": tilt, "torso": -0.5 * tilt, "hip_x": tilt * 0.22,
                     "ft_l_x": 5.0, "ft_r_x": 5.0, "knee_out": 0.9, "sh_l": 150.0, "sh_r": 150.0,
                     "el_l": 15.0 + (25.0 if i % 2 else 0.0), "el_r": 40.0 - (25.0 if i % 2 else 0.0),
                     "head": -0.4 * tilt, "mouth": 2.0 if i in (2, 3, 6) else 1.0, "gaze": tilt / 14.0})
    # and back down into the squat, arms coming to the thighs
    keys.append({"drop": 0.18, "pitch": 22.0, "ft_l_x": 6.0, "ft_r_x": 6.0, "knee_out": 1.0, "sh_l": 60.0, "sh_r": 60.0,
                 "el_l": -10.0, "el_r": -10.0, "mouth": 1.0})
    return {"name": "Twerk", "key_seconds": 0.17, "base": {}, "keys": keys}


def _bharatanatyam() -> J:
    base = {"drop": 0.24, "ft_l_x": -3.4, "ft_r_x": -3.4, "knee_out": 1.0, "mouth": 1.0}
    waist = {"sh_l": 36.0, "sh_r": 36.0, "el_l": -122.0, "el_r": -122.0, "wr_l": -40.0, "wr_r": -40.0,
             "mudra_l": 3.0, "mudra_r": 3.0}
    keys: list[dict[str, float]] = []
    for i in range(8):                       # tatta adavu: hands at the waist, the feet strike in turn
        side = "l" if (i // 2) % 2 == 0 else "r"
        lifted = i % 2 == 0
        slide = 1.6 if i % 2 == 0 else -1.6  # attami: the head glides side to side
        key: dict[str, float] = {**waist, "head_x": slide, "gaze": slide / 1.6, "bob": 0.0}
        key["ft_" + side + "_y"] = 5.5 if lifted else 0.0
        keys.append(key)
    arms = {"sh_l": 90.0, "sh_r": 90.0, "el_l": 0.0, "el_r": 0.0, "wr_l": 84.0, "wr_r": 84.0,
            "mudra_l": 1.0, "mudra_r": 1.0, "gaze": 0.0, "head_x": 0.0}
    keys.append(dict(arms))                  # natyarambhe: arms out, pataka hands
    for side, other, toward in (("l", "r", -1.0), ("r", "l", 1.0)):
        reach = {**arms, "sh_" + side: 140.0, "wr_" + side: 40.0, "mudra_" + side: 2.0,
                 "sh_" + other: 82.0, "ft_" + side + "_x": 7.0, "toe_" + side: -24.0, "ft_" + side + "_y": 1.2,
                 "torso": -4.0 * toward, "gaze": toward, "head_x": 1.4 * toward, "head": -4.0 * toward}
        keys.append(reach)                   # natta adavu: the heel taps out, the arm opens upward
        keys.append({**reach, "ft_" + side + "_y": 0.0, "head_x": -0.6 * toward})
        keys.append(dict(arms))
    keys.append({**arms, "sh_l": 60.0, "sh_r": 60.0, "el_l": -70.0, "el_r": -70.0, "mudra_l": 3.0, "mudra_r": 3.0})
    return {"name": "Bharatanatyam", "key_seconds": 0.3, "base": base, "keys": keys}


def _salsa() -> J:
    base = {"drop": 0.07, "knee_out": 0.3, "ft_l_x": 1.0, "ft_r_x": 1.0, "sh_l": 26.0, "sh_r": 26.0,
            "el_l": 116.0, "el_r": 116.0, "wr_l": -16.0, "wr_r": -16.0, "mouth": 1.0, "flare": 0.15}
    # On1: weight goes to the stepping foot, the hip of the weighted leg rises (Cuban motion), and
    # the free knee softens. Counts 1-2-3 (pause 4), 5-6-7 (pause 8).
    weight = [(-3.2, "l"), (2.2, "r"), (-2.4, "l"), (-1.2, "l"), (3.2, "r"), (-2.2, "l"), (2.4, "r"), (1.2, "r")]

    def count(i: int, hip: float, on: str) -> dict[str, float]:
        free = "r" if on == "l" else "l"
        tilt = 8.0 if on == "r" else -8.0
        sway = 10.0 if on == "r" else -10.0
        return {"hip_x": hip, "pelvis": tilt * (0.6 if i % 4 == 3 else 1.0), "torso": -0.45 * tilt,
                "ft_" + free + "_y": 1.4 if i % 4 != 3 else 0.6, "head": -0.3 * tilt, "gaze": hip / 3.2,
                "sh_l": 26.0 - sway, "sh_r": 26.0 + sway, "el_l": 116.0 + sway, "el_r": 116.0 - sway}

    keys = [count(i, hip, on) for i, (hip, on) in enumerate(weight)]
    turn = [count(i, hip, on) for i, (hip, on) in enumerate(weight)]
    turn[3].update({"sh_r": 150.0, "el_r": 30.0, "wr_r": -20.0})              # prep: the right hand goes up
    spin = [1.0, -0.55, -0.55, 1.0]
    for j, k in enumerate(range(4, 8)):
        turn[k].update({"sx": spin[j], "flare": 0.95 if j in (1, 2) else 0.45, "sh_r": 165.0, "el_r": 14.0,
                        "sh_l": 62.0, "el_l": 40.0, "pelvis": 0.0, "torso": 0.0, "hip_x": 0.0})
    return {"name": "Salsa", "key_seconds": 0.25, "base": base, "keys": keys + turn}


# -- looks ----------------------------------------------------------------------------------------------


def _shade(hex_color: str, k: float) -> str:
    """Scale a #rrggbb colour's channels by ``k`` (darker below 1, lighter towards white above 1)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    if k <= 1.0:
        r, g, b = (int(c * k + 0.5) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * (k - 1.0) + 0.5) for c in (r, g, b))
    return "#%02x%02x%02x" % (min(255, r), min(255, g), min(255, b))


SKINS = ["#f6d5b8", "#eab988", "#d39a6a", "#a86f4c", "#7a4b33"]
OUTFITS = ["#f6f6f3", "#e23b4a", "#ff5fa2", "#b3123f", "#f59f0a", "#2fb36b", "#1f8fe0", "#7b5cff", "#1d1f26"]


def _skin_look(color: str) -> dict[str, str]:
    return {"skin": color, "skin2": _shade(color, 0.9)}


def _outfit_look(color: str) -> dict[str, str]:
    return {"outfit": color, "outfit2": _shade(color, 0.86 if color != "#1d1f26" else 1.35)}


_COMMON = {"ink": "#1b1d23", "gold": "#e3b23c", "gold2": "#b8862a", "blush": "#d98a7f"}

_CHARACTERS: list[tuple[str, J, Callable[[], list[J]]]] = [
    ("smooth", {"name": "Smooth", "body": "fig", "dance": "moonwalk", "skin": 1, "outfit": 0,
                "palette": {"hair": PALETTE["hair"], "shirt": PALETTE["shirt"], "tie": PALETTE["tie"],
                            "glove": "#ffffff"}}, _smooth_parts),
    ("zuri", {"name": "Zuri", "body": "dancer", "dance": "twerk", "skin": 4, "outfit": 2,
              "palette": {"hair": "#1d1a1f", "hair2": "#3a3340", "pants": "#7d8594", "pants2": "#646b78",
                          "shoe": "#f5f5f5", "sole": "#cfd2d8", "lip": "#6b2b3a"}}, _zuri_parts),
    ("mira", {"name": "Mira", "body": "dancer", "dance": "bharatanatyam", "skin": 3, "outfit": 3,
              "palette": {"hair": "#141015", "jasmine": "#fbfbf4", "alta": "#c8102e", "lip": "#a3243b",
                          "silver": "#d9dde3"}}, _mira_parts),
    ("luz", {"name": "Luz", "body": "dancer", "dance": "salsa", "skin": 2, "outfit": 1,
             "palette": {"hair": "#3b2418", "flower": "#ffd23f", "flower2": "#ff8c42", "heel": "#1d1f26",
                         "lip": "#c0172f"}}, _luz_parts),
]

_DANCES: list[tuple[str, Callable[[], J]]] = [
    ("moonwalk", _moonwalk), ("twerk", _twerk), ("bharatanatyam", _bharatanatyam), ("salsa", _salsa),
]

_CATALOG: J | None = None


def catalog() -> J:
    """Everything the page needs to draw what the pets draw: bodies, characters, dances, mudras, looks."""
    global _CATALOG
    if _CATALOG is None:
        characters: J = {}
        for cid, meta, parts in _CHARACTERS:
            palette = {**_COMMON, **meta["palette"], **_skin_look(SKINS[meta["skin"]]),
                       **_outfit_look(OUTFITS[meta["outfit"]])}
            characters[cid] = {**{k: v for k, v in meta.items() if k != "palette"}, "palette": palette, "parts": parts()}
        _CATALOG = {
            "version": 1,
            "rest": dict(REST),
            "discrete": list(DISCRETE),
            "tempo": {k: list(v) for k, v in TEMPO.items()},
            "bodies": BODIES,
            "order": [cid for cid, _, _ in _CHARACTERS],
            "characters": characters,
            "dance_order": [did for did, _ in _DANCES],
            "dances": {did: build() for did, build in _DANCES},
            "mudras": {
                "0": [_ellipse("hand", 0.0, -2.3, 2.7, 2.7, "$", "ink", 0.7, n=14)],
                "1": [_rrect("hand", -1.7, -6.6, 1.7, -0.4, 1.3, "$", "ink", 0.6),
                      _poly("hand", [(1.4, -1.2), (3.0, -2.4), (3.1, -3.3), (1.6, -2.8)], "$", "ink", 0.5),
                      _line("hand", (-0.55, -6.0), (-0.55, -3.6), w=0.3), _line("hand", (0.55, -6.0), (0.55, -3.6), w=0.3)],
                "2": [*[_line("hand", (1.6 * math.sin(a * math.pi / 180.0), -2.0 - 1.6 * math.cos(a * math.pi / 180.0)),
                              (4.8 * math.sin(a * math.pi / 180.0), -2.0 - 4.8 * math.cos(a * math.pi / 180.0)),
                              c="$", w=1.3) for a in (-64, -32, 0, 32, 64)],
                      _ellipse("hand", 0.0, -2.0, 2.1, 2.1, "$", "ink", 0.6, n=12)],
                "3": [_ellipse("hand", 0.0, -1.9, 2.2, 2.0, "$", "ink", 0.6, n=12)],
            },
            "skins": [_skin_look(c) for c in SKINS],
            "outfits": [_outfit_look(c) for c in OUTFITS],
        }
    return _CATALOG


def look_palette(char_id: str, skin: int | None = None, outfit: int | None = None) -> dict[str, str]:
    """A character's colours, with an optional skin tone and outfit colour from :data:`SKINS`/:data:`OUTFITS`."""
    cat = catalog()
    palette = dict(cat["characters"][char_id]["palette"])
    if skin is not None and 0 <= skin < len(cat["skins"]):
        palette.update(cat["skins"][skin])
    if outfit is not None and 0 <= outfit < len(cat["outfits"]):
        palette.update(cat["outfits"][outfit])
    return palette


# -- the choice -----------------------------------------------------------------------------------------


def default_choice() -> J:
    """Smooth on the desktop, everyone on the page, each doing their own dance in their own colours."""
    cat = catalog()
    return {
        "pet": "smooth",
        "stage": list(cat["order"]),
        "chars": {cid: {"dance": cat["characters"][cid]["dance"], "skin": None, "outfit": None} for cid in cat["order"]},
    }


def normalize_choice(raw: object) -> J:
    """Keep what is valid in ``raw`` and fill the rest from :func:`default_choice`. Never raises."""
    cat = catalog()
    choice = default_choice()
    if not isinstance(raw, Mapping):
        return choice
    if raw.get("pet") in cat["characters"]:
        choice["pet"] = raw["pet"]
    stage = raw.get("stage")
    if isinstance(stage, list):
        wanted = {s for s in stage if isinstance(s, str)}
        choice["stage"] = [cid for cid in cat["order"] if cid in wanted]
    chars = raw.get("chars")
    if isinstance(chars, Mapping):
        for cid, spec in chars.items():
            if cid not in cat["characters"] or not isinstance(spec, Mapping):
                continue
            mine = choice["chars"][cid]
            if spec.get("dance") in cat["dances"]:
                mine["dance"] = spec["dance"]
            for key, options in (("skin", cat["skins"]), ("outfit", cat["outfits"])):
                value = spec.get(key)
                if value is None or (isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(options)):
                    mine[key] = value
    return choice


def pet_of(raw: object) -> tuple[str, str, int | None, int | None]:
    """(character, dance, skin, outfit) for the desktop pet, from a choice as ``status.json`` carries it."""
    choice = normalize_choice(raw)
    spec = choice["chars"][choice["pet"]]
    return choice["pet"], spec["dance"], spec["skin"], spec["outfit"]


def cycle(raw: object, what: str) -> J:
    """The choice with the pet moved to the next character (``what="character"``) or its next dance."""
    cat = catalog()
    choice = normalize_choice(raw)
    if what == "character":
        order = cat["order"]
        choice["pet"] = order[(order.index(choice["pet"]) + 1) % len(order)]
    else:
        spec = choice["chars"][choice["pet"]]
        order = cat["dance_order"]
        spec["dance"] = order[(order.index(spec["dance"]) + 1) % len(order)]
    return choice


def choice_path() -> Path:
    return Path(os.path.expanduser("~")) / ".evalloop" / "avatar.json"


def load_choice(path: str | os.PathLike[str] | None) -> J:
    """The saved choice at ``path`` (defaults when there is none, or it does not parse)."""
    if path is None:
        return default_choice()
    try:
        return normalize_choice(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return default_choice()


def save_choice(path: str | os.PathLike[str] | None, choice: Mapping[str, Any]) -> J:
    """Normalise and save ``choice`` at ``path`` (not saved when ``path`` is None). Returns what was kept."""
    kept = normalize_choice(choice)
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(kept, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    return kept
