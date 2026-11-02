"""When nothing else matched: work out what you wanted done before treating it as chat.

"throw on spotify", "hop on discord", "take me to youtube", "i need steam" aren't in her command
list, but they name something she can open with a word that means "open it". So she rewrites them
as the plain command ("open spotify") and does that. Only when the name really is one of your apps,
games, sites or folders (a close match), so "go to sleep" or "i need a break" stay chat.

Nothing here runs anything: the rewritten words go through the normal parser and router, same as
if you'd said them that way.
"""

from __future__ import annotations

import re
from typing import Callable

from .parser import split_targets

OPENISH = (r"(?:throw on|put on|pop on|stick on|hop on|hop onto|hop in|jump on|jump onto|jump into|jump in|"
           r"get on|get onto|get into|go on|go onto|go to|go into|head to|take me to|bring me to|"
           r"show me|switch to|swap to|flip to|gimme|give me|get me|i need|i want|i wanna|i wanna use|"
           r"i want to use|i need to use|lemme see|let me see|lemme use|let me use|let s do|lets do|let s hop on|"
           r"lets hop on|time for|i m going on|im going on|i m hopping on|im hopping on)")
CLOSEISH = (r"(?:get rid of|close out(?: of)?|exit out(?: of)?|x out(?: of)?|shut|turn off|kill off|nuke|"
            r"i m done with|im done with|i m done using|im done using|stop running)")
MUSIC = r"(?:some |my |a )?(?:music|tunes|songs|song|a song|something|a banger|bangers|beats)"
MUSICISH = (rf"(?:(?:i (?:wanna|want to|need to|need)|let s|lets|let me|lemme) )?"
            rf"(?:listen to|hear|put on|throw on|pop on|play me|put|throw|pop|bump|blast) {MUSIC}(?: on)?")
LISTEN = r"(?:(?:i (?:wanna|want to)|let s|lets|let me|lemme) )?(?:listen to|put on|throw on|bump|blast) (.+)"
TAIL = r"(?:\s+(?:up|on|real quick|quick|for a bit|for a sec|again|now|rn|for me|please))+$"
BARE_MINIMUM = 0.92        # a name on its own ("spotify") has to be a near-exact match


def guess_command(t: str, known: Callable[[str], bool]) -> str | None:
    """Normalised words that didn't parse -> a plain command that does ("open spotify"), or None.

    known(name) says whether a name is one of your apps / games / sites / folders."""
    t = t.strip()
    if not t:
        return None
    if re.fullmatch(MUSICISH, t):
        return "play music"
    m = re.fullmatch(OPENISH + r"\s+(?:the |my |up )?(.+)", t)
    if m:
        names = _names(m.group(1))
        if names and all(known(n) for n in names):
            return "open " + " and ".join(names)
    m = re.fullmatch(CLOSEISH + r"\s+(?:the |my )?(.+)", t)
    if m:
        names = _names(m.group(1))
        if names and all(known(n) for n in names):
            return "close " + " and ".join(names)
    m = re.fullmatch(LISTEN, t)
    if m:
        names = _names(m.group(1))
        if names and all(known(n) for n in names):
            return "open " + " and ".join(names)                     # "listen to spotify"
        what = re.sub(r"^(?:some|a bit of|a little|my) ", "", re.sub(TAIL, "", m.group(1)).strip())
        return "play " + what                                          # "listen to lofi" = play it
    return None


def guess_bare(t: str, known_exactly: Callable[[str], bool]) -> str | None:
    """Just a name ("spotify", "capri discord") = open it."""
    t = re.sub(TAIL, "", t.strip())
    if t and len(t.split()) <= 3 and known_exactly(t):
        return "open " + t
    return None


def _names(text: str) -> tuple[str, ...]:
    return tuple(n for n in (re.sub(TAIL, "", part).strip() for part in split_targets(re.sub(TAIL, "", text))) if n)
