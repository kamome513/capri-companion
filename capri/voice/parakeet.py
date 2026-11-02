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

MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_NAME}.tar.bz2"
MODEL_MB = 480
FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")


def installed() -> bool:
    """The sherpa-onnx engine is there (it's built into Capri.exe; pip install sherpa-onnx otherwise)."""
    return importlib.util.find_spec("sherpa_onnx") is not None


def _complete(folder: Path) -> bool:
    return all((folder / f).is_file() for f in FILES)


def find_model() -> Path | None:
    override = os.environ.get("CAPRI_PARAKEET_MODEL")
    if override:
        return Path(override) if _complete(Path(override)) else None
    for base in (user_models_dir(), MODELS_DIR):
        if _complete(base / MODEL_NAME):
            return base / MODEL_NAME
    return None


def ready() -> bool:
    return installed() and find_model() is not None


def download(progress: Callable[[int, int], None] | None = None, dest: Path | None = None,
             url: str = MODEL_URL, opener=urllib.request.urlopen) -> Path:
    """Fetch and unpack the model (blocking). progress(done_bytes, total_bytes)."""
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
        target = dest / MODEL_NAME
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
        self._lock = threading.Lock()
        self.resting = False              # in a game: model unloaded (~900 MB back), Vosk alone hears you

    def _load(self):
        if self._recognizer is None:
            folder = self.folder()
            if folder is None:
                raise RuntimeError("the Parakeet model isn't downloaded yet")
            import sherpa_onnx
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(folder / "encoder.int8.onnx"), decoder=str(folder / "decoder.int8.onnx"),
                joiner=str(folder / "joiner.int8.onnx"), tokens=str(folder / "tokens.txt"),
                num_threads=self.threads, model_type="nemo_transducer", decoding_method="greedy_search")
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
        """16-bit mono audio -> what was said ("" if nothing = keep Vosk's). Blocking (well under a second)."""
        if not pcm or self.resting:
            return ""
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < rate * 0.3:
            return ""
        if rate != 16000:                                      # the model wants 16 kHz
            n = int(len(audio) * 16000 / rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
            rate = 16000
        with self._lock:
            recognizer = self._load()
            stream = recognizer.create_stream()
            stream.accept_waveform(rate, audio)
            recognizer.decode_stream(stream)
            text = stream.result.text
        return plain(text)


def plain(text: str) -> str:
    """'Hey Capri, open Discord.' -> 'hey capri open discord' (how Vosk writes it, so the rest of
    her command matching sees the same thing whichever ears heard it)."""
    text = re.sub(r"[^\w' ]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip(" '")
