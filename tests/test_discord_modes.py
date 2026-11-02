"""v1.38: her Discord status changes with what you're doing - "Backseat gaming" while you play, "Vibing to
music" while music plays - and her pictures are animated."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.integrations import discord_presence as dp  # noqa: E402
from capri.integrations import now_doing as nd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# -- what Discord is told ---------------------------------------------------------------------------------
def test_desktop_is_plugged_in_with_her_animated_picture():
    act = dp.activity("desktop", 1, dp.INVITE)
    assert act["details"] == "Plugged in" and "state" not in act
    assert act["assets"]["large_image"] == dp.ART + "capri.gif" and "small_image" not in act["assets"]
    assert [b["label"] for b in act["buttons"]] == ["Get Capri", "Join her Discord"]


def test_gaming_names_the_game_from_your_library():
    act = dp.activity("drone", 1, dp.INVITE, "gaming", "Deadlock")
    assert (act["details"], act["state"]) == ("Backseat gaming", "Playing Deadlock")
    assert act["assets"]["small_image"] == dp.ART + "gaming.gif" and act["assets"]["small_text"] == "Gaming"
    assert dp.activity("drone", 1, "", "gaming", "")["state"] == "Drone mode: on"       # a game she can't name
    assert len(dp.activity("drone", 1, "", "gaming", "x" * 300)["state"]) <= 128            # Discord's limit
    assert len(act["buttons"]) == 2


def test_music_never_says_the_song():
    act = dp.activity("desktop", 1, dp.INVITE, "music")
    assert (act["details"], act["state"]) == ("Vibing to music", "Headphones on")
    assert act["assets"]["small_image"] == dp.ART + "music.gif"


def test_the_pictures_are_real_animated_gifs_in_the_repo():
    Image = pytest.importorskip("PIL.Image")
    for name, size in (("capri.gif", 320), ("gaming.gif", 128), ("music.gif", 128)):
        path = ROOT / "assets" / "discord" / name
        assert path.stat().st_size < 2_000_000, name
        with Image.open(path) as im:
            assert im.format == "GIF" and im.n_frames >= 12 and im.size == (size, size)
            assert im.info.get("loop") == 0                                   # loops forever
    assert dp.ART == "https://raw.githubusercontent.com/kamome513/capri-companion/main/assets/discord/"


def test_presence_sends_the_new_mode_when_it_changes():
    from test_discord_presence import FakeDiscord, presence, settle
    fake = FakeDiscord()
    try:
        p, clock = presence(fake)
        p.step()
        assert settle(lambda: len(fake.activities()) == 1)
        p.set_doing("music")
        clock[0] += 10
        p.step()
        assert settle(lambda: len(fake.activities()) == 2) and fake.activities()[1]["details"] == "Vibing to music"
        p.set_doing("music")                                                   # same again: nothing sent
        clock[0] += 10
        p.step()
        time.sleep(0.1)
        assert len(fake.activities()) == 2
        p.set_state("drone")
        p.set_doing("gaming", "Deadlock")
        clock[0] += 10
        p.step()
        assert settle(lambda: len(fake.activities()) == 3) and fake.activities()[2]["state"] == "Playing Deadlock"
        p.set_doing("", "Deadlock")                                            # game closed: name dropped
        assert p.game == ""
    finally:
        fake.stop()


# -- is music playing? ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sounding,titles,music", [
    (["Spotify.exe"], [], True),
    (["spotify"], [], True),                                                   # Linux MPRIS name
    (["MusicBee.exe"], [], True),
    (["Microsoft.Media.Player.exe"], [], True),
    (["chrome.exe"], ["Blinding Lights - YouTube Music - Google Chrome"], True),
    (["firefox.instance_1234"], ["Starboy • The Weeknd — Mozilla Firefox"], True),   # the Spotify web player
    (["msedge.exe"], ["Lofi beats | SoundCloud - Microsoft Edge"], True),
    (["chrome.exe"], ["How to cook rice - YouTube - Google Chrome"], False),    # a video isn't music
    (["vlc.exe"], [], False),
    (["Discord.exe"], [], False),
    ([], ["Song - YouTube Music"], False),                                     # music site open, but silent
    (["deadlock.exe", "Spotify.exe"], [], True),
])
def test_what_counts_as_music(sounding, titles, music):
    assert nd.music_playing(sounding, lambda: titles) is music


def test_titles_are_only_looked_up_for_a_sounding_browser():
    asked = []
    assert nd.music_playing(["Spotify.exe"], lambda: asked.append(1) or []) and not asked
    assert not nd.music_playing(["chrome.exe"], lambda: 1 / 0)                 # a failing lookup isn't music


def test_music_stays_on_between_songs():
    clock = [0.0]
    playing = [["Spotify.exe"]]
    w = nd.MusicWatch(lambda: playing[0], lambda: [], clock=lambda: clock[0])
    assert w.check()
    playing[0] = []
    clock[0] += 10
    assert w.check()                                                           # a gap between songs
    clock[0] += nd.HEARD_FOR
    assert not w.check()


def test_a_broken_sound_system_just_means_no_music():
    def boom():
        raise OSError("no audio")
    assert nd.MusicWatch(boom, lambda: []).check() is False


def test_browser_titles_come_from_browser_windows_only():
    procs = [SimpleNamespace(pid=1, name="chrome.exe", exe="C:/x/chrome.exe"),
             SimpleNamespace(pid=2, name="Discord.exe", exe="C:/x/Discord.exe"),
             SimpleNamespace(pid=3, name="firefox", exe="/usr/lib/firefox/firefox")]
    desktop = SimpleNamespace(windows_for=lambda pids: [p * 10 for p in pids], window_title=lambda w: f"w{w}")
    assert nd.browser_titles(lambda: procs, desktop) == ["w10", "w30"]


def test_game_names_come_from_the_library():
    games = [SimpleNamespace(name="Deadlock", install_dir=Path("/games/steamapps/common/Deadlock"))]
    assert nd.game_title("/games/steamapps/common/Deadlock/game/bin/deadlock", games) == "Deadlock"
    assert nd.game_title("/games/steamapps/common/DeadlockTools/x", games) == ""
    assert nd.game_title("", games) == ""


# -- the watcher ------------------------------------------------------------------------------------------------
def test_status_watch_reports_changes_and_gaming_wins():
    got = []
    gaming, music = [False], [False]
    w = nd.MusicWatch(lambda: ["Spotify.exe"] if music[0] else [], lambda: [])
    s = nd.StatusWatch(lambda *a: got.append(a), lambda: gaming[0], lambda: "Deadlock", w, off_thread=False)
    s.tick()
    assert got == [("", "")]
    s.tick()
    assert got == [("", "")]                                                   # unchanged: not reported again
    music[0] = True
    s.tick()
    gaming[0] = True
    s.tick()
    assert got[1:] == [("music", ""), ("gaming", "Deadlock")]


def test_status_watch_checks_windows_sound_off_the_main_thread():
    import threading
    got, threads = [], []
    main = threading.current_thread()

    def sounding():
        threads.append(threading.current_thread())
        return ["Spotify.exe"]
    s = nd.StatusWatch(lambda *a: got.append(a), lambda: False, lambda: "", nd.MusicWatch(sounding, lambda: []),
                       off_thread=True)
    s.tick()
    end = time.time() + 3
    while time.time() < end and ("music", "") not in got:
        app.processEvents()
        time.sleep(0.01)
    assert ("music", "") in got and threads and threads[0] is not main


def test_status_watch_rests_while_discord_status_is_off():
    got = []
    s = nd.StatusWatch(lambda *a: got.append(a), lambda: True, lambda: "", None, off_thread=False,
                       wanted=lambda: False)
    s.tick()
    assert got == []


# -- Linux: real D-Bus with stand-in media players -----------------------------------------------------------------
FAKE_PLAYER = textwrap.dedent('''
    import sys
    from PySide6.QtCore import QCoreApplication, QObject, Property, ClassInfo
    from PySide6.QtDBus import QDBusConnection, QDBusAbstractAdaptor
    app = QCoreApplication([])

    @ClassInfo({"D-Bus Interface": "org.mpris.MediaPlayer2.Player"})
    class Player(QDBusAbstractAdaptor):
        def _status(self):
            return sys.argv[2]
        PlaybackStatus = Property(str, _status)

    obj = QObject()
    Player(obj)
    bus = QDBusConnection.sessionBus()
    bus.registerObject("/org/mpris/MediaPlayer2", obj, QDBusConnection.RegisterOption.ExportAdaptors)
    bus.registerService("org.mpris.MediaPlayer2." + sys.argv[1])
    print("ready", flush=True)
    app.exec()
''')


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("dbus-daemon"), reason="Linux D-Bus")
def test_linux_media_players_over_dbus(tmp_path):
    from PySide6.QtDBus import QDBusConnection
    daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address"], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True)
    players = []
    try:
        address = daemon.stdout.readline().strip()
        script = tmp_path / "player.py"
        script.write_text(FAKE_PLAYER)
        env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address, QT_QPA_PLATFORM="offscreen")
        for name, status in (("spotify", "Playing"), ("vlc", "Paused"), ("firefox.instance_7", "Playing")):
            players.append(subprocess.Popen([sys.executable, str(script), name, status], env=env,
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True))
        for pl in players:
            assert pl.stdout.readline().strip() == "ready"
        bus = QDBusConnection.connectToBus(address, "capri-test-bus")
        assert bus.isConnected()
        assert sorted(nd.linux_sounding(bus)) == ["firefox.instance_7", "spotify"]
        QDBusConnection.disconnectFromBus("capri-test-bus")
    finally:
        for pl in players:
            pl.kill()
        daemon.kill()


# -- Windows: the sound mixer's sessions (stand-ins for Windows' own objects) ----------------------------------
class FakeSession:
    def __init__(self, state, pid, peak):
        self.state, self.pid, self.peak = state, pid, peak

    def GetState(self):
        return self.state

    def QueryInterface(self, iface):
        return self

    def GetProcessId(self):
        return self.pid

    def GetPeakValue(self):
        return self.peak


def test_windows_sessions_only_count_apps_making_sound():
    sessions = [FakeSession(1, 101, 0.3), FakeSession(0, 102, 0.3), FakeSession(1, 103, 0.0),
                FakeSession(1, os.getpid(), 0.5), FakeSession(1, 0, 0.5)]
    fake_sessions = SimpleNamespace(GetSession=lambda i: sessions[i])
    psutil = SimpleNamespace(Process=lambda pid: SimpleNamespace(name=lambda: {101: "Spotify.exe"}.get(pid, "x.exe")))
    com = {"Control2": object(), "Meter": object()}
    found = [nd._session_app(fake_sessions, i, com, os.getpid(), psutil) for i in range(len(sessions))]
    assert found == ["Spotify.exe", "", "", "", ""]      # playing; paused; silent; Capri herself; system sounds


def test_windows_session_errors_are_skipped():
    broken = SimpleNamespace(GetSession=lambda i: 1 / 0)
    assert nd._session_app(broken, 0, {}, 1, None) == ""
