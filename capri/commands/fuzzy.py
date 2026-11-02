"""Matching what Vosk heard to app names, by how they *sound*.

Speech recognition only knows dictionary words, so "Bloxstrap" arrives as
"blocks strap" and "Counter-Strike 2" as "counter strike two". Both sides are
reduced to a rough phonetic key before comparing:

    "Bloxstrap"     -> blokstrap
    "blocks strap"  -> blokstrap
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    return " ".join(ONES[int(d)] for d in str(n))   # 2077 -> "two zero seven seven"


def spell_numbers(text: str) -> str:
    return re.sub(r"\d+", lambda m: " " + number_words(int(m.group())) + " ", text)


# Order matters: multi-letter sounds first.
SOUNDS = [
    ("tion", "shun"), ("ph", "f"), ("ck", "k"), ("qu", "kw"), ("x", "ks"), ("wh", "w"),
    ("c", "k"), ("q", "k"), ("z", "s"), ("y", "i"), ("ee", "i"), ("oo", "u"), ("ou", "u"),
]


def sound_key(text: str) -> str:
    """Rough phonetic key: letters only, sound-alike spellings merged, no doubles."""
    t = spell_numbers(text.lower())
    t = re.sub(r"[^a-z]", "", t)
    for a, b in SOUNDS:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)        # "blokssstrap" -> "blokstrap"
    t = re.sub(r"(?<=.)[e]$", "", t)       # silent trailing e
    return t


def similarity(spoken: str, name: str) -> float:
    a, b = sound_key(spoken), sound_key(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # "opera" for "Opera GX", "minecraft" for "Minecraft Launcher": a whole-word prefix.
    spoken_words, name_words = spoken.lower().split(), re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    n = len(spoken_words)
    if spoken_words and name_words[:n] == spoken_words:
        ratio = max(ratio, 0.86)
    elif spoken_words and any(name_words[i:i + n] == spoken_words for i in range(len(name_words))):
        ratio = max(ratio, 0.84)   # "chrome" in "Google Chrome"
    elif b.startswith(a) and len(a) >= 4:
        ratio = max(ratio, 0.8)
    return ratio
