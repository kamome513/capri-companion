"""D on the video call, brought to life from one picture (assets/d/d.png).

The picture is cut at his neck into a head and a body (with a soft overlap, so no gap
shows), and then:
* talking  - his mouth opens and closes with his voice, his head nods and tilts with
             what he's saying, now and then a little shake;
* listening (her turn) - a slow head tilt, the odd nod, a glance to the side;
* always   - he breathes (shoulders rise and fall) and blinks every few seconds.

The face spots below are for the supplied picture; another picture of D drawn the same
way round (facing the viewer, head at the top) works with the same numbers roughly.
"""

from __future__ import annotations

import math
import random

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

# Where things are on the picture, as shares of its width / height (220 x 360 for assets/d/d.png).
CROP = (0.036, 0.0, 0.727, 0.444)          # head and shoulders: x, y, w, h
NECK = (90 / 220, 82 / 360)                 # his head turns about here
CUT = (80 / 360, 87 / 360)                  # head / body overlap rows (soft edge in between)
EYES = ((75.8 / 220, 58 / 360), (95 / 220, 50.8 / 360))
EYE_R = 3.4 / 220
MOUTH = (92.5 / 220, 73.5 / 360)
MOUTH_W = 10 / 220


def _split(img: QImage) -> tuple[QImage, QImage]:
    """(head, body) layers of the picture, overlapping with soft edges across the neck."""
    src = img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    h, w = src.height(), src.width()
    a = np.frombuffer(src.constBits(), np.uint8).reshape(h, src.bytesPerLine() // 4, 4)[:, :w].astype(np.float32)
    rows = np.arange(h, dtype=np.float32)[:, None, None]
    top, bottom = CUT[0] * h, CUT[1] * h
    head = np.clip((bottom - rows) / max(1.0, bottom - top), 0, 1)               # 1 above the neck, 0 below
    body = np.clip((rows - top) / max(1.0, (bottom - top) * 0.5), 0, 1)          # 0 above, 1 below

    def layer(mask: np.ndarray) -> QImage:
        out = np.ascontiguousarray((a * mask).astype(np.uint8))
        return QImage(out.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888_Premultiplied).copy()
    return layer(head), layer(body)


class Puppet:
    def __init__(self, image: QImage) -> None:
        self.image = image
        self.w, self.h = image.width(), image.height()
        self._layers: tuple | None = None
        self._lids: list[QColor] = []
        for ex, ey in EYES:                                    # his skin just above each eye, for the lids
            c = image.pixelColor(round(ex * self.w), max(0, round(ey * self.h - EYE_R * self.w * 1.4)))
            self._lids.append(c if c.alpha() > 200 else QColor(232, 200, 188))
        self._rng = random.Random(4)
        self._next_blink, self._blink_at = 1.5, -1.0
        self._nods: list[float] = []

    def _scaled(self, k: float) -> tuple[QImage, QImage, float]:
        """Head and body layers pre-scaled by k (so they're drawn 1:1 - sharp), cached."""
        if self._layers is None or abs(self._layers[2] - k) > 1e-3:
            w, h = max(1, round(self.w * k)), max(1, round(self.h * k))
            small = self.image.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            head, body = _split(small)
            self._layers = (head, body, k)
        return self._layers

    def paint(self, p: QPainter, v: QRectF, now: float, mouth: float, speaking: bool, dpr: float = 1.0) -> None:
        """Draw him filling the video rect `v`. mouth 0..1 (his voice), speaking = his turn."""
        cx, cy, cw, ch = CROP[0] * self.w, CROP[1] * self.h, CROP[2] * self.w, CROP[3] * self.h
        k = max(v.width() / cw, v.height() / ch)
        head, body, kk = self._scaled(k * dpr)
        nx, ny = NECK[0] * self.w, NECK[1] * self.h
        # his head: nods / tilts while he talks, a slow tilt and the odd nod while he listens
        if speaking:
            angle = 2.6 * math.sin(now * 4.1) + 1.4 * math.sin(now * 7.3)
            if math.sin(now * 0.9) > 0.93:                       # a little shake of the head
                angle += 3.0 * math.sin(now * 22)
            lift = -0.8 * abs(math.sin(now * 8.5))
            look = 0.0
        else:
            angle = 3.2 * math.sin(now * 0.7)
            lift = 0.9 * max(0.0, math.sin(now * 2.4)) if math.sin(now * 0.45) > 0.6 else 0.0   # nodding along
            look = 1.2 if math.sin(now * 0.33) > 0.7 else 0.0  # a glance aside
        breathe = 1 + 0.012 * math.sin(now * 2.1)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(v.left(), v.top())
        p.scale(k, k)
        p.translate(-cx, -cy)                                    # now in picture pixels
        # body (breathing: the shoulders rise a touch)
        p.save()
        bottom = cy + ch
        p.translate(0, bottom)
        p.scale(1, breathe)
        p.translate(0, -bottom)
        p.scale(1 / kk, 1 / kk)
        p.drawImage(QPointF(0, 0), body)
        p.restore()
        # head
        p.save()
        p.translate(nx, ny + lift - (breathe - 1) * (bottom - ny))
        p.rotate(angle)
        p.translate(-nx + look, -ny)
        p.save()
        p.scale(1 / kk, 1 / kk)
        p.drawImage(QPointF(0, 0), head)
        p.restore()
        self._face(p, now, mouth)
        p.restore()
        p.restore()

    def _face(self, p: QPainter, now: float, mouth: float) -> None:
        """Blinks and his mouth, in picture pixels."""
        if now > self._next_blink:
            self._blink_at, self._next_blink = now, now + self._rng.uniform(2.2, 5.0)
        r = EYE_R * self.w
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if 0 <= now - self._blink_at < 0.16:
            for (ex, ey), lid in zip(EYES, self._lids):
                c = QPointF(ex * self.w, ey * self.h)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(lid)
                p.drawEllipse(c, r * 1.25, r * 0.85)
                p.setPen(QPen(QColor(30, 30, 40), 0.9))
                p.drawLine(c - QPointF(r * 1.1, -r * 0.2), c + QPointF(r * 1.1, r * 0.2))
        if mouth > 0.05:
            mx, my = MOUTH[0] * self.w, MOUTH[1] * self.h
            half, tall = MOUTH_W * self.w * 0.42, 0.8 + 3.2 * mouth
            p.setPen(QPen(QColor(70, 30, 40), 0.7))
            p.setBrush(QColor(90, 20, 34))
            p.drawRoundedRect(QRectF(mx - half, my - tall * 0.35, half * 2, tall), tall * 0.45, tall * 0.45)
            if mouth > 0.45:                                     # a hint of teeth
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(240, 236, 232))
                p.drawRect(QRectF(mx - half * 0.7, my - tall * 0.35 + 0.3, half * 1.4, 0.8))
