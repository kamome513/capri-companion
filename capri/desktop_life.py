"""2.4: her life on your desktop - she reacts when your apps open and close, and Chaos Mode.

* AppReactions - every few seconds: which of your apps and games started or quit (the ones in her apps list).
  She says something about it now and then (never more than one line every couple of minutes, never in quiet
  mode or mid-game). Settings -> Extras -> "React when I open or close apps".
* ChaosMode - every few seconds, while she's idle and you're not in a game: something wild and harmless, often two
  at once - she flings herself across the screen, a swarm of clones, lightning, her cursor zipping around, a dash,
  a dance, a hologram flicker. It never touches your windows, files or keys, and never draws on your screen. Off
  until you turn it on ("chaos mode on", or Settings -> Extras).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer

log = logging.getLogger("capri")

OPEN_LINES = ["{app}? Nice.", "Ooh, {app}. What are we doing?", "{app}'s up. I'll be here.",
              "Firing up {app}, huh?", "{app}. Good choice, choom."]
CLOSE_LINES = ["Bye, {app}.", "{app}'s gone. Done with it?", "And {app} is closed.", "{app}, delta'd."]
GAME_OPEN = ["{app}! Let's go - I'm cheering.", "Game time: {app}. Try not to rage.", "{app}? I call next turn."]


class AppReactions(QObject):
    CHECK_MS = 4000
    SAY_GAP = 120.0           # at most one line this often
    SAME_APP_GAP = 600.0      # and about the same app at most this often

    def __init__(self, running: Callable[[], set[str]], names: Callable[[], dict[str, tuple[str, bool]]],
                 say: Callable[[str], None], allowed: Callable[[], bool], clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None, event: Callable[[str, str], None] | None = None) -> None:
        """running(): the process names running now (lower case). names(): {process name: (app name, is a game)}.
        event(kind, app): every open / close (for automations), even when she says nothing."""
        super().__init__()
        self.running, self.names, self.say, self.allowed = running, names, say, allowed
        self.clock, self.rng = clock, rng or random.Random()
        self.on_event = event                 # (not "event": that's QObject's own method)
        self.seen: set[str] | None = None
        self._last_said = -1e9
        self._last_app: dict[str, float] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()

    def check(self) -> None:
        try:
            now_running = {p.lower() for p in self.running()}
        except Exception:
            return
        known = self.names()
        mine = {p for p in now_running if p in known}
        if self.seen is None:                      # the first look: just remember what's open
            self.seen = mine
            return
        opened, closed = mine - self.seen, self.seen - mine
        self.seen = mine
        for proc, kind in [(p, "open") for p in sorted(opened)] + [(p, "close") for p in sorted(closed)]:
            app, game = known[proc]
            if self.on_event is not None:
                try:
                    self.on_event(("game_" if game else "app_") + kind, app)
                except Exception:
                    log.exception("app reactions: an automation failed")
            self._react(app, game, kind)

    def _react(self, app: str, game: bool, kind: str) -> None:
        now = self.clock()
        if not self.allowed() or now - self._last_said < self.SAY_GAP \
                or now - self._last_app.get(app, -1e9) < self.SAME_APP_GAP:
            return
        pool = (GAME_OPEN if game else OPEN_LINES) if kind == "open" else CLOSE_LINES
        self._last_said = self._last_app[app] = now
        self.say(self.rng.choice(pool).format(app=app))


class ChaosMode(QObject):
    GAP = (6.0, 16.0)          # (2.4.1) actual chaos: something every few seconds...
    COMBO = 0.4                # ...and often two things at once

    def __init__(self, actions: dict[str, Callable[[], None]], allowed: Callable[[], bool],
                 rng: random.Random | None = None) -> None:
        super().__init__()
        self.actions, self.allowed = actions, allowed
        self.rng = rng or random.Random()
        self.on = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._go)

    def set_on(self, on: bool) -> None:
        self.on = on
        if on:
            self._timer.start(int(self.rng.uniform(1.5, 3.0) * 1000))      # the first one right away
        else:
            self._timer.stop()

    def _go(self) -> None:
        if not self.on:
            return
        if self.allowed():
            names = sorted(self.actions)
            picks = self.rng.sample(names, 2 if len(names) > 1 and self.rng.random() < self.COMBO else 1)
            for name in picks:
                log.info("chaos: %s", name)
                try:
                    self.actions[name]()
                except Exception:
                    log.exception("chaos: %s failed", name)
        self._timer.start(int(self.rng.uniform(*self.GAP) * 1000))
