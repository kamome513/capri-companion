"""Roaming: now and then, while nothing's going on, she teleports somewhere else along the bottom of her
screen and stands there for a while.

The teleport is her power - Blackwall-style: a dark void opens behind her, jagged black shards with red
glowing edges rise out of the floor and spiral up around her, red static crackles through it, the shards close
in and she tears apart like a broken feed - gone with a red flash. Then the same in reverse where she lands:
the void opens, the shards spiral in, she pieces herself back together band by band, and the shards burst
off and fall away.

Only while she's idle: not listening, thinking or talking, not in drone mode, not sitting on a window or
lying on her panel, not hidden. Anything that needs her (you say "Hey Capri", a reply...) cuts it short and
she's simply there. Settings -> Extras -> "Roam around"; "go for a walk" / "teleport" / "stay there" by voice.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient

from ..states import State
from . import fx
from .overlay_window import OverlayWindow
from .rig import Pose, Rig

if TYPE_CHECKING:
    from .companion import Companion

WAIT = (45.0, 140.0)      # seconds between teleports
DISTANCE = (0.15, 0.55)   # how far she goes, as a share of the screen's width
BUSY = {State.LISTENING, State.PROCESSING, State.LAUNCHING, State.SPEAKING}   # she's needed: no roaming
# the teleport's beats, in seconds
GATHER, ENGULF, VANISH, TRAVEL, APPEAR, SETTLE = 0.55, 0.2, 0.14, 0.12, 0.42, 0.34
SHARDS = 16
RED, CYAN = fx.RED, fx.CYAN
DARK = QColor(6, 3, 8)


@dataclass
class Shard:
    angle: float                 # where on the orbit
    height: float                # 0 (feet) .. 1 (head)
    length: float                # share of her height
    width: float
    speed: float                 # orbit speed (radians / s)
    kinks: tuple                 # the jagged bends along it


def make_shards(rng: random.Random) -> list[Shard]:
    return [Shard(rng.uniform(0, math.tau), rng.uniform(0.0, 1.0), rng.uniform(0.12, 0.3), rng.uniform(0.025, 0.05),
                  rng.uniform(2.2, 4.0) * rng.choice((1, 1, -1)),
                  tuple(rng.uniform(-0.5, 0.5) for _ in range(3))) for _ in range(SHARDS)]


def shard_path(base: QPointF, direction: float, length: float, width: float, kinks: tuple) -> QPainterPath:
    """A jagged spike: wide at its base, bending a couple of times, sharp at the tip - like her hair."""
    dx, dy = math.cos(direction), math.sin(direction)
    nx, ny = -dy, dx
    pts_l, pts_r = [], []
    for i, k in enumerate((0.0,) + kinks):
        t = i / (len(kinks) + 1)
        w = width * (1 - t) ** 0.8
        cx, cy = base.x() + dx * length * t + nx * k * width * 1.4, base.y() + dy * length * t + ny * k * width * 1.4
        pts_l.append(QPointF(cx + nx * w, cy + ny * w))
        pts_r.append(QPointF(cx - nx * w, cy - ny * w))
    tip = QPointF(base.x() + dx * length, base.y() + dy * length)
    path = QPainterPath(pts_l[0])
    for pt in pts_l[1:] + [tip] + list(reversed(pts_r)):
        path.lineTo(pt)
    path.closeSubpath()
    return path


class TeleportFX(OverlayWindow):
    """A see-through window over the stretch of screen she teleports across."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.rig: Rig | None = None
        self.fh = 250.0
        self.here = QPointF()            # her feet now
        self.there = QPointF()           # where she's going
        self.t = 0.0                     # seconds into the teleport
        self.sprite: QImage | None = None
        self.red: QImage | None = None
        self.cyan: QImage | None = None
        self.shards: list[Shard] = []
        self.effects = fx.Effects()
        self.dirty = fx.DirtyTracker()
        self._rng = random.Random()

    # -- where ------------------------------------------------------------------------------------------------------
    def around(self, feet: QPointF) -> QRectF:
        r = self.fh * 0.85
        return QRectF(feet.x() - r, feet.y() - self.fh * 1.45, 2 * r, self.fh * 1.55)

    def refresh(self, now: float) -> None:
        area = self.around(self.here).united(self.around(self.there)) if self.TRAVEL_IN(self.t) else \
            (self.around(self.here) if self.t < GATHER + ENGULF + VANISH else self.around(self.there))
        self.update()                     # the whole window each frame (partial repaints left old frames on Windows)

    @staticmethod
    def TRAVEL_IN(t: float) -> bool:                                       # noqa: N802
        return GATHER + ENGULF < t < GATHER + ENGULF + VANISH + TRAVEL + 0.05

    # -- painting -------------------------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        try:
            self._paint_frame(p, event)
        except Exception:                                  # a bad frame: log it - the window still finishes cleanly
            import logging
            logging.getLogger("capri").exception("effects: a frame failed to draw")
        finally:
            p.end()

    def _paint_frame(self, p: QPainter, event) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(-QPointF(self.geometry().topLeft()))
        now, t = time.monotonic(), self.t
        if self.sprite is None:                                             # she's home: the last bits fall away
            self.effects.paint_under(p, now)
            self.effects.paint_over(p, now)
            return
        self.effects.paint_under(p, now)
        out_end = GATHER + ENGULF + VANISH
        in_start = out_end + TRAVEL
        if t < out_end:                                                     # leaving
            power = fx.ease_out(t / GATHER) if t < GATHER else 1.0
            close = fx.ease_in((t - GATHER) / ENGULF) if t >= GATHER else 0.0
            gone = (t - GATHER - ENGULF) / VANISH if t >= GATHER + ENGULF else 0.0
            self._scene(p, self.here, power * (1 - 0.6 * gone), close, gone, t, leaving=True)
        elif t < in_start:                                                  # the jump: a red glitch line between
            k = (t - out_end) / TRAVEL
            self._streak(p, k)
        else:                                                               # arriving
            k = (t - in_start) / APPEAR
            if k < 1:
                self._scene(p, self.there, fx.ease_out(min(1.0, k * 1.6)), 1 - fx.ease_out(k), 1 - fx.ease_out(k), t,
                            leaving=False)
            else:
                s = (t - in_start - APPEAR) / SETTLE                         # standing there; the power fades off
                self._void(p, self.there, 0.6 * (1 - s))
                self._her(p, self.there, 1.0, 0.0, settle=s)
        self.effects.paint_over(p, now)

    def _scene(self, p: QPainter, feet: QPointF, power: float, close: float, gone: float, t: float,
               leaving: bool) -> None:
        """The void, the shards (behind her, then her, then in front of her), the static."""
        self._void(p, feet, power)
        self._shards(p, feet, power, close, t, front=False)
        self._her(p, feet, 1 - gone if leaving else 1 - gone, max(close, gone))
        self._shards(p, feet, power, close, t, front=True)
        self._static(p, feet, power * (0.4 + 0.6 * close))

    def _void(self, p: QPainter, feet: QPointF, power: float) -> None:
        if power <= 0.01:
            return
        centre = feet - QPointF(0, self.fh * 0.5)
        r = self.fh * (0.45 + 0.25 * power)
        g = QRadialGradient(centre, r)
        g.setColorAt(0, QColor(0, 0, 0, int(200 * power)))
        g.setColorAt(0.62, QColor(12, 0, 6, int(170 * power)))
        g.setColorAt(0.8, QColor(RED.red(), RED.green(), RED.blue(), int(110 * power)))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.save()
        p.translate(centre)
        p.scale(0.72, 1.0)
        p.translate(-centre)
        p.drawEllipse(centre, r, r)
        p.restore()
        floor = QRadialGradient(feet, self.fh * 0.5)                       # a red pool on the floor
        floor.setColorAt(0, QColor(RED.red(), RED.green(), RED.blue(), int(150 * power)))
        floor.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(floor)
        p.drawEllipse(feet, self.fh * 0.5, self.fh * 0.09)

    def _shards(self, p: QPainter, feet: QPointF, power: float, close: float, t: float, front: bool) -> None:
        if power <= 0.01:
            return
        rx = self.fh * (0.42 - 0.24 * close)
        for s in self.shards:
            a = s.angle + s.speed * t * (1 + 1.5 * close)
            depth = math.sin(a)
            if (depth >= 0) != front:
                continue
            rise = min(1.0, power * 1.25 - s.height * 0.25)                 # they come up out of the floor
            if rise <= 0:
                continue
            y = feet.y() - self.fh * (s.height * 0.95 * rise)
            base = QPointF(feet.x() + math.cos(a) * rx, y + depth * self.fh * 0.05)
            direction = -math.pi / 2 + math.cos(a) * 0.9 + (0.25 if s.speed > 0 else -0.25)   # up, leaning out
            length = self.fh * s.length * rise * (0.75 + 0.25 * math.sin(t * 9 + s.angle))
            path = shard_path(base, direction, length, self.fh * s.width, s.kinks)
            shade = 0.55 + 0.45 * (depth + 1) / 2                         # nearer = brighter edge
            p.setPen(QPen(QColor(RED.red(), RED.green(), RED.blue(), int(90 * power * shade)), self.fh * 0.022))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)                                                # the glow
            p.setPen(QPen(QColor(255, 60, 100, int(255 * power * shade)), max(1.0, self.fh * 0.006)))
            p.setBrush(QColor(DARK.red(), DARK.green(), DARK.blue(), int(240 * power)))
            p.drawPath(path)

    def _static(self, p: QPainter, feet: QPointF, amount: float) -> None:
        """Red static and dead blocks crackling inside her power (at camera speed: it steps, it doesn't glide)."""
        if amount <= 0.02:
            return
        r = random.Random(int(time.monotonic() * 30))
        box = self.around(feet).adjusted(self.fh * 0.25, self.fh * 0.25, -self.fh * 0.25, -self.fh * 0.05)
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(3 + 9 * amount)):
            w, h = r.uniform(4, self.fh * 0.22), r.uniform(1.5, 5)
            x, y = r.uniform(box.left(), box.right() - w), r.uniform(box.top(), box.bottom())
            c = QColor(r.choice((RED, RED, QColor(0, 0, 0), QColor(255, 255, 255), CYAN)))
            c.setAlpha(int(r.uniform(90, 220) * amount))
            p.setBrush(c)
            p.drawRect(QRectF(x, y, w, h))

    def _her(self, p: QPainter, feet: QPointF, visible: float, tear: float, settle: float = -1.0) -> None:
        """Her, whole or torn into sideways-jumping bands with her colours split."""
        if visible <= 0.01 or self.sprite is None:
            return
        img = self.sprite
        top_left = QPointF(feet.x() - img.width() / 2, feet.y() - self.fh * 1.12)
        squash = 0.0
        if settle >= 0:                                                   # a little bob as she lands
            squash = math.exp(-settle * 7) * math.sin(settle * 18) * 0.06
        if tear <= 0.02:
            p.save()
            p.setOpacity(visible)
            p.translate(feet)
            p.scale(1 + squash, 1 - squash)
            p.translate(-feet)
            p.drawImage(top_left, img)
            p.restore()
            return
        r = random.Random(int(time.monotonic() * 30))
        split = self.fh * 0.05 * tear
        p.setOpacity(min(1.0, visible) * 0.8)
        p.drawImage(top_left + QPointF(-split, 0), self.red)
        p.drawImage(top_left + QPointF(split, r.uniform(-2, 2)), self.cyan)
        p.setOpacity(min(1.0, visible))
        y = 0.0
        while y < img.height():                                           # horizontal bands, jumping sideways
            band = r.uniform(3, self.fh * 0.06)
            shift = r.choice((-1, 1)) * r.uniform(0, self.fh * 0.3) * tear if r.random() < 0.6 else 0.0
            if r.random() > tear * 0.35:                                   # some bands are already gone
                p.drawImage(QRectF(top_left.x() + shift, top_left.y() + y, img.width(), band), img,
                            QRectF(0, y, img.width(), band))
            y += band
        p.setOpacity(1.0)

    def _streak(self, p: QPainter, k: float) -> None:
        """The jump itself: a thin red glitch line racing along the floor from here to there."""
        a, b = self.here - QPointF(0, self.fh * 0.06), self.there - QPointF(0, self.fh * 0.06)
        head = a + (b - a) * fx.ease_in_out(k)
        tail = a + (b - a) * fx.ease_in_out(max(0.0, k - 0.35))
        for width, alpha in ((self.fh * 0.05, 70), (self.fh * 0.012, 255)):
            p.setPen(QPen(QColor(RED.red(), RED.green(), RED.blue(), alpha), width, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawLine(tail, head)
        p.setPen(QPen(QColor(255, 255, 255, 230), max(1.0, self.fh * 0.004)))
        p.drawLine(tail + (head - tail) * 0.6, head)


class RoamShow(QObject):
    def __init__(self, companion: "Companion", rig: Callable[[], Rig | None], enabled: Callable[[], bool],
                 idle: Callable[[], bool] = lambda: True, rng: random.Random | None = None,
                 quiet: Callable[[], bool] = lambda: False) -> None:
        super().__init__()
        self.companion, self.rig, self.enabled, self.idle = companion, rig, enabled, idle
        self.quiet = quiet
        self.home_x: float | None = None                       # her corner, while she's off somewhere else
        self.rng = rng or random.Random()
        self.fx = TeleportFX()
        self.active = False
        self._timer = fx.precise_timer(self, 8)
        self._timer.timeout.connect(self._tick)
        self._clock = QTimer(self)                  # when the next teleport is due
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._maybe_walk)
        self._due = time.monotonic() + self.rng.uniform(*WAIT)
        self._started = 0.0
        self._ground = 0.0
        self._to = 0.0
        self._panel = False
        self._burst_done = self._arrive_done = False
        self._ended = 0.0
        self._settled = False

    CALM = 60.0              # seconds after she last did something for you before she may wander
    HOME_AFTER = (20.0, 45.0)  # away from her corner: back this long after

    def start(self) -> None:
        self._clock.start()

    # -- when ------------------------------------------------------------------------------------------------
    def can_walk(self) -> bool:
        c = self.companion
        if c.controller.state in BUSY or not self.idle() or self._quiet():
            self._calm_since = time.monotonic()               # working for you / a game: stay put a while
            return False
        return (not self.active and not c.hidden and not c.drone and not c.perched and not c.lounging()
                and not c.busy_elsewhere and c.character.isVisible()
                and time.monotonic() - getattr(self, "_calm_since", -1e9) >= self.CALM)

    def _quiet(self) -> bool:
        try:
            return bool(self.quiet())
        except Exception:
            return False

    def _maybe_walk(self) -> None:
        now = time.monotonic()
        if not self.enabled():
            if self.home_x is not None and self.can_walk():
                self.walk(self.home_x)                         # turned off while away: home to her corner
            return
        if now < self._due:
            self.can_walk()                                    # (keeps track of when she last worked for you)
            return
        self._due = now + self.rng.uniform(*WAIT)
        if not self.can_walk():
            return
        if self.home_x is not None:                            # away: back to her corner
            self.walk(self.home_x)
        else:
            self.walk()

    @property
    def length(self) -> float:
        return GATHER + ENGULF + VANISH + TRAVEL + APPEAR + SETTLE

    # -- the teleport ------------------------------------------------------------------------------------------
    def walk(self, to_x: float | None = None) -> bool:
        """Teleport to `to_x` (screen x of her feet), or somewhere else along the bottom. False if she can't now."""
        c = self.companion
        if not self.can_walk():
            return False
        self._timer.stop()                                                   # (a last one still fading out)
        rig = self.rig()
        if rig is None:
            return False
        body = c.content_geometry()
        area = c.screen.availableGeometry()
        fh = float(c.character.figure_height())
        margin = fh * 0.3
        here = float(body.center().x())
        if to_x is None:
            far = self.rng.uniform(*DISTANCE) * area.width()
            room_left, room_right = here - area.left() - margin, area.right() - margin - here
            direction = -1 if room_left > room_right and self.rng.random() < 0.7 or room_right < far else 1
            to_x = here + direction * far
        to_x = max(area.left() + margin, min(float(to_x), area.right() + 1 - margin))
        if abs(to_x - here) < fh * 0.3:
            if self.home_x is not None and abs(to_x - self.home_x) < fh * 0.3:
                self.home_x = None
            return False
        going_home = self.home_x is not None and abs(to_x - self.home_x) < 1
        if going_home:
            self.home_x = None
        elif self.home_x is None:
            self.home_x = here                                 # where to come back to
            self._due = time.monotonic() + self.rng.uniform(*self.HOME_AFTER)
        self._ground, self._to = float(body.bottom() + 1), to_x
        f = self.fx
        f.rig, f.fh = rig, fh
        f.here, f.there = QPointF(here, self._ground), QPointF(to_x, self._ground)
        pose = Pose(energy=1.0, squat=0.15, t=time.monotonic() * 2.2)
        f.sprite = fx.render(rig, fh, pose)
        f.red = fx.render(rig, fh, pose, tint=RED, hair=False)
        f.cyan = fx.render(rig, fh, pose, tint=CYAN, hair=False)
        f.shards = make_shards(self.rng)
        f.effects.clear()
        f.dirty = fx.DirtyTracker()
        f.t = 0.0
        f.setGeometry(QRect(area.left(), round(self._ground - fh * 1.6), area.width(), round(fh * 1.75)))
        f.show()
        f.raise_()
        self._panel = c.panel.isVisible()
        c.busy_elsewhere = True
        c.character.hide()
        c.panel.hide()
        self.active, self._burst_done, self._arrive_done = True, False, False
        self._started = time.monotonic()
        now = self._started
        f.effects.motes(f.here - QPointF(0, fh * 0.5), fh * 0.7, 26, now, inward=True, colours=(RED, RED, CYAN),
                        life=(0.35, 0.55))
        self._timer.start()
        return True

    def stop(self) -> None:
        """Something needs her: she's simply there (where she was, if she hadn't left yet)."""
        if self.active:
            self._finish(self.fx.here.x() if self.fx.t < GATHER + ENGULF else self._to)

    def _tick(self) -> None:
        now = time.monotonic()
        f = self.fx
        if not self.active:                                                 # lingering: effects fading out
            if f.effects.busy(now) and now - self._ended < 2.0:
                f.update()
                return
            self._timer.stop()
            f.hide()
            return
        t = now - self._started
        f.t = t
        if self.companion.controller.state in BUSY:
            return self._finish(f.here.x() if t < GATHER + ENGULF else self._to)
        e = f.effects
        if not self._burst_done and t >= GATHER + ENGULF:                     # gone: the shards burst off
            self._burst_done = True
            mid = f.here - QPointF(0, f.fh * 0.5)
            e.flash(mid, now, f.fh * 0.6, 0.22)
            e.shards(mid, -math.pi / 2, 14, now, f.fh)
            e.sparks(mid, -math.pi / 2, math.pi, 18, (200, 700), now, colours=(RED, RED, QColor(255, 255, 255)))
            e.ring(f.here, now, f.fh * 0.55, RED, 0.4, flat=0.25, width=3)
        if not self._arrive_done and t >= GATHER + ENGULF + VANISH + TRAVEL:  # landing there
            self._arrive_done = True
            e.motes(f.there - QPointF(0, f.fh * 0.5), f.fh * 0.75, 24, now, inward=True, colours=(RED, CYAN),
                    life=(0.25, 0.4))
            e.ring(f.there, now, f.fh * 0.6, CYAN, 0.5, flat=0.25, width=3)
        if self._arrive_done and t >= GATHER + ENGULF + VANISH + TRAVEL + APPEAR * 0.85 and \
                not getattr(self, "_settled", False):
            self._settled = True
            e.shards(f.there - QPointF(0, f.fh * 0.6), -math.pi / 2, 10, now, f.fh)
            e.flash(f.there - QPointF(0, f.fh * 0.5), now, f.fh * 0.45, 0.18)
        e.prune(now)
        f.refresh(now)
        if t >= self.length:
            self._finish(self._to)

    def _finish(self, x: float) -> None:
        self._timer.stop()
        self._settled = False
        self.fx.t = self.length
        c, f = self.companion, self.fx
        content = c.character.content_rect()
        target = QPoint(round(x - (content.x() + content.width() / 2)), round(self._ground - (content.y() + content.height())))
        c._move_character(target, c.screen)
        c._remember_position()
        c.busy_elsewhere = False
        c.show()
        if not self._panel:
            c.panel.hide()
        QTimer.singleShot(60, lambda: None if c.busy_elsewhere or c.perched else c.place())   # some window
        # managers put a window back where *they* like when it's shown again: where she landed, please
        f.sprite = f.rig = None
        self.active = False
        self._ended = time.monotonic()
        if f.effects.busy(self._ended):
            self._timer.start()                                             # let the shards finish falling
        else:
            f.hide()
