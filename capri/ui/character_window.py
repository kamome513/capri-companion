"""The window that shows Capri herself.

Styles (Settings -> Character):
* body     - the character sheet's full-body frames: idle / blink / look around /
             listening / thinking / speaking / happy / confused, with an idle
             animation (breathing, blinking, glancing around) and wild hair.
* portrait - a talking head in a neon card: her 8 expressions, and the 16 mouth
             shapes lip-synced to what she's saying.
* classic  - the first art (screenshots in a portrait card, or a cut-out PNG).
* lying    - "lie on the panel": the sheet's lying-down pose resting on the status panel.

While she talks she animates with her voice (all styles): the mouth follows
the syllables, she bounces slightly, loud moments throw a short glitch, and
her emotion picks the face / pose.
"""

from __future__ import annotations

import logging
import math
import random
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPaintEvent, QPen, QRadialGradient

from .. import emotions
from ..states import STATE_STYLES, State
from . import theme
from .art import CARD, CharacterArt
from .hair import HAIR_STYLES, WildHair, make_hair, tint_hair
from . import looks
from .idle_acts import FPS as ACT_FPS, Ctx, IdleActs
from .overlay_window import OverlayWindow
from .rig import Pose, Rig
from .sprites import SpriteArt

log = logging.getLogger("capri")

GLOW = 6          # room around the card for the neon glow
CHAMFER = 16      # size of the clipped card corners
MOUTH_OPEN, MOUTH_CLOSE = 0.5, 0.28   # hysteresis so the mouth doesn't flicker
GLITCH_FRAMES = 2
BODY_REF_HEIGHT = 230                 # pixel height of the sheet's idle frame (2x import)
BODY_SCALE = 1.32                     # body style: her full-body figure's height vs the display height
LYING_FACE = (0.16, 0.47)             # her eyes on the lying-down art (share of its width / height)
BODY_SIDE, BODY_TOP = 0.34, 0.28      # room around her (x figure height) for the hair storm and props
# body style: how each expression moves her full-body figure
BODY_POSES = {
    "idle": {}, "blink": {"blink": 1.0}, "look_around": {"lean": 0.035},
    "listening": {"energy": 0.45, "lean": -0.03}, "thinking": {"energy": 0.2, "squat": 0.06},
    "speaking": {"mouth": 1.0}, "happy": {"energy": 0.6, "reach": 0.35}, "confused": {"energy": 0.25, "lean": -0.06},
}
IDLE_FPS = 30                         # idle tick rate (her hair sways at this) - repaints only when something changes
TALK_FPS = 60                         # while she talks, or moves from one pose to another: smooth
SMOOTH_TAU = 0.11                     # seconds: how quickly she eases from one pose into the next
BLINK_SECONDS = 0.17
LOOK_FPS = 30                         # the animated picture styles move all the time

STATE_FRAME = {State.LISTENING: "listening", State.PROCESSING: "thinking", State.LAUNCHING: "thinking",
               State.ERROR: "confused"}


class CharacterWindow(OverlayWindow):
    def __init__(self, art: CharacterArt, height: int, always_on_top: bool = True,
                 sprites: SpriteArt | None = None, style: str = "classic") -> None:
        super().__init__(always_on_top)
        self.art = art
        self.sprites = sprites
        self.state = State.IDLE
        self.emotion = "neutral"
        self._cache: dict[tuple, QImage] = {}
        self.talking = False
        self.level = 0.0
        self.mouth_open = False
        self.viseme = ""
        self._glitch = 0
        self._rng = random.Random(7)
        self.hair_style = "storm"
        self.hair = make_hair("storm")
        self.lying_hair = make_hair("storm", flow_in=True)   # lying down: the same hair, flowing into her
        self.wild_hair = 0.7
        self.idle_animation = True
        self.lying = False
        self.lying_width = 280
        self._t0 = time.monotonic()
        self._blink_until = self._look_until = 0.0
        self.napping = False                    # you've been away a while: eyes shut, little z's (2.3.4)
        self._nap_since = 0.0
        self._next_blink = self._t0 + 3.0
        self._next_look = self._t0 + 14.0
        self._smooth: dict[str, float] = {}     # body style: her pose right now, easing towards the target
        self._smooth_at = time.monotonic()
        self._smooth_ready = False              # the first pose is taken as it is (no easing in from nothing)
        self._moving = False
        self._state_at = time.monotonic()
        self._rig_full: Rig | None = None       # body style: her full-body figure, cut up
        self._rig_small: Rig | None = None      # ...pre-scaled to her size on this screen
        self._rig_key: tuple | None = None
        self._paint_failed = False
        self.acts = IdleActs()                  # gaming / watching / calls with D / glitching while idle
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)   # frames on time (no Windows 15.6 ms judder)
        self._timer.setInterval(int(1000 / IDLE_FPS))
        from .glitch import DragSway, RealGlitch
        self.glitch_every = 0                   # seconds between random glitches (0 = never, the default): Settings
        self.body_look = "full"                 # her figure: "full" (solid colours) or "neon" (Settings -> Character)
        self.real_glitch = RealGlitch(every=lambda: self.glitch_every)
        self.sway = DragSway()                  # she dangles while you drag her
        self.setMouseTracking(True)             # hovering over her: she floats up and leans to your cursor
        self._hover = 0.0                       # 0..1 eased
        self.grooving = False                   # music's playing: she vibes to it (a little bounce and sway)
        self._groove = 0.0                      # 0..1 eased in and out
        self._hover_on = False
        self._hover_x = 0.0
        self._sway_at = time.monotonic()
        self._next_drag_glitch = 0.0
        self._frame_key = None
        self._timer.timeout.connect(self._tick)
        self._look_painter = None
        self.style = self._valid_style(style)
        self.setWindowTitle(f"{art.name} - character")
        self.set_display_height(height)

    # -- configuration ---------------------------------------------------------
    @property
    def mode(self) -> str:
        if self.style.startswith("look:"):
            return "look"
        if self.lying and self.style != "classic" and self.sprites is not None and self.sprites.lying is not None:
            return "lying"
        return self.style

    def _valid_style(self, style: str) -> str:
        if style.startswith("look:"):                    # one of the animated pictures (looks.py)
            if looks.load(style[5:]) is not None:
                return style
            style = "body"
        return style if (self.sprites is not None or style == "classic") else "classic"

    def set_style(self, style: str) -> None:
        self.style = self._valid_style(style)
        self._look_painter = None
        self.set_display_height(self.display_height)

    def look_painter(self) -> looks.LookPainter | None:
        if self.mode != "look":
            return None
        look = looks.load(self.style[5:])
        if self._look_painter is None or self._look_painter.look is not look:
            self._look_painter = looks.LookPainter(look)
        return self._look_painter

    def set_look(self, wild_hair: float, idle_animation: bool, hair_style: str | None = None) -> None:
        self.wild_hair, self.idle_animation = wild_hair, idle_animation
        if hair_style and hair_style != self.hair_style:
            self.hair_style = hair_style
            self.hair = make_hair(hair_style) if hair_style in HAIR_STYLES else WildHair()
            self.lying_hair = make_hair(hair_style, flow_in=True)
            for rig in (self._rig_full, self._rig_small):
                if rig is not None:
                    rig.set_hair_style(hair_style)
        self.set_display_height(self.display_height)

    def _paint_hair_and_sprite(self, p: QPainter, image: QImage, x: float, y: float, head: QRectF | None,
                               face_key: str, size: tuple[int, int]) -> None:
        """Spikes go behind her; the storm goes over her own hair, with her face put back on top."""
        energy = self.level if self.talking else 0.0
        t = self._t()
        if head is not None and self.hair_style not in HAIR_STYLES:          # (old "spikes": behind her)
            self.hair.paint(p, head, t if self.talking else int(t * 8) / 8, self.wild_hair, energy)
        tinted = face_key == "lying" and self.hair_style == "storm" and self.wild_hair > 0 and self.sprites is not None
        if tinted:                                # her own hair beside her face: the traced hair's colour
            image = self._scaled("tint:lying", self._hair_tinted("lying", self.sprites.lying), size[0], size[1], cover=False)
        p.drawImage(QPointF(x, y), image)
        face = self.sprites.face_layer.get(face_key) if self.sprites else None
        if tinted and face is not None:
            face = self._hair_tinted("face:lying", face)
        if head is not None and self.hair_style in HAIR_STYLES and self.wild_hair > 0:
            hair = self.lying_hair if face_key == "lying" else self.hair     # lying down: no line where it meets her
            hair.paint_cached(p, head, t, self.wild_hair, energy,     # cached per boil step at rest
                                   (self.width(), self.height()), self.devicePixelRatioF())
            if face is not None:
                p.drawImage(QPointF(x, y), self._scaled("face:" + face_key + (":tint" if tinted else ""), face,
                                                        size[0], size[1], cover=False))

    def _hair_tinted(self, key: str, src: QImage) -> QImage:
        """A sprite with her own hair recoloured like the traced hair (see hair.tint_hair), made once."""
        cache = self.__dict__.setdefault("_tint_cache", {})
        if key not in cache:
            box = self.sprites.head_box.get("lying") if self.sprites else None
            box = box.adjusted(-0.03, -0.02, 0.05, 0.12) if box is not None else QRectF(0, 0, 0.4, 0.5)
            cache[key] = tint_hair(src, box)
        return cache[key]

    def set_lying(self, on: bool, width: int) -> None:
        self.lying, self.lying_width = on, width
        self.set_display_height(self.display_height)

    def set_display_height(self, height: int) -> None:
        self.display_height = height
        self._cache.clear()
        mode = self.mode
        if mode == "classic":
            idle = self.art.pose("idle")
            if self.art.mode == CARD:
                self._art_size = (round(height * 0.8), height)
                self.setFixedSize(self._art_size[0] + GLOW * 2, height + GLOW * 2)
            else:
                width = round(height * idle.width() / idle.height())
                self._art_size = (width, height)
                self.setFixedSize(width, height)
        elif mode == "look":
            look = self.look_painter().look
            if look.cutout:                                   # a figure that stands free
                h = round(height * 1.25)
                w = round(h * look.aspect)
                if w > height * 2.2:
                    w = round(height * 2.2)
                    h = round(w / look.aspect)
                self._look_rect = QRectF(4, 4, w, h)
                self.setFixedSize(w + 8, h + 8)
            else:                                             # a full picture: in a neon card
                h = round(height * 0.95)
                w = round(min(h * look.aspect, height * 1.7))
                self._look_rect = QRectF(GLOW, GLOW, w, h)
                self.setFixedSize(w + GLOW * 2, h + GLOW * 2)
            self._art_size = (round(self._look_rect.width()), round(self._look_rect.height()))
        elif mode == "portrait":
            self._art_size = (round(height * 0.85), round(height * 0.82))   # a squarer "video call" card
            self.setFixedSize(self._art_size[0] + GLOW * 2, self._art_size[1] + GLOW * 2)
        elif mode == "body":
            # her full-body figure (the sheet's standing art), a bit taller than the old knee-length frames
            src = self.sprites.frame("standing")
            self._figure_h = round(height * BODY_SCALE)
            self._figure_w = round(self._figure_h * src.width() / src.height())
            hair = 0.4 + 0.6 * min(1.4, self.wild_hair / 0.7)     # the storm needs room above her head
            self._margin = (round(self._figure_h * BODY_SIDE), round(self._figure_h * BODY_TOP * hair))
            self.setFixedSize(self._figure_w + 2 * self._margin[0], self._figure_h + self._margin[1] + 4)
        else:  # lying
            img = self.sprites.lying
            self._scale = self.lying_width / img.width()
            head_w = self.sprites.head_box["lying"].width() * img.width() * self._scale
            m = self.hair.margin(head_w, self.wild_hair)
            self._margin = (round(m * 0.8), round(m * 0.75))
            self.setFixedSize(round(img.width() * self._scale) + 2 * self._margin[0],
                              round(img.height() * self._scale) + self._margin[1] + 2)
        self._update_timer()
        self.update()

    def content_rect(self) -> QRect:
        """Where *she* is inside the window (window coords) - the rest is room for hair and glow.

        Only this part has to stay on screen, so she can stand right against the edge
        while her hair hangs off it.
        """
        mode = self.mode
        if mode == "look":
            return self._look_rect.toAlignedRect()
        if mode in ("classic", "portrait"):
            if mode == "classic" and self.art.mode != CARD:
                return self.rect()
            return QRect(GLOW, GLOW, self._art_size[0], self._art_size[1])
        if mode == "body":
            fw, fh = self._figure_w, self._figure_h
            return QRect(round(self.width() / 2 - fw / 2), self.height() - 2 - fh, fw, fh + 2)
        img = self.sprites.lying
        sw, sh = round(img.width() * self._scale), round(img.height() * self._scale)
        return QRect(self._margin[0], self.height() - 2 - sh, sw, sh + 2)

    def set_state(self, state: State, emotion: str | None = None) -> None:
        emotion = emotion or "neutral"
        if state is not self.state or emotion != self.emotion:
            self.state, self.emotion = state, emotion
            self._state_at = time.monotonic()
            self._moving = True                   # ease into the new pose (fast frames until settled)
            self._update_timer()
            if self.acts.update(time.monotonic(), self._acts_allowed()):   # she drops what she was doing
                self._update_timer()
            self.update()

    def play_act(self, name: str) -> bool:
        """Start an idle activity now (the menu / tests). False if she can't right now."""
        if not self._acts_allowed():
            return False
        self.acts.begin(name, time.monotonic())
        self._update_timer()
        self.update()
        return True

    # -- talking -----------------------------------------------------------------
    def set_talking(self, on: bool) -> None:
        self.talking = on
        if on and self.acts.act:
            self.acts.stop(time.monotonic())
        if not on:
            self.level, self.mouth_open, self._glitch, self.viseme = 0.0, False, 0, ""
        self._update_timer()
        self.update()

    def set_voice_level(self, level: float) -> None:
        self.level = level
        was = self.mouth_open
        if level > MOUTH_OPEN:
            self.mouth_open = True
        elif level < MOUTH_CLOSE:
            self.mouth_open = False
        if was != self.mouth_open and self._rng.random() < 0.5:
            self._glitch = GLITCH_FRAMES          # swap between expressions behind a glitch
        elif self._rng.random() < 0.05 * level:
            self._glitch = GLITCH_FRAMES
        elif self._glitch:
            self._glitch -= 1
        self.update()

    def set_viseme(self, viseme: str) -> None:
        if viseme != self.viseme:
            self.viseme = viseme
            self.update()

    def pose_name(self) -> str:
        """Which image is showing right now (also used by the tests)."""
        mode = self.mode
        if mode == "look":
            return "look"
        if mode == "classic":
            if self.talking:
                return "speaking" if self.mouth_open else "idle"
            return STATE_STYLES[self.state].pose
        emo = emotions.get(self.emotion)
        if mode == "portrait":
            if self.talking and self.mouth_open and self.viseme:
                return "viseme:" + self.viseme
            if self.talking or self.state in (State.SUCCESS, State.ERROR, State.SPEAKING):
                return "face:" + emo.face
            return "face:" + ("serious" if self.state in (State.PROCESSING, State.LAUNCHING) else "neutral")
        if mode == "lying":
            return "lying"
        # body
        if self.talking:
            return "speaking" if self.mouth_open else emo.body
        if self.state in STATE_FRAME:
            return STATE_FRAME[self.state]
        if self.state in (State.SUCCESS, State.SPEAKING):
            return emo.body
        now = time.monotonic()
        act_pose = self.acts.pose(now)
        if act_pose is not None and act_pose in self.sprites.body:
            return act_pose
        if now < self._blink_until or self.napping:
            return "blink"
        if now < self._look_until:
            return "look_around"
        return "idle"

    # -- animation clock -------------------------------------------------------------
    def _animating(self) -> bool:
        if not self.isVisible():
            return False
        if self.napping:
            return True                                  # the z's drift up (an idle frame rate is plenty)
        if self.mode == "classic":
            return False
        if self.mode == "look":
            return self.talking or self.idle_animation
        return self.talking or self.idle_animation or self.wild_hair > 0

    def _acts_allowed(self) -> bool:
        return (self.mode in ("body", "lying") and self.idle_animation and not self.talking and self.state is State.IDLE
                and self.isVisible())

    def _blinking(self) -> bool:
        return time.monotonic() < self._blink_until

    def _update_timer(self) -> None:
        fast = self.talking or (self.mode == "body" and (self._moving or self._blinking())) or self._special()
        fps = TALK_FPS if fast else LOOK_FPS if self.mode == "look" else ACT_FPS if self.acts.act else IDLE_FPS
        self._timer.setInterval(int(1000 / fps))
        if self._animating():
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self.acts.act:
            self.acts.stop(time.monotonic())
        self._timer.stop()          # hidden = no CPU at all

    # -- held / glitching ----------------------------------------------------------------
    def set_held(self, held: bool) -> None:
        """You picked her up (dragging) / let go: she dangles and swings."""
        if held:
            self.sway.grab()
            self._next_drag_glitch = time.monotonic() + 0.35
        else:
            self.sway.drop()
        self._update_timer()

    def held_at(self, x: float) -> None:
        self.sway.moved(x)

    # -- your mouse over her ------------------------------------------------------------
    def enterEvent(self, event) -> None:
        super().enterEvent(event)                 # (hovering starts when your mouse really moves over her)

    def leaveEvent(self, event) -> None:
        self._hover_on = False
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._hover_x = event.position().x()
        if not self._hover_on and QRectF(self.content_rect()).adjusted(-20, -40, 20, 0).contains(event.position()):
            self._hover_on = True
            self._update_timer()
        super().mouseMoveEvent(event)

    def _hover_step(self, dt: float) -> None:
        goal = 1.0 if self._hover_on and not self.sway.held else 0.0
        self._hover += (goal - self._hover) * (1 - math.exp(-dt / 0.18))
        if abs(self._hover - goal) < 0.002:
            self._hover = goal

    def glitch_now(self, light: bool = False) -> None:
        self.real_glitch.start(light)
        self._update_timer()

    def _special(self) -> bool:
        """Something that needs full-speed frames right now: a glitch, her swinging, your mouse on her, or music."""
        return self.real_glitch.active or self.sway.swinging or self._hover_on or self._hover > 0.0 or \
            (self.mode == "body" and (self.grooving or self._groove > 0.0))

    GROOVE_BPM = 104                            # her bounce, about the speed of most songs

    def set_grooving(self, on: bool) -> None:
        """Music on / off: she starts (or stops) vibing to it."""
        if on != self.grooving:
            self.grooving = on
            self._update_timer()

    def groove_moves(self, now: float) -> dict[str, float]:
        """Her vibe while music plays, eased in / out: knees bouncing on the beat, swaying every two beats,
        hair bouncing, stepping side to side a little."""
        if self._groove <= 0.0:
            return {}
        beat = now * self.GROOVE_BPM / 60.0 * 2 * math.pi
        g = self._groove
        bounce = max(0.0, math.sin(beat)) ** 2
        return {"squat": 0.14 * bounce * g, "lean": 0.055 * math.sin(beat / 2) * g,
                "stride": 0.16 * math.sin(beat / 2) * g, "energy": (0.3 + 0.25 * bounce) * g,
                "wag": 0.35 * math.sin(beat / 2) * g}

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._sway_at = min(0.05, now - self._sway_at), now
        self._hover_step(dt)
        want = 1.0 if self.grooving and not self.talking and not self.sway.held else 0.0
        if self._groove != want:                                   # eases in / out over about half a second
            step = dt / 0.5
            self._groove = min(want, self._groove + step) if want > self._groove else max(want, self._groove - step)
        if self.sway.swinging:
            self.sway.step(dt)
        if self.real_glitch.due(self.isVisible() and not self.talking and self.mode != "classic" and self.state
                                not in (State.LISTENING, State.PROCESSING, State.LAUNCHING, State.SPEAKING)):
            self.real_glitch.start()
        if self.idle_animation and not self.talking and self.state is State.IDLE:
            if now >= self._next_blink:
                self._blink_until = now + BLINK_SECONDS
                self._next_blink = now + self._rng.uniform(2.5, 6.0)
                self._update_timer()                         # smooth blink: fast frames for a moment
            if now >= self._next_look:
                self._look_until = now + 1.7
                self._next_look = now + self._rng.uniform(12.0, 26.0)
        if self.acts.update(now, self._acts_allowed()):
            self._update_timer()
        if self._special():                                  # a glitch / swinging / your mouse on her: full speed
            if self._timer.interval() != int(1000 / TALK_FPS):
                self._update_timer()
            self.update()
            return
        if self.talking or (self.mode == "body" and (self._moving or self._blinking())):
            self.update()
            if not self.talking and not self._moving and not self._blinking():
                self._update_timer()
            return
        if self.mode == "body" and self._timer.interval() != int(1000 / (ACT_FPS if self.acts.act else IDLE_FPS)):
            self._update_timer()                             # settled: back to the light idle rate
        # At rest, only repaint when something visible changed: pose, breathing bob, hair boil step.
        key = (self.pose_name(), round(self._bob() * 8), self._hair_step(), self.acts.frame_key(now),
               int(self._t() * LOOK_FPS) if self.mode == "look" else 0)      # looks move all the time
        if key != self._frame_key:
            self._frame_key = key
            self.update()

    def _bob(self) -> float:
        """Breathing: a gentle, sub-pixel rise and fall."""
        if not self.idle_animation:
            return 0.0
        return 1.4 * math.sin(self._t() * 2 * math.pi / 3.6)

    def _hair_step(self) -> int:
        if self.wild_hair <= 0:
            return 0
        if self.mode == "body":
            return self.figure_rig().hair.step(self._t(), 0.0)[1]
        if hasattr(self.hair, "step"):
            return self.hair.step(self._t(), 0.0)[1]
        return int(self._t() * 8)

    # -- painting ---------------------------------------------------------------------
    def _scaled(self, key: str, image: QImage, w: int, h: int, cover: bool) -> QImage:
        dpr = self.devicePixelRatioF()
        k = (key, dpr, w, h, cover)
        if k not in self._cache:
            self._cache[k] = CharacterArt.scaled(image, w, h, dpr, cover=cover)
        return self._cache[k]

    def accent(self) -> QColor:
        style = STATE_STYLES[self.state]
        if style.alert:
            return theme.ALERT
        if self.state is State.LISTENING or self.talking:
            return theme.GREEN
        return theme.PANEL_BORDER

    def _draw_glitch(self, p: QPainter, image: QImage, x: float, y: float) -> None:
        """A few horizontal slices of the image, shifted sideways, plus neon scan lines."""
        dpr = image.devicePixelRatio()
        w, h = image.width() / dpr, image.height() / dpr
        for _ in range(3):
            band_y = self._rng.uniform(0, h - 6)
            band_h = self._rng.uniform(3, 10)
            dx = self._rng.choice((-1, 1)) * self._rng.uniform(3, 8)
            src = QRectF(0, band_y * dpr, image.width(), band_h * dpr)
            p.drawImage(QRectF(x + dx, y + band_y, w, band_h), image, src)
        for color in (theme.GREEN, QColor(255, 54, 160)):
            c = QColor(color)
            c.setAlpha(150)
            p.setPen(QPen(c, 1))
            ly = y + self._rng.uniform(0, h)
            p.drawLine(QPointF(x, ly), QPointF(x + w, ly))

    def _t(self) -> float:
        return time.monotonic() - self._t0 if (self.idle_animation or self.talking) else 0.0

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        try:
            draw = {"classic": self._paint_classic, "portrait": self._paint_portrait, "body": self._paint_body,
                    "lying": self._paint_lying, "look": self._paint_look}[self.mode]
            if self.real_glitch.active:                       # a real glitch: her picture, then broken up
                dpr = self.devicePixelRatioF()
                snap = QImage(round(self.width() * dpr), round(self.height() * dpr),
                              QImage.Format.Format_ARGB32_Premultiplied)
                snap.setDevicePixelRatio(dpr)
                snap.fill(0)
                q = QPainter(snap)
                q.setRenderHint(QPainter.RenderHint.Antialiasing)
                q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                draw(q)
                q.end()
                self.real_glitch.paint(p, snap, QRectF(self.content_rect()), max(0.5, self.display_height / 420))
            else:
                draw(p)
            if self.napping and not self.talking:
                self._paint_zzz(p)
        except Exception:
            # Never leave her invisible (and the panel floating over nothing): log it once, draw her plainly.
            if not self._paint_failed:
                self._paint_failed = True
                log.exception("drawing Capri failed (%s style)", self.mode)
            p.end()
            p = QPainter(self)
            image = self.art.pose("idle")
            target = QRectF(self.content_rect())
            scale = min(target.width() / max(1, image.width()), target.height() / max(1, image.height()))
            w, h = image.width() * scale, image.height() * scale
            p.drawImage(QRectF(target.center().x() - w / 2, target.bottom() - h, w, h), image)
        p.end()

    def set_napping(self, on: bool) -> None:
        """You've been away (no mouse or keyboard) a while: she naps. Any input and she's awake again."""
        if on == self.napping:
            return
        self.napping, self._nap_since = on, time.monotonic()
        self._update_timer()
        self.update()

    def _paint_zzz(self, p: QPainter) -> None:
        """Three z's drifting up from her head, each fading out as it rises."""
        from PySide6.QtGui import QFont
        c = self.content_rect()
        top = self.visual_top() if self.mode == "body" else c.top()
        size = max(10.0, c.width() * 0.13)
        x0, y0 = c.center().x() + c.width() * 0.18, top + size * 2.2
        t = time.monotonic() - self._nap_since
        p.save()
        font = QFont()
        font.setBold(True)
        for i in range(3):
            phase = ((t * 0.35) + i / 3.0) % 1.0
            font.setPixelSize(round(size * (0.6 + 0.6 * phase)))
            p.setFont(font)
            col = QColor(theme.GREEN)
            col.setAlphaF(max(0.0, min(1.0, 1.3 * (1 - phase))) * min(1.0, t / 1.5))
            p.setPen(col)
            p.drawText(QPointF(x0 + size * 1.4 * phase + 3 * math.sin(phase * 6.28), y0 - size * 2.4 * phase), "z")
        p.restore()

    def figure_height(self) -> int:
        """How tall her full-body figure is at this size (the dashes use the same size)."""
        return self._figure_h if self.mode == "body" else round(self.display_height * BODY_SCALE)

    def visual_top(self) -> int:
        """Where the top of her (her hair storm included) is, in window coordinates - the panel sits there."""
        c = self.content_rect()
        if self.mode == "body" and self.wild_hair > 0:
            return max(0, c.top() - round(self._figure_h * 0.21 * min(1.3, self.wild_hair / 0.7)))
        if self.mode in ("body", "lying", "look"):
            return max(0, c.top() - (6 if self.mode != "look" else 0))
        return 0

    def _bounce(self) -> float:
        return -2.5 * self.level if self.talking else 0.0       # a little hop on each syllable

    def _paint_classic(self, p: QPainter) -> None:
        pose = self.pose_name()
        w, h = self._art_size
        image = self._scaled("classic:" + pose, self.art.pose(pose), w, h, self.art.mode == CARD)
        bounce = self._bounce()
        if self.art.mode != CARD:
            iw, ih = image.width() / image.devicePixelRatio(), image.height() / image.devicePixelRatio()
            x, y = (self.width() - iw) / 2, self.height() - ih + bounce
            p.drawImage(QPointF(x, y), image)
            if self._glitch:
                self._draw_glitch(p, image, x, y)
            return
        self._paint_card(p, image, bounce)

    def _paint_card(self, p: QPainter, image: QImage, bounce: float, backdrop: bool = False,
                    hair_head: QRectF | None = None, align_bottom: bool = False) -> None:
        w, h = self._art_size
        frame = QRectF(GLOW, GLOW, w, h)
        path = card_path(frame)
        p.save()
        p.setClipPath(path)
        if backdrop:
            self._paint_backdrop(p, frame)
        iw, ih = image.width() / image.devicePixelRatio(), image.height() / image.devicePixelRatio()
        x = frame.x() + (w - iw) / 2
        y = (frame.bottom() - ih if align_bottom else frame.y() + (h - ih) / 2) + bounce
        if hair_head is not None:
            head = QRectF(x + hair_head.x() * iw, y + hair_head.y() * ih, hair_head.width() * iw,
                          hair_head.height() * ih)
            self.hair.paint(p, head, self._t(), self.wild_hair * 0.6, self.level if self.talking else 0.0)
        p.drawImage(QPointF(x, y), image)
        if self._glitch:
            self._draw_glitch(p, image, x, y)
        p.restore()

        accent = self.accent()
        glow = QColor(accent)
        glow.setAlpha(60 + int(150 * self.level) if self.talking else 60)   # glow pulses with her voice
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(glow, 5))
        p.drawPath(path)
        p.setPen(QPen(accent, 1.6))
        p.drawPath(path)
        p.setPen(QPen(theme.GREEN, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        l, t, r, b = frame.left(), frame.top(), frame.right(), frame.bottom()
        p.drawPolyline([QPointF(l + 3, b - 18), QPointF(l + 3, b - 3), QPointF(l + 18, b - 3)])
        p.drawPolyline([QPointF(r - 18, t + 3), QPointF(r - 3, t + 3), QPointF(r - 3, t + 18)])

    def _paint_backdrop(self, p: QPainter, frame: QRectF) -> None:
        """Dark screen with drifting red sparkles - her red hair needs a dark backdrop to read."""
        g = QRadialGradient(QPointF(frame.center().x(), frame.top() + frame.height() * 0.35), frame.width())
        g.setColorAt(0, QColor(46, 18, 42))
        g.setColorAt(1, QColor(10, 6, 14))
        p.fillRect(frame, g)
        rng = random.Random(5)
        t = self._t() if self.talking else int(self._t() * 4) / 4      # twinkle in steps at rest
        for i in range(70):
            x = frame.left() + rng.random() * frame.width()
            y = frame.top() + rng.random() * frame.height()
            a = 90 + int(120 * (0.5 + 0.5 * math.sin(t * rng.uniform(1, 3) + i)))
            p.fillRect(QRectF(x, y, 1.6, 1.6), QColor(255, 60, 100, a))

    def _paint_portrait(self, p: QPainter) -> None:
        pose = self.pose_name()
        kind, name = pose.split(":", 1)
        src = self.sprites.mouth(name) if kind == "viseme" else self.sprites.face(name)
        w, h = self._art_size
        # the whole head across the card, resting on its bottom edge (the head art is cut off there)
        image = self._scaled(pose, src, w, w, cover=False)
        self._paint_card(p, image, self._bounce() + self._bob() + 2, backdrop=True, align_bottom=True)

    def release_caches(self) -> None:
        """Forget pre-scaled images and the cut-up figure (game mode: she's hidden). Rebuilt when shown."""
        self._cache.clear()
        self._rig_full = self._rig_small = self._rig_key = None
        self.acts._tints.clear()
        self.acts._puppet = None

    def set_body_look(self, look: str) -> None:
        if look != self.body_look:
            self.body_look = look
            self._rig_full = self._rig_small = self._rig_key = None
            self._lying_neon = None
            self.update()

    def full_rig(self) -> Rig | None:
        """Her full-body figure cut into parts, at full size (None without her sprites). Her sitting window
        uses it too, so she looks the same sitting on a window."""
        if self.sprites is None:
            return None
        if self._rig_full is None:
            from .neon import body_image
            self._rig_full = Rig(body_image(self.sprites.frame("standing"), self.body_look),
                                 self.hair_style if self.hair_style in HAIR_STYLES else "storm")
        return self._rig_full

    def figure_rig(self) -> Rig:
        """Her full-body figure, pre-scaled for this size and screen (rebuilt if either changes)."""
        self.full_rig()
        dpr = self.devicePixelRatioF()
        key = (self._figure_h, dpr)
        if self._rig_key != key:
            self._rig_small, self._rig_key = self._rig_full.resized(max(8, round(self._figure_h * dpr))), key
        return self._rig_small

    def figure_pose(self, name: str | None = None) -> Pose:
        """The body style's pose: for a named expression exactly (the tests), else right now - eased
        from the last pose into this one, blinking smoothly, the mouth following her voice."""
        if name is not None:
            return Pose(t=self._t(), wild=min(1.5, self.wild_hair / 0.7), **BODY_POSES.get(name, {}))
        now = time.monotonic()
        current = self.pose_name()
        moves = dict(BODY_POSES.get("idle" if current in ("blink", "speaking") else current, {}))
        if self.talking:
            moves["energy"] = max(moves.get("energy", 0.0), 0.3 + 0.7 * self.level)
            moves["mouth"] = min(1.0, 0.25 + self.level) if self.level > 0.08 else 0.0
        elif self.acts.act:
            moves["mouth"] = self.acts.mouth(now)                  # her turn on the call with D
        if self.sway.held:                                         # dangling from your cursor
            held = self.sway.pose_moves(now)
            held.pop("lean", None)
            moves.update(held)
        smooth = self._ease_towards(moves, now)
        if self.sway.swinging:
            smooth = dict(smooth)
            smooth["lean"] = smooth.get("lean", 0.0) + self.sway.angle
        if self._groove > 0.0 and self.mode == "body":             # music: she vibes to it
            smooth = dict(smooth)
            for k, v in self.groove_moves(now).items():
                smooth[k] = max(smooth.get(k, 0.0), v) if k in ("energy", "squat") else smooth.get(k, 0.0) + v
        if self._hover > 0.0:                                      # leaning to your cursor, hair perking up
            smooth = dict(smooth)
            side = max(-1.0, min(1.0, (self._hover_x - self.width() / 2) / max(1.0, self.width() / 2)))
            smooth["lean"] = smooth.get("lean", 0.0) + 0.07 * side * self._hover
            smooth["energy"] = max(smooth.get("energy", 0.0), 0.45 * self._hover)
            smooth["sweep"] = smooth.get("sweep", 0.0) + 0.12 * self._hover
        blink = 0.0
        if now < self._blink_until:                                # closes and opens, not on / off
            blink = math.sin(math.pi * min(1.0, 1 - (self._blink_until - now) / BLINK_SECONDS))
        if self.napping and not self.talking:                      # asleep: eyes shut, head nodding a little
            blink = min(1.0, (now - self._nap_since) / 0.8)
            smooth = dict(smooth)
            smooth["lean"] = smooth.get("lean", 0.0) + 0.03 * math.sin(now * 0.9)
            smooth["squat"] = max(smooth.get("squat", 0.0), 0.12)
            smooth["energy"] = 0.0
        eyes = ""
        since = now - self._state_at
        if self.emotion in ("happy", "playful") and self.state in (State.SUCCESS, State.SPEAKING) and not self.talking:
            eyes = "happy"                                          # pleased with herself
        if self.emotion in ("playful", "smirk") and self.state is State.SUCCESS and 0.15 < since < 0.6:
            eyes = "wink"
        return Pose(t=self._t(), wild=min(1.5, self.wild_hair / 0.7), blink=blink, eyes=eyes, **smooth)

    def _ease_towards(self, target: dict[str, float], now: float) -> dict[str, float]:
        dt = min(0.25, max(0.0, now - self._smooth_at))
        self._smooth_at = now
        k = 1 - math.exp(-dt / SMOOTH_TAU)
        k_mouth = 1 - math.exp(-dt / 0.045)                         # a mouth closes quicker than a body moves
        first = not self._smooth_ready
        self._smooth_ready = True
        out = {}
        for key in set(target) | set(self._smooth):
            goal = target.get(key, 0.0)
            cur = goal if first else self._smooth.get(key, 0.0)
            if key in ("mouth", "energy") and goal > cur:
                cur = goal                                          # opens / flares at once, settles gently
            else:
                cur += (goal - cur) * (k_mouth if key == "mouth" else k)
            out[key] = goal if abs(cur - goal) < 0.003 else cur
        self._smooth = {k2: v for k2, v in out.items() if v or k2 in target}
        self._moving = any(abs(out[k2] - target.get(k2, 0.0)) > 0.003 for k2 in out)
        return out

    def _paint_figure(self, p: QPainter, jolt: QPointF) -> None:
        lift = self._hover * (7 + 2 * math.sin(time.monotonic() * 3.2)) * max(0.6, self._figure_h / 300)
        feet = QPointF(self.width() / 2 + jolt.x(),
                       self.height() - 2 + self._bounce() + self._bob() + jolt.y() - lift)    # hovering up
        pose = self.figure_pose()
        self.figure_rig().paint(p, feet, self._figure_h, pose, "left" if pose.reach else "right")

    def _paint_body(self, p: QPainter) -> None:
        now = time.monotonic()
        jolt = self.acts.offset(now)
        snapshot = None
        if self.acts.act == "glitch":                      # the glitch needs a picture of her to tear up
            dpr = self.devicePixelRatioF()
            snapshot = QImage(round(self.width() * dpr), round(self.height() * dpr),
                              QImage.Format.Format_ARGB32_Premultiplied)
            snapshot.setDevicePixelRatio(dpr)
            snapshot.fill(0)
            q = QPainter(snapshot)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self._paint_figure(q, jolt)
            q.end()
            p.drawImage(QPointF(0, 0), snapshot)
        else:
            self._paint_figure(p, jolt)
        body = QRectF(self.content_rect())
        if self.state is State.ERROR:                      # a red flicker over her
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            c = QColor(theme.ALERT)
            c.setAlpha(70)
            p.fillRect(self.rect(), c)
            p.restore()
        if self.acts.act:
            rig = self.figure_rig()
            k = self._figure_h / rig.h
            head = QRectF(body.x() + rig.head.x() * k, body.y() + rig.head.y() * k,
                          rig.head.width() * k, rig.head.height() * k)
            self.acts.paint(p, Ctx(snapshot, body, head, self.width(), self.height()), now)

    def _paint_look(self, p: QPainter) -> None:
        """One of the animated pictures: free-standing, or filling a neon card."""
        painter = self.look_painter()
        look, t = painter.look, self._t()
        r, dpr = QRectF(self._look_rect), self.devicePixelRatioF()
        level = self.level if self.talking else 0.0
        if look.cutout:
            painter.paint(p, r, t, level, self.talking, dpr, self.wild_hair / 0.7)
            return
        path = card_path(r)
        p.save()
        p.setClipPath(path)
        self._paint_backdrop(p, r)
        scale = max(r.width() / look.image.width(), r.height() / look.image.height()) * 1.04
        w, h = look.image.width() * scale, look.image.height() * scale
        painter.paint(p, QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h), t, level, self.talking,
                      dpr, self.wild_hair / 0.7)
        p.restore()
        accent = self.accent()
        glow = QColor(accent)
        glow.setAlpha(60 + int(150 * self.level) if self.talking else 60)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(glow, 5))
        p.drawPath(path)
        p.setPen(QPen(accent, 1.6))
        p.drawPath(path)

    def _paint_lying_figure(self, p: QPainter, jolt: QPointF) -> tuple[QRectF, QRectF | None]:
        src = self.sprites.lying
        if self.body_look == "neon":                        # lying on the panel in the same look
            if getattr(self, "_lying_neon", None) is None:
                from .neon import neon_array
                from .rig import _to_array, _to_image
                self._lying_neon = _to_image(neon_array(_to_array(src)))
            src = self._lying_neon
        sw, sh = round(src.width() * self._scale), round(src.height() * self._scale)
        image = self._scaled("lying:" + self.body_look, src, sw, sh, cover=False)
        x = float(self._margin[0]) + jolt.x()
        y = float(self.height() - 2 - sh) + self._bounce() + self._bob() + jolt.y()
        p.save()
        hb = self.sprites.head_box.get("lying")
        head = QRectF(x + hb.x() * sw, y + hb.y() * sh, hb.width() * sw, hb.height() * sh * 0.8) if hb else None
        if self.state is State.ERROR:
            image = self._tinted(image, theme.ALERT)
        self._paint_hair_and_sprite(p, image, x, y, head, "lying", (sw, sh))
        if self._glitch:
            self._draw_glitch(p, image, x, y)
        p.restore()
        return QRectF(x, y, sw, sh), head

    def _paint_lying(self, p: QPainter) -> None:
        now = time.monotonic()
        jolt = self.acts.offset(now)
        snapshot = None
        if self.acts.act == "glitch":
            dpr = self.devicePixelRatioF()
            snapshot = QImage(round(self.width() * dpr), round(self.height() * dpr),
                              QImage.Format.Format_ARGB32_Premultiplied)
            snapshot.setDevicePixelRatio(dpr)
            snapshot.fill(0)
            q = QPainter(snapshot)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            body, head = self._paint_lying_figure(q, jolt)
            q.end()
            p.drawImage(QPointF(0, 0), snapshot)
        else:
            body, head = self._paint_lying_figure(p, jolt)
        if self.acts.act and head is not None:
            face = QPointF(body.x() + body.width() * LYING_FACE[0], body.y() + body.height() * LYING_FACE[1])
            self.acts.paint(p, Ctx(snapshot, body, head, self.width(), self.height(), lying=True, face_at=face), now)

    def _tinted(self, image: QImage, color: QColor) -> QImage:
        """The sprite washed with a colour (only where it's opaque) - a red flicker on errors."""
        key = ("tint", image.cacheKey(), color.rgba())
        if key in self._cache:
            return self._cache[key]
        tinted = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
        tinted.setDevicePixelRatio(image.devicePixelRatio())
        tinted.fill(0)
        tp = QPainter(tinted)
        tp.drawImage(0, 0, image)
        tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        c = QColor(color)
        c.setAlpha(70)
        tp.fillRect(tinted.rect(), c)
        tp.end()
        self._cache[key] = tinted
        return tinted


def card_path(r: QRectF) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(r.left() + CHAMFER, r.top())
    path.lineTo(r.right(), r.top())
    path.lineTo(r.right(), r.bottom() - CHAMFER)
    path.lineTo(r.right() - CHAMFER, r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + CHAMFER)
    path.closeSubpath()
    return path
