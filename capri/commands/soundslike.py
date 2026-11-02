"""Hearing what you meant when the words came out (or came through) a bit wrong: accents, a bad
mic, slurring. "shot down my computa" -> "shut down my computer", "lee call" -> "leave call".

Each word becomes a rough *sound* code that ignores what accents and mics usually change: most
vowels, b/p, d/t, g/k, v/w/f, s/z/j, l/r. If what you said sounds very like one of her commands
(and clearly more like that one than any other), she does that command. Only for short things
that aren't already a command or chat, so normal conversation is left alone.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

COMMANDS = [
    "shut down my computer", "restart my computer", "lock my computer", "put my computer to sleep",
    "open discord", "close discord", "open spotify", "close spotify", "open steam", "open youtube",
    "mute me", "unmute me", "deafen me", "undeafen me", "join call", "leave call", "stream my screen",
    "stop streaming", "take a screenshot", "minimize everything", "bring everything back", "show my desktop",
    "play music", "pause the music", "skip this song", "next song", "previous song", "turn it up", "turn it down",
    "what song is this", "what time is it", "whats the date", "whats the weather", "is it going to rain",
    "whats using my ram", "how much storage do i have left", "set a timer for five minutes", "cancel my timer",
    "how long is left", "switch tabs", "close this tab", "open a new tab", "refresh the page", "scroll down",
    "scroll up", "copy that", "paste", "undo", "select all", "drone mode", "lie down", "get up", "hide", "come back",
    "go to the bottom left", "go to the bottom right", "go to the top left", "go to the top right",
    "stop talking", "talk faster", "talk slower", "speak up", "change your voice", "repeat that",
    "what did i say", "search mode", "open the chat", "turn on game hype", "turn off game hype",
    "sit on my window", "get off the window", "set up your brain", "tell me a joke", "be sarcastic",
    "be normal", "click subscribe", "play the video", "pause the video", "never mind",
]
MAX_WORDS = 7
GOOD = 0.84            # this much alike...
MARGIN = 0.04          # ...and clearly closer than the next-best command

_PAIRS = [("tion", "sn"), ("sion", "sn"), ("ph", "f"), ("ck", "k"), ("sh", "s"), ("ch", "s"), ("th", "t"),
          ("wh", "w"), ("gh", ""), ("kn", "n"), ("wr", "r"), ("qu", "kw"), ("x", "ks")]
_CLASS = str.maketrans({"b": "p", "d": "t", "g": "k", "q": "k", "v": "f", "w": "f", "z": "s", "j": "s",
                        "l": "r", "m": "n", "h": None, "y": None})


def sound_key(word: str) -> str:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return ""
    for a, b in _PAIRS:
        w = w.replace(a, b)
    w = re.sub(r"c(?=[eiy])", "s", w).replace("c", "k")
    first = "a" if w[0] in "aeiou" else ""
    w = re.sub(r"[aeiou]", "", w).translate(_CLASS)
    w = re.sub(r"(.)\1+", r"\1", w)
    return (first + w) or "a"


def phrase_key(text: str) -> str:
    return " ".join(sound_key(w) for w in text.split())


def closest(text: str, extra: list[str] | tuple[str, ...] = ()) -> str | None:
    """The command `text` sounds like, or None if it doesn't clearly sound like one."""
    said = text.strip().lower()
    words = said.split()
    if not words or len(words) > MAX_WORDS:
        return None
    key = phrase_key(said)
    scored = []
    for command in list(COMMANDS) + [c for c in extra if c]:
        if abs(len(command.split()) - len(words)) > 2:
            continue
        sound = SequenceMatcher(None, key, phrase_key(command)).ratio()
        spelled = SequenceMatcher(None, said, command).ratio()
        scored.append((0.65 * sound + 0.35 * spelled, command))
    if not scored:
        return None
    scored.sort(reverse=True)
    best, command = scored[0]
    runner_up = next((s for s, c in scored[1:] if c != command), 0.0)
    if best >= GOOD and best - runner_up >= MARGIN and command != said:
        return command
    return None
