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
MAX_ACTIONS = 4               # per look
SAY_GAP = 9.0                 # seconds between her comments
PROMPT = """You're playing the game on this screen for the user, as Capri. Their goal: {goal}.
Look at the screen and pick your next moves. Reply with ONLY a JSON object, nothing else:
{{"say": "<a few words in your own voice, or empty>", "do": [<1 to 4 moves>], "done": <true once the goal is done or impossible>}}
Moves:
  {{"key": "w", "hold": 1.0}}       hold a key that long (0.05-3 s). Keys: a-z, 0-9, space, shift, ctrl, tab, up, down, left, right
  {{"look": [dx, dy]}}              turn the camera / move the mouse that many pixels (-600..600)
  {{"click": [x, y], "button": "left", "hold": 0}}   click at x, y = fractions 0..1 across / down the game window;
                                     "hold" seconds keeps the button down (mining, attacking); "button" left or right
  {{"wait": 0.5}}                   wait (up to 2 s)
Your last moves: {history}"""


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
    return {"say": str(plan.get("say") or "")[:160], "do": moves[:MAX_ACTIONS], "done": bool(plan.get("done"))}


def checked(move, window: Rect) -> tuple | None:
    """One move, made safe: ("key", key, seconds) / ("look", dx, dy) / ("click", x, y, button, hold) / ("wait", s).
    None if it isn't one she's allowed to do."""
    if not isinstance(move, dict):
        return None
    try:
        if "key" in move:
            key = clean_key(str(move["key"]))
            return ("key", key, max(0.05, min(MAX_HOLD, float(move.get("hold", 0.15))))) if key else None
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
        return f"held {move[1]} {move[2]:.1f}s"
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
                 jpeg: Callable[[object], str] | None = None) -> None:
        self.brain, self.hands_factory, self.grab = brain, hands_factory, grab
        self.foreground, self.window_rect, self.say, self.finished, self.cursor = \
            foreground, window_rect, say, finished, cursor
        self.clock, self.sleep = clock, sleep
        self.jpeg = jpeg or self._jpeg
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.goal = ""
        self.moves: list[str] = []

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
        if background:
            self.thread = threading.Thread(target=self._run, args=(hwnd,), daemon=True, name="capri-game")
            self.thread.start()
        else:
            self._run(hwnd)
        return ""

    def stop(self) -> None:
        self.stop_event.set()

    # -- the loop --------------------------------------------------------------------------------------------------
    def _run(self, hwnd: int) -> None:
        why = "done"
        try:
            hands = self.hands_factory()
            why = self._play(hwnd, hands)
        except Exception as exc:
            log.exception("game: stopped by a problem")
            why = f"problem: {exc}"
        self.finished(why)

    def _play(self, hwnd: int, hands) -> str:
        started, last_said = self.clock(), -1e9
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
            jpeg = self.jpeg(image) if image is not None else ""
            if not jpeg:
                return "no picture"
            history = "; ".join(self.moves[-8:]) or "none yet"
            reply = self.brain.look(PROMPT.format(goal=self.goal, history=history), jpeg)
            if getattr(reply, "missing", False):
                return "no ai"
            if getattr(reply, "error", False):
                return "ai: " + (reply.text or "it didn't answer")
            plan = parse_plan(reply.text)
            if plan is None:
                self.moves.append("(answer wasn't a plan)")
                continue
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
            if plan["done"]:
                return "done"
        return "steps"

    def _do(self, hands, move: tuple) -> None:
        kind = move[0]
        if kind == "key":
            hands.hold(move[1], move[2])
        elif kind == "look":
            hands.look(move[1], move[2])
        elif kind == "click":
            self.cursor(move[1], move[2])                       # her cursor glides there first
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
    "no ai": "I need an AI that can see to play. Pick one in my Settings.",
}


def ending(why: str) -> str:
    if why.startswith("ai: "):
        return f"My AI stopped me: {why[4:]}"
    if why.startswith("problem: "):
        return "Something went wrong, so I stopped."
    return ENDINGS.get(why, "I stopped.")
