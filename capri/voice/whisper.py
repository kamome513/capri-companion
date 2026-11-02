"""Better hearing for accents: Whisper (faster-whisper), optional.

Vosk (her normal ears) is quick and light but trained mostly on American English, so accents
trip it up. Whisper was trained on a huge range of accents and is much better at them. With
Settings -> Wake word -> Hearing set to "Whisper" (and it installed: setup_hearing.bat), the
wake word is still caught by Vosk, but what you said after it is re-heard by Whisper on your PC.
Nothing leaves your PC. Its model (~150 MB, "base.en") downloads once, the first time it's used.

It's nudged towards her words (Capri, your apps' names, her commands) with a prompt, so
"open Discord" isn't heard as "open this cord".
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("capri")

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
MODELS = ROOT / "models" / "whisper"
SIZES = {"base.en": "Good (about 150 MB)", "small.en": "Best for strong accents (about 480 MB, slower)",
         "distil-small.en": "Best for accents, quicker (about 330 MB)"}
HINT = ("Capri, open, close, play, search, click, minimise, Discord, Spotify, Opera, Steam, YouTube, Twitch, "
        "screenshot, highlight, drone mode, join call, leave call, mute me, deafen me, stream my screen, "
        "shut down my computer, set a timer")


def installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


class WhisperEars:
    def __init__(self, size: Callable[[], str] = lambda: "base.en", hints: Callable[[], list[str]] = lambda: []) -> None:
        self.size, self.hints = size, hints
        self._model = None
        self._loaded = ""
        self._lock = threading.Lock()

    def _load(self):
        size = self.size() if self.size() in SIZES else "base.en"
        if self._model is None or self._loaded != size:
            from faster_whisper import WhisperModel
            MODELS.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(size, device="cpu", compute_type="int8", download_root=str(MODELS))
            self._loaded = size
            log.info("hearing: Whisper %s loaded", size)
        return self._model

    def transcribe(self, pcm: bytes, rate: int) -> str:
        """16-bit mono audio -> what was said ("" if nothing). Blocking (about a second)."""
        if not pcm:
            return ""
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if rate != 16000:                                  # Whisper wants 16 kHz
            n = int(len(audio) * 16000 / rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
        if len(audio) < 16000 * 0.3:
            return ""
        hint = HINT + (", " + ", ".join(self.hints()[:40]) if self.hints() else "")
        with self._lock:
            model = self._load()
            segments, _info = model.transcribe(audio, language="en", beam_size=5, vad_filter=True,
                                               initial_prompt=hint, condition_on_previous_text=False,
                                               temperature=(0.0, 0.2, 0.4))     # retries unclear words
            text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
