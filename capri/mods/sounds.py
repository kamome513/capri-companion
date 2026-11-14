"""Sound packs: a short sound for her events (wake, done, error, pat, throw, greet, click) from the enabled pack.
Played quietly on its own (it never cuts her voice off); 16-bit PCM WAV only, up to a few seconds."""

from __future__ import annotations

import logging
import threading
import wave
from pathlib import Path

log = logging.getLogger("capri")
MAX_SECONDS = 4.0
_cache: dict[str, tuple] = {}


def _load(path: Path):
    key = str(path)
    if key not in _cache:
        import numpy as np
        with wave.open(key, "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError("only 16-bit WAV sounds")
            rate, ch = w.getframerate(), w.getnchannels()
            frames = w.readframes(min(w.getnframes(), int(rate * MAX_SECONDS)))
        x = np.frombuffer(frames, "<i2").astype(np.float32) / 32768.0
        if ch > 1:
            x = x.reshape(-1, ch).mean(1)
        _cache[key] = (x, rate)
    return _cache[key]


def play(event: str, volume: float = 0.6, enabled: bool = True) -> bool:
    """Play the enabled sound pack's sound for `event` (if it has one). True if a sound started."""
    from .effects import EFFECTS
    path = EFFECTS.sounds.get(event)
    if not enabled or path is None:
        return False

    def run() -> None:
        try:
            import sounddevice as sd
            x, rate = _load(path)
            sd.play(x * max(0.0, min(1.0, volume)), rate, blocking=False)
        except Exception as exc:
            log.info("mods: couldn't play the %s sound: %s", event, exc)
    threading.Thread(target=run, daemon=True, name="capri-sfx").start()
    return True
