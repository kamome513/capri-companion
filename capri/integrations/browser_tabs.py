"""Your browser's tabs and the video player's Play / Pause button, read through Windows UI
Automation (the screen-reader interface) - "switch tabs on Opera" / "play the video".

Read-only until she presses the one tab or button you asked for. Windows only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .screen_targets import name_score

TAB_ITEM = 50019
BUTTON = 50000
BROWSER_EXES = {
    "opera": ("opera.exe", "opera_gx.exe", "launcher.exe"), "chrome": ("chrome.exe",), "edge": ("msedge.exe",),
    "firefox": ("firefox.exe",), "brave": ("brave.exe",), "vivaldi": ("vivaldi.exe",),
}
ANY_BROWSER = tuple(sorted({e for exes in BROWSER_EXES.values() for e in exes if e != "launcher.exe"}))
ORDINALS = {"first": 0, "1st": 0, "one": 0, "second": 1, "2nd": 1, "two": 1, "third": 2, "3rd": 2, "three": 2,
            "fourth": 3, "4th": 3, "four": 3, "fifth": 4, "5th": 4, "five": 4, "last": -1}
SUFFIXES = re.compile(r"\s*-\s*(?:audio playing|playing audio|audio muted|camera or microphone recording|"
                      r"pinned|network error|crashed)\s*$", re.IGNORECASE)
# YouTube: "Play (k)" / "Pause (k)"; Twitch: "Play (space/k)" / "Pause (space/k)"
PLAYER = re.compile(r"^(play|pause)\b(?!list| all| next| previous)", re.IGNORECASE)


@dataclass
class Tab:
    name: str
    rect: tuple[int, int, int, int]           # physical screen pixels
    element: object | None = None


def short(name: str) -> str:
    """How she says a tab: the site's name if the title ends with one ("xQc - Twitch" -> Twitch)."""
    parts = [p.strip() for p in re.split(r"\s+[-|–—]\s+", name) if p.strip()]
    if len(parts) > 1 and len(parts[-1]) <= 14:
        return parts[-1]
    return (parts[0] if parts else name)[:28]


def pick_tab(said: str, tabs: list[Tab]) -> Tab | None:
    """The tab you meant: "the twitch one", "youtube", "the second one", "the last tab"."""
    words = re.sub(r"[^a-z0-9 ]+", " ", said.lower())
    words = re.sub(r"^(?:(?:um|uh|okay|ok|switch|change|go|move|to|over|the|my|on|that|this|please)\s+)+", "", words)
    words = re.sub(r"(?:\s+(?:one|tab|page|window|please|thanks|then))+$", "", words).strip()
    if not words or not tabs:
        return None
    if words in ORDINALS:
        i = ORDINALS[words]
        return tabs[i] if -len(tabs) <= i < len(tabs) else None
    best, score = None, 0.0
    for tab in tabs:
        s = max(name_score(words, tab.name), name_score(words, short(tab.name)))
        title = re.sub(r"[^a-z0-9 ]+", " ", tab.name.lower())
        if re.search(rf"\b{re.escape(words)}\b", title):          # "twitch" in "xQc - Twitch"
            s = max(s, 0.8)
        if s > score:
            best, score = tab, s
    return best if score >= 0.78 else None


class BrowserTabs:
    def __init__(self, ui, desktop, processes: Callable[[], list], front: Callable[[], int | None]) -> None:
        self.ui, self.desktop, self.processes, self.front = ui, desktop, processes, front

    def window(self, browser: str = "") -> int | None:
        """That browser's window (the one in front if it's one of them), else any browser's."""
        exes = BROWSER_EXES.get(browser, ANY_BROWSER)
        pids = [p.pid for p in self.processes() if (p.name or "").lower() in exes]
        if not pids:
            return None
        windows = self.desktop.windows_for(pids)
        front = self.front()
        if front in windows:
            return front
        return self.desktop.main_window(pids)

    def _named(self, hwnd: int, control: int) -> list:
        found = []
        for _attempt in range(2):                      # Chromium wakes its accessibility on the first ask
            found = [b for b in self.ui.buttons(hwnd, control=control, with_rects=True)
                     if b.name and b.rect and b.rect[2] - b.rect[0] > 2]
            if found:
                break
        return found

    def tabs(self, hwnd: int) -> list[Tab]:
        """The window's tabs, left to right."""
        out = [Tab(SUFFIXES.sub("", b.name).strip(), b.rect, b) for b in self._named(hwnd, TAB_ITEM)]
        return sorted(out, key=lambda t: (t.rect[1] // 40, t.rect[0]))

    def player_button(self, hwnd: int) -> Tab | None:
        """The video player's Play / Pause button (YouTube, Twitch...) - the biggest player's."""
        found = [Tab(b.name, b.rect, b) for b in self._named(hwnd, BUTTON) if PLAYER.match(b.name.strip())]
        keyed = [t for t in found if "(" in t.name]       # the player's own button names its shortcut
        found = keyed or found
        if not found:
            return None
        return max(found, key=lambda t: t.rect[1])         # the control bar sits under the video

    def play_button(self, hwnd: int) -> Tab | None:
        """A music page's Play button: the first song's (the topmost), or "Pause" if it's already
        playing. Not the player bar's "play next / previous / current"."""
        found = [Tab(b.name, b.rect, b) for b in self._named(hwnd, BUTTON) if MUSIC_PLAY.match(b.name.strip())]
        playing = [t for t in found if is_playing(t)]
        if playing:
            return playing[0]
        return min(found, key=lambda t: (t.rect[1], t.rect[0])) if found else None


# "Play", "Play Let You Down", "Play song" - not "Playlist", "Play all", "Play next", "Play current"
MUSIC_PLAY = re.compile(r"^(?:play|pause)\b(?!list| all| next| previous| current| queue| later| from| radio)",
                        re.IGNORECASE)


def is_playing(button: Tab) -> bool:
    """A player shows "Pause" while it's playing."""
    return button.name.strip().lower().startswith("pause")
