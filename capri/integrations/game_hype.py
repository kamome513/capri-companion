"""Game hype: she cheers when you get a kill ("Nice kill!", "Headshot!", "ACE!").

Only games that report what's happening, through their official, local interfaces:
* Counter-Strike 2 and Dota 2 - Valve's Game State Integration: the game itself sends your stats
  to Capri on this PC (127.0.0.1), with a secret token. Capri puts the small config file
  ("gamestate_integration_capri.cfg") in the game's cfg folder; restart the game once after.
* League of Legends - Riot's Live Client Data on this PC (https://127.0.0.1:2999), read once a
  second only while a match is running.
Other games (Valorant, Fortnite, Apex...) don't share kills, so she can't see them there.

Nothing is sent anywhere. Settings -> PC & chat -> Game hype (off by default for deaths).
"""

from __future__ import annotations

import json
import logging
import random
import secrets
import ssl
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger("capri")

PORT = 3271
BIG_MOMENTS = {"triple", "quad", "ace", "match_win"}      # saved as clips with "Save big moments"
RANK = ["encourage", "kill", "first_blood", "headshot", "double", "triple", "quad", "ace", "round_win", "match_win"]
BURST_MS = 900            # kills this close together become one line ("Triple!")
MIN_GAP = 2.0             # seconds between her lines
LEAGUE = "https://127.0.0.1:2999/liveclientdata"
LEAGUE_EXE = "league of legends.exe"

LINES = {   # event: plain lines; PERSONA overrides below
    "kill": ["Nice kill!", "Got 'em!", "Clean!", "Nice one!", "Down they go!"],
    "headshot": ["Headshot!", "Right in the head! Nice!", "Boom, headshot!"],
    "first_blood": ["First blood! Let's go!"],
    "double": ["Double kill!", "Two down!"],
    "triple": ["Triple kill! You're on fire!", "Three! Let's go!"],
    "quad": ["Four kills! Insane!", "Quad kill! Somebody stop you!"],
    "ace": ["ACE! That was insane!", "You aced it! Legend!"],
    "round_win": ["Round's ours!", "Nice round!"],
    "match_win": ["GG! You won!", "Victory! GG!"],
    "match_loss": ["GG. Next one's ours.", "Unlucky. Run it back."],
    "death": ["Unlucky.", "Ouch. You'll get them next time.", "Shake it off."],
}
PERSONA = {
    "sarcastic": {"kill": ["Wow, you hit something.", "A kill. I'm shocked."], "death": ["Called it."],
                  "ace": ["Okay, fine. That was actually impressive."]},
    "tsundere": {"kill": ["N-not bad. For you.", "Hmph. Lucky shot."], "ace": ["W-whatever! ...That was amazing."],
                 "death": ["Idiot! Be careful!"]},
    "sweet": {"kill": ["Great job!", "You're doing amazing!"], "death": ["Aw, it's okay! You've got this!"]},
    "deadpan": {"kill": ["Kill confirmed.", "Target down."], "ace": ["Ace. Impressive."], "death": ["You died."]},
    "silly": {"kill": ["Bonk! Gottem!", "Yeet! Nice kill!"], "ace": ["ACE ACE ACE! Wheee!"]},
    "gremlin": {"kill": ["Heh heh. Crunch.", "Snack acquired."], "ace": ["Total carnage! Heh heh!"]},
    "hype": {"kill": ["LET'S GO! NICE KILL!", "WHAT A SHOT!"], "ace": ["ACE! ARE YOU KIDDING ME?!"]},
    "kuudere": {"kill": ["...Nice.", "...Good shot."], "death": ["...Unlucky."]},
}


# Lines are put together from parts, so she almost never says the same thing twice in a match.
OPENERS = ["", "", "Ooh, ", "Yes! ", "Okay, ", "Whoa, ", "Ha! ", "Let's go, ", "Damn, "]
CORES = {
    "kill": ["nice kill", "clean kill", "got 'em", "beautiful", "that's how it's done", "sent them back to the lobby",
             "deleted", "outplayed", "too easy", "one down", "smooth", "they never saw it coming"],
    "headshot": ["headshot", "right between the eyes", "what aim", "one tap", "clean headshot", "crispy aim"],
    "double": ["double kill", "two for one", "that's two", "back to back"],
    "triple": ["triple kill", "three down", "you're on fire", "somebody stop you"],
    "quad": ["four kills", "quad kill", "unreal", "you're cooking"],
    "ace": ["that's an ace", "you wiped them all", "absolute legend", "clip that", "insane"],
    "first_blood": ["first blood", "you drew first blood", "first one's yours"],
    "round_win": ["round's ours", "nice round", "that round was clean", "another one"],
    "match_win": ["GG, you won", "victory", "you carried", "that's a W", "winner winner"],
    "match_loss": ["GG, next one's ours", "unlucky, run it back", "shake it off, you played well", "we go again"],
    "death": ["unlucky", "you'll get them next time", "shake it off", "they got lucky", "rough one"],
    "encourage": ["you're doing great", "looking sharp out there", "you've got this", "nice and focused",
                  "you're playing really well", "keep that energy", "remember to breathe", "stay hydrated, champ",
                  "proud of you, keep going", "you're locked in today"],
}
CLOSERS = {"kill": ["!", "!", ", choom!", ". Again!", ". Keep it up!"],
           "encourage": [".", "!", ", choom.", ". Keep going!"],
           "death": [".", ". Next one.", ", choom."]}
_recent: list[str] = []


def line(event: str, persona: str, rng: random.Random | None = None) -> str:
    """A fresh line for what happened, in her personality (theirs now and then, else built from parts)."""
    rng = rng or random
    own = PERSONA.get(persona, {}).get(event)
    if own and rng.random() < 0.35:
        return rng.choice(own)
    cores = CORES.get(event) or CORES["kill"]
    closers = CLOSERS.get(event) or (["!", "!", "!!"] if event not in ("match_loss",) else ["."])
    for _ in range(12):                                 # skip anything she said recently
        opener = rng.choice(OPENERS) if event not in ("death", "match_loss", "encourage") else ""
        core = rng.choice(cores)
        starts = not opener or opener.rstrip().endswith(("!", "."))     # "Yes! That's..." / "Okay, that's..."
        text = opener + (core[0].upper() + core[1:] if starts else core) + rng.choice(closers)
        if persona == "deadpan":
            text = text.replace("!", ".")
        if text not in _recent:
            break
    _recent.append(text)
    del _recent[:-20]
    return text


# -- what each game tells us -------------------------------------------------------------------------------
def _num(d: dict, *path, default=0):
    for key in path:
        d = d.get(key) if isinstance(d, dict) else None
    return d if isinstance(d, (int, float)) else default


class CS2:
    """Counter-Strike 2 Game State Integration: your kills, headshots, multi-kills, rounds, the match."""

    def __init__(self) -> None:
        self.last: dict = {}

    def update(self, data: dict) -> list[str]:
        player, me = data.get("player") or {}, (data.get("provider") or {}).get("steamid")
        if not me or player.get("steamid") != me:
            return []                                  # spectating someone else after dying
        now = {"kills": _num(player, "match_stats", "kills"), "deaths": _num(player, "match_stats", "deaths"),
               "round_kills": _num(player, "state", "round_kills"), "hs": _num(player, "state", "round_killhs"),
               "round": _num(data, "map", "round"), "phase": (data.get("round") or {}).get("phase", ""),
               "map_phase": (data.get("map") or {}).get("phase", "")}
        before, self.last = self.last, now
        if not before:
            return []
        out = []
        if now["kills"] > before["kills"]:
            rk = now["round_kills"]
            out.append({2: "double", 3: "triple", 4: "quad"}.get(rk, "ace" if rk >= 5 else
                       "headshot" if now["hs"] > before["hs"] else "kill"))
        if now["deaths"] > before["deaths"]:
            out.append("death")
        win = (data.get("round") or {}).get("win_team")
        if now["phase"] == "over" and before["phase"] != "over" and win and win == player.get("team"):
            out.append("round_win")
        if now["map_phase"] == "gameover" and before["map_phase"] != "gameover":
            mine = "team_ct" if player.get("team") == "CT" else "team_t"
            other = "team_t" if mine == "team_ct" else "team_ct"
            mine_score, other_score = _num(data, "map", mine, "score"), _num(data, "map", other, "score")
            out.append("match_win" if mine_score > other_score else "match_loss")
        return out


class Dota2:
    def __init__(self) -> None:
        self.last: dict = {}

    def update(self, data: dict) -> list[str]:
        player = data.get("player") or {}
        if "kills" not in player:
            return []
        now = {"kills": _num(player, "kills"), "deaths": _num(player, "deaths"),
               "streak": _num(player, "kill_streak"), "win": (data.get("map") or {}).get("win_team", "none")}
        before, self.last = self.last, now
        if not before:
            return []
        out = []
        if now["kills"] > before["kills"]:
            out.append({2: "double", 3: "triple", 4: "quad"}.get(now["streak"], "ace" if now["streak"] >= 5 else "kill"))
        if now["deaths"] > before["deaths"]:
            out.append("death")
        if now["win"] not in ("none", "", None) and before["win"] in ("none", "", None):
            out.append("match_win" if now["win"] == player.get("team_name") else "match_loss")
        return out


class League:
    """Riot's Live Client Data: ChampionKill / Multikill / Ace / FirstBlood / GameEnd for you."""

    def __init__(self) -> None:
        self.seen = -1

    @staticmethod
    def _is_me(name: str, me: str) -> bool:
        return bool(name) and name.split("#")[0].strip().lower() == me.split("#")[0].strip().lower()

    def update(self, events: list[dict], me: str) -> list[str]:
        out = []
        first = self.seen < 0
        for e in events:
            eid = e.get("EventID", -1)
            if eid <= self.seen:
                continue
            self.seen = eid
            if first:
                continue                               # joined mid-game: don't cheer old kills
            name = e.get("EventName", "")
            if name == "ChampionKill" and self._is_me(e.get("KillerName", ""), me):
                out.append("kill")
            elif name == "ChampionKill" and self._is_me(e.get("VictimName", ""), me):
                out.append("death")
            elif name == "Multikill" and self._is_me(e.get("KillerName", ""), me):
                out.append({2: "double", 3: "triple", 4: "quad"}.get(e.get("KillStreak", 0), "ace"))
            elif name == "Ace" and self._is_me(e.get("Acer", ""), me):
                out.append("ace")
            elif name == "FirstBlood" and self._is_me(e.get("Recipient", ""), me):
                out.append("first_blood")
            elif name == "GameEnd":
                out.append("match_win" if e.get("Result") == "Win" else "match_loss")
        return out


# -- the config files Valve's games read ------------------------------------------------------------------------
def cfg_text(game: str, token: str) -> str:
    data = ('"provider" "1" "player_id" "1" "player_state" "1" "player_match_stats" "1" "round" "1" "map" "1"'
            if game == "cs2" else '"provider" "1" "map" "1" "player" "1" "hero" "1"')
    return (f'"Capri Game Hype"\n{{\n "uri" "http://127.0.0.1:{PORT}/{game}"\n "timeout" "1.0"\n "buffer" "0.1"\n'
            f' "throttle" "0.1"\n "heartbeat" "30.0"\n "auth" {{ "token" "{token}" }}\n "data" {{ {data} }}\n}}\n')


def cfg_path(game: str, install_dir: Path) -> Path:
    if game == "cs2":
        return install_dir / "game" / "csgo" / "cfg" / "gamestate_integration_capri.cfg"
    return install_dir / "game" / "dota" / "cfg" / "gamestate_integration" / "gamestate_integration_capri.cfg"


GAMES = {"730": "cs2", "570": "dota2"}         # Steam app id -> which game


class GameHype(QObject):
    """Listens while the setting is on; says a line (in her personality) when something happens."""
    _event = Signal(str)

    def __init__(self, settings, say: Callable[[str], None], games: Callable[[], list], processes: Callable[[], list],
                 busy: Callable[[], bool] = lambda: False, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self.settings, self.say, self.games, self.processes, self.busy, self.clock = \
            settings, say, games, processes, busy, clock
        self.trackers = {"cs2": CS2(), "dota2": Dota2()}
        self.league = League()
        self._server: ThreadingHTTPServer | None = None
        self._pending: list[str] = []
        self._last_said = -1e9
        self.on_big_moment: Callable[[str], None] | None = None   # a triple kill, an ace, a win
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.timeout.connect(self._say_best)
        self._event.connect(self._got)
        self._league_timer = QTimer(self)
        self._league_timer.timeout.connect(self._league_tick)
        self.status = ""

    PREVIEW = ["kill", "headshot", "double", "death", "triple", "ace", "round_win", "encourage", "match_win"]
    PREVIEW_GAP_MS = 2600

    def preview(self) -> list[str]:
        """Settings -> Preview: a run of what she'd say in a match (in her personality), one every couple
        of seconds - so you hear them before a game. Returns the lines, in order."""
        persona = getattr(self.settings, "personality", "edgerunner")
        lines = [line(event, persona) for event in self.PREVIEW]
        for i, text in enumerate(lines):
            QTimer.singleShot(i * self.PREVIEW_GAP_MS, lambda text=text: self.say(text))
        return lines

    # -- on / off ----------------------------------------------------------------------------------
    def apply(self) -> str:
        """Start or stop to match the setting. Returns a status line for Settings."""
        on = bool(getattr(self.settings, "game_hype", False))
        if on and self._server is None:
            self._start()
        elif not on and self._server is not None:
            self._stop()
        self.status = self._setup_files() if on else "Off."
        return self.status

    def _token(self) -> str:
        if not getattr(self.settings, "game_hype_token", ""):
            self.settings.game_hype_token = secrets.token_hex(16)
            self.settings.save()
        return self.settings.game_hype_token

    def _setup_files(self) -> str:
        found = []
        for game in self.games():
            key = GAMES.get(str(getattr(game, "appid", "")))
            if key is None or not getattr(game, "install_dir", None):
                continue
            path = cfg_path(key, Path(game.install_dir))
            text = cfg_text(key, self._token())
            try:
                if not path.exists() or path.read_text(encoding="utf-8") != text:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
                    log.info("game hype: wrote %s", path)
                found.append("Counter-Strike 2" if key == "cs2" else "Dota 2")
            except OSError as exc:
                log.warning("game hype: couldn't write %s: %s", path, exc)
        games = ", ".join(found + ["League of Legends"])
        return f"On for {games}. (Restart CS2 / Dota 2 once if they were open.)"

    def _start(self) -> None:
        hype = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):                              # noqa: N802 - http.server's name
                length = min(int(self.headers.get("Content-Length") or 0), 200_000)
                try:
                    data = json.loads(self.rfile.read(length).decode("utf-8", "replace") or "{}")
                except ValueError:
                    data = {}
                self.send_response(200)
                self.end_headers()
                game = self.path.strip("/")
                if (data.get("auth") or {}).get("token") != hype._token() or game not in hype.trackers:
                    return                                   # not from the game we set up
                for event in hype.trackers[game].update(data):
                    hype._event.emit(event)

            def log_message(self, *args):                    # quiet
                pass
        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError as exc:
            log.warning("game hype: port %s busy: %s", PORT, exc)
            self._server = None
            return
        threading.Thread(target=self._server.serve_forever, name="capri-game-hype", daemon=True).start()
        self._league_timer.start(5000)                       # is a League match running?
        log.info("game hype: listening on 127.0.0.1:%s", PORT)

    def _stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            threading.Thread(target=server.shutdown, daemon=True).start()
        self._league_timer.stop()

    # -- League: read only while a match runs -------------------------------------------------------
    def _league_tick(self) -> None:
        running = any((p.name or "").lower() == LEAGUE_EXE for p in self.processes())
        self._league_timer.setInterval(1200 if running else 5000)
        if running:
            threading.Thread(target=self._league_read, daemon=True).start()
        else:
            self.league = League()

    def _league_read(self) -> None:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE                  # Riot's own certificate, on 127.0.0.1 only
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
        try:
            with opener.open(LEAGUE + "/activeplayername", timeout=1.0) as r:
                me = json.loads(r.read().decode())
            with opener.open(LEAGUE + "/eventdata", timeout=1.0) as r:
                events = json.loads(r.read().decode()).get("Events", [])
        except (OSError, ValueError):
            return                                           # loading screen / not in a match yet
        for event in self.league.update(events, str(me)):
            self._event.emit(event)

    # -- saying it --------------------------------------------------------------------------------------
    def _got(self, event: str) -> None:
        if event == "death" and not getattr(self.settings, "game_hype_deaths", False):
            return
        self._pending.append(event)
        self._flush.start(BURST_MS)                          # wait a moment: more kills may follow

    def _say_best(self) -> None:
        events, self._pending = self._pending, []
        if not events:
            return
        best = max(events, key=lambda e: RANK.index(e) if e in RANK else -1)
        if best == "kill" and events.count("kill") >= 2:
            best = "double" if events.count("kill") == 2 else "triple"
        if best in BIG_MOMENTS and self.on_big_moment is not None:
            try:
                self.on_big_moment(best)                      # "Save big moments": a clip of it
            except Exception:
                log.exception("game hype: big moment")
        if self.busy() or self.clock() - self._last_said < MIN_GAP:
            return
        self._last_said = self.clock()
        self.say(line(best, getattr(self.settings, "personality", "edgerunner")))
