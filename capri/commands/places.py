"""Folders and Windows places you can name: "open downloads", "show me my pictures",
"open file explorer", "open the recycle bin".

Every location here is fixed (Windows' own known folders), so saying a name only
ever picks one of them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

L = QStandardPaths.StandardLocation
KNOWN_FOLDERS = {
    "downloads": L.DownloadLocation, "documents": L.DocumentsLocation, "desktop": L.DesktopLocation,
    "pictures": L.PicturesLocation, "videos": L.MoviesLocation, "music": L.MusicLocation,
}
ALIASES = {
    "downloads": ["download", "my downloads", "downloads folder"],
    "documents": ["my documents", "docs", "document"],
    "desktop": ["my desktop"],
    "pictures": ["photos", "my pictures", "my photos", "images"],
    "videos": ["my videos", "video", "movies", "clips"],
    "music": ["my music"],
}
SHELL_PLACES = {
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer", "my files": "explorer",
    "windows explorer": "explorer", "file manager": "explorer",
    "this pc": "shell:MyComputerFolder", "my computer": "shell:MyComputerFolder",
    "recycle bin": "shell:RecycleBinFolder", "bin": "shell:RecycleBinFolder", "trash": "shell:RecycleBinFolder",
    "apps folder": "shell:AppsFolder", "all apps": "shell:AppsFolder", "applications": "shell:AppsFolder",
    "control panel": "shell:ControlPanelFolder",
}


def folder(name: str) -> Path | None:
    location = KNOWN_FOLDERS.get(name)
    if location is None:
        return None
    path = QStandardPaths.writableLocation(location)     # follows OneDrive / moved folders
    return Path(path) if path and Path(path).is_dir() else None


def explorer_exe() -> str:
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe")


def places() -> dict[str, str]:
    """spoken name -> folder path or shell: location."""
    out: dict[str, str] = {}
    for name in KNOWN_FOLDERS:
        path = folder(name)
        if path is not None:
            for spoken in [name] + ALIASES.get(name, []):
                out[spoken] = str(path)
    onedrive = os.environ.get("OneDrive")
    if onedrive and Path(onedrive).is_dir():
        out["onedrive"] = onedrive
        out["one drive"] = onedrive
    if sys.platform == "win32":
        for spoken, where in SHELL_PLACES.items():
            out[spoken] = explorer_exe() if where == "explorer" else where
    return out


def search_roots() -> list[Path]:
    """Where "find my ..." looks: your own folders, never Windows or program folders."""
    roots = [p for p in (folder(n) for n in KNOWN_FOLDERS) if p is not None]
    onedrive = os.environ.get("OneDrive")
    if onedrive and Path(onedrive).is_dir():
        roots.append(Path(onedrive))
    unique: list[Path] = []
    for r in sorted(set(roots), key=lambda p: len(p.parts)):     # skip folders inside another root
        if not any(u == r or u in r.parents for u in unique):
            unique.append(r)
    return unique
