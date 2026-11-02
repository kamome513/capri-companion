"""Turns the speaker's loudness track into a live 0..1 level at 30 fps.

Runs only while she's talking, so idle CPU stays at zero.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from .sprites import visemes_for_text

QUIET = 0.25    # below this loudness the mouth is closed


class LipSync(QObject):
    level = Signal(float)          # 0 = silent / mouth closed, 1 = loudest
    talking = Signal(bool)
    progress = Signal(float)       # 0..1 through the sentence (for the typewriter text)
    viseme = Signal(str)           # mouth shape (A, E, O, M, TH...) - "" while closed

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._levels: list[float] = []
        self._frame = 1 / 30
        self._duration = 0.0
        self._start = 0.0
        self._smoothed = 0.0
        self._visemes: list[str] = []
        self._last_viseme = ""

    def start(self, text: str, levels: list, frame: float, duration: float) -> None:
        self._levels, self._frame, self._duration = list(levels), frame, max(duration, 0.01)
        self._visemes = visemes_for_text(text)
        self._start = time.monotonic()
        self._smoothed = 0.0
        self.talking.emit(True)
        self._timer.start()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.level.emit(0.0)
            self.viseme.emit("")
            self.progress.emit(1.0)
            self.talking.emit(False)

    def _tick(self) -> None:
        elapsed = time.monotonic() - self._start
        if elapsed >= self._duration:
            return self.stop()
        i = int(elapsed / self._frame)
        raw = self._levels[i] if i < len(self._levels) else 0.0
        # quick attack, slower release - reads as a mouth opening and closing
        self._smoothed = raw if raw > self._smoothed else self._smoothed * 0.6 + raw * 0.4
        self.level.emit(self._smoothed)
        self.progress.emit(elapsed / self._duration)
        # Mouth shape: walk through the sentence's letters in step with the audio.
        shape = ""
        if self._visemes and self._smoothed >= QUIET:
            shape = self._visemes[min(len(self._visemes) - 1, int(elapsed / self._duration * len(self._visemes)))]
        if shape != self._last_viseme:
            self._last_viseme = shape
            self.viseme.emit(shape)
