"""Media keys: pause / next / previous / volume for whatever is playing.

Same as pressing the keys on a media keyboard, so it works with Spotify,
YouTube in a browser, VLC, etc. - no account or setup needed.
"""

from __future__ import annotations

import sys

KEYS = {
    "play_pause": 0xB3, "next": 0xB0, "previous": 0xB1,
    "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD,
}
VOLUME_STEPS = 5          # each press is ~2%, so one command is ~10%
KEYEVENTF_KEYUP = 0x0002


def press(name: str) -> None:
    if sys.platform != "win32":
        raise OSError("media keys are only available on Windows")
    import ctypes
    vk = KEYS[name]
    repeats = VOLUME_STEPS if name in ("volume_up", "volume_down") else 1
    for _ in range(repeats):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
