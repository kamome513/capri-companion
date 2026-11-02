"""Character-sheet art, idle animation, wild hair, lying on the panel, emotions and voice prosody."""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtCore import QRectF, QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri import emotions  # noqa: E402
from capri.app import asset_root  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.speech.speaker import MASTER_GAIN, prosody  # noqa: E402
from capri.states import State  # noqa: E402
from capri.ui.art import CharacterArt  # noqa: E402
from capri.ui.character_window import CharacterWindow  # noqa: E402
from capri.ui.companion import Companion  # noqa: E402
from capri.ui.hair import WildHair  # noqa: E402
from capri.ui.sprites import SpriteArt, visemes_for_text  # noqa: E402

ART = CharacterArt.load(asset_root() / "capri")
SPRITES = SpriteArt.load(asset_root() / "capri_v2")


@pytest.fixture(autouse=True)
def clean():
    Settings.path().unlink(missing_ok=True)
    yield
    Settings.path().unlink(missing_ok=True)


def test_sheet_imported_completely():
    assert SPRITES is not None
    assert set(SPRITES.body) >= {"idle", "blink", "look_around", "listening", "thinking", "speaking", "happy",
                                 "confused", "standing"}
    assert set(SPRITES.expressions) == {"neutral", "happy", "smirk", "surprised", "serious", "angry", "sad",
                                        "playful"}
    assert len(SPRITES.visemes) == 16 and SPRITES.lying is not None
    for img in list(SPRITES.body.values()) + [SPRITES.lying]:
        # real transparency: corners clear, middle solid
        assert img.pixelColor(0, 0).alpha() == 0 and img.pixelColor(img.width() - 1, 0).alpha() == 0
    idle = SPRITES.body["idle"]
    assert idle.pixelColor(idle.width() // 2, idle.height() // 2).alpha() == 255


def test_visemes_from_text():
    assert visemes_for_text("Launching") == ["L", "A", "O", "N", "CH", "I", "N", "D"]
    assert visemes_for_text("the sky") == ["TH", "E", "S", "D", "I"]
    assert visemes_for_text("...!") == []


def make_window(style="body"):
    w = CharacterWindow(ART, 190, True, SPRITES, style)
    w.show()
    return w


def test_body_poses_follow_state_and_emotion():
    w = make_window()
    assert w.pose_name() == "idle"
    for state, pose in ((State.LISTENING, "listening"), (State.PROCESSING, "thinking"),
                        (State.ERROR, "confused")):
        w.set_state(state)
        assert w.pose_name() == pose
    w.set_state(State.SUCCESS, "happy")
    assert w.pose_name() == "happy"
    w.set_state(State.SUCCESS, "serious")
    assert w.pose_name() == "thinking"
    w.set_talking(True)
    w.set_voice_level(0.9)
    assert w.pose_name() == "speaking"


def test_idle_animation_blinks_and_looks_around():
    w = make_window()
    w.set_state(State.IDLE)
    w._next_blink = time.monotonic() - 1
    w._tick()
    assert w.pose_name() == "blink"
    time.sleep(0.2)                                                    # a smooth blink: about 0.17 s
    assert w.pose_name() == "idle"
    w._next_look = time.monotonic() - 1
    w._next_blink = time.monotonic() + 100
    w._tick()
    assert w.pose_name() == "look_around"


def test_animation_stops_when_hidden_or_off():
    w = make_window()
    assert w._timer.isActive()
    w.hide()
    assert not w._timer.isActive()
    w.show()
    w.set_look(0.0, False)
    assert not w._timer.isActive()               # no hair, no idle animation: zero CPU at idle
    w.set_talking(True)
    assert w._timer.isActive()
    c = CharacterWindow(ART, 190, True, SPRITES, "classic")
    c.show()
    assert not c._timer.isActive()


def test_wild_hair_makes_room_and_draws():
    calm, wild = make_window(), make_window()
    calm.set_look(0.0, True)
    wild.set_look(1.0, True)
    assert wild.height() > calm.height()              # (the width is set by the room for her idle activities)
    img = QImage(300, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    WildHair().paint(p, QRectF(100, 100, 100, 80), t=1.0, intensity=1.0, energy=0.5)
    p.end()
    drawn = sum(img.pixelColor(x, y).alpha() > 0 for x in range(0, 300, 5) for y in range(0, 300, 5))
    assert drawn > 150


def test_portrait_lip_sync_and_expressions():
    w = make_window("portrait")
    assert w.pose_name() == "face:neutral"
    w.set_state(State.ERROR, "sad")
    assert w.pose_name() == "face:sad"
    w.set_talking(True)
    w.set_viseme("O")
    w.set_voice_level(0.9)
    assert w.pose_name() == "viseme:O"
    w.set_voice_level(0.1)
    assert w.pose_name() == "face:sad"          # between syllables: her emotion's face


def make_companion(**settings):
    controller = CompanionController()
    controller.set_state(State.IDLE, "Standing by.")
    c = Companion(controller, ART, Settings(**settings), SPRITES)
    c.show()
    app.processEvents()
    return c, controller


def test_lying_on_the_panel():
    c, controller = make_companion()
    c.set_lounge(True)
    app.processEvents()
    ch, panel = c.character.geometry(), c.panel.geometry()
    assert c.character.mode == "lying" and c.lounging()
    assert ch.bottom() > panel.top() and ch.top() < panel.top()       # resting on the panel's top edge
    assert not c.panel.tail_visible
    area = c.screen.availableGeometry()
    assert panel.bottom() <= area.bottom() + 1                          # still fully on screen
    assert panel.left() < c.content_geometry().center().x() < panel.right()   # she's over the panel
    assert Settings.load().lounge is True
    c.set_lounge(False)
    assert c.character.mode == "body" and c.panel.tail_visible


def test_lying_needs_the_new_art():
    c, controller = make_companion(character_style="classic")
    c.set_lounge(True)
    assert c.character.mode == "classic"


def test_panel_icon_shows_her_face():
    c, controller = make_companion()
    controller.set_state(State.ERROR, "Couldn't find photoshop.", "sad")
    assert c.panel._icon_src is SPRITES.face("sad")
    c.set_talking(True)
    c.set_viseme("A")
    assert c.panel._icon_src is SPRITES.mouth("A")
    c.set_talking(False)
    assert c.panel._icon_src is SPRITES.face("sad")
    c.set_style("classic")
    assert c.panel._icon_src is ART.icon


def test_style_switch_keeps_her_in_place():
    c, controller = make_companion()
    anchor = c.content_geometry().bottomRight()
    for style in ("portrait", "classic", "body"):
        c.set_style(style)
        assert c.content_geometry().bottomRight() == anchor
    assert Settings.load().character_style == "body"


# -- emotions + voice -------------------------------------------------------------------------
def test_emotion_tags_and_guesses():
    assert emotions.split_tag("[playful] Nice try.") == ("playful", "Nice try.")
    assert emotions.split_tag("[nonsense] Hi") == ("", "[nonsense] Hi")
    assert emotions.split_tag("Hi") == ("", "Hi")
    assert emotions.guess("Couldn't find photoshop.", State.ERROR) == "confused"
    assert emotions.guess("Spotify said no (500).", State.ERROR) == "angry"
    assert emotions.guess("Launching Deadlock.", State.SUCCESS) == "happy"
    assert emotions.guess("Close Deadlock? Say yes or no.", State.LISTENING) == "serious"
    assert emotions.guess("80% chance of rain. Grab an umbrella.", State.SUCCESS) == "sad"


def test_voice_is_girlier_and_quieter_by_default():
    s = Settings()
    speed, pitch, gain = prosody(s, "neutral")
    assert pitch > 2.0                                  # higher than the voice's own pitch
    assert gain == pytest.approx(0.6 * MASTER_GAIN)     # quieter than before (was 0.8)
    assert speed == pytest.approx(0.68)                 # her preset: a touch quicker, plus energetic (1.18)


def test_emotions_change_her_voice():
    s = Settings()
    _, p_happy, g_happy = prosody(s, "happy")
    sp_sad, p_sad, g_sad = prosody(s, "sad")
    sp_angry, _, g_angry = prosody(s, "angry")
    _, p_neutral, g_neutral = prosody(s, "neutral")
    assert p_happy > p_neutral > p_sad
    assert sp_sad < 0.5 < sp_angry
    assert g_sad < g_neutral < g_angry


def test_assistant_speaks_with_emotion():
    from types import SimpleNamespace
    from capri.assistant import Assistant
    from capri.voice.service import VoiceService
    lines = []
    speaker = SimpleNamespace(speaking_changed=SimpleNamespace(connect=lambda f: None),
                              say=lambda text, then=None, emotion="": lines.append((text, emotion)) or True)
    controller = CompanionController()
    a = Assistant(controller, Settings(), VoiceService(True, False, "", 0.8), speaker)
    a.show_result(State.ERROR, "Couldn't find photoshop.")
    a.show_result(State.SPEAKING, "Ha. Nice try.", emotion="smirk")
    assert lines == [("Couldn't find photoshop.", "confused"), ("Ha. Nice try.", "smirk")]
    assert controller.emotion == "smirk"


def test_ai_reply_emotion_is_parsed_and_not_spoken():
    from types import SimpleNamespace
    from capri.ai.claude import ClaudeBrain
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="[playful] Ha. Nope.")])
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **k: resp)))
    reply = ClaudeBrain(lambda: "k", {}, client_factory=lambda key: client).ask("do my homework")
    assert (reply.emotion, reply.text) == ("playful", "Ha. Nope.")


def test_character_tab_controls():
    from capri.ui.look_tab import LookTab
    c, controller = make_companion()
    tab = LookTab(c)
    styles = [tab.style_box.itemData(i) for i in range(tab.style_box.count())]
    assert styles[:3] == ["body", "portrait", "classic"] and "look:Grin" in styles     # + the animated pictures
    tab.style_box.setCurrentIndex(1)
    assert c.character.mode == "portrait" and Settings.load().character_style == "portrait"
    assert not hasattr(tab, "hair") and not hasattr(tab, "hair_style")       # always the full storm
    tab.idle.setChecked(False)
    assert (c.settings.wild_hair, c.settings.idle_animation) == (1.0, False)
    tab.style_box.setCurrentIndex(0)
    tab.lounge.setChecked(True)
    assert c.character.mode == "lying"


def test_storm_hair_covers_her_hair_but_not_her_face():
    from capri.ui.hair import StormHair
    w = make_window()
    w.set_look(0.8, False, "storm")
    assert isinstance(w.hair, StormHair) and set(SPRITES.face_layer) >= {"idle", "speaking", "lying"}
    img = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    w.render(img)
    # the face layer is drawn last: its green mask must still be visible on top of the red storm
    face = SPRITES.face_layer["idle"]
    greens = sum(1 for x in range(0, img.width(), 2) for y in range(0, img.height(), 2)
                 if img.pixelColor(x, y).green() > 150 and img.pixelColor(x, y).red() < 110)
    reds = sum(1 for x in range(0, img.width(), 2) for y in range(0, img.height() // 2, 2)
               if (c := img.pixelColor(x, y)).red() > 180 and c.green() < 70 and c.alpha() > 200)
    assert greens > 20 and reds > 300 and not face.isNull()
    w.set_look(0.8, False, "spikes")
    assert not isinstance(w.hair, StormHair)


def test_storm_moves_smoothly():
    """v1.26: no stepped "boil" any more - from one frame to the next every point moves only a little."""
    from capri.ui.hair import StormHair
    h = StormHair()
    head = QRectF(100, 100, 80, 70)
    a, b = h.mass(head, 1.00, 0.8, 0.0), h.mass(head, 1.0 + 1 / 15, 0.8, 0.0)
    moves = [math.dist(a[i].toTuple(), b[i].toTuple()) for i in range(a.count())]
    assert 0 < max(moves) < head.width() * 0.03                          # it moves, gently
    c = h.mass(head, 1.0 + 1 / 15, 0.8, 0.9)                              # talking: it flares
    assert c.boundingRect().width() > b.boundingRect().width()
    assert h.shape(head, 1.0, 0.8, 0.0).boundingRect().width() > head.width() * 1.8   # wide, like the show


def test_panel_is_a_clean_message_without_static():
    from capri.controller import CompanionController
    from capri.ui.status_panel import StatusPanel
    from capri.ui.art import CharacterArt
    from capri.app import asset_root
    controller = CompanionController()
    panel = StatusPanel(controller, CharacterArt.load(asset_root() / "capri").icon)
    panel.set_static(True)                       # old settings files ask for static: ignored
    panel.show()
    controller.set_state(State.SUCCESS, "Launching Deadlock.")
    app.processEvents()
    assert not panel.static_on and not panel._static_timer.isActive()   # no static, no timer
    img = panel.grab().toImage()
    assert not img.isNull()
def test_choom_is_said_right():
    from capri.speech.pronounce import respell, sapi_xml
    assert respell("Hey choom. Preem, Choom!") == "Hey choom. Preme, Choom!"    # "choom" = ch-oo-m, "preme" = one syllable
    assert respell("chumps and chooms") == "chumps and chooms"
    xml = sapi_xml("Close it, choom? <yes> & no")
    assert '<pron sym="ch uw 1 m"/>' in xml and "&lt;yes&gt; &amp; no" in xml
    assert "choom" not in xml


def test_capri_voice_preset_and_style():
    import numpy as np
    from capri.speech.effects import CAPRI_PRESET, STYLES, apply_style
    from capri.speech.engines import Audio
    assert Settings().speech_style == "capri" and "capri" in STYLES
    assert CAPRI_PRESET["speech_pitch"] > 0.5 and CAPRI_PRESET["speech_speed"] > 0.5
    t = np.arange(16000) / 16000
    out = apply_style(Audio((0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 16000), "capri")
    assert np.isfinite(out.samples).all() and abs(abs(out.samples).max() - 0.9) < 1e-3


def test_idle_repaints_only_when_something_changes():
    w = make_window()
    w.set_state(State.IDLE)
    w._next_blink = w._next_look = time.monotonic() + 100
    calls = []
    w.update = lambda *a: calls.append(1)
    w._tick()                       # first tick: draws
    for _ in range(20):             # same instant: nothing visible changed -> no repaint at all
        w._tick()
    assert len(calls) == 1
    w._next_blink = time.monotonic() - 1
    w._tick()                       # a blink is a visible change
    assert len(calls) == 2


def test_storm_hair_is_rendered_once_per_boil_step():
    from capri.ui.hair import StormHair
    h = StormHair()
    renders = []
    original = h.paint
    h.paint = lambda *a, **k: (renders.append(1), original(*a, **k))
    img = QImage(300, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    head = QRectF(100, 100, 80, 70)
    for i in range(10):             # 10 repaints inside one frame of its sway (1/15 s)
        h.paint_cached(p, head, 1.0 + i * 0.005, 0.8, 0.0, (300, 300), 1.0)
    h.paint_cached(p, head, 1.3, 0.8, 0.0, (300, 300), 1.0)   # next step
    p.end()
    assert len(renders) == 2
