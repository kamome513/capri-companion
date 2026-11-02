"""Windows desktop control: power (shut down / restart / sleep / lock), minimising
windows, and pressing Discord's mute / deafen keys.

Every action here is one fixed thing with a hard-coded command - nothing said,
and nothing an AI writes, ever becomes part of a command line. Shut down,
restart and sleep are only reached after a spoken "yes" (see the router).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol

from ..hotkeys import parse as parse_hotkey

POWER_ACTIONS = ("shutdown", "restart", "sleep", "lock")
# shutdown.exe, always from System32 (never whatever "shutdown" is on PATH), with fixed arguments.
SHUTDOWN_ARGS = {"shutdown": ["/s", "/t", "0"], "restart": ["/r", "/t", "0"]}
DISCORD_EXES = {"discord.exe", "discordptb.exe", "discordcanary.exe"}
# Discord's own default keybinds. They only work while Discord is the window in front.
DISCORD_DEFAULT_KEYS = {"mute": "ctrl+shift+m", "deafen": "ctrl+shift+d"}

VK_MODIFIERS = {0x0001: 0x12, 0x0002: 0x11, 0x0004: 0x10, 0x0008: 0x5B}   # alt, ctrl, shift, win
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SW_MINIMIZE, SW_RESTORE = 6, 9
WS_MINIMIZEBOX = 0x00020000
WS_EX_TOOLWINDOW = 0x00000080
GW_OWNER = 4
GWL_STYLE, GWL_EXSTYLE = -16, -20
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
# Text boxes she can write into directly: Notepad's (old and Windows 11), WordPad-style rich text boxes.
TEXT_BOX_CLASSES = {"edit", "richedit20w", "richedit20a", "richedit50w", "richeditd2dpt"}
EM_REPLACESEL, WM_GETTEXTLENGTH, SMTO_ABORTIFHUNG = 0x00C2, 0x000E, 0x0002


class Desktop(Protocol):
    def power(self, action: str) -> None: ...
    def minimize_all(self) -> int: ...
    def minimize_foreground(self) -> int: ...
    def minimize(self, pids: list[int]) -> int: ...
    def restore(self) -> int: ...
    def press_keys(self, combo: str) -> None: ...
    def press_in_window(self, pids: list[int], combo: str) -> bool: ...
    def bring_to_front(self, hwnd: int) -> bool: ...
    def press_enter(self) -> None: ...
    def type_text(self, text: str) -> None:
        """Type text into whatever has focus, as real key presses (Unicode, so any letter works)."""
        if self._send_keys(text) == 0:
            raise OSError("Windows blocked the key presses")

    def type_into(self, hwnd: int, text: str) -> str:
        """Type text into one app's window. Returns how it went:
        "typed" - written straight into its text box (Notepad and other classic text boxes: works even
                  if Windows won't let the window come to the front),
        "keys" - typed as key presses after bringing the window to the front (Discord, browsers...),
        "no_focus" - the window wouldn't come to the front, so nothing was typed (rather than typing
                  into the wrong window),
        "blocked" - Windows refused the key presses (the app is probably running as administrator)."""
        user32 = self._user32()
        self.bring_to_front(hwnd)                         # so you see it happen
        box = self._text_box(hwnd)
        if box and self._write_into(box, text):
            return "typed"
        if user32.GetForegroundWindow() != hwnd and not self.bring_to_front(hwnd):
            return "no_focus"
        time.sleep(0.15)                                  # a moment for its text box to take the focus
        if user32.GetForegroundWindow() != hwnd:
            return "no_focus"
        return "keys" if self._send_keys(text) else "blocked"

    def _send_keys(self, text: str) -> int:
        """Key presses for each character (UTF-16, so emoji work too). How many Windows accepted."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
        data = text.encode("utf-16-le")
        units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        sent = 0
        for unit in units:
            pair = (INPUT * 2)(INPUT(type=1, u=_U(ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE, 0, 0))),
                               INPUT(type=1, u=_U(ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))))
            sent += user32.SendInput(2, pair, ctypes.sizeof(INPUT))
            time.sleep(0.008)
        return sent

    def _text_box(self, hwnd: int) -> int | None:
        """The window's classic text box (Notepad's page), if it has one: the biggest visible one."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        found: list[tuple[int, int]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(child, _lparam):
            if self.window_class(child).lower() in TEXT_BOX_CLASSES and user32.IsWindowVisible(child):
                r = wintypes.RECT()
                user32.GetWindowRect(child, ctypes.byref(r))
                found.append(((r.right - r.left) * (r.bottom - r.top), child))
            return True

        user32.EnumChildWindows(hwnd, each, 0)
        return max(found)[1] if found else None

    def _write_into(self, box: int, text: str) -> bool:
        """Put the text where the cursor is in a text box (like typing it), then check it's there."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                               wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        user32.SendMessageTimeoutW.restype = ctypes.c_size_t

        def send(msg: int, wparam: int = 0, lparam: int = 0) -> int | None:
            out = ctypes.c_size_t()
            ok = user32.SendMessageTimeoutW(box, msg, wparam, lparam, SMTO_ABORTIFHUNG, 2000, ctypes.byref(out))
            return int(out.value) if ok else None

        before = send(WM_GETTEXTLENGTH)
        buf = ctypes.create_unicode_buffer(text)
        if before is None or send(EM_REPLACESEL, 1, ctypes.addressof(buf)) is None:
            return False
        after = send(WM_GETTEXTLENGTH)
        return after is not None and after > before

    def windows_for(self, pids: list[int]) -> list[int]: ...
    def window_title(self, hwnd: int) -> str: ...
    def window_class(self, hwnd: int) -> str: ...
    def window_rect(self, pids: list[int]) -> tuple[int, int, int, int] | None: ...
    def main_window(self, pids: list[int]) -> int | None: ...
    def windows_of_class(self, cls: str) -> list[int]: ...
    def hwnd_rect(self, hwnd: int) -> tuple[int, int, int, int] | None: ...
    def window_at(self, x: int, y: int) -> int | None: ...
    def pid_of(self, hwnd: int) -> int: ...


def key_sequence(combo: str) -> list[tuple[int, bool]]:
    """'ctrl+shift+m' -> [(ctrl, down), (shift, down), (M, down), (M, up), (shift, up), (ctrl, up)]."""
    flags, vk = parse_hotkey(combo)
    mods = [code for bit, code in VK_MODIFIERS.items() if flags & bit]
    downs = [(m, True) for m in mods] + [(vk, True)]
    return downs + [(code, False) for code, _ in reversed(downs)]


class WindowsDesktop:
    def __init__(self) -> None:
        self._minimized: list[int] = []      # what "minimise everything" hid, for "bring them back"

    # -- power ---------------------------------------------------------------------------
    def power(self, action: str) -> None:
        if action not in POWER_ACTIONS:
            raise ValueError(action)
        if sys.platform != "win32":
            raise OSError("power controls are only available on Windows")
        import ctypes
        if action == "lock":
            if not ctypes.windll.user32.LockWorkStation():
                raise OSError("Windows wouldn't lock")
        elif action == "sleep":
            # SetSuspendState(hibernate=False, force=True, wake_events_disabled=False): plain sleep.
            if not ctypes.windll.powrprof.SetSuspendState(False, True, False):
                raise OSError("Windows wouldn't go to sleep")
        else:
            exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "shutdown.exe"
            subprocess.Popen([str(exe), *SHUTDOWN_ARGS[action]], shell=False, close_fds=True,
                             creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -- windows ---------------------------------------------------------------------------
    def _user32(self):
        if sys.platform != "win32":
            raise OSError("window controls are only available on Windows")
        import ctypes
        return ctypes.windll.user32

    def _app_windows(self, pids: set[int] | None = None) -> list[int]:
        """Normal app windows (what Win+D would hide): visible, top-level, minimisable,
        not tool windows, not the taskbar/desktop, and never Capri's own."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        me, found = os.getpid(), []
        user32.GetWindowLongW.restype = ctypes.c_long

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == me or (pids is not None and pid.value not in pids):
                return True
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
                return True
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not style & WS_MINIMIZEBOX or ex & WS_EX_TOOLWINDOW or not user32.GetWindowTextLengthW(hwnd):
                return True
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value not in SHELL_CLASSES:
                found.append(hwnd)
            return True

        user32.EnumWindows(collect, 0)
        return found

    def _minimize(self, hwnds: list[int]) -> int:
        user32 = self._user32()
        for hwnd in hwnds:
            user32.ShowWindowAsync(hwnd, SW_MINIMIZE)   # async: a frozen app can't hang Capri
        return len(hwnds)

    def minimize_all(self) -> int:
        hwnds = self._app_windows()
        self._minimized = hwnds
        return self._minimize(hwnds)

    def minimize_foreground(self) -> int:
        hwnd = self._user32().GetForegroundWindow()
        return self._minimize([hwnd]) if hwnd and hwnd in self._app_windows() else 0

    def minimize(self, pids: list[int]) -> int:
        return self._minimize(self._app_windows(set(pids)))

    def restore(self) -> int:
        user32 = self._user32()
        hwnds = [h for h in self._minimized if user32.IsWindow(h) and user32.IsIconic(h)]
        for hwnd in reversed(hwnds):                    # back in their old stacking order
            user32.ShowWindowAsync(hwnd, SW_RESTORE)
        self._minimized = []
        return len(hwnds)

    # -- keys (Discord) ------------------------------------------------------------------------
    def press_keys(self, combo: str) -> None:
        """Press a key combo system-wide, e.g. a Discord keybind. Held briefly: Discord
        polls its keybinds and can miss an instant tap."""
        user32 = self._user32()
        for vk, down in key_sequence(combo):
            user32.keybd_event(vk, 0, 0 if down else KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)

    def press_in_window(self, pids: list[int], combo: str) -> bool:
        """Bring the app's window to the front, press the combo, then put back whatever was in front.
        False = no window to press it in (e.g. Discord is closed to the tray)."""
        user32 = self._user32()
        windows = self._app_windows(set(pids))
        minimised = [h for h in self._all_windows(set(pids)) if user32.IsIconic(h)]
        target = (windows or minimised or [None])[0]
        if target is None:
            return False
        before = user32.GetForegroundWindow()
        was_minimised = bool(user32.IsIconic(target))
        if was_minimised:
            user32.ShowWindow(target, SW_RESTORE)
        # Windows only lets the foreground app hand over focus; a tap of Alt satisfies that rule.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(target)
        for _ in range(20):
            if user32.GetForegroundWindow() == target:
                break
            time.sleep(0.02)
        else:
            if was_minimised:
                user32.ShowWindow(target, SW_MINIMIZE)
            return False
        time.sleep(0.05)
        self.press_keys(combo)
        time.sleep(0.05)
        if was_minimised:
            user32.ShowWindow(target, SW_MINIMIZE)
        if before and before != target and user32.IsWindow(before):
            user32.SetForegroundWindow(before)
        return True

    def bring_to_front(self, hwnd: int) -> bool:
        """Restore + focus a window (e.g. Spotify before typing a search into it)."""
        user32 = self._user32()
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.keybd_event(0x12, 0, 0, 0)                 # the Alt tap that lets focus move (see above)
        user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        for _ in range(25):
            if user32.GetForegroundWindow() == hwnd:
                return True
            time.sleep(0.02)
        return False

    def foreground(self) -> int:
        """The window that has the keyboard right now."""
        return int(self._user32().GetForegroundWindow() or 0)

    def press_enter(self) -> None:
        user32 = self._user32()
        user32.keybd_event(0x0D, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)

    def type_text(self, text: str) -> None:
        """Type text into whatever has focus, as real key presses (Unicode, so any letter works)."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        for ch in text:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                event = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, ord(ch), flags, 0, 0)))
                user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
            time.sleep(0.01)

    def windows_for(self, pids: list[int]) -> list[int]:
        """An app's windows: normal visible ones first, then minimised / tray-hidden ones."""
        visible = self._app_windows(set(pids))
        return visible + [h for h in self._all_windows(set(pids)) if h not in visible]

    def window_title(self, hwnd: int) -> str:
        import ctypes
        user32 = self._user32()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def window_class(self, hwnd: int) -> str:
        import ctypes
        buf = ctypes.create_unicode_buffer(128)
        self._user32().GetClassNameW(hwnd, buf, 128)
        return buf.value

    def main_window(self, pids: list[int]) -> int | None:
        found = self._app_windows(set(pids))
        return found[0] if found else None

    def windows_of_class(self, cls: str) -> list[int]:
        """Visible top-level windows of a class, front-most first (e.g. File Explorer's CabinetWClass)."""
        user32 = self._user32()
        found, hwnd = [], user32.FindWindowExW(None, None, cls, None)
        while hwnd:
            if user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            hwnd = user32.FindWindowExW(None, hwnd, cls, None)
        return found

    def hwnd_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        if self._user32().GetWindowRect(hwnd, ctypes.byref(r)):
            return (r.left, r.top, r.right, r.bottom)
        return None

    def window_at(self, x: int, y: int) -> int | None:
        """The app window under a screen point (its top-level window)."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        root = user32.GetAncestor(hwnd, 2) if hwnd else None          # GA_ROOT
        return int(root) if root else None

    def pid_of(self, hwnd: int) -> int:
        import ctypes
        from ctypes import wintypes
        pid = wintypes.DWORD()
        self._user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def window_rect(self, pids: list[int]) -> tuple[int, int, int, int] | None:
        """(left, top, right, bottom) of the app's main visible window, in screen pixels."""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        for hwnd in self._app_windows(set(pids)):
            r = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r)) and r.right - r.left > 50 and r.bottom - r.top > 50:
                return (r.left, r.top, r.right, r.bottom)
        return None

    def _all_windows(self, pids: set[int]) -> list[int]:
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and not user32.GetWindow(hwnd, GW_OWNER) and user32.GetWindowTextLengthW(hwnd):
                found.append(hwnd)
            return True

        user32.EnumWindows(collect, 0)
        return found
