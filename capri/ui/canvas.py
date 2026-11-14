"""Her drawing layer (2.4): she draws on your screen with her pink cursor - circles round things, highlights,
arrows pointing at things, and little doodles (a heart, a star, a smiley, a cat...). A see-through, click-through
window over the screen she's drawing on: you can keep using everything under it. Drawings fade away by themselves
(or "clear the drawing"). Nothing on your screen is changed - it's only drawn over.

Each mark is drawn stroke by stroke, with her cursor following the pen.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen

from . import theme
from .overlay_window import OverlayWindow

PINK = QColor(255, 46, 122)
CYAN = QColor(0, 226, 255)
YELLOW = QColor(255, 230, 0)
DRAW_SECONDS = 0.9           # how long one mark takes to draw
STAY_SECONDS = 9.0           # how long a finished mark stays
FADE_SECONDS = 1.2


@dataclass
class Mark:
    points: list                # [QPointF] in screen coordinates (one stroke; closed shapes repeat the first point)
    colour: QColor
    width: float = 5.0
    fill: QColor | None = None  # highlights: a see-through fill
    label: str = ""
    label_at: QPointF | None = None
    started: float = field(default_factory=time.monotonic)
    draw_for: float = DRAW_SECONDS
    stay: float = STAY_SECONDS

    def progress(self, now: float) -> float:
        return max(0.0, min(1.0, (now - self.started) / max(0.01, self.draw_for)))

    def alpha(self, now: float) -> float:
        age = now - self.started - self.draw_for - self.stay
        return 1.0 if age <= 0 else max(0.0, 1.0 - age / FADE_SECONDS)

    def done(self, now: float) -> bool:
        return self.alpha(now) <= 0.0


# -- shapes (points of one stroke, around 0,0 in a 1x1 box) -------------------------------------------------------
def _ellipse(n: int = 48, wobble: float = 0.04) -> list[tuple[float, float]]:
    pts = []
    for i in range(n + 3):                                    # a little overshoot, like a hand-drawn circle
        a = -math.pi / 2 + 2 * math.pi * i / n
        r = 1.0 + wobble * math.sin(i * 1.7)
        pts.append((0.5 + 0.5 * r * math.cos(a), 0.5 + 0.5 * r * math.sin(a)))
    return pts


def _heart(n: int = 60):
    pts = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((0.5 + x / 34, 0.45 + y / 34))
    return pts


def _star():
    pts = []
    for i in range(11):
        a = -math.pi / 2 + i * math.pi / 5
        r = 0.5 if i % 2 == 0 else 0.2
        pts.append((0.5 + r * math.cos(a), 0.5 + r * math.sin(a)))
    return pts


def _smiley():
    face = _ellipse(40, 0.02)
    smile = [(0.5 + 0.28 * math.cos(a), 0.52 + 0.22 * math.sin(a)) for a in
             [math.pi * (0.15 + 0.7 * i / 12) for i in range(13)]]
    return face, smile, [(0.36, 0.36), (0.37, 0.4)], [(0.63, 0.36), (0.64, 0.4)]


def _cat():
    head = _ellipse(40, 0.02)
    ears = [(0.18, 0.28), (0.22, 0.0), (0.4, 0.12), (0.6, 0.12), (0.78, 0.0), (0.82, 0.28)]
    whisk_l = [(0.05, 0.6), (0.32, 0.62)]
    whisk_r = [(0.68, 0.62), (0.95, 0.6)]
    eyes = [(0.36, 0.45), (0.37, 0.5)]
    eyes2 = [(0.63, 0.45), (0.64, 0.5)]
    return head, ears, whisk_l, whisk_r, eyes, eyes2


def _lightning():
    return [(0.6, 0.0), (0.25, 0.55), (0.5, 0.55), (0.35, 1.0), (0.78, 0.4), (0.52, 0.4), (0.7, 0.0)]


DOODLES = {"heart": lambda: [_heart()], "star": lambda: [_star()], "smiley": lambda: list(_smiley()),
           "cat": lambda: list(_cat()), "lightning": lambda: [_lightning()], "circle": lambda: [_ellipse()]}
DOODLE_COLOURS = {"heart": PINK, "star": YELLOW, "smiley": YELLOW, "cat": CYAN, "lightning": YELLOW, "circle": PINK}


def place(shape: list[tuple[float, float]], box: QRectF) -> list[QPointF]:
    return [QPointF(box.x() + x * box.width(), box.y() + y * box.height()) for x, y in shape]


class ScreenCanvas(OverlayWindow):
    """Covers one screen; shown only while something is drawn on it."""

    def __init__(self, cursor: Callable[[int, int], None] | None = None) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.cursor = cursor or (lambda x, y: None)           # her pink cursor follows the pen (logical px)
        self.marks: list[Mark] = []
        self._origin = QPointF(0, 0)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._font = QFont(theme.MONO_FAMILIES[0])
        self._font.setFamilies(theme.MONO_FAMILIES)
        self._font.setBold(True)
        self._font.setPixelSize(18)

    # -- what she draws ---------------------------------------------------------------------------------------------
    def _cover(self, at: QPointF) -> None:
        screen = QGuiApplication.screenAt(at.toPoint()) or QGuiApplication.primaryScreen()
        geo = screen.geometry() if screen is not None else QRect(0, 0, 1920, 1080)
        if self.geometry() != geo:
            self.setGeometry(geo)
        self._origin = QPointF(geo.topLeft())

    def add(self, mark: Mark) -> Mark:
        if mark.points:
            self._cover(mark.points[0])
        delay = sum(max(0.0, m.started + m.draw_for - time.monotonic()) for m in self.marks[-1:])
        mark.started = time.monotonic() + delay                 # one after another, like real drawing
        self.marks.append(mark)
        self.show()
        self.raise_()
        self._timer.start()
        return mark

    def circle(self, rect: QRectF, label: str = "", colour: QColor = PINK) -> Mark:
        pad = max(10.0, 0.18 * max(rect.width(), rect.height()))
        box = rect.adjusted(-pad, -pad * 0.8, pad, pad * 0.8)
        return self.add(Mark(place(_ellipse(), box), QColor(colour), 5.0, label=label,
                             label_at=QPointF(box.right() + 8, box.top())))

    def highlight(self, rect: QRectF, label: str = "", colour: QColor = YELLOW) -> Mark:
        box = rect.adjusted(-4, -4, 4, 4)
        fill = QColor(colour)
        fill.setAlpha(60)
        pts = [box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft(), box.topLeft()]
        return self.add(Mark(pts, QColor(colour), 3.0, fill=fill, label=label,
                             label_at=QPointF(box.left(), box.top() - 10)))

    def point(self, at: QPointF, label: str = "", colour: QColor = CYAN) -> Mark:
        """An arrow from up-left, its tip on `at`."""
        start = QPointF(at.x() - 110, at.y() - 80)
        tip = QPointF(at)
        ang = math.atan2(tip.y() - start.y(), tip.x() - start.x())
        head = [QPointF(tip.x() - 22 * math.cos(ang - 0.45), tip.y() - 22 * math.sin(ang - 0.45)), tip,
                QPointF(tip.x() - 22 * math.cos(ang + 0.45), tip.y() - 22 * math.sin(ang + 0.45))]
        steps = [QPointF(start.x() + (tip.x() - start.x()) * i / 12, start.y() + (tip.y() - start.y()) * i / 12)
                 for i in range(13)]
        return self.add(Mark(steps + head, QColor(colour), 5.0, label=label, label_at=QPointF(start.x() - 10,
                                                                                             start.y() - 12)))

    def doodle(self, name: str, box: QRectF) -> bool:
        """A little drawing in `box` (heart, star, smiley, cat, lightning, circle). False if she can't draw that."""
        make = DOODLES.get(name)
        if make is None:
            return False
        for stroke in make():
            self.add(Mark(place(stroke, box), QColor(DOODLE_COLOURS.get(name, PINK)), 5.0,
                          draw_for=0.5 + 0.02 * len(stroke)))
        return True

    def clear(self) -> None:
        self.marks.clear()
        self._timer.stop()
        self.hide()

    # -- drawing ----------------------------------------------------------------------------------------------------
    def _tick(self) -> None:
        now = time.monotonic()
        self.marks = [m for m in self.marks if not m.done(now)]
        if not self.marks:
            return self.clear()
        live = [m for m in self.marks if 0 < (now - m.started) < m.draw_for]
        if live:                                                # her cursor at the pen's tip
            m = live[-1]
            k = m.progress(now)
            tip = m.points[min(len(m.points) - 1, int(k * (len(m.points) - 1)))]
            self.cursor(int(tip.x()), int(tip.y()))
        self.update()

    def paintEvent(self, event) -> None:
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(-self._origin)
        for m in self.marks:
            if now < m.started:
                continue
            k, a = m.progress(now), m.alpha(now)
            n = max(2, int(round(k * (len(m.points) - 1))) + 1)
            path = QPainterPath(m.points[0])
            for pt in m.points[1:n]:
                path.lineTo(pt)
            if m.fill is not None and k >= 1.0:
                fill = QColor(m.fill)
                fill.setAlphaF(fill.alphaF() * a)
                p.fillPath(path, fill)
            for width, alpha in ((m.width * 3.2, 0.22), (m.width, 1.0)):   # glow, then the line
                c = QColor(m.colour)
                c.setAlphaF(alpha * a)
                pen = QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.drawPath(path)
            if m.label and k >= 1.0 and m.label_at is not None:
                p.setFont(self._font)
                c = QColor(255, 255, 255)
                c.setAlphaF(a)
                p.setPen(c)
                p.drawText(m.label_at, m.label[:60])
        p.end()
