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


def test_the_deck_is_a_bar_she_stands_on_and_steps_off():
    from capri.ui import music_deck as md
    from test_v111 import companion
    t = [100.0]
    c = companion()
    c.place()
    feet = c.content_geometry().bottom()
    deck = MusicDeck()
    keeper = DeckKeeper(deck, c, lambda: "Artist - Song", lambda: True, clock=lambda: t[0])
    keeper.music_changed(True)
    t[0] += md.RISE
    keeper._step()
    assert deck.isVisible() and deck.title == "Artist - Song" and deck.width() > deck.height() * 3   # landscape
    body = c.content_geometry()
    assert body.bottom() == feet - (md.BODY - md.SINK)                 # up on it...
    assert deck.y() == body.bottom() + 1 - md.SINK                     # ...feet on its top edge
    area = c.screen.availableGeometry()
    assert deck.x() <= body.left() and deck.geometry().right() >= body.right()          # under all of her
    assert deck.geometry().right() <= area.right() and deck.y() + md.BODY <= area.bottom() + 1   # on screen
    keeper.music_changed(False)
    t[0] += md.LINGER + 1
    keeper.tick()
    t[0] += md.RISE
    keeper._step()
    assert not deck.isVisible() and c.platform == 0 and c.content_geometry().bottom() == feet   # back on the floor


def test_she_lies_on_the_deck_with_her_text_box_under_it():
    from capri.ui import music_deck as md
    from test_v111 import companion
    t = [100.0]
    c = companion(lounge=True)
    c.set_lounge(True)
    c.place()
    deck = MusicDeck()
    keeper = DeckKeeper(deck, c, lambda: "x", lambda: True, clock=lambda: t[0])
    keeper.music_changed(True)
    t[0] += md.RISE
    keeper._step()
    body = c.content_geometry()
    assert c.lounging() and deck.y() == body.bottom() + 1 - md.SINK and deck.width() >= body.width()
    assert c.panel.y() + 20 > deck.y() + md.BODY - 20                    # the text box below the deck


def test_deck_off_in_settings():
    from test_v111 import companion
    deck = MusicDeck()
    keeper = DeckKeeper(deck, companion(), lambda: "x", lambda: False)
    keeper.music_changed(True)
    assert not deck.isVisible() and keeper.companion.platform == 0


def test_turn_the_deck_on_and_off_by_voice():
    from capri.commands.parser import Kind, parse
    for said, which in (("hide the music bar", "off"), ("turn off the music deck", "off"), ("turn the music bar off", "off"),
                        ("show the music bar", "on"), ("bring back the music deck", "on")):
        got = parse(said)
        assert got.kind == Kind.MUSIC_DECK and got.query == which, said
    assert parse("pause the music").kind == Kind.MEDIA and parse("close spotify").kind == Kind.CLOSE


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



# -- online voices: exactly as the service makes them -----------------------------------------------------------------
def test_online_voices_get_no_effects_and_one_request_per_line():
    import numpy as np
    from capri.settings import Settings
    from capri.speech.engines import Audio
    from capri.speech.speaker import Speaker
    sent = []
    clean = (np.sin(np.arange(4410) / 7) * 0.3).astype(np.float32)

    class Box:
        last = ("fish: your Fish Audio voice", "")

        def synthesize(self, text, voice, speed, pitch):
            sent.append(text)
            return Audio(clean.copy(), 22050, pitched=True, natural=True, as_is=True)

        def voices(self):
            return ["fish: your Fish Audio voice"]
    played = []
    s = Settings(speech_voice="fish: your Fish Audio voice", speech_style="glitch", speech_expression=1.0)
    sp = Speaker(s, Box, player=lambda samples, rate: played.append(samples.copy()) or (lambda: None),
                 sleep=lambda t: None)
    sp.ready.wait(5)
    sp._speak("Hey choom. This is a longer line, with more than one sentence. And a third one!")
    assert len(sent) == 1                                        # the whole line in one request
    assert np.allclose(played[0] / max(1e-9, abs(played[0]).max()), clean / abs(clean).max(), atol=1e-4)
    sp.shutdown()


def test_voice_options_hide_for_online_voices():
    from test_v11 import FakeDesktop, rig
    from test_v122 import _tab
    r = rig(FakeDesktop())
    tab = _tab(r)
    tab.show()
    tab.voice.addItem("Fish Audio (online, your key)", "fish: your Fish Audio voice")
    tab.voice.setCurrentIndex(tab.voice.findData("fish: your Fish Audio voice"))
    form = tab._voice_form
    assert not form.isRowVisible(tab.style_box) and not form.isRowVisible(tab.expression)
    assert not form.isRowVisible(tab.pitch) and tab.preset_btn.isHidden() and form.isRowVisible(tab.online_note)
    tab.voice.addItem("beeps: retro", "beeps: retro")
    tab.voice.setCurrentIndex(tab.voice.findData("beeps: retro"))
    assert form.isRowVisible(tab.style_box) and form.isRowVisible(tab.expression)
