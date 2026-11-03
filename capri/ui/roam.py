"""Roaming: now and then, while nothing's going on, she goes for a little walk along the bottom of her
screen and stands somewhere else for a while. Her legs step one at a time, her arms swing, her hair
bounces with the steps.

Only while she's idle: not listening, thinking or talking, not in drone mode, not sitting on a window or
lying on her panel, not hidden. Anything that needs her (you say "Hey Capri", a reply...) stops the walk
where she is. Settings -> PC & chat -> "Roam around"; "go for a walk" / "stay there" by voice.
"""

from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QTimer
from PySide6.QtGui import QPainter

from ..states import State
from .overlay_window import OverlayWindow
from .rig import Pose, Rig

if TYPE_CHECKING:
    from .companion import Companion

SPEED = 0.42              # her heights per second
STEP = 0.36               # one step, in her heights
EASE = 0.35               # seconds to get going / to stop
WAIT = (45.0, 140.0)      # seconds between walks
DISTANCE = (0.12, 0.45)   # how far she goes, as a share of the screen's width
BUSY = {State.LISTENING, State.PROCESSING, State.LAUNCHING, State.SPEAKING}   # she's needed: no walking


class WalkFX(OverlayWindow):
    """A see-through strip along the bottom of her screen, with her walking on it."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.rig: Rig | None = None
        self.fh = 250.0
        self.feet = QPointF()
        self.pose = Pose()

    def paintEvent(self, event) -> None:
        if self.rig is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.rig.paint(p, self.feet - QPointF(self.geometry().topLeft()), self.fh, self.pose, "right")
        p.end()


class RoamShow(QObject):
    def __init__(self, companion: "Companion", rig: Callable[[], Rig | None], enabled: Callable[[], bool],
                 idle: Callable[[], bool] = lambda: True, rng: random.Random | None = None) -> None:
        super().__init__()
        self.companion, self.rig, self.enabled, self.idle = companion, rig, enabled, idle
        self.rng = rng or random.Random()
        self.fx = WalkFX()
        self.active = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._clock = QTimer(self)                  # when the next walk is due
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._maybe_walk)
        self._due = time.monotonic() + self.rng.uniform(*WAIT)
        self._from = self._to = 0.0
        self._ground = 0.0
        self._phase = 0.0
        self._started = 0.0
        self._length = 0.0
        self._panel = False

    def start(self) -> None:
        self._clock.start()

    # -- when ------------------------------------------------------------------------------------------------
    def can_walk(self) -> bool:
        c = self.companion
        return (not self.active and not c.hidden and not c.drone and not c.perched and not c.lounging()
                and not c.busy_elsewhere and c.character.isVisible() and c.controller.state not in BUSY
                and self.idle())

    def _maybe_walk(self) -> None:
        if time.monotonic() < self._due or not self.enabled():
            return
        self._due = time.monotonic() + self.rng.uniform(*WAIT)
        if self.can_walk():
            self.walk()

    # -- walking ---------------------------------------------------------------------------------------------
    def walk(self, to_x: float | None = None) -> bool:
        """Walk to `to_x` (screen x of her feet), or somewhere else along the bottom. False if she can't now."""
        c = self.companion
        if not self.can_walk():
            return False
        rig = self.rig()
        if rig is None or not getattr(rig, "legs", None):
            return False
        body = c.content_geometry()
        area = c.screen.availableGeometry()
        fh = float(c.character.figure_height())
        margin = fh * 0.2
        here = float(body.center().x())
        if to_x is None:
            far = self.rng.uniform(*DISTANCE) * area.width()
            room_left, room_right = here - area.left() - margin, area.right() - margin - here
            direction = -1 if room_left > room_right and self.rng.random() < 0.7 or room_right < far else 1
            to_x = here + direction * far
        to_x = max(area.left() + margin, min(float(to_x), area.right() + 1 - margin))
        if abs(to_x - here) < fh * 0.3:
            return False
        self._from, self._to, self._ground = here, to_x, float(body.bottom() + 1)
        self._length = abs(to_x - here) / (SPEED * fh) + EASE
        self._phase, self._started = 0.0, time.monotonic()
        fx = self.fx
        fx.rig, fx.fh, fx.feet = rig, fh, QPointF(here, self._ground)
        fx.pose = Pose(t=time.monotonic() * 2.2)
        fx.setGeometry(QRect(area.left(), round(self._ground - fh * 1.45), area.width(), round(fh * 1.45) + 4))
        fx.show()
        fx.raise_()
        self._panel = c.panel.isVisible()
        c.busy_elsewhere = True
        c.character.hide()
        c.panel.hide()
        self.active = True
        self._last = time.monotonic()
        self._timer.start()
        return True

    def stop(self) -> None:
        """Something needs her: she stops right where she is."""
        if self.active:
            self._finish(self.fx.feet.x())

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(0.05, now - self._last), now
        t = now - self._started
        fx = self.fx
        if t >= self._length or self.companion.controller.state in BUSY:
            return self._finish(fx.feet.x() if t < self._length else self._to)
        # speed eases in and out; the distance covered follows the eased speed
        k = t / self._length
        ease = 0.5 - 0.5 * math.cos(math.pi * k)
        x = self._from + (self._to - self._from) * ease
        speed = abs(x - fx.feet.x()) / max(dt, 1e-3)
        self._phase += speed * dt / (STEP * fx.fh) * math.pi
        stride = math.sin(self._phase) * min(1.0, speed / (SPEED * fx.fh * 0.6))
        heading = 1 if self._to > self._from else -1
        bob = -abs(math.sin(self._phase)) * fx.fh * 0.012
        fx.feet = QPointF(x, self._ground + bob)
        fx.pose = Pose(stride=stride or 1e-4, lean=0.05 * heading * min(1.0, speed / (SPEED * fx.fh)),
                       energy=0.35 + 0.25 * abs(stride), t=now * 2.2)
        fx.update()

    def _finish(self, x: float) -> None:
        self._timer.stop()
        c, fx = self.companion, self.fx
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
        fx.hide()
        fx.rig = None
        self.active = False
