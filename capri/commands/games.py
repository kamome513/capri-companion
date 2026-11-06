"""Game mode: while you play, Capri turns into her little flying disk - and back once the game
has closed.

Two ways in:
* she launches a game ("play deadlock"): she watches for the game's own processes (anything
  running from its install folder); if they never show up she turns back after a few minutes;
* you start a game yourself: every few seconds she looks at the window in front (just that
  one - a cheap check). It's a game if it runs from a game library (Steam, Epic, Riot, Xbox,
  GOG, EA, Ubisoft, Rockstar...), if Windows reports a full-screen Direct3D game, or if it's a
  full-screen window of something that isn't a browser / video player / Office / Discord...
  (that last one has to stay in front for two checks in a row). She stays a drone until that
  game's process ends, even while you alt-tab.

"Normal mode" works anytime; if you say it during a game she leaves that game alone.
Settings: the menu's "Drone mode in games" turns all of this off.
"""

from __future__ import annotations

import ntpath
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

CHECK_SECONDS = 5.0
SCAN_SECONDS = 4.0         # looking at the window in front
NEVER_STARTED = 180.0      # no game process by then: back to normal
GONE_CHECKS = 2            # game processes missing this many checks in a row = it closed

GAME_FOLDERS = ("\\steamapps\\common\\", "\\epic games\\", "\\riot games\\", "\\xboxgames\\", "\\gog games\\",
                "\\gog galaxy\\games\\", "\\ea games\\", "\\electronic arts\\", "\\ubisoft game launcher\\games\\",
                "\\rockstar games\\", "\\battle.net\\games\\", "\\blizzard\\", "\\roblox\\versions\\",
                "\\minecraft\\", "\\.minecraft\\", "\\minecraft launcher\\", "microsoft.4297127d64ec6_",
                "\\itch\\apps\\",
                # Roblox started through a bootstrapper lives in the bootstrapper's own folder (2.3.4: with Bloxstrap
                # she never noticed you were playing, so Discord didn't say "Roblox with Capri")
                "\\bloxstrap\\versions\\", "\\fishstrap\\versions\\", "\\voidstrap\\versions\\",
                "\\windowsapps\\robloxcorporation")
# Games whose program has a name of its own (RobloxPlayerBeta.exe is "Roblox")
GAME_NAMES = {"robloxplayerbeta": "Roblox", "windows10universal": "Roblox", "javaw": "Minecraft",
              "minecraft.windows": "Minecraft", "project8": "Deadlock", "cs2": "Counter-Strike 2",
              "valorant-win64-shipping": "VALORANT", "fortniteclient-win64-shipping": "Fortnite",
              "r5apex": "Apex Legends", "r5apex_dx12": "Apex Legends", "league of legends": "League of Legends",
              "rocketleague": "Rocket League", "gta5": "GTA V", "gta5_enhanced": "GTA V", "overwatch": "Overwatch 2",
              "marvel-win64-shipping": "Marvel Rivals", "eldenring": "Elden Ring", "dota2": "Dota 2"}
LAUNCHERS = {"steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "riotclientservices.exe",
             "riotclientux.exe", "battle.net.exe", "eadesktop.exe", "upc.exe", "ubisoftconnect.exe",
             "galaxyclient.exe", "rockstarlauncher.exe", "launcher.exe", "robloxplayerlauncher.exe",
             "minecraftlauncher.exe", "xboxpcapp.exe", "gamebar.exe", "crashreporter.exe", "unitycrashhandler64.exe"}
NOT_GAMES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe", "vivaldi.exe",
    "iexplore.exe", "arc.exe", "vlc.exe", "mpc-hc64.exe", "mpc-hc.exe", "mpc-be64.exe", "potplayermini64.exe",
    "potplayer.exe", "wmplayer.exe", "video.ui.exe", "microsoft.media.player.exe", "applicationframehost.exe",
    "netflix.exe", "powerpnt.exe", "winword.exe", "excel.exe", "onenote.exe", "acrord32.exe", "acrobat.exe",
    "code.exe", "devenv.exe", "discord.exe", "spotify.exe", "obs64.exe", "explorer.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe", "lockapp.exe",
    "python.exe", "pythonw.exe", "capri.exe", "taskmgr.exe", "mstsc.exe", "photos.exe", "microsoft.photos.exe",
    "clipchamp.exe", "capcut.exe", "premiere pro.exe", "afterfx.exe", "davinci resolve.exe", "resolve.exe",
} | LAUNCHERS


@dataclass
class Front:
    """The window in front."""
    pid: int
    exe: str                 # full path
    fullscreen: bool = False # covers its whole monitor
    d3d: bool = False        # Windows says: a full-screen Direct3D game is running


# Linux: where games live (Steam's Proton / native games, Lutris, Heroic, itch, Minecraft).
LINUX_GAME_FOLDERS = ("/steamapps/common/", "/games/", "/lutris/", "/heroic/", "/itch/apps/", "/.minecraft/",
                      "/compatdata/", "/.var/app/com.valvesoftware.steam/")
LINUX_NOT_GAMES = {"firefox", "firefox-esr", "chrome", "chromium", "google-chrome", "brave", "vivaldi-bin", "opera",
                   "vlc", "mpv", "totem", "celluloid", "discord", "spotify", "code", "obs", "nautilus", "dolphin",
                   "thunar", "gnome-shell", "plasmashell", "steam", "steamwebhelper", "xdg-desktop-portal",
                   "libreoffice", "soffice.bin", "evince", "okular", "eog", "gwenview", "gimp", "krita", "blender"}


def looks_like_game(front: Front, game_dirs: list[str] = ()) -> str:
    """Why it's a game ("library" / "d3d" / "fullscreen"), or "" if it isn't one."""
    raw = front.exe or ""
    if raw.startswith("/"):                               # Linux
        low = raw.lower()
        name = low.rsplit("/", 1)[-1]
        if not raw or front.pid == os.getpid() or name in LINUX_NOT_GAMES or name in LAUNCHERS:
            return ""
        if any(f in low for f in LINUX_GAME_FOLDERS) or any(raw.startswith(d) for d in game_dirs if d):
            return "library"
        return "fullscreen" if front.fullscreen else ""
    exe = raw.lower()                                     # Windows paths: case doesn't matter
    name = ntpath.basename(exe)
    if not exe or front.pid == os.getpid() or name in LAUNCHERS:
        return ""
    if any(f in exe for f in GAME_FOLDERS) or any(exe.startswith(d) for d in game_dirs):
        return "library"
    if name in NOT_GAMES or "\\windows\\" in exe:
        return ""
    if front.d3d:
        return "d3d"
    if front.fullscreen:
        return "fullscreen"
    return ""


def linux_front() -> Front | None:
    """Linux (X11): the window you're using, its program, and whether it covers its whole screen."""
    from ..linux import x11
    x = x11.shared()
    if x is None:
        return None
    wid = x.active()
    if not wid:
        return None
    pid = x.pid(wid)
    exe = ""
    try:
        import psutil
        exe = psutil.Process(pid).exe() if pid else ""
    except Exception:
        exe = ""
    full = x.is_fullscreen(wid)
    if not full:
        g = x.geometry(wid)
        try:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtCore import QPoint
            screen = QGuiApplication.screenAt(QPoint((g[0] + g[2]) // 2, (g[1] + g[3]) // 2)) if g else None
            if screen is not None and g:
                r, ratio = screen.geometry(), screen.devicePixelRatio()
                full = g[0] <= r.left() * ratio and g[1] <= r.top() * ratio and \
                    g[2] >= (r.right() + 1) * ratio and g[3] >= (r.bottom() + 1) * ratio
        except Exception:
            pass
    return Front(pid, exe, full, False)


def windows_front() -> Front | None:
    """The foreground window's process, and whether it's full screen. (Linux: linux_front.)"""
    if sys.platform.startswith("linux"):
        return linux_front()
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32, kernel32, shell32 = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.shell32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
    exe = ""
    if handle:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            exe = buf.value
        kernel32.CloseHandle(handle)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    monitor = user32.MonitorFromWindow(hwnd, 2)                      # MONITOR_DEFAULTTONEAREST
    full = False
    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        m = info.rcMonitor
        full = rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW"):                        # the desktop itself
            full = False
        if (user32.GetWindowLongW(hwnd, -16) & 0x00C00000) == 0x00C00000:
            full = False                       # has a title bar: a maximised app (auto-hidden taskbar), not a game
    state = ctypes.c_int(0)
    d3d = shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value == 3
    return Front(pid.value, exe, full, d3d)


class GameWatch(QObject):
    _checked = Signal(bool)
    changed = Signal(bool)                  # drone on / off

    def __init__(self, set_drone: Callable[[bool], None], processes: Callable[[], list],
                 enabled: Callable[[], bool] = lambda: True, clock: Callable[[], float] = time.monotonic,
                 front: Callable[[], Front | None] = windows_front,
                 game_dirs: Callable[[], list[str]] = lambda: [],
                 alive: Callable[[int], bool] | None = None, auto: Callable[[], bool] = lambda: True) -> None:
        super().__init__()
        self.set_drone, self.processes, self.enabled, self.clock = set_drone, processes, enabled, clock
        self.front, self.game_dirs, self.auto = front, game_dirs, auto
        self.alive = alive or _pid_alive
        self.active = False
        self.folder: str | None = None
        self.name = ""
        self.pid: int | None = None          # the game she spotted herself (auto)
        self._declined: set[int] = set()     # games you said "normal mode" in
        self._maybe: int | None = None       # full-screen something, seen once
        self._seen = False
        self._missing = 0
        self._started = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(int(CHECK_SECONDS * 1000))
        self._timer.timeout.connect(self._check)
        self._checked.connect(self._on_check)
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(int(SCAN_SECONDS * 1000))
        self._scan_timer.timeout.connect(self.scan)

    def watch(self) -> None:
        """Start looking out for games you start yourself."""
        if self.front is not None:
            self._scan_timer.start()

    def started(self, name: str, folder: Path | str | None) -> None:
        """A game was just launched."""
        if not self.enabled():
            return
        self.name = name
        self.folder = os.path.normcase(str(folder)) + os.sep if folder else None
        self._seen, self._missing, self._started = False, 0, self.clock()
        self._go(True)
        self._timer.start()

    def stop(self) -> None:
        """Back to normal (the game closed, or you said so)."""
        self._timer.stop()
        if self.pid is not None and self.alive(self.pid):
            self._declined.add(self.pid)                 # you said "normal mode" mid-game: leave this one be
        self.pid = None
        if self.active:
            self._go(False)

    def _go(self, on: bool) -> None:
        self.active = on
        self.set_drone(on)
        self.changed.emit(on)

    # -- spotting a game in front ---------------------------------------------------------------
    def scan(self) -> None:
        if self.pid is not None:                          # in a game she spotted: is it still running?
            if not self.alive(self.pid):
                self.pid = None
                if self.active:
                    self._go(False)
            return
        if self.active or not (self.enabled() and self.auto()):
            return
        try:
            front = self.front()
        except Exception:
            return
        if front is None or front.pid in self._declined:
            self._maybe = None
            return
        why = looks_like_game(front, [d.lower() for d in self.game_dirs()])
        if why == "fullscreen" and self._maybe != front.pid:
            self._maybe = front.pid                       # full screen once could be anything: check again
            return
        self._maybe = None
        if why:
            self.pid, self.name = front.pid, Path(front.exe).stem
            self._go(True)
        self._declined = {p for p in self._declined if self.alive(p)}

    # -- a game she launched ----------------------------------------------------------------------
    def running(self) -> bool:
        if self.folder is None:
            return False
        return any(p.exe and os.path.normcase(p.exe).startswith(self.folder) for p in self.processes())

    def _check(self) -> None:
        threading.Thread(target=lambda: self._checked.emit(self.running()), daemon=True).start()

    def _on_check(self, running: bool) -> None:
        if not self.active or self.pid is not None:
            return
        if running:
            self._seen, self._missing = True, 0
        elif self._seen:
            self._missing += 1
            if self._missing >= GONE_CHECKS:
                self.stop()
        elif self.clock() - self._started > NEVER_STARTED:
            self.stop()


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return False
