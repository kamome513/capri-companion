""""Take a screenshot": every monitor (or just the window you're using - "screenshot this
window"), saved as a PNG in your Pictures\\Screenshots folder and copied to the clipboard.

She steps out of the picture for a moment (her windows hide while it's taken), then a quick
camera flash. Nothing is uploaded anywhere.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, QRect, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

from .overlay_window import OverlayWindow

log = logging.getLogger("capri")

HIDE_FOR = 220          # ms her windows are hidden before the capture (Windows needs a moment to repaint)
FLASH = 0.3


def screenshots_folder() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or Path.home() / "Pictures") / "Screenshots"


def virtual_screen() -> tuple[int, int, int, int] | None:
    """Every monitor together, in physical pixels (Windows)."""
    if sys.platform != "win32":
        return None
    import ctypes
    m = ctypes.windll.user32.GetSystemMetrics
    left, top = m(76), m(77)                     # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    return left, top, left + m(78), top + m(79)  # SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN


def _to_image(rgb: np.ndarray) -> QImage:
    h, w = rgb.shape[:2]
    rgba = np.dstack([rgb, np.full((h, w), 255, np.uint8)])
    return QImage(np.ascontiguousarray(rgba).tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


def _qt_grab() -> QImage:
    """Not Windows: every monitor through Qt (X11: the whole desktop in one go)."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QImage()
    g = screen.virtualGeometry()
    image = screen.grabWindow(0, g.x(), g.y(), g.width(), g.height()).toImage()
    return image if not image.isNull() else screen.grabWindow(0).toImage()


class _Flash(OverlayWindow):
    def __init__(self) -> None:
        super().__init__(True)
        self.set_click_through(True)
        self._start = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def fire(self, geometry: QRect) -> None:
        self.setGeometry(geometry)
        self._start = time.monotonic()
        self.show()
        self._timer.start()

    def _tick(self) -> None:
        if time.monotonic() - self._start > FLASH:
            self._timer.stop()
            self.hide()
        else:
            self.update()

    def paintEvent(self, event) -> None:
        k = (time.monotonic() - self._start) / FLASH
        if 0 <= k < 1:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(255, 255, 255, int(150 * (1 - k) ** 2)))
            p.end()


class Screenshotter(QObject):
    _saved = Signal(object, object)          # (callback, path or exception) - back on the UI thread

    def __init__(self, her_windows: Callable[[], list], window_rect: Callable[[], tuple | None] = lambda: None,
                 grab: Callable[[tuple], np.ndarray | None] | None = None, folder: Callable[[], Path] = screenshots_folder,
                 clipboard: bool = True, now: Callable[[], datetime] = datetime.now) -> None:
        super().__init__()
        self.her_windows, self.window_rect, self.folder, self.clipboard, self.now = \
            her_windows, window_rect, folder, clipboard, now
        if grab is None:
            from ..integrations.screen_click import grab as grab_rect
            grab = grab_rect
        self.grab = grab
        self.flashes: list[_Flash] = []
        self.busy = False
        self._saved.connect(lambda done, result: done(result))

    def take(self, which: str, done: Callable[[object], None]) -> None:
        """which = "screen" (every monitor) or "window" (the one you're using). done(path | Exception)."""
        if self.busy:
            return done(RuntimeError("already taking one"))
        self.busy = True
        hidden = [w for w in self.her_windows() if w is not None and w.isVisible()]
        for w in hidden:
            w.hide()
        QTimer.singleShot(HIDE_FOR, lambda: self._capture(which, hidden, done))

    def _capture(self, which: str, hidden: list, done: Callable[[object], None]) -> None:
        try:
            image = self._image(which)
        except Exception as exc:
            image = exc
        for w in hidden:
            w.show()
        self.busy = False
        if isinstance(image, Exception) or image.isNull():
            return done(image if isinstance(image, Exception) else OSError("couldn't capture the screen"))
        if self.clipboard:
            QGuiApplication.clipboard().setImage(image)
        self._flash()
        threading.Thread(target=self._save, args=(image, done), daemon=True).start()

    def _image(self, which: str) -> QImage:
        rect = self.window_rect() if which == "window" else virtual_screen()
        if which == "window" and rect is None:
            rect = virtual_screen()               # no window found: the whole screen instead
        if rect is not None:
            rgb = self.grab(rect)
            if rgb is not None:
                return _to_image(rgb)
        return _qt_grab()

    def _save(self, image: QImage, done: Callable[[object], None]) -> None:
        try:
            folder = self.folder()
            folder.mkdir(parents=True, exist_ok=True)
            stamp = self.now().strftime("%Y-%m-%d %H-%M-%S")
            path = folder / f"Capri screenshot {stamp}.png"
            n = 2
            while path.exists():
                path = folder / f"Capri screenshot {stamp} ({n}).png"
                n += 1
            if not image.save(str(path), "PNG"):
                raise OSError(f"couldn't save to {folder}")
            log.info("screenshot saved: %s", path)
            result: object = path
        except Exception as exc:
            result = exc
        self._saved.emit(done, result)

    def _flash(self) -> None:
        screens = QGuiApplication.screens()
        while len(self.flashes) < len(screens):
            self.flashes.append(_Flash())
        for flash, screen in zip(self.flashes, screens):
            flash.fire(screen.geometry())

