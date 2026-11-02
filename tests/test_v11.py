"""v1.1: PC power, minimising, Discord, "play X by Y", conversation, sign-in greeting,
start-up default, hair colour and her neural voice. No Windows, network or audio needed:
the Windows parts are faked at the Desktop / registry boundary."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import FakeSpeaker, FakeSpotifyApi, connected, settle  # noqa: E402,F401
from test_commands import FakeCompanion, FakeSystem, make_catalog  # noqa: E402

from capri import autostart, chat  # noqa: E402
from capri.ai.claude import to_intent  # noqa: E402
from capri.assistant import CONVERSATION_TURNS, Assistant  # noqa: E402
from capri.commands.desktop import key_sequence  # noqa: E402
from capri.commands.parser import Intent, Kind, parse  # noqa: E402
from capri.commands.router import CommandRouter, Services  # noqa: E402
from capri.commands.system import ProcessInfo  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.integrations import spotify as sp  # noqa: E402
from capri.session import WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK, SessionWatcher  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402
from capri.voice.service import VoiceService  # noqa: E402


# -- parsing -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, kind, query", [
    ("shutdown", Kind.POWER, "shutdown"), ("shut down my pc", Kind.POWER, "shutdown"),
    ("turn off the computer", Kind.POWER, "shutdown"), ("power off", Kind.POWER, "shutdown"),
    ("restart my computer", Kind.POWER, "restart"), ("reboot", Kind.POWER, "restart"),
    ("put my pc to sleep", Kind.POWER, "sleep"), ("sleep", Kind.POWER, "sleep"),
    ("go to sleep", Kind.POWER, "sleep"), ("lock my pc", Kind.POWER, "lock"), ("lock the screen", Kind.POWER, "lock"),
    ("minimize everything", Kind.MINIMIZE, ""), ("minimise all windows", Kind.MINIMIZE, ""),
    ("minimize my screens", Kind.MINIMIZE, ""), ("show desktop", Kind.MINIMIZE, ""),
    ("bring them back", Kind.RESTORE, ""), ("restore my windows", Kind.RESTORE, ""),
    ("mute me", Kind.DISCORD, "mute"), ("mute myself on discord", Kind.DISCORD, "mute"),
    ("unmute me", Kind.DISCORD, "unmute"), ("mute my mic", Kind.DISCORD, "mute"),
    ("deafen me", Kind.DISCORD, "deafen"), ("undeafen", Kind.DISCORD, "undeafen"),
    ("deafen myself on discord", Kind.DISCORD, "deafen"),
    ("how are you", Kind.CHAT, "how_are_you"), ("tell me a joke", Kind.CHAT, "joke"),
    ("good morning", Kind.CHAT, "good_morning"), ("thanks capri", Kind.CHAT, "thanks"),
    ("im good", Kind.CHAT, "im_good"), ("hello", Kind.CHAT, "hello"),
])
def test_parse_new_commands(text, kind, query):
    i = parse(text)
    assert (i.kind, i.query) == (kind, query)


def test_close_still_beats_power_for_apps():
    assert parse("shut down discord") == Intent(Kind.CLOSE, ("discord",))
    assert parse("close deadlock").kind is Kind.CLOSE


def test_minimise_targets():
    assert parse("minimize discord and spotify") == Intent(Kind.MINIMIZE, ("discord", "spotify"))
    assert parse("minimize this") == Intent(Kind.MINIMIZE, ("this",))


@pytest.mark.parametrize("text, song, artist, where", [
    ("play let you down by nf", "let you down", "nf", ()),
    ("play the search by nf on spotify", "the search", "nf", ()),
    ("play songs by the weekend", "", "the weekend", ()),
    ("play blinding lights", "blinding lights", "", ()),
    ("play let you down by nf on youtube", "let you down", "nf", ("youtube",)),
])
def test_parse_play_song_by_artist(text, song, artist, where):
    i = parse(text)
    assert (i.kind, i.query, i.artist, i.targets) == (Kind.PLAY, song, artist, where)


# -- a router with a fake desktop ------------------------------------------------------------------------------
class FakeDesktop:
    def __init__(self, window=True):
        self.calls = []
        self.window = window

    def power(self, action):
        self.calls.append(("power", action))

    def minimize_all(self):
        self.calls.append(("minimize_all",))
        return 3

    def minimize_foreground(self):
        self.calls.append(("minimize_this",))
        return 1

    def minimize(self, pids):
        self.calls.append(("minimize", tuple(pids)))
        return len(pids)

    def restore(self):
        self.calls.append(("restore",))
        return 3

    def press_keys(self, combo):
        self.calls.append(("keys", combo))

    def press_in_window(self, pids, combo):
        self.calls.append(("in_window", tuple(pids), combo))
        return self.window


def rig(desktop=None, settings=None, processes=None, **services):
    controller = CompanionController()
    service = VoiceService(True, False, "", 0.8)
    listens = []
    service.listen_now = lambda *a: listens.append(1)
    speaker = FakeSpeaker()
    assistant = Assistant(controller, settings or Settings(slang=False), service, speaker)
    system = FakeSystem(processes if processes is not None else [ProcessInfo(10, "Discord.exe")])
    router = CommandRouter(assistant, FakeCompanion(), make_catalog(), system,
                           Services(settings=assistant.settings, desktop=desktop, **services))
    assistant.command_handler = router.handle
    return SimpleNamespace(controller=controller, service=service, speaker=speaker, router=router,
                           assistant=assistant, listens=listens, system=system)


def test_shutdown_only_after_a_spoken_yes():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("shut down my pc")
    assert r.speaker.lines[-1] == "Look up there, think we can make it?" and r.listens == [1]
    assert d.calls == []                                   # nothing yet
    r.service.command.emit("yes")
    assert d.calls == [("power", "shutdown")]
    assert not r.speaker.lines[-1].startswith("Shutting down.")     # v1.32: silent once it's going down
    assert r.controller.message.startswith("Shutting down.")          # (her goodbye is only written)


@pytest.mark.parametrize("answer", ["no", "nah", "uh what", ""])
def test_anything_but_yes_keeps_the_pc_on(answer):
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("restart my computer")
    if answer:
        r.service.command.emit(answer)
    else:
        r.service.no_command.emit()                       # silence
    assert d.calls == []
    assert r.controller.message == "Okay, leaving it on."


def test_sleep_confirms_and_lock_does_not():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("put my pc to sleep")
    r.service.command.emit("yeah")
    r.service.command.emit("lock my pc")
    assert d.calls == [("power", "sleep"), ("power", "lock")]
    assert r.controller.message == "Locked."


def test_the_ai_cannot_skip_the_shutdown_question():
    d = FakeDesktop()
    r = rig(d)
    intent = to_intent("pc_control", {"action": "shutdown"})
    r.router.dispatch(intent)
    assert d.calls == [] and r.speaker.lines[-1] == "Look up there, think we can make it?"
    assert to_intent("pc_control", {"action": "format_c"}) is None


def test_minimise_everything_and_bring_back():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("minimize everything")
    assert d.calls == [("minimize_all",)] and r.controller.message == "Cleared your screen."
    r.service.command.emit("bring them back")
    assert d.calls[-1] == ("restore",) and r.controller.message == "Windows are back."


def test_minimise_an_app():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("minimize discord")
    assert d.calls == [("minimize", (10,))] and r.controller.message == "Minimised Discord."
    r.service.command.emit("minimize deadlock")
    assert r.controller.message == "Deadlock isn't running."


def test_discord_mute_uses_discords_own_keys_by_default():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("mute me")
    assert d.calls == [("in_window", (10,), "ctrl+shift+m")]
    assert r.controller.message == "Pressed mute on Discord."
    assert r.speaker.lines == []                          # never talks over your call
    r.service.command.emit("deafen me")
    assert d.calls[-1] == ("in_window", (10,), "ctrl+shift+d")


def test_discord_with_your_own_keybind_works_from_anywhere():
    d = FakeDesktop()
    r = rig(d, Settings(slang=False, discord_mute_key="ctrl+alt+shift+m"))
    r.service.command.emit("unmute me")
    assert d.calls == [("keys", "ctrl+alt+shift+m")]


def test_discord_not_running_or_in_tray():
    r = rig(FakeDesktop(), processes=[])
    r.service.command.emit("mute me")
    assert r.controller.message == "Discord isn't running."
    r2 = rig(FakeDesktop(window=False))
    r2.service.command.emit("deafen me")
    assert "tray" in r2.controller.message


def test_key_sequence():
    assert key_sequence("ctrl+shift+m") == [(0x11, True), (0x10, True), (ord("M"), True),
                                             (ord("M"), False), (0x10, False), (0x11, False)]
    with pytest.raises(ValueError):
        key_sequence("m")


# -- spotify: song + artist ---------------------------------------------------------------------------------
class RankedApi(FakeSpotifyApi):
    """Fielded search finds nothing (speech spelled the artist oddly); the loose search
    returns a cover first and the real song second."""

    def __call__(self, method, url, params=None, data=None, json_body=None, headers=None):
        if url.endswith("/search"):
            self.calls.append((method, url, params, data, json_body, None))
            if params["q"].startswith("track:"):
                return {"tracks": {"items": []}}
            return {"tracks": {"items": [
                {"name": "Let You Down (Piano Cover)", "uri": "spotify:track:cover", "artists": [{"name": "Covers Co"}]},
                {"name": "Let You Down", "uri": "spotify:track:1", "artists": [{"name": "NF"}]}]}}
        return super().__call__(method, url, params, data, json_body, headers)


def test_spotify_search_with_artist_picks_the_real_song(connected):
    api = RankedApi()
    spotify = sp.Spotify(lambda: "client123", api, sleep=lambda s: None)
    track = spotify.play("let you down", "n f")
    assert track.uri == "spotify:track:1"
    queries = [c[2]["q"] for c in api.calls if c[1].endswith("/search")]
    assert queries == ["track:let you down artist:n f", "let you down n f"]


def test_router_passes_song_and_artist_and_says_what_it_found(connected):
    api = FakeSpotifyApi()
    spotify = sp.Spotify(lambda: "client123", api, sleep=lambda s: None)
    r = rig(FakeDesktop(), spotify=spotify)
    r.service.command.emit("play let you down by nf")
    assert settle(3, lambda: r.controller.state is State.SUCCESS)
    assert r.controller.message == "Playing Let You Down by NF."


# -- conversation ----------------------------------------------------------------------------------------------
def test_small_talk_keeps_listening_for_your_answer():
    r = rig(FakeDesktop())
    r.service.command.emit("hey how are you")
    assert r.controller.state is State.SPEAKING and r.speaker.lines[-1].endswith("?")
    assert r.listens == [1]                                # listening for the reply, no wake word
    r.service.command.emit("im good")
    assert r.speaker.lines[-1] == "Preem. Glad you're good."     # follows on from her question
    r.service.no_command.emit()                            # you stop talking: quiet, no "didn't catch that"
    assert r.controller.state is State.IDLE and "catch" not in r.controller.message


def test_conversation_has_a_limit_and_an_off_switch():
    r = rig(FakeDesktop())
    for _ in range(CONVERSATION_TURNS + 2):
        r.service.command.emit("tell me a joke")
    assert len(r.listens) == CONVERSATION_TURNS
    r2 = rig(FakeDesktop(), Settings(slang=False, conversation=False))
    r2.service.command.emit("how are you")
    assert r2.listens == []


def test_commands_are_not_mistaken_for_chat():
    assert parse("open discord").kind is Kind.OPEN
    assert parse("whats the weather").kind is Kind.WEATHER
    assert parse("what time is it").kind is Kind.TIME


def test_greeting_depends_on_the_time():
    assert chat.greeting(8, False)[0].startswith(("Good morning", "Morning"))
    assert "evening" in chat.greeting(20, False)[0].lower()
    talk = chat.SmallTalk(clock=lambda: datetime(2026, 1, 1, 15))
    assert "afternoon" in talk.reply("good_morning", False)[0]


# -- start-up and sign-in --------------------------------------------------------------------------------------
def test_autostart_switched_on_once_by_default(monkeypatch):
    state = {"enabled": False, "command": ""}
    monkeypatch.setattr(autostart, "SUPPORTED", True)
    monkeypatch.setattr(autostart, "is_enabled", lambda: state["enabled"])
    monkeypatch.setattr(autostart, "current_command", lambda: state["command"])

    def set_enabled(on):
        state["enabled"], state["command"] = on, autostart.launch_command() if on else ""
    monkeypatch.setattr(autostart, "set_enabled", set_enabled)
    s = Settings()
    assert autostart.ensure_default(s) == "enabled" and state["enabled"]
    assert autostart.STARTUP_FLAG in state["command"]
    state["enabled"] = False                        # you turned it off in the tray...
    assert autostart.ensure_default(s) == "" and not state["enabled"]   # ...and it stays off
    Settings.path().unlink(missing_ok=True)


def test_session_watcher_reports_unlock():
    w = SessionWatcher()
    seen = []
    w.signed_in.connect(lambda: seen.append(1))
    assert w.handle(WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK)
    assert not w.handle(WM_WTSSESSION_CHANGE, 0x7)       # locking is not signing in
    assert seen == [1]


def test_big_greeting_then_back_to_the_corner():
    from capri.app import asset_root
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.greeting import GreetingShow
    from capri.ui.sprites import SpriteArt
    art = CharacterArt.load(asset_root() / "capri")
    sprites = SpriteArt.load(asset_root() / "capri_v2")
    c = Companion(CompanionController(), art, Settings(), sprites)
    c.show()
    g = GreetingShow(c)
    g.play("Good morning! Ready for today?", "happy")
    settle(0.8)
    area = c.screen.availableGeometry()
    big = g.big.geometry()
    assert g.active and not c.character.isVisible()
    assert big.height() > area.height() * 0.5                         # big...
    assert abs(g.big.geometry().left() + g.big.content_rect().center().x() - area.center().x()) <= 2   # ...centred
    assert g.caption.isVisible() and "Good morning" in g.caption.text
    g.set_talking(True)
    g.set_talking(False)
    g.done_talking()
    assert settle(4, lambda: not g.active)
    assert c.character.isVisible() and c.panel.isVisible()            # home again
    assert not g.caption.isVisible() and not g.flyer.isVisible()


# -- looks and voice -----------------------------------------------------------------------------------------------
def test_storm_hair_is_hot_pink():
    """v1.26: hot pink like the show (and your reference), a touch pinker than the red on her body."""
    from capri.ui.hair import STORM_RED
    r, g, b = STORM_RED.getRgb()[:3]
    body = (239, 16, 69)                                               # median red on her sprite
    assert r > 240 and g < 50 and body[2] < b < 120


def test_capri_style_is_clean_now():
    """No ring-mod / comb / bit-crush: a pure tone comes out as a pure tone (just brighter)."""
    from capri.speech.effects import apply_style
    from capri.speech.engines import Audio
    rate = 24000
    t = np.arange(rate) / rate
    x = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    y = apply_style(Audio(x, rate, pitched=True), "capri").samples
    mid = y[2000:-2000]
    spec = np.abs(np.fft.rfft(mid * np.hanning(len(mid))))
    peak = spec.argmax()
    side = np.concatenate([spec[:peak - 20], spec[peak + 20:]])
    assert abs(peak * rate / len(mid) - 440) < 2 and side.max() < spec[peak] * 0.01


class FakeKokoro:
    def __init__(self, *a):
        self.created = []

    def get_voice_style(self, name):
        return np.full(4, {"af_bella": 1.0, "af_heart": 2.0}[name], dtype=np.float32)

    def create(self, text, voice, speed, lang):
        self.created.append((text, voice if isinstance(voice, str) else voice.tolist(), speed, lang))
        return np.ones(24000, dtype=np.float32), 24000


def test_neural_voice_blend_and_tape_lift(tmp_path, monkeypatch):
    from capri.speech import engines
    (tmp_path / engines.KOKORO_MODEL).write_bytes(b"x")
    np.savez(tmp_path / engines.KOKORO_VOICES, af_bella=np.zeros(1), af_heart=np.zeros(1), am_adam=np.zeros(1))
    (tmp_path / (engines.KOKORO_VOICES + ".npz")).rename(tmp_path / engines.KOKORO_VOICES)
    monkeypatch.setitem(sys.modules, "kokoro_onnx", SimpleNamespace(Kokoro=FakeKokoro))
    e = engines.KokoroEngine(tmp_path)
    assert e.voices() == ["neural: Capri", "neural: af_bella", "neural: af_heart"]   # female voices only
    e._kokoro = FakeKokoro()
    audio = e.synthesize("Hey choom!", "neural: Capri", 0.5, pitch=4.0)
    text, style, speed, lang = e._kokoro.created[0]
    assert text == "Hey choom!" and lang == "en-us"                    # says "choom" right
    assert np.allclose(style, 0.6 * 1.0 + 0.4 * 2.0)                   # the Capri blend
    lift = 2 ** (4.0 * engines.KokoroEngine.PITCH_SCALE / 12)
    assert abs(speed - 1.1 / lift) < 1e-6                              # rendered slower...
    assert abs(len(audio.samples) - 24000 / lift) <= 1 and audio.pitched   # ...played faster: same length, higher


def test_default_voice_prefers_her_neural_voice():
    from capri.speech.engines import VoiceBox
    box = VoiceBox.__new__(VoiceBox)
    box.engines = [SimpleNamespace(voices=lambda: ["Microsoft Zira Desktop", "neural: Capri", "neural: af_sky"])]
    assert box.default_voice() == "neural: Capri"


def test_speaker_keeps_a_voice_reload_when_new_lines_arrive():
    from capri.speech.speaker import Speaker
    made = []

    def factory():
        made.append(1)
        return SimpleNamespace(synthesize=lambda *a: None, voices=lambda: [])
    spk = Speaker(Settings(), factory, player=lambda s, r: (lambda: None), sleep=lambda s: None)
    spk.ready.wait(2)
    spk.reload_voices()
    spk.say("hello")
    deadline = time.monotonic() + 2
    while len(made) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    spk.shutdown()
    assert len(made) == 2
