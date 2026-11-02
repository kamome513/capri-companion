"""v1.10: search mode that waits for you, "go into downloads" / "minimise X" visits, the
chat window, game drone mode and her idle activities."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import random  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QRect, QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.games import NEVER_STARTED, GameWatch  # noqa: E402
from capri.commands.parser import Intent, Kind, parse  # noqa: E402
from capri.states import State  # noqa: E402


def companion():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(),
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    return c


# -- parsing ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, kind", [
    ("hey capri switch to search mode", Kind.SEARCH_MODE), ("switch to search mode", Kind.SEARCH_MODE),
    ("open chat", Kind.CHAT_WINDOW), ("open the chat window", Kind.CHAT_WINDOW),
    ("drone mode", Kind.DRONE_ON), ("game mode", Kind.DRONE_ON), ("normal mode", Kind.DRONE_OFF),
    ("minimise discord", Kind.MINIMIZE)])
def test_new_commands_parse(text, kind):
    assert parse(text).kind is kind


@pytest.mark.parametrize("text", ["go into download folder", "go into downloads", "hey capri go into my downloads folder"])
def test_go_into_a_folder(text):
    intent = parse(text)
    assert intent.kind is Kind.OPEN and intent.targets[0] in ("download", "downloads")


# -- search mode ---------------------------------------------------------------------------------------------------
def test_search_mode_waits_long_for_your_answer_and_shows_on_the_panel():
    from capri.assistant import ASK_WAIT
    r = rig(FakeDesktop())
    waits = []
    r.service.listen_now = lambda *a: waits.append(a[0] if a else None)
    r.service.command.emit("hey capri switch to search mode")
    assert waits == [ASK_WAIT] and ASK_WAIT >= 12           # time to think of what to search
    assert r.speaker.lines[-1] == "Search mode on. What do you want to search?"
    r.service.no_command.emit()                              # a pause: she asks again, still in search mode
    assert "SEARCH MODE" in r.controller.message and len(waits) == 2


# -- "go into downloads": Explorer, then she zaps the folder ------------------------------------------------------------
def test_go_into_downloads_uses_the_folder_visit(monkeypatch):
    monkeypatch.setattr("os.path.isdir", lambda p: True)
    opened = []
    r = rig(FakeDesktop(), open_folder=lambda label, path: opened.append((label, path)))
    folder = "C:/Users/me/Downloads"
    r.router.catalog._load_places = lambda: {"downloads": folder, "download": folder}
    r.router.catalog._scanned = -1e9
    r.service.command.emit("go into download folder")
    assert opened and opened[0][0].lower() == "downloads"
    assert not [c for c in r.system.calls if c[0] == "open"]          # not opened twice


# -- "minimise discord": she dashes over and zaps its minimise button ---------------------------------------------------
class WindowDesktop(FakeDesktop):
    def main_window(self, pids):
        return 77


def test_minimise_goes_through_the_visit_and_minimises_on_impact():
    d = WindowDesktop()
    visits = []
    r = rig(d, minimize_visit=lambda name, pids, then: visits.append((name, tuple(pids), then)))
    r.service.command.emit("minimise discord")
    assert visits and visits[0][:2] == ("Discord", (10,))
    assert ("minimize", (10,)) not in d.calls                          # not before the bolt lands
    visits[0][2]()
    assert ("minimize", (10,)) in d.calls


class Element:
    def __init__(self, rect):
        self.rect, self.pressed = rect, 0

    def press(self):
        self.pressed += 1


class UI:
    def __init__(self, found):
        self.found = found

    def buttons(self, hwnd, names, control=None, with_rects=False):
        return [e for n, e in self.found if n in names]


class Visit:
    def __init__(self):
        self.calls = []

    def visit(self, target, then, window=None, near=False):
        self.calls.append((target, window))
        then()


class VisitDesktop:
    def __init__(self):
        self.explorers = [1]

    def main_window(self, pids):
        return 5

    def hwnd_rect(self, hwnd):
        return (100, 100, 700, 500)

    def windows_of_class(self, cls):
        return list(self.explorers)


def test_visit_actions_find_the_minimise_button():
    from capri.ui.visit_actions import VisitActions
    button = Element((640, 100, 686, 130))
    visit, done = Visit(), []
    va = VisitActions(visit, VisitDesktop(), UI([("Minimize", button)]), lambda t: None)
    va.minimize("Discord", [10], lambda: done.append(1))
    assert settle(2, lambda: done)
    target, window = visit.calls[0]
    assert target == QRect(640, 100, 46, 30) and window == QRect(100, 100, 600, 400)


def test_visit_actions_zap_downloads_in_explorer(monkeypatch):
    from capri.ui import visit_actions
    monkeypatch.setattr(visit_actions.time, "sleep", lambda s: None)   # (patches time.sleep for the test only)
    d = VisitDesktop()
    entry = Element((110, 300, 220, 324))
    visit, opened = Visit(), []

    def open_item(target):
        opened.append(target)
        d.explorers.append(2)                                       # Explorer opens a new window
    va = visit_actions.VisitActions(visit, d, UI([("Downloads", entry)]), open_item)
    va.open_folder("Downloads", "C:/Users/me/Downloads")
    assert settle(2, lambda: entry.pressed)                            # zapped -> Explorer goes there
    assert opened[0].endswith("explorer.exe") and len(opened) == 1
    assert visit.calls[0][0] == QRect(110, 300, 110, 24)


def test_visit_actions_fall_back_to_just_opening_the_folder(monkeypatch):
    from capri.ui import visit_actions
    monkeypatch.setattr(visit_actions.time, "sleep", lambda s: None)
    monkeypatch.setattr(visit_actions, "EXPLORER_WAIT", 0.05)
    opened = []
    va = visit_actions.VisitActions(Visit(), VisitDesktop(), UI([]), opened.append)
    va.open_folder("Downloads", "C:/Users/me/Downloads")              # no Explorer window ever shows up
    assert settle(2, lambda: "C:/Users/me/Downloads" in opened)


def test_the_visit_show_zaps_then_brings_her_home():
    from capri.ui.visit import VisitShow
    c = companion()
    show = VisitShow(c)
    hits = []
    show.visit(QRect(500, 300, 46, 30), lambda: hits.append(show.fx.zap is not None), window=QRect(200, 300, 400, 300))
    assert show.active and show.fx.isVisible() and not c.character.isVisible()
    assert settle(2, lambda: hits) and hits == [True]                  # the action runs when the bolt lands
    assert settle(3, lambda: not show.active)
    assert c.character.isVisible() and not show.fx.isVisible()


# -- chat window -----------------------------------------------------------------------------------------------
def test_typing_in_the_chat_window_works_like_talking():
    from capri.ui.chat_window import ChatWindow
    r = rig(FakeDesktop())
    chat = ChatWindow(r.assistant, QImage(16, 16, QImage.Format.Format_ARGB32))
    chat.input.setText("open discord")
    chat.send()
    assert ("you", "open discord") in chat.lines
    assert r.system.calls and r.system.calls[0][0] == "program"       # Discord launched
    assert settle(2, lambda: any(who == "capri" and "Discord" in text for who, text in chat.lines))
    assert chat.input.text() == ""


def test_the_chat_window_command_opens_it():
    opened = []
    r = rig(FakeDesktop(), open_chat=lambda: opened.append(1))
    r.service.command.emit("open the chat window")
    assert opened == [1] and r.controller.state is State.SUCCESS


# -- game mode: the drone ---------------------------------------------------------------------------------------------
def test_game_watch_turns_her_into_the_drone_and_back():
    states = []
    watch = GameWatch(states.append, lambda: [])
    watch.started("Deadlock", "C:/Games/Deadlock")
    assert states == [True] and watch.active
    watch._on_check(True)                                            # the game is running
    watch._on_check(False)
    assert states == [True]                                          # one miss isn't enough
    watch._on_check(False)
    assert states == [True, False] and not watch.active


def test_game_watch_gives_up_if_the_game_never_starts():
    now = [0.0]
    states = []
    watch = GameWatch(states.append, lambda: [], clock=lambda: now[0])
    watch.started("Deadlock", "C:/Games/Deadlock")
    now[0] = NEVER_STARTED + 1
    watch._on_check(False)
    assert states == [True, False]


def test_game_watch_sees_the_games_own_processes():
    proc = SimpleNamespace(exe="C:/Games/Deadlock/game/bin/win64/project8.exe")
    watch = GameWatch(lambda on: None, lambda: [proc])
    watch.started("Deadlock", "C:/Games/Deadlock")
    assert watch.running()
    watch.folder = "C:/Games/Other/"
    assert not watch.running()


def test_game_watch_off_in_settings():
    states = []
    GameWatch(states.append, lambda: [], enabled=lambda: False).started("Deadlock", "C:/x")
    assert states == []


def test_drone_mode_swaps_her_for_the_disk():
    c = companion()
    c.set_drone(True)
    assert c.drone_window.isVisible() and not c.character.isVisible()
    img = QImage(c.drone_window.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    c.drone_window.render(img, QPoint())
    assert any(img.pixelColor(x, 56).alpha() > 0 for x in range(0, 112, 4))   # the disk is drawn
    c.set_drone(False)
    assert c.character.isVisible() and not c.drone_window.isVisible()


class DroneCompanion:
    def __init__(self):
        self.drone = []

    def set_drone(self, on):
        self.drone.append(on)


def test_drone_voice_commands():
    r = rig(FakeDesktop())
    r.router.companion = DroneCompanion()
    r.service.command.emit("drone mode")
    r.service.command.emit("back to normal")
    assert r.router.companion.drone == [True, False]


# -- idle activities -----------------------------------------------------------------------------------------------
def test_idle_activities_start_on_their_own_and_stop_when_busy():
    from capri.ui.idle_acts import FIRST, IdleActs
    acts = IdleActs(random.Random(1))
    assert not acts.update(0.0, True) and acts.act is None             # not straight away
    assert acts.update(FIRST[1] + 1, True) and acts.act is not None
    assert acts.update(FIRST[1] + 2, False) and acts.act is None       # you talked to her: she stops
    acts.update(FIRST[1] + 3, True)
    assert acts.act is None                                            # and waits a while before the next


def test_idle_activities_can_be_turned_off():
    from capri.ui.idle_acts import IdleActs
    acts = IdleActs(random.Random(1))
    acts.enabled = False
    acts.update(0.0, True)
    assert not acts.update(10_000.0, True) and acts.act is None


def test_on_a_call_with_d_she_holds_her_hand_to_her_ear_and_they_take_turns():
    from capri.ui.idle_acts import IdleActs
    acts = IdleActs(random.Random(2))
    acts.begin("call", 0.0, length=15)
    assert acts.pose(1.0) == "look_around"
    speakers = {acts.talking(t / 10) for t in range(10, 140)}
    assert speakers == {"d", "capri"}


@pytest.mark.parametrize("name", ["glitch", "gaming", "watching", "call"])
def test_each_activity_draws(name):
    c = companion()
    w = c.character
    assert w.play_act(name) and w.acts.act == name
    w.acts.start -= 2.0                                              # a couple of seconds in
    if name == "glitch":
        now = time.monotonic()
        w.acts._bursts = [(now - 1, now + 1)]
    plain = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    plain.fill(0)
    w.render(plain, QPoint())
    w.acts.act = None
    bare = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    bare.fill(0)
    w.render(bare, QPoint())
    assert plain != bare                                             # the activity shows


def test_talking_stops_an_activity():
    c = companion()
    assert c.character.play_act("gaming")
    c.character.set_talking(True)
    assert c.character.acts.act is None
    assert not c.character.play_act("call")                          # not while she's talking
