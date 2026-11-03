"""v1.39: roaming - now and then she walks somewhere else along the bottom of the screen, legs stepping."""

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


def test_she_walks_to_a_spot_and_stands_there():
    c = companion()
    show = roam.RoamShow(c, rig, enabled=lambda: True)
    assert show.walk(900)
    assert c.busy_elsewhere and show.active
    strides = set()
    end = time.time() + 10
    while show.active and time.time() < end:
        app.processEvents()
        strides.add(round(show.fx.pose.stride, 1))
        time.sleep(0.005)
    assert not show.active and c.remembered == 1 and c.shown == 1 and not c.busy_elsewhere
    feet_x = c.moved_to.x() + 40 + 45
    assert abs(feet_x - 900) <= 1 and c.moved_to.y() + 30 + 250 == 860
    assert max(strides) > 0.5 and min(strides) < -0.5                  # both legs stepped


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
    end = time.time() + 1.2
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    c.controller.state = State.LISTENING
    run(show, 2)
    feet_x = c.moved_to.x() + 40 + 45
    assert not show.active and 300 < feet_x < 1450                     # stopped part way


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
    show._maybe_walk()
    assert show.active
    run(show)
    assert show._due > time.monotonic() + roam.WAIT[0] - 15


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
    assert r.assistant.settings.roam is False and stopped and "stay put" in r.controller.message
    r.router.handle("start roaming")
    assert r.assistant.settings.roam is True
