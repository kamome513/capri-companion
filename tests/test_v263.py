"""2.6.3: band-inspired vibes; styles fade into each other; her built-in styles update with her."""

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
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager  # noqa: E402
from capri.mods.store import Store  # noqa: E402
from capri.ui import style_fx  # noqa: E402

STORE = Store(lambda: "", folder=ROOT / "assets" / "mods")
BY = {m.id: m for m in STORE.builtin()}
BANDS = ("nirvana-vibe", "radiohead-vibe", "deftones-vibe", "smiths-vibe", "linkin-park-vibe", "arctic-monkeys-vibe",
         "mcr-vibe", "pink-floyd-vibe", "cure-vibe", "metallica-vibe")


@pytest.fixture(autouse=True)
def plain_after():
    yield
    effects.reload(ModManager(Path(tempfile.mkdtemp())))


def _wear(sid, m=None):
    m = m or ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(STORE.download(BY[sid]))
    effects.reload(m)
    return m


def test_ten_band_vibes_each_their_own():
    from styles_data import STYLES
    bands = [s for s in STYLES if s["theme"] == "Bands"]
    assert [s["id"] for s in bands] == list(BANDS)
    palettes = {tuple(sorted(s["palette"].items())) for s in bands}
    assert len(palettes) == 10                                    # every one its own colours
    for s in bands:
        assert style_fx.validate(s["style"]) == "", s["id"]
        assert s["description"].startswith("Inspired by")       # interpretations, named as such
        assert s["id"] in BY


def test_bands_tab_lists_them_and_each_applies():
    from capri.settings import Settings
    from capri.ui.styles_tab import StylesTab
    m = ModManager(Path(tempfile.mkdtemp()))
    m.changed.append(lambda: effects.reload(m))
    s = Settings()
    s.save = lambda: None
    tab = StylesTab(m, STORE, s)
    tab.theme.setCurrentIndex(tab.theme.findData("Bands"))
    assert tab.list.count() == 10
    for row in range(tab.list.count()):
        tab.list.setCurrentRow(row)
        tab.apply()
        assert tab.applied() in BANDS and effects.EFFECTS.style
    assert sum(1 for x in m.enabled() if x.manifest.type == "skin") == 1      # one vibe at a time


@pytest.mark.parametrize("sid", BANDS)
def test_each_vibe_draws_standing_quickly(sid):
    from test_v111 import companion
    c = companion()
    w = c.character
    _wear(sid)
    img = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    for _ in range(3):
        w.render(img, QPoint())
    t = time.perf_counter()
    for _ in range(8):
        img.fill(0)
        w._tick()
        w.render(img, QPoint())
    assert (time.perf_counter() - t) / 8 < 0.05
    assert w.sway is not None and w.idle_motion is not None    # her idle / grab / drag still there


def test_new_effects_draw():
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QPainter
    fx = style_fx.StyleFX()
    fx.set_style({"materials": [{"kind": k} for k in ("distress", "metal", "haze", "swirl")],
                  "events": [{"kind": "spotlight", "every": [1, 2]}]}, 0.0, {})
    img = QImage(300, 500, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    c = style_fx.Ctx(QRectF(0, 0, 300, 500), QRectF(100, 100, 100, 380), QRectF(120, 100, 60, 60),
                     [QPointF(140, 130), QPointF(160, 128)], QPointF(150, 480), 1.0)
    fx.figure(img, c)
    p = QPainter(img)
    fx._ev_spotlight(p, c, 0.5, {"kind": "spotlight"}, __import__("random").Random(1), "back")
    p.end()
    assert any(img.pixelColor(x, y).alpha() > 0 for x in range(0, 300, 5) for y in range(0, 500, 5))


def test_switching_vibes_crossfades():
    from test_v111 import companion
    c = companion()
    w = c.character
    m = _wear("nirvana-vibe")
    m.changed.append(w.begin_crossfade)
    m.changed.append(lambda: effects.reload(m))
    m.install_bytes(STORE.download(BY["pink-floyd-vibe"]))
    assert w._crossfade_k() is not None and w._special()       # fading, at full frame rate
    img = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    w.render(img, QPoint())
    w._xfade = (w._xfade[0], time.monotonic() - 5)
    assert w._crossfade_k() is None                            # ...and done
