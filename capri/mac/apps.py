"""Your Mac's apps: the .app bundles in Applications (yours and the system's), with the name you know them by and
the name their process runs as."""

from __future__ import annotations

import plistlib
from dataclasses import dataclass
from pathlib import Path

APP_DIRS = ("/Applications", "/Applications/Utilities", "/System/Applications", "/System/Applications/Utilities",
            "~/Applications")
SKIP = {"capri"}


@dataclass
class MacApp:
    name: str
    path: Path
    executable: str
    bundle_id: str = ""


def read_bundle(app: Path) -> MacApp | None:
    """Name, executable and id from the app's Info.plist (folder name if it can't be read)."""
    info = {}
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
    except Exception:
        pass
    name = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or app.stem).strip() or app.stem
    exe = str(info.get("CFBundleExecutable") or app.stem)
    if name.lower() in SKIP:
        return None
    return MacApp(name, app, exe, str(info.get("CFBundleIdentifier") or ""))


def installed_apps(dirs: list[Path] | None = None) -> list[MacApp]:
    found: dict[str, MacApp] = {}
    for base in dirs if dirs is not None else [Path(d).expanduser() for d in APP_DIRS]:
        if not base.is_dir():
            continue
        for app in sorted(base.glob("*.app")):
            got = read_bundle(app)
            if got is not None:
                found.setdefault(got.name.lower(), got)
    return sorted(found.values(), key=lambda a: a.name.lower())
