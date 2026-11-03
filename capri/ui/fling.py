"""Throwing her: drag her and let go quickly and she flies - spinning, stretching with the speed, a red
afterimage trail behind her.

When she hits the edge of the screen:
* hard: a SLAM. A split-second freeze (hit-stop) with a white impact frame, she squashes flat against it,
  the "wall" cracks and bits of it break off, sparks and a shockwave ring fly out, she glitches (RGB split)
  and everything shakes. Then she BOUNCES off it, tumbling, and keeps bouncing (smaller each time) until she
  ends up lying on the floor seeing stars - and gets back up with a little spring.
* softly: she bounces off, or lands on her feet.

All of it is drawn on one see-through, click-through window over her screen, with the same full-body figure
as her dash (rig.py), repainting only the part of the screen that changes, on a precise 120 Hz timer.
She's back in her own window where she landed once she's up.
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

from . import fx
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
HIT_STOP = 0.07           # the freeze at the moment of impact
SLAM_TIME = 0.24          # squashed flat against the wall (after the freeze)
BOUNCE = 0.42             # how much speed a slam gives back (she bounces off)
FLOOR_BOUNCE = 0.38       # each floor bounce keeps this much
REST_SPEED = 260.0        # slower than this on the floor: she stops bouncing
TOPPLE_TIME = 0.3
DAZED_TIME = 1.0
GETUP_TIME = 0.6
LAND_TIME = 0.32
WIDTH = 0.15              # her half-thickness, as a share of her height
STEP = 1 / 240            # physics sub-step (no tunnelling through walls at high speed)
RED, CYAN, GREEN, WHITE = fx.RED, fx.CYAN, fx.GREEN, fx.WHITE
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


def nearest_lying(angle: float) -> float:
    """+90 or -90: whichever way she's closer to lying."""
    a = ((angle + 180) % 360) - 180
    return 90.0 if a >= 0 else -90.0


@dataclass
class Body:
    """Where she is (the middle of her), how she's turned, and how she's squashed."""
    centre: QPointF = field(default_factory=QPointF)
    vel: QPointF = field(default_factory=QPointF)
    angle: float = 0.0                 # degrees, clockwise; 0 = standing, +-90 = lying
    spin: float = 0.0                  # degrees per second
    squash: tuple[float, float] = (1.0, 1.0)   # her own width / height scale
    shake: QPointF = field(default_factory=QPointF)


@dataclass
class Ghost:
    born: float
    centre: QPointF
    angle: float
    image: QImage                      # her silhouette, rendered once (not every frame)


class FlingFX(OverlayWindow):
    """Paints the throw: her, her afterimages, the effects."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.rig: Rig | None = None
        self.fh = 250.0
        self.body = Body()
        self.pose = Pose()
        self.ghosts: list[Ghost] = []
        self.effects = fx.Effects()
        self.glitch = 0.0                  # 0..1: how much she's RGB-split right now
        self.stars = 0.0                   # 0..1: stars round her head
        self.impact = 0.0                  # 0..1: the white impact frame
        self.stretch = 0.0                 # squash-and-stretch along her flight
        self.shake = QPointF()             # the whole scene shakes after a slam
        self.visible_body = True
        self._tints: dict[str, QImage] = {}
        self._tint_key = None
        self._rng = random.Random()
        self.dirty = fx.DirtyTracker()

    # -- what to repaint -----------------------------------------------------------------------------------------
    def body_rect(self) -> QRectF:
        c, r = self.body.centre + self.body.shake + self.shake, self.fh * 0.95
        return QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def refresh(self, now: float) -> None:
        area = self.effects.bounds(now)
        if self.visible_body:
            area = area.united(self.body_rect())
        for g in self.ghosts:
            r = self.fh * 0.9
            area = area.united(QRectF(g.centre.x() - r, g.centre.y() - r, 2 * r, 2 * r))
        dirty = self.dirty.frame(area).translated(-QPointF(self.geometry().topLeft()))
        self.update(dirty.toAlignedRect())

    def tinted(self, colour: str) -> QImage:
        """Her silhouette in one colour, for this pose (cached; re-made only when the pose really changes)."""
        key = (round(self.pose.squat, 1), round(self.pose.sweep, 1), round(self.pose.blink, 1))
        if key != self._tint_key:
            self._tints, self._tint_key = {}, key
        if colour not in self._tints:
            tint = {"red": RED, "cyan": CYAN, "white": WHITE}[colour]
            self._tints[colour] = fx.render(self.rig, self.fh, self.pose, 0.5, tint, hair=False)
        return self._tints[colour]

    def ghost(self, now: float) -> None:
        self.ghosts.append(Ghost(now, QPointF(self.body.centre), self.body.angle, self.tinted("red")))
        del self.ghosts[:-10]

    # -- painting ------------------------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        if self.rig is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setClipRect(event.rect())
        p.translate(-QPointF(self.geometry().topLeft()) + self.shake)    # screen coordinates (+ the shake)
        now = time.monotonic()
        self.effects.paint_under(p, now)
        for g in self.ghosts:                                             # red afterimages
            age = (now - g.born) / 0.28
            if age < 1:
                self._sprite(p, g.image, g.centre, g.angle, (1.0, 1.0), 0.5, 0.42 * (1 - age) ** 1.5)
        if self.visible_body:
            b = self.body
            centre = b.centre + b.shake
            if self.glitch > 0.02:                                         # RGB split
                off = self.fh * 0.04 * self.glitch
                self._sprite(p, self.tinted("red"), centre + QPointF(-off, 0), b.angle, b.squash, 0.5,
                             0.75 * self.glitch)
                self._sprite(p, self.tinted("cyan"), centre + QPointF(off, off * 0.3), b.angle, b.squash, 0.5,
                             0.75 * self.glitch)
            self._paint_her(p, centre)
            if self.impact > 0.01:                                         # the white impact frame
                self._sprite(p, self.tinted("white"), centre, b.angle, b.squash, 0.5, min(1.0, self.impact))
            if self.glitch > 0.35:
                self._paint_slices(p, centre)
            if self.stars > 0:
                self._paint_stars(p, now)
        self.effects.paint_over(p, now)
        p.end()

    def _transform(self, p: QPainter, centre: QPointF, angle: float, squash: tuple[float, float]) -> None:
        p.translate(centre)
        if self.stretch > 0.01:                                           # stretched along her flight
            v = self.body.vel
            heading = math.degrees(math.atan2(v.y(), v.x()))
            p.rotate(heading)
            p.scale(1 + self.stretch, 1 - self.stretch * 0.45)
            p.rotate(-heading)
        p.rotate(angle)
        p.scale(*squash)

    def _paint_her(self, p: QPainter, centre: QPointF) -> None:
        b = self.body
        p.save()
        self._transform(p, centre, b.angle, b.squash)
        self.rig.paint(p, QPointF(0, self.fh / 2), self.fh, self.pose, "right")
        p.restore()

    def _sprite(self, p: QPainter, img: QImage, centre: QPointF, angle: float, squash: tuple[float, float],
                scale: float, opacity: float) -> None:
        p.save()
        p.setOpacity(max(0.0, min(1.0, opacity)))
        self._transform(p, centre, angle, squash)
        p.scale(1 / scale, 1 / scale)
        p.drawImage(-fx.anchor(self.fh, scale), img)
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
        """Three little stars circling her head, twinkling."""
        b = self.body
        a = math.radians(b.angle)
        head = b.centre + QPointF(math.sin(a) * self.fh * 0.42, -math.cos(a) * self.fh * 0.42)
        rx, ry = self.fh * 0.18, self.fh * 0.055
        for i in range(3):
            t = now * 4.6 + i * math.tau / 3
            pos = head + QPointF(math.cos(t) * rx, math.sin(t) * ry - self.fh * 0.07)
            r = self.fh * 0.032 * (0.85 + 0.3 * math.sin(now * 9 + i))
            colour = QColor((QColor(255, 230, 80), GREEN, CYAN)[i])
            colour.setAlphaF(min(1.0, self.stars))
            glow = QRadialGradient(pos, r * 2.6)
            glow.setColorAt(0, QColor(colour.red(), colour.green(), colour.blue(), int(110 * self.stars)))
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(pos, r * 2.6, r * 2.6)
            path = QPainterPath()
            for k in range(8):
                rr = r if k % 2 == 0 else r * 0.38
                ang = k * math.pi / 4 + t
                pt = pos + QPointF(math.cos(ang) * rr, math.sin(ang) * rr)
                path.moveTo(pt) if k == 0 else path.lineTo(pt)
            path.closeSubpath()
            p.setBrush(colour)
            p.drawPath(path)

    def busy(self, now: float) -> bool:
        """Anything still fading out?"""
        return self.effects.busy(now) or any(now - g.born < 0.28 for g in self.ghosts)


class ThrowShow(QObject):
    """Runs a throw: physics with bounces, the slam, dazed, getting up - then she's home where she landed."""

    def __init__(self, companion: "Companion", rig: Callable[[], Rig | None], say: Callable[[str, str], None],
                 enabled: Callable[[], bool] = lambda: True) -> None:
        super().__init__()
        self.companion, self.rig, self.say, self.enabled = companion, rig, say, enabled
        self.fx = FlingFX()
        self.active = False
        self.state = ""
        self.area = QRect()
        self.slammed = False
        self.walls: list[str] = []          # what she slammed into, in order
        self._rng = random.Random()
        self._timer = fx.precise_timer(self, 8)
        self._timer.timeout.connect(self._tick)
        self._last = 0.0
        self._state_at = 0.0
        self._wall = ""                     # which wall she slammed: "left" / "right" / "top" / "bottom"
        self._feet = QPointF()              # where she'll stand up
        self._lie = 90.0                    # the angle she lies at
        self._from = 0.0
        self._said = False
        self._shake_at = -1e9
        self._shake_strength = 0.0
        self._squash_at = -1e9              # a floor bounce: a quick squash
        self._slam_speed = 0.0

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
        f = self.fx
        f.rig, f.fh = rig, fh
        f.body = Body(QPointF(body.center().x(), body.bottom() - fh / 2), QPointF(velocity), 0.0, velocity.x() * SPIN)
        f.pose = Pose(sweep=0.8, energy=1.0, t=time.monotonic())
        f.ghosts = []
        f.effects.clear()
        f.glitch = f.stars = f.impact = f.stretch = 0.0
        f.shake = QPointF()
        f.visible_body = True
        f._tint_key = None
        f.dirty = fx.DirtyTracker()
        screen = c.screen
        self.area = screen.availableGeometry()
        f.setGeometry(screen.geometry())
        f.show()
        f.raise_()
        c.busy_elsewhere = True
        c.character.hide()
        c.panel.hide()
        self.active, self.slammed, self._said = True, False, False
        self.walls: list[str] = []
        self._set("fly")
        self._last = time.monotonic()
        self._timer.start()
        f.effects.sparks(f.body.centre + QPointF(0, fh * 0.45), -math.pi / 2, 1.2, 10, (120, 420), time.monotonic(),
                         colours=(RED, CYAN), life=(0.2, 0.4))
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
        f = self.fx
        f.pose.t = now * 2.2
        getattr(self, "_on_" + self.state)(dt, now - self._state_at, now)
        f.glitch = max(0.0, f.glitch - dt * 2.2)
        f.impact = max(0.0, f.impact - dt * 7)
        shake_age = now - self._shake_at
        if shake_age < 0.35:
            k = self._shake_strength * (1 - shake_age / 0.35) ** 2
            f.shake = QPointF(self._rng.uniform(-k, k), self._rng.uniform(-k, k))
        else:
            f.shake = QPointF()
        f.ghosts = [g for g in f.ghosts if now - g.born < 0.28]
        f.effects.prune(now)
        f.refresh(now)

    def _floor(self) -> float:
        return float(self.area.bottom() + 1)

    def _clamp_x(self, x: float, half: float) -> float:
        return max(self.area.left() + half, min(x, self.area.right() + 1 - half))

    def _pivot(self, feet: QPointF, angle: float) -> QPointF:
        """Her middle, when she's turned by `angle` about her feet (and not sunk into the floor)."""
        a = math.radians(angle)
        half = self.fx.fh / 2
        return feet + QPointF(half * math.sin(a), -half * math.cos(a) - self.fx.fh * WIDTH * abs(math.sin(a)))

    def _feet_of(self, centre: QPointF, angle: float) -> QPointF:
        a = math.radians(angle)
        return QPointF(centre.x() - self.fx.fh / 2 * math.sin(a), self._floor())

    def _shake(self, now: float, strength: float) -> None:
        self._shake_at, self._shake_strength = now, strength

    # flying (and bouncing) --------------------------------------------------------------------------------------------
    def _on_fly(self, dt: float, k: float, now: float) -> None:
        f, b = self.fx, self.fx.body
        steps = max(1, int(math.ceil(dt / STEP)))
        h = dt / steps
        for _ in range(steps):
            b.vel = QPointF(b.vel.x() * (1 - DRAG * h), b.vel.y() * (1 - DRAG * h) + GRAVITY * h)
            b.centre += b.vel * h
            b.angle += b.spin * h
            if self._collide(now):
                return
        speed = math.hypot(b.vel.x(), b.vel.y())
        f.stretch = min(0.22, speed / 9000)
        bounce_age = now - self._squash_at                                    # a floor bounce's squash
        if bounce_age < 0.25:
            s = math.exp(-bounce_age * 14) * math.cos(bounce_age * 40) * 0.28
            b.squash = (1 + s, 1 - s)
        else:
            b.squash = (1.0, 1.0)
        if speed > 500 and (not f.ghosts or now - f.ghosts[-1].born > 0.028):
            f.ghost(now)
        f.pose = Pose(sweep=0.8, squat=0.2, energy=1.0, blink=0.6 if self.slammed else 0.0, t=now * 2.2)
        if k > 8:                                                               # never fly forever
            self._settle(now)

    def _collide(self, now: float) -> bool:
        """Hit an edge this step? Handles it; True if the flight state changed."""
        f, b, a = self.fx, self.fx.body, self.area
        ex, ey = extents(f.fh, b.angle)
        wall = ""
        if b.centre.x() - ex < a.left() and b.vel.x() < 0:
            wall = "left"
        elif b.centre.x() + ex > a.right() + 1 and b.vel.x() > 0:
            wall = "right"
        elif b.centre.y() - ey < a.top() and b.vel.y() < 0:
            wall = "top"
        elif b.centre.y() + ey > self._floor() and b.vel.y() > 0:
            wall = "bottom"
        if not wall:
            return False
        normal_speed = abs(b.vel.x()) if wall in ("left", "right") else abs(b.vel.y())
        if normal_speed >= SLAM_SPEED:
            self._start_slam(wall, now, normal_speed)
            return True
        # a soft hit: bounce off it
        if wall == "left":
            b.centre.setX(a.left() + ex)
            b.vel = QPointF(-b.vel.x() * 0.45, b.vel.y() * 0.8)
            b.spin = -b.spin * 0.6
        elif wall == "right":
            b.centre.setX(a.right() + 1 - ex)
            b.vel = QPointF(-b.vel.x() * 0.45, b.vel.y() * 0.8)
            b.spin = -b.spin * 0.6
        elif wall == "top":
            b.centre.setY(a.top() + ey)
            b.vel = QPointF(b.vel.x() * 0.8, -b.vel.y() * 0.35)
        else:
            b.centre.setY(self._floor() - ey)
            if normal_speed > REST_SPEED:                                       # a bounce off the floor
                b.vel = QPointF(b.vel.x() * 0.7, -b.vel.y() * FLOOR_BOUNCE)
                upright = abs(((b.angle + 180) % 360) - 180) < 30
                if upright and not self.slammed:                                # feet first: stay on her feet
                    b.spin *= 0.3
                else:
                    b.spin = b.spin * 0.55 + b.vel.x() * 0.25                   # tumbling: she rolls with it
                self._squash_at = now
                f.effects.dust(QPointF(b.centre.x(), self._floor()), now, f.fh, 4)
                if normal_speed > 600:
                    f.effects.ring(QPointF(b.centre.x(), self._floor()), now, f.fh * 0.35, CYAN, 0.35, flat=0.28,
                                   width=2.5)
                    self._shake(now, f.fh * 0.012)
            else:
                self._settle(now)
                return True
        return False

    def _settle(self, now: float) -> None:
        """She's come to rest on the floor: on her feet if she's upright-ish, else lying (then dazed)."""
        f, b = self.fx, self.fx.body
        angle = ((b.angle + 180) % 360) - 180
        f.stretch = 0.0
        b.squash = (1.0, 1.0)
        if abs(angle) < 45 and not self.slammed:
            self._feet = QPointF(self._clamp_x(b.centre.x(), f.fh * WIDTH), self._floor())
            self._from = angle
            f.effects.dust(self._feet, now, f.fh, 6)
            return self._set("land")
        self._feet = QPointF(self._clamp_x(self._feet_of(b.centre, angle).x() if abs(angle) > 45 else b.centre.x(),
                                           f.fh * WIDTH), self._floor())
        self._from, self._lie = angle, nearest_lying(angle) if abs(angle) > 20 else (90.0 if b.vel.x() >= 0 else -90.0)
        if abs(self._from) > 120:                                              # upside down: roll the short way
            self._from = self._from - 360 if self._from > 0 and self._lie < 0 else \
                self._from + 360 if self._from < 0 and self._lie > 0 else self._from
        self._set("topple")

    # the slam ------------------------------------------------------------------------------------------------------
    def _start_slam(self, wall: str, now: float, speed: float) -> None:
        f, b, a = self.fx, self.fx.body, self.area
        strength = min(1.0, speed / 3000)
        self._wall, self._slam_speed, self.slammed = wall, speed, True
        self.walls.append(wall)
        half = f.fh * WIDTH
        if wall in ("left", "right"):
            b.angle = 0.0                                                   # flat against the wall, upright
            y = max(a.top() + f.fh / 2, min(b.centre.y(), self._floor() - f.fh / 2))
            b.centre = QPointF(a.left() + half * 0.55 if wall == "left" else a.right() + 1 - half * 0.55, y)
            at = QPointF(a.left() if wall == "left" else a.right() + 1, y - f.fh * 0.1)
            normal = QPointF(1 if wall == "left" else -1, 0)
        else:
            b.angle = 90.0 if b.vel.x() >= 0 else -90.0                     # flat against the ceiling / floor
            x = self._clamp_x(b.centre.x(), f.fh / 2)
            b.centre = QPointF(x, a.top() + half * 0.55 if wall == "top" else self._floor() - half * 0.55)
            at = QPointF(x, a.top() if wall == "top" else self._floor())
            normal = QPointF(0, 1 if wall == "top" else -1)
        self._impact_at, self._normal = at, normal
        self._bounce_vel = QPointF(b.vel)
        b.spin = 0.0
        out = math.atan2(normal.y(), normal.x())
        e = f.effects
        e.flash(at, now, f.fh * (0.55 + 0.4 * strength), 0.2)
        e.sparks(at, out, 1.25, int(22 + 26 * strength), (260, 1100 * (0.6 + 0.6 * strength)), now)
        e.sparks(at, out, 0.5, 8, (700, 1500), now, colours=(WHITE,), life=(0.12, 0.22), size=(2.5, 4))
        e.shards(at, out, int(8 + 10 * strength), now, f.fh)
        e.crack(at, normal, now, f.fh * (0.5 + 0.45 * strength))
        flat = 0.3 if wall in ("top", "bottom") else 3.0
        e.ring(at, now, f.fh * (0.55 + 0.4 * strength), CYAN, 0.42, flat=flat, width=4)
        e.ring(at, now, f.fh * (0.35 + 0.3 * strength), RED, 0.32, flat=flat, width=3)
        e.dust(at, now, f.fh, 5)
        f.glitch, f.stars, f.impact, f.stretch = 1.0, 1.0, 1.0, 0.0
        f.ghosts = []
        f.pose = Pose(squat=0.6, blink=0.9, energy=1.0, t=now * 2.2)
        self._shake(now, f.fh * (0.03 + 0.05 * strength))
        self.say(self._rng.choice(OUCH), "angry")
        self._said = True
        self._set("slam")

    def _on_slam(self, dt: float, k: float, now: float) -> None:
        f, b = self.fx, self.fx.body
        if k < HIT_STOP:                                                    # the freeze
            flat = 0.5
            b.squash = (flat, 1.25) if self._wall in ("left", "right") else (1.25, flat)
            return
        t = (k - HIT_STOP) / SLAM_TIME
        flat = 0.5 + 0.5 * fx.spring(t)                                     # springing back with a wobble
        thin, tall = flat, 1 + (1 - flat) * 0.5
        b.squash = (thin, tall) if self._wall in ("left", "right") else (tall, thin)
        half, area = f.fh * WIDTH, self.area
        if self._wall == "left":
            b.centre.setX(area.left() + half * thin)
        elif self._wall == "right":
            b.centre.setX(area.right() + 1 - half * thin)
        elif self._wall == "top":
            b.centre.setY(area.top() + half * thin)
        else:
            b.centre.setY(self._floor() - half * thin)
        if t < 1:
            return
        # BOUNCE off it, tumbling away
        v, n = self._bounce_vel, self._normal
        normal_part = abs(v.x()) if self._wall in ("left", "right") else abs(v.y())
        tangent = QPointF(v.x(), 0) if self._wall in ("top", "bottom") else QPointF(0, v.y())
        back = QPointF(n.x(), n.y()) * normal_part * BOUNCE
        kick = QPointF(0, -min(520.0, normal_part * 0.18)) if self._wall in ("left", "right") else QPointF()
        b.vel = back + tangent * 0.5 + kick
        b.spin = (520 + normal_part * 0.12) * (1 if n.x() >= 0 else -1) * (1 if self._wall != "top" else 0.6)
        b.squash = (1.0, 1.0)
        if self._wall == "bottom":                                          # a faceplant: up off the floor a bit
            b.vel = QPointF(v.x() * 0.4, -min(700.0, normal_part * BOUNCE))
            b.spin = 380 * (1 if v.x() >= 0 else -1)
        self._set("fly")

    # lying, dazed, getting up -------------------------------------------------------------------------------------------
    def _on_topple(self, dt: float, k: float, now: float) -> None:
        """Rolling over onto her side, from wherever she ended up."""
        f, b = self.fx, self.fx.body
        t = min(1.0, k / TOPPLE_TIME)
        b.angle = self._from + (self._lie - self._from) * fx.ease_in(t) ** 0.7
        b.centre = self._pivot(self._feet, b.angle) if abs(self._from) < 60 else \
            QPointF(b.centre.x(), self._floor() - f.fh * WIDTH - (1 - t) * 4)
        if t >= 1:
            b.angle = self._lie
            b.centre = QPointF(self._clamp_x(b.centre.x(), f.fh / 2), self._floor() - f.fh * WIDTH)
            self._feet = QPointF(self._clamp_x(self._feet_of(b.centre, self._lie).x(), f.fh * WIDTH), self._floor())
            f.effects.dust(QPointF(b.centre.x(), self._floor()), now, f.fh, 6)
            self._squash_at = now
            f.stars = max(f.stars, 0.9 if self.slammed else 0.0)
            if not self._said and self.slammed:
                self.say(self._rng.choice(OUCH), "angry")
                self._said = True
            self._set("dazed")

    def _on_dazed(self, dt: float, k: float, now: float) -> None:
        f, b = self.fx, self.fx.body
        bounce = math.exp(-k * 10) * math.sin(k * 32)                         # a little bounce as she lands
        b.squash = (1 - 0.12 * bounce, 1 + 0.06 * bounce)
        twitch = math.sin(k * 3.2) * 1.6
        b.angle = self._lie + twitch * (1 if self._lie > 0 else -1)
        b.centre = QPointF(b.centre.x(), self._floor() - f.fh * WIDTH)
        f.pose = Pose(blink=0.75 + 0.25 * math.sin(k * 5), energy=0.4, t=now * 2.2)
        if k >= (DAZED_TIME if self.slammed else DAZED_TIME * 0.45):
            b.squash = (1.0, 1.0)
            self._from = b.angle
            self._feet = QPointF(self._clamp_x(self._feet_of(b.centre, b.angle).x(), f.fh * WIDTH), self._floor())
            self._set("getup")

    def _on_getup(self, dt: float, k: float, now: float) -> None:
        f, b = self.fx, self.fx.body
        t = min(1.0, k / GETUP_TIME)
        b.angle = self._from * (1 - fx.spring(t, 1.6))
        b.centre = self._pivot(self._feet, b.angle)
        f.stars = max(0.0, 1 - t * 1.4) if self.slammed else 0.0
        f.pose = Pose(squat=0.5 * math.sin(math.pi * t), energy=0.6, t=now * 2.2)
        if t >= 1:
            self._home(now)

    def _on_land(self, dt: float, k: float, now: float) -> None:
        f, b = self.fx, self.fx.body
        t = min(1.0, k / LAND_TIME)
        b.angle = self._from * (1 - fx.spring(t, 1.8))
        b.centre = self._pivot(self._feet, b.angle)
        squash = math.exp(-t * 6) * 0.22
        b.squash = (1 + squash, 1 - squash)
        f.pose = Pose(squat=0.7 * math.sin(math.pi * t), energy=0.7, t=now * 2.2)
        if t >= 1:
            b.squash = (1.0, 1.0)
            self._home(now)

    # back in her window ------------------------------------------------------------------------------------------------
    def _home(self, now: float) -> None:
        c, f = self.companion, self.fx
        f.visible_body, f.stars = False, 0.0
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
        if self.fx.busy(now) and k < 3.0:
            return
        self._timer.stop()
        self.fx.hide()
        self.fx.rig = None
        self.active = False
