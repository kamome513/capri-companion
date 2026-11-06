"""Her own cursor: a little hot-pink, angular pointer that glides to wherever she's about to click or type - while
she plays a game for you, clicks a button you asked for, or types into an app - so you can see what she's doing.
Click-through; it disappears a moment after she's done."""

from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from . import fx
from .overlay_window import OverlayWindow

SIZE = 34
PINK = QColor(255, 46, 122)          # hot pink-red, like her hair
GLOW = QColor(255, 46, 122, 90)


class HerCursor(OverlayWindow):
    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.resize(SIZE, SIZE)
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.timeout.connect(self.hide)
        self._clicked_at = -1e9
        self._pulse = fx.precise_timer(self, 16)
        self._pulse.timeout.connect(self.update)

    def glide(self, x: int, y: int) -> None:
        """Move (smoothly) so the tip is at screen point x, y (logical pixels), and ripple there."""
        target = QPoint(x - 4, y - 4)
        if not self.isVisible():
            self.move(target + QPoint(-60, -40))
            self.show()
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(target)
        self._anim.start()
        self._clicked_at = time.monotonic() + 0.22
        self._pulse.start()
        self._hide.start(2500)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tip = QPointF(4, 4)
        age = time.monotonic() - self._clicked_at
        if 0 <= age < 0.45:                                  # a ripple where she clicks
            k = age / 0.45
            ring = QColor(PINK)
            ring.setAlpha(int(230 * (1 - k)))
            p.setPen(QPen(ring, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(tip, 3 + 12 * k, 3 + 12 * k)
        elif age > 0.6:
            self._pulse.stop()
        arrow = QPainterPath(tip)
        for pt in ((19, 11), (12.5, 13), (15.5, 21.5), (11.5, 23), (8.5, 15), (4, 19)):   # a little shard pointer
            arrow.lineTo(QPointF(*pt))
        arrow.closeSubpath()
        p.setPen(QPen(GLOW, 5))
        p.drawPath(arrow)                                    # glow
        p.setPen(QPen(QColor(255, 255, 255), 1.2))
        p.setBrush(PINK)
        p.drawPath(arrow)
        p.end()
