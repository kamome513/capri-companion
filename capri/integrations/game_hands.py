"""Her hands in a game: holding keys (to walk, jump, sprint), clicking, and turning the camera with the mouse.

Games read the keyboard differently from normal apps, so on Windows the keys go in as hardware scan codes
(SendInput with KEYEVENTF_SCANCODE - what DirectInput / raw-input games see), and camera turns as relative mouse
movement. On Linux it's X11's XTEST (what any X11 / XWayland game sees).

Only the keys in ALLOWED can ever be pressed - letters, digits, space, shift, ctrl, tab, arrows and a few game
keys. No Windows key, no Alt, no Enter (chat), no Escape (that's yours: it stops her), no key combos (one key at
a time), so nothing here can close a window, open a menu outside the game or type into a chat.
"""

from __future__ import annotations

import sys
import time

ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789") | {"space", "shift", "ctrl", "tab", "up", "down", "left",
                                                          "right", "f", "e", "q", "r"}
MAX_HOLD = 3.0            # seconds a key can be held in one go
MAX_LOOK = 600            # pixels a camera turn can move in one go

# Windows: set-1 scan codes
SCAN = {**{c: code for c, code in zip("qwertyuiop", range(0x10, 0x1A))},
        **{c: code for c, code in zip("asdfghjkl", range(0x1E, 0x27))},
        **{c: code for c, code in zip("zxcvbnm", range(0x2C, 0x33))},
        "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
        "space": 0x39, "shift": 0x2A, "ctrl": 0x1D, "tab": 0x0F,
        "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D}
EXTENDED = {"up", "down", "left", "right"}
XK_NAMES = {"space": "space", "shift": "Shift_L", "ctrl": "Control_L", "tab": "Tab", "up": "Up", "down": "Down",
            "left": "Left", "right": "Right"}


def _wait(seconds: float, escape) -> None:
    """Hold for `seconds` - but let go the moment you press Esc."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if escape():
            return
        time.sleep(min(0.05, max(0.0, end - time.monotonic())))


def _turning(seconds: float, look: tuple[int, int], nudge, escape) -> None:
    """Spread a camera turn over `seconds` (while a key is held): smooth steering, not one jerk."""
    end = time.monotonic() + seconds
    steps = max(1, int(seconds / 0.03))
    dx, dy = look
    done_x = done_y = 0
    for i in range(1, steps + 1):
        if escape():
            return
        want_x, want_y = round(dx * i / steps), round(dy * i / steps)
        nudge(want_x - done_x, want_y - done_y)
        done_x, done_y = want_x, want_y
        time.sleep(max(0.0, min(0.03, end - time.monotonic())))
    _wait(max(0.0, end - time.monotonic()), escape)


def clean_key(key: str) -> str | None:
    """A key she may press, normalised ("Space" -> "space", "W" -> "w"), or None."""
    k = (key or "").strip().lower()
    k = {"spacebar": "space", "lshift": "shift", "control": "ctrl", "arrowup": "up", "arrowdown": "down",
         "arrowleft": "left", "arrowright": "right"}.get(k, k)
    return k if k in ALLOWED else None


class WindowsGameHands:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.user32 = ctypes, ctypes.windll.user32

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]
        self.KEYBDINPUT, self.MOUSEINPUT, self.INPUT = KEYBDINPUT, MOUSEINPUT, INPUT
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

    def _send(self, *inputs) -> None:
        arr = (self.INPUT * len(inputs))(*inputs)
        self.user32.SendInput(len(inputs), arr, self.ctypes.sizeof(self.INPUT))

    def _key(self, key: str, up: bool):
        flags = 0x0008 | (0x0002 if up else 0) | (0x0001 if key in EXTENDED else 0)   # SCANCODE | KEYUP | EXTENDED
        inp = self.INPUT(type=1)
        inp.u.ki = self.KEYBDINPUT(0, SCAN[key], flags, 0, 0)
        return inp

    def hold(self, key: str, seconds: float, look: tuple[int, int] = (0, 0)) -> None:
        """Hold a key that long - turning the camera at the same time if `look` isn't (0, 0) (walk and steer)."""
        self._send(self._key(key, False))
        try:
            if look != (0, 0):
                _turning(max(0.03, min(MAX_HOLD, seconds)), look, self._nudge, self.escape_pressed)
            else:
                _wait(max(0.03, min(MAX_HOLD, seconds)), self.escape_pressed)
        finally:
            self._send(self._key(key, True))

    def _nudge(self, dx: int, dy: int) -> None:
        inp = self.INPUT(type=0)
        inp.u.mi = self.MOUSEINPUT(int(dx), int(dy), 0, 0x0001, 0, 0)                    # MOUSEEVENTF_MOVE
        self._send(inp)

    def press(self, button: str = "left", hold: float = 0.0) -> None:
        """Press a mouse button where the pointer is - in a first-person game that's the crosshair (mining in
        Minecraft: hold it). The pointer isn't moved: that would turn the camera."""
        down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
        inp = self.INPUT(type=0)
        inp.u.mi = self.MOUSEINPUT(0, 0, 0, down, 0, 0)
        self._send(inp)
        try:
            _wait(max(0.05, min(MAX_HOLD, hold)), self.escape_pressed)
        finally:
            inp = self.INPUT(type=0)
            inp.u.mi = self.MOUSEINPUT(0, 0, 0, up, 0, 0)
            self._send(inp)

    def pointer_hidden(self) -> bool:
        """The game has hidden the mouse pointer: it's steering the camera with it (Minecraft, shooters...)."""
        ctypes = self.ctypes
        from ctypes import wintypes

        class CURSORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hCursor", wintypes.HANDLE),
                        ("ptScreenPos", wintypes.POINT)]
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if not self.user32.GetCursorInfo(ctypes.byref(info)):
            return False
        return not (info.flags & 0x0001)                                                  # CURSOR_SHOWING

    def look(self, dx: int, dy: int) -> None:
        """Turn the camera: relative mouse movement, in a few small steps (games read deltas)."""
        steps = max(1, int(max(abs(dx), abs(dy)) / 40))
        for i in range(steps):
            inp = self.INPUT(type=0)
            inp.u.mi = self.MOUSEINPUT(int(dx / steps), int(dy / steps), 0, 0x0001, 0, 0)    # MOUSEEVENTF_MOVE
            self._send(inp)
            time.sleep(0.01)

    def click(self, x: int, y: int, button: str = "left", hold: float = 0.0) -> None:
        """Click there; hold > 0 keeps the button down that long (mining, attacking)."""
        self.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.03)
        down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
        for i, flag in enumerate((down, up)):
            inp = self.INPUT(type=0)
            inp.u.mi = self.MOUSEINPUT(0, 0, 0, flag, 0, 0)
            self._send(inp)
            time.sleep(max(0.05, min(MAX_HOLD, hold)) if i == 0 else 0.03)

    def escape_pressed(self) -> bool:
        return bool(self.user32.GetAsyncKeyState(0x1B) & 0x8000)


class LinuxGameHands:
    def __init__(self, x11=None) -> None:
        from ..linux import x11 as x11mod
        self.x = x11 or x11mod.shared()
        if self.x is None:
            raise OSError("no X11 display")
        from Xlib import X, XK
        from Xlib.ext import xtest
        self.X, self.XK, self.xtest = X, XK, xtest

    def _code(self, key: str) -> int:
        name = XK_NAMES.get(key, key)
        return self.x.d.keysym_to_keycode(self.XK.string_to_keysym(name))

    def hold(self, key: str, seconds: float, look: tuple[int, int] = (0, 0)) -> None:
        code = self._code(key)
        if not code:
            return
        self.xtest.fake_input(self.x.d, self.X.KeyPress, code)
        self.x.d.sync()
        try:
            if look != (0, 0):
                _turning(max(0.03, min(MAX_HOLD, seconds)), look, self._nudge, self.escape_pressed)
            else:
                _wait(max(0.03, min(MAX_HOLD, seconds)), self.escape_pressed)
        finally:
            self.xtest.fake_input(self.x.d, self.X.KeyRelease, code)
            self.x.d.sync()

    def look(self, dx: int, dy: int) -> None:
        steps = max(1, int(max(abs(dx), abs(dy)) / 40))
        for _ in range(steps):
            self.xtest.fake_input(self.x.d, self.X.MotionNotify, True, x=int(dx / steps), y=int(dy / steps))
            self.x.d.sync()
            time.sleep(0.01)

    def _nudge(self, dx: int, dy: int) -> None:
        self.xtest.fake_input(self.x.d, self.X.MotionNotify, True, x=int(dx), y=int(dy))
        self.x.d.sync()

    def press(self, button: str = "left", hold: float = 0.0) -> None:
        number = 1 if button == "left" else 3
        self.xtest.fake_input(self.x.d, self.X.ButtonPress, number)
        self.x.d.sync()
        try:
            _wait(max(0.05, min(MAX_HOLD, hold)), self.escape_pressed)
        finally:
            self.xtest.fake_input(self.x.d, self.X.ButtonRelease, number)
            self.x.d.sync()

    @staticmethod
    def pointer_hidden() -> bool:
        return False                      # (X11 doesn't say; the AI's "mine" / "use" moves press in place anyway)

    def click(self, x: int, y: int, button: str = "left", hold: float = 0.0) -> None:
        number = 1 if button == "left" else 3
        self.xtest.fake_input(self.x.d, self.X.MotionNotify, x=int(x), y=int(y))
        self.xtest.fake_input(self.x.d, self.X.ButtonPress, number)
        self.x.d.sync()
        time.sleep(max(0.05, min(MAX_HOLD, hold)))
        self.xtest.fake_input(self.x.d, self.X.ButtonRelease, number)
        self.x.d.sync()

    def escape_pressed(self) -> bool:
        keys = self.x.d.query_keymap()
        code = self.x.d.keysym_to_keycode(self.XK.string_to_keysym("Escape"))
        return bool(keys[code // 8] & (1 << (code % 8)))


def game_hands():
    if sys.platform == "win32":
        return WindowsGameHands()
    if sys.platform.startswith("linux"):
        return LinuxGameHands()
    raise OSError("not on this system")
