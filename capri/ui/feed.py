"""The call cards above her panel (right-click -> Panel -> Activity log style -> Call cards):
the conversation as a Night City call - what she heard you say on the right ("You"), her
replies on the left ("Capri"), each with its call icon (callstyle.py), "..." while she thinks.
In the chat window's skin colours. Each line fades out after a while; nothing on screen = no CPU.
"""

from __future__ import annotations

import re
import time
from typing import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QPainter

from .callstyle import CallColors, Row, layout, paint_row
from .overlay_window import OverlayWindow

LIFE = 14.0            # seconds a line stays
SHOWN = 3              # lines at once
FADE = 0.7
ENTER = 0.25
SCALE = 0.72           # smaller than in the chat window
GAP = 6


def heard_text(detail: str) -> str:
    """'"open discord"' / '"open this cord" -> "open discord"' -> what she understood."""
    quoted = re.findall(r'"([^"]*)"', detail)
    return quoted[-1] if quoted else detail


class FeedWindow(OverlayWindow):
    resized = Signal()

    def __init__(self, controller, always_on_top: bool = True, clock: Callable[[], float] = time.monotonic,
                 colours: Callable[[], CallColors] = CallColors) -> None:
        super().__init__(always_on_top)
        self.set_click_through(True)              # information only: clicks go to what's behind
        self.setWindowTitle("Capri - feed")
        self.controller, self.clock, self.colours = controller, clock, colours
        self.cards: list[dict] = []               # {"who", "text", "born"}
        self.allowed = True
        self.card_width = 300
        self.typing = False
        self._seen = getattr(controller, "total", 0)
        self._t0 = clock()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        controller.changed.connect(self._pick_up)
        self.resize(self.card_width, 1)

    # -- lines --------------------------------------------------------------------------------------
    def _pick_up(self) -> None:
        total = getattr(self.controller, "total", 0)
        new, self._seen = total - self._seen, total
        if new > 0:
            for verb, detail in list(self.controller.entries)[-min(new, SHOWN):]:
                if verb.lower() == "heard":
                    self._add("you", heard_text(detail))
        typing = getattr(self.controller.state, "value", "") == "processing"
        if typing != self.typing:
            self.typing = typing
            self._relayout()

    def add_reply(self, text: str, _emotion: str = "") -> None:
        """Her line (connected to Assistant.replied)."""
        if text and not (self.cards and self.cards[-1]["who"] == "capri" and self.cards[-1]["text"] == text):
            self.typing = False
            self._add("capri", text)

    def _add(self, who: str, text: str) -> None:
        self.cards.append({"who": who, "text": text, "born": self.clock()})
        del self.cards[:-SHOWN]
        self._relayout()

    def set_width(self, width: int) -> None:
        if width != self.card_width:
            self.card_width = width
            self._relayout()

    def set_allowed(self, on: bool) -> None:
        self.allowed = on
        self._relayout()

    def _rows(self) -> list[Row]:
        rows = [Row(c["who"], c["text"]) for c in self.cards]
        if self.typing and self.cards and self.cards[-1]["who"] == "you":
            rows.append(Row("capri", "", typing=True))
        return rows

    def _relayout(self) -> None:
        now = self.clock()
        self.cards = [c for c in self.cards if now - c["born"] < LIFE]
        rows = self._rows()
        height = max(1, int(sum(layout(r, self.card_width, SCALE)[0] + GAP for r in rows)) + 4)
        if self.size().toTuple() != (self.card_width + 8, height):
            self.resize(self.card_width + 8, height)
            self.resized.emit()
        show = self.allowed and bool(rows)
        if show and not self.isVisible():
            self.show()
        elif not show and self.isVisible():
            self.hide()
        if show and not self._timer.isActive():
            self._timer.start()
        elif not show:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        now = self.clock()
        if any(now - c["born"] >= LIFE for c in self.cards):
            return self._relayout()
        moving = self.typing or any(now - c["born"] < ENTER + 0.1 or now - c["born"] > LIFE - FADE for c in self.cards)
        self._timer.setInterval(33 if moving else 500)         # still lines: barely any CPU
        self.update()

    # -- drawing --------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        now = self.clock()
        colours = self.colours()
        y = 2.0
        cards = self.cards + ([{"born": now}] if len(self._rows()) > len(self.cards) else [])
        for row, card in zip(self._rows(), cards):
            age = now - card["born"]
            fade = min(1.0, max(0.0, (LIFE - age) / FADE)) if not row.typing else 1.0
            enter = min(1.0, age / ENTER) if not row.typing else 1.0
            p.setOpacity(fade * enter)
            y += paint_row(p, row, y, self.card_width, colours, SCALE, left=4, t=now - self._t0, shadow=True) + GAP
        p.end()
