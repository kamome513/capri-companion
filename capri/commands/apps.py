"""The user's configured apps (``%LOCALAPPDATA%\\Capri\\apps.json``).

Each entry says how to launch something and which processes belong to it.
Only these entries, installed Steam games and Start-menu shortcuts can ever
be launched - there is no way to run an arbitrary command.
"""

from __future__ import annotations

import json
import logging
import ntpath
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths

log = logging.getLogger("capri")

# Launch types
PROGRAM = "program"     # an .exe (or any file Windows can open) + optional arguments
STEAM = "steam"         # a Steam app id, launched with steam://rungameid/<id>
WEBSITE = "website"     # http(s) URL, or an allowed app link like spotify:
LAUNCH_TYPES = (PROGRAM, STEAM, WEBSITE)

# What "close X" does
CLOSE_ASK = "ask"        # confirm first ("Close Deadlock? Say yes or no.") - for games
CLOSE_NORMAL = "normal"  # like clicking X; asks before force-closing if it keeps running
CLOSE_FORCE = "force"    # end the process straight away (tray apps like Discord)
CLOSE_MODES = (CLOSE_ASK, CLOSE_NORMAL, CLOSE_FORCE)

# App links allowed in WEBSITE entries besides http(s). No file:, no scripts.
SAFE_SCHEMES = ("http", "https", "steam", "spotify", "discord", "roblox", "roblox-player", "minecraft",
                "ms-settings", "mailto")


@dataclass
class AppEntry:
    name: str
    launch_type: str = PROGRAM
    target: str = ""                  # path, Steam app id or URL; "" = not set up yet
    arguments: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)      # other ways to say it
    processes: list[str] = field(default_factory=list)    # e.g. ["Discord.exe"]
    close: str = CLOSE_NORMAL

    def expanded_target(self) -> str:
        return os.path.expandvars(self.target) if self.launch_type == PROGRAM else self.target.strip()

    def is_configured(self) -> bool:
        return bool(self.target.strip())

    def names(self) -> list[str]:
        return [self.name] + [a for a in self.aliases if a.strip()]


def _first_existing(*candidates: str) -> str:
    for c in candidates:
        if Path(os.path.expandvars(c)).exists():
            return c
    return ""


# The apps every Capri used to come with. Kept so an old apps.json can drop the ones that
# were never installed (they showed up in the list as if they were).
OLD_DEFAULT_NAMES = {"discord", "spotify", "chrome", "opera gx", "deadlock", "minecraft", "bloxstrap",
                     "roblox", "steam"}
APPS_VERSION = 2


def _common_apps() -> list[AppEntry]:
    """Well-known apps, each only if it's really on this PC."""
    out = []
    discord = _first_existing(r"%LOCALAPPDATA%\Discord\Update.exe")
    if discord:
        out.append(AppEntry("Discord", PROGRAM, discord, ["--processStart", "Discord.exe"],
                            processes=["Discord.exe"], close=CLOSE_FORCE))
    spotify = _first_existing(r"%APPDATA%\Spotify\Spotify.exe")
    if spotify:
        out.append(AppEntry("Spotify", PROGRAM, spotify, processes=["Spotify.exe"], close=CLOSE_FORCE))
    chrome = _first_existing(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                             r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                             r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    if chrome:
        out.append(AppEntry("Chrome", PROGRAM, chrome, aliases=["google chrome"], processes=["chrome.exe"]))
    opera = _first_existing(r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe",
                            r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe")
    if opera:
        out.append(AppEntry("Opera GX", PROGRAM, opera, aliases=["opera"], processes=["opera.exe"]))
    minecraft = _first_existing(r"C:\XboxGames\Minecraft Launcher\Content\Minecraft.exe",
                                r"%ProgramFiles(x86)%\Minecraft Launcher\MinecraftLauncher.exe",
                                r"%ProgramFiles%\Minecraft Launcher\MinecraftLauncher.exe")
    if minecraft:
        out.append(AppEntry("Minecraft", PROGRAM, minecraft, aliases=["minecraft launcher", "mine craft"],
                            processes=["Minecraft.exe", "MinecraftLauncher.exe", "Minecraft.Windows.exe"],
                            close=CLOSE_ASK))
    blox = _first_existing(r"%LOCALAPPDATA%\Bloxstrap\Bloxstrap.exe")
    if blox:
        out.append(AppEntry("Bloxstrap", PROGRAM, blox, aliases=["blocks strap", "blox strap"],
                            processes=["Bloxstrap.exe"]))
    if _first_existing(r"%LOCALAPPDATA%\Roblox\Versions"):
        # No launch target: "open roblox" finds the Roblox Player Start-menu shortcut.
        out.append(AppEntry("Roblox", PROGRAM, "", aliases=["rob locks"],
                            processes=["RobloxPlayerBeta.exe"], close=CLOSE_ASK))
    steam = _first_existing(r"%ProgramFiles(x86)%\Steam\steam.exe", r"%ProgramFiles%\Steam\steam.exe")
    if steam:
        out.append(AppEntry("Steam", PROGRAM, steam, processes=["steam.exe", "steamwebhelper.exe"]))
    return out


GAME_EXTRAS = {"1422450": (["dead lock"], ["deadlock.exe", "project8.exe"])}   # Steam id: aliases, processes


def found_games(steam: list | None = None, shortcuts: list | None = None) -> list[AppEntry]:
    """Every game downloaded on this PC: Steam's library, plus Start-menu shortcuts that point
    into a game library (Epic, Riot, Xbox, GOG, EA, Ubisoft, Battle.net...)."""
    from .discovery import shortcuts as find_shortcuts, steam_games
    from .games import GAME_FOLDERS, LAUNCHERS
    out: dict[str, AppEntry] = {}
    try:
        steam = steam_games() if steam is None else steam
    except Exception:
        steam = []
    for g in steam:
        aliases, procs = GAME_EXTRAS.get(g.appid, ([], []))
        out[g.name.lower()] = AppEntry(g.name, STEAM, g.appid, aliases=list(aliases), processes=list(procs),
                                       close=CLOSE_ASK)
    try:
        shortcuts = find_shortcuts() if shortcuts is None else shortcuts
    except Exception:
        shortcuts = []
    for sc in shortcuts:
        target = str(sc.target or "")
        low = target.lower().replace("/", "\\")
        if not target or not any(f in low for f in GAME_FOLDERS) or ntpath.basename(low) in LAUNCHERS:
            continue
        if sc.name.lower() not in out:
            out[sc.name.lower()] = AppEntry(sc.name, PROGRAM, str(sc.path), processes=[ntpath.basename(target)],
                                            close=CLOSE_ASK)
    return sorted(out.values(), key=lambda e: e.name.lower())


def default_apps(games: list[AppEntry] | None = None) -> list[AppEntry]:
    """What a new apps list starts with: the common apps that are installed + your games."""
    apps = _common_apps()
    have = {a.name.lower() for a in apps}
    for g in found_games() if games is None else games:
        if g.name.lower() not in have:
            apps.append(g)
            have.add(g.name.lower())
    return apps


def add_found_games(apps: list[AppEntry], games: list[AppEntry] | None = None) -> list[AppEntry]:
    """The games on this PC that aren't in `apps` yet (by name or Steam id)."""
    names = {n.lower() for a in apps for n in a.names()}
    ids = {a.target.strip() for a in apps if a.launch_type == STEAM}
    return [g for g in (found_games() if games is None else games)
            if g.name.lower() not in names and not (g.launch_type == STEAM and g.target in ids)]


def entry_status(e: AppEntry, steam_ids: set[str] | None = None) -> tuple[bool | None, str]:
    """(ok, words) for the Apps tab: True = found, False = broken, None = Capri will look for it."""
    target = e.target.strip()
    if not target:
        return None, "No path - Capri looks it up in your Start menu"
    if e.launch_type == STEAM:
        if not target.isdigit():
            return False, "A Steam id is a number"
        if steam_ids is not None and target not in steam_ids:
            return False, "Not installed in Steam"
        return True, "Steam game"
    if e.launch_type == WEBSITE:
        scheme = target.split(":", 1)[0].lower() if ":" in target else ""
        return (True, "Link") if scheme in SAFE_SCHEMES else (False, "Links start with https://")
    raw = e.expanded_target().strip().strip('"')
    path = Path(raw)
    if not (path.is_absolute() or ntpath.isabs(raw) and re.match(r"^(?:[a-zA-Z]:[\\/]|\\\\)", raw)):
        return False, "Needs the full path (e.g. C:\\Games\\game.exe)"
    if not path.exists():
        return False, "File not found here"
    return True, "Found"


def _old_default_missing(e: AppEntry, steam_ids: set[str] | None) -> bool:
    """A leftover default from an older Capri for something that isn't on this PC."""
    if e.name.lower() not in OLD_DEFAULT_NAMES:
        return False
    if e.launch_type == STEAM:
        return steam_ids is not None and e.target.strip() not in steam_ids
    if e.launch_type == WEBSITE:
        return e.name.lower() == "spotify" and not _first_existing(r"%APPDATA%\Spotify\Spotify.exe")
    if e.name.lower() == "roblox":
        return not _first_existing(r"%LOCALAPPDATA%\Roblox\Versions")
    return not e.target.strip() or not Path(e.expanded_target()).exists()


def _installed_steam_ids() -> set[str] | None:
    try:
        from .discovery import steam_games, steam_root
        return {g.appid for g in steam_games()} if steam_root() is not None else set()
    except Exception:
        return None


def apps_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    return Path(base) / "apps.json"


def load_apps() -> list[AppEntry]:
    path = apps_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        apps = default_apps()
        save_apps(apps)
        return apps
    except (OSError, ValueError) as exc:
        log.warning(f"ignoring unreadable {path}: {exc}")
        return default_apps()

    apps = []
    version = raw.get("version", 1) if isinstance(raw, dict) else 1
    for item in raw.get("apps", []) if isinstance(raw, dict) else []:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        entry = AppEntry(
            name=str(item["name"]).strip(),
            launch_type=item.get("launch_type") if item.get("launch_type") in LAUNCH_TYPES else PROGRAM,
            target=str(item.get("target", "")),
            arguments=[str(a) for a in item.get("arguments", []) if isinstance(a, (str, int))],
            aliases=[str(a) for a in item.get("aliases", []) if isinstance(a, str)],
            processes=[str(p) for p in item.get("processes", []) if isinstance(p, str)],
            close=item.get("close") if item.get("close") in CLOSE_MODES else CLOSE_NORMAL,
        )
        apps.append(entry)
    if version < APPS_VERSION:
        # Older Capri filled the list with apps you might not have (Deadlock, Roblox...) and none of
        # the games you DO have. Drop the missing ones, add your downloaded games, once.
        steam_ids = _installed_steam_ids()
        apps = [a for a in apps if not _old_default_missing(a, steam_ids)]
        apps += add_found_games(apps)
        save_apps(apps)
    return apps


def save_apps(apps: list[AppEntry]) -> None:
    path = apps_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": APPS_VERSION, "apps": [asdict(a) for a in apps]}, indent=2),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        log.warning(f"could not save {path}: {exc}")
