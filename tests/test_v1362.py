"""v1.36.2: "the hey capri" wakes her (a stray little word in front of her name), commands that start
with "the" still work, downloads verify on PCs whose antivirus scans HTTPS, and the hearing settings
only show what the picked hearing needs."""

from __future__ import annotations

import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_wakeword import make  # noqa: E402

from capri import net  # noqa: E402
from capri.voice.wakeword import Rejected, Wake, clean_command  # noqa: E402


def word(w, start, end, conf=1.0):
    return {"word": w, "start": start, "end": end, "conf": conf}


def utterance(*words):
    return {"result": list(words), "text": " ".join(w["word"] for w in words)}


@pytest.mark.parametrize("lead", ["the", "a", "uh", "um", "oh", "okay", "yeah", "hi"])
def test_a_little_word_before_hey_capri_still_wakes_her(lead):
    listener = make()
    events = listener._on_wake_utterance(utterance(word(lead, 0.0, 0.2), word("hey", 0.25, 0.45),
                                                   word("capri", 0.5, 1.0)))
    assert isinstance(events[0], Wake) and events[0].phrase == "hey capri"


def test_the_capri_without_hey_too():
    events = make()._on_wake_utterance(utterance(word("the", 0.0, 0.2), word("capri", 0.25, 0.8)))
    assert isinstance(events[0], Wake) and events[0].phrase == "capri"


@pytest.mark.parametrize("said", [
    [word("went", 0, .3), word("to", .3, .5), word("capri", .5, 1.0)],                  # "I went to capri"
    [word("the", 0, .2), word("went", .2, .4), word("capri", .5, 1.0)],                # filler + a real word
    [word("the", 0, .2), word("the", .2, .4), word("capri", .5, 1.0)],                 # only one filler
])
def test_her_name_mid_sentence_still_doesnt(said):
    events = make()._on_wake_utterance(utterance(*said))
    assert not any(isinstance(e, Wake) for e in events) and (not events or isinstance(events[0], Rejected))


@pytest.mark.parametrize("heard, clean", [
    ("the open discord", "open discord"), ("uh play lofi", "play lofi"), ("the hey capri open discord", "open discord"),
    ("um the what time is it", "what time is it"), ("the weather", "weather"), ("open the door", "open the door"),
    ("the", "the"),
])
def test_commands_starting_with_the(heard, clean):
    assert clean_command(heard) == clean


def test_downloads_get_certificate_fallbacks():
    import urllib.request
    net._done = ""
    try:
        assert net.use_system_certificates().startswith("fallbacks:")
        assert any(isinstance(h, net.FallbackHTTPSHandler) for h in urllib.request._opener.handlers)
    finally:
        urllib.request.install_opener(None)
        net._done = ""


def test_download_errors_in_plain_words():
    err = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    assert "antivirus" in net.friendly(err)
    assert "antivirus" in net.friendly(OSError("<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] ...>"))
    assert "timed out" in net.friendly(TimeoutError("timed out"))


# -- the hearing settings ---------------------------------------------------------------------------------------------
def window(**settings):
    from PySide6.QtGui import QImage
    from test_commands import make_catalog
    from test_v11 import FakeCompanion, FakeSpeaker, FakeSystem
    from capri.assistant import Assistant
    from capri.commands.router import CommandRouter
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.settings_window import SettingsWindow
    from capri.voice.service import VoiceService
    s = Settings(**settings)
    a = Assistant(CompanionController(), s, VoiceService(True, False, "", 0.8), FakeSpeaker())
    router = CommandRouter(a, FakeCompanion(), make_catalog(), FakeSystem([]))
    win = SettingsWindow(router, s, QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [])
    win.show()
    return win


def test_only_what_the_picked_hearing_needs(monkeypatch):
    from capri.voice import parakeet, whisper
    monkeypatch.setattr(parakeet, "ready", lambda: False)
    monkeypatch.setattr(parakeet, "installed", lambda: True)
    monkeypatch.setattr(whisper, "installed", lambda: False)
    win = window(hearing="vosk")
    assert win.parakeet_btn.isHidden() and win.whisper_btn.isHidden() and win.whisper_size.isHidden()
    win.hearing.setCurrentIndex(win.hearing.findData("parakeet"))
    assert not win.parakeet_btn.isHidden() and win.whisper_btn.isHidden() and win.whisper_size.isHidden()
    assert "Press Download" in win.parakeet_status.text()
    win.hearing.setCurrentIndex(win.hearing.findData("whisper"))
    assert win.parakeet_btn.isHidden() and not win.whisper_btn.isHidden() and not win.whisper_size.isHidden()
    monkeypatch.setattr(parakeet, "ready", lambda: True)
    win.hearing.setCurrentIndex(win.hearing.findData("parakeet"))
    assert win.parakeet_btn.isHidden() and "Press Apply" in win.parakeet_status.text()


def test_the_installed_app_doesnt_offer_whisper_it_cant_install(monkeypatch):
    from capri.voice import whisper
    monkeypatch.setattr(whisper, "installed", lambda: False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    win = window()
    assert win.hearing.findData("whisper") < 0 and win.hearing.findData("parakeet") >= 0


def test_a_failed_download_says_why(monkeypatch):
    from capri.voice import parakeet

    def fail(progress=None, **k):
        raise OSError("<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>")
    monkeypatch.setattr(parakeet, "ready", lambda: False)
    monkeypatch.setattr(parakeet, "installed", lambda: True)
    monkeypatch.setattr(parakeet, "download", fail)
    win = window(hearing="parakeet")
    win._download_parakeet()
    from test_stage5 import settle
    assert settle(3, lambda: "antivirus" in win.parakeet_status.text())
    assert win.parakeet_btn.isEnabled() and not win.parakeet_btn.isHidden()      # try again
