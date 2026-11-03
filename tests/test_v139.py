"""v1.39: NVIDIA keys for her brain, and Fish Audio voices (like ElevenLabs, with free credits)."""

from __future__ import annotations

import io
import sys
import urllib.error
import wave
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.speech.engines import BeepEngine, FishAudioEngine, VoiceBox  # noqa: E402


def wav_bytes(samples: np.ndarray, rate: int = 24000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


@pytest.fixture
def fish():
    sent = []
    reply = {"data": wav_bytes((np.sin(np.arange(2400) / 4) * 9000))}

    def fetch(url, body, headers):
        sent.append((url, body, headers))
        if isinstance(reply["data"], Exception):
            raise reply["data"]
        return reply["data"]
    FishAudioEngine.key = staticmethod(lambda: " fa-key ")
    FishAudioEngine.voice_id = staticmethod(lambda: "https://fish.audio/m/abc123def/")
    yield FishAudioEngine(fetch=fetch), sent, reply
    FishAudioEngine.key = staticmethod(lambda: "")
    FishAudioEngine.voice_id = staticmethod(lambda: "")


def test_nvidia_is_a_brain_you_can_pick():
    from capri.ai.openai_compat import KEY_HINTS, PRESETS
    label, url, model, needs_key = PRESETS["nvidia"]
    assert "NVIDIA" in label and url == "https://integrate.api.nvidia.com/v1" and model and needs_key
    assert "build.nvidia.com" in KEY_HINTS["nvidia"]


def test_nvidia_talks_the_openai_way_to_its_address():
    from capri.ai.openai_compat import OpenAIBrain
    brain = OpenAIBrain(lambda: "nvidia", lambda: "", lambda: "", lambda: "nvapi-123", {})
    assert brain._preset() == "nvidia"
    assert PRESET_URL(brain).startswith("https://integrate.api.nvidia.com/v1")


def PRESET_URL(brain) -> str:
    from capri.ai.openai_compat import PRESETS
    return PRESETS[brain._preset()][1]


def test_fish_audio_voice(fish):
    engine, sent, _ = fish
    assert engine.voices() == [FishAudioEngine.NAME]
    audio = engine.synthesize("Hey choom.", FishAudioEngine.NAME, 0.5)
    url, body, headers = sent[0]
    assert url == "https://api.fish.audio/v1/tts" and headers["Authorization"] == "Bearer fa-key"
    assert body["reference_id"] == "abc123def" and body["format"] == "wav" and body["text"] == "Hey chooom."
    assert audio.rate == 24000 and len(audio.samples) == 2400 and audio.natural


def test_fish_audio_stereo_is_made_mono(fish):
    engine, _sent, reply = fish
    reply["data"] = wav_bytes(np.ones(4800) * 1000, rate=44100, channels=2)
    audio = engine.synthesize("Hi.", FishAudioEngine.NAME, 0.5)
    assert audio.rate == 44100 and len(audio.samples) == 2400


def test_no_voice_id_uses_their_default(fish):
    engine, sent, _ = fish
    FishAudioEngine.voice_id = staticmethod(lambda: "")
    engine.synthesize("Hi.", FishAudioEngine.NAME, 0.5)
    assert "reference_id" not in sent[0][1]


@pytest.mark.parametrize("text,voice", [("abc123", "abc123"), ("https://fish.audio/m/xyz/", "xyz"),
                                        ("https://fish.audio/m/xyz?share=1", "xyz"), ("  ", "")])
def test_voice_links_or_ids(text, voice):
    assert FishAudioEngine.voice_from(text) == voice


@pytest.mark.parametrize("code,why", [(401, "key doesn't work"), (402, "out of credit"), (404, "no voice")])
def test_fish_problems_fall_back_to_her_normal_voice(fish, code, why):
    engine, _sent, reply = fish
    reply["data"] = urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
    box = VoiceBox.__new__(VoiceBox)
    box.engines, box.last = [engine, BeepEngine()], ("", "")
    box.default_voice = lambda: "beeps: retro"
    audio = box.synthesize("Hi there.", FishAudioEngine.NAME, 0.5)
    assert len(audio.samples) and why in box.last[1] and "normal voice" in box.last[1]


def test_not_audio_is_said_plainly(fish):
    engine, _sent, reply = fish
    reply["data"] = b'{"message": "nope"}'
    with pytest.raises(RuntimeError) as caught:
        engine.synthesize("Hi.", FishAudioEngine.NAME, 0.5)
    assert "isn't audio" in str(caught.value)


def test_adding_a_fish_key_picks_that_voice():
    from test_v11 import FakeDesktop, rig
    from test_v122 import _tab
    from capri import secrets
    r = rig(FakeDesktop())
    tab = _tab(r)
    try:
        tab.fish_key.setText("fa-new")
        tab.fish_voice.setText("https://fish.audio/m/myvoice/")
        tab.apply()
        s = r.assistant.settings
        assert s.speech_voice == FishAudioEngine.NAME and s.fish_voice == "myvoice"
        assert secrets.get("fish_audio_api_key") == "fa-new"
    finally:
        secrets.set_many({"fish_audio_api_key": ""})


def test_her_voice_also_plays_in_your_mic(monkeypatch):
    import threading
    import types
    from capri.speech import speaker
    played, streams = [], []

    class Stream:
        def __init__(self, device, samplerate, channels, dtype):
            streams.append((device, samplerate))
            self.got = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def write(self, block):
            self.got += len(block)
    devices = [{"name": "Speakers", "max_output_channels": 2, "default_samplerate": 48000},
               {"name": "Microphone", "max_output_channels": 0, "default_samplerate": 48000},
               {"name": "CABLE Input", "max_output_channels": 2, "default_samplerate": 48000}]
    fake = types.SimpleNamespace(play=lambda s, r: played.append(r), stop=lambda: None, OutputStream=Stream,
                                 query_devices=lambda i=None: devices if i is None else devices[i])
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(speaker, "mic_device", lambda: "CABLE Input")
    assert speaker.output_devices() == ["Speakers", "CABLE Input"]
    stop = speaker._sounddevice_player(np.zeros(2400, np.float32), 24000)
    for t in threading.enumerate():
        if t.name == "capri-voice-mic":
            t.join(2)
    stop()
    assert played == [24000] and streams == [(2, 48000)]          # resampled to what the cable wants


def test_no_mic_device_is_just_the_speakers(monkeypatch):
    import types
    from capri.speech import speaker
    fake = types.SimpleNamespace(play=lambda s, r: None, stop=lambda: None, query_devices=lambda i=None: [],
                                 OutputStream=lambda **k: pytest.fail("no second output"))
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(speaker, "mic_device", lambda: "")
    speaker._sounddevice_player(np.zeros(10, np.float32), 24000)()


def test_head_pats_and_pokes():
    from PySide6.QtCore import QPoint, QRect
    from capri.ui.companion import Companion
    got = []
    c = SimpleNamespace(hidden=False, drone=False, settings=SimpleNamespace(head_pats=True), _last_pat=-1e9,
                        content_geometry=lambda: QRect(100, 100, 80, 300), patted=SimpleNamespace(emit=got.append))
    Companion._clicked(c, QPoint(140, 150))
    c._last_pat = -1e9
    Companion._clicked(c, QPoint(140, 350))
    Companion._clicked(c, QPoint(140, 150))                      # too soon after the last one
    c._last_pat = -1e9
    Companion._clicked(c, QPoint(10, 10))                         # not on her
    assert got == ["head", "body"]
