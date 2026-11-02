"""v1.24: she understands a command however you say it - extra words, other words, another order."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from variations import CASES, CHAT  # noqa: E402

from capri.commands.understand import understand  # noqa: E402

KNOWN = {"discord", "spotify", "steam", "youtube", "opera"}
SAID = [(kind, what, phrase) for kind, what, phrases in CASES for phrase in phrases]


@pytest.mark.parametrize("kind, what, phrase", SAID)
def test_every_way_of_saying_it(kind, what, phrase):
    intent = understand(phrase, lambda name: name in KNOWN)
    assert intent.kind.value == kind and (not what or intent.query == what or what in intent.targets), \
        (phrase, intent)


@pytest.mark.parametrize("sentence", CHAT)
def test_chat_never_turns_into_a_command(sentence):
    assert understand(sentence, lambda name: name in KNOWN).kind.value in ("unknown", "chat"), sentence


def test_she_acts_on_a_wordy_command():
    from test_v11 import FakeDesktop, rig
    d = FakeDesktop()
    r = rig(d)
    r.router.handle("hey capri i'm done for today shut down my computer")
    assert r.speaker.lines[-1] == "Look up there, think we can make it?"      # still asks first
    r.service.command.emit("no")
    r.router.handle("could you please open up discord for me real quick")
    assert any("Discord" in str(c) for c in r.system.calls)


def test_dropping_words_never_changes_what_you_meant():
    # only filler words are ever left out: "shut steam down" must not become "shut down"
    assert understand("shut steam down", lambda n: n in KNOWN).kind.value == "close"
    assert understand("the time flies", lambda n: n in KNOWN).kind.value in ("unknown", "chat")


# -- her animations, smooth -------------------------------------------------------------------------------------
def _standing():
    from test_look import make_window
    w = make_window()
    w.figure_pose()                                                      # settle on her idle pose
    return w


def test_she_eases_into_a_new_pose_instead_of_snapping():
    import time
    from capri.states import State
    from capri.ui.character_window import BODY_POSES
    w = _standing()
    w.set_state(State.ERROR)                                             # confused: leans back
    target = BODY_POSES["confused"]["lean"]
    leans = []
    for _ in range(30):
        time.sleep(0.012)
        leans.append(w.figure_pose().lean)
    assert abs(leans[0]) < abs(target) * 0.4                             # not there at once...
    assert any(abs(target) * 0.3 < abs(x) < abs(target) * 0.9 for x in leans)   # ...passing through the middle
    assert abs(leans[-1] - target) < 0.01                                # ...and arriving


def test_fast_frames_only_while_she_moves():
    import time
    from capri.states import State
    from capri.ui.character_window import IDLE_FPS, TALK_FPS
    w = _standing()
    w.set_state(State.LISTENING)
    assert w._timer.interval() == int(1000 / TALK_FPS)                    # 60 fps while she moves
    for _ in range(40):
        time.sleep(0.012)
        w.figure_pose()
        w._tick()
    assert w._timer.interval() == int(1000 / IDLE_FPS)                    # still again: back to the light rate


def test_blinks_close_and_open_smoothly():
    import time
    w = _standing()
    w._next_blink = time.monotonic() - 1
    w._tick()
    seen = []
    for _ in range(25):
        seen.append(w.figure_pose().blink)
        time.sleep(0.008)
    assert max(seen) > 0.8 and any(0.15 < b < 0.75 for b in seen)        # in-between frames, not on / off


def test_happy_eyes_after_something_went_well():
    from capri.states import State
    w = _standing()
    w.set_state(State.SUCCESS, "happy")
    assert w.figure_pose().eyes == "happy"
    w.set_state(State.IDLE)
    assert w.figure_pose().eyes == ""


def test_idle_activities_run_smoothly():
    from capri.ui.idle_acts import FPS
    assert FPS >= 30
