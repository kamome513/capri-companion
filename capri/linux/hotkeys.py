"""System-wide keyboard shortcuts on Linux (X11 key grabs).

Like Windows' RegisterHotKey: the X server tells Capri only when *her* combo is pressed, whatever
app has the keyboard - she never sees any other keystrokes. Num Lock / Caps Lock don't get in the
way (each combo is grabbed with and without them).

On Wayland, apps can't grab keys outside their own windows. There, bind a shortcut in your
desktop's keyboard settings to `capri --listen` (or the AppImage with --listen): it tells the running
Capri to listen, exactly like push-to-talk.
"""

from __future__ import annotations

import select
import threading
from typing import Callable

from .x11 import combo_keysyms

LOCK_VARIANTS = (0, 2, 16, 18)            # none, Caps Lock, Num Lock, both
MODIFIER_MASKS = {"Control_L": 4, "Shift_L": 1, "Alt_L": 8, "Super_L": 64}


def parse(combo: str) -> tuple[int, str]:
    """'ctrl+alt+c' -> (X modifier mask, key's keysym name). Raises ValueError."""
    names = combo_keysyms(combo)
    *mods, key = names
    mask = 0
    for m in mods:
        mask |= MODIFIER_MASKS[m]
    if not mask:
        raise ValueError("a hotkey needs at least one of ctrl/alt/shift/win")
    return mask, key


class X11Hotkeys:
    """Grabs on the root window, read on a background thread. `fire(id)` is called on that thread."""

    def __init__(self, fire: Callable[[int], None], display=None) -> None:
        from Xlib import X, XK, display as xdisplay
        self.X, self.XK = X, XK
        self.d = display or xdisplay.Display()
        self.root = self.d.screen().root
        self.fire = fire
        self.grabs: dict[tuple[int, int], int] = {}        # (keycode, mask) -> id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="capri-hotkeys")
        self._thread.start()

    def register(self, combo: str, hotkey_id: int) -> str | None:
        from Xlib import error
        try:
            mask, key = parse(combo)
        except ValueError as exc:
            return f"bad hotkey '{combo}': {exc}"
        sym = self.XK.string_to_keysym(key) or (ord(key) if len(key) == 1 else 0)
        code = self.d.keysym_to_keycode(sym) if sym else 0
        if not code:
            return f"no key for '{key}' on this keyboard"
        failed = error.CatchError(error.BadAccess)
        for extra in LOCK_VARIANTS:
            self.root.grab_key(code, mask | extra, True, self.X.GrabModeAsync, self.X.GrabModeAsync, onerror=failed)
        self.d.sync()
        if failed.get_error():
            for extra in LOCK_VARIANTS:
                self.root.ungrab_key(code, mask | extra)
            self.d.sync()
            return f"{combo} is already used by another app"
        self.grabs[(code, mask)] = hotkey_id
        return None

    def unregister_all(self) -> None:
        for code, mask in list(self.grabs):
            for extra in LOCK_VARIANTS:
                self.root.ungrab_key(code, mask | extra)
        self.grabs.clear()
        self.d.sync()

    def _loop(self) -> None:
        fd = self.d.fileno()
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([fd], [], [], 0.5)
                if not ready and not self.d.pending_events():
                    continue
                while self.d.pending_events():
                    ev = self.d.next_event()
                    if ev.type == self.X.KeyPress:
                        mask = ev.state & ~(2 | 16) & 0xFF            # ignore Caps / Num Lock
                        hotkey_id = self.grabs.get((ev.detail, mask))
                        if hotkey_id is not None:
                            self.fire(hotkey_id)
            except Exception:
                if self._stop.wait(1.0):
                    return

    def stop(self) -> None:
        self._stop.set()
        try:
            self.unregister_all()
            self.d.close()
        except Exception:
            pass
