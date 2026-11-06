"""v2.3: her languages - the 25 that Parakeet v3 hears: hearing, the everyday commands, her voice, her lines."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri import languages  # noqa: E402
from capri.ai.claude import AIReply  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402


@pytest.fixture(autouse=True)
def back_to_english():
    yield
    languages.set_current("en")


def test_twenty_five_languages():
    assert len(languages.LANGUAGES) == 25 and "en" in languages.LANGUAGES
    assert set(languages.COMMANDS) == set(languages.LANGUAGES) - {"en"}       # every other one has its commands
    assert languages.find("German") == "de" and languages.find("deutsch") == "de" and languages.find("xx") == ""


@pytest.mark.parametrize("code,said,kind,what", [
    ("de", "öffne discord", Kind.OPEN, "discord"), ("de", "wie spät ist es", Kind.TIME, ""),
    ("de", "lauter", Kind.MEDIA, "volume_up"), ("fr", "ouvre spotify", Kind.OPEN, "spotify"),
    ("fr", "mets en pause", Kind.MEDIA, "pause"), ("es", "abre el chrome", Kind.OPEN, "chrome"),
    ("es", "siguiente canción", Kind.MEDIA, "next"), ("it", "chiudi discord", Kind.CLOSE, "discord"),
    ("pt", "que horas são", Kind.TIME, ""), ("pl", "otwórz steam", Kind.OPEN, "steam"),
    ("nl", "hoe laat is het", Kind.TIME, ""), ("sv", "öppna spotify", Kind.OPEN, "spotify"),
    ("uk", "голосніше", Kind.MEDIA, "volume_up"), ("el", "άνοιξε spotify", Kind.OPEN, "spotify"),
    ("cs", "kolik je hodin", Kind.TIME, ""), ("fi", "avaa steam", Kind.OPEN, "steam"),
])
def test_everyday_commands_in_her_languages(code, said, kind, what):
    got = parse(languages.to_english(said, code))
    assert got.kind == kind and (not what or got.query == what or what in got.targets), (said, got)


def test_cyrillic_app_names_become_latin_for_her_app_matching():
    assert languages.to_english("открой дискорд", "ru") == "open diskord"
    assert languages.to_english("was geht ab", "de") == "was geht ab"                 # not a command: as it was


def test_the_ai_is_told_to_answer_in_your_language():
    from capri.ai.claude import system_prompt
    assert "Always reply in" not in system_prompt(False)
    languages.set_current("de")
    assert "Always reply in German (Deutsch)" in system_prompt(False)


def test_switch_language_by_voice():
    assert parse("speak german").targets == ("de",) and parse("switch to french").targets == ("fr",)
    assert parse("talk to me in spanish").kind == Kind.LANGUAGE and parse("speak up").kind == Kind.VOICE


# -- hearing -----------------------------------------------------------------------------------------------------------
def test_parakeet_v3_for_other_languages(tmp_path, monkeypatch):
    from capri.voice import parakeet
    assert parakeet.model_name("en") == parakeet.MODEL_NAME and parakeet.model_name("de") == parakeet.MULTI_NAME
    assert parakeet.model_mb("fr") == parakeet.MULTI_MB
    monkeypatch.setattr(parakeet, "user_models_dir", lambda: tmp_path)
    monkeypatch.setattr(parakeet, "MODELS_DIR", tmp_path / "none")
    multi = tmp_path / parakeet.MULTI_NAME
    multi.mkdir()
    for f in parakeet.FILES:
        (multi / f).write_text("x")
    assert parakeet.find_model("de") == multi and parakeet.find_model("en") == multi   # v3 hears English too
    (tmp_path / parakeet.MULTI_NAME / "tokens.txt").unlink()
    assert parakeet.find_model("de") is None


def test_in_another_language_parakeet_hears_even_what_vosk_couldnt():
    from fake_vosk import RATE, FakeRecognizer, speak
    from capri.voice.wakeword import Command, NoCommand, WakeWordListener

    class DeafToGerman(FakeRecognizer):                # Vosk (English) makes out no words in German
        def Result(self):
            super().Result()
            return '{"result": [], "text": ""}'

        def PartialResult(self):
            return '{"partial": ""}'

        def FinalResult(self):
            super().FinalResult()
            return '{"text": ""}'
    t = [0.0]
    listener = WakeWordListener(lambda r: FakeRecognizer(r, True), lambda r: DeafToGerman(r, False), RATE, 0.8,
                                clock=lambda: t[0])
    listener.any_language = True
    events = []
    for chunk in speak("hey", "capri", 0.8, "open", "discord", 9.0):
        t[0] += 0.1
        events += listener.feed(chunk)
    commands = [e for e in events if isinstance(e, Command)]
    assert commands and commands[0].text == "" and commands[0].audio                  # handed to Parakeet
    listener.any_language = False
    events = []
    for chunk in speak("hey", "capri", 0.8, "open", "discord", 9.0):
        t[0] += 0.1
        events += listener.feed(chunk)
    assert any(isinstance(e, NoCommand) for e in events) and not any(isinstance(e, Command) for e in events)


def test_nothing_heard_by_either_is_no_command():
    from capri.voice.service import VoiceService
    from capri.voice.wakeword import Command
    s = VoiceService(False, True, "", 0.8)
    got = []
    s.no_command.connect(lambda: got.append("none"))
    s.command.connect(lambda text: got.append(text))
    s._refined(lambda audio, rate: "", Command("", (), b"\0\0" * 8000))
    s._refined(lambda audio, rate: "öffne discord", Command("", (), b"\0\0" * 8000))
    assert got == ["none", "öffne discord"]


# -- speaking ----------------------------------------------------------------------------------------------------------
def test_a_voice_that_speaks_your_language_is_picked():
    from capri.speech import engines as e
    class FakeSapi(e.SapiEngine):
        def __init__(self):
            pass

        def voices(self):
            return ["Microsoft Zira", "Microsoft Hedda"]

        def voice_for(self, code):
            return "Microsoft Hedda" if code == "de" else ""
    box = e.VoiceBox.__new__(e.VoiceBox)
    fake_sapi = FakeSapi()
    espeak = e.EspeakEngine()
    espeak.voices = lambda: ["espeak: en"]
    box.engines = [fake_sapi, espeak, e.BeepEngine()]
    languages.set_current("de")
    assert box.for_language("Microsoft Zira") == "Microsoft Hedda"                      # the German Windows voice
    languages.set_current("lv")
    assert box.for_language("Microsoft Zira") == "espeak: en"                           # espeak speaks Latvian
    assert box.for_language("beeps: retro") == "beeps: retro"
    assert box.for_language("fish: your Fish Audio voice") == "fish: your Fish Audio voice"
    languages.set_current("en")
    assert box.for_language("Microsoft Zira") == "Microsoft Zira"


def test_her_neural_voice_speaks_every_language():
    from capri.speech.engines import KokoroEngine
    assert all(KokoroEngine.speaks(code) for code in languages.LANGUAGES)          # (2.3.2: not just es/fr/it/pt)
    assert not KokoroEngine.speaks("xx")


def test_espeak_says_it_in_your_language(monkeypatch):
    import shutil
    from capri.speech import engines as e
    if not (shutil.which("espeak-ng") or shutil.which("espeak")):
        pytest.skip("no espeak-ng here")
    ran = []
    real = e.subprocess.run
    monkeypatch.setattr(e.subprocess, "run", lambda argv, **kw: ran.append(argv) or real(argv, **kw))
    languages.set_current("de")
    audio = e.EspeakEngine().synthesize("Hallo, ich bin Capri.", "espeak: en", 0.5)
    assert len(audio.samples) > 1000 and ran[0][ran[0].index("-v") + 1] == "de"


# -- her own lines, translated by your AI once -----------------------------------------------------------------------
def test_her_lines_are_translated_once_and_remembered(tmp_path):
    from capri.translate import LineTranslator
    asked = []

    def look(prompt, jpeg):
        asked.append(prompt)
        return AIReply("Discord ist offen.")
    t = LineTranslator(look, tmp_path, background=False)
    languages.set_current("de")
    got = []
    t.translate("Opened Discord.", got.append)
    t.translate("Opened Discord.", got.append)
    assert got == ["Discord ist offen.", "Discord ist offen."] and len(asked) == 1 and "German" in asked[0]
    again = LineTranslator(lambda p, j: AIReply("nope"), tmp_path, background=False)
    assert again.cached("Opened Discord.") == "Discord ist offen."                       # kept on disk
    languages.set_current("en")
    t.translate("Opened Discord.", got.append)
    assert got[-1] == "Opened Discord."


def test_no_ai_means_english_lines():
    from capri.translate import LineTranslator
    languages.set_current("fr")
    t = LineTranslator(lambda p, j: AIReply("x"), None, available=lambda: False, background=False)
    got = []
    t.translate("Opened Discord.", got.append)
    assert got == ["Opened Discord."]


def test_she_says_her_result_in_your_language():
    from test_v11 import FakeDesktop, rig
    from capri.translate import LineTranslator
    r = rig(FakeDesktop())
    shown = []
    a = r.assistant if hasattr(r, "assistant") else r.router.assistant
    a.translator = LineTranslator(lambda p, j: AIReply("Fertig!"), None, background=False)
    real = a._say_and_show
    a._say_and_show = lambda state, text, emotion, then=None, **kw: shown.append(text) or real(state, text, emotion,
                                                                                               then=then, **kw)
    languages.set_current("de")
    from capri.states import State
    a.show_result(State.SUCCESS, "Done!")
    a.show_result(State.SPEAKING, "Schon erledigt.", translated=True)
    assert shown[:2] == ["Fertig!", "Schon erledigt."]


def test_settings_picker_makes_parakeet_her_ears():
    from test_v11 import FakeDesktop, rig
    from test_v122 import _tab  # noqa: F401  (the settings window helpers)
    from capri.ui.settings_window import SettingsWindow
    from PySide6.QtGui import QImage
    r = rig(FakeDesktop())
    w = SettingsWindow(r.router, r.router.services.settings, QImage(8, 8, QImage.Format.Format_ARGB32),
                       lambda: [])
    w.language.setCurrentIndex(w.language.findData("fr"))
    assert w.hearing.currentData() == "parakeet" and not w.hearing.isEnabled()
    assert "French" in w.language_note.text()
    w.language.setCurrentIndex(w.language.findData("en"))
    assert w.hearing.isEnabled()


def test_only_what_comes_after_the_spoken_cue_is_kept():
    from capri.voice.parakeet import after_cue
    result = SimpleNamespace(tokens=["▁Das", "▁ist", "▁Deutsch", ".", "▁Öff", "ne", "▁Discord", "."],
                             timestamps=[0.2, 0.5, 1.0, 1.4, 3.1, 3.3, 3.5, 3.9])
    assert after_cue(result, 2.5) == "Öffne Discord."
    assert after_cue(SimpleNamespace(tokens=[], timestamps=[]), 2.5) == ""


def test_every_language_has_a_spoken_cue():
    assert set(languages.CUES) == set(languages.LANGUAGES) - {"en"}
    assert all(len(cue.split()) >= 8 for cue in languages.CUES.values())        # long enough to tell the language


def test_a_slightly_misheard_whole_command_still_counts():
    assert languages.to_english("wie spat ist es", "de") == "what time is it"
    assert languages.to_english("która rodzina", "pl") == "what time is it"
    assert languages.to_english("wie geht es dir heute", "de") == "wie geht es dir heute"   # chat stays chat


# -- the double Capri after a wall slam -------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", [(True, False), (True, True)])         # text box: pops up / only for her name
def test_no_second_capri_back_home_while_shes_being_thrown(mode):
    """Her "Ow!" mid-throw used to make her window visible again at home: two of her until the slam was over."""
    from test_v111 import companion
    from capri.states import State
    c = companion()
    c.settings.show_panel, (c.settings.panel_popup, c.settings.panel_on_name) = True, mode
    c.busy_elsewhere = True                         # what the throw (and the teleport, greeting...) sets
    c.character.hide()
    c.controller.set_state(State.LISTENING, "Listening...")
    c.set_talking(True)                             # "Ow! Rude."
    c._popup_check()
    c.set_talking(False)
    c._apply_visibility()
    assert not c.character.isVisible()
    c.busy_elsewhere = False                        # the throw's over: she's back in her window
    c.show()
    assert c.character.isVisible()


def test_elevenlabs_says_why_and_falls_back_to_its_free_voice():
    import io
    import urllib.error
    from capri.speech.engines import ElevenLabsEngine
    sent = []

    def fetch(url, body, headers):
        sent.append(url)
        if "MyLibraryVoice" in url:
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(
                b'{"detail": {"status": "voice_limit_reached", "message": "Free users cannot use library voices '
                b'via the API. Please upgrade your subscription."}}'))
        return b"\x00\x10" * 2205
    ElevenLabsEngine.key = staticmethod(lambda: "k")
    ElevenLabsEngine.voice_id = staticmethod(lambda: "MyLibraryVoice")
    try:
        audio = ElevenLabsEngine(fetch=fetch).synthesize("Hey.", "elevenlabs: your voice", 0.5)
        assert len(audio.samples) == 2205 and ElevenLabsEngine.DEFAULT_VOICE in sent[-1]

        def refuse(url, body, headers):
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(
                b'{"detail": {"status": "text_too_long", "message": "Text is too long."}}'))
        with pytest.raises(RuntimeError, match="Text is too long"):
            ElevenLabsEngine(fetch=refuse).synthesize("Hey.", "elevenlabs: your voice", 0.5)
    finally:
        ElevenLabsEngine.key = staticmethod(lambda: "")
        ElevenLabsEngine.voice_id = staticmethod(lambda: "")


def test_a_picture_model_that_wont_take_a_system_message_still_looks():
    """Groq / NVIDIA picture models have refused a system message next to an image: one message instead."""
    from capri.ai.openai_compat import OpenAIBrain
    from capri.integrations import http
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        sent.append(json_body)
        if any(m["role"] == "system" for m in json_body["messages"]):
            raise http.HttpError(400, '{"error": {"message": "prompting with images is incompatible with system '
                                      'messages"}}')
        return {"choices": [{"message": {"content": "Deadlock, mid-match."}}]}
    b = OpenAIBrain(lambda: "groq", lambda: "", lambda: "", lambda: "k", {}, fetch=fetch)
    reply = b.look("what do you see", "QUJD")
    assert not reply.error and reply.text == "Deadlock, mid-match."
    assert [m["role"] for m in sent[-1]["messages"]] == ["user"]


def test_on_a_busy_pc_she_makes_the_whole_line_before_talking():
    """v2.3: her voice broke up while Deadlock loaded - the next piece wasn't ready when the last one ended."""
    import time as _time
    import numpy as np
    from capri.settings import Settings
    from capri.speech.engines import Audio
    from capri.speech.speaker import Speaker
    played = []

    class SlowBox:
        last = ("espeak: en", "")

        def synthesize(self, text, voice, speed, pitch):
            _time.sleep(0.12)                                   # slow: a game is loading
            return Audio(np.full(2205, 0.3, np.float32), 22050, pitched=True)   # 0.1 s of sound

        def voices(self):
            return ["espeak: en"]
    s = Settings(speech_voice="espeak: en")
    sp = Speaker(s, SlowBox, player=lambda samples, rate: played.append(len(samples)) or (lambda: None),
                 sleep=lambda t: None)
    sp.ready.wait(5)
    sp._speak("First part of the line. Second part of it. And a third one too.")
    assert len(played) == 1 and played[0] > 2 * 2205                 # one go, all of it
    sp.shutdown()


# -- "play this for me" with the local brain "set up your brain" installs (llama3.2 can't see) -------------------------
def test_local_looks_use_a_model_that_can_see():
    from capri.ai import local
    from capri.integrations import http
    sent = []

    def fetch(method, url, json_body=None, timeout=None, **kw):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.2:latest"}, {"name": "gemma3:4b"}]}
        sent.append(json_body)
        if json_body["model"].startswith("llama3.2"):
            raise http.HttpError(400, '{"error": "this model is missing data required for image input"}')
        return {"message": {"content": "A Deadlock match."}}
    import inspect
    params = inspect.signature(local.LocalBrain.__init__).parameters
    b = local.LocalBrain(**{k: v for k, v in {"model": lambda: "llama3.2", "url": lambda: "", "info": {},
                                               "fetch": fetch}.items() if k in params})
    b.chosen = "llama3.2:latest"
    reply = b.look("play", "QUJD")
    assert not reply.error and reply.text == "A Deadlock match." and sent[-1]["model"] == "gemma3:4b"


def test_no_local_eyes_says_how_to_get_them_not_400():
    from capri.ai import local
    from capri.integrations import http

    def fetch(method, url, json_body=None, timeout=None, **kw):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.2:latest"}]}
        raise http.HttpError(400, '{"error": "this model is missing data required for image input"}')
    import inspect
    params = inspect.signature(local.LocalBrain.__init__).parameters
    b = local.LocalBrain(**{k: v for k, v in {"model": lambda: "llama3.2", "url": lambda: "", "info": {},
                                               "fetch": fetch}.items() if k in params})
    b.chosen = "llama3.2:latest"
    reply = b.look("play", "QUJD")
    assert reply.error and reply.blind and "give yourself eyes" in reply.text and "400" not in reply.text
    assert parse("give yourself eyes").kind == Kind.AI_SETUP and parse("give yourself eyes").query == "eyes"


@pytest.mark.parametrize("name,sees", [("gemma3:4b", True), ("llava:7b", True), ("llama3.2-vision", True),
                                       ("qwen2.5vl:7b", True), ("minicpm-v", True), ("moondream", True),
                                       ("llama3.2", False), ("llama3.2:1b", False), ("mistral", False)])
def test_which_local_models_can_see(name, sees):
    from capri.ai.local import can_see
    assert can_see(name) is sees


def test_right_click_language_menu_switches_her():
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QMenu
    from test_v111 import companion
    from capri.ui.tray import CompanionMenu
    c = companion()
    menu = CompanionMenu(c, QImage(8, 8, QImage.Format.Format_ARGB32))
    picked = []
    menu.add_languages(picked.append)
    order = [a.text() for a in menu.menu.actions()]
    assert order.index("Language") == order.index("Size") + 1                # right under Size
    assert len(menu.languages) == 25
    menu.languages["de"].trigger()
    assert picked == ["de"]
    c.settings.language = "fr"
    menu._sync_language()
    assert menu.languages["fr"].isChecked() and not menu.languages["de"].isChecked()


# -- 2.3.1: she types her reply but says nothing ----------------------------------------------------------------------
def _streamed_wav(size_field: int, seconds: float = 0.5) -> bytes:
    import struct
    pcm = b"\x00\x10" * int(44100 * seconds)
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    return b"RIFF" + struct.pack("<I", 0) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + \
        struct.pack("<I", size_field) + pcm


@pytest.mark.parametrize("size_field", [0, 0xFFFFFFFF, 999_999_999])
def test_a_streamed_fish_wav_is_heard_not_silence(size_field):
    """A streamed WAV says "0 bytes" of sound in its header: read literally, she said nothing at all."""
    import io
    import wave
    raw = _streamed_wav(size_field)
    try:                                                                        # what used to happen:
        with wave.open(io.BytesIO(raw)) as w:
            old = w.readframes(w.getnframes())
    except wave.Error:
        old = b""                                                               # refused, or...
    assert size_field != 0 or old == b""                                        # ...no sound at all
    from capri.speech.engines import FishAudioEngine
    FishAudioEngine.key = staticmethod(lambda: "k")
    try:
        audio = FishAudioEngine(fetch=lambda u, b, h: raw).synthesize("How are you?", "fish: your Fish Audio voice", 0.6)
    finally:
        FishAudioEngine.key = staticmethod(lambda: "")
    assert len(audio.samples) == 22050 and audio.rate == 44100


def test_an_online_voice_that_sends_no_sound_falls_back_to_her_voice():
    from capri.speech import engines as e
    FishAudioEngine = e.FishAudioEngine
    FishAudioEngine.key = staticmethod(lambda: "k")
    try:
        with pytest.raises(RuntimeError, match="no sound"):
            FishAudioEngine(fetch=lambda u, b, h: _streamed_wav(0, 0)).synthesize("Hi", "fish: x", 0.6)
    finally:
        FishAudioEngine.key = staticmethod(lambda: "")


def test_things_she_says_by_herself_show_in_her_text_box():
    from test_v11 import FakeDesktop, rig
    from capri.states import State
    r = rig(FakeDesktop())
    a = r.router.assistant
    a.remark("Nice kill!", emotion="happy")
    assert r.controller.state in (State.SPEAKING, State.IDLE) and "Nice kill!" in (r.controller.message or "") or \
        any("Nice kill!" in str(e) for e in getattr(r.controller, "entries", []))


def test_long_replies_show_whole():
    from capri.ui import status_panel
    assert status_panel.ANSWER_LINES >= 12


# -- 2.3.2 --------------------------------------------------------------------------------------------------------------
def test_text_box_modes_in_the_right_click_menu():
    from PySide6.QtGui import QImage
    from test_v111 import companion
    from capri.ui.tray import CompanionMenu
    c = companion()
    menu = CompanionMenu(c, QImage(8, 8, QImage.Format.Format_ARGB32))
    menu.box_modes["name"].trigger()
    assert c.settings.show_panel and c.settings.panel_popup and c.settings.panel_on_name
    menu.box_modes["never"].trigger()
    assert not c.settings.show_panel
    menu.sync()
    assert menu.box_modes["never"].isChecked()


def test_compact_mode_keeps_her_size_and_her_text_box_grows_with_her():
    from test_v111 import companion
    c = companion()
    tall = c.character.display_height
    c.set_compact(True)
    assert c.character.display_height == tall                  # compact: just a smaller text box
    narrow = c.panel.panel_width
    c.set_compact(False)
    normal = c.panel.panel_width
    c.set_size(200)
    assert c.panel.panel_width > normal and narrow < normal      # bigger her, bigger box
    c.set_size(60)
    assert c.panel.panel_width < normal


def test_keep_my_voice_in_another_language():
    from capri.speech import engines as e
    box = e.VoiceBox.__new__(e.VoiceBox)
    espeak = e.EspeakEngine()
    espeak.voices = lambda: ["espeak: en"]
    box.engines = [espeak]
    languages.set_current("ru")
    assert box.for_language("neural: Capri") == "espeak: en"
    languages.keep_voice = True
    try:
        assert box.for_language("neural: Capri") == "neural: Capri"          # only what she hears changed
    finally:
        languages.keep_voice = False


def test_no_gap_between_her_hair_crown_and_head():
    """The black crown over her face sat in a slightly bigger hole in her hair: a sliver of desktop showed."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from capri.ui.hair import StormHair
    hair = StormHair()
    head = QRectF(200, 200, 80, 90)
    img = QImage(480, 480, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 255, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    hair.paint(p, head, 0.0, 1.0)
    p.end()
    gaps = []
    for poly in hair._place(hair._crown, head, 0.0, 1.0, 0.0):
        for k in range(poly.count()):
            pt = poly.at(k)
            if not head.adjusted(4, 4, -4, -4).contains(pt):
                continue                                    # the outside of her hair may touch the desktop
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    c = img.pixelColor(int(pt.x()) + dx, int(pt.y()) + dy)
                    if c.green() > 120 and c.red() < 80:    # mostly background showing through
                        gaps.append((int(pt.x()) + dx, int(pt.y()) + dy))
    assert not gaps, gaps
