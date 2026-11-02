"""Companion states shared by the UI and (later) the voice/command modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    LAUNCHING = "launching"
    SPEAKING = "speaking"
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True)
class StateStyle:
    badge: str          # text shown in the status badge
    pose: str           # character pose name looked up in the art manifest
    pulse: bool = False  # animate the badge while in this state
    alert: bool = False  # use the error colour instead of green


STATE_STYLES: dict[State, StateStyle] = {
    State.IDLE: StateStyle("STANDBY", "idle"),
    State.LISTENING: StateStyle("LISTENING", "listening", pulse=True),
    State.PROCESSING: StateStyle("PROCESSING", "thinking", pulse=True),
    State.LAUNCHING: StateStyle("LAUNCHING", "thinking", pulse=True),
    State.SPEAKING: StateStyle("SPEAKING", "speaking"),
    State.SUCCESS: StateStyle("DONE", "success"),
    State.ERROR: StateStyle("ERROR", "error", alert=True),
}
