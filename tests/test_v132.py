"""v1.32: two commands without an "and", Discord's call buttons clicked for real when pressing doesn't take,
quiet shutdowns, her own hair recoloured to match, hearing tuned to your voice, and Ollama saying why."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QRectF, QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from fake_vosk import RATE, FakeRecognizer, speak  # noqa: E402
from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Kind  # noqa: E402
from capri.states import State  # noqa: E402
from capri.voice.wakeword import Heard, Rejected, Wake, WakeWordListener, sounds_like_capri  # noqa: E402


# -- two commands at once ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said, kinds", [
    ("close discord open notepad", [(Kind.CLOSE, "discord"), (Kind.OPEN, "notepad")]),
    ("close discord an open notepad", [(Kind.CLOSE, "discord"), (Kind.OPEN, "notepad")]),
    ("open notepad close discord", [(Kind.OPEN, "notepad"), (Kind.CLOSE, "discord")]),
    ("close discord open notepad open youtube", [(Kind.CLOSE, "discord"), (Kind.OPEN, "notepad"), (Kind.OPEN, "youtube")]),
    ("close discord and open notepad", [(Kind.CLOSE, "discord"), (Kind.OPEN, "notepad")]),
])
def test_two_commands_in_one_breath(said, kinds):
    r = rig(FakeDesktop())
    steps = r.router._split_steps(said)
    assert [(i.kind, i.targets[0]) for i, _ in steps] == kinds


@pytest.mark.parametrize("said", ["search youtube for open source", "open the play store", "play let you down by nf",
                                  "turn on stop motion", "open discord"])
def test_one_command_stays_one(said):
    assert rig(FakeDesktop()).router._split_steps(said) == []


# -- Discord: a real click when pressing doesn't take ---------------------------------------------------------------
def test_a_control_that_wont_press_gets_clicked():
    from test_v120 import FakeDiscordUI
    from capri.integrations.app_buttons import DiscordCall
    ui = FakeDiscordUI()
    clicks = []
    original = ui._b

    def stubborn(name, rect=(10, 900, 40, 930)):
        b = original(name, rect)
        if name in ("Share Your Screen", "Stop Streaming"):
            real = b.press

            def press():
                raise OSError("not invokable")
            b.press, b.real = press, real
        return b
    ui._b = stubborn

    def click(x, y):                                     # the mouse lands on whatever's there
        clicks.append((x, y))
        if not ui.streaming and not ui.picker:
            ui.picker = True
        elif ui.streaming:
            ui.streaming = False
    clock = [0.0]
    call = DiscordCall(ui, lambda pids: [1], sleep=lambda t: clock.__setitem__(0, clock[0] + t),
                       clock=lambda: clock[0], click=click)
    assert call.stream([1]) == "streaming" and clicks
    assert call.stop_stream([1]) == "stopped" and not ui.streaming


# -- quiet shutdowns -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said, line", [("restart my computer", "Restarting"), ("put my computer to sleep", "Sleep")])
def test_power_goodbyes_are_written_not_said(said, line):
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit(said)
    asked = len(r.speaker.lines)
    r.service.command.emit("yes")
    assert d.calls and len(r.speaker.lines) == asked and r.controller.message.startswith(line)


# -- her hair --------------------------------------------------------------------------------------------------------
def test_hair_is_the_reference_colour():
    from capri.ui.hair import STORM_RED
    assert STORM_RED.getRgb()[:3] == (249, 8, 84)


def test_her_own_hair_is_recoloured_to_match():
    from capri.ui.hair import STORM_RED, tint_hair
    img = QImage(20, 10, QImage.Format.Format_ARGB32)
    img.fill(QColor(200, 20, 60))                          # her sprite's crimson hair
    for x in range(10, 20):
        for y in range(10):
            img.setPixelColor(x, y, QColor(20, 230, 110))   # her green mask
    out = tint_hair(img, QRectF(0, 0, 1, 1))
    colours = {out.pixelColor(x, y).getRgb()[:3] for x in range(10) for y in range(10)}
    assert colours <= {STORM_RED.getRgb()[:3], (255, 255, 255)}
    assert out.pixelColor(15, 5).getRgb()[:3] == (20, 230, 110)


# -- hearing ---------------------------------------------------------------------------------------------------------
class Hears(FakeRecognizer):
    def __init__(self, rate, heard):
        super().__init__(rate, False)
        self.heard = heard

    def _json(self, words):
        import json
        data = json.loads(super()._json(words))
        data["text"] = data["text"].replace("capri", self.heard)
        return json.dumps(data)


def _listen(heard="capri", confidence=0.97, verify=True, learned=(), training=False):
    listener = WakeWordListener(lambda r: FakeRecognizer(r, True, {"capri": confidence}), lambda r: Hears(r, heard),
                                RATE, 0.8)
    listener.voice_check, listener.verify_wake = None, verify
    listener.learned, listener.training = list(learned), training
    events = []
    for chunk in speak(0.5, "capri", 1.0):
        events += listener.feed(chunk)
    return events


def test_a_slightly_unsure_capri_still_wakes_her_when_the_second_listen_agrees():
    assert any(isinstance(e, Wake) for e in _listen(confidence=0.7))           # was missed before (< 80%)
    assert not any(isinstance(e, Wake) for e in _listen(confidence=0.7, verify=False))
    assert not any(isinstance(e, Wake) for e in _listen(heard="happy", confidence=0.7))   # still no false wakes


@pytest.mark.parametrize("said", ["cap free", "cap tree", "kapri", "copper e"])
def test_more_accents_count(said):
    assert sounds_like_capri(said)


def test_how_she_hears_your_voice_counts_once_taught():
    assert not any(isinstance(e, Wake) for e in _listen(heard="gabby"))
    assert any(isinstance(e, Wake) for e in _listen(heard="gabby", learned=["gabby"]))


def test_training_reports_and_never_wakes():
    events = _listen(heard="cap free", training=True)
    heard = [e for e in events if isinstance(e, Heard)]
    assert heard and heard[0].confidence > 0.9 and "cap free" in heard[0].said
    assert not any(isinstance(e, (Wake, Rejected)) for e in events)


def test_learning_from_your_tries():
    from capri.voice.training import learn
    threshold, variants, note = learn([(0.72, "hey capri"), (0.66, "gabby"), (0.81, "capri"), (0.7, "cap free")])
    assert threshold == pytest.approx(0.66 - 0.05 + 0.15) and variants == ["gabby"] and "Got it" in note
    assert learn([])[0] is None and "microphone" in learn([])[2]
    assert learn([(0.0, "happy"), (0.0, "")])[0] is None


def test_teach_her_your_voice_in_settings():
    from capri.ui.settings_window import SettingsWindow
    r = rig(FakeDesktop())
    win = SettingsWindow(r.router, r.assistant.settings, QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [])
    service = r.router.assistant.service
    win._teach_voice()
    for conf, said in [(0.7, "hey capri"), (0.68, "gabby"), (0.8, "capri"), (0.75, "capri")]:
        service.heard.emit(conf, said)
    s = r.assistant.settings
    assert s.wake_threshold == pytest.approx(0.78) and s.wake_variants == ["gabby"]
    assert "Got it" in win.teach_status.text() and win.teach_btn.isEnabled()


def test_a_near_miss_shows_in_her_log():
    r = rig(FakeDesktop())
    r.service.rejected.emit("capri (heard happy)", 0.62)
    assert any("stayed asleep" in str(e) for e in r.controller.entries)


# -- Ollama says why it isn't answering ------------------------------------------------------------------------------
def test_ollama_running_without_the_model_says_so():
    from capri.ai.claude import ClaudeBrain
    from capri.ai.local import Brains, LocalBrain
    from capri.settings import Settings

    def fetch(method, url, **k):
        return {"models": [{"name": "nomic-embed-text"}]}  # Ollama's up, but no chat model at all
    s = Settings()
    brains = Brains(s, ClaudeBrain(lambda: "", info={}), LocalBrain(lambda: "", lambda: "llama3.2", {}, fetch=fetch))
    reply = brains.ask("hey how are you")
    assert reply.missing and "ollama pull llama3.2" in reply.text and "built-in chat" in reply.text
    r = rig(FakeDesktop(), settings=s, brain=brains)
    r.service.command.emit("tell me about your day")
    assert settle(3, lambda: r.controller.state is State.ERROR) and "isn't downloaded" in r.controller.message


# -- over games ----------------------------------------------------------------------------------------------------
class _Win:
    def __init__(self, hwnd):
        self.hwnd = hwnd

    def winId(self):
        return self.hwnd


def _keeper(front, in_game=False, enabled=True):
    from capri.commands.games import Front
    from capri.ui.stay_on_top import TopmostKeeper
    raised, notes = [], []
    k = TopmostKeeper(lambda: front if front is None else Front(**front), in_game=lambda: in_game,
                      enabled=lambda: enabled, windows=lambda: [_Win(11), _Win(22)], raise_one=raised.append,
                      note=notes.append)
    return k, raised, notes


def test_back_on_top_over_a_full_screen_game():
    k, raised, notes = _keeper({"pid": 5, "exe": "C:\\\\Games\\\\x.exe", "fullscreen": True})
    assert k.tick() and raised == [11, 22] and notes == []


def test_left_alone_over_normal_windows_or_when_off():
    k, raised, _ = _keeper({"pid": 5, "exe": "C:\\\\x\\\\notepad.exe"})
    assert not k.tick() and raised == []
    k, raised, _ = _keeper({"pid": 5, "exe": "C:\\\\Games\\\\x.exe", "fullscreen": True}, enabled=False)
    assert not k.tick() and raised == []
    k, raised, _ = _keeper(None, in_game=True)                    # a game she knows about: on top too
    assert k.tick() and raised == [11, 22]


def test_exclusive_full_screen_is_explained_once():
    k, raised, notes = _keeper({"pid": 7, "exe": "C:\\\\Games\\\\x.exe", "fullscreen": True, "d3d": True})
    k.tick()
    k.tick()
    assert len(notes) == 1 and "borderless" in notes[0]


def test_in_games_she_can_stay_herself():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.look_tab import LookTab
    from capri.ui.sprites import SpriteArt
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(),
                  SpriteArt.load(asset_root() / "capri_v2"))
    tab = LookTab(c)
    assert tab.games_box.currentData() == "drone"                       # the default, as before
    c.set_drone(True)
    tab.games_box.setCurrentIndex(tab.games_box.findData("herself"))
    assert not c.settings.game_drone and not c.settings.auto_game_drone and not c.drone


# -- v1.34: sitting on windows ---------------------------------------------------------------------------------------
def _perch(covered):
    from test_v116 import companion, window_rect
    from capri.ui.perch import WindowPerch
    c = companion(perch_windows=False)
    rects = {7: window_rect(), 9: window_rect().translated(40, 60)}
    front = {"hwnd": 7}
    p = WindowPerch(c, lambda: (front["hwnd"], rects[front["hwnd"]]) if front["hwnd"] in rects else None,
                    rects.get, top=lambda: (7, rects[7]), covered=lambda hwnd: hwnd in covered)
    p.set_enabled(True)
    return c, p, front


def test_she_leaves_a_window_that_got_covered():
    covered = set()
    c, p, front = _perch(covered)
    assert c.perched and p.hwnd == 7
    covered.add(7)                                   # Discord maximised over Spotify: nowhere to sit in front
    front["hwnd"] = None
    p.tick()
    assert c.perched                                 # one look: could be a passing popup
    p.tick()
    assert not c.perched and p.hwnd is None          # still covered: home


def test_covered_but_the_front_window_is_sittable_she_hops_there():
    covered = set()
    c, p, front = _perch(covered)
    covered.add(7)
    front["hwnd"] = 9
    p.tick()
    p.tick()
    assert c.perched and p.hwnd == 9


def test_closing_the_window_she_sits_on_teleports_her_home_then_zaps():
    from test_v116 import companion, window_rect
    from capri.ui.perch import WindowPerch
    from capri.ui.zap import ZapShow
    from PySide6.QtCore import QRect
    c = companion(perch_windows=False)
    c.show()
    win = window_rect()
    c.window_perch = WindowPerch(c, lambda: None, lambda hwnd: win, top=lambda: (7, win))
    c.window_perch.set_enabled(True)
    assert c.perched
    z = ZapShow(c, lambda pids: QRect(200, 150, 700, 500))
    z.HOME_FIRST_MS = 10
    closed = []
    z.zap("Spotify", [10], lambda: closed.append(c.perched))
    assert not c.perched and not closed              # home first...
    assert settle(3, lambda: bool(closed)) and closed == [False] and z.fx.isVisible() is not None   # ...then the zap


# -- v1.34: her voice -------------------------------------------------------------------------------------------
def test_beeps_are_smooth():
    import numpy as np
    from capri.speech.engines import BeepEngine
    for kind in ("retro", "cute"):
        a = BeepEngine().synthesize("Hey choom, nice one! What's up?", "beeps: " + kind, 0.5).samples
        assert len(a) > 2000 and np.abs(a).max() < 0.95
        assert np.abs(np.diff(a)).max() < 0.25                         # no clicks: never a sudden jump
        assert abs(a[0]) < 0.01 and abs(a[-1]) < 0.01                  # starts and ends in silence


def test_one_blip_fades_in_and_out_and_glides():
    import numpy as np
    from capri.speech.engines import BeepEngine
    b = BeepEngine._blip(880.0, 1100.0, 0.08, 22050, "square")
    assert abs(b[0]) < 1e-3 and abs(b[-1]) < 0.02 and np.abs(np.diff(b)).max() < 0.25


@pytest.mark.parametrize("plain, said", [(False, "Nice one, choom."), (True, "Nice one, chooom.")])
def test_choom_is_spelled_for_each_kind_of_voice(plain, said):
    from capri.speech.pronounce import respell, sapi_xml
    assert respell("Nice one, choom.", plain=plain) == said
    assert 'sym="ch uw 1 m"' in sapi_xml("Nice one, choom.")             # Windows voices: the exact sounds


def test_elevenlabs_never_gets_chom():
    from capri.speech.engines import ElevenLabsEngine
    sent = []

    def fetch(url, body, headers):
        sent.append(body["text"])
        return b"\\x00\\x00" * 100
    ElevenLabsEngine.key = staticmethod(lambda: "k")
    try:
        ElevenLabsEngine(fetch=fetch).synthesize("Hey choom.", ElevenLabsEngine.NAME, 0.5)
    finally:
        ElevenLabsEngine.key = staticmethod(lambda: "")
    assert sent == ["Hey chooom."]


def test_the_installed_app_keeps_her_neural_voice_in_your_user_folder(monkeypatch):
    import sys
    from capri.speech import engines
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(engines, "KOKORO_DIR", Path("/nonexistent/models/kokoro"))
    assert engines.kokoro_folder().parts[-2:] == ("models", "kokoro") and "Capri" in str(engines.kokoro_folder()) \
        or "capri" in str(engines.kokoro_folder())
