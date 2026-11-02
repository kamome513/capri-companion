"""v1.20: music app setting sticks, YouTube Music plays the song, expressive voice, a real chat
fallback, Discord screen sharing, and a pile of small fixes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Kind, parse  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402


def _tab(r):
    from capri.ui.assistant_tab import AssistantTab
    r.assistant.speaker.say = lambda *a, **k: True
    r.assistant.speaker.voices = lambda: []
    return AssistantTab(r.assistant, r.router, None)


# -- the music app setting ---------------------------------------------------------------------------------
def test_picking_a_music_app_takes_effect_straight_away():
    r = rig(FakeDesktop())
    tab = _tab(r)
    tab.music_service.setCurrentIndex(tab.music_service.findData("youtube_music"))
    assert r.assistant.settings.music_service == "youtube_music"
    assert Settings.load().music_service == "youtube_music"           # saved, not just in memory


def test_closing_settings_keeps_what_you_changed():
    from capri.ui.settings_window import SettingsWindow
    r = rig(FakeDesktop())
    s = r.assistant.settings
    tab = _tab(r)
    win = SettingsWindow(r.router, s, QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [],
                         extra_tabs=((tab, "Assistant"),))
    win.show()
    tab.city.setText("Oslo")
    tab.city.textEdited.emit("Oslo")                                  # as if typed
    win.close()
    assert s.weather_city == "Oslo"


def test_settings_does_not_undo_changes_made_by_voice():
    from capri.ui.settings_window import SettingsWindow
    r = rig(FakeDesktop())
    s = r.assistant.settings
    tab = _tab(r)
    win = SettingsWindow(r.router, s, QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [],
                         extra_tabs=((tab, "Assistant"),))
    win.tabs.setCurrentIndex(win.tabs.count() - 1)                    # on the Assistant tab
    win.show()
    win.close()
    r.router.handle("use soundcloud for music")                        # said while Settings was closed
    s.speech_style = "glitch"
    win.show()
    assert tab.music_service.currentData() == "soundcloud" and tab.style_box.currentData() == "glitch"
    tab.apply()
    assert s.music_service == "soundcloud" and s.speech_style == "glitch"
    win.close()


def test_play_uses_the_music_app_you_picked():
    r = rig(FakeDesktop())
    r.assistant.settings.music_service = "soundcloud"
    r.router.handle("play let you down by nf")
    from test_stage5 import settle
    assert settle(3, lambda: any("soundcloud.com" in str(c) for c in r.system.calls))


# -- playing the song on any music app ----------------------------------------------------------------------
def test_finding_songs_on_each_service(monkeypatch):
    monkeypatch.undo()                                                # the real finders, fake internet
    import json

    from capri.integrations import music_find as mf
    music_reply = json.dumps({"contents": {"musicResponsiveListItemRenderer": {"x": 1, "videoId": "dQw4w9WgXcQ"}}})
    assert mf.find_track("youtube_music", "let you down nf", post=lambda url, body: music_reply) == \
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
    page = 'var ytInitialData = {"adSlotRenderer":{},"videoRenderer":{"videoId":"abcdefghijk","title":"x"}};'

    def offline(url, body):
        raise OSError("offline")
    assert mf.find_track("youtube_music", "x", fetch=lambda url: page, post=offline) == \
        "https://music.youtube.com/watch?v=abcdefghijk"                # backup: YouTube's top video
    deezer = json.dumps({"data": [{"link": "https://www.deezer.com/track/3135556"}]})
    assert mf.find_track("deezer", "x", fetch=lambda url: deezer) == "https://www.deezer.com/track/3135556"
    apple = json.dumps({"results": [{"trackViewUrl": "https://music.apple.com/us/album/let-you-down/1?i=2"}]})
    assert mf.find_track("apple_music", "x", fetch=lambda url: apple).startswith("https://music.apple.com/us/album/")
    band = '<div class="heading"><a href="https://nfrealmusic.bandcamp.com/track/let-you-down?from=search">'
    assert mf.find_track("bandcamp", "x", fetch=lambda url: band) == "https://nfrealmusic.bandcamp.com/track/let-you-down"
    evil = json.dumps({"data": [{"link": "https://evil.example.com/track/1"}]})
    assert mf.find_track("deezer", "x", fetch=lambda url: evil) is None   # only the service's own pages
    assert mf.find_track("soundcloud", "x", fetch=lambda url: "") is None  # no public search: search page


class FakeTabs:
    def __init__(self, names):
        from capri.integrations.browser_tabs import Tab
        self.buttons = [Tab(n, (0, 100 + i * 50, 40, 140 + i * 50)) for i, n in enumerate(names)]
        self.after_press = None

    def front(self):
        return 7

    def window(self, browser=""):
        return 7

    def play_button(self, hwnd):
        from capri.integrations.browser_tabs import BrowserTabs
        ui = type("UI", (), {"buttons": lambda _s, h, control, with_rects: [
            type("B", (), {"name": t.name, "rect": t.rect})() for t in self.buttons]})()
        return BrowserTabs(ui, None, lambda: [], lambda: 7).play_button(hwnd)


def _music_rig(service, found, names):
    from types import SimpleNamespace
    from test_stage5 import settle
    r = rig(FakeDesktop())
    r.assistant.settings.music_service = service
    tabs = FakeTabs(names)
    clicked = []

    def click(target):
        clicked.append(target.name)
        tabs.buttons = [type(b)("Pause", b.rect) if b.name == target.name else b for b in tabs.buttons]
    r.router.services.tabs, r.router.services.click_at = tabs, click
    r.router.services.music_find = SimpleNamespace(find_track=lambda s, q: found, find_video=lambda q: None,
                                                   AUTOPLAYS={"youtube_music"}, WATCH="", MUSIC_WATCH="")
    r.router._sleep = lambda t: None
    return r, clicked, settle


def test_play_on_deezer_opens_the_song_and_presses_play():
    r, clicked, settle = _music_rig("deezer", "https://www.deezer.com/track/1",
                                    ["Playlist", "Play next", "Play", "Play"])
    r.router.handle("play let you down by nf")
    assert settle(3, lambda: r.controller.message.startswith("Playing"))
    assert ("open", "https://www.deezer.com/track/1") in r.system.calls
    assert clicked == ["Play"]


def test_play_on_soundcloud_presses_the_first_results_play():
    r, clicked, settle = _music_rig("soundcloud", None, ["Play", "Play"])
    r.router.handle("play let you down by nf")
    assert settle(3, lambda: r.controller.message.startswith("Playing"))
    assert any("soundcloud.com/search" in str(c) for c in r.system.calls) and clicked == ["Play"]


def test_youtube_music_plays_by_itself():
    r, clicked, settle = _music_rig("youtube_music", "https://music.youtube.com/watch?v=abcdefghijk", [])
    r.router.handle("play let you down by nf on youtube music")
    assert settle(3, lambda: r.controller.message.startswith("Playing"))
    assert ("open", "https://music.youtube.com/watch?v=abcdefghijk") in r.system.calls and clicked == []


def test_no_play_button_is_said_honestly():
    r, clicked, settle = _music_rig("tidal", None, [])
    r.router.handle("play let you down by nf")
    assert settle(3, lambda: "click" in r.controller.message.lower())
    assert clicked == []


# -- highs and lows in her voice ------------------------------------------------------------------------------
def _syllables(seconds=2.0, rate=22050, hz=220.0):
    import numpy as np
    from capri.speech.engines import Audio
    t = np.arange(int(rate * seconds)) / rate
    env = 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * 2.2 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t))
    return Audio((np.sin(2 * np.pi * hz * t) * env * 0.8).astype(np.float32), rate, pitched=True)


def _pitch_track(x, rate, win=0.12):
    import numpy as np
    n = int(rate * win)
    out = []
    for start in range(0, len(x) - n, n):
        seg = x[start:start + n] * np.hanning(n)
        spec = np.abs(np.fft.rfft(seg, 8 * n))
        out.append(np.fft.rfftfreq(8 * n, 1 / rate)[int(np.argmax(spec))])
    return np.array(out)


def test_her_voice_goes_up_and_down():
    import numpy as np
    from capri.speech.effects import intonation
    a = _syllables()
    flat = _pitch_track(a.samples, a.rate)
    lively = _pitch_track(intonation(a, 1.0, seed=3).samples, a.rate)
    semis = 12 * np.log2(lively / 220.0)
    assert np.ptp(12 * np.log2(flat / 220.0)) < 0.3                 # the input: one steady tone
    assert np.ptp(semis) > 2.5                                         # now: real highs and lows
    out = intonation(a, 1.0, seed=3)
    assert 0.8 < len(out.samples) / len(a.samples) < 1.25 and np.isfinite(out.samples).all()


def test_questions_go_up_at_the_end():
    import numpy as np
    from capri.speech.effects import intonation
    a = _syllables()
    told = _pitch_track(intonation(a, 1.0, seed=5).samples, a.rate)
    asked = _pitch_track(intonation(a, 1.0, question=True, seed=5).samples, a.rate)
    assert asked[-3:].mean() > told[-3:].mean() * 2 ** (2 / 12)      # 2+ semitones higher at the end


def test_steady_when_expression_is_off_and_deadpan_barely_moves():
    from capri import personality
    from capri.speech.effects import intonation
    a = _syllables()
    assert intonation(a, 0.0).samples is a.samples
    assert personality.get("deadpan").expressive < 0.5 < personality.get("hype").expressive


def test_expression_is_a_setting():
    r = rig(FakeDesktop())
    tab = _tab(r)
    tab.expression.setValue(90)
    tab.apply()
    assert r.assistant.settings.speech_expression == 0.9


# -- the chatbot: sensible replies ----------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["ngnge", "blorp zzk", "asdkjh qwpoe"])
def test_nonsense_gets_didnt_catch_that_not_why(said):
    import random

    from capri.chatbot import ChatBot
    bot = ChatBot(rng=random.Random(1))
    for persona in ("edgerunner", "sarcastic", "sweet", "deadpan"):
        text, _emotion = bot.reply(said, persona)
        assert bot.last_kind == "misheard" and "why" not in text.lower()


def test_no_interrogating_catch_all():
    from capri.chatbot import BANK
    for persona, options in BANK["generic"].items():
        for _emotion, plain, street in options:
            assert "why" not in plain.lower() and "explain" not in plain.lower(), plain


@pytest.mark.parametrize("said, kind", [
    ("i played valorant all day", "about_games"), ("my homework is killing me", "about_school"),
    ("my dog is sick", "bad_news"), ("i won my ranked match", "good_news"), ("ugh", "sigh"),
    ("how do magnets work", "dont_know"), ("the sky is blue", "generic"),
])
def test_she_reacts_to_what_you_said(said, kind):
    from capri.chatbot import ChatBot
    bot = ChatBot()
    bot.reply(said)
    assert bot.last_kind == kind


@pytest.mark.parametrize("said, subject", [("what is a black hole", "black hole"), ("who was napoleon", "napoleon"),
                                           ("tell me about minecraft", "minecraft"), ("define entropy", "entropy")])
def test_what_is_questions_get_looked_up(said, subject):
    from capri.chatbot import ChatBot
    bot = ChatBot()
    bot.reply(said)
    assert (bot.last_kind, bot.last_subject) == ("lookup", subject)


def test_wikipedia_answers_are_short_and_clean(monkeypatch):
    monkeypatch.undo()
    from capri.integrations import answers
    pages = {"search": ["napoleon", ["Napoleon"]], "summary": {"type": "standard", "extract":
             "Napoleon Bonaparte (born Napoleone di Buonaparte; 15 August 1769 - 5 May 1821) was a French "
             "military officer and statesman. He rose to prominence during the French Revolution. "
             "He led a series of campaigns across Europe and much more that is far too long to say out loud now."}}
    got = answers.lookup("napoleon", get=lambda url: pages["search" if "opensearch" in url else "summary"])
    assert got.startswith("Napoleon Bonaparte was a French military officer") and "(" not in got
    assert len(got.split()) <= answers.MAX_WORDS + 1
    ambiguous = {"search": ["x", ["Mercury"]], "summary": {"type": "disambiguation", "extract": "Mercury may be"}}
    assert answers.lookup("mercury", get=lambda url: ambiguous["search" if "opensearch" in url else "summary"]) is None
    assert answers.lookup("x", get=lambda url: (_ for _ in ()).throw(OSError("offline"))) is None


def test_no_ai_what_is_gets_a_real_answer():
    from types import SimpleNamespace
    from test_stage5 import settle
    r = rig(FakeDesktop())
    r.assistant.settings.ai_enabled = False
    r.router.services.answers = SimpleNamespace(lookup=lambda s: "A black hole is a region of spacetime.")
    r.router.handle("what is a black hole")
    assert settle(3, lambda: r.controller.message == "A black hole is a region of spacetime.")


def test_unanswerable_offers_a_search_and_does_it():
    r = rig(FakeDesktop())
    r.assistant.settings.ai_enabled = False
    r.router.handle("how do magnets work")
    assert "look it up" in r.speaker.lines[-1].lower() or "search" in r.speaker.lines[-1].lower()
    r.service.command.emit("yes")
    assert any("magnets" in str(c) for c in r.system.calls)


def test_a_new_command_after_the_offer_still_works():
    r = rig(FakeDesktop())
    r.assistant.settings.ai_enabled = False
    r.router.handle("how do magnets work")
    r.service.command.emit("open discord")
    assert any("Discord" in str(c) for c in r.system.calls)


# -- Discord: stream, stop streaming, leave the call ----------------------------------------------------------
@pytest.mark.parametrize("said, action", [
    ("hey capri stream my screen", "stream"), ("share my screen", "stream"), ("go live", "stream"),
    ("screen share", "stream"), ("stop streaming", "stop_stream"), ("stop my stream", "stop_stream"),
    ("stop sharing my screen", "stop_stream"), ("hey capri leave call", "leave"), ("leave the call", "leave"),
    ("hang up", "leave"), ("leave vc", "leave"), ("disconnect from the call", "leave"),
])
def test_discord_call_commands(said, action):
    intent = parse(said)
    assert intent.kind is Kind.DISCORD and intent.query == action


def test_watching_a_stream_is_still_a_video():
    assert parse("stop the stream").kind is Kind.VIDEO


class FakeDiscordUI:
    """Discord's voice panel: Mute/Deafen, Share Your Screen, Disconnect - plus a settings page
    "Disconnect" (for a linked account) far away from the voice panel."""

    def __init__(self, in_call=True):
        self.in_call, self.streaming, self.picker, self.pressed = in_call, False, False, []

    def _b(self, name, rect=(10, 900, 40, 930)):
        ui = self

        class B:
            def __init__(self):
                self.name, self.rect = name, rect

            def press(self):
                ui.pressed.append(name)
                if name == "Share Your Screen":
                    ui.picker = True
                elif name == "Go Live":
                    ui.picker, ui.streaming = False, True
                elif name == "Stop Streaming":
                    ui.streaming = False
                elif name == "Disconnect" and self.rect[0] < 500:
                    ui.in_call = ui.streaming = False
                elif name == "Join Voice":
                    ui.in_call = True

            def toggled(self):
                return None
        return B()

    def buttons(self, hwnd, names=None, control=None, with_rects=False):
        out = [self._b("Mute", (10, 1000, 40, 1030)), self._b("Disconnect", (900, 300, 980, 330))]   # settings one
        if self.in_call:
            out += [self._b("Disconnect", (200, 940, 230, 970))]
            out += [self._b("Stop Streaming")] if self.streaming else [self._b("Share Your Screen")]
        if self.picker:
            out += [self._b("Go Live", (500, 600, 600, 640))]
        return [b for b in out if names is None or b.name in names]

    def clickables(self, hwnd):
        picker = [self._b("Screens"), self._b("Screen 1"), self._b("Screen Share")] if self.picker else []
        join = [self._b("Join Voice", (400, 500, 480, 530))] if getattr(self, "viewing", False) and not self.in_call else []
        return self.buttons(hwnd) + picker + join


def _call(ui):
    from capri.integrations.app_buttons import DiscordCall
    clock = [0.0]

    def sleep(t):
        clock[0] += t
    return DiscordCall(ui, lambda pids: [1], sleep=sleep, clock=lambda: clock[0])


def test_streaming_your_screen():
    ui = FakeDiscordUI()
    assert _call(ui).stream([1]) == "streaming"
    assert ui.pressed[:1] == ["Share Your Screen"] and "Screen 1" in ui.pressed and ui.pressed[-1] == "Go Live"
    assert _call(ui).stream([1]) == "already_streaming"
    assert _call(ui).stop_stream([1]) == "stopped" and not ui.streaming
    assert _call(ui).stop_stream([1]) == "not_streaming"


def test_leaving_presses_the_voice_panels_disconnect_only():
    ui = FakeDiscordUI()
    assert _call(ui).leave([1]) == "left" and not ui.in_call
    assert _call(ui).leave([1]) == "no_call"                 # never the settings page's Disconnect
    assert _call(FakeDiscordUI(in_call=False)).stream([1]) == "no_call"


def test_she_says_what_happened():
    from test_stage5 import settle
    from capri.commands.system import ProcessInfo
    r = rig(FakeDesktop(), processes=[ProcessInfo(10, "Discord.exe")])
    ui = FakeDiscordUI()
    r.router.services.discord_call = _call(ui)
    r.router.handle("hey capri leave call")
    assert settle(3, lambda: r.controller.message == "Left the call.")
    r.router.services.discord_call = None
    r.router.handle("stream my screen")
    assert settle(3, lambda: "Windows" in r.controller.message)    # honest off Windows


# -- the bug sweep ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said, kind, query", [
    ("show my desktop", Kind.MINIMIZE, ""),                          # was "stream my screen"
    ("stop talking", Kind.QUIET, ""), ("shut up", Kind.QUIET, ""), ("be quiet", Kind.QUIET, ""),
    ("turn it down a bit", Kind.MEDIA, "volume_down"), ("turn the sound up a little", Kind.MEDIA, "volume_up"),
    ("talk faster", Kind.VOICE, "faster"), ("slow down", Kind.VOICE, "slower"), ("speak up", Kind.VOICE, "louder"),
    ("change your voice", Kind.VOICE, "next_style"), ("be more expressive", Kind.VOICE, "more_expressive"),
    ("sit on my window", Kind.PERCH_ON, ""), ("get off the window", Kind.PERCH_OFF, ""),
    ("cancel my timer", Kind.TIMER, "cancel"), ("how long is left", Kind.TIMER, "left"),
    ("be sarcastic", Kind.PERSONALITY, ""), ("silence me", Kind.DISCORD, "mute"),
])
def test_everyday_phrasings(said, kind, query):
    intent = parse(said)
    assert intent.kind is kind and intent.query == query


@pytest.mark.parametrize("said, targets", [
    ("set a timer for 5 minutes", ("300", "")), ("five minute timer", ("300", "")),
    ("timer for twenty five minutes", ("1500", "")), ("set a timer for an hour and a half", ("5400", "")),
    ("remind me in 10 minutes to check the oven", ("600", "check the oven")),
    ("remind me to call mom in two hours", ("7200", "call mom")),
])
def test_timers_and_reminders_parse(said, targets):
    intent = parse(said)
    assert intent.kind is Kind.TIMER and intent.query == "add" and intent.targets == targets


@pytest.mark.parametrize("said, clock", [("set an alarm for 7:30 am", "7:30"), ("wake me up at 7am", "7:00"),
                                         ("set an alarm for 10 pm", "22:00"), ("wake me up at 6 30 in the morning", "6:30")])
def test_alarms_parse(said, clock):
    intent = parse(said)
    assert intent.kind is Kind.TIMER and intent.query == "alarm" and intent.targets[0] == clock


def test_search_site_for_something():
    intent = parse("search youtube for cat videos")
    assert intent.targets == ("youtube",) and intent.query == "cat videos"


def test_a_timer_rings_and_can_be_cancelled():
    from capri.commands.router import spoken_duration
    from test_stage5 import settle
    r = rig(FakeDesktop())
    r.router.handle("set a timer for 5 minutes")
    assert r.controller.message == "Timer set for 5 minutes."
    r.router.handle("how long is left")
    assert "left" in r.controller.message and "minute" in r.controller.message
    r.router.handle("cancel my timer")
    assert r.controller.message == "Cancelled your timer." and r.router._timers == []
    r.router.dispatch(parse("remind me in 1 second to stretch"))
    assert settle(3, lambda: r.controller.message == "Reminder: stretch.")
    assert spoken_duration(5400) == "1 hour and 30 minutes" and spoken_duration(90) == "1 minute and 30 seconds"


def test_stop_talking_stops_her():
    r = rig(FakeDesktop())
    stopped = []
    r.speaker.stop = lambda: stopped.append(1)
    lines_before = len(r.speaker.lines)
    r.router.handle("shut up")
    assert stopped and len(r.speaker.lines) == lines_before         # and she doesn't answer back


def test_voice_changes_by_voice():
    r = rig(FakeDesktop())
    s = r.assistant.settings
    speed, style = s.speech_speed, s.speech_style
    r.router.handle("talk faster")
    assert s.speech_speed > speed and r.controller.message.startswith("Faster")
    r.router.handle("change your voice")
    assert s.speech_style != style and "New voice" in r.controller.message
    s.speech_volume = 1.0
    r.router.handle("speak up")
    assert "as far as" in r.controller.message


@pytest.mark.parametrize("said, kind", [("who made you", "creator"), ("are you there", "here"),
                                        ("flip a coin", "coin"), ("roll a dice", "dice")])
def test_small_things_she_should_just_know(said, kind):
    from capri.chatbot import ChatBot
    bot = ChatBot()
    bot.reply(said)
    assert bot.last_kind == kind


@pytest.mark.parametrize("said, kind", [("you suck", "insult"), ("why", "why"), ("what should i eat", "idea_food"),
                                        ("what should i play tonight", "idea_play"),
                                        ("show me my documents", "generic")])      # not "what are you watching?"
def test_sweep_fixes(said, kind):
    from capri.chatbot import ChatBot
    bot = ChatBot()
    bot.reply(said)
    assert bot.last_kind == kind


def test_whats_your_name_is_answered_not_searched():
    assert parse("what's your name").kind is Kind.CHAT
