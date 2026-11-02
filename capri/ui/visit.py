"""Capri dashes over to something on screen and zaps it - "go into downloads" (the Downloads
entry in File Explorer), "minimise Discord" (Discord's minimise button), "unmute me" (Discord's
Mute button). Standing or lying on the panel, she gets up and goes.

    crouch, hair flaring -> dash there with red lag lightning crackling behind her and red
    afterimages -> land beside it (on the window's top edge, or the bottom of the screen) ->
    point at it -> a bolt from her hand hits it with a shock ring (the real action runs at
    the impact) -> she lowers her arm and dashes home the same way.

No bending: her arm is aimed straight at the target. Uses her full-body figure (rig.py).
Click-through, never takes focus; ~2 s, then nothing runs.
"""

from __future__ import annotations

import logging
import math
import random
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QSizeF, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtCore import Qt

from . import lightning
from .overlay_window import OverlayWindow
from .rig import REACH_DEGREES, SHOULDER, Pose, Rig

if TYPE_CHECKING:
    from .companion import Companion

log = logging.getLogger("capri")

FIGURE_HEIGHT = 250           # when her own figure's size isn't known
WINDUP, DASH, LAND, RAISE, ZAP, HOLD, LOWER = 0.14, 0.34, 0.12, 0.22, 0.42, 0.3, 0.2
IMPACT = 0.12                 # into the zap: when the bolt lands (and the action runs)
TRAIL = 0.55
STAND_OFF = 0.55              # how far beside the target she stands (x her height)
RED = QColor(236, 16, 70)


def _screen_for(rect: QRect):
    screen = QGuiApplication.screenAt(rect.center())
    if screen is not None:
        return screen
    return min(QGuiApplication.screens(),
               key=lambda s: (s.geometry().center() - rect.center()).manhattanLength())


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class VisitFX(OverlayWindow):
    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.rig: Rig | None = None
        self.side = "right"
        self.feet: QPointF | None = None
        self.pose = Pose()
        self.trail: list[tuple[float, QPointF]] = []
        self.ghosts: list[tuple[float, QRectF, QImage]] = []
        self.bursts: list[tuple[float, QPointF]] = []
        self.zap: tuple[float, QPointF, QRectF] | None = None    # (start, hand, target)
        self.fh = FIGURE_HEIGHT                                  # her height on screen
        self._rng = random.Random()

    def ghost(self, now: float) -> None:
        if self.rig is None or self.feet is None:
            return
        w, h = int(self.fh * 1.4), int(self.fh * 1.45)
        img = QImage(w // 2, h // 2, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        q = QPainter(img)
        q.scale(0.5, 0.5)
        anchor = QPointF(w / 2, h - 4)
        self.rig.paint(q, anchor, self.fh, self.pose, self.side)
        q.resetTransform()
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        q.fillRect(img.rect(), RED)
        q.end()
        self.ghosts.append((now, QRectF(self.feet - anchor, QSizeF(w, h)), img))
        del self.ghosts[:-8]

    def paintEvent(self, event) -> None:
        if self.rig is None:
            return
        p = QPainter(self)
        self.paint_scene(p, QPointF(self.geometry().topLeft()))
        p.end()

    def paint_scene(self, p: QPainter, o: QPointF) -> None:
        """The whole dash, in screen coordinates shifted by `o` (the painting window's top-left).
        Each monitor the dash crosses has its own window painting this same scene."""
        if self.rig is None:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        now = time.monotonic()
        for t, at, img in self.ghosts:                                  # red lag afterimages
            age = (now - t) / TRAIL
            if age < 1:
                p.setOpacity(0.45 * (1 - age))
                p.drawImage(at.translated(-o + QPointF(self._rng.uniform(-3, 3), 0)), img)
        p.setOpacity(1.0)
        lightning.crackle(p, [(t, pt - o) for t, pt in self.trail], now, TRAIL,
                          [self.fh * f for f in (0.85, 0.6, 0.35, 0.1)], self._rng, arcs=7)
        for t, pt in self.bursts:                                       # red flash where she lands / leaves
            age = (now - t) / 0.35
            if 0 <= age < 1:
                g = QRadialGradient(pt - o, 90)
                g.setColorAt(0, QColor(RED.red(), RED.green(), RED.blue(), int(170 * (1 - age))))
                g.setColorAt(1, QColor(0, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(pt - o, 90, 90)
        if self.feet is not None:
            self.rig.paint(p, self.feet - o, self.fh, self.pose, self.side)
        if self.zap is not None:                                        # her bolt into the target
            t0, hand, target = self.zap
            k = (now - t0) / ZAP
            if 0 <= k < 1:
                center = target.center() - o
                strength = (1 - k) * self._rng.uniform(0.75, 1.0)
                lightning.draw(p, lightning.bolt(hand - o, center, self._rng, roughness=0.22, depth=5), strength, 1.3)
                if k * ZAP >= IMPACT:                                   # shock ring + crackle on the target
                    hit = 1 - (k * ZAP - IMPACT) / (ZAP - IMPACT)
                    r = 10 + 34 * (1 - hit)
                    p.setPen(QPen(QColor(236, 16, 70, int(230 * hit)), 3))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(center, target.width() / 2 + r, target.height() / 2 + r)
                    for _ in range(3):
                        end = center + QPointF(self._rng.uniform(-40, 40), self._rng.uniform(-40, 40))
                        lightning.draw(p, lightning.bolt(center, end, self._rng, roughness=0.3, depth=3), hit, 0.7)


class _Mirror(OverlayWindow):
    """The dash on another monitor: a window there painting the same scene (one window per
    monitor, so each is drawn at its own monitor's scaling)."""

    def __init__(self, scene: VisitFX) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.scene = scene

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        self.scene.paint_scene(p, QPointF(self.geometry().topLeft()))
        p.end()


class VisitShow(QObject):
    def __init__(self, companion: Companion) -> None:
        super().__init__()
        self.companion = companion
        self.fx = VisitFX()
        self.mirrors: list[_Mirror] = []
        self.active = False
        self._rig: Rig | None = None
        self._rig_full: Rig | None = None
        self._rig_key: tuple | None = None
        self.fh = FIGURE_HEIGHT
        self._then: Callable[[], None] | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def rig(self) -> Rig | None:
        """Her full-body figure, pre-scaled to her size on this screen (sharp, not shrunk on the fly)."""
        sprites = self.companion.sprites
        if sprites is None or "standing" not in getattr(sprites, "body", {}):
            return None
        if self._rig_full is None:
            self._rig_full = Rig(sprites.frame("standing"))
        style = getattr(self.companion.settings, "hair_style", "storm")
        self._rig_full.set_hair_style(style)
        dpr = self.companion.screen.devicePixelRatio()
        key = (self.fh, dpr, style)
        if self._rig_key != key:
            self._rig, self._rig_key = self._rig_full.resized(max(8, round(self.fh * dpr))), key
        return self._rig

    @property
    def ground(self) -> QPointF | None:
        return self.fx.feet

    def _spot(self, target: QRect, window: QRect | None, near: bool = False) -> tuple[QPointF, str]:
        """Where she stands: beside the target - right next to it, hovering (`near`, for a button
        inside a window), or on its window's top edge if there's room above it, else on the bottom
        of the screen. And which arm points at it."""
        c, fh = self.companion, self.fh
        area = _screen_for(target).availableGeometry()       # the target's monitor, not hers
        tx = target.center().x()
        room_right = area.right() - tx
        lead = 1 if room_right < fh * 0.9 or tx - area.left() > room_right else -1
        x = tx - lead * fh * (STAND_OFF * 0.75 if near else STAND_OFF)   # lead=1: she's left of it, pointing right
        x = max(area.left() + 40, min(x, area.right() - 40))
        ground = area.bottom() + 1
        if near:                                     # her shoulder a little above it, arm angled down at it
            ground = min(ground, target.center().y() + fh * 0.55)
            ground = max(ground, area.top() + fh)
        elif window is not None and window.top() - fh * 1.15 > area.top():
            ground = window.top()
        return QPointF(x, ground), ("right" if lead == 1 else "left")

    def _aim(self, side: str, feet: QPointF, target: QPointF) -> float:
        """Pose.reach that points her arm straight at the target."""
        rig = self._rig
        s = self.fh / rig.h
        sx = feet.x() + (SHOULDER[side][0] * rig.w - rig.feet.x()) * s
        sy = feet.y() + (SHOULDER[side][1] * rig.h - rig.feet.y()) * s
        lead = 1 if side == "right" else -1
        angle = math.degrees(math.atan2((target.x() - sx) * lead, target.y() - sy))   # 0 = straight down
        return max(0.0, min(3.0, angle / REACH_DEGREES))

    def visit(self, target: QRect, then: Callable[[], None], window: QRect | None = None, near: bool = False) -> None:
        """Dash to `target` (screen rect), zap it, run `then` at the impact, dash home.
        `near`: hover right beside it (a button inside a window) instead of landing on an edge."""
        c = self.companion
        if self.active or c.hidden or c.drone or not c.character.isVisible():
            return then()
        self.fh = c.character.figure_height()
        rig = self.rig()
        if rig is None:
            return then()
        home = c.content_geometry()
        self._lying = c.lounging()                       # she gets up off the panel, and lies back down after
        self._home = QPointF(home.center().x(), home.bottom())
        self._spot_at, side = self._spot(target, window, near)
        self._target = QRectF(target)
        self._side = side
        self._reach = self._aim(side, self._spot_at, self._target.center())
        fx = self.fx
        fx.rig, fx.feet, fx.pose, fx.side, fx.fh = rig, QPointF(self._home), Pose(energy=0.7), side, self.fh
        fx.trail, fx.ghosts, fx.bursts, fx.zap = [], [], [(time.monotonic(), QPointF(self._home))], None
        pad = self.fh
        box = QRectF(self._home, self._spot_at).normalized().united(self._target)
        box = box.adjusted(-pad, -self.fh - pad * 0.6, pad, 60).toAlignedRect()
        # one window per monitor the dash crosses (hers first)
        pieces = [box.intersected(s.geometry()) for s in sorted(QGuiApplication.screens(), key=lambda s: s is not c.screen)]
        pieces = [r for r in pieces if not r.isEmpty()] or [box.intersected(c.screen.geometry())]
        while len(self.mirrors) < len(pieces) - 1:
            self.mirrors.append(_Mirror(fx))
        for window, piece in zip([fx] + self.mirrors, pieces):
            window.setGeometry(piece)
            window.show()
            window.raise_()
        c.busy_elsewhere = True
        c.character.hide()
        if not self._lying:                              # lying: the panel stays, she stands up on it
            c.panel.hide()
        self.active, self._then, self._start = True, then, time.monotonic()
        self._timer.start()

    def _tick(self) -> None:
        fx, now = self.fx, time.monotonic()
        t = now - self._start
        hair = dict(energy=0.9 + 0.1 * math.sin(now * 23), t=now * 2.2)
        legs = [(WINDUP, "windup"), (DASH, "there"), (LAND, "land"), (RAISE, "raise"), (ZAP, "zap"), (HOLD, "hold"),
                (LOWER, "lower"), (DASH, "home"), (TRAIL, "fade")]
        for length, leg in legs:
            if t <= length:
                self._step(leg, t / length, now, hair)
                break
            t -= length
        else:
            return self._finish()
        fx.update()
        for m in self.mirrors:
            if m.isVisible():
                m.update()

    def _step(self, leg: str, k: float, now: float, hair: dict) -> None:
        fx = self.fx
        if leg == "windup":
            fx.pose = Pose(squat=0.5 * ease(k), sweep=0.3 * ease(k), **hair)
        elif leg in ("there", "home"):
            a, b = (self._home, self._spot_at) if leg == "there" else (self._spot_at, self._home)
            e = ease(k)
            fx.feet = QPointF(a.x() + (b.x() - a.x()) * e, a.y() + (b.y() - a.y()) * e - math.sin(math.pi * e) * 70)
            heading = 1 if b.x() >= a.x() else -1
            fx.side = "right" if heading > 0 else "left"
            fx.pose = Pose(lean=0.2 * heading * math.sin(math.pi * e), sweep=math.sin(math.pi * min(1.0, k * 1.4)),
                           eyes="happy" if leg == "home" else "", **hair)               # pleased on the way back
            fx.trail.append((now, QPointF(fx.feet)))
            if not fx.ghosts or now - fx.ghosts[-1][0] > 0.045:
                fx.ghost(now)
            if k < 0.06 or k > 0.97:
                fx.bursts.append((now, QPointF(fx.feet)))
        elif leg == "land":
            fx.feet, fx.side = QPointF(self._spot_at), self._side
            fx.pose = Pose(squat=0.4 * math.sin(math.pi * k), blink=math.sin(math.pi * k) * 0.9, **hair)   # lands, blinks
        elif leg == "raise":
            fx.pose = Pose(reach=self._reach * ease(k), **hair)
        elif leg == "zap":
            fx.pose = Pose(reach=self._reach, poke=0.3 * math.sin(math.pi * min(1.0, k * 3)),
                           eyes="wink" if 0.15 < k < 0.6 else "", **hair)              # a wink as she pokes it
            if fx.zap is None:
                hand = self._rig.hand_tip(fx.feet, self.fh, fx.pose, self._side)
                fx.zap = (now, hand, self._target)
            if k * ZAP >= IMPACT and self._then is not None:
                then, self._then = self._then, None
                try:
                    then()                                           # the real action
                except Exception:
                    log.exception("visit action failed")
        elif leg == "hold":
            fx.pose = Pose(reach=self._reach, eyes="happy", **hair)
        elif leg == "lower":
            fx.pose = Pose(reach=self._reach * (1 - ease(k)), **hair)
        elif leg == "fade":
            fx.feet = None
            if not self.companion.character.isVisible():
                self.companion.busy_elsewhere = False
                self.companion.show()

    def _finish(self) -> None:
        self._timer.stop()
        if self._then is not None:                # never leave a command undone
            then, self._then = self._then, None
            then()
        self.fx.hide()
        for m in self.mirrors:
            m.hide()
        self.fx.rig, self.fx.ghosts = None, []
        self.active = False
        self.companion.busy_elsewhere = False
        self.companion.show()
