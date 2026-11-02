"""The shutdown "cyberpsychosis": after you say yes to shutting down, your screen loses it.

About 3.5 seconds, on every monitor, then the real shutdown:
    0.0-1.0  your screen starts glitching - torn slices, red/cyan split, rising static
    1.0-2.6  full psychosis - shaking, red heartbeat pulses, inverted flickers and warnings
             (CYBERPSYCHOSIS DETECTED, NEURAL LINK UNSTABLE, SANDEVISTAN OVERLOAD...)
    2.6-3.3  FLATLINE - an old-TV collapse to a line, a dot, then black
    3.4      the PC shuts down (if Windows refuses, the screen comes back and she says so)

It's drawn on a snapshot of your screen, so nothing on the PC is touched until the
shutdown itself. A matching glitch / flatline sound plays (at her voice volume).
"""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from . import theme

GLITCH_END = 1.0
PSYCHO_END = 2.6
COLLAPSE_END = 3.3
TOTAL = 3.45
WARNINGS = ["CYBERPSYCHOSIS DETECTED", "NEURAL LINK UNSTABLE", "SANDEVISTAN OVERLOAD", "ERR 0xC4PR1 // CHROME REJECTED",
            "MAXTAC NOTIFIED", "SYSTEM INTEGRITY 3%", "CAN'T STOP. WON'T STOP.", "WAKE UP, CHOOM"]


def _channels(img: QImage) -> tuple[QImage, QImage]:
    """(red-only, cyan-only) copies of a screenshot, at half size - for the colour split."""
    small = img.scaled(max(1, img.width() // 2), max(1, img.height() // 2),
                       Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    small = small.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = small.width(), small.height()
    a = np.frombuffer(small.constBits(), np.uint8).reshape(h, small.bytesPerLine() // 4, 4)[:, :w].copy()
    red, cyan = a.copy(), a.copy()
    red[..., 1:3] = 0
    cyan[..., 0] = 0
    return (QImage(red.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy(),
            QImage(cyan.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy())


class PsychosisWindow(QWidget):
    """Covers one monitor with its own glitching snapshot."""

    def __init__(self, geometry: QRect, shot: QPixmap) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(geometry)
        self.shot = shot.toImage() if not shot.isNull() else QImage()
        if self.shot.isNull():                                  # no snapshot: glitch a dark screen instead
            self.shot = QImage(geometry.size(), QImage.Format.Format_RGB32)
            self.shot.fill(QColor(12, 10, 16))
        self.red, self.cyan = _channels(self.shot)
        self.t = 0.0
        self._rng = random.Random()
        self._np = np.random.default_rng()
        self._noise: QImage | None = None
        self._font = QFont(theme.MONO_FAMILIES[0])
        self._font.setFamilies(theme.MONO_FAMILIES)
        self._font.setBold(True)

    def _static(self) -> QImage:
        w, h = max(1, self.width() // 6), max(1, self.height() // 6)
        grey = self._np.integers(0, 256, (h, w), dtype=np.uint8)
        rgba = np.dstack([grey, grey, grey, np.full_like(grey, 255)])
        return QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        t, rng, W, H = self.t, self._rng, self.width(), self.height()
        full = QRectF(0, 0, W, H)
        p.fillRect(self.rect(), Qt.GlobalColor.black)
        if t >= COLLAPSE_END:                                   # flatlined: black
            p.end()
            return
        collapse = max(0.0, (t - PSYCHO_END) / (COLLAPSE_END - PSYCHO_END))
        heat = min(1.0, t / GLITCH_END) if t < GLITCH_END else 1.0
        if collapse > 0:                                        # old-TV off: squash to a line, then a dot
            sy = max(0.004, 1 - collapse * 1.6) if collapse < 0.62 else 0.004
            sx = 1.0 if collapse < 0.62 else max(0.0, 1 - (collapse - 0.62) / 0.38)
            p.translate(W / 2, H / 2)
            p.scale(sx, sy)
            p.translate(-W / 2, -H / 2)
        shake = QPointF(rng.uniform(-1, 1), rng.uniform(-1, 1)) * (4 + 18 * heat) * (1 if t > 0.25 else 0.2)
        p.drawImage(full.translated(shake), self.shot)
        # torn slices: bands of the screen jump sideways
        for _ in range(int(2 + 16 * heat)):
            y = rng.uniform(0, H)
            h = rng.uniform(4, 40 + 80 * heat)
            dx = rng.uniform(-1, 1) * (20 + 160 * heat)
            src = QRectF(0, y, W, h)
            p.drawImage(src.translated(dx, 0), self.shot, QRectF(src.x() * self.shot.width() / W,
                                                                  src.y() * self.shot.height() / H,
                                                                  self.shot.width(), h * self.shot.height() / H))
        # red / cyan colour split
        split = 3 + 26 * heat * (0.6 + 0.4 * math.sin(t * 31))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.setOpacity(0.55 * heat)
        p.drawImage(full.translated(split, 0), self.red)
        p.drawImage(full.translated(-split, 0), self.cyan)
        p.setOpacity(1.0)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # static
        if self._noise is None or rng.random() < 0.7:
            self._noise = self._static()
        p.setOpacity(0.03 + 0.32 * heat * heat)
        p.drawImage(full, self._noise)
        p.setOpacity(1.0)
        if t >= GLITCH_END:
            beat = (math.sin(t * 2 * math.pi * 2.2) + 1) / 2 ** 1      # a racing heartbeat
            p.fillRect(full, QColor(236, 16, 70, int(40 + 90 * beat * beat)))
            if rng.random() < 0.12:                                    # inverted flicker
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
                p.fillRect(full, Qt.GlobalColor.white)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for _ in range(rng.randint(1, 3)):                         # the warnings
                text = rng.choice(WARNINGS)
                self._font.setPixelSize(int(H * rng.uniform(0.035, 0.08)))
                p.setFont(self._font)
                x, y = rng.uniform(0, W * 0.55), rng.uniform(H * 0.1, H * 0.9)
                for off, color in ((4, QColor(0, 230, 255, 200)), (-4, QColor(255, 30, 90, 230)), (0, QColor(255, 240, 245))):
                    p.setPen(QPen(color))
                    p.drawText(QPointF(x + off, y), text)
        if t >= PSYCHO_END - 0.25:                                     # FLATLINE
            self._font.setPixelSize(int(H * 0.16))
            p.setFont(self._font)
            p.setPen(QColor(255, 30, 90))
            p.drawText(full, Qt.AlignmentFlag.AlignCenter, "FLATLINE")
        p.end()


def _sound(volume: float) -> None:
    """Glitch bursts, a falling whine, then the flatline tone. Best-effort: silent if no audio."""
    try:
        import sounddevice as sd
        rate = 22050
        n = int(rate * COLLAPSE_END)
        t = np.arange(n) / rate
        rng = np.random.default_rng()
        gate = (rng.random(int(COLLAPSE_END * 40)) < 0.45).repeat(rate // 40)[:n]
        noise = rng.uniform(-1, 1, n) * np.pad(gate, (0, max(0, n - len(gate))))[:n] * np.minimum(1, t / 1.0)
        whine = np.sin(2 * np.pi * (1800 - 1500 * np.minimum(1, t / PSYCHO_END)) * t) * 0.25
        flat_start = int(PSYCHO_END * rate)
        flat = np.zeros(n)
        flat[flat_start:] = np.sin(2 * np.pi * 1000 * t[flat_start:]) * 0.35
        x = (0.35 * noise + whine * (t < PSYCHO_END) + flat).astype(np.float32)
        sd.play(x * float(volume) * 0.6, rate)
    except Exception:
        pass


class PsychosisShow(QObject):
    def __init__(self, volume: Callable[[], float] = lambda: 0.6, sound: bool = True) -> None:
        super().__init__()
        self.volume, self.sound = volume, sound
        self.windows: list[PsychosisWindow] = []
        self.active = False
        self._then: Callable[[], None] | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def play(self, then: Callable[[], None]) -> None:
        """Run the show on every monitor, then `then` (the shutdown)."""
        if self.active:
            return
        self.windows = []
        for screen in QGuiApplication.screens():
            shot = screen.grabWindow(0)                 # the screen as it is right now
            self.windows.append(PsychosisWindow(screen.geometry(), shot))
        for w in self.windows:
            w.show()
            w.raise_()
        if self.sound:
            threading.Thread(target=_sound, args=(self.volume(),), daemon=True).start()
        self.active, self._then, self._start = True, then, time.monotonic()
        self._timer.start()

    def _tick(self) -> None:
        t = time.monotonic() - self._start
        for w in self.windows:
            w.t = t
            w.update()
        if t >= TOTAL and self._then is not None:
            self._timer.stop()
            then, self._then = self._then, None
            then()                                      # the real shutdown; the screen stays black

    def abort(self) -> None:
        """Shutdown didn't happen (Windows refused): give the screen back."""
        self._timer.stop()
        self._then = None
        for w in self.windows:
            w.hide()
            w.deleteLater()
        self.windows = []
        self.active = False
