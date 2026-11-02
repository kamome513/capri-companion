"""The Night City call look, shared by the chat window and the call cards above her panel:

    Capri                                                   You
    [(CALL)]  her line, in amber...           what you said  [(CALL)]
    ‾‾‾                                                       ‾‾‾

A name above a square call icon (her colour / yours, scanlines, "(CALL)" and a little bar),
the line in amber beside it. Hers on the left, yours on the right; "..." while she thinks.
The colours come from the chat skin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen



@dataclass(frozen=True)
class CallColors:
    name: str = "#4fd8c4"          # the names above the icons
    her: str = "#c4142f"           # her call icon
    you: str = "#2f9e44"           # yours
    text: str = "#d9a93b"          # the lines
    dim: str = "#8a8a96"


def fonts(scale: float = 1.0) -> tuple[QFont, QFont, QFont]:
    """(name, line, CALL) fonts."""
    name = QFont()
    name.setFamilies(["Rajdhani", "Bahnschrift", "Segoe UI Semibold", "DejaVu Sans"])
    name.setPixelSize(round(17 * scale))
    name.setBold(True)
    line = QFont(name)
    line.setPixelSize(round(16 * scale))
    line.setBold(False)
    call = QFont()
    call.setFamilies(["Bahnschrift SemiBold Condensed", "Arial Narrow", "DejaVu Sans Condensed", "Arial"])
    call.setPixelSize(round(15 * scale))
    call.setBold(True)
    return name, line, call


def paint_icon(p: QPainter, r: QRectF, colour: QColor, call_font: QFont, pulse: float = 0.0) -> None:
    """The square call icon: colour, scanlines, "( CALL )", and a short bar at the bottom."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.fillRect(r, colour)
    p.setClipRect(r)
    y = r.top()
    while y < r.bottom():                                       # TV lines, like her panel
        p.fillRect(QRectF(r.left(), y, r.width(), 1.0), QColor(0, 0, 0, 52))
        p.fillRect(QRectF(r.left(), y + 1.0, r.width(), 1.0), QColor(255, 255, 255, 14))
        y += 3
    p.setClipping(False)
    light = QColor(255, 255, 255)
    tint = QColor(colour).lighter(185)
    c = r.center()
    p.setFont(call_font)
    fm = QFontMetricsF(call_font)
    word = "CALL"
    tw = fm.horizontalAdvance(word)
    p.setPen(light)
    p.drawText(QPointF(c.x() - tw / 2, c.y() + fm.capHeight() / 2), word)
    # the "( )" around it, a little brighter while it rings
    arc = QRectF(c.x() - tw / 2 - r.width() * 0.13, c.y() - r.height() * 0.24, tw + r.width() * 0.26, r.height() * 0.48)
    pen = QPen(tint, max(1.5, r.width() / 22), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    pen.setColor(QColor(tint.red(), tint.green(), tint.blue(), int(200 + 55 * pulse)))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(arc.left(), arc.top(), arc.height() * 0.7, arc.height()), 100 * 16, 160 * 16)
    p.drawArc(QRectF(arc.right() - arc.height() * 0.7, arc.top(), arc.height() * 0.7, arc.height()), -80 * 16, 160 * 16)
    # the little bar under it
    p.fillRect(QRectF(r.left() + r.width() * 0.12, r.bottom() - r.height() * 0.12, r.width() * 0.5,
                      max(1.5, r.height() / 30)), QColor(255, 255, 255, 190))
    p.restore()


@dataclass
class Row:
    who: str                       # "capri" / "you"
    text: str
    typing: bool = False           # "..." while she thinks


ICON = 64                          # call square size at scale 1 (the chat window uses a smaller one)


def layout(row: Row, width: float, scale: float = 1.0, icon: float | None = None,
           plate: bool = False) -> tuple[float, list[str]]:
    """(height, wrapped lines) of a row at this width."""
    name_f, line_f, _ = fonts(scale)
    icon = (icon or ICON) * scale
    room = max(60.0, width - icon - (18 + (24 if plate else 0)) * scale)
    lines = _wrap("..." if row.typing else row.text, QFontMetricsF(line_f), room)
    name_h = QFontMetricsF(name_f).height()
    text_h = len(lines) * QFontMetricsF(line_f).height()
    return name_h + max(icon, text_h + (22 if plate else 8) * scale) + 10 * scale, lines


def _wrap(text: str, fm: QFontMetricsF, room: float) -> list[str]:
    out: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            test = f"{line} {word}".strip()
            if fm.horizontalAdvance(test) <= room or not line:
                line = test
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or [""]


def paint_row(p: QPainter, row: Row, top: float, width: float, colours: CallColors, scale: float = 1.0,
              left: float = 0.0, t: float = 0.0, shadow: bool = False, icon: float | None = None,
              plate: bool = False) -> float:
    """Draw one row at `top`; returns its height. plate = the line sits on a little glass plate
    like her message panel (the chat window); without, it floats on your wallpaper (call cards)."""
    name_f, line_f, call_f = fonts(scale)
    height, lines = layout(row, width, scale, icon, plate)
    icon_size = (icon or ICON) * scale
    icon = icon_size
    if icon_size < 56 * scale:                                   # smaller squares: smaller "CALL"
        call_f.setPixelSize(max(9, round(call_f.pixelSize() * icon_size / (ICON * scale))))
    name_h = QFontMetricsF(name_f).height()
    mine = row.who == "you"
    icon_r = QRectF(left + width - icon - 2 if mine else left + 2, top + name_h + 2, icon, icon)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    # name above the icon
    p.setFont(name_f)
    name = "You" if mine else "Capri"
    nw = QFontMetricsF(name_f).horizontalAdvance(name)
    _text(p, QPointF(icon_r.right() - nw if mine else icon_r.left(), top + name_h * 0.8), name,
          QColor(colours.name), shadow)
    pulse = 0.5 + 0.5 * math.sin(t * 5) if row.typing else 0.0
    paint_icon(p, icon_r, QColor(colours.you if mine else colours.her), call_f, pulse)
    # the line beside it
    p.setFont(line_f)
    fm = QFontMetricsF(line_f)
    if row.typing:
        dots = "." * (1 + int(t * 3) % 3)
        _text(p, QPointF(icon_r.right() + 14 * scale, icon_r.top() + fm.ascent() + 4 * scale), dots,
              QColor(colours.dim), shadow)
        return height
    pad = 12 * scale if plate else 0.0
    y = icon_r.top() + fm.ascent() + 4 * scale + (pad * 0.6 if plate else 0)
    widest = max((fm.horizontalAdvance(line) for line in lines), default=0.0)
    if plate:
        box_w = widest + pad * 2
        bx = icon_r.left() - 10 * scale - box_w if mine else icon_r.right() + 10 * scale
        box = QRectF(bx, icon_r.top(), box_w, len(lines) * fm.height() + pad * 1.4)
        _plate(p, box, QColor(colours.you if mine else colours.her), mine, scale)
    for line in lines:
        lw = fm.horizontalAdvance(line)
        if plate:
            x = box.left() + pad if not mine else box.right() - pad - lw
        else:
            x = icon_r.left() - 14 * scale - lw if mine else icon_r.right() + 14 * scale
        _text(p, QPointF(x, y), line, QColor(colours.text), shadow)
        y += fm.height()
    return height


def _plate(p: QPainter, box: QRectF, edge: QColor, mine: bool, scale: float) -> None:
    """The glass plate under a line in the chat window: dark, scanlined, a thin frame in the
    speaker's colour with one corner cut - like her message panel."""
    from PySide6.QtGui import QLinearGradient, QPainterPath
    cut = 8 * scale
    path = QPainterPath()
    if mine:                                                     # yours: the top-left corner cut
        path.moveTo(box.left() + cut, box.top())
        path.lineTo(box.right(), box.top())
        path.lineTo(box.right(), box.bottom())
        path.lineTo(box.left(), box.bottom())
        path.lineTo(box.left(), box.top() + cut)
    else:                                                        # hers: the bottom-right corner cut
        path.moveTo(box.left(), box.top())
        path.lineTo(box.right(), box.top())
        path.lineTo(box.right(), box.bottom() - cut)
        path.lineTo(box.right() - cut, box.bottom())
        path.lineTo(box.left(), box.bottom())
    path.closeSubpath()
    g = QLinearGradient(box.topLeft(), box.bottomRight())
    g.setColorAt(0, QColor(edge.red() // 6 + 8, edge.green() // 6 + 6, edge.blue() // 6 + 10, 235))
    g.setColorAt(1, QColor(6, 6, 10, 240))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    p.setClipPath(path)
    y = box.top()
    while y < box.bottom():                                      # TV lines
        p.fillRect(QRectF(box.left(), y, box.width(), 1), QColor(255, 255, 255, 10))
        y += 3
    p.setClipping(False)
    frame = QColor(edge)
    frame.setAlpha(200)
    p.setPen(QPen(frame, 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.fillRect(QRectF(box.right() - 2.5 if mine else box.left(), box.top(), 2.5, box.height()), edge)
    p.restore()


def _text(p: QPainter, at: QPointF, text: str, colour: QColor, shadow: bool) -> None:
    """Text, with a soft dark shadow when it sits straight on your wallpaper (the call cards)."""
    if shadow:
        p.setPen(QColor(0, 0, 0, 150))
        for dx, dy in ((1.2, 1.2), (0, 1.4), (1.4, 0)):
            p.drawText(at + QPointF(dx, dy), text)
    p.setPen(colour)
    p.drawText(at, text)

