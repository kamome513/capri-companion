"""v1.8: Spotify by exact track (no Premium needed), branching lightning, search mode,
the close-app lightning blast, no bending, and a sharp big greeting."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import random  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRect, QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import FakeSpotify, settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Intent, Kind, parse  # noqa: E402
from capri.commands.system import ProcessInfo  # noqa: E402
from capri.integrations.spotify_app import Played, SpotifyApp, main_window_titles, track_ids_from_page  # noqa: E402
from capri.states import State  # noqa: E402
from capri.ui import lightning  # noqa: E402

DDG_PAGE = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopen.spotify.com%2Ftrack%2F'
            '7oDd86yk8itslrA9HRP2ki&amp;rut=x">Let You Down - song by NF | Spotify</a>'
            '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopen.spotify.com%2Fintl-de%2Ftrack%2F'
            '1111111111111111111111">Let You Down (Piano Cover)</a>'
            '<a href="https://open.spotify.com/track/7oDd86yk8itslrA9HRP2ki">dupe</a>')
TITLES = {"7oDd86yk8itslrA9HRP2ki": "Let You Down", "1111111111111111111111": "Let You Down (Piano Cover)"}


# -- Spotify ---------------------------------------------------------------------------------------------
def test_track_links_in_search_pages():
    assert track_ids_from_page(DDG_PAGE) == ["7oDd86yk8itslrA9HRP2ki", "1111111111111111111111"]
    assert track_ids_from_page("https://open.spotify.com/track/ABCDEFGHIJKLMNOPQRSTUV?si=x") == \
        ["ABCDEFGHIJKLMNOPQRSTUV"]


class FakeSpotifyPC:
    """A PC with the Spotify app: opening a track link starts it (or not), the window title follows."""

    def __init__(self, running=True, autoplay=True, page=DDG_PAGE):
        self.running, self.autoplay, self.page = running, autoplay, page
        self.title = "Spotify Free" if running else ""
        self.opened, self.urls, self.pressed = [], [], 0
        self.loaded = None

    def open_item(self, target):
        self.opened.append(target)
        if target == "spotify:":
            self.running, self.title = True, "Spotify Free"
        elif target.startswith("spotify:track:"):
            self.loaded = target.split(":")[-1]
            if self.autoplay:
                self.title = "NF - " + TITLES.get(self.loaded, "?")

    def press_play(self, pids, name):
        self.pressed += 1
        if self.loaded:
            self.title = "NF - " + TITLES.get(self.loaded, "?")
        return True

    def fetch_text(self, url):
        self.urls.append(url)
        return self.page

    def fetch_json(self, url):
        self.urls.append(url)
        if "itunes" in url or "deezer" in url:
            return {}                                       # no catalog result: use the web search
        return {"title": TITLES.get(url.rsplit("%2F", 1)[-1], "")}

    def app(self, api_search=None, press=True):
        return SpotifyApp(self.open_item, lambda: [5] if self.running else [], lambda pids: [self.title],
                          self.press_play if press else None, self.fetch_text, self.fetch_json,
                          api_search=api_search, sleep=lambda s: None)


def test_plays_the_exact_track_without_premium():
    pc = FakeSpotifyPC()
    result = pc.app().play("let you down", "nf")
    assert result == Played("playing", "NF - Let You Down")
    assert pc.opened == ["spotify:track:7oDd86yk8itslrA9HRP2ki"]       # the real song, not the cover
    web = [u for u in pc.urls if "duckduckgo" in u]
    assert web and "let+you+down+nf" in web[0]


def test_presses_play_when_opening_alone_does_not_start_it():
    pc = FakeSpotifyPC(autoplay=False)
    assert pc.app().play("let you down", "nf").status == "playing" and pc.pressed == 1


def test_says_opened_when_it_really_did_not_play():
    pc = FakeSpotifyPC(autoplay=False)
    assert pc.app(press=False).play("let you down", "nf") == Played("opened", "Let You Down")


def test_starts_spotify_first():
    pc = FakeSpotifyPC(running=False)
    assert pc.app().play("let you down", "nf").status == "playing"
    assert pc.opened == ["spotify:", "spotify:track:7oDd86yk8itslrA9HRP2ki"]


def test_uses_spotifys_own_search_when_connected():
    pc = FakeSpotifyPC()
    played = pc.app(api_search=lambda q, a: "spotify:track:7oDd86yk8itslrA9HRP2ki").play("let you down", "nf")
    assert played.status == "playing"
    assert pc.urls == []                                                 # no other lookups needed


def test_not_found_and_search_failures():
    pc = FakeSpotifyPC(page="<html>no results</html>")
    assert pc.app().play("zzzz", "").status == "not_found"
    assert [u.split("/")[2] for u in pc.urls] == ["itunes.apple.com", "api.deezer.com", "html.duckduckgo.com",
                                                  "www.bing.com"]       # every source, in order


class AppService:
    def __init__(self, result):
        self.result, self.calls = result, []

    def play(self, query, artist):
        self.calls.append((query, artist))
        return self.result


def test_router_uses_the_app_player_and_reports_truthfully():
    r = rig(FakeDesktop(), spotify=FakeSpotify(connected=False), spotify_app=AppService(Played("playing", "NF - Let You Down")))
    r.service.command.emit("play let you down by nf")
    assert settle(3, lambda: r.controller.state is State.SUCCESS)
    assert r.router.services.spotify_app.calls == [("let you down", "nf")]
    assert r.controller.message == "Playing NF - Let You Down." and r.speaker.lines == []
    r2 = rig(FakeDesktop(), spotify=FakeSpotify(connected=False), spotify_app=AppService(Played("opened", "Let You Down")))
    r2.service.command.emit("play let you down by nf")
    assert settle(3, lambda: r2.controller.state is State.SUCCESS)
    assert r2.controller.message == "Opened Let You Down in Spotify. Hit play."


def test_router_without_premium_falls_back_to_the_app_player():
    from capri.integrations import spotify as sp
    service = AppService(Played("playing", "NF - Let You Down"))
    r = rig(FakeDesktop(), spotify=FakeSpotify(error=sp.PremiumRequired("Premium")), spotify_app=service)
    r.service.command.emit("play let you down by nf")
    assert settle(3, lambda: service.calls)
    assert settle(3, lambda: r.controller.message == "Playing NF - Let You Down.")


# -- lightning ---------------------------------------------------------------------------------------------
def test_bolts_branch_and_end_where_they_should():
    rng = random.Random(4)
    paths = lightning.bolt(QPointF(0, 0), QPointF(400, 50), rng)
    main = paths[0]
    assert main[0] == QPointF(0, 0) and main[-1] == QPointF(400, 50)
    assert len(main) == 2 ** 5 + 1 and len(paths) > 1                    # fractal zig-zag, with forks
    img = QImage(500, 200, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    lightning.draw(p, paths)
    p.end()
    assert img.pixelColor(200, 25).alpha() > 0 or any(img.pixelColor(x, y).alpha() for x in range(0, 500, 5)
                                                      for y in range(0, 200, 5))


# -- search mode --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["go into search mode", "search mode", "hey capri go into search mode",
                                  "enter search mode", "i want to search something", "search"])
def test_parse_search_mode(text):
    assert parse(text) == Intent(Kind.SEARCH_MODE)


def test_search_mode_asks_searches_and_asks_again(monkeypatch):
    from capri.commands import router as router_module
    monkeypatch.setattr(router_module, "SEARCH_MODE_GAP", 10)
    r = rig(FakeDesktop())
    r.service.command.emit("go into search mode")
    assert r.speaker.lines[-1] == "Search mode on. What do you want to search?" and r.listens
    r.service.command.emit("search funny cats on youtube")                 # no wake word needed
    assert r.system.calls[-1] == ("open", "https://www.youtube.com/results?search_query=funny+cats")
    assert settle(2, lambda: r.speaker.lines[-1] == "Anything else to search?")
    r.service.command.emit("best deadlock builds")                         # just the words works too
    assert r.system.calls[-1] == ("open", "https://www.google.com/search?q=best+deadlock+builds")
    assert settle(2, lambda: r.speaker.lines[-1] == "Anything else to search?")
    r.service.command.emit("thats all")
    assert r.controller.message == "Search mode off."
    calls = len(r.system.calls)
    r.service.command.emit("hello")                                        # back to normal: that's small talk
    assert len(r.system.calls) == calls


def test_search_mode_ends_quietly_on_silence():
    r = rig(FakeDesktop())
    r.service.command.emit("search mode")
    r.service.no_command.emit()                                            # first silence: "still there?"
    assert r.speaker.lines[-1].startswith("Still there?") and "SEARCH MODE" in r.controller.message
    r.service.no_command.emit()
    assert r.controller.message == "Search mode off."


# -- closing with lightning -----------------------------------------------------------------------------------
class Zap:
    def __init__(self):
        self.calls = []

    def __call__(self, name, pids, then):
        self.calls.append((name, tuple(pids)))
        then()


def test_closing_an_app_blasts_its_window():
    zap = Zap()
    r = rig(FakeDesktop(), zap=zap)
    r.service.command.emit("close discord")
    assert zap.calls == [("Discord", (10,))]
    assert ("terminate", (10,)) in r.system.calls or ("close", (10,)) in r.system.calls


def test_the_zap_show_closes_at_impact():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    from capri.ui.zap import ZapShow
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(),
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    z = ZapShow(c, lambda pids: QRect(200, 150, 700, 500))
    closed = []
    z.zap("Discord", [10], lambda: closed.append(z.fx.t))
    assert z.fx.isVisible() and c.character.isVisible()                    # she stays put and fires
    assert settle(2, lambda: closed)
    assert 0.2 <= closed[0] < 0.5                                          # at the impact, not before
    assert settle(2, lambda: not z.active) and not z.fx.isVisible()


def test_song_catalog_route_finds_the_real_song():
    """iTunes' public search -> best song + artist match -> song.link -> the Spotify track."""
    calls = []

    def fetch_json(url):
        calls.append(url)
        if "itunes" in url:
            return {"results": [
                {"trackName": "Let You Down (Piano Version)", "artistName": "Covers Co", "trackViewUrl": "https://m/1"},
                {"trackName": "Let You Down", "artistName": "NF", "trackViewUrl": "https://m/2"}]}
        if "song.link" in url:
            assert "m%2F2" in url                              # the real song's page, not the cover's
            return {"linksByPlatform": {"spotify": {"url": "https://open.spotify.com/track/7oDd86yk8itslrA9HRP2ki"}}}
        return {}
    app = SpotifyApp(lambda t: None, lambda: [5], lambda pids: ["Spotify"], None, lambda u: "", fetch_json,
                     sleep=lambda s: None)
    assert app.find_track("let you down", "n f") == ("7oDd86yk8itslrA9HRP2ki", "Let You Down")
    assert not any("duckduckgo" in u for u in calls)


def test_bing_wrapped_links_are_read():
    import base64
    wrapped = base64.urlsafe_b64encode(b"https://open.spotify.com/track/7oDd86yk8itslrA9HRP2ki").decode().rstrip("=")
    page = f'<a href="https://www.bing.com/ck/a?!&&p=abc&u=a1{wrapped}&ntb=1">Let You Down</a>'
    assert track_ids_from_page(page) == ["7oDd86yk8itslrA9HRP2ki"]


def test_only_spotifys_main_window_counts():
    class Desk:
        def windows_for(self, pids):
            return [1, 2, 3]

        def window_class(self, h):
            return {1: "IME", 2: "Chrome_WidgetWin_0", 3: "MSCTFIME UI"}[h]

        def window_title(self, h):
            return {1: "Default IME", 2: "NF - Let You Down", 3: "MSCTFIME UI"}[h]
    assert main_window_titles(Desk(), [5]) == ["NF - Let You Down"]


def test_already_playing_is_not_restarted():
    pc = FakeSpotifyPC()
    pc.title = "NF - Let You Down"
    assert pc.app().play("let you down", "nf") == Played("playing", "NF - Let You Down")
    assert not any(o.startswith("spotify:track:") for o in pc.opened)


# -- understanding you better -----------------------------------------------------------------------------------
def test_recogniser_alternatives_are_read():
    from capri.voice.wakeword import heard
    assert heard({"alternatives": [{"text": "oh pen this cord", "confidence": 210.0},
                                   {"text": "open discord", "confidence": 205.0},
                                   {"text": "open discord", "confidence": 190.0}]}) == ["oh pen this cord", "open discord"]
    assert heard({"text": "capri open discord"}) == ["open discord"]
    assert heard({"text": ""}) == []


def test_the_runner_up_wins_when_it_is_a_real_command():
    from capri.commands.router import CommandRouter
    assert CommandRouter.choose(["oh pen this cord", "open discord"]) == "open discord"
    assert CommandRouter.choose(["what time is it", "watt time is it"]) == "what time is it"
    assert CommandRouter.choose(["blah blah", "blah blah blah"]) == "blah blah"


def test_assistant_uses_the_best_guess():
    r = rig(FakeDesktop())
    r.assistant.choose = r.router.choose
    r.service.alternatives.emit(["open discord"])
    r.service.command.emit("oh pen this cord")
    assert r.system.calls and r.system.calls[0][0] == "program"         # Discord launched


# -- cyberpsychosis shutdown ---------------------------------------------------------------------------------------
class Psycho:
    def __init__(self):
        self.played, self.aborted = [], False

    def play(self, then):
        self.played.append(then)

    def abort(self):
        self.aborted = True


def test_shutdown_goes_through_cyberpsychosis_first():
    d = FakeDesktop()
    psycho = Psycho()
    r = rig(d, psychosis=psycho)
    r.service.command.emit("shut down my pc")
    r.service.command.emit("yes")
    assert psycho.played and d.calls == []               # the show first...
    psycho.played[0]()
    assert d.calls == [("power", "shutdown")]            # ...then the real shutdown


def test_psychosis_show_runs_then_shuts_down():
    from capri.ui.psychosis import TOTAL, PsychosisShow
    show = PsychosisShow(sound=False)
    done = []
    show.play(lambda: done.append(1))
    assert show.windows and all(w.isVisible() for w in show.windows)
    assert settle(TOTAL + 1.5, lambda: done)
    show.abort()
    assert not show.windows and not show.active


# -- Discord: zap the real button, then press it --------------------------------------------------------------------
class DiscordUI:
    def __init__(self):
        self.calls = []

    def locate(self, pids, kind):
        self.calls.append(("locate", kind))
        return (900, 1000, 940, 1032)                       # Mute's spot on screen

    def set(self, pids, kind, want):
        self.calls.append(("set", kind, want))
        return "unmuted" if not want else "muted"


def test_discord_button_is_zapped_then_pressed():
    ui = DiscordUI()
    zaps = []

    def zap_at(rect, pids, then):
        zaps.append(rect)
        assert ("set", "mute", False) not in ui.calls      # not pressed before the bolt lands
        then()
    r = rig(FakeDesktop(), discord_buttons=ui, zap_at=zap_at)
    r.service.command.emit("unmute me")
    assert settle(3, lambda: r.controller.state is State.SUCCESS)
    assert zaps == [(900, 1000, 940, 1032)]
    assert ui.calls == [("locate", "mute"), ("set", "mute", False)]
    assert r.controller.message == "Unmuted. You're live on Discord."
