"""2.6.2: hologram mode never leaves her stuck click-through; styles live only in the Styles tab; Thornveil's
thorn vines and roses in her hair; smoother idle / grab / drag / release."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager  # noqa: E402


@pytest.fixture(autouse=True)
def plain_after():
    yield
    effects.reload(ModManager(Path(tempfile.mkdtemp())))


def _through(w) -> bool:
    return bool(w.windowFlags() & Qt.WindowType.WindowTransparentForInput)


def _companion():
    from test_v111 import companion
    c = companion()
    c.settings.save = lambda: None
    c._save = lambda: None
    return c


def test_hologram_off_means_she_can_be_moved_again():
    c = _companion()
    c.set_hologram(True)
    assert _through(c.character) and c.settings.hologram
    assert c.settings.click_through is False                    # the setting itself is never changed
    c.set_hologram(False)
    assert not _through(c.character) and not c.settings.hologram


def test_chaos_flicker_never_keeps_the_hologram():
    c = _companion()
    c.set_hologram(True, keep=False)
    assert _through(c.character) and not c.settings.hologram
    c.set_hologram(c.settings.hologram, keep=False)
    assert not _through(c.character) and not c.character.hologram


def test_click_through_still_works_with_the_hologram():
    c = _companion()
    c.set_click_through(True)
    c.set_hologram(True)
    c.set_hologram(False)
    assert _through(c.character)                                # you'd switched it on yourself: it stays
    c.set_click_through(False)
    assert not _through(c.character)


def test_stuck_click_through_is_cleared_once_after_the_update():
    from capri.app import _unstick_click_through_once
    from capri.settings import Settings
    s = Settings()
    s.save = lambda: None
    s.last_version, s.click_through = "2.6.1", True
    _unstick_click_through_once(s)
    assert s.click_through is False
    s.last_version, s.click_through = "2.6.2", True
    _unstick_click_through_once(s)
    assert s.click_through is True


def test_styles_are_only_in_the_styles_tab():
    from capri.mods.store import Store
    from capri.ui.mods_tab import ModsTab
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    m = ModManager(Path(tempfile.mkdtemp()))
    skin = next(x for x in store.builtin() if x.type == "skin")
    other = next(x for x in store.builtin() if x.type == "cosmetic")
    m.install_bytes(store.download(skin))
    m.install_bytes(store.download(other))
    tab = ModsTab(m, store)
    shown = {tab.installed_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(tab.installed_list.count())}
    assert shown == {other.id}
    tab._listed(store.builtin(), "")
    listed = {tab.store_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(tab.store_list.count())}
    assert listed and not any(x.type == "skin" for x in store.builtin() if x.id in listed)
    cats = [tab.category.itemText(i) for i in range(tab.category.count())]
    assert "Skins & outfits" not in cats


# -- Thornveil ---------------------------------------------------------------------------------------------------
def _style(sid):
    from capri.mods.store import Store
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    m = ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(store.download({x.id: x for x in store.builtin()}[sid]))
    effects.reload(m)
    return m


def test_thornveil_has_vines_and_roses_in_her_hair():
    _style("thornveil")
    assert effects.EFFECTS.style["hair"]["kind"] == "briar"
    from capri.ui import style_fx
    assert style_fx.validate(effects.EFFECTS.style) == ""
    from test_v111 import render
    c = _companion()
    w = c.character
    w.style_now()
    img = render(w)
    rose = QColor(effects.EFFECTS.style["hair"]["color2"])
    head = w.content_rect().adjusted(0, -80, 0, -w.content_rect().height() // 2)
    found = any(abs(img.pixelColor(x, y).red() - rose.red()) < 50 and img.pixelColor(x, y).green() < 60
                and img.pixelColor(x, y).red() > 120
                for x in range(max(0, head.left()), min(img.width(), head.right()), 2)
                for y in range(max(0, head.top()), head.bottom(), 2))
    assert found                                                 # red roses up in her hair


# -- the music bar -------------------------------------------------------------------------------------------------
def test_music_bar_takes_her_style_colours():
    from capri.ui.music_deck import deck_colours, RED
    assert deck_colours()[0] == RED
    _style("stormborn")
    red, cyan, green, top, bottom = deck_colours()
    assert red == QColor(effects.EFFECTS.palette["hair"]) and red != RED
    assert top.alpha() == 240


# -- sitting on a window keeps her style -------------------------------------------------------------------------------
def test_sitting_keeps_her_style_effects():
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage
    c = _companion()
    s = c.sit_window
    s.refresh()
    s.show()
    plain_size = s.size()
    _style("frutiger-aero")
    assert s._style() is not None
    s.refresh()
    assert s.width() > plain_size.width()                       # a little room round her for the effects
    seat_before = s.pos() + s.seat_point()
    s.refresh()
    assert s.pos() + s.seat_point() == seat_before              # ...and she stays on her seat
    img = QImage(s.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    s.render(img, QPoint())                                      # draws (with its effects) without trouble
    path = s._picture_ctx(0.0).hair
    assert path is not None and not path.isEmpty()
    box = path.boundingRect()
    assert box.height() < s.content_rect().height() * 0.75      # her hair - not the whole picture


# -- idle / grab / drag / release ----------------------------------------------------------------------------------------
def test_idle_is_never_frozen_and_never_a_loop():
    import random
    from capri.ui.motion import IdleMotion
    m = IdleMotion(random.Random(3))
    seen = []
    for _ in range(60 * 30):                                     # 30 s at 60 fps
        m.step(1 / 60)
        seen.append(m.moves())
    for key in ("breath", "tilt", "lean", "look_x", "arms"):
        values = [s[key] for s in seen]
        assert max(values) - min(values) > 1e-3, key             # it moves...
    tilt = [s["tilt"] for s in seen]
    assert max(abs(t) for t in tilt) < 8                         # ...but only a little
    assert max(abs(s["lean"]) for s in seen) < 0.03
    a, b = tilt[:600], tilt[600:1200]                            # no 10 s loop
    assert max(abs(x - y) for x, y in zip(a, b)) > 0.2


def test_idle_is_the_same_at_any_frame_rate():
    import random
    from capri.ui.motion import IdleMotion
    a, b = IdleMotion(random.Random(5)), IdleMotion(random.Random(5))
    for _ in range(300):
        a.step(1 / 60)
    for _ in range(150):
        b.step(1 / 30)
    for key, v in a.moves().items():
        assert abs(v - b.moves()[key]) < 0.05 * max(1.0, abs(v)), key


def test_carried_she_swings_follows_through_and_settles():
    from PySide6.QtCore import QPointF
    from capri.ui.motion import DragMotion

    class Clock:
        t = 50.0

        def __call__(self):
            return self.t
    clock = Clock()
    m = DragMotion(clock=clock)
    m.grab(QPointF(60, 40))
    peak = 0.0
    for i in range(30):                                          # you swing her right
        clock.t += 1 / 60
        m.moved(QPointF(200 + i * 20, 300))
        m.step(1 / 60)
        peak = min(peak, m.angle)
    assert -m.MAX_SWING - 1 < peak < -2                          # trails behind, within limits
    moves = m.pose_moves()
    assert moves["hair_drag"] > 0 and moves["spread"] > 3        # hair trails, arms out a little
    lag = moves["tilt"]
    for _ in range(12):                                          # you stop: she swings back past upright a touch
        clock.t += 1 / 60
        m.step(1 / 60)
    assert m.angle > peak and lag != m.pose_moves()["tilt"]
    m.drop()
    settle = []
    for _ in range(180):
        clock.t += 1 / 60
        m.step(1 / 60)
        settle.append(m.pose_moves()["squat"])
    assert max(settle) > 0.05                                    # her knees give as she's put down
    assert not m.swinging and abs(m.angle) < 0.05                # ...then she's still


def test_her_head_tilts_but_her_feet_stay_put():
    from capri.ui.rig import Pose
    from test_v111 import render
    c = _companion()
    w = c.character
    rig = w.figure_rig()
    from PySide6.QtCore import QPointF
    feet = QPointF(100, 300)
    a = rig.head_transform(feet, 250, Pose()).map(QPointF(rig.head.center()))
    b = rig.head_transform(feet, 250, Pose(tilt=4.0)).map(QPointF(rig.head.center()))
    assert (a - b).manhattanLength() > 0.5
    img = render(w)
    assert not img.isNull()


def test_held_she_swings_round_your_grip_and_stays_under_it():
    from PySide6.QtCore import QPointF
    c = _companion()
    w = c.character
    w._press_at = QPointF(w.width() / 2, w.content_rect().top() + 20)
    w.set_held(True)
    pivot = QPointF(w.sway.pivot)
    assert abs(pivot.x() - w.width() / 2) < 1 and w.sway.held and w._special()
    w.set_held(False)
    assert not w.sway.held


def test_her_own_installed_styles_update_with_capri():
    """(2.6.3) A built-in style installed by an older Capri (the old Thornveil) is brought up to date - its
    picture AND what she wears - and stays on."""
    import io
    import json
    import zipfile
    from capri.mods.store import Store, refresh_builtins
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    m = _style("thornveil")
    folder = m.get("thornveil").folder
    old = json.loads((folder / "mod.json").read_text(encoding="utf-8"))
    old["style"]["hair"]["kind"] = "thorn"                     # as 2.6.0 installed it
    (folder / "mod.json").write_text(json.dumps(old), encoding="utf-8")
    assert m.get("thornveil").manifest.data["style"]["hair"]["kind"] == "thorn"
    assert refresh_builtins(m, store) == ["thornveil"]
    assert m.get("thornveil").manifest.data["style"]["hair"]["kind"] == "briar" and m.get("thornveil").enabled
    assert refresh_builtins(m, store) == []                    # up to date: left alone
    mine = io.BytesIO()                                        # your own mod is never touched
    with zipfile.ZipFile(mine, "w") as z:
        z.writestr("mod.json", json.dumps({"id": "sakura", "name": "My Sakura", "version": "9.0.0", "type": "skin",
                                           "author": "you", "capri": ">=2.4.0", "palette": {"hair": "#00ff00"}}))
    m.install_bytes(mine.getvalue())
    assert refresh_builtins(m, store) == [] and m.get("sakura").manifest.author == "you"
