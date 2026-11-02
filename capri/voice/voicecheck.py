"""Was that a person saying "Capri", or a sound? Discord pings, notification chimes and game
sounds can fool the wake word recogniser now and then. A spoken "Capri" and a chime look very
different, though:

* a chime is one or two pure tones that hold their pitch, high up, with nothing in between;
* a voice has breathy noise (the k and p in "Capri"), a pitch that moves, and most of its
  energy low down where voices live (roughly 100-1000 Hz).

So the audio of the wake word itself is checked; a chime is rejected. All on this PC, on the
second of audio she already has - nothing is kept or sent.
"""

from __future__ import annotations

import numpy as np

MIN_SECONDS = 0.18


def voice_check(pcm: bytes, rate: int) -> tuple[bool, str]:
    """(looks like a voice, why not). Errs towards "voice" when unsure, so real wakes still work."""
    x = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype=np.int16).astype(np.float32)
    if len(x) < rate * MIN_SECONDS:
        return True, ""                                   # too short to judge: let the recogniser decide
    frame, hop = int(rate * 0.032), int(rate * 0.010)
    window = np.hanning(frame).astype(np.float32)
    frames = [x[i:i + frame] * window for i in range(0, len(x) - frame, hop)]
    spec = np.abs(np.fft.rfft(np.array(frames), axis=1)) ** 2
    freqs = np.fft.rfftfreq(frame, 1 / rate)
    band = (freqs >= 80) & (freqs <= 5000)
    spec = spec[:, band] + 1e-9
    f = freqs[band]
    energy = spec.sum(1)
    loud = energy > energy.max() * 0.25                   # the sound itself, not the room around it
    if loud.sum() < 4:
        return True, ""
    s = spec[loud]
    flatness = np.exp(np.mean(np.log(s), 1)) / np.mean(s, 1)            # 0 = pure tones, 1 = noise
    top = np.median(np.sort(s, 1)[:, -6:].sum(1) / s.sum(1))            # energy in its strongest few frequencies
    peaks = np.median([(row > row.max() * 0.1).sum() for row in s])     # how many frequencies stand out
    e = energy[loud]
    fading = (np.diff(np.log(e)) < 0.05).mean() if len(e) > 2 else 0.0  # only ever dying away after the hit
    signs = [top > 0.88, flatness.max() < 0.02, fading > 0.86, peaks <= 4]
    # A voice spreads over many frequencies (its harmonics, the k and p); a chime is a few pure
    # tones - true even through a room's echo and a noisy mic.
    if (top > 0.85 and peaks <= 5) or sum(signs) >= 3:
        return False, "a chime / ping, not a voice"
    return True, ""
