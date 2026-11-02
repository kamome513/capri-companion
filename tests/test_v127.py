"""v1.27: her new hair (a wide hot-pink blaze of shards, moving smoothly) and the blades at her feet, on
every figure; fewer false wake-ups; a pasted AI key is checked straight away; and Discord mute / deafen
never tabs you out of a game."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from fake_vosk import RATE, FakeRecognizer, speak  # noqa: E402
from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402
from test_v13 import ButtonsService  # noqa: E402

from capri.states import State  # noqa: E402
from capri.voice.wakeword import (DECOYS, WAKE_GRAMMAR, Rejected, Wake, WakeWordListener,  # noqa: E402
                                  sounds_like_capri)


# -- her hair and the blades at her feet -----------------------------------------------------------------------
def _figure(wild: float) -> np.ndarray:
    from capri.app import asset_root
    from capri.ui.rig import Pose, Rig
    from capri.ui.sprites import SpriteArt
    rig_ = Rig(SpriteArt.load(asset_root() / "capri_v2").frame("standing")).resized(300)
    img = QImage(400, 420, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    rig_.paint(p, QPointF(200, 400), 300, Pose(t=1.0, wild=wild))
    p.end()
    from capri.ui import looks
    return looks.to_array(img)


def test_no_spikes_on_her_legs_and_a_blaze_above_her_head():
    """(v1.34: the blades on her legs were taken out again - only her hair is drawn around her.)"""
    on, off = _figure(1.0), _figure(0.0)
    feet = (slice(330, 402), slice(0, 400))
    assert ((on[feet][..., 3] > 0) == (off[feet][..., 3] > 0)).all()          # her legs: exactly her own art
    assert (on[:100, :, 3] > 0).sum() > (off[:100, :, 3] > 0).sum() + 2000   # hair well above her head


def test_hair_is_wide_and_hot_pink():
    from capri.ui.hair import STORM_RED, StormHair
    head = QRectF(100, 100, 80, 80)
    box = StormHair().shape(head, 0.5, 1.0, 0.0).boundingRect()
    assert box.width() > head.width() * 1.8 and box.top() < head.top() - head.height() * 0.8
    assert STORM_RED.red() > 240 and STORM_RED.blue() > 80


# -- false wake-ups ------------------------------------------------------------------------------------------------
def test_decoys_keep_similar_words_off_her_name():
    assert {"happy", "copy", "carry", "sorry"} <= set(DECOYS) and "capri" in WAKE_GRAMMAR and "[unk]" in WAKE_GRAMMAR


@pytest.mark.parametrize("said, yes", [
    ("capri", True), ("hey capri open discord", True), ("kapree", True), ("cap re", True), ("caprice", True),
    ("happy", False), ("copy", False), ("carry", False), ("sorry", False), ("gravy", False), ("", False),
])
def test_sounds_like_capri(said, yes):
    assert sounds_like_capri(said) is yes


class Hears(FakeRecognizer):
    """The full recogniser, hearing `heard` where 'capri' was said."""

    def __init__(self, rate, heard):
        super().__init__(rate, False)
        self.heard = heard

    def _json(self, words):
        data = json.loads(super()._json(words))
        data["text"] = data["text"].replace("capri", self.heard)
        return json.dumps(data)


def _listen(heard, word_seconds=0.4, verify=True):
    listener = WakeWordListener(lambda r: FakeRecognizer(r, True), lambda r: Hears(r, heard), RATE, 0.8)
    listener.verify_wake = verify
    listener.voice_check = None
    events = []
    for chunk in speak(0.5, "capri", 1.0, word_seconds=word_seconds):
        events += listener.feed(chunk)
    return events


def test_a_real_capri_still_wakes_her():
    assert any(isinstance(e, Wake) for e in _listen("capri"))
    assert any(isinstance(e, Wake) for e in _listen("kapree"))          # an accent: still her


def test_a_sound_alike_is_caught_on_the_second_listen():
    events = _listen("happy")
    assert not any(isinstance(e, Wake) for e in events)
    assert any(isinstance(e, Rejected) and "happy" in e.text for e in events)


def test_a_blip_too_short_to_be_her_name_does_not_wake_her():
    events = _listen("capri", word_seconds=0.1, verify=False)
    assert not any(isinstance(e, Wake) for e in events)
    assert any(isinstance(e, Rejected) and "too short" in e.text for e in events)


# -- a pasted AI key is checked straight away -------------------------------------------------------------------
def test_pasting_an_ai_key_checks_it_right_away():
    from capri import secrets
    from capri.ui.assistant_tab import AssistantTab
    secrets.delete("openai_api_key")
    r = rig(FakeDesktop())
    r.assistant.speaker.say = lambda *a, **k: True
    r.assistant.speaker.voices = lambda: []
    tested = []
    r.router.test_ai = lambda report: tested.append(report)
    tab = AssistantTab(r.assistant, r.router, None)
    tab.ai_pick.setCurrentIndex(tab.ai_pick.findData("auto"))
    assert not tab.ai_key.isHidden() or tab._ai_form.isRowVisible(tab.ai_key)      # auto: the key box is there
    tab.ai_key.setText("sk-test")
    tab.ai_key.editingFinished.emit()
    assert secrets.get("openai_api_key") == "sk-test" and tested                    # saved and tried
    assert r.assistant.settings.ai_provider == "openai" and r.assistant.settings.ai_enabled
    tab.ai_key.editingFinished.emit()                                               # same key again: no re-test
    assert len(tested) == 1
    secrets.delete("openai_api_key")


# -- Discord mid-game ------------------------------------------------------------------------------------------------
def _discord(outcome="unavailable", key="", gaming=True):
    d = FakeDesktop()
    zaps = []
    r = rig(d, discord_buttons=ButtonsService(outcome), in_game=lambda: gaming,
            zap_at=lambda *a, **k: zaps.append(a))
    r.assistant.settings.discord_deafen_key = key
    return r, d, zaps


def test_mid_game_your_keybind_is_pressed_without_touching_focus():
    r, d, zaps = _discord(key="ctrl+alt+shift+d")
    r.service.command.emit("deafen me")
    assert settle(2, lambda: r.controller.state is State.SUCCESS)
    assert d.calls == [("keys", "ctrl+alt+shift+d")] and zaps == []


def test_mid_game_the_button_is_pressed_in_the_background():
    r, d, zaps = _discord(outcome="deafened")
    r.service.command.emit("deafen me")
    assert settle(2, lambda: r.controller.state is State.SUCCESS)
    assert r.router.services.discord_buttons.calls and zaps == [] and d.calls == []   # no lightning, no keys


def test_mid_game_she_never_brings_discord_forward():
    r, d, zaps = _discord(outcome="unavailable")
    r.service.command.emit("deafen me")
    assert settle(2, lambda: r.controller.state is State.ERROR)
    assert not any(c[0] == "in_window" for c in d.calls)                           # no tabbing out
    assert "game" in r.controller.message


def test_outside_a_game_nothing_changed():
    r, d, zaps = _discord(outcome="unavailable", gaming=False)
    r.router.services.zap_at = None
    r.service.command.emit("deafen me")
    assert settle(2, lambda: r.controller.state is State.SUCCESS)
    assert any(c[0] == "in_window" for c in d.calls)                               # Discord's own shortcut
