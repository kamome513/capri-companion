"""Capri's hands on a Linux desktop (X11): windows, keys, typing, clicks.

Everything goes through the X server with python-xlib: the window manager's standard
(EWMH) properties to find and move between windows, and the XTEST extension for key presses
and clicks - the same mechanism xdotool uses. No command line is ever built.

On Wayland, Capri runs through XWayland (run.sh / the AppImage set that up), so her own windows
can be placed; she can see and control other X11 / XWayland apps. Native Wayland apps can't be
read or typed into by any app (that's Wayland's design) - typing falls back to wtype / ydotool
when they're installed (see linux/desktop.py).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Iterable

MAX_WAIT = 0.6                  # seconds to wait for the window manager to do something

# Window types that aren't app windows (docks, desktop, menus...).
NOT_APP_TYPES = {"_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK", "_NET_WM_WINDOW_TYPE_TOOLBAR",
                 "_NET_WM_WINDOW_TYPE_MENU", "_NET_WM_WINDOW_TYPE_SPLASH", "_NET_WM_WINDOW_TYPE_NOTIFICATION",
                 "_NET_WM_WINDOW_TYPE_TOOLTIP", "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU",
                 "_NET_WM_WINDOW_TYPE_POPUP_MENU", "_NET_WM_WINDOW_TYPE_COMBO", "_NET_WM_WINDOW_TYPE_DND"}

# "ctrl+shift+m" names -> X keysym names.
MODIFIER_KEYSYMS = {"ctrl": "Control_L", "control": "Control_L", "shift": "Shift_L", "alt": "Alt_L",
                    "win": "Super_L", "super": "Super_L", "meta": "Super_L"}
NAMED_KEYSYMS = {"space": "space", "enter": "Return", "return": "Return", "tab": "Tab", "esc": "Escape",
                 "escape": "Escape", "backspace": "BackSpace", "insert": "Insert", "delete": "Delete",
                 "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next", "up": "Up",
                 "down": "Down", "left": "Left", "right": "Right", "pause": "Pause", "scrolllock": "Scroll_Lock",
                 "plus": "plus", "minus": "minus", "printscreen": "Print", "menu": "Menu"}
SPECIAL_CHARS = {"\t": "Tab", " ": "space"}
# Media keys (X11's XF86 keysyms, by value - python-xlib doesn't know these names).
XF86_KEYSYMS = {"XF86AudioPlay": 0x1008FF14, "XF86AudioPause": 0x1008FF31, "XF86AudioNext": 0x1008FF17,
                "XF86AudioPrev": 0x1008FF16, "XF86AudioRaiseVolume": 0x1008FF13,
                "XF86AudioLowerVolume": 0x1008FF11, "XF86AudioMute": 0x1008FF12}


def available() -> bool:
    """Is there an X server to talk to (an X11 session, or XWayland)?"""
    if not os.environ.get("DISPLAY"):
        return False
    import importlib.util
    return importlib.util.find_spec("Xlib") is not None


def keysym_for_char(ch: str) -> int:
    """The X keysym that types this character (any Unicode letter)."""
    from Xlib import XK
    if ch in SPECIAL_CHARS:
        return XK.string_to_keysym(SPECIAL_CHARS[ch])
    code = ord(ch)
    if 0x20 <= code <= 0x7E or 0xA0 <= code <= 0xFF:
        return code                                        # Latin-1: keysym == code point
    return 0x01000000 | code                               # every other Unicode character


class X11:
    """One connection to the X server. Thread-safe enough for Capri: one lock around every call."""

    def __init__(self, display=None) -> None:
        from Xlib import X, XK, display as xdisplay
        self.X = X
        self.d = display or xdisplay.Display()
        self.root = self.d.screen().root
        self._atoms: dict[str, int] = {}
        self._lock = threading.RLock()
        self.has_xtest = bool(self.d.query_extension("XTEST"))
        self.minimized: list[int] = []

    # -- properties ----------------------------------------------------------------------------
    def atom(self, name: str) -> int:
        if name not in self._atoms:
            self._atoms[name] = self.d.intern_atom(name)
        return self._atoms[name]

    def _win(self, wid: int):
        return self.d.create_resource_object("window", int(wid))

    def _prop(self, wid: int | None, name: str, kind=None):
        from Xlib import X
        try:
            win = self.root if wid is None else self._win(wid)
            p = win.get_full_property(self.atom(name), kind if kind is not None else X.AnyPropertyType)
            return p.value if p is not None else None
        except Exception:                       # the window went away meanwhile: nothing
            return None

    def _ints(self, wid: int | None, name: str) -> list[int]:
        v = self._prop(wid, name)
        try:
            return [int(x) for x in v] if v is not None else []
        except TypeError:
            return []

    def _atom_names(self, wid: int, name: str) -> set[str]:
        names = set()
        for a in self._ints(wid, name):
            try:
                names.add(self.d.get_atom_name(a))
            except Exception:
                pass
        return names

    # -- windows ---------------------------------------------------------------------------------
    def stacking(self) -> list[int]:
        """Every managed top-level window, bottom to top."""
        with self._lock:
            return self._ints(None, "_NET_CLIENT_LIST_STACKING") or self._ints(None, "_NET_CLIENT_LIST")

    def active(self) -> int:
        with self._lock:
            ids = self._ints(None, "_NET_ACTIVE_WINDOW")
            return ids[0] if ids else 0

    def pid(self, wid: int) -> int:
        with self._lock:
            ids = self._ints(wid, "_NET_WM_PID")
            return ids[0] if ids else 0

    def title(self, wid: int) -> str:
        with self._lock:
            v = self._prop(wid, "_NET_WM_NAME", self.atom("UTF8_STRING")) or self._prop(wid, "WM_NAME")
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace")
        return str(v or "")

    def wm_class(self, wid: int) -> tuple[str, str]:
        """(instance, class) - e.g. ("discord", "discord"), ("Navigator", "firefox")."""
        with self._lock:
            try:
                got = self._win(wid).get_wm_class()
            except Exception:
                got = None
        return (got[0] or "", got[1] or "") if got else ("", "")

    def states(self, wid: int) -> set[str]:
        with self._lock:
            return self._atom_names(wid, "_NET_WM_STATE")

    def types(self, wid: int) -> set[str]:
        with self._lock:
            return self._atom_names(wid, "_NET_WM_WINDOW_TYPE")

    def is_app_window(self, wid: int) -> bool:
        """A normal app window (what the taskbar shows): not a dock, menu, desktop or tool."""
        if self.types(wid) & NOT_APP_TYPES:
            return False
        if "_NET_WM_STATE_SKIP_TASKBAR" in self.states(wid):
            return False
        return True

    def is_minimized(self, wid: int) -> bool:
        return "_NET_WM_STATE_HIDDEN" in self.states(wid)

    def is_fullscreen(self, wid: int) -> bool:
        return "_NET_WM_STATE_FULLSCREEN" in self.states(wid)

    def geometry(self, wid: int) -> tuple[int, int, int, int] | None:
        """(left, top, right, bottom) on screen, including the window manager's frame."""
        with self._lock:
            try:
                win = self._win(wid)
                g = win.get_geometry()
                pos = win.translate_coords(self.root, 0, 0)
                x, y = -pos.x, -pos.y
                ext = self._ints(wid, "_NET_FRAME_EXTENTS") or [0, 0, 0, 0]
                left, right, top, bottom = (ext + [0, 0, 0, 0])[:4]
                return (x - left, y - top, x + g.width + right, y + g.height + bottom)
            except Exception:
                return None

    def windows(self, pids: Iterable[int] | None = None, names: Iterable[str] = (),
                include_minimized: bool = True) -> list[int]:
        """App windows, front-most first: of these processes (or, for sandboxed apps whose
        window reports a different process id, whose class matches one of `names`)."""
        me = os.getpid()
        wanted = set(pids) if pids is not None else None
        lowered = {n.lower().removesuffix(".exe") for n in names if n}
        found = []
        for wid in reversed(self.stacking()):
            pid = self.pid(wid)
            if pid == me or not self.is_app_window(wid):
                continue
            if not include_minimized and self.is_minimized(wid):
                continue
            if wanted is not None and pid not in wanted:
                inst, cls = self.wm_class(wid)
                if not lowered or not ({inst.lower(), cls.lower()} & lowered):
                    continue
            found.append(wid)
        return found

    def window_at(self, x: int, y: int) -> int | None:
        for wid in reversed(self.stacking()):
            if self.is_minimized(wid) or not self.is_app_window(wid):
                continue
            g = self.geometry(wid)
            if g and g[0] <= x < g[2] and g[1] <= y < g[3]:
                return wid
        return None

    # -- asking the window manager -------------------------------------------------------------
    def _client_message(self, wid: int, name: str, data: list[int]) -> None:
        from Xlib import X
        from Xlib.protocol import event
        ev = event.ClientMessage(window=self._win(wid), client_type=self.atom(name),
                                 data=(32, (data + [0] * 5)[:5]))
        mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
        self.root.send_event(ev, event_mask=mask)
        self.d.flush()

    def activate(self, wid: int, wait: float = MAX_WAIT) -> bool:
        """Bring a window to the front and give it the keyboard (un-minimising it). True if it worked."""
        with self._lock:
            try:
                self._client_message(wid, "_NET_ACTIVE_WINDOW", [2, self.X.CurrentTime, 0])
                win = self._win(wid)
                win.map()
                self.d.flush()
            except Exception:
                return False
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if self.active() == wid:
                return True
            time.sleep(0.02)
        return self.active() == wid

    def raise_window(self, wid: int) -> None:
        """Put one of Capri's own windows back on top, without giving it the keyboard."""
        from Xlib import X
        with self._lock:
            try:
                self._client_message(wid, "_NET_RESTACK_WINDOW", [2, 0, X.Above])
                self._win(wid).configure(stack_mode=X.Above)
                self.d.flush()
            except Exception:
                pass

    def minimize(self, wid: int) -> None:
        with self._lock:
            try:
                self._client_message(wid, "WM_CHANGE_STATE", [3])          # IconicState
            except Exception:
                pass

    def close(self, wid: int) -> None:
        """Like clicking the window's X."""
        with self._lock:
            try:
                self._client_message(wid, "_NET_CLOSE_WINDOW", [self.X.CurrentTime, 2])
            except Exception:
                pass

    # -- keys and the mouse (XTEST) ---------------------------------------------------------------
    def _need_xtest(self) -> None:
        if not self.has_xtest:
            raise OSError("this X server can't take key presses (no XTEST)")

    def _keycode(self, keysym: int) -> tuple[int, bool]:
        """(keycode, needs shift) for a keysym on the current keyboard layout; (0, False) if absent."""
        for code, index in self.d.keysym_to_keycodes(keysym):
            if index in (0, 1):
                return code, index == 1
        return 0, False

    def _fake(self, keycode: int, down: bool) -> None:
        from Xlib import X
        from Xlib.ext import xtest
        xtest.fake_input(self.d, X.KeyPress if down else X.KeyRelease, keycode)

    def press_keysyms(self, names: list[str], hold: float = 0.03) -> None:
        """Press keys together, e.g. ["Control_L", "Shift_L", "m"], then release them in reverse."""
        from Xlib import XK
        self._need_xtest()
        with self._lock:
            codes, borrowed = [], None
            for name in names:
                sym = XF86_KEYSYMS.get(name) or XK.string_to_keysym(name)
                if not sym and len(name) == 1:
                    sym = keysym_for_char(name)
                if not sym:
                    raise OSError(f"no key called {name!r}")
                code, _shift = self._keycode(sym)
                if not code and borrowed is None:          # e.g. no media keys on this keyboard: borrow one
                    spare = self._spare_keycode()
                    if spare:
                        self.d.change_keyboard_mapping(spare, [(sym, sym)])
                        self.d.sync()
                        time.sleep(0.02)
                        code, borrowed = spare, spare
                if not code:
                    raise OSError(f"no key for {name!r} on this keyboard")
                codes.append(code)
            try:
                for code in codes:
                    self._fake(code, True)
                    self.d.sync()
                    time.sleep(hold / 3)
                time.sleep(hold)
                for code in reversed(codes):
                    self._fake(code, False)
                    self.d.sync()
            finally:
                if borrowed is not None:
                    time.sleep(0.02)
                    self.d.change_keyboard_mapping(borrowed, [(0, 0)])
                    self.d.sync()

    def press_combo(self, combo: str) -> None:
        """'ctrl+shift+m' / 'f9' / 'XF86AudioPlay'."""
        self.press_keysyms(combo_keysyms(combo))

    def _spare_keycode(self) -> int:
        first = self.d.display.info.min_keycode
        count = self.d.display.info.max_keycode - first + 1
        mapping = self.d.get_keyboard_mapping(first, count)
        for offset in range(count - 1, -1, -1):           # from the top: usually unused
            if not any(mapping[offset]):
                return first + offset
        return 0

    def type_text(self, text: str, delay: float = 0.008) -> int:
        """Type text as key presses. Letters the layout doesn't have are typed through a spare key
        that's briefly given that letter (how xdotool does it). Returns how many characters went."""
        from Xlib import XK
        self._need_xtest()
        typed = 0
        shift = self._keycode(XK.string_to_keysym("Shift_L"))[0]
        with self._lock:
            spare = 0
            for ch in text:
                if ch in "\r\n":
                    continue                                   # she never presses Enter
                if ord(ch) < 0x20 and ch != "\t":
                    continue
                sym = keysym_for_char(ch)
                code, needs_shift = self._keycode(sym)
                remapped = False
                if not code:
                    spare = spare or self._spare_keycode()
                    if not spare:
                        continue
                    self.d.change_keyboard_mapping(spare, [(sym, sym)])
                    self.d.sync()
                    time.sleep(0.01)
                    code, needs_shift, remapped = spare, False, True
                if needs_shift and shift:
                    self._fake(shift, True)
                self._fake(code, True)
                self._fake(code, False)
                if needs_shift and shift:
                    self._fake(shift, False)
                self.d.sync()
                if remapped:
                    time.sleep(0.01)
                    self.d.change_keyboard_mapping(spare, [(0, 0)])
                    self.d.sync()
                typed += 1
                time.sleep(delay)
        return typed

    def click(self, x: int, y: int, button: int = 1, double: bool = False) -> None:
        from Xlib import X
        from Xlib.ext import xtest
        self._need_xtest()
        with self._lock:
            xtest.fake_input(self.d, X.MotionNotify, x=int(x), y=int(y))
            self.d.sync()
            time.sleep(0.03)
            for _ in range(2 if double else 1):
                xtest.fake_input(self.d, X.ButtonPress, button)
                self.d.sync()
                time.sleep(0.03)
                xtest.fake_input(self.d, X.ButtonRelease, button)
                self.d.sync()
                time.sleep(0.05)

    def scroll(self, up: bool, clicks: int = 5) -> None:
        from Xlib import X
        from Xlib.ext import xtest
        self._need_xtest()
        with self._lock:
            for _ in range(clicks):
                for kind in (X.ButtonPress, X.ButtonRelease):
                    xtest.fake_input(self.d, kind, 4 if up else 5)
                self.d.sync()
                time.sleep(0.02)

    def pointer(self) -> tuple[int, int]:
        with self._lock:
            p = self.root.query_pointer()
            return int(p.root_x), int(p.root_y)


def combo_keysyms(combo: str) -> list[str]:
    """'ctrl+shift+m' -> ['Control_L', 'Shift_L', 'm']. Raises ValueError for an unknown key."""
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty key combo")
    *mods, key = parts
    out = []
    for m in mods:
        if m.lower() not in MODIFIER_KEYSYMS:
            raise ValueError(f"unknown modifier '{m}'")
        out.append(MODIFIER_KEYSYMS[m.lower()])
    low = key.lower()
    if key.startswith("XF86"):
        out.append(key)
    elif len(key) == 1:
        out.append(low if key.isalpha() else key)
    elif low in NAMED_KEYSYMS:
        out.append(NAMED_KEYSYMS[low])
    elif low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
        out.append(f"F{int(low[1:])}")
    else:
        raise ValueError(f"unknown key '{key}'")
    return out


_shared: X11 | None = None
_shared_lock = threading.Lock()


def shared() -> X11 | None:
    """One X11 connection for the app (None when there's no X server)."""
    global _shared
    with _shared_lock:
        if _shared is None and available():
            try:
                _shared = X11()
            except Exception:
                _shared = None
        return _shared
