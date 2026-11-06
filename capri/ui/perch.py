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
SIT_HEIGHT = {False: 220, True: 125}     # normal / compact (2.3.4: smaller - 300 was bigger than her standing)
FIGURE_HEIGHT = 250                      # her standing figure's height at size 100% (as in her own window)
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
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)   # frames on time
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
    """Her sitting on the window's edge (v2.3.2): her own full-body figure - the same as when she stands, storm
    hair and all - with her thighs resting along the edge and her shins hanging off it, swinging from the knee
    out of step. She blinks, and her mouth moves while she talks.

    Without her figure (another look), the old drawn sitting picture: each lower leg swinging from its knee."""

    def __init__(self, always_on_top: bool = True, compact: bool = False, art: Path = ART,
                 size: int = 100, figure: Callable[[], object] | None = None) -> None:
        super().__init__(always_on_top)
        self.art = art
        self.figure = figure or (lambda: None)          # -> her CharacterWindow (her rig, hair, voice level)
        info = json.loads((art / "sit.json").read_text())
        self.art_w, self.art_h = info["size"]
        self.knees = {"black": QPointF(*info["black_knee"]), "red": QPointF(*info["red_knee"])}
        self.seat = float(info["seat"])
        self.talking = False
        self._t0 = time.monotonic()
        self._scaled: dict = {}
        self._scaled_key = None
        self._rig_small = None
        self._rig_key = None
        self._geo = None                                 # (rig, figure height, box, edge) for the rig layout
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self.update)
        self.size_pct = size
        self.set_compact(compact, size)

    # -- which figure: her rig, or the old picture --------------------------------------------------------
    def _rig(self):
        ch = self.figure()
        rig = ch.full_rig() if ch is not None and hasattr(ch, "full_rig") else None
        return rig if rig is not None and rig.can_sit() else None

    def set_compact(self, compact: bool, size: int = 100) -> None:
        self.size_pct = size
        rig = self._rig()
        if rig is None:
            self._geo = None
            self.height_px = round(SIT_HEIGHT[compact] * size / 100)
            self.s = self.height_px / self.art_h
            self.setFixedSize(QSize(round(self.art_w * self.s) + PAD * 2, self.height_px + PAD * 2))
        else:
            fig_h = max(40, round(FIGURE_HEIGHT * size / 100))
            k = fig_h / rig.h
            head = rig.head
            pad, hh = head.width() * 1.35, head.height()
            reach = rig.shins["right"].height() * 0.3     # her feet swinging out
            left = min(0.0, head.left() - pad)
            right = max(rig.w + rig.sit_side() + reach, head.right() + pad)
            top = head.top() - hh * 1.8
            bottom = rig.sit_feet_y() + 6
            origin = QPointF((-left) * k + 4, (-top) * k + 4)          # the figure's (0, 0) in the window
            self._geo = (rig, fig_h, k, origin)
            self.height_px = round((bottom - top) * k)
            self.setFixedSize(QSize(round((right - left) * k) + 8, self.height_px + 8))
        self.update()

    def refresh(self) -> None:
        """Her look, hair or size changed: lay her out again."""
        self._rig_small = self._rig_key = None
        self.set_compact(False, self.size_pct)

    def set_talking(self, on: bool) -> None:
        self.talking = on

    def seat_point(self) -> QPoint:
        """Where on the window she sits: the window's top edge goes through this point."""
        if self._geo is not None:
            rig, _h, k, origin = self._geo
            knee = rig.sit_knee("right")
            return QPoint(round(origin.x() + knee.x() * k), round(origin.y() + rig.sit_edge_y() * k))
        return QPoint(round(PAD + self.knees["black"].x() * self.s), round(PAD + self.seat * self.s))

    def content_rect(self) -> QRect:
        if self._geo is not None:
            rig, _h, k, origin = self._geo
            box = rig.sit_box()
            return QRect(round(origin.x() + box.x() * k), round(origin.y() + box.y() * k),
                         round(box.width() * k), round(box.height() * k))
        return QRect(PAD, PAD, round(self.art_w * self.s), self.height_px)

    def showEvent(self, event) -> None:
        if (self._rig() is None) != (self._geo is None):
            self.refresh()                              # her look changed while she wasn't sitting
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        self._scaled, self._scaled_key = {}, None          # nothing kept while she isn't sitting
        self._rig_small = self._rig_key = None
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

    def kicks(self, t: float) -> tuple[float, float]:
        """Her shins' swing (-1..1, black leg, red leg) at time t: out of step, livelier while she talks."""
        black, red, _breath = self.pose(t)
        return black / 10.0, red / 3.2 * 0.55

    def paintEvent(self, event) -> None:
        rig = self._rig()
        if (rig is None) != (self._geo is None) or (rig is not None and rig is not self._geo[0]):
            self.refresh()                              # her look or hair changed: lay her out again
            rig = self._rig()
        if self._geo is not None and rig is not None:
            return self._paint_rig()
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

    def _paint_rig(self) -> None:
        from .rig import Pose
        rig, fig_h, _k, origin = self._geo
        dpr = self.devicePixelRatioF()
        key = (fig_h, dpr, id(rig))
        if self._rig_key != key:                        # pre-scaled for this size and screen: sharp and quick
            self._rig_small, self._rig_key = rig.resized(max(8, round(fig_h * dpr))), key
        small = self._rig_small
        ch = self.figure()
        t = time.monotonic() - self._t0
        level = float(getattr(ch, "level", 0.0) or 0.0) if self.talking else 0.0
        wild = float(getattr(ch, "wild_hair", 0.7))
        blink = max(0.0, 1.0 - abs((t % 4.3) - 0.12) / 0.12)        # a blink every few seconds
        pose = Pose(sit=1.0, wild=wild, t=t, energy=level, blink=blink, mouth=min(1.0, level * 1.6))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(origin)
        p.scale(1 / dpr, 1 / dpr)
        small.paint_sitting(p, QPointF(0, 0), small.h, pose, self.kicks(t))
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


# -- Windows plumbing (Linux: below) ---------------------------------------------------------------------------------
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


# -- Linux plumbing (X11) ----------------------------------------------------------------------------
def _x():
    if not sys.platform.startswith("linux"):
        return None
    from ..linux import x11
    return x11.shared()


def _linux_sittable(x, wid: int) -> QRect | None:
    if not wid or x.pid(wid) == os.getpid() or not x.is_app_window(wid) or x.is_minimized(wid):
        return None
    states = x.states(wid)
    if "_NET_WM_STATE_FULLSCREEN" in states or {"_NET_WM_STATE_MAXIMIZED_VERT", "_NET_WM_STATE_MAXIMIZED_HORZ"} <= states:
        return None
    g = x.geometry(wid)
    if not g or g[2] - g[0] < 200 or g[3] - g[1] < 120:
        return None
    from .screen_spots import to_logical
    return to_logical(g)


def _linux_front() -> tuple[int, QRect] | None:
    x = _x()
    if x is None:
        return None
    wid = x.active()
    rect = _linux_sittable(x, wid)
    return (wid, rect) if rect is not None else None


def _linux_top() -> tuple[int, QRect] | None:
    x = _x()
    if x is None:
        return None
    found = _linux_front()
    if found is not None:
        return found
    for wid in reversed(x.stacking()):
        rect = _linux_sittable(x, wid)
        if rect is not None:
            return wid, rect
    return None


def _linux_covered(wid: int) -> bool:
    x = _x()
    if x is None or not wid:
        return False
    mine = x.geometry(wid)
    if not mine:
        return False
    y = mine[1] + 6
    seat = [(px, y) for px in (mine[2] - 220, mine[2] - 140, mine[2] - 60) if px > mine[0]]
    order = x.stacking()                                  # bottom to top
    if wid not in order:
        return False
    me = os.getpid()
    for above in order[order.index(wid) + 1:]:
        if x.pid(above) == me or x.is_minimized(above) or not x.is_app_window(above):
            continue
        r = x.geometry(above)
        if r and sum(r[0] <= px < r[2] and r[1] <= py < r[3] for px, py in seat) >= 2:
            return True
    return False


def front_window() -> tuple[int, QRect] | None:
    """The window you're using, if she can sit on it."""
    if sys.platform.startswith("linux"):
        return _linux_front()
    if sys.platform != "win32":
        return None
    import ctypes
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    rect = _sittable(hwnd)
    return (hwnd, rect) if rect is not None else None


def window_rect(hwnd: int) -> QRect | None:
    if sys.platform.startswith("linux"):
        x = _x()
        return _linux_sittable(x, hwnd) if x is not None else None
    if sys.platform != "win32":
        return None
    return _sittable(hwnd)


def top_window() -> tuple[int, QRect] | None:
    """The window you're using - or, if that's hers (her menu was just open), the top window
    she can sit on."""
    if sys.platform.startswith("linux"):
        return _linux_top()
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
    if sys.platform.startswith("linux"):
        return _linux_covered(hwnd)
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
