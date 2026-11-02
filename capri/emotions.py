"""Capri's emotions: how each one looks (face / body frame) and sounds (voice prosody)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .states import State


@dataclass(frozen=True)
class Emotion:
    face: str          # expression art (expressions/<face>.png)
    body: str          # body frame while she shows it (body/<body>.png)
    pitch: float       # semitones relative to her normal voice
    rate: float        # speaking speed multiplier
    gain: float        # loudness multiplier


EMOTIONS: dict[str, Emotion] = {
    "neutral":   Emotion("neutral",   "idle",      0.0, 1.00, 1.00),
    "happy":     Emotion("happy",     "happy",     1.5, 1.06, 1.05),
    "playful":   Emotion("playful",   "happy",     2.0, 1.08, 1.05),
    "smirk":     Emotion("smirk",     "idle",      0.5, 0.97, 0.95),
    "surprised": Emotion("surprised", "confused",  2.5, 1.10, 1.08),
    "confused":  Emotion("surprised", "confused",  1.0, 0.95, 0.95),
    "serious":   Emotion("serious",   "thinking", -1.0, 0.94, 1.00),
    "sad":       Emotion("sad",       "idle",     -1.5, 0.88, 0.82),
    "angry":     Emotion("angry",     "idle",     -0.5, 1.10, 1.12),
}

# What she feels by default when showing a result in each state.
DEFAULT_FOR_STATE = {
    State.IDLE: "neutral", State.LISTENING: "neutral", State.PROCESSING: "serious",
    State.LAUNCHING: "happy", State.SPEAKING: "playful", State.SUCCESS: "happy", State.ERROR: "sad",
}

TAG = re.compile(r"^\s*\[(\w+)\]\s*")


def get(name: str | None) -> Emotion:
    return EMOTIONS.get(name or "neutral", EMOTIONS["neutral"])


def split_tag(text: str) -> tuple[str, str]:
    """'[playful] Nice try.' -> ('playful', 'Nice try.'). Unknown or missing tag -> ''."""
    m = TAG.match(text)
    if m and m.group(1).lower() in EMOTIONS:
        return m.group(1).lower(), text[m.end():]
    return "", text


def guess(text: str, state: State) -> str:
    """A light guess from the words, for lines that don't say how she feels."""
    t = text.lower()
    if state is State.ERROR:
        if any(w in t for w in ("couldn't find", "not sure", "isn't set up", "not set up")):
            return "confused"
        if any(w in t for w in ("refused", "said no", "not allowed", "fried", "glitch")):
            return "angry"
        return "sad"
    if "?" in t:
        return "serious" if state is State.LISTENING else "playful"
    if any(w in t for w in ("umbrella", "rain", "storm", "snow")):
        return "sad"
    if any(w in t for w in ("closed", "leaving")):
        return "smirk"
    return DEFAULT_FOR_STATE.get(state, "neutral")
