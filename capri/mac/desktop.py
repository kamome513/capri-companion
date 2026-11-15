"""Capri on macOS: the same jobs as commands/desktop.py and commands/system.py do on Windows (and linux/desktop.py
on Linux).

* Other apps' windows, key presses, typing: Quartz events and the Accessibility API (mac/quartz.py). macOS asks
  you once to allow Capri under System Settings > Privacy & Security > Accessibility.
* Power: the Mac's own System Events (shut down / restart) and pmset (sleep) - fixed commands, never a shell,
  and they still only happen after your spoken "yes" (see the router).
* Apps: .app bundles (mac/apps.py), opened with `open`; closed the Mac way - asked to quit, like Cmd+Q - and only
  after that, if you say so, by force.
* "Minimise everything" hides your apps (like Option-clicking the desktop), and brings them back after.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from ..commands.system import PROTECTED, ProcessInfo
from . import quartz

# Never close these on a Mac, whatever was said.
MAC_PROTECTED = {
    "kernel_task", "launchd", "windowserver", "loginwindow", "dock", "finder", "systemuiserver", "controlcenter",
    "notificationcenter", "coreaudiod", "spotlight", "universalaccessd", "securityd", "cfprefsd", "distnoted",
    "capri", "python", "python3", "python3.12", "bash", "zsh", "sh", "login", "sshd", "airplayuxagent",
}

POWER_COMMANDS = {
    "shutdown": [["osascript", "-e", 'tell application "System Events" to shut down']],
    "restart": [["osascript", "-e", 'tell application "System Events" to restart']],
    "sleep": [["pmset", "sleepnow"]],
    "lock": [["osascript", "-e", 'tell application "System Events" to keystroke "q" using {control down, '
                                 'command down}'], ["pmset", "displaysleepnow"]],
}


def _run_first(commands: list[list[str]], run: Callable = subprocess.run, timeout: float = 10.0) -> bool:
    for argv in commands:
        exe = shutil.which(argv[0]) or (f"/usr/bin/{argv[0]}" if os.path.exists(f"/usr/bin/{argv[0]}") else None)
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
        raise OSError("your Mac said no (Capri may need permission to control System Events)")


def media(name: str) -> None:
    if name not in quartz.MEDIA:
        raise KeyError(name)
    if not quartz.media_key(name):
        raise OSError("the media key didn't go through")


def spotify_play(run: Callable = subprocess.run) -> bool:
    """Spotify on a Mac: press its Play (not play/pause - never pauses a song)."""
    return _run_first([["osascript", "-e", 'if application "Spotify" is running then tell application "Spotify" '
                                         'to play']], run, timeout=4.0)


def _need_permission() -> OSError:
    return OSError("Capri needs permission for that: System Settings > Privacy & Security > Accessibility "
                   "(turn Capri on)")


class MacDesktop:
    """commands/desktop.py's Desktop, on a Mac. Window ids are the system's window numbers."""

    def __init__(self, run: Callable = subprocess.run) -> None:
        self._run = run
        self._hidden: list = []

    def power(self, action: str) -> None:
        power(action, self._run)

    # -- windows -------------------------------------------------------------------------------------------------
    def _wins(self) -> list[dict]:
        try:
            me = os.getpid()
            return [w for w in quartz.windows() if w["pid"] != me]
        except Exception:
            return []

    def _win(self, wid: int) -> dict | None:
        return next((w for w in self._wins() if w["id"] == wid), None)

    def windows_for(self, pids: list[int]) -> list[int]:
        want = set(pids)
        return [w["id"] for w in self._wins() if w["pid"] in want]

    def minimize_all(self) -> int:
        """Hide every app (the Mac's "show desktop"); restore() brings them back."""
        me = os.getpid()
        apps = [a for a in quartz.regular_apps() if int(a.processIdentifier()) != me and not a.isHidden()
                and str(a.localizedName() or "") != "Finder"]
        for a in apps:
            a.hide()
        self._hidden = apps
        return len(apps)

    def minimize_foreground(self) -> int:
        pid = quartz.frontmost_pid()
        if not pid or pid == os.getpid():
            return 0
        front = next((w for w in self._wins() if w["pid"] == pid), None)
        win = quartz.ax_window_for(pid, front["rect"] if front else None)
        if win is None:
            raise _need_permission()
        return 1 if quartz.ax_set_minimized(win, True) else 0

    def minimize(self, pids: list[int]) -> int:
        n = 0
        for pid in set(pids):
            app = quartz.running_app(pid)
            if app is not None and app.hide():
                n += 1
        return n

    def restore(self) -> int:
        apps, self._hidden = self._hidden, []
        for a in apps:
            try:
                a.unhide()
            except Exception:
                pass
        return len(apps)

    def main_window(self, pids: list[int]) -> int | None:
        wins = self.windows_for(pids)
        return wins[0] if wins else None

    def window_title(self, wid: int) -> str:
        w = self._win(wid)
        return (w["title"] or w["owner"]) if w else ""

    def window_class(self, wid: int) -> str:
        w = self._win(wid)
        return w["owner"] if w else ""

    def windows_of_class(self, cls: str) -> list[int]:
        low = cls.lower()
        return [w["id"] for w in self._wins() if w["owner"].lower() == low]

    def hwnd_rect(self, wid: int) -> tuple[int, int, int, int] | None:
        w = self._win(wid)
        return w["rect"] if w else None

    def window_rect(self, pids: list[int]) -> tuple[int, int, int, int] | None:
        want = set(pids)
        for w in self._wins():
            r = w["rect"]
            if w["pid"] in want and r[2] - r[0] > 50 and r[3] - r[1] > 50:
                return r
        return None

    def window_at(self, x: int, y: int) -> int | None:
        for w in self._wins():                                  # front to back: the first one there
            r = w["rect"]
            if r[0] <= x < r[2] and r[1] <= y < r[3]:
                return w["id"]
        return None

    def pid_of(self, wid: int) -> int:
        w = self._win(wid)
        return w["pid"] if w else 0

    def foreground(self) -> int:
        pid = quartz.frontmost_pid()
        front = next((w for w in self._wins() if w["pid"] == pid), None)
        return front["id"] if front else 0

    def bring_to_front(self, wid: int) -> bool:
        w = self._win(wid)
        if w is None:
            return False
        ok = quartz.activate(w["pid"])
        try:
            win = quartz.ax_window_for(w["pid"], w["rect"])
            if win is not None:
                quartz.ax_raise(win)
        except Exception:
            pass
        return ok

    # -- keys ----------------------------------------------------------------------------------------------------
    def press_keys(self, combo: str) -> None:
        if not quartz.press_combo(combo):
            raise OSError(f"don't know the keys {combo!r}")

    def press_enter(self) -> None:
        quartz.press_combo("return")

    def press_in_window(self, pids: list[int], combo: str) -> bool:
        """Bring the app up, press the combo, give the keyboard back to what had it."""
        target = next(iter(pids), 0)
        before = quartz.frontmost_pid()
        if not target or not quartz.activate(target):
            return False
        time.sleep(0.12)
        ok = quartz.press_combo(combo)
        time.sleep(0.05)
        if before and before != target:
            quartz.activate(before)
        return ok

    def type_text(self, text: str) -> None:
        if not quartz.trusted():
            raise _need_permission()
        if quartz.type_text(text) == 0 and text.strip():
            raise OSError("the key presses didn't go through")

    def type_into(self, wid: int, text: str) -> str:
        if not self.bring_to_front(wid):
            return "no_focus"
        time.sleep(0.2)
        w = self._win(wid)
        if w is None or quartz.frontmost_pid() != w["pid"]:
            return "no_focus"
        if not quartz.trusted():
            return "blocked"
        return "keys" if quartz.type_text(text) or not text.strip() else "blocked"


class MacSystem:
    """commands/system.py's System, on a Mac."""

    def __init__(self, popen: Callable = subprocess.Popen, desktop: MacDesktop | None = None) -> None:
        self._popen = popen
        self._desktop = desktop

    @property
    def desktop(self) -> MacDesktop:
        if self._desktop is None:
            self._desktop = MacDesktop()
        return self._desktop

    def _spawn(self, argv: list[str], cwd: str | None = None) -> None:
        self._popen(argv, cwd=cwd, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def launch_program(self, path: str, args: list[str]) -> None:
        target = Path(os.path.expanduser(path))
        if target.suffix == ".app" or (target.is_dir() and (target / "Contents").is_dir()):
            if not target.exists():
                raise FileNotFoundError(path)
            return self._spawn(["open", "-a", str(target)] + (["--args", *args] if args else []))
        if not target.exists():
            found = shutil.which(path)
            if not found:
                return self._spawn(["open", "-a", path])           # an app by its name ("Discord")
            target = Path(found)
        if target.is_file() and os.access(target, os.X_OK):
            self._spawn([str(target), *args], cwd=str(target.parent))
        else:
            self.open_item(str(target))

    def open_item(self, target: str) -> None:
        """Files, folders, web links and app links (spotify:, steam://...) - what double-clicking does."""
        self._spawn(["open", target])

    def processes(self) -> list[ProcessInfo]:
        import psutil
        me = os.getpid()
        try:
            user = psutil.Process(me).username()
        except psutil.Error:
            user = None
        protected = PROTECTED | MAC_PROTECTED
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
        """Ask each app to quit, like Cmd+Q (it can still ask you to save)."""
        n = 0
        for pid in pids:
            app = None
            try:
                app = quartz.running_app(pid)
            except Exception:
                pass
            if app is not None and app.terminate():
                n += 1
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                n += 1
            except OSError:
                pass
        return n

    def terminate(self, pids: list[int]) -> None:
        """Force: quit now, and if it hasn't after 2 seconds, end it."""
        import psutil
        procs = []
        for pid in pids:
            try:
                app = quartz.running_app(pid)
                if app is not None:
                    app.forceTerminate()
            except Exception:
                pass
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
        """Finder, with the file selected."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        self._spawn(["open", "-R", str(p)])


# -- start at login (a LaunchAgent) -----------------------------------------------------------------------------------
AGENT_ID = "com.capri.companion"


def agent_file(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{AGENT_ID}.plist"


def launch_argv() -> list[str]:
    """How to start this Capri: the app (Capri.app), or from the code."""
    import sys
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        app = next((p for p in exe.parents if p.suffix == ".app"), None)
        return ["/usr/bin/open", "-a", str(app)] if app is not None else [str(exe)]
    root = Path(__file__).resolve().parents[2]
    run_sh = root / "run.sh"
    if run_sh.exists():
        return ["/bin/bash", str(run_sh)]
    return [sys.executable, "-m", "capri"]


def agent_text(argv: list[str]) -> str:
    import plistlib
    return plistlib.dumps({"Label": AGENT_ID, "ProgramArguments": list(argv), "RunAtLoad": True,
                           "ProcessType": "Interactive"}).decode("utf-8")
