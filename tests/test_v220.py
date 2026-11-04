"""v2.2: AI 400s fixed for good (every error shape, vision models), screen reading that works, Fish Audio as it
sounds on the site, the music bar's pause button, her tools (windows, one app's volume, lag, internet, her own
settings, timers), she vibes to music, a crash is reported once, and she learns from her game mistakes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ai.claude import AIReply  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations import http  # noqa: E402


# -- AI errors: the service's own words, whatever shape -----------------------------------------------------------
@pytest.mark.parametrize("body,said", [
    ('{"error": {"message": "Unknown field max_tokens"}}', "Unknown field max_tokens"),
    ('[{"error": {"code": 400, "message": "Invalid value at messages"}}]', "Invalid value at messages"),
    ('{"type": "about:blank", "status": 400, "title": "Bad Request", "detail": "Inference error: image not '
     'supported"}', "Inference error: image not supported"),
    ('{"detail": [{"loc": ["body", "messages"], "msg": "field required"}]}', "field required"),
    ('{"error": "model is required"}', "model is required"),
    ('{"status": 400, "title": "Bad Request"}', "Bad Request"),
])
def test_every_error_shape_is_read(body, said):
    from capri.ai.openai_compat import OpenAIBrain
    assert OpenAIBrain._detail(http.HttpError(400, body)) == said


def brain(preset, fetch, model=""):
    from capri.ai.openai_compat import OpenAIBrain
    return OpenAIBrain(lambda: preset, lambda: "", lambda: model, lambda: "key", {}, fetch=fetch)


def test_what_do_you_see_switches_to_a_model_that_can_see():
    """NVIDIA's default chat model is text-only: she looks with its vision model instead, and remembers it."""
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        sent.append(json_body)
        if json_body["model"] == "meta/llama-3.3-70b-instruct":
            raise http.HttpError(400, '{"status": 400, "title": "Bad Request", "detail": "Image input is not '
                                      'supported by this model"}')
        return {"choices": [{"message": {"content": "[playful] A creeper. Run."}}]}
    b = brain("nvidia", fetch)
    reply = b.look("what do you see", "QUJD")
    assert not reply.error and reply.text == "A creeper. Run." and reply.emotion == "playful"
    assert sent[1]["model"] == "meta/llama-4-maverick-17b-128e-instruct"
    b.look("and now?", "QUJD")
    assert sent[2]["model"] == "meta/llama-4-maverick-17b-128e-instruct"          # straight to the one that works


def test_nvidia_also_gets_its_inline_picture_format():
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        sent.append(json_body)
        if isinstance(json_body["messages"][1]["content"], list):
            raise http.HttpError(400, '{"detail": "Input should be a valid string"}')
        return {"choices": [{"message": {"content": "Looks like Fortnite."}}]}
    reply = brain("nvidia", fetch).look("what do you see", "QUJD")
    assert reply.text == "Looks like Fortnite."
    assert '<img src="data:image/jpeg;base64,QUJD" />' in sent[-1]["messages"][1]["content"]


def test_a_refused_look_says_the_real_reason_not_just_400():
    def fetch(method, url, json_body=None, headers=None, timeout=None):
        raise http.HttpError(400, '{"error": {"message": "Request too large for this tier"}}')
    reply = brain("groq", fetch).look("what do you see", "QUJD")
    assert reply.error and "Request too large" in reply.text and "400" in reply.text


def test_chat_drops_an_option_the_service_wont_take_even_unnamed():
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        sent.append(dict(json_body))
        if "max_tokens" in json_body:
            raise http.HttpError(400, '{"detail": "Bad Request"}')
        return {"choices": [{"message": {"content": "Hey."}}]}
    b = brain("nvidia", fetch)
    assert b.ask("hi").text == "Hey." and "max_tokens" not in sent[-1]
    assert b.ask("again").text == "Hey." and "max_tokens" not in sent[-1]           # remembered


def test_big_pictures_are_shrunk_for_nvidia():
    from capri.ai.openai_compat import small_jpeg
    from capri.integrations.screen_watch import to_jpeg_b64
    img = QImage(1280, 720, QImage.Format.Format_RGB32)
    for y in range(0, 720, 3):
        for x in range(0, 1280, 3):
            img.setPixelColor(x, y, QColor((x * 7) % 255, (y * 13) % 255, (x * y) % 255))
    big = to_jpeg_b64(img, 1280, 95)
    small = small_jpeg(big, 60_000)
    assert len(big) > 60_000 and len(small) <= 60_000


# -- screen reading ---------------------------------------------------------------------------------------------------
def test_a_black_screenshot_is_retried_with_the_window_then_explained():
    from capri.integrations.screen_watch import BLACK_SCREEN, ScreenWatch, is_blank
    black = QImage(800, 600, QImage.Format.Format_RGB32)
    black.fill(QColor(0, 0, 0))
    seen = QImage(800, 600, QImage.Format.Format_RGB32)
    seen.fill(QColor(30, 120, 200))
    seen.setPixelColor(10, 10, QColor(255, 255, 255))
    assert is_blank(black) and not is_blank(seen)
    asked = []
    look_brain = SimpleNamespace(look=lambda prompt, jpeg: asked.append(jpeg) or AIReply("A blue screen."))
    s = SimpleNamespace(watch_screen=True, watch_every=60, watch_remember=False)
    answers = []
    w = ScreenWatch(s, look_brain, lambda: black, lambda: "Game", lambda *a: None, background=False,
                    grab_window=lambda: seen)
    w.ask("what do you see", lambda text, emotion: answers.append(text))
    assert answers == ["A blue screen."] and asked                                 # the window, not black
    w = ScreenWatch(s, look_brain, lambda: black, lambda: "Game", lambda *a: None, background=False,
                    grab_window=lambda: black)
    w.ask("what do you see", lambda text, emotion: answers.append(text))
    assert answers[-1] == BLACK_SCREEN                                             # never a black picture to the AI


# -- Fish Audio -------------------------------------------------------------------------------------------------------
def test_fish_audio_asks_for_full_quality_at_its_natural_speed():
    import io
    import wave
    from capri.speech.engines import FishAudioEngine, fish_speed
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x10" * 4410)
    sent = []
    FishAudioEngine.key = staticmethod(lambda: "k")
    FishAudioEngine.voice_id = staticmethod(lambda: "https://fish.audio/m/abc123/")
    try:
        audio = FishAudioEngine(fetch=lambda url, body, headers: sent.append(body) or buf.getvalue()).synthesize(
            "Hey choom.", "fish: your Fish Audio voice", 0.6)
    finally:
        FishAudioEngine.key = staticmethod(lambda: "")
        FishAudioEngine.voice_id = staticmethod(lambda: "")
    body = sent[0]
    assert body["latency"] == "normal" and body["prosody"]["speed"] == 1.0 and body["reference_id"] == "abc123"
    assert audio.rate == 44100 and audio.as_is
    assert fish_speed(0.0) == 0.8 and fish_speed(1.0) == 1.2


def test_online_voices_keep_a_steady_speed_whatever_her_mood():
    import numpy as np
    from capri.settings import Settings
    from capri.speech.engines import Audio
    from capri.speech.speaker import MASTER_GAIN, Speaker
    speeds, gains = [], []

    class Box:
        last = ("fish: your Fish Audio voice", "")

        def synthesize(self, text, voice, speed, pitch):
            speeds.append(speed)
            return Audio(np.full(2205, 0.5, np.float32), 22050, pitched=True, natural=True, as_is=True)

        def voices(self):
            return ["fish: your Fish Audio voice"]
    s = Settings(speech_voice="fish: your Fish Audio voice", speech_speed=0.6, speech_volume=1.0)
    sp = Speaker(s, Box, player=lambda samples, rate: gains.append(float(samples.max())) or (lambda: None),
                 sleep=lambda t: None)
    sp.ready.wait(5)
    sp._speak("Woo!", emotion="excited")
    sp._speak("Oh.", emotion="sad")
    assert speeds == [0.6, 0.6] and gains[0] == pytest.approx(gains[1]) == pytest.approx(0.5 * MASTER_GAIN)
    sp.shutdown()


# -- the music bar's play / pause ---------------------------------------------------------------------------------------
def test_pause_on_her_bar_flips_at_once_and_the_bar_stays():
    from capri.ui import music_deck as md
    from test_v111 import companion
    t = [100.0]
    deck = md.MusicDeck()
    vibing = []
    keeper = md.DeckKeeper(deck, companion(), lambda: "A - B", lambda: True, clock=lambda: t[0], groove=vibing.append)
    keeper.music_changed(True)
    assert deck.playing and vibing[-1] is True
    deck.pressed.emit("play_pause")
    assert not deck.playing and vibing[-1] is False                     # pause symbol -> play symbol, right away
    keeper.tick()
    assert not deck.playing                                             # the music check hasn't noticed yet: still paused
    keeper.music_changed(False)
    t[0] += md.LINGER + 5
    keeper.tick()
    assert deck.isVisible()                                             # paused with her button: the bar waits for you
    deck.pressed.emit("play_pause")
    assert deck.playing


# -- her tools ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said,kind,targets,query", [
    ("put chrome on the left and discord on the right", Kind.ARRANGE, ("chrome", "discord"), "left,right"),
    ("put spotify on the right", Kind.ARRANGE, ("spotify",), "right"),
    ("snap this to the left", Kind.ARRANGE, ("",), "left"),
    ("maximize steam", Kind.ARRANGE, ("steam",), "maximize"),
    ("put chrome and discord side by side", Kind.ARRANGE, ("chrome", "discord"), "side_by_side"),
    ("turn discord down", Kind.APP_VOLUME, ("discord",), "down"),
    ("make spotify louder", Kind.APP_VOLUME, ("spotify",), "up"),
    ("set chrome to 30 percent", Kind.APP_VOLUME, ("chrome",), "set:30"),
    ("why is my game lagging", Kind.PC_INFO, (), "lag"),
    ("my fps is so low", Kind.PC_INFO, (), "lag"),
    ("how is my internet", Kind.PC_INFO, (), "internet"),
    ("run a speed test", Kind.PC_INFO, (), "internet"),
])
def test_her_tools_by_voice(said, kind, targets, query):
    got = parse(said)
    assert got.kind == kind and got.targets == targets and got.query == query, got


@pytest.mark.parametrize("said,kind", [("turn it down", Kind.MEDIA), ("turn the music down", Kind.MEDIA),
                                       ("mute discord", Kind.DISCORD), ("make yourself bigger", Kind.SIZE),
                                       ("move the drone to the left", Kind.DRONE_CORNER),
                                       ("go to the bottom left", Kind.MOVE)])
def test_old_commands_still_mean_what_they_did(said, kind):
    assert parse(said).kind == kind


def test_window_layouts():
    from capri.integrations.her_tools import layout_rects
    work = (0, 0, 1920, 1040)
    assert layout_rects(work, "left") == [(0, 0, 960, 1040)]
    assert layout_rects(work, "right") == [(960, 0, 960, 1040)]
    assert layout_rects(work, "top_right") == [(960, 0, 960, 520)]
    assert layout_rects(work, "side_by_side", 3) == [(0, 0, 640, 1040), (640, 0, 640, 1040), (1280, 0, 640, 1040)]
    assert layout_rects((100, 50, 1100, 850), "maximize") == [(100, 50, 1000, 800)]


def test_one_apps_volume_on_linux_uses_only_its_own_stream():
    from capri.integrations import her_tools
    listing = ('Sink Input #12\n\tVolume: front-left: 52428 /  80% / -5 dB\n\t\tapplication.name = "Discord"\n'
               'Sink Input #13\n\tVolume: front-left: 65536 / 100%\n\t\tapplication.name = "Firefox"\n')
    ran = []

    def run(argv, **kw):
        ran.append(argv)
        return SimpleNamespace(stdout=listing if argv[:2] == ["pactl", "list"] else "")
    import shutil
    real = shutil.which
    shutil.which = lambda name: "/usr/bin/pactl" if name == "pactl" else real(name)
    try:
        changed, level = her_tools._pulse_app_volume({"discord"}, "down", 0, run=run)
    finally:
        shutil.which = real
    assert changed == ["Discord"] and level == 53
    assert ["pactl", "set-sink-input-volume", "12", "53%"] in ran
    assert not any("13" in a for a in ran if a[:2] != ["pactl", "list"])         # Firefox untouched
    assert her_tools.new_level(50, "set", 120) == 100 and her_tools.new_level(5, "down", 0) == 0


def test_lag_report_names_the_likely_cause():
    from capri.integrations import her_tools
    procs = [SimpleNamespace(pid=i, info={"name": n}, cpu_percent=lambda _=None, v=v: v)
             for i, (n, v) in enumerate([("chrome.exe", 640.0), ("game.exe", 120.0)], start=10)]
    ps = SimpleNamespace(
        process_iter=lambda attrs=None: procs, cpu_percent=lambda _=None: 97.0, cpu_count=lambda: 8,
        virtual_memory=lambda: SimpleNamespace(total=16e9, available=8e9),
        disk_io_counters=lambda: SimpleNamespace(busy_time=0), sensors_temperatures=lambda: {})
    text = her_tools.lag_report(ps, sleep=lambda s: None, run=lambda *a, **k: SimpleNamespace(stdout=""),
                                ping=lambda: {"ms": 30.0, "jitter": 5.0, "lost": 0})
    assert text.startswith("Most likely your CPU is maxed out (97%)") and "Chrome" in text and "ping 30 ms" in text


def test_internet_report():
    from capri.integrations import her_tools
    clock = iter([0.0, 0.025, 1.0, 1.030, 2.0, 2.020, 3.0, 3.028])
    p = her_tools.ping(4, connect=lambda addr: None, clock=lambda: next(clock))
    assert 20 <= p["ms"] <= 30 and p["lost"] == 0
    assert her_tools.internet_report(lambda: p, lambda: 240.0).startswith("Your ping is")
    assert "240 Mbps" in her_tools.internet_report(lambda: p, lambda: 240.0)
    assert "offline" in her_tools.internet_report(lambda: {"offline": True}, lambda: 0.0)


def test_her_tools_for_the_ai():
    from capri.ai.claude import TOOLS, to_intent
    names = {t["name"] for t in TOOLS}
    assert {"arrange_windows", "set_app_volume", "set_timer", "change_setting"} <= names
    assert to_intent("arrange_windows", {"apps": ["Chrome", "Discord"], "layouts": ["left", "right"]}) == \
        parse("put chrome on the left and discord on the right").__class__(Kind.ARRANGE, ("Chrome", "Discord"),
                                                                           query="left,right")
    assert to_intent("set_app_volume", {"app": "Discord", "action": "set", "percent": 30}).query == "set:30"
    assert to_intent("set_timer", {"minutes": 5, "label": "pizza"}).targets == ("300", "pizza")
    assert to_intent("change_setting", {"setting": "text_box", "value": "Name"}).query == "name"
    assert to_intent("change_setting", {"setting": "api_key", "value": "x"}) is None    # only her own safe settings


def test_she_changes_her_own_text_box_setting():
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    from capri.commands.parser import Intent
    r.router.dispatch(Intent(Kind.SETTING, ("text_box",), query="name"))
    s = r.router.services.settings
    assert s.panel_popup and s.panel_on_name and s.show_panel


# -- she vibes to music -------------------------------------------------------------------------------------------------
def test_she_vibes_while_music_plays():
    from test_v111 import companion
    ch = companion().character
    ch.set_grooving(True)
    for _ in range(40):
        ch._tick()
        ch._groove = min(1.0, ch._groove + 0.05)
    assert ch._special() and ch._groove > 0.9
    moves = ch.groove_moves(12.3)
    assert set(moves) >= {"squat", "lean", "stride", "energy"}
    ch.set_grooving(False)
    ch._groove = 0.0
    assert ch.groove_moves(12.3) == {}


# -- a crash is mentioned once ---------------------------------------------------------------------------------------------
def test_a_crash_is_reported_once(tmp_path):
    from capri import logs
    crash = tmp_path / "crash.log"
    crash.write_text("Fatal Python error: Segmentation fault\n  File \"vosk\", line 1\n", encoding="utf-8")
    assert "Segmentation fault" in logs._unreported_crash(crash)
    assert logs._unreported_crash(crash) == ""                         # told: not again
    with open(crash, "a", encoding="utf-8") as f:
        f.write("Fatal Python error: Aborted\n")
    assert logs._unreported_crash(crash).startswith("Fatal Python error: Aborted")


# -- learning from her game mistakes ------------------------------------------------------------------------------------
def test_she_remembers_lessons_per_game_and_uses_them(tmp_path):
    from capri.integrations import game_agent as ga
    from test_game_agent import Brain, Hands
    lessons = ga.GameLessons(tmp_path / "lessons.json")
    plans = [AIReply(json.dumps({"say": "", "do": [{"key": "w", "hold": 0.5}], "done": False,
                                 "lesson": "Close the left door when Bonnie shows up at it"})),
             AIReply(json.dumps({"say": "", "do": [{"key": "a", "hold": 0.2}], "done": True}))]
    brain = Brain(*plans)
    window = ga.Rect(0, 0, 800, 600)
    done = []
    a = ga.GameAgent(brain, lambda: Hands(), lambda r: object(), lambda: 7, lambda h: window, lambda s: None,
                     done.append, sleep=lambda s: None, jpeg=lambda img: "QUJD",
                     title=lambda h: "Five Nights at Freddy's - v1.13", lessons=lessons)
    a.start("survive the night", background=False)
    assert lessons.lessons("five nights at freddy's") == ["Close the left door when Bonnie shows up at it"]
    assert ga.GameLessons(tmp_path / "lessons.json").lessons("five nights at freddy's")      # kept on disk
    brain2 = Brain(AIReply(json.dumps({"say": "", "do": [], "done": True})))
    b = ga.GameAgent(brain2, lambda: Hands(), lambda r: object(), lambda: 7, lambda h: window, lambda s: None,
                     done.append, sleep=lambda s: None, jpeg=lambda img: "QUJD",
                     title=lambda h: "Five Nights at Freddy's", lessons=ga.GameLessons(tmp_path / "lessons.json"))
    b.start("survive", background=False)
    assert "Close the left door when Bonnie shows up" in brain2.prompts[0]        # next time, she knows
    assert not lessons.add("five nights at freddy's", "Close the left door when Bonnie shows up at it!")


def test_after_handing_back_she_thinks_it_over(tmp_path):
    from capri.integrations import game_agent as ga
    from test_game_agent import Brain, Hands
    lessons = ga.GameLessons(tmp_path / "lessons.json")
    moves = [AIReply(json.dumps({"say": "", "do": [{"key": "w", "hold": 0.2}], "done": False}))] * 3
    brain = Brain(*moves, AIReply("Check the cameras before Foxy runs."))
    hands = Hands(escape_after=3)
    a = ga.GameAgent(brain, lambda: hands, lambda r: object(), lambda: 7, lambda h: ga.Rect(0, 0, 800, 600),
                     lambda s: None, lambda why: None, sleep=lambda s: None, jpeg=lambda img: "QUJD",
                     title=lambda h: "FNAF", lessons=lessons)
    a.start("survive", background=False)
    assert lessons.lessons("fnaf") == ["Check the cameras before Foxy runs."]
    assert lessons.games["fnaf"]["tries"] == 1 and lessons.games["fnaf"]["last"] == "escape"
