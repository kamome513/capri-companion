"""v1.4: pressing Discord's real Mute / Deafen buttons (reading the state back), and
playing a Spotify search result without the Web API. UI Automation itself is faked."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands import router as router_module  # noqa: E402
from capri.commands.system import ProcessInfo  # noqa: E402
from capri.integrations.app_buttons import DiscordButtons, SpotifyButtons  # noqa: E402
from capri.integrations.uia import find_buttons  # noqa: E402
from capri.states import State  # noqa: E402


# -- a fake Discord user panel ---------------------------------------------------------------------
class Discord:
    """Behaves like Discord: deafen also mutes; undeafen gives back the mic as it was."""

    def __init__(self, muted=False, deafened=False, toggles=True, labels_flip=False):
        self.muted, self.deafened = muted, deafened
        self.toggles, self.labels_flip = toggles, labels_flip
        self.presses = []

    def buttons(self, hwnd, names=None):
        mic_on = self.muted or self.deafened
        mute = Btn(self, "mute", ("Unmute" if mic_on and self.labels_flip else "Mute"), mic_on)
        deaf = Btn(self, "deafen", ("Undeafen" if self.deafened and self.labels_flip else "Deafen"), self.deafened)
        out = [mute, deaf, Btn(self, "x", "Settings", None)]
        return [b for b in out if names is None or b.name in names]


class Btn:
    def __init__(self, app, kind, name, on):
        self.app, self.kind, self.name, self.on = app, kind, name, on

    def toggled(self):
        return self.on if self.app.toggles else None

    def press(self):
        self.app.presses.append(self.kind)
        if self.kind == "mute":
            if self.app.deafened:                 # Discord: unmuting while deafened undeafens too
                self.app.deafened = self.app.muted = False
            else:
                self.app.muted = not self.app.muted
        elif self.kind == "deafen":
            self.app.deafened = not self.app.deafened


def discord(fake):
    return DiscordButtons(fake, lambda pids: [1], sleep=lambda s: None)


@pytest.mark.parametrize("start, kind, want, outcome, presses", [
    ({}, "mute", True, "muted", ["mute"]),
    ({"muted": True}, "mute", True, "already_muted", []),
    ({"muted": True}, "mute", False, "unmuted", ["mute"]),
    ({}, "mute", False, "already_unmuted", []),
    ({"deafened": True}, "mute", False, "unmuted", ["deafen"]),                  # undeafen brings the mic back
    ({"deafened": True, "muted": True}, "mute", False, "unmuted", ["deafen", "mute"]),
    ({}, "deafen", True, "deafened", ["deafen"]),                               # exactly one press
    ({"deafened": True}, "deafen", True, "already_deafened", []),
    ({"deafened": True}, "deafen", False, "undeafened", ["deafen"]),
])
def test_discord_buttons(start, kind, want, outcome, presses):
    fake = Discord(**start)
    assert discord(fake).set([5], kind, want) == outcome
    assert fake.presses == presses


def test_discord_buttons_with_flipping_labels_and_no_switch_state():
    fake = Discord(muted=True, toggles=False, labels_flip=True)
    assert discord(fake).set([5], "mute", False) == "unmuted"
    assert discord(fake).set([5], "mute", False) == "already_unmuted"


def test_no_buttons_means_unavailable():
    class Empty:
        def buttons(self, hwnd, names=None):
            return []
    b = DiscordButtons(Empty(), lambda pids: [1], sleep=lambda s: None)
    b_find = find_buttons(Empty(), [1], None, bool, timeout=0.0, sleep=lambda s: None)
    assert b.set([5], "mute", True) == "unavailable" and b_find == []


class ButtonsService:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def set(self, pids, kind, want):
        self.calls.append((tuple(pids), kind, want))
        return self.outcome


def test_router_uses_buttons_and_reports_real_state():
    d = FakeDesktop()
    r = rig(d, discord_buttons=ButtonsService("unmuted"))
    r.service.command.emit("unmute me on discord")
    assert settle(3, lambda: r.controller.state is State.SUCCESS)
    assert r.router.services.discord_buttons.calls == [((10,), "mute", False)]
    assert r.controller.message == "Unmuted. You're live on Discord." and d.calls == []     # no key presses
    r.service.command.emit("deafen me")
    assert settle(3, lambda: len(r.router.services.discord_buttons.calls) == 2)
    assert r.router.services.discord_buttons.calls[-1] == ((10,), "deafen", True)


def test_router_falls_back_to_keys_without_buttons():
    d = FakeDesktop()
    r = rig(d, discord_buttons=ButtonsService("unavailable"))
    r.service.command.emit("mute me")
    assert settle(3, lambda: d.calls)
    assert d.calls == [("in_window", (10,), "ctrl+shift+m")]


def test_router_says_when_discord_did_not_change():
    r = rig(FakeDesktop(), discord_buttons=ButtonsService("failed"))
    r.service.command.emit("mute me")
    assert settle(3, lambda: r.controller.state is State.ERROR)
    assert "didn't change" in r.controller.message


# -- Spotify without the Web API --------------------------------------------------------------------
class SpotifyApp:
    def __init__(self, results=("Play Liked Songs", "Play Let You Down by NF", "Play Let You Down (Piano)"),
                 plays=True):
        self.results, self.plays, self.playing, self.pressed = list(results), plays, False, []
        self.looks = 0

    def buttons(self, hwnd, names=None):
        self.looks += 1
        visible = self.results if self.looks > 1 else ["Play Liked Songs"]     # results load a moment later
        out = [Play(self, n) for n in ["Play" if not self.playing else "Pause", *visible]]
        return [b for b in out if names is None or b.name in names]


class Play:
    def __init__(self, app, name):
        self.app, self.name = app, name

    def toggled(self):
        return None

    def press(self):
        self.app.pressed.append(self.name)
        self.app.playing = self.app.plays


def test_spotify_presses_the_best_result_and_checks_it_plays():
    fake = SpotifyApp()
    s = SpotifyButtons(fake, lambda pids: [1], sleep=lambda x: None)
    assert s.play([7], "let you down nf") == "Let You Down by NF"
    assert fake.pressed == ["Play Let You Down by NF"]


def test_spotify_reports_nothing_when_it_did_not_start():
    fake = SpotifyApp(plays=False)
    assert SpotifyButtons(fake, lambda pids: [1], sleep=lambda x: None).play([7], "let you down nf", timeout=0.1) == ""


class SpotifyService:
    def __init__(self, label):
        self.label, self.calls = label, []

    def play(self, pids, terms):
        self.calls.append((tuple(pids), terms))
        return self.label


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(router_module, "SPOTIFY_START_WAIT", 1.0)
    monkeypatch.setattr(router_module, "SPOTIFY_SETTLE", 0.0)


def test_spotify_not_running_starts_it_then_searches_then_plays(quick):
    from test_stage5 import FakeSpotify
    service = SpotifyService("Let You Down by NF")
    r = rig(FakeDesktop(), spotify=FakeSpotify(connected=False), spotify_buttons=service)
    real_open = r.system.open_item

    def open_item(target):                     # opening "spotify:" starts Spotify
        real_open(target)
        if target == "spotify:":
            r.system.procs[20] = ProcessInfo(20, "Spotify.exe")
    r.system.open_item = open_item
    r.service.command.emit("play let you down by nf")
    assert settle(4, lambda: r.controller.state is State.SUCCESS)
    assert r.system.calls == [("open", "spotify:"), ("open", "spotify:search:let%20you%20down%20nf")]
    assert service.calls == [((20,), "let you down nf")]
    assert r.controller.message == "Playing Let You Down by NF."


def test_spotify_search_shown_when_play_button_not_found(quick):
    from test_stage5 import FakeSpotify
    r = rig(FakeDesktop(), spotify=FakeSpotify(connected=False), spotify_buttons=SpotifyService(""),
            processes=[ProcessInfo(20, "Spotify.exe")])
    r.service.command.emit("play blinding lights")
    assert settle(4, lambda: r.controller.state is State.SUCCESS)
    assert r.system.calls == [("open", "spotify:search:blinding%20lights")]
    assert r.controller.message == "Pulled up blinding lights in Spotify. Hit play."
