"""The on-screen pet, done properly: a Qt (PySide6) transparent desktop figure.

Tkinter cannot composite per-pixel window transparency on macOS, so the floating character is built
on Qt, which can: a frameless, always-on-top, translucent ``QWidget`` with **nothing** behind the
figure — just him. Qt also gives antialiased vector drawing and a real ``QTransform`` shear, so the
Smooth-Criminal lean is exact (the body tilts as one plank, feet planted) and the motion is smooth
at 60fps.

This is the one place EvalLoop uses a non-stdlib dependency, and only for the optional pet UI — the
eval engine stays pure standard library. The dance, the poll and the figure's measurements are
reused from :mod:`evalloop.session.overlay`; only the *rendering* is Qt here.

He stands when idle and dances only while evaluating (the desktop-pet model). Click him for the live
report panel; drag to move; Esc to dismiss.
"""

from __future__ import annotations

import time
import webbrowser
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from evalloop.session.overlay import (
    FIGURE_HEIGHT,
    MOOD,
    PALETTE,
    Pose,
    _Poller,
    _runs,
    _str_list,
    _testing_now,
    pose,
    signal_line,
)

__all__ = ["run_overlay_qt"]

_ACCENT = {
    "idle": "#5e5ce6", "evaluating": "#5e5ce6", "happy": "#30d158",
    "alarmed": "#ff453a", "unsure": "#ff9f0a", "errored": "#ff453a",
}


def _c(hex_color: str) -> QtGui.QColor:
    return QtGui.QColor(hex_color)


def _body_transform(ox: float, oy: float, s: float, p: Pose, extra_lean: float) -> QtGui.QTransform:
    """Figure space (feet at origin, y up) -> screen, with the lean sheared in as one rigid plank."""
    t = QtGui.QTransform()
    t.translate(ox + p.glide * s, oy)                 # glide: the moonwalk sideways slide (feet too)
    t.scale(s, -s)                                    # figure units -> px, y points up
    t.translate(0.0, p.bob)                           # bob lifts the whole body
    t.shear((p.lean + extra_lean) / FIGURE_HEIGHT, 0.0)   # lean: x += (lean/H)*y  — feet (y=0) fixed
    t.scale(1.0 + 0.4 * p.squash, 1.0 - p.squash)     # squash-and-stretch
    return t


def _poly(pts: list[tuple[float, float]]) -> QtGui.QPolygonF:
    return QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in pts])


def draw_figure_qt(painter: QtGui.QPainter, ox: float, oy: float, s: float, p: Pose) -> None:
    """Draw the minifigure with QPainter. Only the figure — no backdrop."""
    suit, hair, skin = _c(PALETTE["suit"]), _c(PALETTE["hair"]), _c(PALETTE["skin"])
    shirt, tie, ink = _c(PALETTE["shirt"]), _c(PALETTE["tie"]), _c(PALETTE["ink"])

    ink_pen = QtGui.QPen(ink)
    ink_pen.setCosmetic(True)
    ink_pen.setWidthF(1.1)
    no_pen = QtGui.QPen(QtCore.Qt.PenStyle.NoPen)

    def fill(poly: list[tuple[float, float]], color: QtGui.QColor, outline: bool = False) -> None:
        painter.setPen(ink_pen if outline else no_pen)
        painter.setBrush(color)
        painter.drawPolygon(_poly(poly))

    def limb(a: tuple[float, float], b: tuple[float, float], w: float, color: QtGui.QColor) -> None:
        pen_o = QtGui.QPen(ink)
        pen_o.setWidthF(w + 1.2)
        pen_o.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_o)
        painter.drawLine(QtCore.QPointF(*a), QtCore.QPointF(*b))
        pen_i = QtGui.QPen(color)
        pen_i.setWidthF(w)
        pen_i.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_i)
        painter.drawLine(QtCore.QPointF(*a), QtCore.QPointF(*b))

    def line(a: tuple[float, float], b: tuple[float, float], w: float = 0.9) -> None:
        pen = QtGui.QPen(ink)
        pen.setWidthF(w)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(*a), QtCore.QPointF(*b))

    def ellipse(cx: float, cy: float, rx: float, ry: float, color: QtGui.QColor, outline: bool = False) -> None:
        painter.setPen(ink_pen if outline else no_pen)
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QPointF(cx, cy), rx, ry)

    body = _body_transform(ox, oy, s, p, 0.0)
    head = _body_transform(ox, oy, s, p, p.hat_lag)

    # ===== BODY =====
    painter.setTransform(body)

    # free (right) arm, behind the torso, with its counter-swing
    limb((-13.0, 63.0), (-18.5 + p.swing, 43.0), 5.0, suit)
    ellipse(-18.5 + p.swing, 41.0, 2.7, 2.7, skin, outline=True)

    # legs: white trousers (subtle gradient for form), black shoes + ankle band.
    # Each leg lifts (knee bends, foot rises) on its beat with a small sideways kick — the dance step.
    grad = QtGui.QLinearGradient(QtCore.QPointF(-13, 0), QtCore.QPointF(13, 0))
    grad.setColorAt(0.0, _c("#dcdcd8"))
    grad.setColorAt(0.55, _c(PALETTE["suit"]))
    grad.setColorAt(1.0, _c("#ffffff"))
    lift_amp = 7.0
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 1.4, sx * 12.8))
        lift = max(0.0, (p.step if sx < 0 else -p.step)) * lift_amp
        kick = lift * 0.35 * sx
        x0 += kick
        x1 += kick
        painter.setPen(ink_pen)
        painter.setBrush(QtGui.QBrush(grad))
        painter.drawPolygon(_poly([(x0, 5 + lift), (x1, 5 + lift), (x1, 36), (x0, 36)]))
        fill([(x0, 0 + lift), (x1, 0 + lift), (x1, 5 + lift), (x0, 5 + lift)], hair, outline=True)   # shoe
        fill([(x0, 8 + lift), (x1, 8 + lift), (x1, 11 + lift), (x0, 11 + lift)], hair)              # ankle band

    # torso: white jacket (left-lit gradient), blue shirt V, white tie, lapels, belt
    painter.setPen(ink_pen)
    painter.setBrush(QtGui.QBrush(grad))
    painter.drawPolygon(_poly([(-14.0, 36), (14.0, 36), (16.0, 64), (-16.0, 64)]))
    fill([(-6.8, 64), (6.8, 64), (0, 44)], shirt)
    fill([(-2.1, 63), (2.1, 63), (1.3, 45), (-1.3, 45)], tie, outline=True)
    line((-6.8, 64), (-1.8, 45), 0.8)
    line((6.8, 64), (1.8, 45), 0.8)
    line((-14.4, 39.5), (14.4, 39.5), 0.9)

    # glove arm, raising with the dance
    rx = 17.5 + 2.0 * (1 - p.arm)
    ry = 43.0 + (77.0 - 43.0) * p.arm
    limb((13.0, 63.0), (rx, ry), 5.0, suit)
    ellipse(rx, ry - 1.5, 2.9, 2.9, _c("#ffffff"), outline=True)

    # ===== HEAD (follows with the hat lag) =====
    painter.setTransform(head)
    fill([(-3.4, 63), (3.4, 63), (3.4, 67), (-3.4, 67)], skin, outline=True)   # neck
    painter.setPen(ink_pen)
    painter.setBrush(skin)
    painter.drawRoundedRect(QtCore.QRectF(-8.6, 66.5, 17.2, 18.5), 3.2, 3.2)    # face
    painter.setPen(no_pen)
    painter.setBrush(_c("#e3c6a2"))
    painter.drawRoundedRect(QtCore.QRectF(-8.6, 66.5, 7.6, 18.5), 3.0, 3.0)     # cheek shade
    for sx in (-1, 1):
        ellipse(sx * 3.3, 77.5, 1.05, 1.3, ink)                                # eye
        line((sx * 5.0, 80.4), (sx * 1.9, 81.1), 1.0)                          # brow
    line((-2.3, 72.6), (2.3, 72.6), 0.9)                                        # mouth

    # hair: fringe + a lock down each side
    fill([(-8.7, 82.0), (8.7, 82.0), (8.7, 85.2), (-8.7, 85.2)], hair)
    fill([(-8.5, 84.5), (-11.4, 81.0), (-12.0, 73.0), (-9.6, 68.5), (-7.8, 71.0), (-8.5, 77.0)], hair)
    fill([(8.5, 84.5), (11.4, 81.0), (12.0, 74.0), (10.0, 70.0), (8.0, 72.5), (8.5, 78.0)], hair)

    # fedora: wide brim, black band, pinched crown
    ellipse(0, 85.4, 21.0, 3.6, suit, outline=True)
    ellipse(0, 86.2, 20.0, 1.9, _c("#dedede"))
    fill([(-11.0, 85.6), (11.0, 85.6), (11.0, 89.0), (-11.0, 89.0)], hair)
    fill([(-11.0, 88.8), (-9.6, 95.2), (-5.4, 97.4), (-1.9, 95.8), (2.0, 97.6), (5.8, 97.4),
          (9.8, 95.0), (11.0, 88.8)], suit, outline=True)

    painter.resetTransform()


class _Pet(QtWidgets.QWidget):
    """The transparent, frameless, always-on-top figure widget."""

    def __init__(self, poller: _Poller, scale: float, dashboard_url: str) -> None:
        # NOT Qt.Tool: macOS auto-hides Tool windows when their app is not frontmost, which makes a
        # desktop pet vanish the moment you click another app. A plain frameless stay-on-top window
        # keeps him visible over everything.
        super().__init__(
            None,
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._poller = poller
        self._scale = scale
        self._dashboard_url = dashboard_url
        self._t0 = time.monotonic()
        self._cloud_h = 42
        self._w = 136
        self._h = int(self._cloud_h + FIGURE_HEIGHT * scale + 10)
        self.resize(self._w, self._h)
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        # Start centred so he is easy to find on first launch; drag him wherever afterwards.
        self.move(screen.center().x() - self._w // 2, screen.center().y() - self._h // 2)
        self._panel = _Panel(poller)
        self._drag_off: QtCore.QPoint | None = None
        self._moved = False

        timer = QtCore.QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)  # ~60fps

    def _tick(self) -> None:
        self.update()
        if self._panel.isVisible():
            self._panel.update()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        state = self._poller.state
        t = time.monotonic() - self._t0
        self._draw_cloud(painter, state, t)
        ox, oy = self._w / 2.0, self._h - 6.0
        draw_figure_qt(painter, ox, oy, self._scale, pose(state, t))

    def _draw_cloud(self, painter: QtGui.QPainter, state: str, t: float) -> None:
        # Always on: "testing X…" while a run is in flight, else the last file graded and its result,
        # else "watching <project>". The in-flight state is too brief to poll, so the bubble shows a
        # signal that is always truthful rather than one that is almost always blank.
        text, accent_hex = signal_line(self._poller.data, state)
        if state == "evaluating":
            text += "." * (1 + int(t * 2) % 3)
        accent = _c(accent_hex)
        fm = QtGui.QFontMetrics(QtGui.QFont("Helvetica Neue", 9, QtGui.QFont.Weight.DemiBold))
        width = min(self._w - 8.0, max(84.0, fm.horizontalAdvance(text) + 22.0))
        x0 = (self._w - width) / 2
        rect = QtCore.QRectF(x0, 5, width, 24)
        painter.setPen(QtGui.QPen(accent, 1.2))
        painter.setBrush(_c("#1b1e26"))
        painter.drawRoundedRect(rect, 11, 11)
        painter.setPen(_c("#f3f3f5"))
        painter.setFont(QtGui.QFont("Helvetica Neue", 9, QtGui.QFont.Weight.DemiBold))
        painter.drawText(rect, int(QtCore.Qt.AlignmentFlag.AlignCenter), text)
        painter.setBrush(_c("#1b1e26"))
        painter.setPen(QtGui.QPen(accent, 1.0))
        painter.drawEllipse(QtCore.QPointF(self._w / 2 - 1, 33), 3.0, 3.5)

    # --- interaction: drag to move, click to toggle the panel, Esc to quit ---
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self._quit()
            return
        self._drag_off = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self._moved = False

    def _quit(self) -> None:
        self._poller.stop()
        self._panel.close()
        self.close()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_off is not None:
            self._moved = True
            self.move(event.globalPosition().toPoint() - self._drag_off)
            if self._panel.isVisible():
                self._panel.place(self)

    def mouseReleaseEvent(self, _event: QtGui.QMouseEvent) -> None:
        self._drag_off = None
        if not self._moved:
            if self._panel.isVisible():
                self._panel.hide()
            else:
                self._panel.place(self)
                self._panel.show()

    def mouseDoubleClickEvent(self, _event: QtGui.QMouseEvent) -> None:
        webbrowser.open(self._dashboard_url)   # the full physics dashboard in the browser

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self._quit()


class _Panel(QtWidgets.QWidget):
    """A translucent native report panel that appears beside the pet when he is clicked."""

    W, H = 440, 500

    def __init__(self, poller: _Poller) -> None:
        super().__init__(
            None,
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._poller = poller
        self.resize(self.W, self.H)

    def place(self, anchor: QtWidgets.QWidget) -> None:
        g = anchor.frameGeometry()
        self.move(max(10, g.left() - self.W - 14), g.top())

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        data = self._poller.data
        state = self._poller.state
        accent = _c(_ACCENT.get(state, "#5e5ce6"))
        mono = "SF Mono"

        painter.setPen(QtGui.QPen(_c("#2b2f3a"), 1))
        painter.setBrush(_c("#121319"))
        painter.drawRoundedRect(QtCore.QRectF(3, 3, self.W - 6, self.H - 6), 20, 20)

        def text(x: float, y: float, s: str, color: str, size: int, weight: QtGui.QFont.Weight,
                 family: str = "Helvetica Neue",
                 align: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft) -> None:
            painter.setPen(_c(color))
            painter.setFont(QtGui.QFont(family, size, weight))
            painter.drawText(QtCore.QRectF(x, y, self.W - x - 22, 22), int(align), s)

        def wrapped(x: float, y: float, w: float, s: str, color: str, size: int, family: str) -> float:
            painter.setPen(_c(color))
            font = QtGui.QFont(family, size)
            painter.setFont(font)
            rect = QtCore.QRectF(x, y, w, 60)
            flags = int(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.TextFlag.TextWordWrap)
            bound = painter.boundingRect(rect, flags, s)
            painter.drawText(rect, flags, s)
            return bound.height()

        # header
        painter.setBrush(accent)
        painter.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        painter.drawEllipse(QtCore.QPointF(30, 31), 5, 5)
        text(42, 20, "EvalLoop", "#f3f3f5", 15, QtGui.QFont.Weight.DemiBold)
        text(0, 20, MOOD.get(state, state) + "   ", _ACCENT.get(state, "#5e5ce6"), 10,
             QtGui.QFont.Weight.DemiBold, align=QtCore.Qt.AlignmentFlag.AlignRight)

        runs = _runs(data)
        latest = next((r for r in runs if r.get("cases")), None)
        passed = failed = pending = 0
        for r in runs:
            for cs in (r.get("cases") or []):
                v = cs.get("verdict") if isinstance(cs, dict) else None
                passed += v == "passed"
                failed += v == "failed"
                pending += v not in ("passed", "failed")

        # project + the file being tested right now (or last)
        project = str(data.get("root", "")).rstrip("/\\").replace("\\", "/").split("/")[-1] or "—"
        now = _testing_now(data)
        file = now if now else (", ".join(b.split("/")[-1] for b in _str_list(latest.get("trigger")))
                                if latest and latest.get("trigger") else "watching")
        text(26, 44, f"{project}  ·  testing {file}"[:50], "#9aa0ad", 10, QtGui.QFont.Weight.Normal)
        painter.setPen(QtGui.QPen(_c("#23262f"), 1))
        painter.drawLine(QtCore.QPointF(22, 70), QtCore.QPointF(self.W - 22, 70))

        # tally
        y = 82.0
        for i, (n, lab, col) in enumerate((
            (len(runs), "runs", "#f3f3f5"), (passed, "passed", "#30d158"),
            (failed, "failed", "#ff453a"), (pending, "pending", "#ff9f0a"),
        )):
            x = 28 + i * ((self.W - 56) / 4)
            text(x, y, str(n), col, 19, QtGui.QFont.Weight.DemiBold)
            text(x, y + 22, lab, "#7d828e", 9, QtGui.QFont.Weight.Normal)
        y += 54

        tech = {"A1_execution_based": "execution", "sql": "SQL match", "rag": "RAG recall",
                "agent": "end-state", "db_access": "DB read-only", "agent_scaffold": "agent detected"}

        def ellip(s: str, n: int) -> str:
            return s if len(s) <= n else s[: n - 1] + "…"

        # per-run pass rate with its real Wilson interval
        rate = latest.get("rate") if latest else None
        if isinstance(rate, dict):
            est = int(round(float(rate["estimate"]) * 100))
            lo, hi = int(round(float(rate["lower"]) * 100)), int(round(float(rate["upper"]) * 100))
            col = "#30d158" if float(rate["estimate"]) >= 0.999 else ("#ff453a" if int(rate["failed"]) else "#ff9f0a")
            text(26, y, f"{est}%", col, 21, QtGui.QFont.Weight.DemiBold)
            text(80, y + 6, f"[{lo}–{hi}%]  ·  n={rate['n']} decided  ·  95% Wilson", "#7d828e", 9, QtGui.QFont.Weight.Normal)
            y += 32

        cases = latest.get("cases") if latest else []
        if cases:
            text(26, y, "CASES", "#7d828e", 9, QtGui.QFont.Weight.DemiBold)
            text(0, y, "test · technique · result   ", "#5b5e68", 9, QtGui.QFont.Weight.Normal,
                 align=QtCore.Qt.AlignmentFlag.AlignRight)
            y += 20
            painter.setPen(QtGui.QPen(_c("#23262f"), 1))
            painter.drawLine(QtCore.QPointF(26, y - 4), QtCore.QPointF(self.W - 26, y - 4))
            shown = [c for c in cases if isinstance(c, dict)][:6]
            for c in shown:
                v = str(c.get("verdict", ""))
                dot = {"passed": "#30d158", "failed": "#ff453a"}.get(v, "#ff9f0a")
                painter.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
                painter.setBrush(_c(dot))
                painter.drawEllipse(QtCore.QPointF(33, y + 9), 3.5, 3.5)
                text(44, y, ellip(str(c.get("name", "case")), 30), "#e9ebf2", 11, QtGui.QFont.Weight.Normal, family=mono)
                text(0, y, {"passed": "PASS", "failed": "FAIL"}.get(v, "PEND") + "   ", dot, 10,
                     QtGui.QFont.Weight.DemiBold, align=QtCore.Qt.AlignmentFlag.AlignRight)
                klass = str(c.get("failure_class", "")) or tech.get(str(c.get("record", "")), str(c.get("record", "")))
                text(44, y + 15, ellip(f"{tech.get(str(c.get('record','')), '')}  ·  {klass}", 44), "#7d828e", 9, QtGui.QFont.Weight.Normal)
                y += 32
                if v == "failed":
                    ev = str(c.get("detail", "")).strip()[:160] or "no evidence"
                    eh = wrapped(44, y - 6, self.W - 70, ev, "#ff9f9f", 9, mono)
                    y += min(eh, 30) - 2
            if len(cases) > len(shown):
                text(26, y, f"+ {len(cases) - len(shown)} more cases — double-click me for the full table", "#7d828e", 9, QtGui.QFont.Weight.Normal)
        elif latest:
            text(26, y + 6, "nothing was graded in this run", "#7d828e", 11, QtGui.QFont.Weight.Normal)
        else:
            text(26, y + 6, "Nothing evaluated yet — edit a file and I’ll test it.", "#7d828e", 11, QtGui.QFont.Weight.Normal)


def run_overlay_qt(*, host: str = "127.0.0.1", port: int = 7420, poll: float = 1.5, scale: float = 0.64) -> None:
    """Open the Qt desktop pet. Blocks on the Qt event loop until dismissed (Esc)."""
    poller = _Poller(f"http://{host}:{port}/status.json", interval=poll)
    poller.start()
    app: Any = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    pet = _Pet(poller, scale, f"http://{host}:{port}/")
    pet.show()
    app.exec()
