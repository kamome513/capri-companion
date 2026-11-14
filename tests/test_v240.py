"""2.4: mods - checks, install / uninstall / on-off / conflicts / export / import, the store, and what mods change."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager, pack_folder, validate_folder  # noqa: E402
from capri.mods.manifest import ModError, check, fits  # noqa: E402
from capri.mods.store import Store, update_all, updates  # noqa: E402

BUILTIN = Path(__file__).resolve().parents[1] / "assets" / "mods"


def _mod(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _lines_mod(mod_id="pack", version="1.0.0", **extra) -> bytes:
    data = {"id": mod_id, "name": mod_id.title(), "version": version, "type": "lines",
            "lines": {"greet": [f"hi from {mod_id}"], "pat": ["pat from " + mod_id]}, **extra}
    return _mod({"mod.json": json.dumps(data)})


@pytest.fixture
def manager(tmp_path):
    m = ModManager(tmp_path / "mods")
    yield m
    effects.reload(ModManager(tmp_path / "empty"))          # leave no mod effects behind for other tests


def test_the_checks_catch_bad_mods():
    good = {"id": "neon", "name": "Neon", "version": "1.0", "type": "skin", "palette": {"hair": "#00ffcc"}}
    assert check(good).type == "skin"
    for bad, why in (({**good, "id": "Bad Id!"}, "id"), ({**good, "type": "virus"}, "type"),
                     ({**good, "palette": {"hair": "red"}}, "colour"), ({**good, "version": "one"}, "version"),
                     ({"id": "bb", "name": "B", "version": "1", "type": "behaviour",
                       "settings": {"auto_update": False}}, "can't change")):
        with pytest.raises(ModError, match=why):
            check(bad)
    with pytest.raises(ModError, match="no programs"):
        check({**good, "type": "lines", "lines": {"greet": ["x"]}}, {"evil.exe": 10})
    assert fits(">=2.4.0", "2.4.0") and fits(">=2.4,<3", "2.9.1") and not fits(">=3", "2.4.0")


def test_install_turn_on_off_conflicts_export_import_uninstall(manager, tmp_path):
    a = manager.install_bytes(_lines_mod("alpha"))
    assert a.enabled and a.manifest.name == "Alpha" and (manager.root / "alpha" / "mod.json").is_file()
    skin1 = _mod({"mod.json": json.dumps({"id": "ice", "name": "Ice", "version": "1", "type": "skin",
                                          "palette": {"hair": "#33e0ff"}})})
    skin2 = _mod({"mod.json": json.dumps({"id": "acid", "name": "Acid", "version": "1", "type": "skin",
                                          "palette": {"hair": "#7dff3a"}})})
    manager.install_bytes(skin1)
    manager.install_bytes(skin2, enable=False)
    off = manager.set_enabled("acid", True)                 # two skins: the new one wins
    assert off == ["Ice"] and [m.id for m in manager.enabled()] == ["alpha", "acid"]
    out = manager.export("alpha", tmp_path / "share")
    assert out.suffix == ".capri-mod"
    manager.uninstall("alpha")
    assert manager.get("alpha") is None
    again = manager.install_file(out)
    assert again.id == "alpha" and again.manifest.data["lines"]["greet"] == ["hi from alpha"]
    v2 = manager.install_bytes(_lines_mod("alpha", "2.0.0"))
    assert v2.manifest.version == "2.0.0" and v2.enabled           # an update keeps it on


def test_unsafe_or_broken_files_are_refused(manager):
    for files, why in (({"mod.json": json.dumps({"id": "x1", "name": "X", "version": "1", "type": "lines",
                                                  "lines": {"greet": ["a"]}}), "../../evil.png": b"x"}, "unsafe"),
                       ({"readme.txt": b"no manifest"}, "no mod.json"),
                       ({"mod.json": "{not json"}, "valid JSON"),
                       ({"mod.json": json.dumps({"id": "x2", "name": "X", "version": "1", "type": "sounds",
                                                 "sounds": {"done": "missing.wav"}})}, "isn't in the mod")):
        with pytest.raises(ModError, match=why):
            manager.install_bytes(_mod(files))
    with pytest.raises(ModError, match="not a zip"):
        manager.install_bytes(b"MZ\x90\x00 an exe")
    with pytest.raises(ModError, match="needs Capri"):
        manager.install_bytes(_lines_mod("future", capri=">=99"))
    assert manager.installed() == []


def test_the_builtin_store_mods_are_all_valid_and_install(manager):
    store = Store(lambda: "", folder=BUILTIN)
    listings = store.builtin()
    kinds = {m.type for m in listings}
    assert len(listings) >= 10 and kinds == {"skin", "cosmetic", "animations", "personality", "behaviour",
                                             "lines", "sounds", "look"}
    for listing in listings:
        assert listing.preview, listing.id                  # every one has a preview picture
        manager.install_bytes(store.download(listing), source="store", enable=False)
    assert len(manager.installed()) == len(listings)


def test_online_store_checks_downloads_and_updates(manager):
    newer = _lines_mod("alpha", "2.0.0")
    index = {"mods": [{"id": "alpha", "name": "Alpha", "version": "2.0.0", "type": "lines", "category": "x",
                       "url": "https://raw.githubusercontent.com/x/alpha.capri-mod",
                       "sha256": hashlib.sha256(newer).hexdigest(), "size": len(newer), "rating": 4.5, "ratings": 8},
                      {"id": "evil", "name": "Evil", "version": "1", "type": "lines", "url": "https://evil.example/x"}]}

    def fetch(url, limit=0):
        return json.dumps(index).encode() if url.endswith("index.json") else newer
    store = Store(lambda: "https://raw.githubusercontent.com/x/index.json", fetch=fetch, folder=Path("/nonexistent"))
    found = store.online()
    assert [m.id for m in found] == ["alpha"] and found[0].rating == 4.5        # not-GitHub links are dropped
    manager.install_bytes(_lines_mod("alpha", "1.0.0"), source="store")
    assert [m.id for m in updates(found, {"alpha": "1.0.0"})] == ["alpha"]
    assert update_all(manager, store) == ["Alpha 2.0.0"] and manager.version_of("alpha") == "2.0.0"
    found[0].sha256 = "0" * 64
    with pytest.raises(ModError, match="checksum"):
        store.download(found[0])
    broken = Store(lambda: "https://raw.githubusercontent.com/x/index.json",
                   fetch=lambda *a: (_ for _ in ()).throw(OSError("offline")), folder=BUILTIN)
    assert broken.listings() and "isn't reachable" in broken.online_error   # offline: built-in mods still there


def test_what_mods_change(manager):
    from capri import personality
    store = Store(lambda: "", folder=BUILTIN)
    by_id = {m.id: m for m in store.builtin()}
    for mod_id in ("neon-ice", "cyber-ears", "holo-visor", "dance-floor", "noir", "cozy-chrome", "synth-blips"):
        manager.install_bytes(store.download(by_id[mod_id]), source="store")
    e = effects.reload(manager)
    assert e.palette["hair"] == "#33e0ff" and {c.slot for c in e.cosmetics} == {"ears", "face"}
    assert {a["name"] for a in e.animations} == {"Hip sway", "Victory wave", "Big stretch"}
    assert "noir" in personality.PERSONALITIES and set(e.sounds) >= {"wake", "done", "pat"}
    assert "Welcome home, choom. Kettle's on." in e.mix("greet", [])
    from capri.ui import hair
    assert hair.STORM_RED.name() == "#33e0ff"
    manager.set_enabled("noir", False)
    manager.set_enabled("neon-ice", False)
    effects.reload(manager)
    assert "noir" not in personality.PERSONALITIES and hair.STORM_RED.name() == hair.STORM_RED_DEFAULT.name()


def test_a_skin_recolours_her(manager):
    from PySide6.QtGui import QColor, QImage
    img = QImage(4, 1, QImage.Format.Format_RGBA8888)
    for x, c in enumerate(((249, 8, 84), (40, 230, 110), (110, 60, 200), (20, 18, 26))):
        img.setPixelColor(x, 0, QColor(*c))
    out = effects.recolor(img, {"hair": "#33e0ff", "accent": "#ffe600", "outline": "#2a6cff"})
    hair_px, accent_px = out.pixelColor(0, 0), out.pixelColor(1, 0)
    assert hair_px.blue() > 200 and hair_px.red() < 120           # pink-red -> ice blue
    assert accent_px.red() > 200 and accent_px.green() > 200       # green -> yellow
    assert out.pixelColor(3, 0) == img.pixelColor(3, 0)            # (body not in this palette: unchanged)


def test_animation_keyframes_play_smoothly():
    anim = {"seconds": 2.0, "loop": 2, "keys": [{"t": 0, "lean": 0.0}, {"t": 0.5, "lean": 0.2, "eyes": "happy"},
                                                 {"t": 1, "lean": 0.0}]}
    start, _ = effects.animation_moves(anim, 0.0)
    mid, eyes = effects.animation_moves(anim, 1.0)
    quarter, _ = effects.animation_moves(anim, 0.5)
    assert start["lean"] == 0 and abs(mid["lean"] - 0.2) < 1e-6 and 0 < quarter["lean"] < 0.2 and eyes == "happy"
    assert effects.animation_moves(anim, 3.0) is not None and effects.animation_moves(anim, 4.1) is None


def test_behaviour_mods_give_your_settings_back(manager):
    from capri.settings import Settings
    s = Settings()
    s.roaming, s.glitches = False, 600
    store = Store(lambda: "", folder=BUILTIN)
    manager.install_bytes(store.download(next(m for m in store.builtin() if m.id == "free-roam")))
    effects.apply_behaviour(s, manager)
    assert s.roaming and s.glitches == 600          # (2.4.1: Free Roam no longer makes her glitch)
    manager.set_enabled("free-roam", False)
    effects.apply_behaviour(s, manager)
    assert not s.roaming and s.glitches == 600


def test_mod_maker_templates_are_valid(tmp_path):
    from capri.mods.creator import new_mod
    from capri.mods.manifest import TYPES
    for kind in TYPES:
        folder = new_mod(tmp_path, kind, f"my-{kind}", f"My {kind}")
        ok, report = validate_folder(folder)
        assert ok, report
        assert pack_folder(folder)
    (tmp_path / "my-skin" / "mod.json").write_text('{"id": "x"}')
    ok, report = validate_folder(tmp_path / "my-skin")
    assert not ok and "Not ready" in report


# -- desktop interactions ----------------------------------------------------------------------------------------------
def test_she_draws_marks_stroke_by_stroke_and_they_fade(monkeypatch):
    import time as _t
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QImage
    from capri.ui import canvas as cv
    followed = []
    c = cv.ScreenCanvas(cursor=lambda x, y: followed.append((x, y)))
    c.circle(QRectF(300, 300, 120, 40), "Start")
    c.point(QPointF(500, 500), "here")
    assert c.doodle("heart", QRectF(50, 50, 150, 150)) and not c.doodle("dragon", QRectF(0, 0, 9, 9))
    assert c.isVisible() and len(c.marks) == 3
    assert c.marks[1].started >= c.marks[0].started + c.marks[0].draw_for - 0.01      # one after another
    c.marks[0].started -= cv.DRAW_SECONDS / 2
    c._tick()
    assert followed                                                 # her cursor follows the pen
    img = QImage(c.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    for m in c.marks:
        m.started = _t.monotonic() - m.draw_for                    # all drawn
    c.render(img)
    from capri.ui import looks
    assert (looks.to_array(img)[..., 3] > 0).sum() > 500
    for m in c.marks:
        m.started -= 100                                            # long ago: faded
    c._tick()
    assert not c.marks and not c.isVisible()


def test_clones_appear_pop_and_clear():
    from PySide6.QtGui import QColor, QImage
    from capri.ui.clones import MAX_CLONES, Clones
    pic = QImage(60, 120, QImage.Format.Format_ARGB32_Premultiplied)
    pic.fill(QColor(255, 0, 80))
    cl = Clones(lambda: pic)
    assert cl.make(5) == 5 and cl.count == 5
    cl.clones[0].pop()
    assert cl.count == 4
    assert cl.make(50) == MAX_CLONES - 4                            # never more than MAX_CLONES at once
    assert cl.clear() == MAX_CLONES and cl.count == 0
    assert Clones(lambda: None).make(3) == 0


def test_app_reactions_once_in_a_while_and_events_always():
    from capri.desktop_life import AppReactions
    running, said, events, clock = [{"explorer.exe"}], [], [], [0.0]
    r = AppReactions(lambda: running[0], lambda: {"spotify.exe": ("Spotify", False), "game:deadlock": ("Deadlock", True)},
                     said.append, lambda: True, clock=lambda: clock[0], event=lambda k, a: events.append((k, a)))
    r._timer.stop()
    r.check()                                                       # first look: just remembers
    running[0] = {"explorer.exe", "spotify.exe"}
    r.check()
    assert events == [("app_open", "Spotify")] and len(said) == 1 and "Spotify" in said[0]
    running[0] = {"explorer.exe", "spotify.exe", "game:deadlock"}
    clock[0] += 30
    r.check()
    assert events[-1] == ("game_open", "Deadlock") and len(said) == 1   # too soon to say more
    clock[0] += 700                                                 # (the same app: at most every 10 min)
    running[0] = {"explorer.exe", "game:deadlock"}
    r.check()
    assert events[-1] == ("app_close", "Spotify") and len(said) == 2


def test_chaos_mode_only_when_allowed():
    from capri.desktop_life import ChaosMode
    did, allowed = [], [False]
    c = ChaosMode({"a": lambda: did.append("a"), "b": lambda: did.append("b")}, lambda: allowed[0])
    c.COMBO = 0.0                                                   # (one at a time here; 2.4.1 does combos too)
    c.set_on(True)
    c._go()
    assert did == []                                                # busy / in a game: nothing
    allowed[0] = True
    c._go()
    assert len(did) == 1
    c.set_on(False)
    c._go()
    assert len(did) == 1


def test_desktop_commands_by_voice():
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    calls = []

    class Desk:
        def doodle(self, name, box=None):
            calls.append(("doodle", name))
            return True
        def clear(self):
            calls.append(("clear",))
        def clones(self, n, life=None):
            calls.append(("clones", n))
            return n
        def clear_clones(self):
            calls.append(("clear_clones",))
            return 2
        def chaos(self, on):
            calls.append(("chaos", on))
        def mark(self, kind, rect, label):
            calls.append(("mark", kind, label))
    r.router.services.desk = Desk()
    for said in ("draw me a cat", "make 4 clones", "clear the clones", "chaos mode on", "clear the drawing"):
        r.router.handle(said)
    assert calls == [("doodle", "cat"), ("clones", 4), ("clear_clones",), ("chaos", True), ("clear",)]
    assert r.assistant.settings.chaos_mode


def test_hologram_mode_gives_your_click_through_back():
    from test_v116 import companion
    c = companion()
    from PySide6.QtCore import Qt
    through = lambda: bool(c.character.windowFlags() & Qt.WindowType.WindowTransparentForInput)   # noqa: E731
    c.set_click_through(False)
    c.set_hologram(True)
    assert through() and c.character.hologram and c.settings.hologram
    assert not c.settings.click_through                    # (2.6.2: the setting itself is never changed)
    c.set_hologram(False)
    assert not through() and not c.settings.click_through and not c.character.hologram


# -- screen intelligence -----------------------------------------------------------------------------------------------
def test_ai_answers_with_marks_are_read_and_drawn_where_they_are():
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage
    from capri.ai.claude import AIReply
    from capri.integrations.screen_intel import ScreenIntel, parse_answer
    say, marks = parse_answer('Sure! {"say": "That red box says the file is missing.", "marks": '
                              '[{"label": "Error", "x": 0.25, "y": 0.5, "w": 0.5, "h": 0.1}, {"label": "bad", "x": 7}]}')
    assert say.startswith("That red box") and marks == [{"label": "Error", "x": 0.25, "y": 0.5, "w": 0.5, "h": 0.1}]
    assert parse_answer("Just words, no JSON.") == ("Just words, no JSON.", [])
    prompts, drawn, answers = [], [], []

    class Watch:
        def _look(self, prompt, then):
            prompts.append(prompt)
            then(AIReply('{"say": "Your build failed: a missing semicolon on line 12.", "marks": '
                         '[{"label": "line 12", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}]}'))
    shot = QImage(200, 100, QImage.Format.Format_RGB32)
    shot.fill(QColor(30, 30, 30))
    intel = ScreenIntel(Watch(), lambda: shot, lambda: QRectF(1000, 0, 1920, 1080), drawn.extend)
    intel.look("error", "help me fix this", lambda text, emotion: answers.append((text, emotion)))
    assert "1-3 concrete steps" in prompts[0] and "help me fix this" in prompts[0]
    assert answers[0][0].startswith("Your build failed") and answers[0][1] == "serious"
    rect, label = drawn[0]
    assert label == "line 12" and (rect.x(), rect.y()) == (1000 + 192, 216) and round(rect.width()) == 576


def test_what_changed_is_found_on_this_pc():
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from capri.integrations.screen_intel import ScreenIntel
    shot = QImage(640, 360, QImage.Format.Format_RGB32)
    shot.fill(QColor(30, 30, 40))
    drawn = []
    intel = ScreenIntel(None, lambda: shot, lambda: QRectF(0, 0, 640, 360), drawn.extend)
    said, n = intel.changes()                                       # no picture yet: she takes one
    assert n == 0 and "taken a picture" in said
    said, n = intel.changes()
    assert n == 0 and "Nothing's changed" in said
    p = QPainter(shot)
    p.fillRect(500, 20, 100, 60, QColor(255, 255, 255))           # a notification popped up
    p.end()
    said, n = intel.changes()
    assert n == 1 and drawn and "circled" in said
    rect = drawn[0][0]
    assert 470 <= rect.x() <= 510 and rect.y() <= 30 and rect.right() >= 590


def test_screen_intel_commands_by_voice():
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    calls = []

    class Intel:
        def look(self, task, question, then):
            calls.append((task, question))
            then("It's a spreadsheet of your budget.", "neutral")
        def remember(self):
            calls.append(("remember",))
            return True
        def changes(self):
            calls.append(("changes",))
            return "1 part of your screen changed.", 1
    r.router.services.intel = Intel()
    for said in ("read this chart", "help me fix this error", "remember my screen", "what changed", "explain this app"):
        r.router.handle(said)
    assert [c[0] for c in calls] == ["chart", "error", "remember", "changes", "explain"]
    assert calls[1][1] == "help me fix this error"


# -- automations -------------------------------------------------------------------------------------------------------
def _engine(settings, now=None, idle=None):
    from datetime import datetime
    from capri.automation import AutomationEngine
    ran, said, clock = [], [], [0.0]
    e = AutomationEngine(settings, ran.append, said.append, idle_seconds=idle, clock=lambda: clock[0],
                         now=now or datetime.now)
    e._timer.stop()
    return e, ran, said, clock


def test_automations_are_checked_and_kept_in_settings(tmp_path):
    from capri import automation as auto
    from capri.settings import Settings
    good = auto.Automation("Morning", "time", "9:05", [{"type": "say", "value": "Morning!"}], days=[0, 1])
    assert good.problem() == ""
    assert auto.Automation("x", "time", "25:00", [{"type": "say", "value": "a"}]).problem().startswith("the time")
    assert auto.Automation("x", "app_open", "", [{"type": "say", "value": "a"}]).problem().startswith("say which")
    assert auto.Automation("x", "startup", "", []).problem() == "add at least one action"
    assert auto.Automation.from_dict({"trigger": "rm -rf", "actions": []}) is None
    bad_step = auto.Automation.from_dict({"name": "a", "trigger": "startup", "actions": [{"type": "shell", "value": "x"}]})
    assert bad_step.actions == []                                    # only command / say / wait steps exist
    s = Settings()
    auto.save(s, [good])
    assert auto.load(Settings.load())[0].to_dict() == good.to_dict()   # survives a restart


def test_app_and_game_events_and_phrases_run_the_right_automations():
    from capri import automation as auto
    from capri.settings import Settings
    s = Settings()
    s.automations = [auto.Automation("Spotify", "app_open", "spotify", [{"type": "command", "value": "do a dance"}]).to_dict(),
                     auto.Automation("Deadlock", "game_open", "Deadlock",
                                                   [{"type": "command", "value": "quiet mode"},
                                                    {"type": "say", "value": "Good luck."}]).to_dict(),
                     auto.Automation("Gaming", "phrase", "Gaming time!", [{"type": "command", "value": "open steam"}]).to_dict(),
                     auto.Automation("Off one", "app_open", "spotify", [{"type": "say", "value": "x"}], enabled=False).to_dict()]
    e, ran, said, clock = _engine(s)
    e.app_event("app_open", "Spotify")
    e.app_event("game_open", "Deadlock")
    assert ran == ["do a dance", "quiet mode"] and said == ["Good luck."]
    e.app_event("app_open", "Spotify")                              # moments later: not again
    assert ran == ["do a dance", "quiet mode"]
    clock[0] += 30
    e.app_event("app_open", "Spotify")
    assert ran[-1] == "do a dance"
    assert e.phrase("gaming time") and ran[-1] == "open steam" and not e.phrase("something else")


def test_time_triggers_once_a_day_on_the_chosen_days():
    from datetime import datetime
    from capri import automation as auto
    from capri.settings import Settings
    s = Settings()
    s.automations = [auto.Automation("Weekday 9", "time", "09:00", [{"type": "say", "value": "Morning"}],
                                     days=[0, 1, 2, 3, 4]).to_dict()]
    now = [datetime(2026, 11, 13, 9, 0)]                            # a Friday
    e, ran, said, clock = _engine(s, now=lambda: now[0])
    e.tick()
    clock[0] += 60
    e.tick()                                                        # still 09:00: once
    assert said == ["Morning"]
    now[0] = datetime(2026, 11, 14, 9, 0)                           # Saturday: not chosen
    clock[0] += 99999
    e.tick()
    assert said == ["Morning"]


def test_away_and_back():
    from capri import automation as auto
    from capri.settings import Settings
    s = Settings()
    s.automations = [auto.Automation("Away", "away", "10", [{"type": "command", "value": "quiet mode"}]).to_dict(),
                     auto.Automation("Back", "back", "", [{"type": "say", "value": "Welcome back"}]).to_dict()]
    idle = [0.0]
    e, ran, said, clock = _engine(s, idle=lambda: idle[0])
    idle[0] = 11 * 60
    e.tick()
    e.tick()
    assert ran == ["quiet mode"]
    idle[0] = 2
    e.tick()
    assert said == ["Welcome back"]


def test_wait_steps_really_wait():
    import time as _t
    from capri import automation as auto
    from capri.settings import Settings
    s = Settings()
    e, ran, said, clock = _engine(s)
    e.run(auto.Automation("w", "startup", "", [{"type": "say", "value": "one"}, {"type": "wait", "value": "0.3"},
                                                {"type": "say", "value": "two"}]))
    assert said == ["one"]
    end = _t.monotonic() + 2
    while _t.monotonic() < end and said == ["one"]:
        app.processEvents()
        _t.sleep(0.02)
    assert said == ["one", "two"]


def test_a_phrase_automation_runs_through_her_commands_and_cant_loop():
    from capri import automation as auto
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    s = r.assistant.settings
    s.automations = [auto.Automation("Loop", "phrase", "loop time", [{"type": "command", "value": "loop time"},
                                                                     {"type": "command", "value": "quiet mode"}]).to_dict()]
    e, _ran, _said, _clock = _engine(s)
    e.run_command = r.router.handle
    r.router.services.automations = e
    r.router.handle("loop time")
    assert s.quiet_mode                                             # its steps ran (the loop step didn't re-run it)


def test_the_automation_editor_saves_what_you_build():
    from capri import automation as auto
    from capri.settings import Settings
    from capri.ui.automation_tab import AutomationTab
    s = Settings()
    tab = AutomationTab(s, None, lambda: ["Spotify", "Discord"])
    tab._from_template(1 + [t.name for t in auto.TEMPLATES].index("Gaming time"))
    assert auto.load(s)[0].name == "Gaming time"
    tab.name.setText("Movie night")
    tab.trigger.setCurrentIndex(tab.trigger.findData("app_open"))
    tab.value.setEditText("Spotify")
    tab._save()
    saved = auto.load(s)[0]
    assert saved.name == "Movie night" and saved.trigger == "app_open" and saved.value == "Spotify"
    assert [a["value"] for a in saved.actions] == ["open discord", "3", "open steam"]


def test_a_game_automation_without_a_name_is_any_game():
    from capri import automation as auto
    from capri.settings import Settings
    s = Settings()
    s.automations = [auto.Automation("Any game", "game_open", "", [{"type": "command", "value": "quiet mode"}]).to_dict()]
    assert auto.load(s)[0].problem() == ""
    e, ran, said, clock = _engine(s)
    e.app_event("game_open", "Hollow Knight")
    assert ran == ["quiet mode"]
