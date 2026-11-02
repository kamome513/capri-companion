"""A stand-in for vosk.KaldiRecognizer, driven by synthetic "audio".

Each 16-bit sample's low byte is a word marker (0 = silence), so a test can
"speak" words and pauses with exact timing. The fake mimics the Vosk
behaviour the listener relies on:
* an utterance ends after 0.5 s of silence (AcceptWaveform returns True)
* word start/end times count from the recogniser's creation
* in grammar mode, words outside the grammar come out as "[unk]"
"""

from __future__ import annotations

import json

RATE = 16000
CHUNK = RATE // 10                     # 100 ms, like the real microphone stream
WORDS = {1: "capri", 2: "hey", 3: "open", 4: "discord", 5: "went", 6: "to", 7: "spotify", 8: "last"}
MARK = {w: m for m, w in WORDS.items()}
STEP = 160                             # inspect every 10 ms


def speak(*parts, word_seconds: float = 0.4) -> list[bytes]:
    """speak("capri", 0.3, "open", "discord", 1.0) -> 100 ms chunks (numbers = pause seconds)."""
    samples = bytearray()
    for part in parts:
        if isinstance(part, (int, float)):
            samples += bytes(int(part * RATE) * 2)
        else:
            mark = MARK[part]
            samples += bytes([mark, 0]) * int(word_seconds * RATE)
            samples += bytes(int(0.05 * RATE) * 2)   # tiny gap between words
    return [bytes(samples[i:i + CHUNK * 2]) for i in range(0, len(samples), CHUNK * 2)]


class FakeRecognizer:
    created = 0

    def __init__(self, rate: int, grammar: bool, confidence: dict[str, float] | None = None) -> None:
        FakeRecognizer.created += 1
        self.rate, self.grammar = rate, grammar
        self.confidence = confidence or {}
        self.samples = 0
        self.words: list[list] = []      # [word, start, end]
        self.current: int | None = None
        self.silence = 0
        self.result: list[list] = []
        self.received = bytearray()

    def _name(self, word: str) -> str:
        if not self.grammar:
            return word
        return word if word in ("capri", "hey") else "[unk]"

    def AcceptWaveform(self, data: bytes) -> bool:
        self.received += data
        ended = False
        for i in range(0, len(data) // 2, STEP):
            mark = data[i * 2]
            t = self.samples / self.rate
            if mark:
                self.silence = 0
                if mark != self.current:
                    self.words.append([WORDS[mark], t, t])
                    self.current = mark
                self.words[-1][2] = t + STEP / self.rate
            else:
                self.current = None
                self.silence += STEP
                if self.words and self.silence >= 0.5 * self.rate:
                    self.result, self.words = self.words, []
                    ended = True
            self.samples += STEP
        return ended

    def _json(self, words) -> str:
        items = [{"word": self._name(w), "start": s, "end": e,
                  "conf": self.confidence.get(w, 0.97)} for w, s, e in words]
        return json.dumps({"result": items, "text": " ".join(i["word"] for i in items)})

    def Result(self) -> str:
        words, self.result = self.result, []
        return self._json(words)

    def PartialResult(self) -> str:
        return json.dumps({"partial": " ".join(self._name(w) for w, _, _ in self.words)})

    def FinalResult(self) -> str:
        words = self.result + self.words
        self.result, self.words = [], []
        return self._json(words)
