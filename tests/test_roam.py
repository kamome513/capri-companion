"""Roaming - now and then she teleports somewhere else along the bottom of the screen (v1.39 walked; v1.40
teleports, with her power closing in around her first)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.commands.parser import Kind, parse  # noqa: E402
from capri.states import State  # noqa: E402
from capri.ui import roam  # noqa: E402
from test_fling import FakeCompanion, rig  # noqa: E402


def companion():
    c = FakeCompanion()
    c.controller = SimpleNamespace(state=State.IDLE)
    c.character.isVisible = lambda: True
    c.panel.isVisible = lambda: True
    return c


def run(show, seconds=10):
    end = time.time() + seconds
    while show.active and time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def test_her_legs_come_apart_for_walking():
    r = rig()
    assert r.legs is not None and set(r.legs) == {"left", "right"}
    assert r.hip_joints["left"].x() < r.hip_joints["right"].x()


def test_she_teleports_to_a_spot_and_stands_there():
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    assert show.walk(900)
    assert c.busy_elsewhere and show.active and len(show.fx.shards) == roam.SHARDS and show.fx.sprite is not None
    seen = set()
    end = time.time() + 6
    while show.active and time.time() < end:
        app.processEvents()
        t = show.fx.t
        seen.add("gather" if t < roam.GATHER else "gone" if t < roam.GATHER + roam.ENGULF + roam.VANISH + roam.TRAVEL
                 else "arrive")
        time.sleep(0.005)
    assert seen == {"gather", "gone", "arrive"}
    assert not show.active and c.remembered == 1 and c.shown == 1 and not c.busy_elsewhere
    feet_x = c.moved_to.x() + 40 + 45
    assert abs(feet_x - 900) <= 1 and c.moved_to.y() + 30 + 250 == 860


def test_the_teleport_paints():
    from PySide6.QtGui import QImage
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    show.walk(300)
    img = QImage(1600, 500, QImage.Format.Format_ARGB32_Premultiplied)
    for t in (0.2, roam.GATHER + 0.1, roam.GATHER + roam.ENGULF + 0.05, roam.GATHER + roam.ENGULF + roam.VANISH + 0.05,
              roam.GATHER + roam.ENGULF + roam.VANISH + roam.TRAVEL + 0.2, show.length - 0.1):
        show.fx.t = t
        img.fill(0)
        show.fx.render(img)                                             # every beat draws without falling over
    show.stop()


def test_a_teleport_phrase():
    assert parse("teleport somewhere").kind is Kind.ROAM and parse("teleport").query == "walk"


@pytest.mark.parametrize("state", [State.LISTENING, State.PROCESSING, State.SPEAKING])
def test_not_while_shes_needed(state):
    c = companion()
    c.controller.state = state
    assert not roam.RoamShow(c, rig, enabled=lambda: True).walk(900)


def test_a_finished_message_doesnt_stop_her():
    c = companion()
    c.controller.state = State.ERROR                                   # e.g. an old "voice model missing"
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    assert show.walk(900)
    run(show)


def test_hey_capri_stops_her_where_she_is():
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    show.walk(300)
    end = time.time() + 0.3
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    c.controller.state = State.LISTENING
    run(show, 2)
    feet_x = c.moved_to.x() + 40 + 45
    assert not show.active and abs(feet_x - 1450) <= 1                 # needed before she left: still here


def test_she_stays_on_her_screen():
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    assert show.walk(-5000)
    run(show, 20)
    assert c.moved_to.x() + 40 + 45 >= 0


def test_off_means_no_walks():
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: False)
    show._due = 0
    show._maybe_walk()
    assert not show.active


def test_now_and_then_by_herself():
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    show._due = 0
    home = c.content_geometry().center().x()
    show._maybe_walk()
    assert show.active and show.home_x is not None
    run(show)
    assert time.monotonic() + roam.RoamShow.HOME_AFTER[0] - 15 < show._due < time.monotonic() + 46
    show._due = 0
    show._maybe_walk()                                   # v2.3: back to her corner after a while
    run(show)
    assert show.home_x is None and abs(c.content_geometry().center().x() - home) < 3
    assert show._due > time.monotonic() + roam.WAIT[0] - 15


def test_she_stays_put_right_after_a_command_and_in_games():
    """v2.3: "close opera and open deadlock" - she teleported mid-command while the game started."""
    from capri.states import State
    c = companion()
    gaming = [False]
    show = roam.RoamShow(c, rig, enabled=lambda: True, quiet=lambda: gaming[0])
    c.controller.state = State.LAUNCHING                 # "Opening Deadlock..."
    assert not show.can_walk()
    c.controller.state = State.SUCCESS                   # "Opened Deadlock."
    assert not show.can_walk()                           # just worked for you: she waits a minute
    show._calm_since -= roam.RoamShow.CALM + 1
    gaming[0] = True
    assert not show.can_walk()                           # the game's up: no wandering
    gaming[0] = False
    show._calm_since -= roam.RoamShow.CALM + 1
    assert show.can_walk()


def test_roaming_is_off_unless_you_turn_it_on():
    from capri.settings import Settings
    assert Settings().roaming is False


@pytest.mark.parametrize("text,which", [
    ("go for a walk", "walk"), ("hey capri take a walk", "walk"), ("walk around", "walk"),
    ("stretch your legs", "walk"), ("can you go roam around", "walk"), ("wander around for a bit", "walk"),
    ("stay there", "stay"), ("stop walking around", "stay"), ("stay put", "stay"), ("don't wander", "stay"),
    ("start roaming", "on"), ("feel free to wander", "on"),
])
def test_what_she_understands(text, which):
    intent = parse(text)
    assert intent.kind is Kind.ROAM and intent.query == which


def test_stay_there_turns_it_off():
    from test_v11 import FakeDesktop, rig as router_rig
    r = router_rig(FakeDesktop())
    stopped = []
    r.router.services.roam = SimpleNamespace(stop=lambda: stopped.append(1), walk=lambda: True)
    r.router.services.settings = r.assistant.settings
    r.router.handle("stay there")
    assert r.assistant.settings.roaming is False and stopped and "stay put" in r.controller.message
    r.router.handle("start roaming")
    assert r.assistant.settings.roaming is True
