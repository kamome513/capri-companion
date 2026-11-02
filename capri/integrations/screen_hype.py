"""Game hype for any game: she watches the middle of your game's screen (on this PC, never sent
anywhere) for the words games put up - "ELIMINATED", "HEADSHOT", "DOUBLE KILL", "VICTORY",
"KILLED BY" - and cheers. Plus, if you like, a "you're doing great" now and then while you play.

Only while a game is in front, about every 1.5 seconds, reading a shrunk copy of the middle of
the screen with Windows' own OCR (ocr_worker.py). Games in exclusive full screen can show up black
to screenshots - set the game to borderless / windowed full screen if she never reacts.
Off by default: Settings -> PC & chat -> Game hype.
"""

from __future__ import annotations

import logging
import random
import re
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger("capri")

SCAN_MS = 1500
COOLDOWN = 4.0                  # the same banner stays up a few seconds: once is enough
# What games write on screen -> what happened. Checked in this order: "ELIMINATED BY X" is you dying.
SIGNS = [
    ("death", r"\b(?:eliminated by|killed by|knocked (?:down )?by|downed by|you died|you were (?:killed|eliminated)|"
              r"you are dead|wasted|spectating)\b"),
    ("ace", r"\b(?:ace|penta ?kill|team ?wipe|squad wiped|flawless)\b"),
    ("quad", r"\b(?:quadra ?kill|quad ?kill|ultra ?kill)\b"),
    ("triple", r"\b(?:triple ?kill|three kills)\b"),
    ("double", r"\b(?:double ?kill|two kills)\b"),
    ("headshot", r"\bhead ?shot\b"),
    ("first_blood", r"\bfirst blood\b"),
    ("match_win", r"\b(?:victory(?: royale)?|winner winner|you win|you won|match won|champions?|#1)\b"),
    ("match_loss", r"\b(?:defeat|you lose|you lost|match lost|game over)\b"),
    ("round_win", r"\b(?:round won|round win|round victory)\b"),
    ("kill", r"\b(?:you eliminated|eliminated|elimination|knocked down|knocked|you killed|enemy (?:down|killed)|"
             r"kill confirmed|killed|\+\s?\d+\s?kill)\b"),
]


def read_signs(text: str) -> set[str]:
    """OCR text -> what it shows. A death hides the kill words in the same banner."""
    t = re.sub(r"[^a-z0-9#+ ]+", " ", text.lower())
    found = {event for event, pattern in SIGNS if re.search(pattern, t)}
    if "death" in found:
        found -= {"kill", "headshot"}
    if found & {"double", "triple", "quad", "ace"}:
        found.discard("kill")
    return found


class ScreenWatcher(QObject):
    _found = Signal(object)

    def __init__(self, settings, in_game: Callable[[], bool], game_rect: Callable[[], tuple | None],
                 read: Callable[[object], str], emit: Callable[[str], None], grab: Callable[[tuple], object],
                 clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None) -> None:
        super().__init__()
        # (named on_event, never "emit": that would hide QObject.emit, which PySide uses to send signals)
        self.settings, self.in_game, self.game_rect, self.read, self.on_event, self.grab = \
            settings, in_game, game_rect, read, emit, grab
        self.clock, self.rng = clock, rng or random.Random()
        self._shown: set[str] = set()
        self._said: dict[str, float] = {}
        self._busy = False
        self._next_cheer = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._found.connect(self._seen)

    def apply(self) -> None:
        on = bool(getattr(self.settings, "game_hype_screen", False) or getattr(self.settings, "game_hype_encourage", False))
        if on and not self._timer.isActive():
            self._timer.start(SCAN_MS)
            self._next_cheer = self.clock() + self.rng.uniform(300, 600)
        elif not on:
            self._timer.stop()

    def _tick(self) -> None:
        if not self.in_game():
            self._shown = set()
            return
        if getattr(self.settings, "game_hype_encourage", False) and self.clock() >= self._next_cheer:
            self._next_cheer = self.clock() + self.rng.uniform(360, 720)       # every 6-12 minutes
            self.on_event("encourage")
        if getattr(self.settings, "game_hype_screen", False) and not self._busy:
            self._busy = True
            threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self) -> None:
        try:
            rect = self.game_rect()
            if not rect:
                return self._found.emit(set())
            l, t, r, b = rect
            w, h = r - l, b - t
            middle = (l + w // 5, t + h // 6, r - w // 5, b - h // 8)       # where games put their banners
            shot = self.grab(middle)
            self._found.emit(read_signs(self.read(shot)) if shot is not None else set())
        except Exception as exc:
            log.info("screen hype: %s", exc)
            self._found.emit(set())

    def _seen(self, signs) -> None:
        self._busy = False
        now = self.clock()
        new = set(signs) - self._shown                  # only when a banner appears, not while it stays
        self._shown = set(signs)
        for event in new:
            if now - self._said.get(event, -1e9) >= COOLDOWN:
                self._said[event] = now
                self.on_event(event)


def grab_image(rect: tuple[int, int, int, int], width: int = 1100):
    """A shrunk, OCR-ready copy of part of the screen (a QImage), or None."""
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from .screen_click import grab
    from .screen_targets import prepare_for_ocr
    shot = grab(rect)
    if shot is None:
        return None
    shot = prepare_for_ocr(shot)
    h, w = shot.shape[:2]
    rgba = np.ascontiguousarray(np.dstack([shot, np.full((h, w), 255, np.uint8)]))
    img = QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
    return img.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation) if w > width else img
