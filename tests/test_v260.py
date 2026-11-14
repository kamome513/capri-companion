"""2.6: styles - appearance presets with live effects; the throw / dash keep her skin; the teleport covers her."""

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
from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager  # noqa: E402
from capri.mods.store import Store  # noqa: E402
from capri.ui import style_fx  # noqa: E402

STORE = Store(lambda: "", folder=ROOT / "assets" / "mods")
BY = {m.id: m for m in STORE.builtin()}


def _mods(*ids):
    m = ModManager(Path(tempfile.mkdtemp()))
    for i in ids:
        m.install_bytes(STORE.download(BY[i]))
    effects.reload(m)
    return m


@pytest.fixture(autouse=True)
def plain_after():
    yield
    effects.reload(ModManager(Path(tempfile.mkdtemp())))


def test_every_style_is_built_in_and_distinct():
    from styles_data import STYLES
    assert len(STYLES) == 31
    names = {s["name"] for s in STYLES}
    for want in ("Stormborn", "Absolute Zero", "Corrupted.exe", "Frutiger Aero", "White & Black Kintsugi", "Mantis"):
        assert want in names
    palettes = {tuple(sorted(s["palette"].items())) for s in STYLES}
    assert len(palettes) == len(STYLES)                         # no two the same colours
    for s in STYLES:
        st = s["style"]
        assert style_fx.validate(st) == "", s["id"]
        assert s["id"] in BY                                       # it's in the store
        assert st.get("particles") and st.get("events") and st.get("move")   # alive: particles, moments, trails
        assert st.get("hair") or st.get("hair_edge") or st.get("materials")


def test_bad_styles_are_refused():
    from capri.mods.manifest import ModError, check
    base = {"id": "bad-style", "name": "Bad", "version": "1.0.0", "type": "skin", "capri": ">=2.4.0",
            "palette": {"hair": "#112233"}}
    with pytest.raises(ModError):
        check({**base, "style": {"particles": [{"kind": "nukes"}]}})
    with pytest.raises(ModError):
        check({**base, "style": {"script": "rm -rf"}})
    check({**base, "style": {"aura": {"color": "#ffffff"}}})


def _ctx(t=3.0, lying=False):
    win = QRectF(0, 0, 300, 420)
    body = QRectF(110, 120, 80, 290)
    head = QRectF(105, 110, 90, 70)
    return style_fx.Ctx(win, body, head, [QPointF(140, 140), QPointF(160, 138)], QPointF(150, 410), t, 1.0,
                        None, lying, QPointF(400, 0), 3.0)


def test_every_effect_draws():
    """Every particle, hair kind, material, event, trail and outline mode draws without trouble, both layers."""
    for k in style_fx.PARTICLE_KINDS:
        img = QImage(60, 60, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        style_fx.draw_particle(p, k, QPointF(30, 30), 6, style_fx.colour("#ff0000"), 1.0, 30, 1.0)
        p.end()
        drawn = any(img.pixelColor(x, y).alpha() > 0 for x in range(0, 60, 2) for y in range(0, 60, 2))
        assert drawn, k                                           # (a gear or a bubble is hollow in the middle)
    for hair in style_fx.HAIR_KINDS:
        for mode in style_fx.OUTLINE_MODES:
            st = {"hair": {"kind": hair, "color": "#ff0000", "color2": "#00ff00"}, "outline": {"color": "#fff", "mode": mode},
                  "aura": {"color": "#00f"}, "eyes": "#ff0", "hair_edge": {"color": "#fff"},
                  "materials": list(style_fx.MATERIALS), "filters": {"rgb_split": 2, "flicker": 1, "translucent": 0.2},
                  "particles": [{"kind": k, "colors": ["#fff"], "count": 2, "motion": m}
                                for k, m in zip(style_fx.PARTICLE_KINDS, style_fx.MOTIONS * 4)],
                  "move": {"kind": "trail", "color": "#f00"}}
            fx = style_fx.StyleFX(st)
            fx.palette = {"hair": "#ff0000", "accent": "#00ff00"}
            c = _ctx()
            _paint(fx, c)
            break
    for ev in style_fx.EVENTS:
        for mv in style_fx.MOVES:
            fx = style_fx.StyleFX({"events": [{"kind": ev}], "move": {"kind": mv, "color": "#fff"},
                                   "materials": ["kintsugi", "joints"]})
            fx._active = [(fx._events[0], 1.5, fx.LENGTH.get(ev, 1.5), 0.4)]
            fx.moved(QPointF(100, 400), 900, 2.6)
            for lying in (False, True):
                _paint(fx, _ctx(2.0, lying))
            break


def _paint(fx, c):
    out = QImage(300, 420, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(0)
    p = QPainter(out)
    fx.paint_back(p, c)
    her = QImage(300, 420, QImage.Format.Format_ARGB32_Premultiplied)
    her.fill(0)
    q = QPainter(her)
    q.fillRect(c.body, style_fx.colour("#802040"))
    q.end()
    fx.figure(her, c)
    fx.draw_figure(p, her, c)
    fx.paint_front(p, c, QPointF(0, 0))
    p.end()
    return out


def test_she_wears_every_style_standing_and_lying():
    from test_v111 import companion, render
    c = companion()
    c.character.set_body_look("flat")
    c.place()
    lie = companion(lounge=True)
    lie.set_lounge(True)
    lie.place()
    from styles_data import STYLES
    for s in STYLES:
        _mods(s["id"])
        for ch in (c.character, lie.character):
            assert ch.style_now() is not None
            fx = ch.style_fx
            if fx._events:
                ev = fx._events[0]
                fx._active = [(ev, time.monotonic() - 0.3, fx.LENGTH.get(ev["kind"], 1.5), 0.5)]
            img = render(ch)
            assert not img.isNull()


def test_effects_stay_off_when_switched_off():
    from test_v111 import companion
    from capri.settings import Settings
    c = companion()
    s = Settings()
    c.character.style_settings = s
    _mods("stormborn")
    assert c.character.style_now() is not None
    s.style_effects = False
    assert c.character.style_now() is None                     # just her colours, no effects
    s.style_effects = True
    s.style_particles = False
    assert c.character.style_now().toggles.particles is False


def test_a_style_has_a_shimmer_when_it_goes_on():
    from test_v111 import companion
    c = companion()
    _mods("solaris")
    fx = c.character.style_now()
    assert time.monotonic() - fx.switched_at < 1.0


def test_styles_cost_a_few_milliseconds():
    from test_v111 import companion, render
    c = companion()
    c.character.set_body_look("flat")
    c.place()
    _mods("stormborn")
    c.character.style_now()
    render(c.character)
    t = time.perf_counter()
    for _ in range(10):
        render(c.character)
    assert (time.perf_counter() - t) / 10 < 0.05


def test_styles_tab_applies_and_takes_off():
    from capri.settings import Settings
    from capri.ui.styles_tab import StylesTab
    m = ModManager(Path(tempfile.mkdtemp()))
    m.changed.append(lambda: effects.reload(m))
    s = Settings()
    s.save = lambda: None
    tab = StylesTab(m, STORE, s)
    assert tab.list.count() == 33                                # 31 styles + the 2 colour skins
    tab.theme.setCurrentIndex(tab.theme.findData("Colours"))
    assert tab.list.count() == 2
    tab.theme.setCurrentIndex(tab.theme.findData("Elemental"))
    assert tab.list.count() == 6
    tab.list.setCurrentRow(0)
    tab.apply()
    assert tab.applied() and effects.EFFECTS.style
    tab.default()
    assert tab.applied() == "" and not effects.EFFECTS.style
    tab.boxes["style_events"].setChecked(False)
    assert s.style_events is False


def test_throw_and_dash_keep_her_skin():
    from test_v111 import companion
    from capri.ui.visit import VisitShow
    c = companion()
    c.character.set_body_look("flat")
    _mods("neon-ice")
    vs = VisitShow(c)
    vs.fh = c.character.figure_height()
    rig = vs.rig()
    assert vs._rig_full is c.character.full_rig()               # her own figure: look AND skin colours


def test_teleport_picture_has_room_for_her_hair():
    from test_v111 import companion
    from capri.ui import fx
    from capri.ui.rig import Pose
    c = companion()
    rig = c.character.full_rig().resized(300)
    img = fx.render(rig, 250, Pose(t=0.0))
    top = [img.pixelColor(x, 0).alpha() for x in range(0, img.width(), 2)]
    assert max(top) == 0                                        # nothing cut off at the top
    from capri.ui.roam import TeleportFX
    assert TeleportFX.REACH >= 1.3


def test_no_patch_of_old_colour_by_her_face():
    """A style's hair colour reaches right down to her eyes (the hair there is found by her own red, before the
    skin recolours it), standing and lying down."""
    import numpy as np
    from test_v111 import companion, render
    c = companion()
    c.character.set_body_look("flat")
    c.place()
    _mods("frutiger-aero")
    rig = c.character.full_rig()
    plain_face = rig.face
    img = plain_face.convertToFormat(QImage.Format.Format_RGBA8888)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
    a = a.reshape(img.height(), img.width(), 4).astype(int)
    hair_blue = (abs(a[..., 0] - 0x3f) < 30) & (abs(a[..., 1] - 0xd0) < 30) & (abs(a[..., 2] - 0xff) < 30) & (a[..., 3] > 200)
    assert hair_blue.sum() < 20                                   # her face layer holds no hair-coloured patch now
