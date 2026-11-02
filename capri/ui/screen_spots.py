"""Where things are on screen, for her lightning to aim at: an app's taskbar button
(found through Windows UI Automation), and converting Windows' physical pixels to
Qt's scaled ones."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

from ..commands.fuzzy import similarity

log = logging.getLogger("capri")


def taskbar_icon(ui, name: str) -> QRect | None:
    """Where `name`'s taskbar button is, in Qt's (logical) screen coordinates. None = not there.
    Falls back to the Start button, so she always has somewhere to land."""
    if sys.platform != "win32" or ui is None:
        return None
    import ctypes
    user32 = ctypes.windll.user32
    best, start = None, None
    for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        hwnd = user32.FindWindowW(cls, None)
        if not hwnd:
            continue
        try:
            buttons = ui.buttons(hwnd, with_rects=True)
        except Exception:
            continue
        for b in buttons:
            if not b.rect or b.rect[2] <= b.rect[0]:
                continue
            label = b.name.split(" - ")[0].strip()       # "Discord - 1 running window"
            if label.lower() == "start" and start is None:
                start = b.rect
            score = similarity(name, label) if label else 0.0
            if score >= 0.78 and (best is None or score > best[0]):
                best = (score, b.rect, b.name)
    if best:
        log.info("teleport: %s -> taskbar button %r", name, best[2])
    else:
        log.info("teleport: no taskbar button for %s%s", name, ", using Start" if start else "")
    rect = best[1] if best else start
    return _to_logical(rect) if rect else None


def _to_logical(rect: tuple[int, int, int, int]) -> QRect:
    """UI Automation reports physical pixels; Qt windows are placed in scaled ones.
    Qt keeps each screen's top-left corner where Windows has it and scales from there,
    so a second monitor's origin must not be scaled (that sent her lightning to the wrong spot)."""
    left, top, right, bottom = rect
    for screen in QGuiApplication.screens():
        g, dpr = screen.geometry(), screen.devicePixelRatio()
        native = QRect(g.x(), g.y(), round(g.width() * dpr), round(g.height() * dpr))
        if native.contains(QPoint((left + right) // 2, (top + bottom) // 2)):
            return QRect(round(g.x() + (left - native.x()) / dpr), round(g.y() + (top - native.y()) / dpr),
                         round((right - left) / dpr), round((bottom - top) / dpr))
    return QRect(left, top, right - left, bottom - top)


# -- lightning ---------------------------------------------------------------------------------------


def to_logical(rect: tuple[int, int, int, int]) -> QRect:
    return _to_logical(rect)
