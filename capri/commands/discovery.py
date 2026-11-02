"""Finds things Capri can open without any setup: Steam games and Start-menu shortcuts.

Read-only: it only reads Steam's library files and the Start-menu folders.
"""

from __future__ import annotations

import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SteamGame:
    appid: str
    name: str
    install_dir: Path          # ...\steamapps\common\<game>; its processes belong to the game


@dataclass(frozen=True)
class Shortcut:
    name: str
    path: Path                 # the .lnk / .url file (Linux: the app's .desktop menu entry)
    target: Path | None        # resolved .exe, when the shortcut points at one (Linux: its program)
    names: tuple[str, ...] = ()   # Linux: names its processes / windows go by ("discord", "firefox")


# Steam "apps" that aren't games you'd ask for.
STEAM_SKIP = re.compile(r"redistributable|steamworks|proton|steam linux runtime|soundtrack|dedicated server|"
                        r"\bsdk\b|benchmark", re.I)
SHORTCUT_SKIP = re.compile(r"uninstall|readme|read me|release notes|help|manual|documentation|website|"
                           r"license|changelog|support|faq|\bsetup\b|repair", re.I)


# -- Steam ------------------------------------------------------------------------
def steam_root() -> Path | None:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
                if path.is_dir():
                    return path
        except OSError:
            pass
    for guess in (r"%ProgramFiles(x86)%\Steam", r"%ProgramFiles%\Steam", "~/.steam/steam", "~/.local/share/Steam",
                  "~/.var/app/com.valvesoftware.Steam/.local/share/Steam", "~/snap/steam/common/.local/share/Steam"):
        path = Path(os.path.expanduser(os.path.expandvars(guess)))
        if path.is_dir():
            return path
    return None


def _vdf_pairs(text: str) -> list[tuple[str, str]]:
    return re.findall(r'"([^"]+)"\s+"([^"]*)"', text)


def steam_libraries(root: Path) -> list[Path]:
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        for key, value in _vdf_pairs(vdf.read_text(encoding="utf-8", errors="ignore")):
            if key == "path":
                lib = Path(value.replace("\\\\", "\\"))
                if lib not in libs:
                    libs.append(lib)
    except OSError:
        pass
    return libs


def steam_games(root: Path | None = None) -> list[SteamGame]:
    root = root or steam_root()
    if root is None:
        return []
    games: dict[str, SteamGame] = {}
    for lib in steam_libraries(root):
        apps = lib / "steamapps"
        if not apps.is_dir():
            continue
        for manifest in apps.glob("appmanifest_*.acf"):
            try:
                fields = dict(_vdf_pairs(manifest.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
            appid, name, folder = fields.get("appid"), fields.get("name"), fields.get("installdir")
            if appid and name and folder and not STEAM_SKIP.search(name):
                games[appid] = SteamGame(appid, name, apps / "common" / folder)
    return sorted(games.values(), key=lambda g: g.name.lower())


# -- Start menu ------------------------------------------------------------------------
def start_menu_dirs() -> list[Path]:
    dirs = []
    for base in (os.environ.get("APPDATA"), os.environ.get("PROGRAMDATA")):
        if base:
            path = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if path.is_dir():
                dirs.append(path)
    return dirs


def lnk_target(path: Path) -> Path | None:
    """The local file a .lnk points to (MS-SHLLINK LinkInfo), or None."""
    try:
        data = path.read_bytes()
        if len(data) < 76 or struct.unpack_from("<I", data, 0)[0] != 0x4C:
            return None
        flags = struct.unpack_from("<I", data, 20)[0]
        pos = 76
        if flags & 0x01:                                  # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if not flags & 0x02:                              # HasLinkInfo
            return None
        info = pos
        header_size = struct.unpack_from("<I", data, info + 4)[0]
        info_flags = struct.unpack_from("<I", data, info + 8)[0]
        if not info_flags & 0x01:                         # VolumeIDAndLocalBasePath
            return None
        if header_size >= 0x24:
            offset = struct.unpack_from("<I", data, info + 28)[0]
            if offset:
                start = end = info + offset
                while data[end:end + 2] != b"\x00\x00":   # UTF-16 terminator, 2-byte aligned
                    end += 2
                    if end >= len(data):
                        return None
                return Path(data[start:end].decode("utf-16-le"))
        offset = struct.unpack_from("<I", data, info + 16)[0]
        end = data.index(b"\x00", info + offset)
        return Path(data[info + offset:end].decode("mbcs" if sys.platform == "win32" else "latin-1"))
    except (OSError, struct.error, ValueError, UnicodeDecodeError, LookupError):
        return None


def linux_shortcuts(dirs: list[Path] | None = None) -> list[Shortcut]:
    """Every app in your Linux menus (.desktop entries: system, your own, Flatpak, Snap)."""
    from ..linux.apps import installed_entries
    return [Shortcut(e.name, e.path, e.program(), e.process_names()) for e in installed_entries(dirs)]


def shortcuts(dirs: list[Path] | None = None) -> list[Shortcut]:
    if sys.platform.startswith("linux") and dirs is None:
        return linux_shortcuts()
    found: dict[str, Shortcut] = {}
    for base in dirs if dirs is not None else start_menu_dirs():
        for path in base.rglob("*"):
            if path.suffix.lower() not in (".lnk", ".url") or SHORTCUT_SKIP.search(path.stem):
                continue
            target = lnk_target(path) if path.suffix.lower() == ".lnk" else None
            key = path.stem.lower()
            if key not in found:   # per-user shortcuts win over all-users ones
                found[key] = Shortcut(path.stem, path, target)
    return sorted(found.values(), key=lambda s: s.name.lower())


# -- Every installed app (Windows' "Applications" folder) -------------------------------------
@dataclass(frozen=True)
class InstalledApp:
    """An app from shell:AppsFolder - the list the Start menu's "All apps" shows.

    This is where Microsoft Store apps live (Clipchamp, Calculator, the new Outlook,
    WhatsApp, Xbox...), which have no shortcut files at all. ``app_id`` is the name
    Windows itself gives the app; it's launched as shell:AppsFolder\\<app_id>.
    """
    name: str
    app_id: str
    exe: Path | None = None    # desktop apps: the program file, when Windows reports one

    @property
    def store_package(self) -> str:
        """'Clipchamp.Clipchamp' for a Store app id like 'Clipchamp.Clipchamp_yxz26nhyzhsrt!App'."""
        if "!" in self.app_id and "_" in self.app_id.split("!")[0]:
            return self.app_id.split("!")[0].rsplit("_", 1)[0]
        return ""


BAD_ID = re.compile(r'["<>|*?\r\n\t/]')        # web links and anything odd are skipped


def installed_apps(read_folder=None) -> list[InstalledApp]:
    """Read shell:AppsFolder. Read-only; Windows only (elsewhere: nothing)."""
    try:
        entries = read_folder() if read_folder else _read_apps_folder()
    except Exception:
        return []
    found: dict[str, InstalledApp] = {}
    for name, app_id in entries:
        name, app_id = (name or "").strip(), (app_id or "").strip()
        if not name or not app_id or BAD_ID.search(app_id) or SHORTCUT_SKIP.search(name):
            continue
        exe = Path(app_id) if re.match(r"^[a-zA-Z]:\\", app_id) and app_id.lower().endswith(".exe") else None
        if name.lower() not in found:
            found[name.lower()] = InstalledApp(name, app_id, exe)
    return sorted(found.values(), key=lambda a: a.name.lower())


def _read_apps_folder() -> list[tuple[str, str]]:
    if sys.platform != "win32":
        return []
    import comtypes
    import comtypes.client
    comtypes.CoInitialize()
    shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
    folder = shell.NameSpace("shell:AppsFolder")
    if folder is None:
        return []
    items = folder.Items()
    return [(items.Item(i).Name, items.Item(i).Path) for i in range(items.Count)]
