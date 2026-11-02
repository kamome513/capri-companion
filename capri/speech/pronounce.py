"""Saying Night City slang right.

TTS voices don't know street words: "choom" comes out as "chum". For Windows
(SAPI) voices we hand over the exact phonemes; for other engines a respelling
that they read correctly.

    choom = "ch-oo-m", rhymes with "room"   (SAPI phonemes: ch uw m)
    preem = "preem", one smooth syllable like the end of "supreme" (SAPI phonemes: p r iy m, a bit slower)
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

# word: (respelling for espeak-based engines - her neural voice, SAPI American-English phonemes)
# "choom" reads right as it is there (tʃuːm); "chewm" came out as "chom" on other voices.
WORDS = {
    "choom": ("choom", "ch uw 1 m"),
    "chooms": ("chooms", "ch uw 1 m z"),
    "preem": ("preme", "p r iy 1 m"),           # one syllable: "preeem" was read "pree-um" (two)
    "gonk": ("gonk", "g aa 1 ng k"),
    "eddies": ("eddies", "eh 1 d iy z"),
    "corpo": ("corpo", "k ao 1 r p ow"),
    "hmph": ("humph", "hh ah 1 m f"),           # tsundere's "Hmph!" - the sound, not "H M P H"
    "hmf": ("humph", "hh ah 1 m f"),
    "tch": ("tsk", "t s k"),                    # "Tch." - a click, not "T C H"
}
# Voices that read plain English with no phoneme help (ElevenLabs, a Windows voice that rejects phonemes):
# a long "oo" they can't shorten to "chom".
PLAIN = {"choom": "chooom", "chooms": "chooomz"}
SLOW = {"preem": -2}       # SAPI <rate speed>: a little drawn out, still one syllable
PATTERN = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.IGNORECASE)


# Stutters ("I-it's", "W-what?!", "D-don't", "B-baka") are sounded out: the first sound, a tiny
# pause, then the word - like a real stammer, not a letter read out or a dash skipped.
STUTTER = re.compile(r"\b([A-Za-z]{1,2})-(?=([A-Za-z][A-Za-z']*))")
ONSETS = {   # first sound: (respelling, SAPI phonemes)
    "wh": ("wuh", "w ah"), "th": ("thuh", "dh ah"), "sh": ("shh", "sh"), "ch": ("chuh", "ch ah"),
    "ph": ("fuh", "f ah"), "b": ("buh", "b ah"), "c": ("kuh", "k ah"), "d": ("duh", "d ah"), "f": ("fuh", "f ah"),
    "g": ("guh", "g ah"), "h": ("huh", "hh ah"), "j": ("juh", "jh ah"), "k": ("kuh", "k ah"), "l": ("luh", "l ah"),
    "m": ("mm", "m"), "n": ("nn", "n"), "p": ("puh", "p ah"), "q": ("kuh", "k ah"), "r": ("ruh", "r ah"),
    "s": ("sss", "s"), "t": ("tuh", "t ah"), "v": ("vuh", "v ah"), "w": ("wuh", "w ah"), "x": ("eks", "eh k s"),
    "y": ("yuh", "y ah"), "z": ("zuh", "z ah"),
    "a": ("ah", "ae"), "e": ("eh", "eh"), "i": ("ih", "ih"), "o": ("oh", "ow"), "u": ("uh", "ah"),
}
PAUSE_MS = 140


def _onset(word: str) -> tuple[str, str]:
    w = word.lower()
    if w in ("i", "i'm", "i'll", "i've", "i'd") or w.startswith("i'"):
        return ("eye", "ay")                                  # "I-I'm" stammers on "I"
    return ONSETS.get(w[:2]) or ONSETS.get(w[:1]) or ("uh", "ah")


def _stutters(text: str):
    """(start, end, word after it) for each real stutter: "W-what", not "e-mail" or "T-shirt"."""
    for m in STUTTER.finditer(text):
        head, word = m.group(1), m.group(2)
        if word.lower().startswith(head.lower()) and len(word) > len(head):
            yield m.start(), m.end(), word


def sound_out(text: str) -> str:
    """Stutters as sounds with a pause: "W-what?!" -> "Wuh... what?!" (for voices without SAPI)."""
    out, last = [], 0
    for start, end, word in _stutters(text):
        sound = _onset(word)[0]
        out.append(text[last:start])
        out.append((sound.capitalize() if text[start].isupper() else sound) + "... ")
        last = end
    out.append(text[last:])
    return "".join(out)


def respell(text: str, plain: bool = False) -> str:
    """Plain-text version for engines that can't take phonemes (stutters sounded out too).
    plain: for voices that read English letters as they are (ElevenLabs...), not espeak's rules."""
    def sub(m: re.Match) -> str:
        key = m.group(1).lower()
        word = PLAIN.get(key, WORDS[key][0]) if plain else WORDS[key][0]
        return word.capitalize() if m.group(1)[0].isupper() else word
    return PATTERN.sub(sub, sound_out(text))


def sapi_xml(text: str) -> str:
    """Escaped SAPI XML with exact pronunciations for the slang words, and stutters sounded out."""
    marks = [(start, end, "stutter", word) for start, end, word in _stutters(text)]
    marks += [(m.start(), m.end(), "slang", m.group(1).lower()) for m in PATTERN.finditer(text)]
    out, last = [], 0
    for start, end, kind, word in sorted(marks):
        if start < last:
            continue
        out.append(escape(text[last:start]))
        if kind == "stutter":
            out.append(f'<pron sym="{_onset(word)[1]}"/><silence msec="{PAUSE_MS}"/>')
        else:
            pron = f'<pron sym="{WORDS[word][1]}"/>'
            out.append(f'<rate speed="{SLOW[word]}">{pron}</rate>' if word in SLOW else pron)
        last = end
    out.append(escape(text[last:]))
    return "".join(out)
