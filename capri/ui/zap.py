"""Closing an app: Capri blasts its window with her red lag lightning.

    "Hey Capri, close Discord" -> sparks crackle around her hand -> a bolt (with
    forks) leaps from her to Discord's window -> the window flashes red with
    arcs crawling over its edges and glitch slices -> it closes (the real close
    happens at the moment of impact) -> everything fades.

The window's position comes from Windows; if it has no window on screen, she
fires at the middle of the screen. About 0.9 s, click-through, never takes focus.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter

from . import lightning
from .overlay_window import OverlayWindow

if TYPE_CHECKING:
    from .companion import Companion

CHARGE = 0.14        # sparks gather at her hand
IMPACT = 0.24        # the bolt lands (the real close runs here)
FIRE_END = 0.55      # the main bolt fades
DONE = 0.95


class ZapFX(OverlayWindow):
    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.hand = QPointF()
        self.target = QRectF()
        self.t = 0.0
        self.small = False                 # one button (Discord's Mute) rather than a whole window
        self._rng = random.Random()

    def _perimeter(self, r: QRectF) -> QPointF:
        u = self._rng.random() * 2 * (r.width() + r.height())
        if u < r.width():
            return QPointF(r.left() + u, r.top())
        u -= r.width()
        if u < r.height():
            return QPointF(r.right(), r.top() + u)
        u -= r.height()
        if u < r.width():
            return QPointF(r.right() - u, r.bottom())
        return QPointF(r.left(), r.bottom() - (u - r.width()))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        self.paint_scene(p, QPointF(self.geometry().topLeft()))
        p.end()

    def paint_scene(self, p: QPainter, o: QPointF) -> None:
        """The blast in screen coordinates shifted by `o`. Every monitor it crosses has a window
        painting this; the same random bolts each frame, so they line up across the edge."""
        rng = random.Random(int(self.t * 60))
        self._rng = rng
        hand, target, t = self.hand - o, self.target.translated(-o), self.t
        center = target.center()
        if t < IMPACT + 0.1:                                          # charging: sparks around her hand
            k = min(1.0, t / CHARGE)
            for _ in range(3):
                end = hand + QPointF(rng.uniform(-40, 40), rng.uniform(-40, 40)) * k
                lightning.draw(p, lightning.bolt(hand, end, rng, roughness=0.3, depth=3, branch=0.2), 0.8 * k, 0.7)
        if CHARGE <= t < FIRE_END:                                    # the blast
            k = 1 - max(0.0, (t - IMPACT) / (FIRE_END - IMPACT))
            lightning.draw(p, lightning.bolt(hand, center, rng, roughness=0.2, depth=6, branch=0.45), k, 1.6)
            for _ in range(2):                                        # forks that hit the window's edges
                lightning.draw(p, lightning.bolt(hand, self._perimeter(target), rng, roughness=0.22, depth=5,
                                                 branch=0.3), 0.6 * k, 0.9)
        if t >= IMPACT:                                               # the window gets fried
            k = max(0.0, 1 - (t - IMPACT) / (DONE - IMPACT))
            p.fillRect(target, QColor(236, 16, 70, int(90 * k)))
            for _ in range(int(2 + 4 * k)):                           # glitch slices
                y = target.top() + rng.random() * target.height()
                h = rng.uniform(3, 14)
                dx = rng.uniform(-30, 30) * k
                p.fillRect(QRectF(target.left() + dx, y, target.width(), h),
                           QColor(255, 60, 110, int(120 * k)) if rng.random() < 0.6 else QColor(10, 0, 8, int(140 * k)))
            spread = 34 if self.small else 90
            for _ in range(int(3 + 5 * k)):                           # arcs crawling over its edges
                a = self._perimeter(target)
                b = a + QPointF(rng.uniform(-spread, spread), rng.uniform(-spread, spread))
                lightning.draw(p, lightning.bolt(a, b, rng, roughness=0.3, depth=4, branch=0.35), k, 0.9)
            p.setPen(QColor(255, 170, 190, int(220 * k)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(target.adjusted(1, 1, -1, -1))
            if self.small:                                            # a shock ring around the button
                r = 10 + 40 * (1 - k)
                p.setPen(QColor(236, 16, 70, int(230 * k)))
                p.drawEllipse(center, target.width() / 2 + r, target.height() / 2 + r)


class _ZapMirror(OverlayWindow):
    """The blast on another monitor."""

    def __init__(self, scene: ZapFX) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.scene = scene

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        self.scene.paint_scene(p, QPointF(self.geometry().topLeft()))
        p.end()


class ZapShow(QObject):
    def __init__(self, companion: Companion, window_rect: Callable[[list[int]], QRect | None]) -> None:
        super().__init__()
        self.companion = companion
        self.window_rect = window_rect
        self.fx = ZapFX()
        self.mirrors: list[_ZapMirror] = []
        self.active = False
        self._then: Callable[[], None] | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    HOME_FIRST_MS = 380         # sitting on a window: her teleport home, then the zap

    def zap(self, name: str, pids: list[int], then: Callable[[], None]) -> None:
        """Blast the app's window, run `then` (the real close) at the impact."""
        try:
            rect = self.window_rect(pids)
        except Exception:
            rect = None
        self.zap_at(rect, then)

    def zap_at(self, rect: QRect | None, then: Callable[[], None], small: bool = False) -> None:
        """Fire at a spot on screen - a whole window, or (small=True) one button, like Discord's
        Mute - and run `then` at the impact."""
        c = self.companion
        perch = getattr(c, "window_perch", None)
        if not self.active and not c.hidden and getattr(c, "perched", False) and perch is not None:
            # Sitting on a window (maybe the one you're closing): teleport home first, then zap from there.
            perch.go_home()
            QTimer.singleShot(self.HOME_FIRST_MS, lambda: self.zap_at(rect, then, small))
            return
        if self.active or c.hidden or not c.character.isVisible():
            return then()
        screens = QGuiApplication.screens()
        if rect is None or not any(rect.intersects(s.geometry()) for s in screens):
            full = c.screen.geometry()
            rect = QRect(full.center().x() - 240, full.center().y() - 160, 480, 320)
        body = c.content_geometry()
        if c.lounging():                           # lying on the panel: from her hand, by her face
            hand = QPointF(body.left() + body.width() * 0.22, body.top() + body.height() * 0.62)
        else:
            toward = 1 if rect.center().x() > body.center().x() else -1
            hand = QPointF(body.center().x() + toward * body.width() * 0.45, body.top() + body.height() * 0.55)
        fx = self.fx
        fx.hand, fx.target, fx.t, fx.small = hand, QRectF(rect), 0.0, small
        area = QRect(rect).united(body).adjusted(-140, -140, 140, 140)
        # one window per monitor the blast crosses (hers first): each drawn at its own scaling
        pieces = [area.intersected(s.geometry()) for s in sorted(screens, key=lambda s: s is not c.screen)]
        pieces = [r for r in pieces if not r.isEmpty()] or [area.intersected(c.screen.geometry())]
        while len(self.mirrors) < len(pieces) - 1:
            self.mirrors.append(_ZapMirror(fx))
        for window, piece in zip([fx] + self.mirrors, pieces):
            window.setGeometry(piece)
            window.show()
            window.raise_()
        c.character.raise_()                       # she stays in front of her own lightning
        c.character.set_talking(True)              # she glitches with the power as she fires
        c.character.set_voice_level(0.95)
        self.active, self._then, self._start = True, then, time.monotonic()
        self._timer.start()

    def _tick(self) -> None:
        t = time.monotonic() - self._start
        self.fx.t = t
        if t >= IMPACT and self._then is not None:
            then, self._then = self._then, None
            then()                                 # the close itself
        if t >= FIRE_END and self.companion.character.talking:
            self.companion.character.set_talking(False)
        if t >= DONE:
            self._timer.stop()
            self.fx.hide()
            for m in self.mirrors:
                m.hide()
            self.active = False
            if self._then is not None:
                then, self._then = self._then, None
                then()
            return
        self.fx.update()
        for m in self.mirrors:
            if m.isVisible():
                m.update()
