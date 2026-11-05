"""Wake word ("Capri" / "Hey Capri") and command capture.

Pure logic: feed it 16-bit mono PCM chunks, it returns events. It never
touches the microphone or the UI, so it can be tested with recorded audio.

How it works
------------
* A Vosk recogniser restricted to a tiny grammar - ``capri``, ``hey capri``
  or "unknown" - listens continuously. Everything that isn't Capri's name
  comes out as ``[unk]``. Nothing is transcribed while waiting.
* An utterance only counts as a wake-up if it *starts* with "capri" (or
  "hey capri") and Vosk's confidence in that word is at least
  ``threshold``. "I went to Capri last year" or an unsure match is ignored.
* The grammar also has decoys - everyday words and ones that sound a bit like her
  name ("happy", "copy", "sorry"...). With only "capri" to choose from, the
  recogniser forces any similar sound onto it; with decoys, "happy" stays "happy".
* A "capri" too short to be the word (a click, a blip) doesn't count, and - with
  ``verify_wake`` on - the full recogniser listens to just that bit again: it has to
  sound like "capri" there too (accent-tolerant), or she stays asleep.
* Only after a wake-up is the following speech run through the full
  English recogniser to get the command text.
* "Capri, open Discord" in one breath works too: recent audio is kept in a
  short in-memory ring buffer, so the audio *after* the word "capri" can be
  re-read and transcribed. The buffer is never saved or sent anywhere.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .voicecheck import voice_check

# Decoys: everyday words and near-sounds, so they aren't forced onto "capri" (see above).
DECOYS = ["happy", "copy", "carry", "cherry", "crappy", "gravy", "crazy", "creepy", "pretty", "sorry", "free",
          "three", "tree", "april", "captain", "capture", "cap", "crap", "grab", "cabin", "kappa", "play", "pray",
          "spray", "perry", "jerry", "harry", "berry", "very", "every", "apple", "okay", "yeah", "hi", "a", "the",
          "and", "i", "you", "it", "to", "is", "that", "what", "no", "yes", "go", "come", "on", "get"]
WAKE_GRAMMAR = ["hey capri", "capri", *DECOYS, "[unk]"]
# A command that's only its opening words - she waits for the rest instead of acting on "can you".
LEAD_IN = re.compile(r"(?:(?:can|could|would|will|do|did) (?:you|u|ya)(?: please)?|please|so|um+|uh+|hey|okay|ok|and|"
                     r"i (?:want|need) you to|(?:can|could) you (?:just|maybe)|do you think you (?:can|could)|"
                     r"i was wondering if you (?:can|could)|is it possible (?:for you )?to)")
VERIFY_RELAX = 0.15           # with the second listen on, the first can be this much less sure (fewer missed wakes)
MIN_WAKE_SECONDS = 0.2        # "capri" takes longer than this to say: shorter is a click or a blip
VERIFY_PAD_SECONDS = 0.12     # a little audio after the word, for the second listen
WAKE_WORD = "capri"
# A breath, a click or an "uh" before her name often comes out as one of these little words ("the hey capri").
# One of them in front still counts as calling her; a real word ("went to capri") doesn't.
FILLERS = {"the", "a", "uh", "um", "oh", "okay", "yeah", "hi", "and", "so", "ah", "er", "erm", "hmm", "yo"}
UNKNOWN = "[unk]"

COMMAND_START_TIMEOUT = 6.0   # seconds to start speaking after a bare "Capri"
COMMAND_MAX_LENGTH = 12.0     # longest command we'll wait for
RING_SECONDS = 20.0           # audio history kept for one-breath commands
BYTES_PER_SAMPLE = 2

log = logging.getLogger("capri")


class Recognizer(Protocol):
    """The parts of ``vosk.KaldiRecognizer`` we use."""
    def AcceptWaveform(self, data: bytes) -> bool: ...
    def Result(self) -> str: ...
    def PartialResult(self) -> str: ...
    def FinalResult(self) -> str: ...


# Factories so tests can supply fake recognisers: (sample_rate) -> Recognizer
RecognizerFactory = Callable[[int], Recognizer]


# -- events ------------------------------------------------------------------
@dataclass(frozen=True)
class Wake:
    phrase: str        # "capri" or "hey capri"
    confidence: float


@dataclass(frozen=True)
class Partial:
    text: str          # command text so far, for live display


@dataclass(frozen=True)
class Command:
    text: str          # what was said after the wake word (the recogniser's best guess)
    alternatives: tuple[str, ...] = ()   # its runner-up guesses, best first
    audio: bytes = field(default=b"", compare=False, repr=False)   # its own audio (for Whisper's second listen)


@dataclass(frozen=True)
class NoCommand:
    pass               # woke up but heard nothing usable in time


@dataclass(frozen=True)
class Heard:
    """Teaching her your voice: one "Hey Capri" as she heard it (no wake-up while training)."""
    confidence: float  # how sure the wake word check was it was "capri" (0 = it didn't hear "capri" at all)
    said: str          # what the full recogniser made of it ("capri", "cap free"...)


@dataclass(frozen=True)
class Rejected:
    text: str          # a near-miss, e.g. "capri" with low confidence (for diagnostics)
    confidence: float


Event = Wake | Partial | Command | NoCommand | Rejected | Heard


CAPRI_SOUND = re.compile(r"kp[ftkp]?r")   # k-p-r, maybe with a sound slipped in: "cap free", "cap tree"


def sounds_like_capri(said: str, learned: list[str] | tuple[str, ...] = ()) -> bool:
    """Does any of the recogniser's guesses start with something that sounds like "capri"? Accent-tolerant
    ("kapree", "cap re", "capri's", "copper e", "cap free"...) but not "happy", "copy" or "carry" - plus the
    ways it hears *your* voice say it, learned when you taught her (Settings -> Teach her your voice)."""
    from difflib import SequenceMatcher

    from ..commands.soundslike import sound_key
    for guess in said.split("|"):
        words = [w for w in guess.split() if w not in ("hey", "hay", "a", "uh", "um", "oh")][:3]
        if "capri" in words:
            return True
        joined = ""
        for w in words:
            joined += sound_key(w).lstrip("a") if joined else sound_key(w)
            if CAPRI_SOUND.match(joined.lstrip("a")):
                return True
        start = " ".join(words[:2])
        if start and any(SequenceMatcher(None, start, v).ratio() >= 0.8 or start.startswith(v) for v in learned):
            return True
    return False


COMMAND_FILLERS = {"the", "uh", "um", "umm", "uhh", "ah", "erm", "hmm"}   # "the open discord" (not "oh": "oh pen" = open)


def clean_command(text: str) -> str:
    """Drop a repeated wake word ("capri capri open discord"), a stray "the" / "uh" in front
    ("the open discord"), and extra spaces."""
    words = text.split()
    while words and (words[0] in ("hey", WAKE_WORD) or words[0] in COMMAND_FILLERS and len(words) > 1):
        words.pop(0)
    return re.sub(r"\s+", " ", " ".join(words)).strip()


_DECIMAL_COMMA = re.compile(r"(:\s*-?\d+),(\d+)")


def vosk_json(text: str) -> dict:
    """A Vosk result. With a comma-decimal language on Linux (German, French, Portuguese...) Vosk can write
    numbers like "confidence" : 412,34 - not valid JSON, and that used to kill her hearing. Those are read as
    412.34; anything still unreadable counts as "heard nothing" instead of breaking."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        try:
            data = json.loads(_DECIMAL_COMMA.sub(r"\1.\2", text or ""))
        except ValueError:
            log.warning("hearing: unreadable result from the recogniser: %r", (text or "")[:200])
            return {}
    return data if isinstance(data, dict) else {}


def heard(result: dict) -> list[str]:
    """Every transcript in a recogniser result, best first. With SetMaxAlternatives the
    result is {"alternatives": [{"text": ...}, ...]} instead of {"text": ...}."""
    if "alternatives" in result:
        texts = [clean_command(a.get("text", "")) for a in result.get("alternatives") or []]
    else:
        texts = [clean_command(result.get("text", ""))]
    out: list[str] = []
    for t in texts:
        if t and t not in out:
            out.append(t)
    return out


def command_from(texts: list[str], audio: bytes = b"") -> "Command":
    return Command(texts[0], tuple(texts[1:]), audio)


class WakeWordListener:
    def __init__(self, wake_factory: RecognizerFactory, command_factory: RecognizerFactory,
                 sample_rate: int = 16000, threshold: float = 0.80,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._wake_factory = wake_factory
        self._command_factory = command_factory
        self.rate = sample_rate
        self.threshold = threshold
        self.wake_enabled = True
        self._clock = clock

        self._samples = 0                      # total samples received so far
        self._ring: deque[tuple[int, bytes]] = deque()   # (first sample index, chunk)
        self._wake = self._new_wake()
        self._command: Recognizer | None = None
        self._command_started = 0.0
        self._heard_speech = False
        self._lead = ""
        self._start_timeout = COMMAND_START_TIMEOUT
        self.voice_check = voice_check          # (audio, rate) -> (is it a voice?, why not) - None = off
        self.verify_wake = False                # second listen with the full recogniser (on in the app)
        self.learned: list[str] = []            # how the full recogniser hears *you* say her name (taught)
        self.training = False                   # teaching her your voice: report each "Hey Capri", never wake

    # -- public -----------------------------------------------------------
    @property
    def capturing(self) -> bool:
        """True while recording a command (after the wake word / push-to-talk)."""
        return self._command is not None

    def listen_now(self, start_timeout: float | None = None) -> list[Event]:
        """Push-to-talk: skip the wake word and capture the next utterance. start_timeout = how
        long to wait for you to start talking (longer when she's asked you something)."""
        if not self.capturing:
            self._begin_command()
        self._start_timeout = start_timeout or COMMAND_START_TIMEOUT
        return []

    def cancel(self) -> None:
        self._command = None
        self._wake = self._new_wake()

    def feed(self, chunk: bytes) -> list[Event]:
        start = self._samples
        self._samples += len(chunk) // BYTES_PER_SAMPLE
        self._remember(start, chunk)

        if self.capturing:
            return self._feed_command(chunk)
        if not self.wake_enabled:
            return []
        if not self._wake.AcceptWaveform(chunk):
            return []
        return self._on_wake_utterance(vosk_json(self._wake.Result()))

    # -- wake word ----------------------------------------------------------
    def _new_wake(self) -> Recognizer:
        self._wake_origin = self._samples    # Vosk word times count from here
        return self._wake_factory(self.rate)

    def _on_wake_utterance(self, result: dict) -> list[Event]:
        words = result.get("result") or []
        if not words:
            return []
        if self.training:                       # teaching her your voice: just report how it sounded
            return [self._heard(words)]
        lead = 1 if words[0].get("word") in FILLERS and len(words) > 1 else 0     # "the hey capri"
        words = words[lead:]
        i = 1 if words[0].get("word") == "hey" and len(words) > 1 else 0
        first = words[i]
        if first.get("word") != WAKE_WORD:
            if any(w.get("word") == WAKE_WORD for w in words):
                # Said in the middle of a sentence: not a call for her.
                w = next(w for w in words if w.get("word") == WAKE_WORD)
                return [Rejected(result.get("text", ""), float(w.get("conf", 0)))]
            return []
        conf = float(first.get("conf", 0.0))
        needed = self.threshold - VERIFY_RELAX if self.verify_wake else self.threshold
        if conf < needed:                       # (the second listen below catches what slips through)
            return [Rejected(result.get("text", ""), conf)]
        if "start" in first and "end" in first and float(first["end"]) - float(first["start"]) < MIN_WAKE_SECONDS:
            return [Rejected(f"{result.get('text', '')} (too short)", conf)]
        if self.voice_check is not None and "start" in words[0] and "end" in first:
            # Was it a person? A Discord ping or a chime can sound like "Capri" to the recogniser.
            start = self._wake_origin + int(float(words[0]["start"]) * self.rate)
            end = self._wake_origin + int(float(first["end"]) * self.rate)
            audio = self._audio_since(start)[: max(0, end - start) * BYTES_PER_SAMPLE]
            is_voice, why = self.voice_check(audio, self.rate)
            if not is_voice:
                return [Rejected(f"{result.get('text', '')} ({why})", conf)]

        if self.verify_wake and "start" in words[0] and "end" in first:
            start = self._wake_origin + int(float(words[0]["start"]) * self.rate)
            end = self._wake_origin + int((float(first["end"]) + VERIFY_PAD_SECONDS) * self.rate)
            said = self._said(self._audio_since(start)[: max(0, end - start) * BYTES_PER_SAMPLE])
            if not sounds_like_capri(said, self.learned) and not (not said and conf >= 0.95):
                return [Rejected(f"{result.get('text', '')} (heard \u201c{said[:20]}\u201d)", conf)]

        events: list[Event] = [Wake("hey capri" if i == 1 else "capri", conf)]
        rest = words[i + 1:]
        if rest:
            # More speech followed in the same breath: transcribe it from the ring buffer.
            start = self._wake_origin + int(float(first["end"]) * self.rate)
            texts = self._transcribe_since(start)
            if texts:
                events.append(command_from(texts, self._audio_since(start)))
                self._wake = self._new_wake()
                return events
        self._begin_command()
        return events

    # -- command capture --------------------------------------------------------
    def _begin_command(self) -> None:
        self._start_timeout = COMMAND_START_TIMEOUT
        self._command = self._command_factory(self.rate)
        self._command_started = self._clock()
        self._command_sample = self._samples
        self._heard_speech = False
        self._lead = ""                         # "can you" heard so far (the rest is coming)

    def _finish(self, event: Event) -> list[Event]:
        self._command = None
        self._wake = self._new_wake()   # fresh wake recogniser, nothing carried over
        return [event]

    def _feed_command(self, chunk: bytes) -> list[Event]:
        rec = self._command
        assert rec is not None
        elapsed = self._clock() - self._command_started
        if rec.AcceptWaveform(chunk):
            texts = heard(vosk_json(rec.Result()))
            if texts and LEAD_IN.fullmatch(texts[0]) and not self._lead:
                # "Can you..." and a pause while you think: not the whole command - keep listening for the rest.
                self._lead = texts[0]
                self._command_started = self._clock()
                self._heard_speech = False
                return [Partial(texts[0] + "...")]
            if texts:
                if self._lead:
                    texts = [f"{self._lead} {t}" for t in texts]
                    self._lead = ""
                return self._finish(command_from(texts, self._audio_since(self._command_sample)))
        else:
            partial = clean_command(vosk_json(rec.PartialResult()).get("partial", ""))
            if partial:
                self._heard_speech = True
                return [Partial(partial)]

        if elapsed >= max(COMMAND_MAX_LENGTH, self._start_timeout + 6) or \
                (not self._heard_speech and elapsed >= self._start_timeout):
            texts = heard(vosk_json(rec.FinalResult()))
            if self._lead:                                    # only ever said "can you": that's all there is
                texts = [f"{self._lead} {t}" for t in texts] if texts else [self._lead]
                self._lead = ""
            return self._finish(command_from(texts, self._audio_since(self._command_sample)) if texts else NoCommand())
        return []

    # -- audio history -------------------------------------------------------------
    def _remember(self, start: int, chunk: bytes) -> None:
        self._ring.append((start, chunk))
        keep_from = self._samples - int(RING_SECONDS * self.rate)
        while self._ring and self._ring[0][0] + len(self._ring[0][1]) // BYTES_PER_SAMPLE <= keep_from:
            self._ring.popleft()

    def _audio_since(self, sample: int) -> bytes:
        sample = max(sample, self._ring[0][0] if self._ring else 0)
        parts = []
        for start, chunk in self._ring:
            end = start + len(chunk) // BYTES_PER_SAMPLE
            if end <= sample:
                continue
            offset = max(0, sample - start) * BYTES_PER_SAMPLE
            parts.append(chunk[offset:])
        return b"".join(parts)

    def _heard(self, words: list[dict]) -> Heard:
        """Training: how sure the wake check was about "capri", and what the full recogniser heard."""
        conf = max((float(w.get("conf", 0.0)) for w in words if w.get("word") == WAKE_WORD), default=0.0)
        said = ""
        if "start" in words[0] and "end" in words[-1]:
            start = self._wake_origin + int(float(words[0]["start"]) * self.rate)
            end = self._wake_origin + int((float(words[-1]["end"]) + VERIFY_PAD_SECONDS) * self.rate)
            said = self._said(self._audio_since(start)[: max(0, end - start) * BYTES_PER_SAMPLE])
        return Heard(conf, said)

    def _said(self, audio: bytes) -> str:
        """The full recogniser's words for a bit of audio (all its guesses, raw)."""
        if not audio:
            return ""
        rec = self._command_factory(self.rate)
        rec.AcceptWaveform(audio)
        result = vosk_json(rec.FinalResult())
        texts = [a.get("text", "") for a in result.get("alternatives") or []] or [result.get("text", "")]
        return " | ".join(t for t in texts if t)

    def _transcribe_since(self, sample: int) -> list[str]:
        audio = self._audio_since(sample)
        if not audio:
            return []
        rec = self._command_factory(self.rate)
        rec.AcceptWaveform(audio)
        return heard(vosk_json(rec.FinalResult()))
