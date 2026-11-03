"""v1.16: a solid green visor, the activity feed as holocall cards, a cyberdeck settings window,
the menu in folders, sitting on windows, "switch tabs on opera" and "play the video"."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QRect, QStandardPaths  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.app import asset_root  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.integrations.browser_tabs import PLAYER, Tab, is_playing, pick_tab, short  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.ui import looks  # noqa: E402
from capri.ui.art import CharacterArt  # noqa: E402
from capri.ui.companion import Companion  # noqa: E402
from capri.ui.sprites import SpriteArt  # noqa: E402


def companion(**kw) -> Companion:
    s = Settings(**kw)
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), s,
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    app.processEvents()
    return c


# -- the green visor drone -------------------------------------------------------------------------------
def test_green_shows_where_the_fin_sways_and_the_visor_is_unchanged():
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainter
    from capri.ui.drone import MASK_FILE, MaskDrone

    def render(d, t, energy):
        img = QImage(300, 300, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        d._last_t = t
        d.paint(p, QPointF(150, 150), 280, t, energy)
        p.end()
        return looks.to_array(img)[..., 3] > 128
    d = MaskDrone()
    joint = looks.to_array(d.joint)
    assert (joint[..., 3] > 0).any() and (joint[joint[..., 3] > 0][:, 1] > 200).all()     # plain green
    rest = render(d, 0.0, 0.0)
    y = int(10 + d.fin_top * 280 / d.h)
    for t in np.linspace(0, 3, 30):                 # swaying hard (talking): nothing opens at its base
        assert (rest & ~render(d, t, 1.0))[y - 8:y + 6].sum() <= 10
    # the visor itself is the picture as it was: her layers at rest add up to it
    original = looks.to_array(looks.analyse("mask", QImage(str(MASK_FILE))).image)[..., 3] > 128
    layers = sum((looks.to_array(i)[..., 3] > 128).astype(int) for i in (d.fin, d.visor, d.mouth) + tuple(d.irises))
    assert ((layers > 0) == original)[d.top:d.bottom].mean() > 0.995


def test_hair_storm_look_is_gone_and_a_saved_choice_falls_back():
    from capri.ui.character_window import CharacterWindow
    assert "Hair Storm" not in looks.available()
    w = CharacterWindow(CharacterArt.load(asset_root() / "capri"), 190, True, SpriteArt.load(asset_root() / "capri_v2"),
                        "look:Hair Storm")
    assert w.mode != "look"


def test_lying_hair_has_no_edge_line_where_it_meets_her():
    from capri.ui.hair import STORM_EDGE, StormHair
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter

    def edge_rows(hair):
        img = QImage(400, 400, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        head = QRectF(150, 150, 100, 100)
        hair.paint(p, head, 1.0, 1.0)
        p.end()
        a = looks.to_array(img)
        purple = (abs(a[..., 0].astype(int) - STORM_EDGE.red()) < 8) & (abs(a[..., 2].astype(int) - STORM_EDGE.blue()) < 8)
        return purple[int(head.top() + head.height() * 0.2):].sum()   # below her hairline
    assert edge_rows(StormHair()) == 0                     # v1.28: flat pink like the show, no purple outline
    assert edge_rows(StormHair(flow_in=True)) == 0         # lying down: it flows into her, no line
    assert StormHair(flow_in=True).points == StormHair().points       # same hair shape


def test_lying_hair_has_no_gaps_down_to_her_head():
    from capri.ui.hair import StormHair
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter
    head = QRectF(150, 150, 100, 100)
    for t in np.linspace(0, 3, 12):                       # every boil step
        img = QImage(400, 400, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        StormHair(flow_in=True).paint(p, head, float(t), 1.0)
        p.end()
        a = looks.to_array(img)[..., 3]
        band = a[int(head.top()):int(head.top() + head.height() * 0.7), int(head.left()) + 5:int(head.right()) - 5]
        assert (band > 200).all()                         # solid hair from the mass down onto her head
    assert all(-10 < s[0] < 190 for s in StormHair(flow_in=True).shards)   # nothing hanging down into her


def test_card_pictures_keep_their_teeth():
    assert looks.load("Grin").mouth is not None


# -- the activity feed ----------------------------------------------------------------------------------
def test_the_log_is_in_the_panel_by_default():
    c = companion()
    c.controller.log("Heard", "open discord")
    app.processEvents()
    assert c.settings.log_style == "panel" and c.panel.show_log and not c.feed.isVisible()


def test_the_log_can_be_holocall_cards_above_the_panel():
    c = companion(log_style="cards")
    for verb, detail in (("Wake", "hey capri"), ("Heard", '"open this cord" -> "open discord"'), ("Launch", "Discord")):
        c.controller.log(verb, detail)
    c.feed.add_reply("Launching Discord.")
    app.processEvents()
    # 1.19: a call - what she understood you said, then her reply (log lines like "Launch" aren't cards)
    assert c.controller.total == 3
    assert [(x["who"], x["text"]) for x in c.feed.cards] == [("you", "open discord"), ("capri", "Launching Discord.")]
    assert c.feed.isVisible() and not c.panel.show_log
    assert c.feed.geometry().bottom() <= c.panel.geometry().top() + 20    # right on top of the panel
    c.set_show_log(False)
    assert not c.feed.isVisible()


def test_cards_fade_out():
    from capri.ui import feed
    now = [100.0]
    c = companion()
    f = feed.FeedWindow(c.controller, clock=lambda: now[0])
    c.controller.log("Heard", "hi")
    assert len(f.cards) == 1 and f.isVisible()
    now[0] += feed.LIFE + 1
    f._tick()
    assert f.cards == [] and not f.isVisible()


# -- the menu in folders ------------------------------------------------------------------------------------
def test_the_menu_is_sorted_into_folders():
    from PySide6.QtWidgets import QMenu

    from capri.ui.tray import CompanionMenu
    c = companion()
    menu = CompanionMenu(c, QImage(8, 8, QImage.Format.Format_ARGB32))
    # (not QAction.menu(): on PySide 6.8 the menu it returns gets deleted when Python lets go of it)
    subs = {m.menuAction(): m.title() for m in menu.menu.findChildren(QMenu)}
    folders = [subs[a] for a in menu.menu.actions() if a in subs]
    assert folders == ["Size", "Capri", "Panel", "Drone", "Window"]
    menu.log_styles["cards"].trigger()
    assert c.settings.log_style == "cards" and not c.panel.show_log
    menu.log_styles["panel"].trigger()
    assert c.settings.log_style == "panel" and c.panel.show_log
    menu._fill_designs()
    designs = [a.text() for a in menu.design_menu.actions()]
    assert "Look: Grin" in designs and not any("Spikes" in d for d in designs)
    menu.a_perch.trigger()
    assert c.settings.perch_windows and c.window_perch.enabled
    menu.a_perch.trigger()
    assert not c.settings.perch_windows and not c.window_perch.enabled


# -- sitting on windows -------------------------------------------------------------------------------------
def window_rect():
    a = QGuiApplication.primaryScreen().availableGeometry()
    return QRect(a.left() + 100, a.top() + 360, 500, 300)


def test_she_sits_on_the_window_and_the_panel_stays_home():
    c = companion()
    home_panel = c.panel.geometry()
    win = window_rect()
    assert c.perch_on(win)
    app.processEvents()
    sit = c.sit_window
    seat = sit.pos() + sit.seat_point()
    assert abs(seat.y() - win.top()) <= 6 and win.left() < seat.x() < win.right()
    assert sit.isVisible() and not c.character.isVisible()
    assert c.panel.geometry().bottom() == home_panel.bottom() and c.panel.x() == home_panel.x()
    c.leave_perch()
    assert c.character.isVisible() and not sit.isVisible()
    assert c.panel.geometry() == home_panel


def test_no_room_above_the_window_no_sitting():
    c = companion()
    a = QGuiApplication.primaryScreen().availableGeometry()
    assert not c.perch_on(QRect(a.left() + 50, a.top() + 5, 400, 300))
    assert not c.perched


def test_get_up_takes_her_off_the_window():
    c = companion()
    c.perch_on(window_rect())
    c.reset_position()
    assert not c.perched and c.character.isVisible() and not c.sit_window.isVisible()


def test_both_legs_swing_without_coming_apart():
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainter
    from capri.ui.perch import ART, SitWindow
    sit = SitWindow()
    poses = [sit.pose(t) for t in np.linspace(0, 2, 40)]
    black, red = [p[0] for p in poses], [p[1] for p in poses]
    assert max(black) > 8 and min(black) < -8 and max(red) > 2 and min(red) < -2    # both swing
    assert black.index(max(black)) != red.index(max(red))                          # out of step

    def layer(name):
        return looks.to_array(QImage(str(ART / f"{name}.png")))
    base = layer("base")
    for name in ("black", "red"):
        leg = layer(name)
        knee = sit.knees[name]
        ys = np.flatnonzero((leg[..., 3] > 128).any(1))
        assert ys.min() < knee.y() + 40 < ys.max()            # the leg reaches up to its knee...
        top = (leg[..., 3] > 128) & (np.arange(leg.shape[0])[:, None] < ys.min() + 30)
        assert (base[top, 3] > 128).mean() > 0.9              # ...and the body keeps the shin's top too
    # high quality: her picture at full size, smooth edges (partly see-through outline pixels)
    assert base.shape[0] >= 700 and ((base[..., 3] > 0) & (base[..., 3] < 255)).any()

    def coverage(angles):
        img = QImage(sit.art_w, sit.art_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.drawImage(0, 0, QImage(str(ART / "base.png")))
        for name, a in zip(("black", "red"), angles):
            k = sit.knees[name]
            p.save()
            p.translate(k)
            p.rotate(a)
            p.translate(-k)
            p.drawImage(0, 0, QImage(str(ART / f"{name}.png")))
            p.restore()
        p.end()
        return looks.to_array(img)[..., 3] > 128
    def holes(mask):                                          # see-through spots inside her
        edge = np.zeros_like(mask)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        return ~mask & ~looks.flood(edge, ~mask, limit=8000)
    rest = holes(coverage((0, 0)))
    for angles in ((10, -3), (-10, 3), (10, 3), (-10, -3)):   # swinging: no new gaps open up in her
        now = holes(coverage(angles))
        fresh = now & ~looks.flood(now & rest, now, limit=8000)   # (the sky between her legs may widen)
        assert fresh.sum() <= 30, (angles, fresh.sum())
    sit.show()
    app.processEvents()
    assert not sit.grab().isNull()


class Fronts:
    def __init__(self):
        self.front, self.rects = None, {}

    def get_front(self):
        return (self.front, self.rects[self.front]) if self.front in self.rects else None

    def rect_of(self, hwnd):
        return self.rects.get(hwnd)


def perch_rig():
    from capri.ui.perch import WindowPerch
    c = companion(perch_windows=False)
    f = Fronts()
    p = WindowPerch(c, f.get_front, f.rect_of)
    p.set_enabled(True)
    return c, f, p


def test_turning_it_on_sends_her_straight_to_your_window():
    from capri.ui.perch import WindowPerch
    c = companion(perch_windows=False)
    win = window_rect()
    p = WindowPerch(c, lambda: None, lambda hwnd: win, top=lambda: (7, win))
    p.set_enabled(True)                          # no waiting for the window to "settle"
    assert c.perched and p.hwnd == 7 and p._follow.isActive()


def test_she_keeps_up_when_you_drag_the_window():
    from capri.ui.perch import FOLLOW_EVERY, WindowPerch
    assert FOLLOW_EVERY <= 20                    # a position lookup every frame while she sits
    c = companion(perch_windows=False)
    rects = {7: window_rect()}
    p = WindowPerch(c, lambda: None, rects.get, top=lambda: (7, rects[7]))
    p.set_enabled(True)
    start = c.sit_window.pos()
    for step in range(1, 6):                     # dragged 10 px a frame
        rects[7] = window_rect().translated(10 * step, 0)
        p.follow()
        assert c.sit_window.pos() == start + QPoint(10 * step, 0)
    del rects[7]                                 # closed
    p.follow()
    assert not c.perched and not p._follow.isActive()


def test_she_hops_on_the_window_youre_using_and_home_when_it_closes():
    from capri.ui.perch import SETTLE_LOOKS
    c, f, p = perch_rig()
    f.rects[1] = window_rect()
    f.front = 1
    for _ in range(SETTLE_LOOKS):
        p.tick()
    assert c.perched and p.hwnd == 1
    moved = window_rect().translated(40, 20)
    f.rects[1] = moved                          # you drag the window: she rides along
    p.tick()
    assert c.perch_rect == moved
    del f.rects[1]                              # closed (or minimised)
    f.front = None
    p.tick()
    assert not c.perched and c.character.isVisible()


def test_dragging_her_off_keeps_her_off_that_window():
    from capri.ui.perch import SETTLE_LOOKS
    c, f, p = perch_rig()
    f.rects[1] = window_rect()
    f.front = 1
    for _ in range(SETTLE_LOOKS):
        p.tick()
    c.sit_window.drag_started.emit()
    c.sit_window.drag_moved.emit(QPoint(-60, 120))
    c.sit_window.drag_finished.emit()
    assert not c.perched and c.character.isVisible()
    for _ in range(SETTLE_LOOKS + 1):
        p.tick()
    assert not c.perched                         # not straight back on
    f.rects[2] = window_rect().translated(30, 0)
    f.front = 2                                  # another window: she'll sit on that
    for _ in range(SETTLE_LOOKS):
        p.tick()
    assert c.perched and p.hwnd == 2


def test_drone_mode_takes_her_off_the_window():
    c, f, p = perch_rig()
    c.perch_on(window_rect())
    c.set_drone(True)
    assert not c.perched and not c.sit_window.isVisible()
    c.set_drone(False)


# -- the cyberdeck ------------------------------------------------------------------------------------------
def test_settings_is_a_cyberdeck_with_real_readouts():
    from capri.ui.settings_window import SettingsWindow
    r = rig(FakeDesktop())
    s = Settings(voice_enabled=False, mic_muted=True)
    win = SettingsWindow(r.router, s, QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [])
    assert win.tabs.tabText(0) == "01 // APPS" and win.tabs.tabText(2) == "03 // WAKE WORD"
    chips = dict(win._chips())
    assert "VOICE OFF" in chips and chips["VOICE OFF"] is False and "MIC MUTED" in chips
    assert any(k.startswith("APPS ") for k in chips)


# -- switch tabs -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, browser, name", [
    ("switch tabs on opera", "opera", ""), ("hey capri switch tabs on opera gx", "opera", ""), ("switch tab", "", ""),
    ("change tabs in chrome", "chrome", ""), ("switch to the twitch tab", "", "twitch"),
    ("go to the youtube tab in chrome", "chrome", "youtube"), ("switch tabs to twitch", "", "twitch"),
])
def test_tab_commands(text, browser, name):
    intent = parse(text)
    assert intent.kind is Kind.TAB and intent.targets == ((browser,) if browser else ()) and intent.query == name


TABS = [Tab("Inbox (3) - Gmail", (0, 0, 200, 30), "gmail"), Tab("xQc - Twitch", (200, 0, 400, 30), "twitch"),
        Tab("lofi hip hop radio - YouTube", (400, 0, 600, 30), "youtube")]


@pytest.mark.parametrize("said, want", [("twitch one", "twitch"), ("the twitch one", "twitch"), ("youtube", "youtube"),
                                         ("the second one", "twitch"), ("last one", "youtube"), ("gmail", "gmail"),
                                         ("reddit", None)])
def test_picking_the_tab_you_mean(said, want):
    tab = pick_tab(said, TABS)
    assert (tab.element if tab else None) == want


def test_how_she_says_tabs():
    assert short("xQc - Twitch") == "Twitch" and short("Inbox (3) - Gmail") == "Gmail"


class FakeTabs:
    def __init__(self, tabs=TABS, player=None, window=5):
        self._tabs, self._player, self._window = list(tabs), player, window

    def window(self, browser=""):
        return self._window

    def front(self):
        return self._window

    def tabs(self, hwnd):
        return self._tabs

    def player_button(self, hwnd):
        return self._player


def tab_rig(**kw):
    zaps, clicks = [], []
    media_key = kw.pop("media_key", None)
    d = FakeDesktop()
    d.bring_to_front = lambda hwnd: True
    r = rig(d, tabs=FakeTabs(**kw), click_at=clicks.append, zap_rect=lambda rect, then: (zaps.append(rect), then()),
            media_key=media_key)
    return r, zaps, clicks


def test_switch_tabs_asks_which_then_zaps_it():
    r, zaps, clicks = tab_rig()
    r.service.command.emit("switch tabs on opera")
    assert settle(2, lambda: r.speaker.lines and "Which tab?" in r.speaker.lines[-1])
    assert "Twitch" in r.speaker.lines[-1] and "YouTube" in r.speaker.lines[-1]
    r.service.command.emit("twitch one")
    assert settle(2, lambda: clicks)
    assert zaps == [(200, 0, 400, 30)] and clicks[0].element == "twitch"
    assert settle(2, lambda: r.controller.message == "Switched to Twitch.")


def test_switch_to_a_named_tab_goes_straight_there():
    r, zaps, clicks = tab_rig()
    r.service.command.emit("switch to the youtube tab")
    assert settle(2, lambda: clicks)
    assert clicks[0].element == "youtube" and not any("Which tab" in line for line in r.speaker.lines)


def test_no_browser_open():
    r, zaps, clicks = tab_rig(window=None)
    r.service.command.emit("switch tabs on opera")
    assert settle(2, lambda: r.controller.message == "I can't find Opera GX open.")


# -- play the video ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, action", [("play the video", "play"), ("pause the video", "pause"),
                                          ("resume the stream", "play"), ("stop the video", "pause")])
def test_video_commands(text, action):
    intent = parse(text)
    assert intent.kind is Kind.VIDEO and intent.query == action


def test_music_commands_stay_music():
    assert parse("play").kind is Kind.MEDIA and parse("pause").kind is Kind.MEDIA
    assert parse("play deadlock").kind is Kind.PLAY


@pytest.mark.parametrize("name, ok", [("Play (k)", True), ("Pause (space/k)", True), ("Playlist", False),
                                      ("Play all", False), ("Play next", False)])
def test_player_buttons(name, ok):
    assert bool(PLAYER.match(name)) is ok


def test_play_the_video_presses_play():
    button = Tab("Play (k)", (300, 600, 340, 640), "play")
    r, zaps, clicks = tab_rig(player=button)
    r.service.command.emit("play the video")
    assert settle(2, lambda: clicks)
    assert zaps == [(300, 600, 340, 640)] and clicks[0].element == "play"
    assert settle(2, lambda: r.controller.message == "Playing.")


def test_already_playing_is_left_alone():
    button = Tab("Pause (k)", (300, 600, 340, 640), "pause")
    assert is_playing(button)
    r, zaps, clicks = tab_rig(player=button)
    r.service.command.emit("play the video")
    assert settle(2, lambda: r.controller.message == "It's already playing.")
    assert clicks == [] and zaps == []
    r.service.command.emit("pause the video")
    assert settle(2, lambda: clicks)


def test_no_player_button_uses_the_media_key_and_says_so():
    keys = []
    r, zaps, clicks = tab_rig(player=None, media_key=keys.append)
    r.service.command.emit("play the video")
    assert settle(2, lambda: keys == ["play_pause"])
    assert "media key" in r.controller.message and clicks == []
