"""The "Extras" welcome: shown once, a few seconds after she starts (and once after updating to a version with new
extras), so you can switch on the things that start off. Everything here is in Settings too."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# (setting, title, what it does)
EXTRAS = [
    ("watch_screen", "Watch my screen",
     "Now and then she glances at your screen and says something about it. The picture goes to your AI."),
    ("clips", "Clip my games",
     "She keeps the last two minutes of your game. Say “clip that” and she saves it as a video."),
    ("roam", "Roam around", "She goes for little walks along the bottom of your screen."),
    ("throwable", "Throw her", "Flick her and let go. She hits the edge of the screen hard."),
    ("voice_enabled", "Listen for “Hey Capri”", "She listens for her name, on your PC, and answers when you say it."),
]


class _Signals(QObject):
    clips = Signal(str)        # "" = on, else why not


class ExtrasDialog(QDialog):
    def __init__(self, settings, on_saved: Callable[[], None],
                 clips_turn_on: Callable[[Callable[[str], None]], None] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings, self.on_saved, self.clips_turn_on = settings, on_saved, clips_turn_on
        self.setWindowTitle("Capri - Extras")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(520)
        from .deck import STYLE
        self.setStyleSheet(STYLE)                              # her cyberdeck look, like Settings
        root = QVBoxLayout(self)
        title = QLabel("EXTRAS")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 20px; font-weight: 700; letter-spacing: 2px; color: #ff2d55;")
        root.addWidget(title)
        intro = QLabel("Pick what you want her to do. You can change any of it later in Settings.")
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.boxes: dict[str, QCheckBox] = {}
        for key, name, what in EXTRAS:
            row = QVBoxLayout()
            box = QCheckBox(name)
            box.setChecked(bool(getattr(settings, key, False)))
            box.setStyleSheet("font-weight: 600;")
            row.addWidget(box)
            hint = QLabel(what)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            hint.setContentsMargins(26, 0, 0, 6)
            row.addWidget(hint)
            root.addLayout(row)
            self.boxes[key] = box
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        done = QPushButton("Done")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        buttons.addWidget(done)
        root.addLayout(buttons)
        self._signals = _Signals()
        self._signals.clips.connect(self._clips_ready)

    def accept(self) -> None:
        s = self.settings
        for key, box in self.boxes.items():
            if key == "clips":
                continue
            setattr(s, key, box.isChecked())
        want_clips = self.boxes["clips"].isChecked()
        if not want_clips:
            s.clips = False
        s.extras_offered = True
        s.save()
        self.on_saved()
        if want_clips and not s.clips and self.clips_turn_on is not None:
            self.status.setText("Setting up clips (on Windows the recorder downloads once, about 31 MB)...")
            signals, turn_on = self._signals, self.clips_turn_on

            def work() -> None:
                try:
                    turn_on(lambda text: None)
                    signals.clips.emit("")
                except Exception as exc:
                    signals.clips.emit(str(exc) or type(exc).__name__)
            threading.Thread(target=work, daemon=True, name="capri-extras-clips").start()
            return                                          # stays open until clips are ready (or not)
        super().accept()

    def _clips_ready(self, problem: str) -> None:
        if problem:
            self.boxes["clips"].setChecked(False)
            self.status.setText(f"Clips didn't turn on: {problem}")
            return
        self.on_saved()
        super().accept()
