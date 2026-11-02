""""Sit on windows": Capri hops onto the window you're using and sits on its top edge,
following it if you move it. Her message panel stays at home in its corner. When that window
goes away (closed, minimised, maximised) she teleports back onto the panel.

* switching to another window: she hops over to it once it has stayed in front for a moment;
* full-screen things, maximised windows, the desktop and her own windows aren't sat on;
* dragging her off a window drops her there (that becomes her spot) - she won't jump back onto
  that same window until you've used another one;
* off in drone mode, while hidden, and while she's off zapping something.

Turning it on (or starting Capri with it on) sends her straight onto your window.

Windows only (it reads where windows are); elsewhere the setting does nothing. Cheap: a few
window lookups twice a second, plus one position lookup a frame while she's sitting on one.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient

from . import lightning
from .overlay_window import OverlayWindow

if TYPE_CHECKING:
    from .companion import Companion

log = logging.getLogger("capri")

LOOK_EVERY = 500        # ms between looks at the window in front
FOLLOW_EVERY = 15       # ms while she sits on one: she keeps up as you drag it (one cheap lookup)
SETTLE_LOOKS = 2        # a new window has to stay in front this many looks before she hops
COVERED_LOOKS = 2       # her window has to stay covered this many looks (a passing popup doesn't move her)
FLASH = 0.4             # seconds of the teleport flash
FLASH_SIZE = 200
RED = QColor(236, 16, 70)
ART = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "perch"
SIT_HEIGHT = {False: 300, True: 170}     # normal / compact
SINK = 4                                 # px of her thigh resting below the window's top edge
PAD = 24                                 # room round her for the swinging foot
FPS = 30

Front = Callable[[], "tuple[int, QRect] | None"]


class _Flash(OverlayWindow):
    """A red burst with a few sparks where she vanishes / appears."""

    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self.resize(FLASH_SIZE, FLASH_SIZE)
        self._start = 0.0
        self._rng = random.Random()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def fire(self, at: QPoint) -> None:
        self.move(at.x() - FLASH_SIZE // 2, at.y() - FLASH_SIZE // 2)
        self._start = time.monotonic()
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self) -> None:
        if time.monotonic() - self._start >= FLASH:
            self._timer.stop()
            self.hide()
        else:
            self.update()

    def paintEvent(self, event) -> None:
        k = (time.monotonic() - self._start) / FLASH
        if not 0 <= k < 1:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(FLASH_SIZE / 2, FLASH_SIZE / 2)
        r = FLASH_SIZE * (0.2 + 0.3 * k)
        g = QRadialGradient(c, r)
        g.setColorAt(0, QColor(255, 235, 240, int(220 * (1 - k))))
        g.setColorAt(0.35, QColor(RED.red(), RED.green(), RED.blue(), int(180 * (1 - k))))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, r, r)
        for i in range(4):
            a = self._rng.uniform(0, 2 * math.pi)
            end = c + QPointF(math.cos(a), math.sin(a)) * FLASH_SIZE * 0.45
            lightning.draw(p, lightning.bolt(c, end, self._rng, roughness=0.3, depth=3), 1 - k, 0.8)
        p.end()


class SitWindow(OverlayWindow):
    """Her sitting on the window's edge, swinging her legs: the black one and the red one each
    swing from their own knee, out of step. Each lower leg is its own layer (the part the other
    leg hid is painted in), and the top of each shin also stays in her body, so a knee never
    opens up and nothing shows a gap as they swing. She breathes a little, pivoting on her
    seat, so she stays put on the edge."""

    def __init__(self, always_on_top: bool = True, compact: bool = False, art: Path = ART) -> None:
        super().__init__(always_on_top)
        self.art = art
        info = json.loads((art / "sit.json").read_text())
        self.art_w, self.art_h = info["size"]
        self.knees = {"black": QPointF(*info["black_knee"]), "red": QPointF(*info["red_knee"])}
        self.seat = float(info["seat"])
        self.talking = False
        self._t0 = time.monotonic()
        self._scaled: dict = {}
        self._scaled_key = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self.update)
        self.set_compact(compact)

    def set_compact(self, compact: bool) -> None:
        self.height_px = SIT_HEIGHT[compact]
        self.s = self.height_px / self.art_h
        self.setFixedSize(QSize(round(self.art_w * self.s) + PAD * 2, self.height_px + PAD * 2))
        self.update()

    def set_talking(self, on: bool) -> None:
        self.talking = on

    def seat_point(self) -> QPoint:
        """Where on the window she sits on the edge: under her black knee, at seat height."""
        return QPoint(round(PAD + self.knees["black"].x() * self.s), round(PAD + self.seat * self.s))

    def content_rect(self) -> QRect:
        return QRect(PAD, PAD, round(self.art_w * self.s), self.height_px)

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        self._scaled, self._scaled_key = {}, None          # nothing kept while she isn't sitting
        super().hideEvent(event)

    def _layers(self, dpr: float) -> dict:
        """Each layer read from disk and scaled once (smoothly) to her size on this screen - sharp,
        and the full-size pictures aren't kept in memory."""
        w, h = round(self.art_w * self.s * dpr), round(self.height_px * dpr)
        if self._scaled_key != (w, h):
            def fit(name: str) -> QImage:
                img = QImage(str(self.art / f"{name}.png"))
                out = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                out.setDevicePixelRatio(dpr)
                return out
            self._scaled = {n: fit(n) for n in ("base", "black", "red")}
            self._scaled_key = (w, h)
        return self._scaled

    def pose(self, t: float) -> tuple[float, float, float]:
        """(black leg angle, red leg angle - degrees, breath) at time t: her legs swing out of step."""
        speed = 1.6 if self.talking else 1.0                # a bit livelier while she talks
        phase = t * speed * math.pi
        black = 10.0 * math.sin(phase) + 1.5 * math.sin(t * 0.7)
        red = -3.2 * math.sin(phase + 0.9)
        breath = 0.01 * math.sin(t * 1.6)
        return black, red, breath

    def paintEvent(self, event) -> None:
        layers = self._layers(self.devicePixelRatioF())
        black, red, breath = self.pose(time.monotonic() - self._t0)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        seat = QPointF(self.seat_point())
        p.translate(seat)                                   # she breathes, pivoting on her seat
        p.scale(1.0, 1.0 + breath)
        p.translate(-seat)
        p.translate(PAD, PAD)
        p.drawImage(QPointF(0, 0), layers["base"])
        for name, angle in (("black", black), ("red", red)):  # the red leg crosses in front
            knee = self.knees[name] * self.s
            p.save()
            p.translate(knee)
            p.rotate(angle)
            p.translate(-knee)
            p.drawImage(QPointF(0, 0), layers[name])
            p.restore()
        p.end()


class WindowPerch(QObject):
    def __init__(self, companion: Companion, front: Front | None = None,
                 rect_of: Callable[[int], QRect | None] | None = None, top: Front | None = None,
                 covered: Callable[[int], bool] | None = None) -> None:
        super().__init__()
        self.companion = companion
        self.front = front or front_window
        self.rect_of = rect_of or window_rect
        self.top = top or top_window
        self.covered = covered or (seat_covered if front is None else (lambda hwnd: False))
        self._covered_looks = 0
        self.hwnd: int | None = None             # the window she's sitting on
        self._skip: int | None = None            # you dragged her off this one
        self._candidate: int | None = None
        self._seen = 0
        self.flashes = (_Flash(), _Flash())
        self._timer = QTimer(self)
        self._timer.setInterval(LOOK_EVERY)
        self._timer.timeout.connect(self.tick)
        self._follow = QTimer(self)               # while she sits: keep up with the window, every frame
        self._follow.setInterval(FOLLOW_EVERY)
        self._follow.timeout.connect(self.follow)
        companion.perch_dropped.connect(self._dropped)
        if companion.settings.perch_windows:
            self._timer.start()
            QTimer.singleShot(1500, self.hop_now)  # on at start-up: straight onto your window

    @property
    def enabled(self) -> bool:
        return self._timer.isActive()

    def set_enabled(self, on: bool) -> None:
        if on:
            self._timer.start()
            self.hop_now()                        # turned on: she teleports onto your window right away
        else:
            self._timer.stop()
            self.go_home()

    def hop_now(self) -> None:
        """Onto the window you're using (or the top one, if that's her own menu) - no waiting."""
        c = self.companion
        if not self.enabled or c.drone or c.hidden or c.busy_elsewhere or c.perched:
            return
        try:
            found = self.top()
        except Exception:
            found = None
        if found is not None and found[0] != self._skip and c.can_perch(found[1]):
            self._hop(*found)

    def _dropped(self) -> None:
        self._skip, self.hwnd = self.hwnd, None
        self._follow.stop()

    def follow(self) -> None:
        """Every frame while she sits: ride along with the window as you drag it."""
        c = self.companion
        if self.hwnd is None or not c.perched:
            self._follow.stop()
            return
        rect = self.rect_of(self.hwnd)
        if rect is None:
            log.info("perch: her window is gone - back to the panel")
            return self.go_home()
        if rect != c.perch_rect and not c.perch_follow(rect):
            self.go_home()                        # it went right up to the top of the screen

    def tick(self) -> None:
        c = self.companion
        if c.drone or c.hidden:
            if c.perched and c.hidden:
                c.leave_perch()                 # (the drone takes her off it itself)
            self.hwnd = None
            self._follow.stop()
            return
        if c.busy_elsewhere:
            return
        if self.hwnd is not None and not c.perched:   # something else took her home
            self.hwnd = None
            self._follow.stop()
        if self.hwnd is not None and self.rect_of(self.hwnd) is None:
            log.info("perch: her window is gone - back to the panel")
            return self.go_home()
        try:
            front = self.front()
        except Exception:
            front = None
        # Her window went behind another one (Discord maximised over Spotify): she'd be sitting on an
        # edge you can't see. Onto the window you're using if she can sit on it, else home.
        if self.hwnd is not None and self._is_covered():
            self._covered_looks += 1
            if self._covered_looks >= COVERED_LOOKS:
                self._covered_looks = 0
                log.info("perch: her window is covered - moving")
                if front is not None and front[0] != self.hwnd and c.can_perch(front[1]):
                    return self._hop(*front)
                return self.go_home()
        else:
            self._covered_looks = 0
        if front is not None and front[0] != self._skip:
            self._skip = None                   # you've used another window since dragging her off
        if front is not None and front[0] != self.hwnd and front[0] != self._skip and c.can_perch(front[1]):
            self._seen = self._seen + 1 if front[0] == self._candidate else 1
            self._candidate = front[0]
            if self._seen >= SETTLE_LOOKS:
                return self._hop(*front)
        else:
            self._candidate, self._seen = None, 0
        if self.hwnd is not None:
            self.follow()

    def _is_covered(self) -> bool:
        try:
            return bool(self.covered(self.hwnd))
        except Exception:
            return False

    def _hop(self, hwnd: int, rect: QRect) -> None:
        c = self.companion
        was = c.content_geometry().center()
        self._candidate, self._seen = None, 0
        if not c.perch_on(rect):
            return
        self.hwnd = hwnd
        log.info("perch: sitting on a window at %s", rect.getRect())
        self._flash(was, c.content_geometry().center())
        self._follow.start()

    def go_home(self) -> None:
        c = self.companion
        self.hwnd = None
        self._follow.stop()
        if not c.perched:
            return
        was = c.content_geometry().center()
        c.leave_perch()
        if c.character.isVisible():
            self._flash(was, c.content_geometry().center())

    def _flash(self, a: QPoint, b: QPoint) -> None:
        if a != b:
            self.flashes[0].fire(a)
            self.flashes[1].fire(b)


# -- Windows plumbing ---------------------------------------------------------------------------------
def _sittable(hwnd: int) -> QRect | None:
    """The window's visible rectangle (Qt's coordinates) if she can sit on it, else None:
    it must exist, be visible, not minimised / maximised / full screen / cloaked, and not hers."""
    import ctypes
    from ctypes import wintypes
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    if not hwnd or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return None
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return None
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow"):
        return None
    if user32.GetWindowLongW(hwnd, -20) & 0x80:                       # WS_EX_TOOLWINDOW: popups, tooltips
        return None
    cloaked = wintypes.DWORD()
    if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
        return None                                                    # a hidden store app / other desktop
    r = wintypes.RECT()
    if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:   # the visible frame
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    if r.right - r.left < 200 or r.bottom - r.top < 120:
        return None

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    if user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
        m = info.rcMonitor
        if r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom:
            return None                                                # full screen
    from .screen_spots import to_logical
    return to_logical((r.left, r.top, r.right, r.bottom))


def front_window() -> tuple[int, QRect] | None:
    """The window you're using, if she can sit on it."""
    if sys.platform != "win32":
        return None
    import ctypes
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    rect = _sittable(hwnd)
    return (hwnd, rect) if rect is not None else None


def window_rect(hwnd: int) -> QRect | None:
    if sys.platform != "win32":
        return None
    return _sittable(hwnd)


def top_window() -> tuple[int, QRect] | None:
    """The window you're using - or, if that's hers (her menu was just open), the top window
    she can sit on."""
    if sys.platform != "win32":
        return None
    found = front_window()
    if found is not None:
        return found
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    hits: list[tuple[int, QRect]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user32.GetWindowTextLengthW(hwnd) > 0 and not user32.GetWindow(hwnd, 4):    # titled, no owner
            rect = _sittable(hwnd)
            if rect is not None:
                hits.append((hwnd, rect))
                return False                      # z-order: the first one is on top
        return True
    user32.EnumWindows(each, 0)
    return hits[0] if hits else None


def seat_covered(hwnd: int) -> bool:
    """Is the spot she sits on (the right part of the window's top edge) hidden under another window
    stacked above it? Her own windows, tooltips / popups and hidden windows don't count."""
    if sys.platform != "win32" or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi

    def frame(h: int) -> wintypes.RECT | None:
        r = wintypes.RECT()
        if dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0 and \
                not user32.GetWindowRect(h, ctypes.byref(r)):
            return None
        return r

    mine = frame(hwnd)
    if mine is None:
        return False
    y = mine.top + 6
    seat = [(x, y) for x in (mine.right - 220, mine.right - 140, mine.right - 60) if x > mine.left]
    me = os.getpid()
    above = user32.GetWindow(hwnd, 3)                   # GW_HWNDPREV: the next window up the stack
    for _ in range(400):
        if not above:
            return False
        if user32.IsWindowVisible(above) and not user32.IsIconic(above):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(above, ctypes.byref(pid))
            cloaked = wintypes.DWORD()
            hidden = dwm.DwmGetWindowAttribute(above, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 \
                and cloaked.value
            tool = user32.GetWindowLongW(above, -20) & 0x80                 # WS_EX_TOOLWINDOW
            r = frame(above) if pid.value != me and not hidden and not tool else None
            if r is not None and sum(r.left <= x < r.right and r.top <= y < r.bottom for x, y in seat) >= 2:
                return True
        above = user32.GetWindow(above, 3)
    return False
