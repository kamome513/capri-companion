"""v1.19.1: "pull up spotify" and other casual asks get done, instead of chatted about."""

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

from capri.commands.guess import guess_bare, guess_command  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402

KNOWN = {"spotify", "discord", "steam", "youtube", "opera gx"}


def known(name: str) -> bool:
    return name in KNOWN


@pytest.mark.parametrize("said", ["pull up spotify", "bring up spotify", "pull spotify up", "get spotify up",
                                  "can you pull up spotify", "get spotify open", "get spotify going"])
def test_pull_up_is_open(said):
    intent = parse(said)
    assert intent.kind is Kind.OPEN and intent.targets == ("spotify",)


def test_pull_up_the_weather_and_volume_are_not_apps():
    assert parse("pull up the weather").kind is Kind.WEATHER
    assert parse("bring up the volume").query == "volume_up"


@pytest.mark.parametrize("said, meant", [
    ("throw on spotify", "open spotify"), ("hop on discord", "open discord"), ("jump on steam", "open steam"),
    ("take me to youtube", "open youtube"), ("go to youtube", "open youtube"), ("show me opera gx", "open opera gx"),
    ("i need discord", "open discord"), ("get on discord and steam", "open discord and steam"),
    ("get rid of discord", "close discord"), ("listen to spotify", "open spotify"),
    ("i wanna listen to music", "play music"), ("put some music on", "play music"),
    ("listen to lofi", "play lofi"), ("put on some lofi", "play lofi"),
])
def test_casual_asks_become_commands(said, meant):
    assert guess_command(said, known) == meant


@pytest.mark.parametrize("said", ["i need a break", "get on with it", "go to bed", "show me what you got",
                                  "i want a hug", "how are you"])
def test_chat_stays_chat(said):
    assert guess_command(said, known) is None and guess_bare(said, known) is None


def test_just_the_name_opens_it():
    assert guess_bare("spotify", known) == "open spotify"
    assert guess_bare("spotify now", known) == "open spotify"


def test_she_opens_it_instead_of_asking_why():
    r = rig(FakeDesktop())
    for said in ("pull up discord", "hop on discord", "throw on discord", "discord"):
        r.system.calls.clear()
        r.router.handle(said)
        assert any(c[0] == "program" and "Discord" in str(c[1]) or c[0] == "open" for c in r.system.calls), said
    r.system.calls.clear()
    r.router.handle("take me to youtube")
    assert ("open", "https://www.youtube.com") in r.system.calls


def test_unknown_names_still_get_chat():
    r = rig(FakeDesktop())
    r.router.handle("i need a break")
    assert r.system.calls == [] and r.speaker.lines        # she answers, opens nothing


def test_the_ai_is_told_casual_asks_are_asks():
    from capri.ai.claude import system_prompt
    prompt = system_prompt(False)
    assert "pull up Spotify" in prompt and "never ask why" in prompt


# -- personalities you can hear ---------------------------------------------------------------------------
def _speechy(seconds=1.5, rate=22050):
    import numpy as np
    from capri.speech.engines import Audio
    t = np.arange(int(rate * seconds)) / rate
    x = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((220, 660, 1500, 3200, 5200), 1))
    x = x * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
    return Audio((x / np.max(np.abs(x)) * 0.8).astype(np.float32), rate, pitched=True)


def test_every_personality_has_its_own_voice():
    from capri import personality
    voices = [(p.voice, p.tone) for p in personality.PERSONALITIES.values()]
    assert len(set(voices)) == len(voices)
    pitches = [v[1] for v, _tone in voices]
    assert max(pitches) - min(pitches) >= 6                 # semitones apart: easy to hear


def test_every_tone_changes_the_sound():
    import numpy as np
    from capri.speech.effects import TONES, apply_tone
    a = _speechy()
    for tone in TONES:
        y = apply_tone(a, tone).samples
        assert np.isfinite(y).all() and np.mean(np.abs(y - a.samples)) > 0.01, tone
    assert apply_tone(a, "").samples is a.samples


def test_the_glitch_voice_really_glitches():
    import numpy as np
    from capri.speech.effects import _glitch
    rate = 22050
    x = _speechy(3.0, rate).samples
    hits = 0
    for seed in range(6):
        y = _glitch(x, rate, np.random.default_rng(seed))
        n = min(len(x), len(y))
        changed = np.abs(y[:n] - x[:n]) > 0.05
        hits += changed[: int(rate * 0.7)].any()              # a hiccup early on, even in a short line
        assert np.isfinite(y).all() and 0.9 < len(y) / len(x) < 1.15   # v1.21: gentle
    assert hits >= 5


def test_the_glitch_style_still_sounds_clean():
    import numpy as np
    from capri.speech.effects import apply_style
    out = apply_style(_speechy(0.6), "glitch", seed=3)
    assert np.isfinite(out.samples).all() and abs(np.abs(out.samples).max() - 0.9) < 1e-3


def _tab(r):
    from capri.ui.assistant_tab import AssistantTab
    said = []
    r.assistant.speaker.say = lambda text, emotion="neutral", force=False: said.append((text, emotion)) or True
    r.assistant.speaker.voices = lambda: []
    return AssistantTab(r.assistant, r.router, None), said


def test_picking_a_personality_says_it_in_its_voice():
    from capri import personality
    r = rig(FakeDesktop())
    tab, said = _tab(r)
    tab.personality.setCurrentIndex(tab.personality.findData("tsundere"))
    assert r.assistant.settings.personality == "tsundere"
    assert said[-1] == (personality.get("tsundere").intro, "angry")


def test_test_voice_uses_the_current_personality():
    from capri import personality
    r = rig(FakeDesktop())
    tab, said = _tab(r)
    r.assistant.settings.personality = "deadpan"           # changed by voice while Settings was open
    tab.show()
    tab._test_voice()
    assert personality.get("deadpan").intro in said[-1][0]
    assert r.assistant.settings.personality == "deadpan"   # Settings didn't undo it
    tab.hide()


def test_preem_is_one_syllable_for_every_engine():
    import re
    import shutil
    import subprocess
    from capri.speech.pronounce import respell
    assert respell("preem") == "preme"
    if shutil.which("espeak-ng"):                          # what espeak / Piper / Kokoro's fallback make of it
        phonemes = subprocess.run(["espeak-ng", "-q", "-x", "-v", "en-us", "preme"],
                                  capture_output=True, text=True).stdout.strip()
        assert re.fullmatch(r"pr'?i:m", phonemes)          # p-r-ee-m: no "pree-um"


# -- her words and her voice together -------------------------------------------------------------------------
def test_the_first_chunk_is_short_so_she_starts_sooner():
    from capri.speech.speaker import speech_chunks
    chunks = speech_chunks("Opened Discord. Spotify's going too.")
    assert chunks[0] == "Opened Discord."
    chunks = speech_chunks("You're using 10.2 gigs of RAM right now, and most of it is Opera with its forty tabs. "
                           "Close a few.")
    assert chunks[0] == "You're using 10.2 gigs of RAM right now," and len(chunks) >= 2
    assert " ".join(chunks).split() == ("You're using 10.2 gigs of RAM right now, and most of it is Opera with "
                                        "its forty tabs. Close a few.").split()
    assert speech_chunks("Done.") == ["Done."]


class _Voice:
    def __init__(self, gate=None, delay=0.0):
        import threading
        self.gate, self.delay, self.made = gate or threading.Event(), delay, []
        if gate is None:
            self.gate.set()

    def synthesize(self, text, voice, speed, pitch):
        import time

        import numpy as np
        from capri.speech.engines import Audio
        self.gate.wait(5)
        time.sleep(self.delay)
        self.made.append((text, time.monotonic()))
        return Audio(np.zeros(int(22050 * 0.25), np.float32) + 0.1, 22050, pitched=True)

    def voices(self):
        return []


def test_the_next_sentence_is_made_while_she_says_this_one():
    import time

    from capri.settings import Settings
    from capri.speech.speaker import Speaker
    from test_stage5 import settle
    voice = _Voice()
    played = []
    sp = Speaker(Settings(), lambda: voice, player=lambda x, r: (played.append(time.monotonic()), lambda: None)[1],
                 sleep=time.sleep)
    sp.ready.wait(2)
    sp.say("Opened Discord. Spotify is playing your lofi playlist now. Enjoy it, choom.", force=True)
    assert settle(5, lambda: not sp.busy())
    assert len(played) >= 2 and len(voice.made) == len(played)
    assert voice.made[1][1] < played[0] + 0.25                 # made before the first one finished playing
    sp.shutdown()


def _talking_rig(voice):
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.speech.speaker import Speaker
    from capri.voice.service import VoiceService
    from capri.assistant import Assistant
    service = VoiceService(True, False, "", 0.8)
    service.listen_now = lambda *a: None
    speaker = Speaker(Settings(), lambda: voice, player=lambda x, r: (lambda: None), sleep=lambda t: None)
    speaker.ready.wait(2)
    controller = CompanionController()
    assistant = Assistant(controller, Settings(), service, speaker)
    shown = []
    assistant.replied.connect(lambda text, emo: shown.append(text))
    return assistant, controller, speaker, shown


def test_her_words_show_when_her_voice_starts():
    import threading

    from capri.states import State
    from test_stage5 import settle
    gate = threading.Event()
    assistant, controller, speaker, shown = _talking_rig(_Voice(gate))
    controller.set_state(State.PROCESSING, "Thinking...")
    assistant.show_result(State.SPEAKING, "Opened Discord.")
    app.processEvents()
    assert controller.message == "Thinking..." and shown == []     # her voice isn't ready: no text yet
    gate.set()
    assert settle(3, lambda: controller.message == "Opened Discord.")
    assert shown == ["Opened Discord."]
    speaker.shutdown()


def test_her_words_still_show_if_the_voice_fails():
    from capri.states import State
    from test_stage5 import settle

    class Broken(_Voice):
        def synthesize(self, *a):
            raise RuntimeError("no voice")
    assistant, controller, speaker, shown = _talking_rig(Broken())
    assistant.show_result(State.SPEAKING, "Opened Discord.")
    assert settle(3, lambda: controller.message == "Opened Discord.")
    speaker.shutdown()


def test_a_newer_command_wins_over_old_words():
    import threading

    from capri.states import State
    from test_stage5 import settle
    gate = threading.Event()
    assistant, controller, speaker, shown = _talking_rig(_Voice(gate))
    assistant.show_result(State.SPEAKING, "Old news.")
    assistant._on_wake("hey capri", 0.9)                    # you start a new command
    listening = controller.message
    gate.set()
    settle(1, lambda: False)
    assert controller.message == listening and "Old news." not in shown
    speaker.shutdown()


def test_her_questions_show_when_she_asks_them():
    import threading

    from test_stage5 import settle
    gate = threading.Event()
    assistant, controller, speaker, shown = _talking_rig(_Voice(gate))
    assistant.confirm("Look up there, think we can make it?", lambda yes: None)
    app.processEvents()
    assert shown == []
    gate.set()
    assert settle(3, lambda: controller.message == "Look up there, think we can make it?")
    speaker.shutdown()
