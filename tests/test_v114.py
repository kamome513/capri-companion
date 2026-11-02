"""v1.14: your own fixes for words she mishears ("to school" -> "discord")."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands import parser  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.settings import Settings  # noqa: E402


@pytest.fixture(autouse=True)
def no_fixes():
    parser.set_corrections([])
    yield
    parser.set_corrections([])


def test_your_fix_turns_what_she_heard_into_what_you_meant():
    assert parse("open to school").targets != ("discord",)
    parser.set_corrections([["to school", "discord"]])
    assert parse("hey capri open to school") == parse("open discord")
    assert parse("close to school").targets == ("discord",)
    assert parse("mute me on to school").kind is Kind.DISCORD


def test_whole_words_only_and_longest_first():
    parser.set_corrections([["to school", "discord"], ["open to school", "open spotify"]])
    assert parse("open to school").targets == ("spotify",)            # the longer fix wins
    assert parser.correct("back to schoolbag") == "back to schoolbag"  # not inside another word


def test_tell_her_by_voice():
    s = Settings(slang=False)
    s.corrections = []
    r = rig(FakeDesktop(), settings=s)
    r.service.command.emit("when I say to school I mean discord")
    assert s.corrections == [["to school", "discord"]]
    assert r.controller.message == 'Got it. When I hear "to school", I\'ll take it as "discord".'
    r.service.command.emit("open to school")
    assert r.system.calls and r.system.calls[-1][0] == "program"       # Discord opened
    assert Settings.load().corrections == [["to school", "discord"]]  # kept


def test_saying_it_again_replaces_the_old_fix():
    s = Settings(slang=False)
    s.corrections = [["to school", "steam"]]
    r = rig(FakeDesktop(), settings=s)
    r.service.command.emit("if you hear to school it means discord")
    assert s.corrections == [["to school", "discord"]]


def test_fixes_survive_a_restart(tmp_path):
    s = Settings()
    s.corrections = [["to school", "discord"], ["spot a phi", "spotify"]]
    s.save()
    assert Settings.load().corrections == [["to school", "discord"], ["spot a phi", "spotify"]]


def test_the_settings_table():
    from test_commands import make_catalog  # noqa: F401
    from capri.ui.settings_window import SettingsWindow
    r = rig(FakeDesktop())
    s = r.assistant.settings
    s.corrections = [["to school", "discord"]]
    win = SettingsWindow(r.router, s, QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [])
    assert win.fixes.rowCount() == 1 and win.fixes.item(0, 1).text() == "discord"
    win.show()
    r.assistant.last_heard = "open spot a phi"
    win._refresh_last_heard()
    assert 'open spot a phi' in win.last_heard.text() and win.fix_last.isEnabled()
    win._add_fix("spot a phi")
    win.fixes.item(1, 1).setText("spotify")                             # what you type in the table
    assert s.corrections == [["to school", "discord"], ["spot a phi", "spotify"]]
    assert parse("open spot a phi").targets == ("spotify",)
    win.fixes.setCurrentCell(0, 0)
    win._remove_fix()
    assert s.corrections == [["spot a phi", "spotify"]]
