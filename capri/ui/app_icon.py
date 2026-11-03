"""Capri's app icon - her USB shard on a dark neon tile (tools/make_app_icon.py draws it). Used for the taskbar,
the tray and her windows; her face (art.icon) stays for her text box and the chat."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon


def icon_files() -> tuple[Path, Path]:
    from ..app import asset_root
    folder = asset_root() / "capri"
    return folder / "app_icon.ico", folder / "app_icon.png"


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """Every size of it (16 - 256 px) so Windows picks a sharp one for the tray and taskbar."""
    ico, png = icon_files()
    icon = QIcon(str(ico)) if ico.is_file() else QIcon()
    if icon.isNull() or not icon.availableSizes():
        icon = QIcon(str(png))
    return icon
