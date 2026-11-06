"""2.3.4: she naps while you're away, and tells you when your PC is running out of memory or disk space.

* NapWatch - no mouse or keyboard for a while (Settings: nap_minutes): she closes her eyes and little z's drift up.
  Any input and she's awake. Never while you're in a game, while she's busy, or while she's talking.
* PcWarnings - every few minutes: memory nearly full (two looks in a row) or the system drive nearly full. Each
  warning at most every few hours, never mid-game, never in quiet mode.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer

log = logging.getLogger("capri")


def idle_seconds_source() -> Callable[[], float] | None:
    """How long since the last mouse / keyboard input, in seconds - or None where she can't tell."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        kernel32.GetTickCount.restype = wintypes.DWORD

        def idle() -> float:
            info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
            if not user32.GetLastInputInfo(ctypes.byref(info)):
                return 0.0
            return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0
        return idle
    if sys.platform.startswith("linux"):
        try:
            from Xlib import display
            from Xlib.ext import screensaver  # noqa: F401 - registers query_info
            d = display.Display()
            if not d.has_extension("MIT-SCREEN-SAVER"):
                return None
            root = d.screen().root

            def idle_x() -> float:
                return root.screensaver_query_info().idle / 1000.0
            return idle_x
        except Exception:
            return None
    return None


class NapWatch(QObject):
    CHECK_MS = 5000
    AWAKE_AFTER = 3.0          # seconds since your last input that count as "you're back"

    def __init__(self, idle: Callable[[], float] | None, minutes: Callable[[], int],
                 may_nap: Callable[[], bool], set_napping: Callable[[bool], None]) -> None:
        super().__init__()
        self.idle, self.minutes, self.may_nap, self.set_napping = idle, minutes, may_nap, set_napping
        self.napping = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_MS)
        self._timer.timeout.connect(self.check)
        if idle is not None:
            self._timer.start()

    def check(self) -> None:
        if self.idle is None:
            return
        try:
            away = self.idle()
        except Exception:
            return
        limit = max(0, int(self.minutes() or 0)) * 60
        if self.napping and (away < self.AWAKE_AFTER or not self.may_nap() or limit == 0):
            self._set(False)
        elif not self.napping and limit and away >= limit and self.may_nap():
            self._set(True)

    def _set(self, on: bool) -> None:
        self.napping = on
        log.info("nap: %s", "asleep" if on else "awake")
        self.set_napping(on)


def gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


class PcWarnings(QObject):
    CHECK_MS = 5 * 60 * 1000
    EVERY = 4 * 3600           # the same warning again after this long at the soonest
    MEMORY = 93.0              # % used
    DISK_GB = 5.0              # free on the system drive
    DISK_PCT = 4.0

    def __init__(self, enabled: Callable[[], bool], say: Callable[[str], None], psutil_module=None,
                 system_drive: str | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self.enabled, self.say, self.clock = enabled, say, clock
        self.ps = psutil_module
        self.drive = system_drive or ((__import__("os").environ.get("SystemDrive", "C:") + "\\")
                                      if sys.platform == "win32" else "/")
        self._last: dict[str, float] = {}
        self._high_memory = 0
        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()

    def _ps(self):
        if self.ps is None:
            import psutil
            self.ps = psutil
        return self.ps

    def check(self) -> None:
        if not self.enabled():
            self._high_memory = 0
            return
        try:
            ps = self._ps()
            mem = ps.virtual_memory()
            disk = ps.disk_usage(self.drive)
        except Exception as exc:
            log.info("pc warnings: couldn't look (%s)", exc)
            return
        self._high_memory = self._high_memory + 1 if mem.percent >= self.MEMORY else 0
        if self._high_memory >= 2:
            self._warn("memory", f"Your PC's almost out of memory ({mem.percent:.0f}% used). Closing an app or "
                                 f"a few browser tabs would help - ask me “why is my PC slow?” to see what's using it.")
        free_pct = 100.0 * disk.free / disk.total if disk.total else 100.0
        if disk.free < self.DISK_GB * 1024 ** 3 or free_pct < self.DISK_PCT:
            where = self.drive.rstrip("\\/") or "/"
            self._warn("disk", f"Your {where} drive is nearly full: {gb(disk.free)} left. Games and updates can "
                               f"fail when it runs out.")

    def _warn(self, what: str, text: str) -> None:
        now = self.clock()
        if now - self._last.get(what, -1e12) < self.EVERY:
            return
        self._last[what] = now
        self.say(text)
