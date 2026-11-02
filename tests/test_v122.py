"""v1.22: Discord buttons found the reliable way, the mute zap on target, one AI picker, ElevenLabs,
beep voice, screen-watching game hype, and better hearing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Kind, parse  # noqa: E402


# -- Discord ------------------------------------------------------------------------------------------------
class SlowDiscord:
    """Discord the way it really behaves: the first look comes back empty (its accessibility is
    waking up), and the voice panel's buttons only show up when asked for by name."""

    def __init__(self):
        self.looks, self.pressed, self.in_call = 0, [], True

    def _b(self, name, rect):
        ui = self

        class B:
            def __init__(self):
                self.name, self.rect = name, rect

            def press(self):
                ui.pressed.append(name)
                if name == "Disconnect":
                    ui.in_call = False
        return B()

    def buttons(self, hwnd, names=None, control=None, with_rects=False):
        self.looks += 1
        if self.looks < 3:
            return []                                              # waking up
        out = [self._b("Mute", (200, 1000, 232, 1032)), self._b("Deafen", (232, 1000, 264, 1032))]
        if self.in_call:
            out.append(self._b("Disconnect", (250, 950, 282, 982)))
        return [b for b in out if names is None or b.name in names]

    def clickables(self, hwnd):
        return []                                                  # the loose list misses them


def _clock():
    t = [0.0]
    return (lambda s: t.__setitem__(0, t[0] + s)), (lambda: t[0])


def test_leave_finds_disconnect_by_its_exact_name_after_discord_wakes_up():
    from capri.integrations.app_buttons import DiscordCall
    sleep, clock = _clock()
    ui = SlowDiscord()
    assert DiscordCall(ui, lambda pids: [1], sleep=sleep, clock=clock).leave([1]) == "left"
    assert ui.pressed == ["Disconnect"]


def test_mute_zap_waits_for_discord_to_wake_up():
    from capri.integrations.app_buttons import DiscordButtons
    ui = SlowDiscord()
    rect = DiscordButtons(ui, lambda pids: [1], sleep=lambda s: None).locate([1], "mute")
    assert rect == (200, 1000, 232, 1032)                          # the real button, not a guess


def test_leave_call_with_your_discord_keybind():
    from capri.commands.system import ProcessInfo
    d = FakeDesktop()
    r = rig(d, processes=[ProcessInfo(10, "Discord.exe")])
    r.router.services.discord_call = object()                      # Windows
    r.assistant.settings.discord_leave_key = "ctrl+shift+l"
    r.router.handle("leave call")
    assert r.controller.message == "Left the call." and any("ctrl+shift+l" in str(c) for c in d.calls)


# -- Settings: one AI picker, only the boxes that AI needs -------------------------------------------------------
def _tab(r):
    from capri.ui.assistant_tab import AssistantTab
    r.assistant.speaker.say = lambda *a, **k: True
    r.assistant.speaker.voices = lambda: []
    return AssistantTab(r.assistant, r.router, None)


def test_one_ai_list_and_only_what_it_needs():
    r = rig(FakeDesktop())
    tab = _tab(r)
    tab.ai_pick.setCurrentIndex(tab.ai_pick.findData("openai:openai"))
    assert tab.ollama_model_row.isHidden() and tab.api_key.isHidden() and tab.ai_url.isHidden()   # no Ollama for ChatGPT
    assert not tab.ai_key.isHidden() and not tab.ai_model_row.isHidden()
    tab.apply()
    s = r.assistant.settings
    assert s.ai_provider == "openai" and s.openai_preset == "openai"
    tab.ai_pick.setCurrentIndex(tab.ai_pick.findData("local"))
    assert not tab.ollama_model_row.isHidden() and tab.ai_key.isHidden()
    tab.ai_pick.setCurrentIndex(tab.ai_pick.findData("openai:custom"))
    assert not tab.ai_url.isHidden()
    tab.ai_pick.setCurrentIndex(tab.ai_pick.findData("openai:groq"))
    tab.apply()
    assert s.openai_preset == "groq"
    s.ai_provider, s.openai_preset = "claude", "openai"
    tab.reload()
    assert tab.ai_pick.currentData() == "claude" and not tab.api_key.isHidden()


def test_join_call_has_its_own_settings_group():
    from capri.settings import Settings
    from capri.ui.pc_tab import PcTab
    joined = []
    s = Settings()
    tab = PcTab(s, lambda: None, lambda: None, join_now=lambda: joined.append(1))
    tab.call.setText("https://discord.com/channels/1/2")
    tab.join_test.click()
    assert s.discord_call == "https://discord.com/channels/1/2" and joined == [1]
    tab.call.setText("not a link")
    assert tab.apply() is False and "voice channel link" in tab.status.text()


# -- voices: beeps and ElevenLabs ---------------------------------------------------------------------------------
def test_beep_voice_blips_instead_of_words():
    import numpy as np
    from capri.speech.engines import BeepEngine
    from capri.speech.effects import levels
    e = BeepEngine()
    assert e.voices() == ["beeps: retro", "beeps: cute"]
    short = e.synthesize("Hi.", "beeps: retro", 0.5)
    long = e.synthesize("Opened Discord for you, choom. Have fun!", "beeps: retro", 0.5)
    assert long.natural and long.pitched and len(long.samples) > 3 * len(short.samples)
    assert np.abs(long.samples).max() <= 0.33 and np.isfinite(long.samples).all()
    assert max(levels(long)) > 0.5                                       # her mouth still moves with it
    cute = e.synthesize("Opened Discord for you, choom. Have fun!", "beeps: cute", 0.5)
    assert not np.array_equal(cute.samples[:2000], long.samples[:2000])


def _eleven(reply=None, error=None):
    from capri.speech.engines import ElevenLabsEngine
    sent = []

    def fetch(url, body, headers):
        sent.append((url, body, headers))
        if error:
            raise error
        return reply
    ElevenLabsEngine.key = staticmethod(lambda: "xi-key")
    ElevenLabsEngine.voice_id = staticmethod(lambda: "voice123")
    return ElevenLabsEngine(fetch=fetch), sent


def test_elevenlabs_voice():
    import numpy as np
    from capri.speech.engines import ElevenLabsEngine
    pcm = (np.sin(np.arange(4410) / 5) * 8000).astype(np.int16).tobytes()
    engine, sent = _eleven(pcm)
    try:
        assert engine.voices() == [ElevenLabsEngine.NAME]
        audio = engine.synthesize("Hey choom.", ElevenLabsEngine.NAME, 0.5)
        url, body, headers = sent[0]
        assert "voice123" in url and "pcm_22050" in url and headers["xi-api-key"] == "xi-key"
        assert body["text"] == "Hey chooom." and audio.rate == 22050 and len(audio.samples) == 4410   # (v1.34: not "chom")
        assert audio.natural and audio.pitched
    finally:
        ElevenLabsEngine.key = staticmethod(lambda: "")


def test_elevenlabs_problems_fall_back_to_her_normal_voice():
    import io
    import urllib.error
    from capri.speech.engines import ElevenLabsEngine, EspeakEngine, VoiceBox, BeepEngine
    engine, _ = _eleven(error=urllib.error.HTTPError("u", 402, "pay", {}, io.BytesIO(b"")))
    try:
        box = VoiceBox.__new__(VoiceBox)
        normal = BeepEngine()                                              # stands in for her normal voice
        box.engines, box.last = [engine, normal], ("", "")
        box.default_voice = lambda: "beeps: retro"
        audio = box.synthesize("Hi there.", ElevenLabsEngine.NAME, 0.5)
        assert len(audio.samples) and "out of credit" in box.last[1] and "normal voice" in box.last[1]
    finally:
        ElevenLabsEngine.key = staticmethod(lambda: "")


def test_adding_an_elevenlabs_key_picks_that_voice():
    from capri.speech.engines import ElevenLabsEngine
    r = rig(FakeDesktop())
    tab = _tab(r)
    tab.eleven_key.setText("xi-new-key")
    tab.eleven_voice.setText("abc")
    tab.apply()
    s = r.assistant.settings
    assert s.speech_voice == ElevenLabsEngine.NAME and s.elevenlabs_voice == "abc"
    from capri import secrets
    secrets.set_many({"elevenlabs_api_key": ""})


def test_natural_voices_get_no_added_intonation():
    import numpy as np
    from capri.settings import Settings
    from capri.speech.engines import BeepEngine
    from capri.speech.speaker import Speaker

    class Box:
        last = ("beeps: retro", "")

        def synthesize(self, text, voice, speed, pitch):
            return BeepEngine().synthesize(text, "beeps: retro", speed, pitch)

        def voices(self):
            return ["beeps: retro"]
    s = Settings()
    s.speech_style, s.speech_expression = "natural", 1.0
    sp = Speaker(s, Box, player=lambda x, r: (lambda: None), sleep=lambda t: None)
    sp.ready.wait(2)
    sp.voicebox = Box()
    a = sp._render("Hello there friend.", 0.5, 0.0)
    b = BeepEngine().synthesize("Hello there friend.", "beeps: retro", 0.5, 0.0)
    assert len(a.samples) == len(b.samples)                             # not re-timed by intonation
    sp.shutdown()


# -- game hype in any game: watching the screen -----------------------------------------------------------------
@pytest.mark.parametrize("text, signs", [
    ("YOU ELIMINATED xX_Sniper_Xx | 150 m", {"kill"}),
    ("ELIMINATED BY xX_Sniper_Xx", {"death"}),
    ("HEADSHOT | +100", {"headshot"}),
    ("DOUBLE KILL", {"double"}),
    ("#1 VICTORY ROYALE", {"match_win"}),
    ("DEFEAT", {"match_loss"}),
    ("KNOCKED DOWN PlayerTwo", {"kill"}),
    ("YOU DIED", {"death"}),
    ("Press F to open the map | Ammo 30", set()),
])
def test_reading_what_games_put_on_screen(text, signs):
    from capri.integrations.screen_hype import read_signs
    assert read_signs(text) == signs


def test_the_watcher_cheers_once_per_banner():
    from types import SimpleNamespace
    from test_stage5 import settle
    from capri.integrations.screen_hype import ScreenWatcher
    screens = iter(["", "YOU ELIMINATED Bob", "YOU ELIMINATED Bob", "", "HEADSHOT", "ELIMINATED BY Bob"] + [""] * 50)
    heard = []
    s = SimpleNamespace(game_hype_screen=True, game_hype_encourage=False)
    t = [0.0]
    w = ScreenWatcher(s, lambda: True, lambda: (0, 0, 1920, 1080), lambda img: next(screens), heard.append,
                      lambda rect: object(), clock=lambda: t[0])
    for _ in range(6):
        t[0] += 1.5
        w._tick()
        assert settle(2, lambda: not w._busy)
    assert heard == ["kill", "headshot", "death"]                    # the banner that stayed up: once


def test_no_screen_reading_outside_games():
    from types import SimpleNamespace
    from capri.integrations.screen_hype import ScreenWatcher
    reads = []
    s = SimpleNamespace(game_hype_screen=True, game_hype_encourage=True)
    w = ScreenWatcher(s, lambda: False, lambda: (0, 0, 10, 10), lambda img: reads.append(1) or "", lambda e: None,
                      lambda rect: object())
    w._tick()
    assert reads == [] and not w._busy


def test_encouragement_now_and_then():
    from types import SimpleNamespace
    from capri.integrations.screen_hype import ScreenWatcher
    heard = []
    t = [0.0]
    s = SimpleNamespace(game_hype_screen=False, game_hype_encourage=True)
    w = ScreenWatcher(s, lambda: True, lambda: None, lambda img: "", heard.append, lambda rect: None, clock=lambda: t[0])
    w.apply()
    t[0] += 200
    w._tick()
    assert heard == []                                                # not every second
    t[0] += 1000
    w._tick()
    assert heard == ["encourage"]
    w._timer.stop()


def test_lines_barely_ever_repeat():
    import random
    from capri.integrations import game_hype
    rng = random.Random(3)
    kills = [game_hype.line("kill", "edgerunner", rng) for _ in range(40)]
    assert len(set(kills)) >= 35                                      # practically endless
    assert all(game_hype.line("encourage", "edgerunner", rng) for _ in range(5))
    assert all("!" not in game_hype.line("kill", "deadpan", rng) for _ in range(20))


# -- hearing: accents, bad mics, slurring ------------------------------------------------------------------------
@pytest.mark.parametrize("said, meant", [
    ("shot down my computa", "shut down my computer"), ("lee call", "leave call"), ("join coll", "join call"),
    ("tek a screen shot", "take a screenshot"), ("mute mi", "mute me"), ("pley music", "play music"),
    ("opun discort", "open discord"), ("stob streaming", "stop streaming"), ("skib dis song", "skip this song"),
    ("wat time is it", "what time is it"), ("clothe spotify", "close spotify"), ("deefin me", "deafen me"),
    ("leaf call", "leave call"),
])
def test_misheard_commands_are_recovered(said, meant):
    from capri.commands.soundslike import closest
    assert closest(said) == meant


@pytest.mark.parametrize("said", ["i like pizza", "my dog is cute", "that was fun", "i went outside",
                                  "tell me about cats", "how was your day"])
def test_chat_is_left_alone(said):
    from capri.commands.soundslike import closest
    assert closest(said) is None


def test_she_acts_on_what_you_meant():
    d = FakeDesktop()
    r = rig(d)
    r.router.handle("shot down my computa")
    assert r.speaker.lines[-1] == "Look up there, think we can make it?"   # asks first, as always
    r.service.command.emit("no")
    r.router.handle("wat time is it")
    assert r.controller.message.startswith("It's")


def test_mic_cleanup_turns_a_quiet_mic_up_and_hiss_down():
    import numpy as np
    from capri.voice.cleanup import MicCleaner
    rate = 16000
    clean = MicCleaner(rate)
    t = np.arange(1600) / rate
    quiet_voice = (np.sin(2 * np.pi * 300 * t) * 400).astype(np.int16).tobytes()      # a far-away / cheap mic
    hiss = (np.random.default_rng(1).standard_normal(1600) * 60).astype(np.int16).tobytes()
    for _ in range(20):
        clean(hiss)
    for _ in range(15):
        out = np.frombuffer(clean(quiet_voice), np.int16).astype(np.float32)
    assert np.sqrt(np.mean(out ** 2)) > 4 * np.sqrt(np.mean(np.frombuffer(quiet_voice, np.int16).astype(np.float32) ** 2))
    for _ in range(5):
        gap = np.frombuffer(clean(hiss), np.int16).astype(np.float32)
    assert np.sqrt(np.mean(gap ** 2)) < np.sqrt(np.mean(out ** 2)) / 5                # words stand out from the hiss
    rumble = (np.sin(2 * np.pi * 20 * t) * 8000).astype(np.int16).tobytes()
    assert np.abs(np.frombuffer(MicCleaner(rate)(rumble), np.int16)).mean() < 0.5 * 8000 * 0.64   # desk thumps cut


def test_the_app_turns_mic_cleanup_on_from_your_setting():
    from capri.voice.service import VoiceService
    service = VoiceService(True, False, "", 0.8)
    assert service.cleanup is False                                    # off until the app applies your setting
    from capri.settings import Settings
    assert Settings().mic_cleanup is True                              # ...which is on by default
