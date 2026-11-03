"""v2.0: the music deck, the chat bits on her text box (what you said + TYPE / TALK), and hovering over her."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QRect, QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ui.music_deck import DeckKeeper, MusicDeck, tidy_title  # noqa: E402


@pytest.mark.parametrize("raw,clean", [
    ("Chase Atlantic - Consume - YouTube Music - Google Chrome", "Chase Atlantic - Consume"),
    ("Starboy • The Weeknd", "Starboy - The Weeknd"),
    ("Spotify Premium", "Music"), ("Spotify Free", "Music"), ("Daft Punk - One More Time", "Daft Punk - One More Time"),
])
def test_song_titles(raw, clean):
    assert tidy_title(raw) == clean


def test_the_deck_buttons_press_media_keys():
    deck = MusicDeck()
    deck.set_music(True, "A - B")
    deck.shown_at = 0
    img = QImage(deck.size(), QImage.Format.Format_ARGB32_Premultiplied)
    deck.render(img)                                             # draws (and lays out its buttons)
    got = []
    deck.pressed.connect(got.append)
    for name in ("previous", "play_pause", "next"):
        centre = deck._buttons[name].center()
        deck._clicked(deck.mapToGlobal(QPoint(int(centre.x()), int(centre.y()))))
    assert got == ["previous", "play_pause", "next"]


class FakeCompanion:
    hidden = drone = busy_elsewhere = False

    def __init__(self):
        self.screen = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 1600, 860))

    def content_geometry(self):
        return QRect(1400, 560, 90, 300)


def test_the_deck_comes_and_goes_with_the_music():
    t = [100.0]
    deck = MusicDeck()
    keeper = DeckKeeper(deck, FakeCompanion(), lambda: "Artist - Song", lambda: True, clock=lambda: t[0])
    keeper.music_changed(True)
    assert deck.isVisible() and deck.title == "Artist - Song"
    assert deck.pos().x() + deck.width() <= 1400                  # beside her, not on her
    keeper.music_changed(False)
    keeper.tick()
    assert deck.isVisible()                                      # stays a moment after the song
    t[0] += 10
    keeper.tick()
    assert not deck.isVisible()


def test_deck_off_in_settings():
    deck = MusicDeck()
    keeper = DeckKeeper(deck, FakeCompanion(), lambda: "x", lambda: False)
    keeper.music_changed(True)
    assert not deck.isVisible()


# -- her text box: what you said, TYPE / TALK ----------------------------------------------------------------------
def panel():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.states import State
    from capri.ui.status_panel import StatusPanel
    c = CompanionController()
    c.log("Heard", '"open discord" -> "open discord"')
    c.log("Launch", "Discord")
    c.set_state(State.SUCCESS, "Opened Discord.")
    p = StatusPanel(c, QImage(str(asset_root() / "capri" / "icon.png")))
    p.refresh()
    img = QImage(p.size(), QImage.Format.Format_ARGB32_Premultiplied)
    p.render(img)
    return p


def test_text_box_shows_what_you_said():
    p = panel()
    assert p.heard() == "open discord" and p._you == "open discord"


def test_type_and_talk_buttons():
    p = panel()
    got = []
    p.type_clicked.connect(lambda: got.append("type"))
    p.talk_clicked.connect(lambda: got.append("talk"))
    for name in ("type", "talk"):
        centre = p._buttons[name].center()
        p._clicked(p.mapToGlobal(QPoint(int(centre.x()), int(centre.y()))))
    assert got == ["type", "talk"]


def test_chat_bits_can_be_turned_off():
    p = panel()
    tall = p.height()
    p.chat_bits = False
    p.refresh()
    p.render(QImage(p.size(), QImage.Format.Format_ARGB32_Premultiplied))
    assert p.height() < tall and p._buttons == {}


# -- hovering -----------------------------------------------------------------------------------------------------------
def test_she_floats_up_when_your_mouse_is_on_her():
    from test_v111 import companion
    ch = companion().character
    ch._hover_on, ch._hover_x = True, ch.width() * 0.8
    for _ in range(40):
        ch._hover_step(1 / 60)
    assert ch._hover > 0.9 and ch._special()
    pose = ch.figure_pose()
    assert pose.lean > 0 and pose.energy >= 0.4                 # leaning toward your cursor, hair up
    ch._hover_on = False
    for _ in range(120):
        ch._hover_step(1 / 60)
    assert ch._hover == 0.0
