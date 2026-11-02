"""Notices when you're typing, so the mic picking up your keyboard (or you muttering while you
type) isn't taken as something said to Capri.

Only runs while she listens *without* the wake word (a follow-up in a conversation, an answer
to her question, search mode). It never sees which keys you press: a few times a second it
asks Windows when the PC last had any input (GetLastInputInfo) and where the mouse is. Input
while the mouse stayed put means keys (or clicks). Moving the mouse alone doesn't count.
"""

from __future__ import annotations

import sys
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer

SAMPLE_MS = 150


def _windows_input() -> tuple[Callable[[], int], Callable[[], tuple[int, int]]] | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    user32 = ctypes.windll.user32

    def last_input() -> int:
        info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
        user32.GetLastInputInfo(ctypes.byref(info))
        return int(info.dwTime)

    def cursor() -> tuple[int, int]:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    return last_input, cursor


class TypingWatch(QObject):
    def __init__(self, last_input: Callable[[], int] | None = None, cursor: Callable[[], tuple[int, int]] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        if last_input is None or cursor is None:
            found = _windows_input()
            if found is not None:
                last_input, cursor = found
        self.last_input, self.cursor, self.clock = last_input, cursor, clock
        self.typed_at = -1e9
        self._seen: tuple[int, tuple[int, int]] | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(SAMPLE_MS)
        self._timer.timeout.connect(self.sample)

    @property
    def available(self) -> bool:
        return self.last_input is not None

    def start(self) -> None:
        if not self.available:
            return
        self._seen = None
        self.sample()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def sample(self) -> None:
        if not self.available:
            return
        try:
            now = (self.last_input(), self.cursor())
        except Exception:
            return
        if self._seen is not None and now[0] != self._seen[0] and now[1] == self._seen[1]:
            self.typed_at = self.clock()                # input, but the mouse didn't move: keys / clicks
        self._seen = now

    def typed_within(self, seconds: float) -> bool:
        self.sample()
        return self.clock() - self.typed_at <= seconds
