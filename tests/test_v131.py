"""v1.31: pick her hair - "Like the show" (traced, the default) or "Classic spiky" (her first) - in
Settings, the menu or by voice; every figure of her follows it."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.commands.parser import Kind, parse  # noqa: E402
from capri.ui.hair import ClassicStormHair, StormHair, make_hair  # noqa: E402


@pytest.mark.parametrize("said, style", [
    ("change your hair", ""), ("use your old hair", "classic"), ("classic hair", "classic"),
    ("go back to your original hair", "classic"), ("switch your hair to the new one", "storm"), ("new hair please", "storm"),
])
def test_hair_by_voice(said, style):
    intent = parse(said)
    assert intent.kind is Kind.HAIR and intent.query == style


@pytest.mark.parametrize("said", ["i like your hair", "hair dryer", "what's your hair like"])
def test_talking_about_hair_is_still_chat(said):
    assert parse(said).kind is not Kind.HAIR


def test_make_hair():
    assert isinstance(make_hair("classic"), ClassicStormHair) and isinstance(make_hair("storm"), StormHair)
    assert isinstance(make_hair("whatever"), StormHair)


def test_settings_keep_a_valid_style(tmp_path, monkeypatch):
    from capri.settings import Settings
    s = Settings()
    assert s.hair_style == "storm"
    s.hair_style = "classic"
    s.save()
    assert Settings.load().hair_style == "classic"
    s.hair_style = "spikes"                                            # (an old value): back to the default
    s.save()
    assert Settings.load().hair_style == "storm"


def _rig_pixels(style: str):
    from capri.app import asset_root
    from capri.ui import looks
    from capri.ui.rig import Pose, Rig
    from capri.ui.sprites import SpriteArt
    rig = Rig(SpriteArt.load(asset_root() / "capri_v2").frame("standing"), style).resized(300)
    img = QImage(400, 420, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    rig.paint(p, QPointF(200, 400), 300, Pose(t=0.5, wild=1.0))
    p.end()
    return rig, looks.to_array(img)


def test_only_the_traced_hair_hides_her_own():
    classic, a = _rig_pixels("classic")
    storm, b = _rig_pixels("storm")
    assert isinstance(classic.hair, ClassicStormHair) and isinstance(storm.hair, StormHair)
    assert (a != b).any()
    classic.set_hair_style("storm")
    assert isinstance(classic.hair, StormHair) and classic.hair_style == "storm"


def test_switching_by_voice_saves_it_and_she_says_so():
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    looks = []
    r.router.companion.set_look = lambda wild, idle, style: (looks.append(style),
                                                             setattr(r.assistant.settings, "hair_style", style))
    r.router.handle("use your old hair")
    assert looks == ["classic"] and "classic spiky" in r.controller.message
    r.router.handle("change your hair")
    assert looks[-1] == "storm"                                          # swaps back


def test_the_window_and_menu_follow_the_style():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.look_tab import LookTab
    from capri.ui.sprites import SpriteArt
    from capri.ui.tray import CompanionMenu
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(),
                  SpriteArt.load(asset_root() / "capri_v2"))
    menu = CompanionMenu(c, QImage(8, 8, QImage.Format.Format_ARGB32))
    tab = LookTab(c)
    menu.hair_styles["classic"].trigger()
    assert c.settings.hair_style == "classic" and isinstance(c.character.hair, ClassicStormHair)
    assert tab.hair_box.currentData() == "classic"                     # Settings shows it too
    tab.hair_box.setCurrentIndex(tab.hair_box.findData("storm"))
    assert c.settings.hair_style == "storm" and menu.hair_styles["storm"].isChecked()
    assert isinstance(c.character.lying_hair, StormHair) and c.character.lying_hair.flow_in
