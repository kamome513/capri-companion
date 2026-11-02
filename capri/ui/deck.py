"""The settings window dressed as a cyberdeck: a stylesheet (black chassis, crimson trim, cyan
focus, monospace caps) and the deck's header plate.

The header is decoration plus real readouts only: every chip shows an actual setting
(voice, microphone, spoken replies, chatbot, how many apps she knows) - nothing made up.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme

RED = theme.MSG_RED.name()
CYAN = theme.MSG_CYAN.name()
GREEN = theme.GREEN.name()
MONO = ", ".join(f'"{f}"' for f in theme.MONO_FAMILIES)

STYLE = f"""
QDialog {{ background: #07070a; }}
QWidget {{ background: #07070a; color: #e4e4ea; font-size: 9pt; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: #07070a; }}
QTabWidget::pane {{ border: 1px solid #3a0d1c; border-top: 2px solid {RED}; background: #0a0a0e; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: #100c12; color: #8e8e9a; font-family: {MONO}; font-size: 8pt; font-weight: bold;
    padding: 7px 14px; margin-right: 3px; border: 1px solid #2a0e18; border-bottom: none;
    border-top-left-radius: 0; border-top-right-radius: 9px; }}
QTabBar::tab:hover {{ color: {CYAN}; border-color: #0d4250; }}
QTabBar::tab:selected {{ background: #1c0710; color: #ffffff; border-color: {RED}; }}
QLabel {{ background: transparent; }}
QLabel#hint {{ color: #7c7c88; }}
QLabel#result {{ color: {GREEN}; font-family: {MONO}; }}
QTableWidget, QListWidget, QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: #0e0e13; border: 1px solid #2a1420; selection-background-color: #4a0a22;
    selection-color: #ffffff; padding: 3px; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{ border: 1px solid {CYAN}; }}
QTableWidget {{ gridline-color: #1d1018; alternate-background-color: #111117; }}
QHeaderView::section {{
    background: #140a10; color: {CYAN}; border: 0; border-bottom: 1px solid #3a0d1c; padding: 5px;
    font-family: {MONO}; font-size: 8pt; font-weight: bold; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox QAbstractItemView {{ background: #0e0e13; border: 1px solid {RED}; selection-background-color: #4a0a22; }}
QPushButton {{
    background: #12080d; color: #f0f0f4; border: 1px solid {RED}; padding: 6px 14px;
    font-family: {MONO}; font-size: 8pt; font-weight: bold; }}
QPushButton:hover {{ color: {CYAN}; border-color: {CYAN}; background: #08171c; }}
QPushButton:pressed {{ background: {RED}; color: #000000; }}
QPushButton:disabled {{ color: #4c4c55; border-color: #2a1420; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid {RED}; background: #0e0e13; }}
QCheckBox::indicator:checked {{ background: {CYAN}; border-color: {CYAN}; }}
QCheckBox::indicator:hover {{ border-color: {CYAN}; }}
QRadioButton::indicator {{ width: 11px; height: 11px; border: 1px solid {RED}; border-radius: 6px; background: #0e0e13; }}
QRadioButton::indicator:checked {{ background: {CYAN}; }}
QSlider::groove:horizontal {{ height: 4px; background: #2a0e18; }}
QSlider::sub-page:horizontal {{ background: {RED}; }}
QSlider::handle:horizontal {{ width: 10px; margin: -6px 0; background: {CYAN}; }}
QGroupBox {{ border: 1px solid #2a1420; margin-top: 14px; padding-top: 10px; background: #0b0b0f; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {CYAN};
    font-family: {MONO}; font-size: 8pt; font-weight: bold; }}
QScrollBar:vertical {{ background: #0a0a0e; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #4a0a22; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {RED}; }}
QScrollBar:horizontal {{ background: #0a0a0e; height: 9px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #4a0a22; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QToolTip {{ background: #0e0e13; color: #e4e4ea; border: 1px solid {CYAN}; }}
"""


def slot_title(n: int, title: str) -> str:
    """A tab's name as a numbered deck slot: "01 // APPS"."""
    return f"{n:02d} // {title.replace('&&', '&').upper().replace('&', '&&')}"


class DeckHeader(QWidget):
    """The deck's top plate: name, version, and live chips for her real settings."""

    HEIGHT = 58

    def __init__(self, version: str, chips: Callable[[], list[tuple[str, bool]]]) -> None:
        super().__init__()
        self.version, self.chips = version, chips
        self.setFixedHeight(self.HEIGHT)
        self._title = QFont()
        self._title.setFamilies(theme.MONO_FAMILIES)
        self._title.setPixelSize(17)
        self._title.setBold(True)
        self._title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self._small = QFont()
        self._small.setFamilies(theme.MONO_FAMILIES)
        self._small.setPixelSize(9)
        self._small.setBold(True)
        self._small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -3)
        cut = 14
        plate = QPainterPath(QPointF(r.left(), r.top()))
        plate.lineTo(r.right() - cut, r.top())
        plate.lineTo(r.right(), r.top() + cut)
        plate.lineTo(r.right(), r.bottom())
        plate.lineTo(r.left() + cut, r.bottom())
        plate.lineTo(r.left(), r.bottom() - cut)
        plate.closeSubpath()
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, QColor(40, 6, 18))
        g.setColorAt(0.55, QColor(12, 8, 14))
        g.setColorAt(1, QColor(6, 14, 18))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(plate)
        p.save()
        p.setClipPath(plate)
        y = r.top()
        while y < r.bottom():                                   # scanlines
            p.fillRect(QRectF(r.left(), y, r.width(), 1), QColor(255, 255, 255, 7))
            y += 3
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(theme.MSG_RED, 1.2))
        p.drawPath(plate)
        p.fillRect(QRectF(r.left() + 10, r.bottom() - 2, 120, 2), theme.MSG_CYAN)    # trim
        # name plate
        p.setFont(self._title)
        p.setPen(QColor(245, 245, 248))
        p.drawText(QPointF(r.left() + 18, r.top() + 27), "CAPRI")
        x = r.left() + 18 + QFontMetrics(self._title).horizontalAdvance("CAPRI ")
        p.setPen(theme.MSG_RED)
        p.drawText(QPointF(x, r.top() + 27), "// DECK")
        p.setFont(self._small)
        p.setPen(QColor(130, 130, 142))
        p.drawText(QPointF(r.left() + 18, r.top() + 44), f"◢ COMPANION OS  v{self.version}")
        # chips: her real settings, right to left
        fm = QFontMetrics(self._small)
        cx = r.right() - 22
        for label, on in reversed(self.chips()):
            w = fm.horizontalAdvance(label) + 18
            chip = QRectF(cx - w, r.top() + 18, w, 20)
            colour = theme.MSG_CYAN if on else QColor(110, 110, 120)
            p.setPen(QPen(colour, 1))
            p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 26))
            p.drawRect(chip)
            p.fillRect(QRectF(chip.left() + 5, chip.center().y() - 2, 4, 4), colour)
            p.setPen(colour if on else QColor(150, 150, 160))
            p.drawText(chip.adjusted(13, 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), label)
            cx = chip.left() - 6
        p.end()
