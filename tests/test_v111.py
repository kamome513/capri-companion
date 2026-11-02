"""v1.11: her full-body figure, the panel sitting on her hair (and never floating alone), the
drone parked in a bottom corner, idle activities and dashes while she lies on the panel,
the dash right up to Discord's button, and Spotify's on-screen Play button fallback."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QStandardPaths, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402
from test_v18 import FakeSpotifyPC  # noqa: E402

from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations.screen_click import find_play_button  # noqa: E402
from capri.integrations.spotify_app import SpotifyApp  # noqa: E402
from capri.states import State  # noqa: E402
from capri.ui.rig import _to_array  # noqa: E402


def companion(**settings):
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    s = Settings()
    for k, v in settings.items():
        setattr(s, k, v)
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), s,
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    return c


def render(w) -> QImage:
    img = QImage(w.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    w.render(img, QPoint())
    return img


def opaque_rows(img: QImage, x0: int, x1: int) -> list[int]:
    return [y for y in range(img.height()) if any(img.pixelColor(x, y).alpha() > 40 for x in range(x0, x1, 2))]


# -- her full-body figure ---------------------------------------------------------------------------------
def test_standing_she_is_her_whole_body():
    from capri.ui.character_window import BODY_SCALE
    c = companion()
    w = c.character
    body = w.content_rect()
    assert body.height() - 2 == round(190 * BODY_SCALE)               # legs and all, a sensible size
    assert body.height() / body.width() > 2.8                          # her tall full-body figure
    rows = opaque_rows(render(w), body.left(), body.right())
    assert rows and rows[-1] >= body.bottom() - 4                      # her feet reach the ground


def test_she_blinks_and_talks_with_the_full_body():
    c = companion()
    w = c.character
    assert w.figure_pose("blink").blink == 1.0
    w.set_talking(True)
    w.set_voice_level(0.9)
    assert w.figure_pose().mouth > 0 and w.figure_pose().energy > 0.5
    still = render(w)
    w.set_voice_level(0.0)
    for _ in range(40):                                                # her mouth eases shut (v1.24)
        time.sleep(0.01)
        w.figure_pose()
    assert w.figure_pose().mouth == 0
    assert render(w) != still


def test_the_rig_scales_down_sharply():
    from capri.app import asset_root
    from capri.ui.rig import Pose, Rig
    full = Rig(QImage(str(asset_root() / "capri_v2" / "body" / "standing.png")))
    small = full.resized(250)
    assert small.h == 250 and abs(small.w / small.h - full.w / full.h) < 0.02
    img = QImage(200, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    small.paint(p, QPointF(100, 290), 250, Pose(blink=1.0, mouth=1.0))
    p.end()
    assert opaque_rows(img, 60, 140)


# -- the panel ------------------------------------------------------------------------------------------------
def test_the_panel_sits_right_on_her_hair():
    c = companion()
    c.controller.set_state(State.SUCCESS, "Opening Discord...")
    ch, panel = c.character, c.panel.geometry()
    top = ch.y() + ch.visual_top()
    tail_tip = panel.bottom() - 6                                       # minus the panel's glow
    assert 0 <= top - tail_tip <= 12


def test_the_panel_never_floats_over_nothing():
    c = companion()
    c.character.hide()                                                  # something left her hidden
    c.controller.set_state(State.SUCCESS, "Done.")
    assert c.character.isVisible()


def test_a_drawing_error_never_leaves_her_invisible(monkeypatch):
    c = companion()
    w = c.character
    monkeypatch.setattr(w, "_paint_body", lambda p: 1 / 0)
    assert opaque_rows(render(w), 0, w.width())                         # a plain picture of her instead


# -- the drone's corner --------------------------------------------------------------------------------------
@pytest.mark.parametrize("corner", ["left", "right"])
def test_the_drone_parks_in_a_bottom_corner(corner):
    c = companion()
    c.set_drone_corner(corner)
    c.set_drone(True)
    d, area = c.drone_window.geometry(), c.screen.availableGeometry()
    assert abs(d.bottom() - area.bottom()) <= 8
    if corner == "left":
        assert abs(d.left() - area.left()) <= 8
    else:
        assert abs(d.right() - area.right()) <= 8
    assert c.panel.geometry().bottom() <= d.top() + 20                   # her messages pop up above it


def test_moving_the_drone_by_voice():
    class C:
        corner = None

        def set_drone_corner(self, side):
            self.corner = side
    r = rig(FakeDesktop())
    r.router.companion = C()
    assert parse("move the drone to the left").kind is Kind.DRONE_CORNER
    r.service.command.emit("hey capri put the drone bottom left")
    assert r.router.companion.corner == "left"
    r.service.command.emit("drone right")
    assert r.router.companion.corner == "right" and r.controller.message == "Drone parked bottom right."


# -- lying on the panel ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["glitch", "gaming", "watching", "call"])
def test_idle_activities_while_lying_down(name):
    c = companion(lounge=True)
    w = c.character
    assert w.mode == "lying" and w.play_act(name)
    w.acts.start -= 2.0
    if name == "glitch":
        now = time.monotonic()
        w.acts._bursts = [(now - 1, now + 1)]
    with_act = render(w)
    w.acts.act = None
    assert with_act != render(w)


def test_she_gets_up_off_the_panel_to_dash():
    from capri.ui.visit import VisitShow
    c = companion(lounge=True)
    show = VisitShow(c)
    hits = []
    show.visit(QRect(300, 300, 32, 32), lambda: hits.append(1), near=True)
    assert show.active and not c.character.isVisible() and c.panel.isVisible()   # the panel stays put
    assert settle(2, lambda: hits)
    assert settle(3, lambda: not show.active)
    assert c.character.isVisible() and c.character.mode == "lying"             # back to lying down


def test_she_stands_right_beside_a_button():
    from capri.ui.visit import VisitShow
    c = companion()
    show = VisitShow(c)
    show.fh = 250
    button = QRect(200, 300, 32, 32)
    feet, side = show._spot(button, QRect(50, 100, 600, 400), near=True)
    assert abs(feet.x() - button.center().x()) < 250 * 0.6
    assert button.center().y() < feet.y() < button.center().y() + 250        # beside it, not on the window top


def test_dash_size_matches_her():
    c = companion()
    assert c.character.figure_height() == c.character.content_rect().height() - 2


# -- Spotify: the green Play button on screen ------------------------------------------------------------------
def spotify_page(scale=1.0, button=True):
    w, h = int(1000 * scale), int(700 * scale)
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(18, 18, 18))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(scale, scale)
    p.fillRect(QRectF(300, 40, 200, 200), QColor(30, 200, 90))                 # green album art
    p.setPen(Qt.PenStyle.NoPen)
    if button:
        p.setBrush(QColor(30, 215, 96))
        p.drawEllipse(QPointF(330, 300), 28, 28)
        p.setBrush(QColor(0, 0, 0))
        p.drawPolygon(QPolygonF([QPointF(322, 288), QPointF(322, 312), QPointF(342, 300)]))
    p.setBrush(QColor(30, 215, 96))
    p.drawEllipse(QPointF(400, 300), 9, 9)                                    # the liked heart
    p.drawEllipse(QPointF(500, 660), 20, 20)                                  # in the player bar
    p.end()
    return _to_array(img)[..., :3]


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_finds_the_green_play_button(scale):
    assert find_play_button(spotify_page(scale)) == (round(330 * scale), round(300 * scale))


def test_no_play_button_no_click():
    assert find_play_button(spotify_page(button=False)) is None
    assert find_play_button(np.zeros((300, 300, 3), np.uint8)) is None


def test_clicks_play_on_screen_when_nothing_else_worked():
    pc = FakeSpotifyPC(autoplay=False)
    clicks = []

    def click(pids):
        clicks.append(pids)
        pc.title = "NF - Let You Down"
        return True
    app = SpotifyApp(pc.open_item, lambda: [5], lambda pids: [pc.title], lambda pids, name: False,
                     pc.fetch_text, pc.fetch_json, click_play=click, sleep=lambda s: None)
    result = app.play("let you down", "nf")
    assert clicks == [[5]] and result.status == "playing"


def test_an_ad_first_still_counts_as_playing():
    pc = FakeSpotifyPC(autoplay=False)

    def opened(target):
        pc.open_item(target)
        if target.startswith("spotify:track:"):
            pc.title = "Advertisement"                                      # Spotify Free
    app = SpotifyApp(opened, lambda: [5], lambda pids: [pc.title], None, pc.fetch_text, pc.fetch_json,
                     sleep=lambda s: None)
    result = app.play("let you down", "nf")
    assert result.status == "playing" and result.title == "Let You Down"


# -- D on the video call ---------------------------------------------------------------------------------------
def test_the_video_call_shows_d():
    from capri.app import asset_root
    c = companion()
    w = c.character
    picture = asset_root() / "d" / "d.png"
    assert picture.is_file()
    assert w.play_act("call")
    w.acts.start -= 3.0                                                 # past the ringing
    w.acts.contact = None
    generic = render(w)                                                 # no picture: a simple avatar
    w.acts.contact = QImage(str(picture))
    with_d = render(w)
    assert with_d != generic
    # his blue jacket is on the card, to the left of her head
    blue = sum(1 for x in range(0, w.width() // 2, 2) for y in range(0, w.height() // 2, 2)
               if (lambda q: q.blue() > 150 and q.red() < 120 and q.alpha() > 200)(with_d.pixelColor(x, y)))
    assert blue > 20


def test_d_talks_blinks_and_moves():
    from capri.app import asset_root
    from capri.ui.contact import Puppet
    pup = Puppet(QImage(str(asset_root() / "d" / "d.png")))
    pup._next_blink = 1e9

    def frame(now, mouth, speaking, blink=False):
        pup._blink_at = now - 0.05 if blink else -10
        img = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        pup.paint(p, QRectF(0, 0, 200, 200), now, mouth, speaking)
        p.end()
        return img
    closed = frame(10.0, 0.0, True)
    assert frame(10.0, 1.0, True) != closed                             # his mouth opens
    assert frame(10.0, 0.0, True, blink=True) != closed                 # he blinks
    assert frame(10.4, 0.0, True) != closed                             # his head moves as he talks
    assert frame(31.0, 0.0, False) != frame(33.0, 0.0, False)           # and while he listens


# -- 1.11.2: the other monitor, up to the minimise button, voice "play" like Test Spotify ----------------------------
def test_she_lands_on_the_targets_monitor(monkeypatch):
    from capri.ui import visit
    other = QRect(800, 0, 800, 600)

    class Screen:
        def availableGeometry(self):
            return other
    monkeypatch.setattr(visit, "_screen_for", lambda rect: Screen())
    c = companion()
    show = visit.VisitShow(c)
    show.fh = 250
    button = QRect(1430, 4, 46, 30)                                    # a maximised window's minimise button
    feet, side = show._spot(button, QRect(800, 0, 800, 560), near=True)
    assert other.left() < feet.x() < other.right()                      # on that monitor, not clamped to hers
    assert feet.y() <= 260 and side == "right"                          # up at the top, pointing at it


def test_minimise_flies_up_beside_the_button():
    from capri.ui.visit_actions import VisitActions

    class Visit:
        calls = []

        def visit(self, target, then, window=None, near=False):
            self.calls.append(near)
            then()

    class Desktop:
        def main_window(self, pids):
            return 5

        def hwnd_rect(self, hwnd):
            return (0, 0, 800, 560)

    class UI:
        def buttons(self, hwnd, names, control=None, with_rects=False):
            return [type("B", (), {"rect": (640, 0, 686, 30), "name": "Minimize"})()]
    done = []
    v = Visit()
    VisitActions(v, Desktop(), UI(), lambda t: None).minimize("Discord", [1], lambda: done.append(1))
    assert settle(2, lambda: done) and v.calls == [True]


def test_voice_play_uses_the_same_steps_as_test_spotify():
    from capri.integrations.spotify_app import Played
    from test_stage5 import FakeSpotify
    calls = []

    class App:
        def play(self, query, artist=""):
            calls.append((query, artist))
            return Played("playing", "otuka - skin")
    spotify = FakeSpotify()
    spotify.connected = True                                            # Premium, connected
    r = rig(FakeDesktop(), spotify=spotify, spotify_app=App())
    r.service.command.emit("play skin by otuka")
    assert settle(2, lambda: calls) and calls == [("skin", "otuka")]
    assert settle(2, lambda: r.controller.message == "Playing otuka - skin.")


# -- 1.11.3: "go into drone mode", even when it's heard as "drive mode" -------------------------------------------
@pytest.mark.parametrize("text", ["go into drone mode", "hey capri go into drone mode", "go into drive mode",
                                  "go in to drone mode", "switch to drive mode", "drive mode", "enter droid mode",
                                  "go into the drone mode", "activate drone mode", "go into game mode"])
def test_drone_mode_however_it_is_heard(text):
    assert parse(text).kind is Kind.DRONE_ON


@pytest.mark.parametrize("text", ["exit drive mode", "get out of drone mode", "leave drone mode", "back to normal"])
def test_leaving_drone_mode(text):
    assert parse(text).kind is Kind.DRONE_OFF


@pytest.mark.parametrize("text", ["drive to the shop", "start game", "open drive"])
def test_drive_alone_is_not_drone(text):
    assert parse(text).kind is not Kind.DRONE_ON


def test_go_into_drone_mode_does_not_minimise_anything():
    d = FakeDesktop()
    drones = []

    class C:
        def set_drone(self, on):
            drones.append(on)
    r = rig(d)
    r.router.companion = C()
    r.service.command.emit("hey capri go into drive mode")
    assert drones == [True] and d.calls == []


def test_the_ai_knows_drone_mode():
    from capri.ai.claude import to_intent
    assert to_intent("set_display", {"option": "drone_on"}).kind is Kind.DRONE_ON
    assert to_intent("set_display", {"option": "drone_off"}).kind is Kind.DRONE_OFF


# -- 1.11.4: typing isn't talking ------------------------------------------------------------------------------
class Keys:
    """A fake PC: typing bumps the last-input time while the mouse stays still."""

    def __init__(self):
        self.tick, self.mouse, self.now = 0, (100, 100), 1000.0

    def type(self):
        self.tick += 1

    def move_mouse(self):
        self.tick += 1
        self.mouse = (self.mouse[0] + 5, self.mouse[1])


def typing_rig(keys, **services):
    from capri.typing_watch import TypingWatch
    r = rig(FakeDesktop(), **services)
    r.assistant.typing = TypingWatch(lambda: keys.tick, lambda: keys.mouse)
    return r


def test_typing_is_spotted_but_moving_the_mouse_is_not():
    from capri.typing_watch import TypingWatch
    keys = Keys()
    watch = TypingWatch(lambda: keys.tick, lambda: keys.mouse)
    watch.start()
    keys.move_mouse()
    watch.sample()
    assert not watch.typed_within(5)
    keys.type()
    watch.sample()
    assert watch.typed_within(5)
    watch.stop()


def test_search_mode_ignores_your_keyboard_and_switches_off():
    keys = Keys()
    r = typing_rig(keys)
    r.service.command.emit("search mode")
    keys.type()                                             # you start typing in your browser...
    r.service.command.emit("the")                           # ...and the mic "hears" your keyboard
    assert not [c for c in r.system.calls if c[0] == "open"]   # nothing opened in your browser
    assert r.controller.message == "You're typing - search mode off."


def test_a_follow_up_heard_while_typing_is_ignored():
    keys = Keys()
    r = typing_rig(keys)
    r.assistant._follow_up = True
    r.assistant._listen_without_wake()
    keys.type()
    calls = len(r.system.calls)
    r.service.command.emit("open discord")
    assert len(r.system.calls) == calls and not r.assistant._follow_up


def test_hey_capri_still_works_while_typing():
    keys = Keys()
    r = typing_rig(keys)
    keys.type()
    r.service.command.emit("open discord")                  # after the wake word: always for her
    assert r.system.calls and r.system.calls[0][0] == "program"


def test_search_mode_skips_junk_words():
    r = rig(FakeDesktop())
    r.service.command.emit("search mode")
    r.service.command.emit("uh")
    assert not [c for c in r.system.calls if c[0] == "open"]
    assert r.speaker.lines[-1].startswith("Still there?")
    r.service.command.emit("funny cats")
    assert r.system.calls[-1] == ("open", "https://www.google.com/search?q=funny+cats")
