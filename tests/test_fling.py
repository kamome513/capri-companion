"""v1.39: throw her - flick and let go: she flies, slams into the screen's edge, slides down, sees stars and
gets back up where she landed."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QRect, QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ui import fling  # noqa: E402

AREA = QRect(0, 0, 1600, 860)            # her screen, minus the taskbar
_RIG = None


def rig():
    global _RIG
    if _RIG is None:
        from capri.app import asset_root
        from capri.ui.rig import Rig
        _RIG = Rig(QImage(str(asset_root() / "capri_v2" / "body" / "standing.png"))).resized(250)
    return _RIG


class Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


class FakeCompanion:
    def __init__(self, feet=QPoint(1450, 860)):
        self.drone = self.perched = self.hidden = self.busy_elsewhere = False
        self.feet = feet
        self.moved_to = None
        self.remembered = self.shown = 0
        self.screen = SimpleNamespace(availableGeometry=lambda: AREA, geometry=lambda: QRect(0, 0, 1600, 900))
        content = QRect(40, 30, 90, 250)                                 # her body inside her window
        self.character = SimpleNamespace(figure_height=lambda: 250, hide=lambda: None, content_rect=lambda: content)
        self.panel = SimpleNamespace(hide=lambda: None)

    def lounging(self):
        return False

    def content_geometry(self):
        return QRect(self.feet.x() - 45, self.feet.y() - 250, 90, 250)

    def _move_character(self, target, screen=None):
        self.moved_to = target

    def _remember_position(self):
        self.remembered += 1

    def show(self):
        self.shown += 1

    def place(self):
        pass


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(fling, "time", c)
    return c


def run(show, clock, seconds=12.0, step=1 / 60):
    states = []
    while show.active and seconds > 0:
        clock.t += step
        seconds -= step
        show._tick()
        if not states or states[-1] != show.state:
            states.append(show.state)
    return states


def make(companion=None, said=None):
    companion = companion or FakeCompanion()
    said = said if said is not None else []
    show = fling.ThrowShow(companion, rig, lambda text, emotion: said.append((text, emotion)))
    return show, companion, said


def test_a_slow_let_go_is_not_a_throw(clock):
    show, c, _ = make()
    assert not show.throw(QPointF(300, -100)) and not show.active


def test_thrown_at_the_wall_she_slams_slides_and_gets_up(clock):
    show, c, said = make()
    assert show.throw(QPointF(-3200, -500))
    assert c.busy_elsewhere
    states = run(show, clock)
    assert states[:3] == ["fly", "slam", "fly"]                            # slams, then BOUNCES off
    assert states[-4:] == ["topple", "dazed", "getup", "fade"] and show.walls[0] == "left"
    assert not show.active and c.shown == 1 and c.remembered == 1 and not c.busy_elsewhere
    assert c.moved_to.x() + 40 + 45 < 1000                              # bounced back off the left wall...
    assert c.moved_to.y() + 30 + 250 == AREA.bottom() + 1               # ...standing on the taskbar
    assert any(e == "angry" for _t, e in said)                          # "Ow! Rude."


def test_the_slam_overloads_the_screen_and_sparks_fly(clock):
    show, c, _ = make()
    show.throw(QPointF(-3500, 0))
    for _ in range(600):
        if show.state == "slam":
            break
        clock.t += 1 / 60
        show._tick()
    fx = show.fx
    e = fx.effects
    assert e.bursts and not e.cracks and e.rings and e.flashes and fx.glitch > 0.5 and fx.stars > 0.5 and fx.impact > 0.5
    assert any(p.kind == "shard" for p in e.particles) and any(p.kind == "spark" for p in e.particles)
    assert any(p.kind == "block" for p in e.particles) and any(p.kind == "glyph" for p in e.particles)
    clock.t += 0.15
    show._tick()
    left = fx.body.centre.x() - fx.fh * fling.WIDTH * fx.body.squash[0]
    assert abs(left - AREA.left()) < 1                                  # flat against the wall, not through it
    img = QImage(1600, 900, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    fx.resize(1600, 900)
    fx.render(img)                                                      # painting doesn't fall over


def test_thrown_at_the_ceiling_she_drops(clock):
    show, c, _ = make()
    show.throw(QPointF(200, -4200))
    states = run(show, clock)
    assert "slam" in states and states[-1] == "fade" and show.walls[0] == "top"


def test_a_gentle_toss_lands_on_her_feet(clock):
    show, c, said = make(FakeCompanion(QPoint(200, 700)))
    assert show.throw(QPointF(1350, 0))
    show.fx.body.spin = 0                                               # no tumbling: feet first
    states = run(show, clock)
    assert "slam" not in states and "land" in states and states[-1] == "fade"
    assert not any(e == "angry" for _t, e in said)


def test_never_off_the_screen(clock):
    for v in (QPointF(-6000, -6000), QPointF(6000, 3000), QPointF(-5000, 2000), QPointF(9000, -9000)):
        show, c, _ = make()
        show.throw(v)
        run(show, clock)
        feet_x = c.moved_to.x() + 40 + 45
        assert AREA.left() <= feet_x <= AREA.right() + 1


@pytest.mark.parametrize("busy", ["drone", "perched", "hidden", "busy_elsewhere"])
def test_not_while_shes_busy(clock, busy):
    show, c, _ = make()
    setattr(c, busy, True)
    assert not show.throw(QPointF(-3000, 0))


def test_off_in_settings(clock):
    c = FakeCompanion()
    show = fling.ThrowShow(c, rig, lambda *a: None, enabled=lambda: False)
    assert not show.throw(QPointF(-3000, 0))


def test_release_speed_is_from_the_last_moment_of_the_drag():
    samples = [(0.0, QPointF(0, 0)), (0.5, QPointF(10, 0)), (0.55, QPointF(110, 0)), (0.6, QPointF(260, 0))]
    v = fling.speed_of(samples)
    assert 2400 < v.x() < 2600 and v.y() == 0
    assert fling.speed_of(samples[:1]) == QPointF()


def test_her_size_when_turned():
    assert fling.extents(200, 0) == pytest.approx((30, 100))
    assert fling.extents(200, 90) == pytest.approx((100, 30))


def test_she_says_ow_once_per_throw_not_on_every_bounce(clock):
    show, c, said = make()
    show.throw(QPointF(-5200, -2600))                              # hard: several slams and bounces
    run(show, clock)
    assert len(show.walls) >= 1 and len(said) == 1 and said[0][1] == "angry"


def test_every_frame_repaints_the_whole_window(clock):
    """Repainting only part of it left old frames of her stuck on the screen (Windows)."""
    show, c, _ = make()
    show.throw(QPointF(-3000, 0))
    asked = []
    show.fx.update = lambda *a: asked.append(a)
    clock.t += 1 / 60
    show._tick()
    assert asked == [()]


def test_old_effects_never_break_a_frame(clock):
    """A spark drawn after its life ran out used to break the frame (old frames of her then stayed on screen)."""
    show, c, _ = make()
    show.throw(QPointF(-3500, 0))
    for _ in range(80):
        clock.t += 1 / 60
        show._tick()
    fx = show.fx
    fx.effects.dust(QPointF(500, 800), clock.t - 5, 250)               # long dead, not pruned yet
    fx.effects.sparks(QPointF(500, 800), 0, 1, 5, (100, 200), clock.t - 5)
    fx.effects.ring(QPointF(500, 800), clock.t - 5, 100)
    fx.effects.burst(QPointF(0, 500), QPointF(1, 0), clock.t - 5, 250)    # a slam long over
    from capri.ui import fx as fxmod
    real = fxmod.time if hasattr(fxmod, "time") else None
    img = QImage(1600, 900, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    fx.resize(1600, 900)
    fx.render(img)                                                      # no TypeError, no half-drawn frame


def test_the_overload_flickers_and_paints_every_moment(clock):
    """Arcs, tear, impact lines, dead pixels and glyphs: drawn at every age without breaking a frame."""
    from capri.ui import fx as fxmod
    e = fxmod.Effects()
    e.burst(QPointF(0, 400), QPointF(1, 0), 10.0, 260)
    e.burst(QPointF(800, 0), QPointF(0, 1), 10.0, 260)
    img = QImage(1600, 900, QImage.Format.Format_ARGB32_Premultiplied)
    drawn = set()
    from PySide6.QtGui import QPainter
    for i in range(70):
        now = 10.0 + i / 60
        img.fill(0)
        p = QPainter(img)
        e.paint_under(p, now)
        e.paint_over(p, now)
        p.end()
        drawn.add(img.pixelColor(20, 400).alpha() > 0 or img.pixelColor(40, 420).alpha() > 0)
    assert True in drawn                                                # it shows...
    assert not e.busy(10.0 + 2.0)                                       # ...and it's all gone after
