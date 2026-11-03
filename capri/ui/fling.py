"""Throwing her: drag her and let go quickly and she flies, spinning, with gravity.

What happens when she lands depends on what she hits, and how hard:
* she hits a side wall or the top of the screen hard: SLAM. She flattens against it, glitches and shakes,
  the "wall" cracks, sparks fly, and she sees stars. Then she peels off and slides down (side wall) or
  drops (ceiling). At the bottom she crumples, lies there dazed a moment, and gets back up.
* she hits the bottom of the screen hard: a faceplant, then dazed, then up again.
* she hits it softly: a little bounce, and she lands on her feet.

All of it is drawn on one see-through, click-through window over her screen, with the same full-body
figure as her dash (rig.py). She's back in her own window where she landed once she's up.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient

from .overlay_window import OverlayWindow
from .rig import Pose, Rig

if TYPE_CHECKING:
    from .companion import Companion

log = logging.getLogger("capri")
THROW_SPEED = 1300.0      # px/s at release: faster than this is a throw, slower is just putting her down
GRAVITY = 1700.0          # px/s²
LIFT = 0.3                # a sideways throw always arcs up a little (she's tossed, not slid)
DRAG = 0.6                # air drag per second (velocity *= 1 - DRAG*dt)
SLAM_SPEED = 850.0        # hitting something faster than this is a slam
MAX_SPEED = 6000.0
SPIN = 0.55               # degrees of spin per px/s of sideways speed, per second
SLAM_TIME = 0.5           # stuck flat against the wall
CRUMPLE_TIME = 0.35
DAZED_TIME = 1.1
GETUP_TIME = 0.55
LAND_TIME = 0.3
CRACK_LIFE = 2.2          # the crack on the "wall" fades after this
WIDTH = 0.15              # her half-thickness, as a share of her height
RED = QColor(236, 16, 70)
CYAN = QColor(40, 230, 255)
GREEN = QColor(60, 255, 150)
OUCH = ["Ow! Rude.", "Hey! I'm fragile hardware!", "Okay. Ow.", "Did you just throw me?!",
        "That's a firmware crack, choom.", "Seeing stars here...", "Again and I bite.", "Nice arm. Ow."]
WHEE = ["Whoa!", "Hey!", "Wheee!", "Careful!"]


def speed_of(samples: list[tuple[float, QPointF]], window: float = 0.08) -> QPointF:
    """Your drag's speed (px/s) over its last `window` seconds."""
    if len(samples) < 2:
        return QPointF()
    t_end, p_end = samples[-1]
    first = samples[0]
    for t, p in reversed(samples[:-1]):
        first = (t, p)
        if t_end - t >= window:
            break
    dt = t_end - first[0]
    if dt <= 1e-3:
        return QPointF()
    return (p_end - first[1]) / dt


def extents(height: float, angle: float) -> tuple[float, float]:
    """Half her width / height on screen when turned by `angle` degrees."""
    a = math.radians(angle)
    half_h, half_w = height / 2, height * WIDTH
    return (abs(math.sin(a)) * half_h + abs(math.cos(a)) * half_w,
            abs(math.cos(a)) * half_h + abs(math.sin(a)) * half_w)


def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def _overshoot(t: float) -> float:
    """0 -> 1 with a little spring past the end."""
    t = max(0.0, min(1.0, t))
    return 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2


@dataclass
class Spark:
    pos: QPointF
    vel: QPointF
    born: float
    life: float
    colour: QColor


@dataclass
class Crack:
    at: QPointF
    lines: list[list[QPointF]]
    born: float


@dataclass
class Body:
    """Where she is (the middle of her), how she's turned, and how she's squashed."""
    centre: QPointF = field(default_factory=QPointF)
    vel: QPointF = field(default_factory=QPointF)
    angle: float = 0.0                 # degrees, clockwise; 0 = standing, +-90 = lying
    spin: float = 0.0                  # degrees per second
    squash: tuple[float, float] = (1.0, 1.0)   # her own width / height scale
    shake: QPointF = field(default_factory=QPointF)


class FlingFX(OverlayWindow):
    """Paints the throw: her, her afterimages, sparks, the crack, stars, dust."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.rig: Rig | None = None
        self.fh = 250.0
        self.body = Body()
        self.pose = Pose()
        self.ghosts: list[tuple[float, QPointF, float]] = []      # (time, centre, angle)
        self.sparks: list[Spark] = []
        self.cracks: list[Crack] = []
        self.dust: list[tuple[float, QPointF]] = []
        self.flash: tuple[float, QPointF] | None = None
        self.glitch = 0.0                  # 0..1: how much she's RGB-split right now
        self.stars = 0.0                   # 0..1: stars round her head
        self.visible_body = True
        self._rng = random.Random()

    # -- effects --------------------------------------------------------------------------------------------
    def burst(self, at: QPointF, normal: QPointF, now: float, strength: float) -> None:
        """Sparks fly off the wall at `at`, mostly along `normal` (away from the wall)."""
        n = int(14 + 18 * strength)
        base = math.atan2(normal.y(), normal.x())
        for _ in range(n):
            a = base + self._rng.uniform(-1.25, 1.25)
            v = self._rng.uniform(250, 900) * (0.6 + 0.6 * strength)
            colour = self._rng.choice((RED, RED, QColor(255, 240, 230), CYAN, GREEN))
            self.sparks.append(Spark(QPointF(at), QPointF(math.cos(a) * v, math.sin(a) * v), now,
                                     self._rng.uniform(0.25, 0.6), colour))
        self.flash = (now, QPointF(at))

    def crack(self, at: QPointF, normal: QPointF, now: float, size: float) -> None:
        """A spidery crack where she hit, spreading along the wall (across `normal`)."""
        lines = []
        out = math.atan2(normal.y(), normal.x())             # away from the wall, into the screen
        for i in range(self._rng.randint(7, 10)):
            a = out + self._rng.uniform(-1.45, 1.45)
            length = size * self._rng.uniform(0.35, 1.0)
            pts, p = [QPointF(at)], QPointF(at)
            steps = self._rng.randint(3, 5)
            for _ in range(steps):
                a += self._rng.uniform(-0.5, 0.5)
                p = p + QPointF(math.cos(a), math.sin(a)) * (length / steps)
                pts.append(QPointF(p))
            lines.append(pts)
        ring = [at + QPointF(math.cos(k / 8 * math.tau), math.sin(k / 8 * math.tau)) * size * 0.18 *
                self._rng.uniform(0.7, 1.3) for k in range(9)]
        lines.append(ring)
        self.cracks.append(Crack(QPointF(at), lines, now))

    def puff(self, at: QPointF, now: float) -> None:
        for dx in (-1, -0.4, 0.3, 1):
            self.dust.append((now, at + QPointF(dx * self.fh * 0.2, 0)))

    # -- painting -----------------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        if self.rig is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(-QPointF(self.geometry().topLeft()))      # paint in screen coordinates
        now = time.monotonic()
        self._paint_cracks(p, now)
        self._paint_dust(p, now)
        for t, centre, angle in self.ghosts:                   # red afterimages while she flies
            age = (now - t) / 0.3
            if age < 1:
                self._paint_her(p, centre, angle, (1.0, 1.0), opacity=0.35 * (1 - age), tint=RED)
        if self.visible_body:
            b = self.body
            centre = b.centre + b.shake
            if self.glitch > 0.02:                               # RGB split: she glitches on impact
                off = self.fh * 0.035 * self.glitch
                self._paint_her(p, centre + QPointF(-off, 0), b.angle, b.squash, 0.7 * self.glitch, RED)
                self._paint_her(p, centre + QPointF(off, off * 0.3), b.angle, b.squash, 0.7 * self.glitch, CYAN)
            self._paint_her(p, centre, b.angle, b.squash)
            if self.glitch > 0.3:                                # torn slices across her
                self._paint_slices(p, centre)
            if self.stars > 0:
                self._paint_stars(p, now)
        self._paint_sparks(p, now)
        if self.flash is not None:
            t, at = self.flash
            age = (now - t) / 0.22
            if age < 1:
                r = self.fh * (0.25 + 0.5 * age)
                g = QRadialGradient(at, r)
                g.setColorAt(0, QColor(255, 255, 255, int(230 * (1 - age))))
                g.setColorAt(0.35, QColor(RED.red(), RED.green(), RED.blue(), int(160 * (1 - age))))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(at, r, r)
        p.end()

    def _her_transform(self, p: QPainter, centre: QPointF, angle: float, squash: tuple[float, float]) -> None:
        p.translate(centre)
        p.rotate(angle)
        p.scale(*squash)

    def _paint_her(self, p: QPainter, centre: QPointF, angle: float, squash: tuple[float, float],
                   opacity: float = 1.0, tint: QColor | None = None) -> None:
        if tint is None:
            p.save()
            p.setOpacity(opacity)
            self._her_transform(p, centre, angle, squash)
            self.rig.paint(p, QPointF(0, self.fh / 2), self.fh, self.pose, "right")
            p.restore()
            return
        size = int(self.fh * 1.5)                               # a tinted copy of her, drawn off-screen first
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._her_transform(q, QPointF(size / 2, size / 2), angle, squash)
        self.rig.paint(q, QPointF(0, self.fh / 2), self.fh, self.pose, "right", hair=False)
        q.resetTransform()
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        q.fillRect(img.rect(), tint)
        q.end()
        p.save()
        p.setOpacity(opacity)
        p.drawImage(centre - QPointF(size / 2, size / 2), img)
        p.restore()

    def _paint_slices(self, p: QPainter, centre: QPointF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(3):
            y = centre.y() + self._rng.uniform(-0.45, 0.45) * self.fh
            w = self.fh * self._rng.uniform(0.25, 0.6)
            x = centre.x() - w / 2 + self._rng.uniform(-0.15, 0.15) * self.fh
            colour = self._rng.choice((RED, CYAN, GREEN))
            p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), int(150 * self.glitch)))
            p.drawRect(QRectF(x, y, w, self._rng.uniform(2, 6)))

    def _paint_stars(self, p: QPainter, now: float) -> None:
        """Three little stars circling her head."""
        b = self.body
        a = math.radians(b.angle)
        head = b.centre + QPointF(math.sin(a) * self.fh * 0.42, -math.cos(a) * self.fh * 0.42)
        rx, ry = self.fh * 0.17, self.fh * 0.05
        for i in range(3):
            t = now * 4.2 + i * math.tau / 3
            pos = head + QPointF(math.cos(t) * rx, math.sin(t) * ry - self.fh * 0.06)
            r = self.fh * 0.03 * (0.8 + 0.3 * math.sin(t))
            colour = (QColor(255, 230, 80), GREEN, CYAN)[i]
            colour.setAlphaF(min(1.0, self.stars))
            path = QPainterPath()
            for k in range(8):
                rr = r if k % 2 == 0 else r * 0.38
                ang = k * math.pi / 4 + t
                pt = pos + QPointF(math.cos(ang) * rr, math.sin(ang) * rr)
                path.moveTo(pt) if k == 0 else path.lineTo(pt)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawPath(path)

    def _paint_sparks(self, p: QPainter, now: float) -> None:
        for s in self.sparks:
            age = (now - s.born) / s.life
            if not 0 <= age < 1:
                continue
            dt = now - s.born
            pos = s.pos + s.vel * dt + QPointF(0, 0.5 * GRAVITY * 0.6 * dt * dt)
            tail = pos - s.vel * 0.025
            c = QColor(s.colour)
            c.setAlphaF(1 - age)
            p.setPen(QPen(c, 2.6 * (1 - age) + 0.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(tail, pos)

    def _paint_cracks(self, p: QPainter, now: float) -> None:
        for c in self.cracks:
            age = now - c.born
            if age > CRACK_LIFE:
                continue
            fade = 1.0 if age < CRACK_LIFE - 0.7 else (CRACK_LIFE - age) / 0.7
            grow = min(1.0, age / 0.12)
            for width, colour in ((5.0, QColor(10, 6, 12, int(200 * fade))), (1.6, QColor(255, 120, 140, int(220 * fade)))):
                p.setPen(QPen(colour, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                for line in c.lines:
                    shown = max(2, int(len(line) * grow + 0.999))
                    path = QPainterPath(line[0])
                    for pt in line[1:shown]:
                        path.lineTo(pt)
                    p.drawPath(path)

    def _paint_dust(self, p: QPainter, now: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for t, at in self.dust:
            age = (now - t) / 0.6
            if 0 <= age < 1:
                r = self.fh * (0.05 + 0.12 * age)
                p.setBrush(QColor(200, 190, 200, int(110 * (1 - age))))
                p.drawEllipse(at + QPointF(0, -r * 0.6 - age * 10), r, r * 0.7)

    def busy(self, now: float) -> bool:
        """Anything still fading out?"""
        return any(now - c.born < CRACK_LIFE for c in self.cracks) or \
            any(now - s.born < s.life for s in self.sparks) or any(now - t < 0.6 for t, _ in self.dust)


class ThrowShow(QObject):
    """Runs a throw: physics, then slam / slide / crumple / dazed / get up - then she's home where she landed."""

    def __init__(self, companion: "Companion", rig: Callable[[], Rig | None], say: Callable[[str, str], None],
                 enabled: Callable[[], bool] = lambda: True) -> None:
        super().__init__()
        self.companion, self.rig, self.say, self.enabled = companion, rig, say, enabled
        self.fx = FlingFX()
        self.active = False
        self.state = ""
        self.area = QRect()
        self._rng = random.Random()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._last = 0.0
        self._state_at = 0.0
        self._wall = ""                     # which wall she slammed: "left" / "right" / "top" / "bottom"
        self._feet = QPointF()              # where she'll stand up
        self._lie = 90.0                    # the angle she lies at

    # -- starting -------------------------------------------------------------------------------------------
    def throw(self, velocity: QPointF) -> bool:
        """She was let go at `velocity` (px/s). True if this is a throw (she's flying now)."""
        c = self.companion
        speed = math.hypot(velocity.x(), velocity.y())
        log.info("throw: let go at %.0f px/s", speed)
        if self.active or speed < THROW_SPEED or not self.enabled() or c.drone or c.perched or c.hidden \
                or c.lounging() or c.busy_elsewhere:
            return False
        rig = self.rig()
        if rig is None:
            log.info("throw: no full-body figure for this look")
            return False
        if speed > MAX_SPEED:
            velocity = velocity * (MAX_SPEED / speed)
        if velocity.y() > -LIFT * abs(velocity.x()):
            velocity = QPointF(velocity.x(), -LIFT * abs(velocity.x()))
        body = c.content_geometry()
        fh = float(c.character.figure_height())
        fx = self.fx
        fx.rig, fx.fh = rig, fh
        fx.body = Body(QPointF(body.center().x(), body.bottom() - fh / 2), QPointF(velocity),
                       0.0, velocity.x() * SPIN)
        fx.pose = Pose(sweep=0.8, energy=1.0, eyes="", t=time.monotonic())
        fx.ghosts, fx.sparks, fx.cracks, fx.dust, fx.flash = [], [], [], [], None
        fx.glitch, fx.stars, fx.visible_body = 0.0, 0.0, True
        screen = c.screen
        self.area = screen.availableGeometry()
        fx.setGeometry(screen.geometry())
        fx.show()
        fx.raise_()
        c.busy_elsewhere = True
        c.character.hide()
        c.panel.hide()
        self.active = True
        self._set("fly")
        self._last = time.monotonic()
        self._timer.start()
        if self._rng.random() < 0.5:
            self.say(self._rng.choice(WHEE), "surprised")
        return True

    def _set(self, state: str) -> None:
        self.state, self._state_at = state, time.monotonic()

    # -- every frame ------------------------------------------------------------------------------------------
    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        fx = self.fx
        fx.pose.t = now * 2.2
        getattr(self, "_on_" + self.state)(dt, now - self._state_at, now)
        fx.glitch = max(0.0, fx.glitch - dt * 1.6)
        fx.ghosts = [g for g in fx.ghosts if now - g[0] < 0.3]
        fx.update()

    def _floor(self) -> float:
        return float(self.area.bottom() + 1)

    def _clamp_x(self, x: float, half: float) -> float:
        return max(self.area.left() + half, min(x, self.area.right() + 1 - half))

    def _pivot(self, feet: QPointF, angle: float) -> QPointF:
        """Her middle, when she's turned by `angle` about her feet (and not sunk into the floor)."""
        a = math.radians(angle)
        half = self.fx.fh / 2
        return feet + QPointF(half * math.sin(a), -half * math.cos(a) - self.fx.fh * WIDTH * abs(math.sin(a)))

    # flying -------------------------------------------------------------------------------------------------------
    def _on_fly(self, dt: float, k: float, now: float) -> None:
        fx, b, a = self.fx, self.fx.body, self.area
        b.vel = QPointF(b.vel.x() * (1 - DRAG * dt), b.vel.y() * (1 - DRAG * dt) + GRAVITY * dt)
        b.centre += b.vel * dt
        b.angle += b.spin * dt
        if not fx.ghosts or now - fx.ghosts[-1][0] > 0.035:
            fx.ghosts.append((now, QPointF(b.centre), b.angle))
        ex, ey = extents(fx.fh, b.angle)
        if b.centre.x() - ex < a.left() and b.vel.x() < 0:
            self._hit("left", now)
        elif b.centre.x() + ex > a.right() + 1 and b.vel.x() > 0:
            self._hit("right", now)
        elif b.centre.y() - ey < a.top() and b.vel.y() < 0:
            self._hit("top", now)
        elif b.centre.y() + ey > a.bottom() + 1 and b.vel.y() > 0:
            self._hit("bottom", now)
        elif k > 6:                                                    # never fly forever
            self._hit("bottom", now)

    def _hit(self, wall: str, now: float) -> None:
        fx, b, a = self.fx, self.fx.body, self.area
        normal_speed = abs(b.vel.x()) if wall in ("left", "right") else abs(b.vel.y())
        if normal_speed >= SLAM_SPEED:
            return self._start_slam(wall, now, min(1.0, normal_speed / 3000))
        ex, ey = extents(fx.fh, b.angle)
        b.spin *= 0.6
        if wall == "left":
            b.centre.setX(a.left() + ex)
            b.vel = QPointF(-b.vel.x() * 0.35, b.vel.y() * 0.7)
        elif wall == "right":
            b.centre.setX(a.right() + 1 - ex)
            b.vel = QPointF(-b.vel.x() * 0.35, b.vel.y() * 0.7)
        elif wall == "top":
            b.centre.setY(a.top() + ey)
            b.vel = QPointF(b.vel.x() * 0.7, -b.vel.y() * 0.3)
        else:                                                          # a soft landing
            angle = ((b.angle + 180) % 360) - 180
            if abs(angle) < 50:                                        # on her feet
                self._feet = QPointF(self._clamp_x(b.centre.x(), fx.fh * WIDTH), self._floor())
                self._from = angle
                fx.puff(self._feet, now)
                return self._set("land")
            self._lie = 90.0 if angle > 0 else -90.0                   # on her side: dazed a moment
            b.angle = self._lie
            b.centre = QPointF(self._clamp_x(b.centre.x(), fx.fh / 2), self._floor() - fx.fh * WIDTH)
            self._feet = self._feet_of(b.centre, b.angle)
            fx.puff(self._feet, now)
            fx.stars = 0.8
            self._dazed_start(now)

    def _feet_of(self, centre: QPointF, angle: float) -> QPointF:
        a = math.radians(angle)
        return QPointF(centre.x() - self.fx.fh / 2 * math.sin(a), self._floor())

    # the slam -----------------------------------------------------------------------------------------------------
    def _start_slam(self, wall: str, now: float, strength: float) -> None:
        fx, b, a = self.fx, self.fx.body, self.area
        self._wall = wall
        half = fx.fh * WIDTH
        if wall in ("left", "right"):
            b.angle = 0.0                                              # flat against the wall, upright
            x = a.left() + half * 0.55 if wall == "left" else a.right() + 1 - half * 0.55
            y = max(a.top() + fx.fh / 2, min(b.centre.y(), self._floor() - fx.fh / 2))
            b.centre = QPointF(x, y)
            at = QPointF(a.left() if wall == "left" else a.right() + 1, y - fx.fh * 0.1)
            normal = QPointF(1 if wall == "left" else -1, 0)
        else:
            moving = 1 if b.vel.x() >= 0 else -1
            b.angle = 90.0 * moving                                    # flat against the ceiling / floor
            y = a.top() + half * 0.55 if wall == "top" else self._floor() - half * 0.55
            x = self._clamp_x(b.centre.x(), fx.fh / 2)
            b.centre = QPointF(x, y)
            at = QPointF(x, a.top() if wall == "top" else self._floor())
            normal = QPointF(0, 1 if wall == "top" else -1)
        b.vel, b.spin = QPointF(), 0.0
        fx.burst(at, normal, now, strength)
        fx.crack(at, normal, now, fx.fh * (0.45 + 0.4 * strength))
        fx.glitch, fx.stars = 1.0, 1.0
        fx.pose = Pose(squat=0.6, blink=0.85, energy=1.0, t=now * 2.2)
        self.say(self._rng.choice(OUCH), "angry")
        self._said = True
        self._set("slam")

    def _on_slam(self, dt: float, k: float, now: float) -> None:
        fx, b = self.fx, self.fx.body
        flat = 0.5 + 0.5 * _ease_out(min(1.0, k / SLAM_TIME))           # flattened, springing back with a wobble
        wobble = math.sin(k * 38) * 0.08 * max(0.0, 1 - k / SLAM_TIME)
        thin, tall = flat + wobble, 1 + (1 - flat) * 0.45 - wobble * 0.5
        b.squash = (thin, tall) if self._wall in ("left", "right") else (tall, thin)
        half, area = fx.fh * WIDTH, self.area                           # squashed against it, not through it
        if self._wall == "left":
            b.centre.setX(area.left() + half * thin)
        elif self._wall == "right":
            b.centre.setX(area.right() + 1 - half * thin)
        elif self._wall == "top":
            b.centre.setY(area.top() + half * thin)
        else:
            b.centre.setY(self._floor() - half * thin)
        shake = fx.fh * 0.03 * max(0.0, 1 - k / SLAM_TIME)
        b.shake = QPointF(self._rng.uniform(-shake, shake), self._rng.uniform(-shake, shake))
        if k < SLAM_TIME:
            return
        b.squash, b.shake = (1.0, 1.0), QPointF()
        if self._wall in ("left", "right"):
            b.vel = QPointF()
            self._set("slide")
        elif self._wall == "top":
            b.vel = QPointF()
            self._set("fall")
        else:                                                          # faceplant on the floor
            self._lie = b.angle
            b.centre.setY(self._floor() - fx.fh * WIDTH)
            self._feet = self._feet_of(b.centre, b.angle)
            self._dazed_start(now)

    def _on_slide(self, dt: float, k: float, now: float) -> None:
        """Peeling off the wall and sliding down it."""
        fx, b = self.fx, self.fx.body
        away = 1 if self._wall == "left" else -1
        b.angle = away * 9 * min(1.0, k / 0.3)
        b.vel = QPointF(0, b.vel.y() + GRAVITY * 0.45 * dt)
        b.centre += b.vel * dt
        b.centre.setX(b.centre.x() + away * fx.fh * 0.04 * dt)
        fx.pose = Pose(squat=0.3, blink=0.6, sweep=0.3, energy=0.8, t=now * 2.2)
        if b.centre.y() + fx.fh / 2 >= self._floor():
            self._feet = QPointF(b.centre.x(), self._floor())
            self._from = b.angle
            self._lie = 90.0 * away                                    # she crumples away from the wall
            self._set("crumple")

    def _on_fall(self, dt: float, k: float, now: float) -> None:
        """Dropping off the ceiling, still flat."""
        fx, b = self.fx, self.fx.body
        b.vel = QPointF(0, b.vel.y() + GRAVITY * dt)
        b.centre += b.vel * dt
        if b.centre.y() + fx.fh * WIDTH >= self._floor():
            b.centre.setY(self._floor() - fx.fh * WIDTH)
            self._lie = b.angle
            self._feet = self._feet_of(b.centre, b.angle)
            fx.puff(QPointF(b.centre.x(), self._floor()), now)
            fx.glitch = 0.6
            self._dazed_start(now)

    def _crumple_to_floor(self, now: float) -> None:
        self._from = self.fx.body.angle
        self._set("crumple")

    def _on_crumple(self, dt: float, k: float, now: float) -> None:
        """Toppling over sideways from her feet."""
        fx, b = self.fx, self.fx.body
        t = min(1.0, k / CRUMPLE_TIME)
        b.angle = self._from + (self._lie - self._from) * t * t        # falling over speeds up
        b.centre = self._pivot(self._feet, b.angle)
        if t >= 1:
            fx.puff(QPointF(b.centre.x(), self._floor()), now)
            fx.glitch = 0.5
            self._dazed_start(now)

    def _dazed_start(self, now: float) -> None:
        fx = self.fx
        fx.stars = max(fx.stars, 0.9)
        if not getattr(self, "_said", False):
            self.say(self._rng.choice(OUCH), "angry")
            self._said = True
        self._set("dazed")

    def _on_dazed(self, dt: float, k: float, now: float) -> None:
        fx, b = self.fx, self.fx.body
        bounce = math.exp(-k * 9) * math.sin(k * 30)                   # a little bounce when she lands
        b.squash = (1 - 0.12 * bounce, 1 + 0.06 * bounce)
        twitch = math.sin(k * 3) * 1.5
        b.angle = self._lie + twitch * (1 if self._lie > 0 else -1)
        b.centre = QPointF(b.centre.x(), self._floor() - fx.fh * WIDTH)
        fx.pose = Pose(blink=0.75 + 0.25 * math.sin(k * 5), energy=0.4, t=now * 2.2)
        if k >= DAZED_TIME:
            b.squash = (1.0, 1.0)
            self._feet = QPointF(self._clamp_x(self._feet_of(b.centre, self._lie).x(), fx.fh * WIDTH), self._floor())
            self._from = self._lie
            self._set("getup")

    def _on_getup(self, dt: float, k: float, now: float) -> None:
        fx, b = self.fx, self.fx.body
        t = min(1.0, k / GETUP_TIME)
        b.angle = self._from * (1 - _overshoot(t))
        b.centre = self._pivot(self._feet, b.angle)
        fx.stars = max(0.0, 1 - t * 1.3)
        fx.pose = Pose(squat=0.5 * math.sin(math.pi * t), energy=0.6, t=now * 2.2)
        if t >= 1:
            self._home()

    def _on_land(self, dt: float, k: float, now: float) -> None:
        fx, b = self.fx, self.fx.body
        t = min(1.0, k / LAND_TIME)
        b.angle = self._from * (1 - _ease_out(t))
        b.centre = self._pivot(self._feet, b.angle)
        fx.pose = Pose(squat=0.6 * math.sin(math.pi * t), energy=0.7, t=now * 2.2)
        if t >= 1:
            self._home()

    # back in her window ------------------------------------------------------------------------------------------------
    def _home(self) -> None:
        c, fx = self.companion, self.fx
        fx.visible_body, fx.stars = False, 0.0
        content = c.character.content_rect()
        feet = self._feet
        target = QPoint(round(feet.x() - (content.x() + content.width() / 2)),
                        round(feet.y() - (content.y() + content.height())))
        c._move_character(target, c.screen)
        c._remember_position()
        c.busy_elsewhere = False
        c.show()
        QTimer.singleShot(60, lambda: None if c.busy_elsewhere or c.perched else c.place())   # some window
        # managers put a window back where *they* like when it's shown again: where she landed, please
        self._said = False
        self._set("fade")

    def _on_fade(self, dt: float, k: float, now: float) -> None:
        if self.fx.busy(now) and k < CRACK_LIFE + 0.5:
            return
        self._timer.stop()
        self.fx.hide()
        self.fx.rig = None
        self.active = False
