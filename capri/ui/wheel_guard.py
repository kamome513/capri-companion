"""Scrolling down a settings page never changes a setting (v2.3.2).

Qt gives the mouse wheel to whatever box is under the pointer, so scrolling past a drop-down, a number box or a
slider changed it. Now the wheel scrolls the page; a drop-down changes only when you open it, and a number box or
slider only after you've clicked it.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox,
                               QScrollBar, QWidget)


class WheelGuard(QObject):
    """(2.3.6: it caught the page's own scroll bars too, so a scroll bar handed the wheel to itself, again and
    again, until Capri crashed. Scroll bars are never guarded now, and it never hands the wheel on twice.)"""

    def __init__(self) -> None:
        super().__init__()
        self._passing = False

    def eventFilter(self, obj, event) -> bool:                                    # noqa: N802 (Qt name)
        if event.type() != QEvent.Type.Wheel or not isinstance(obj, QWidget) or isinstance(obj, QScrollBar):
            return False
        if self._passing:
            return False                                   # (already handing this one on: let it through)
        if not isinstance(obj, QComboBox) and obj.hasFocus():
            return False                                   # you clicked it: the wheel is for it now
        area = _page_of(obj)
        bar = area.verticalScrollBar() if area is not None else None
        if bar is not None and bar is not obj:
            self._passing = True
            try:
                QApplication.sendEvent(bar, event)
            finally:
                self._passing = False
        return True


def _page_of(widget: QWidget) -> QAbstractScrollArea | None:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea) and not isinstance(parent, QComboBox):
            return parent
        parent = parent.parentWidget()
    return None


_GUARD: WheelGuard | None = None


def guard(root: QWidget) -> int:
    """Protect every drop-down, number box and slider under `root` (safe to call again for new ones)."""
    global _GUARD
    if _GUARD is None:
        _GUARD = WheelGuard()
    count = 0
    for kind in (QComboBox, QAbstractSpinBox, QAbstractSlider):
        for box in root.findChildren(kind):
            if isinstance(box, QScrollBar):
                continue                                   # a scroll bar itself: it IS the scrolling
            if box.property("capri_wheel_guard"):
                continue
            box.setProperty("capri_wheel_guard", True)
            if not isinstance(box, QComboBox):
                box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)          # not focused by just hovering/scrolling
            box.installEventFilter(_GUARD)
            count += 1
    return count
