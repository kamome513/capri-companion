"""Ties the character window and the status panel together as one companion."""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QScreen

from .. import emotions
from ..controller import CompanionController
from ..settings import SavedPosition, Settings
from ..states import State
from .art import CharacterArt
from .character_window import CharacterWindow
from .drone import DroneWindow
from .feed import FeedWindow
from .perch import SINK, SitWindow, WindowPerch
from .sprites import SpriteArt
from .status_panel import GLOW as PANEL_GLOW
from .status_panel import StatusPanel

SCREEN_MARGIN = 2    # default gap between Capri and the screen edge / taskbar: the very corner
PANEL_GAP = 2        # gap between the panel's tail tip and Capri
TAIL_AT = 0.78       # preferred tail position across the panel width
CHARACTER_HEIGHT = {False: 190, True: 105}   # normal / compact (at size 100%)
SIZES = ((60, "Tiny"), (80, "Small"), (100, "Normal"), (125, "Big"), (150, "Bigger"), (200, "Huge"))


def her_height(compact: bool, size: int) -> int:
    """Her height: her Size only (compact mode makes her text box smaller, not her - v2.3.2)."""
    return max(40, round(CHARACTER_HEIGHT[False] * max(50, min(200, int(size or 100))) / 100))


def box_scale(size: int) -> float:
    """How much her text box grows / shrinks with her size (a bit less than she does, so it stays readable)."""
    return max(0.75, min(1.5, (max(50, min(200, int(size or 100))) / 100) ** 0.75))
LOUNGE_OVERLAP = 7   # px of Capri's body resting over the panel's top edge when lying on it


class Companion(QObject):
    context_menu_requested = Signal(QPoint)
    settings_changed = Signal()
    patted = Signal(str)                  # "head" (a head pat) / "body" (a poke): click her
    drone_changed = Signal(bool)          # game mode on / off (the app frees memory for your game)
    perch_dropped = Signal()              # you dragged her off the window she was sitting on

    def __init__(self, controller: CompanionController, art: CharacterArt, settings: Settings,
                 sprites: SpriteArt | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.settings = settings
        self.art = art
        self.sprites = sprites
        self.hidden = False   # "Hide Capri" is temporary, never saved
        self.drone = False    # game mode: she's a little flying disk (never saved)
        self.busy_elsewhere = False   # a show (dash, greeting) has her out of her window for a moment
        self.on_throw: Callable[[QPointF], bool] | None = None   # a flick-and-let-go: fling.ThrowShow
        self._popup_until = 0.0                    # popup text box: shown until then
        self._popup_message = ""
        self._called = False                       # "only when you say her name": you're talking to her right now
        self._panel_fading = False
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.timeout.connect(lambda: None if self.drone else self._apply_visibility())
        self._lying_raised = False
        self.perch_rect: QRect | None = None  # the window she's sitting on ("Sit on windows")
        self.platform = 0                     # px she stands up on her music deck (0: on the floor)
        self.moved: list = []                 # called after she's moved (the music deck follows her feet)
        self._panel_home = QPoint()
        self.talking = False
        self.viseme = ""

        top = settings.always_on_top
        self.panel = StatusPanel(controller, art.icon, top)
        self.panel.set_compact(settings.compact, box_scale(settings.size))
        self.panel.set_show_log(settings.show_log and settings.log_style != "cards")
        self.panel.set_static(settings.panel_static)
        self.character = CharacterWindow(art, her_height(settings.compact, settings.size), top, sprites,
                                         settings.character_style)
        self.character.set_look(settings.wild_hair, settings.idle_animation, settings.hair_style)
        self.character.acts.enabled = settings.idle_acts
        self.character.set_lying(settings.lounge, self._lying_width())
        self._update_face()
        self.screen: QScreen = QGuiApplication.primaryScreen()
        self.screen.availableGeometryChanged.connect(self._on_area_changed)
        self._drag_origin = QPoint()

        self.drone_window = DroneWindow(top)
        self.drone_window.set_style(settings.drone_look)
        self.sit_window = SitWindow(top, False, size=settings.size)
        self.feed = FeedWindow(controller, top, colours=self._call_colours)   # the chat skin's colours
        self.feed.resized.connect(self._place_feed)
        controller.changed.connect(self._on_changed)
        for window in (self.character, self.panel, self.drone_window, self.sit_window):
            window.context_menu_requested.connect(self.context_menu_requested)
            window.set_click_through(settings.click_through)
        self.character.clicked.connect(self._clicked)
        self._last_pat = -1e9
        for window in (self.character, self.panel):
            window.drag_started.connect(self._drag_start)
            window.drag_moved.connect(self._drag_move)
            window.drag_finished.connect(self._drag_end)
        # the drone is dragged on its own, anywhere; it stays where you leave it
        self.drone_window.drag_started.connect(lambda: setattr(self, "_drone_origin", self.drone_window.pos()))
        self.drone_window.drag_moved.connect(self._drone_drag)
        self.drone_window.drag_finished.connect(self._drone_dropped)
        # dragging her while she sits on a window lifts her off it: she stays where you drop her
        self.sit_window.drag_started.connect(lambda: setattr(self, "_sit_origin", self.sit_window.pos()))
        self.sit_window.drag_moved.connect(lambda d: self.sit_window.move(getattr(self, "_sit_origin") + d))
        self.sit_window.drag_finished.connect(self._sit_dropped)

        # Monitor plugged in / unplugged: re-place once Qt has settled. If her saved
        # monitor is missing she goes to the primary one, and returns when it's back.
        app = QGuiApplication.instance()
        for sig in (app.screenAdded, app.screenRemoved, app.primaryScreenChanged):
            sig.connect(lambda _s: QTimer.singleShot(0, self.place))
        self.window_perch = WindowPerch(self)          # "Sit on windows" (off unless you turn it on)

    # -- screens ----------------------------------------------------------------
    def _set_screen(self, screen: QScreen) -> None:
        if screen is self.screen:
            return
        try:
            self.screen.availableGeometryChanged.disconnect(self._on_area_changed)
        except (RuntimeError, TypeError):
            pass   # previous screen already gone (monitor unplugged)
        self.screen = screen
        screen.availableGeometryChanged.connect(self._on_area_changed)

    def _on_area_changed(self, _geom: QRect) -> None:
        # Resolution, scaling or taskbar changed: keep the same corner offset.
        self.place()

    @staticmethod
    def _screen_named(name: str) -> QScreen | None:
        return next((s for s in QGuiApplication.screens() if s.name() == name), None)

    @staticmethod
    def _screen_for(rect: QRect) -> QScreen:
        screen = QGuiApplication.screenAt(rect.center())
        if screen is not None:
            return screen
        # Centre is off every screen (e.g. dragged into a gap): use the nearest one.
        def distance(s: QScreen) -> int:
            return (s.availableGeometry().center() - rect.center()).manhattanLength()
        return min(QGuiApplication.screens(), key=distance)

    # -- placement ----------------------------------------------------------------
    def place(self) -> None:
        """Put Capri at her saved spot (or the default bottom-right corner)."""
        saved = self.settings.position
        screen = (saved and self._screen_named(saved.screen)) or QGuiApplication.primaryScreen()
        right, bottom = (saved.right, saved.bottom) if saved else (SCREEN_MARGIN, SCREEN_MARGIN)
        area = screen.availableGeometry()
        c = self.character.content_rect()
        # the offsets are from the screen's corner to *her* (not to her window's transparent margin)
        target = QPoint(area.right() + 1 - right - (c.x() + c.width()),
                        area.bottom() + 1 - bottom - (c.y() + c.height()))
        self._move_character(target, screen)

    def content_geometry(self) -> QRect:
        """Her visible body in screen coordinates."""
        if self.perched:
            return self.sit_window.content_rect().translated(self.sit_window.pos())
        return self.character.content_rect().translated(self.character.pos())

    def _move_character(self, target: QPoint, screen: QScreen | None = None) -> None:
        ch = self.character
        c = ch.content_rect()
        screen = screen or self._screen_for(c.translated(target))
        self._set_screen(screen)
        area = screen.availableGeometry()
        # Keep *her* on screen; her window's transparent hair/glow margin may hang off the edge,
        # so she can stand right against the side of the screen.
        x = max(area.left() - c.x(), min(target.x(), area.right() + 1 - (c.x() + c.width())))
        below = self._lounge_extra() + self.platform   # lying on the panel / standing on her music deck
        y = max(area.top() - c.y(), min(target.y(), area.bottom() + 1 - (c.y() + c.height()) - below))
        ch.move(x, y)
        self._place_panel()
        for follow in list(self.moved):
            follow()

    def set_platform(self, height: int) -> None:
        """Stand her up on her music deck (height px) or back down (0). Only lifts her if she's on the floor:
        dragged up the screen, the deck just slides under her feet."""
        height = max(0, int(height))
        old, self.platform = self.platform, height
        if height == old or self.drone or self.perched or self.busy_elsewhere:
            return
        ch, c = self.character, self.character.content_rect()
        floor = self.screen.availableGeometry().bottom() + 1 - (c.y() + c.height()) - self._lounge_extra()
        if ch.y() >= floor - old - 12:                    # she was on the floor (or on the deck at the floor)
            self._move_character(QPoint(ch.x(), ch.y() + old - height))

    def lounging(self) -> bool:
        return self.character.mode == "lying"

    def _lying_width(self) -> int:
        return round(self.panel.panel_width * 0.92)

    def _lounge_extra(self) -> int:
        if not (self.lounging() and self.settings.show_panel and not self.hidden):
            return 0
        return self.panel.height() - LOUNGE_OVERLAP - PANEL_GLOW

    def _place_drone(self) -> None:
        self.drone_window.move(self.drone_anchor().topLeft())

    def _keep_her_with_the_panel(self) -> None:
        """The panel never floats over nothing: if it's up, so is she (or her drone)."""
        if self.hidden or self.busy_elsewhere or not self.panel.isVisible():
            return
        figure = self.drone_window if self.drone else self.sit_window if self.perched else self.character
        if not figure.isVisible():
            figure.show()

    def _place_panel(self, keep_drone: bool = False) -> None:
        self._place_panel_only(keep_drone)
        self._place_feed()

    def _place_feed(self) -> None:
        """The activity feed's call cards sit right on top of the panel, lined up with it."""
        panel, feed = self.panel, self.feed
        feed.set_width(panel.panel_width)
        area = self._screen_for(panel.geometry()).availableGeometry()
        bottom = panel.y() + PANEL_GLOW - 4
        if self.lounging() and not (self.drone or self.perched):    # she lies on the panel: above her
            bottom = min(bottom, self.character.y() + self.character.visual_top() - 2)
        y = max(area.top(), bottom - feed.height())
        feed.move(panel.x() + PANEL_GLOW - 4, y)
        feed.set_allowed(self._feed_wanted())

    def _feed_wanted(self) -> bool:
        s = self.settings
        return self.panel.isVisible() and s.show_log and s.log_style == "cards"

    def _place_panel_only(self, keep_drone: bool = False) -> None:
        panel, ch = self.panel, self.character
        area = self.screen.availableGeometry()
        self._keep_her_with_the_panel()
        if self.perched and not self.drone:
            # she's off sitting on a window: the panel waits at home (its bottom edge stays put)
            panel.set_tail(panel.width() / 2, up=False, visible=False)
            panel.move(self._panel_home.x(), self._panel_home.y() - panel.height())
            return
        if self.drone:
            if not keep_drone:
                self._place_drone()
            d = self.drone_window.geometry()
            area = self._screen_for(d).availableGeometry()
            x = max(area.left(), min(round(d.center().x() - PANEL_GLOW - panel.panel_width * TAIL_AT),
                                     area.right() + 1 - panel.width()))
            panel.set_tail(d.center().x() - x, up=False)
            panel.move(x, d.top() - PANEL_GAP - panel.height() + PANEL_GLOW + 14)
            return
        if self.lounging():
            # She lies along the top of the panel: panel underneath, no tail, her on top.
            x = round(self.content_geometry().center().x() - panel.width() / 2)
            x = max(area.left(), min(x, area.right() + 1 - panel.width()))
            panel.set_tail(panel.width() / 2, up=False, visible=False)
            spot = QPoint(x, ch.y() + ch.height() - LOUNGE_OVERLAP - PANEL_GLOW + self.platform)   # (under her deck)
            if spot != panel.pos() or not self._lying_raised:
                panel.move(spot)
                ch.raise_()                                # her on top of the panel - only when it moved,
                self._lying_raised = True                  # not on every status update
            return
        aim_x = self.content_geometry().center().x()     # the tail points at her, not her window
        x = round(aim_x - PANEL_GLOW - panel.panel_width * TAIL_AT)
        if ch.mode == "look":                            # a picture card: the panel sits right on it, edges lined up
            x = self.content_geometry().right() + 1 + PANEL_GLOW - panel.width()
        x = max(area.left(), min(x, area.right() + 1 - panel.width()))
        top = ch.y() + ch.visual_top()                    # the top of her hair, not of her window
        above = top - PANEL_GAP - panel.height() + PANEL_GLOW
        if above >= area.top():
            panel.set_tail(aim_x - x, up=False)
            panel.move(x, above)
        else:
            # Not enough room above her (dragged near the top): hang below instead.
            panel.set_tail(aim_x - x, up=True)
            panel.move(x, ch.y() + ch.height() + PANEL_GAP - PANEL_GLOW)

    def _remember_position(self) -> None:
        if self.perched:                                  # her spot is home, not the window she's on
            return
        area, c = self.screen.availableGeometry(), self.content_geometry()
        bottom = area.bottom() + 1 - (c.y() + c.height())
        if self.platform and bottom <= self.platform + self._lounge_extra() + 1:
            bottom = max(0, bottom - self.platform)        # up on her music deck: home is the floor under it
        self.settings.position = SavedPosition(self.screen.name(), area.right() + 1 - (c.x() + c.width()), bottom)
        self.settings.save()

    # -- dragging -------------------------------------------------------------------
    def _clicked(self, at: QPoint) -> None:
        """A click on her: her head (the top third of her) is a pat, the rest a poke. Not every millisecond."""
        if self.hidden or self.drone or not getattr(self.settings, "head_pats", True):
            return
        if time.monotonic() - self._last_pat < 1.2:
            return
        body = self.content_geometry()
        if not body.contains(at):
            return
        self._last_pat = time.monotonic()
        self.patted.emit("head" if at.y() < body.top() + body.height() * 0.33 else "body")

    def _drag_start(self) -> None:
        self._drag_origin = self.character.pos()
        self._drag_samples = [(time.monotonic(), QPointF(QCursor.pos()))]
        self.character.set_held(True)                       # she dangles from your cursor

    def _drag_move(self, delta: QPoint) -> None:
        self._move_character(self._drag_origin + delta)
        samples = getattr(self, "_drag_samples", [])
        samples.append((time.monotonic(), QPointF(QCursor.pos())))
        del samples[:-12]
        self.character.held_at(float(QCursor.pos().x()))

    def _drag_end(self) -> None:
        """Let go: thrown if you flicked her (see fling.py), else she stays where you put her."""
        from .fling import speed_of
        samples = getattr(self, "_drag_samples", [])
        if samples and time.monotonic() - samples[-1][0] > 0.06:
            samples = []                                    # you stopped before letting go: no throw
        self._drag_samples = []
        self.character.set_held(False)
        if self.on_throw is not None and samples and self.on_throw(speed_of(samples)):
            return
        self._remember_position()

    # -- options (each one is saved) -------------------------------------------------------
    def _save(self) -> None:
        self.settings.save()
        self.settings_changed.emit()

    def set_size(self, size: int) -> None:
        """Right-click -> Size: make her bigger or smaller (her feet stay where they are)."""
        self.settings.size = max(50, min(200, int(size)))
        self.set_compact(self.settings.compact)

    def set_compact(self, compact: bool) -> None:
        self.settings.compact = compact
        self.sit_window.set_compact(False, self.settings.size)          # (her size, not compact mode)
        window = self.perch_rect
        if window is not None:
            self.leave_perch()
        ch = self.character
        anchor = self.content_geometry().bottomRight()   # keep her feet where they are
        self.panel.set_compact(compact, box_scale(self.settings.size))
        ch.lying_width = self._lying_width()
        ch.set_display_height(her_height(compact, self.settings.size))
        self._move_character(anchor - ch.content_rect().bottomRight(), self.screen)
        self._remember_position()
        self._save()
        if window is not None:
            self.perch_on(window)

    def set_style(self, style: str) -> None:
        """Her design. Lying down is the full-body art's pose, so picking another design (portrait,
        a look...) gets her up off the panel by itself - no need to turn "lie down" off first."""
        self.settings.character_style = style
        getting_up = style != "body" and self.settings.lounge
        if getting_up:
            self.settings.lounge = False

        def change() -> None:
            if getting_up:
                self.character.set_lying(False, self._lying_width())
            self.character.set_style(style)
        self._relayout(change)
        if getting_up:
            self.settings_changed.emit()                  # the menu's "Lie on the panel" tick goes off

    def set_look(self, wild_hair: float, idle_animation: bool, hair_style: str | None = None) -> None:
        self.settings.wild_hair, self.settings.idle_animation = wild_hair, idle_animation
        changed = bool(hair_style) and hair_style != self.settings.hair_style
        if hair_style:
            self.settings.hair_style = hair_style
        self._relayout(lambda: self.character.set_look(wild_hair, idle_animation, hair_style))
        if changed:
            self._save()                                  # (also tells the menu and Settings)

    def set_body_look(self, look: str) -> None:
        """Settings -> Character -> Body: neon (dark, glowing edges) or full colour."""
        self.settings.body_style = look
        self.character.set_body_look(look)
        self._save()

    def set_idle_acts(self, on: bool) -> None:
        self.settings.idle_acts = on
        self.character.acts.enabled = on
        self._save()

    def play_act(self, name: str) -> bool:
        """Do an idle activity right now (tray menu). Only in the body style, while she's idle."""
        if self.drone or self.hidden:
            return False
        return self.character.play_act(name)

    def set_panel_static(self, on: bool) -> None:
        self.settings.panel_static = on
        self.panel.set_static(on)
        self._save()

    def _call_colours(self):
        from .chat_window import SKINS
        return SKINS.get(getattr(self.settings, "chat_skin", "holocall"), SKINS["holocall"]).call

    def windows(self) -> list:
        """All her on-screen windows (a screenshot hides them for a moment)."""
        return [self.character, self.panel, self.drone_window, self.sit_window, self.feed]

    def set_search_mode(self, on: bool) -> None:
        """Search mode: her panel's colours flip while it's on (and flip back by themselves after a
        minute without a new question, in case search mode was cut short)."""
        self.panel.set_inverted(on)
        if on:
            if not hasattr(self, "_search_timer"):
                self._search_timer = QTimer(self)
                self._search_timer.setSingleShot(True)
                self._search_timer.timeout.connect(lambda: self.panel.set_inverted(False))
            self._search_timer.start(60_000)
        elif hasattr(self, "_search_timer"):
            self._search_timer.stop()

    def set_personality(self, key: str) -> None:
        self.settings.personality = key
        self._save()

    def set_perch_windows(self, on: bool) -> None:
        """Sit on the window you're using; teleport back onto the panel when it goes away."""
        self.settings.perch_windows = on
        self.window_perch.set_enabled(on)
        self._save()

    def set_lounge(self, on: bool) -> None:
        self.settings.lounge = on
        self._relayout(lambda: self.character.set_lying(on, self._lying_width()))

    def _relayout(self, change) -> None:
        """Apply a look change, keeping her feet (bottom-right) where they were."""
        ch = self.character
        if self.perched:                                  # she's on a window: it shows when she's home
            change()
            self._update_face()
            self._save()
            return
        anchor = self.content_geometry().bottomRight()
        change()
        self._move_character(anchor - ch.content_rect().bottomRight(), self.screen)
        self._update_face()
        self._remember_position()
        self._save()

    # -- face in the panel icon (new art) -----------------------------------------------
    def set_talking(self, on: bool) -> None:
        self.talking = on
        self.drone_window.set_talking(on)
        self.sit_window.set_talking(on)
        if self.drone:
            self._apply_visibility()
        elif getattr(self.settings, "panel_popup", False):          # popup text box: up while she talks,
            if not on and self._name_only() and not self._called:
                pass                                                  # (her own remark: no box for it)
            elif not on:                                              # and a few seconds after
                self._popup_until = max(self._popup_until, time.monotonic() + self.POPUP_SECONDS)
                self._popup_timer.start(int(self.POPUP_SECONDS * 1000) + 50)
            self._apply_visibility()
        if not on:
            self.viseme = ""
        self._update_face()

    def set_viseme(self, viseme: str) -> None:
        self.viseme = viseme
        self.character.set_viseme(viseme)
        self._update_face()

    def _update_face(self) -> None:
        """With the character-sheet art, the panel icon is her face - expressions, and mouth shapes as she talks."""
        if self.sprites is None or self.settings.character_style == "classic":
            self.panel.set_icon_source(self.art.icon)
            return
        if self.talking and self.viseme:
            self.panel.set_icon_source(self.sprites.mouth(self.viseme))
            return
        emo = emotions.get(self.controller.emotion or emotions.DEFAULT_FOR_STATE.get(self.controller.state))
        self.panel.set_icon_source(self.sprites.face(emo.face))

    def set_show_panel(self, show: bool) -> None:
        self.settings.show_panel = show
        self._apply_visibility()
        self._save()

    def set_log_style(self, style: str) -> None:
        """"panel": the log lines under her message (the classic look) | "cards": call cards above it."""
        self.settings.log_style = style
        self.set_show_log(self.settings.show_log)

    def set_show_log(self, show: bool) -> None:
        self.settings.show_log = show
        self.panel.set_show_log(show and self.settings.log_style != "cards")
        self._place_panel()
        self._save()

    def set_always_on_top(self, on: bool) -> None:
        self.settings.always_on_top = on
        for window in (self.character, self.panel, self.drone_window, self.sit_window, self.feed):
            window.set_always_on_top(on)
        self._save()

    def set_click_through(self, on: bool) -> None:
        self.settings.click_through = on
        for window in (self.character, self.panel, self.drone_window, self.sit_window):
            window.set_click_through(on)
        self._save()

    def reset_position(self) -> None:
        """Back to the very bottom-right ("get up" / "stand up" / Reset position) - off any window."""
        was_perched = self.perched
        self.perch_rect = None
        self.sit_window.hide()
        self.settings.position = None
        self.place()
        self._apply_visibility()
        self._save()
        if was_perched:
            self.perch_dropped.emit()                 # she won't hop straight back onto that window

    def set_hidden(self, hidden: bool) -> None:
        self.hidden = hidden
        self._apply_visibility()
        self.settings_changed.emit()

    def _apply_visibility(self) -> None:
        try:
            import shiboken6
            if not shiboken6.isValid(self.drone_window):
                return                                  # a late timer while she's closing: her windows are gone
        except ImportError:
            pass
        self._set_visibility()
        self.feed.set_allowed(self._feed_wanted())

    def _set_visibility(self) -> None:
        if self.drone:
            # Game mode: just the little disk; the panel only shows while you're talking to her.
            busy = self.controller.state is not State.IDLE or self.talking
            self.character.setVisible(False)
            self.sit_window.setVisible(False)
            self.drone_window.setVisible(not self.hidden)
            self.panel.setVisible(not self.hidden and self.settings.show_panel and busy)
            return
        self.drone_window.setVisible(False)
        if self.busy_elsewhere:
            # She's out of her window for a show (thrown, teleporting, greeting, a dash): showing it now made two of
            # her - the one in the show and a second one back home ("Ow!" popping the text box up did it).
            # The show puts her back in her window itself when it's done.
            self.sit_window.setVisible(False)
            self.character.setVisible(False)
            return
        self.sit_window.setVisible(not self.hidden and self.perched)
        self.character.setVisible(not self.hidden and not self.perched)
        self._show_panel(not self.hidden and self.settings.show_panel and self._panel_wanted())

    # -- the text box: always, or only popping up when she talks back ------------------------------------------
    POPUP_SECONDS = 6.0                       # it stays this long after she's done (longer for long replies)

    def _name_only(self) -> bool:
        """Text box mode "only when you say her name": it pops up when you call her ("hey Capri", the TALK
        hotkey) and stays for that conversation - not for things she says by herself (screen comments, hype...)."""
        return bool(getattr(self.settings, "panel_popup", False) and getattr(self.settings, "panel_on_name", False))

    def _panel_wanted(self) -> bool:
        if not getattr(self.settings, "panel_popup", False) or self.lounging():
            return True                           # (lying on it: she needs it)
        state = self.controller.state
        if self._name_only():
            if state is State.LISTENING:
                self._called = True               # you said her name (or pressed TALK)
            if not self._called:
                return False
        busy = self.talking or state in (State.LISTENING, State.PROCESSING, State.LAUNCHING, State.SPEAKING)
        if busy or time.monotonic() < self._popup_until:
            return True
        self._called = False                      # that conversation's over
        return False

    def _show_panel(self, visible: bool) -> None:
        """Show / hide the text box - popping in and fading out in popup mode."""
        panel = self.panel
        popup = getattr(self.settings, "panel_popup", False)
        if visible == panel.isVisible() and not (visible and self._panel_fading):
            return
        if not popup:
            panel.setWindowOpacity(1.0)
            panel.setVisible(visible)
            return
        from PySide6.QtCore import QPropertyAnimation
        anim = getattr(self, "_panel_anim", None)
        if anim is not None:
            anim.stop()
        anim = QPropertyAnimation(panel, b"windowOpacity", self)
        self._panel_anim = anim
        if visible:
            self._panel_fading = False
            panel.setWindowOpacity(0.0)
            panel.setVisible(True)
            self._place_panel()
            anim.setDuration(160)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
        else:
            self._panel_fading = True
            anim.setDuration(260)
            anim.setStartValue(panel.windowOpacity())
            anim.setEndValue(0.0)
            anim.finished.connect(lambda: (panel.setVisible(False), panel.setWindowOpacity(1.0),
                                           setattr(self, "_panel_fading", False)) if self._panel_fading else None)
        anim.start()

    def _popup_check(self) -> None:
        """Popup mode: something new to say (or she's listening / thinking): show it, and hide it later."""
        if not getattr(self.settings, "panel_popup", False):
            return
        c = self.controller
        if self._name_only():
            if c.state is State.LISTENING:
                self._called = True
            elif not self._called:                               # she's talking by herself: no box
                self._popup_message = c.message
                if not self.drone:
                    self._apply_visibility()
                return
        if c.message != self._popup_message or self.talking or c.state in (State.LISTENING, State.PROCESSING,
                                                                            State.LAUNCHING, State.SPEAKING):
            if c.message != self._popup_message and c.state is State.IDLE and not self._popup_message:
                self._popup_message = c.message                  # (her first idle line: no popup for it)
                return
            self._popup_message = c.message
            self._popup_until = time.monotonic() + self.POPUP_SECONDS + min(8.0, len(c.message or "") / 25)
            self._popup_timer.start(int((self._popup_until - time.monotonic()) * 1000) + 50)
        if not self.drone:
            self._apply_visibility()

    def set_drone(self, on: bool) -> None:
        """Game mode on / off: she turns into a little flying disk while you play."""
        if on == self.drone:
            return
        if on and self.perched:                           # off the window, straight into the drone
            self.perch_rect = None
            self.sit_window.hide()
            self.place()
        self.drone = on
        self._place_drone()
        self._place_panel()
        self._apply_visibility()
        if on:
            self.character.release_caches()            # she's hidden: drop her pre-drawn images
        self.settings_changed.emit()
        self.drone_changed.emit(on)

    DRONE_INSET = 6                                   # the drone has a little transparent room round it

    def drone_anchor(self) -> QRect:
        """Where the drone hovers: where you last dragged it, else the very bottom-right corner."""
        d = self.drone_window
        screen, right, bottom = self.screen, -self.DRONE_INSET, -self.DRONE_INSET
        saved = self.settings.drone_spot.split("|")
        if len(saved) == 3:
            found = self._screen_named(saved[0])
            try:
                if found is not None:
                    screen, right, bottom = found, int(saved[1]), int(saved[2])
            except ValueError:
                pass
        area = screen.availableGeometry()
        x = area.right() + 1 - right - d.width()
        y = area.bottom() + 1 - bottom - d.height()
        x = max(area.left() - self.DRONE_INSET, min(x, area.right() + 1 - d.width() + self.DRONE_INSET))
        y = max(area.top() - self.DRONE_INSET, min(y, area.bottom() + 1 - d.height() + self.DRONE_INSET))
        return QRect(x, y, d.width(), d.height())

    def _drone_drag(self, delta: QPoint) -> None:
        self.drone_window.move(getattr(self, "_drone_origin", self.drone_window.pos()) + delta)
        self._place_panel(keep_drone=True)

    def _drone_dropped(self) -> None:
        d = self.drone_window.geometry()
        screen = self._screen_for(d)
        area = screen.availableGeometry()
        self.settings.drone_spot = f"{screen.name()}|{area.right() + 1 - d.right() - 1}|{area.bottom() - d.bottom()}"
        self._place_panel()
        self._save()

    def set_drone_look(self, look: str) -> None:
        """"disk" or "mask" - how she looks as the drone."""
        self.settings.drone_look = look
        self.drone_window.set_style(look)
        self._save()

    def move_to(self, spot: str) -> bool:
        """"Go to the bottom left" etc.: she teleports there (and it becomes her spot).
        spot: bottom_left | bottom_right | top_left | top_right | middle | other_screen | main_screen.
        False if there's no other monitor to go to."""
        screens = QGuiApplication.screens()
        here = self._screen_for(self.content_geometry())
        if spot == "other_screen":
            if len(screens) < 2:
                return False
            screen, spot = screens[(screens.index(here) + 1) % len(screens)] if here in screens else screens[1], "bottom_right"
        elif spot == "main_screen":
            screen, spot = QGuiApplication.primaryScreen(), "bottom_right"
        else:
            screen = here
        was = self.content_geometry().center()
        area = screen.availableGeometry()
        if self.drone:                                     # the drone flies there instead
            d = self.drone_window
            right = {"bottom_left": area.width() - d.width() + self.DRONE_INSET, "top_left": area.width() - d.width() + self.DRONE_INSET,
                     "middle": (area.width() - d.width()) // 2}.get(spot, -self.DRONE_INSET)
            bottom = {"top_left": area.height() - d.height() + self.DRONE_INSET, "top_right": area.height() - d.height() + self.DRONE_INSET,
                      "middle": (area.height() - d.height()) // 2}.get(spot, -self.DRONE_INSET)
            self.settings.drone_spot = f"{screen.name()}|{right}|{bottom}"
            self._place_panel()
            self._save()
            return True
        if self.perched:                                   # off the window she was sitting on
            self.perch_rect = None
            self.sit_window.hide()
            self.perch_dropped.emit()
        c = self.character.content_rect()
        w, h = c.width(), c.height()
        left = area.width() - w - SCREEN_MARGIN
        top = area.height() - h - SCREEN_MARGIN
        right, bottom = {
            "bottom_right": (SCREEN_MARGIN, SCREEN_MARGIN), "bottom_left": (left, SCREEN_MARGIN),
            "top_right": (SCREEN_MARGIN, top), "top_left": (left, top),
            "middle": ((area.width() - w) // 2, (area.height() - h) // 2),
        }.get(spot, (SCREEN_MARGIN, SCREEN_MARGIN))
        self.settings.position = SavedPosition(screen.name(), right, bottom)
        self._lying_raised = False
        self.place()
        self._apply_visibility()
        self._save()
        if hasattr(self, "window_perch") and self.character.isVisible():
            self.window_perch._flash(was, self.content_geometry().center())   # the red teleport flash
        return True

    def set_drone_corner(self, corner: str) -> None:
        """"move the drone to the left / right": that bottom corner of her screen."""
        d, area = self.drone_window, self.screen.availableGeometry()
        right = -self.DRONE_INSET if corner != "left" else area.width() - d.width() + self.DRONE_INSET
        self.settings.drone_spot = f"{self.screen.name()}|{right}|{-self.DRONE_INSET}"
        self._place_panel()
        self._save()

    # -- state ------------------------------------------------------------------------
    def _on_changed(self) -> None:
        c = self.controller
        self.character.set_state(c.state, c.emotion or emotions.guess(c.message, c.state))
        self._update_face()
        # The panel's height depends on its content; keep it sitting on Capri.
        self._place_panel()
        if self.drone:
            self._apply_visibility()
        else:
            self._popup_check()

    def show(self) -> None:
        self._lying_raised = False
        if self.perched:
            self._apply_visibility()
            self._place_panel()
            return
        self.place()
        self._apply_visibility()

    # -- sitting on a window ("Sit on windows" - perch.py decides which one) ---------------------
    @property
    def perched(self) -> bool:
        return self.perch_rect is not None

    def _perch_spot(self, window: QRect) -> QPoint | None:
        """Where her sitting window goes on `window`: seat on its top edge, towards its right end.
        None if there's no room above it for her."""
        sit = self.sit_window
        seat = sit.seat_point()
        area = self._screen_for(window).availableGeometry()
        x = window.right() - 40 - sit.content_rect().right()
        x = max(area.left() - sit.content_rect().left(),
                min(x, area.right() + 1 - sit.content_rect().right() - 1))
        y = window.top() + SINK - seat.y()
        if y + sit.content_rect().top() < area.top():
            return None
        return QPoint(x, y)

    def can_perch(self, window: QRect) -> bool:
        return self._perch_spot(window) is not None

    def perch_on(self, window: QRect) -> bool:
        """Sit on top of `window` (Qt screen rect). The panel stays at home."""
        if self.drone or self.hidden:
            return False
        spot = self._perch_spot(window)
        if spot is None:
            return False
        if not self.perched:
            self._panel_home = QPoint(self.panel.x(), self.panel.y() + self.panel.height())
        self.perch_rect = QRect(window)
        self.sit_window.move(spot)
        self._apply_visibility()
        self._place_panel()
        return True

    def perch_follow(self, window: QRect) -> bool:
        """The window she sits on moved: just move her with it (no re-layout - every frame)."""
        spot = self._perch_spot(window)
        if spot is None:
            return False
        self.perch_rect = QRect(window)
        if spot != self.sit_window.pos():
            self.sit_window.move(spot)
        return True

    def leave_perch(self) -> None:
        """Back home, onto the panel."""
        if not self.perched:
            return
        self.perch_rect = None
        self.sit_window.hide()
        self._lying_raised = False
        self.place()
        self._apply_visibility()

    def _sit_dropped(self) -> None:
        """You dragged her off the window: she stands where you let go (her new spot)."""
        sit, ch = self.sit_window, self.character
        feet = sit.pos() + QPoint(sit.content_rect().center().x(), sit.content_rect().bottom())
        self.perch_rect = None
        sit.hide()
        c = ch.content_rect()
        self._move_character(feet - QPoint(c.center().x(), c.bottom()), self._screen_for(QRect(feet, feet)))
        self._apply_visibility()
        self._remember_position()
        self.perch_dropped.emit()
