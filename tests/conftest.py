"""Runs before any test module: headless Qt with two simulated monitors.

Qt reads the platform setting only once, when the first QApplication is
created, so it has to be set here rather than in individual test files.
"""

import json
import os
import tempfile
from pathlib import Path

_screens = {
    "synchronousWindowSystemEvents": True,
    "screens": [
        {"name": "DISPLAY1", "x": 0, "y": 0, "width": 1920, "height": 1080,
         "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},
        {"name": "DISPLAY2", "x": 1920, "y": 0, "width": 2560, "height": 1440,
         "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},
    ],
}
_cfg = Path(tempfile.gettempdir()) / "capri_test_screens.json"
_cfg.write_text(json.dumps(_screens))
os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={_cfg}"


# Nothing in the tests ever goes to the internet to find a song.
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_music_lookups(monkeypatch):
    from capri.integrations import music_find
    monkeypatch.setattr(music_find, "find_track", lambda service, query, *a, **k: None)
    monkeypatch.setattr(music_find, "find_video", lambda query, *a, **k: None)
    monkeypatch.setattr(music_find, "find_song", lambda query, *a, **k: None)


@pytest.fixture(autouse=True)
def _no_answer_lookups(monkeypatch):
    from capri.integrations import answers
    monkeypatch.setattr(answers, "lookup", lambda subject, *a, **k: None)


@pytest.fixture(autouse=True)
def _fake_audio_is_a_voice(monkeypatch):
    """The fake recogniser's "audio" is word markers, not sound: the is-it-a-voice check (tested on
    real sound in test_v123) would call it a chime."""
    from capri.voice import wakeword
    monkeypatch.setattr(wakeword, "voice_check", lambda audio, rate: (True, ""))


def pytest_sessionfinish(session, exitstatus):
    """Tear down the thousands of test windows and objects while Qt is still fully alive. Left to
    PySide's own shutdown pass, one of them is now and then deleted twice (a crash after every test
    has already passed)."""
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for _ in range(3):
        app.processEvents()
    for window in QApplication.topLevelWidgets():
        window.hide()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    app.processEvents()
