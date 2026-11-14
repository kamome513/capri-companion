"""2.6.1: colour skins in the Styles tab; the throw / dash / teleport effects in her skin's colours; the eye drone
wears her skin and a light touch of her style."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager  # noqa: E402
from capri.mods.store import Store  # noqa: E402
from capri.ui import fx  # noqa: E402

STORE = Store(lambda: "", folder=ROOT / "assets" / "mods")
BY = {m.id: m for m in STORE.builtin()}


def _wear(i):
    m = ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(STORE.download(BY[i]))
    effects.reload(m)
    return m


@pytest.fixture(autouse=True)
def plain_after():
    yield
    effects.reload(ModManager(Path(tempfile.mkdtemp())))


def _drone(t=4.3):
    from capri.ui.drone import DroneWindow
    w = DroneWindow()
    w._t0 = time.monotonic() - t
    img = QImage(112, 112, QImage.Format.Format_ARGB32)
    img.fill(0)
    w.render(img, QPoint(0, 0))
    return w, img


def _has(img, colour, tol=40):
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() > 200 and abs(c.red() - colour.red()) + abs(c.green() - colour.green()) + \
                    abs(c.blue() - colour.blue()) < tol:
                return True
    return False


def test_effect_colours_follow_her_skin():
    assert fx.her_red() == fx.RED and fx.her_cyan() == fx.CYAN
    _wear("neon-ice")
    pal = effects.EFFECTS.palette
    assert fx.her_red() == QColor(pal["hair"])
    assert fx.her_cyan() == QColor(pal.get("eyes") or pal["accent"])


def test_throw_afterimages_wear_her_skin():
    from capri.ui.fling import FlingFX
    from capri.ui.rig import Rig
    from capri.app import asset_root
    _wear("stormborn")
    f = FlingFX()
    f.rig, f.fh = Rig(QImage(str(asset_root() / "capri_v2" / "body" / "standing.png"))).resized(200), 200.0
    f.ghost(time.monotonic())
    assert _has(f.ghosts[-1].image, QColor(effects.EFFECTS.palette["hair"]))
    assert not _has(f.ghosts[-1].image, fx.RED, tol=20)


def test_drone_wears_her_skin_and_style():
    _, plain = _drone()
    assert _has(plain, QColor(236, 16, 70))
    _wear("stormborn")
    w, styled = _drone()
    assert _has(styled, QColor(effects.EFFECTS.palette["hair"]))
    assert not _has(styled, QColor(236, 16, 70), tol=20)
    assert w.PARTICLES <= 8                                     # a light touch: easy on the PC


def test_drone_style_effects_switch_off_and_stay_cheap():
    from capri.settings import Settings
    _wear("frutiger-aero")
    w, _ = _drone()
    s = Settings()
    s.style_effects = False
    w.style_settings = s
    img = QImage(112, 112, QImage.Format.Format_ARGB32)
    t = time.perf_counter()
    for _ in range(20):
        img.fill(0)
        w.render(img, QPoint(0, 0))
    assert (time.perf_counter() - t) / 20 < 0.01


def test_colour_skins_are_in_the_styles_tab():
    from capri.settings import Settings
    from capri.ui.styles_tab import StylesTab
    s = Settings()
    s.save = lambda: None
    m = ModManager(Path(tempfile.mkdtemp()))
    m.changed.append(lambda: effects.reload(m))
    tab = StylesTab(m, STORE, s)
    tab.theme.setCurrentIndex(tab.theme.findData("Colours"))
    names = {tab.list.item(i).text() for i in range(tab.list.count())}
    assert names == {"Neon Ice", "Toxic Glitch"}
    tab.list.setCurrentRow(0)
    assert "no effects" in tab.theme_label.text()
    tab.apply()
    assert tab.applied() in ("neon-ice", "toxic-glitch") and effects.EFFECTS.palette
