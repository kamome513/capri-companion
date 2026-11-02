"""Stage 2 behaviour tests, run headless with Qt's offscreen platform.

    pip install pytest
    python -m pytest tests

Simulates two monitors (1920x1080 + 2560x1440) and uses Qt's test mode for
settings, so your real settings file is never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Two simulated monitors are configured in conftest.py (must happen before Qt starts).

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, QStandardPaths, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])
app.setApplicationName("CapriTest")

from capri.app import asset_root  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.settings import SavedPosition, Settings  # noqa: E402
from capri.states import State  # noqa: E402
from capri.ui.art import CharacterArt  # noqa: E402
from capri.ui.companion import CHARACTER_HEIGHT, SCREEN_MARGIN, Companion  # noqa: E402

ART = CharacterArt.load(asset_root() / "capri")


@pytest.fixture(autouse=True)
def clean_settings():
    Settings.path().unlink(missing_ok=True)
    yield
    Settings.path().unlink(missing_ok=True)


def make(settings: Settings | None = None) -> Companion:
    controller = CompanionController()
    controller.log("Boot", "overlay online")
    controller.set_state(State.IDLE, "Standing by.")
    companion = Companion(controller, ART, settings or Settings.load())
    companion.show()
    app.processEvents()
    return companion


def drag(window, delta: QPoint) -> None:
    start_local = QPointF(window.width() / 2, window.height() / 2)
    start = QPointF(window.mapToGlobal(start_local.toPoint()))

    def send(kind, local, glob, buttons):
        ev = QMouseEvent(kind, local, glob, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window, ev)

    send(QEvent.Type.MouseButtonPress, start_local, start, Qt.MouseButton.LeftButton)
    for i in range(1, 6):   # several moves, like a real drag
        step = QPointF(delta.x() * i / 5, delta.y() * i / 5)
        send(QEvent.Type.MouseMove, start_local + step, start + step, Qt.MouseButton.LeftButton)
    end = start + QPointF(delta)
    send(QEvent.Type.MouseButtonRelease, start_local + QPointF(delta), end, Qt.MouseButton.NoButton)
    app.processEvents()


def area(name: str):
    return next(s for s in QGuiApplication.screens() if s.name() == name).availableGeometry()


def assert_panel_on_capri(c: Companion) -> None:
    ch, panel = c.content_geometry(), c.panel.geometry()
    tail_tip_x = panel.x() + c.panel.tail_x
    assert abs(tail_tip_x - ch.center().x()) <= 1, "tail should point at Capri"
    if c.panel.tail_up:
        assert panel.top() >= ch.bottom() - 10
    else:
        assert panel.bottom() <= ch.top() + 10


def test_default_bottom_right_of_primary():
    c = make()
    a = QGuiApplication.primaryScreen().availableGeometry()
    ch = c.content_geometry()
    assert ch.right() == a.right() - SCREEN_MARGIN
    assert ch.bottom() == a.bottom() - SCREEN_MARGIN
    assert_panel_on_capri(c)
    assert not c.panel.tail_up


def test_drag_moves_both_and_saves_position():
    c = make()
    before_char, before_panel = c.character.pos(), c.panel.pos()
    drag(c.character, QPoint(-300, -200))
    assert c.character.pos() == before_char + QPoint(-300, -200)
    assert c.panel.pos() == before_panel + QPoint(-300, -200)
    saved = Settings.load().position
    assert saved == SavedPosition("DISPLAY1", SCREEN_MARGIN + 300, SCREEN_MARGIN + 200)


def test_dragging_the_panel_moves_capri_too():
    c = make()
    before = c.character.pos()
    drag(c.panel, QPoint(-120, -40))
    assert c.character.pos() == before + QPoint(-120, -40)
    assert_panel_on_capri(c)


def test_clamped_to_screen():
    c = make()
    drag(c.character, QPoint(0, 500))   # try to push her off the bottom of DISPLAY1
    a = area("DISPLAY1")
    assert c.screen.name() == "DISPLAY1"
    assert c.content_geometry().right() <= a.right()
    assert c.content_geometry().bottom() <= a.bottom()


def test_second_monitor_is_remembered():
    c = make()
    drag(c.character, QPoint(1200, -100))   # into DISPLAY2
    assert c.screen.name() == "DISPLAY2"
    saved = Settings.load().position
    assert saved.screen == "DISPLAY2"
    pos = c.character.pos()
    c2 = make()   # fresh start reads the saved settings
    assert c2.screen.name() == "DISPLAY2"
    assert c2.character.pos() == pos


def test_missing_monitor_falls_back_to_primary():
    c = make(Settings(position=SavedPosition("DISPLAY9", 50, 50)))
    assert c.screen is QGuiApplication.primaryScreen()
    assert c.content_geometry().bottom() == area("DISPLAY1").bottom() - 50


def test_panel_flips_below_near_top_of_screen():
    c = make()
    drag(c.character, QPoint(-200, -2000))
    assert c.content_geometry().top() == area("DISPLAY1").top()
    assert c.panel.tail_up
    assert_panel_on_capri(c)
    drag(c.character, QPoint(0, 600))
    assert not c.panel.tail_up
    assert_panel_on_capri(c)


def test_compact_mode_keeps_feet_in_place_and_persists():
    c = make()
    anchor = c.content_geometry().bottomRight()
    c.set_compact(True)
    app.processEvents()
    assert c.character.display_height == CHARACTER_HEIGHT[True]
    assert c.content_geometry().bottomRight() == anchor
    assert c.panel.panel_width < 300
    assert_panel_on_capri(c)
    assert Settings.load().compact is True
    c.set_compact(False)
    assert c.content_geometry().bottomRight() == anchor


def test_panel_and_hide_toggles():
    c = make()
    c.set_show_panel(False)
    assert c.character.isVisible() and not c.panel.isVisible()
    c.set_hidden(True)
    assert not c.character.isVisible() and not c.panel.isVisible()
    c.set_hidden(False)
    assert c.character.isVisible() and not c.panel.isVisible()
    c.set_show_panel(True)
    assert c.panel.isVisible()
    assert Settings.load().show_panel is True


def test_log_toggle_changes_panel_height():
    c = make()
    tall = c.panel.height()
    c.set_show_log(False)
    assert c.panel.height() < tall
    assert_panel_on_capri(c)


def test_always_on_top_and_click_through_flags():
    c = make()
    for w in (c.character, c.panel):
        assert w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    c.set_always_on_top(False)
    c.set_click_through(True)
    for w in (c.character, c.panel):
        assert not (w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        assert w.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert w.isVisible()   # flag changes must not leave her hidden
    s = Settings.load()
    assert s.always_on_top is False and s.click_through is True
    c2 = make()
    assert c2.character.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_corrupt_settings_file_uses_defaults():
    path = Settings.path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load() == Settings()


def test_menu_reflects_settings():
    from capri.ui.tray import CompanionMenu
    c = make(Settings(compact=True, show_log=True))
    menu = CompanionMenu(c, ART.icon)
    assert menu.a_compact.isChecked()
    assert not menu.a_log.isEnabled()     # compact never shows the log
    menu.a_compact.trigger()              # user clicks "Compact mode"
    assert c.settings.compact is False and menu.a_log.isEnabled()
    menu.a_hide.trigger()
    assert c.hidden and menu.a_hide.text() == "Show Capri"


def test_she_can_stand_right_against_the_screen_edge():
    c = make(Settings(position=SavedPosition("DISPLAY2", 0, 0)))
    a = area("DISPLAY2")
    body = c.content_geometry()
    assert body.right() == a.right() and body.bottom() == a.bottom()     # flush with the corner
    assert c.character.geometry().right() > a.right()                    # her hair margin hangs past it
    drag(c.character, QPoint(300, 0))                                     # pushing further right does nothing
    assert c.content_geometry().right() == a.right()
