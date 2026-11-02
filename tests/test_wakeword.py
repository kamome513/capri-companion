"""Wake word logic tests, using the fake recogniser (no microphone, no model)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_vosk import CHUNK, RATE, FakeRecognizer, speak  # noqa: E402

from capri.voice.wakeword import (RING_SECONDS, Command, NoCommand, Partial, Rejected, Wake,  # noqa: E402
                                  WakeWordListener, clean_command)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def make(threshold=0.8, confidence=None):
    clock = Clock()
    commands: list[FakeRecognizer] = []

    def command_factory(rate):
        rec = FakeRecognizer(rate, grammar=False)
        commands.append(rec)
        return rec

    listener = WakeWordListener(lambda rate: FakeRecognizer(rate, True, confidence), command_factory,
                                RATE, threshold, clock)
    listener.test_clock = clock
    listener.test_commands = commands
    return listener


def run(listener, chunks):
    events = []
    for chunk in chunks:
        listener.test_clock.t += len(chunk) / 2 / RATE
        events += listener.feed(chunk)
    return events


def kinds(events):
    return [type(e).__name__ for e in events]


def test_capri_pause_then_command():
    listener = make()
    events = run(listener, speak(0.5, "capri", 1.0, "open", "discord", 1.0))
    assert isinstance(events[0], Wake) and events[0].phrase == "capri"
    assert any(isinstance(e, Partial) for e in events)
    assert events[-1] == Command("open discord")
    assert not listener.capturing


def test_hey_capri_command_in_one_breath():
    listener = make()
    events = run(listener, speak(0.3, "hey", "capri", "open", "spotify", 1.0))
    assert kinds(events) == ["Wake", "Command"]
    assert events[0].phrase == "hey capri"
    assert events[1] == Command("open spotify")
    # The command recogniser only got audio from *after* the word "capri".
    audio = bytes(listener.test_commands[-1].received)
    assert 1 not in audio[0::2] and 2 not in audio[0::2]


def test_capri_mid_sentence_is_ignored():
    listener = make()
    events = run(listener, speak(0.3, "went", "to", "capri", "last", 1.0, 3.0))
    assert not any(isinstance(e, (Wake, Command)) for e in events)
    assert kinds(events) == ["Rejected"]
    assert not listener.capturing


def test_unrelated_speech_produces_nothing():
    listener = make()
    assert run(listener, speak(0.2, "open", "discord", 1.0, "went", "to", 1.0)) == []


def test_low_confidence_is_ignored_and_does_not_block_next_call():
    unsure = make(threshold=0.8, confidence={"capri": 0.55})
    events = run(unsure, speak(0.2, "capri", "open", "discord", 1.0, 2.0))
    assert kinds(events) == ["Rejected"] and events[0].confidence == 0.55
    assert not unsure.capturing

    sure = make(threshold=0.8, confidence={"capri": 0.92})
    assert kinds(run(sure, speak(0.2, "capri", "open", "discord", 1.0))) == ["Wake", "Command"]


def test_threshold_is_respected_exactly():
    listener = make(threshold=0.9, confidence={"capri": 0.89})
    assert kinds(run(listener, speak("capri", 1.0))) == ["Rejected"]
    listener.threshold = 0.85
    assert kinds(run(listener, speak("capri", 1.0)))[0] == "Wake"


def test_bare_capri_then_silence_times_out():
    listener = make()
    events = run(listener, speak("capri", 8.0))
    assert kinds(events) == ["Wake", "NoCommand"]
    assert not listener.capturing


def test_works_again_after_each_command():
    listener = make()
    seq = speak("capri", "open", "discord", 1.0, 2.0, "hey", "capri", 0.8, "open", "spotify", 1.0,
                3.0, "capri", "open", "discord", 1.0)
    commands = [e for e in run(listener, seq) if isinstance(e, Command)]
    assert commands == [Command("open discord"), Command("open spotify"), Command("open discord")]


def test_wake_disabled_ignores_name_but_push_to_talk_works():
    listener = make()
    listener.wake_enabled = False
    assert run(listener, speak("capri", "open", "discord", 1.0)) == []
    listener.listen_now()
    assert listener.capturing
    events = run(listener, speak(0.3, "open", "spotify", 1.0))
    assert events[-1] == Command("open spotify")


def test_push_to_talk_strips_a_spoken_wake_word():
    listener = make()
    listener.listen_now()
    events = run(listener, speak("capri", "open", "spotify", 1.0))
    assert events[-1] == Command("open spotify")


def test_cancel_stops_capture():
    listener = make()
    run(listener, speak("capri", 1.0))
    assert listener.capturing
    listener.cancel()
    assert not listener.capturing


def test_ring_buffer_is_bounded():
    listener = make()
    run(listener, speak(60.0))
    held = sum(len(c) for _, c in listener._ring) / 2 / RATE
    assert held <= RING_SECONDS + CHUNK / RATE


def test_clean_command():
    assert clean_command("capri capri  open discord") == "open discord"
    assert clean_command("hey capri open chrome") == "open chrome"
    assert clean_command("capri") == ""
    assert clean_command("") == ""


def test_events_are_simple_values():
    assert Command("a") == Command("a") and Rejected("x", 0.1) != Rejected("x", 0.2)
    assert NoCommand() == NoCommand()
