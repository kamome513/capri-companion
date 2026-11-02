"""Settings -> PC & chat: conversation, sign-in greeting, start-up and Discord keys."""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .. import autostart
from ..hotkeys import parse as parse_hotkey
from ..settings import Settings

DISCORD_HELP = ("Out of the box Capri presses Discord's own Ctrl+Shift+M / Ctrl+Shift+D, by bringing Discord "
                "to the front for a split second - that can't reach Discord while it's closed to the tray, and "
                "can blip a full-screen game. For a clean, works-anywhere toggle: in Discord open User Settings "
                "→ Keybinds → Add a Keybind → Toggle Mute (and Toggle Deafen), record a combo like "
                "Ctrl+Alt+Shift+M, and type the same combo here.")
POWER_HELP = ("“Shut down”, “restart” and “sleep” always ask you first, out loud - anything but a clear “yes” "
              "keeps the PC on. “Lock my PC” and “minimise everything” / “bring them back” just happen.")


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class PcTab(QWidget):
    def __init__(self, settings: Settings, on_saved: Callable[[], None], preview_greeting: Callable[[], None],
                 game_hype=None, join_now: Callable[[], None] | None = None, updates=None,
                 restart: Callable[[], None] | None = None) -> None:
        super().__init__()
        self._join_now = join_now
        self.updates = updates
        self.settings = settings
        self._on_saved = on_saved
        self.game_hype = game_hype
        s = settings
        root = QVBoxLayout(self)

        talk = QGroupBox("Conversation")
        form = QFormLayout(talk)
        self.conversation = QCheckBox("Keep chatting: when she asks you something, listen for your answer "
                                      "(no “Hey Capri” needed)")
        self.conversation.setChecked(s.conversation)
        form.addRow(self.conversation)
        self.teleport = QCheckBox("Red lag lightning: zap Discord's buttons, blast windows she closes, dash "
                                  "over to zap folders and minimise buttons")
        self.teleport.setChecked(s.teleport)
        form.addRow(self.teleport)
        form.addRow(_hint("Try “hey Capri, how are you”, “tell me a joke”, “I'm bored”. With AI chat on "
                          "(Assistant tab) she can talk about anything."))
        root.addWidget(talk)

        hello = QGroupBox("When you sign in")
        form = QFormLayout(hello)
        self.greet = QCheckBox("Greet me when I sign in, unlock or wake the PC")
        self.greet.setChecked(s.greet_on_login)
        self.big = QCheckBox("Big, in the middle of the screen (then she shrinks back to her corner)")
        self.big.setChecked(s.big_greeting)
        self.start = QCheckBox("Start Capri with Windows" if not autostart.LINUX else "Start Capri when I log in")
        self.start.setEnabled(autostart.SUPPORTED)
        self.start.setChecked(autostart.is_enabled())
        form.addRow(self.greet)
        form.addRow(self.big)
        form.addRow(self.start)
        preview = QPushButton("Preview greeting")
        preview.clicked.connect(lambda: (self.apply(), preview_greeting()))
        form.addRow(preview)
        root.addWidget(hello)

        hype = QGroupBox("Game hype  (“nice kill!”)")
        form = QFormLayout(hype)
        form.addRow(_hint("She cheers when you get kills, multi-kills and wins. Works in Counter-Strike 2, Dota 2 "
                          "and League of Legends (the games that report kills; Valorant, Fortnite and Apex don't). "
                          "For CS2 / Dota 2 she adds a small config file to the game's folder - restart the game once."))
        self.hype = QCheckBox("Cheer when I get kills")
        self.hype.setChecked(s.game_hype)
        self.hype_deaths = QCheckBox("Also say something when I die")
        self.hype_deaths.setChecked(s.game_hype_deaths)
        self.hype_screen = QCheckBox("Any game: watch my screen for kills (\u201cELIMINATED\u201d, \u201cHEADSHOT\u201d, "
                                     "\u201cVICTORY\u201d...) - read on this PC, never sent anywhere")
        self.hype_screen.setChecked(s.game_hype_screen)
        self.hype_encourage = QCheckBox("Encourage me now and then while I play (\u201cyou're doing great\u201d)")
        self.hype_encourage.setChecked(s.game_hype_encourage)
        self.hype_status = QLabel("")
        self.hype_status.setObjectName("hint")
        self.hype_status.setWordWrap(True)
        form.addRow(self.hype)
        form.addRow(self.hype_deaths)
        form.addRow(self.hype_screen)
        form.addRow(self.hype_encourage)
        if self.game_hype is not None:
            preview = QPushButton("Preview - hear what she says")
            preview.setToolTip("She says a run of lines - a kill, a headshot, a double, an ace, a win... - "
                               "in her current personality.")
            preview.clicked.connect(self._preview_hype)
            form.addRow(preview)
        form.addRow(self.hype_status)
        root.addWidget(hype)

        discord = QGroupBox("Discord  (“mute me”, “deafen me”)")
        form = QFormLayout(discord)
        form.addRow(_hint(DISCORD_HELP))
        self.mute_key = QLineEdit(s.discord_mute_key)
        self.mute_key.setPlaceholderText("empty = Discord's Ctrl+Shift+M")
        self.deafen_key = QLineEdit(s.discord_deafen_key)
        self.deafen_key.setPlaceholderText("empty = Discord's Ctrl+Shift+D")
        form.addRow("Toggle Mute keybind", self.mute_key)
        form.addRow("Toggle Deafen keybind", self.deafen_key)
        from ..integrations import discord_presence
        self.presence = QCheckBox("Show \u201cPlaying Capri\u201d on my Discord profile (plugged in / music)")
        self.presence.setChecked(getattr(s, "discord_presence", True))
        self.presence.setEnabled(discord_presence.APP_ID != "")
        self.presence.setToolTip("Your friends see animated Capri: \u201cPlugged in\u201d or \u201cVibing to "
                                 "music\u201d (never the song, never what you say to her). While you're in a game "
                                 "she steps off Discord so your game shows. Discord's own Activity Privacy setting "
                                 "still decides who sees it.")
        form.addRow(self.presence)
        root.addWidget(discord)

        call = QGroupBox("Discord call  (“join call”, “leave call”, “stream my screen”)")
        form = QFormLayout(call)
        form.addRow(_hint("1. In Discord, right-click the voice channel you want -> Copy Link.  2. Paste it below.  "
                          "3. Say “Hey Capri, join call” - she opens it and presses Join Voice."))
        self.call = QLineEdit(s.discord_call)
        self.call.setPlaceholderText("https://discord.com/channels/...")
        form.addRow("Your voice channel", self.call)
        self.leave_key = QLineEdit(s.discord_leave_key)
        self.leave_key.setPlaceholderText("optional: Discord -> Settings -> Keybinds -> Disconnect from Voice Channel, "
                                          "then type the same keys here (e.g. ctrl+shift+l)")
        form.addRow("Leave call keybind", self.leave_key)
        self.join_test = QPushButton("Join it now")
        self.join_test.clicked.connect(lambda: self.apply() and self._join_now is not None and self._join_now())
        form.addRow(self.join_test)
        root.addWidget(call)

        upd = QGroupBox("Updates")
        form = QFormLayout(upd)
        self.auto_update = QCheckBox("Update automatically: check GitHub once a day, download a new Capri in the "
                                     "background, and install it the next time she starts")
        self.auto_update.setChecked(getattr(s, "auto_update", True))
        form.addRow(self.auto_update)
        self.update_btn = QPushButton("Check for updates now")
        self.update_status = _hint(updates.status if updates is not None else "")
        self.update_status.setWordWrap(True)
        if updates is not None:
            self.update_btn.clicked.connect(updates.menu_clicked)
            updates.changed.connect(self._update_changed)
        else:
            self.update_btn.setEnabled(False)
        form.addRow(self.update_btn, self.update_status)
        self.restart_btn = QPushButton("Restart Capri")
        self.restart_btn.setToolTip("Close and start her again - a downloaded update installs on the way")
        if restart is not None:
            self.restart_btn.clicked.connect(restart)
        else:
            self.restart_btn.setEnabled(False)
        form.addRow(self.restart_btn, _hint("Close and start her again. A downloaded update installs on the way."))
        root.addWidget(upd)

        power = QGroupBox("PC power and windows")
        QVBoxLayout(power).addWidget(_hint(POWER_HELP))
        root.addWidget(power)
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

    def _preview_hype(self) -> None:
        lines = self.game_hype.preview()
        self.hype_status.setText("Preview: " + "  \u2022  ".join(lines))

    def apply(self) -> bool:
        s = self.settings
        for box in (self.mute_key, self.deafen_key, self.leave_key):
            combo = box.text().strip().lower().replace(" ", "")
            if combo:
                try:
                    parse_hotkey(combo)
                except ValueError as exc:
                    self.status.setText(f"Discord keybind “{box.text()}”: {exc}")
                    return False
            box.setText(combo)
        s.auto_update = self.auto_update.isChecked()
        s.conversation = self.conversation.isChecked()
        s.teleport = self.teleport.isChecked()
        s.greet_on_login = self.greet.isChecked()
        s.big_greeting = self.big.isChecked()
        s.discord_mute_key = self.mute_key.text()
        s.discord_deafen_key = self.deafen_key.text()
        s.discord_leave_key = self.leave_key.text()
        from ..integrations.app_buttons import call_link
        if self.call.text().strip() and call_link(self.call.text()) is None:
            self.status.setText("Your call: paste a voice channel link (right-click the channel -> Copy Link).")
            return False
        s.discord_call = self.call.text().strip()
        s.discord_presence = self.presence.isChecked()
        s.game_hype = self.hype.isChecked()
        s.game_hype_deaths = self.hype_deaths.isChecked()
        s.game_hype_screen = self.hype_screen.isChecked()
        s.game_hype_encourage = self.hype_encourage.isChecked()
        message = "Saved."
        if autostart.SUPPORTED and self.start.isChecked() != autostart.is_enabled():
            try:
                autostart.set_enabled(self.start.isChecked())
            except OSError as exc:
                message = f"Couldn't change {autostart.LABEL}: {exc}"
        s.save()
        self._on_saved()
        if self.game_hype is not None:
            self.hype_status.setText(self.game_hype.apply())
        self.status.setText(message)
        return True

    def _update_changed(self, text: str) -> None:
        self.update_status.setText(text)
        if self.updates is not None:
            self.update_btn.setText(self.updates.label())
