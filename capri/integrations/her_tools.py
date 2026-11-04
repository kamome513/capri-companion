"""Her tools around your PC:

* Arranging windows: "put Chrome on the left and Discord on the right", "Spotify on the right", "make Steam full
  screen", "Discord and Chrome side by side".
* One app's volume: "turn Discord down", "turn Spotify up", "set Chrome to 30%", "mute Discord" - only that app,
  in the Windows volume mixer (Linux: PulseAudio / PipeWire via pactl).
* Why your game stutters: CPU, memory, disk, the GPU (NVIDIA's own nvidia-smi, if it's there), temperatures, and
  the apps using the most - with the most likely cause first.
* How your internet is: ping (how long a connection takes, a few times: that's the lag) and a short download speed
  test (Cloudflare's public speed test file).

Everything here runs fixed commands / system calls with values she checked - never text from an AI.
"""

from __future__ import annotations

import logging
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from typing import Callable

log = logging.getLogger("capri")

LAYOUTS = ("left", "right", "top", "bottom", "maximize", "center", "top_left", "top_right", "bottom_left",
           "bottom_right", "side_by_side")


# -- arranging windows ---------------------------------------------------------------------------------------------
def layout_rects(work: tuple[int, int, int, int], layout: str, count: int = 1) -> list[tuple[int, int, int, int]]:
    """Where `count` windows go for a layout, inside the work area (left, top, right, bottom) -> [(x, y, w, h)].
    side_by_side splits the screen into equal columns (one per window)."""
    left, top, right, bottom = work
    w, h = right - left, bottom - top
    half_w, half_h = w // 2, h // 2
    if layout == "side_by_side":
        n = max(1, min(4, count))
        col = w // n
        return [(left + i * col, top, col if i < n - 1 else w - col * (n - 1), h) for i in range(n)]
    spots = {
        "left": (left, top, half_w, h), "right": (left + half_w, top, w - half_w, h),
        "top": (left, top, w, half_h), "bottom": (left, top + half_h, w, h - half_h),
        "maximize": (left, top, w, h),
        "center": (left + w // 6, top + h // 8, w * 2 // 3, h * 3 // 4),
        "top_left": (left, top, half_w, half_h), "top_right": (left + half_w, top, w - half_w, half_h),
        "bottom_left": (left, top + half_h, half_w, h - half_h),
        "bottom_right": (left + half_w, top + half_h, w - half_w, h - half_h),
    }
    return [spots.get(layout, spots["maximize"])] * max(1, count)


def _win_work_area(hwnd: int) -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    if not monitor or not user32.GetMonitorInfoW(wintypes.HANDLE(monitor), ctypes.byref(info)):
        return None
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


def _win_place(hwnd: int, rect: tuple[int, int, int, int], maximize: bool) -> bool:
    """Move / size a window on Windows, allowing for the invisible resize border Windows 10/11 add."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    h = wintypes.HWND(hwnd)
    if maximize:
        user32.ShowWindow(h, 3)                                        # SW_MAXIMIZE
        user32.SetForegroundWindow(h)
        return True
    user32.ShowWindow(h, 9)                                            # SW_RESTORE (un-maximise first)
    x, y, w, hgt = rect
    outer, frame = wintypes.RECT(), wintypes.RECT()
    pad = (0, 0, 0, 0)
    if user32.GetWindowRect(h, ctypes.byref(outer)):
        try:
            ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(frame), ctypes.sizeof(frame)) == 0
        except (AttributeError, OSError):
            ok = False
        if ok:                                                          # DWMWA_EXTENDED_FRAME_BOUNDS
            pad = (frame.left - outer.left, frame.top - outer.top, outer.right - frame.right,
                   outer.bottom - frame.bottom)
    ok = user32.SetWindowPos(h, 0, x - pad[0], y - pad[1], w + pad[0] + pad[2], hgt + pad[1] + pad[3],
                             0x0004 | 0x0040)                          # SWP_NOZORDER | SWP_SHOWWINDOW
    user32.SetForegroundWindow(h)
    return bool(ok)


def _x11_place(x11, wid: int, rect: tuple[int, int, int, int], maximize: bool) -> bool:
    """Linux (X11): ask the window manager to un-maximise and move / size the window (or maximise it)."""
    remove, add, toggle = 0, 1, 2  # noqa: F841 - _NET_WM_STATE actions
    try:
        horz, vert = x11.atom("_NET_WM_STATE_MAXIMIZED_HORZ"), x11.atom("_NET_WM_STATE_MAXIMIZED_VERT")
        x11._client_message(wid, "_NET_WM_STATE", [add if maximize else remove, horz, vert, 1])
        if not maximize:
            x, y, w, h = rect
            # _NET_MOVERESIZE_WINDOW: gravity static(10) + x, y, w, h given (bits 8-11), from a normal app (bit 12)
            x11._client_message(wid, "_NET_MOVERESIZE_WINDOW", [10 | (0xF << 8) | (1 << 12), x, y, w, h])
        x11._client_message(wid, "_NET_ACTIVE_WINDOW", [2, 0, 0])
        return True
    except Exception as exc:
        log.info("arrange: X11 didn't take it: %s", exc)
        return False


def place_window(desktop, hwnd: int, rect: tuple[int, int, int, int], maximize: bool = False) -> bool:
    if sys.platform == "win32":
        return _win_place(hwnd, rect, maximize)
    x11 = getattr(desktop, "x", None)
    return _x11_place(x11, hwnd, rect, maximize) if x11 is not None else False


def work_area(desktop, hwnd: int) -> tuple[int, int, int, int] | None:
    """The usable part of the screen the window is on (without the taskbar)."""
    if sys.platform == "win32":
        return _win_work_area(hwnd)
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QGuiApplication
    rect = desktop.hwnd_rect(hwnd) if hasattr(desktop, "hwnd_rect") else None
    screen = None
    if rect:
        screen = QGuiApplication.screenAt(QPoint((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2))
    screen = screen or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    g = screen.availableGeometry()
    return g.left(), g.top(), g.right() + 1, g.bottom() + 1


# -- one app's volume ----------------------------------------------------------------------------------------------
def _clean_exe(name: str) -> str:
    return re.sub(r"\.exe$", "", (name or "").lower())


def _win_app_volume(names: set[str], action: str, percent: int) -> tuple[list[str], int]:
    """Windows volume mixer: change the sessions of these programs. -> (apps changed, their new volume %)."""
    import comtypes
    import psutil
    from ctypes import HRESULT, POINTER, c_float, c_int
    from comtypes import CLSCTX_ALL, COMMETHOD, GUID, IUnknown

    from .now_doing import _com

    class ISimpleAudioVolume(IUnknown):
        _iid_ = GUID("{87CE5498-68D6-44E5-9215-6DA47EF883D8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "SetMasterVolume", (["in"], c_float, "level"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetMasterVolume", (["out"], POINTER(c_float), "level")),
            COMMETHOD([], HRESULT, "SetMute", (["in"], c_int, "mute"), (["in"], POINTER(GUID), "ctx")),
            COMMETHOD([], HRESULT, "GetMute", (["out"], POINTER(c_int), "mute")),
        ]
    comtypes.CoInitialize()
    changed, level = [], -1
    try:
        com = _com()
        enum = comtypes.CoCreateInstance(com["CLSID"], com["Enumerator"], CLSCTX_ALL)
        device = enum.GetDefaultAudioEndpoint(0, 1)
        manager = device.Activate(com["Manager2"]._iid_, CLSCTX_ALL, None).QueryInterface(com["Manager2"])
        sessions = manager.GetSessionEnumerator()
        for i in range(sessions.GetCount()):
            try:
                control = sessions.GetSession(i)
                pid = control.QueryInterface(com["Control2"]).GetProcessId()
                if not pid:
                    continue
                exe = psutil.Process(pid).name()
                if _clean_exe(exe) not in names:
                    continue
                volume = control.QueryInterface(ISimpleAudioVolume)
                now = volume.GetMasterVolume()
                new = new_level(now * 100, action, percent)
                if action == "mute":
                    volume.SetMute(1, None)
                elif action == "unmute":
                    volume.SetMute(0, None)
                else:
                    volume.SetMute(0, None)
                    volume.SetMasterVolume(new / 100.0, None)
                changed.append(exe)
                level = round(new)
            except Exception:
                continue
    finally:
        comtypes.CoUninitialize()
    return changed, level


def new_level(now: float, action: str, percent: int) -> float:
    """The volume after "down" / "up" (a third less / more, at least 10 points) or "set"."""
    if action == "set":
        return float(max(0, min(100, percent)))
    step = max(10.0, now / 3)
    return max(0.0, min(100.0, now - step if action == "down" else now + step if action == "up" else now))


def _pulse_app_volume(names: set[str], action: str, percent: int, run=subprocess.run) -> tuple[list[str], int]:
    """Linux: PulseAudio / PipeWire's per-app streams, with pactl (fixed arguments: stream number and a %)."""
    if not shutil.which("pactl"):
        return [], -1
    out = run(["pactl", "list", "sink-inputs"], capture_output=True, text=True, timeout=5).stdout
    changed, level = [], -1
    for block in out.split("Sink Input #")[1:]:
        index = block.split("\n", 1)[0].strip()
        apps = re.findall(r'application\.(?:name|process\.binary) = "([^"]+)"', block)
        if not index.isdigit() or not any(_clean_exe(a) in names for a in apps):
            continue
        m = re.search(r"Volume:[^\n]*?(\d+)%", block)
        now = float(m.group(1)) if m else 100.0
        if action in ("mute", "unmute"):
            run(["pactl", "set-sink-input-mute", index, "1" if action == "mute" else "0"], timeout=5)
        else:
            new = new_level(now, action, percent)
            run(["pactl", "set-sink-input-mute", index, "0"], timeout=5)
            run(["pactl", "set-sink-input-volume", index, f"{round(new)}%"], timeout=5)
            level = round(new)
        changed.append(apps[0] if apps else index)
    return changed, level


def app_volume(exe_names: list[str], action: str, percent: int = 50) -> tuple[list[str], int]:
    """Change only these programs' volume. action: down | up | set | mute | unmute. -> (apps changed, new %)."""
    names = {_clean_exe(n) for n in exe_names if n}
    if action not in ("down", "up", "set", "mute", "unmute") or not names:
        return [], -1
    if sys.platform == "win32":
        return _win_app_volume(names, action, int(percent))
    return _pulse_app_volume(names, action, int(percent))


# -- why your game stutters ----------------------------------------------------------------------------------------
def gpu_stats(run=subprocess.run) -> dict | None:
    """NVIDIA's own nvidia-smi (if it's installed): load %, temperature, memory used / total (MB)."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = run([exe, "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,name",
                   "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=6).stdout
        load, temp, used, total, name = [p.strip() for p in out.splitlines()[0].split(",")][:5]
        return {"load": float(load), "temp": float(temp), "used": float(used), "total": float(total), "name": name}
    except Exception:
        return None


def lag_report(ps=None, sleep: Callable[[float], None] = time.sleep, run=subprocess.run,
               ping: Callable[[], dict] | None = None) -> str:
    """What's most likely making your game stutter right now, with the numbers."""
    from .pc_stats import _psutil, cpu, memory, nice_name
    ps = ps or _psutil()
    load, cpu_apps = cpu(ps, sleep=sleep)
    used, total, ram_apps = memory(ps)
    ram_pct = 100 * used / total if total else 0
    disk_busy = 0.0
    try:
        a = ps.disk_io_counters()
        sleep(0.5)
        b = ps.disk_io_counters()
        disk_busy = min(100.0, (b.busy_time - a.busy_time) / 5.0) if hasattr(a, "busy_time") else 0.0
    except Exception:
        pass
    gpu = gpu_stats(run)
    temps = []
    try:
        for _name, entries in (ps.sensors_temperatures() or {}).items():
            temps += [e.current for e in entries if getattr(e, "current", 0)]
    except Exception:
        pass
    net = ping() if ping is not None else None
    causes = []
    if load >= 90:
        top = cpu_apps[0] if cpu_apps else None
        causes.append((load, f"your CPU is maxed out ({load:.0f}%)" + (f", mostly {top.name}" if top else "")))
    if ram_pct >= 88:
        top = ram_apps[0] if ram_apps else None
        causes.append((ram_pct, f"your memory is nearly full ({ram_pct:.0f}%)" + (f", {top.name} uses the most"
                                                                                  if top else "")))
    if gpu and gpu["load"] >= 97:
        causes.append((gpu["load"], f"your graphics card is at {gpu['load']:.0f}% - lower the game's graphics "
                                    "settings or frame cap"))
    if gpu and gpu["total"] and gpu["used"] / gpu["total"] > 0.95:
        causes.append((96, "your graphics card's memory is full - lower the texture quality"))
    hot = max(temps) if temps else (gpu["temp"] if gpu else 0)
    if hot >= 90:
        causes.append((hot, f"something's running hot ({hot:.0f}°C) and may be slowing itself down"))
    if disk_busy >= 90:
        causes.append((disk_busy, "your disk is flat out (an update or download?)"))
    if net and net.get("ms") and (net["ms"] > 120 or net.get("jitter", 0) > 40 or net.get("lost")):
        causes.append((80, f"your connection is laggy ({net['ms']:.0f} ms ping"
                           + (f", jumping by {net['jitter']:.0f} ms" if net.get("jitter", 0) > 40 else "")
                           + (", some tries failed" if net.get("lost") else "") + ")"))
    numbers = [f"CPU {load:.0f}%", f"memory {ram_pct:.0f}%"]
    if gpu:
        numbers.append(f"GPU {gpu['load']:.0f}% at {gpu['temp']:.0f}°C")
    if net and net.get("ms"):
        numbers.append(f"ping {_ms(net['ms'])}")
    hogs = [a.name for a in cpu_apps[:3] if a.amount >= 5] if cpu_apps else []
    if not causes:
        line = "Nothing on your PC looks maxed out (" + ", ".join(numbers) + ")."
        if hogs:
            line += " Busiest: " + ", ".join(hogs) + "."
        return line + " If it still stutters, try capping the game's frame rate, or updating your graphics driver."
    causes.sort(key=lambda c: -c[0])
    return ("Most likely " + causes[0][1] + "." + (" Also " + "; ".join(c[1] for c in causes[1:3]) + "."
                                                    if len(causes) > 1 else "")
            + " (" + ", ".join(numbers) + ")")


# -- how your internet is ------------------------------------------------------------------------------------------
PING_HOSTS = (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443))
SPEED_URL = "https://speed.cloudflare.com/__down?bytes=25000000"


def ping(tries: int = 6, connect: Callable | None = None, clock=time.perf_counter) -> dict:
    """How long a connection takes (ms), its jitter and how many tries failed."""
    connect = connect or (lambda addr: socket.create_connection(addr, timeout=2).close())
    times, lost = [], 0
    for i in range(tries):
        host = PING_HOSTS[i % len(PING_HOSTS)]
        start = clock()
        try:
            connect(host)
            times.append((clock() - start) * 1000)
        except OSError:
            lost += 1
    if not times:
        return {"ms": 0.0, "jitter": 0.0, "lost": lost, "offline": True}
    return {"ms": statistics.median(times), "jitter": (max(times) - min(times)) if len(times) > 1 else 0.0,
            "lost": lost, "offline": False}


def download_speed(seconds: float = 5.0, opener=urllib.request.urlopen, clock=time.perf_counter) -> float:
    """Megabits per second, downloading Cloudflare's speed test file for a few seconds."""
    req = urllib.request.Request(SPEED_URL, headers={"User-Agent": "Capri"})
    got, start = 0, clock()
    with opener(req, timeout=10) as r:
        while clock() - start < seconds:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            got += len(chunk)
    took = max(0.05, clock() - start)
    return got * 8 / took / 1e6


def _ms(ms: float) -> str:
    return "under 1 ms" if ms < 1 else f"{ms:.0f} ms"


def internet_report(ping_fn: Callable[[], dict] = ping, speed_fn: Callable[[], float] = download_speed) -> str:
    p = ping_fn()
    if p.get("offline"):
        return "You look offline: I couldn't reach the internet at all."
    try:
        mbps = speed_fn()
    except Exception as exc:
        log.info("internet: speed test failed: %s", exc)
        mbps = 0.0
    feel = ("great" if p["ms"] < 40 and p["jitter"] < 20 else "fine" if p["ms"] < 90 and p["jitter"] < 40
            else "laggy")
    line = f"Your ping is {_ms(p['ms'])} ({feel} for games)"
    if p["jitter"] >= 25:
        line += f", but it jumps around by {p['jitter']:.0f} ms"
    if p.get("lost"):
        line += f", and {p['lost']} of my tries failed"
    if mbps:
        line += f". Download is about {mbps:.0f} Mbps" + (" - slow for streaming" if mbps < 10 else "")
    return line + "."
