"""Game mode: while you play, Capri shrinks into a little flying disk - a broken-up ring of
her red / green / black shards slowly spinning around her eye, hovering out of the way.

The eye looks around and blinks, the shards drift apart and snap back, a red spark
jumps off now and then, and it all glows brighter while she talks. ~110 px, 30 fps
only while it's on screen.
"""

from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient

from . import lightning, looks
from .overlay_window import OverlayWindow

SIZE = 112
SHARDS = 12
COLORS = [QColor(236, 16, 70), QColor(40, 214, 120), QColor(16, 10, 20), QColor(150, 8, 44)]
EYE_BLUE = QColor(70, 150, 255)


MASK_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "drone" / "mask.png"
MASK_GREEN = QColor(16, 238, 112)


GREEN_RGBA = np.array([MASK_GREEN.red(), MASK_GREEN.green(), MASK_GREEN.blue(), 255], np.uint8)
SEAM = 6                   # rows of the fin tucked under the part it sways from
JOINT = 26                 # rows of green behind the fin's base: what shows as it sways


class MaskDrone:
    """The other drone look: her green visor with its fin - eyes that look around and blink,
    the fin wiggling from its base, the zigzag mouth chattering as she talks."""

    def __init__(self, path: Path = MASK_FILE) -> None:
        look = looks.analyse("mask", QImage(str(path)))
        a = looks.to_array(look.image)
        h, w = a.shape[:2]
        rgb = a[..., :3].astype(int)
        green = (a[..., 3] > 128) & (rgb[..., 1] > 190) & (rgb[..., 0] < 120)
        band = np.flatnonzero(green.mean(1) > 0.45)
        fin_top = int(band[0]) if len(band) else h // 3          # where the fin's tip joins its body
        # the visor: the solid band around her eyes; the zigzag below it is the mouth
        rows = (a[..., 3] > 128).mean(1)
        eye_y = int(np.mean([e[1] for e in look.eyes])) if look.eyes else int(h * 0.65)
        top = bottom = min(h - 1, max(0, eye_y))
        while top > 0 and rows[top - 1] > 0.2:
            top -= 1
        while bottom + 1 < h and rows[bottom + 1] > 0.2:
            bottom += 1
        self.w, self.h, self.top, self.bottom, self.fin_top = w, h, top, bottom, fin_top

        def rows_of(y0: int, y1: int, src=a) -> QImage:
            part = src.copy()
            part[:y0, :, 3] = 0
            part[y1:, :, 3] = 0
            return looks.to_image(part)
        # the irises, cut out so they can move inside the whites of her eyes
        self.eyes, self.irises = [], []
        middle = a.copy()
        yy, xx = np.mgrid[0:h, 0:w]
        for x, y, r in look.eyes:
            dist = np.hypot(xx - x, yy - y)
            blue = (rgb[..., 2] > 150) & (rgb[..., 0] < 100)
            white = (rgb >= 225).all(-1)
            iris = (dist <= r * 1.05) & (blue | (white & (dist < r * 0.55)))
            layer = np.zeros_like(a)
            layer[iris] = a[iris]
            self.irises.append(looks.to_image(layer))
            middle[iris, :3] = 255
            self.eyes.append((x, y, r))
        base = np.flatnonzero(a[max(0, fin_top - 2), :, 3] > 128)
        cols = np.zeros(w, bool)
        if len(base):
            cols[max(0, base.min() - 2):base.max() + 3] = True
        fin = a.copy()                                        # the tip, reaching a little way under
        fin[fin_top + SEAM:, :, 3] = 0                        # the body it sways from
        fin[fin_top:fin_top + SEAM, ~cols, 3] = 0
        self.fin = looks.to_image(fin)
        # behind the tip's base: plain green, so the gap it opens as it sways is green, not see-through
        joint = np.zeros_like(a)
        patch = np.zeros((h, w), bool)
        patch[max(0, fin_top - JOINT):fin_top + 2] = a[max(0, fin_top - JOINT):fin_top + 2, :, 3] > 128
        patch = looks._grow(looks._grow(patch)) & (yy >= fin_top - JOINT)
        joint[patch] = GREEN_RGBA
        self.joint = looks.to_image(joint)
        self.visor = rows_of(fin_top, bottom + 1, middle)
        self.mouth = rows_of(bottom + 1, h)
        self.pivot = QPointF(float(base.mean()) if len(base) else w * 0.4, float(fin_top))
        self.mouth_top = bottom + 1
        self._rng = random.Random(8)
        self._blink_at, self._next_blink = -10.0, 2.5
        self._look, self._target, self._next_look = QPointF(), QPointF(), 1.0

    def _layers(self, height: float, dpr: float) -> dict:
        """Every part pre-scaled once (smoothly) to its size on screen - clean edges, no shimmer."""
        key = (round(height * dpr), dpr)
        if getattr(self, "_scaled_key", None) != key:
            w, h = max(1, round(self.w * height / self.h * dpr)), max(1, round(height * dpr))

            def fit(img: QImage) -> QImage:
                out = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                out.setDevicePixelRatio(dpr)
                return out
            self._scaled = {"fin": fit(self.fin), "visor": fit(self.visor), "mouth": fit(self.mouth),
                            "joint": fit(self.joint),
                            "irises": [fit(i) for i in self.irises]}
            self._scaled_key = key
        return self._scaled

    def paint(self, p: QPainter, c: QPointF, height: float, t: float, energy: float, dpr: float = 1.0) -> None:
        s = height / self.h                                       # picture px -> screen px
        layers = self._layers(height, dpr)
        dt = max(0.0, min(0.1, t - getattr(self, "_last_t", t)))
        self._last_t = t
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(c.x() - self.w * s / 2, c.y() - self.h * s / 2)
        if t > self._next_look:                                   # her eyes wander, easing over
            self._target = QPointF(self._rng.uniform(-1, 1), self._rng.uniform(-0.6, 0.6))
            self._next_look = t + self._rng.uniform(0.8, 2.4)
        self._look += (self._target - self._look) * (1 - math.exp(-dt * 7))
        pivot = self.pivot * s
        p.drawImage(QPointF(0, 0), layers["joint"])               # green behind where the fin sways
        p.save()                                                  # the fin, swaying from its base
        p.translate(pivot)
        p.rotate(5 * math.sin(t * 2.1) + 1.5 * math.sin(t * 3.7) + 9 * energy * math.sin(t * 11))
        p.translate(-pivot)
        p.drawImage(QPointF(0, 0), layers["fin"])
        p.restore()
        p.drawImage(QPointF(0, 0), layers["visor"])
        for (x, y, r), iris in zip(self.eyes, layers["irises"]):
            p.drawImage(QPointF(self._look.x() * r * 0.45 * s, self._look.y() * r * 0.35 * s), iris)
        if t > self._next_blink:
            self._blink_at, self._next_blink = t, t + self._rng.uniform(2.5, 6.0)
        b = (t - self._blink_at) / 0.18
        shut = math.sin(math.pi * b) if 0 <= b < 1 else 0.0       # eases shut and open
        if shut > 0:
            for x, y, r in self.eyes:
                rx, ry, cx, cy = r * 1.9 * s, r * 1.8 * s, x * s, y * s
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(MASK_GREEN)
                p.drawEllipse(QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry * shut))
                if shut > 0.6:
                    p.setPen(QPen(QColor(110, 40, 210), max(1.0, r * 0.18 * s)))
                    p.drawLine(QPointF(cx - rx * 0.8, cy), QPointF(cx + rx * 0.8, cy + r * 0.1 * s))
        p.save()                                                  # the mouth opens with her voice
        jaw = self.mouth_top * s
        p.translate(0, jaw)
        p.scale(1, 1 + 0.45 * energy)
        p.translate(0, -jaw)
        p.drawImage(QPointF(0, 0), layers["mouth"])
        p.restore()
        p.restore()


class DroneWindow(OverlayWindow):
    def __init__(self, always_on_top: bool = True) -> None:
        super().__init__(always_on_top)
        self.setWindowTitle("Capri - drone")
        self.resize(SIZE, SIZE)
        self.level = 0.0
        self.talking = False
        self._t0 = time.monotonic()
        self._rng = random.Random(5)
        self._next_blink = 3.0
        self._blink_at = -1.0
        self._look = QPointF()
        self._look_target = QPointF()
        self._next_look = 1.0
        self._spark: tuple[float, float] | None = None       # (start, angle)
        self._glitch = (-1.0, 0)                               # (until, shard)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)   # frames on time
        self._timer.timeout.connect(self.update)
        self.style = "disk"
        self._mask: MaskDrone | None = None

    def set_style(self, style: str) -> None:
        """"disk" (shards round her eye) or "mask" (her green visor with its fin)."""
        self.style = style if style in ("disk", "mask") else "disk"
        if self.style == "mask" and self._mask is None:
            try:
                self._mask = MaskDrone()
            except Exception:
                self.style = "disk"
        self._timer.setInterval(16 if self.style == "mask" else 33)   # the mask glides at 60 fps
        self.update()

    # -- driven by her voice (same signals as the character) -----------------------------------
    def set_voice_level(self, level: float) -> None:
        self.level = level

    def set_talking(self, on: bool) -> None:
        self.talking = on
        if not on:
            self.level = 0.0

    def center_offset(self) -> QPointF:
        """Where the disk's middle is inside the window."""
        return QPointF(SIZE / 2, SIZE / 2)

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    # -- drawing ------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        t = time.monotonic() - self._t0
        rng = self._rng
        energy = min(1.0, self.level * 1.4) if self.talking else 0.0
        c = QPointF(SIZE / 2, SIZE / 2 + 3 * math.sin(t * 2.2))       # hovering
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.style == "mask" and self._mask is not None:
            glow = QRadialGradient(c, 50)
            glow.setColorAt(0, QColor(16, 238, 112, int(40 + 110 * energy)))
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(c, 50, 50)
            # a little smaller and higher than the disk: room for the fin to sway and the mouth to open
            self._mask.paint(p, c - QPointF(0, 5), SIZE - 24, t, energy, self.devicePixelRatioF())
            p.end()
            return

        glow = QRadialGradient(c, 46)
        glow.setColorAt(0, QColor(236, 16, 70, int(70 + 90 * energy)))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, 46, 46)

        # the broken ring: shards drifting apart and back, spinning (faster when she talks)
        if t > self._glitch[0] and rng.random() < 0.02:
            self._glitch = (t + 0.15, rng.randrange(SHARDS))
        spin = t * (24 + 90 * energy)
        for i in range(SHARDS):
            a = math.radians(spin + i * 360 / SHARDS)
            half = math.radians(360 / SHARDS / 2 - 4)
            gap = 2.5 + 2.5 * math.sin(t * 2.6 + i * 1.7)
            if t < self._glitch[0] and i == self._glitch[1]:
                gap += 7
            r_in, r_out = 21 + gap, 36 + gap + 3 * math.sin(t * 3.1 + i)
            pts = [QPointF(c.x() + math.cos(a - half) * r_in, c.y() + math.sin(a - half) * r_in),
                   QPointF(c.x() + math.cos(a - half * 0.7) * r_out, c.y() + math.sin(a - half * 0.7) * r_out),
                   QPointF(c.x() + math.cos(a + half) * (r_out - 5), c.y() + math.sin(a + half) * (r_out - 5)),
                   QPointF(c.x() + math.cos(a + half * 0.9) * (r_in + 3), c.y() + math.sin(a + half * 0.9) * (r_in + 3))]
            path = QPainterPath(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            path.closeSubpath()
            p.setPen(QPen(QColor(8, 4, 10), 1.2))
            p.setBrush(COLORS[i % len(COLORS)])
            p.drawPath(path)

        # the eye
        if t > self._next_blink:
            self._blink_at, self._next_blink = t, t + rng.uniform(2.5, 6.0)
        open_ = 1.0
        if 0 <= t - self._blink_at < 0.14:
            open_ = abs(1 - (t - self._blink_at) / 0.07)
        if t > self._next_look:
            self._look_target = QPointF(rng.uniform(-3.5, 3.5), rng.uniform(-2.5, 2.5))
            self._next_look = t + rng.uniform(0.8, 2.4)
        self._look += (self._look_target - self._look) * 0.15
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 6, 12))
        p.drawEllipse(c, 15, 15)
        sclera = QRectF(c.x() - 11, c.y() - 9 * open_, 22, 18 * open_)
        p.setBrush(QColor(236, 240, 255))
        p.drawEllipse(sclera)
        if open_ > 0.25:
            iris = c + self._look
            p.save()
            p.setClipRect(sclera)
            ig = QRadialGradient(iris, 6.5)
            ig.setColorAt(0, QColor(150, 210, 255))
            ig.setColorAt(1, EYE_BLUE.darker(130 - int(30 * energy)))
            p.setBrush(ig)
            p.drawEllipse(iris, 6.2, 6.2)
            p.setBrush(QColor(4, 4, 10))
            p.drawEllipse(iris, 2.4, 2.4)
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawEllipse(iris + QPointF(-1.8, -1.8), 1.2, 1.2)
            p.restore()

        # a stray red spark now and then (more while she talks)
        if self._spark is None and rng.random() < 0.015 + 0.05 * energy:
            self._spark = (t, rng.uniform(0, math.tau))
        if self._spark is not None:
            start, ang = self._spark
            k = (t - start) / 0.25
            if k >= 1:
                self._spark = None
            else:
                a = c + QPointF(math.cos(ang) * 34, math.sin(ang) * 34)
                b = c + QPointF(math.cos(ang) * 52, math.sin(ang) * 52)
                lightning.draw(p, lightning.bolt(a, b, rng, roughness=0.35, depth=3, branch=0.2), 1 - k, 0.6)
        p.end()
