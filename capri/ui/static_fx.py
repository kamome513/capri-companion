"""TV static + scanlines + glitch bursts for the status panel (the cyberpunk "dead channel" look)."""

from __future__ import annotations

import random
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

FRAMES = 6                 # pre-made noise frames, cycled (cheap: no noise is generated per frame)
IDLE_OPACITY = 0.11        # always-on static: subtle, like a dead channel behind the text
BURST_OPACITY = 0.45       # on a status change: a quick hit of heavy static
BURST_SECONDS = 0.35
CYAN = QColor(0, 230, 255)
MAGENTA = QColor(255, 40, 200)


class StaticFX:
    def __init__(self, seed: int = 3) -> None:
        self._rng = random.Random(seed)
        self._np = np.random.default_rng(seed)
        self._frames: list[QImage] = []
        self._size = (0, 0)
        self._frame = 0
        self.burst_until = 0.0

    def burst(self) -> None:
        self.burst_until = time.monotonic() + BURST_SECONDS

    @property
    def bursting(self) -> bool:
        return time.monotonic() < self.burst_until

    def step(self) -> None:
        self._frame = (self._frame + 1 + self._rng.randrange(FRAMES - 1)) % FRAMES

    def _noise(self, w: int, h: int) -> QImage:
        if (w, h) != self._size:
            self._size = (w, h)
            self._frames = []
            for _ in range(FRAMES):
                grey = self._np.integers(0, 256, (h, w), dtype=np.uint8)
                rgba = np.dstack([grey, grey, grey, np.full_like(grey, 255)])
                img = QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
                self._frames.append(img)
        return self._frames[self._frame % FRAMES]

    def paint(self, p: QPainter, shape: QPainterPath, body: QRectF) -> None:
        """Draw inside the panel body: static, scanlines, and during a burst, tearing bars."""
        w, h = max(1, int(body.width())), max(1, int(body.height()))
        burst = self.bursting
        p.save()
        p.setClipPath(shape)
        p.setOpacity(BURST_OPACITY if burst else IDLE_OPACITY)
        p.drawImage(body.topLeft(), self._noise(w, h))
        p.setOpacity(1.0)
        line = QColor(0, 0, 0, 70)
        y = body.top()
        while y < body.bottom():                                  # CRT scanlines
            p.fillRect(QRectF(body.left(), y, body.width(), 1), line)
            y += 3
        if burst:
            for _ in range(self._rng.randint(2, 4)):              # tearing glitch bars
                by = body.top() + self._rng.random() * body.height()
                bh = self._rng.uniform(1.5, 5)
                c = QColor(self._rng.choice((CYAN, MAGENTA, QColor(57, 230, 107))))
                c.setAlpha(self._rng.randint(90, 170))
                bx = body.left() + self._rng.uniform(-20, body.width() * 0.5)
                p.fillRect(QRectF(bx, by, self._rng.uniform(40, body.width()), bh), c)
        p.restore()

    def paint_border(self, p: QPainter, shape: QPainterPath) -> None:
        """A split-colour (chromatic) edge: faint always, strong during a burst."""
        burst = self.bursting
        alpha = 160 if burst else 45
        shift = self._rng.uniform(1.5, 3.5) if burst else 1.0
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)              # outline only - never refill the panel
        for color, dx in ((CYAN, -shift), (MAGENTA, shift)):
            c = QColor(color)
            c.setAlpha(alpha)
            p.setPen(QPen(c, 1.0))
            p.drawPath(shape.translated(QPointF(dx, 0)))
        p.restore()
