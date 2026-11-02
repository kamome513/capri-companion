"""Words that differ by system: what Windows and Linux call the same things."""

from __future__ import annotations

import sys

LINUX = sys.platform.startswith("linux")
START_MENU = "apps menu" if LINUX else "Start menu"
FILE_MANAGER = "your file manager" if LINUX else "File Explorer"
