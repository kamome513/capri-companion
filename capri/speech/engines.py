"""Text-to-speech engines. Each turns text into 16-bit mono PCM (all offline).

* SapiEngine  - the voices built into Windows (no download, always there).
* KokoroEngine - neural voices (natural, expressive, offline). Her default
  once installed: ``pip install kokoro-onnx`` plus two model files in
  models/kokoro/ (tools/download_voice.py, or Settings -> Assistant).
* PiperEngine - optional neural voices (more natural). Needs ``pip install
  piper-tts`` and a voice file (.onnx + .onnx.json) in models/voices/.
* EspeakEngine - Linux fallback, used for development/testing only.
"""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path
import shutil
from xml.sax.saxutils import escape

from .pronounce import respell, sapi_xml
import subprocess
import sys
import wave
from dataclasses import dataclass
from typing import Callable
import numpy as np

from ..voice.model import MODELS_DIR

log = logging.getLogger("capri")

VOICES_DIR = MODELS_DIR / "voices"
KOKORO_DIR = MODELS_DIR / "kokoro"


def kokoro_folder():
    """Where her neural voice is (or goes): next to Capri when run from her folder (or bundled), else - the
    installed Capri.exe - your user folder (%LOCALAPPDATA%\\Capri\\models\\kokoro), kept across reinstalls."""
    if (KOKORO_DIR / KOKORO_MODEL).exists() or not getattr(sys, "frozen", False):
        return KOKORO_DIR
    from ..voice.model import user_models_dir
    return user_models_dir() / "kokoro"
KOKORO_MODEL = "kokoro-v1.0.int8.onnx"      # 88 MB, quantised: quick on any CPU
KOKORO_VOICES = "voices-v1.0.bin"
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


@dataclass
class Audio:
    samples: np.ndarray   # float32, -1..1, mono
    rate: int
    pitched: bool = False # True if the engine already applied the requested pitch
    natural: bool = False # True if it already rises and falls by itself (ElevenLabs, beeps): no added intonation
    as_is: bool = False   # True for online voices (ElevenLabs, Fish Audio): played exactly as they come - no effects


def _from_int16(data: bytes, rate: int) -> Audio:
    return Audio(np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0, rate)


class SapiEngine:
    """Windows SAPI 5 via COM, rendered into memory (never to the speakers directly)."""

    PREFIX = ""
    SAFT22kHz16BitMono = 22
    SVSF_IS_XML = 8

    def __init__(self) -> None:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()          # this engine lives on the speech thread
        self._client = comtypes.client
        self._voice = comtypes.client.CreateObject("SAPI.SpVoice")

    def voices(self) -> list[str]:
        tokens = self._voice.GetVoices()
        return [tokens.Item(i).GetDescription() for i in range(tokens.Count)]

    LANG_IDS = {"en": 0x09, "de": 0x07, "fr": 0x0C, "es": 0x0A, "it": 0x10, "pt": 0x16, "nl": 0x13, "pl": 0x15,
                "ru": 0x19, "uk": 0x22, "sv": 0x1D, "da": 0x06, "fi": 0x0B, "cs": 0x05, "sk": 0x1B, "sl": 0x24,
                "hr": 0x1A, "bg": 0x02, "ro": 0x18, "hu": 0x0E, "el": 0x08, "et": 0x25, "lv": 0x26, "lt": 0x27,
                "mt": 0x3A}

    def voice_for(self, code: str) -> str:
        """An installed Windows voice that speaks this language ("" if none): its Language attribute is a list
        of Windows language numbers (e.g. "407" = German)."""
        want = self.LANG_IDS.get(code)
        tokens = self._voice.GetVoices()
        for i in range(tokens.Count):
            token = tokens.Item(i)
            try:
                ids = [int(x, 16) & 0x3FF for x in str(token.GetAttribute("Language") or "").split(";") if x]
            except (ValueError, Exception):
                continue
            if want in ids:
                return token.GetDescription()
        return ""

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        tokens = self._voice.GetVoices()
        for i in range(tokens.Count):
            if tokens.Item(i).GetDescription() == voice:
                self._voice.Voice = tokens.Item(i)
                break
        self._voice.Rate = int(round((speed - 0.5) * 12))          # SAPI: -10..10, 0 = normal
        stream = self._client.CreateObject("SAPI.SpMemoryStream")
        fmt = self._client.CreateObject("SAPI.SpAudioFormat")
        fmt.Type = self.SAFT22kHz16BitMono
        stream.Format = fmt
        self._voice.AudioOutputStream = stream
        # SAPI's own pitch control sounds far better than shifting the audio afterwards.
        level = max(-10, min(10, round(pitch)))
        try:
            # exact phonemes for slang ("choom" = ch-oo-m, not "chum")
            self._voice.Speak(f'<pitch absmiddle="{level}">{sapi_xml(text)}</pitch>', self.SVSF_IS_XML)
        except Exception:
            # a voice that rejects the phoneme tags: fall back to respelled text
            self._voice.Speak(f'<pitch absmiddle="{level}">{escape(respell(text, plain=True))}</pitch>',
                              self.SVSF_IS_XML)
        audio = _from_int16(bytes(stream.GetData()), 22050)
        audio.pitched = True
        return audio


class PiperEngine:
    PREFIX = "piper: "

    def __init__(self) -> None:
        import piper  # noqa: F401 - fail early if not installed
        self._loaded: dict[str, object] = {}

    def voices(self) -> list[str]:
        if not VOICES_DIR.is_dir():
            return []
        return [self.PREFIX + p.stem for p in sorted(VOICES_DIR.glob("*.onnx"))
                if p.with_suffix(".onnx.json").exists()]

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        from piper import PiperVoice
        name = voice[len(self.PREFIX):]
        if name not in self._loaded:
            self._loaded[name] = PiperVoice.load(str(VOICES_DIR / f"{name}.onnx"))
        v = self._loaded[name]
        rate = int(v.config.sample_rate)
        length = 1.5 - speed                                        # Piper: bigger = slower
        if hasattr(v, "synthesize_stream_raw"):                     # piper-tts 1.2
            data = b"".join(v.synthesize_stream_raw(respell(text), length_scale=length))
        else:                                                       # piper-tts 1.3+ (checked on 1.8)
            from piper import SynthesisConfig
            chunks = list(v.synthesize(respell(text), syn_config=SynthesisConfig(length_scale=length)))
            data = b"".join(chunk.audio_int16_bytes for chunk in chunks)
            if chunks:
                rate = int(chunks[0].sample_rate)
        return _from_int16(data, rate)


class KokoroEngine:
    """Kokoro-82M neural voices via ONNX, fully offline.

    "Capri" is a blend of two of its brightest female voices, raised a touch by
    playing her back slightly faster (rendered slower first, so the speed stays
    put). Tape-style pitching lifts the formants too - a younger, lighter,
    anime-ish timbre - and has none of the warble of a pitch-shifter.
    """

    PREFIX = "neural: "
    CAPRI = "Capri"
    CAPRI_BLEND = {"af_bella": 0.6, "af_heart": 0.4}
    PITCH_SCALE = 0.5      # her voice is already high: half the slider's semitones is plenty
    FEMALE = ("af_", "bf_")

    def __init__(self, folder=None) -> None:
        import kokoro_onnx  # noqa: F401 - fail early if not installed
        self.folder = folder or kokoro_folder()
        self._kokoro = None
        self._names: list[str] | None = None

    @classmethod
    def installed(cls, folder=None) -> bool:
        folder = folder or kokoro_folder()
        return (folder / KOKORO_MODEL).exists() and (folder / KOKORO_VOICES).exists()

    def voices(self) -> list[str]:
        if not self.installed(self.folder):
            return []
        if self._names is None:
            with np.load(self.folder / KOKORO_VOICES) as bank:     # just the names, not the data
                self._names = sorted(n for n in bank.files if n.startswith(self.FEMALE))
        return [self.PREFIX + self.CAPRI] + [self.PREFIX + n for n in self._names]

    def _model(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(str(self.folder / KOKORO_MODEL), str(self.folder / KOKORO_VOICES))
        return self._kokoro

    @staticmethod
    def speaks(code: str) -> bool:
        from .. import languages
        return code == "en" or languages.get(code).kokoro is not None

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        from .. import languages
        k = self._model()
        name = voice[len(self.PREFIX):]
        own = languages.get().kokoro                                # Spanish, French, Italian, Portuguese
        if own is not None:
            style, lang = own
        else:
            if name == self.CAPRI:
                style = sum(w * k.get_voice_style(v) for v, w in self.CAPRI_BLEND.items())
            else:
                style = name
            lang = "en-gb" if name.startswith("bf_") else "en-us"
        lift = 2 ** (pitch * self.PITCH_SCALE / 12)
        tempo = (0.8 + 0.6 * speed) / lift                          # 0.5 -> 1.1x, before the lift
        said = respell(text) if own is None else text               # (her slang respellings are English)
        samples, rate = k.create(said, voice=style, speed=max(0.5, min(2.0, tempo)), lang=lang)
        x = np.asarray(samples, dtype=np.float32)
        if abs(lift - 1) > 1e-3:
            n = int(len(x) / lift)
            x = np.interp(np.arange(n) * lift, np.arange(len(x)), x).astype(np.float32)
        return Audio(x, int(rate), pitched=True)


class _EspeakLib:
    """espeak-ng through its library (the copy her neural voice already ships, espeakng_loader) -
    so Linux has a real voice even without the espeak-ng program installed."""

    def __init__(self) -> None:
        import ctypes
        import espeakng_loader
        self.ctypes = ctypes
        self.lib = ctypes.CDLL(espeakng_loader.get_library_path())
        self.samples: list[bytes] = []
        CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)

        def collect(wav, count, _events):
            if wav and count > 0:
                self.samples.append(ctypes.string_at(wav, count * 2))
            return 0
        self._callback = CALLBACK(collect)              # kept alive as long as the library uses it
        self.lib.espeak_Initialize.restype = ctypes.c_int
        data = espeakng_loader.get_data_path().encode()
        self.rate = self.lib.espeak_Initialize(2, 500, ctypes.c_char_p(str(Path(data.decode()).parent).encode()), 0)
        if self.rate <= 0:
            self.rate = self.lib.espeak_Initialize(2, 500, ctypes.c_char_p(data), 0)
        if self.rate <= 0:
            raise RuntimeError("espeak-ng didn't start")
        self.lib.espeak_SetSynthCallback(self._callback)
        self.lib.espeak_SetVoiceByName(b"en")
        self.voice = "en"
        self.lock = threading.Lock()

    def synth(self, text: str, wpm: int, pitch: int, voice: str = "en") -> Audio:
        c = self.ctypes
        with self.lock:
            if voice != self.voice:
                self.lib.espeak_SetVoiceByName(voice.encode())
                self.voice = voice
            self.samples = []
            self.lib.espeak_SetParameter(1, int(wpm), 0)          # espeakRATE
            self.lib.espeak_SetParameter(3, int(pitch), 0)        # espeakPITCH
            data = text.encode("utf-8") + b"\0"
            self.lib.espeak_Synth(c.c_char_p(data), c.c_size_t(len(data)), 0, 0, 0, 1, None, None)  # espeakCHARS_UTF8
            self.lib.espeak_Synchronize()
            raw = b"".join(self.samples)
        return _from_int16(raw, self.rate)


class EspeakEngine:
    PREFIX = "espeak: "
    _lib: _EspeakLib | None = None
    _lib_failed = False

    @classmethod
    def _library(cls) -> _EspeakLib | None:
        if cls._lib is None and not cls._lib_failed:
            try:
                cls._lib = _EspeakLib()
            except Exception:
                cls._lib_failed = True
        return cls._lib

    def voices(self) -> list[str]:
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            return [self.PREFIX + "en"]
        import importlib.util
        return [self.PREFIX + "en"] if importlib.util.find_spec("espeakng_loader") is not None else []

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        from .. import languages
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        p = max(0, min(99, round(50 + pitch * 4)))
        lang = languages.get()
        said = respell(text) if lang.code == "en" else text
        if not exe:
            lib = self._library()
            if lib is None:
                raise RuntimeError("espeak-ng isn't available")
            audio = lib.synth(said, int(130 + speed * 80), p, lang.espeak)
            audio.pitched = True
            return audio
        wav = subprocess.run([exe, "--stdout", "-v", lang.espeak, "-s", str(int(130 + speed * 80)), "-p", str(p),
                              "--", said], capture_output=True, check=True).stdout
        with wave.open(io.BytesIO(wav)) as w:
            audio = _from_int16(w.readframes(w.getnframes()), w.getframerate())
        audio.pitched = True
        return audio


class BeepEngine:
    """No words at all: chiptune blips as she "talks", like the text boxes in old handheld RPGs.
    retro = Game Boy-ish (a softened square), cute = rounder, sine-like blips. Smooth (v1.34): each blip
    fades in and out (no clicks), glides from the last note instead of jumping, and they run into each
    other like syllables instead of being chopped apart by silence."""

    PREFIX = "beeps: "
    KINDS = {"retro": (880.0, "square"), "cute": (1175.0, "soft")}
    GLIDE = 0.35            # share of each blip spent sliding from the last note to this one
    OVERLAP = 0.3           # share of a blip that overlaps the next (legato)

    def voices(self) -> list[str]:
        return [self.PREFIX + k for k in self.KINDS]

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        rate = 22050
        base, wave_kind = self.KINDS.get(voice[len(self.PREFIX):], self.KINDS["retro"])
        base *= 2 ** (pitch / 12)
        blip = 0.085 - 0.03 * max(0.0, min(1.0, speed))              # faster talker, shorter blips
        notes: list[tuple[float, float]] = []                        # (start seconds, hz)
        t = 0.0
        letters = 0
        chars = text.strip()
        for i, ch in enumerate(chars):
            if ch.isalnum():
                letters += 1
                if letters % 2:                                          # a blip every other letter
                    continue
                step = 3 if ch.lower() in "aeiouy" else (ord(ch.lower()) * 7) % 5 - 2
                last = all(not c.isalnum() for c in chars[i + 1:i + 6])
                if last and "?" in chars[i + 1:i + 6]:
                    step += 5                                            # questions go up at the end
                notes.append((t, base * 2 ** (step / 12)))
                t += blip * (1 - self.OVERLAP)
            elif ch == " ":
                letters = 0
                t += blip * 0.45
            elif ch in ",;:-":
                t += 0.14
            elif ch in ".!?":
                t += 0.24
        if not notes:
            return Audio(np.zeros(int(rate * 0.1), np.float32), rate, pitched=True, natural=True)
        out = np.zeros(int(rate * (t + blip + 0.05)), np.float32)
        previous = notes[0][1]
        for start, hz in notes:
            piece = self._blip(previous, hz, blip, rate, wave_kind)
            i = int(start * rate)
            out[i:i + len(piece)] += piece[: len(out) - i]
            previous = hz
        out = np.convolve(out, np.ones(3, np.float32) / 3, mode="same")    # a touch of softening
        return Audio(np.clip(out, -0.9, 0.9).astype(np.float32), rate, pitched=True, natural=True)

    @classmethod
    def _blip(cls, from_hz: float, hz: float, seconds: float, rate: int, kind: str) -> np.ndarray:
        n = max(1, int(rate * seconds))
        k = np.arange(n)
        glide = np.minimum(1.0, k / max(1, int(n * cls.GLIDE)))
        freq = from_hz + (hz - from_hz) * (1 - (1 - glide) ** 2)       # eases into the new note
        phase = 2 * np.pi * np.cumsum(freq) / rate                       # continuous: no jumps in the wave
        if kind == "square":                                             # a square with its harsh edge rounded
            wave = np.sin(phase) + 0.3 * np.sin(3 * phase) + 0.12 * np.sin(5 * phase)
            wave /= 1.25
        else:
            wave = np.sin(phase) + 0.18 * np.sin(2 * phase)
        attack, release = max(1, int(rate * 0.008)), max(1, int(rate * 0.035))
        env = np.ones(n)
        a = min(attack, n)
        env[:a] = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)          # raised-cosine fade in
        r = min(release, n)
        env[n - r:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(r) / r)     # ...and out: no clicks
        return (0.3 * wave * env).astype(np.float32)


class ElevenLabsEngine:
    """ElevenLabs' online voices (your API key + a voice ID, Settings -> Assistant -> Voice).
    Only the line's text is sent, never audio. No key: not offered."""

    PREFIX = "elevenlabs: "
    NAME = PREFIX + "your ElevenLabs voice"
    DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"         # one of ElevenLabs' standard voices; paste your own ID
    MODEL = "eleven_flash_v2_5"                    # their quickest
    key: Callable[[], str] = staticmethod(lambda: "")
    voice_id: Callable[[], str] = staticmethod(lambda: "")

    def __init__(self, fetch=None) -> None:
        self._fetch = fetch or self._post

    def voices(self) -> list[str]:
        return [self.NAME] if (type(self).key() or "").strip() else []

    @staticmethod
    def _detail(exc) -> str:
        """ElevenLabs' own words: {"detail": {"status": "voice_limit_reached", "message": "..."}} or a string."""
        import json
        try:
            data = json.loads(exc.read().decode("utf-8", "replace") or "{}")
        except Exception:
            return ""
        detail = data.get("detail") if isinstance(data, dict) else None
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("status") or "")[:200]
        return str(detail or "")[:200]

    @staticmethod
    def _post(url: str, body: dict, headers: dict) -> bytes:
        import json
        import urllib.request
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        import urllib.error
        voice_id = (type(self).voice_id() or "").strip() or self.DEFAULT_VOICE
        from .. import languages
        said = respell(text, plain=True) if languages.english() else text     # (her slang respellings are English)
        body = {"text": said, "model_id": self.MODEL,      # "chooom", never "chom"
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                                   "speed": round(0.85 + 0.3 * max(0.0, min(1.0, speed)), 2)}}
        headers = {"xi-api-key": type(self).key().strip()}
        url = "https://api.elevenlabs.io/v1/text-to-speech/{}?output_format=pcm_22050"
        try:
            raw = self._fetch(url.format(voice_id), body, headers)
        except urllib.error.HTTPError as exc:
            detail = self._detail(exc)
            log.warning("speech: ElevenLabs refused (HTTP %s): %s", exc.code, detail)
            low = detail.lower()
            limited = any(w in low for w in ("library", "voice_limit", "voice limit", "free", "subscription",
                                             "custom voices", "not allowed", "upgrade"))
            if exc.code in (400, 402, 403, 422) and limited and voice_id != self.DEFAULT_VOICE:
                try:                     # your plan can't use that voice: her default ElevenLabs voice instead
                    raw = self._fetch(url.format(self.DEFAULT_VOICE), body, headers)
                    log.info("speech: ElevenLabs won't use voice %s on this plan - used the default voice", voice_id)
                    audio = _from_int16(raw[: len(raw) // 2 * 2], 22050)
                    audio.pitched, audio.natural, audio.as_is = True, True, True
                    return audio
                except (urllib.error.HTTPError, OSError):
                    pass
            reason = {401: "the key doesn't work (or it's out of credit)", 402: "out of credit",
                      429: "too many requests / out of credit", 404: "no voice with that ID",
                      422: "no voice with that ID"}.get(exc.code, f"error {exc.code}")
            raise RuntimeError(f"ElevenLabs: {detail or reason}"[:160]) from None
        except OSError as exc:
            raise RuntimeError("ElevenLabs: can't reach it") from exc
        if len(raw) < 64:
            raise RuntimeError("ElevenLabs: sent no sound")
        audio = _from_int16(raw[: len(raw) // 2 * 2], 22050)
        audio.pitched, audio.natural, audio.as_is = True, True, True    # their voice as it is
        return audio


def read_wav(raw: bytes) -> tuple[int, int, int, bytes]:
    """(rate, bytes per sample, channels, sound) from a WAV - also one that was streamed: those say "0 bytes" (or
    a made-up size) for their sound because it wasn't known yet, so everything after the header is the sound.
    Reading the size literally made her say nothing at all."""
    import struct
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise RuntimeError("the voice service sent something that isn't audio")
    pos, rate, width, channels = 12, 0, 0, 0
    while pos + 8 <= len(raw):
        kind, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = pos + 8
        if kind == b"fmt ":
            channels, rate = struct.unpack("<HI", raw[body + 2:body + 8])
            width = struct.unpack("<H", raw[body + 14:body + 16])[0] // 8
        elif kind == b"data":
            end = len(raw) if size in (0, 0xFFFFFFFF) or body + size > len(raw) else body + size
            data = raw[body:end]
            return rate, width, max(1, channels), data[: len(data) // max(1, width * max(1, channels))
                                                      * max(1, width * max(1, channels))]
        pos = body + size + (size & 1)
    raise RuntimeError("the voice service sent audio with no sound in it")


def fish_speed(speed: float) -> float:
    """Your speed setting (0..1, default 0.6) -> Fish's speed: exactly 1.0 (the voice as it is) at the default."""
    return round(max(0.8, min(1.2, 1.0 + (float(speed) - 0.6) * 0.5)), 2)


class FishAudioEngine:
    """Fish Audio's online voices (fish.audio: free to sign up, with free credits for its API) - your API key
    + a voice's ID from its library (fish.audio/m/<ID>), Settings -> Assistant -> Voice.
    Only the line's text is sent, never audio. No key: not offered."""

    PREFIX = "fish: "
    NAME = PREFIX + "your Fish Audio voice"
    URL = "https://api.fish.audio/v1/tts"
    MODEL = "s1"
    key: Callable[[], str] = staticmethod(lambda: "")
    voice_id: Callable[[], str] = staticmethod(lambda: "")

    def __init__(self, fetch=None) -> None:
        self._fetch = fetch or ElevenLabsEngine._post

    def voices(self) -> list[str]:
        return [self.NAME] if (type(self).key() or "").strip() else []

    @staticmethod
    def voice_from(text: str) -> str:
        """A pasted voice link (https://fish.audio/m/abc123/) or the bare ID -> the ID."""
        text = (text or "").strip().rstrip("/")
        if "/m/" in text:
            text = text.split("/m/", 1)[1].split("/", 1)[0]
        return text.split("?", 1)[0]

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        import io
        import urllib.error
        import wave
        # "normal" latency: Fish's full-quality read ("balanced" is quicker but rougher - it sounded off).
        # The speed is your speed setting only (1.0 at the default), steady from line to line.
        body = {"text": text, "format": "wav", "sample_rate": 44100, "latency": "normal", "normalize": True,
                "prosody": {"speed": fish_speed(speed), "volume": 0}}
        voice_id = self.voice_from(type(self).voice_id())
        if voice_id:
            body["reference_id"] = voice_id
        headers = {"Authorization": "Bearer " + type(self).key().strip(), "model": self.MODEL}
        try:
            raw = self._fetch(self.URL, body, headers)
        except urllib.error.HTTPError as exc:
            reason = {401: "the key doesn't work", 402: "out of credit", 403: "out of credit / not allowed",
                      429: "too many requests", 404: "no voice with that ID",
                      400: "it didn't take that voice ID", 422: "it didn't take that voice ID"}.get(exc.code,
                                                                                               f"error {exc.code}")
            raise RuntimeError(f"Fish Audio: {reason}") from None
        except OSError as exc:
            raise RuntimeError("Fish Audio: can't reach it") from exc
        rate, width, channels, frames = read_wav(raw)
        if width != 2:
            raise RuntimeError("Fish Audio: unexpected audio format")
        if not frames:
            raise RuntimeError("Fish Audio: sent no sound")
        samples = np.frombuffer(frames[: len(frames) // 2 * 2], np.int16)
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
        audio = _from_int16(samples.tobytes(), rate)
        audio.pitched, audio.natural, audio.as_is = True, True, True    # their voice as it is: no effects on it
        return audio


ONLINE = (ElevenLabsEngine, FishAudioEngine)
ONLINE_PREFIXES = ("elevenlabs: ", "fish: ")


def is_online(voice: str) -> bool:
    """An online voice (ElevenLabs / Fish Audio): it's played as it comes - Capri's voice options don't apply."""
    return (voice or "").startswith(ONLINE_PREFIXES)


def available_engines() -> list:
    engines = []
    for cls in (KokoroEngine,) + ((SapiEngine, EspeakEngine) if sys.platform == "win32" else (EspeakEngine,)) + \
            (PiperEngine,):
        try:
            engine = cls()
            if engine.voices():
                engines.append(engine)
        except Exception:
            continue   # not installed / no voices: just not offered
    return [ElevenLabsEngine(), FishAudioEngine()] + engines + [BeepEngine()]   # online: once you add a key


class VoiceBox:
    """Picks the engine for a voice name and synthesises with it."""

    def __init__(self) -> None:
        self.engines = available_engines()
        self.last = ("", "")          # (voice that said the last line, a note) - Settings' "Test voice"

    def voices(self) -> list[str]:
        return [v for e in self.engines for v in e.voices()]

    def synthesize(self, text: str, voice: str, speed: float, pitch: float = 0.0) -> Audio:
        if not self.voices():
            raise RuntimeError("no text-to-speech voices available")
        voice = voice if voice and any(voice in e.voices() for e in self.engines) else self.default_voice()
        voice = self.for_language(voice)
        engine = next(e for e in self.engines if voice in e.voices())
        try:
            audio = engine.synthesize(text, voice, speed, pitch)
        except RuntimeError as exc:
            if not isinstance(engine, ONLINE):
                raise
            fallback = self.default_voice()                  # online voice failed: her normal one, and say why
            engine = next(e for e in self.engines if fallback in e.voices())
            audio = engine.synthesize(text, fallback, speed, pitch)
            self.last = (fallback, f"{exc} - used her normal voice")
            return audio
        self.last = (voice, "")
        return audio

    def for_language(self, voice: str) -> str:
        """Your voice if it speaks your language; else one that does: her neural voice (Spanish, French, Italian,
        Portuguese), a Windows voice for that language, then espeak-ng. Online voices and beeps speak them all."""
        from .. import languages
        code = languages.current()
        if code == "en" or voice.startswith((ElevenLabsEngine.PREFIX, FishAudioEngine.PREFIX, BeepEngine.PREFIX)):
            return voice
        if voice.startswith(KokoroEngine.PREFIX) and KokoroEngine.speaks(code):
            return voice
        for engine in self.engines:
            if isinstance(engine, KokoroEngine) and KokoroEngine.speaks(code) and engine.voices():
                return engine.voices()[0]
        for engine in self.engines:
            if isinstance(engine, SapiEngine):
                try:
                    found = engine.voice_for(code)
                except Exception:
                    found = ""
                if found:
                    return found
        for engine in self.engines:
            if isinstance(engine, EspeakEngine) and engine.voices():
                return engine.voices()[0]
        return voice

    def warm_up(self, voice: str = "") -> None:
        """Load the neural voice now (on the speech thread, ~1 s) so her first line isn't late."""
        for engine in self.engines:
            if isinstance(engine, KokoroEngine) and engine.voices():
                try:
                    engine._model()
                except Exception:
                    pass   # reported when she first tries to speak

    def default_voice(self) -> str:
        """Her neural voice if installed, else another neural voice, else a female Windows voice."""
        voices = [v for v in self.voices()
                  if not v.startswith((BeepEngine.PREFIX, ElevenLabsEngine.PREFIX, FishAudioEngine.PREFIX))] \
            or self.voices()
        capri = KokoroEngine.PREFIX + KokoroEngine.CAPRI
        if capri in voices:
            return capri
        piper = [v for v in voices if v.startswith(PiperEngine.PREFIX)]
        if piper:
            return piper[0]
        for hint in ("zira", "hazel", "susan", "eva", "aria", "jenny", "female"):
            for v in voices:
                if hint in v.lower():
                    return v
        return voices[0]


def download_kokoro(folder=None, progress=None) -> None:
    """Fetch her neural voice (~120 MB, once) from the kokoro-onnx releases on GitHub.

    ``progress(file_name, done_bytes, total_bytes)`` is called as it goes. Files are written
    as .part and renamed at the end, so an interrupted download never looks installed.
    """
    import urllib.request
    folder = folder or kokoro_folder()
    folder.mkdir(parents=True, exist_ok=True)
    for name in (KOKORO_VOICES, KOKORO_MODEL):
        target = folder / name
        if target.exists():
            continue
        part = target.with_name(name + ".part")
        with urllib.request.urlopen(KOKORO_URL + name, timeout=30) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(1 << 16):
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(name, done, total)
        part.replace(target)
