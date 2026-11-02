"""Teaching her your voice (Settings -> Hearing -> Teach her your voice).

You say "Hey Capri" a few times. For each one the wake word check reports how sure it was that it heard
"capri", and the full recogniser what it made of it. From that she picks her wake-word threshold for
*your* voice and mic (a bit below your quietest "Capri", so you always wake her - the second listen keeps
the false wake-ups out), and remembers the ways it hears you say her name that don't already sound like
"capri" to her ("cap free"), so those count too. Nothing is recorded or kept but those few words.
"""

from __future__ import annotations

from .wakeword import VERIFY_RELAX, sounds_like_capri

SAMPLES = 4
MIN_THRESHOLD, MAX_THRESHOLD = 0.55, 0.95
FILLER = {"hey", "hay", "a", "uh", "um", "oh", "hi", "the"}


def learn(samples: list[tuple[float, str]], known: list[str] | None = None) -> tuple[float | None, list[str], str]:
    """samples: (confidence it was "capri", what the full recogniser heard) for each try.
    -> (new threshold or None to keep yours, ways she hears you to remember, what to tell you)."""
    if not samples:
        return None, list(known or []), "I didn't hear anything. Check your microphone (and that it isn't muted)."
    caught = [c for c, _ in samples if c > 0]
    variants = list(known or [])
    for _, said in samples:
        first = said.split("|")[0].split()
        words = [w for w in first if w not in FILLER][:2]
        phrase = " ".join(words)
        if phrase and not sounds_like_capri(said) and phrase not in variants:
            variants.append(phrase)                       # how your voice comes through: counts as her name now
    variants = variants[-12:]
    if not caught:
        return None, variants, ("I never heard “Capri” - check that the right microphone is picked in "
                                "Settings, then try again a little closer to it.")
    threshold = round(min(MAX_THRESHOLD, max(MIN_THRESHOLD, min(caught) - 0.05 + VERIFY_RELAX)), 2)
    note = f"Got it. I'll wake up at {round(threshold * 100)}% sure, tuned to your voice"
    if len(caught) < len(samples):
        note += f" (I only caught “Capri” {len(caught)} of {len(samples)} times - say it once more if I miss you)"
    if len(variants) > len(known or []):
        note += ", and I know how your mic makes my name sound now"
    return threshold, variants, note + "."
