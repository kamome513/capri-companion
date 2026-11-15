"""Words that differ by system: what Windows and Linux call the same things."""

from __future__ import annotations

import sys

LINUX = sys.platform.startswith("linux")
MAC = sys.platform == "darwin"
START_MENU = "Applications folder" if MAC else "apps menu" if LINUX else "Start menu"
FILE_MANAGER = "Finder" if MAC else "your file manager" if LINUX else "File Explorer"
