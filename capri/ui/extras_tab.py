"""Settings -> Extras: the things you can switch on (everything that used to be on the first-start welcome),
and how her text box and glitches behave."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ..settings import Settings


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class _ClipSignals(QObject):
    progress = Signal(str)
    done = Signal(str)


class ExtrasTab(QWidget):
    def __init__(self, settings: Settings, on_saved: Callable[[], None],
                 clips_turn_on: Callable[[Callable[[str], None]], None] | None = None) -> None:
        super().__init__()
        self.settings, self._on_saved, self._clips_turn_on = settings, on_saved, clips_turn_on
        self._clip_signals = _ClipSignals()
        self._clip_signals.progress.connect(lambda text: self.clip_status.setText(text))
        self._clip_signals.done.connect(self._clips_ready)
        s = settings
        root = QVBoxLayout(self)

        look = QGroupBox("Her text box and glitches")
        form = QFormLayout(look)
        self.panel_mode = QComboBox()
        for key, label in (("always", "Always there"), ("popup", "Only when she talks back (pops up)"),
                           ("name", "Only when you say her name (pops up)"), ("never", "Never (just her)")):
            self.panel_mode.addItem(label, key)
        mode = "never" if not s.show_panel else ("name" if s.panel_on_name else "popup") if s.panel_popup \
            else "always"
        self.panel_mode.setCurrentIndex(self.panel_mode.findData(mode))
        form.addRow("Text box", self.panel_mode)
        self.panel_chat = QCheckBox("Show what you said, and TYPE / TALK buttons on it")
        self.panel_chat.setChecked(s.panel_chat)
        form.addRow(self.panel_chat)
        self.glitch_every = QComboBox()
        for secs, label in ((0, "never"), (60, "every minute"), (180, "every 3 minutes"), (300, "every 5 minutes"),
                            (600, "every 10 minutes")):
            self.glitch_every.addItem(label, secs)
        index = self.glitch_every.findData(s.glitches)
        if index < 0:
            self.glitch_every.addItem(f"every {s.glitches} seconds", s.glitches)
            index = self.glitch_every.count() - 1
        self.glitch_every.setCurrentIndex(index)
        form.addRow("She glitches", self.glitch_every)
        root.addWidget(look)

        clips = QGroupBox("Clips  (“hey Capri, clip that”)")
        form = QFormLayout(clips)
        form.addRow(_hint("She keeps the last two minutes of your screen and sound on your PC. Say “clip that” (or "
                          "“clip the last minute”) and she saves it as a video. Nothing is uploaded."))
        self.clip_on = QCheckBox("Clip my games")
        self.clip_on.setChecked(s.clips)
        form.addRow(self.clip_on)
        self.clip_when = QComboBox()
        for key, label in (("games", "Only while I'm in a game"), ("always", "Always (any screen)")):
            self.clip_when.addItem(label, key)
        self.clip_when.setCurrentIndex(max(0, self.clip_when.findData(s.clip_when)))
        form.addRow("Record", self.clip_when)
        self.clip_length = QComboBox()
        for secs in (15, 30, 60, 90, 120):
            self.clip_length.addItem(f"{secs} seconds" if secs < 60 else f"{secs // 60} min" if secs % 60 == 0
                                     else "1.5 min", secs)
        self.clip_length.setCurrentIndex(max(0, self.clip_length.findData(s.clip_length)))
        form.addRow("“Clip that” saves", self.clip_length)
        self.clip_fps = QComboBox()
        for fps in (30, 60):
            self.clip_fps.addItem(f"{fps} fps", fps)
        self.clip_fps.setCurrentIndex(max(0, self.clip_fps.findData(s.clip_fps)))
        form.addRow("Frame rate", self.clip_fps)
        self.clip_res = QComboBox()
        for key, label in (("auto", "Auto (up to 1080p)"), ("720p", "720p (lightest)"), ("1080p", "1080p"),
                           ("full", "Full (as your screen is)")):
            self.clip_res.addItem(label, key)
        self.clip_res.setCurrentIndex(max(0, self.clip_res.findData(s.clip_resolution)))
        form.addRow("Resolution", self.clip_res)
        self.clip_sound = QCheckBox("With sound (what your speakers play)")
        self.clip_sound.setChecked(s.clip_sound)
        form.addRow(self.clip_sound)
        self.clip_moments = QCheckBox("Save big moments by themselves (triple kills, aces, wins - with Game hype)")
        self.clip_moments.setChecked(s.clip_moments)
        form.addRow(self.clip_moments)
        from ..integrations.clips import default_folder
        self._clip_folder = s.clip_folder or str(default_folder())
        self.clip_folder = QLabel(self._clip_folder)
        self.clip_folder.setObjectName("hint")
        self.clip_folder.setWordWrap(True)
        pick = QPushButton("Choose folder...")
        pick.clicked.connect(self._choose_clip_folder)
        form.addRow(pick, self.clip_folder)
        open_btn = QPushButton("Open clips folder")
        open_btn.clicked.connect(self._open_clip_folder)
        self.clip_status = _hint("")
        form.addRow(open_btn, self.clip_status)
        root.addWidget(clips)

        watch = QGroupBox("Watch my screen  (“hey Capri, what do you see?”)")
        form = QFormLayout(watch)
        form.addRow(_hint("Now and then she glances at your screen and says something about it. The picture goes "
                          "to the AI you picked (Assistant tab) - with Ollama it stays on your PC. She doesn't look "
                          "while a password manager, bank, sign-in page or private window is in front."))
        self.watch_on = QCheckBox("Watch my screen and comment")
        self.watch_on.setChecked(s.watch_screen)
        form.addRow(self.watch_on)
        self.watch_every = QComboBox()
        for secs in (60, 120, 300, 600):
            self.watch_every.addItem("every minute" if secs == 60 else f"every {secs // 60} minutes", secs)
        self.watch_every.setCurrentIndex(max(0, self.watch_every.findData(s.watch_every)))
        form.addRow("How often", self.watch_every)
        self.watch_remember = QCheckBox("Remember what she sees (her last few comments, on your PC)")
        self.watch_remember.setChecked(s.watch_remember)
        form.addRow(self.watch_remember)
        root.addWidget(watch)

        her = QGroupBox("Her on your desktop")
        form = QFormLayout(her)
        self.throwable = QCheckBox("Throw her: flick her and let go (she slams into the edge of the screen)")
        self.throwable.setChecked(s.throwable)
        form.addRow(self.throwable)
        self.roam = QCheckBox("Roam around: now and then she teleports somewhere else along the bottom")
        self.roam.setChecked(s.roam)
        form.addRow(self.roam)
        form.addRow(_hint("Say “teleport” / “go for a walk” or “stay there”."))
        self.music_deck = QCheckBox("Music deck: while music plays, she stands on a neon bar (song, play / pause, skip)")
        self.music_deck.setChecked(s.music_deck)
        form.addRow(self.music_deck)
        self.game_play = QCheckBox("Let her play games: say “play this for me” (she presses keys and clicks in the "
                                   "game in front - Esc stops her)")
        self.game_play.setChecked(s.game_play)
        form.addRow(self.game_play)
        self.head_pats = QCheckBox("Head pats: click her head and she reacts (click her body: a poke)")
        self.head_pats.setChecked(s.head_pats)
        form.addRow(self.head_pats)
        root.addWidget(her)

        mic = QGroupBox("Her voice in your mic  (Discord, Roblox, games)")
        form = QFormLayout(mic)
        form.addRow(_hint("Her voice also plays on the device you pick here. Pick a virtual cable (VB-Audio "
                          "Virtual Cable is free: pick “CABLE Input”) or “Steam Streaming Speakers”, then in "
                          "Discord / Roblox pick the matching microphone (“CABLE Output” / “Steam Streaming "
                          "Microphone”). Your friends hear her."))
        from ..speech.speaker import output_devices
        self.mic_device = QComboBox()
        self.mic_device.addItem("Off", "")
        for name in output_devices():
            self.mic_device.addItem(name, name)
        if s.mic_voice_device and self.mic_device.findData(s.mic_voice_device) < 0:
            self.mic_device.addItem(s.mic_voice_device + "  (not plugged in)", s.mic_voice_device)
        self.mic_device.setCurrentIndex(max(0, self.mic_device.findData(s.mic_voice_device)))
        form.addRow("Also play her voice on", self.mic_device)
        root.addWidget(mic)
        root.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        row.addWidget(self.status)
        save = QPushButton("Save")
        save.clicked.connect(self.apply)
        row.addWidget(save)
        root.addLayout(row)

    def apply(self) -> bool:
        s = self.settings
        mode = self.panel_mode.currentData()
        s.show_panel, s.panel_popup, s.panel_on_name = mode != "never", mode in ("popup", "name"), mode == "name"
        s.panel_chat = self.panel_chat.isChecked()
        s.glitches = int(self.glitch_every.currentData())
        s.clip_when = self.clip_when.currentData()
        s.clip_length = int(self.clip_length.currentData())
        s.clip_fps = int(self.clip_fps.currentData())
        s.clip_resolution = self.clip_res.currentData()
        s.clip_sound = self.clip_sound.isChecked()
        s.clip_moments = self.clip_moments.isChecked()
        from ..integrations.clips import default_folder
        s.clip_folder = "" if self._clip_folder == str(default_folder()) else self._clip_folder
        s.watch_screen = self.watch_on.isChecked()
        s.watch_every = int(self.watch_every.currentData())
        s.watch_remember = self.watch_remember.isChecked()
        s.throwable = self.throwable.isChecked()
        s.head_pats = self.head_pats.isChecked()
        s.game_play = self.game_play.isChecked()
        s.music_deck = self.music_deck.isChecked()
        s.mic_voice_device = self.mic_device.currentData() or ""
        s.roam = self.roam.isChecked()
        if not self.clip_on.isChecked():
            s.clips = False
        elif not s.clips and self._clips_turn_on is not None:
            self._start_clips()                       # may download the recorder first (Windows)
        s.save()
        self._on_saved()
        self.status.setText("Saved.")
        return True

    # -- clips --------------------------------------------------------------------------------------------------
    def _start_clips(self) -> None:
        self.clip_status.setText("Turning clips on...")
        signals, turn_on = self._clip_signals, self._clips_turn_on

        def work() -> None:
            try:
                turn_on(signals.progress.emit)
                signals.done.emit("")
            except Exception as exc:
                signals.done.emit(str(exc) or type(exc).__name__)
        threading.Thread(target=work, daemon=True, name="capri-clips-on").start()

    def _clips_ready(self, problem: str) -> None:
        if problem:
            self.clip_on.setChecked(False)
            self.clip_status.setText(f"Clips didn't turn on: {problem}")
        else:
            self.clip_status.setText("Clips are on. Say “clip that” in a game.")
            self._on_saved()

    def _choose_clip_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Where clips go", self._clip_folder)
        if folder:
            self._clip_folder = folder
            self.clip_folder.setText(folder)

    def _open_clip_folder(self) -> None:
        folder = Path(self._clip_folder)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

