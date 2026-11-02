"""Start-with-Windows via the per-user Run key (no admin rights needed).

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Capri
The registry itself is the source of truth, so the setting can't drift out
of sync with what Windows will actually do.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Capri"

SUPPORTED = sys.platform == "win32"


STARTUP_FLAG = "--startup"   # tells Capri it was started by Windows at sign-in (so: greet you)


def launch_command() -> str:
    if getattr(sys, "frozen", False):            # packaged Capri.exe
        return f'"{sys.executable}" {STARTUP_FLAG}'
    # From source: run the launcher script with pythonw.exe (no console window).
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    launcher = Path(__file__).resolve().parent.parent / "capri_launcher.py"
    return f'"{interpreter}" "{launcher}" {STARTUP_FLAG}'


def current_command() -> str:
    if not SUPPORTED:
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, VALUE_NAME)[0])
    except OSError:
        return ""


def ensure_default(settings) -> str:
    """Start with Windows is on by default: switched on once, on first run. After that
    it's yours (the tray's "Start with Windows" turns it off for good). Also updates an
    entry from an older version so it carries the --startup flag. Returns what it did."""
    if not SUPPORTED:
        return ""
    try:
        if not settings.autostart_default_done:
            settings.autostart_default_done = True
            settings.save()
            if not is_enabled():
                set_enabled(True)
                return "enabled"
        elif is_enabled() and current_command() != launch_command():
            set_enabled(True)                    # moved folder, or an entry without --startup
            return "updated"
    except OSError:
        return "failed"
    return ""


def is_enabled() -> bool:
    if not SUPPORTED:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not SUPPORTED:
        raise RuntimeError("Start with Windows is only available on Windows")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
