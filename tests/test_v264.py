"""2.6.4: the wall hit plays on any real hit (and with no vibe), she stays in front on a Mac, the update button
just updates (with progress), and the close / zap effect covers the whole window on a Mac."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRect, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri import updater  # noqa: E402
from capri.mods import effects  # noqa: E402
from capri.mods.manager import ModManager  # noqa: E402


@pytest.fixture(autouse=True)
def plain_after():
    yield
    effects.reload(ModManager(Path(tempfile.mkdtemp())))


def _show():
    from test_v111 import companion
    from capri.ui.fling import ThrowShow
    c = companion()
    show = ThrowShow(c, lambda: c.character.full_rig(), lambda *a: None)
    show._os_reduced = False
    spawned = []
    show.impacts.spawn = lambda *a, **k: spawned.append(a)
    return c, show, spawned


def test_her_own_impact_with_no_vibe():
    from capri.ui.impact import DEFAULT_IMPACT, validate
    assert validate(DEFAULT_IMPACT) == ""
    c, show, spawned = _show()
    assert show.vibe_impact() is DEFAULT_IMPACT
    assert show.throw(QPointF(3000, -200))
    show._start_slam("right", time.monotonic(), 2600)
    assert len(spawned) == 1 and spawned[0][2] is DEFAULT_IMPACT
    show._timer.stop()


def test_a_bounce_off_the_wall_is_a_hit_too():
    c, show, spawned = _show()
    assert show.throw(QPointF(3000, -200))
    now = time.monotonic()
    show._vibe_hit("left", 500, now)                       # a bounce: not a slam - still her impact
    show._vibe_hit("left", 900, now + 0.2)                 # ...once per throw
    assert len(spawned) == 1 and spawned[0][1] == QPointF(1, 0)
    show._timer.stop()
    show.active, c.busy_elsewhere = False, False
    assert show.throw(QPointF(-3000, -200))
    show._vibe_hit("bottom", 300, time.monotonic())        # a soft landing isn't a hit
    show._vibe_hit("top", 100, time.monotonic())           # nor a brush
    assert len(spawned) == 1
    show._timer.stop()


def test_effects_off_means_no_vibe_impact():
    from capri.mods.store import Store
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    m = ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(store.download({x.id: x for x in store.builtin()}["solaris"]))
    effects.reload(m)
    c, show, spawned = _show()
    assert show.vibe_impact() is effects.EFFECTS.style["impact"]
    c.settings.style_effects = False
    assert show.vibe_impact() is None


def test_mac_window_rects_are_not_halved(monkeypatch):
    from capri.ui import screen_spots
    monkeypatch.setattr(screen_spots.sys, "platform", "darwin")
    assert screen_spots.to_logical((100, 200, 900, 800)) == QRect(100, 200, 800, 600)


def test_her_windows_stay_when_you_click_another_app():
    from capri.ui.overlay_window import OverlayWindow
    w = OverlayWindow()
    assert w.testAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)


# -- updates ----------------------------------------------------------------------------------------------------------
def _manager(**kw):
    from capri.settings import Settings
    from capri.controller import CompanionController
    from capri.ui.updates import UpdateManager
    calls = {"quit": 0, "installed": []}
    state = {"ready": None}
    defaults = dict(check=lambda: None, download=lambda u, progress=None: Path("x.exe"),
                    ready=lambda: state["ready"], install=lambda p: calls["installed"].append(p) or True,
                    frozen=lambda: True, quit_app=lambda: calls.__setitem__("quit", calls["quit"] + 1),
                    confirm=lambda q: False)
    defaults.update(kw)
    s = Settings()
    s.auto_update = False
    m = UpdateManager(s, CompanionController(), None, None, **defaults)
    m._background = lambda work, callback: callback(_try(work))
    return m, calls, state


def _try(work):
    try:
        return work()
    except Exception as exc:
        return exc


def test_clicking_update_downloads_with_progress_and_installs():
    new = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri.exe", "Capri.exe", 5)
    seen = []

    def download(u, progress=None):
        for done in (1, 2, 3, 4, 5):
            progress(done, 5)
            seen.append(m.status)
        state["ready"] = ("9.9.9", Path("Capri.exe"))
        return Path("Capri.exe")
    m, calls, state = _manager(check=lambda: new, download=download)
    m.found = new                                           # (found earlier; auto-update off, so not fetched)
    assert calls["installed"] == [] and m.label() == "Update to Capri 9.9.9..."
    m.menu_clicked()                                        # you click "Update to 9.9.9"
    assert any("Downloading Capri 9.9.9..." in s and "%" in s for s in seen)
    assert calls["installed"] == [Path("Capri.exe")] and calls["quit"] == 1     # one click: updated


def test_check_for_updates_click_goes_straight_on():
    new = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri.exe", "Capri.exe", 5)

    def download(u, progress=None):
        state["ready"] = ("9.9.9", Path("Capri.exe"))
        return Path("Capri.exe")
    m, calls, state = _manager(check=lambda: new, download=download)
    m.menu_clicked()                                        # "Check for updates" - and there is one
    assert calls["installed"] == [Path("Capri.exe")]


def test_mac_update_unzips_after_she_closes(tmp_path, monkeypatch):
    app_dir = tmp_path / "Applications" / "Capri.app"
    app_dir.mkdir(parents=True)
    monkeypatch.setattr(updater, "mac_app", lambda: str(app_dir))
    ran = []
    assert updater._install_mac(tmp_path / "Capri-macOS.zip", lambda argv, **kw: ran.append(argv), tmp_path)
    script = Path(ran[0][1])
    assert ran[0][0] == "/bin/bash" and script.exists() and "ditto -x -k" in script.read_text()
    assert ran[0][3] == str(app_dir)                         # swaps this very app


def test_updates_are_checked_often():
    assert updater.CHECK_EVERY <= 6 * 3600


def test_update_not_built_for_this_computer_yet_never_opens_github():
    early = updater.Update("9.9.9", "", "", 0)                 # out, but no file for this system yet
    later = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri-macOS.zip", "Capri-macOS.zip", 5)
    answers = [early, early, later]

    def download(u, progress=None):
        state["ready"] = ("9.9.9", Path("Capri-macOS.zip"))
        return Path("Capri-macOS.zip")
    opened = []
    m, calls, state = _manager(check=lambda: answers.pop(0), download=download, open_page=opened.append)
    m.check_now()
    assert "still being made" in m.status and opened == []
    m.menu_clicked()                                            # you click Update: she looks again (still not there)
    assert opened == [] and "still being made" in m.status
    m.menu_clicked()                                            # now it's built: downloads and installs
    assert opened == [] and calls["installed"] == [Path("Capri-macOS.zip")]


def test_later_hits_leave_smaller_cracks_in_her_vibe():
    from capri.mods.store import Store
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    m = ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(store.download({x.id: x for x in store.builtin()}["sakura"]))
    effects.reload(m)
    c, show, spawned = _show()
    assert show.throw(QPointF(3000, -200))
    now = time.monotonic()
    show._start_slam("right", now, 2600)                     # first hit: the full impact
    show._start_slam("left", now + 0.5, 2600)                # later: a smaller crack, sakura's own colours
    assert len(spawned) == 2
    later = spawned[1][2]
    assert later["burst"] == [] and later["crack"]["glow"] == effects.EFFECTS.style["impact"]["crack"]["glow"]
    show._timer.stop()


def test_slam_effects_take_her_vibes_colours():
    from PySide6.QtGui import QColor
    from capri.mods.store import Store
    from capri.ui import fx
    store = Store(lambda: "", folder=ROOT / "assets" / "mods")
    m = ModManager(Path(tempfile.mkdtemp()))
    m.install_bytes(store.download({x.id: x for x in store.builtin()}["stormborn"]))
    effects.reload(m)
    e = fx.Effects()
    e.sparks(QPointF(), 0.0, 1.0, 40, (100, 200), 0.0)
    e.ring(QPointF(), 0.0, 10)
    hair = QColor(effects.EFFECTS.palette["hair"])
    assert any(p.colour == hair for p in e.particles) and not any(p.colour == fx.RED for p in e.particles)
    assert e.rings[0].colour != fx.CYAN


def test_impact_starts_with_its_first_frame_and_windows_are_ready_early():
    from capri.ui.impact import DEFAULT_IMPACT, Impacts
    imps = Impacts()
    imps.prewarm()
    spare = imps._spare
    assert spare is not None
    w = imps.spawn(QPointF(400, 300), QPointF(1, 0), DEFAULT_IMPACT, 250.0)
    assert w is spare and imps._spare is None                  # the ready-made window was used
    w.repaint()
    assert w._started and w.impact.alive(time.monotonic())     # its clock starts when it's first drawn
