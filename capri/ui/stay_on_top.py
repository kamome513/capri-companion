"""Staying over your games.

Capri's windows are "always on top", but a full-screen game often makes *its* window always-on-top too -
and then Windows puts whichever was activated last in front: the game. So while a game (or anything
full screen) is in front, every 1.5 s she puts her visible windows back on top - without activating
them, so your game keeps the keyboard and mouse. Nothing happens the rest of the time.

A game in *exclusive* full screen draws straight to the screen and nothing can show over it; she says so
once (switch the game to borderless / windowed full screen to see her over it).
"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication

HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x0001, 0x0002, 0x0010, 0x0200


def win_topmost(hwnd: int) -> None:
    """Back to the top of the always-on-top windows, without taking focus. Windows only."""
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                      SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)


def on_top_windows() -> list:
    """Her visible always-on-top windows (her, the panel, the drone, cards...)."""
    return [w for w in QApplication.topLevelWidgets()
            if w.isVisible() and w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint]


class TopmostKeeper(QObject):
    INTERVAL_MS = 1500

    def __init__(self, front: Callable[[], object], in_game: Callable[[], bool] = lambda: False,
                 enabled: Callable[[], bool] = lambda: True, windows: Callable[[], list] = on_top_windows,
                 raise_one: Callable[[int], None] = win_topmost, note: Callable[[str], None] = lambda text: None) -> None:
        super().__init__()
        self.front, self.in_game, self.enabled, self.windows = front, in_game, enabled, windows
        self.raise_one, self.note = raise_one, note
        self._told_exclusive: set[int] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self.tick)

    def start(self) -> None:
        self._timer.start()

    def tick(self) -> bool:
        """Put her back on top if a game / full-screen app is in front. True if it did."""
        if not self.enabled():
            return False
        try:
            front = self.front()
        except Exception:
            front = None
        gaming = bool(front is not None and getattr(front, "fullscreen", False)) or self.in_game()
        if not gaming:
            return False
        pid = getattr(front, "pid", None)
        if front is not None and getattr(front, "d3d", False) and pid not in self._told_exclusive:
            self._told_exclusive.add(pid)
            self.note("This game's in exclusive full screen, so I can't show over it. "
                      "Set it to borderless (or windowed) full screen and I'll be there.")
        for window in self.windows():
            try:
                self.raise_one(int(window.winId()))
            except Exception:
                continue
        return True
