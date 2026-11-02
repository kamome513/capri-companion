"""System tray icon and the menu shared by the tray and right-clicking Capri."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QAction, QActionGroup, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import __version__, autostart, personality
from ..hotkeys import pretty
from . import theme
from .companion import Companion

if TYPE_CHECKING:
    from ..assistant import Assistant


def companion_has_lying(c: Companion) -> bool:
    return c.sprites is not None and c.sprites.lying is not None and c.settings.character_style != "classic"


class CompanionMenu(QObject):
    def __init__(self, companion: Companion, icon: QImage, assistant: Assistant | None = None,
                 open_settings: Callable[[], None] | None = None, open_chat: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.companion = companion
        self.assistant = assistant
        self._syncing = False
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        s = companion.settings

        menu = self.menu = QMenu()
        menu.setStyleSheet(theme.MENU_STYLE)
        self.a_hide = menu.addAction("Hide Capri", self._toggle_hidden)
        if open_chat is not None:
            menu.addAction("Chat with Capri...", open_chat)
        self.a_voice = self.a_mute = None
        if assistant is not None:
            menu.addAction(f"Listen now  ({pretty(s.hotkey_listen)})", assistant.listen_now)
        menu.addSeparator()
        # everything else sorted into folders
        if assistant is not None:
            voice = self._sub(menu, "Voice")
            self.a_voice = self._check("Voice activation (wake word)", assistant.set_voice_enabled, voice)
            self.a_mute = self._check("Mute microphone", assistant.set_muted, voice)
            self.a_speech = self._check("Spoken replies", assistant.set_speech_enabled, voice)
            self.mic_menu = self._sub(voice, "Microphone")
            self.mic_menu.aboutToShow.connect(self._fill_mics)
            assistant.settings_changed.connect(self.sync)
        capri = self._sub(menu, "Capri")
        self.design_menu = self._sub(capri, "Design")
        self.design_menu.aboutToShow.connect(self._fill_designs)
        self.a_lounge = self._check("Lie on the panel", companion.set_lounge, capri)
        self.a_perch = self._check("Sit on windows", companion.set_perch_windows, capri)
        self.a_compact = self._check("Compact mode", companion.set_compact, capri)
        hair = self._sub(capri, "Hair")
        hair_group = QActionGroup(hair)
        from .hair import HAIR_STYLES
        self.hair_styles = {}
        for key, label in HAIR_STYLES.items():
            self.hair_styles[key] = self._check(label, lambda on, k=key: on and companion.set_look(
                1.0, companion.settings.idle_animation, k), hair)
            self.hair_styles[key].setActionGroup(hair_group)
        persona = self._sub(capri, "Personality")
        persona_group = QActionGroup(persona)
        self.personalities = {}
        for p in personality.PERSONALITIES.values():
            self.personalities[p.key] = self._check(p.label, lambda on, k=p.key: on and companion.set_personality(k),
                                                    persona)
            self.personalities[p.key].setActionGroup(persona_group)
        if companion.sprites is not None:
            acts = self._sub(capri, "Do something")
            for name, label in (("glitch", "Glitch"), ("gaming", "Play a game"), ("watching", "Watch something"),
                                ("call", "Call D")):
                acts.addAction(label, lambda n=name: companion.play_act(n))
        panel = self._sub(menu, "Panel")
        self.a_panel = self._check("Show status panel", companion.set_show_panel, panel)
        self.a_log = self._check("Show activity log", companion.set_show_log, panel)
        log_style = self._sub(panel, "Activity log style")
        styles_group = QActionGroup(log_style)
        self.log_styles = {}
        for key, label in (("panel", "In the panel (classic)"), ("cards", "Call cards above the panel")):
            self.log_styles[key] = self._check(label, lambda on, k=key: on and companion.set_log_style(k), log_style)
            self.log_styles[key].setActionGroup(styles_group)
        drone = self._sub(menu, "Drone")
        self.a_drone = self._check("Drone mode now", companion.set_drone, drone)
        self.a_auto_drone = self._check("Drone mode when I'm in a game", self._set_auto_drone, drone)
        drone_look = self._sub(drone, "Look")
        self.drone_looks = {}
        looks_group = QActionGroup(drone_look)
        for key, label in (("disk", "Disk"), ("mask", "Mask (green visor)")):
            self.drone_looks[key] = self._check(label, lambda on, k=key: on and companion.set_drone_look(k), drone_look)
            self.drone_looks[key].setActionGroup(looks_group)
        drone.addAction("Tip: drag the drone anywhere").setEnabled(False)
        window = self._sub(menu, "Window")
        self.a_top = self._check("Always on top", companion.set_always_on_top, window)
        self.a_click = self._check(f"Click-through  ({pretty(s.hotkey_click_through)})",
                                   companion.set_click_through, window)
        window.addAction("Reset position", companion.reset_position)
        self.a_autostart = None
        menu.addSeparator()
        if autostart.SUPPORTED:
            self.a_autostart = self._check(autostart.LABEL, self._set_autostart)
        if open_settings is not None:
            self.a_settings = menu.addAction("Settings...", open_settings)
        self.a_update = None
        menu.addAction("Open log folder", self._open_logs)
        about = menu.addAction(f"Capri {__version__}")
        about.setEnabled(False)
        menu.addAction("Exit Capri", QApplication.quit)
        menu.aboutToShow.connect(self.sync)

        self.tray: QSystemTrayIcon | None = None
        if self.tray_available:
            self.tray = QSystemTrayIcon(QIcon(QPixmap.fromImage(icon)))
            self.tray.setToolTip("Capri")
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

        companion.context_menu_requested.connect(self.popup)
        companion.settings_changed.connect(self.sync)
        self.sync()

    def add_updates(self, updates) -> None:
        """'Check for updates' / 'Update now (Capri 1.36.0)' - just above Settings."""
        self.a_update = QAction("Check for updates", self.menu)
        self.a_update.triggered.connect(updates.menu_clicked)
        before = getattr(self, "a_settings", None)
        if before is not None:
            self.menu.insertAction(before, self.a_update)
        else:
            self.menu.addAction(self.a_update)
        self.menu.aboutToShow.connect(lambda: self.a_update.setText(updates.label()))

    def add_restart(self, restart) -> None:
        """'Restart Capri' - just above Exit. Installs a downloaded update on the way."""
        action = QAction("Restart Capri", self.menu)
        action.triggered.connect(restart)
        exit_action = next((a for a in self.menu.actions() if a.text() == "Exit Capri"), None)
        if exit_action is not None:
            self.menu.insertAction(exit_action, action)
        else:
            self.menu.addAction(action)
        self.a_restart = action

    @staticmethod
    def _sub(parent: QMenu, title: str) -> QMenu:
        sub = parent.addMenu(title)
        sub.setStyleSheet(theme.MENU_STYLE)
        return sub

    def _fill_designs(self) -> None:
        """Her looks: the three art styles and every animated picture (yours included)."""
        from . import looks
        from .look_tab import STYLES
        c = self.companion
        self.design_menu.clear()
        group = QActionGroup(self.design_menu)
        have_sheet = c.sprites is not None
        options = [(key, label.split(":")[0], key == "classic" or have_sheet) for key, label in STYLES]
        options += [("look:" + name, f"Look: {name}", True) for name in looks.available()]
        for key, label, ok in options:
            action = self.design_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == c.settings.character_style)
            action.setEnabled(ok)
            action.setActionGroup(group)
            action.triggered.connect(lambda _=False, k=key: c.set_style(k))

    def _check(self, text: str, slot, parent: QMenu | None = None) -> QAction:
        action = (parent or self.menu).addAction(text)
        action.setCheckable(True)
        action.toggled.connect(lambda on: self._apply(slot, on))
        return action

    def _set_auto_drone(self, on: bool) -> None:
        s = self.companion.settings
        s.auto_game_drone = on
        if on:
            s.game_drone = True
        s.save()

    def _apply(self, slot, on: bool) -> None:
        if not self._syncing:
            slot(on)

    def sync(self) -> None:
        """Make every tick mark reflect the real current setting."""
        c, s = self.companion, self.companion.settings
        self._syncing = True
        try:
            self.a_hide.setText("Show Capri" if c.hidden else "Hide Capri")
            self.a_panel.setChecked(s.show_panel)
            self.a_log.setChecked(s.show_log)
            for key, action in self.log_styles.items():
                action.setChecked(s.log_style == key)
            for key, action in self.hair_styles.items():
                action.setChecked(s.hair_style == key)
            self.a_log.setEnabled(s.show_panel and (not s.compact or s.log_style == "cards"))   # compact: no room
            self.a_compact.setChecked(s.compact)
            self.a_lounge.setChecked(s.lounge)
            self.a_perch.setChecked(s.perch_windows)
            for key, action in self.personalities.items():
                action.setChecked(s.personality == key)
            for key, action in self.drone_looks.items():
                action.setChecked(s.drone_look == key)
            self.a_drone.setChecked(getattr(c, "drone", False))
            self.a_auto_drone.setChecked(s.game_drone and s.auto_game_drone)
            self.a_lounge.setEnabled(companion_has_lying(c))
            self.a_top.setChecked(s.always_on_top)
            self.a_click.setChecked(s.click_through)
            # Without a tray icon, click-through would leave no way to turn it back off.
            self.a_click.setEnabled(self.tray_available)
            if self.a_autostart is not None:
                self.a_autostart.setChecked(autostart.is_enabled())
            if self.a_voice is not None:
                self.a_voice.setChecked(s.voice_enabled)
                self.a_mute.setChecked(s.mic_muted)
                self.a_speech.setChecked(s.speech_enabled)
        finally:
            self._syncing = False

    def _fill_mics(self) -> None:
        from ..voice.service import list_input_devices
        self.mic_menu.clear()
        group = QActionGroup(self.mic_menu)
        current = self.companion.settings.input_device
        names = list_input_devices()
        for label, name in [("Windows default", "")] + [(n, n) for n in names]:
            action = self.mic_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(name == current)
            action.setActionGroup(group)
            action.triggered.connect(lambda _=False, n=name: self.assistant.set_device(n))
        if not names:
            self.mic_menu.addAction("(no microphones found)").setEnabled(False)

    @staticmethod
    def _open_logs() -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..logs import log_dir
        log_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))

    def _toggle_hidden(self) -> None:
        self.companion.set_hidden(not self.companion.hidden)

    def _set_autostart(self, on: bool) -> None:
        try:
            autostart.set_enabled(on)
        except OSError as exc:
            if self.tray:
                self.tray.showMessage("Capri", f"Couldn't change {autostart.LABEL}: {exc}",
                                      QSystemTrayIcon.MessageIcon.Warning)
        self.sync()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:   # plain left-click
            self._toggle_hidden()

    def popup(self, pos: QPoint) -> None:
        self.menu.popup(pos)
