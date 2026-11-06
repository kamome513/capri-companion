"""What you're up to, for her Discord status: gaming, listening to music, or neither.

* Music:
  - Windows: Windows' own sound mixer (the same list as the Volume Mixer) says which apps are making
    sound right now. Sound from a music app (Spotify, iTunes / Apple Music, MusicBee, foobar2000...)
    counts. So does a browser's sound, while one of its windows shows a music site (YouTube Music,
    SoundCloud, the Spotify web player...).
  - Linux: media players report "Playing" over D-Bus (MPRIS - what your desktop's media controls use).
    The same rules apply for browsers.
* Gaming: the game check she already does for drone mode. While you play she steps off Discord, so your
  game is what Discord shows.

Only "is music playing / are you in a game" is used - never song names, never what you listen to.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger("capri")

# Programs that are music players (Windows .exe names and Linux program / MPRIS names, lower case,
# without ".exe").
MUSIC_APPS = {
    "spotify", "itunes", "applemusic", "apple music", "musicbee", "foobar2000", "aimp", "winamp", "tidal",
    "tidal-hifi", "deezer", "amazon music", "amazonmusic", "youtube music", "youtube-music",
    "youtubemusicdesktopapp", "cider", "qobuz", "spotube", "dopamine", "mediamonkey", "clementine",
    "strawberry", "audacious", "rhythmbox", "lollypop", "elisa", "amarok", "cmus", "deadbeef", "quodlibet",
    "ncspot", "spotifyd", "spotify-qt", "amberol", "gapless", "mpd", "musikcube", "music.ui", "zunemusic",
    "microsoft.media.player", "pandora", "plexamp", "feishin", "nuclear", "tauon", "harmonoid", "psst",
    "sayonara", "guayadeque", "juk", "exaile", "gnome-music", "g4music", "shortwave", "goodvibes",
    "kasts", "mopidy", "moc", "mocp", "pithos", "tidal-dl", "soundcloud", "fooyin", "museeks",
}
BROWSERS = {
    "chrome", "msedge", "firefox", "firefox-esr", "firefox-bin", "opera", "opera_gx", "brave", "brave-browser",
    "vivaldi", "vivaldi-bin", "arc", "chromium", "chromium-browser", "google-chrome", "librewolf", "waterfox",
    "floorp", "zen", "zen-bin", "thorium", "yandex", "browser", "plasma-browser-integration", "epiphany",
    "falkon", "midori", "microsoft-edge", "msedgewebview2",
}
# A browser window showing one of these is a music site.
MUSIC_SITES = ("youtube music", "spotify", "soundcloud", "apple music", "deezer", "tidal", "pandora",
               "amazon music", "bandcamp", "audiomack", "qobuz", "napster", "last.fm", "mixcloud",
               "lofi girl", "radio garden", "iheartradio", "tunein", "jiosaavn", "anghami", "boomplay")
SPOTIFY_WEB = re.compile(r"\S.* • \S")        # the Spotify web player while it plays: "Song • Artist"
HEARD_FOR = 25.0                               # seconds: music counts until it's been quiet this long
PEAK = 0.0005                                  # quieter than this is silence


def app_name(name: str) -> str:
    """"Spotify.exe" -> "spotify"; MPRIS "chromium.instance1234" -> "chromium"."""
    low = (name or "").strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    if low.endswith(".exe"):
        low = low[:-4]
    if ".instance" in low:
        low = low.split(".instance", 1)[0]
    return low


def is_music_app(name: str) -> bool:
    n = app_name(name)
    return n in MUSIC_APPS or n.split(".")[0] in MUSIC_APPS


def is_browser(name: str) -> bool:
    n = app_name(name)
    return n in BROWSERS or n.split(".")[0] in BROWSERS


def music_site(titles: Iterable[str]) -> bool:
    for title in titles:
        low = (title or "").lower()
        if any(site in low for site in MUSIC_SITES) or SPOTIFY_WEB.search(title or ""):
            return True
    return False


def music_playing(sounding: Iterable[str], browser_titles: Callable[[], list[str]]) -> bool:
    """`sounding`: the apps making sound right now. Music if one is a music player, or a browser that's on a
    music site."""
    names = [app_name(n) for n in sounding if n]
    if any(is_music_app(n) for n in names):
        return True
    if any(is_browser(n) for n in names):
        try:
            return music_site(browser_titles())
        except Exception:
            return False
    return False


# -- Windows: who's making sound (Core Audio sessions, like the Volume Mixer) -------------------------------
_COM = None


def _com():
    """The few Core Audio interfaces needed, declared once (Windows only)."""
    global _COM
    if _COM is not None:
        return _COM
    from ctypes import HRESULT, POINTER, c_float, c_int, c_uint32, c_void_p, c_wchar_p
    from comtypes import COMMETHOD, GUID, IUnknown

    class IAudioMeterInformation(IUnknown):
        _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        _methods_ = [COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "peak"))]

    class IAudioSessionControl(IUnknown):
        _iid_ = GUID("{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(c_int), "state")),
            COMMETHOD([], HRESULT, "GetDisplayName", (["out"], POINTER(c_wchar_p), "name")),
            COMMETHOD([], HRESULT, "SetDisplayName", (["in"], c_wchar_p, "name"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetIconPath", (["out"], POINTER(c_wchar_p), "path")),
            COMMETHOD([], HRESULT, "SetIconPath", (["in"], c_wchar_p, "path"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetGroupingParam", (["out"], POINTER(GUID), "param")),
            COMMETHOD([], HRESULT, "SetGroupingParam", (["in"], POINTER(GUID), "param"),
                      (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "RegisterAudioSessionNotification", (["in"], c_void_p, "client")),
            COMMETHOD([], HRESULT, "UnregisterAudioSessionNotification", (["in"], c_void_p, "client")),
        ]

    class IAudioSessionControl2(IAudioSessionControl):
        _iid_ = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetSessionIdentifier", (["out"], POINTER(c_wchar_p), "id")),
            COMMETHOD([], HRESULT, "GetSessionInstanceIdentifier", (["out"], POINTER(c_wchar_p), "id")),
            COMMETHOD([], HRESULT, "GetProcessId", (["out"], POINTER(c_uint32), "pid")),
        ]

    class IAudioSessionEnumerator(IUnknown):
        _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_int), "count")),
            COMMETHOD([], HRESULT, "GetSession", (["in"], c_int, "index"),
                      (["out"], POINTER(POINTER(IAudioSessionControl)), "session")),
        ]

    class IAudioSessionManager2(IUnknown):
        _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
        _methods_ = [
            # IAudioSessionManager
            COMMETHOD([], HRESULT, "GetAudioSessionControl", (["in"], POINTER(GUID), "guid"),
                      (["in"], c_uint32, "flags"), (["out"], POINTER(POINTER(IUnknown)), "control")),
            COMMETHOD([], HRESULT, "GetSimpleAudioVolume", (["in"], POINTER(GUID), "guid"),
                      (["in"], c_uint32, "flags"), (["out"], POINTER(POINTER(IUnknown)), "volume")),
            # IAudioSessionManager2
            COMMETHOD([], HRESULT, "GetSessionEnumerator",
                      (["out"], POINTER(POINTER(IAudioSessionEnumerator)), "sessions")),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], POINTER(GUID), "iid"), (["in"], c_uint32, "clsctx"),
                      (["in"], c_void_p, "params"), (["out"], POINTER(POINTER(IUnknown)), "out")),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_int, "flow"), (["in"], c_uint32, "mask"),
                      (["out"], POINTER(POINTER(IUnknown)), "devices")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], c_int, "flow"), (["in"], c_int, "role"),
                      (["out"], POINTER(POINTER(IMMDevice)), "device")),
        ]

    _COM = {
        "CLSID": GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"), "Enumerator": IMMDeviceEnumerator,
        "Manager2": IAudioSessionManager2, "Control2": IAudioSessionControl2, "Meter": IAudioMeterInformation,
    }
    return _COM


def windows_sounding() -> list[str]:
    """Windows: the programs making sound right now through your speakers / headphones (e.g. ["Spotify.exe"]).
    Call from a background thread (COM is set up for it here)."""
    import comtypes
    comtypes.CoInitialize()
    try:
        found, problem = _windows_sessions(), ""
    except Exception as exc:                 # every COM object is let go before COM is shut for this thread
        found, problem = [], str(exc) or type(exc).__name__
    comtypes.CoUninitialize()
    if problem:
        raise OSError(problem)
    return found


def _windows_sessions() -> list[str]:
    import comtypes
    import psutil
    from comtypes import CLSCTX_ALL
    com = _com()
    enum = comtypes.CoCreateInstance(com["CLSID"], com["Enumerator"], CLSCTX_ALL)
    device = enum.GetDefaultAudioEndpoint(0, 1)                    # speakers / headphones, multimedia
    manager = device.Activate(com["Manager2"]._iid_, CLSCTX_ALL, None).QueryInterface(com["Manager2"])
    sessions = manager.GetSessionEnumerator()
    out, me = [], os.getpid()
    for i in range(sessions.GetCount()):
        name = _session_app(sessions, i, com, me, psutil)
        if name:
            out.append(name)
    return out


def _session_app(sessions, i: int, com, me: int, psutil) -> str:
    """The program behind sound session i, if it's making sound right now."""
    try:
        control = sessions.GetSession(i)
        if control.GetState() != 1:                                 # 1 = a stream is playing
            return ""
        pid = control.QueryInterface(com["Control2"]).GetProcessId()
        if not pid or pid == me:
            return ""
        if control.QueryInterface(com["Meter"]).GetPeakValue() <= PEAK:
            return ""
        return psutil.Process(pid).name()
    except Exception:
        return ""


# -- Linux: media players over D-Bus (MPRIS) -------------------------------------------------------------------
def linux_sounding(bus=None) -> list[str]:
    """Linux: media players that say they're playing (e.g. ["spotify", "firefox.instance_1"]).
    Main thread (Qt D-Bus)."""
    from PySide6.QtDBus import QDBusConnection, QDBusInterface
    bus = bus or QDBusConnection.sessionBus()
    if not bus.isConnected():
        return []
    reply = bus.interface().registeredServiceNames()
    names = reply.value() if reply.isValid() else []
    out = []
    for name in names or []:
        if not name.startswith("org.mpris.MediaPlayer2."):
            continue
        props = QDBusInterface(name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", bus)
        props.setTimeout(500)                                        # a stuck player never holds her up
        args = props.call("Get", "org.mpris.MediaPlayer2.Player", "PlaybackStatus").arguments()
        status = args[0].variant() if args and hasattr(args[0], "variant") else (args[0] if args else "")
        if status == "Playing":
            out.append(name[len("org.mpris.MediaPlayer2."):])
    return out


# -- putting it together -----------------------------------------------------------------------------------------
class MusicWatch:
    """"Is music playing?" - checked now and then, and it stays True until it's been quiet for HEARD_FOR
    seconds (the gap between songs isn't "stopped")."""

    def __init__(self, sounding: Callable[[], list[str]], browser_titles: Callable[[], list[str]],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.sounding, self.browser_titles, self.clock = sounding, browser_titles, clock
        self._heard = -1e9
        self._failed = False

    def check(self) -> bool:
        try:
            now_playing = music_playing(self.sounding(), self.browser_titles)
            self._failed = False
        except Exception as exc:                     # no sound system / D-Bus: just "not music"
            if not self._failed:
                log.info("discord presence: can't tell if music is playing (%s)", exc)
            self._failed = True
            now_playing = False
        if now_playing:
            self._heard = self.clock()
        return self.playing

    @property
    def playing(self) -> bool:
        return self.clock() - self._heard < HEARD_FOR


def browser_titles(processes: Callable[[], list], desktop) -> list[str]:
    """Titles of every browser window (to spot a music site)."""
    pids = [p.pid for p in processes() if is_browser(getattr(p, "name", "") or Path(getattr(p, "exe", "")).name)]
    if not pids:
        return []
    return [desktop.window_title(w) for w in desktop.windows_for(pids)]


class GameSeen:
    """"Are you in a game?" - and it stays yes while that game runs, even when you alt-tab out of it.
    active: her game mode is on; front_game: the pid of the game in front right now, or None."""

    def __init__(self, active: Callable[[], bool], front_game: Callable[[], int | None],
                 alive: Callable[[int], bool]) -> None:
        self.active, self.front_game, self.alive = active, front_game, alive
        self.pid: int | None = None

    def __call__(self) -> bool:
        if self.active():
            return True
        pid = self.front_game()
        if pid:
            self.pid = pid
            return True
        if self.pid is not None and self.alive(self.pid):
            return True
        self.pid = None
        return False


def game_title(exe: str, library: list[tuple[str, str]]) -> str:
    """A game's name from its program: the Steam game whose folder it's in ("Deadlock"), else the program's name
    tidied up ("HollowKnight.exe" -> "Hollow Knight")."""
    path = (exe or "").replace("\\", "/")
    low = path.lower()
    for name, folder in sorted(library, key=lambda g: -len(g[1])):
        f = folder.replace("\\", "/").lower().rstrip("/")
        if f and (low.startswith(f + "/") or low == f):
            return name
    stem = re.sub(r"\.(exe|x86_64|x86|bin|sh|app)$", "", path.rsplit("/", 1)[-1], flags=re.I)
    from ..commands.games import GAME_NAMES
    if stem.lower() in GAME_NAMES:                          # "RobloxPlayerBeta.exe" -> "Roblox"
        return GAME_NAMES[stem.lower()]
    tag = re.compile(r"[-_ ](win64|win32|shipping|dx11|dx12|vulkan|x64|game|client|launcher)$", re.I)
    while tag.search(stem):                                 # "VALORANT-Win64-Shipping" -> "VALORANT"
        stem = tag.sub("", stem)
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem).replace("_", " ").replace("-", " ")
    words = " ".join(stem.split())
    return words[:1].upper() + words[1:] if words else ""


def sounding_for_platform() -> Callable[[], list[str]] | None:
    if sys.platform == "win32":
        return windows_sounding
    if sys.platform.startswith("linux"):
        return linux_sounding
    return None


class StatusWatch:
    """Every few seconds: gaming? music? -> report(mode) when it changes ("gaming" / "music" / "").
    Music is checked off the main thread on Windows (the sound mixer can be slow); on Linux it's D-Bus and
    window titles, which belong on the main thread and are quick."""

    EVERY_MS = 5000

    def __init__(self, report: Callable[[str], None], in_game: Callable[[], bool], music: MusicWatch | None,
                 off_thread: bool = sys.platform == "win32", wanted: Callable[[], bool] = lambda: True) -> None:
        from PySide6.QtCore import QObject, QTimer, Signal

        class _Bridge(QObject):
            heard = Signal(bool)
        self.report, self.in_game, self.music = report, in_game, music
        self.off_thread, self.wanted = off_thread, wanted
        self.music_on = False
        self.gaming = False
        self._busy = False
        self._last: str | None = None
        self._bridge = _Bridge()
        self._bridge.heard.connect(self._heard)
        self.timer = QTimer()
        self.timer.setInterval(self.EVERY_MS)
        self.timer.timeout.connect(self.tick)

    def start(self) -> None:
        self.timer.start()
        self.tick()

    def stop(self) -> None:
        self.timer.stop()

    def tick(self) -> None:
        if not self.wanted():
            return
        try:
            self.gaming = bool(self.in_game())
        except Exception:
            self.gaming = False
        if self.music is not None and not self._busy and not self.gaming:
            if self.off_thread:
                import threading
                self._busy = True
                threading.Thread(target=lambda: self._bridge.heard.emit(self.music.check()), daemon=True,
                                 name="capri-music-check").start()
            else:
                self.music_on = self.music.check()
        self._decide()

    def _heard(self, on: bool) -> None:
        self._busy = False
        self.music_on = on
        self._decide()

    def _decide(self) -> None:
        now = "gaming" if self.gaming else "music" if self.music_on else ""
        if now != self._last:
            self._last = now
            self.report(now)
