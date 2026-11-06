"""The on-screen pet, done properly: a Qt (PySide6) transparent desktop figure.

Tkinter cannot composite per-pixel window transparency on macOS, so the floating character is built
on Qt, which can: a frameless, always-on-top, translucent ``QWidget`` with **nothing** behind the
figure, just the dancer. Qt gives antialiased vector drawing, so the dancer (from the shared avatar
engine, :mod:`evalloop.session.avatars`) is smooth at 60fps. ``C`` switches character, ``D`` dance.

This is the one place EvalLoop uses a non-stdlib dependency, and only for the optional pet UI — the
eval engine stays pure standard library. The dance, the poll and the figure's measurements are
reused from :mod:`evalloop.session.overlay` and :mod:`evalloop.session.avatars`; only the
*rendering* is Qt here.

He stands when idle and dances only while evaluating (the desktop-pet model). Click him to chat (tell
him what to watch); press R for the live
report panel; drag to move; Esc to dismiss.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from evalloop.session.avatars import FIGURE_HEIGHT, Animator, catalog, cycle, pet_of, pose_prims
from evalloop.session.overlay import (
    MOOD,
    _Poller,
    _runs,
    _str_list,
    _testing_now,
    signal_line,
)

__all__ = ["run_overlay_qt"]

_ACCENT = {
    "idle": "#5e5ce6", "evaluating": "#5e5ce6", "happy": "#30d158",
    "alarmed": "#ff453a", "unsure": "#ff9f0a", "errored": "#ff453a",
}


def _c(hex_color: str) -> QtGui.QColor:
    return QtGui.QColor(hex_color)


def draw_prims_qt(painter: QtGui.QPainter, prims: list[dict[str, Any]], ox: float, oy: float, s: float) -> None:
    """Draw avatar prims (figure space, y up; :func:`~evalloop.session.avatars.pose_prims`) with QPainter,
    feet at (``ox``, ``oy``), scaled by ``s``."""
    for prim in prims:
        pts = prim["p"]
        xy = [QtCore.QPointF(ox + pts[i] * s, oy - pts[i + 1] * s) for i in range(0, len(pts), 2)]
        if prim["k"] == "poly":
            if prim["o"]:
                pen = QtGui.QPen(_c(prim["o"]))
                pen.setWidthF(max(0.6, prim["w"] * s))
                pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
            else:
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(_c(prim["f"]) if prim["f"] else QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPolygon(QtGui.QPolygonF(xy))
        else:
            pen = QtGui.QPen(_c(prim["c"]))
            pen.setWidthF(max(0.5, prim["w"] * s))
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap if prim["r"] else QtCore.Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(xy[0], xy[1])


class _Pet(QtWidgets.QWidget):
    """The transparent, frameless, always-on-top figure widget."""

    def __init__(self, poller: _Poller, scale: float, dashboard_url: str) -> None:
        # NOT Qt.Tool: macOS auto-hides Tool windows when their app is not frontmost, which makes a
        # desktop pet vanish the moment you click another app. A plain frameless stay-on-top window
        # keeps him visible over everything.
        super().__init__(
            None,
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint,
        )
        # It shows without taking focus (so the editor keeps it), but clicking it gives it the keys
        # (Esc, C, D, P, R); a window that never accepts focus never receives a key press at all.
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
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
        # The permission popup is Tk, which cannot share this process with Qt, so it runs as a small
        # subprocess (evalloop.session.consent_popup) whenever the session has a request waiting.
        self._popup_proc: subprocess.Popen[bytes] | None = None
        self._popup_after = 0.0
        self._animator = Animator()
        self._last = time.monotonic()

        timer = QtCore.QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)  # ~60fps

    def _tick(self) -> None:
        self._consent_tick()
        self.update()
        if self._panel.isVisible():
            self._panel.update()

    def _popup_command(self, *extra: str) -> list[str]:
        url = QtCore.QUrl(self._dashboard_url)
        return [sys.executable, "-m", "evalloop.session.consent_popup",
                "--host", url.host() or "127.0.0.1", "--port", str(url.port(7420)), *extra]

    def _consent_tick(self) -> None:
        """Launch the popup process when a permission is waiting and none is open. Never blocks."""
        if self._popup_proc is not None and self._popup_proc.poll() is None:
            return
        if self._popup_proc is not None:
            self._popup_proc = None
            self._popup_after = time.monotonic() + 2.0  # let status.json catch up before relaunching
        if time.monotonic() < self._popup_after:
            return
        consent = self._poller.data.get("consent")
        pending = consent.get("pending") if isinstance(consent, dict) else None
        if isinstance(pending, list) and pending:
            self._popup_proc = subprocess.Popen(self._popup_command())

    def _open_permissions(self) -> None:
        subprocess.Popen(self._popup_command("--permissions"))

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        state = self._poller.state
        now = time.monotonic()
        t, dt, self._last = now - self._t0, now - self._last, now
        self._draw_cloud(painter, state, t)
        ox, oy = self._w / 2.0, self._h - 6.0
        character, dance, skin, outfit = pet_of(self._poller.data.get("avatar"))
        channels = self._animator.advance(dt, catalog()["dances"][dance], state)
        draw_prims_qt(painter, pose_prims(character, channels, skin=skin, outfit=outfit), ox, oy, self._scale)

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

    # --- interaction: drag to move, click to chat, R for the panel, P for permissions, Esc to quit ---
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
            self._open_chat()

    def _toggle_panel(self) -> None:
        if self._panel.isVisible():
            self._panel.hide()
        else:
            self._panel.place(self)
            self._panel.show()

    def _open_chat(self) -> None:
        """The chat is Tk, so it runs as its own process beside the pet. One at a time."""
        proc = getattr(self, "_chat_proc", None)
        if proc is not None and proc.poll() is None:
            return
        pos = self.frameGeometry().topLeft()
        self._chat_proc = subprocess.Popen(self._chat_command(pos.x(), pos.y()))

    def _chat_command(self, x: int, y: int) -> list[str]:
        url = QtCore.QUrl(self._dashboard_url)
        return [sys.executable, "-m", "evalloop.session.chat_popup", "--host", url.host() or "127.0.0.1",
                "--port", str(url.port(7420)), "--x", str(x), "--y", str(y)]

    def mouseDoubleClickEvent(self, _event: QtGui.QMouseEvent) -> None:
        webbrowser.open(self._dashboard_url)   # the full physics dashboard in the browser

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self._quit()
        elif event.key() == QtCore.Qt.Key.Key_P:
            self._open_permissions()
        elif event.key() == QtCore.Qt.Key.Key_R:
            self._toggle_panel()
        elif event.key() in (QtCore.Qt.Key.Key_C, QtCore.Qt.Key.Key_D):
            self._switch("character" if event.key() == QtCore.Qt.Key.Key_C else "dance")

    def _switch(self, what: str) -> None:
        """The next character or dance for the pet, saved by the session so the page follows."""
        choice = cycle(self._poller.data.get("avatar"), what)
        self._poller.data = {**self._poller.data, "avatar": choice}  # show it now; the next poll confirms
        url = QtCore.QUrl(self._dashboard_url)
        endpoint = f"http://{url.host() or '127.0.0.1'}:{url.port(7420)}/avatar"

        def send() -> None:
            request = urllib.request.Request(
                endpoint, data=json.dumps({"avatar": choice}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-EvalLoop-Bot": "1"}, method="POST")
            try:
                urllib.request.urlopen(request, timeout=3).close()
            except OSError:
                pass

        threading.Thread(target=send, daemon=True).start()


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
