"""Capri's voice: synthesise -> style -> play, on a background thread.

While she talks:
* ``started`` carries per-frame loudness so the UI can animate her mouth,
  the glitch effect and the panel's voice bars in sync with the audio;
* ``speaking_changed(True)`` tells the microphone service to ignore input,
  so she never hears (and answers) herself.
"""

from __future__ import annotations

import logging

import queue
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from .. import emotions, personality
from ..settings import Settings
from .effects import LEVEL_FRAME, apply_style, apply_tone, intonation, levels

ECHO_TAIL = 0.35   # keep the mic deaf this long after she stops (room echo)
MASTER_GAIN = 0.7  # she's a desktop companion, not an alarm: even 100% volume stays gentle
PITCH_RANGE = 12   # semitones across the pitch slider (0.5 = the voice's own pitch)


def prosody(settings: Settings, emotion: str) -> tuple[float, float, float]:
    """(speed 0..1, pitch in semitones, gain) for a line said with this emotion."""
    emo = emotions.get(emotion)
    lift, brighter = personality.get(getattr(settings, "personality", "edgerunner")).voice   # energetic
    speed = min(1.0, max(0.0, settings.speech_speed + lift + (emo.rate - 1.0) * 2.5))
    pitch = (settings.speech_pitch - 0.5) * PITCH_RANGE + emo.pitch + brighter
    gain = settings.speech_volume * emo.gain * MASTER_GAIN
    return speed, pitch, gain


# feelings that make her voice go up and down more (or less)
EMOTION_LIFT = {"happy": 1.2, "playful": 1.25, "surprised": 1.4, "angry": 1.15, "smirk": 1.05, "sad": 0.6,
                "serious": 0.7, "neutral": 1.0, "confused": 1.1}


def split_sentences(text: str, short: int = 60) -> list[str]:
    """'Opened Discord. Want music too?' -> two parts. Short sentences stay together (fewer gaps)."""
    import re
    pieces = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    parts: list[str] = []
    for piece in pieces:
        if parts and (len(parts[-1]) < short or len(piece) < 12):
            parts[-1] = f"{parts[-1]} {piece}"
        else:
            parts.append(piece)
    return parts or [text]


def speech_chunks(text: str, first: int = 45) -> list[str]:
    """split_sentences, but the first chunk is kept short (its first sentence, or up to a comma
    if that's long) - the voice engine makes short audio faster, so she starts talking sooner."""
    import re
    pieces = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    if not pieces:
        return [text]
    head, rest = pieces[0], " ".join(pieces[1:])
    if len(head) > first:
        m = re.search(r"^(.{12,}?[,;:\u2014])\s+(.+)$", head)
        if m and len(m.group(1)) <= len(head) - 8:
            head, rest = m.group(1), (m.group(2) + " " + rest).strip()
    return [head] + (split_sentences(rest) if rest else [])


mic_device: Callable[[], str] = lambda: ""     # "Her voice in your mic": a second output (a virtual cable)


def output_devices() -> list[str]:
    """Names of the PC's speakers / headphones / virtual cables (for "Her voice in your mic")."""
    try:
        import sounddevice as sd
        names = []
        for d in sd.query_devices():
            if d.get("max_output_channels", 0) > 0 and d["name"] not in names:
                names.append(d["name"])
        return names
    except Exception:
        return []


def _play_on(name: str, samples, rate: int) -> Callable[[], None]:
    """Also play her line on the device called `name` (resampled to what it wants). Returns stop()."""
    if not name:
        return lambda: None
    import numpy as np
    import sounddevice as sd
    index = next((i for i, d in enumerate(sd.query_devices())
                  if d["name"] == name and d.get("max_output_channels", 0) > 0), None)
    if index is None:
        return lambda: None
    target = int(sd.query_devices(index).get("default_samplerate") or rate)
    data = np.asarray(samples, dtype=np.float32).reshape(-1)
    if target != rate and len(data):
        n = int(len(data) * target / rate)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)
    stop = threading.Event()

    def run() -> None:
        try:
            with sd.OutputStream(device=index, samplerate=target, channels=1, dtype="float32") as out:
                block = max(256, target // 50)
                for at in range(0, len(data), block):
                    if stop.is_set():
                        break
                    out.write(data[at:at + block].reshape(-1, 1))
        except Exception as exc:
            log.info("speech: couldn't play on %r: %s", name, exc)
    threading.Thread(target=run, daemon=True, name="capri-voice-mic").start()
    return stop.set


def _sounddevice_player(samples, rate):
    import sounddevice as sd
    sd.play(samples, rate)
    try:
        also = _play_on(mic_device(), samples, rate)       # her voice in your mic, too
    except Exception as exc:
        log.info("speech: no second output: %s", exc)
        also = lambda: None                              # noqa: E731

    def stop() -> None:
        sd.stop()
        also()
    return stop


log = logging.getLogger("capri")

class Speaker(QObject):
    started = Signal(str, list, float, float)   # text, levels, seconds per level, duration
    began = Signal(int)                         # line number (from say()): her voice for it just started -
                                                # or it never will (failed / nothing to say). Shows the text then.
    finished = Signal()
    speaking_changed = Signal(bool)
    failed = Signal(str)
    spoke = Signal(str, str)                    # which voice said the last line (and a note) - "Test voice"
    _callback = Signal(object)                  # runs "then" callbacks on the UI thread

    def __init__(self, settings: Settings, voicebox_factory: Callable, player=_sounddevice_player,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        super().__init__()
        self._callback.connect(self._run_callback)
        self.settings = settings
        self._voicebox_factory = voicebox_factory
        self._player = player
        self._sleep = sleep
        self._queue: queue.Queue = queue.Queue()
        self._interrupt = threading.Event()
        self._outstanding = 0           # lines queued or being said (synthesis included)
        self.line = 0                   # number of the last line given to say() (see began)
        self._emotion = "neutral"
        self._began = False
        self._count_lock = threading.Lock()
        self.voicebox = None
        self.ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="capri-speech", daemon=True)
        self._thread.start()            # last: the thread uses everything above

    # -- UI thread -------------------------------------------------------------------
    def say(self, text: str, then: Callable[[], None] | None = None, emotion: str = "neutral",
            force: bool = False) -> bool:
        """Speak ``text`` (interrupting anything she's saying). False = not spoken.
        force: even with spoken replies off (Settings' "Test voice")."""
        if not text.strip() or not (self.settings.speech_enabled or force):
            return False
        self._interrupt.set()
        reload, dropped = False, 0
        while not self._queue.empty():
            old = self._queue.get_nowait()
            reload |= old == "reload"                         # drop old lines, never a voice reload
            dropped += isinstance(old, tuple)
        if reload:
            self._queue.put("reload")
        with self._count_lock:
            self._outstanding = max(0, self._outstanding - dropped) + 1
        self.line += 1
        self._queue.put((text, then, emotion, self.line))
        return True

    def busy(self) -> bool:
        """Still got something to say - being synthesised or played. (The panel waits for this
        before going back to "waiting for the wake word".)"""
        return self._outstanding > 0

    def stop(self) -> None:
        self._interrupt.set()

    def reload_voices(self) -> None:
        """Pick up newly installed voices (e.g. her neural voice) without a restart."""
        self._queue.put("reload")

    def shutdown(self) -> None:
        self._interrupt.set()
        self._queue.put(None)

    def _warm_up(self) -> None:
        warm = getattr(self.voicebox, "warm_up", None)
        if warm is None:
            return
        try:
            warm(self.settings.speech_voice)
        except TypeError:
            warm()

    def voices(self) -> list[str]:
        self.ready.wait(5)
        return self.voicebox.voices() if self.voicebox else []

    @Slot(object)
    def _run_callback(self, fn) -> None:
        fn()

    # -- speech thread ----------------------------------------------------------------
    def _run(self) -> None:
        try:
            self.voicebox = self._voicebox_factory()   # COM objects must live on this thread
        except Exception as exc:
            self.failed.emit(f"text-to-speech unavailable: {exc}")
        self.ready.set()
        self._warm_up()
        while True:
            item = self._queue.get()
            if item is None:
                return
            if item == "reload":
                try:
                    self.voicebox = self._voicebox_factory()
                    self._warm_up()
                except Exception as exc:
                    self.failed.emit(f"text-to-speech unavailable: {exc}")
                continue
            text, then, emotion, line = item
            self._interrupt.clear()
            self._began = False
            try:
                self._speak(text, emotion, line)
            except Exception as exc:
                log.warning("speech: couldn't say a line: %r", exc)
                self.failed.emit(str(exc)[:80])
            finally:
                if not self._began:
                    self.began.emit(line)                 # no voice after all: show the text anyway
                with self._count_lock:
                    self._outstanding = max(0, self._outstanding - 1)
                self.finished.emit()
                if then is not None:
                    self._callback.emit(then)

    def _render(self, part: str, speed: float, pitch: float):
        s = self.settings
        audio = self.voicebox.synthesize(part, s.speech_voice, speed, pitch)
        used, note = getattr(self.voicebox, "last", ("", ""))
        if used != getattr(self, "_logged_voice", None):          # which voice she's using - once per change
            self._logged_voice = used
            log.info("speech: voice %s%s", used or "?", f" ({note})" if note else "")
        self.spoke.emit(used, note)
        if getattr(audio, "as_is", False):                # ElevenLabs / Fish Audio: exactly as they made it
            return audio
        natural = getattr(audio, "natural", False)        # beeps: their own ups and downs
        audio = apply_style(audio, s.speech_style, seed=len(part), pitch=pitch)
        persona = personality.get(getattr(s, "personality", "edgerunner"))
        if not natural:
            audio = intonation(audio, getattr(s, "speech_expression", 0.6) * persona.expressive * EMOTION_LIFT.get(
                self._emotion, 1.0), question=part.rstrip().endswith("?"), exclaim=part.rstrip().endswith("!"),
                seed=len(part))
        return apply_tone(audio, persona.tone)

    def _speak(self, text: str, emotion: str = "neutral", line: int = 0) -> None:
        """Say it a chunk at a time, with no waiting: the first chunk is short so she starts
        talking quickly, and each next chunk is made while the one before is playing."""
        if self.voicebox is None:
            raise RuntimeError("no text-to-speech voices available")
        speed, pitch, gain = prosody(self.settings, emotion)
        self._emotion = emotion
        from .engines import is_online
        parts = [text] if is_online(getattr(self.settings, "speech_voice", "")) else speech_chunks(text)
        # (an online voice says the whole line in one go: one request, one consistent read)
        talking = False
        try:
            upcoming = self._render(parts[0], speed, pitch)
            for i, part in enumerate(parts):
                audio, upcoming = upcoming, None
                if self._interrupt.is_set():
                    return
                if len(audio.samples) == 0:
                    if i + 1 < len(parts):
                        upcoming = self._render(parts[i + 1], speed, pitch)
                    continue
                duration = len(audio.samples) / audio.rate
                if not talking:
                    talking = True
                    self.speaking_changed.emit(True)
                stop = self._player(audio.samples * float(gain), audio.rate)
                end = time.monotonic() + duration
                self.started.emit(part, levels(audio), LEVEL_FRAME, duration)
                if not self._began:
                    self._began = True
                    self.began.emit(line)                 # the panel shows her words now, as she says them
                if i + 1 < len(parts):
                    upcoming = self._render(parts[i + 1], speed, pitch)   # while this one plays
                while time.monotonic() < end:
                    if self._interrupt.is_set():
                        stop()
                        return
                    self._sleep(0.03)
            if talking:
                self._sleep(ECHO_TAIL)
        finally:
            if talking:
                self.speaking_changed.emit(False)
