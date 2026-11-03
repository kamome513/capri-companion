"""A chat window: type to Capri instead of talking - styled as a Night City call.

Whatever you type goes exactly where speech goes (Assistant.typed): commands
("open discord"), answers to her questions ("yes", a search in search mode) and
chat. Everything she says or asks appears here too. The history lives only in
memory - nothing is saved.

Five skins, picked from the header (saved in Settings): Holocall (crimson + cyan, like her
panel), Netrunner (a green terminal), Arasaka (corporate black and red), Neon (Night City
pink and yellow) and Braindance (purple). The header shows her face and what she's doing
right now (listening, thinking, talking...) - the real state, nothing made up.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from . import theme
from .callstyle import CallColors, Row, layout, paint_row

MONO = ", ".join(f'"{f}"' for f in theme.MONO_FAMILIES)


@dataclass(frozen=True)
class Skin:
    key: str
    label: str
    title: str             # header plate
    tag: str               # under the title
    bg: str
    panel: str             # message area
    accent: str            # her colour
    you: str               # your colour
    text: str
    dim: str
    font: str = ""         # "" = the normal UI font; else monospace
    you_name: str = "YOU"
    her_name: str = "CAPRI"
    prompt: str = ""       # a terminal-style prefix for lines
    call: CallColors = CallColors()                    # the call look's colours in this skin


SKINS: dict[str, Skin] = {s.key: s for s in (
    Skin("holocall", "Holocall", "CAPRI // HOLOCALL", "INCOMING LINK  -  ENCRYPTED",
         "#07070b", "#0d0a11", "#ec1046", "#00e2ff", "#f2f2f5", "#6f6f7a",
         call=CallColors("#4fd8c4", "#c4142f", "#2f9e44", "#d9a93b", "#8a8a96")),
    Skin("netrunner", "Netrunner", "NETRUNNER://CAPRI", "SESSION OPEN  -  ICE: CLEAR",
         "#020604", "#030a06", "#39e66b", "#b8ff3c", "#c9f7d4", "#3d6b4a", font="mono",
         you_name="user", her_name="capri", prompt="> ",
         call=CallColors("#39e66b", "#167a3a", "#7da81a", "#a8f7c0", "#3d6b4a")),
    Skin("arasaka", "Arasaka", "ARASAKA  //  SECURE CHANNEL", "AUTHORIZED PERSONNEL ONLY",
         "#0b0b0c", "#111113", "#d0021b", "#e8e8ea", "#dcdcdf", "#5d5d63", you_name="OPERATOR",
         call=CallColors("#e8e8ea", "#b0001a", "#4a4a50", "#dcdcdf", "#5d5d63")),
    Skin("neon", "Neon", "NIGHT CITY  //  CAPRI", "WATSON  -  2077  -  LIVE",
         "#0a0614", "#120a1f", "#ff2fb4", "#ffd400", "#fff2fb", "#7a6788",
         call=CallColors("#ffd400", "#e0249e", "#1c9bd6", "#ffe46b", "#7a6788")),
    Skin("braindance", "Braindance", "BD // CAPRI.REC", "RECORDING  -  SENSORY TRACK 3",
         "#08050f", "#0f0a1c", "#a55cff", "#5cf2ff", "#efe6ff", "#6c5c87",
         call=CallColors("#5cf2ff", "#7d3cff", "#2a9d96", "#e7d6ff", "#6c5c87")),
)}


def stylesheet(s: Skin) -> str:
    family = MONO if s.font == "mono" else '"Segoe UI", "Inter", sans-serif'
    return f"""
QWidget#chat {{ background: {s.bg}; }}
QScrollArea {{ background: {s.panel}; border: 1px solid {s.accent}; border-left: 3px solid {s.accent}; }}
QScrollArea > QWidget > QWidget {{ background: {s.panel}; }}
QLineEdit {{ background: {s.panel}; color: {s.text}; border: 1px solid {s.you}; padding: 8px;
             font-family: {family}; font-size: 10.5pt; selection-background-color: {s.accent}; }}
QLineEdit:focus {{ border: 1px solid {s.accent}; }}
QPushButton {{ background: {s.accent}; color: {s.bg}; border: none; padding: 8px 18px;
               font-family: {MONO}; font-weight: bold; letter-spacing: 2px; }}
QPushButton:hover {{ background: {s.you}; }}
QComboBox {{ background: {s.panel}; color: {s.dim}; border: 1px solid {s.dim}; padding: 2px 6px;
             font-family: {MONO}; font-size: 8pt; }}
QComboBox QAbstractItemView {{ background: {s.panel}; color: {s.text}; selection-background-color: {s.accent}; }}
QScrollBar:vertical {{ background: {s.panel}; width: 8px; }}
QScrollBar::handle:vertical {{ background: {s.accent}; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


class CallHeader(QWidget):
    """The top plate: her face in a frame, the skin's title, and her live state."""

    def __init__(self, icon: QImage, state=lambda: "STANDBY") -> None:
        super().__init__()
        self.icon, self.state = icon, state
        self.skin = SKINS["holocall"]
        self.setFixedHeight(66)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(120)                   # the little signal bars move (only while it's open)
        self._timer.timeout.connect(self.update)

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        s = self.skin
        accent, you, dim = QColor(s.accent), QColor(s.you), QColor(s.dim)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -4)
        cut = 12
        plate = QPainterPath(QPointF(r.left(), r.top()))
        plate.lineTo(r.right() - cut, r.top())
        plate.lineTo(r.right(), r.top() + cut)
        plate.lineTo(r.right(), r.bottom())
        plate.lineTo(r.left() + cut, r.bottom())
        plate.lineTo(r.left(), r.bottom() - cut)
        plate.closeSubpath()
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, QColor(accent.red() // 5, accent.green() // 5, accent.blue() // 5))
        g.setColorAt(1, QColor(s.panel))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(plate)
        p.save()
        p.setClipPath(plate)
        y = r.top()
        while y < r.bottom():                                       # scanlines
            p.fillRect(QRectF(r.left(), y, r.width(), 1), QColor(255, 255, 255, 8))
            y += 3
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(accent, 1.2))
        p.drawPath(plate)
        p.fillRect(QRectF(r.left() + 8, r.bottom() - 2, 90, 2), you)
        # her face in a frame
        face = QRectF(r.left() + 10, r.top() + 8, r.height() - 16, r.height() - 16)
        if not self.icon.isNull():
            p.drawImage(face, self.icon)
        p.setPen(QPen(accent, 1.4))
        p.drawRect(face)
        # title + tag
        tx = face.right() + 12
        title = QFont()
        title.setFamilies(theme.MONO_FAMILIES)
        title.setPixelSize(15)
        title.setBold(True)
        title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        room = r.right() - 92 - tx                                  # leave the state readout its corner
        while title.pixelSize() > 10 and QFontMetricsF(title).horizontalAdvance(s.title) > room:
            title.setPixelSize(title.pixelSize() - 1)
        p.setFont(title)
        p.setPen(QColor(s.text))
        p.drawText(QPointF(tx, r.top() + 26), s.title)
        small = QFont(title)
        small.setPixelSize(9)
        small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        p.setFont(small)
        p.setPen(dim)
        p.drawText(QPointF(tx, r.top() + 44), "◢ " + s.tag)
        # her real state, with signal bars
        state = self.state().upper()
        p.setPen(accent)
        p.drawText(QRectF(r.left(), r.top() + 6, r.width() - 24, 14), int(Qt.AlignmentFlag.AlignRight), "● " + state)
        t = time.monotonic() - self._t0
        for i in range(5):
            h = 4 + 10 * abs(math.sin(t * (2.5 if state not in ("STANDBY", "IDLE") else 0.6) + i * 0.9))
            x = r.right() - 24 - (5 - i) * 6
            p.fillRect(QRectF(x, r.bottom() - 10 - h, 3, h), you if i % 2 else accent)
        p.end()


CHAT_ICON = 46                     # call squares in the chat window: a bit smaller than the call cards


class CallLog(QScrollArea):
    """The conversation in the call look (callstyle.py): her on the left, you on the right,
    "..." while she's thinking."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Row] = []
        self.colours = CallColors()
        self.typing = False
        self.canvas = _CallCanvas(self)
        self.setWidget(self.canvas)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)                   # the "..." dots move while she thinks
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.canvas.update)

    def add(self, who: str, text: str) -> None:
        self.rows.append(Row(who, text))
        self._relayout(scroll=True)

    def set_typing(self, on: bool) -> None:
        if on != self.typing:
            self.typing = on
            self._timer.start() if on else self._timer.stop()
            self._relayout(scroll=on)

    def set_colours(self, colours: CallColors) -> None:
        self.colours = colours
        self.canvas.update()

    def all_rows(self) -> list[Row]:
        return self.rows + ([Row("capri", "", typing=True)] if self.typing else [])

    def text(self) -> str:
        return "\n".join(f"{'You' if r.who == 'you' else 'Capri'}: {r.text}" for r in self.rows)

    def _relayout(self, scroll: bool = False) -> None:
        width = max(200, self.viewport().width() - 24)
        self.canvas.setMinimumHeight(int(sum(layout(r, width, icon=CHAT_ICON, plate=True)[0] + 10
                                             for r in self.all_rows()) + 20))
        self.canvas.update()
        if scroll:
            QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()


class _CallCanvas(QWidget):
    def __init__(self, log: CallLog) -> None:
        super().__init__()
        self.log = log

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        y = event.rect().top() - event.rect().top() % 3
        while y < event.rect().bottom() + 3:                     # TV lines across the whole call, like her panel
            p.fillRect(0, y, self.width(), 1, QColor(255, 255, 255, 7))
            y += 3
        width = self.width() - 24
        y = 12.0
        t = time.monotonic() - self.log._t0
        for row in self.log.all_rows():
            y += paint_row(p, row, y, width, self.log.colours, left=12, t=t, icon=CHAT_ICON, plate=True) + 10
        p.end()


class ChatWindow(QWidget):
    def __init__(self, assistant, icon: QImage) -> None:
        super().__init__(None)
        self.assistant = assistant
        self.settings = getattr(assistant, "settings", None)
        self.setObjectName("chat")
        self.setWindowTitle("Capri - Chat")
        from .app_icon import app_icon
        self.setWindowIcon(app_icon())
        self.resize(460, 600)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)
        controller = getattr(assistant, "controller", None)
        self.header = CallHeader(icon, lambda: controller.state.value if controller is not None else "standby")
        root.addWidget(self.header)
        top = QHBoxLayout()
        top.addStretch(1)
        self.skin_box = QComboBox()
        for skin in SKINS.values():
            self.skin_box.addItem("SKIN: " + skin.label.upper(), skin.key)
        self.skin_box.currentIndexChanged.connect(lambda _i: self.set_skin(self.skin_box.currentData()))
        top.addWidget(self.skin_box)
        root.addLayout(top)
        self.log = CallLog()                               # the call look, always (skins recolour it)
        root.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.returnPressed.connect(self.send)
        self.send_button = QPushButton("SEND")
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_button)
        root.addLayout(row)
        self.lines: list[tuple[str, str]] = []                # (who, text)
        self._stamps: list[str] = []
        self.skin = SKINS["holocall"]
        saved = getattr(self.settings, "chat_skin", "holocall") if self.settings is not None else "holocall"
        self.skin_box.setCurrentIndex(max(0, self.skin_box.findData(saved)))
        self.set_skin(saved)
        assistant.replied.connect(self.add_capri)
        if controller is not None:                         # "..." while she's thinking
            controller.changed.connect(lambda: self.log.set_typing(controller.state.value == "processing"))
        self.add_capri("Hey. Type to me here, same as talking.", "happy")

    # -- skins ------------------------------------------------------------------------------------------
    def set_skin(self, key: str) -> None:
        self.skin = SKINS.get(key, SKINS["holocall"])
        self.header.skin = self.skin
        if self.skin_box.currentData() != self.skin.key:            # keep the picker in step
            self.skin_box.blockSignals(True)
            self.skin_box.setCurrentIndex(max(0, self.skin_box.findData(self.skin.key)))
            self.skin_box.blockSignals(False)
        self.setStyleSheet(stylesheet(self.skin))
        self.input.setPlaceholderText("> type a command or just talk" if self.skin.prompt else "Message Capri...")
        self.send_button.setText("EXEC" if self.skin.key == "netrunner" else "SEND")
        if self.settings is not None and getattr(self.settings, "chat_skin", None) != self.skin.key:
            self.settings.chat_skin = self.skin.key
            try:
                self.settings.save()
            except Exception:
                pass
        self.log.set_colours(self.skin.call)
        self.header.update()

    # -- messages ---------------------------------------------------------------------------------------
    def _append(self, who: str, text: str) -> None:
        self.lines.append((who, text))
        self._stamps.append(time.strftime("%H:%M"))
        self.log.add(who, text)

    def add_capri(self, text: str, emotion: str = "") -> None:
        if self.lines and self.lines[-1] == ("capri", text):
            return                                        # the same line twice (shown, then spoken)
        self._append("capri", text)

    def send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._append("you", text)
        self.assistant.typed(text)

    def open(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.FocusReason.OtherFocusReason)
