"""Best hearing for heavy accents: NVIDIA's Parakeet speech model, on your PC (sherpa-onnx).

Vosk (her normal ears) is quick and light but was trained mostly on American English.
Parakeet TDT 0.6B was trained on a huge range of English speakers and is one of the most
accurate open speech models there is - much better with strong accents, mumbling and noisy mics.

How it's used: the wake word is still caught by Vosk (it's tiny and always listening). What you
say *after* "Hey Capri" is re-heard by Parakeet from the same recording - like Whisper, but more
accurate and quicker. Nothing leaves your PC: the model (about 480 MB) downloads once from
the sherpa-onnx project's GitHub releases into %LOCALAPPDATA%\\Capri\\models, and runs offline.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import shutil
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

from .model import MODELS_DIR, user_models_dir

log = logging.getLogger("capri")

MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"           # English
MULTI_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"           # 25 European languages (English too)
RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
MODEL_URL = f"{RELEASES}{MODEL_NAME}.tar.bz2"
MODEL_MB = 480
MULTI_MB = 490
FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")


def model_name(language: str | None = None) -> str:
    """Which Parakeet she needs: v2 for English (smaller), v3 for any of the other 24 languages."""
    from .. import languages
    return MODEL_NAME if (language or languages.current()) == "en" else MULTI_NAME


def model_mb(language: str | None = None) -> int:
    return MODEL_MB if model_name(language) == MODEL_NAME else MULTI_MB


def installed() -> bool:
    """The sherpa-onnx engine is there (it's built into Capri.exe; pip install sherpa-onnx otherwise)."""
    return importlib.util.find_spec("sherpa_onnx") is not None


def _complete(folder: Path) -> bool:
    return all((folder / f).is_file() for f in FILES)


def find_model(language: str | None = None) -> Path | None:
    """The model for your language (in English, the multilingual one does too if that's what you have)."""
    override = os.environ.get("CAPRI_PARAKEET_MODEL")
    if override:
        return Path(override) if _complete(Path(override)) else None
    wanted = model_name(language)
    names = [wanted] + ([MULTI_NAME] if wanted == MODEL_NAME else [])
    for name in names:
        for base in (user_models_dir(), MODELS_DIR):
            if _complete(base / name):
                return base / name
    return None


def ready(language: str | None = None) -> bool:
    return installed() and find_model(language) is not None


def download(progress: Callable[[int, int], None] | None = None, dest: Path | None = None,
             url: str | None = None, opener=urllib.request.urlopen, language: str | None = None) -> Path:
    """Fetch and unpack the model for your language (blocking). progress(done_bytes, total_bytes)."""
    name = model_name(language)
    url = url or f"{RELEASES}{name}.tar.bz2"
    dest = dest or user_models_dir()
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        archive = Path(tmp) / "model.tar.bz2"
        with opener(url, timeout=60) as response, open(archive, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        root = Path(tmp) / "unpacked"
        with tarfile.open(archive, "r:bz2") as tar:
            members = []
            for m in tar.getmembers():          # nothing that escapes the folder, no links, no test clips
                parts = Path(m.name).parts
                if m.name.startswith("/") or ".." in parts or not (m.isfile() or m.isdir()):
                    raise RuntimeError(f"unsafe path in archive: {m.name}")
                if "test_wavs" in parts:
                    continue
                members.append(m)
            tar.extractall(root, members=members)
        inner = next((p for p in root.rglob("*") if p.is_dir() and _complete(p)), None)
        if inner is None:
            raise RuntimeError("the download doesn't contain the Parakeet model")
        target = dest / name
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(inner), target)
    log.info("hearing: Parakeet model downloaded to %s", target)
    return target


class ParakeetEars:
    """transcribe(pcm, rate) -> text, the same shape as WhisperEars (service.refine)."""

    def __init__(self, folder: Callable[[], Path | None] = find_model, threads: int | None = None) -> None:
        self.folder = folder
        self.threads = threads or max(1, min(4, (os.cpu_count() or 2) // 2))
        self._recognizer = None
        self._loaded_from = None
        self._cues: dict[str, object] = {}
        self._lock = threading.Lock()
        self.resting = False              # in a game: model unloaded (~900 MB back), Vosk alone hears you

    def _load(self):
        folder = self.folder()
        if self._recognizer is not None and folder != self._loaded_from:
            self._recognizer = None                                # you changed language: the other model
        if self._recognizer is None:
            if folder is None:
                raise RuntimeError("the Parakeet model isn't downloaded yet")
            import sherpa_onnx
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(folder / "encoder.int8.onnx"), decoder=str(folder / "decoder.int8.onnx"),
                joiner=str(folder / "joiner.int8.onnx"), tokens=str(folder / "tokens.txt"),
                num_threads=self.threads, model_type="nemo_transducer", decoding_method="greedy_search")
            self._loaded_from = folder
            log.info("hearing: Parakeet loaded (%d threads)", self.threads)
        return self._recognizer

    def preload(self) -> None:
        """Load in the background so the first command isn't slow."""
        threading.Thread(target=self._safe_load, daemon=True, name="parakeet-load").start()

    def _safe_load(self) -> None:
        if self.resting:
            return
        try:
            with self._lock:
                self._load()
        except Exception as exc:
            log.warning("hearing: Parakeet couldn't load: %s", exc)

    def rest(self, on: bool) -> None:
        """Game mode: give its memory to the game (Vosk keeps hearing you), and load again after."""
        self.resting = on
        if on:
            with self._lock:
                self._recognizer = None
            log.info("hearing: Parakeet resting while you play (memory freed)")
        else:
            self.preload()

    def transcribe(self, pcm: bytes, rate: int) -> str:
        """16-bit mono audio -> what was said ("" if nothing = keep Vosk's). Blocking (well under a second).
        In another language, a spoken cue in that language goes first so the multilingual model knows which
        language a short command is in (it guesses English otherwise); only what came after the cue is kept."""
        if not pcm or self.resting:
            return ""
        audio = to_16k(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0, rate)
        if len(audio) < 16000 * 0.3:
            return ""
        with self._lock:
            recognizer = self._load()
            cue = self._cue()
            if cue is not None:
                gap = np.zeros(int(0.7 * 16000), np.float32)
                cut = (len(cue) + len(gap) / 2) / 16000
                stream = recognizer.create_stream()
                stream.accept_waveform(16000, np.concatenate([cue, gap, audio]))
                recognizer.decode_stream(stream)
                after = after_cue(stream.result, cut)
                if after:
                    return plain(after)
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, audio)
            recognizer.decode_stream(stream)
            text = stream.result.text
        return plain(text)

    def _cue(self):
        """The spoken cue for your language (16 kHz), made once with espeak-ng. None in English / if it can't."""
        from .. import languages
        code = languages.current()
        sentence = languages.CUES.get(code)
        if sentence is None or self._loaded_from is None or self._loaded_from.name != MULTI_NAME:
            return None
        if code not in self._cues:
            try:
                from ..speech.engines import EspeakEngine
                spoken = EspeakEngine().synthesize(sentence, "espeak: " + code, 0.1)
                self._cues[code] = to_16k(np.asarray(spoken.samples, np.float32), spoken.rate)
            except Exception as exc:
                log.info("hearing: no spoken cue for %s (%s) - hearing without it", code, exc)
                self._cues[code] = None
        return self._cues[code]


def to_16k(audio, rate: int):
    if rate == 16000:
        return audio.astype(np.float32)
    n = int(len(audio) * 16000 / rate)
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)


def after_cue(result, cut: float) -> str:
    """The words that start after `cut` seconds (the cue's end) - from the model's per-token times."""
    tokens, times = list(getattr(result, "tokens", []) or []), list(getattr(result, "timestamps", []) or [])
    if not tokens or len(tokens) != len(times):
        return ""
    return "".join(t for t, at in zip(tokens, times) if at >= cut).replace("\u2581", " ").strip()


def plain(text: str) -> str:
    """'Hey Capri, open Discord.' -> 'hey capri open discord' (how Vosk writes it, so the rest of
    her command matching sees the same thing whichever ears heard it)."""
    text = re.sub(r"[^\w' ]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip(" '")
