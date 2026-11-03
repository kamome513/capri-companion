"""Settings -> Character: which art Capri uses and how lively she is."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QWidget

from . import looks

if TYPE_CHECKING:
    from .companion import Companion

STYLES = [
    ("body", "Full body (character sheet): idle animation, poses, wild hair"),
    ("portrait", "Portrait (character sheet): talking head with all 16 mouth shapes"),
    ("classic", "Classic: the first screenshots, in a neon card"),
]


class LookTab(QWidget):
    def __init__(self, companion: Companion) -> None:
        super().__init__()
        self.companion = companion
        s = companion.settings
        have_sheet = companion.sprites is not None
        form = QFormLayout(self)

        self.style_box = QComboBox()
        for key, label in STYLES:
            if key != "classic" and not have_sheet:
                continue
            self.style_box.addItem(label, key)
        for name in looks.available():                    # the animated pictures (assets/looks + your looks/)
            self.style_box.addItem(f"Look: {name} (animated picture)", "look:" + name)
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(s.character_style)))
        self.style_box.currentIndexChanged.connect(lambda _i: companion.set_style(self.style_box.currentData()))
        form.addRow("Style", self.style_box)
        tip = QLabel("Add your own looks: drop pictures of her into the looks folder next to run.bat, then restart.")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        form.addRow(tip)

        from .hair import HAIR_STYLES
        self.hair_box = QComboBox()
        for key, label in HAIR_STYLES.items():
            self.hair_box.addItem(label, key)
        self.hair_box.setCurrentIndex(max(0, self.hair_box.findData(s.hair_style)))
        self.hair_box.setToolTip("Like the show: the zigzag pile of torn pink strands. Classic spiky: her "
                                 "first hair, a wide spiky block. Or say \u201cchange your hair\u201d.")
        self.hair_box.currentIndexChanged.connect(lambda _i: self._look())       # takes effect right away
        form.addRow("Hair", self.hair_box)
        companion.settings_changed.connect(self._sync_hair)

        self.games_box = QComboBox()
        self.games_box.addItem("Stay as herself - over the game", "herself")
        self.games_box.addItem("Turn into the little drone", "drone")
        self.games_box.setCurrentIndex(1 if s.game_drone and s.auto_game_drone else 0)
        self.games_box.setToolTip("Either way she stays on top of full-screen games (borderless / windowed full "
                                  "screen - nothing can show over exclusive full screen).")
        self.games_box.currentIndexChanged.connect(lambda _i: self._games_mode())
        form.addRow("In games", self.games_box)

        self.drone_box = QComboBox()
        self.drone_box.addItem("Disk: her shards spinning round her eye", "disk")
        self.drone_box.addItem("Mask: her green visor - eyes, fin and grin", "mask")
        self.drone_box.setCurrentIndex(max(0, self.drone_box.findData(s.drone_look)))
        self.drone_box.currentIndexChanged.connect(lambda _i: companion.set_drone_look(self.drone_box.currentData()))
        form.addRow("Drone look (games)", self.drone_box)

        self.idle = QCheckBox("Idle animation (breathing, blinking, looking around)")
        self.idle.setChecked(s.idle_animation)
        self.idle.toggled.connect(self._look)
        form.addRow(self.idle)

        self.lounge = QCheckBox("Lie on the panel (“Capri, lie down” / “get up”)")
        self.lounge.setChecked(s.lounge)
        self.lounge.setEnabled(have_sheet and companion.sprites.lying is not None)
        self.lounge.toggled.connect(companion.set_lounge)
        form.addRow(self.lounge)
        # picking another design gets her up by itself: keep the tick in step (without re-triggering it)
        companion.settings_changed.connect(self._sync_lounge)

        self.perch = QCheckBox("Sit on windows: she hops onto the window you're using, and back onto the "
                               "panel when you close it")
        self.perch.setChecked(s.perch_windows)
        self.perch.toggled.connect(companion.set_perch_windows)
        form.addRow(self.perch)

        self.acts = QCheckBox("Idle activities (glitching, gaming, watching shows, calls with D)")
        self.acts.setChecked(s.idle_acts)
        self.acts.setEnabled(have_sheet)
        self.acts.toggled.connect(companion.set_idle_acts)
        form.addRow(self.acts)

        hint = QLabel("While she talks, her face follows her emotion and her mouth follows the words. "
                      "With no animation she uses no CPU while idle.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)

    def _sync_lounge(self) -> None:
        on = self.companion.settings.lounge
        if self.lounge.isChecked() != on:
            self.lounge.blockSignals(True)
            self.lounge.setChecked(on)
            self.lounge.blockSignals(False)

    def _look(self) -> None:
        self.companion.set_look(1.0, self.idle.isChecked(), self.hair_box.currentData() or "storm")

    def _games_mode(self) -> None:
        s = self.companion.settings
        drone = self.games_box.currentData() == "drone"
        s.game_drone = s.auto_game_drone = drone
        if not drone and self.companion.drone:
            self.companion.set_drone(False)                  # in a game right now: back to herself
        self.companion._save()

    def _sync_hair(self) -> None:
        """Changed by voice or the menu: show it here (without re-triggering it)."""
        i = self.hair_box.findData(self.companion.settings.hair_style)
        if i >= 0 and i != self.hair_box.currentIndex():
            self.hair_box.blockSignals(True)
            self.hair_box.setCurrentIndex(i)
            self.hair_box.blockSignals(False)
