"""Discord's Mute / Deafen buttons and Spotify's Play buttons, pressed for real (see uia.py).

Both read the result back afterwards, so what Capri says is what actually happened.
Button names are Discord's / Spotify's English labels.
"""

from __future__ import annotations

import logging
import re
import time
from difflib import SequenceMatcher
from typing import Callable

from .uia import UI, Button, find_buttons

DISCORD_NAMES = {"mute": ("Mute", "Unmute"), "deafen": ("Deafen", "Undeafen")}
WORD = {("mute", True): "muted", ("mute", False): "unmuted",
        ("deafen", True): "deafened", ("deafen", False): "undeafened"}
SETTLE = 0.5            # seconds for the app to update after a press


def is_on(button: Button) -> bool:
    """Discord's mic switch: on = muted. It's a switch with an on/off state; where it isn't,
    the label flips instead ("Mute" -> "Unmute" while muted)."""
    state = button.toggled()
    if state is not None:
        return state
    return button.name.lower().startswith("un")


class DiscordButtons:
    def __init__(self, ui: UI, windows: Callable[[list[int]], list[int]],
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.ui, self.windows, self.sleep = ui, windows, sleep

    def _find(self, pids: list[int]) -> dict[str, Button]:
        names = {n for pair in DISCORD_NAMES.values() for n in pair}
        found = find_buttons(self.ui, self.windows(pids), names, lambda b: bool(b), timeout=3.0, sleep=self.sleep)
        out: dict[str, Button] = {}
        for b in found:
            for kind, labels in DISCORD_NAMES.items():
                if b.name in labels and kind not in out:
                    out[kind] = b
        return out

    def locate(self, pids: list[int], kind: str) -> tuple[int, int, int, int] | None:
        """Where Discord's Mute / Deafen button is on screen (physical pixels), for her lightning
        to hit. None if it isn't visible (Discord minimised, closed to the tray...)."""
        labels = set(DISCORD_NAMES[kind])
        for attempt in range(6):                      # Discord wakes its accessibility on the first ask
            for hwnd in self.windows(pids):
                try:
                    found = self.ui.buttons(hwnd, labels, with_rects=True)
                except Exception:
                    continue
                for b in found:
                    r = getattr(b, "rect", None)
                    if r and r[2] - r[0] > 4 and r[3] - r[1] > 4 and r[0] > -10000:
                        return r
            if attempt < 5:
                self.sleep(0.35)
        return None

    def set(self, pids: list[int], kind: str, want: bool) -> str:
        """kind mute|deafen, want on/off. Returns what happened:
        muted / unmuted / deafened / undeafened, already_<that>, pressed (state unknown),
        failed (pressed, nothing changed), unavailable (no buttons: use the keys)."""
        found = self._find(pids)
        if kind not in found:
            return "unavailable"
        if kind == "mute" and want is False and "deafen" in found and is_on(found["deafen"]):
            # Deafened = mic off whatever the mute switch says. Undeafen brings it back.
            found["deafen"].press()
            self.sleep(SETTLE)
            found = self._find(pids)
            if "mute" not in found or is_on(found["mute"]) is False:
                return "unmuted"
        target = found[kind]
        before = is_on(target)
        if before is not None and before == want:
            return "already_" + WORD[(kind, want)]
        target.press()
        self.sleep(SETTLE)
        after_found = self._find(pids)
        after = is_on(after_found[kind]) if kind in after_found else None
        if after is None:
            return "pressed"
        return WORD[(kind, want)] if after == want else "failed"


# -- Discord calls: joining, screen share, leaving ------------------------------------------------------------
# Matched loosely (any case, any control type), because Discord renames and restyles these now and then.
SHARE = re.compile(r"^(?:share (?:your |my )?screen|screen ?share|share)$", re.IGNORECASE)
STOP_SHARE = re.compile(r"^(?:stop (?:streaming|sharing|screen ?share|stream|sharing your screen))$", re.IGNORECASE)
LEAVE = re.compile(r"^(?:disconnect|leave (?:call|voice|channel)|hang up|end call)$", re.IGNORECASE)
JOIN = re.compile(r"^(?:join (?:voice|call|channel|voice channel)|join)$", re.IGNORECASE)
GO_LIVE = re.compile(r"^(?:go live|start streaming|stream|share)$", re.IGNORECASE)
SCREENS_TAB = re.compile(r"^(?:screens?|entire screen)$", re.IGNORECASE)
SCREEN_ITEM = re.compile(r"^(?:screen|entire screen|display|monitor)(?:\s*\d+)?(?:\s*\(.*\))?$", re.IGNORECASE)
MIC = re.compile(r"^(?:mute|unmute|turn (?:on|off) microphone)$", re.IGNORECASE)
NAMES = {   # Discord's own labels for each (exact), tried before the loose patterns
    SHARE.pattern: {"Share Your Screen", "Share your screen", "Share Screen", "Screen Share"},
    STOP_SHARE.pattern: {"Stop Streaming", "Stop streaming", "Stop Sharing", "Stop Screen Share"},
    LEAVE.pattern: {"Disconnect", "Leave Call", "Leave call", "Disconnect from voice", "Hang Up"},
    JOIN.pattern: {"Join Voice", "Join voice", "Join Call", "Join call", "Join"},
    GO_LIVE.pattern: {"Go Live", "Go live"},
    MIC.pattern: {"Mute", "Unmute"},
}
CALL_LINK = re.compile(r"(?:https?://)?(?:www\.|ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)")
log = logging.getLogger("capri")


def call_link(text: str) -> str | None:
    """'https://discord.com/channels/123/456' (right-click a voice channel -> Copy Link) -> the address
    that opens it in the Discord app. None if it isn't a channel link."""
    m = CALL_LINK.search(text.strip())
    return f"discord://-/channels/{m.group(1)}/{m.group(2)}" if m else None


class DiscordCall:
    """Joining your call, screen share and leaving, with Discord's own buttons (there are no
    default keybinds for these). Each one checks the result, so she says what really happened.
    When a button can't be found, the names of the ones she did see go to capri.log."""

    def __init__(self, ui, windows: Callable[[list[int]], list[int]], sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, click: Callable[[int, int], None] | None = None) -> None:
        self.ui, self.windows, self.sleep, self.clock, self.click = ui, windows, sleep, clock, click

    def _hit(self, control, worked: Callable[[], bool] | None = None, wait: float = 1.0) -> bool:
        """Press a control: Windows' accessibility press first; if that errors, or `worked` says nothing
        happened, a real mouse click on its middle (some of Discord's controls - its screen picker's
        tiles - only answer to a click). True if it worked (or there's no way to tell)."""
        try:
            control.press()
            pressed = True
        except Exception as exc:
            log.info("discord: %r won't press (%s) - clicking it", getattr(control, "name", "?"), exc)
            pressed = False
        if pressed:
            if worked is None:
                return True
            self.sleep(wait)
            if worked():
                return True
        rect = getattr(control, "rect", None)
        if self.click is None or not rect:
            return pressed and worked is None
        self.click(int((rect[0] + rect[2]) / 2), int((rect[1] + rect[3]) / 2))
        if worked is None:
            return True
        self.sleep(wait)
        return worked()

    def _controls(self, pids: list[int]) -> list:
        """Everything clickable in Discord's windows (two looks: Discord wakes its accessibility up
        on the first one)."""
        for attempt in range(2):
            found = []
            for hwnd in self.windows(pids):
                try:
                    found += [c for c in self.ui.clickables(hwnd) if c.name and getattr(c, "rect", None)]
                except Exception:
                    continue
            if found:
                return found
            if attempt == 0:
                self.sleep(0.4)
        return []

    def _named(self, pids: list[int], names: set[str]) -> list:
        """Exact names, any control type - the same lookup that finds Mute / Deafen."""
        found = []
        for hwnd in self.windows(pids):
            try:
                found += [b for b in self.ui.buttons(hwnd, names, with_rects=True)
                          if getattr(b, "rect", None) and b.rect[2] - b.rect[0] > 2 and b.rect[0] > -10000]
            except Exception:
                continue
        return found

    def _find(self, pids: list[int], pattern: re.Pattern, timeout: float = 0.0) -> list:
        """By name: Discord's exact labels first, then anything that matches loosely. Keeps
        looking for `timeout` seconds (at least two looks: the first can come back empty)."""
        names = NAMES.get(pattern.pattern, set())
        deadline = self.clock() + max(timeout, 0.8)
        while True:
            found = self._named(pids, names) if names else []
            if not found:
                found = [c for c in self._controls(pids) if pattern.match(c.name.strip())]
            if found or self.clock() >= deadline:
                return found
            self.sleep(0.35)

    def _missing(self, what: str, pids: list[int]) -> None:
        names = sorted({c.name.strip()[:30] for c in self._controls(pids)})
        log.info("discord: no %s button. Saw: %s", what, ", ".join(names[:60]) or "(nothing - Discord minimised?)")

    def _call_button(self, pids: list[int], pattern: re.Pattern, timeout: float = 0.0):
        """The one in the voice panel (by your Mute button), not one somewhere else - Discord's
        settings have "Disconnect" buttons for linked accounts too."""
        found = self._find(pids, pattern, timeout)
        if not found:
            return None
        mic = self._find(pids, MIC)
        if not mic:
            return min(found, key=lambda b: b.rect[0])
        m = mic[0].rect
        mx = (m[0] + m[2]) / 2                              # the voice panel sits just above your Mute button
        near = [b for b in found if abs(b.rect[1] - m[1]) < 220 and abs((b.rect[0] + b.rect[2]) / 2 - mx) < 260]
        return max(near, key=lambda b: b.rect[1]) if near else None

    def in_call(self, pids: list[int]) -> bool:
        return self._call_button(pids, LEAVE) is not None

    def join(self, pids: Callable[[], list[int]], timeout: float = 15.0) -> str:
        """After opening your call's link: press Join Voice.
        joined / pressed / already_in_call / no_join_button / no_discord."""
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            now = pids()
            if now:
                join = self._find(now, JOIN)
                if join:
                    join[0].press()
                    self.sleep(1.5)
                    return "joined" if self._call_button(now, LEAVE, timeout=3.0) else "pressed"
                if self.in_call(now) and self.clock() > deadline - timeout + 4:
                    return "already_in_call"                 # no Join button: you're in that call already
            self.sleep(0.6)
        if pids():
            self._missing("Join Voice", pids())
            return "no_join_button"
        return "no_discord"

    def stream(self, pids: list[int]) -> str:
        """streaming / already_streaming / picker (left open for you to pick) / no_call."""
        if self._find(pids, STOP_SHARE):
            return "already_streaming"
        share = self._call_button(pids, SHARE, timeout=3.0)
        if share is None:
            if not self.in_call(pids):
                return "no_call"
            self._missing("Share Your Screen", pids)
            return "no_share_button"
        self._hit(share, lambda: self._picker_open(pids), wait=1.2)
        live = self._pick_screen(pids)
        if live is None:
            self._missing("Go Live", pids)
            return "picker"
        live_now = lambda: self._call_button(pids, STOP_SHARE) is not None or bool(self._find(pids, STOP_SHARE))  # noqa: E731
        return "streaming" if self._hit(live, live_now, wait=1.5) or self._find(pids, STOP_SHARE, timeout=2.5) \
            else "picker"

    def _picker_open(self, pids: list[int]) -> bool:
        return any(GO_LIVE.match(c.name.strip()) or SCREENS_TAB.match(c.name.strip()) or
                   SCREEN_ITEM.match(c.name.strip()) for c in self._controls(pids) if not SHARE.match(c.name.strip()))

    def _pick_screen(self, pids: list[int]):
        """In the screen-share window: the Screens tab, your (first) screen, then Go Live."""
        for _ in range(6):
            things = self._controls(pids)
            tab = next((t for t in things if SCREENS_TAB.match(t.name.strip())), None)
            if tab is not None:
                self._hit(tab)
                self.sleep(0.5)
                things = self._controls(pids)
            screen = next((t for t in things if SCREEN_ITEM.match(t.name.strip())), None)
            if screen is not None:
                self._hit(screen)
                self.sleep(0.8)
            go = [c for c in self._controls(pids) if GO_LIVE.match(c.name.strip()) and not SHARE.match(c.name.strip())]
            go = go or self._find(pids, re.compile(r"^go live$", re.IGNORECASE))
            if go:
                return go[-1]
            self.sleep(0.5)
        return None

    def stop_stream(self, pids: list[int]) -> str:
        """stopped / not_streaming / pressed."""
        stop = self._call_button(pids, STOP_SHARE, timeout=3.0)          # the one in your voice panel
        if stop is None:
            found = self._find(pids, STOP_SHARE)
            if not found:
                return "not_streaming"
            stop = found[0]
        # stopped = your voice panel offers "Share Your Screen" again (other "Stop Streaming" text can linger)
        off = lambda: self._call_button(pids, STOP_SHARE) is None and (  # noqa: E731
            self._call_button(pids, SHARE) is not None or not self._find(pids, STOP_SHARE))
        if self._hit(stop, off, wait=1.0):
            return "stopped"
        self._missing("Stop Streaming (pressed, still streaming)", pids)
        return "pressed"

    def leave(self, pids: list[int]) -> str:
        """left / no_call / pressed."""
        button = self._call_button(pids, LEAVE, timeout=3.0)
        if button is None:
            self._missing("Disconnect", pids)
            return "no_call"
        if self._hit(button, lambda: self._call_button(pids, LEAVE) is None, wait=1.0):
            return "left"
        self._missing("Disconnect (pressed, still in the call)", pids)
        return "pressed"


class SpotifyButtons:
    """Searches inside the Spotify app and presses Play on the best-matching result.

    Spotify's search link (spotify:search:...) is ignored by some versions, so she
    types the search into Spotify's own search box, like you would."""

    def __init__(self, ui: UI, windows: Callable[[list[int]], list[int]],
                 sleep: Callable[[float], None] = time.sleep, desktop=None) -> None:
        self.ui, self.windows, self.sleep, self.desktop = ui, windows, sleep, desktop
        self.log: list[str] = []      # what happened, step by step (goes to capri.log)

    def press_track_play(self, pids: list[int], name: str) -> bool:
        """On the track page Spotify just opened: press its big Play button. There are two buttons
        called "Play" while paused - that one, and the player bar's at the very bottom (which
        would resume the old song) - so pick the highest one on screen, or one naming the song."""
        def wanted(b: Button) -> bool:
            return b.name == "Play" or (name and b.name.startswith("Play ") and name.lower() in b.name.lower())

        for hwnd in self.windows(pids):
            try:
                found = [b for b in self.ui.buttons(hwnd, None, with_rects=True) if wanted(b)]
            except Exception as exc:
                self.log.append(f"Play button lookup failed: {exc}")
                continue
            placed = [b for b in found if getattr(b, "rect", None)]
            window = self.desktop.window_rect(pids) if self.desktop is not None else None
            if window is not None:                         # never the player bar's (bottom ~130 px)
                placed = [b for b in placed if b.rect[1] < window[3] - 130]
            self.log.append(f"{len(found)} Play button(s), {len(placed)} on the page")
            if not placed:
                continue
            top = min(placed, key=lambda b: b.rect[1])
            if len(placed) > 1 and top.rect[1] == max(b.rect[1] for b in placed):
                continue                                   # can't tell them apart: don't guess
            top.press()
            return True
        return False

    def search(self, pids: list[int], terms: str) -> bool:
        """Type `terms` into Spotify's search box and press Enter. False = couldn't."""
        self.log = []
        self._pids = pids
        windows = self.windows(pids)
        if not windows or self.desktop is None:
            self.log.append("no Spotify window")
            return False
        hwnd = windows[0]
        if not self.desktop.bring_to_front(hwnd):
            # Never type or press keys blind: Ctrl+A / Enter would land in whatever IS in front
            # (that's the "selected my whole screen" bug). The caller falls back to spotify:search:.
            self.log.append("couldn't bring Spotify to the front - not pressing any keys")
            return False
        box = None
        try:
            edits = self.ui.edits(hwnd)
            box = next((e for e in edits if any(w in e.name.lower() for w in ("play", "search"))), None) or \
                (edits[0] if edits else None)
        except Exception as exc:
            self.log.append(f"search box lookup failed: {exc}")
        if box is not None:
            self.log.append(f"search box: {box.name!r}")
            try:
                box.focus()
            except Exception:
                box = None
        if box is None:                                # Spotify's own shortcut for its search box
            self.log.append("search box via Ctrl+L")
            self.desktop.press_keys("ctrl+l")
        self.sleep(0.3)
        if not self._still_front(hwnd):
            self.log.append("Spotify lost the focus - not typing")
            return False
        self.desktop.press_keys("ctrl+a")              # replace whatever was in the box
        self.desktop.type_text(terms)
        self.sleep(0.2)
        self.desktop.press_enter()
        return True

    def _still_front(self, hwnd: int) -> bool:
        front = getattr(self.desktop, "foreground", None)
        if front is None:
            return True
        try:
            got = front()
        except Exception:
            return True
        return not got or got == hwnd or got in self.windows(self._pids)

    @staticmethod
    def _score(label: str, wanted: str) -> float:
        return SequenceMatcher(None, label.lower(), wanted.lower()).ratio()

    def play(self, pids: list[int], wanted: str, timeout: float = 8.0) -> str:
        """'' if nothing could be played, else the result's label ("Let You Down by NF")."""
        def results(buttons: list[Button]) -> list[Button]:
            return [b for b in buttons if b.name.startswith("Play ") and len(b.name) > 5]

        def good(buttons: list[Button]) -> bool:      # wait until the search results are showing
            return any(self._score(b.name[5:], wanted) >= 0.5 for b in results(buttons))

        found = find_buttons(self.ui, self.windows(pids), None, good, timeout=timeout, sleep=self.sleep)
        candidates = results(found)
        self.log.append(f"{len(found)} buttons, {len(candidates)} Play buttons"
                        + (f", e.g. {candidates[0].name!r}" if candidates else ""))
        if not candidates:
            return ""
        best = max(enumerate(candidates), key=lambda ib: (self._score(ib[1].name[5:], wanted), -ib[0]))[1]
        best.press()
        self.sleep(1.0)
        after = find_buttons(self.ui, self.windows(pids), {"Pause"}, lambda b: bool(b), timeout=2.0,
                             sleep=self.sleep)
        return best.name[5:] if after else ""
