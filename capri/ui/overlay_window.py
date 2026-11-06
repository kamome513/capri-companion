"""Base class for Capri's frameless, transparent, always-on-top windows."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget


class OverlayWindow(QWidget):
    """A borderless tool window with a per-pixel transparent background.

    * ``Tool`` keeps it out of the taskbar and Alt+Tab.
    * ``WindowDoesNotAcceptFocus`` / ``WA_ShowWithoutActivating`` stop it
      stealing keyboard focus from games when it appears or updates.
    * ``set_click_through(True)`` makes Windows pass *every* click through.

    Left-dragging emits ``drag_started``, then ``drag_moved`` with the cursor
    offset since the press; the Companion decides where both windows go.
    """

    context_menu_requested = Signal(QPoint)
    drag_started = Signal()
    drag_moved = Signal(QPoint)
    drag_finished = Signal()
    clicked = Signal(QPoint)                 # a click without a drag (global position)
    file_dropped = Signal(str)               # a file dragged onto her and let go (its path) - she reads it (2.3.4)

    def __init__(self, always_on_top: bool = True) -> None:
        super().__init__(None)
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setAutoFillBackground(False)
        self._press: QPoint | None = None      # global cursor pos at press
        self._dragging = False

    # -- window flags --------------------------------------------------------
    def _set_flag(self, flag: Qt.WindowType, on: bool) -> None:
        if bool(self.windowFlags() & flag) == on:
            return
        visible = self.isVisible()
        self.setWindowFlag(flag, on)   # Qt hides the window when flags change...
        if visible:
            self.show()                # ...so put it back.

    def set_always_on_top(self, on: bool) -> None:
        self._set_flag(Qt.WindowType.WindowStaysOnTopHint, on)

    def set_click_through(self, on: bool) -> None:
        self._set_flag(Qt.WindowType.WindowTransparentForInput, on)

    # -- mouse ----------------------------------------------------------------
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu_requested.emit(event.globalPos())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.globalPosition().toPoint() - self._press
        if not self._dragging and delta.manhattanLength() < QApplication.startDragDistance():
            return
        if not self._dragging:
            self._dragging = True
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.drag_started.emit()
        self.drag_moved.emit(delta)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return super().mouseReleaseEvent(event)
        was_dragging = self._dragging
        self._press, self._dragging = None, False
        self.unsetCursor()
        if was_dragging:
            self.drag_finished.emit()
        else:
            self.clicked.emit(event.globalPosition().toPoint())

    # -- a file dropped on her: she reads it ---------------------------------------------------------------
    @staticmethod
    def _dropped_file(event) -> str:
        data = event.mimeData()
        if data is None or not data.hasUrls():
            return ""
        files = [u.toLocalFile() for u in data.urls() if u.isLocalFile()]
        return files[0] if files else ""

    def dragEnterEvent(self, event) -> None:                    # noqa: N802 (Qt name)
        if self._dropped_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:                     # noqa: N802
        if self._dropped_file(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:                         # noqa: N802
        path = self._dropped_file(event)
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)
