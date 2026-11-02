"""Keeping Capri light: give idle memory back to Windows.

Python and Qt hold on to memory they're done with. Now and then (and when a game starts) she
runs a garbage collection and asks Windows to trim her working set - the RAM Task Manager
shows drops to what she's really using; anything she needs again comes straight back.
"""

from __future__ import annotations

import gc
import sys


def trim() -> None:
    gc.collect()
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]
        kernel32.SetProcessWorkingSetSize(kernel32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    except Exception:
        pass
