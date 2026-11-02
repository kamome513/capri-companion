"""Little things Capri does on her own while you leave her alone (standing or lying down).

Every minute or so, while she's idle and nobody is talking to her, she picks one:

* glitch    - her chrome hiccups: red / cyan split, torn slices, a jolt.
* gaming    - a holo handheld floats in front of her: a tiny pixel runner, the score
              ticking up, a "HIGH SCORE!" and a little cheer at the end.
* watching  - a holo screen beside her plays some night-city show; its light flickers
              over her as the scenes change.
* call      - she's on a video call with D over her implant: her ear glows, a holo card
              shows him (assets/d/d.png), a running timer and voice bars as they take turns.

Purely visual - nothing on your PC is touched. The moment you talk to her (or she has
anything else to do) the activity stops. Costs nothing between activities; ~30 fps of a
small window while one plays. Settings -> Character -> "Idle activities" turns them off.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QTransform

from . import theme
from .contact import Puppet

ACTS = ("glitch", "gaming", "watching", "call")
WEIGHTS = (2, 3, 3, 3)
LENGTH = {"glitch": (3.0, 4.5), "gaming": (11.0, 16.0), "watching": (12.0, 18.0), "call": (12.0, 18.0)}
FIRST = (40.0, 80.0)          # first one this long after she settles
GAP = (35.0, 80.0)            # between activities
FPS = 30                      # smooth while an activity plays (they run ~15 s every minute or two)
RED = QColor(236, 16, 70)
CYAN = QColor(0, 226, 255)
HOLO = QColor(0, 226, 255, 200)
D_BLUE = QColor(60, 115, 235)                 # D's jacket
HEAD_REF = 51.0               # prop sizes are designed for her head this tall (her normal size)


@dataclass
class Ctx:
    """Where she is in the window this frame."""
    image: QImage | None          # a window-sized picture of her, drawn at (0, 0) - the glitch tears it up
    body: QRectF                  # her figure
    head: QRectF                  # her head (with her sheet hair)
    win_w: float
    win_h: float
    lying: bool = False           # lying on the panel: head on the left, body along the panel
    face_at: QPointF | None = None  # her eyes, when they aren't in the middle of `head`

    @property
    def s(self) -> float:
        return self.head.height() / HEAD_REF

    @property
    def face(self) -> QPointF:
        if self.face_at is not None:
            return self.face_at
        return QPointF(self.head.center().x() + self.head.width() * 0.08, self.head.top() + self.head.height() * 0.55)


class IdleActs:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.enabled = True
        self.act: str | None = None
        self.start = self.end = 0.0
        self.next_at: float | None = None
        self._turns: list[tuple[float, str]] = []       # call: (until, who)
        self._scenes: list[tuple[float, int]] = []      # watching: (until, palette)
        self._bursts: list[tuple[float, float]] = []    # glitch: (from, to)
        self._seed = 0
        self._tints: dict[tuple, QImage] = {}
        self.contact: QImage | None = None              # D's picture (assets/d/d.png) for the video call
        self._puppet: Puppet | None = None
        self._font = QFont(theme.MONO_FAMILIES[0])
        self._font.setFamilies(theme.MONO_FAMILIES)
        self._font.setBold(True)

    # -- scheduling ---------------------------------------------------------------------------
    def update(self, now: float, eligible: bool) -> bool:
        """Start / stop activities. Returns True when the activity changed."""
        if not (eligible and self.enabled):
            if self.act is not None:
                self.stop(now)
                return True
            if self.next_at is not None and self.next_at < now + GAP[0] / 2:
                self.next_at = now + GAP[0] / 2          # don't start right after she was busy
            return False
        if self.next_at is None:
            self.next_at = now + self.rng.uniform(*FIRST)
        if self.act is not None and now >= self.end:
            self.stop(now)
            return True
        if self.act is None and now >= self.next_at:
            self.begin(self.rng.choices(ACTS, WEIGHTS)[0], now)
            return True
        return False

    def begin(self, name: str, now: float, length: float | None = None) -> None:
        rng = self.rng
        self.act, self.start = name, now
        self.end = now + (length if length is not None else rng.uniform(*LENGTH[name]))
        self._seed = rng.randrange(1 << 30)
        if name == "call":
            t, who = now + 0.8, "d"
            self._turns = []
            while t < self.end:
                t += rng.uniform(1.6, 3.2) if who == "d" else rng.uniform(1.0, 2.4)
                self._turns.append((t, who))
                who = "capri" if who == "d" else "d"
        elif name == "watching":
            t, self._scenes = now, []
            while t < self.end:
                t += rng.uniform(2.5, 5.0)
                self._scenes.append((t, rng.randrange(len(SCENES))))
        elif name == "glitch":
            t, self._bursts = now + 0.2, []
            while t < self.end - 0.3:
                d = rng.uniform(0.18, 0.55)
                self._bursts.append((t, t + d))
                t += d + rng.uniform(0.4, 1.2)

    def stop(self, now: float) -> None:
        self.act = None
        self.next_at = now + self.rng.uniform(*GAP)

    # -- what the window asks ---------------------------------------------------------------------
    def frame_key(self, now: float):
        if self.act is None:
            return None
        return self.act, int((now - self.start) * FPS)

    def pose(self, now: float) -> str | None:
        """The body frame to show (None = whatever she'd show anyway)."""
        if self.act == "call":
            return "look_around"                         # her hand up at her ear
        if self.act == "gaming" and self.end - now < 1.3:
            return "happy"                               # the high score cheer
        return None

    def mouth(self, now: float) -> float:
        """Her mouth while it's her turn to talk on the call (0 = closed)."""
        if self.talking(now) != "capri":
            return 0.0
        return self._voice(now, 1)

    def offset(self, now: float) -> QPointF:
        """A jolt during glitch bursts."""
        if self.act == "glitch" and self._bursting(now):
            r = random.Random(int(now * 40))
            return QPointF(r.uniform(-4, 4), r.uniform(-1.5, 1.5))
        return QPointF()

    def talking(self, now: float) -> str | None:
        """Who's talking on the call right now ('d' / 'capri'), None if not on a call or ringing."""
        if self.act != "call" or now - self.start < 0.8:
            return None
        for until, who in self._turns:
            if now < until:
                return who
        return None

    def _bursting(self, now: float) -> bool:
        return any(a <= now < b for a, b in self._bursts)

    # -- painting ----------------------------------------------------------------------------------
    def paint(self, p: QPainter, c: Ctx, now: float) -> None:
        """Called after she's painted (sprite + hair), in window coordinates."""
        if self.act is None:
            return
        t = now - self.start
        fade = min(1.0, t / 0.35, max(0.0, self.end - now) / 0.35)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        {"glitch": self._glitch, "gaming": self._gaming, "watching": self._watching,
         "call": self._call}[self.act](p, c, now, t, fade)
        p.restore()

    def _light(self, p: QPainter, c: Ctx, color: QColor, at: QPointF, radius: float, alpha: int) -> None:
        """Light from a screen falling on her (only where she's painted)."""
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        g = QRadialGradient(at, radius)
        g.setColorAt(0, QColor(color.red(), color.green(), color.blue(), alpha))
        g.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        p.fillRect(QRectF(0, 0, c.win_w, c.win_h), g)
        p.restore()

    def _holo_frame(self, p: QPainter, r: QRectF, color: QColor, fade: float, s: float) -> None:
        glow = QColor(color)
        glow.setAlpha(int(70 * fade))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(glow, 4 * s))
        p.drawRect(r)
        line = QColor(color)
        line.setAlpha(int(230 * fade))
        p.setPen(QPen(line, max(1.0, 1.3 * s)))
        p.drawRect(r)
        k = 7 * s
        p.setPen(QPen(line, max(1.5, 2.2 * s)))
        for x, y, dx, dy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                             (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawPolyline([QPointF(x, y + dy * k), QPointF(x, y), QPointF(x + dx * k, y)])

    def _scanlines(self, p: QPainter, r: QRectF, t: float, s: float) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        step = max(2.0, 3 * s)
        y = r.top() + (t * 20) % step
        while y < r.bottom():
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            y += step

    def _text(self, p: QPainter, at: QPointF, text: str, color: QColor, px: float) -> None:
        self._font.setPixelSize(max(6, round(px)))
        p.setFont(self._font)
        p.setPen(color)
        p.drawText(at, text)

    # glitch -------------------------------------------------------------------------------------------
    def _tint(self, image: QImage, color: QColor) -> QImage:
        key = (image.cacheKey(), color.rgba())
        if key not in self._tints:
            if len(self._tints) > 8:
                self._tints.clear()
            out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
            out.setDevicePixelRatio(image.devicePixelRatio())
            out.fill(0)
            q = QPainter(out)
            q.drawImage(0, 0, image)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            q.fillRect(out.rect(), color)
            q.end()
            self._tints[key] = out
        return self._tints[key]

    def _glitch(self, p: QPainter, c: Ctx, now: float, t: float, fade: float) -> None:
        if not self._bursting(now) or c.image is None:
            return
        r = random.Random(int(now * 30))
        img, dpr, b = c.image, c.image.devicePixelRatio(), c.body
        split = r.uniform(5, 13) * c.s
        red_at, cyan_at = QPointF(-split, 0), QPointF(split, r.uniform(-1.5, 1.5))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOver)   # fringes behind her
        p.setOpacity(0.9)
        p.drawImage(red_at, self._tint(img, RED))
        p.drawImage(cyan_at, self._tint(img, CYAN))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)        # and ghosts over her
        p.setOpacity(0.3)
        p.drawImage(red_at, self._tint(img, RED))
        p.drawImage(cyan_at, self._tint(img, CYAN))
        p.setOpacity(1.0)
        top = max(0.0, b.top() - c.head.height() * 0.4)                 # her hair too
        for _ in range(r.randint(2, 4)):                       # torn slices
            band_y, band_h = r.uniform(top, b.bottom() - 4), r.uniform(2, 12) * c.s
            dx = r.choice((-1, 1)) * r.uniform(4, 14) * c.s
            p.drawImage(QRectF(dx, band_y, c.win_w, band_h), img,
                        QRectF(0, band_y * dpr, img.width(), band_h * dpr))
        for color in (RED, CYAN, QColor(255, 255, 255)):       # stray scan lines across her
            color = QColor(color)
            color.setAlpha(170)
            p.setPen(QPen(color, 1))
            y = r.uniform(top, b.bottom())
            p.drawLine(QPointF(b.left() - 14 * c.s, y), QPointF(b.right() + 14 * c.s, y))
        if r.random() < 0.4:                                   # an error tag pops up
            self._text(p, QPointF(b.left() + b.width() * r.uniform(0.0, 0.4), b.top() + b.height() * r.uniform(0.3, 0.8)),
                       r.choice(["ERR", "0xC4PR1", "SYNC LOST", "//NULL"]), QColor(255, 60, 110), 9 * c.s)

    # gaming -------------------------------------------------------------------------------------------
    def _gaming(self, p: QPainter, c: Ctx, now: float, t: float, fade: float) -> None:
        s = c.s
        w, h = 66 * s, 40 * s
        head, bob = c.head, 1.5 * s * math.sin(t * 2.4)
        if c.lying:                                            # in front of her face, below her chin
            cx = max(w / 2 + 14 * s, c.face.x() - 6 * s)
            r = QRectF(cx - w / 2, min(c.face.y() + 8 * s, c.win_h - h - 2) + bob, w, h)
        else:                                                  # held in front of her chest
            cx = c.body.center().x()
            r = QRectF(cx - w / 2, c.body.top() + c.body.height() * 0.33 + bob, w, h)
        eyes = c.face
        green = QColor(60, 255, 150)
        self._light(p, c, green, QPointF(cx, r.top()), head.height() * 2.6, int(55 * fade))
        # the beam from the screen up to her eyes
        beam = QPainterPath(QPointF(r.left() + w * 0.2, r.top()))
        beam.lineTo(QPointF(eyes.x() - 6 * s, eyes.y()))
        beam.lineTo(QPointF(eyes.x() + 8 * s, eyes.y()))
        beam.lineTo(QPointF(r.right() - w * 0.2, r.top()))
        beam.closeSubpath()
        g = QLinearGradient(QPointF(cx, r.top()), eyes)
        g.setColorAt(0, QColor(60, 255, 150, int(60 * fade)))
        g.setColorAt(1, QColor(60, 255, 150, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(beam)
        # the console body: a holo outline round the screen, with buttons
        body = r.adjusted(-12 * s, -4 * s, 12 * s, 4 * s)
        p.setBrush(QColor(8, 20, 28, int(150 * fade)))
        p.setPen(QPen(QColor(0, 226, 255, int(200 * fade)), max(1.0, 1.4 * s)))
        p.drawRoundedRect(body, 9 * s, 9 * s)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(236, 16, 70, int(220 * fade)))
        p.drawEllipse(QPointF(body.right() - 6 * s, body.center().y() - 3 * s), 2.2 * s, 2.2 * s)
        p.drawEllipse(QPointF(body.right() - 6 * s, body.center().y() + 4 * s), 2.2 * s, 2.2 * s)
        p.setBrush(QColor(0, 226, 255, int(200 * fade)))
        p.drawRect(QRectF(body.left() + 3.5 * s, body.center().y() - 1 * s, 5 * s, 2 * s))
        p.drawRect(QRectF(body.left() + 5 * s, body.center().y() - 2.5 * s, 2 * s, 5 * s))
        # the game: a pixel runner hopping over blocks
        p.save()
        p.setClipRect(r)
        p.setOpacity(fade)
        p.fillRect(r, QColor(4, 18, 12, 225))
        u = 3 * s                                              # one game pixel
        ground = r.bottom() - 6 * s
        p.fillRect(QRectF(r.left(), ground, w, 1.2 * s), green)
        speed = 26 * s
        scroll = t * speed
        rng = random.Random(self._seed)
        x, blocks = 50 * s, []
        while x < scroll + w * 2:
            x += rng.uniform(26, 48) * s
            blocks.append((x, rng.choice((1, 2))))
        px = r.left() + w * 0.25
        jump = 0.0
        for bx, bh in blocks:
            d = (r.left() + bx - scroll) - px
            if -4 * u < d < 4 * u:
                jump = max(jump, math.cos(math.pi / 2 * d / (4 * u)) * (bh + 2.5) * u)
            sx = r.left() + bx - scroll
            if r.left() - u < sx < r.right():
                p.fillRect(QRectF(sx, ground - bh * u, u, bh * u), RED)
        p.fillRect(QRectF(px - u, ground - 2 * u - jump, 2 * u, 2 * u), QColor(255, 255, 255))
        p.fillRect(QRectF(px - u + 1.2 * u, ground - 1.6 * u - jump, 0.5 * u, 0.5 * u), RED)   # her eye
        if s >= 0.7:
            self._text(p, QPointF(r.right() - 24 * s, r.top() + 8 * s), f"{int(t * 37):05d}", green, 6.5 * s)
            if self.end - now < 1.6 and int(t * 6) % 2 == 0:
                self._text(p, QPointF(r.left() + 6 * s, r.top() + 18 * s), "HIGH SCORE!", QColor(255, 220, 60), 8.5 * s)
        self._scanlines(p, r, t, s)
        p.restore()
        self._holo_frame(p, r, CYAN, fade, s * 0.7)

    # watching -----------------------------------------------------------------------------------------
    def _scene(self, now: float) -> int:
        for until, scene in self._scenes:
            if now < until:
                return scene
        return self._scenes[-1][1] if self._scenes else 0

    def _watching(self, p: QPainter, c: Ctx, now: float, t: float, fade: float) -> None:
        s = c.s
        w, h = 78 * s, 50 * s
        head, bob = c.head, 2 * s * math.sin(t * 1.7)
        if c.lying:                                            # floating over her back, facing her
            left, lean = min(head.right() + 6 * s, c.win_w - w - 2), -0.14
            top = max(2.0, c.body.top() + c.body.height() * 0.3 - h) + bob
        elif c.win_w - head.right() >= w * 0.7:                # beside her head, angled at her
            left, lean = min(head.right() - 2 * s, c.win_w - w - 2), 0.14
            top = head.top() + head.height() * 0.1 + bob
        else:
            left, lean = max(2.0, head.left() - w + 2 * s), -0.14
            top = head.top() + head.height() * 0.1 + bob
        r = QRectF(0, 0, w, h)
        scene = SCENES[self._scene(now)]
        flicker = 0.75 + 0.25 * random.Random(int(now * 8)).random()
        accent = scene[2]
        self._light(p, c, accent, QPointF(left + (0 if lean > 0 else w), top + h / 2), head.height() * 3.2,
                    int(70 * fade * flicker))
        p.save()
        p.translate(left, top)
        p.setTransform(QTransform().shear(0, lean), True)      # turned a little towards her
        p.setOpacity(fade)
        p.save()
        p.setClipRect(r)
        sky = QLinearGradient(QPointF(0, 0), QPointF(0, h))
        sky.setColorAt(0, scene[0])
        sky.setColorAt(1, scene[1])
        p.fillRect(r, sky)
        rng = random.Random(self._seed + self._scene(now) * 7919)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 240, 230, 200))
        p.drawEllipse(QPointF(w * rng.uniform(0.6, 0.85), h * 0.25), 5 * s, 5 * s)       # the moon
        drift = (t * 6 * s) % (w * 0.5)
        for layer, (shade, speed) in enumerate(((QColor(20, 10, 30), 0.5), (QColor(8, 4, 12), 1.0))):
            x = -drift * speed
            while x < w:
                bw, bh = rng.uniform(7, 15) * s, rng.uniform(0.3, 0.75 - 0.2 * layer) * h
                p.fillRect(QRectF(x, h - bh, bw - 1, bh), shade)
                if layer == 1:
                    for wy in range(int(h - bh + 3 * s), int(h - 2 * s), max(2, int(4 * s))):
                        if rng.random() < 0.35:
                            p.fillRect(QRectF(x + rng.uniform(1, bw - 3), wy, 1.4 * s, 1.4 * s), accent)
                x += bw
        if scene[3] and int(t * 10) % 3 == 0:                  # action scene: speed lines
            p.setPen(QPen(QColor(255, 255, 255, 120), 1))
            for _ in range(6):
                y = rng.uniform(0, h)
                p.drawLine(QPointF(rng.uniform(0, w * 0.4), y), QPointF(w, y))
        self._scanlines(p, r, t, s)
        progress = (t / max(1.0, self.end - self.start))
        p.fillRect(QRectF(3 * s, h - 3 * s, (w - 6 * s), 1.2 * s), QColor(255, 255, 255, 60))
        p.fillRect(QRectF(3 * s, h - 3 * s, (w - 6 * s) * progress, 1.2 * s), RED)
        if s >= 0.7:
            self._text(p, QPointF(3 * s, 8 * s), "▶ BD", QColor(255, 255, 255, 200), 6.5 * s)
        p.restore()
        self._holo_frame(p, r, CYAN, fade, s * 0.8)
        p.restore()

    # call with D ---------------------------------------------------------------------------------------
    @staticmethod
    def _voice(now: float, who: int) -> float:
        """How loud D (0) / Capri (1) is right now on the call: syllables with little pauses."""
        syllables = abs(math.sin(now * (11.0 if who == 0 else 13.0)))
        phrase = 0.5 + 0.5 * math.sin(now * (2.3 if who == 0 else 2.9))
        return max(0.0, min(1.0, syllables * (0.35 + 0.65 * phrase) * 1.3 - 0.1))

    def _avatar(self, p: QPainter, v: QRectF) -> None:
        """No picture of D: a simple one - dark teal hair, blue jacket."""
        a, rad = v.center(), min(v.width(), v.height()) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(D_BLUE)
        p.drawEllipse(QPointF(a.x(), a.y() + rad * 1.0), rad * 0.95, rad * 0.6)          # jacket
        p.setBrush(QColor(225, 190, 170))
        p.drawEllipse(QPointF(a.x(), a.y() - rad * 0.1), rad * 0.36, rad * 0.46)         # face
        hair = QPainterPath(QPointF(a.x() - rad * 0.5, a.y() + rad * 0.1))
        for dx, dy in ((-0.6, -0.6), (-0.3, -0.75), (0.0, -0.85), (0.35, -0.75), (0.6, -0.55), (0.45, 0.0),
                       (0.3, -0.35), (-0.3, -0.35)):
            hair.lineTo(QPointF(a.x() + dx * rad, a.y() + dy * rad))
        hair.closeSubpath()
        p.setBrush(QColor(20, 52, 62))
        p.drawPath(hair)

    def _call(self, p: QPainter, c: Ctx, now: float, t: float, fade: float) -> None:
        s = c.s
        w, h = 72 * s, 100 * s
        head, bob = c.head, 1.5 * s * math.sin(t * 1.9)
        if c.lying:                                            # above her, past her head
            left = min(head.right() + 4 * s, c.win_w - w - 2)
            top = max(2.0, c.body.top() + c.body.height() * 0.3 - h) + bob
        else:                                                  # beside her head
            left = max(2.0, head.left() - w + 4 * s)
            top = max(2.0, head.top() - 4 * s) + bob
        r = QRectF(left, top, w, h)
        ringing = t < 0.8
        who = self.talking(now)
        # the card
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, QColor(10, 14, 30, int(225 * fade)))
        bg.setColorAt(1, QColor(6, 6, 12, int(235 * fade)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRect(r)
        # the video: D, as a hologram
        v = QRectF(r.left() + 3 * s, r.top() + 3 * s, w - 6 * s, w - 6 * s)
        p.save()
        p.setClipRect(v)
        p.setOpacity(fade)
        g = QLinearGradient(v.topLeft(), v.bottomLeft())
        g.setColorAt(0, QColor(18, 30, 64))
        g.setColorAt(1, QColor(8, 10, 24))
        p.fillRect(v, g)
        voice = self._voice(now, 0) if who == "d" else 0.0
        if ringing:
            p.setOpacity(fade * (0.35 + 0.3 * abs(math.sin(t * 10))))
        if self.contact is not None and not self.contact.isNull():
            if self._puppet is None or self._puppet.image is not self.contact:
                self._puppet = Puppet(self.contact)
            dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
            self._puppet.paint(p, v, now, voice, who == "d", dpr)        # D, talking / listening / blinking
        else:
            self._avatar(p, v.translated(0, 1.2 * s * voice))
        p.setOpacity(fade)
        jitter = random.Random(int(now * 6))
        if jitter.random() < 0.15:                             # a holo-feed hiccup
            band = QRectF(v.left(), v.top() + jitter.uniform(0, v.height() - 6 * s), v.width(), jitter.uniform(2, 6) * s)
            p.fillRect(band.translated(jitter.uniform(-4, 4) * s, 0), QColor(0, 226, 255, 70))
        self._scanlines(p, v, t, s)
        p.restore()
        if s >= 0.7:
            if ringing:
                self._text(p, QPointF(v.left() + 4 * s, v.bottom() - 5 * s), "INCOMING", CYAN, 7 * s)
            else:
                self._text(p, QPointF(v.left() + 3 * s, v.top() + 8 * s), "● LIVE", QColor(255, 60, 100), 5.5 * s)
        p.setPen(Qt.PenStyle.NoPen)                            # the hang-up dot
        p.setBrush(QColor(236, 16, 70, int(230 * fade)))
        p.drawEllipse(QPointF(v.right() - 5 * s, v.top() + 5 * s), 2.6 * s, 2.6 * s)
        # name, timer, voice bars
        tx = r.left() + 4 * s
        if s >= 0.7:
            self._text(p, QPointF(tx, v.bottom() + 9 * s), "D", QColor(255, 255, 255), 8.5 * s)
            status = "CALLING" if ringing else f"{int(t) // 60:02d}:{int(t) % 60:02d}"
            self._text(p, QPointF(tx + 10 * s, v.bottom() + 9 * s), status, QColor(150, 155, 175), 6 * s)
        for row, (name, color) in enumerate((("d", D_BLUE), ("capri", RED))):
            y = v.bottom() + (15 + 6 * row) * s
            for i in range(14):
                level = 0.15
                if who == name:
                    level = 0.25 + 0.75 * abs(math.sin(now * (9 + i * 1.3) + i * 2.1 + row)) * self._voice(now, row)
                bh = max(1.0, 4.5 * s * level)
                col = QColor(color)
                col.setAlpha(int((235 if who == name else 80) * fade))
                p.fillRect(QRectF(tx + i * 4.6 * s, y - bh / 2, 2.4 * s, bh), col)
        blink = 0.4 + 0.6 * abs(math.sin(t * 12)) if ringing else 1.0       # the card flashes while it rings
        self._holo_frame(p, r, CYAN if ringing else (D_BLUE if who == "d" else RED), fade * blink, s * 0.7)
        # her implant glows at her ear; his voice comes out of it
        ear = c.face + QPointF(head.width() * (0.32 if c.lying else 0.22), head.height() * (-0.05 if c.lying else 0.07))
        glow = QRadialGradient(ear, 7 * s)
        glow.setColorAt(0, QColor(90, 150, 255, int((210 if who == "d" else 110) * fade)))
        glow.setColorAt(1, QColor(90, 150, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(ear, 7 * s, 7 * s)
        if who == "d":
            for k in range(3):
                phase = (now * 1.8 + k / 3) % 1.0
                rr = (4 + 10 * phase) * s
                p.setPen(QPen(QColor(110, 165, 255, int(200 * (1 - phase) * fade)), max(1.0, 1.3 * s)))
                p.drawArc(QRectF(ear.x() - rr, ear.y() - rr, 2 * rr, 2 * rr), -50 * 16, 100 * 16)


# (sky top, sky bottom, light colour, action?)
SCENES = [
    (QColor(40, 10, 60), QColor(160, 30, 110), QColor(255, 60, 160), False),     # neon night
    (QColor(80, 0, 10), QColor(240, 40, 30), QColor(255, 60, 40), True),         # a firefight
    (QColor(0, 30, 60), QColor(0, 140, 170), QColor(0, 220, 255), False),        # rain over the bay
    (QColor(60, 20, 0), QColor(250, 150, 40), QColor(255, 180, 60), False),      # sunset
    (QColor(10, 40, 20), QColor(30, 200, 110), QColor(60, 255, 150), True),      # netrun
]
