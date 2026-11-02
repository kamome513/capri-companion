"""What's going on in your PC, in plain words: "what's using all my RAM", "why is my CPU so
high", "how much storage do I have left", "how long has my PC been on", "how's my battery".

Read with psutil, on your PC, when you ask - nothing is watched in between and nothing is sent
anywhere. Apps are grouped by program (Opera's 30 processes count as one "Opera GX").
Memory per app is its working set, like Task Manager's default column - apps that share memory
can add up to a little more than the total.
"""

from __future__ import annotations

import ntpath
import os
import time
from dataclasses import dataclass
from typing import Callable

TOP = 3
# nicer names for common programs
NAMES = {
    "opera": "Opera GX", "opera_gx": "Opera GX", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
    "brave": "Brave", "discord": "Discord", "spotify": "Spotify", "steam": "Steam", "steamwebhelper": "Steam",
    "code": "VS Code", "explorer": "File Explorer", "msmpeng": "Windows Defender", "dwm": "Windows' window manager",
    "svchost": "Windows services", "searchhost": "Windows Search", "obs64": "OBS", "teams": "Teams",
    "ms-teams": "Teams", "whatsapp": "WhatsApp", "epicgameslauncher": "Epic Games", "riotclientservices": "Riot Client",
    "python": "Python", "pythonw": "Python", "capri": "Capri (me)", "ollama": "Ollama (my AI)", "ollama_llama_server": "Ollama (my AI)",
    "memcompression": "Windows memory compression", "vmmem": "WSL / virtual machines", "vmmemwsl": "WSL",
    "robloxplayerbeta": "Roblox", "javaw": "Minecraft (Java)", "deadlock": "Deadlock", "project8": "Deadlock",
    "clipchamp": "Clipchamp", "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "onedrive": "OneDrive",
    "nvcontainer": "NVIDIA", "nvidia share": "NVIDIA overlay", "razer synapse": "Razer Synapse",
}
IGNORE = {"system idle process", "idle", "system", "registry", ""}


@dataclass
class AppUse:
    name: str
    amount: float            # bytes (memory) or % of the whole CPU
    processes: int


def nice_name(exe: str) -> str:
    stem = ntpath.basename(exe or "").lower().removesuffix(".exe")
    return NAMES.get(stem) or stem.replace("_", " ").replace("-", " ").title()


def gb(n: float) -> str:
    g = n / 1024 ** 3
    if g >= 1:
        return f"{g:.1f} GB"
    return f"{n / 1024 ** 2:.0f} MB"


def _group(rows: list[tuple[str, float]]) -> list[AppUse]:
    apps: dict[str, AppUse] = {}
    for name, amount in rows:
        if name.lower() in IGNORE or amount <= 0:
            continue
        app = apps.setdefault(nice_name(name), AppUse(nice_name(name), 0.0, 0))
        app.amount += amount
        app.processes += 1
    return sorted(apps.values(), key=lambda a: a.amount, reverse=True)


def _psutil():
    import psutil
    return psutil


# -- memory ----------------------------------------------------------------------------------------
def memory(ps=None) -> tuple[float, float, list[AppUse]]:
    """(used bytes, total bytes, apps by memory)."""
    ps = ps or _psutil()
    vm = ps.virtual_memory()
    rows = []
    me = os.getpid()
    for p in ps.process_iter(["name", "memory_info"]):
        try:
            info = p.info
            if info.get("memory_info") is not None:
                rows.append(("capri" if p.pid == me else info.get("name") or "", float(info["memory_info"].rss)))
        except Exception:
            continue
    return float(vm.total - vm.available), float(vm.total), _group(rows)


def memory_report(ps=None) -> str:
    used, total, apps = memory(ps)
    top = ", ".join(f"{a.name} {gb(a.amount)}" for a in apps[:TOP])
    pct = round(100 * used / total) if total else 0
    line = f"You're using {gb(used)} of {gb(total)} of RAM, {pct} percent."
    if top:
        line += f" The biggest: {top}."
    if pct >= 85:
        line += " That's nearly full - closing the top one would help most."
    return line


# -- CPU -------------------------------------------------------------------------------------------
def cpu(ps=None, sample: float = 0.6, sleep: Callable[[float], None] = time.sleep) -> tuple[float, list[AppUse]]:
    """(total %, apps by CPU %) - measured over `sample` seconds (blocking)."""
    ps = ps or _psutil()
    procs = []
    for p in ps.process_iter(["name"]):
        try:
            p.cpu_percent(None)                      # first call primes the counter
            procs.append(p)
        except Exception:
            continue
    ps.cpu_percent(None)
    sleep(sample)
    total = float(ps.cpu_percent(None))
    cores = ps.cpu_count() or 1
    rows = []
    for p in procs:
        try:
            name = "capri" if p.pid == os.getpid() else p.info.get("name") or ""
            rows.append((name, float(p.cpu_percent(None)) / cores))   # like Task Manager
        except Exception:
            continue
    return total, _group(rows)


def cpu_report(ps=None, sleep: Callable[[float], None] = time.sleep) -> str:
    total, apps = cpu(ps, sleep=sleep)
    busy = [a for a in apps if a.amount >= 1][:TOP]
    line = f"Your CPU is at {round(total)} percent."
    if busy:
        line += " Busiest: " + ", ".join(f"{a.name} {round(a.amount)} percent" for a in busy) + "."
    else:
        line += " Nothing's working it hard right now."
    return line


# -- her own usage -------------------------------------------------------------------------------------
def own_usage(ps=None, sample: float = 0.6, sleep: Callable[[float], None] = time.sleep) -> tuple[float, float, int]:
    """(RAM bytes, CPU % like Task Manager, process count) for Capri and the helpers she started
    (her screen-reading PowerShell, a speech worker...). Not Ollama: that's its own app."""
    ps = ps or _psutil()
    me = ps.Process(os.getpid())
    procs = [me]
    try:
        procs += me.children(recursive=True)
    except Exception:
        pass
    for p in procs:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    sleep(sample)
    ram = cpu_total = 0.0
    alive = 0
    cores = ps.cpu_count() or 1
    for p in procs:
        try:
            ram += float(p.memory_info().rss)
            cpu_total += float(p.cpu_percent(None)) / cores
            alive += 1
        except Exception:
            continue
    return ram, cpu_total, alive


def own_report(ps=None, sleep: Callable[[float], None] = time.sleep) -> str:
    ram, cpu_used, count = own_usage(ps, sleep=sleep)
    helpers = f", across {count} processes" if count > 1 else ""
    mb = round(ram / 1024 ** 2)
    return f"I'm using {mb} megabytes of RAM and {round(cpu_used, 1):g} percent of your CPU right now{helpers}."


# -- disks, uptime, battery -----------------------------------------------------------------------------
def disk_report(ps=None) -> str:
    ps = ps or _psutil()
    parts = []
    for part in ps.disk_partitions(all=False):
        if "cdrom" in (part.opts or "") or not part.fstype:
            continue
        try:
            u = ps.disk_usage(part.mountpoint)
        except Exception:
            continue
        if u.total < 2 * 1024 ** 3:                  # recovery partitions, tiny system mounts
            continue
        label = part.mountpoint.rstrip("\\/") or part.mountpoint
        parts.append(f"{label} has {gb(u.free)} free of {gb(u.total)}")
    if not parts:
        return "I couldn't read your drives."
    return "; ".join(parts[:4]) + "."


def uptime_report(ps=None, now: Callable[[], float] = time.time) -> str:
    ps = ps or _psutil()
    seconds = max(0, int(now() - ps.boot_time()))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    bits = ([f"{days} day{'s' * (days != 1)}"] if days else []) + ([f"{hours} hour{'s' * (hours != 1)}"] if hours else [])
    if not days:
        bits.append(f"{minutes} minute{'s' * (minutes != 1)}")
    return f"Your PC's been on for {' and '.join(bits)}." + (" Maybe give it a restart sometime." if days >= 7 else "")


def battery_report(ps=None) -> str:
    ps = ps or _psutil()
    b = ps.sensors_battery() if hasattr(ps, "sensors_battery") else None
    if b is None:
        return "This PC doesn't have a battery - it's plugged in for good."
    line = f"Battery's at {round(b.percent)} percent"
    if b.power_plugged:
        return line + " and charging."
    if b.secsleft and b.secsleft > 0:
        h, m = divmod(int(b.secsleft) // 60, 60)
        return line + f", about {h} hour{'s' * (h != 1)} {m} minutes left." if h else line + f", about {m} minutes left."
    return line + "."


def overview(ps=None, sleep: Callable[[float], None] = time.sleep) -> str:
    """'Why is my PC so slow': memory and CPU together."""
    return memory_report(ps) + " " + cpu_report(ps, sleep=sleep)


REPORTS: dict[str, Callable[[], str]] = {
    "ram": memory_report, "cpu": cpu_report, "disk": disk_report, "uptime": uptime_report,
    "battery": battery_report, "overview": overview, "self": own_report,
}


def report(topic: str) -> str:
    """Blocking (a fraction of a second for the CPU) - call from a worker thread."""
    if topic not in REPORTS:
        topic = "overview"
    return REPORTS[topic]()


def ai_tool(args: dict) -> str:
    """For the AI's get_pc_stats tool."""
    return report(str(args.get("topic", "overview")))

