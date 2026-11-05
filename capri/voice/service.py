"""Microphone + wake word running on a background thread.

The UI talks to this through thread-safe method calls; results come back
as Qt signals (delivered on the UI thread).

Microphone use, plainly:
* While voice activation is on, the microphone is open continuously - that
  is the only way any wake word can work. Audio is processed in memory on
  this PC by Vosk and is never saved or sent anywhere.
* Muted, or with voice activation off, the microphone stream is *closed*
  (Windows' mic-in-use indicator goes away). Push-to-talk opens it just for
  one command when voice activation is off.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ..net import friendly
from .model import download_model, find_model, user_models_dir
from .cleanup import MicCleaner
from .wakeword import (WAKE_GRAMMAR, WAKE_WORD, Command, Heard, NoCommand, Partial, Rejected, Wake, clean_command,
                       WakeWordListener)

log = logging.getLogger("capri")

PREFERRED_RATE = 16000
ALTERNATIVES = 4            # transcripts the command recogniser returns (best first)
STALL_SECONDS = 3.0        # no audio for this long = device lost (sleep, unplugged)
RETRY_SECONDS = 5.0


class Status:
    READY = "ready"                   # waiting for the wake word
    VOICE_OFF = "voice_off"           # wake word disabled (push-to-talk still works)
    MUTED = "muted"
    MIC_ERROR = "mic_error"
    MODEL_MISSING = "model_missing"
    MODEL_DOWNLOADING = "model_downloading"   # first start: fetching her speech model (~40 MB, once)
    ENGINE_MISSING = "engine_missing"
    MODEL_ERROR = "model_error"


def list_input_devices() -> list[str]:
    """Microphone names for the menu (default host API only, so no duplicates)."""
    try:
        import sounddevice as sd
        hostapi = sd.default.hostapi
        names = [d["name"] for d in sd.query_devices()
                 if d["max_input_channels"] > 0 and d["hostapi"] == hostapi]
        return list(dict.fromkeys(names))
    except Exception:
        return []


def model_knows_wake_word(model_dir: Path) -> bool | None:
    """Check the model's vocabulary contains 'capri'. None = can't tell."""
    for words in (model_dir / "graph" / "words.txt", model_dir / "words.txt"):
        if words.is_file():
            with words.open(encoding="utf-8", errors="ignore") as fh:
                return any(line.split(" ", 1)[0] == WAKE_WORD for line in fh)
    return None


class VoiceService(QObject):
    status_changed = Signal(str, str)       # Status.*, detail
    wake = Signal(str, float)               # phrase, confidence
    partial = Signal(str)
    command = Signal(str)
    alternatives = Signal(list)       # the recogniser's runner-up guesses, sent just before `command`
    no_command = Signal()
    rejected = Signal(str, float)
    heard = Signal(float, str)              # teaching her your voice: (confidence it was "capri", what she heard)

    def __init__(self, enabled: bool, muted: bool, device: str, threshold: float) -> None:
        super().__init__()
        self._control: queue.Queue = queue.Queue()
        self._enabled, self._muted, self._device, self._threshold = enabled, muted, device, threshold
        self._thread = threading.Thread(target=self._run, name="capri-voice", daemon=True)
        self._status: tuple[str, str] | None = None
        self._speaking = threading.Event()
        self.device_name = ""
        self.refine: Callable[[bytes, int], str] | None = None   # a better second listen (Whisper), if on
        self._rate = 16000
        self.cleanup = False                    # mic clean-up (cleanup.py): level, rumble, hiss - the app turns it on
        self._learned: list[str] = []           # how she hears your voice say her name (taught in Settings)
        self._training = False

    # -- called from the UI thread ----------------------------------------------
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._control.put(("stop", None))
        self._thread.join(timeout=2)

    def set_enabled(self, on: bool) -> None:
        self._control.put(("enabled", on))

    def set_muted(self, on: bool) -> None:
        self._control.put(("muted", on))

    def set_device(self, name: str) -> None:
        self._control.put(("device", name))

    def set_threshold(self, value: float) -> None:
        self._control.put(("threshold", value))

    def set_learned(self, variants: list[str]) -> None:
        self._control.put(("learned", list(variants)))

    def set_training(self, on: bool) -> None:
        """Teaching her your voice: every "Hey Capri" is reported (heard signal) instead of waking her."""
        self._control.put(("training", on))

    def cancel_listen(self) -> None:
        """Stop waiting for a spoken answer (it was typed in the chat window instead)."""
        self._control.put(("cancel", None))

    def listen_now(self, start_timeout: float | None = None) -> None:
        self._control.put(("listen", start_timeout))

    def set_speaking(self, on: bool) -> None:
        """While Capri talks the mic input is thrown away, so she can't hear herself."""
        if on:
            self._speaking.set()
        else:
            self._speaking.clear()

    # -- worker thread -------------------------------------------------------------
    def _emit_status(self, status: str, detail: str = "") -> None:
        if self._status != (status, detail):
            self._status = (status, detail)
            self.status_changed.emit(status, detail)

    def _run(self) -> None:
        try:
            import vosk
        except ImportError:
            self._emit_status(Status.ENGINE_MISSING, "pip install vosk sounddevice")
            return
        model_dir = find_model()
        if model_dir is None:                    # first start (e.g. the .exe): fetch it herself, once
            self._emit_status(Status.MODEL_DOWNLOADING, "40 MB, once")
            try:
                model_dir = download_model(user_models_dir(), quiet=True)
            except Exception as exc:
                log.warning("voice: couldn't download the speech model: %r", exc)
                self._emit_status(Status.MODEL_MISSING, f"couldn't download it ({friendly(exc)[:70]}) - "
                                                        f"check your internet and restart me")
                return
        if model_knows_wake_word(model_dir) is False:
            self._emit_status(Status.MODEL_ERROR, f"{model_dir.name} doesn't know the word 'capri'")
            return
        vosk.SetLogLevel(-1)
        try:
            model = vosk.Model(str(model_dir))
        except Exception as exc:
            self._emit_status(Status.MODEL_ERROR, str(exc))
            return

        def wake_rec(rate: int):
            rec = vosk.KaldiRecognizer(model, rate, json.dumps(WAKE_GRAMMAR))
            rec.SetWords(True)
            return rec

        def command_rec(rate: int):
            rec = vosk.KaldiRecognizer(model, rate)
            if hasattr(rec, "SetMaxAlternatives"):
                rec.SetMaxAlternatives(ALTERNATIVES)   # runner-up guesses: the router picks a real command
            return rec

        def make_listener(rate: int) -> WakeWordListener:
            listener = WakeWordListener(wake_rec, command_rec, rate, self._threshold)
            listener.verify_wake = True              # a second, full listen to every "capri" before she wakes
            return listener

        self._loop(make_listener)

    def _loop(self, make_listener) -> None:
        audio: queue.Queue[bytes] = queue.Queue(maxsize=100)
        stream = None
        listener = None
        push_to_talk = False
        listen_timeout = None
        last_audio = 0.0
        retry_at = 0.0
        cleaner = None

        def close():
            nonlocal stream
            if stream is not None:
                try:
                    stream.abort()
                    stream.close()
                except Exception:
                    pass
                stream = None
            while not audio.empty():
                audio.get_nowait()

        while True:
            # 1. Handle requests from the UI.
            try:
                while True:
                    kind, value = self._control.get_nowait()
                    if kind == "stop":
                        close()
                        return
                    if kind == "enabled":
                        self._enabled = value
                    elif kind == "muted":
                        self._muted = value
                        if value and listener:
                            listener.cancel()
                            push_to_talk = False
                    elif kind == "device":
                        self._device = value
                        close()
                        retry_at = 0.0
                    elif kind == "threshold":
                        self._threshold = value
                        if listener:
                            listener.threshold = value
                    elif kind == "learned":
                        self._learned = value
                    elif kind == "training":
                        self._training = value
                    elif kind == "cancel":
                        push_to_talk = False
                        if listener:
                            listener.cancel()
                    elif kind == "listen":
                        if self._muted:
                            self.no_command.emit()
                        else:
                            push_to_talk = True
                            listen_timeout = value
            except queue.Empty:
                pass

            capturing = bool(listener and listener.capturing)
            want_stream = not self._muted and (self._enabled or capturing or push_to_talk or self._training)

            # 2. Open / close the microphone as needed.
            if not want_stream:
                close()
                self._emit_status(Status.MUTED if self._muted else Status.VOICE_OFF)
                try:
                    kind, value = self._control.get(timeout=0.5)
                    self._control.put((kind, value))   # handled at the top of the loop
                except queue.Empty:
                    pass
                continue

            if stream is None:
                if time.monotonic() < retry_at:
                    time.sleep(0.2)
                    continue
                try:
                    stream, rate = self._open(audio)
                    self._rate = rate
                except Exception as exc:
                    self._emit_status(Status.MIC_ERROR, _short(exc))
                    retry_at = time.monotonic() + RETRY_SECONDS
                    continue
                if listener is None or listener.rate != rate:
                    listener = make_listener(rate)
                cleaner = MicCleaner(rate)
                listener.wake_enabled = self._enabled
                last_audio = time.monotonic()

            listener.wake_enabled = self._enabled or self._training
            listener.threshold = self._threshold
            listener.learned, listener.training = self._learned, self._training
            if push_to_talk:
                listener.listen_now(listen_timeout)
                push_to_talk = False
                self.wake.emit("push-to-talk", 1.0)
            if not listener.capturing:
                self._emit_status(Status.READY if self._enabled else Status.VOICE_OFF, self.device_name)

            # 3. Feed audio to the wake word listener.
            try:
                chunk = audio.get(timeout=0.25)
            except queue.Empty:
                if time.monotonic() - last_audio > STALL_SECONDS:
                    # Device vanished (sleep/resume, unplugged): reopen it.
                    close()
                    if listener:
                        listener.cancel()
                    retry_at = 0.0
                continue
            last_audio = time.monotonic()
            if self._speaking.is_set():
                continue   # her own voice: never fed to the recogniser
            if self.cleanup and cleaner is not None:
                chunk = cleaner(chunk)             # quiet / cheap / far-away mics: a steady, clean level
            try:
                events = listener.feed(chunk)
            except Exception:                      # never let one bad result end her hearing for good
                log.exception("hearing: the recogniser stumbled - starting the listen over")
                try:
                    listener.cancel()
                except Exception:
                    pass
                events = []
            for event in events:
                self._dispatch(event)

    def _dispatch(self, event) -> None:
        if isinstance(event, Wake):
            self.wake.emit(event.phrase, event.confidence)
        elif isinstance(event, Partial):
            self.partial.emit(event.text)
        elif isinstance(event, Command):
            refine = self.refine
            if refine is not None and event.audio:
                threading.Thread(target=self._refined, args=(refine, event), daemon=True).start()
                return
            self.alternatives.emit(list(event.alternatives))
            self.command.emit(event.text)
        elif isinstance(event, NoCommand):
            self.no_command.emit()
        elif isinstance(event, Rejected):
            self.rejected.emit(event.text, event.confidence)
        elif isinstance(event, Heard):
            self.heard.emit(event.confidence, event.said)

    def _refined(self, refine, event) -> None:
        """Whisper's listen of the same words (better with accents); Vosk's guesses stay as runner-ups."""
        try:
            text = clean_command(refine(event.audio, self._rate) or "")
        except Exception as exc:
            log.warning("hearing: the better ears failed, using Vosk: %s", exc)
            text = ""
        if text and text != event.text:
            log.info("hearing: Vosk %r -> re-heard %r", event.text, text)
            self.alternatives.emit([event.text] + [a for a in event.alternatives if a != text])
            self.command.emit(text)
        else:
            self.alternatives.emit(list(event.alternatives))
            self.command.emit(event.text)

    def _open(self, audio: queue.Queue):
        import sounddevice as sd

        device = None
        if self._device:
            for index, info in enumerate(sd.query_devices()):
                if info["name"] == self._device and info["max_input_channels"] > 0:
                    device = index
                    break

        def callback(indata, frames, time_info, status) -> None:
            try:
                audio.put_nowait(bytes(indata))
            except queue.Full:
                pass   # UI thread stalled; dropping audio beats growing memory

        def open_at(rate: int):
            s = sd.RawInputStream(samplerate=rate, blocksize=rate // 10, device=device,
                                  channels=1, dtype="int16", callback=callback)
            s.start()
            return s

        try:
            stream, rate = open_at(PREFERRED_RATE), PREFERRED_RATE
        except sd.PortAudioError:
            # Some devices refuse 16 kHz; use their native rate (Vosk resamples).
            info = sd.query_devices(device if device is not None else sd.default.device[0])
            rate = int(info["default_samplerate"])
            stream = open_at(rate)
        info = sd.query_devices(device if device is not None else sd.default.device[0])
        self.device_name = info["name"]
        return stream, rate


def _short(exc: Exception) -> str:
    text = str(exc).strip() or type(exc).__name__
    if "PortAudio library not found" in text:            # Linux without the sound library
        return "install PortAudio: sudo apt install libportaudio2"
    return text if len(text) < 60 else text[:57] + "..."
