"""Her big hello when you sign in: Capri large in the middle of the screen with a
neon caption, talking (lip-synced), then she shrinks back into her corner.

Every window here is click-through and never takes focus, so it can't get in
the way of whatever you open first. It's a few seconds of animation, then all
three windows are hidden again (no cost when idle).
"""

from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPainterPath, QPen, QPixmap

from ..states import State
from . import theme
from .character_window import CharacterWindow
from .rig import Pose, Rig
from .overlay_window import OverlayWindow
from .static_fx import StaticFX

if TYPE_CHECKING:
    from .companion import Companion

HEIGHT_SHARE = 0.56       # her height, as a share of the screen's height
ENTER_MS = 650
EXIT_MS = 760
MIN_SECONDS = 3.5         # stays at least this long if she isn't speaking (speech off)
MAX_SECONDS = 14.0        # and never longer than this, whatever happens
CAPTION_GAP = 18


class _Caption(OverlayWindow):
    """The greeting text in a big version of her terminal panel."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.text = ""
        self.progress = 1.0
        self.fx = StaticFX(seed=11)
        self._font = theme.sans(22)
        self._head = theme.mono(10, bold=True, spacing=2.0)
        self._timer = QTimer(self)
        self._timer.setInterval(125)
        self._timer.timeout.connect(lambda: (self.fx.step(), self.update()))

    def set_text(self, text: str, width: int) -> None:
        self.text, self.progress = text, 0.0
        fm = QFontMetrics(self._font)
        inner = width - 56
        lines = fm.boundingRect(QRect(0, 0, inner, 1000), Qt.TextFlag.TextWordWrap, text).height()
        self.resize(width, lines + 78)
        self.fx.burst()

    def set_progress(self, value: float) -> None:
        self.progress = value
        self.update()

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        c = 14
        shape = QPainterPath()
        shape.moveTo(r.left() + c, r.top())
        shape.lineTo(r.right(), r.top())
        shape.lineTo(r.right(), r.bottom() - c)
        shape.lineTo(r.right() - c, r.bottom())
        shape.lineTo(r.left(), r.bottom())
        shape.lineTo(r.left(), r.top() + c)
        shape.closeSubpath()
        p.setPen(QPen(theme.PANEL_GLOW, 8))
        p.drawPath(shape)
        p.fillPath(shape, theme.PANEL_BG)
        self.fx.paint(p, shape, r)
        p.setPen(QPen(theme.PANEL_BORDER, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)
        p.setFont(self._head)
        p.setPen(theme.GREEN)
        p.drawText(QRectF(r.left() + 24, r.top() + 12, r.width() - 48, 20), "CAPRI  //  ONLINE")
        shown = self.text[: max(0, round(len(self.text) * self.progress))] if self.progress < 1 else self.text
        p.setFont(self._font)
        p.setPen(theme.TEXT_TITLE)
        p.drawText(QRectF(r.left() + 24, r.top() + 38, r.width() - 48, r.height() - 46),
                   int(Qt.TextFlag.TextWordWrap), shown)
        p.end()


class _Flyer(OverlayWindow):
    """Draws a snapshot of big-Capri while it shrinks into her corner."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.pixmap = QPixmap()
        self.target = QRectF()
        self.opacity = 1.0

    def paintEvent(self, event) -> None:
        if self.pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(self.opacity)
        p.drawPixmap(self.target, self.pixmap, QRectF(self.pixmap.rect()))
        p.end()


def _ease(x: float) -> float:
    """Smooth in and out (0..1 -> 0..1)."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class RigFigure(OverlayWindow):
    """Big, sharp Capri for the greeting: her full-body figure from the character sheet (drawn
    at its own high resolution), performing - she glides in, waves properly (upper arm out,
    forearm up, the hand swinging from the elbow), smiles with her eyes, winks, blinks, talks
    with her grin opening, breathes, and at the end hops back into her corner in an arc."""

    WAVE_AT, RAISE, WAVES, LOWER = 0.35, 0.45, 1.9, 0.5        # seconds: when, and how long each part takes
    WAG_HZ = 2.1

    def __init__(self, rig: Rig, height: int, seed: int = 0) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.rig, self.figure = rig, height
        self.body_w = round(height * rig.w / rig.h)
        self.resize(round(height * 1.05), round(height * 1.22))
        self.talking, self.level, self.state, self.emotion = False, 0.0, State.SPEAKING, "happy"
        self.mouth = 0.0                                         # smoothed lip-sync
        self._rng = random.Random(seed)
        self._next_blink = 1.8
        self._blink_at = -10.0
        self._flight: dict | None = None
        self._trail: list[tuple[QPointF, float]] = []
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(16)                              # 60 fps for the few seconds it's up
        self._timer.timeout.connect(self.update)

    def content_rect(self) -> QRect:
        return QRect((self.width() - self.body_w) // 2, self.height() - 2 - self.figure, self.body_w, self.figure)

    def set_state(self, state: State, emotion: str | None = None) -> None:
        self.state, self.emotion = state, emotion or "happy"

    def set_talking(self, on: bool) -> None:
        self.talking = on
        if not on:
            self.level = 0.0

    def set_voice_level(self, level: float) -> None:
        self.level = level

    def set_viseme(self, viseme: str) -> None:
        pass

    def showEvent(self, event) -> None:
        self._t0 = time.monotonic()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    # -- the performance ---------------------------------------------------------------------------
    def pose_at(self, t: float) -> Pose:
        """Her pose `t` seconds into the greeting."""
        cheerful = self.emotion not in ("sad", "serious", "angry")
        # the wave: raise, swing from the elbow, lower
        w0 = self.WAVE_AT
        w1, w2, w3 = w0 + self.RAISE, w0 + self.RAISE + self.WAVES, w0 + self.RAISE + self.WAVES + self.LOWER
        if t < w0:
            wave = 0.0
        elif t < w1:
            wave = _ease((t - w0) / self.RAISE)
        elif t < w2:
            wave = 1.0
        else:
            wave = 1.0 - _ease((t - w2) / self.LOWER)
        swing = min(1.0, max(0.0, (t - w0) / 0.6)) * (1.0 if t < w2 else wave)
        wag = math.sin((t - w0) * 2 * math.pi * self.WAG_HZ) * swing
        # eyes: smiling while she waves, a wink if she's playful, blinks the rest of the time
        eyes = ""
        if cheerful and w0 + 0.15 < t < w2 - 0.2:
            eyes = "happy"
        if self.emotion in ("playful", "smirk") and w1 + 0.55 < t < w1 + 0.95:
            eyes = "wink"
        if t > self._next_blink:
            self._blink_at, self._next_blink = t, t + self._rng.uniform(2.4, 4.6)
        b = (t - self._blink_at) / 0.17
        blink = math.sin(math.pi * b) if 0 <= b <= 1 else 0.0
        # talking: the grin opens with her voice, smoothed so it doesn't flicker
        target = self.level if self.talking else 0.0
        self.mouth += (target - self.mouth) * (0.45 if target > self.mouth else 0.25)
        energy = 0.5 + 0.45 * self.mouth + 0.35 * max(0.0, 1 - t / 0.8)     # the hair flares as she arrives
        lean = 0.022 * math.sin(t * 1.25) + 0.035 * wave                    # a sway, leaning into the wave
        squat = 0.012 * (1 + math.sin(t * 2.1))                              # breathing
        return Pose(lean=lean, squat=squat, wave=wave, wag=wag, eyes=eyes, blink=blink,
                    mouth=self.mouth, energy=min(1.0, energy), t=t * 1.6)

    def fly_to(self, end: QRect, ms: int, done) -> None:
        """Hop back into her corner: from where she stands to `end` (her small figure, global
        coordinates), in an arc, shrinking, arms trailing - drawn live, not a frozen picture."""
        here = self.mapToGlobal(QPoint(self.width() // 2, self.height() - 2))
        area = QRect(self.geometry()).united(end).adjusted(-60, -int(self.figure * 0.35), 60, 40)
        self._flight = {"from": QPointF(here), "to": QPointF(end.center().x(), end.bottom()),
                        "h0": float(self.figure), "h1": float(max(20, end.height())), "start": time.monotonic(),
                        "ms": ms, "done": done, "origin": QPointF(area.topLeft())}
        self.setGeometry(area)

    def paintEvent(self, event) -> None:
        t = time.monotonic() - self._t0
        pose = self.pose_at(t)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._flight is not None:
            self._paint_flight(p, pose)
        else:
            arrive = _ease(t / 0.55)
            feet = QPointF(self.width() / 2, self.height() - 2 - 2.5 * self.mouth)
            if arrive < 1:                                       # gliding in: a soft glitch shimmer
                p.setOpacity(arrive)
                for k, dx in ((0, -10 * (1 - arrive)), (1, 10 * (1 - arrive))):
                    p.save()
                    p.setOpacity(0.25 * (1 - arrive))
                    self.rig.paint(p, feet + QPointF(dx, 0), self.figure, pose, "right")
                    p.restore()
                p.setOpacity(arrive)
            self.rig.paint(p, feet, self.figure, pose, "right")
        p.end()

    def _paint_flight(self, p: QPainter, pose: Pose) -> None:
        f = self._flight
        v = min(1.0, (time.monotonic() - f["start"]) * 1000 / f["ms"])
        k = _ease(v)
        start, end = f["from"] - f["origin"], f["to"] - f["origin"]
        hop = -math.sin(math.pi * k) * f["h0"] * 0.28                  # up and over, into her corner
        feet = QPointF(start.x() + (end.x() - start.x()) * k, start.y() + (end.y() - start.y()) * k + hop)
        height = f["h0"] * (f["h1"] / f["h0"]) ** k                     # shrinks evenly all the way
        pose.sweep, pose.wave, pose.squat = 0.7 * math.sin(math.pi * min(1.0, v * 1.4)), 0.0, 0.25 * max(0.0, 1 - v * 4)
        pose.lean += 0.18 * math.sin(math.pi * k) * (1 if end.x() > start.x() else -1)
        self._trail = (self._trail + [(feet, height)])[-5:]
        for i, (ghost, gh) in enumerate(self._trail[:-1]):           # a faint motion trail
            p.setOpacity(0.07 * (i + 1) * (1 - v))
            self.rig.paint(p, ghost, gh, pose, "right", hair=False)
        p.setOpacity(1.0 if v < 0.85 else max(0.0, (1 - v) / 0.15))
        self.rig.paint(p, feet, height, pose, "right")
        if v >= 1.0 and f["done"] is not None:
            done, f["done"] = f["done"], None
            QTimer.singleShot(0, done)


class GreetingShow(QObject):
    finished = Signal()

    def __init__(self, companion: Companion) -> None:
        super().__init__()
        self.companion = companion
        self.active = False
        self.big: CharacterWindow | None = None
        self.caption = _Caption()
        self.flyer = _Flyer()
        self._anim: QVariantAnimation | None = None
        self._safety = QTimer(self)
        self._safety.setSingleShot(True)
        self._safety.timeout.connect(self.finish)
        self._spoken = False
        self._rig: Rig | None = None

    # -- lip sync (forwarded while she's big) ---------------------------------------------
    def set_voice_level(self, level: float) -> None:
        if self.active and self.big is not None:
            self.big.set_voice_level(level)

    def set_talking(self, on: bool) -> None:
        if self.active and self.big is not None:
            self.big.set_talking(on)
            if on:
                self._spoken = True

    def set_viseme(self, viseme: str) -> None:
        if self.active and self.big is not None:
            self.big.set_viseme(viseme)

    def set_progress(self, value: float) -> None:
        if self.active:
            self.caption.set_progress(value)

    # -- the show --------------------------------------------------------------------------
    def _make_big(self, height: int):
        c = self.companion
        s = c.settings
        sprites = c.sprites
        if sprites is not None and "standing" in getattr(sprites, "body", {}):
            if self._rig is None:
                self._rig = Rig(sprites.frame("standing"), s.hair_style)
            self._rig.set_hair_style(s.hair_style)
            return RigFigure(self._rig, height)
        style = s.character_style if s.character_style != "portrait" else "body"   # a full-body hello
        big = CharacterWindow(c.art, height, True, c.sprites, style)
        big.set_click_through(True)
        big.set_look(s.wild_hair, s.idle_animation, s.hair_style)
        big.set_display_height(height)
        return big

    def play(self, text: str, emotion: str = "happy") -> None:
        """Show her big with `text`. Call finish() when she's done talking (it also times out)."""
        if self.active:
            return
        self.active, self._spoken = True, False
        c = self.companion
        area = c.screen.availableGeometry()
        height = int(area.height() * HEIGHT_SHARE)
        self.big = big = self._make_big(height)
        big.set_state(State.SPEAKING, emotion)
        body = big.content_rect()
        width = min(area.width() - 80, max(520, int(area.width() * 0.42)))
        self.caption.set_text(text, width)
        total = body.height() + CAPTION_GAP + self.caption.height()
        top = area.top() + max(20, (area.height() - total) // 2)
        final = QPoint(area.center().x() - body.center().x(), top - body.top())
        big.move(final + QPoint(0, 40))
        self.caption.move(area.center().x() - width // 2, top + body.height() + CAPTION_GAP)

        c.busy_elsewhere = True
        c.character.hide()        # just for the show: her "hidden" setting isn't touched
        c.panel.hide()
        for w in (big, self.caption):
            w.setWindowOpacity(0.0)
            w.show()
            w.raise_()

        def enter(v: float) -> None:
            big.move(final + QPoint(0, round(40 * (1 - v))))
            big.setWindowOpacity(v)
            self.caption.setWindowOpacity(v)

        self._animate(ENTER_MS, QEasingCurve.Type.OutCubic, enter, None)
        self._safety.start(int(MAX_SECONDS * 1000))

    def done_talking(self) -> None:
        """Speech finished (or there was none): linger a moment, then fly home."""
        if self.active:
            QTimer.singleShot(700 if self._spoken else int(MIN_SECONDS * 1000), self.finish)

    def finish(self) -> None:
        if not self.active or self.big is None or (self._anim and self._anim.property("leaving")):
            return
        self._safety.stop()
        big, c = self.big, self.companion
        big.set_talking(False)
        if isinstance(big, RigFigure):                   # she hops home herself, still moving
            c.place()
            end = c.content_geometry()
            caption = self.caption

            def fade(v: float) -> None:
                caption.setWindowOpacity(max(0.0, 1 - v * 2.2))
            self._animate(EXIT_MS, QEasingCurve.Type.Linear, fade, None, leaving=True)
            big.fly_to(end, EXIT_MS, self._cleanup)
            return
        start = QRectF(big.geometry())
        snapshot = big.grab()
        c.place()                                        # where she'll stand again
        end = QRectF(c.character.geometry())
        area = QRectF(c.screen.availableGeometry()).united(start).united(end)
        self.flyer.setGeometry(area.toAlignedRect())
        self.flyer.pixmap = snapshot
        origin = self.flyer.geometry().topLeft()
        start.translate(-origin.x(), -origin.y())
        end.translate(-origin.x(), -origin.y())
        self.flyer.target, self.flyer.opacity = start, 1.0
        self.flyer.show()
        self.flyer.raise_()
        big.hide()

        def leave(v: float) -> None:
            self.flyer.target = QRectF(start.x() + (end.x() - start.x()) * v,
                                       start.y() + (end.y() - start.y()) * v,
                                       start.width() + (end.width() - start.width()) * v,
                                       start.height() + (end.height() - start.height()) * v)
            self.flyer.opacity = 1.0 if v < 0.8 else max(0.0, (1 - v) * 5)
            self.caption.setWindowOpacity(max(0.0, 1 - v * 2.5))
            self.flyer.update()

        self._animate(EXIT_MS, QEasingCurve.Type.InOutCubic, leave, self._cleanup, leaving=True)

    def _cleanup(self) -> None:
        self.flyer.hide()
        self.flyer.pixmap = QPixmap()
        self.caption.hide()
        if self.big is not None:
            self.big.hide()
            self.big.deleteLater()
            self.big = None
        self.active = False
        self.companion.busy_elsewhere = False
        self.companion.show()                            # back as she was (respects "Hide Capri")
        self.finished.emit()

    def _animate(self, ms: int, curve: QEasingCurve.Type, step, done, leaving: bool = False) -> None:
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(ms)
        anim.setEasingCurve(curve)
        anim.setProperty("leaving", leaving)
        anim.valueChanged.connect(lambda v: step(float(v)))
        if done is not None:
            anim.finished.connect(done)
        else:
            anim.finished.connect(lambda: step(1.0))
        self._anim = anim
        anim.start()
