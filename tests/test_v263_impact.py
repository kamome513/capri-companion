"""2.6.3: her vibe answers a wall slam - its own impact and its own crack, once per throw."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager  # noqa: E402
from capri.mods.store import Store  # noqa: E402
from capri.ui import impact  # noqa: E402
from styles_data import IMPACTS, STYLES  # noqa: E402

STORE = Store(lambda: "", folder=ROOT / "assets" / "mods")
BY = {m.id: m for m in STORE.builtin()}


@pytest.fixture(autouse=True)
def plain_after():
    yield
    effects.reload(ModManager(Path(tempfile.mkdtemp())))


def test_every_vibe_has_its_own_impact():
    assert set(IMPACTS) == {s["id"] for s in STYLES}            # all 41 - none skipped
    for sid, spec in IMPACTS.items():
        assert impact.validate(spec) == "", sid
        assert spec["burst"] and spec["crack"]
    designs = {repr((sorted(d["kind"] + d.get("shape", "") for d in s["burst"]), s["crack"]["color"],
                     s["crack"]["glow"], sorted(s["crack"].get("deco", [])))) for s in IMPACTS.values()}
    assert len(designs) == len(IMPACTS)                          # every one different


def test_the_first_eight_look_as_asked():
    kinds = {sid: {d["kind"] + ":" + d.get("shape", "") for d in IMPACTS[sid]["burst"]} for sid in IMPACTS}
    assert "particles:gear" in kinds["clockwork"] and "gears" in IMPACTS["clockwork"]["crack"]["deco"]
    assert "shark:" in kinds["abyssal"] and "bubbles" in IMPACTS["abyssal"]["crack"]["deco"]
    assert "flare:" in kinds["solaris"]
    assert "dark:" in kinds["eclipse"]
    assert "glitch:" in kinds["corrupted-exe"] and "rgb" in IMPACTS["corrupted-exe"]["crack"]["deco"]
    assert "particles:crystal" in kinds["glacier-rose"] and "frost" in IMPACTS["glacier-rose"]["crack"]["deco"]
    assert "particles:ember" in kinds["wildfire"] and "magma" in IMPACTS["wildfire"]["crack"]["deco"]


def _draw(spec, t, reduced=False):
    img = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    imp = impact.Impact(QPointF(10, 200), QPointF(1, 0), spec, 250.0, seed=3, reduced=reduced)
    p = QPainter(img)
    imp.paint(p, imp.born + t)
    p.end()
    return img


def _lit(img):
    return sum(1 for x in range(0, img.width(), 4) for y in range(0, img.height(), 4) if img.pixelColor(x, y).alpha())


@pytest.mark.parametrize("sid", sorted(IMPACTS))
def test_each_impact_draws_quickly_through_its_life(sid):
    spec = IMPACTS[sid]
    t0 = time.perf_counter()
    lit = [_lit(_draw(spec, t)) for t in (0.02, 0.15, 0.4, 0.9, 2.0)]
    assert (time.perf_counter() - t0) / 5 < 0.06
    assert all(n > 0 for n in lit)
    assert _lit(_draw(spec, impact.LIFE + 0.1)) == 0             # ...and gone after


def test_reduced_motion_is_calm():
    drawn = []
    for kind in impact.BURST_KINDS:
        name = "_b_" + kind
        orig = getattr(impact.Impact, name)
        setattr(impact.Impact, name, lambda self, *a, _o=orig, _n=name: (drawn.append(_n), _o(self, *a))[1])
    try:
        calm = _draw(IMPACTS["clockwork"], 0.3, reduced=True)
        assert not drawn and _lit(calm) > 0                       # just the crack: nothing flying
        _draw(IMPACTS["clockwork"], 0.3)
        assert drawn                                              # (and normally, the burst)
    finally:
        for kind in impact.BURST_KINDS:
            name = "_b_" + kind
            fn = getattr(impact.Impact, name)
            if getattr(fn, "__defaults__", None):
                setattr(impact.Impact, name, fn.__defaults__[0])


def test_one_impact_per_throw_at_the_first_slam():
    from test_v111 import companion
    from capri.ui.fling import ThrowShow
    c = companion()
    m = ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(STORE.download(BY["clockwork"]))
    effects.reload(m)
    show = ThrowShow(c, lambda: c.character.full_rig(), lambda *a: None)
    show._os_reduced = False
    spawned = []
    show.impacts.spawn = lambda *a, **k: spawned.append(a)
    assert show.throw(QPointF(3000, -200))
    now = time.monotonic()
    show._start_slam("right", now, 2600)
    show._start_slam("right", now + 0.3, 2600)                    # the same throw: no second full impact
    assert len(spawned) == 2 and spawned[1][2]["burst"] == []     # (2.6.4: just a smaller crack)
    spawned.pop()
    at, normal = spawned[0][0], spawned[0][1]
    assert normal == QPointF(-1, 0) and abs(at.x() - (show.area.right() + 1)) < 2
    show._timer.stop()
    show.active, c.busy_elsewhere = False, False                 # (she's home again)
    assert show.throw(QPointF(-3000, -200))                       # picked up and thrown again: another
    show._start_slam("left", time.monotonic(), 2600)
    assert len(spawned) == 2 and spawned[1][2]["burst"]          # a full impact again
    show._timer.stop()


def test_impact_window_stays_put_and_lets_clicks_through():
    w = impact.Impacts().spawn(QPointF(500, 300), QPointF(-1, 0), IMPACTS["wildfire"], 250.0)
    assert w is not None and bool(w.windowFlags() & Qt.WindowType.WindowTransparentForInput)
    centre = w.geometry().center()
    assert abs(centre.x() - 500) <= 1 and abs(centre.y() - 300) <= 1
    w._tick()
    assert w.geometry().center() == centre
    w.impact.born -= impact.LIFE + 1
    w._tick()
    assert not w.isVisible()
