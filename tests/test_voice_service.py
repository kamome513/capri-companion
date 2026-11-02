"""VoiceService thread + Assistant tests with a fake microphone (no hardware)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fake_vosk import RATE, FakeRecognizer, speak  # noqa: E402
from PySide6.QtCore import QStandardPaths, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri import hotkeys  # noqa: E402
from capri.assistant import Assistant  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402
from capri.voice.service import Status, VoiceService  # noqa: E402
from capri.voice.wakeword import WakeWordListener  # noqa: E402


class FakeMic:
    """Plays queued chunks into the service's audio queue in real time-ish."""

    def __init__(self) -> None:
        self.opened = 0
        self.closed = 0
        self.script: list[bytes] = []
        self.lock = threading.Lock()
        self.stalled = False

    def open(self, audio):
        self.opened += 1
        mic = self
        stop = threading.Event()

        class Stream:
            def abort(self):
                stop.set()

            def close(self):
                mic.closed += 1

        def pump():
            while not stop.is_set():
                with mic.lock:
                    chunk = mic.script.pop(0) if mic.script else bytes(RATE // 10 * 2)
                if not mic.stalled:
                    audio.put(chunk)
                time.sleep(0.002)   # much faster than real time

        threading.Thread(target=pump, daemon=True).start()
        return Stream(), RATE

    def say(self, *parts):
        with self.lock:
            self.script += speak(*parts)


class Recorder:
    def __init__(self, service: VoiceService) -> None:
        self.events = []
        direct = Qt.ConnectionType.DirectConnection   # collect on the worker thread
        service.status_changed.connect(lambda s, d: self.events.append(("status", s)), direct)
        service.wake.connect(lambda p, c: self.events.append(("wake", p)), direct)
        service.command.connect(lambda t: self.events.append(("command", t)), direct)
        service.no_command.connect(lambda: self.events.append(("no_command",)), direct)

    def wait_for(self, item, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if item in self.events:
                return True
            time.sleep(0.01)
        raise AssertionError(f"{item} not seen; got {self.events}")


def start(enabled=True, muted=False):
    service = VoiceService(enabled, muted, "", 0.8)
    mic = FakeMic()
    service._open = mic.open
    rec = Recorder(service)

    def listener(rate):
        return WakeWordListener(lambda r: FakeRecognizer(r, True), lambda r: FakeRecognizer(r, False), rate, 0.8)

    thread = threading.Thread(target=service._loop, args=(listener,), daemon=True)
    thread.start()
    return service, mic, rec, thread


def stop(service, thread):
    service._control.put(("stop", None))
    thread.join(2)
    assert not thread.is_alive()


def test_wake_and_command_through_the_thread():
    service, mic, rec, thread = start()
    rec.wait_for(("status", Status.READY))
    mic.say("hey", "capri", "open", "discord", 1.0)
    rec.wait_for(("command", "open discord"))
    assert ("wake", "hey capri") in rec.events
    stop(service, thread)


def test_muted_never_opens_the_microphone():
    service, mic, rec, thread = start(muted=True)
    rec.wait_for(("status", Status.MUTED))
    time.sleep(0.2)
    assert mic.opened == 0
    service.listen_now()                       # push-to-talk while muted
    rec.wait_for(("no_command",))
    assert mic.opened == 0
    service.set_muted(False)
    rec.wait_for(("status", Status.READY))
    assert mic.opened == 1
    rec.events.clear()
    service.set_muted(True)
    rec.wait_for(("status", Status.MUTED))
    assert mic.closed >= 1
    stop(service, thread)


def test_voice_off_closes_mic_but_push_to_talk_opens_it_for_one_command():
    service, mic, rec, thread = start(enabled=False)
    rec.wait_for(("status", Status.VOICE_OFF))
    assert mic.opened == 0
    mic.say(0.3, "open", "spotify", 1.0)
    service.listen_now()
    rec.wait_for(("command", "open spotify"))
    deadline = time.monotonic() + 3
    while mic.closed == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert mic.closed == 1, "mic should close again after the push-to-talk command"
    stop(service, thread)


def test_stalled_microphone_is_reopened(monkeypatch):
    import capri.voice.service as svc
    monkeypatch.setattr(svc, "STALL_SECONDS", 0.3)
    service, mic, rec, thread = start()
    rec.wait_for(("status", Status.READY))
    mic.stalled = True                          # e.g. PC went to sleep
    deadline = time.monotonic() + 3
    while mic.opened < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert mic.opened >= 2
    mic.stalled = False
    mic.say("capri", "open", "discord", 1.0)
    rec.wait_for(("command", "open discord"))   # still works after reconnecting
    stop(service, thread)


def test_mic_open_failure_reports_and_retries(monkeypatch):
    import capri.voice.service as svc
    monkeypatch.setattr(svc, "RETRY_SECONDS", 0.2)
    service = VoiceService(True, False, "", 0.8)
    attempts = []

    def failing_open(audio):
        attempts.append(1)
        raise OSError("Error opening InputStream: no device")

    service._open = failing_open
    rec = Recorder(service)
    thread = threading.Thread(target=service._loop, args=(lambda r: None,), daemon=True)
    thread.start()
    rec.wait_for(("status", Status.MIC_ERROR))
    time.sleep(0.7)
    assert len(attempts) >= 2
    stop(service, thread)


# -- Assistant: what the panel shows --------------------------------------------
@pytest.fixture
def assistant():
    controller = CompanionController()
    service = VoiceService(True, False, "", 0.8)   # not started: we emit its signals by hand
    return Assistant(controller, Settings(), service), controller, service


def test_panel_follows_voice_events(assistant):
    a, controller, service = assistant
    service.status_changed.emit(Status.READY, "USB Mic")
    assert (controller.state, controller.message) == (State.IDLE, "Waiting for wake word...")
    assert ("Mic", "USB Mic") in controller.entries
    assert ("Local", "audio never leaves this PC") in controller.entries
    service.wake.emit("hey capri", 0.93)
    assert controller.state is State.LISTENING and controller.message == "Listening..."
    service.partial.emit("open disc")
    assert controller.message == '"open disc"'
    service.command.emit("open discord")
    assert controller.state is State.IDLE and controller.message == 'Heard: "open discord"'
    assert ("Heard", '"open discord"') in controller.entries
    a._back_to_idle(a._generation)
    assert controller.message == "Waiting for wake word..."


def test_status_change_does_not_interrupt_listening(assistant):
    a, controller, service = assistant
    service.wake.emit("capri", 0.9)
    service.status_changed.emit(Status.READY, "")
    assert controller.state is State.LISTENING


def test_missing_model_is_an_error_with_fix(assistant):
    a, controller, service = assistant
    service.status_changed.emit(Status.MODEL_MISSING, "run setup_voice.bat")
    assert controller.state is State.ERROR and controller.message == "Voice model missing."
    assert ("Fix", "run setup_voice.bat") in controller.entries


def test_rejected_wake_changes_nothing(assistant):
    a, controller, service = assistant
    service.status_changed.emit(Status.READY, "")
    before = (controller.state, controller.message, list(controller.entries))
    service.rejected.emit("[unk] capri", 0.4)
    assert (controller.state, controller.message, list(controller.entries)) == before


def test_command_handler_hook(assistant):
    a, controller, service = assistant
    got = []
    a.command_handler = got.append
    service.command.emit("open discord")
    assert got == ["open discord"] and controller.state is State.PROCESSING


def test_voice_settings_round_trip():
    s = Settings(voice_enabled=False, mic_muted=True, input_device="USB Mic", wake_threshold=0.9)
    s.save()
    loaded = Settings.load()
    assert (loaded.voice_enabled, loaded.mic_muted, loaded.input_device, loaded.wake_threshold) == \
        (False, True, "USB Mic", 0.9)
    Settings.path().write_text('{"wake_threshold": 7, "input_device": 3, "voice_enabled": "yes"}')
    loaded = Settings.load()
    assert loaded.wake_threshold == 1.0 and loaded.input_device == "" and loaded.voice_enabled is True
    Settings.path().unlink()


def test_hotkey_parsing():
    assert hotkeys.parse("ctrl+alt+c") == (0x0002 | 0x0001, ord("C"))
    assert hotkeys.parse("Ctrl + Alt + Shift + C") == (0x0007, ord("C"))
    assert hotkeys.parse("win+f9") == (0x0008, 0x78)
    assert hotkeys.parse("ctrl+space") == (0x0002, 0x20)
    for bad in ("c", "", "ctrl+", "hyper+c", "ctrl+banana"):
        with pytest.raises(ValueError):
            hotkeys.parse(bad)
    assert hotkeys.pretty("ctrl+alt+shift+c") == "Ctrl+Alt+Shift+C"
