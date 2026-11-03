"""The one-file Capri.exe (Windows).

Capri.exe is a small launcher with Capri packed inside it: it unpacks her once per version into
%LOCALAPPDATA%\\Capri\\app\\<version>\\ and starts her from there, with CAPRI_PORTABLE set to its own path.
So everything that means "the app you run" - restarting her, start with Windows, updating - uses that path,
not the unpacked copy (that one is replaced on every update).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV = "CAPRI_PORTABLE"
WINDOWS = sys.platform == "win32"


def exe(env: dict | None = None) -> str:
    """The Capri.exe you run, when it's the one-file Capri ("" otherwise)."""
    env = os.environ if env is None else env
    if not WINDOWS:
        return ""
    path = env.get(ENV, "")
    return path if path and os.path.isfile(path) else ""


def app_folder() -> Path:
    """The folder of the Capri you run (for your own "looks" folder next to it)."""
    if exe():
        return Path(exe()).parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent
