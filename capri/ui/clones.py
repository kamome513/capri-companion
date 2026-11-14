"""Clones (2.4): "make 5 clones" - copies of her glitch in along the bottom of the screen, bob and look around for
a while, then glitch out. Click one and it pops. "Clear the clones" (or Esc via the menu) sends them all away.
Light: each clone is a picture of her taken once, moved and redrawn a few times a second."""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

from .overlay_window import OverlayWindow

MAX_CLONES = 24              # (2.4.2: more)
LIFE = (25.0, 45.0)          # seconds each one stays
GLITCH_IN = 0.45


class Clone(OverlayWindow):
    def __init__(self, picture: QImage, at: QPoint, life: float, rng: random.Random) -> None:
        super().__init__(True)
        self.picture = picture
        dpr = picture.devicePixelRatio() or 1.0
        self.resize(int(picture.width() / dpr), int(picture.height() / dpr))
        self.move(at)
        self.born = time.monotonic()
        self.life = life
        self.phase = rng.uniform(0, math.tau)
        self.flip = rng.random() < 0.5
        self.hue_shift = rng.choice((0, 0, 0, 1))              # now and then a cyan "glitch" clone
        self._timer = QTimer(self)
        self._timer.setInterval(66)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.clicked.connect(lambda _p: self.pop())
        self.popped = False

    def _tick(self) -> None:
        if time.monotonic() - self.born > self.life:
            self.pop()
        self.update()

    def pop(self) -> None:
        if self.popped:
            return
        self.popped = True
        self._timer.stop()
        self.close()
        self.deleteLater()

    def paintEvent(self, event) -> None:
        age = time.monotonic() - self.born
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bob = 3.0 * math.sin(age * 2.2 + self.phase)
        p.translate(0, bob)
        if self.flip:
            p.translate(self.width(), 0)
            p.scale(-1, 1)
        fade_in = min(1.0, age / GLITCH_IN)
        fade_out = min(1.0, max(0.0, (self.life - age) / GLITCH_IN))
        p.setOpacity(0.92 * min(fade_in, fade_out))
        target = QRectF(0, 0, self.width(), self.height())
        if fade_in < 1.0 or fade_out < 1.0:                    # glitching in / out: torn, shifted slices
            rng = random.Random(int(age * 30))
            h = self.picture.height()
            for i in range(8):
                y0, y1 = h * i / 8, h * (i + 1) / 8
                dx = rng.uniform(-14, 14) * (1 - min(fade_in, fade_out))
                src = QRectF(0, y0, self.picture.width(), y1 - y0)
                dpr = self.picture.devicePixelRatio() or 1.0
                p.drawImage(QRectF(dx, y0 / dpr, self.width(), (y1 - y0) / dpr), self.picture, src)
        else:
            p.drawImage(target, self.picture)
        if self.hue_shift:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            p.fillRect(target, QColor(0, 226, 255, 70))
        p.end()


class Clones:
    def __init__(self, picture_of_her, rng: random.Random | None = None) -> None:
        self.picture_of_her = picture_of_her                  # () -> QImage of her as she is now (or None)
        self.rng = rng or random.Random()
        self.clones: list[Clone] = []

    def make(self, n: int, life: float | None = None, area=None) -> int:
        """Up to MAX_CLONES at once. Returns how many she made."""
        self.clones = [c for c in self.clones if not c.popped]
        n = max(0, min(int(n), MAX_CLONES - len(self.clones)))
        pic = self.picture_of_her()
        if not n or pic is None or pic.isNull():
            return 0
        if area is None:                                       # (the screen; a test can pass its own area)
            screen = QGuiApplication.primaryScreen()
            area = screen.availableGeometry() if screen is not None else None
        if area is None:
            return 0
        dpr = pic.devicePixelRatio() or 1.0
        w, h = int(pic.width() / dpr), int(pic.height() / dpr)
        # (2.4.2) spread out over the whole screen: one per slice of its width (a little jitter in each), at any
        # height from a quarter of the way down to the bottom - not bunched up along the floor
        span = max(1, area.width() - w)
        slots = list(range(n))
        self.rng.shuffle(slots)
        top = area.top() + area.height() // 4
        for k in slots:
            x = area.left() + int(span * (k + self.rng.uniform(0.3, 0.7)) / n)
            y = self.rng.randint(min(top, area.bottom() - h), max(top, area.bottom() - h))
            c = Clone(pic, QPoint(x, y), life if life is not None else self.rng.uniform(*LIFE), self.rng)
            c.show()
            self.clones.append(c)
        return n

    def clear(self) -> int:
        n = len([c for c in self.clones if not c.popped])
        for c in self.clones:
            c.pop()
        self.clones.clear()
        return n

    @property
    def count(self) -> int:
        return len([c for c in self.clones if not c.popped])
