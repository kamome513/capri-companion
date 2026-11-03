"""v1.40: real glitches every few minutes, dangling while you drag her, the Neon body look, the text box that
only pops up when she talks back, and frame timers that tick on time."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QRectF, QStandardPaths, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ui import glitch as gl  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def picture(w=200, h=400) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    for i in range(0, h, 20):
        p.fillRect(40, i, 120, 10, QColor(255, 40, 90) if i % 40 else QColor(50, 255, 140))
    p.end()
    return img


# -- real glitches -----------------------------------------------------------------------------------------------
def test_a_glitch_every_few_minutes():
    clock = Clock()
    g = gl.RealGlitch(every=lambda: 180, rng=random.Random(1), clock=clock)
    assert not g.due(True)
    clock.t += 180 * 1.31
    assert g.due(True) and not g.due(False)                     # waits for a moment it's allowed
    g.start()
    assert g.active and 0.3 < g.segments[-1].end < 0.9
    kinds = {s.kind for s in g.segments}
    assert {"tear", "drop"} <= kinds and ("freeze" in kinds)
    clock.t += 1.0
    assert not g.active


def test_never_means_never():
    clock = Clock()
    g = gl.RealGlitch(every=lambda: 0, clock=clock)
    clock.t += 10 ** 6
    assert not g.due(True)


def test_each_part_of_a_glitch_draws():
    clock = Clock()
    g = gl.RealGlitch(every=lambda: 180, rng=random.Random(3), clock=clock)
    g.start()
    snap = picture()
    seen = set()
    while g.active:
        seg = g.segment()
        out = QImage(200, 400, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(0)
        p = QPainter(out)
        g.paint(p, snap, QRectF(40, 0, 120, 400))
        p.end()
        a = np.frombuffer(out.constBits(), np.uint8).reshape(400, 200, 4)
        if seg is not None:
            seen.add(seg.kind)
            if seg.kind == "drop":                                # she's (almost) gone for that frame
                assert a[..., 3].mean() < 40
            elif seg.kind == "tear":                              # torn: not just the picture again
                ref = np.frombuffer(snap.constBits(), np.uint8).reshape(400, 200, 4)
                assert np.abs(a.astype(int) - ref).sum() > 0
        clock.t += 1 / 60
    assert {"tear", "drop"} <= seen


def test_a_frozen_frame_holds_still():
    clock = Clock()
    g = gl.RealGlitch(every=lambda: 180, clock=clock)
    g.segments, g.started = [gl.Segment(0, 1, "freeze")], clock.t
    first, second = picture(), picture()
    second.fill(0)
    for snap in (first, second):
        out = QImage(200, 400, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(0)
        p = QPainter(out)
        g.paint(p, snap, QRectF(40, 0, 120, 400))
        p.end()
        clock.t += 0.02
    assert g.frozen is not None and g.frozen.cacheKey() != second.cacheKey()


# -- dragging ---------------------------------------------------------------------------------------------------------
def test_she_swings_behind_your_movement_and_settles():
    clock = Clock()
    sway = gl.DragSway(clock=clock)
    sway.grab()
    for i in range(20):                                          # you drag her right, fast
        clock.t += 1 / 60
        sway.moved(100 + i * 25)
        sway.step(1 / 60)
    assert sway.angle < -0.1                                     # she trails behind (leans left)
    moves = sway.pose_moves(clock.t)
    assert moves["energy"] == 1.0 and "stride" in moves and moves["sweep"] > 0.5
    sway.drop()
    for _ in range(240):                                         # let go: she swings back and settles
        clock.t += 1 / 60
        sway.step(1 / 60)
    assert abs(sway.angle) < 0.01 and not sway.swinging


def test_the_window_swings_and_glitches_while_held():
    from test_v111 import companion
    ch = companion().character
    ch.set_held(True)
    assert ch.sway.held and ch._special()
    ch.set_held(False)
    ch.glitch_now()
    assert ch.real_glitch.active
    ch.resize(300, 600)
    img = QImage(300, 600, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    ch.render(img)                                               # draws through the glitch without falling over


# -- the Neon look -----------------------------------------------------------------------------------------------------
def test_neon_keeps_her_shape_and_lights_her_edges():
    from capri.app import asset_root
    from capri.ui.neon import neon_array
    from capri.ui.rig import _to_array
    a = _to_array(QImage(str(asset_root() / "capri_v2" / "body" / "standing.png")))
    n = neon_array(a)
    assert n.shape == a.shape and (n[..., 3] == a[..., 3]).all()        # same silhouette: the rig cuts the same
    inside = a[..., 3] > 40
    assert n[inside][:, :3].mean() < a[inside][:, :3].mean() * 0.9     # darker overall...
    bright = (n[..., :3].max(-1) > 200) & inside
    assert 0.08 < bright.sum() / inside.sum() < 0.6                     # ...with glowing edges


def test_body_look_is_a_setting():
    from capri.settings import Settings
    from capri.ui.neon import LOOKS
    assert Settings().body_look == "neon" and set(LOOKS) == {"neon", "full"}


# -- the text box popping up -------------------------------------------------------------------------------------------
def test_text_box_pops_up_only_when_she_talks_back():
    import time
    from test_v111 import companion
    from capri.states import State
    c = companion()
    s = c.settings
    s.panel_popup, s.show_panel = True, True
    c.show()
    c.controller.set_state(State.IDLE, "Waiting for wake word...")
    c._popup_until = 0.0
    c._apply_visibility()
    assert not c._panel_wanted()                                 # just her
    c.controller.set_state(State.LISTENING, "Listening...")
    assert c._panel_wanted()                                     # you're talking to her: it's up
    c.controller.set_state(State.SUCCESS, "Opened Chrome.")
    c.controller.set_state(State.IDLE, "Opened Chrome.")
    assert c._panel_wanted() and c._popup_until > time.monotonic() + 3   # her answer stays up a moment
    c._popup_until = time.monotonic() - 1
    assert not c._panel_wanted()                                 # and then it goes again
    s.panel_popup = False
    assert c._panel_wanted()


# -- smooth frames -------------------------------------------------------------------------------------------------------
def test_animation_timers_tick_on_time():
    from capri.ui import fx
    from test_v111 import companion
    assert fx.precise_timer(None).timerType() == Qt.TimerType.PreciseTimer
    assert companion().character._timer.timerType() == Qt.TimerType.PreciseTimer


def test_qt_problems_go_in_the_log(tmp_path, monkeypatch):
    import logging
    from PySide6.QtCore import qWarning
    from capri import logs
    monkeypatch.setattr(logs, "log_dir", lambda: tmp_path)
    path = logs.setup()
    qWarning("The X11 connection broke (error 1). Did the X11 server die?")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "X11 connection broke" in path.read_text()
    assert (tmp_path / "crash.log").exists()                     # where a hard crash would be written
