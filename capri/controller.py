"""Single source of truth for what Capri is doing.

The overlay windows only *observe* this object. Later stages (wake word,
speech recognition, app launching, TTS) will drive it by calling
``set_state`` / ``log`` - they never touch the widgets directly.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QObject, Signal

from .states import State

MAX_LOG_ROWS = 4


class CompanionController(QObject):
    changed = Signal()

    def __init__(self, channel: str = "SYSTEM") -> None:
        super().__init__()
        self.channel = channel
        self.state = State.IDLE
        self.message = ""
        self.emotion = ""          # how she feels about this message ("" = default for the state)
        self.entries: deque[tuple[str, str]] = deque(maxlen=MAX_LOG_ROWS)
        self.total = 0             # lines logged so far (the feed shows each new one once)

    def set_state(self, state: State, message: str, emotion: str = "") -> None:
        self.state = state
        self.message = message
        self.emotion = emotion
        self.changed.emit()

    def log(self, verb: str, detail: str) -> None:
        self.entries.append((verb, detail))
        self.total += 1
        self.changed.emit()
