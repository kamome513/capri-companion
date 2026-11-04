"""Understanding a command however you put it - extra words, other words, another order.

The parser (parser.py) knows each command's usual phrasings exactly. People don't talk exactly:
"time to shut down the computer", "go open discord", "get me out of the call", "capture my screen",
"put a timer on for 20 minutes". When the parser doesn't get a clear command, this tries, in order:

1. the same words with synonyms swapped for the ones she knows (pc / laptop / rig -> computer,
   reboot -> restart, quit / exit / kill -> close...);
2. the same words with a few extra ones left out (up to 3 - the "time to", "go", "for me", "real
   quick" people add), keeping the version that's a clear command;
3. what it's about, in any word order: a few key ideas per command ("leave" + "call", "capture" +
   "screen", "tell" + "time"...).

A command that names an app only counts if it's one of yours, so a sentence like "my brother shut
the door" never closes anything. Everything still goes through the router's usual confirmations.
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import Callable

from .parser import Intent, Kind, normalise, parse

SYNONYMS = [   # (spoken, what the parser knows) - whole words only
    (r"pc|laptop|rig|machine|desktop computer", "computer"),
    (r"reboot", "restart"),
    (r"quit|exit|terminate|kill off", "close"),
    (r"launch|boot up|fire up|start up|pull up|bring up", "open"),
    (r"microphone|mike", "mic"),
    (r"tune|tunes|track|jam", "song"),
    (r"vc|voice chat|voice channel|voice call|discord call", "call"),
    (r"snap|grab|capture", "take"),
    (r"screen shot|screen grab|screen capture|printscreen|print screen", "screenshot"),
    (r"minimise", "minimize"),
]
FILLERS = {"go", "time", "to", "the", "a", "an", "my", "for", "me", "now", "please", "just", "real", "quick", "quickly",
           "right", "it", "that", "this", "up", "on", "i", "want", "wanna", "need", "you", "can", "could", "would",
           "will", "do", "be", "so", "like", "ok", "okay", "hey", "yo", "capri", "um", "uh", "then", "and", "also",
           "again", "already", "maybe", "kinda", "some", "bit", "little", "lil", "all", "whole", "of", "with", "at",
           "in", "out", "off", "think", "should", "let", "lets", "s", "get", "go", "ahead", "try", "actually"}
MAX_WORDS = 14
MAX_TRIES = 160

# 3. what it's about: (any of these ideas must all be there) -> what to do. Order doesn't matter.
IDEAS = [
    ([r"leave|out|exit|disconnect|hang|drop|bail", r"call|voice"], "leave call"),
    ([r"join|get in|hop in|hop on|connect|enter|put me in", r"call|voice"], "join call"),
    ([r"take|make|save", r"screenshot|picture of (?:my |the )?screen|screen"], "take a screenshot"),
    ([r"tell|know|check|whats|what is|say|give|got|have", r"time(?! zones?| difference)"], "what time is it"),
    ([r"tell|check|whats|what is|hows|how is|look up|give", r"weather|forecast|outside"], "whats the weather"),
    ([r"what s it like|whats it like", r"outside"], "whats the weather"),
    ([r"cold|hot|warm|sunny|raining|snowing|windy|freezing", r"outside|out there|today|right now"], "whats the weather"),
    ([r"timer|countdown", r"\d+|one|two|three|four|five|ten|fifteen|twenty|thirty|minute|second|hour"], None),   # timers: below
    ([r"shut|power|turn|switch", r"down|off", r"computer|everything|it all"], "shut down my computer"),
    ([r"restart"], "restart my computer"),
    ([r"mute"], None),                                    # mute / unmute: the parser's own wording handles these
]
APP_VERBS = [(r"open|start|load|run|use|get on|hop on|jump on|put|bring", "open"), (r"close|shut|turn off|get rid of|end|stop", "close")]
CHATTY = r"\b(?:your|his|her|their|our|is|are|was|were|a|an|mind|risk|heart|word|damage|chance)\b"   # not app names
NOT_ABOUT = (r"\b(?:door|doors|light|lights|life|tv|fridge|oven|car|eyes|mouth|book|lid|present|gift|box|"
             r"bottle|curtains|blinds|fan|heater|tap|club|party)\b")   # the real world, not her


def synonyms(t: str) -> str:
    for spoken, known in SYNONYMS:
        t = re.sub(rf"\b(?:{spoken})\b", known, t)
    return re.sub(r"\s+", " ", t).strip()


def strong(intent: Intent, knows: Callable[[str], bool] | None) -> bool:
    """A clear command (not chat), naming only things she knows."""
    if intent.kind in (Kind.UNKNOWN, Kind.CHAT):
        return False
    if intent.kind in (Kind.OPEN, Kind.CLOSE, Kind.MINIMIZE) and intent.targets and intent.targets != ("this",):
        return knows is not None and all(knows(t) for t in intent.targets)
    if intent.kind in (Kind.ARRANGE, Kind.APP_VOLUME) and any(intent.targets):
        return knows is not None and all(knows(t) for t in intent.targets if t)
    return True


def understand(text: str, knows: Callable[[str], bool] | None = None) -> Intent:
    """What you meant, however you said it. Falls back to the plain parse (UNKNOWN / chat)."""
    if knows is not None:
        seen: dict[str, bool] = {}
        ask = knows
        knows = lambda name: seen[name] if name in seen else seen.setdefault(name, bool(ask(name)))   # noqa: E731
    first = parse(text)
    t = normalise(text)
    if first.kind in (Kind.OPEN, Kind.CLOSE, Kind.MINIMIZE, Kind.UNKNOWN) and (
            re.search(NOT_ABOUT, t) or any(re.search(CHATTY, x) or re.match(r"\w+ing\b", x) for x in first.targets)):
        return Intent(Kind.UNKNOWN, query=t)             # "open the door", "open your mind": chat, not apps
    if strong(first, knows) or first.kind is Kind.CHAT:
        return first
    if first.kind in (Kind.OPEN, Kind.CLOSE) and knows is not None and any(knows(x) for x in first.targets):
        return first                                     # "close discord and photoshop": she says which isn't there
    if not t:
        return first
    swapped = synonyms(t)
    if swapped != t and strong(meant := parse(swapped), knows):
        return meant
    if knows is not None:                                # "take me to youtube", "hop on discord", "get rid of steam"
        from .guess import guess_command
        guessed = guess_command(t, knows)
        if guessed and strong(meant := parse(guessed), knows):
            return meant
    found = _without_extra_words(swapped, knows) or _command_at_the_end(swapped, knows)
    if found is not None:
        return found
    found = _by_ideas(swapped, knows)
    return found if found is not None else first


def _without_extra_words(t: str, knows) -> Intent | None:
    words = t.split()
    if len(words) < 2 or len(words) > MAX_WORDS:
        return None
    most = 3 if len(words) <= 10 else 1
    tries = 0
    for k in range(1, min(most, len(words) - 1) + 1):
        # leave out the filler-ish words first, then any
        options = sorted(combinations(range(len(words)), k),
                         key=lambda drop: sum(words[i] not in FILLERS for i in drop))   # filler-only ones first
        for drop in options:
            if any(words[i] not in FILLERS for i in drop):
                break                                    # only filler words: "shut steam down" never becomes "shut down"
            kept = " ".join(w for i, w in enumerate(words) if i not in drop)
            if len(kept.split()) < 2:
                continue                                 # one word left can mean anything ("i lost my game")
            intent = parse(kept)
            tries += 1
            if strong(intent, knows):
                return intent
            if tries >= MAX_TRIES:
                return None
    return None


COMMAND_WORDS = r"(?:turn|open|close|play|pause|skip|mute|unmute|deafen|leave|join|take|set|stop|shut|restart|lock|" \
                r"minimize|launch|quit|exit|resume|start|put|go|hang)"


def _command_at_the_end(t: str, knows) -> Intent | None:
    """'the music is too loud turn it down': the command after what you were saying."""
    words = t.split()
    for start in range(1, len(words) - 1):
        if re.fullmatch(COMMAND_WORDS, words[start]):
            tail = " ".join(words[start:])
            intent = parse(tail)
            if strong(intent, knows):
                return intent
            found = _without_extra_words(tail, knows)
            if found is not None:
                return found
    return None


def _by_ideas(t: str, knows) -> Intent | None:
    for needs, command in IDEAS:
        if command and all(re.search(rf"\b(?:{n})\b", t) for n in needs):
            intent = parse(command)
            if strong(intent, knows):
                return intent
    m = re.search(r"\btimer\b.*?\b(\d+|one|two|three|four|five|ten|fifteen|twenty|thirty|an?)\s+(seconds?|minutes?|"
                  r"mins?|hours?)\b|\b(\d+|one|two|three|four|five|ten|fifteen|twenty|thirty|an?)\s+(seconds?|minutes?|"
                  r"mins?|hours?)\b.*\btimer\b", t)
    if m:
        amount, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        intent = parse(f"set a timer for {amount} {unit}")
        if intent.kind is Kind.TIMER:
            return intent
    if knows is not None:                                # "discord open it", "go and close spotify for me"
        for verbs, verb in APP_VERBS:
            if not re.search(rf"\b(?:{verbs})\b", t):
                continue
            rest = re.sub(rf"\b(?:{verbs})\b", " ", t)
            names = [w for w in re.split(r"\s+", rest) if w and w not in FILLERS]
            for size in (3, 2, 1):
                for i in range(len(names) - size + 1):
                    name = " ".join(names[i:i + size])
                    if knows(name):
                        return Intent(Kind.OPEN if verb == "open" else Kind.CLOSE, (name,))
    return None
