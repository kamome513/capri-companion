"""Finding your own files and folders by name: "show me my homework folder in File Explorer".

Only looks inside your own folders (Desktop, Documents, Downloads, Pictures,
Videos, Music, OneDrive), a few levels deep, with a time limit. Read-only.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from .fuzzy import similarity

MATCH = 0.82
MAX_DEPTH = 4
MAX_ENTRIES = 40000
TIME_LIMIT = 2.5           # seconds
SKIP_DIRS = {"node_modules", "appdata", "__pycache__", "site-packages", "venv", ".venv", "cache", "temp"}
# Never *opened* from a search (they'd run code); showing them in File Explorer is fine.
RUNNABLE = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
            ".msi", ".msp", ".scr", ".pif", ".lnk", ".url", ".reg", ".hta", ".cpl", ".jar", ".py", ".pyw",
            ".appref-ms", ".application", ".gadget", ".msc", ".inf", ".sys", ".dll", ".sh"}


@dataclass(frozen=True)
class Found:
    path: Path
    score: float
    is_dir: bool

    @property
    def runnable(self) -> bool:
        return not self.is_dir and self.path.suffix.lower() in RUNNABLE


def find(spoken: str, roots: list[Path], clock=time.monotonic) -> Found | None:
    """Best-matching file or folder. Folders and shallower items win near-ties."""
    spoken = spoken.strip()
    if not spoken:
        return None
    deadline = clock() + TIME_LIMIT
    seen = 0
    best: tuple[float, Found] | None = None
    stack = [(root, 0) for root in reversed(roots)]
    while stack and seen < MAX_ENTRIES and clock() < deadline:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            name = entry.name
            if name.startswith((".", "$", "~")) or name.lower() in ("desktop.ini", "thumbs.db"):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            stem = name if is_dir else os.path.splitext(name)[0]
            score = max(similarity(spoken, stem), similarity(spoken, name))
            if score >= MATCH:
                rank = score + (0.03 if is_dir else 0.0) - 0.01 * depth
                if best is None or rank > best[0]:
                    best = (rank, Found(Path(entry.path), score, is_dir))
            if is_dir and depth + 1 < MAX_DEPTH and name.lower() not in SKIP_DIRS:
                stack.append((Path(entry.path), depth + 1))
    return best[1] if best else None
