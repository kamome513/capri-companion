"""Her music deck: while music plays, a slim vertical "data spine" floats beside her - a spinning neon data ring
at the top, the song running up the spine like a tape label, little equaliser bars, and previous / play-pause /
next. It slides away a few seconds after the music stops. Settings -> Extras -> "Music deck".

What's playing comes from the music app's window title (Spotify shows "Artist - Song" while it plays; music sites
show the song in the browser's title). The buttons press your media keys, so they work with any player.
"""

from __future__ import annotations

import math
import time
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen

from . import fx
from .overlay_window import OverlayWindow

W, H = 74, 304
RED, CYAN, GREEN = QColor(236, 16, 70), QColor(40, 230, 255), QColor(60, 255, 150)
LINGER = 6.0                     # seconds it stays after the music stops


def tidy_title(title: str, app: str = "") -> str:
    """"Artist - Song - YouTube Music - Google Chrome" -> "Artist - Song"."""
    t = (title or "").strip()
    for tail in (" - Google Chrome", " - Mozilla Firefox", " — Mozilla Firefox", " - Microsoft​ Edge",
                 " - Microsoft Edge", " - Opera", " - Brave", " - YouTube Music", " - YouTube", " | SoundCloud",
                 " - Spotify", " | Spotify"):
        if t.endswith(tail):
            t = t[: -len(tail)].strip()
    if t.lower() in ("spotify", "spotify free", "spotify premium", ""):
        return app or "Music"
    return t.replace(" • ", " - ")


class MusicDeck(OverlayWindow):
    pressed = Signal(str)                    # "previous" | "play_pause" | "next"

    def __init__(self) -> None:
        super().__init__(True)
        self.setFixedSize(W, H)
        self.title = "Music"
        self.playing = False
        self.shown_at = 0.0
        self._buttons: dict[str, QRectF] = {}
        self._timer = fx.precise_timer(self, 33)            # 30 fps: the ring and bars move
        self._timer.timeout.connect(self.update)
        self.clicked.connect(self._clicked)

    # -- show / hide ----------------------------------------------------------------------------------------------
    def set_music(self, playing: bool, title: str = "") -> None:
        if title:
            self.title = title
        self.playing = playing
        if playing and not self.isVisible():
            self.shown_at = time.monotonic()
            self.setWindowOpacity(0.0)
            self.show()
            self._timer.start()
        self.update()

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _clicked(self, at) -> None:
        local = QPointF(self.mapFromGlobal(at))
        for name, rect in self._buttons.items():
            if rect.adjusted(-3, -3, 3, 3).contains(local):
                self.pressed.emit(name)
                return

    # -- drawing --------------------------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        now = time.monotonic()
        fade = min(1.0, (now - self.shown_at) / 0.25)
        if self.windowOpacity() < 1.0:
            self.setWindowOpacity(fade)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(4, 4, W - 8, H - 8)
        shape = QPainterPath()                                # a spine with clipped corners
        c = 12
        for i, pt in enumerate(((r.left() + c, r.top()), (r.right(), r.top()), (r.right(), r.bottom() - c),
                                (r.right() - c, r.bottom()), (r.left(), r.bottom()), (r.left(), r.top() + c))):
            shape.moveTo(*pt) if i == 0 else shape.lineTo(*pt)
        shape.closeSubpath()
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, QColor(18, 8, 18, 235))
        bg.setColorAt(1, QColor(8, 6, 14, 235))
        p.setPen(QPen(QColor(RED.red(), RED.green(), RED.blue(), 70), 6))
        p.setBrush(bg)
        p.drawPath(shape)
        p.setPen(QPen(RED, 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)
        p.setPen(QPen(CYAN, 2))
        p.drawLine(QPointF(r.left() + 3, r.top() + c + 6), QPointF(r.left() + 3, r.top() + c + 40))
        self._ring(p, QPointF(r.center().x(), r.top() + 34), now)
        self._spine(p, QRectF(r.left() + 10, r.top() + 68, r.width() - 20, 104), now)
        self._bars(p, QRectF(r.left() + 10, r.top() + 180, r.width() - 20, 14), now)
        self._controls(p, r)
        p.end()

    def _ring(self, p: QPainter, centre: QPointF, now: float) -> None:
        """The spinning data ring: two broken arcs turning opposite ways, a pulsing core."""
        spin = now * (110 if self.playing else 12)
        for radius, colour, sign, gaps in ((24, RED, 1, 3), (17, CYAN, -1, 4)):
            p.setPen(QPen(colour, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            rect = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
            seg = 360 / gaps
            for k in range(gaps):
                p.drawArc(rect, int((sign * spin + k * seg) * 16), int(seg * 0.62 * 16))
        pulse = 0.5 + 0.5 * math.sin(now * 6) if self.playing else 0.3
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(GREEN.red(), GREEN.green(), GREEN.blue(), int(110 + 140 * pulse)))
        p.drawEllipse(centre, 4 + 2 * pulse, 4 + 2 * pulse)

    def _spine(self, p: QPainter, box: QRectF, now: float) -> None:
        """The song, written up the spine, scrolling when it's long."""
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(12)
        font.setBold(True)
        fm = QFontMetricsF(font)
        text = self.title.upper()
        width = fm.horizontalAdvance(text)
        p.save()
        p.setClipRect(box)
        p.translate(box.center().x(), box.bottom())
        p.rotate(-90)
        length = box.height()
        offset = 0.0
        if width > length:                                    # marquee
            span = width + 40
            offset = -((now * 28) % span)
        p.setFont(font)
        for copy in ((0.0,) if width <= length else (0.0, width + 40)):
            p.setPen(QColor(255, 255, 255, 235))
            p.drawText(QPointF(offset + copy + (0 if width > length else (length - width) / 2), fm.ascent() / 2 - 2),
                       text)
        p.restore()
        p.setPen(QPen(QColor(RED.red(), RED.green(), RED.blue(), 120), 1))
        p.drawLine(QPointF(box.left() - 2, box.top()), QPointF(box.left() - 2, box.bottom()))
        p.drawLine(QPointF(box.right() + 2, box.top()), QPointF(box.right() + 2, box.bottom()))

    def _bars(self, p: QPainter, box: QRectF, now: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        n = 7
        w = box.width() / n
        for i in range(n):
            level = 0.15 if not self.playing else 0.25 + 0.75 * abs(math.sin(now * (3.1 + i * 0.7) + i * 1.3))
            h = box.height() * level
            g = QLinearGradient(QPointF(0, box.bottom()), QPointF(0, box.bottom() - box.height()))
            g.setColorAt(0, RED)
            g.setColorAt(1, GREEN)
            p.setBrush(g)
            p.drawRect(QRectF(box.left() + i * w + 1, box.bottom() - h, w - 2, h))

    def _controls(self, p: QPainter, r: QRectF) -> None:
        self._buttons = {}
        size, gap = 22.0, 6.0
        top = r.top() + 204
        x = r.center().x() - size / 2
        for i, (name, glyph) in enumerate((("previous", "prev"), ("play_pause", "play" if not self.playing else "pause"),
                                           ("next", "next"))):
            rect = QRectF(x, top + i * (size + gap), size, size)
            self._buttons[name] = rect
            chip = QPainterPath()
            chip.moveTo(rect.left() + 5, rect.top())
            for pt in ((rect.right(), rect.top()), (rect.right(), rect.bottom() - 5), (rect.right() - 5, rect.bottom()),
                       (rect.left(), rect.bottom()), (rect.left(), rect.top() + 5)):
                chip.lineTo(*pt)
            chip.closeSubpath()
            colour = RED if name == "play_pause" else CYAN
            p.setPen(QPen(colour, 1.2))
            p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 45))
            p.drawPath(chip)
            self._glyph(p, rect.center(), glyph, colour)

    @staticmethod
    def _glyph(p: QPainter, c: QPointF, glyph: str, colour: QColor) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        s = 5.0
        if glyph == "pause":
            p.drawRect(QRectF(c.x() - s, c.y() - s, 3.5, 2 * s))
            p.drawRect(QRectF(c.x() + s - 3.5, c.y() - s, 3.5, 2 * s))
            return
        tri = QPainterPath()
        if glyph == "play":
            tri.moveTo(c.x() - s * 0.7, c.y() - s)
            tri.lineTo(c.x() + s, c.y())
            tri.lineTo(c.x() - s * 0.7, c.y() + s)
        elif glyph == "next":
            tri.moveTo(c.x() - s, c.y() - s)
            tri.lineTo(c.x() + s * 0.4, c.y())
            tri.lineTo(c.x() - s, c.y() + s)
            p.drawRect(QRectF(c.x() + s * 0.5, c.y() - s, 2.5, 2 * s))
        else:
            tri.moveTo(c.x() + s, c.y() - s)
            tri.lineTo(c.x() - s * 0.4, c.y())
            tri.lineTo(c.x() + s, c.y() + s)
            p.drawRect(QRectF(c.x() - s * 0.5 - 2.5, c.y() - s, 2.5, 2 * s))
        tri.closeSubpath()
        p.drawPath(tri)


class DeckKeeper:
    """Shows / hides / places the deck from "is music playing" (StatusWatch) and her position."""

    def __init__(self, deck: MusicDeck, companion, title: Callable[[], str], enabled: Callable[[], bool],
                 clock=time.monotonic) -> None:
        self.deck, self.companion, self.title, self.enabled, self.clock = deck, companion, title, enabled, clock
        self.music = False
        self._quiet_since = 0.0
        self.timer = QTimer()
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def music_changed(self, on: bool) -> None:
        if on and not self.music:
            try:
                self.deck.set_music(True, self.title())
            except Exception:
                self.deck.set_music(True)
        self.music = on
        if not on:
            self._quiet_since = self.clock()
        self.tick()

    def tick(self) -> None:
        c, deck = self.companion, self.deck
        wanted = self.enabled() and not c.hidden and not c.drone and not c.busy_elsewhere and \
            (self.music or (deck.isVisible() and self.clock() - self._quiet_since < LINGER))
        if not wanted:
            if deck.isVisible():
                deck.hide()
            return
        if not deck.isVisible():
            deck.set_music(self.music, self.title())
        deck.playing = self.music
        body = c.content_geometry()
        area = c.screen.availableGeometry()
        x = body.left() - deck.width() - 6                    # beside her (the other side if there's no room)
        if x < area.left():
            x = body.right() + 6
        y = max(area.top(), min(body.center().y() - deck.height() // 2, area.bottom() - deck.height()))
        if deck.pos().x() != x or deck.pos().y() != y:
            deck.move(int(x), int(y))
