"""Finding Spotify's big green Play button by looking at the screen, and clicking it.

Used when Windows UI Automation can't see Spotify's buttons (Spotify only shows them to
accessibility tools some of the time). On a track page the Play button is a filled green
circle with a black triangle in the middle - nothing else on the page looks like that
(the green heart is too small, album art is square and has no hole).

Only ever clicks that one button, inside Spotify's own window, then puts your mouse back
and gives the focus back to the window you were in.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable

import numpy as np

log = logging.getLogger("capri")

MIN_SIZE, MAX_SIZE = 28, 140      # the button is 56 px at 100% scaling, 112 px at 200%
PLAYER_BAR = 130                  # the player bar along the bottom has its own (white) Play button


def green_mask(rgb: np.ndarray) -> np.ndarray:
    """Spotify green (#1ED760, and its hover shade)."""
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    return (g > 160) & (r < 110) & (b < 150) & (g - r > 90) & (g - b > 60)


def _blobs(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Connected green regions: (x0, y0, x1, y1, pixels). Coarse rows-of-runs labelling - the
    green parts of a Spotify page are small, so this stays quick."""
    h, w = mask.shape
    labels = np.zeros((h, w), np.int32)
    parent = [0]

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    prev: list[tuple[int, int, int]] = []
    for y in range(h):
        xs = np.flatnonzero(mask[y])
        runs: list[tuple[int, int, int]] = []
        if len(xs):
            cuts = np.flatnonzero(np.diff(xs) > 1)
            for s, e in zip(np.r_[xs[0], xs[cuts + 1]], np.r_[xs[cuts], xs[-1]]):
                label = 0
                for ps, pe, pl in prev:
                    if ps <= e + 1 and pe >= s - 1:
                        if label == 0:
                            label = find(pl)
                        else:
                            a, b = find(label), find(pl)
                            if a != b:
                                parent[b] = a
                if label == 0:
                    parent.append(len(parent))
                    label = len(parent) - 1
                labels[y, s:e + 1] = label
                runs.append((int(s), int(e), label))
        prev = runs
    roots = np.array([find(i) for i in range(len(parent))])
    labels = roots[labels]
    out = []
    for lab in np.unique(labels):
        if lab == 0:
            continue
        ys, xs = np.nonzero(labels == lab)
        out.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1, len(xs)))
    return out


def find_play_button(rgb: np.ndarray) -> tuple[int, int] | None:
    """Centre of the big green round Play button in a screenshot of Spotify's window, or None."""
    h, w = rgb.shape[:2]
    usable = rgb[: max(1, h - PLAYER_BAR)]
    mask = green_mask(usable)
    if not mask.any():
        return None
    best = None
    for x0, y0, x1, y1, n in _blobs(mask):
        bw, bh = x1 - x0, y1 - y0
        if not (MIN_SIZE <= bw <= MAX_SIZE and MIN_SIZE <= bh <= MAX_SIZE and 0.8 <= bw / bh <= 1.25):
            continue
        fill = n / (bw * bh)
        if not 0.5 <= fill <= 0.86:                    # a disc (0.785) less its triangle; art is ~1.0
            continue
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        core = mask[cy - bh // 10: cy + bh // 10 + 1, cx - bw // 10: cx + bw // 10 + 1]
        if core.mean() > 0.5:                          # the play triangle in the middle isn't green
            continue
        if best is None or bw * bh > best[0]:
            best = (bw * bh, cx, cy)
    return (best[1], best[2]) if best else None


class _Notes:
    """Steps for the Test Spotify report (logged as "spotify: ..." lines too)."""

    def __init__(self, into: list[str]) -> None:
        self.into = into

    def append(self, text: str) -> None:
        self.into.append(text)
        log.info("spotify: %s", text)


# -- Windows: grab the window, click the button --------------------------------------------------------
def grab(rect: tuple[int, int, int, int]) -> np.ndarray | None:
    """Screenshot of a screen rectangle (physical pixels) as an RGB array."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    screen = user32.GetDC(0)
    dc = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    try:
        gdi32.SelectObject(dc, bmp)
        gdi32.BitBlt(dc, 0, 0, w, h, screen, left, top, 0x00CC0020 | 0x40000000)   # SRCCOPY | CAPTUREBLT

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]
        info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(info), 0):
            return None
        bgra = np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4)
        return bgra[..., 2::-1].copy()                 # BGR(A) -> RGB
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(0, screen)


def monitor_of(hwnd: int) -> tuple[int, int, int, int] | None:
    """The monitor a window is on (physical pixels: left, top, right, bottom). Windows only."""
    if sys.platform != "win32" or not hwnd:
        return None
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)          # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    if not monitor or not user32.GetMonitorInfoW(wintypes.HANDLE(monitor), ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return r.left, r.top, r.right, r.bottom


def grab_window(hwnd: int) -> np.ndarray | None:
    """A window's own picture (PrintWindow, full content) as RGB: works for GPU-drawn apps (browsers,
    Discord, many games in borderless mode) that a plain screenshot sometimes gets black. Windows only."""
    if sys.platform != "win32" or not hwnd:
        return None
    import ctypes
    from ctypes import wintypes
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0 or w * h > 8192 * 8192:
        return None
    screen = user32.GetDC(0)
    dc = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    try:
        gdi32.SelectObject(dc, bmp)
        if not user32.PrintWindow(wintypes.HWND(hwnd), dc, 2):          # PW_RENDERFULLCONTENT
            return None

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]
        info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(info), 0):
            return None
        bgra = np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4)
        return bgra[..., 2::-1].copy()
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(0, screen)


def click_at(x: int, y: int) -> None:
    """A left click at a screen point (physical pixels); the mouse goes back where it was."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    was = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(was))
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    down, up = button_events("left")                  # your left button, even if Windows swaps them
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.SetCursorPos(was.x, was.y)


def _covered(desktop, x: int, y: int, hwnd: int, pids: list[int]) -> bool:
    """True when another app's window sits over (x, y) - a click there would hit that app.
    Capri's own overlay doesn't count (her figure lets clicks through her transparent parts)."""
    import os
    if not hasattr(desktop, "window_at"):
        return False
    try:
        top = desktop.window_at(x, y)
        return bool(top) and top != hwnd and desktop.pid_of(top) not in (*pids, os.getpid())
    except Exception:
        return False


def click_spotify_play(desktop, pids: list[int], notes: list[str] | None = None) -> bool:
    """Bring Spotify's window up, find the track page's green Play button on screen, click it,
    then give the focus back. False if the button couldn't be seen."""
    notes = _Notes(notes if notes is not None else [])
    if sys.platform != "win32" or desktop is None:
        return False
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = desktop.main_window(pids) if hasattr(desktop, "main_window") else None
    if not hwnd:
        notes.append("screen: no Spotify window")
        return False
    previous = user32.GetForegroundWindow()
    if user32.IsIconic(hwnd):
        user32.ShowWindowAsync(hwnd, 9)                # SW_RESTORE
        time.sleep(0.6)
    if not desktop.bring_to_front(hwnd):
        notes.append("screen: Spotify wouldn't come to the front - not clicking anything")
        return False
    time.sleep(0.5)
    if user32.GetForegroundWindow() != hwnd:       # something jumped in front: a click would hit it
        notes.append("screen: Spotify isn't in front any more - not clicking")
        return False
    rect = desktop.hwnd_rect(hwnd)
    shot = grab(rect) if rect else None
    if shot is None:
        notes.append("screen: couldn't capture Spotify's window")
        return False
    spot = find_play_button(shot)
    if spot is None:
        notes.append("screen: no green Play button visible on Spotify's page")
        return False
    x, y = rect[0] + spot[0], rect[1] + spot[1]
    if user32.GetForegroundWindow() != hwnd or _covered(desktop, x, y, hwnd, pids):
        notes.append("screen: something is covering Spotify's Play button - not clicking")
        return False
    notes.append(f"screen: green Play button at {x},{y} - clicking it")
    click_at(x, y)
    time.sleep(0.3)
    if previous and previous != hwnd:
        user32.SetForegroundWindow(previous)           # back to what you were doing
    return True


# -- more hands on your screen ("highlight the word ...", "right click ...", "scroll down") -------------
LEFT_EVENTS, RIGHT_EVENTS = (0x0002, 0x0004), (0x0008, 0x0010)


def buttons_swapped() -> bool:
    """Windows' "switch primary and secondary buttons" (left-handed mouse). Simulated clicks
    follow the swap, so without this her left click would come out as a right click."""
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetSystemMetrics(23))      # SM_SWAPBUTTON


def button_events(which: str) -> tuple[int, int]:
    """(down, up) mouse_event flags for your primary ("left") / secondary ("right") button."""
    primary = which == "left"
    if buttons_swapped():
        primary = not primary
    return LEFT_EVENTS if primary else RIGHT_EVENTS


def _mouse(event: int, data: int = 0) -> None:
    import ctypes
    ctypes.windll.user32.mouse_event(event, 0, 0, data, 0)


def _cursor() -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _move(x: int, y: int) -> None:
    import ctypes
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def drag_select(rect: tuple[int, int, int, int]) -> None:
    """Highlight text: press at its left edge, drag to its right edge, let go (physical pixels).
    The mouse goes back where it was; the selection stays."""
    left, top, right, bottom = rect
    y = (top + bottom) // 2
    was = _cursor()
    _move(left + 1, y)
    time.sleep(0.05)
    down, up = button_events("left")
    _mouse(down)
    for k in range(1, 9):                                 # a real drag, in steps, so apps see it
        _move(left + 1 + (right - left - 2) * k // 8, y)
        time.sleep(0.015)
    _mouse(up)
    time.sleep(0.05)
    _move(*was)


def double_click_at(x: int, y: int) -> None:
    was = _cursor()
    _move(x, y)
    time.sleep(0.05)
    down, up = button_events("left")
    for _ in range(2):
        _mouse(down)
        time.sleep(0.02)
        _mouse(up)
        time.sleep(0.05)
    _move(*was)


def right_click_at(x: int, y: int) -> None:
    """Right click (the menu opens there; the mouse stays so you can pick from it)."""
    _move(x, y)
    time.sleep(0.05)
    down, up = button_events("right")
    _mouse(down)
    time.sleep(0.04)
    _mouse(up)


def scroll_at(x: int, y: int, notches: int) -> None:
    """Mouse-wheel scroll over a point: notches > 0 = up."""
    was = _cursor()
    _move(x, y)
    time.sleep(0.03)
    for _ in range(abs(notches)):
        _mouse(0x0800, 120 if notches > 0 else -120)      # MOUSEEVENTF_WHEEL, one notch
        time.sleep(0.02)
    _move(*was)


class ScreenHands:
    """What "highlight / double click / right click / scroll" do with the mouse (Windows)."""

    def __init__(self, window_rect: Callable[[], tuple | None]) -> None:
        self.window_rect = window_rect

    def select(self, target) -> None:
        """The app's own selection when she found the words in its text (exact, any length),
        else a mouse drag across them."""
        native = getattr(target.element, "select_text", None)
        if native is not None:
            try:
                native()
                return
            except Exception as exc:
                log.info("highlight: the app wouldn't select it (%s) - dragging over it", exc)
        drag_select(target.rect)

    def double(self, target) -> None:
        double_click_at(*target.center)

    def right(self, target) -> None:
        right_click_at(*target.center)

    def scroll(self, notches: int) -> None:
        rect = self.window_rect()
        x, y = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2) if rect else _cursor()
        scroll_at(x, y, notches)
