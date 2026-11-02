"""System-wide keyboard shortcuts (Windows RegisterHotKey).

Works while any other app has focus, needs no admin rights, and never
sees any other keystrokes - Windows only tells us when *our* combo is pressed.
"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtWidgets import QWidget

SUPPORTED = sys.platform == "win32"

MODIFIERS = {"alt": 0x0001, "ctrl": 0x0002, "control": 0x0002, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "pause": 0x13, "scrolllock": 0x91, "plus": 0xBB, "minus": 0xBD,
}


def parse(combo: str) -> tuple[int, int]:
    """'ctrl+alt+c' -> (modifier flags, virtual-key code). Raises ValueError."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    *mods, key = parts
    flags = 0
    for mod in mods:
        if mod not in MODIFIERS:
            raise ValueError(f"unknown modifier '{mod}'")
        flags |= MODIFIERS[mod]
    if not flags:
        raise ValueError("a hotkey needs at least one of ctrl/alt/shift/win")
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in NAMED_KEYS:
        vk = NAMED_KEYS[key]
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"unknown key '{key}'")
    return flags, vk


def pretty(combo: str) -> str:
    return "+".join(p.strip().capitalize() for p in combo.split("+"))


class HotkeyManager(QWidget):
    """An invisible native window that receives WM_HOTKEY messages."""

    def __init__(self) -> None:
        super().__init__(None)
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1
        if SUPPORTED:
            self.winId()   # create the native window without ever showing it

    def register(self, combo: str, callback: Callable[[], None]) -> str | None:
        """Register a hotkey. Returns an error message, or None on success."""
        if not SUPPORTED:
            return "global hotkeys are only available on Windows"
        try:
            mods, vk = parse(combo)
        except ValueError as exc:
            return f"bad hotkey '{combo}': {exc}"
        import ctypes
        hotkey_id = self._next_id
        if not ctypes.windll.user32.RegisterHotKey(int(self.winId()), hotkey_id, mods | MOD_NOREPEAT, vk):
            return f"{pretty(combo)} is already used by another app"
        self._next_id += 1
        self._callbacks[hotkey_id] = callback
        return None

    def unregister_all(self) -> None:
        if SUPPORTED:
            import ctypes
            for hotkey_id in self._callbacks:
                ctypes.windll.user32.UnregisterHotKey(int(self.winId()), hotkey_id)
        self._callbacks.clear()

    def nativeEvent(self, event_type, message):
        name = event_type.data() if hasattr(event_type, "data") else bytes(event_type)
        if SUPPORTED and bytes(name) == b"windows_generic_MSG":
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self._callbacks:
                self._callbacks[msg.wParam]()
                return True, 0
        return False, 0
