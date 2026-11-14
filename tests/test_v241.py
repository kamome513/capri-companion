"""2.4.1: Russian (and every other language) without an AI, the right voice for English lines, her ears offer,
the flat look, mods lying down, personalities as mods, the palm-out wave, smaller idles, floating when AFK and
the chat-log panel."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri import languages  # noqa: E402


@pytest.fixture(autouse=True)
def back_to_english():
    yield
    languages.set_current("en")


# -- languages ---------------------------------------------------------------------------------------------------------
def test_my_name_in_other_languages():
    assert languages.my_name("Меня зовут Дилан", "ru") == "Дилан"
    assert languages.my_name("menya zovut dylan", "ru") == "Dylan"
    assert languages.my_name("Je m'appelle Dylan.", "fr") == "Dylan"
    assert languages.my_name("ich heiße Sam", "de") == "Sam"
    assert languages.my_name("привет", "ru") == ""
    assert languages.to_english("Меня зовут Дилан", "ru") == "my name is dilan"


def test_every_language_has_her_two_own_lines():
    for code in languages.LANGUAGES:
        if code == "en":
            continue
        assert languages.local_line("need_ai", code)
        assert "Sam" in languages.local_line("nice_to_meet", code, name="Sam")
        assert code in languages.MY_NAME


def test_russian_without_an_ai_answers_in_russian():
    from test_v11 import FakeDesktop, rig
    from capri.settings import Settings
    s = Settings(slang=False)
    s.language = "ru"
    r = rig(FakeDesktop(), settings=s)
    languages.set_current("ru")
    r.service.command.emit("меня зовут Дилан")
    assert r.speaker.lines[-1] == "Приятно познакомиться, Дилан."
    assert r.router.chatbot.memory.name == "Dilan"                     # kept on this PC
    r.service.command.emit("как дела")
    assert r.speaker.lines[-1] == languages.local_line("need_ai", "ru")  # never "Cool." / "Mhm." in English


def test_an_english_line_is_spoken_with_english_sounds():
    assert languages.speaks_english("Cool.", "ru")
    assert not languages.speaks_english("Приятно познакомиться, Дилан.", "ru")
    assert languages.speaks_english("Opened Discord.", "de")
    assert not languages.speaks_english("Ich habe Discord geöffnet.", "de")
    assert languages.speaks_english("anything", "en")
    from test_v232 import _kokoro_engine
    engine = _kokoro_engine()
    languages.set_current("ru")
    engine.synthesize("Okay, it's done.", "neural: Capri", 0.5)
    assert engine._kokoro.calls[-1][2] == "en-us"                       # no Russian sounds on English: no "vroo"
    engine.synthesize("Готово.", "neural: Capri", 0.5)
    assert engine._kokoro.calls[-1][2] == "ru"


def test_only_english_ears_she_offers_to_get_yours(monkeypatch):
    from test_v11 import FakeDesktop, rig
    from capri.voice import parakeet
    r = rig(FakeDesktop())
    languages.set_current("ru")
    monkeypatch.setattr(parakeet, "installed", lambda: True)
    monkeypatch.setattr(parakeet, "ready", lambda *a, **k: False)
    got = []
    monkeypatch.setattr(parakeet, "download", lambda progress, language=None: got.append(language))
    r.assistant.ears_missing = lambda: True
    r.assistant.offer_ears = r.router.offer_ears
    r.service.command.emit("many is a woot dylan")            # what English ears make of Russian
    assert "download" in r.speaker.lines[-1].lower() and "Russian" in r.speaker.lines[-1]
    r.service.command.emit("yes")
    for _ in range(50):
        app.processEvents()
        if got:
            break
        time.sleep(0.02)
    assert got == ["ru"]


# -- her look ----------------------------------------------------------------------------------------------------------
def test_flat_look_is_the_default_and_bold():
    import numpy as np
    from capri.settings import Settings
    from capri.ui import neon
    assert Settings().body_style == "flat" and "flat" in neon.LOOKS
    a = np.zeros((60, 40, 4), np.uint8)
    a[..., 3] = 255
    a[:, :20, :3] = (250, 30, 90)
    a[:, 20:, :3] = (20, 10, 30)
    a[30, 10, :3] = (40, 240, 120)                          # a speck: merged into the shard around it
    out = neon.flat_array(a)
    assert tuple(out[30, 10, :3]) == tuple(neon.FLAT_RED.astype(np.uint8))
    assert tuple(out[30, 30, :3]) == tuple(neon.FLAT_DARK.astype(np.uint8))


def test_old_settings_stand_up_in_the_new_look(tmp_path):
    from capri.app import _new_look_once
    from capri.settings import Settings
    s = Settings()
    s.save = lambda: None
    s.last_version, s.lounge, s.body_style = "2.4.0", True, "full"
    _new_look_once(s)
    assert not s.lounge and s.body_style == "flat" and s.character_style == "body"
    s2 = Settings()
    s2.save = lambda: None
    s2.last_version, s2.lounge = "2.4.1", True
    _new_look_once(s2)
    assert s2.lounge                                         # after that: your choice stays


def _mods(*ids):
    from capri.mods import effects
    from capri.mods.manager import ModManager
    from capri.mods.store import Store
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    by = {m.id: m for m in store.builtin()}
    m = ModManager(Path(tempfile.mkdtemp()))
    for i in ids:
        m.install_bytes(store.download(by[i]))
    effects.reload(m)
    return m


def test_mods_work_lying_down_too():
    from test_v111 import companion, render
    from capri.mods import effects
    c = companion(lounge=True)
    c.set_lounge(True)
    c.place()
    plain = render(c.character)
    try:
        _mods("neon-ice", "holo-visor")
        c.character.update()
        dressed = render(c.character)
        assert c.character.lying_source() is not None
        blue = sum(1 for x in range(0, dressed.width(), 3) for y in range(0, dressed.height(), 3)
                   if (lambda q: q.blue() > 200 and q.red() < 120 and q.alpha() > 200)(dressed.pixelColor(x, y)))
        blue0 = sum(1 for x in range(0, plain.width(), 3) for y in range(0, plain.height(), 3)
                    if (lambda q: q.blue() > 200 and q.red() < 120 and q.alpha() > 200)(plain.pixelColor(x, y)))
        assert blue > blue0 + 50                             # her lying body in the skin's colours, not just hair
    finally:
        _mods()
        assert not effects.EFFECTS.palette


def test_cosmetics_take_a_skins_colours():
    from capri.mods import effects
    try:
        _mods("cyber-ears")
        before = effects.EFFECTS.cosmetics[0].image().copy()
        _mods("cyber-ears", "neon-ice")
        after = effects.EFFECTS.cosmetics[0].image()
        assert before != after
    finally:
        _mods()


def test_every_personality_is_a_mod_and_switches_her(tmp_path):
    from capri import personality
    from capri.mods import effects
    from capri.mods.store import Store
    from capri.settings import Settings
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    ids = {m.id for m in store.builtin()}
    assert {f"{k}-personality" for k in personality.PERSONALITIES} <= ids
    s = Settings()
    s.save = lambda: None
    s.personality = "sweet"
    m = _mods("tsundere-personality")
    effects.apply_behaviour(s, m)
    assert s.personality == "tsundere"
    m.set_enabled("tsundere-personality", False)
    effects.apply_behaviour(s, m)
    assert s.personality == "sweet"                          # yours back
    _mods()


def test_one_personality_mod_at_a_time():
    m = _mods("tsundere-personality")
    from capri.mods.store import Store
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    by = {x.id: x for x in store.builtin()}
    m.install_bytes(store.download(by["sweet-personality"]))
    on = [x.manifest.id for x in m.enabled() if x.manifest.type == "personality"]
    assert len(on) == 1
    from capri.mods import effects
    effects.reload(type(m)(Path(tempfile.mkdtemp())))


def test_wave_moves_the_whole_arm_and_turns_the_hand():
    from capri.ui import rig
    from capri.ui.rig import Pose
    from test_v111 import companion
    c = companion()
    r = c.character.full_rig()
    a = r._arm_angle("right", Pose(wave=1.0, wag=1.0), "right")
    b = r._arm_angle("right", Pose(wave=1.0, wag=-1.0), "right")
    assert abs(a - b) >= 2 * rig.SHOULDER_WAG - 0.01          # the shoulder swings too, not just the elbow


def test_idle_moves_are_smaller():
    from capri.ui import character_window as cw
    assert cw.BODY_POSES["look_around"]["lean"] < 0.035 and cw.CharacterWindow.IDLE_MOVE_SIZE < 1
    from capri.ui.idle_acts import PROP_SIZE
    assert PROP_SIZE < 1


def test_afk_she_floats_smoothly():
    from test_v111 import companion
    c = companion()
    c.place()
    ch = c.character
    assert ch.hover_lift() == 0.0
    ch.set_napping(True)
    ch._nap_since = time.monotonic() - 5
    lifts = [ch.hover_lift(time.monotonic() + k * 0.2) for k in range(18)]
    assert min(lifts) > 0 and max(lifts) - min(lifts) > 1          # up off the ground, rising and falling
    assert all(abs(a - b) < 3 for a, b in zip(lifts, lifts[1:]))   # smoothly
    ch.set_napping(False)
    assert ch.hover_lift() == 0.0


def test_panel_reads_like_a_chat_log():
    from test_v111 import companion
    from capri.states import State
    c = companion()
    c.place()
    ctl = c.panel.controller
    ctl.log("Heard", '"what time is it"')
    ctl.set_state(State.SPEAKING, "It's 9:41.")
    c.panel.refresh()
    assert c.panel._said and c.panel._title_lines[0].startswith("CAPRI: ")
    ctl.set_state(State.PROCESSING, "Thinking...")
    c.panel.refresh()
    assert not c.panel._said


# -- round two: looks / chat skins as mods, the visor, chaos, fewer glitches and idle things -------------------------
def test_looks_and_chat_skins_are_mods_and_switch_her():
    from capri.mods import effects
    from capri.mods.store import Store
    from capri.settings import Settings
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    ids = {m.id for m in store.builtin()}
    assert {"lying-down", "neon-body", "full-colour-body", "flat-body", "classic-hair", "mask-drone",
            "portrait-style", "sit-on-windows", "netrunner-chat", "holocall-chat"} <= ids
    s = Settings()
    s.save = lambda: None
    m = _mods("lying-down", "neon-body", "netrunner-chat")
    changed = effects.apply_behaviour(s, m)
    assert s.lounge and s.body_style == "neon" and s.chat_skin == "netrunner"
    assert {"lounge", "body_style", "chat_skin"} <= set(changed)
    m.set_enabled("neon-body", False)
    effects.apply_behaviour(s, m)
    assert s.body_style == "flat"                              # yours back
    m.set_enabled("full-colour-body", False)
    _mods()


def test_two_body_looks_cant_be_on_together():
    from capri.mods.store import Store
    m = _mods("neon-body")
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    by = {x.id: x for x in store.builtin()}
    m.install_bytes(store.download(by["full-colour-body"]))
    assert [x.manifest.id for x in m.enabled() if x.manifest.type == "look"] == ["full-colour-body"]
    _mods()


def test_a_look_mod_cant_change_anything_else():
    from capri.mods.manifest import ModError, check
    base = {"id": "bad-look", "name": "Bad", "version": "1.0.0", "type": "look", "capri": ">=2.4.0"}
    with pytest.raises(ModError):
        check({**base, "settings": {"ai_provider": "openai"}})
    with pytest.raises(ModError):
        check({**base, "settings": {"body_style": "rainbow"}})
    check({**base, "settings": {"body_style": "neon"}})


def test_moved_settings_are_gone_from_their_old_places():
    from test_v111 import companion
    from capri.ui.look_tab import LookTab
    c = companion()
    tab = LookTab(c)
    form = tab.layout()
    shown = {form.itemAt(i).widget() for i in range(form.count()) if form.itemAt(i).widget() is not None}
    for w in (tab.style_box, tab.hair_box, tab.body_box, tab.drone_box, tab.lounge, tab.perch):
        assert w not in shown
    import inspect
    from capri.ui import assistant_tab, chat_window
    assert 'form.addRow("Personality"' not in inspect.getsource(assistant_tab)
    assert "self.skin_box.hide()" in inspect.getsource(chat_window)


def test_the_visor_sits_on_her_eyes():
    from capri.mods import effects
    from capri.ui.rig import EYES
    from test_v111 import companion, render
    c = companion()
    c.character.set_body_look("flat")
    c.place()
    try:
        _mods("holo-visor")
        img = render(c.character)
        rig = c.character.figure_rig()
        body = c.character.content_rect()
        k = c.character._figure_h / rig.h
        ex = body.x() + (EYES[0][0][0] + EYES[1][0][0]) / 2 * rig.w * k
        ey = body.y() + (EYES[0][0][1] + EYES[1][0][1]) / 2 * rig.h * k
        q = img.pixelColor(round(ex), round(ey))
        assert q.alpha() > 200 and q.green() > q.red()            # the green lens right over her eyes
    finally:
        _mods()
        assert not effects.EFFECTS.cosmetics


def test_chaos_is_chaos_and_never_draws():
    import random
    from capri.desktop_life import ChaosMode
    assert ChaosMode.GAP[1] <= 20 and ChaosMode.COMBO > 0
    did = []
    c = ChaosMode({"a": lambda: did.append("a"), "b": lambda: did.append("b")}, lambda: True, rng=random.Random(3))
    c.set_on(True)
    for _ in range(20):
        c._go()
    assert any(did.count(x) for x in "ab") and len(did) > 20     # some turns do two things at once
    c.set_on(False)
    import inspect
    from capri import app
    src = inspect.getsource(app)
    chaos_src = src[src.index("chaos = ChaosMode("):src.index("app._chaos = chaos")]
    assert "doodle" not in chaos_src and "canvas" not in chaos_src


def test_she_glitches_and_does_things_by_herself_far_less():
    from capri.ui import idle_acts, roam
    from capri.ui.character_window import CharacterWindow  # noqa: F401
    assert idle_acts.WEIGHTS[idle_acts.ACTS.index("glitch")] == 0
    assert idle_acts.GAP[0] >= 180 and roam.WAIT[0] >= 120
    from test_v111 import companion
    from capri.states import State
    c = companion()
    c.place()
    ctl = c.panel.controller
    ctl.set_state(State.PROCESSING, "Thinking...")
    c.panel.refresh()
    ctl.set_state(State.SPEAKING, "Hi.")
    c.panel.refresh()
    assert not c.panel.static.bursting                          # no static burst on an ordinary change
    ctl.set_state(State.ERROR, "Nope.")
    c.panel.refresh()
    assert c.panel.static.bursting


def test_afk_float_keeps_her_arms_still():
    from test_v111 import companion
    c = companion()
    c.place()
    ch = c.character
    ch.set_napping(True)
    ch._nap_since = time.monotonic() - 5
    a = ch.figure_pose().sweep
    time.sleep(0.6)
    b = ch.figure_pose().sweep
    assert abs(a - b) < 0.02


# -- round three: mods in her greeting and on her panel, no "ow" when you move her, compact box, more clones ---------
def test_her_greeting_wears_her_mods():
    from test_v111 import companion
    from capri.ui.greeting import GreetingShow as Greeting
    c = companion()
    c.character.set_body_look("flat")
    try:
        _mods("neon-ice", "holo-visor")
        g = Greeting.__new__(Greeting)
        g.companion, g._rig = c, None
        big = g._make_big(300)
        assert big.rig is c.character.full_rig()                 # her real figure: look + skin colours
        import inspect
        from capri.ui import greeting
        assert "paint_cosmetics" in inspect.getsource(greeting.RigFigure)
    finally:
        _mods()


def test_her_panel_takes_a_skin():
    from PySide6.QtGui import QColor
    from test_v111 import companion
    from capri.ui import theme
    c = companion()
    assert c.panel.mod_red() == QColor(theme.MSG_RED)
    try:
        _mods("neon-ice")
        assert c.panel.mod_red() == QColor("#33e0ff")            # the skin's colour on the panel
        icon = c.panel._icon()
        assert not icon.isNull()
    finally:
        _mods()


def test_moving_her_never_makes_her_talk():
    import inspect
    from capri import app
    src = inspect.getsource(app)
    i = src.index("throw_show = ThrowShow(")
    assert "lambda text, emotion: None" in src[i:i + 200]


def test_always_the_compact_text_box():
    from test_v111 import companion
    from capri.ui.status_panel import compact_metrics
    from capri.ui.companion import box_scale
    c = companion()
    assert c.panel.panel_width == compact_metrics(box_scale(c.settings.size)).width
    c.set_compact(False)
    assert c.panel.panel_width == compact_metrics(box_scale(c.settings.size)).width


def test_clones_are_many_and_spread_out():
    import random
    from PySide6.QtGui import QGuiApplication, QImage
    from capri.ui.clones import MAX_CLONES, Clones
    assert MAX_CLONES >= 20
    pic = QImage(60, 120, QImage.Format.Format_ARGB32_Premultiplied)
    pic.fill(0xff00ff00)
    cl = Clones(lambda: pic, rng=random.Random(4))
    assert cl.make(10, 30) == 10
    area = QGuiApplication.primaryScreen().availableGeometry()
    xs = sorted(c.x() for c in cl.clones)
    ys = [c.y() for c in cl.clones]
    assert xs[-1] - xs[0] > area.width() * 0.6                    # across the screen
    assert max(ys) - min(ys) > 40                                  # and at different heights
    assert min(b - a for a, b in zip(xs, xs[1:])) > 0               # not stacked on each other
    cl.clear()
    from capri.commands.more import desk_intent
    assert desk_intent("make clones")[2] == "8"


def test_her_chat_box_changes_back_when_the_skin_goes_off():
    from PySide6.QtGui import QColor
    from test_v111 import companion, render
    from capri.ui import theme
    c = companion()
    c.place()
    try:
        _mods("neon-ice")
        c.panel.mods_changed()
        on = render(c.panel)
        _mods()
        c.panel.mods_changed()
        off = render(c.panel)
        assert c.panel.mod_red() == QColor(theme.MSG_RED)
        assert on != off                                       # redrawn in her own colours again
    finally:
        _mods()


def test_mod_pictures_show_her():
    import io
    import zipfile
    from PIL import Image
    for f in sorted((ROOT / "assets" / "mods").glob("*.capri-mod")):
        z = zipfile.ZipFile(f)
        pv = next(n for n in z.namelist() if n.endswith("preview.png"))
        im = Image.open(io.BytesIO(z.read(pv))).convert("RGB")
        assert im.size == (256, 256)
        assert len(set(im.resize((32, 32)).getdata())) > 60, f.name     # a picture, not a few stripes


# -- 2.5: a real head pat, a quicker throw ---------------------------------------------------------------------------
def test_head_pat_is_a_rub_not_a_click():
    from PySide6.QtCore import QPointF, Qt
    from test_v111 import companion
    c = companion()
    c.place()
    ch = c.character
    got = []
    c.patted.connect(got.append)
    head = ch.head_area()
    y = head.center().y()
    ch._rub_step(QPointF(head.center().x(), y), Qt.MouseButton.NoButton)    # just resting there: nothing
    time.sleep(0.3)
    ch._rub_step(QPointF(head.center().x() + 1, y), Qt.MouseButton.NoButton)
    assert got == []
    x0 = head.center().x()
    for i in range(12):                                                      # back and forth over her head
        ch._rub_step(QPointF(x0 + (25 if i % 2 else -25), y), Qt.MouseButton.NoButton)
        time.sleep(0.09)
    assert got == ["head"]
    for i in range(12):                                                      # straight after: a short rest
        ch._rub_step(QPointF(x0 + (25 if i % 2 else -25), y), Qt.MouseButton.NoButton)
        time.sleep(0.02)
    assert got == ["head"]
    low = QPointF(x0, ch.content_rect().bottom() - 5)                         # rubbing her legs: not a pat
    ch._rub = None
    del ch._rub
    for i in range(12):
        ch._rub_step(low + QPointF(25 if i % 2 else -25, 0), Qt.MouseButton.NoButton)
        time.sleep(0.09)
    assert got == ["head"]


def test_quicker_after_a_throw():
    from capri.ui import fling
    assert fling.DAZED_TIME + fling.GETUP_TIME + fling.SLAM_TIME + fling.HIT_STOP < 1.2
