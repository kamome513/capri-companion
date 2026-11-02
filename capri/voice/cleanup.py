"""Cleaning up the microphone before her ears hear it - for quiet or cheap mics, mics far away,
and noisy rooms. Runs on each 0.1 s chunk, a fraction of a millisecond, all on this PC.

* rumble filter: cuts the low hum / desk thumps below ~80 Hz that drown words on cheap mics;
* level: a quiet mic (or you far from it) is turned up to a steady level, a loud one down a bit,
  smoothly, so words come through the same however you sound;
* hiss gate: background noise between words is turned down, so she doesn't hear "words" in it.
"""

from __future__ import annotations

import numpy as np

TARGET = 3200.0            # the speech level she hears best (16-bit RMS)
MAX_GAIN = 10.0            # never boost more than this (quiet mics), never cut below 0.4
MIN_GAIN = 0.4


class MicCleaner:
    def __init__(self, rate: int) -> None:
        self.rate = rate
        self.gain = 1.0
        self.noise = 300.0                     # running guess of the room's noise level
        self.speech = TARGET                   # running guess of your speaking level
        self._x1 = 0.0                         # rumble filter's memory
        self._y1 = 0.0
        rc = 1.0 / (2 * np.pi * 80.0)
        self._a = rc / (rc + 1.0 / rate)

    def __call__(self, chunk: bytes) -> bytes:
        if len(chunk) % 2 or not chunk:
            return chunk
        x = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        x = self._highpass(x)
        level = float(np.sqrt(np.mean(x * x))) + 1e-3
        # the room: follows quiet chunks quickly down, loud ones only slowly up
        self.noise = 0.9 * self.noise + 0.1 * level if level < self.noise * 1.5 else self.noise * 1.002
        talking = level > max(self.noise * 2.5, 120.0)
        if talking:
            self.speech = 0.85 * self.speech + 0.15 * level
            want = min(MAX_GAIN, max(MIN_GAIN, TARGET / self.speech))
            self.gain += (want - self.gain) * 0.25          # smooth: no pumping
        y = x * self.gain
        if not talking:
            y *= 0.35                                          # the hiss between words, turned down
        y = np.tanh(y / 30000.0) * 30000.0                     # never clips harshly
        return y.astype(np.int16).tobytes()

    def _highpass(self, x: np.ndarray) -> np.ndarray:
        out = np.empty_like(x)
        a, x1, y1 = self._a, self._x1, self._y1
        for i in range(len(x)):                                # one pole: ~1600 samples per chunk, cheap
            y1 = a * (y1 + x[i] - x1)
            x1 = x[i]
            out[i] = y1
        self._x1, self._y1 = x1, y1
        return out
