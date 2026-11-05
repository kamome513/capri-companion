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


def test_her_neural_voice_speaks_spanish_french_italian_portuguese():
    from capri.speech.engines import KokoroEngine
    assert KokoroEngine.speaks("es") and KokoroEngine.speaks("fr") and KokoroEngine.speaks("pt")
    assert not KokoroEngine.speaks("de")


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
