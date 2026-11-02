"""Starting and stopping programs on Windows - the only module that does either.

* Launching never goes through a shell: programs start with an argument list,
  shortcuts / links via the Windows "open" verb (os.startfile).
* Closing only ever touches *your own* processes, never Windows itself, and
  never Capri.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Never close these, whatever was said.
PROTECTED = {
    "system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "shellexperiencehost.exe", "textinputhost.exe", "securityhealthsystray.exe", "audiodg.exe",
    "conhost.exe", "dllhost.exe", "lockapp.exe", "logonui.exe", "taskmgr.exe", "msmpeng.exe",
    "python.exe", "pythonw.exe", "capri.exe",
}


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe: str = ""


class System(Protocol):
    def launch_program(self, path: str, args: list[str]) -> None: ...
    def open_item(self, target: str) -> None: ...
    def processes(self) -> list[ProcessInfo]: ...
    def request_close(self, pids: list[int]) -> int: ...
    def terminate(self, pids: list[int]) -> None: ...
    def running(self, pids: list[int]) -> list[int]: ...
    def reveal(self, path: str) -> None: ...


class WindowsSystem:
    def launch_program(self, path: str, args: list[str]) -> None:
        exe = Path(path)
        if not exe.exists():
            raise FileNotFoundError(path)
        if exe.suffix.lower() == ".exe":
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([str(exe), *args], cwd=str(exe.parent), shell=False, close_fds=True,
                             creationflags=flags, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.open_item(str(exe))   # .lnk, .url, documents: Windows' own "open"

    def open_item(self, target: str) -> None:
        if sys.platform == "win32":
            os.startfile(target)   # noqa: S606 - the Windows "open" verb, no shell
        else:
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def processes(self) -> list[ProcessInfo]:
        import psutil
        me = os.getpid()
        try:
            user = psutil.Process(me).username()
        except psutil.Error:
            user = None
        found = []
        for p in psutil.process_iter(["pid", "name", "exe", "username"]):
            info = p.info
            name = info.get("name") or ""
            if info["pid"] == me or name.lower() in PROTECTED:
                continue
            if user is not None and info.get("username") != user:
                continue   # other users' and system processes are off-limits
            found.append(ProcessInfo(info["pid"], name, info.get("exe") or ""))
        return found

    def request_close(self, pids: list[int]) -> int:
        """Politely ask: send WM_CLOSE to each visible window (same as clicking X)."""
        if sys.platform != "win32" or not pids:
            return 0
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        wanted, windows = set(pids), []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in wanted and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):
                windows.append(hwnd)   # visible, top-level, not owned by another window
            return True

        user32.EnumWindows(collect, 0)
        for hwnd in windows:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
        return len(windows)

    def terminate(self, pids: list[int]) -> None:
        import psutil
        for pid in pids:
            try:
                psutil.Process(pid).terminate()
            except psutil.Error:
                pass

    def running(self, pids: list[int]) -> list[int]:
        import psutil
        return [pid for pid in pids if psutil.pid_exists(pid)]

    def reveal(self, path: str) -> None:
        """Open File Explorer with this file or folder selected (Windows' own
        SHOpenFolderAndSelectItems - no command line involved)."""
        if not Path(path).exists():
            raise FileNotFoundError(path)
        if sys.platform != "win32":
            return self.open_item(str(Path(path).parent))
        import ctypes
        shell32 = ctypes.windll.shell32
        ctypes.windll.ole32.CoInitialize(None)
        shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        pidl = shell32.ILCreateFromPathW(ctypes.c_wchar_p(str(Path(path))))
        if not pidl:
            return self.open_item(str(Path(path).parent))
        try:
            if shell32.SHOpenFolderAndSelectItems(ctypes.c_void_p(pidl), 0, None, 0) != 0:
                self.open_item(str(Path(path).parent))
        finally:
            shell32.ILFree(ctypes.c_void_p(pidl))
