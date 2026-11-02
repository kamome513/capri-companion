"""Sound on Linux: the AppImage carries its own PortAudio (the library the microphone and speaker
code uses), so nothing has to be installed. From the code, your system's libportaudio2 is used."""

from __future__ import annotations

import ctypes.util
import os
import sys
from pathlib import Path


def bundled_portaudio() -> str | None:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    for name in ("libportaudio.so.2", "libportaudio.so"):
        for folder in (Path(base), Path(base) / "lib"):
            if (folder / name).is_file():
                return str(folder / name)
    return None


def use_bundled_portaudio() -> bool:
    """Make sounddevice load the bundled PortAudio (it asks ctypes.util.find_library("portaudio"))."""
    path = bundled_portaudio()
    if not path or not sys.platform.startswith("linux"):
        return False
    original = ctypes.util.find_library

    def find_library(name: str):
        if name in ("portaudio", "portaudio-2"):
            return path
        return original(name)
    ctypes.util.find_library = find_library
    os.environ.setdefault("CAPRI_PORTAUDIO", path)
    return True
