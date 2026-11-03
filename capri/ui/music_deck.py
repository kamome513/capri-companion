"""Her music deck: while music plays, she stands on a neon hover bar - a spinning data ring at one end, the song
scrolling along it, little equaliser bars, and previous / play-pause / next at the other end. She rises onto it
when the music starts and steps back down a few seconds after it stops. Lying down, she lies on it.
On / off: Settings -> Extras -> "Music deck", the tray menu (Capri -> Music deck), or "hide the music bar".

What's playing comes from the music app's window title (Spotify shows "Artist - Song" while it plays; music sites
show the song in the browser's title). The buttons press your media keys, so they work with any player.
"""

from __future__ import annotations

import math
import re
import time
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from . import fx
from .overlay_window import OverlayWindow

W = 250                          # standing; wider when she lies on it
BODY = 44                        # the bar itself (she stands on its top edge)
GLOW = 10                        # its hover glow underneath
H = BODY + GLOW
SINK = 3                         # px of her feet resting below the bar's top edge
RED, CYAN, GREEN = QColor(236, 16, 70), QColor(40, 230, 255), QColor(60, 255, 150)
LINGER = 6.0                     # seconds it stays after the music stops
RISE = 0.28                      # seconds she takes to rise onto it / step down


NOT_SONGS = {"default ime", "msctfime ui", "chrome legacy window", "spotify", "spotify free", "spotify premium",
             "music", "apple music", "itunes", "media player", "windows media player", "groove music", "deezer",
             "tidal", "amazon music", "youtube music", "soundcloud", "youtube", "vlc media player", "foobar2000",
             "now playing", "new tab", "home"}
REFRESH = 3.0                    # seconds between re-reading what's playing (the song changes)


def tidy_title(title: str, app: str = "") -> str:
    """"Artist - Song - YouTube Music - Google Chrome" -> "Artist - Song"."""
    t = re.sub(r"^\(\d+\)\s*|^[▶►⏸❚]+\s*", "", (title or "").strip())   # "(3) ..." unread count, "▶ ..." playing mark
    for tail in (" - Google Chrome", " - Mozilla Firefox", " — Mozilla Firefox", " - Microsoft​ Edge",
                 " - Microsoft Edge", " - Opera", " - Brave", " - YouTube Music", " - YouTube", " | SoundCloud",
                 " - Spotify", " | Spotify"):
        if t.endswith(tail):
            t = t[: -len(tail)].strip()
    if t.lower() in ("spotify", "spotify free", "spotify premium", ""):
        return app or "Music"
    return t.replace(" • ", " - ").replace(" — ", " - ")


def song_from(titles) -> str:
    """The song, from a music app's (or a music site's) window titles - skipping its hidden helper windows
    ("Default IME", "GDI+ Window"...) and app-name-only titles, preferring one that looks like "Artist - Song"."""
    found = []
    for raw in titles:
        t = tidy_title(raw or "")
        low = t.lower()
        if not t or low in NOT_SONGS or low.startswith(("gdi+ window", "msctfime", "default ime")) or len(t) < 2:
            continue
        found.append(t)
    for t in found:
        if " - " in t:
            return t
    return found[0] if found else ""


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

    def set_width(self, width: int) -> None:
        width = max(W, int(width))
        if width != self.width():
            self.setFixedSize(width, H)

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
        w = self.width()
        r = QRectF(2, 1, w - 4, BODY - 2)
        # hover glow under the bar (it floats)
        under = QRadialGradient(QPointF(w / 2, BODY), w * 0.45)
        pulse = 0.5 + 0.5 * math.sin(now * 3) if self.playing else 0.3
        under.setColorAt(0, QColor(RED.red(), RED.green(), RED.blue(), int(70 + 50 * pulse)))
        under.setColorAt(1, QColor(RED.red(), RED.green(), RED.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(under)
        p.drawRect(QRectF(0, BODY - 2, w, GLOW + 2))
        # the bar: angled ends, like a blade
        c = 14
        shape = QPainterPath()
        for i, pt in enumerate(((r.left() + c, r.top()), (r.right() - c, r.top()), (r.right(), r.top() + c),
                                (r.right() - c * 0.6, r.bottom()), (r.left() + c * 0.6, r.bottom()),
                                (r.left(), r.top() + c))):
            shape.moveTo(*pt) if i == 0 else shape.lineTo(*pt)
        shape.closeSubpath()
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, QColor(24, 10, 22, 240))
        bg.setColorAt(1, QColor(8, 6, 14, 240))
        p.setBrush(bg)
        p.setPen(QPen(QColor(RED.red(), RED.green(), RED.blue(), 160), 1.2))
        p.drawPath(shape)
        # the deck she stands on: a bright edge along the top
        for width, alpha in ((5.0, 70), (2.0, 255)):
            p.setPen(QPen(QColor(255, 60, 100, alpha), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawLine(QPointF(r.left() + c, r.top() + 1), QPointF(r.right() - c, r.top() + 1))
        p.setPen(QPen(CYAN, 2))                                         # cyan ticks in the angled ends
        p.drawLine(QPointF(r.left() + 5, r.top() + c + 4), QPointF(r.left() + 10, r.bottom() - 6))
        p.drawLine(QPointF(r.right() - 5, r.top() + c + 4), QPointF(r.right() - 10, r.bottom() - 6))
        controls = 3 * 20 + 2 * 5
        self._ring(p, QPointF(r.left() + 30, r.center().y() + 1), now)
        left, right = r.left() + 52, r.right() - 16 - controls - 8
        self._title(p, QRectF(left, r.top() + 7, right - left, 15), now)
        self._bars(p, QRectF(left, r.top() + 26, right - left, 10), now)
        self._controls(p, QPointF(r.right() - 16 - controls, r.center().y() + 1))
        p.end()

    def _ring(self, p: QPainter, centre: QPointF, now: float) -> None:
        """The spinning data ring: two broken arcs turning opposite ways, a pulsing core."""
        spin = now * (110 if self.playing else 12)
        for radius, colour, sign, gaps in ((15, RED, 1, 3), (10, CYAN, -1, 4)):
            p.setPen(QPen(colour, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            rect = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
            seg = 360 / gaps
            for k in range(gaps):
                p.drawArc(rect, int((sign * spin + k * seg) * 16), int(seg * 0.62 * 16))
        pulse = 0.5 + 0.5 * math.sin(now * 6) if self.playing else 0.3
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(GREEN.red(), GREEN.green(), GREEN.blue(), int(110 + 140 * pulse)))
        p.drawEllipse(centre, 3 + 1.5 * pulse, 3 + 1.5 * pulse)

    def _title(self, p: QPainter, box: QRectF, now: float) -> None:
        """The song, scrolling along the bar when it's long."""
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(12)
        font.setBold(True)
        fm = QFontMetricsF(font)
        text = self.title.upper()
        width = fm.horizontalAdvance(text)
        p.save()
        p.setClipRect(box)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 235))
        base = box.top() + (box.height() + fm.ascent() - fm.descent()) / 2
        if width <= box.width():
            p.drawText(QPointF(box.left(), base), text)
        else:                                                       # marquee
            span = width + 40
            offset = -((now * 28) % span)
            for copy in (0.0, span):
                p.drawText(QPointF(box.left() + offset + copy, base), text)
        p.restore()

    def _bars(self, p: QPainter, box: QRectF, now: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        n = max(6, int(box.width() // 7))
        w = box.width() / n
        for i in range(n):
            level = 0.15 if not self.playing else 0.25 + 0.75 * abs(math.sin(now * (3.1 + (i % 7) * 0.7) + i * 1.3))
            h = box.height() * level
            g = QLinearGradient(QPointF(0, box.bottom()), QPointF(0, box.bottom() - box.height()))
            g.setColorAt(0, RED)
            g.setColorAt(1, GREEN)
            p.setBrush(g)
            p.drawRect(QRectF(box.left() + i * w + 1, box.bottom() - h, w - 2, h))

    def _controls(self, p: QPainter, left_middle: QPointF) -> None:
        self._buttons = {}
        size, gap = 20.0, 5.0
        for i, (name, glyph) in enumerate((("previous", "prev"), ("play_pause", "play" if not self.playing else "pause"),
                                           ("next", "next"))):
            rect = QRectF(left_middle.x() + i * (size + gap), left_middle.y() - size / 2, size, size)
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
    """Shows / hides the deck from "is music playing" (StatusWatch), keeps it under her feet (or under her, lying),
    and lifts her onto it - smoothly - and back down."""

    def __init__(self, deck: MusicDeck, companion, title: Callable[[], str], enabled: Callable[[], bool],
                 clock=time.monotonic) -> None:
        self.deck, self.companion, self.title, self.enabled, self.clock = deck, companion, title, enabled, clock
        self.music = False
        self._quiet_since = 0.0
        self.lift = 0.0                                 # how far she's up on it right now (px)
        self._titled = -1e9
        self._from, self._to, self._since = 0.0, 0.0, 0.0
        self.timer = QTimer(deck)                       # (both go with the deck)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.rise = fx.precise_timer(deck, 16)
        self.rise.timeout.connect(self._step)
        if hasattr(companion, "moved"):
            companion.moved.append(self.place)          # dragged around: the deck stays under her feet

    def _song(self) -> str:
        try:
            return self.title() or ""
        except Exception:
            return ""

    def music_changed(self, on: bool) -> None:
        if on and not self.music:
            self.deck.set_music(True, self._song())
            self._titled = self.clock()
        self.music = on
        if not on:
            self._quiet_since = self.clock()
        self.tick()

    def wanted(self) -> bool:
        c, deck = self.companion, self.deck
        if not self.enabled() or getattr(c, "drone", False) or getattr(c, "perched", False):
            return False
        return self.music or (deck.isVisible() and self.clock() - self._quiet_since < LINGER)

    def tick(self) -> None:
        c, deck = self.companion, self.deck
        on = self.wanted()
        away = c.hidden or c.busy_elsewhere                # thrown / teleporting / hidden: the deck waits
        if not on or away:
            if deck.isVisible():
                deck.hide()
            if not on:
                self._lift_to(0.0)
            return
        if not deck.isVisible():
            deck.set_music(self.music, self._song())
            self._titled = self.clock()
        elif self.music and self.clock() - self._titled >= REFRESH:      # the next song: the bar keeps up
            self._titled = self.clock()
            song = self._song()
            if song and song != deck.title:
                deck.title = song
                deck.update()
        deck.playing = self.music
        self._lift_to(BODY - SINK)
        self.place()

    # -- her standing on it --------------------------------------------------------------------------------------------
    def _lift_to(self, target: float) -> None:
        if target == self._to and (self.rise.isActive() or self.lift == target):
            return
        self._from, self._to, self._since = self.lift, target, self.clock()
        if self.rise.interval() and not self.rise.isActive():
            self.rise.start()
        self._step()

    def _step(self) -> None:
        t = min(1.0, (self.clock() - self._since) / RISE) if RISE else 1.0
        self.lift = self._from + (self._to - self._from) * fx.ease_out(t)
        if t >= 1.0:
            self.lift = self._to
            self.rise.stop()
        set_platform = getattr(self.companion, "set_platform", None)
        if set_platform is not None:
            set_platform(round(self.lift))
        self.place()

    def place(self) -> None:
        """The deck right under her feet (lying: under her body), lined up with her middle."""
        c, deck = self.companion, self.deck
        try:
            if not deck.isVisible():
                return
        except RuntimeError:                              # the deck's gone (Capri closing): stop following her
            if self.place in getattr(c, "moved", []):
                c.moved.remove(self.place)
            return
        body = c.content_geometry()
        area = c.screen.availableGeometry()
        lying = bool(getattr(c, "lounging", lambda: False)())
        deck.set_width(body.width() + 40 if lying else W)
        x = max(area.left(), min(round(body.center().x() - deck.width() / 2), area.right() + 1 - deck.width()))
        y = min(body.bottom() + 1 - SINK, area.bottom() + 1 - BODY)
        if deck.pos().x() != x or deck.pos().y() != y:
            deck.move(int(x), int(y))
        figure = getattr(c, "character", None)
        if figure is not None and figure.isVisible():
            figure.raise_()                               # her feet in front of the bar
