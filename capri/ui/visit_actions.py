"""What Capri dashes over to zap: an app's minimise button, or a folder's entry in File Explorer.

The looking-up (Windows UI Automation) runs off the UI thread; the show and the action
run on it. If a button can't be found she zaps the window itself and the action still
happens the normal way - nothing depends on the show working.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRect, Signal

from .screen_spots import to_logical

log = logging.getLogger("capri")

MINIMISE_NAMES = {"Minimize", "Minimise"}
EXPLORER_CLASS = "CabinetWClass"
EXPLORER_WAIT = 5.0          # seconds for the new Explorer window to show up


class _Bridge(QObject):
    run = Signal(object)


class VisitActions:
    def __init__(self, visit, desktop, ui, open_item: Callable[[str], None]) -> None:
        self.visit, self.desktop, self.ui, self.open_item = visit, desktop, ui, open_item
        self._bridge = _Bridge()
        self._bridge.run.connect(lambda fn: fn())

    def _later(self, work: Callable[[], object], then: Callable[[object], None]) -> None:
        def run() -> None:
            try:
                result = work()
            except Exception as exc:
                log.info("visit: lookup failed: %s", exc)
                result = None
            self._bridge.run.emit(lambda: then(result))
        threading.Thread(target=run, daemon=True).start()

    def _named(self, hwnd: int, names: set[str], leftmost: bool = False) -> QRect | None:
        found = [b for b in self.ui.buttons(hwnd, names, with_rects=True)
                 if getattr(b, "rect", None) and b.rect[2] - b.rect[0] > 2 and b.rect[0] > -10000]
        if not found:
            return None
        pick = min(found, key=lambda b: b.rect[0]) if leftmost else found[0]
        self._picked = pick
        return to_logical(pick.rect)

    # -- "minimise Discord" ----------------------------------------------------------------------
    def minimize(self, name: str, pids: list[int], then: Callable[[], None]) -> None:
        def look():
            hwnd = self.desktop.main_window(pids)
            if hwnd is None:
                return None
            window = self.desktop.hwnd_rect(hwnd)
            button = self._named(hwnd, MINIMISE_NAMES)
            log.info("visit: %s minimise button %s", name, "found" if button else "not found")
            return (button, to_logical(window) if window else None)

        def go(found) -> None:
            if not found or not (found[0] or found[1]):
                return then()
            button, window = found
            target = button or QRect(window.right() - 140, window.top(), 46, 32)   # where it usually is
            self.visit.visit(target, then, window=window, near=True)   # up beside the button, wherever it is
        self._later(look, go)

    # -- "go into downloads" -----------------------------------------------------------------------
    def open_folder(self, label: str, path: str) -> None:
        """Open File Explorer, dash over, zap the folder in its sidebar - which opens it."""
        before = set(self.desktop.windows_of_class(EXPLORER_CLASS))
        self.open_item(self.desktop_explorer())
        self._picked = None

        def look():
            deadline = time.monotonic() + EXPLORER_WAIT
            while time.monotonic() < deadline:
                new = [h for h in self.desktop.windows_of_class(EXPLORER_CLASS) if h not in before]
                if new:
                    hwnd = new[0]
                    time.sleep(0.6)                                    # let its sidebar fill in
                    window = self.desktop.hwnd_rect(hwnd)
                    item = None
                    for _ in range(6):
                        item = self._named(hwnd, {label}, leftmost=True)
                        if item:
                            break
                        time.sleep(0.3)
                    log.info("visit: Explorer %s entry %s", label, "found" if item else "not found")
                    return (item, to_logical(window) if window else None, self._picked)
                time.sleep(0.15)
            return None

        def go(found) -> None:
            if not found:
                return self.open_item(path)                           # no new window: just open it
            item, window, element = found

            def select() -> None:
                try:
                    if element is not None:
                        element.press()                               # Explorer goes to that folder
                        return
                except Exception as exc:
                    log.info("visit: couldn't select %s: %s", label, exc)
                self.open_item(path)
            self.visit.visit(item or QRect(window.left() + 20, window.top() + 120, 160, 28), select, window=window,
                             near=True)
        self._later(look, go)

    @staticmethod
    def desktop_explorer() -> str:
        import os
        return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe")
