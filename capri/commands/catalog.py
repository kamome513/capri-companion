"""Everything Capri can open or close, and matching spoken names against it."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .apps import CLOSE_NORMAL, PROGRAM, SAFE_SCHEMES, STEAM, WEBSITE, AppEntry
from .discovery import InstalledApp, Shortcut, SteamGame
from .fuzzy import similarity
from .system import ProcessInfo

log = logging.getLogger("capri")

MATCH_THRESHOLD = 0.78        # below this, "couldn't find that"
PROCESS_THRESHOLD = 0.85      # stricter when guessing from running process names
RESCAN_SECONDS = 120
FORCED_RESCAN_GAP = 10        # a miss rescans straight away, but not over and over

KNOWN_SITES = {
    "youtube": "https://www.youtube.com", "twitch": "https://www.twitch.tv", "reddit": "https://www.reddit.com",
    "google": "https://www.google.com", "gmail": "https://mail.google.com", "github": "https://github.com",
    "netflix": "https://www.netflix.com", "twitter": "https://x.com", "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.com", "google maps": "https://maps.google.com",
}
TLDS = {"com": "com", "net": "net", "org": "org", "io": "io", "gg": "gg", "tv": "tv", "dev": "dev",
        "co uk": "co.uk", "co": "co", "app": "app", "me": "me"}


@dataclass(frozen=True)
class Target:
    name: str
    kind: str                         # "app" | "steam" | "shortcut" | "installed" | "place" | "website"
    entry: AppEntry | None = None
    game: SteamGame | None = None
    shortcut: Shortcut | None = None
    url: str = ""
    installed: InstalledApp | None = None
    place: str = ""                   # a folder / shell location ("place" targets)

    def describe(self) -> str:
        if self.entry is not None:
            e = self.entry
            if not e.is_configured():
                return f"{e.name} (not set up yet)"
            if e.launch_type == STEAM:
                return f"{e.name} (Steam game {e.target})"
            if e.launch_type == WEBSITE:
                return f"{e.name} ({e.target})"
            return f"{e.name} ({e.expanded_target()})"
        if self.game is not None:
            return f"{self.game.name} (Steam game {self.game.appid})"
        if self.shortcut is not None:
            return f"{self.shortcut.name} (Start menu shortcut)"
        if self.installed is not None:
            kind = "Store app" if self.installed.store_package else "installed app"
            return f"{self.installed.name} ({kind} {self.installed.app_id})"
        if self.place:
            return f"{self.name} (folder {self.place})"
        return f"{self.name} ({self.url})"


@dataclass(frozen=True)
class Match:
    target: Target
    score: float
    heard: str


def url_is_safe(url: str) -> bool:
    m = re.match(r"^([a-z][a-z0-9+.-]*):", url.strip().lower())
    return bool(m) and m.group(1) in SAFE_SCHEMES


def spoken_website(spoken: str) -> str | None:
    """'youtube dot com' -> https://youtube.com"""
    m = re.fullmatch(r"(?:www dot )?([a-z0-9 ]+?) dot (" + "|".join(TLDS) + r")", spoken.strip().lower())
    if not m:
        return None
    return f"https://{m.group(1).replace(' ', '')}.{TLDS[m.group(2)]}"


class Catalog:
    def __init__(self, load_apps: Callable[[], list[AppEntry]],
                 load_games: Callable[[], list[SteamGame]],
                 load_shortcuts: Callable[[], list[Shortcut]],
                 clock: Callable[[], float] = time.monotonic,
                 load_installed: Callable[[], list[InstalledApp]] = list,
                 load_places: Callable[[], dict[str, str]] = dict) -> None:
        self._load_apps, self._load_games, self._load_shortcuts = load_apps, load_games, load_shortcuts
        self._load_installed, self._load_places = load_installed, load_places
        self._clock = clock
        self.apps: list[AppEntry] = []
        self.games: list[SteamGame] = []
        self.shortcuts: list[Shortcut] = []
        self.installed: list[InstalledApp] = []
        self.places: dict[str, str] = {}
        self._scanned = -1e9
        self.reload_apps()

    def reload_apps(self) -> None:
        self.apps = self._load_apps()

    def rescan(self, force: bool = False, now: bool = False) -> None:
        """now=True: the Rescan button - always scans."""
        since = self._clock() - self._scanned
        if now or (force and since > FORCED_RESCAN_GAP) or since > RESCAN_SECONDS:
            try:
                self.games = self._load_games()
            except Exception as exc:
                log.warning(f"Steam library scan failed: {exc}")
            try:
                self.shortcuts = self._load_shortcuts()
            except Exception as exc:
                log.warning(f"Start menu scan failed: {exc}")
            try:
                self.installed = self._load_installed()
            except Exception as exc:
                log.warning(f"installed apps scan failed: {exc}")
            try:
                self.places = self._load_places()
            except Exception as exc:
                log.warning(f"folder lookup failed: {exc}")
            self._scanned = self._clock()

    # -- matching ----------------------------------------------------------------
    def _candidates(self) -> list[tuple[str, Target, float]]:
        """(name to compare, target, bonus). Your own entries win close calls."""
        out = []
        for entry in self.apps:
            for name in entry.names():
                out.append((name, Target(entry.name, "app", entry=entry), 0.04))
        for game in self.games:
            out.append((game.name, Target(game.name, "steam", game=game), 0.02))
        shortcut_names = set()
        for sc in self.shortcuts:
            shortcut_names.add(sc.name.lower())
            out.append((sc.name, Target(sc.name, "shortcut", shortcut=sc), 0.0))
        for app in self.installed:          # Store apps etc.; a same-named shortcut already covers the rest
            if app.name.lower() not in shortcut_names:
                out.append((app.name, Target(app.name, "installed", installed=app), -0.01))
        for name, place in self.places.items():
            out.append((name, Target(name.title() if name.islower() else name, "place", place=place), 0.01))
        for name, url in KNOWN_SITES.items():
            out.append((name, Target(name.title(), "website", url=url), 0.0))
        return out

    def _ranked(self, spoken: str) -> list[Match]:
        best: dict[int, tuple[float, Match]] = {}
        for name, target, bonus in self._candidates():
            score = similarity(spoken, name)
            if score < MATCH_THRESHOLD:
                continue
            key = id(target.entry) if target.entry is not None else hash(target)
            rank = score + bonus   # the bonus only breaks near-ties, never passes the threshold
            if key not in best or rank > best[key][0]:
                best[key] = (rank, Match(target, min(score, 1.0), spoken))
        return [m for _, m in sorted(best.values(), key=lambda item: item[0], reverse=True)]

    def find(self, spoken: str) -> Match | None:
        """Best launchable match; an un-configured entry only if nothing else fits."""
        url = spoken_website(spoken)
        if url:
            return Match(Target(url.split("//", 1)[1], "website", url=url), 1.0, spoken)
        for attempt in (False, True):
            self.rescan(force=attempt)   # on a miss, rescan once in case it was just installed
            ranked = self._ranked(spoken)
            usable = [m for m in ranked if m.target.entry is None or m.target.entry.is_configured()]
            if usable:
                return usable[0]
            if ranked:
                return ranked[0]          # e.g. "Opera GX" listed but no path yet
        return None

    def guess(self, spoken: str, minimum: float = 0.86) -> Match | None:
        """A close match only, without the forced rescan find() does on a miss - for checking
        whether chat-sounding words ("throw on spotify") name something she can open."""
        url = spoken_website(spoken)
        if url:
            return Match(Target(url.split("//", 1)[1], "website", url=url), 1.0, spoken)
        self.rescan()
        ranked = [m for m in self._ranked(spoken) if m.score >= minimum]
        return ranked[0] if ranked else None

    # -- closing -------------------------------------------------------------------------
    def running_for(self, spoken: str, processes: list[ProcessInfo]) -> tuple[str, list[int], str]:
        """(display name, pids, close mode) for 'close <spoken>'. Empty pids = not running."""
        self.rescan()
        for match in self._ranked(spoken):
            t = match.target
            pids = self._pids_for(t, processes)
            if pids:
                mode = t.entry.close if t.entry is not None else (
                    "ask" if t.game is not None else CLOSE_NORMAL)
                return t.name, pids, mode
        # Not in any list: try running programs by their file name ("notepad" -> notepad.exe).
        best: tuple[float, str] | None = None
        for p in processes:
            stem = Path(p.name).stem
            score = similarity(spoken, stem)
            if score >= PROCESS_THRESHOLD and (best is None or score > best[0]):
                best = (score, stem)
        if best:
            pids = [p.pid for p in processes if Path(p.name).stem.lower() == best[1].lower()]
            return best[1], pids, CLOSE_NORMAL
        ranked = self._ranked(spoken)
        return (ranked[0].target.name if ranked else spoken), [], CLOSE_NORMAL

    @staticmethod
    def _pids_for(t: Target, processes: list[ProcessInfo]) -> list[int]:
        if t.entry is not None:
            names = {n.lower() for n in t.entry.processes}
            pids = [p.pid for p in processes if p.name.lower() in names]
            if pids or t.entry.launch_type != PROGRAM or not t.entry.is_configured():
                return pids
            exe = os.path.normcase(t.entry.expanded_target())
            return [p.pid for p in processes if p.exe and os.path.normcase(p.exe) == exe]
        if t.game is not None:
            folder = os.path.normcase(str(t.game.install_dir)) + os.sep
            return [p.pid for p in processes if p.exe and os.path.normcase(p.exe).startswith(folder)]
        if t.shortcut is not None and t.shortcut.target is not None:
            exe = os.path.normcase(str(t.shortcut.target))
            return [p.pid for p in processes if p.exe and os.path.normcase(p.exe) == exe]
        if t.installed is not None:
            if t.installed.exe is not None:
                exe = os.path.normcase(str(t.installed.exe))
                return [p.pid for p in processes if p.exe and os.path.normcase(p.exe) == exe]
            package = t.installed.store_package.lower()
            if package:   # Store apps run from ...\WindowsApps\<package>_<version>_<arch>__<publisher>\
                marker = os.sep + "windowsapps" + os.sep + package + "_"
                return [p.pid for p in processes if p.exe and marker in os.path.normcase(p.exe).lower()]
        return []
