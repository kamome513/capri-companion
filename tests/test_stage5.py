"""Stage 5: voice + animation, music, weather, optional AI. No network, audio or API key needed."""

from __future__ import annotations

import sys
import threading
import time
import urllib.request
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

from test_commands import FakeCompanion, FakeSystem, make_catalog  # noqa: E402
from test_voice_service import start, stop  # noqa: E402

from capri import secrets  # noqa: E402
from capri.ai import claude  # noqa: E402
from capri.ai.claude import ClaudeBrain, to_intent  # noqa: E402
from capri.assistant import Assistant  # noqa: E402
from capri.commands.parser import Intent, Kind, parse, parse_yes_no  # noqa: E402
from capri.commands.router import CommandRouter, Services  # noqa: E402
from capri.commands.system import ProcessInfo  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.integrations import http  # noqa: E402
from capri.integrations import spotify as sp  # noqa: E402
from capri.integrations.weather import Weather, WeatherError  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.speech.effects import apply_style, levels  # noqa: E402
from capri.speech.engines import Audio  # noqa: E402
from capri.speech.speaker import Speaker  # noqa: E402
from capri.states import State  # noqa: E402
from capri.voice.service import VoiceService  # noqa: E402


def settle(seconds=2.0, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if until and until():
            return True
        time.sleep(0.01)
    return False


def tone(seconds=0.6, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    env = (np.sin(np.pi * t / seconds) ** 2)               # a "syllable"
    return Audio((0.5 * env * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate)


# -- parser -------------------------------------------------------------------------------
@pytest.mark.parametrize("text,kind,query,day", [
    ("play let you down by nf", Kind.PLAY, "let you down", "today"),
    ("play blinding lights on spotify", Kind.PLAY, "blinding lights", "today"),
    ("pause the music", Kind.MEDIA, "pause", "today"), ("stop the music", Kind.MEDIA, "pause", "today"),
    ("resume", Kind.MEDIA, "resume", "today"), ("play music", Kind.MEDIA, "resume", "today"),
    ("next song", Kind.MEDIA, "next", "today"), ("skip this song", Kind.MEDIA, "next", "today"),
    ("previous song", Kind.MEDIA, "previous", "today"), ("turn it up", Kind.MEDIA, "volume_up", "today"),
    ("whats playing", Kind.NOW_PLAYING, "", "today"), ("what song is this", Kind.NOW_PLAYING, "", "today"),
    ("whats the weather", Kind.WEATHER, "", "today"), ("whats the weather today", Kind.WEATHER, "", "today"),
    ("whats the weather tomorrow", Kind.WEATHER, "", "tomorrow"),
    ("whats the weather in new york tomorrow", Kind.WEATHER, "new york", "tomorrow"),
    ("hows the weather in london", Kind.WEATHER, "london", "today"),
    ("will it rain tomorrow in paris", Kind.RAIN, "paris", "tomorrow"),
    ("do i need an umbrella", Kind.RAIN, "", "today"),
])
def test_parse_stage5(text, kind, query, day):
    i = parse(text)
    assert (i.kind, i.query, i.day) == (kind, query, day)


def test_close_and_open_still_work():
    assert parse("stop discord").kind is Kind.CLOSE
    assert parse("open spotify").kind is Kind.OPEN


def test_her_own_question_is_not_an_answer():
    assert parse_yes_no("yes or no") is None
    assert parse_yes_no("say yes or no") is None


# -- voice effects ----------------------------------------------------------------------------
@pytest.mark.parametrize("style", ["natural", "netrunner", "glitch"])
def test_styles_are_clean(style):
    out = apply_style(tone(), style, seed=1)
    assert np.isfinite(out.samples).all()
    assert 0.85 <= np.abs(out.samples).max() <= 0.9001
    assert 0.4 < len(out.samples) / out.rate < 0.9


def dominant_hz(x, rate):
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.fft.rfftfreq(len(x), 1 / rate)[int(np.argmax(spectrum))]


def test_pitch_shift_raises_pitch_but_keeps_her_speed():
    from capri.speech.effects import pitch_shift
    rate = 16000
    t = np.arange(rate) / rate
    x = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    up = pitch_shift(x, rate, 4.0)                       # +4 semitones = x1.26
    assert abs(len(up) - len(x)) / len(x) < 0.04          # same length = same speaking speed
    assert abs(dominant_hz(up, rate) - 220 * 2 ** (4 / 12)) < 8
    assert pitch_shift(x, rate, 0.0) is x


def test_engine_pitch_is_not_applied_twice():
    a = tone()
    a.pitched = True
    assert np.array_equal(apply_style(a, "natural", pitch=5.0).samples * 0 + 1, np.ones(len(a.samples)))
    assert len(apply_style(a, "natural", pitch=5.0).samples) == len(a.samples)


def test_levels_follow_loudness():
    lv = levels(tone(0.9))
    assert 25 <= len(lv) <= 28                              # 30 per second
    assert all(0 <= v <= 1 for v in lv)
    mid = len(lv) // 2
    assert lv[mid] > lv[0] and lv[mid] > lv[-1]             # loud in the middle of the syllable


# -- speaker ---------------------------------------------------------------------------------------
class FakeVoiceBox:
    def __init__(self):
        self.said = []

    def voices(self):
        return ["Fake Zira"]

    def synthesize(self, text, voice, speed, pitch=0.0):
        self.said.append((text, voice, speed, pitch))
        return tone(0.3)


class FakePlayer:
    def __init__(self):
        self.played = []
        self.stopped = 0

    def __call__(self, samples, rate):
        self.played.append((float(np.abs(samples).max()), rate))
        return self.stop

    def stop(self):
        self.stopped += 1


def make_speaker(**settings):
    s = Settings(**settings)
    box, player = FakeVoiceBox(), FakePlayer()
    speaker = Speaker(s, lambda: box, player)
    events = []
    speaker.started.connect(lambda text, lv, frame, dur: events.append(("started", text, len(lv), round(dur, 1))))
    speaker.speaking_changed.connect(lambda on: events.append(("speaking", on)))
    speaker.finished.connect(lambda: events.append(("finished",)))
    return speaker, box, player, events, s


def test_speaker_says_and_signals():
    speaker, box, player, events, s = make_speaker(speech_volume=0.5, speech_style="natural")
    called = []
    assert speaker.say("Launching Deadlock.", then=lambda: called.append(threading.current_thread().name))
    assert settle(3, lambda: called)
    assert box.said[0][0] == "Launching Deadlock."
    assert player.played and abs(player.played[0][0] - 0.315) < 0.01    # 0.9 peak x 0.5 volume x 0.7 master
    kinds = [e[0] for e in events]
    assert kinds.index("speaking") < kinds.index("started") < kinds.index("finished")
    assert ("speaking", False) in events
    assert called == ["MainThread"]                                       # "then" runs on the UI thread
    speaker.shutdown()


def test_speaker_respects_spoken_replies_off():
    speaker, box, player, events, s = make_speaker(speech_enabled=False)
    assert speaker.say("hello") is False
    settle(0.3)
    assert box.said == [] and player.played == []
    speaker.shutdown()


def test_new_line_interrupts_the_old_one(monkeypatch):
    speaker, box, player, events, s = make_speaker()
    box.synthesize = lambda text, voice, speed, pitch=0.0: tone(2.0)
    speaker.say("a long sentence")
    settle(0.4, lambda: player.played)
    speaker.say("short")
    assert settle(4, lambda: events.count(("finished",)) >= 2)
    assert player.stopped >= 1
    speaker.shutdown()


def test_mic_ignores_her_own_voice():
    service, mic, rec, thread = start()
    from capri.voice.service import Status
    rec.wait_for(("status", Status.READY))
    service.set_speaking(True)
    mic.say("capri", "open", "discord", 1.0)
    time.sleep(1.0)
    assert not any(e[0] == "command" for e in rec.events)
    service.set_speaking(False)
    mic.say("capri", "open", "spotify", 1.0)
    rec.wait_for(("command", "open spotify"))
    stop(service, thread)


class FakeSpeaker:
    def __init__(self):
        self.lines = []
        self.emotions = []
        self.speaking_changed = SimpleNamespace(connect=lambda f: None)

    def say(self, text, then=None, emotion="neutral"):
        self.lines.append(text)
        self.emotions.append(emotion)
        if then:
            then()
        return True

    def stop(self):
        pass


def test_confirmation_is_spoken_before_listening():
    controller = CompanionController()
    service = VoiceService(True, False, "", 0.8)
    order = []
    service.listen_now = lambda: order.append("listen")
    speaker = FakeSpeaker()
    speaker.say = lambda text, then=None, emotion="": (order.append(("say", text, emotion)), then and then(), True)[-1]
    a = Assistant(controller, Settings(), service, speaker)
    a.confirm("Close Deadlock? Say yes or no.", lambda yes: None)
    assert order == [("say", "Close Deadlock? Say yes or no.", "serious"), "listen"]


# -- weather ------------------------------------------------------------------------------------------
GEO = {"results": [{"name": "Manchester", "country": "United Kingdom", "latitude": 53.48, "longitude": -2.24}]}
FORECAST = {
    "current": {"temperature_2m": 13.6, "apparent_temperature": 11.0, "weather_code": 61, "wind_speed_10m": 20},
    "daily": {"weather_code": [61, 0], "temperature_2m_max": [15.2, 18.9], "temperature_2m_min": [8.6, 7.1],
              "precipitation_probability_max": [80, 10]},
}


def fake_fetch(calls):
    def fetch(method, url, params=None, **kw):
        calls.append((url, dict(params or {})))
        if "geocoding" in url:
            return GEO if params["name"].lower() != "atlantis" else {"results": []}
        return FORECAST
    return fetch


def test_weather_today_and_tomorrow():
    calls = []
    w = Weather("metric", fake_fetch(calls))
    assert w.report("manchester") == ("Manchester today: 14\u00b0 now and light rain. High 15\u00b0, low 9\u00b0, "
                                      "80% chance of rain.")              # high, low, rain - no advice
    assert w.report("manchester", "tomorrow").startswith("Tomorrow in Manchester: clear skies. High 19\u00b0, low 7\u00b0, ")
    assert sum("geocoding" in u for u, _ in calls) == 1        # the place is looked up once
    assert calls[-1][1]["temperature_unit"] == "celsius"
    w.units = "imperial"
    w.report("manchester")
    assert calls[-1][1]["temperature_unit"] == "fahrenheit"
    assert w.will_it_rain("manchester") == "80% chance of rain in Manchester today."
    assert "tomorrow" in w.will_it_rain("manchester", "tomorrow")


def test_weather_errors():
    with pytest.raises(WeatherError, match="Atlantis"):
        Weather("metric", fake_fetch([])).report("Atlantis")

    def offline(*a, **k):
        raise OSError("no network")
    with pytest.raises(WeatherError, match="unreachable"):
        Weather("metric", offline).report("Manchester")


# -- spotify -----------------------------------------------------------------------------------------------
class FakeSpotifyApi:
    def __init__(self, premium=True, devices=None):
        self.calls = []
        self.premium = premium
        self.devices = devices if devices is not None else [{"id": "pc1", "type": "Computer", "is_active": False}]

    def __call__(self, method, url, params=None, data=None, json_body=None, headers=None):
        self.calls.append((method, url, params, data, json_body, (headers or {}).get("Authorization")))
        if url == sp.TOKEN_URL:
            return {"access_token": "fresh", "expires_in": 3600,
                    **({"refresh_token": "r2"} if data["grant_type"] == "authorization_code" else {})}
        if url.endswith("/search"):
            return {"tracks": {"items": [{"name": "Let You Down", "uri": "spotify:track:1",
                                          "artists": [{"name": "NF"}]}]}}
        if url.endswith("/devices"):
            return {"devices": self.devices}
        if url.endswith("/me/player/play") and method == "PUT":
            if not self.premium:
                raise http.HttpError(403, '{"error": {"status": 403, "reason": "PREMIUM_REQUIRED"}}')
            return None
        if url.endswith("/currently-playing"):
            return {"item": {"name": "Let You Down", "artists": [{"name": "NF"}], "uri": "spotify:track:1"}}
        return None


@pytest.fixture
def connected():
    secrets.set_many({"spotify_refresh_token": "r1", "spotify_access_token": "old",
                      "spotify_expires_at": str(time.time() + 1000)})
    yield
    secrets.path().unlink(missing_ok=True)


def test_spotify_play(connected):
    api = FakeSpotifyApi()
    spotify = sp.Spotify(lambda: "client123", api, sleep=lambda s: None)
    track = spotify.play("let you down nf")
    assert (track.name, track.artist) == ("Let You Down", "NF")
    put = [c for c in api.calls if c[0] == "PUT"][0]
    assert put[2] == {"device_id": "pc1"} and put[4] == {"uris": ["spotify:track:1"]} and put[5] == "Bearer old"
    assert spotify.now_playing().name == "Let You Down"


def test_spotify_needs_premium(connected):
    spotify = sp.Spotify(lambda: "client123", FakeSpotifyApi(premium=False), sleep=lambda s: None)
    with pytest.raises(sp.PremiumRequired):
        spotify.play("anything")


def test_spotify_opens_app_when_no_device(connected):
    api = FakeSpotifyApi(devices=[])
    launched = []

    def launch():
        launched.append(1)
        api.devices = [{"id": "pc9", "type": "Computer", "is_active": True}]
    spotify = sp.Spotify(lambda: "c", api, launch_app=launch, sleep=lambda s: None)
    spotify.play("x")
    assert launched == [1] and [c for c in api.calls if c[0] == "PUT"][0][2] == {"device_id": "pc9"}


def test_spotify_refreshes_expired_token(connected):
    secrets.set_many({"spotify_expires_at": "0"})
    api = FakeSpotifyApi()
    sp.Spotify(lambda: "client123", api, sleep=lambda s: None).search("x")
    assert api.calls[0][1] == sp.TOKEN_URL and api.calls[0][3]["grant_type"] == "refresh_token"
    assert api.calls[1][5] == "Bearer fresh"


def test_spotify_not_connected():
    secrets.path().unlink(missing_ok=True)
    with pytest.raises(sp.NotConnected):
        sp.Spotify(lambda: "c", FakeSpotifyApi()).search("x")


def test_spotify_connect_pkce_flow():
    secrets.path().unlink(missing_ok=True)
    api = FakeSpotifyApi()
    seen = {}

    def browser(url):           # plays the part of the user approving in the browser
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        seen.update(q)
        cb = f"{q['redirect_uri']}?code=abc&state={q['state']}"
        threading.Thread(target=lambda: urllib.request.urlopen(cb, timeout=5).read(), daemon=True).start()

    spotify = sp.Spotify(lambda: "client123", api, open_url=browser)
    spotify.connect(timeout=10)
    assert seen["code_challenge_method"] == "S256" and seen["client_id"] == "client123"
    token_call = api.calls[-1]
    assert token_call[3]["code"] == "abc" and token_call[3]["code_verifier"]
    assert spotify.connected and secrets.get("spotify_refresh_token") == "r2"
    spotify.disconnect()
    assert not spotify.connected


# -- router: music, weather, AI ----------------------------------------------------------------------------------
class FakeSpotify:
    def __init__(self, connected=True, error=None):
        self.connected, self.error, self.calls = connected, error, []

    def play(self, query, artist=""):
        self.calls.append(("play", query, artist))
        if self.error:
            raise self.error
        return sp.Track("Let You Down", "NF", "spotify:track:1")

    def pause(self):
        self.calls.append(("pause",))

    def resume(self):
        self.calls.append(("resume",))

    def next(self):
        self.calls.append(("next",))

    def previous(self):
        self.calls.append(("previous",))

    def now_playing(self):
        return sp.Track("Let You Down", "NF", "u")


class FakeBrain:
    def __init__(self, reply):
        self.reply, self.asked = reply, []

    def ask(self, text):
        self.asked.append(text)
        return self.reply


def rig(**services):
    controller = CompanionController()
    service = VoiceService(True, False, "", 0.8)
    service.listen_now = lambda *a: None
    speaker = FakeSpeaker()
    assistant = Assistant(controller, services.pop("settings", Settings(slang=False)), service, speaker)
    system = FakeSystem([ProcessInfo(10, "Discord.exe")])
    keys = []
    router = CommandRouter(assistant, FakeCompanion(), make_catalog(), system,
                           Services(settings=assistant.settings, media_key=keys.append, **services))
    assistant.command_handler = router.handle
    return controller, service, system, speaker, keys, router


def test_play_song_on_spotify_without_talking_over_it():
    fake = FakeSpotify()
    controller, service, system, speaker, keys, router = rig(spotify=fake)
    service.command.emit("play let you down by nf")
    assert settle(3, lambda: controller.state is State.SUCCESS)
    assert fake.calls == [("play", "let you down", "nf")]          # song and artist, searched separately
    assert controller.message == "Playing Let You Down by NF." and speaker.lines == []


def test_play_without_spotify_connection_opens_search():
    controller, service, system, speaker, keys, router = rig(spotify=FakeSpotify(connected=False))
    system.procs[20] = ProcessInfo(20, "Spotify.exe")          # already running (v1.4 tests cover starting it)
    service.command.emit("play let you down by nf")
    assert system.calls == [("open", "spotify:search:let%20you%20down%20nf")]
    assert controller.message == "Pulled up let you down by nf in Spotify. Hit play."


def test_play_without_premium_falls_back_to_search():
    fake = FakeSpotify(error=sp.PremiumRequired("Premium"))
    controller, service, system, speaker, keys, router = rig(spotify=fake)
    system.procs[20] = ProcessInfo(20, "Spotify.exe")
    service.command.emit("play blinding lights")
    assert settle(3, lambda: system.calls)
    assert system.calls[0][1].startswith("spotify:search:blinding")


def test_play_a_game_launches_it():
    controller, service, system, speaker, keys, router = rig(spotify=FakeSpotify())
    service.command.emit("play deadlock")
    assert ("open", "steam://rungameid/1422450") in system.calls


def test_media_controls():
    fake = FakeSpotify()
    controller, service, system, speaker, keys, router = rig(spotify=fake)
    service.command.emit("pause the music")
    assert settle(3, lambda: fake.calls == [("pause",)])
    controller2, service2, system2, speaker2, keys2, router2 = rig(spotify=FakeSpotify(connected=False))
    service2.command.emit("next song")
    service2.command.emit("turn it up")
    assert keys2 == ["next", "volume_up"] and speaker2.lines == []


def test_weather_needs_a_city_then_reports():
    w = Weather("metric", fake_fetch([]))
    controller, service, system, speaker, keys, router = rig(weather=w)
    service.command.emit("whats the weather")
    assert controller.message == "Tell me your city first, in Settings."
    router.services.settings.weather_city = "Manchester"
    service.command.emit("whats the weather tomorrow")
    assert settle(3, lambda: controller.state is State.SUCCESS)
    assert controller.message.startswith("Tomorrow in Manchester")
    assert speaker.lines[-1] == controller.message            # she says it out loud


def test_unknown_without_ai():
    controller, service, system, speaker, keys, router = rig()
    service.command.emit("teach me quantum physics")
    assert controller.state is State.SPEAKING and controller.message      # 1.17: her chatbot always replies
    assert controller.message != "Not sure what you mean."


def test_ai_answers_in_her_voice():
    brain = FakeBrain(claude.AIReply("Why did the netrunner cross the road? To jack the other side."))
    controller, service, system, speaker, keys, router = rig(settings=Settings(ai_enabled=True, slang=False), brain=brain)
    service.command.emit("tell me a joke")
    assert settle(3, lambda: controller.state is State.SPEAKING)
    assert brain.asked == ["tell me a joke"] and "netrunner" in speaker.lines[-1]


def test_ai_action_goes_through_the_router():
    brain = FakeBrain(claude.AIReply("", Intent(Kind.OPEN, ("blocks strap",))))
    controller, service, system, speaker, keys, router = rig(settings=Settings(ai_enabled=True, slang=False), brain=brain)
    service.command.emit("fire up my favourite launcher thingy")  # not an app name -> the AI works it out
    assert settle(3, lambda: system.calls)
    assert brain.asked == ["fire up my favourite launcher thingy"]
    assert system.calls == [("program", r"C:\bx\Bloxstrap.exe", ())]   # same catalog, same launcher


def test_ai_suggestion_that_doesnt_exist_doesnt_loop():
    brain = FakeBrain(claude.AIReply("", Intent(Kind.OPEN, ("photoshop",))))
    controller, service, system, speaker, keys, router = rig(settings=Settings(ai_enabled=True, slang=False), brain=brain)
    service.command.emit("open my picture editor")
    assert settle(3, lambda: controller.state is State.ERROR)
    assert brain.asked == ["open my picture editor"] and controller.message == "Couldn't find photoshop."


def test_ai_cannot_invent_actions():
    assert to_intent("run_shell", {"cmd": "del C:\\"}) is None
    assert to_intent("control_music", {"action": "format_disk"}) is None
    assert to_intent("set_display", {"option": "explode"}) is None
    assert to_intent("open_app", {"names": []}) is None
    assert to_intent("open_app", {"names": ["Discord"]}) == Intent(Kind.OPEN, ("Discord",))


# -- ClaudeBrain with a fake Anthropic client -----------------------------------------------------------------------
def text_block(t):
    return SimpleNamespace(type="text", text=t)


def tool_block(id_, name, inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


class FakeClient:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        import copy
        self.requests.append(copy.deepcopy(kwargs))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def reply(*blocks, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


def brain_with(responses, info=None, clock=None):
    client = FakeClient(responses)
    b = ClaudeBrain(lambda: "sk-test", info or {}, client_factory=lambda key: client,
                    **({"clock": clock} if clock else {}))
    return b, client


def test_brain_request_shape():
    b, client = brain_with([reply(text_block("Hey."))])
    assert b.ask("hi").text == "Hey."
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert req["output_config"] == {"effort": "low"} and req["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in req and "temperature" not in req
    assert all(t["strict"] and t["input_schema"]["additionalProperties"] is False for t in req["tools"])
    assert req["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


def test_brain_info_tool_loop():
    b, client = brain_with([reply(tool_block("t1", "get_weather", {"place": "", "day": "today"}), stop="tool_use"),
                            reply(text_block("Rainy. Classic."))],
                           info={"get_weather": lambda a: "Manchester: 14 and light rain"})
    assert b.ask("should i bring a coat").text == "Rainy. Classic."
    second = client.requests[1]["messages"]
    assert second[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "t1",
                                        "content": "Manchester: 14 and light rain", "is_error": False}


def test_brain_action_becomes_intent_and_history_stays_valid():
    b, client = brain_with([reply(text_block("On it."), tool_block("t1", "close_app", {"names": ["Discord"]}),
                                  stop="tool_use"),
                            reply(text_block("You're welcome."))])
    r = b.ask("get rid of discord")
    assert r.intent == Intent(Kind.CLOSE, ("Discord",))
    b.ask("thanks")
    msgs = client.requests[1]["messages"]
    # the tool result is answered at the start of the next user turn (append-only history)
    assert msgs[-1]["role"] == "user" and msgs[-1]["content"][0]["tool_use_id"] == "t1"
    assert msgs[-1]["content"][-1] == {"type": "text", "text": "thanks"}
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]


def test_brain_refusal_and_errors():
    import anthropic
    import httpx2
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    b, client = brain_with([reply(stop="refusal"),
                            anthropic.AuthenticationError("bad", response=httpx2.Response(401, request=req), body=None),
                            anthropic.APIConnectionError(request=req)])
    assert b.ask("x").text == "Not touching that one."
    assert "key" in b.ask("y").text
    assert b.ask("z").text == "Can't reach the AI right now." and b.messages == []


def test_brain_forgets_after_idle():
    now = [0.0]
    b, client = brain_with([reply(text_block("a")), reply(text_block("b"))], clock=lambda: now[0])
    b.ask("one")
    now[0] += claude.CONVERSATION_IDLE + 1
    b.ask("two")
    assert len(client.requests[1]["messages"]) == 1


# -- animation --------------------------------------------------------------------------------------------------
def test_character_mouth_follows_voice():
    from capri.app import asset_root
    from capri.ui.art import CharacterArt
    from capri.ui.character_window import CharacterWindow
    w = CharacterWindow(CharacterArt.load(asset_root() / "capri"), 190)
    w.set_talking(True)
    poses = []
    for level in (0.1, 0.7, 0.6, 0.35, 0.2, 0.9):
        w.set_voice_level(level)
        poses.append(w.pose_name())
    assert poses == ["idle", "speaking", "speaking", "speaking", "idle", "speaking"]   # with hysteresis
    w.set_talking(False)
    assert w.pose_name() == "idle" and w.level == 0


def test_panel_typewriter_and_bars():
    from capri.ui.status_panel import StatusPanel
    from PySide6.QtGui import QImage
    c = CompanionController()
    c.set_state(State.SPEAKING, "Why did the netrunner cross the road? To jack the other side, obviously. "
                                "Then she fell asleep on the keyboard and woke up in someone else's fridge.")
    panel = StatusPanel(c, QImage(8, 8, QImage.Format.Format_ARGB32))
    assert len(panel._title_lines) > 2                 # long AI answers get more lines
    panel.set_talking(True)
    assert panel.reveal == 0.0
    panel.set_progress(0.5)
    assert 0.5 < panel.reveal < 0.6
    panel.set_talking(False)
    assert panel.reveal == 1.0


# -- Night City slang ------------------------------------------------------------------------------
def test_slang_lines():
    import random as rnd
    from capri import lines
    text, emotion = lines.line("not_found", True, rnd.Random(1), thing="photoshop")
    assert "photoshop" in text and emotion == "confused"
    assert any(w in text.lower() for w in ("choom", "gonk", "rig"))
    assert lines.line("not_found", False, thing="photoshop") == ("Couldn't find photoshop.", "confused")
    for key, (emo, plain, variants) in lines.LINES.items():   # every variant formats with the same fields
        fields = {f: "X" for f in ("name", "names", "thing", "query", "time", "date", "track", "artist",
                                          "where", "label", "side", "service", "style", "what", "What")}
        assert plain.format(**fields) and all(v.format(**fields) for v in variants), key
        assert emo in __import__("capri.emotions", fromlist=["EMOTIONS"]).EMOTIONS, key


def test_router_talks_like_night_city():
    controller, service, system, speaker, keys, router = rig(settings=Settings(slang=True))
    service.command.emit("open blocks strap")
    assert "Bloxstrap" in controller.message
    service.command.emit("open photoshop")
    assert "photoshop" in controller.message and controller.message != "Couldn't find photoshop."
    assert controller.emotion == "confused"


def test_ai_gets_slang_instructions_only_when_on():
    from capri.lines import SLANG_PROMPT
    for on in (True, False):
        b, client = brain_with([reply(text_block("[playful] Preem."))])
        b._slang = lambda on=on: on
        b.ask("hi")
        assert (SLANG_PROMPT in client.requests[0]["system"]) is on
