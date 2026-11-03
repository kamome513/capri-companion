"""Her glitches, made to look like the real thing - a broken video feed, not a filter.

RealGlitch: every few minutes (Settings: "Glitch now and then", 3 minutes by default, or never) her picture
breaks up for about half a second: it TEARS into horizontal bands that jump sideways (some doubled), the red and
cyan channels split apart, blocks of her get swapped with other parts of her (datamosh) or blanked, scan lines
roll over her, the frame FREEZES for a moment, then DROPS (she's gone for a couple of frames), then snaps back
with a jolt. Real glitches step at a camera's frame rate rather than smoothly, so the pattern changes every
1/30 s, while the window still repaints at full speed.

DragSway: while you drag her she dangles from your cursor - she swings behind the way you move (a damped
pendulum), her legs kick, her arms trail, her hair goes wild, and she flickers a little.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPen

RED = QColor(255, 30, 80)
CYAN = QColor(30, 235, 255)
GLITCH_FPS = 30                    # a broken feed changes at camera speed, not at 120 Hz


@dataclass
class Segment:
    start: float
    end: float
    kind: str                       # tear | freeze | drop | shift | light


def plan(rng: random.Random) -> list[Segment]:
    """One glitch burst's timeline (~0.45-0.8 s)."""
    kinds = rng.choice([
        ["tear", "freeze", "drop", "tear", "shift", "light"],
        ["light", "tear", "drop", "tear", "freeze", "light"],
        ["tear", "shift", "drop", "freeze", "tear", "light"],
        ["shift", "tear", "freeze", "drop", "light"],
    ])
    length = {"tear": (0.06, 0.12), "freeze": (0.07, 0.14), "drop": (0.03, 0.06), "shift": (0.06, 0.1),
              "light": (0.08, 0.14)}
    out, t = [], 0.0
    for k in kinds:
        d = rng.uniform(*length[k])
        out.append(Segment(t, t + d, k))
        t += d
    return out


def tinted(image: QImage, colour: QColor) -> QImage:
    out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.setDevicePixelRatio(image.devicePixelRatio())
    out.fill(0)
    q = QPainter(out)
    q.drawImage(0, 0, image)
    q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    q.fillRect(out.rect(), colour)
    q.end()
    return out


class RealGlitch:
    def __init__(self, every=lambda: 180, rng: random.Random | None = None, clock=time.monotonic) -> None:
        self.every, self.rng, self.clock = every, rng or random.Random(), clock
        self.segments: list[Segment] = []
        self.started = 0.0
        self.frozen: QImage | None = None
        self._next = clock() + self._gap()
        self._tints: tuple | None = None

    def _gap(self) -> float:
        every = float(self.every() or 0)
        return every * self.rng.uniform(0.7, 1.3) if every > 0 else 1e12

    # -- when ---------------------------------------------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self.segments) and self.clock() - self.started < self.segments[-1].end

    def due(self, allowed: bool) -> bool:
        """Time for one? (When it isn't allowed right now, it waits for the next moment it is.)"""
        now = self.clock()
        if self.active or not allowed or now < self._next:
            return False
        return float(self.every() or 0) > 0

    def start(self, light: bool = False) -> None:
        self.started = self.clock()
        self.segments = [Segment(0, 0.12, "light")] if light else plan(self.rng)
        self.frozen = None
        self._next = self.started + self._gap()

    def rescheduled(self) -> None:
        """The setting changed."""
        self._next = self.clock() + self._gap()

    def segment(self) -> Segment | None:
        t = self.clock() - self.started
        return next((s for s in self.segments if s.start <= t < s.end), None)

    # -- drawing --------------------------------------------------------------------------------------------------------
    def paint(self, p: QPainter, snap: QImage, body: QRectF, scale: float = 1.0) -> None:
        """Draw this frame of the glitch from `snap` (a window-sized picture of her, drawn at 0, 0)."""
        seg = self.segment()
        if seg is None:
            p.drawImage(QPointF(0, 0), snap)
            return
        frame = int((self.clock() - self.started) * GLITCH_FPS)
        r = random.Random(hash((round(self.started, 3), frame)))
        if seg.kind == "freeze":
            if self.frozen is None:
                self.frozen = snap.copy()
            snap = self.frozen                                     # the feed hangs on one frame
        if seg.kind == "drop":                                     # a dropped frame: she's not there
            self._scanlines(p, body, r, 0.5, scale)
            if r.random() < 0.5:
                p.setOpacity(0.12)
                p.drawImage(QPointF(r.uniform(-6, 6) * scale, 0), self._tint(snap, CYAN))
                p.setOpacity(1.0)
            return
        heavy = seg.kind in ("tear", "shift")
        jolt = QPointF(r.uniform(-1, 1) * (9 if seg.kind == "shift" else 4) * scale,
                       r.uniform(-1, 1) * (2 if heavy else 1) * scale)
        split = r.uniform(4, 12 if heavy else 6) * scale
        red, cyan = self._tint(snap, RED), self._tint(snap, CYAN)
        p.setOpacity(0.85)                                         # the colour channels pulled apart
        p.drawImage(jolt + QPointF(-split, r.uniform(-1, 1) * scale), red)
        p.drawImage(jolt + QPointF(split, r.uniform(-1, 1) * scale), cyan)
        p.setOpacity(1.0)
        if seg.kind == "light":
            p.drawImage(jolt, snap)
            self._bands(p, snap, body, r, 1, 2, 8 * scale, jolt)
        else:
            self._torn(p, snap, body, r, jolt, scale, seg.kind == "shift")
            self._blocks(p, snap, body, r, scale)
        self._scanlines(p, body, r, 1.0 if heavy else 0.6, scale)

    def _tint(self, snap: QImage, colour: QColor) -> QImage:
        key = (snap.cacheKey(), colour.rgba())
        if self._tints is None or self._tints[0] != key:
            self._tints = (key, tinted(snap, colour))
        return self._tints[1]

    def _torn(self, p: QPainter, snap: QImage, body: QRectF, r: random.Random, jolt: QPointF, scale: float,
              big: bool) -> None:
        """Her picture in horizontal bands, many of them jumped sideways - the signature of a broken feed."""
        dpr = snap.devicePixelRatio()
        w, h = snap.width() / dpr, snap.height() / dpr
        y = 0.0
        while y < h:
            band = r.uniform(2, 22 if big else 14) * scale
            shift = 0.0
            if body.top() - 40 * scale < y < body.bottom() and r.random() < (0.55 if big else 0.4):
                shift = r.choice((-1, 1)) * r.uniform(3, 34 if big else 18) * scale
            src = QRectF(0, y * dpr, snap.width(), band * dpr)
            p.drawImage(QRectF(jolt.x() + shift, jolt.y() + y, w, band), snap, src)
            if shift and r.random() < 0.2:                         # a doubled band
                p.setOpacity(0.5)
                p.drawImage(QRectF(jolt.x() - shift * 0.6, jolt.y() + y, w, band), snap, src)
                p.setOpacity(1.0)
            y += band

    def _bands(self, p: QPainter, snap: QImage, body: QRectF, r: random.Random, lo: int, hi: int, reach: float,
               jolt: QPointF) -> None:
        dpr = snap.devicePixelRatio()
        w = snap.width() / dpr
        for _ in range(r.randint(lo, hi)):
            y, band = r.uniform(body.top(), body.bottom()), r.uniform(3, 10)
            p.drawImage(QRectF(jolt.x() + r.choice((-1, 1)) * r.uniform(3, reach), y, w, band), snap,
                        QRectF(0, y * dpr, snap.width(), band * dpr))

    def _blocks(self, p: QPainter, snap: QImage, body: QRectF, r: random.Random, scale: float) -> None:
        """Datamosh: chunks of her copied from somewhere else on her, and a few dead blocks."""
        dpr = snap.devicePixelRatio()
        for _ in range(r.randint(2, 5)):
            bw, bh = r.uniform(12, body.width() * 0.6), r.uniform(4, 22) * scale
            x, y = r.uniform(body.left() - 10, body.right() - bw + 10), r.uniform(body.top(), body.bottom() - bh)
            if r.random() < 0.65:
                sx, sy = r.uniform(body.left(), body.right() - bw), r.uniform(body.top(), body.bottom() - bh)
                p.drawImage(QRectF(x, y, bw, bh), snap, QRectF(sx * dpr, sy * dpr, bw * dpr, bh * dpr))
            else:
                colour = QColor(r.choice((RED, CYAN, QColor(10, 6, 14), QColor(255, 255, 255))))
                colour.setAlpha(r.randint(120, 230))
                p.fillRect(QRectF(x, y, bw, bh * 0.5), colour)

    def _scanlines(self, p: QPainter, body: QRectF, r: random.Random, strength: float, scale: float) -> None:
        top, bottom = body.top() - 30 * scale, body.bottom()
        for colour in (RED, CYAN, QColor(255, 255, 255)):
            c = QColor(colour)
            c.setAlpha(int(180 * strength))
            p.setPen(QPen(c, max(1.0, scale)))
            yy = r.uniform(top, bottom)
            p.drawLine(QPointF(body.left() - 18 * scale, yy), QPointF(body.right() + 18 * scale, yy))
        dark = QColor(0, 0, 0, int(50 * strength))
        p.setPen(QPen(dark, 1))
        y = top + r.uniform(0, 3)
        while y < bottom:
            p.drawLine(QPointF(body.left() - 6, y), QPointF(body.right() + 6, y))
            y += 3 * scale


class DragSway:
    """She dangles from your cursor while you drag her: a damped pendulum driven by how you move."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.held = False
        self.angle = 0.0                 # -1..1 lean (Pose.lean units)
        self.speed = 0.0
        self._vx = 0.0
        self._last_x: float | None = None
        self._last_t = clock()
        self.since = 0.0

    def grab(self) -> None:
        self.held, self.since, self._last_x = True, self.clock(), None

    def drop(self) -> None:
        self.held = False

    def moved(self, x: float) -> None:
        now = self.clock()
        if self._last_x is not None:
            dt = max(1e-3, now - self._last_t)
            self._vx = 0.7 * self._vx + 0.3 * (x - self._last_x) / dt
        self._last_x, self._last_t = x, now

    def step(self, dt: float) -> None:
        """Advance the swing: she lags behind your movement and swings back, settling when you stop."""
        target = max(-0.55, min(0.55, -self._vx / 2600)) if self.held else 0.0
        self._vx *= math.exp(-dt * 6)                            # your movement fades once you stop moving
        k, damping = 38.0, 5.5
        acc = k * (target - self.angle) - damping * self.speed
        self.speed += acc * dt
        self.angle += self.speed * dt

    @property
    def swinging(self) -> bool:
        return self.held or abs(self.angle) > 0.004 or abs(self.speed) > 0.004

    def pose_moves(self, now: float) -> dict[str, float]:
        """The pose while she's held: leaning with the swing, arms trailing, legs kicking, hair wild."""
        t = now - self.since
        if not self.held:
            return {"lean": self.angle}
        kick = math.sin(t * 7.5) * 0.55 + math.sin(t * 3.1) * 0.25
        return {"lean": self.angle, "sweep": 0.55 + 0.25 * abs(math.sin(t * 2.3)), "stride": kick,
                "energy": 1.0, "squat": 0.0}
