"""Automations (2.4): "when X happens, do these things" - built in Settings -> Automations, kept in her settings.

Triggers                              Actions (run one after another)
  app_open / app_close  <app name>      command  - anything you could say to her ("open discord", "quiet mode",
  game_open / game_close <game name>               "set volume to 30", "draw a heart"...)
  time      "HH:MM" (+ days)            say      - she says something
  startup   (when Capri starts)         wait     - seconds (up to 10 minutes)
  away      <minutes> without input
  back      (you come back after being away)
  phrase    <words> - a custom voice command ("gaming time")

Actions go through her normal command system, so they can only do what you could ask her to do yourself - with the
same questions first for anything risky (shutting down asks you). Nothing else is ever run. An automation can't
start itself again in a loop, and the same one runs at most once every 20 seconds.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QObject, QTimer

log = logging.getLogger("capri")

TRIGGERS = {"app_open": "When I open an app", "app_close": "When I close an app",
            "game_open": "When I start a game", "game_close": "When I quit a game",
            "time": "At a time of day", "startup": "When Capri starts", "away": "When I've been away",
            "back": "When I come back", "phrase": "When I say..."}
ACTIONS = {"command": "Do a command", "say": "Say something", "wait": "Wait (seconds)"}
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MAX_ACTIONS = 20
MIN_GAP = 20.0                # seconds: the same automation at most this often
MAX_WAIT = 600


@dataclass
class Automation:
    name: str
    trigger: str
    value: str = ""
    actions: list = field(default_factory=list)      # [{"type": "command"|"say"|"wait", "value": str}]
    enabled: bool = True
    days: list = field(default_factory=list)         # time triggers: 0=Mon..6=Sun ([] = every day)

    def to_dict(self) -> dict:
        return {"name": self.name, "trigger": self.trigger, "value": self.value, "actions": self.actions,
                "enabled": self.enabled, "days": self.days}

    @staticmethod
    def from_dict(d: dict) -> "Automation | None":
        """A stored automation, checked (None if it isn't a proper one)."""
        if not isinstance(d, dict) or d.get("trigger") not in TRIGGERS:
            return None
        actions = []
        for a in d.get("actions", [])[:MAX_ACTIONS] if isinstance(d.get("actions"), list) else []:
            if isinstance(a, dict) and a.get("type") in ACTIONS and str(a.get("value", "")).strip():
                actions.append({"type": a["type"], "value": str(a["value"])[:300]})
        days = [int(x) for x in d.get("days", []) if isinstance(x, int) and 0 <= x <= 6] \
            if isinstance(d.get("days"), list) else []
        return Automation(str(d.get("name") or "Automation")[:60], d["trigger"], str(d.get("value", ""))[:120],
                          actions, bool(d.get("enabled", True)), days)

    def problem(self) -> str:
        """Why it can't run as it is ("" = fine)."""
        if not self.actions:
            return "add at least one action"
        if self.trigger in ("app_open", "app_close", "phrase") and not self.value.strip():
            return "say which " + ("words" if self.trigger == "phrase" else "app")   # (a game: empty = any game)
        if self.trigger == "time" and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", self.value.strip()):
            return "the time must look like 18:30"
        if self.trigger == "away":
            try:
                if not 1 <= int(self.value) <= 600:
                    raise ValueError
            except ValueError:
                return "away needs minutes (1-600)"
        for a in self.actions:
            if a["type"] == "wait":
                try:
                    if not 0 < float(a["value"]) <= MAX_WAIT:
                        raise ValueError
                except ValueError:
                    return f"a wait must be 1-{MAX_WAIT} seconds"
        return ""


def load(settings) -> list[Automation]:
    return [a for a in (Automation.from_dict(d) for d in getattr(settings, "automations", []) or []) if a is not None]


def save(settings, automations: list[Automation]) -> None:
    settings.automations = [a.to_dict() for a in automations]
    settings.save()


def words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split())


class AutomationEngine(QObject):
    CHECK_MS = 15_000

    def __init__(self, settings, run_command: Callable[[str], None], say: Callable[[str], None],
                 idle_seconds: Callable[[], float] | None = None, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = datetime.now, log_action: Callable[[str, str], None] | None = None) -> None:
        super().__init__()
        self.settings, self.run_command, self.say = settings, run_command, say
        self.idle_seconds, self.clock, self.now = idle_seconds, clock, now
        self.log_action = log_action or (lambda what, detail: None)
        self._last_run: dict[str, float] = {}
        self._fired_today: dict[str, str] = {}             # time automations: name -> the date it last ran
        self._away_fired: set[str] = set()
        self._was_away = False
        self._depth = 0                                    # running an automation right now (no loops)
        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_MS)
        self._timer.timeout.connect(self.tick)
        self._timer.start()
        QTimer.singleShot(15_000, lambda: self.fire("startup"))

    # -- triggers ---------------------------------------------------------------------------------------------------
    def automations(self) -> list[Automation]:
        return [a for a in load(self.settings) if a.enabled and not a.problem()]

    def fire(self, trigger: str, value: str = "") -> int:
        """Something happened: run the automations it triggers. Returns how many started."""
        started = 0
        for a in self.automations():
            if a.trigger != trigger:
                continue
            if trigger in ("app_open", "app_close", "game_open", "game_close") and a.value.strip():
                if words(a.value) not in words(value) and words(value) not in words(a.value):
                    continue                                   # (a game automation with no name: any game)
            if self.run(a):
                started += 1
        return started

    def app_event(self, kind: str, app: str) -> None:
        """From her app watcher: app_open / app_close / game_open / game_close."""
        self.fire(kind, app)

    def phrase(self, said: str) -> bool:
        """A custom voice command: True if one of your phrase automations took it."""
        if self._depth:
            return False
        heard = words(said)
        for a in self.automations():
            if a.trigger == "phrase" and words(a.value) == heard:
                return self.run(a)
        return False

    def tick(self) -> None:
        now = self.now()
        today, hm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
        for a in self.automations():
            if a.trigger == "time":
                h, m = (int(x) for x in a.value.split(":"))
                due = f"{h:02d}:{m:02d}"
                if hm == due and self._fired_today.get(a.name) != today and (not a.days or now.weekday() in a.days):
                    self._fired_today[a.name] = today
                    self.run(a)
        if self.idle_seconds is None:
            return
        try:
            away = self.idle_seconds()
        except Exception:
            return
        for a in self.automations():
            if a.trigger == "away" and away >= int(a.value) * 60 and a.name not in self._away_fired:
                self._away_fired.add(a.name)
                self.run(a)
        if away >= 300:
            self._was_away = True
        elif away < 10:
            if self._was_away:
                self._was_away = False
                self._away_fired.clear()
                self.fire("back")
            self._away_fired.clear()

    # -- running ----------------------------------------------------------------------------------------------------
    def run(self, a: Automation, force: bool = False) -> bool:
        """Start an automation's actions (one after another; waits really wait). False if it ran moments ago."""
        if not force and self.clock() - self._last_run.get(a.name, -1e9) < MIN_GAP:
            return False
        self._last_run[a.name] = self.clock()
        log.info("automation: %s (%s)", a.name, a.trigger)
        self.log_action("Automation", a.name)
        self._step(a, list(a.actions))
        return True

    def _step(self, a: Automation, todo: list) -> None:
        while todo:
            action = todo.pop(0)
            kind, value = action["type"], action["value"]
            if kind == "wait":
                QTimer.singleShot(int(min(MAX_WAIT, float(value)) * 1000), lambda: self._step(a, todo))
                return
            self._depth += 1
            try:
                if kind == "say":
                    self.say(value)
                elif kind == "command":
                    self.run_command(value)
            except Exception:
                log.exception("automation %s: an action failed", a.name)
            finally:
                self._depth -= 1


TEMPLATES = [
    Automation("Game on: quiet mode", "game_open", "", [{"type": "command", "value": "quiet mode"},
                                                       {"type": "say", "value": "Good luck out there."}]),
    Automation("Game over: chatty again", "game_close", "", [{"type": "command", "value": "quiet mode off"}]),
    Automation("Morning routine", "time", "09:00", [{"type": "say", "value": "Morning! Let's do this."},
                                                   {"type": "command", "value": "what's the weather"}], days=[0, 1, 2, 3, 4]),
    Automation("Gaming time", "phrase", "gaming time", [{"type": "command", "value": "open discord"},
                                                       {"type": "wait", "value": "3"},
                                                       {"type": "command", "value": "open steam"}]),
    Automation("Welcome back", "back", "", [{"type": "say", "value": "Welcome back, choom."}]),
    Automation("Spotify vibes", "app_open", "Spotify", [{"type": "command", "value": "do a dance"}]),
]
