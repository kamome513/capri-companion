"""v1.15: animated looks (her pictures come alive) and the mask drone."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QRectF, QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ui import looks  # noqa: E402


def render(w) -> QImage:
    img = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    w.render(img, QPoint())
    return img


def window(style):
    from capri.app import asset_root
    from capri.ui.art import CharacterArt
    from capri.ui.character_window import CharacterWindow
    from capri.ui.sprites import SpriteArt
    w = CharacterWindow(CharacterArt.load(asset_root() / "capri"), 190, True,
                        SpriteArt.load(asset_root() / "capri_v2"), style)
    w.set_look(0.7, True, "storm")
    return w


def test_her_looks_are_there():
    assert {"Stare", "Glitch", "Grin"} <= set(looks.available())
    assert "Hair Storm" not in looks.available()                            # removed in 1.16


@pytest.mark.parametrize("name, cutout, eyes, mouth", [
    ("Stare", False, 2, False), ("Glitch", False, 2, False), ("Grin", False, 2, True)])
def test_each_picture_is_understood(name, cutout, eyes, mouth):
    look = looks.load(name)
    assert look.cutout is cutout and len(look.eyes) == eyes and (look.mouth is not None) is mouth
    assert look.hair is not None and len(look.sparkles) > 20                  # red hair: sway + sparkles


def test_a_white_background_is_cut_out():
    a = np.full((60, 80, 4), 255, np.uint8)
    a[20:40, 30:50, :3] = (236, 16, 70)                                      # her, on white
    a[25:30, 35:40, :3] = 255                                                # white inside her stays
    out, share = looks.cut_out_white(a)
    assert out[0, 0, 3] == 0 and out[30, 40, 3] == 255 and out[27, 37, 3] == 255 and share > 0.5


@pytest.mark.parametrize("name", ["Stare", "Grin"])
def test_looks_are_animated(name):
    w = window("look:" + name)
    assert w.mode == "look" and w._animating() is False                      # (not shown yet)
    w.show()
    assert w._animating()
    w._t0 = time.monotonic() - 3.0
    a = render(w)
    w._t0 = time.monotonic() - 3.9
    b = render(w)
    assert a != b                                                             # hair / sparkles / bob move


def test_the_grin_opens_when_she_talks():
    w = window("look:Grin")
    painter = w.look_painter()
    painter._next_glitch = 1e9
    w._t0 = time.monotonic() - 2.0
    quiet = render(w)
    w.set_talking(True)
    w.set_voice_level(0.8)
    w._t0 = time.monotonic() - 2.0
    assert render(w) != quiet


def test_blinks():
    look = looks.load("Stare")
    painter = looks.LookPainter(look)
    painter._next_blink, painter._blink_at = 1e9, 10.0
    assert painter.blinking(10.08) > 0.9 and painter.blinking(10.5) == 0.0


def test_a_missing_look_falls_back():
    assert window("look:Nope").style == "body"


def test_your_own_pictures_become_looks(tmp_path, monkeypatch):
    mine = tmp_path / "looks"
    mine.mkdir()
    img = QImage(120, 90, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.fillRect(30, 20, 60, 60, QColor(236, 16, 70))
    p.end()
    img.save(str(mine / "my_fave.png"))
    monkeypatch.setattr(looks, "folders", lambda: [mine])
    assert "My Fave" in looks.available()
    assert looks.load("My Fave").cutout


def test_the_mask_drone():
    from capri.ui.drone import DroneWindow
    d = DroneWindow()
    d.set_style("mask")
    assert d.style == "mask" and d._mask is not None and len(d._mask.eyes) == 2
    d._t0 = time.monotonic() - 1.0
    calm = render(d)
    d.set_talking(True)
    d.set_voice_level(0.9)
    d._t0 = time.monotonic() - 1.0
    talking = render(d)
    assert calm != talking
    assert any(calm.pixelColor(x, 50).alpha() > 0 for x in range(0, 112, 4))


def test_drone_look_setting():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(),
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.set_drone_look("mask")
    assert c.drone_window.style == "mask" and Settings.load().drone_look == "mask"
