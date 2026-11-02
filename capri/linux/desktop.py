"""Capri on Linux: the same jobs as commands/desktop.py and commands/system.py do on Windows.

* Windows of other apps, typing, key presses: linux/x11.py (X11 / XWayland).
* Power: systemd's own commands (systemctl / loginctl) - fixed argument lists, never a shell, and
  shut down / restart / sleep still only happen after your spoken "yes" (see the router).
* Media keys: playerctl / wpctl / pactl when installed (they work everywhere, Wayland too),
  otherwise the keyboard's media keys through X11.
* Apps: started from their menu entries (linux/apps.py) or directly, detached from Capri; closed
  like clicking X (the window manager's close), and only after that, if you say so, by force.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from ..commands.system import PROTECTED, ProcessInfo
from . import x11 as x11mod

# Never close these on Linux, whatever was said: the desktop itself, sound, the session.
LINUX_PROTECTED = {
    "systemd", "init", "xorg", "x", "xwayland", "gnome-shell", "gnome-session-binary", "plasmashell", "kwin_x11",
    "kwin_wayland", "mutter", "xfwm4", "xfce4-panel", "xfdesktop", "openbox", "i3", "sway", "hyprland", "weston",
    "pipewire", "pipewire-pulse", "wireplumber", "pulseaudio", "dbus-daemon", "dbus-broker", "gdm", "sddm",
    "lightdm", "polkitd", "at-spi-bus-launcher", "at-spi2-registryd", "ibus-daemon", "fcitx5", "bash", "zsh",
    "fish", "sh", "login", "sshd", "nautilus-desktop", "cinnamon", "marco", "budgie-wm", "capri", "apprun",
    "python3", "python",
}

POWER_COMMANDS = {
    "shutdown": [["systemctl", "poweroff"], ["loginctl", "poweroff"]],
    "restart": [["systemctl", "reboot"], ["loginctl", "reboot"]],
    "sleep": [["systemctl", "suspend"], ["loginctl", "suspend"]],
    "lock": [["loginctl", "lock-session"], ["xdg-screensaver", "lock"],
             ["gdbus", "call", "--session", "--dest", "org.freedesktop.ScreenSaver", "--object-path",
              "/org/freedesktop/ScreenSaver", "--method", "org.freedesktop.ScreenSaver.Lock"]],
}

# media key -> commands to try (fixed), then the X11 media key.
MEDIA_COMMANDS = {
    "play_pause": [["playerctl", "play-pause"]],
    "next": [["playerctl", "next"]],
    "previous": [["playerctl", "previous"]],
    "volume_up": [["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "10%+"],
                  ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], ["amixer", "-q", "set", "Master", "10%+"]],
    "volume_down": [["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%-"],
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], ["amixer", "-q", "set", "Master", "10%-"]],
    "mute": [["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
             ["amixer", "-q", "set", "Master", "toggle"]],
}
MEDIA_KEYSYMS = {"play_pause": "XF86AudioPlay", "next": "XF86AudioNext", "previous": "XF86AudioPrev",
                 "volume_up": "XF86AudioRaiseVolume", "volume_down": "XF86AudioLowerVolume", "mute": "XF86AudioMute"}


def _run_first(commands: list[list[str]], run: Callable = subprocess.run, timeout: float = 10.0) -> bool:
    """Run the first of these fixed commands that's installed and works. True if one did."""
    for argv in commands:
        exe = shutil.which(argv[0])
        if not exe:
            continue
        try:
            result = run([exe, *argv[1:]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, timeout=timeout)
            if getattr(result, "returncode", 0) == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def power(action: str, run: Callable = subprocess.run) -> None:
    if action not in POWER_COMMANDS:
        raise ValueError(action)
    if not _run_first(POWER_COMMANDS[action], run):
        raise OSError({"lock": "Couldn't lock the screen", "sleep": "Your system wouldn't go to sleep"}.get(
            action, "Your system said no (it may need you to be logged in at the computer)"))


def media(name: str, run: Callable = subprocess.run) -> None:
    if name not in MEDIA_KEYSYMS:
        raise KeyError(name)
    if _run_first(MEDIA_COMMANDS.get(name, []), run, timeout=3.0):
        return
    x = x11mod.shared()
    if x is None:
        raise OSError("install playerctl (and pipewire / pulseaudio tools) for media controls")
    x.press_keysyms([MEDIA_KEYSYMS[name]])


def spotify_play(run: Callable = subprocess.run) -> bool:
    """Spotify on Linux takes orders over MPRIS: press its Play (not play/pause - never pauses a song)."""
    return _run_first([["playerctl", "--player=spotify", "play"]], run, timeout=3.0)


# -- typing on Wayland ---------------------------------------------------------------------------------
def wayland_session() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def wayland_type(text: str, run: Callable = subprocess.run) -> bool:
    """Type into a native Wayland app (X11 can't reach those): wtype (Sway, Hyprland...) or ydotool."""
    text = text.replace("\r", "").replace("\n", " ")       # she never presses Enter
    for argv in (["wtype", "--", text], ["ydotool", "type", "--", text]):
        exe = shutil.which(argv[0])
        if not exe:
            continue
        try:
            if run([exe, *argv[1:]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=30).returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


class LinuxDesktop:
    """commands/desktop.py's Desktop, on Linux. Window ids are X11 window ids."""

    def __init__(self, x: x11mod.X11 | None = None, run: Callable = subprocess.run) -> None:
        self._x = x
        self._run = run
        self._minimized: list[int] = []

    @property
    def x(self) -> x11mod.X11:
        x = self._x or x11mod.shared()
        if x is None:
            raise OSError("no X11 display - start Capri in an X11 session (or with XWayland)")
        return x

    # -- power -------------------------------------------------------------------------------------
    def power(self, action: str) -> None:
        power(action, self._run)

    # -- windows -------------------------------------------------------------------------------------
    def _names(self, pids) -> set[str]:
        """Process names of these pids (sandboxed apps' windows report another pid: match by class)."""
        names = set()
        try:
            import psutil
            for pid in pids:
                try:
                    names.add(psutil.Process(pid).name())
                except psutil.Error:
                    pass
        except ImportError:
            pass
        return names

    def windows_for(self, pids: list[int]) -> list[int]:
        return self.x.windows(set(pids), self._names(pids))

    def _visible(self, pids=None) -> list[int]:
        x = self.x
        names = self._names(pids) if pids is not None else ()
        return x.windows(set(pids) if pids is not None else None, names, include_minimized=False)

    def minimize_all(self) -> int:
        wins = self._visible()
        self._minimized = wins
        for w in wins:
            self.x.minimize(w)
        return len(wins)

    def minimize_foreground(self) -> int:
        active = self.x.active()
        if active and active in self._visible():
            self.x.minimize(active)
            return 1
        return 0

    def minimize(self, pids: list[int]) -> int:
        wins = self._visible(pids)
        for w in wins:
            self.x.minimize(w)
        return len(wins)

    def restore(self) -> int:
        alive = set(self.x.stacking())                   # still open (minimising can still be in progress)
        wins = [w for w in self._minimized if w in alive]
        for w in reversed(wins):                       # back in their old stacking order
            self.x.activate(w, wait=0.2)
        self._minimized = []
        return len(wins)

    def main_window(self, pids: list[int]) -> int | None:
        wins = self._visible(pids)
        return wins[0] if wins else None

    def window_title(self, wid: int) -> str:
        return self.x.title(wid)

    def window_class(self, wid: int) -> str:
        return self.x.wm_class(wid)[1]

    def windows_of_class(self, cls: str) -> list[int]:
        low = cls.lower()
        return [w for w in self.x.windows() if low in {s.lower() for s in self.x.wm_class(w)}]

    def hwnd_rect(self, wid: int) -> tuple[int, int, int, int] | None:
        return self.x.geometry(wid)

    def window_rect(self, pids: list[int]) -> tuple[int, int, int, int] | None:
        for w in self._visible(pids):
            g = self.x.geometry(w)
            if g and g[2] - g[0] > 50 and g[3] - g[1] > 50:
                return g
        return None

    def window_at(self, x: int, y: int) -> int | None:
        return self.x.window_at(x, y)

    def pid_of(self, wid: int) -> int:
        return self.x.pid(wid)

    def foreground(self) -> int:
        return self.x.active()

    def bring_to_front(self, wid: int) -> bool:
        return self.x.activate(wid)

    # -- keys ----------------------------------------------------------------------------------------
    def press_keys(self, combo: str) -> None:
        self.x.press_combo(combo)

    def press_enter(self) -> None:
        self.x.press_keysyms(["Return"])

    def press_in_window(self, pids: list[int], combo: str) -> bool:
        """Bring the app's window up, press the combo, put back what was in front (Discord's keybinds
        only work while Discord has the keyboard)."""
        wins = self.windows_for(pids)
        if not wins:
            return False
        target, before = wins[0], self.x.active()
        was_minimized = self.x.is_minimized(target)
        if not self.x.activate(target):
            return False
        time.sleep(0.05)
        self.x.press_combo(combo)
        time.sleep(0.05)
        if was_minimized:
            self.x.minimize(target)
        if before and before != target:
            self.x.activate(before, wait=0.3)
        return True

    def type_text(self, text: str) -> None:
        """Type into whatever has the keyboard."""
        x = x11mod.shared() if self._x is None else self._x
        active = x.active() if x is not None else 0
        if (x is None or not active) and wayland_session():
            if wayland_type(text, self._run):
                return
            raise OSError("typing into Wayland apps needs wtype or ydotool (or log in with an X11 session)")
        if x is None:
            raise OSError("no X11 display to type into")
        if x.type_text(text) == 0 and text.strip():
            raise OSError("the key presses didn't go through")

    def type_into(self, wid: int, text: str) -> str:
        if not self.x.activate(wid):
            return "no_focus"
        time.sleep(0.15)
        if self.x.active() != wid:
            return "no_focus"
        return "keys" if self.x.type_text(text) or not text.strip() else "blocked"


class LinuxSystem:
    """commands/system.py's System, on Linux."""

    def __init__(self, popen: Callable = subprocess.Popen, desktop: LinuxDesktop | None = None) -> None:
        self._popen = popen
        self._desktop = desktop

    @property
    def desktop(self) -> LinuxDesktop:
        if self._desktop is None:
            self._desktop = LinuxDesktop()
        return self._desktop

    def launch_program(self, path: str, args: list[str]) -> None:
        target = Path(os.path.expanduser(path))
        if target.suffix == ".desktop":
            from .apps import launch_desktop_file
            return launch_desktop_file(target, self._popen)
        if not target.exists():
            found = shutil.which(path)
            if not found:
                raise FileNotFoundError(path)
            target = Path(found)
        if target.is_file() and os.access(target, os.X_OK):
            self._popen([str(target), *args], cwd=str(target.parent), start_new_session=True, close_fds=True,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.open_item(str(target))

    def open_item(self, target: str) -> None:
        if target.endswith(".desktop") and os.path.isfile(target):
            from .apps import launch_desktop_file
            return launch_desktop_file(target, self._popen)
        opener = shutil.which("xdg-open") or shutil.which("gio")
        if opener is None:
            raise OSError("xdg-open isn't installed")
        argv = [opener, target] if opener.endswith("xdg-open") else [opener, "open", target]
        self._popen(argv, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def processes(self) -> list[ProcessInfo]:
        import psutil
        me = os.getpid()
        try:
            user = psutil.Process(me).username()
        except psutil.Error:
            user = None
        protected = PROTECTED | LINUX_PROTECTED
        found = []
        for p in psutil.process_iter(["pid", "name", "exe", "username"]):
            info = p.info
            name = info.get("name") or ""
            if info["pid"] == me or name.lower() in protected:
                continue
            if user is not None and info.get("username") != user:
                continue
            found.append(ProcessInfo(info["pid"], name, info.get("exe") or ""))
        return found

    def request_close(self, pids: list[int]) -> int:
        """Like clicking X on each of the app's windows."""
        try:
            wins = self.desktop.windows_for(pids)
        except OSError:
            wins = []
        for w in wins:
            self.desktop.x.close(w)
        if not wins:                                  # no window (tray app): ask the process nicely
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
        return len(wins) or len(pids)

    def terminate(self, pids: list[int]) -> None:
        """Force: ask to quit now, and if it hasn't after 2 seconds, end it."""
        import psutil
        procs = []
        for pid in pids:
            try:
                p = psutil.Process(pid)
                p.terminate()
                procs.append(p)
            except psutil.Error:
                pass

        def finish() -> None:
            _gone, alive = psutil.wait_procs(procs, timeout=2)
            for p in alive:
                try:
                    p.kill()
                except psutil.Error:
                    pass
        threading.Thread(target=finish, daemon=True).start()

    def running(self, pids: list[int]) -> list[int]:
        import psutil
        out = []
        for pid in pids:
            try:
                if psutil.Process(pid).status() != psutil.STATUS_ZOMBIE:
                    out.append(pid)
            except psutil.Error:
                pass
        return out

    def reveal(self, path: str) -> None:
        """Your file manager with the file selected (the freedesktop FileManager1 call every desktop
        supports), else just its folder."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        gdbus = shutil.which("gdbus")
        if gdbus:
            try:
                subprocess.run([gdbus, "call", "--session", "--dest", "org.freedesktop.FileManager1",
                                "--object-path", "/org/freedesktop/FileManager1", "--method",
                                "org.freedesktop.FileManager1.ShowItems", f"['{p.resolve().as_uri()}']", ""],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=True)
                return
            except (OSError, subprocess.SubprocessError):
                pass
        self.open_item(str(p if p.is_dir() else p.parent))


# -- start with your login (XDG autostart) ---------------------------------------------------------------
def autostart_file(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    base = Path(env.get("XDG_CONFIG_HOME") or Path(env.get("HOME") or Path.home()) / ".config")
    return base / "autostart" / "capri.desktop"


def launch_argv() -> list[str]:
    """How to start this Capri: the AppImage, the built app, or from the code (run.sh)."""
    if os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"]]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    root = Path(__file__).resolve().parents[2]
    run_sh = root / "run.sh"
    if run_sh.exists():
        return [str(run_sh)]
    return [sys.executable, "-m", "capri"]


def _exec_quote(arg: str) -> str:
    if not any(c in arg for c in ' \t"`$\\'):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$") + '"'


def desktop_entry_text(argv: list[str], extra: str = "", autostart: bool = False) -> str:
    exec_line = " ".join(_exec_quote(a) for a in argv) + (f" {extra}" if extra else "")
    lines = ["[Desktop Entry]", "Type=Application", "Name=Capri", "GenericName=Desktop companion",
             "Comment=A cyberpunk desktop companion", f"Exec={exec_line}", "Icon=capri", "Terminal=false",
             "Categories=Utility;", "StartupNotify=false"]
    if autostart:
        lines += ["X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=3"]
    return "\n".join(lines) + "\n"


def menu_entry_file(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    base = Path(env.get("XDG_DATA_HOME") or Path(env.get("HOME") or Path.home()) / ".local" / "share")
    return base / "applications" / "capri.desktop"


def ensure_menu_entry(icon_png: Path, env: dict | None = None) -> str:
    """AppImage: put Capri in your apps menu (and keep the entry pointing at the AppImage if you move it).
    Returns what it did ("added" / "updated" / "")."""
    env = os.environ if env is None else env
    appimage = env.get("APPIMAGE")
    if not appimage:
        return ""
    entry = menu_entry_file(env)
    text = desktop_entry_text([appimage])
    try:
        old = entry.read_text(encoding="utf-8")
    except OSError:
        old = None
    if old == text:
        return ""
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(text, encoding="utf-8")
    icons = entry.parent.parent / "icons" / "hicolor" / "128x128" / "apps"
    try:
        icons.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_png, icons / "capri.png")
    except OSError:
        pass
    return "added" if old is None else "updated"
