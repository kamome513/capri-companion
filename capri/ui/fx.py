"""Shared effects for her full-screen moments (the throw, the teleport): her figure as a cached sprite, glows,
sparks, debris, shockwave rings, dust - and dirty-rect tracking, so a frame only repaints the part of the
screen that changed (a full-screen see-through window repainted 60 times a second is what makes things stutter).

Every effect is time-based (it knows when it was born), so the look doesn't depend on the frame rate.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient

from .rig import Pose, Rig

RED = QColor(236, 16, 70)
CYAN = QColor(40, 230, 255)
GREEN = QColor(60, 255, 150)
WHITE = QColor(255, 244, 248)
GRAVITY = 1700.0


def precise_timer(parent, ms: int = 8) -> QTimer:
    """A frame timer that really ticks on time (Windows' normal timers step in ~15.6 ms jumps: judder)."""
    timer = QTimer(parent)
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(ms)
    return timer


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t


def spring(t: float, wobble: float = 2.2) -> float:
    """0 -> 1, overshooting a little and settling (for squash-and-stretch and getting up)."""
    t = max(0.0, min(1.0, t))
    return 1 - math.exp(-6.5 * t) * math.cos(wobble * math.pi * t)


# -- her as a sprite -------------------------------------------------------------------------------------------
def render(rig: Rig, height: float, pose: Pose, scale: float = 1.0, tint: QColor | None = None,
           hair: bool = True) -> QImage:
    """Her drawn into her own image (feet at the bottom middle), optionally as a flat-coloured silhouette."""
    w, h = int(height * 1.5 * scale) + 4, int(height * 1.25 * scale) + 4
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(scale, scale)
    rig.paint(p, QPointF(w / scale / 2, height * 1.12), height, pose, "right", hair=hair)
    p.end()
    if tint is not None:
        q = QPainter(img)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        q.fillRect(img.rect(), tint)
        q.end()
    return img


def anchor(height: float, scale: float = 1.0) -> QPointF:
    """Where her middle is in a render() image."""
    w = int(height * 1.5 * scale) + 4
    return QPointF(w / 2, (height * 1.12 - height / 2) * scale)


def blurred(img: QImage, amount: int = 10) -> QImage:
    """A soft glow version of an image (shrink and grow back smoothly - cheap and good enough)."""
    small = img.scaled(max(1, img.width() // amount), max(1, img.height() // amount),
                       Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return small.scaled(img.width(), img.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


# -- particles ------------------------------------------------------------------------------------------------------
@dataclass
class Particle:
    pos: QPointF
    vel: QPointF
    born: float
    life: float
    colour: QColor
    size: float = 2.5
    kind: str = "spark"              # spark (a streak) | dot | shard (a spinning triangle) | mote (drifts, no gravity)
    spin: float = 0.0
    angle: float = 0.0
    gravity: float = 0.6
    shape: list = field(default_factory=list)

    def at(self, now: float) -> QPointF:
        dt = now - self.born
        return self.pos + self.vel * dt + QPointF(0, 0.5 * GRAVITY * self.gravity * dt * dt)

    def velocity(self, now: float) -> QPointF:
        return self.vel + QPointF(0, GRAVITY * self.gravity * (now - self.born))


@dataclass
class Ring:
    at: QPointF
    born: float
    life: float
    radius: float
    colour: QColor
    flat: float = 1.0                # < 1: squashed along the floor; > 1: along a wall
    width: float = 4.0


@dataclass
class Crack:
    at: QPointF
    lines: list
    born: float
    life: float = 2.4


class Effects:
    """All the bits flying about, and the part of the screen they cover."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.particles: list[Particle] = []
        self.rings: list[Ring] = []
        self.cracks: list[Crack] = []
        self.flashes: list[tuple[float, QPointF, float, float]] = []   # (born, at, radius, life)

    def clear(self) -> None:
        self.particles, self.rings, self.cracks, self.flashes = [], [], [], []

    # -- making them -------------------------------------------------------------------------------------------
    def sparks(self, at: QPointF, direction: float, spread: float, count: int, speed: tuple[float, float],
               now: float, colours=(RED, RED, WHITE, CYAN), life=(0.25, 0.6), size=(1.8, 3.2), kind="spark",
               gravity: float = 0.6) -> None:
        r = self.rng
        for _ in range(count):
            a = direction + r.uniform(-spread, spread)
            v = r.uniform(*speed)
            self.particles.append(Particle(QPointF(at), QPointF(math.cos(a) * v, math.sin(a) * v), now,
                                           r.uniform(*life), QColor(r.choice(colours)), r.uniform(*size), kind,
                                           gravity=gravity))

    def shards(self, at: QPointF, direction: float, count: int, now: float, scale: float) -> None:
        """Bits of the "wall" breaking off: little spinning glassy triangles that fall."""
        r = self.rng
        for _ in range(count):
            a = direction + r.uniform(-1.1, 1.1)
            v = r.uniform(180, 650)
            s = scale * r.uniform(0.02, 0.05)
            shape = [QPointF(r.uniform(-s, s), r.uniform(-s, s)) for _ in range(3)]
            colour = r.choice((QColor(30, 22, 40), QColor(60, 40, 70), QColor(CYAN), QColor(RED)))
            self.particles.append(Particle(QPointF(at), QPointF(math.cos(a) * v, math.sin(a) * v - 120), now,
                                           r.uniform(0.7, 1.3), colour, s, "shard", r.uniform(-900, 900),
                                           r.uniform(0, 360), 1.0, shape))

    def motes(self, around: QPointF, radius: float, count: int, now: float, inward: bool, colours=(CYAN, WHITE, RED),
              life=(0.3, 0.6)) -> None:
        """Glowing specks gathering in (inward) or flying off (outward) - for the teleport."""
        r = self.rng
        for _ in range(count):
            a = r.uniform(0, math.tau)
            d = r.uniform(0.4, 1.0) * radius
            start = around + QPointF(math.cos(a) * d, math.sin(a) * d * 1.6)
            lf = r.uniform(*life)
            vel = (around - start) / lf if inward else QPointF(math.cos(a), math.sin(a) * 1.6) * r.uniform(60, 240)
            self.particles.append(Particle(start if inward else QPointF(around + (start - around) * 0.25), vel, now,
                                           lf, QColor(r.choice(colours)), r.uniform(1.5, 3.2), "mote", gravity=0.0))

    def ring(self, at: QPointF, now: float, radius: float, colour: QColor = CYAN, life: float = 0.45,
             flat: float = 1.0, width: float = 4.0) -> None:
        self.rings.append(Ring(QPointF(at), now, life, radius, QColor(colour), flat, width))

    def flash(self, at: QPointF, now: float, radius: float, life: float = 0.2) -> None:
        self.flashes.append((now, QPointF(at), radius, life))

    def crack(self, at: QPointF, normal: QPointF, now: float, size: float) -> None:
        """A spidery crack where she hit, spreading away from the wall into the screen."""
        r = self.rng
        lines, out = [], math.atan2(normal.y(), normal.x())
        for _ in range(r.randint(8, 11)):
            a = out + r.uniform(-1.5, 1.5)
            length = size * r.uniform(0.35, 1.0)
            pts, pt = [QPointF(at)], QPointF(at)
            steps = r.randint(3, 5)
            for _ in range(steps):
                a += r.uniform(-0.45, 0.45)
                pt = pt + QPointF(math.cos(a), math.sin(a)) * (length / steps)
                pts.append(QPointF(pt))
            lines.append(pts)
        ring = [at + QPointF(math.cos(k / 8 * math.tau), math.sin(k / 8 * math.tau)) * size * 0.2 * r.uniform(0.7, 1.3)
                for k in range(9)]
        lines.append(ring)
        self.cracks.append(Crack(QPointF(at), lines, now))

    def dust(self, at: QPointF, now: float, size: float, count: int = 6) -> None:
        r = self.rng
        for i in range(count):
            side = -1 if i % 2 else 1
            self.particles.append(Particle(at + QPointF(r.uniform(-0.3, 0.3) * size, 0),
                                           QPointF(side * r.uniform(40, 160), -r.uniform(10, 60)), now,
                                           r.uniform(0.45, 0.8), QColor(205, 195, 210), size * r.uniform(0.06, 0.11),
                                           "dust", gravity=-0.02))

    # -- keeping tidy ----------------------------------------------------------------------------------------------
    def prune(self, now: float) -> None:
        self.particles = [p for p in self.particles if now - p.born < p.life]
        self.rings = [g for g in self.rings if now - g.born < g.life]
        self.cracks = [c for c in self.cracks if now - c.born < c.life]
        self.flashes = [f for f in self.flashes if now - f[0] < f[3]]

    def busy(self, now: float) -> bool:
        self.prune(now)
        return bool(self.particles or self.rings or self.cracks or self.flashes)

    def bounds(self, now: float) -> QRectF:
        """Where they all are right now (to repaint just that)."""
        box = QRectF()
        for p in self.particles:
            pt = p.at(now)
            box = box.united(QRectF(pt.x() - 30, pt.y() - 30, 60, 60))
        for g in self.rings:
            r = g.radius * 1.2 + g.width * 3
            box = box.united(QRectF(g.at.x() - r, g.at.y() - r, 2 * r, 2 * r))
        for c in self.cracks:
            for line in c.lines:
                for pt in line:
                    box = box.united(QRectF(pt.x() - 8, pt.y() - 8, 16, 16))
        for _t, at, radius, _l in self.flashes:
            box = box.united(QRectF(at.x() - radius, at.y() - radius, 2 * radius, 2 * radius))
        return box

    # -- drawing -----------------------------------------------------------------------------------------------------
    def paint_under(self, p: QPainter, now: float) -> None:
        """Behind her: cracks, dust, rings."""
        for c in self.cracks:
            age = now - c.born
            if not 0 <= age < c.life:
                continue
            fade = 1.0 if age < c.life - 0.7 else max(0.0, (c.life - age) / 0.7)
            grow = min(1.0, age / 0.09)
            for width, colour in ((7.0, QColor(255, 40, 90, int(50 * fade))), (4.5, QColor(8, 4, 10, int(210 * fade))),
                                  (1.5, QColor(255, 150, 170, int(230 * fade)))):
                p.setPen(QPen(colour, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                for line in c.lines:
                    shown = max(2, int(len(line) * grow + 0.999))
                    path = QPainterPath(line[0])
                    for pt in line[1:shown]:
                        path.lineTo(pt)
                    p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.particles:
            if pt.kind != "dust":
                continue
            age = (now - pt.born) / pt.life
            if not 0 <= age < 1:
                continue                                   # (finished: never drawn past its life)
            r = pt.size * (1 + 1.6 * age)
            p.setBrush(QColor(pt.colour.red(), pt.colour.green(), pt.colour.blue(), int(120 * (1 - age) ** 1.5)))
            p.drawEllipse(pt.at(now), r, r * 0.65)
        for g in self.rings:
            age = (now - g.born) / g.life
            if not 0 <= age < 1:
                continue
            r = g.radius * (0.25 + 0.75 * ease_out(age))
            c = QColor(g.colour)
            for width, alpha in ((g.width * 3, 60), (g.width, 230)):
                c.setAlpha(int(alpha * (1 - age) ** 1.4))
                p.setPen(QPen(c, max(0.5, width * (1 - age * 0.6))))
                p.setBrush(Qt.BrushStyle.NoBrush)
                rx, ry = (r, r * g.flat) if g.flat <= 1 else (r / g.flat, r)    # floor: flat; wall: tall
                p.drawEllipse(g.at, rx, ry)

    def paint_over(self, p: QPainter, now: float) -> None:
        """In front of her: sparks, shards, motes, flashes."""
        p.setBrush(Qt.BrushStyle.NoBrush)
        for pt in self.particles:
            if pt.kind == "dust":
                continue
            age = (now - pt.born) / pt.life
            if not 0 <= age < 1:
                continue
            pos = pt.at(now)
            c = QColor(pt.colour)
            if pt.kind == "spark":
                c.setAlphaF(max(0.0, 1 - age))
                tail = pos - pt.velocity(now) * 0.022
                p.setPen(QPen(c, pt.size * (1 - age) + 0.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(tail, pos)
            elif pt.kind == "shard":
                c.setAlphaF(max(0.0, min(1.0, (1 - age) * 1.4)))
                p.save()
                p.translate(pos)
                p.rotate(pt.angle + pt.spin * (now - pt.born))
                p.setPen(QPen(QColor(CYAN.red(), CYAN.green(), CYAN.blue(), int(200 * (1 - age))), 1.2))
                p.setBrush(c)
                p.drawPolygon(QPolygonF(pt.shape))
                p.restore()
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:                                                         # mote / dot: a soft glowing speck
                fade = math.sin(math.pi * min(1.0, age)) if pt.kind == "mote" else 1 - age
                g = QRadialGradient(pos, pt.size * 3)
                g.setColorAt(0, QColor(255, 255, 255, int(255 * fade)))
                g.setColorAt(0.3, QColor(c.red(), c.green(), c.blue(), int(220 * fade)))
                g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(pos, pt.size * 3, pt.size * 3)
                p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(Qt.PenStyle.NoPen)
        for born, at, radius, life in self.flashes:
            age = (now - born) / life
            if not 0 <= age < 1:
                continue
            r = radius * (0.6 + 0.5 * age)
            g = QRadialGradient(at, r)
            g.setColorAt(0, QColor(255, 255, 255, int(240 * (1 - age))))
            g.setColorAt(0.35, QColor(RED.red(), RED.green(), RED.blue(), int(150 * (1 - age))))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(g)
            p.drawEllipse(at, r, r)


class DirtyTracker:
    """Repaint only what changed: the union of where things are now and where they were last frame."""

    def __init__(self) -> None:
        self.last = QRectF()

    def frame(self, now_rect: QRectF) -> QRectF:
        area = now_rect.united(self.last) if not self.last.isNull() else now_rect
        self.last = now_rect
        return area.adjusted(-6, -6, 6, 6)


def now() -> float:
    return time.monotonic()
