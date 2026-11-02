"""Carries out parsed commands. The only bridge from speech to actions.

Every action is one of a fixed set (launch a catalog entry, close matching
processes, open a search URL, control music, change a widget option). Text -
spoken or AI-generated - never becomes a command line.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote, quote_plus

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .. import lines, personality
from ..chat import SmallTalk
from ..chatbot import ChatBot
from ..states import State
from .apps import CLOSE_ASK, CLOSE_FORCE, PROGRAM, STEAM, WEBSITE
from . import files
from .catalog import Catalog, Match, Target, url_is_safe
from . import soundslike
from .understand import understand
from .guess import BARE_MINIMUM, guess_bare, guess_command
from .desktop import DISCORD_DEFAULT_KEYS, DISCORD_EXES, Desktop
from .parser import Intent, Kind, normalise, parse, type_where
from .parser import _search as parse_search_words
from .system import System

log = logging.getLogger("capri")

if TYPE_CHECKING:
    from ..ai.claude import ClaudeBrain
    from ..assistant import Assistant
    from ..integrations.spotify import Spotify
    from ..integrations.weather import Weather
    from ..settings import Settings
    from ..ui.companion import Companion

GRACEFUL_WAIT = 4.0     # seconds for an app to close after "clicking X"
FORCE_WAIT = 3.0
SEARCH_URL = "https://www.google.com/search?q={}"
SITE_SEARCH = {
    "google": SEARCH_URL, "youtube": "https://www.youtube.com/results?search_query={}",
    "bing": "https://www.bing.com/search?q={}", "duckduckgo": "https://duckduckgo.com/?q={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}", "reddit": "https://www.reddit.com/search/?q={}",
    "amazon": "https://www.amazon.com/s?k={}", "twitch": "https://www.twitch.tv/search?term={}",
    "github": "https://github.com/search?q={}",
}
BROWSERS = {"opera": ("Opera GX", "opera gx", "opera"), "chrome": ("Chrome", "chrome", "google chrome"),
            "edge": ("Edge", "microsoft edge", "edge"), "firefox": ("Firefox", "firefox", "mozilla firefox"),
            "brave": ("Brave", "brave", "brave browser")}
YOUTUBE_URL = "https://www.youtube.com/results?search_query={}"
# Music services without a "play this" API: their own search page, in your browser. ({q} = query-string
# encoded, {p} = path encoded.) Fixed addresses only - what you said only ever goes in the search part.
MUSIC_URLS = {
    "youtube_music": "https://music.youtube.com/search?q={q}", "soundcloud": "https://soundcloud.com/search?q={q}",
    "apple_music": "https://music.apple.com/us/search?term={q}", "deezer": "https://www.deezer.com/search/{p}",
    "tidal": "https://listen.tidal.com/search?q={q}", "amazon_music": "https://music.amazon.com/search/{p}",
    "bandcamp": "https://bandcamp.com/search?q={q}",
}
# what the mic makes of keyboard clatter / a mumble - never searched for
SEARCH_JUNK = (r"(?:(?:the|a|an|uh|um|er|erm|ah|oh|huh|hmm|mm|hm|ha|hey|and|but|so|i|it|is|in|to|of|on|yeah|yes"
               r"|ok|okay|what|like|just|this|that|you|me|my|one|two|no)\s*)+|[a-z]{1,2}")
SEARCH_MODE_MAX = 6          # searches in a row before search mode switches itself off
SEARCH_MODE_GAP = 2600       # ms after a search before she asks for the next one
SEARCH_MODE_STOP = (r"(?:no|nope|nah|stop|done|exit|quit|cancel|nothing|that s all|thats all|thats it|that s it|"
                    r"no thanks|nothing else|i m done|im done|exit search mode|stop searching|end search mode|"
                    r"never mind|nevermind|bye)(?: thanks| thank you| capri)?")
SPOTIFY_START_WAIT = 25.0   # seconds for a closed Spotify to start
SPOTIFY_SETTLE = 3.0        # then for its window to finish loading
DEAFEN_MEMORY = 3 * 3600   # how long she trusts "I deafened you" (you might undeafen by clicking)
GAME_MATCH = 0.92       # "play deadlock" launches the game only on a near-exact name match

MEDIA_LINES = {"pause": "Paused.", "resume": "Resuming.", "next": "Skipping.", "previous": "Going back one.",
               "volume_up": "Louder.", "volume_down": "Quieter."}
MEDIA_KEYS = {"pause": "play_pause", "resume": "play_pause", "next": "next", "previous": "previous",
              "volume_up": "volume_up", "volume_down": "volume_down"}


def spoken_duration(total: int) -> str:
    """300 -> '5 minutes', 5400 -> '1 hour and 30 minutes', 90 -> '1 minute and 30 seconds'."""
    total = max(0, int(total))
    h, rest = divmod(total, 3600)
    m, sec = divmod(rest, 60)
    parts = [f"{n} {unit}{'s' if n != 1 else ''}" for n, unit in ((h, "hour"), (m, "minute"), (sec, "second"))
             if n and not (unit == "second" and h)]
    return " and ".join(parts[:2]) if parts else "0 seconds"


def spoken_clock(hour: int, minute: int) -> str:
    """(7, 30) -> '7:30 AM', (22, 0) -> '10 PM'."""
    suffix = "AM" if hour < 12 else "PM"
    h = hour % 12 or 12
    return f"{h}:{minute:02d} {suffix}" if minute else f"{h} {suffix}"


@dataclass
class Services:
    """Optional helpers (Stage 5). Anything left as None is reported as not set up."""
    settings: Settings | None = None
    weather: Weather | None = None
    spotify: Spotify | None = None
    media_key: Callable[[str], None] | None = None
    brain: ClaudeBrain | None = None
    desktop: Desktop | None = None
    file_roots: Callable[[], list] | None = None    # your own folders, for "find my ..." (None = off)
    discord_buttons: Any = None     # presses Discord's real Mute / Deafen buttons (None = keys only)
    discord_call: Any = None        # app_buttons.DiscordCall: screen share, stop streaming, leave the call
    spotify_buttons: Any = None     # presses Play on a Spotify search result (None = just show the search)
    spotify_app: Any = None         # plays an exact track in the Spotify app (spotify_app.SpotifyApp)
    zap: Callable[[str, list[int], Callable[[], None]], None] | None = None   # lightning at a window she closes
    zap_at: Callable[[Any, list[int], Callable[[], None]], None] | None = None  # lightning at a button (Discord)
    psychosis: Any = None           # the shutdown cyberpsychosis show (ui/psychosis.py)
    minimize_visit: Callable[[str, list[int], Callable[[], None]], None] | None = None   # dash + zap its "_" button
    open_chat: Callable[[], None] | None = None     # shows the chat window
    games: Any = None               # GameWatch: drone mode while a game she launched runs
    open_folder: Callable[[str, str], None] | None = None   # open Explorer, dash + zap the folder in its sidebar
    screen: Any = None              # screen_targets.Finder: "click subscribe" / "click that"
    click_at: Callable[[Any], None] | None = None           # presses / clicks a found Target
    zap_rect: Callable[[Any, Callable[[], None]], None] | None = None   # she zaps a screen spot, then the click
    tabs: Any = None                # browser_tabs.BrowserTabs: "switch tabs on opera", "play the video"
    pc_info: Callable[[str], str] | None = None             # pc_stats.report: "what's using all my ram"
    screenshot: Callable[[str, Callable[[Any], None]], None] | None = None   # "take a screenshot"
    hands: Any = None               # screen_click.ScreenHands: highlight / double / right click / scroll
    music_find: Any = None          # finds songs on music apps (None = integrations.music_find; tests swap it)
    answers: Any = None             # quick answers, "what is X" (None = integrations.answers; tests swap it)
    about_you: Any = None           # about_you.AboutYou: what she remembers about you (your PC only)
    front: Callable[[], Any] | None = None   # the window in front (Windows), for "open X and type Y"
    in_game: Callable[[], bool] | None = None   # are you in a game right now (then: never tab you out of it)
    open_settings: Callable[[], None] | None = None   # "open your settings": her Settings window
    updates: Any = None             # ui.updates.UpdateManager: "check for updates" / "update yourself"
    restart: Callable[[], None] | None = None   # "restart yourself": a fresh Capri (installs a waiting update)
    doctor: Any = None              # ai.doctor.AIDoctor: "set up your brain"


class _Bridge(QObject):
    done = Signal(object, object)     # callback, result (or the exception it raised)



def _wanted(intent: Intent) -> str:
    """The song as said: "let you down by nf", "songs by nf", "blinding lights"."""
    if intent.query and intent.artist:
        return f"{intent.query} by {intent.artist}"
    return intent.query or intent.artist


def join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


class CommandRouter(QObject):
    def __init__(self, assistant: Assistant, companion: Companion | None, catalog: Catalog,
                 system: System, services: Services | None = None) -> None:
        super().__init__()
        self.services = services or Services()
        self._bridge = _Bridge()
        self._bridge.done.connect(self._finish_background)
        self._told_ai = False
        self.ai_status: tuple[str, bool, str] | None = None   # (when, worked?, what) - shown in Settings
        self._text = ""
        self.small_talk = SmallTalk()
        from ..about_you import AboutYou
        memory = self.services.about_you if self.services.about_you is not None else AboutYou(path=None)
        self.chatbot = ChatBot(self.small_talk, memory=memory)   # her own chat: always a reply, AI or not
        self._heard = self._prev_heard = self._last_line = ""
        self._deafened_by_me = False      # Capri pressed deafen (and not undeafen) since
        self._deafened_at = 0.0
        self.assistant = assistant
        if hasattr(assistant, "replied"):            # her last line, for "say that again"
            assistant.replied.connect(lambda text, _emotion: setattr(self, "_last_line", text))
        self.controller = assistant.controller
        self.companion = companion
        self.catalog = catalog
        self.system = system
        self._close_queue: list[str] = []
        self._closed: list[str] = []
        self._close_errors: list[str] = []

    # -- entry point -----------------------------------------------------------------
    def handle(self, text: str) -> None:
        self._prev_heard, self._heard = getattr(self, "_heard", ""), text     # for "repeat what I said"
        self._said_count = getattr(self, "_said_count", 0) + 1
        shortcut = self._shortcut_for(text)
        if shortcut is not None:                        # one of your own shortcuts ("gaming time")
            return self._run_shortcut(*shortcut)
        own = self._own_app_command(text)
        if own is not None:                             # your own app names / "also say" names come first
            self._learn_from_rephrase(own, text)
            return self.dispatch(own, text)
        steps = self._split_steps(text)
        if len(steps) >= 2:                             # "open notepad and type hi tiktok": one thing after another
            return self._run_steps(steps)
        taught = self._button_for(text)
        if taught is not None:                          # a button you taught her ("leave call" -> the red one)
            return self._press_taught(taught)
        intent = understand(text, lambda name: self._knows(name))   # extra words, other words, any order
        if intent != parse(text):
            self.controller.log("Understood", f'"{normalise(text)[:30]}" -> {intent.kind.value} '
                                              f'{" ".join(intent.targets) or intent.query}'[:60])
        if intent.kind is Kind.UNKNOWN:
            intent = self._act_on_it(intent, text)        # "throw on spotify": that's an ask, not chat
        if self._sounds_off(intent):                      # accents / bad mic: "lee call" -> "leave call"
            meant = soundslike.closest(normalise(text), self._sound_names())
            if meant is not None:
                self.controller.log("Heard", f'"{normalise(text)}" -> "{meant}"')
                intent = parse(meant)
        self._learn_from_rephrase(intent, text)
        self.dispatch(intent, text)

    OWN_VERBS = {"open": Kind.OPEN, "launch": Kind.OPEN, "start": Kind.OPEN, "run": Kind.OPEN, "load": Kind.OPEN,
                 "close": Kind.CLOSE, "quit": Kind.CLOSE, "exit": Kind.CLOSE, "kill": Kind.CLOSE, "shut": Kind.CLOSE}

    def _own_app_command(self, text: str) -> Intent | None:
        """'open my chat' when "my chat" is one of *your* app names or "also say" names (Settings -> Apps):
        that app, not one of her built-in commands that happens to sound the same (her chat window)."""
        t = re.sub(r"^(?:(?:can you|could you|would you|please|hey|yo|capri)\s+)*", "", normalise(text))
        t = re.sub(r"(?:\s+(?:please|for me|up|down))+$", "", t)
        verb, _, rest = t.partition(" ")
        kind = self.OWN_VERBS.get(verb)
        if kind is None:
            verb, rest, kind = None, t, Kind.OPEN               # just the name: open it
        rest = re.sub(r"^up ", "", rest)
        names = {rest, re.sub(r"^(?:the|my) ", "", rest)}
        for entry in getattr(self.catalog, "apps", []):
            aliases = {normalise(a) for a in entry.aliases if a.strip()}
            known = aliases | {normalise(entry.name)}
            # a verb + any of its names, or (on its own) one of your "also say" names
            if names & (known if verb else aliases):
                return Intent(kind, (entry.name.lower(),))
        return None

    def _act_on_it(self, intent: Intent, text: str) -> Intent:
        """Words that didn't parse but name something she can open with an 'open it' word ("hop on
        discord", "take me to youtube"), or just the name ("spotify"): do it. Else unchanged (chat)."""
        t = normalise(text)
        meant = (guess_command(t, lambda name: self._knows(name)) or
                 guess_bare(t, lambda name: self._knows(name, BARE_MINIMUM)))
        if not meant:
            return intent
        guessed = parse(meant)
        if guessed.kind is Kind.UNKNOWN:
            return intent
        self.controller.log("Got it", f'"{t}" -> {meant}')
        return guessed

    def _sounds_off(self, intent: Intent) -> bool:
        """Not a command - or an open / close of something she's never heard of ("close computa")."""
        if intent.kind is Kind.UNKNOWN:
            return True
        if intent.kind in (Kind.OPEN, Kind.CLOSE) and intent.targets:
            return not any(self._knows(t, 0.78) for t in intent.targets)
        return False

    def _sound_names(self) -> list[str]:
        """'open X' / 'close X' for your apps and games, to match misheard names against."""
        try:
            names = {getattr(e, "name", "") for e in getattr(self.catalog, "apps", [])} | \
                    {getattr(g, "name", "") for g in getattr(self.catalog, "games", [])}
        except Exception:
            names = set()
        names = sorted(n.lower() for n in names if n and len(n) < 30)[:150]
        return [f"{verb} {n}" for n in names for verb in ("open", "close")]

    def _knows(self, name: str, minimum: float = 0.86) -> bool:
        if not name.strip():
            return False
        try:
            return self.catalog.guess(name, minimum) is not None
        except Exception as exc:                               # a scan problem mustn't break talking
            log.warning(f"catalog guess failed: {exc}")
            return False

    # -- adapting to you: your shortcuts, and learning what you meant --------------------------------
    LEARN_DELAY_MS = 6000            # "want me to remember...?" waits until she's done with the command
    ACTION_KINDS = {Kind.OPEN, Kind.CLOSE, Kind.SEARCH, Kind.PLAY, Kind.MEDIA, Kind.MINIMIZE, Kind.RESTORE,
                    Kind.DISCORD, Kind.CLICK, Kind.REVEAL, Kind.TAB, Kind.VIDEO, Kind.PC_INFO, Kind.SCREENSHOT,
                    Kind.SCREEN, Kind.MOVE, Kind.WEATHER, Kind.RAIN, Kind.TIME, Kind.DATE, Kind.DRONE_ON,
                    Kind.DRONE_OFF, Kind.LOUNGE_ON, Kind.LOUNGE_OFF, Kind.PERSONALITY}

    def _shortcuts(self) -> list:
        s = self.services.settings
        return [p for p in (getattr(s, "shortcuts", None) or []) if isinstance(p, (list, tuple)) and len(p) == 2]

    def _shortcut_for(self, text: str) -> tuple[str, str] | None:
        from .fuzzy import similarity
        said = normalise(text)
        if not said:
            return None
        for phrase, command in self._shortcuts():
            key = normalise(phrase)
            if said == key or (len(key) >= 6 and similarity(said, key) >= 0.9):
                return phrase, command
        return None

    def _run_shortcut(self, phrase: str, command: str) -> None:
        """Your shortcut: its command(s), one after another ("open steam and then play lofi")."""
        parts = [p.strip() for p in re.split(r"\s+(?:and then|then)\s+", command) if p.strip()]
        self.controller.log("Shortcut", f'"{phrase}"')
        for i, part in enumerate(parts):
            QTimer.singleShot(i * 2500, lambda part=part: self.dispatch(parse(part), part))

    def _shortcut(self, intent: Intent) -> None:
        """'When I say gaming time, open steam and discord'."""
        s = self.services.settings
        phrase, command = intent.targets[:2]
        first = parse(command)
        if s is None or not phrase or first.kind in (Kind.UNKNOWN, Kind.CHAT):
            return self.assistant.show_result(State.ERROR, f"I don't know how to \u201c{command}\u201d yet.")
        self._save_shortcut(phrase, command)
        self.assistant.show_result(State.SUCCESS, personality.flavor(
            f"Got it. When you say \u201c{phrase}\u201d, I'll {command}.", self._persona()), emotion="happy")

    def _save_shortcut(self, phrase: str, command: str) -> None:
        s = self.services.settings
        key = normalise(phrase)
        s.shortcuts = [p for p in self._shortcuts() if normalise(p[0]) != key] + [[phrase, command]]
        s.save()
        self.controller.log("Learned", f'"{phrase}" -> {command}')

    def _forget(self, intent: Intent) -> None:
        s = self.services.settings
        key = normalise(intent.targets[0] if intent.targets else "")
        kept = [p for p in self._shortcuts() if normalise(p[0]) != key]
        if s is None or len(kept) == len(self._shortcuts()):
            return self.assistant.show_result(State.ERROR, f"I don't have a shortcut for \u201c{key}\u201d.")
        s.shortcuts = kept
        s.save()
        self.assistant.show_result(State.SUCCESS, f"Forgotten. \u201c{key}\u201d is just words again.")

    def _learn_from_rephrase(self, intent: Intent, text: str) -> None:
        """She didn't get something, then you said it another way and it worked: offer to remember
        that the first way means the second (a shortcut). Asked once she's done, never mid-action."""
        missed = getattr(self, "_missed", None)
        if intent.kind not in self.ACTION_KINDS or missed is None:
            return
        said, at = missed
        self._missed = None
        if time.monotonic() - at > 40 or normalise(said) == normalise(text) or self._shortcut_for(said):
            return
        count = self._said_count

        def ask() -> None:
            if self._said_count != count or getattr(self.assistant, "_busy", False) or \
                    getattr(self.assistant, "_pending", None) is not None:
                return                                    # you've moved on: don't interrupt
            self.assistant.confirm(f"Want me to remember that \u201c{said}\u201d means \u201c{text}\u201d? "
                                   f"Say yes or no.",
                                   lambda yes: (self._save_shortcut(said, text), self.assistant.show_result(
                                       State.SUCCESS, "Learned it.", emotion="happy")) if yes else
                                   self.assistant.show_result(State.IDLE, "Okay, I won't."))
        QTimer.singleShot(self.LEARN_DELAY_MS, ask)

    @staticmethod
    def choose(guesses: list[str]) -> str:
        """Of the recogniser's guesses (best first), the first that's a command she knows -
        so "oh pen this cord" loses to the runner-up "open discord"."""
        for guess in guesses:
            if parse(guess).kind is not Kind.UNKNOWN:
                return guess
        return guesses[0]

    def dispatch(self, intent: Intent, text: str = "") -> None:
        self._text = text      # the original words, for the AI fallback ("" = came from the AI)
        if intent.kind is not Kind.SEARCH_MODE:
            self._search_ui(False)                        # anything else ends search mode's look
        handler = {
            Kind.OPEN: self._open, Kind.CLOSE: self._close, Kind.SEARCH: self._search,
            Kind.TIME: self._time, Kind.DATE: self._date,
            Kind.COMPACT_ON: lambda i: self._widget("compact", True, "compact_on"),
            Kind.COMPACT_OFF: lambda i: self._widget("compact", False, "compact_off"),
            Kind.PANEL_HIDE: lambda i: self._widget("panel", False, "panel_hide"),
            Kind.PANEL_SHOW: lambda i: self._widget("panel", True, "panel_show"),
            Kind.HIDE: lambda i: self._widget("hidden", True, "hide"),
            Kind.SHOW: lambda i: self._widget("hidden", False, "show"),
            Kind.LOUNGE_ON: lambda i: self._widget("lounge", True, "lounge_on"),
            Kind.LOUNGE_OFF: lambda i: self._widget("lounge", False, "lounge_off"),
            Kind.CANCEL: lambda i: self._result(State.IDLE, "cancel"),
            Kind.PLAY: self._play, Kind.MEDIA: self._media, Kind.NOW_PLAYING: self._now_playing,
            Kind.WEATHER: self._weather, Kind.RAIN: self._weather,
            Kind.POWER: self._power, Kind.MINIMIZE: self._minimize, Kind.RESTORE: self._restore,
            Kind.DISCORD: self._discord, Kind.CHAT: self._chat, Kind.REVEAL: self._reveal,
            Kind.SEARCH_MODE: lambda i: self._search_mode(0),
            Kind.CHAT_WINDOW: self._chat_window,
            Kind.DRONE_ON: lambda i: self._drone(True), Kind.DRONE_OFF: lambda i: self._drone(False),
            Kind.DRONE_CORNER: self._drone_corner, Kind.CLICK: self._click, Kind.CORRECTION: self._learn_fix,
            Kind.TAB: self._tab, Kind.VIDEO: self._video,
            Kind.PC_INFO: self._pc_info, Kind.SCREENSHOT: self._screenshot, Kind.PERSONALITY: self._personality,
            Kind.SCREEN: self._screen, Kind.REPEAT: self._repeat, Kind.MOVE: self._move, Kind.AI_SETUP: self._ai_setup,
            Kind.SHORTCUT: self._shortcut, Kind.FORGET: self._forget, Kind.MUSIC_SERVICE: self._music_service,
            Kind.LEARN_BUTTON: self._learn_button, Kind.FORGET_BUTTON: self._forget_button, Kind.TYPE: self._type, Kind.HAIR: self._hair, Kind.SETTINGS: self._settings, Kind.UPDATE: self._update, Kind.RESTART_APP: self._restart_app,
            Kind.QUIET: self._quiet, Kind.VOICE: self._voice, Kind.TIMER: self._timer,
            Kind.PERCH_ON: lambda i: self._perch(True), Kind.PERCH_OFF: lambda i: self._perch(False),
            Kind.HYPE_ON: lambda i: self._hype(True), Kind.HYPE_OFF: lambda i: self._hype(False),
        }.get(intent.kind)
        if handler is None:
            return self._unknown(intent, text)
        if intent.kind is Kind.SEARCH:
            # Searching only happens inside search mode: "search cats" switches it on and asks.
            self.controller.log("Search", "say it in search mode")
            return self._search_mode(0)
        handler(intent)

    def explain(self, text: str) -> str:
        """Dry run for the Settings 'Try a command' box: what *would* happen."""
        intent = parse(text)
        if intent.kind is Kind.OPEN:
            lines = []
            for spoken in intent.targets:
                m = self.catalog.find(spoken)
                lines.append(f'Open "{spoken}" → ' +
                             (f"{m.target.describe()}  [match {m.score:.0%}]" if m else "nothing matches"))
            return "\n".join(lines)
        if intent.kind is Kind.CLOSE:
            lines = []
            processes = self._processes()
            for spoken in intent.targets:
                name, pids, mode = self.catalog.running_for(spoken, processes)
                state = f"{len(pids)} process(es) running" if pids else "not running"
                lines.append(f'Close "{spoken}" → {name}: {state}, close mode "{mode}"')
            return "\n".join(lines)
        if intent.kind is Kind.SEARCH:
            where = intent.targets[0] if intent.targets else "google"
            return f"Search for “{intent.query}” " + (f"in {where.title()}" if where in BROWSERS else f"on {where.title()}")
        if intent.kind is Kind.PLAY:
            game = None if intent.artist else self._game_for(intent.query)
            if game:
                return f'Play "{intent.query}" → launch {game.target.describe()}'
            if "youtube" in intent.targets:
                return f'Search YouTube for "{_wanted(intent)}"'
            how = "on Spotify" if self._spotify_ready() else \
                "by opening Spotify's search (connect Spotify to auto-play)"
            song = f'the song "{intent.query}" by {intent.artist}' if intent.query and intent.artist else \
                f"songs by {intent.artist}" if intent.artist else f'"{intent.query}"'
            return f"Play {song} {how}"
        if intent.kind is Kind.POWER:
            return {"lock": "Lock the PC"}.get(intent.query, f"{intent.query.capitalize()} the PC (asks yes/no first)")
        if intent.kind is Kind.MINIMIZE:
            return ("Minimise every window" if not intent.targets else "Minimise the window in front"
                    if intent.targets == ("this",) else "Minimise " + ", ".join(intent.targets))
        if intent.kind is Kind.DISCORD:
            return f"Press Discord's {intent.query} key"
        if intent.kind is Kind.REVEAL:
            m = self.catalog.find(intent.targets[0])
            return (f'Show "{intent.targets[0]}" in File Explorer → ' +
                    (m.target.describe() if m else "search your own folders for it"))
        if intent.kind is Kind.CHAT:
            return "Small talk" + (" (AI)" if self._ai_available() else "")
        if intent.kind is Kind.MEDIA:
            return f"Music: {intent.query.replace('_', ' ')}"
        if intent.kind in (Kind.WEATHER, Kind.RAIN):
            place = intent.query or (self.services.settings.weather_city if self.services.settings else "")
            return f"Weather for {place or '(set your city in Settings)'}, {intent.day}"
        if intent.kind is Kind.UNKNOWN:
            s = self.services.settings
            ai = bool(s and s.ai_enabled and self.services.brain)
            return "Not a built-in command: " + ("she asks the AI." if ai else "she'd say she doesn't understand.")
        return intent.kind.value.replace("_", " ").capitalize()

    # -- open ----------------------------------------------------------------------------
    def _open(self, intent: Intent) -> None:
        if len(intent.targets) == 1 and self.catalog.find(intent.targets[0]) is None and self._files_on():
            return self._open_file(intent.targets[0])      # not an app: maybe one of your files / folders
        if self._ai_available() and self._text and all(self.catalog.find(t) is None for t in intent.targets):
            # "open that blocky strap thing": no app by that name, so let the AI work out what was meant.
            # (An AI-suggested name comes back with no text, so this can't loop.)
            return self._unknown(intent, self._text)
        launched, problems = [], []
        for spoken in intent.targets:
            match = self.catalog.find(spoken)
            if match is None:
                self.controller.log("Error", f'no app called "{spoken}"')
                problems.append(self._phrase("not_found", thing=spoken))
                if self._heard:
                    self._missed = (self._heard, time.monotonic())   # say it another way and she learns
                continue
            problem = self._launch(match)
            if problem:
                problems.append(problem)
            else:
                launched.append(match.target.name)
        if problems:
            self.assistant.show_result(State.ERROR, problems[0] if not launched else
                                       f"Opened {join_names(launched)}. {problems[0]}",
                                       emotion="confused")
        elif len(launched) == 1:
            self._result(State.SUCCESS, "launch", name=launched[0])
        else:
            self._result(State.SUCCESS, "launch_many", names=join_names(launched))

    def launch_entry(self, entry) -> str | None:
        """Settings window 'Test launch'. Returns a problem message, or None."""
        problem = self._launch(Match(Target(entry.name, "app", entry=entry), 1.0, entry.name))
        self.assistant.show_result(State.ERROR if problem else State.SUCCESS,
                                   problem or f"Launching {entry.name}.")
        return problem

    def _launch(self, match: Match) -> str | None:
        """Launch a catalog target. Returns a problem message, or None on success."""
        t: Target = match.target
        if match.heard.lower() != t.name.lower():
            self.controller.log("Match", f'"{match.heard}" → {t.name}')
        self.controller.set_state(State.LAUNCHING, f"Opening {t.name}...")
        try:
            if t.entry is not None:
                e = t.entry
                if not e.is_configured():
                    self.controller.log("Fix", f"add {e.name}'s path in Settings")
                    return self._phrase("not_set_up", name=e.name)
                if e.launch_type == STEAM:
                    if not e.target.strip().isdigit():
                        return f"{e.name}'s Steam app id looks wrong."
                    self.system.open_item(f"steam://rungameid/{e.target.strip()}")
                    game = next((g for g in self.catalog.games if g.appid == e.target.strip()), None)
                    self._game_launched(e.name, game.install_dir if game else None)
                elif e.launch_type == WEBSITE:
                    if not url_is_safe(e.target):
                        return f"{e.name}'s link isn't allowed."
                    self.system.open_item(e.target.strip())
                elif e.launch_type == PROGRAM:
                    self.system.launch_program(e.expanded_target(), e.arguments)
            elif t.game is not None:
                self.system.open_item(f"steam://rungameid/{t.game.appid}")
                self._game_launched(t.game.name, t.game.install_dir)
            elif t.shortcut is not None:
                self.system.open_item(str(t.shortcut.path))
            elif t.installed is not None:                  # from Windows' own app list (Store apps too)
                self.system.open_item("shell:AppsFolder\\" + t.installed.app_id)
            elif t.place:                                  # a fixed folder / Windows place
                if self.services.open_folder is not None and os.path.isdir(t.place):
                    self.services.open_folder(Path(t.place).name, t.place)   # Explorer, then she zaps it open
                else:
                    self.system.open_item(t.place)
            elif t.url:
                if not url_is_safe(t.url):
                    return "That link isn't allowed."
                self.system.open_item(t.url)
        except FileNotFoundError:
            self.controller.log("Fix", f"{t.name}'s path is wrong, check Settings")
            return f"Couldn't find {t.name} on this PC."
        except OSError as exc:
            self.controller.log("Error", str(exc)[:60])
            return f"Couldn't start {t.name}."
        self.controller.log("Launch", t.describe())
        return None

    # -- close -----------------------------------------------------------------------------
    def _processes(self):
        try:
            return self.system.processes()
        except Exception as exc:
            self.controller.log("Error", f"can't list programs: {str(exc)[:40]}")
            return []

    def _close(self, intent: Intent) -> None:
        self._close_queue = list(intent.targets)
        self._closed, self._close_errors = [], []
        self._close_next()

    def _close_next(self) -> None:
        if not self._close_queue:
            return self._close_summary()
        spoken = self._close_queue.pop(0)
        name, pids, mode = self.catalog.running_for(spoken, self._processes())
        if not pids:
            self._close_errors.append(self._phrase("not_running", name=name))
            return self._close_next()
        self.controller.set_state(State.PROCESSING, f"Closing {name}...")
        if mode == CLOSE_FORCE:
            self._force(name, pids)
        elif mode == CLOSE_ASK:
            self.assistant.confirm(self._phrase("ask_close", name=name),
                                   lambda yes: self._graceful(name, pids, then_force=True) if yes
                                   else self._skip(name))
        else:
            self._graceful(name, pids, then_force=False)

    def _graceful(self, name: str, pids: list[int], then_force: bool) -> None:
        self.controller.set_state(State.PROCESSING, f"Closing {name}...")
        self._zap(name, pids, lambda: self.system.request_close(pids))

        def after(remaining: list[int]) -> None:
            if not remaining:
                self._done(name)
            elif then_force:
                self._force(name, remaining)   # you already said yes
            else:
                self.assistant.confirm(self._phrase("ask_force", name=name),
                                       lambda yes: self._force(name, remaining) if yes else self._skip(name))
        self._wait_exit(pids, GRACEFUL_WAIT, after)

    def _force(self, name: str, pids: list[int]) -> None:
        self._zap(name, pids, lambda: self.system.terminate(pids))

        def after(remaining: list[int]) -> None:
            if remaining:
                self._close_errors.append(self._phrase("cant_close", name=name))
                self.controller.log("Error", f"{name} refused to close")
                self._close_next()
            else:
                self._done(name)
        self._wait_exit(pids, FORCE_WAIT, after)

    def _zap(self, name: str, pids: list[int], close: Callable[[], None]) -> None:
        """She blasts the window with red lightning; `close` runs at the impact."""
        if self.services.zap is None:
            return close()
        self.services.zap(name, pids, close)

    def _done(self, name: str) -> None:
        self.controller.log("Closed", name)
        self._closed.append(name)
        self._close_next()

    def _skip(self, name: str) -> None:
        self.controller.log("Kept", name)
        self._close_errors.append(self._phrase("kept", name=name))
        self._close_next()

    def _close_summary(self) -> None:
        if self._closed and not self._close_errors:
            self._result(State.SUCCESS, "closed", names=join_names(self._closed))
        elif self._closed:
            self.assistant.show_result(State.SUCCESS, self._phrase("closed", names=join_names(self._closed)) + " " +
                                       self._close_errors[0], emotion="smirk")
        elif self._close_errors:
            leaving = self._close_errors[0].startswith("Leaving")
            self.assistant.show_result(State.IDLE if leaving else State.ERROR, self._close_errors[0],
                                       emotion="neutral" if leaving else "smirk")

    def _wait_exit(self, pids: list[int], seconds: float, done: Callable[[list[int]], None]) -> None:
        deadline = [seconds]

        def poll() -> None:
            remaining = self.system.running(pids)
            deadline[0] -= 0.25
            if not remaining or deadline[0] <= 0:
                timer.stop()
                done(remaining)

        timer = QTimer(self)
        timer.setInterval(250)
        timer.timeout.connect(poll)
        timer.start()

    # -- everything else -----------------------------------------------------------------------
    def _search(self, intent: Intent) -> None:
        where = intent.targets[0] if intent.targets else ""
        url = SITE_SEARCH.get(where, SEARCH_URL).format(quote_plus(intent.query))
        self.controller.log("Search", f"{intent.query} ({where or 'google'})")
        if where in BROWSERS:
            return self._search_in_browser(where, url, intent.query)
        self.system.open_item(url)
        if where and where != "google":
            return self._result(State.SUCCESS, "search_in", query=intent.query, where=where.title()
                                if where != "youtube" else "YouTube")
        self._result(State.SUCCESS, "search", query=intent.query)

    def _search_mode(self, done: int, quiet: int = 0) -> None:
        """'Go into search mode': she asks what to search, searches it ("cats on YouTube" works),
        and asks again - no wake word needed, 15 s to answer each time. One silence gets a
        "still there?"; a second one (or "stop") ends it. Ends itself after SEARCH_MODE_MAX."""
        if done >= SEARCH_MODE_MAX:
            return self._result(State.IDLE, "search_mode_off")
        key = "search_mode_ask" if done == 0 and quiet == 0 else "search_mode_still" if quiet else "search_mode_more"
        question = self._phrase(key)
        if done == 0 and quiet == 0:
            self.controller.log("Search", "search mode on")
        self._search_ui(True)

        def answer(text: str | None) -> None:
            words = normalise(text or "")
            if getattr(self.assistant, "interrupted_by_typing", False):
                return self._result(State.IDLE, "search_mode_typing")    # you're busy typing: leave it
            if words and not re.fullmatch(SEARCH_MODE_STOP, words) and re.fullmatch(SEARCH_JUNK, words):
                self.controller.log("Ignored", f'"{words}" - not a search')
                words = ""                                               # keyboard noise, "uh", "the"...
            if not words:
                if quiet == 0:
                    return self._search_mode(done, quiet=1)     # once: "still there?"
                return self._result(State.IDLE, "search_mode_off")
            if re.fullmatch(SEARCH_MODE_STOP, words):
                return self._result(State.IDLE, "search_mode_off")
            intent = parse(text)
            if intent.kind is not Kind.SEARCH or not intent.query:
                intent = parse_search_words(re.sub(r"^(?:search(?: for| up)?|look up|google)\s+", "", words))
            self._text = text
            self._search(intent)
            QTimer.singleShot(SEARCH_MODE_GAP, lambda: self._search_mode(done + 1))
        self.assistant.ask(question, answer, label="" if done == 0 and quiet == 0 else "[SEARCH MODE] ")

    def _search_in_browser(self, browser: str, url: str, query: str) -> None:
        """'search up cats on opera': a Google search, opened in *that* browser. The browser is
        started from its own program file with the search address as its only argument."""
        label, *names = BROWSERS[browser]
        exe = None
        for spoken in names:
            m = self.catalog.find(spoken)
            if m is not None and m.score >= 0.85:
                path = self._file_of(m.target)
                if path and path.lower().endswith(".exe"):
                    exe, label = path, m.target.name
                    break
        if exe is not None:
            try:
                self.system.launch_program(exe, [url])
                return self._result(State.SUCCESS, "search_in", query=query, where=label)
            except OSError as exc:
                self.controller.log("Error", f"{label}: {str(exc)[:40]}")
        self.system.open_item(url)                            # not installed / not found: default browser
        self.controller.log("Fix", f"add {label} in Settings > Apps")
        self._result(State.SUCCESS, "search_default", query=query, where=label)

    def _time(self, intent: Intent) -> None:
        self._result(State.SUCCESS, "time", time=datetime.now().strftime('%I:%M %p').lstrip('0'))

    def _date(self, intent: Intent) -> None:
        now = datetime.now()
        self._result(State.SUCCESS, "date", date=f"{now.strftime('%A')}, {now.day} {now.strftime('%B')}")

    def _widget(self, what: str, on: bool, key: str) -> None:
        c = self.companion
        if c is None:
            return self.assistant.show_result(State.ERROR, "Can't do that here.")
        if what == "compact":
            c.set_compact(on)
            if not on and getattr(c, "drone", False):
                self._drone(False)
                return
        elif what == "panel":
            c.set_show_panel(on)
        elif what == "hidden":
            c.set_hidden(on)
        elif what == "lounge":
            sprites = getattr(c, "sprites", None)
            style = getattr(getattr(c, "settings", None), "character_style", "body")
            if on and (sprites is None or sprites.lying is None or style == "classic"):
                return self.assistant.show_result(State.ERROR, "I can only lie down in the new art style.")
            c.set_lounge(on)
            if not on and hasattr(c, "reset_position"):
                c.reset_position()                       # "get up": back to her spot, the very bottom-right
        self._result(State.SUCCESS, key)

    # -- what she says (plain or Night City slang) ------------------------------------------
    def _slang(self) -> bool:
        s = self.services.settings
        return bool(s and s.slang)

    def _phrase(self, key: str, **fields) -> str:
        return lines.line(key, self._slang(), **fields)[0]

    def _persona(self) -> str:
        s = self.services.settings
        return getattr(s, "personality", "edgerunner") if s else "edgerunner"

    def _result(self, state: State, key: str, speak: bool = True, **fields) -> None:
        text, emotion = lines.line(key, self._slang(), **fields)
        if state is State.SUCCESS:                     # done: in her personality's own words, or a remark
            text = personality.line(key, self._persona(), fields) or personality.flavor(text, self._persona())
        if key in ("search_mode_off", "search_mode_typing"):
            self._search_ui(False)
        if state is State.ERROR and key in ("not_found", "unknown", "click_not_found", "tab_not_found") and self._heard:
            self._missed = (self._heard, time.monotonic())   # if you then say it another way and it works, she learns
        self.assistant.show_result(state, text, speak=speak, emotion=emotion)

    def _search_ui(self, on: bool) -> None:
        """Search mode: her panel in inverted colours while it's on."""
        c = self.companion
        if c is not None and hasattr(c, "set_search_mode"):
            c.set_search_mode(on)

    def _say_chat(self, text: str, topic: str = "") -> None:
        """Her own chatbot's reply (no AI, or the AI's down) - she always answers. "What is X":
        she looks it up (Wikipedia's summary). A question she can't answer: she offers to search it."""
        words, emotion = self.chatbot.reply(text or topic, self._persona(), self._slang(), topic=topic)
        s = self.services.settings
        follow_up = bool(s is None or s.conversation)
        kind, subject = getattr(self.chatbot, "last_kind", ""), getattr(self.chatbot, "last_subject", "")
        if kind == "lookup" and subject:
            self.controller.set_state(State.PROCESSING, f"Looking up {subject}...")

            def answered(answer) -> None:
                if isinstance(answer, str) and answer:
                    self.controller.log("Answer", f"Wikipedia: {subject}"[:40])
                    return self.assistant.show_result(State.SPEAKING, answer, emotion="happy", follow_up=follow_up)
                self._offer_search(words, subject)
            return self._background(lambda: self._answers().lookup(subject), answered)
        if kind == "dont_know" and text.strip():
            return self._offer_search(words, normalise(text))
        self.assistant.show_result(State.SPEAKING, words, emotion=emotion, follow_up=follow_up)

    def _answers(self):
        from ..integrations import answers
        return getattr(self.services, "answers", None) or answers

    def _offer_search(self, question: str, query: str) -> None:
        """'Not sure. Want me to look it up?' - yes: a web search for it."""
        from .parser import parse_yes_no

        def answer(said: str | None) -> None:
            yes = parse_yes_no(said or "")
            if re.fullmatch(r"(?:yes |yeah |sure )?(?:look it up|search it|search for it|google it|please|go for it|"
                            r"find out|do that)", normalise(said or "")):
                yes = True
            if yes is True:
                return self._search(Intent(Kind.SEARCH, query=query))     # you said yes: search it now
            if yes is False or not (said or "").strip():
                return self.assistant.show_result(State.IDLE, "Okay, never mind.", emotion="neutral")
            self.handle(said)                                  # you said something else: that's next
        self.assistant.ask(question, answer, emotion="confused", wait=8.0)

    # -- background work (network) ------------------------------------------------------
    def _background(self, work: Callable[[], Any], then: Callable[[Any], None]) -> None:
        job = [work, then, self._bridge]

        def run() -> None:
            work, then, bridge = job
            job.clear()
            try:
                result = work()
            except Exception as exc:   # handed to `then` on the UI thread
                result = exc
            work = None
            bridge.done.emit(then, result)
            # Let go here: the last reference to her (and her Qt objects) must die on the UI thread,
            # never in this worker - Qt objects destroyed off their thread corrupt memory.
            then = bridge = result = None
        threading.Thread(target=run, daemon=True).start()

    @Slot(object, object)
    def _finish_background(self, then, result) -> None:
        then(result)

    # -- music ------------------------------------------------------------------------------
    def _spotify_ready(self) -> bool:
        sp = self.services.spotify
        return bool(sp is not None and sp.connected)

    def _game_for(self, spoken: str) -> Match | None:
        m = self.catalog.find(spoken)
        if m and m.score >= GAME_MATCH and m.target.kind in ("app", "steam", "shortcut", "installed") and \
                (m.target.entry is None or m.target.entry.is_configured()):
            return m
        return None

    def _play(self, intent: Intent) -> None:
        query, artist = intent.query, intent.artist
        wanted = _wanted(intent)
        if "youtube" in intent.targets:
            return self._play_youtube(wanted)
        if intent.targets and intent.targets[0] in MUSIC_URLS:          # "play X on soundcloud"
            return self._play_on(intent.targets[0], wanted)
        game = None if artist else self._game_for(query)
        if game is not None:                       # "play deadlock" = launch the game
            problem = self._launch(game)
            if problem:
                return self.assistant.show_result(State.ERROR, problem)
            return self._result(State.SUCCESS, "launch", name=game.target.name)
        default = getattr(self.services.settings, "music_service", "spotify")
        if default in MUSIC_URLS:                                       # your music app isn't Spotify
            return self._play_on(default, wanted)
        if default == "youtube":
            return self._play_youtube(wanted)
        if self.services.spotify_app is not None or not self._spotify_ready():
            # On Windows always the Spotify app itself: find the exact track (with Spotify's own
            # search when connected), open it in the app on this PC and check it's playing - the
            # same steps as Settings -> Test Spotify. (Premium's remote "play" could start it on
            # another device, or nowhere, while saying it worked.)
            return self._spotify_app_play(query, artist, wanted)
        from ..integrations import spotify as sp
        self.controller.set_state(State.PROCESSING, f"Finding {wanted}...")

        def done(result) -> None:
            if isinstance(result, sp.Track):
                self.controller.log("Play", f"{result.name} - {result.artist}")
                self._result(State.SUCCESS, "playing", speak=False,          # the music is the answer
                             track=result.name, artist=result.artist)
            elif isinstance(result, (sp.PremiumRequired, sp.NotConnected)):
                if isinstance(result, sp.PremiumRequired):
                    self.controller.log("Note", "no Premium: playing it in the app")
                self._spotify_app_play(query, artist, wanted)
            elif isinstance(result, sp.NoDevice):                # app not ready in time: do it in the app
                self._spotify_app_play(query, artist, wanted)
            elif isinstance(result, sp.SpotifyError) and str(result).startswith("Couldn't find"):
                self._result(State.ERROR, "not_on_spotify", query=wanted)
            elif isinstance(result, Exception):
                self.assistant.show_result(State.ERROR, str(result) or "Spotify glitched.")
        self._background(lambda: self.services.spotify.play(query, artist), done)

    def _play_youtube(self, wanted: str) -> None:
        """The video itself (found from YouTube's results), playing - or the search if it can't be found."""
        from ..integrations import music_find
        self.controller.set_state(State.PROCESSING, f"Finding {wanted}...")

        def done(video) -> None:
            if isinstance(video, str):
                self.system.open_item(music_find.WATCH.format(video))
                self.controller.log("Play", f"YouTube: {wanted}"[:40])
                return self._result(State.SUCCESS, "youtube_playing", query=wanted)
            self.system.open_item(YOUTUBE_URL.format(quote_plus(wanted)))
            self._result(State.SUCCESS, "youtube", query=wanted)
        self._background(lambda: self._finder().find_video(wanted), done)

    def _finder(self):
        from ..integrations import music_find
        return getattr(self.services, "music_find", None) or music_find

    def _play_on(self, service: str, wanted: str) -> None:
        """Any music app: find the song's own page and open it (YouTube Music starts playing by
        itself); the others get their Play button pressed once the page is up. No song page to
        be found (SoundCloud, Tidal, Amazon): their search, and Play on the first result."""
        from .parser import MUSIC_SERVICES
        label = MUSIC_SERVICES[service][1]
        self.controller.set_state(State.PROCESSING, f"Finding {wanted} on {label}...")

        def found(url) -> None:
            finder = self._finder()
            if not isinstance(url, str):
                url = None
            self.system.open_item(url or MUSIC_URLS[service].format(q=quote_plus(wanted), p=quote(wanted)))
            self.controller.log("Play", f"{label}: {wanted}"[:40])
            if url and service in finder.AUTOPLAYS:
                return self._result(State.SUCCESS, "music_site_playing", service=label, query=wanted)
            self._press_play(label, wanted)
        self._background(lambda: self._finder().find_track(service, wanted), found)

    PLAY_WAIT = 3.5          # seconds for the page to load before looking for its Play button
    PLAY_TRIES = 5

    def _press_play(self, label: str, wanted: str) -> None:
        """The music page is opening: wait for it, then zap its Play button (the first song's)."""
        tabs = self.services.tabs
        if tabs is None or self.services.click_at is None:          # not on Windows: the page is open
            return self._result(State.SUCCESS, "music_site", service=label, query=wanted)
        self.controller.set_state(State.PROCESSING, f"Opening {label}...")
        sleep = getattr(self, "_sleep", time.sleep)

        def look():
            sleep(self.PLAY_WAIT)
            for _ in range(self.PLAY_TRIES):
                hwnd = tabs.front() or tabs.window("")
                button = tabs.play_button(hwnd) if hwnd else None
                if button is not None:
                    return button
                sleep(1.5)
            return None

        def found(button) -> None:
            from ..integrations.browser_tabs import is_playing
            if isinstance(button, Exception) or button is None:
                return self._result(State.SUCCESS, "music_site", service=label, query=wanted)
            if is_playing(button):                                      # it started by itself
                return self._result(State.SUCCESS, "music_site_playing", service=label, query=wanted)

            def pressed(outcome) -> None:
                if isinstance(outcome, Exception):
                    return self._result(State.SUCCESS, "music_site", service=label, query=wanted)
                self.controller.log("Click", f"{label}: Play")
                self._background(check, lambda now: self._result(
                    State.SUCCESS, "music_site_playing" if now is True else "music_site_pressed",
                    service=label, query=wanted))

            def check() -> bool:                                        # did it start? (Play became Pause)
                sleep(1.5)
                hwnd = tabs.front() or tabs.window("")
                now = tabs.play_button(hwnd) if hwnd else None
                return now is not None and is_playing(now)
            self._press_on_screen(button.name, button.rect, button.element, pressed)
        self._background(look, found)

    def _music_service(self, intent: Intent) -> None:
        """'Use SoundCloud for music': where "play ..." goes from now on."""
        from .parser import MUSIC_SERVICES
        key = intent.targets[0] if intent.targets else "spotify"
        s = self.services.settings
        if s is not None:
            s.music_service = key
            s.save()
        self._result(State.SUCCESS, "music_service", service=MUSIC_SERVICES[key][1])

    def _spotify_app_play(self, query: str, artist: str, wanted: str) -> None:
        """Find the exact track, open it in the Spotify app and check it's playing (spotify_app.py)."""
        app = self.services.spotify_app
        if app is None:
            return self._spotify_search(wanted, f"{query} {artist}".strip())
        self.controller.set_state(State.PROCESSING, f"Finding {wanted}...")

        def done(result) -> None:
            status = getattr(result, "status", "")
            if status == "playing":
                self.controller.log("Play", result.title[:60])
                return self.assistant.show_result(State.SUCCESS, self._phrase("playing_found", label=result.title),
                                                  speak=False, emotion="happy")
            if status == "opened":
                self.controller.log("Play", f"opened {result.title[:50]}")
                return self._result(State.SUCCESS, "spotify_opened", name=result.title)
            if status == "not_installed":                       # no Spotify app at all: YouTube
                self.system.open_item(YOUTUBE_URL.format(quote_plus(wanted)))
                return self._result(State.SUCCESS, "youtube", query=wanted)
            if status == "no_spotify":                          # just slow to open: stay in Spotify
                return self._spotify_open_search(wanted, f"{query} {artist}".strip())
            if isinstance(result, Exception):
                self.controller.log("Error", f"Spotify: {str(result)[:40]}")
            self.controller.log("Note", "couldn't find the exact track - showing the search")
            self._spotify_search(wanted, f"{query} {artist}".strip())
        self._background(lambda: app.play(query or artist, artist if query else ""), done)

    def _spotify_search(self, query: str, terms: str = "") -> None:
        """No Spotify connection (or no Premium): search in the Spotify app, then press Play on
        the best-matching result. Spotify ignores a search link while it's still starting up,
        so if it isn't running she starts it first and waits for it."""
        terms = terms or query
        buttons = self.services.spotify_buttons
        running = self._spotify_pids()
        if buttons is None and running:
            return self._spotify_open_search(query, terms)
        try:
            if not running:
                self.system.open_item("spotify:")
        except OSError:
            self.system.open_item(YOUTUBE_URL.format(quote_plus(query)))   # no Spotify app installed
            return self.assistant.show_result(State.SUCCESS, f"No Spotify here, so YouTube it is: {query}.")
        self.controller.set_state(State.PROCESSING, f"Finding {query} in Spotify...")

        def work():
            pids = running
            for _ in range(int(SPOTIFY_START_WAIT / 0.5)):
                if pids:
                    break
                time.sleep(0.5)
                pids = self._spotify_pids()
            if not running:
                time.sleep(SPOTIFY_SETTLE)                  # let it finish loading first
            typed = False
            if buttons is not None and pids and hasattr(buttons, "search"):
                typed = buttons.search(pids, terms)          # type it into Spotify's own search box
            if not typed:
                self.system.open_item("spotify:search:" + quote(terms))
            if buttons is None or not pids:
                return ""
            label = buttons.play(pids, terms)
            for step in getattr(buttons, "log", [])[-6:]:
                log.info("spotify: %s", step)
            return label

        def done(result) -> None:
            if isinstance(result, str) and result:
                self.controller.log("Play", result)
                return self.assistant.show_result(State.SUCCESS, self._phrase("playing_found", label=result),
                                                  speak=False, emotion="happy")
            if isinstance(result, Exception):
                self.controller.log("Error", f"Spotify: {str(result)[:40]}")
            if not self._spotify_ready():
                self.controller.log("Tip", "connect Spotify in Settings to auto-play")
            self._result(State.SUCCESS, "spotify_search", query=query)
        self._background(work, done)

    def _spotify_open_search(self, query: str, terms: str) -> None:
        self.system.open_item("spotify:search:" + quote(terms))
        if not self._spotify_ready():
            self.controller.log("Tip", "connect Spotify in Settings to auto-play")
        self._result(State.SUCCESS, "spotify_search", query=query)

    def _spotify_pids(self) -> list[int]:
        return [p.pid for p in self._processes() if p.name.lower() == "spotify.exe"]

    def _media(self, intent: Intent) -> None:
        action = intent.query
        line = MEDIA_LINES.get(action, "Done.")

        def by_key() -> None:
            if self.services.media_key is None:
                return self.assistant.show_result(State.ERROR, "Media keys aren't available here.")
            try:
                self.services.media_key(MEDIA_KEYS[action])
            except OSError as exc:
                return self.assistant.show_result(State.ERROR, str(exc)[:60])
            self.assistant.show_result(State.SUCCESS, line, speak=False)   # don't talk over the music

        if self._spotify_ready() and action in ("pause", "resume", "next", "previous"):
            sp = self.services.spotify
            call = {"pause": sp.pause, "resume": sp.resume, "next": sp.next, "previous": sp.previous}[action]
            # Exact control through Spotify; media keys if that fails (e.g. it's playing elsewhere).
            self._background(call, lambda r: by_key() if isinstance(r, Exception) else
                             self.assistant.show_result(State.SUCCESS, line, speak=False))
        else:
            by_key()

    def _now_playing(self, intent: Intent) -> None:
        if not self._spotify_ready():
            return self.assistant.show_result(State.ERROR, "Connect Spotify in Settings and I can tell you.")

        def done(result) -> None:
            if isinstance(result, Exception):
                self.assistant.show_result(State.ERROR, str(result) or "Spotify glitched.")
            elif result is None:
                self._result(State.IDLE, "nothing_playing")
            else:
                self._result(State.SUCCESS, "now_playing", track=result.name, artist=result.artist)
        self._background(self.services.spotify.now_playing, done)

    # -- PC power, windows, Discord ------------------------------------------------------------
    def _desktop(self) -> Desktop | None:
        if self.services.desktop is None:
            self.assistant.show_result(State.ERROR, "I can't control the PC here.")
        return self.services.desktop

    def _power(self, intent: Intent) -> None:
        action = intent.query
        if self._desktop() is None:
            return
        if action == "lock":
            return self._power_go(action)
        # Shut down / restart / sleep: only after a clear spoken "yes".
        self.assistant.confirm(self._phrase("ask_" + action),
                               lambda yes: self._power_go(action) if yes else self._result(State.IDLE, "power_kept"))

    def _power_go(self, action: str) -> None:
        text, emotion = lines.line("go_" + action, self._slang())
        self.controller.log("Power", action)

        psychosis = self.services.psychosis

        def go() -> None:
            try:
                self.services.desktop.power(action)
            except (OSError, ValueError) as exc:
                if psychosis is not None:
                    psychosis.abort()                     # Windows said no: give the screen back
                self.controller.log("Error", str(exc)[:60])
                self._result(State.ERROR, "power_failed")

        self.controller.set_state(State.SUCCESS, text, emotion)
        if action == "lock":
            go()                                          # instant; she says it as the screen locks
            return self.assistant.show_result(State.SUCCESS, text, emotion=emotion)
        # Shut down / restart / sleep: quiet from here on - her goodbye is only written, and anything she
        # was still saying stops, so nothing talks over the PC going down.
        speaker = getattr(self.assistant, "speaker", None)
        if speaker is not None and hasattr(speaker, "stop"):
            speaker.stop()
        if action == "shutdown" and psychosis is not None:
            return psychosis.play(go)                     # the screen glitches out, flatlines, then it shuts down
        go()

    def _minimize(self, intent: Intent) -> None:
        desktop = self._desktop()
        if desktop is None:
            return
        try:
            if not intent.targets:
                count = desktop.minimize_all()
                return self._result(State.SUCCESS, "minimized_all" if count else "nothing_to_minimize")
            if intent.targets == ("this",):
                count = desktop.minimize_foreground()
                return self._result(State.SUCCESS, "minimized_this" if count else "nothing_to_minimize")
            done, missing = [], []
            processes = self._processes()
            for i, spoken in enumerate(intent.targets):
                name, pids, _mode = self.catalog.running_for(spoken, processes)
                if pids and i == 0 and self.services.minimize_visit is not None and hasattr(desktop, "main_window") \
                        and desktop.main_window(pids) is not None:
                    # she dashes over and zaps its minimise button; it minimises on impact
                    self.services.minimize_visit(name, pids, lambda pids=pids: desktop.minimize(pids))
                    done.append(name)
                elif pids and desktop.minimize(pids):
                    done.append(name)
                else:
                    missing.append(self._phrase("no_window", name=name) if pids else
                                   self._phrase("not_running", name=name))
        except OSError as exc:
            return self.assistant.show_result(State.ERROR, str(exc)[:60])
        if done and not missing:
            self._result(State.SUCCESS, "minimized", name=join_names(done))
        elif done:
            self.assistant.show_result(State.SUCCESS, self._phrase("minimized", name=join_names(done)) + " " + missing[0])
        else:
            self.assistant.show_result(State.ERROR, missing[0], emotion="confused")

    def _restore(self, intent: Intent) -> None:
        desktop = self._desktop()
        if desktop is None:
            return
        try:
            count = desktop.restore()
        except OSError as exc:
            return self.assistant.show_result(State.ERROR, str(exc)[:60])
        self._result(State.SUCCESS if count else State.ERROR, "restored" if count else "nothing_to_restore")

    def _discord(self, intent: Intent) -> None:
        """Presses Discord's own Mute / Deafen button (and reads it back, so she knows your
        real state). If the buttons can't be reached, falls back to Discord's keyboard shortcuts."""
        desktop = self._desktop()
        if desktop is None:
            return
        action = intent.query                              # mute | unmute | deafen | undeafen | stream | ...
        if action == "join":                               # opens Discord if it isn't running
            return self._discord_join()
        pids = [p.pid for p in self._processes() if p.name.lower() in DISCORD_EXES]
        if not pids:
            return self._result(State.ERROR, "discord_off")
        if action in ("stream", "stop_stream", "leave"):
            return self._discord_call(action, pids)
        # Mid-game: nothing may take the focus off your game. Your own Discord keybind (works from
        # anywhere), else Discord's button pressed in the background - never bringing Discord forward.
        gaming = self._in_game()
        if gaming and self._own_discord_key(action):
            return self._discord_keys(action, pids)
        buttons = self.services.discord_buttons
        if buttons is None:
            return self._discord_keys(action, pids) if not gaming else self._result(State.ERROR, "discord_in_game")
        kind = "mute" if action in ("mute", "unmute") else "deafen"
        want = action in ("mute", "deafen")

        def done(outcome) -> None:
            if isinstance(outcome, Exception) or outcome == "unavailable":
                if isinstance(outcome, Exception):
                    self.controller.log("Discord", f"buttons: {str(outcome)[:40]}")
                if gaming:                                 # the keys would bring Discord forward: not mid-game
                    self.controller.log("Fix", "Settings > PC & chat > Discord keybinds")
                    return self._result(State.ERROR, "discord_in_game")
                return self._discord_keys(action, pids)
            self.controller.log("Discord", f"{action}: {outcome}")
            if outcome == "failed":
                return self._result(State.ERROR, "discord_failed")
            if outcome == "pressed":
                return self._result(State.SUCCESS, "discord_" + action, speak=False)
            self._result(State.SUCCESS, "discord_" + outcome, speak=False)   # don't talk over your call
        def press() -> None:
            self._background(lambda: buttons.set(pids, kind, want), done)

        zap_at = self.services.zap_at
        if gaming or zap_at is None or not hasattr(buttons, "locate"):
            return press()                                 # (mid-game: no lightning across your game)

        def aim(rect) -> None:                      # red lag lightning at the button, pressed on impact
            try:
                zap_at(None if isinstance(rect, Exception) else rect, pids, press, kind=kind)
            except TypeError:                         # a zapper that doesn't know about kinds
                zap_at(None if isinstance(rect, Exception) else rect, pids, press)
        self._background(lambda: buttons.locate(pids, kind), aim)

    def _discord_join(self) -> None:
        """'Join call': opens your saved voice channel in Discord and presses Join Voice."""
        from ..integrations.app_buttons import call_link
        s = self.services.settings
        link = call_link(getattr(s, "discord_call", "") or "") if s is not None else None
        if link is None:
            return self._result(State.ERROR, "discord_no_link")
        call = self.services.discord_call
        if call is None:
            return self._result(State.ERROR, "discord_call_windows")
        self.controller.set_state(State.PROCESSING, "Joining your call...")
        try:
            self.system.open_item(link)
        except OSError as exc:
            return self.assistant.show_result(State.ERROR, f"Couldn't open Discord: {str(exc)[:40]}")

        def pids() -> list[int]:
            return [p.pid for p in self._processes() if p.name.lower() in DISCORD_EXES]

        def done(outcome) -> None:
            if isinstance(outcome, Exception):
                self.controller.log("Discord", f"join: {str(outcome)[:40]}")
                return self._result(State.ERROR, "discord_call_failed")
            self.controller.log("Discord", f"join: {outcome}")
            line = {"pressed": "discord_joined"}.get(outcome, "discord_" + outcome)
            self._result(State.SUCCESS if outcome in ("joined", "pressed", "already_in_call") else State.ERROR, line)
        self._background(lambda: call.join(pids), done)

    def _discord_call(self, action: str, pids: list[int]) -> None:
        """'Stream my screen' / 'stop streaming' / 'leave call': Discord's own buttons (screen
        share -> your screen -> Go Live; Stop Streaming; Disconnect), checked afterwards."""
        call = self.services.discord_call
        if call is None:
            return self._result(State.ERROR, "discord_call_windows")
        self.controller.set_state(State.PROCESSING, {"stream": "Going live...", "stop_stream": "Stopping your stream...",
                                                     "leave": "Leaving the call..."}[action])

        def done(outcome) -> None:
            if isinstance(outcome, Exception):
                self.controller.log("Discord", f"call: {str(outcome)[:40]}")
                return self._result(State.ERROR, "discord_call_failed")
            self.controller.log("Discord", f"{action}: {outcome}")
            line = {"pressed": "discord_call_failed"}.get(outcome, "discord_" + outcome)
            good = outcome in ("streaming", "stopped", "left", "picker")
            self._result(State.SUCCESS if good else State.ERROR, line)
        s = self.services.settings
        leave_key = (getattr(s, "discord_leave_key", "") or "").strip() if s is not None else ""
        if action == "leave" and leave_key and self.services.desktop is not None:
            try:                                      # your Discord "Disconnect" keybind: works from anywhere
                self.services.desktop.press_keys(leave_key)
            except (OSError, ValueError) as exc:
                return self.assistant.show_result(State.ERROR, f"Couldn't press your Disconnect key: {str(exc)[:40]}")
            self.controller.log("Discord", f"leave ({leave_key})")
            return self._result(State.SUCCESS, "discord_left")
        work = {"stream": call.stream, "stop_stream": call.stop_stream, "leave": call.leave}[action]
        self._background(lambda: work(pids), done)

    def _in_game(self) -> bool:
        check = self.services.in_game
        try:
            return bool(check and check())
        except Exception:
            return False

    def _own_discord_key(self, action: str) -> str:
        """Your Discord keybind for this (Settings -> PC & chat), or "" - the same choice as _discord_keys."""
        s = self.services.settings
        if s is None:
            return ""
        deafened = self._deafened_by_me and time.monotonic() - self._deafened_at < DEAFEN_MEMORY
        key = "deafen" if (action == "unmute" and deafened) or action in ("deafen", "undeafen") else "mute"
        return (s.discord_mute_key if key == "mute" else s.discord_deafen_key).strip()

    def _discord_keys(self, action: str, pids: list[int]) -> None:
        """Fallback: Discord's keyboard shortcuts (they toggle, so she can't know your state).
        If *she* deafened you, "unmute me" undeafens you: while deafened, Discord keeps your
        mic off whatever the mute key does."""
        desktop = self.services.desktop
        deafened = self._deafened_by_me and time.monotonic() - self._deafened_at < DEAFEN_MEMORY
        key, line = ("deafen", "discord_undeafen_for_mic") if action == "unmute" and deafened else \
            ("mute" if action in ("mute", "unmute") else "deafen", "discord_" + action)
        s = self.services.settings
        own_key = (s.discord_mute_key if key == "mute" else s.discord_deafen_key).strip() if s else ""
        try:
            if own_key:
                desktop.press_keys(own_key)                # your Discord keybind: works from anywhere
            elif not desktop.press_in_window(pids, DISCORD_DEFAULT_KEYS[key]):
                self.controller.log("Fix", "Settings > PC & chat > Discord keybinds")
                return self._result(State.ERROR, "discord_hidden")
        except (OSError, ValueError) as exc:
            return self.assistant.show_result(State.ERROR, f"Couldn't press Discord's key: {str(exc)[:40]}")
        if key == "deafen":
            self._deafened_by_me = action == "deafen"
            self._deafened_at = time.monotonic()
        self.controller.log("Discord", f"{action} ({own_key or DISCORD_DEFAULT_KEYS[key]})")
        self._result(State.SUCCESS, line, speak=False)

    # -- File Explorer and your files -----------------------------------------------------------
    def _files_on(self) -> bool:
        return self.services.file_roots is not None

    def _find_file(self, spoken: str, then: Callable[[files.Found | None], None]) -> None:
        self.controller.set_state(State.PROCESSING, f"Looking for {spoken}...")
        roots = self.services.file_roots

        def done(result) -> None:
            then(None if isinstance(result, Exception) else result)
        self._background(lambda: files.find(spoken, roots()), done)

    def _open_file(self, spoken: str) -> None:
        text = self._text

        def found(hit: files.Found | None) -> None:
            if hit is None:
                if self._ai_available() and text:
                    return self._unknown(Intent(Kind.UNKNOWN), text)
                self.controller.log("Error", f'no app or file called "{spoken}"')
                return self._result(State.ERROR, "not_found", thing=spoken)
            name = hit.path.name
            if hit.runnable:                                # never run a program found by name
                self.system.reveal(str(hit.path))
                return self._result(State.SUCCESS, "runnable_found", name=name)
            self.system.open_item(str(hit.path))
            self.controller.log("Open", str(hit.path)[-60:])
            self._result(State.SUCCESS, "opened_file", name=name)
        self._find_file(spoken, found)

    def _reveal(self, intent: Intent) -> None:
        spoken = intent.targets[0]
        m = self.catalog.find(spoken)
        t = m.target if m else None
        try:
            if t is not None and t.place:
                self.system.open_item(t.place)
                return self._result(State.SUCCESS, "revealed", name=t.name)
            if t is not None and t.installed is not None and t.installed.exe is None:
                self.system.open_item("shell:AppsFolder")   # Store apps have no folder you can browse
                return self._result(State.SUCCESS, "store_app_place", name=t.name)
            path = self._file_of(t) if t is not None else None
            if path is not None:
                self.system.reveal(path)
                self.controller.log("Explorer", path[-60:])
                return self._result(State.SUCCESS, "revealed", name=t.name)
        except OSError as exc:
            return self.assistant.show_result(State.ERROR, f"Couldn't open File Explorer: {str(exc)[:40]}")
        if not self._files_on():
            return self._result(State.ERROR, "not_found", thing=spoken)

        def found(hit: files.Found | None) -> None:
            if hit is None:
                return self._result(State.ERROR, "not_in_files", thing=spoken)
            self.system.reveal(str(hit.path))
            self.controller.log("Explorer", str(hit.path)[-60:])
            self._result(State.SUCCESS, "revealed", name=hit.path.name)
        self._find_file(spoken, found)

    @staticmethod
    def _file_of(t: Target) -> str | None:
        """Where an app lives on disk, if it has a real file."""
        candidates = []
        if t.entry is not None and t.entry.launch_type == PROGRAM and t.entry.is_configured():
            candidates.append(t.entry.expanded_target())
        if t.game is not None:
            candidates.append(str(t.game.install_dir))
        if t.shortcut is not None:
            if t.shortcut.target is not None:
                candidates.append(str(t.shortcut.target))
            candidates.append(str(t.shortcut.path))
        if t.installed is not None and t.installed.exe is not None:
            candidates.append(str(t.installed.exe))
        return next((c for c in candidates if os.path.exists(c)), None)

    def _drone(self, on: bool) -> None:
        games, c = self.services.games, self.companion
        if games is not None and not on:
            games.stop()
        if c is not None and hasattr(c, "set_drone"):
            c.set_drone(on)
            return self._result(State.SUCCESS, "drone_on" if on else "drone_off")
        self.assistant.show_result(State.ERROR, "Can't do that here.")

    def _click(self, intent: Intent) -> None:
        """'Click subscribe' / 'click that': find it on screen, zap it from where she is (lying on
        the panel, or standing), and click it as the bolt lands. Risky labels are asked first."""
        finder = self.services.screen
        if finder is None or self.services.click_at is None:
            return self.assistant.show_result(State.ERROR, "I can only click things on Windows.")
        label = intent.targets[0] if intent.targets else ""
        self.controller.set_state(State.PROCESSING, f'Looking for "{label}"...' if label else
                                  "Looking at what you're pointing at...")

        def found(target) -> None:
            if isinstance(target, Exception) or target is None:
                if isinstance(target, Exception):
                    self.controller.log("Error", f"click: {str(target)[:40]}")
                return self._result(State.ERROR, "click_not_found" if label else "click_nothing", label=label)
            from ..integrations.screen_targets import RISKY
            if target.risky or RISKY.search(label):
                return self.assistant.confirm(f'Click "{target.name[:40]}"? Say yes or no.',
                                              lambda yes: go(target) if yes else self._result(State.IDLE, "click_cancelled"))
            go(target)

        def go(target) -> None:
            def clicked(outcome) -> None:
                if isinstance(outcome, Exception):
                    return self._result(State.ERROR, "click_failed", name=target.name[:40])
                self.controller.log("Click", f"{target.name[:40]} ({target.how})")
                self._result(State.SUCCESS, "clicked", name=target.name[:40], speak=False)

            def fire() -> None:                           # at the bolt's impact
                self._background(lambda: self.services.click_at(target), clicked)
            if self.services.zap_rect is not None:
                self.services.zap_rect(target.rect, fire)
            else:
                fire()
        self._background(lambda: finder.find(label), found)

    def _press_on_screen(self, name: str, rect, element, then: Callable[[Any], None], before=None) -> None:
        """Zap a thing she found (a tab, a player button) and press it as the bolt lands."""
        from ..integrations.screen_targets import Target
        target = Target(name, rect, "ui", element)

        def fire() -> None:
            def work() -> None:
                if before is not None:
                    before()
                self.services.click_at(target)
            self._background(work, then)
        if self.services.zap_rect is not None:
            self.services.zap_rect(rect, fire)
        else:
            fire()

    def _tab(self, intent: Intent) -> None:
        """'Switch tabs on Opera': she reads the tab names, asks which one ("the twitch one"),
        and zaps it. 'Switch to the twitch tab' goes straight there."""
        from ..integrations.browser_tabs import pick_tab, short
        tabs = self.services.tabs
        if tabs is None or self.services.click_at is None:
            return self.assistant.show_result(State.ERROR, "I can only switch tabs on Windows.")
        browser = intent.targets[0] if intent.targets else ""
        label = BROWSERS[browser][0] if browser in BROWSERS else (browser.title() or "your browser")
        self.controller.set_state(State.PROCESSING, "Looking at your tabs...")

        def look():
            hwnd = tabs.window(browser)
            return None if hwnd is None else (hwnd, tabs.tabs(hwnd))

        def found(result) -> None:
            if isinstance(result, Exception):
                self.controller.log("Error", f"tabs: {str(result)[:40]}")
                return self._result(State.ERROR, "tab_none", name=label)
            if result is None:
                return self._result(State.ERROR, "tab_no_browser", name=label)
            hwnd, found_tabs = result
            if not found_tabs:
                return self._result(State.ERROR, "tab_none", name=label)
            if intent.query:
                return choose(hwnd, found_tabs, intent.query)
            names = [short(t.name) for t in found_tabs[:4]]
            listed = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]
            if len(found_tabs) > 4:
                listed = ", ".join(names) + f" and {len(found_tabs) - 4} more"
            question, emotion = lines.line("tab_which", self._slang(), names=listed)
            self.assistant.ask(question, lambda text: choose(hwnd, found_tabs, text or ""), emotion=emotion)

        def choose(hwnd, found_tabs, said: str) -> None:
            if not said.strip() or re.fullmatch(r"(?:never ?mind|cancel|none|nothing|no|forget it|stay)", normalise(said)):
                return self._result(State.IDLE, "tab_cancelled")
            tab = pick_tab(said, found_tabs)
            if tab is None:
                return self._result(State.ERROR, "tab_not_found", label=normalise(said)[:30])
            self.controller.log("Tab", short(tab.name))

            def done(outcome) -> None:
                if isinstance(outcome, Exception):
                    return self._result(State.ERROR, "click_failed", name=short(tab.name))
                self._result(State.SUCCESS, "tab_switched", name=short(tab.name), speak=False)
            desktop = self.services.desktop
            self._press_on_screen(tab.name, tab.rect, tab.element, done,
                                  before=(lambda: desktop.bring_to_front(hwnd)) if desktop is not None else None)
        self._background(look, found)

    def _video(self, intent: Intent) -> None:
        """'Play the video' / 'pause the video': the player's own Play / Pause button (YouTube,
        Twitch...) in the window you're on, zapped. No button found: the play/pause media key."""
        from ..integrations.browser_tabs import is_playing
        tabs, want = self.services.tabs, intent.query
        if tabs is None or self.services.click_at is None:
            return self._media(Intent(Kind.MEDIA, query="resume" if want == "play" else "pause"))
        self.controller.set_state(State.PROCESSING, "Finding the player...")

        def look():
            hwnd = tabs.front() or tabs.window("")
            if hwnd is None:
                return None
            button = tabs.player_button(hwnd)
            if button is None and hwnd != tabs.window(""):
                other = tabs.window("")                    # you're in another app: the browser's player
                button = tabs.player_button(other) if other is not None else None
            return button

        def by_key() -> None:
            if self.services.media_key is None:
                return self._result(State.ERROR, "click_not_found", label="play")
            try:
                self.services.media_key(MEDIA_KEYS["resume"])
            except OSError as exc:
                return self.assistant.show_result(State.ERROR, str(exc)[:60])
            self._result(State.SUCCESS, "video_key")

        def found(button) -> None:
            if isinstance(button, Exception) or button is None:
                return by_key()
            if is_playing(button) == (want == "play"):
                return self._result(State.IDLE, "video_already_playing" if want == "play" else "video_already_paused")
            self.controller.log("Video", want)
            self._press_on_screen(button.name, button.rect, button.element, lambda outcome: (
                self._result(State.ERROR, "click_failed", name=button.name[:30]) if isinstance(outcome, Exception)
                else self._result(State.SUCCESS, "video_played" if want == "play" else "video_paused", speak=False)))
        self._background(look, found)

    # -- hands on your screen ------------------------------------------------------------------------
    def _screen(self, intent: Intent) -> None:
        """Highlight / copy words on screen, double / right click things, scroll, and a fixed set of
        key presses (select all, undo, refresh...) into the window you're using."""
        from .parser import SCREEN_KEYS
        action = intent.query
        if action in SCREEN_KEYS:
            desktop = self.services.desktop
            if desktop is None:
                return self.assistant.show_result(State.ERROR, "I can't press keys here.")
            _pattern, combo, line = SCREEN_KEYS[action]
            try:
                desktop.press_keys(combo)
            except Exception as exc:
                return self.assistant.show_result(State.ERROR, str(exc)[:60] or "Those keys didn't go through.")
            self.controller.log("Keys", combo)
            return self.assistant.show_result(State.SUCCESS, personality.flavor(line, self._persona()), speak=False)
        hands = self.services.hands
        if hands is None:
            return self.assistant.show_result(State.ERROR, "I can only do that on Windows.")
        if action.startswith("scroll_"):
            amount = {"bit": 3, "lot": 15}.get(intent.targets[0] if intent.targets else "", 6)
            notches = amount if action == "scroll_up" else -amount
            self._background(lambda: hands.scroll(notches), lambda r: self.assistant.show_result(
                State.ERROR if isinstance(r, Exception) else State.SUCCESS,
                "Couldn't scroll." if isinstance(r, Exception) else f"Scrolled {action[7:]}.", speak=False))
            return
        finder = self.services.screen
        label = intent.targets[0] if intent.targets else ""
        if finder is None or not label:
            return self.assistant.show_result(State.ERROR, "I can only do that on Windows.")
        self.controller.set_state(State.PROCESSING, f'Looking for "{label}"...')
        find = finder.find_text if action in ("highlight", "copy") and hasattr(finder, "find_text") else finder.find
        done_lines = {"highlight": "Highlighted \u201c{n}\u201d.", "copy": "Copied \u201c{n}\u201d.",
                      "double_click": "Double-clicked {n}.", "right_click": "Right-clicked {n}."}

        def act(target) -> None:
            if action == "highlight":
                hands.select(target)
            elif action == "copy":
                hands.select(target)
                time.sleep(0.1)
                self.services.desktop.press_keys("ctrl+c")
            elif action == "double_click":
                hands.double(target)
            else:
                hands.right(target)

        def go(target) -> None:
            def finished(outcome) -> None:
                if isinstance(outcome, Exception):
                    return self._result(State.ERROR, "click_failed", name=target.name[:40])
                self.controller.log(action.replace("_", " ").title(), target.name[:40])
                self.assistant.show_result(State.SUCCESS, personality.flavor(
                    done_lines[action].format(n=target.name[:40]), self._persona()), speak=False)

            def fire() -> None:
                self._background(lambda: act(target), finished)
            if self.services.zap_rect is not None:
                self.services.zap_rect(target.rect, fire)
            else:
                fire()

        def found(target) -> None:
            if isinstance(target, Exception) or target is None:
                return self._result(State.ERROR, "click_not_found", label=label)
            from ..integrations.screen_targets import RISKY
            if action == "double_click" and (target.risky or RISKY.search(label)):
                return self.assistant.confirm(f'Double-click "{target.name[:40]}"? Say yes or no.',
                                              lambda yes: go(target) if yes else self._result(State.IDLE, "click_cancelled"))
            go(target)
        self._background(lambda: find(label), found)

    def _repeat(self, intent: Intent) -> None:
        """'Repeat what I said' / 'say that again' / 'repeat after me ...'."""
        if intent.query == "after":
            return self.assistant.show_result(State.SPEAKING, intent.targets[0], emotion="playful")
        if intent.query == "me":
            line = self._last_line
            return self.assistant.show_result(State.SPEAKING, line or "I haven't said anything yet.")
        heard = self._prev_heard.strip()
        if not heard:
            return self.assistant.show_result(State.SPEAKING, "You haven't said anything yet.")
        self.assistant.show_result(State.SPEAKING, f"You said: \u201c{heard}\u201d", emotion="playful")

    def _move(self, intent: Intent) -> None:
        """'Go to the bottom left' / 'move to the top right' / 'go to my other monitor'."""
        c = self.companion
        spot = intent.targets[0] if intent.targets else "bottom_right"
        if c is None or not hasattr(c, "move_to"):
            return self.assistant.show_result(State.ERROR, "Can't move here.")
        if not c.move_to(spot):
            return self.assistant.show_result(State.ERROR, "There's no other monitor to go to.")
        where = {"other_screen": "your other monitor", "main_screen": "your main monitor",
                 "middle": "the middle"}.get(spot, "the " + spot.replace("_", " "))
        self.assistant.show_result(State.SUCCESS, personality.flavor(f"Teleported to {where}.", self._persona()),
                                   speak=False)

    def _ai_setup(self, intent: Intent) -> None:
        """'Set up your brain' / 'is your AI working': find out why she can't think, and fix it."""
        from ..ai import doctor as dr
        doc = self.services.doctor
        if doc is None:
            return self.assistant.show_result(State.ERROR, "I can't check my AI here.")
        self.controller.set_state(State.PROCESSING, "Checking my brain...")

        def refresh() -> None:
            brain = self.services.brain
            if hasattr(brain, "refresh"):
                brain.refresh()

        def checked(result, retried: bool = False) -> None:
            if isinstance(result, Exception):
                return self.assistant.show_result(State.ERROR, "I couldn't check my AI.")
            code, message = result
            if code in (dr.READY, dr.CLAUDE, dr.ONLINE):
                refresh()
                return self.assistant.show_result(State.SUCCESS, message, emotion="happy")
            if code in (dr.NEEDS_KEY, getattr(dr, "UNREACHABLE", "unreachable")):   # only you can fix these
                return self.assistant.show_result(State.ERROR, message, emotion="confused")
            if code == dr.STOPPED and not retried:
                self.controller.log("AI", "starting Ollama")
                self.controller.set_state(State.PROCESSING, "Waking up my AI brain...")
                self._background(doc.start, lambda _r: QTimer.singleShot(
                    8000, lambda: self._background(doc.status, lambda r: checked(r, retried=True))))
                return
            if code == dr.STOPPED:
                return self.assistant.show_result(State.ERROR, "Ollama's not answering yet. Give it a minute, "
                                                               "then ask me again.")
            if code == dr.NO_MODEL:
                return self.assistant.confirm(f"{message} Download it now? It's about 2 gigabytes. Say yes or no.",
                                              lambda yes: download() if yes else self.assistant.show_result(
                                                  State.IDLE, "Okay. I'll stick to my offline brain."))
            self.assistant.confirm(f"{message} Install it? It's about 2 gigabytes, and a setup window will "
                                   f"open. Say yes or no.",
                                   lambda yes: install() if yes else self.assistant.show_result(
                                       State.IDLE, "Okay. You can also add a Claude key in Settings."))

        def download() -> None:
            last = [-1]

            def progress(p: float) -> None:          # from the download thread: show it on the panel
                pct = int(p * 100)
                if pct != last[0]:
                    last[0] = pct
                    self._bridge.done.emit(lambda v: self.controller.set_state(
                        State.PROCESSING, f"Downloading my brain... {v}%"), pct)

            def done(result) -> None:
                if isinstance(result, Exception):
                    return self.assistant.show_result(State.ERROR, f"The download failed: {str(result)[:60]}")
                refresh()
                self.controller.log("AI", "brain downloaded")
                self.assistant.show_result(State.SUCCESS, "Brain downloaded. I can actually think now. "
                                                          "Ask me anything!", emotion="happy")
            self.controller.log("AI", "downloading " + doc.model())
            self._background(lambda: doc.pull(progress), done)

        def install() -> None:
            if not doc.install():
                return self.assistant.show_result(State.ERROR, "I can't run the setup here. Run setup_ai.bat.")
            self.controller.log("AI", "setup_ai.bat opened")
            self.assistant.show_result(State.SUCCESS, "Setup's running in its own window. When it's done, "
                                                      "ask me: is your AI working?")
        self._background(doc.status, checked)

    def _pc_info(self, intent: Intent) -> None:
        """'What's using all my RAM' / 'why is my CPU so high' / 'how much storage is left'."""
        report = self.services.pc_info
        if report is None:
            return self.assistant.show_result(State.ERROR, "I can't read the PC's stats here.")
        topic = intent.query or "overview"
        self.controller.set_state(State.PROCESSING, {"ram": "Checking your RAM...", "cpu": "Watching your CPU...",
                                                     "disk": "Checking your drives..."}.get(topic, "Checking your PC..."))

        def done(text) -> None:
            if isinstance(text, Exception):
                self.controller.log("Error", f"pc info: {str(text)[:40]}")
                return self.assistant.show_result(State.ERROR, "I couldn't read your PC's stats.")
            self.controller.log("PC", topic)
            self.assistant.show_result(State.SUCCESS, text)
        self._background(lambda: report(topic), done)

    def _screenshot(self, intent: Intent) -> None:
        """'Take a screenshot' (every monitor) / 'screenshot this window'."""
        take = self.services.screenshot
        if take is None:
            return self.assistant.show_result(State.ERROR, "I can't take screenshots here.")

        def done(result) -> None:
            if isinstance(result, Exception):
                self.controller.log("Error", f"screenshot: {str(result)[:40]}")
                return self._result(State.ERROR, "screenshot_failed")
            self.controller.log("Screenshot", getattr(result, "name", str(result))[:40])
            self._result(State.SUCCESS, "screenshot_saved", name=getattr(result, "name", str(result)))
        take(intent.query or "screen", done)

    def _personality(self, intent: Intent) -> None:
        """'Be sarcastic' / 'change your personality to tsundere' / 'what's your personality'."""
        s = self.services.settings
        if not intent.targets:
            p = personality.get(self._persona())
            return self._result(State.SUCCESS, "personality_now", name=p.label.split(" (")[0])
        key = intent.targets[0]
        c = self.companion
        if key == "edgerunner" and self._persona() == "edgerunner" and getattr(c, "drone", False):
            return self._drone(False)                     # "go back to normal" in game mode: out of the drone
        if s is not None:
            s.personality = key
            s.save()
        if c is not None and hasattr(c, "settings_changed"):
            c.settings_changed.emit()
        p = personality.get(key)
        self.controller.log("Mode", p.label.split(" (")[0])
        self.assistant.show_result(State.SUCCESS, p.intro or f"{p.label} mode.", emotion=p.emotion or "playful")

    def _learn_fix(self, intent: Intent) -> None:
        """'When I say to school I mean discord': from now on "to school" is read as "discord"."""
        from .parser import plain, set_corrections
        s = self.services.settings
        heard, meant = (plain(t) for t in intent.targets[:2])
        if s is None or not heard or not meant or heard == meant:
            return self._result(State.ERROR, "unknown")
        s.corrections = [p for p in s.corrections if plain(p[0]) != heard] + [[heard, meant]]
        s.save()
        set_corrections(s.corrections)
        self.controller.log("Fix", f'"{heard}" -> "{meant}"')
        self._result(State.SUCCESS, "fix_learned", query=heard, name=meant)

    def _drone_corner(self, intent: Intent) -> None:
        c = self.companion
        if c is None or not hasattr(c, "set_drone_corner"):
            return self.assistant.show_result(State.ERROR, "Can't do that here.")
        side = intent.targets[0]
        c.set_drone_corner(side)
        self._result(State.SUCCESS, "drone_corner", side=side)

    def _game_launched(self, name: str, folder) -> None:
        if self.services.games is not None:
            self.services.games.started(name, folder)

    def _chat_window(self, intent: Intent) -> None:
        if self.services.open_chat is None:
            return self.assistant.show_result(State.ERROR, "No chat window here.")
        self.services.open_chat()
        self._result(State.SUCCESS, "chat_open")

    # -- small talk ----------------------------------------------------------------------------
    def _chat(self, intent: Intent) -> None:
        s = self.services.settings
        if self._ai_available() and self._text.strip():
            return self._unknown(intent, self._text)       # with AI on, she chats properly
        if self._persona() == "edgerunner":
            text, emotion = self.small_talk.reply(intent.query, self._slang())
            return self.assistant.show_result(State.SPEAKING, text, emotion=emotion,
                                              follow_up=bool(s is None or s.conversation))
        self._say_chat(self._text, topic=intent.query)

    # -- weather ------------------------------------------------------------------------------
    def _weather(self, intent: Intent) -> None:
        settings, weather = self.services.settings, self.services.weather
        place = intent.query or (settings.weather_city if settings else "")
        if weather is None:
            return self.assistant.show_result(State.ERROR, "Weather isn't set up.")
        if not place:
            self.controller.log("Fix", "Settings > Assistant > home city")
            return self._result(State.ERROR, "need_city")
        if settings:
            weather.units = settings.weather_units
        self.controller.set_state(State.PROCESSING, f"Checking the sky over {place.title()}...")
        if intent.kind is Kind.RAIN:
            def work():
                return weather.will_it_rain(place, intent.day)
        else:
            def work():
                return weather.report(place, intent.day)

        def done(result) -> None:
            if isinstance(result, Exception):
                self.assistant.show_result(State.ERROR, str(result) or "Weather glitched.")
            else:
                self.assistant.show_result(State.SUCCESS, result)
        self._background(work, done)

    # -- several things in one sentence, step by step ---------------------------------------------------
    STEP_SEPARATOR = re.compile(r"(?i)(\s*,\s*(?:and then |then |and )?|\s+(?:and then|then|after that|and also|and)\s+)")
    STEP_TIMEOUT = 12.0          # seconds a step may take (longer while she waits for your yes / no)
    WINDOW_WAIT = 6.0            # after opening an app: how long to wait for its window

    def _one_step(self, said: str) -> Intent:
        intent = understand(said, lambda name: self._knows(name))
        return self._act_on_it(intent, said) if intent.kind is Kind.UNKNOWN else intent

    def _split_steps(self, text: str) -> list[tuple[Intent, str]]:
        """'open notepad and type hi tiktok' -> [open notepad, type hi tiktok]. Only where each part
        is a command by itself - "open discord and spotify" stays one step, and everything after
        "type" is what gets typed."""
        pieces = self.STEP_SEPARATOR.split(text.strip())
        if len(pieces) < 3:
            return self._split_run_on(text)
        knows = lambda name: self._knows(name)                                  # noqa: E731
        whole = understand(text, knows)
        if whole.kind in (Kind.SHORTCUT, Kind.CORRECTION, Kind.LEARN_BUTTON, Kind.FORGET, Kind.FORGET_BUTTON,
                          Kind.TYPE, Kind.TIMER) or (whole.kind in (Kind.OPEN, Kind.CLOSE, Kind.MINIMIZE)
                                                     and len(whole.targets) > 1 and all(knows(t) for t in whole.targets)):
            return []                                    # one command already ("open deadlock and discord")
        steps = [pieces[0]]
        for sep, piece in zip(pieces[1::2], pieces[2::2]):
            last = steps[-1]
            if parse(last).kind is Kind.TYPE or not piece.strip():
                steps[-1] = last + sep + piece                   # "type hi and bye": all of it is typed
                continue
            now, before = self._one_step(piece), self._one_step(last)       # "go to notepad" counts too
            if now.kind not in (Kind.UNKNOWN, Kind.CHAT) and before.kind not in (Kind.UNKNOWN, Kind.CHAT):
                steps.append(piece)
            else:
                steps[-1] = last + sep + piece
        if len(steps) < 2:
            return []
        return [(self._one_step(step), step) for step in steps]

    # where a second command can start when speech recognition dropped the "and" ("close discord open spotify")
    SECOND_VERB = re.compile(r"(?i)\b(?:(?:an|n|in|en|und|plus)\s+)?(?=(?:open|close|quit|exit|kill|launch|start|"
                             r"play|pause|mute|unmute|deafen|undeafen|minimi[sz]e|take|search|type|leave|join|stream|"
                             r"stop|set|turn)\b)")

    SELF_CONTAINED = {Kind.OPEN, Kind.CLOSE, Kind.DISCORD, Kind.MEDIA, Kind.MINIMIZE, Kind.RESTORE, Kind.SCREENSHOT,
                      Kind.QUIET, Kind.DRONE_ON, Kind.DRONE_OFF, Kind.LOUNGE_ON, Kind.LOUNGE_OFF}

    def _split_run_on(self, text: str) -> list[tuple[Intent, str]]:
        """'close discord open spotify': two commands with no "and" between them (it's often lost in
        speech). Split before the second command word - only when both halves are commands by themselves
        and the first names something you have, so "open the play store" or "turn on stop motion" stay whole."""
        words = text.strip()
        if parse(words).kind in (Kind.TYPE, Kind.SHORTCUT, Kind.CORRECTION, Kind.TIMER, Kind.LEARN_BUTTON):
            return []
        for m in self.SECOND_VERB.finditer(words):
            if m.start() == 0:
                continue
            first, second = words[:m.start()].strip(" ,"), words[m.end():].strip()
            if not first or not second:
                continue
            a, b = self._one_step(first), self._one_step(second)
            if a.kind not in self.SELF_CONTAINED or b.kind in (Kind.UNKNOWN, Kind.CHAT):
                continue                                   # ("search youtube for open source": all one search)
            if a.targets and not all(self._knows(t) for t in a.targets):
                continue                                   # "open the play store": not two things
            rest = self._split_steps(second) or [(b, second)]
            return [(a, first)] + rest
        return []

    @staticmethod
    def _step_words(intent: Intent) -> tuple[str, str]:
        """(what she's about to do, what's done) - for "wait a second while I ..." and "alright, ..."."""
        names = " and ".join(t[:1].upper() + t[1:] for t in intent.targets) if intent.targets else ""
        k = intent.kind
        if k is Kind.OPEN:
            return f"open {names}", f"{names} {'are' if len(intent.targets) > 1 else 'is'} open"
        if k is Kind.CLOSE:
            return f"close {names}", f"{names} {'are' if len(intent.targets) > 1 else 'is'} closed"
        if k is Kind.TYPE:
            return "type that in", "your message is typed"
        if k is Kind.PLAY:
            return f"put on {intent.query or intent.artist}", f"{intent.query or intent.artist} is on"
        if k is Kind.SEARCH:
            return f"search {intent.query}", "the search is up"
        if k is Kind.MEDIA:
            words = {"pause": "pause the music", "resume": "play the music", "next": "skip the song",
                     "previous": "go back a song", "volume_up": "turn it up", "volume_down": "turn it down"}
            return words.get(intent.query, "sort the music"), "the music's sorted"
        if k is Kind.DISCORD:
            words = {"mute": ("mute you", "you're muted"), "unmute": ("unmute you", "you're unmuted"),
                     "deafen": ("deafen you", "you're deafened"), "undeafen": ("undeafen you", "you can hear again"),
                     "join": ("join your call", "you're in the call"), "leave": ("leave the call", "you're out of the call"),
                     "stream": ("share your screen", "you're live"), "stop_stream": ("stop the stream", "the stream's off")}
            return words.get(intent.query, ("sort Discord", "Discord's sorted"))
        if k is Kind.SCREENSHOT:
            return "take a screenshot", "the screenshot's saved"
        if k is Kind.MINIMIZE:
            return "clear your screen", "your screen's clear"
        if k is Kind.TIMER:
            return "set that timer", "the timer's running"
        return k.value.replace("_", " "), "that's done"

    def _run_steps(self, steps: list[tuple[Intent, str]]) -> None:
        """Say what she's going to do, do each step in turn (waiting for an app's window before typing
        into it), then say how it went."""
        plans = [self._step_words(i)[0] for i, _ in steps]
        plan = "Wait a second while I " + (", ".join(plans[:-1]) + " and " + plans[-1]) + "."
        self.controller.log("Steps", " -> ".join(p for p in plans)[:60])
        self.controller.set_state(State.PROCESSING, plan)
        self.assistant.say(plan, emotion="happy")
        self._steps = {"todo": list(steps), "done": []}
        QTimer.singleShot(400, self._next_step)

    def _front(self):
        front = getattr(self.services, "front", None)
        try:
            return front() if callable(front) else None
        except Exception:
            return None

    def _next_step(self) -> None:
        st = getattr(self, "_steps", None)
        if st is None:
            return
        if not st["todo"]:
            return self._finish_steps()
        intent, said = st["todo"].pop(0)
        if intent.kind is Kind.TYPE and not intent.targets and st["done"] and st["done"][-1].kind is Kind.OPEN \
                and st["done"][-1].targets and not (type_where(intent.query or "") and
                                                    self._knows(type_where(intent.query or "")[1])):
            intent = Intent(Kind.TYPE, st["done"][-1].targets[-1:], query=intent.query)   # into what she opened
        before = self._front()
        self.assistant.collect = []
        started = time.monotonic()
        try:
            self.dispatch(intent, said)
        except Exception as exc:                              # one step failing mustn't leave her stuck
            log.exception("step failed")
            self.assistant.collect.append((State.ERROR, str(exc)[:60]))

        def check() -> None:
            got = self.assistant.collect
            if got is None:
                return
            waiting = getattr(self.assistant, "_pending", None) is not None or \
                getattr(self.assistant, "_asking", None) is not None
            if got:
                state, message = got[-1]
                self.assistant.collect = None
                if state is State.ERROR:
                    return self._finish_steps(error=message)
                st["done"].append(intent)
                if intent.kind is Kind.OPEN:
                    return self._wait_for_window(before, time.monotonic())
                return QTimer.singleShot(350, self._next_step)
            allowed = self.STEP_TIMEOUT * (4 if waiting else 1) + \
                (len(intent.query or "") * 0.02 if intent.kind is Kind.TYPE else 0)   # long text takes a while
            if time.monotonic() - started > allowed:
                self.assistant.collect = None
                return self._finish_steps(error="that took too long")
            QTimer.singleShot(150, check)
        QTimer.singleShot(60, check)

    def _wait_for_window(self, before, since: float) -> None:
        """After opening an app: wait until its window is in front (so typing goes into it)."""
        now = self._front()
        if now is None and before is None:
            return QTimer.singleShot(350, self._next_step)        # can't tell here: carry on
        if (now is not None and now != before) or time.monotonic() - since > self.WINDOW_WAIT:
            return QTimer.singleShot(700, self._next_step)        # a moment for it to be ready for keys
        QTimer.singleShot(150, lambda: self._wait_for_window(before, since))

    def _finish_steps(self, error: str = "") -> None:
        st, self._steps = getattr(self, "_steps", None), None
        self.assistant.collect = None
        done = [self._step_words(i)[1] for i in (st["done"] if st else [])]
        if error:
            error = error.rstrip(".!") + "."
            if done:                                          # "Notepad is open, but I can only type on Windows."
                said = done[0][:1].upper() + done[0][1:] + "".join(f", {d}" for d in done[1:])
                error = f"{said}, but {error[:1].lower() + error[1:] if not error.startswith('I ') else error}"
            return self.assistant.show_result(State.ERROR, error)
        text = "Alright, " + (", ".join(done[:-1]) + " and " + done[-1] if len(done) > 1 else done[0]) + "."
        self.assistant.show_result(State.SUCCESS, text, emotion="happy")

    def _settings(self, intent: Intent) -> None:
        """'Open your settings': her own Settings window."""
        opener = self.services.open_settings
        if opener is None:
            return self.assistant.show_result(State.ERROR, "My settings aren't available here.")
        opener()
        self.assistant.show_result(State.SUCCESS, "Here are my settings.", emotion="happy")

    def _restart_app(self, intent: Intent) -> None:
        """'Restart yourself': close and start again (a downloaded update installs on the way)."""
        if self.services.restart is None:
            return self.assistant.show_result(State.ERROR, "I can't restart myself here.")
        self.assistant.show_result(State.SUCCESS, "Restarting. Back in a sec.", speak=False)
        QTimer.singleShot(800, self.services.restart)

    def _update(self, intent: Intent) -> None:
        """'Check for updates' / 'update yourself': a downloaded update installs (after a yes),
        otherwise she checks GitHub."""
        updates = self.services.updates
        if updates is None:
            return self.assistant.show_result(State.ERROR, "I can't update myself here.")
        said = (self._text or "").lower()
        if "update yourself" in said or "install" in said or "update now" in said:
            if updates.update_now():
                return
        updates.check_now()

    def _hair(self, intent: Intent) -> None:
        """'Change your hair' (swap) / 'use your old hair' / 'new hair': her hair style, saved."""
        c, s = self.companion, self.services.settings
        if c is None or not hasattr(c, "set_look") or s is None:
            return self._result(State.ERROR, "unknown")
        now = getattr(s, "hair_style", "storm")
        style = intent.query or ("classic" if now == "storm" else "storm")
        c.set_look(1.0, s.idle_animation, style)
        from ..ui.hair import HAIR_STYLES
        self.assistant.show_result(State.SUCCESS, "Same hair, choom - it's already on." if style == now else
                                   f"New look: {HAIR_STYLES[style].lower()} hair.", emotion="happy")

    TYPE_WAIT = 9.0              # after opening the app to type in: how long to wait for its window

    def _type(self, intent: Intent, waited: float = 0.0) -> None:
        """'Type hi tiktok' (the window you're on) / 'type hi in notepad' (that app - opened first if it
        isn't running). Never Enter - so whatever she types can't run as a command anywhere."""
        desktop = self.services.desktop
        words = re.sub(r"[\r\n]+", " ", intent.query or "").strip()
        where = intent.targets[0] if intent.targets else ""
        if not where and (split := type_where(words)) and self._knows(split[1]):
            words, where = split                                     # "type hi in notepad"
        if not words:
            return self._result(State.ERROR, "unknown")
        if desktop is None or not (hasattr(desktop, "type_into") or hasattr(desktop, "type_text")):
            return self.assistant.show_result(State.ERROR, "I can only type on Windows.")
        if not hasattr(desktop, "type_into"):                         # (an older desktop: keys into the front)
            return self._type_keys(desktop, words)
        label = where[:1].upper() + where[1:]
        if where:
            hwnd = self._window_of(where)
            if hwnd is None:
                if getattr(self, "_steps", None) is None and waited == 0:
                    opened = Intent(Kind.OPEN, (where,))                # not open: open it, then type
                    return self._run_steps([(opened, ""), (Intent(Kind.TYPE, (where,), query=words), "")])
                if waited < self.TYPE_WAIT:                             # just opened: its window's coming
                    again = Intent(Kind.TYPE, (where,), query=words)
                    return QTimer.singleShot(300, lambda: self._type(again, waited + 0.3))
                return self.assistant.show_result(State.ERROR, f"I couldn't find {label}'s window to type in.")
        else:
            hwnd = self._front()
            if hwnd is None:
                return self.assistant.show_result(State.ERROR, "There's no window in front for me to type in.")
        self.controller.set_state(State.PROCESSING, "Typing...")

        def done(how) -> None:
            if isinstance(how, Exception):
                return self.assistant.show_result(State.ERROR, f"Couldn't type: {str(how)[:40]}")
            self.controller.log("Typed", f"{how}: {words[:30]}")
            if how == "no_focus":
                return self.assistant.show_result(
                    State.ERROR, f"Windows wouldn't let me bring {label or 'that window'} to the front, so I "
                                 f"didn't type anything. Click into it and tell me again.")
            if how == "blocked":
                return self.assistant.show_result(
                    State.ERROR, f"Windows blocked my typing in {label or 'that window'}. It's probably running "
                                 f"as administrator.")
            self.assistant.show_result(State.SUCCESS, f"Typed it in {label}." if where else "Typed it.",
                                       emotion="happy")
        self._background(lambda: desktop.type_into(hwnd, words), done)

    def _type_keys(self, desktop, words: str) -> None:
        try:
            desktop.type_text(words)
        except OSError as exc:
            return self.assistant.show_result(State.ERROR, f"Couldn't type: {str(exc)[:40]}")
        self.controller.log("Typed", words[:40])
        self.assistant.show_result(State.SUCCESS, "Typed it.", emotion="happy")

    def _window_of(self, name: str) -> int | None:
        """The main window of a running app you named ("notepad" -> Notepad's window), or None."""
        desktop = self.services.desktop
        try:
            _, pids, _ = self.catalog.running_for(name, self._processes())
            if not pids or not hasattr(desktop, "windows_for"):
                return None
            found = desktop.windows_for(pids)
        except Exception as exc:
            log.warning(f"window lookup failed: {exc}")
            return None
        return found[0] if found else None

    # -- buttons you taught her by pointing -------------------------------------------------------------
    def _taught(self) -> list[dict]:
        s = self.services.settings
        return [b for b in (getattr(s, "learned_buttons", None) or []) if isinstance(b, dict) and b.get("phrase")]

    def _button_for(self, text: str) -> dict | None:
        from .fuzzy import similarity
        said = normalise(text)
        for taught in self._taught():
            key = normalise(taught["phrase"])
            if said and (said == key or (len(key) >= 6 and similarity(said, key) >= 0.9)):
                return taught
        return None

    def _learn_button(self, intent: Intent) -> None:
        """'This red button makes me leave call' - with the mouse on it. She reads what's under the
        pointer (its name, which app, where in the window) and saves it as a new skill: saying
        "leave call" then presses that button. Saved as data (settings), never as code."""
        phrase = normalise(intent.targets[0] if intent.targets else "")
        finder, desktop, s = self.services.screen, self.services.desktop, self.services.settings
        if not phrase or s is None:
            return self._result(State.ERROR, "unknown")
        if finder is None or desktop is None or not hasattr(desktop, "window_at"):
            return self.assistant.show_result(State.ERROR, "I can only learn buttons on Windows.")
        self.controller.set_state(State.PROCESSING, "Looking at what you're pointing at...")

        def look() -> dict | None:
            target = finder.under_mouse()
            x, y = finder.cursor()
            hwnd = desktop.window_at(x, y)
            if target is None or not hwnd:
                return None
            pid = desktop.pid_of(hwnd)
            app = next((p.name for p in self._processes() if p.pid == pid), "")
            rect = desktop.hwnd_rect(hwnd)
            if not app or not rect or rect[2] <= rect[0] or rect[3] <= rect[1]:
                return None
            cx, cy = target.center
            name = target.name if target.element is not None and target.name not in ("that", "") else ""
            return {"phrase": phrase, "app": app, "name": name, "x": round((cx - rect[0]) / (rect[2] - rect[0]), 4),
                    "y": round((cy - rect[1]) / (rect[3] - rect[1]), 4)}

        def learned(skill) -> None:
            if isinstance(skill, Exception) or skill is None:
                return self.assistant.show_result(State.ERROR, "I couldn't see what you're pointing at. Put your "
                                                               "mouse on the button and say it again.")
            s.learned_buttons = [b for b in self._taught() if normalise(b["phrase"]) != phrase] + [skill]
            s.save()
            what = f"\u201c{skill['name']}\u201d" if skill["name"] else "that spot"
            app = skill["app"].rsplit(".", 1)[0].title()
            self.controller.log("Learned", f'"{phrase}" -> {app}: {skill["name"] or "spot"}'[:40])
            self.assistant.show_result(State.SUCCESS, f"Learned it. When you say \u201c{phrase}\u201d, I'll press "
                                                      f"{what} in {app}.", emotion="happy")
        self._background(look, learned)

    def _forget_button(self, intent: Intent) -> None:
        s = self.services.settings
        key = normalise(intent.targets[0] if intent.targets else "")
        kept = [b for b in self._taught() if normalise(b["phrase"]) != key]
        if s is None or len(kept) == len(self._taught()):
            return self.assistant.show_result(State.ERROR, f"I haven't learned a \u201c{key}\u201d button.")
        s.learned_buttons = kept
        s.save()
        self.assistant.show_result(State.SUCCESS, f"Forgotten. \u201c{key}\u201d is back to normal.")

    def _press_taught(self, skill: dict) -> None:
        """Find the taught button in its app (by name, near where it was; else that spot) and zap it."""
        from ..integrations.screen_targets import RISKY, Target
        desktop, ui = self.services.desktop, getattr(self.services.screen, "ui", None)
        app = str(skill.get("app", ""))
        label = app.rsplit(".", 1)[0].title()
        if desktop is None or self.services.click_at is None:
            return self.assistant.show_result(State.ERROR, "I can only press buttons on Windows.")
        pids = [p.pid for p in self._processes() if p.name.lower() == app.lower()]
        if not pids:
            return self.assistant.show_result(State.ERROR, f"{label} isn't running.")
        self.controller.set_state(State.PROCESSING, f"Pressing it in {label}...")

        def find():
            best = None
            for hwnd in desktop.windows_for(pids):
                rect = desktop.hwnd_rect(hwnd)
                if not rect or rect[2] - rect[0] < 50:
                    continue
                want = (rect[0] + float(skill.get("x", 0.5)) * (rect[2] - rect[0]),
                        rect[1] + float(skill.get("y", 0.5)) * (rect[3] - rect[1]))
                if skill.get("name") and ui is not None:
                    try:
                        named = [c for c in ui.clickables(hwnd) if c.name.strip().lower() == skill["name"].lower()]
                    except Exception:
                        named = []
                    for c in named:
                        cx, cy = (c.rect[0] + c.rect[2]) / 2, (c.rect[1] + c.rect[3]) / 2
                        d = abs(cx - want[0]) + abs(cy - want[1])
                        if best is None or d < best[0]:
                            best = (d, Target(c.name, c.rect, "ui", c))
                if best is None:                         # no name (or not found): the spot you showed her
                    x, y = int(want[0]), int(want[1])
                    best = (1e9, Target(skill.get("name") or "that", (x - 10, y - 10, x + 10, y + 10), "mouse", None))
            return best[1] if best else None

        def found(target) -> None:
            if isinstance(target, Exception) or target is None:
                return self.assistant.show_result(State.ERROR, f"I couldn't find that button in {label}.")
            if RISKY.search(target.name or ""):
                return self.assistant.confirm(f"Press \u201c{target.name}\u201d? Say yes or no.",
                                              lambda yes: go(target) if yes else self._result(State.IDLE, "click_cancelled"))
            go(target)

        def go(target) -> None:
            def done(outcome) -> None:
                if isinstance(outcome, Exception):
                    return self._result(State.ERROR, "click_failed", name=target.name[:40])
                self.controller.log("Pressed", f"{skill['phrase']}: {target.name}"[:40])
                self.assistant.show_result(State.SUCCESS, "Done.", speak=False, emotion="happy")
            self._press_on_screen(target.name, target.rect, target.element, done)
        self._background(find, found)

    # -- quiet, her voice, timers, window sitting -----------------------------------------------------
    def _quiet(self, intent: Intent) -> None:
        """'Stop talking' / 'shut up': she stops mid-word and says nothing more."""
        speaker = getattr(self.assistant, "speaker", None)
        if speaker is not None and hasattr(speaker, "stop"):
            speaker.stop()
        self._result(State.IDLE, "quiet", speak=False)

    VOICE_STEPS = {"faster": ("speech_speed", 0.12), "slower": ("speech_speed", -0.12),
                   "louder": ("speech_volume", 0.15), "softer": ("speech_volume", -0.15),
                   "higher": ("speech_pitch", 0.08), "lower": ("speech_pitch", -0.08),
                   "more_expressive": ("speech_expression", 0.2), "less_expressive": ("speech_expression", -0.2)}

    def _voice(self, intent: Intent) -> None:
        """'Talk faster' / 'speak up' / 'change your voice': changed (and saved), said in the new voice."""
        from ..speech.effects import STYLES
        s = self.services.settings
        if s is None:
            return self._result(State.ERROR, "unknown")
        ask = intent.query
        fields = {}
        if ask == "next_style":
            keys = list(STYLES)
            s.speech_style = keys[(keys.index(s.speech_style) + 1) % len(keys)] if s.speech_style in keys else keys[0]
            fields["style"] = STYLES[s.speech_style].split(" (")[0]
        else:
            name, step = self.VOICE_STEPS[ask]
            before = getattr(s, name)
            setattr(s, name, round(min(1.0, max(0.0, before + step)), 2))
            if getattr(s, name) == before:
                return self._result(State.SUCCESS, "voice_limit")
        s.save()
        self.assistant.settings_changed.emit()
        self._result(State.SUCCESS, "voice_" + ask, **fields)

    def _timer(self, intent: Intent) -> None:
        """Timers, reminders and alarms. They live while she's running (not after a restart)."""
        timers = self.__dict__.setdefault("_timers", [])
        if intent.query == "cancel":
            if not timers:
                return self._result(State.ERROR, "timer_none")
            what = "alarm" if all(t["kind"] == "alarm" for t in timers) else \
                "reminder" if all(t["kind"] == "reminder" for t in timers) else "timer"
            what += "s" if len(timers) > 1 else ""
            for t in timers:
                t["timer"].stop()
            timers.clear()
            return self._result(State.SUCCESS, "timer_cancelled", what=what, What=what.capitalize())
        if intent.query == "left":
            if not timers:
                return self._result(State.ERROR, "timer_none")
            soonest = min(timers, key=lambda t: t["due"])
            return self._result(State.SUCCESS, "timer_left",
                                time=spoken_duration(int(soonest["due"] - time.monotonic())).capitalize())
        if intent.query == "alarm":
            hour, minute = (int(x) for x in intent.targets[0].split(":"))
            now = datetime.now()
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)
            wait, kind, label = int((due - now).total_seconds()), "alarm", spoken_clock(hour, minute)
        else:
            wait = int(intent.targets[0])
            label = intent.targets[1] if len(intent.targets) > 1 else ""
            kind = "reminder" if label else "timer"
        wait = max(1, min(wait, 24 * 3600 * 2))
        timer = QTimer(self)
        timer.setSingleShot(True)
        entry = {"timer": timer, "kind": kind, "label": label, "due": time.monotonic() + wait, "length": wait}

        def ring() -> None:
            if entry in timers:
                timers.remove(entry)
            self.controller.log("Timer", f"{kind}: {label or spoken_duration(entry['length'])}"[:40])
            if kind == "alarm":
                self._result(State.SUCCESS, "alarm_done", time=label)
            elif kind == "reminder":
                self._result(State.SUCCESS, "reminder_done", label=label)
            else:
                self._result(State.SUCCESS, "timer_done", time=spoken_duration(entry["length"]))
        timer.timeout.connect(ring)
        timer.start(wait * 1000)
        timers.append(entry)
        self.controller.log("Timer", f"{kind} in {spoken_duration(wait)}"[:40])
        if kind == "alarm":
            return self._result(State.SUCCESS, "alarm_set", time=label)
        if kind == "reminder":
            return self._result(State.SUCCESS, "reminder_set", label=label, time=spoken_duration(wait))
        self._result(State.SUCCESS, "timer_set", time=spoken_duration(wait))

    def _hype(self, on: bool) -> None:
        """'Turn on game hype': she cheers for your kills (CS2, Dota 2, League)."""
        s = self.services.settings
        if s is None:
            return self._result(State.ERROR, "unknown")
        s.game_hype = on
        s.save()
        self.assistant.settings_changed.emit()          # the app starts / stops listening to your games
        self._result(State.SUCCESS, "hype_on" if on else "hype_off")

    def _perch(self, on: bool) -> None:
        c = self.companion
        if c is not None and hasattr(c, "set_perch_windows"):
            c.set_perch_windows(on)
        elif self.services.settings is not None:
            self.services.settings.perch_windows = on
        self._result(State.SUCCESS, "perch_on" if on else "perch_off")

    # -- everything else: optional AI -------------------------------------------------------------
    def _ai_available(self) -> bool:
        s = self.services.settings
        return bool(s and s.ai_enabled and self.services.brain is not None)

    AI_PROBLEM_REPEAT = 600.0      # seconds before she mentions the same AI problem again

    def _note_ai(self, ok: bool, text: str) -> None:
        """The last thing the AI did, for Settings -> AI ("Last answer: ...")."""
        self.ai_status = (time.strftime("%H:%M"), ok, text)

    def _tell_ai_problem(self, problem: str) -> bool:
        """Say why the AI isn't answering (out of credit, key wrong...), once every so often - instead of
        quietly falling back to her own chat, which made a new key look like it did nothing."""
        said = getattr(self, "_ai_problems", {})
        self._ai_problems = said
        if time.monotonic() - said.get(problem, -1e9) < self.AI_PROBLEM_REPEAT:
            return False
        said[problem] = time.monotonic()
        self.controller.log("AI", problem[:60])
        self.assistant.show_result(State.ERROR, problem + " Till then I'm using my own chat.")
        return True

    def test_ai(self, report) -> None:
        """Settings -> 'Test it': ask the AI for real and report exactly what happened."""
        brain = self.services.brain
        if brain is None:
            return report("No AI here.")
        self.controller.set_state(State.PROCESSING, "Asking my AI...")

        def ask():
            return brain.ask("Say hi to me in under ten words, in your own style."), \
                (brain.which() if hasattr(brain, "which") else "")

        def done(got) -> None:
            if isinstance(got, Exception):
                return report(f"Failed: {str(got)[:80]}")
            reply, which = got
            if getattr(reply, "missing", False) and not reply.text:
                return report("No AI is set up yet: pick one and add its key.")
            if getattr(reply, "error", False):
                self.assistant.show_result(State.ERROR, reply.text)
                detail = getattr(reply, "detail", "")
                self._note_ai(False, reply.text + (f" ({detail})" if detail else ""))
                return report(reply.text + (f"\nDetails: {detail}" if detail else ""))
            self._note_ai(True, (reply.text or "")[:80])
            report(f"Working ({which or 'AI'}): \u201c{reply.text[:80]}\u201d")
            self.assistant.show_result(State.SPEAKING, reply.text, emotion=reply.emotion)
        self._background(ask, done)

    def _about_you(self, text: str) -> None:
        """Anything about you stays on your PC: her own chatbot answers it, never the AI."""
        from ..about_you import FORGET_ALL, _norm
        memory = self.chatbot.memory
        if re.fullmatch(FORGET_ALL, _norm(text)):
            if memory.empty():
                return self._say_chat("what do you know about me")

            def answer(yes: bool) -> None:
                if yes:
                    memory.forget_all()
                    self.controller.log("Memory", "forgot everything about you")
                    self.assistant.show_result(State.SUCCESS, "Done. Everything I knew about you is deleted.")
                else:
                    self.assistant.show_result(State.SUCCESS, "Okay, I'll keep it.")
            return self.assistant.confirm("Forget everything I know about you? Say yes or no.", answer)
        self.controller.log("Memory", "kept on this PC")
        self._say_chat(text)

    def _unknown(self, intent: Intent, text: str = "") -> None:
        brain = self.services.brain
        from ..about_you import is_personal
        if text.strip() and getattr(self.chatbot, "memory", None) is not None and is_personal(text):
            return self._about_you(text)
        if not (self._ai_available() and text.strip()):
            if not text.strip():
                return self._result(State.ERROR, "unknown")
            if not self._told_ai:
                self.controller.log("Tip", "turn on AI chat in Settings")
                self._told_ai = True
            if intent.kind is Kind.UNKNOWN:
                self._missed = (text, time.monotonic())    # if you rephrase it and it works, she learns
            return self._say_chat(text)                    # her own chatbot: she always answers
        self.controller.set_state(State.PROCESSING, "Thinking...")

        def done(reply) -> None:
            topic = intent.query if intent.kind is Kind.CHAT else ""
            if isinstance(reply, Exception):
                self.controller.log("AI", f"failed: {str(reply)[:40]}")
                return self._say_chat(text, topic=topic)
            problem = (reply.text or "").strip() if getattr(reply, "error", False) and not reply.intent else ""
            if problem:
                self._note_ai(False, problem + (f" ({reply.detail})" if getattr(reply, "detail", "") else ""))
            if problem and self._tell_ai_problem(problem):     # no credit, bad key...: say so, don't hide it
                return
            if problem or getattr(reply, "missing", False):   # (already told you): her own chatbot meanwhile
                self.controller.log("AI", (problem or "none set up")[:50] + " - my own chat instead")
                if not problem and not self._told_ai:
                    self._told_ai = True
                    self.controller.log("Tip", "setup_ai.bat: free local AI chat")
                return self._say_chat(text, topic=topic)
            self.controller.log("AI", "answered")
            self._note_ai(True, (reply.text or "")[:80])
            several = getattr(reply, "intents", None) or []
            if len(several) > 1:                          # "open Notepad, then type hi": step by step
                self.controller.log("AI", " -> ".join(i.kind.value for i in several))
                return self._run_steps([(i, "") for i in several])
            if reply.intent is not None:
                self.controller.log("AI", reply.intent.kind.value + " " +
                                    (", ".join(reply.intent.targets) or reply.intent.query))
                return self.dispatch(reply.intent)        # same rules as a spoken command
            s = self.services.settings
            self.assistant.show_result(State.ERROR if reply.error else State.SPEAKING, reply.text,
                                       emotion=reply.emotion,
                                       follow_up=not reply.error and bool(s is None or s.conversation))
        self._background(lambda: brain.ask(text), done)
