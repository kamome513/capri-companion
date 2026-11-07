"""She plays your game: "Hey Capri, play this for me" / "your turn" / "...and make me a pickaxe".

How: every step she looks at the game window (a picture to the AI you picked - one that can see), the AI picks
her next few moves (hold a key, turn the camera, click, wait), and her hands do them (game_hands.py). Then she
looks again. She says what she's up to now and then.

It's slow (each look takes the AI a second or few) and she's still learning, so it's best at simple goals: walk
over there, look around, mine that, attack, jump. Safety:
* Off until you turn on Settings -> Extras -> "Let her play games".
* Only the window that was in front when you asked. If you switch away, she stops.
* Press Esc (or say "stop", "my turn") and she stops at once. She also stops after 5 minutes.
* Only game keys, one at a time (no Windows key, Alt, Enter or combos); clicks only inside the game window.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .game_hands import MAX_HOLD, MAX_LOOK, clean_key

log = logging.getLogger("capri")

MAX_TIME = 300.0              # seconds
MAX_STEPS = 120
MAX_ACTIONS = 6               # per look
SAY_GAP = 9.0                 # seconds between her comments
PROMPT = """You're Capri, playing the game on this screen for the user. Their goal: {goal}.
{notes}Look carefully at the screen. Work out: what game is this, who is the player's character, what's the
objective (beat enemies? reach the exit? survive? collect things?), what's happening right now - then act.
Reply with ONLY a JSON object, nothing else:
{{"game": "<what game this is>", "objective": "<how you win, in a few words>", "plan": "<what you're doing next
and why, one short sentence>", "say": "<a few words to the user in your own voice, or empty>",
"do": [<2 to 6 moves>], "done": <true only once the goal is done or impossible>}}
Moves:
  {{"key": "d", "hold": 0.6}}          hold a key that long (0.05-3 s). Keys: a-z, 0-9, space, shift, ctrl, tab, up, down, left, right
  {{"keys": ["d", "space"], "hold": 0.5}}   hold two keys together (jump while running, sprint forward...)
  {{"key": "w", "hold": 2, "look": [dx, dy]}}   hold a key AND turn the camera at the same time
  {{"look": [dx, dy]}}                 turn the camera / move the mouse that many pixels (-600..600)
  {{"mine": 1.5}}                      hold the left mouse button where the crosshair / pointer is (break, attack, shoot)
  {{"use": 0}}                         right-click where the crosshair / pointer is (place, use, aim)
  {{"click": [x, y], "button": "left", "hold": 0}}   click at x, y = fractions 0..1 across / down the game window
  {{"wait": 0.5}}                      wait (up to 2 s)
Move with the KEYBOARD (most games: WASD or the arrow keys walk, space or W / up jumps). Clicking is for menus,
buttons and aiming - clicking the ground doesn't walk in most games. Hold movement keys long enough to see it
happen (0.4-1.5 s). If the last moves changed nothing, the keys you used don't work here: try different ones.
{hints}{lessons}Your last moves: {history}
{feedback}"""
# What a new player is told about a few games (by the game's window title)
GAME_HINTS = {
    "minecraft": "Minecraft: W walks, space jumps, shift sneaks, ctrl sprints. To break a block (wood, dirt, stone), "
                 "turn so the crosshair is ON the block, then \"mine\" for 1-3 s (logs take about 2 s by hand) - "
                 "too short and it breaks nothing. Look down a bit ([0, 100]) to aim at blocks on the ground. 1-9 "
                 "pick the hotbar slot. If a menu is open (\"Game Menu\", inventory), click \"Back to Game\" or "
                 "press e to close the inventory. Don't stare at the sky: keep the view near the horizon.",
    "roblox": "Roblox: WASD walks, space jumps, the camera turns while the right mouse button is held - use the "
              "arrow keys left / right to turn instead.",
}


def hints_for(game: str) -> str:
    low = (game or "").lower()
    return "".join(text + "\n" for name, text in GAME_HINTS.items() if name in low)


LESSONS_INTRO = "What you learned playing this game before - use it, don't repeat these mistakes:\n{items}\n"
REFLECT = """You were playing this game for the user (goal: {goal}) and it ended: {why}.
Your last moves: {history}
In ONE short sentence, what should you do differently next time in this game? Reply with only that sentence."""
MAX_LESSONS = 12              # per game (the newest kept)
REFLECT_ON = ("escape", "time", "steps", "stopped")      # endings worth thinking about


def game_name(title: str) -> str:
    """A game's window title -> the name its lessons are kept under ("Five Nights at Freddy's 2 - v1.0" ->
    "five nights at freddy's 2")."""
    t = re.split(r"\s+[-|–—]\s+", (title or "").strip())[0]
    t = re.sub(r"\s*\(?(?:v|version\s*)\d[\w.]*\)?\s*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip().lower()[:80]


class GameLessons:
    """What she learned from her mistakes, per game, in a small file on this PC (never sent anywhere except as
    part of her prompt to your AI while she plays that game)."""

    def __init__(self, path=None) -> None:
        self.path = path
        self.games: dict[str, dict] = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path is not None else {}
            self.games = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            self.games = {}

    def lessons(self, game: str) -> list[str]:
        return [str(x) for x in self.games.get(game, {}).get("lessons", [])][-MAX_LESSONS:]

    def add(self, game: str, lesson: str) -> bool:
        """Keep a new lesson (not one she already has, said differently). True if it was new."""
        from difflib import SequenceMatcher
        lesson = re.sub(r"\s+", " ", (lesson or "").strip().strip('"'))[:160]
        if not game or len(lesson) < 6:
            return False
        entry = self.games.setdefault(game, {"lessons": [], "tries": 0})
        have = entry.setdefault("lessons", [])
        if any(SequenceMatcher(None, lesson.lower(), old.lower()).ratio() > 0.8 for old in have):
            return False
        have.append(lesson)
        del have[:-MAX_LESSONS]
        self.save()
        return True

    def notes(self, game: str) -> dict:
        """What she worked out about this game: {"game", "objective", "plan", "keys_work", "keys_dead"}."""
        return dict(self.games.get(game, {}).get("notes", {})) if game else {}

    def set_notes(self, game: str, notes: dict) -> None:
        if not game:
            return
        entry = self.games.setdefault(game, {"lessons": [], "tries": 0})
        entry["notes"] = {k: v for k, v in notes.items() if v not in ("", None, [])}
        self.save()

    def played(self, game: str, why: str) -> None:
        if not game:
            return
        entry = self.games.setdefault(game, {"lessons": [], "tries": 0})
        entry["tries"] = int(entry.get("tries", 0)) + 1
        entry["last"] = why
        self.save()

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.games, indent=1), encoding="utf-8")
        except OSError:
            pass


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int


def parse_plan(text: str) -> dict | None:
    """The AI's answer -> {"say", "do", "done"} (it may wrap the JSON in words or a code block)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        plan = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(plan, dict):
        return None
    moves = plan.get("do") if isinstance(plan.get("do"), list) else []
    return {"say": str(plan.get("say") or "")[:160], "do": moves[:MAX_ACTIONS], "done": bool(plan.get("done")),
            "lesson": str(plan.get("lesson") or "")[:160], "game": str(plan.get("game") or "")[:80],
            "objective": str(plan.get("objective") or "")[:160], "plan": str(plan.get("plan") or "")[:200]}


def checked(move, window: Rect) -> tuple | None:
    """One move, made safe: ("key", key, seconds) / ("look", dx, dy) / ("click", x, y, button, hold) / ("wait", s).
    None if it isn't one she's allowed to do."""
    if not isinstance(move, dict):
        return None
    try:
        if "key" in move:
            key = clean_key(str(move["key"]))
            if not key:
                return None
            hold = max(0.05, min(MAX_HOLD, float(move.get("hold", 0.15))))
            if isinstance(move.get("look"), (list, tuple)) and len(move["look"]) == 2:
                dx, dy = (int(max(-MAX_LOOK, min(MAX_LOOK, float(v)))) for v in move["look"])
                return ("key", key, hold, dx, dy)                   # walk and turn at once
            return ("key", key, hold)
        if "keys" in move and isinstance(move["keys"], (list, tuple)):
            keys = tuple(k for k in (clean_key(str(x)) for x in move["keys"][:2]) if k)
            if not keys:
                return None
            hold = max(0.05, min(MAX_HOLD, float(move.get("hold", 0.3))))
            return ("keys", keys, hold) if len(keys) > 1 else ("key", keys[0], hold)
        if "mine" in move or "attack" in move:
            return ("press", "left", max(0.1, min(MAX_HOLD, float(move.get("mine", move.get("attack")) or 1.0))))
        if "use" in move:
            return ("press", "right", max(0.05, min(MAX_HOLD, float(move.get("use") or 0.1))))
        if "look" in move:
            dx, dy = move["look"]
            return ("look", int(max(-MAX_LOOK, min(MAX_LOOK, float(dx)))), int(max(-MAX_LOOK, min(MAX_LOOK, float(dy)))))
        if "click" in move:
            fx, fy = (max(0.0, min(1.0, float(v))) for v in move["click"])
            button = "right" if str(move.get("button", "left")).lower().startswith("r") else "left"
            hold = max(0.0, min(MAX_HOLD, float(move.get("hold", 0) or 0)))
            return ("click", window.x + round(fx * (window.w - 1)), window.y + round(fy * (window.h - 1)), button, hold)
        if "wait" in move:
            return ("wait", max(0.0, min(2.0, float(move["wait"]))))
    except (TypeError, ValueError):
        return None
    return None


def describe(move: tuple) -> str:
    kind = move[0]
    if kind == "key":
        return f"held {move[1]} {move[2]:.1f}s" + (f" turning {move[3]:+d},{move[4]:+d}" if len(move) > 3 else "")
    if kind == "press":
        return ("mined" if move[1] == "left" else "used") + f" {move[2]:.1f}s"
    if kind == "keys":
        return f"held {'+'.join(move[1])} {move[2]:.1f}s"
    if kind == "look":
        return f"looked {move[1]:+d},{move[2]:+d}"
    if kind == "click":
        return f"{move[3]}-clicked" + (f" {move[4]:.1f}s" if move[4] else "")
    return f"waited {move[1]:.1f}s"


class GameAgent:
    """Runs one game session on a background thread. Everything it needs comes in as callables (tests fake them)."""

    def __init__(self, brain, hands_factory: Callable, grab: Callable[[Rect], object],
                 foreground: Callable[[], int], window_rect: Callable[[int], Rect | None],
                 say: Callable[[str], None], finished: Callable[[str], None],
                 cursor: Callable[[int, int], None] = lambda x, y: None, clock=time.monotonic, sleep=time.sleep,
                 jpeg: Callable[[object], str] | None = None, title: Callable[[int], str] = lambda hwnd: "",
                 lessons: GameLessons | None = None) -> None:
        self.brain, self.hands_factory, self.grab = brain, hands_factory, grab
        self.foreground, self.window_rect, self.say, self.finished, self.cursor = \
            foreground, window_rect, say, finished, cursor
        self.clock, self.sleep = clock, sleep
        self.jpeg = jpeg or self._jpeg
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.goal = ""
        self.moves: list[str] = []
        self.title = title
        self.lessons = lessons or GameLessons(None)
        self.game = ""
        self._last_jpeg = ""
        self.notes: dict = {}

    @staticmethod
    def _jpeg(image) -> str:
        from .screen_watch import to_jpeg_b64
        return to_jpeg_b64(image, 1024, 65)

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, goal: str, background: bool = True) -> str:
        """Start playing the window in front. "" if she started, else why not."""
        if self.running:
            return "I'm already playing."
        hwnd = self.foreground()
        rect = self.window_rect(hwnd) if hwnd else None
        if not hwnd or rect is None or rect.w < 100 or rect.h < 100:
            return "Put the game in front first, then ask me."
        self.goal = (goal or "").strip() or "play well: explore, and do whatever makes sense in this game"
        self.stop_event.clear()
        self.moves = []
        try:
            self.game = game_name(self.title(hwnd))
        except Exception:
            self.game = ""
        if background:
            self.thread = threading.Thread(target=self._run, args=(hwnd,), daemon=True, name="capri-game")
            self.thread.start()
        else:
            self._run(hwnd)
        return ""

    def stop(self) -> None:
        self.stop_event.set()

    # -- the loop --------------------------------------------------------------------------------------------------
    @staticmethod
    def _blank(image) -> bool:
        try:
            from .screen_watch import is_blank
            return is_blank(image)
        except Exception:
            return False

    def _run(self, hwnd: int) -> None:
        log.info("game: playing %r (goal: %s)", self.game, self.goal)
        why = "done"
        try:
            hands = self.hands_factory()
            why = self._play(hwnd, hands)
        except Exception as exc:
            log.exception("game: stopped by a problem")
            why = f"problem: {exc}"
        log.info("game: stopped - %s (%d moves)", why, len(self.moves))
        self.finished(why)
        try:
            self._reflect(why)
        except Exception:
            log.info("game: couldn't think it over", exc_info=True)

    def _reflect(self, why: str) -> None:
        """After a session that didn't reach the goal: one sentence on what to do differently, kept for next time."""
        self.lessons.played(self.game, why)
        if why not in REFLECT_ON or not self.game or not self._last_jpeg or len(self.moves) < 3:
            return
        history = "; ".join(self.moves[-12:])
        reply = self.brain.look(REFLECT.format(goal=self.goal, why=ENDINGS.get(why, why), history=history),
                                self._last_jpeg)
        if not getattr(reply, "error", False) and self.lessons.add(self.game, reply.text or ""):
            log.info("game: learned for %s: %s", self.game, (reply.text or "")[:120])

    def _prompt(self, history: str, feedback: str = "") -> str:
        learned = self.lessons.lessons(self.game)
        intro = LESSONS_INTRO.format(items="\n".join(f"- {x}" for x in learned)) if learned else ""
        n = self.notes
        notes = ""
        if n.get("game") or n.get("objective"):
            notes += f"What you worked out so far: it's {n.get('game') or 'this game'}"
            notes += f"; to win: {n['objective']}" if n.get("objective") else ""
            notes += f"; your plan: {n['plan']}" if n.get("plan") else ""
            notes += ". Change any of it if the screen says otherwise.\n"
        if n.get("keys_work") or n.get("keys_dead"):
            notes += "When you tried the keys: " + (f"{', '.join(n.get('keys_work', []))} made things move" if
                                                    n.get("keys_work") else "no key made anything move")
            notes += (f"; {', '.join(n['keys_dead'])} did nothing" if n.get("keys_dead") else "") + ".\n"
        return PROMPT.format(goal=self.goal, history=history, lessons=intro, hints=hints_for(self.game),
                             notes=notes, feedback=feedback)

    # -- seeing what her moves did ---------------------------------------------------------------------------------
    @staticmethod
    def _thumb(image):
        """A tiny grey copy of a picture, to compare two moments (None if it isn't a picture she can read)."""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QImage
            if not isinstance(image, QImage) or image.isNull():
                return None
            import numpy as np
            small = image.scaled(96, 54, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
            a = np.frombuffer(small.constBits(), np.uint8).reshape(small.height(), small.bytesPerLine())[:, :96]
            return a.astype(np.int16)
        except Exception:
            return None

    @staticmethod
    def _changed(a, b) -> float | None:
        """How much of the picture changed between two thumbs (0..1), or None."""
        if a is None or b is None or a.shape != b.shape:
            return None
        import numpy as np
        return float(np.mean(np.abs(a - b) > 18))

    PROBE_KEYS = ("d", "a", "right", "left", "space", "w", "up")
    MOVED = 0.012              # this much of the picture changing after a key = the key does something

    def _probe(self, hwnd: int, hands, window) -> None:
        """New game: press each usual movement key a moment and see if anything moves - so the AI knows which
        keys this game listens to (and if none do, the game probably needs a click first, to take the keys)."""
        if self.notes.get("keys_work") or not hasattr(hands, "hold"):
            return
        if self._thumb(self.grab(window)) is None:
            return                                          # no picture to compare: skip it
        for attempt in range(2):
            work, dead = [], []
            for key in self.PROBE_KEYS:
                if self.stop_event.is_set() or hands.escape_pressed() or self.foreground() != hwnd:
                    return
                before = self._thumb(self.grab(window))
                hands.hold(key, 0.35)
                self.sleep(0.12)
                change = self._changed(before, self._thumb(self.grab(window)))
                (work if change is not None and change >= self.MOVED else dead).append(key)
            log.info("game: keys that move things: %s; nothing: %s", work or "none", dead or "none")
            if work or attempt or getattr(hands, "pointer_hidden", lambda: False)():
                break
            self.cursor(window.x + window.w // 2, window.y + window.h // 2)   # none worked: click into the game
            self.sleep(0.2)
            hands.click(window.x + window.w // 2, window.y + window.h // 2, "left", 0.0)
            self.sleep(0.3)
        self.notes["keys_work"], self.notes["keys_dead"] = work, dead
        self.lessons.set_notes(self.game, self.notes)

    def _play(self, hwnd: int, hands) -> str:
        started, last_said = self.clock(), -1e9
        self.notes = self.lessons.notes(self.game)
        first = self.window_rect(hwnd)
        if first is not None:
            try:
                self._probe(hwnd, hands, first)
            except Exception:
                log.info("game: couldn't try the keys", exc_info=True)
        change = None                                       # how much her last moves changed the picture
        for _step in range(MAX_STEPS):
            if self.stop_event.is_set():
                return "stopped"
            if self.clock() - started > MAX_TIME:
                return "time"
            if hands.escape_pressed():
                return "escape"
            if self.foreground() != hwnd:
                return "switched"
            window = self.window_rect(hwnd)
            if window is None:
                return "closed"
            image = self.grab(window)
            if image is not None and self._blank(image):
                log.info("game: the picture of %s came out black", self.game or "the game")
                return "black"                          # exclusive fullscreen hides the picture from other apps
            jpeg = self.jpeg(image) if image is not None else ""
            if not jpeg:
                return "no picture"
            self._last_jpeg = jpeg
            now_thumb = self._thumb(image)
            feedback = "" if change is None else (
                "After your last moves the picture barely changed: those moves did nothing here. Do something "
                "different (other keys, hold longer, or click into the game first)." if change < self.MOVED else
                "After your last moves the picture changed - check if it was what you wanted.")
            history = "; ".join(self.moves[-8:]) or "none yet"
            reply = self.brain.look(self._prompt(history, feedback), jpeg)
            if getattr(reply, "missing", False):
                return "no ai"
            if getattr(reply, "error", False):
                return "ai: " + (reply.text or "it didn't answer")
            plan = parse_plan(reply.text)
            log.info("game: step %d - AI said: %s", _step + 1, re.sub(r"\s+", " ", reply.text or "")[:300])
            if plan is None:
                self.moves.append("(answer wasn't a plan)")
                continue
            if plan["lesson"] and self.lessons.add(self.game, plan["lesson"]):
                log.info("game: learned for %s: %s", self.game, plan["lesson"])
            if any(plan[k] for k in ("game", "objective", "plan")):   # what she's worked out: kept for next look
                for k in ("game", "objective", "plan"):
                    if plan[k]:
                        self.notes[k] = plan[k]
                self.lessons.set_notes(self.game, self.notes)
            if plan["say"] and self.clock() - last_said > SAY_GAP:
                last_said = self.clock()
                self.say(plan["say"])
            for raw in plan["do"]:
                move = checked(raw, window)
                if move is None:
                    continue
                if self.stop_event.is_set() or hands.escape_pressed():
                    return "escape" if not self.stop_event.is_set() else "stopped"
                if self.foreground() != hwnd:
                    return "switched"
                self._do(hands, move)
                self.moves.append(describe(move))
                log.info("game: did %s", describe(move))
            change = self._changed(now_thumb, self._thumb(self.grab(window))) if plan["do"] and now_thumb is not None \
                else None                                   # before her moves vs after them
            if plan["done"]:
                return "done"
        return "steps"

    def _do(self, hands, move: tuple) -> None:
        kind = move[0]
        if kind == "keys":
            if hasattr(hands, "hold_many"):
                hands.hold_many(move[1], move[2])
            else:
                hands.hold(move[1][0], move[2])
        elif kind == "key":
            if len(move) > 3:
                hands.hold(move[1], move[2], look=(move[3], move[4]))
            else:
                hands.hold(move[1], move[2])
        elif kind == "look":
            hands.look(move[1], move[2])
        elif kind == "press":
            hands.press(move[1], move[2])
        elif kind == "click":
            hidden = getattr(hands, "pointer_hidden", lambda: False)
            if hidden():                                        # the game steers the camera with the mouse:
                hands.press(move[3], max(move[4], 0.1))         # moving the pointer would yank the view - press here
            else:
                self.cursor(move[1], move[2])                   # her cursor glides there first
                self.sleep(0.25)
                hands.click(move[1], move[2], move[3], move[4])
        elif kind == "wait":
            self.sleep(move[1])


ENDINGS = {
    "done": "Done! Your turn.",
    "stopped": "Okay, stopping. It's all yours.",
    "escape": "Okay, hands off. Your turn.",
    "switched": "You switched away, so I stopped.",
    "closed": "The game closed, so I stopped.",
    "time": "That's five minutes - I'll hand it back.",
    "steps": "I've done all I can for now. Your turn.",
    "no picture": "I can't see the game window, so I stopped.",
    "black": "Your game shows up black to me - it's in exclusive fullscreen. Switch it to windowed (F11 in "
             "Minecraft) or borderless, then ask me again.",
    "no ai": "I need an AI that can see to play. Pick one in my Settings.",
}


def ending(why: str) -> str:
    if why.startswith("ai: "):
        return f"My AI stopped me: {why[4:]}"
    if why.startswith("problem: "):
        return "Something went wrong, so I stopped."
    return ENDINGS.get(why, "I stopped.")
