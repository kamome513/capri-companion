"""Colours and fonts matching the black terminal panel in the reference."""

from PySide6.QtGui import QColor, QFont

PANEL_BG = QColor(10, 10, 12, 242)
PANEL_BORDER = QColor(132, 76, 255)
PANEL_GLOW = QColor(132, 76, 255, 55)
TEXT_TITLE = QColor(242, 242, 244)
TEXT_HEADER = QColor(226, 226, 230)
TEXT_DIM = QColor(118, 118, 126)
TEXT_LOG = QColor(196, 196, 200)
GREEN = QColor(57, 230, 107)
# The status panel as a cyberpunk message
MSG_RED = QColor(236, 16, 70)
MSG_CYAN = QColor(0, 226, 255)
MSG_GLOW = QColor(236, 16, 70, 60)
MSG_BG_TOP = QColor(22, 6, 12, 240)
MSG_BG_BOTTOM = QColor(6, 6, 10, 245)
MSG_SCANLINE = QColor(255, 255, 255, 9)
ALERT = QColor(255, 54, 92)
BADGE_TEXT = QColor(6, 10, 6)
ICON_FRAME = QColor(48, 48, 54)

MONO_FAMILIES = ["Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", "Courier New"]
SANS_FAMILIES = ["Segoe UI Semibold", "Segoe UI", "Inter", "DejaVu Sans", "Arial"]


def mono(point_size: float, bold: bool = False, spacing: float = 0.0) -> QFont:
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(point_size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def sans(point_size: float, bold: bool = True) -> QFont:
    font = QFont()
    font.setFamilies(SANS_FAMILIES)
    font.setPointSizeF(point_size)
    font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return font


MENU_STYLE = f"""
QMenu {{
    background: #0a0a0c;
    color: #e6e6ea;
    border: 1px solid {PANEL_BORDER.name()};
    font-family: {", ".join(f'"{f}"' for f in MONO_FAMILIES)};
    font-size: 9pt;
    padding: 4px;
}}
QMenu::item {{ padding: 4px 18px 4px 10px; }}
QMenu::item:selected {{ background: #1b1430; color: {GREEN.name()}; }}
QMenu::item:disabled {{ color: #55555c; }}
QMenu::separator {{ height: 1px; background: #2c2440; margin: 4px 6px; }}
"""
