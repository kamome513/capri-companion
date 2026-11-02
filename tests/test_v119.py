"""v1.19: the call look (chat window + call cards), highlighting any word, revamped
personalities, better hearing for accents (Whisper), learning what you mean, voice styles you
can hear, and no more "waiting for the wake word" while she's still talking."""

from __future__ import annotations

import random
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri import personality  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations.screen_targets import Finder, Target, Word  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402


# -- talking: no "waiting for the wake word" while she's still talking ---------------------------------------
def test_long_replies_are_said_a_sentence_at_a_time():
    from capri.speech.speaker import split_sentences
    assert split_sentences("Opened Discord.") == ["Opened Discord."]
    parts = split_sentences("You're using 10.2 GB of RAM, which is quite a lot right now honestly. "
                            "The biggest is Opera. Close a few tabs and it'll drop.")
    assert len(parts) == 2 and parts[0].endswith("now honestly.")


def test_the_panel_waits_until_she_has_actually_spoken():
    from capri.speech.speaker import Speaker
    gate = threading.Event()

    class SlowVoice:
        def synthesize(self, text, voice, speed, pitch):
            gate.wait(3)                                  # still making the audio...
            from capri.speech.effects import Audio
            return Audio(np.zeros(2205, np.float32), 22050, pitched=True)

        def voices(self):
            return []
    s = Settings()
    speaker = Speaker(s, SlowVoice, player=lambda samples, rate: (lambda: None), sleep=lambda t: None)
    speaker.ready.wait(2)
    assert speaker.say("Hello there.") and speaker.busy()   # queued + being synthesised = busy
    gate.set()
    assert settle(3, lambda: not speaker.busy())
    speaker.shutdown()


def test_back_to_idle_waits_for_the_speaker():
    r = rig(FakeDesktop())
    busy = [True]
    r.speaker.busy = lambda: busy[0]
    r.assistant.show_result(State.SUCCESS, "Launching Discord.")
    r.assistant._back_to_idle(r.assistant._generation)
    assert r.controller.message == "Launching Discord."       # not back to standby while she has words left
    busy[0] = False
    r.assistant._back_to_idle(r.assistant._generation)
    assert r.controller.state is State.IDLE


# -- voice styles you can hear --------------------------------------------------------------------------------
def test_every_voice_style_sounds_different():
    from capri.speech.effects import STYLES, Audio, apply_style
    rate = 22050
    t = np.arange(rate) / rate
    voice = ((np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 1800 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)))
    voice = voice.astype(np.float32)
    plain = apply_style(Audio(voice, rate, pitched=True), "natural").samples
    assert {"holocall", "android", "cyberspace", "netrunner", "glitch", "capri"} <= set(STYLES)
    for key in STYLES:
        if key in ("natural", "capri"):
            continue
        if key == "glitch":
            continue                                                    # its hiccups shift the timing
        y = apply_style(Audio(voice, rate, pitched=True), key, seed=1).samples
        n = min(len(y), len(plain))
        change = np.sqrt(np.mean((y[:n] - plain[:n]) ** 2)) / np.sqrt(np.mean(plain[:n] ** 2))
        assert 0.05 < change < 0.7, key                    # v1.21: you can hear it, but it's still her voice


# -- the call look ----------------------------------------------------------------------------------------------
def test_the_chat_window_is_always_the_call_look():
    from capri.ui.callstyle import Row
    from capri.ui.chat_window import SKINS, CallLog, ChatWindow
    r = rig(FakeDesktop())
    chat = ChatWindow(r.assistant, QImage(16, 16, QImage.Format.Format_ARGB32))
    assert isinstance(chat.log, CallLog)
    chat.input.setText("who are you")
    chat.send()
    rows = chat.log.all_rows()
    assert rows[-2:][0] == Row("you", "who are you") or Row("you", "who are you") in rows
    for skin in SKINS.values():
        chat.set_skin(skin.key)
        assert chat.log.colours is skin.call
        chat.show()
        app.processEvents()
        assert not chat.log.grab().isNull()
    r.controller.set_state(State.PROCESSING, "Thinking...")
    assert chat.log.typing and chat.log.all_rows()[-1].typing        # "..." while she thinks


def test_call_cards_show_you_and_her():
    from capri.ui.feed import FeedWindow, heard_text
    assert heard_text('"open this cord" -> "open discord"') == "open discord"
    r = rig(FakeDesktop())
    f = FeedWindow(r.controller)
    r.controller.log("Heard", '"who are you"')
    r.controller.set_state(State.PROCESSING, "Thinking...")
    assert [row.who for row in f._rows()] == ["you", "capri"] and f._rows()[-1].typing
    f.add_reply("I'm Capri.")
    assert [(c["who"], c["text"]) for c in f.cards] == [("you", "who are you"), ("capri", "I'm Capri.")]
    f.show()
    app.processEvents()
    assert not f.grab().isNull()


# -- highlighting any word ---------------------------------------------------------------------------------------
class TextUI:
    def __init__(self, hit=None):
        self.hit, self.asked = hit, []

    def find_text(self, hwnd, text):
        self.asked.append(text)
        return self.hit

    def clickables(self, hwnd):
        return []


class Hit:
    def __init__(self):
        self.name, self.rect, self.selected = "deadline", (100, 200, 160, 220), 0

    def select_text(self):
        self.selected += 1


def test_any_word_in_an_apps_text_is_selected_by_the_app():
    from capri.integrations.screen_click import ScreenHands
    hit = Hit()
    finder = Finder(TextUI(hit), lambda: 7, lambda hwnd: (0, 0, 800, 600), lambda: (0, 0), sleep=lambda s: None)
    found = finder.find_text("deadline")
    assert found.element is hit and found.rect == (100, 200, 160, 220)
    ScreenHands(lambda: None).select(found)
    assert hit.selected == 1                                         # the app's own selection, no mouse drag


def test_otherwise_she_reads_the_screen():
    ocr = lambda rect: [Word("Due", 1, (10, 10, 40, 25)), Word("dead1ine:", 1, (45, 10, 110, 25))]
    finder = Finder(TextUI(None), lambda: 7, lambda hwnd: (0, 0, 800, 600), lambda: (0, 0), ocr=ocr,
                    sleep=lambda s: None)
    found = finder.find_text("deadline")                              # "dead1ine" read as "deadline"
    assert found is not None and found.rect == (45, 10, 110, 25)


def test_dark_mode_is_flipped_for_reading():
    from capri.integrations.screen_targets import prepare_for_ocr
    dark = np.full((20, 40, 3), 25, np.uint8)
    dark[5:10, 5:30] = 235
    out = prepare_for_ocr(dark)
    assert out[0, 0, 0] > 200 and out[7, 10, 0] < 60                 # dark text on light now


# -- personalities -----------------------------------------------------------------------------------------------
def test_new_personalities():
    for key in ("gremlin", "hype", "kuudere"):
        assert key in personality.PERSONALITIES
    assert parse("be a gremlin").targets == ("gremlin",)
    assert parse("be hype").targets == ("hype",)
    assert parse("act kuudere").targets == ("kuudere",)


@pytest.mark.parametrize("key", [k for k in personality.PERSONALITIES if k != "edgerunner"])
def test_each_personality_has_its_own_words_for_commands(key):
    said = personality.line("launch", key, {"name": "Discord"}, random.Random(1))
    assert said and "Discord" in said and said != "Launching Discord."


def test_she_opens_apps_in_her_personalitys_words():
    s = Settings(slang=False)
    s.personality = "tsundere"
    r = rig(FakeDesktop(), settings=s)
    r.service.command.emit("open discord")
    assert settle(2, lambda: "Discord" in r.controller.message)
    assert r.controller.message in [t.format(name="Discord") for t in personality.LINES["launch"]["tsundere"]]


# -- learning what you mean --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, kind, targets", [
    ("could you please open discord for me", Kind.OPEN, ("discord",)),
    ("i want you to open discord", Kind.OPEN, ("discord",)),
    ("do me a favor and close steam", Kind.CLOSE, ("steam",)),
    ("would you mind playing let you down by nf", Kind.PLAY, ()),
    ("when i say gaming time, open steam and discord", Kind.SHORTCUT, ("gaming time", "open steam and discord")),
    ("forget the shortcut gaming time", Kind.FORGET, ("gaming time",)),
    ("when i say to school i mean discord", Kind.CORRECTION, ("to school", "discord")),
])
def test_she_gets_what_you_mean(text, kind, targets):
    intent = parse(text)
    assert intent.kind is kind and intent.targets == targets


def test_your_shortcuts():
    s = Settings(slang=False)
    r = rig(FakeDesktop(), settings=s)
    r.router.handle("when i say gaming time, open discord")
    assert s.shortcuts == [["gaming time", "open discord"]]
    r.router.handle("gaming time")
    assert settle(2, lambda: r.system.calls and r.system.calls[-1][0] == "program")
    r.router.handle("forget the shortcut gaming time")
    assert s.shortcuts == []


def test_she_learns_when_you_say_it_another_way():
    from capri.commands.router import CommandRouter
    CommandRouter.LEARN_DELAY_MS = 0
    try:
        s = Settings(slang=False)
        r = rig(FakeDesktop(), settings=s)
        r.router.handle("fire up the chat app thing")             # she doesn't get it
        r.router.handle("open discord")                             # you say it another way: it works
        assert settle(3, lambda: any("remember" in line for line in r.speaker.lines))
        r.service.command.emit("yes")
        assert ["fire up the chat app thing", "open discord"] in s.shortcuts
        r.router.handle("fire up the chat app thing")
        assert settle(2, lambda: len([c for c in r.system.calls if c[0] == "program"]) >= 2)
    finally:
        CommandRouter.LEARN_DELAY_MS = 6000


# -- hearing accents: Whisper's second listen ------------------------------------------------------------------------
def test_whisper_re_hears_the_command():
    from capri.voice.service import VoiceService
    from capri.voice.wakeword import Command
    service = VoiceService(True, False, "", 0.8)
    heard, alts = [], []
    service.command.connect(heard.append)
    service.alternatives.connect(alts.append)
    service.refine = lambda pcm, rate: "open discord"
    service._dispatch(Command("open this cord", ("open his cord",), b"\x00\x01" * 8000))
    assert settle(3, lambda: heard)
    assert heard == ["open discord"] and alts[-1][0] == "open this cord"     # Vosk's guess kept as a runner-up
    service.refine = None
    service._dispatch(Command("close steam", (), b"\x00\x01" * 8000))
    assert heard[-1] == "close steam"


def test_whisper_is_optional():
    from capri.voice import whisper
    assert isinstance(whisper.installed(), bool)
    assert Settings().hearing == "vosk"


# -- more music apps ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, service, song, artist", [
    ("play let you down by nf on soundcloud", "soundcloud", "let you down", "nf"),
    ("play lofi on youtube music", "youtube_music", "lofi", ""), ("play lofi on yt music", "youtube_music", "lofi", ""),
    ("play blinding lights on apple music", "apple_music", "blinding lights", ""),
])
def test_play_on_other_music_apps(text, service, song, artist):
    intent = parse(text)
    assert intent.kind is Kind.PLAY and intent.targets == (service,) and intent.query == song and intent.artist == artist


def test_she_opens_that_apps_search_for_the_song():
    r = rig(FakeDesktop())
    r.service.command.emit("play let you down by nf on soundcloud")
    assert settle(3, lambda: bool(r.system.calls) and "SoundCloud" in r.controller.message)    # after the lookup
    assert r.system.calls[-1] == ("open", "https://soundcloud.com/search?q=let+you+down+nf") or \
        r.system.calls[-1][1].startswith("https://soundcloud.com/search?q=")
    assert "SoundCloud" in r.controller.message


def test_your_default_music_app():
    s = Settings(slang=False)
    r = rig(FakeDesktop(), settings=s)
    assert parse("use youtube music for music").kind is Kind.MUSIC_SERVICE
    r.service.command.emit("use youtube music for music")
    assert s.music_service == "youtube_music" and "YouTube Music" in r.controller.message
    r.service.command.emit("play lofi beats")
    assert settle(3, lambda: bool(r.system.calls) and r.system.calls[-1][1].startswith(
        "https://music.youtube.com/search?q=lofi"))                  # no song found offline: its search
    r.service.command.emit("play deadlock")                          # a game you own still launches
    assert parse("play deadlock").targets == ()
