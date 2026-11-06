"""2.3.4 commands: quiet mode, reminders at a time or on a day, rock paper scissors.

All matched on the normalised words (lower case, no punctuation: "9:30 p.m." arrives as "9 30 p m").
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# -- quiet mode: she stops commenting by herself (she still answers you) -----------------------------------
QUIET_ON = (r"(?:turn on |switch on |enable |start |go (?:in|into|in to) |use )?(?:the |your )?quiet mode(?: on| please)?"
            r"|(?:stop|quit|no more) (?:commenting|making comments|checking in|pop ?ins?)"
            r"(?: for (?:a while|now|a bit))?"
            r"|(?:don t|dont|do not) (?:bother|disturb|interrupt) me(?: for (?:a while|now|a bit))?"
            r"|leave me alone(?: for (?:a while|now|a bit))?|i need to (?:focus|concentrate)")
QUIET_OFF = (r"(?:turn off |switch off |disable |stop |end |leave |exit )(?:the |your )?quiet mode|quiet mode off"
             r"|(?:you can )?(?:talk|comment|chat) again|(?:start|go back to) (?:commenting|talking) again")


def quiet_mode_intent(t: str) -> str:
    """"on" / "off" / ""."""
    if re.fullmatch(QUIET_OFF, t):
        return "off"
    if re.fullmatch(QUIET_ON, t):
        return "on"
    return ""


# -- reminders at a time / on a day ("remind me tomorrow at 9 to call mum") ---------------------------------
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
               "oct": 10, "nov": 11, "dec": 12})
DAYS = {d: i for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY = "|".join(DAYS)
_NTH = r"(\d{1,2})(?:st|nd|rd|th)?"
_HALF = r"(am|pm|a m|p m|in the morning|in the afternoon|in the evening|at night|tonight)"
TIME = rf"(?:at )?(\d{{1,2}})(?:(?: |:)(\d{{2}}))? ?{_HALF}?|at noon|at midnight|noon|midnight"
DAY = (rf"today|tonight|tomorrow(?: morning| afternoon| evening| night)?|the day after tomorrow"
       rf"|(?:on |this |next )?(?:{_DAY})|(?:on )?(?:the )?{_NTH} (?:of )?(?:{_MONTH})|(?:on )?(?:{_MONTH}) (?:the )?{_NTH}")
WHEN = rf"(?:(?P<day>{DAY})(?: at)? ?(?P<time>{TIME})?|(?P<time2>{TIME})(?: (?P<day2>{DAY}))?)"
REMIND = [rf"remind me (?:to |about |that )?(?P<what>.+?) {WHEN}",
          rf"remind me {WHEN} (?:to |about |that )?(?P<what>.+)"]


def reminder_intent(t: str) -> tuple[str, str] | None:
    """("<day>|<time>", what) - when is resolved later (when_due), against the clock then."""
    for pattern in REMIND:
        m = re.fullmatch(pattern, t)
        if not m:
            continue
        day = (m.group("day") or m.group("day2") or "").strip()
        when = (m.group("time") or m.group("time2") or "").strip()
        what = m.group("what").strip()
        if not (day or when) or not what or re.fullmatch(r"\d+ (?:seconds?|minutes?|hours?)", what):
            continue
        if when and not day and not re.search(r"\d|noon|midnight", when):
            continue
        return f"{day}|{when}", what
    return None


def _clock(spec: str, day_hint: str) -> tuple[int, int] | None:
    """'9' / '9 30 pm' / 'at noon' -> (hour, minute); None if there's no time."""
    spec = spec.replace("at ", "").strip()
    if not spec:
        return None
    if spec == "noon":
        return 12, 0
    if spec == "midnight":
        return 0, 0
    m = re.fullmatch(rf"(\d{{1,2}})(?:(?: |:)(\d{{2}}))? ?{_HALF}?", spec)
    if not m:
        return None
    h, mi, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(" ", "")
    later = half in ("pm", "intheafternoon", "intheevening", "atnight", "tonight") or \
        any(w in day_hint for w in ("evening", "night", "tonight", "afternoon"))
    if later and h < 12:
        h += 12
    if half in ("am", "inthemorning") and h == 12:
        h = 0
    if not half and not later and 1 <= h <= 6:
        h += 12                                   # "at 5" means 5 pm: nobody sets 5 am reminders by accident
    return (h, mi) if 0 <= h < 24 and 0 <= mi < 60 else None


def when_due(spec: str, now: datetime) -> datetime | None:
    """'tomorrow|9 30 am' -> the datetime it means (the next one after `now`)."""
    day, _, clock_words = spec.partition("|")
    day = day.strip()
    clock = _clock(clock_words, day)
    base = now.replace(second=0, microsecond=0)
    if not day:                                   # just a time: the next time it's that time
        if clock is None:
            return None
        due = base.replace(hour=clock[0], minute=clock[1])
        return due if due > now else due + timedelta(days=1)
    if clock is None:
        clock = (20, 0) if "night" in day or "evening" in day else (15, 0) if "afternoon" in day else (9, 0)
    if day in ("today", "tonight"):
        date = base
    elif day.startswith("tomorrow"):
        date = base + timedelta(days=1)
    elif day == "the day after tomorrow":
        date = base + timedelta(days=2)
    else:
        name = day.split()[-1]
        if name in DAYS:
            ahead = (DAYS[name] - base.weekday()) % 7
            if ahead == 0 or day.startswith("next"):
                ahead = ahead or 7
            date = base + timedelta(days=ahead)
        else:
            m = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)?", day)
            month = next((MONTHS[w] for w in day.split() if w in MONTHS), None)
            if not m or month is None:
                return None
            try:
                date = base.replace(month=month, day=int(m.group(1)))
            except ValueError:
                return None
            if date.replace(hour=clock[0], minute=clock[1]) <= now:
                try:
                    date = date.replace(year=date.year + 1)
                except ValueError:
                    return None
    due = date.replace(hour=clock[0], minute=clock[1])
    return due if due > now else None


def spoken_when(due: datetime, now: datetime) -> str:
    """'at 9:30 pm' / 'tomorrow at 9 am' / 'on Friday 5 December at 9 am'."""
    h = due.hour % 12 or 12
    clock = f"{h}{':%02d' % due.minute if due.minute else ''} {'am' if due.hour < 12 else 'pm'}"
    days = (due.date() - now.date()).days
    if days == 0:
        return f"at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    if days < 7:
        return f"on {due.strftime('%A')} at {clock}"
    return f"on {due.strftime('%A')} {due.day} {due.strftime('%B')} at {clock}"


# -- rock paper scissors -------------------------------------------------------------------------------------
HANDS = ("rock", "paper", "scissors")
RPS_START = (r"(?:(?:let s|lets|can we|wanna|want to|do you want to) )?(?:play )?(?:a (?:game|round) of )?"
             r"rock paper scissors(?: with me)?(?: please)?|play (?:a game )?with me")
RPS_PICK = r"(?:(?:i (?:pick|choose|go|play|throw|say)|i ll (?:pick|go|play|throw)|my pick is) )?(rock|paper|scissors?)"
RPS_WITH_PICK = rf"rock paper scissors (?:i (?:pick|choose|go|play|throw) )?(rock|paper|scissors?)"


def rps_intent(t: str) -> str:
    """"start" / "rock" / "paper" / "scissors" / ""."""
    m = re.fullmatch(RPS_WITH_PICK, t)
    if m:
        return _hand(m.group(1))
    if re.fullmatch(RPS_START, t):
        return "start"
    m = re.fullmatch(RPS_PICK, t)
    return _hand(m.group(1)) if m else ""


def _hand(word: str) -> str:
    return "scissors" if word.startswith("scissor") else word


def rps_winner(you: str, her: str) -> str:
    """"you" / "her" / "draw"."""
    if you == her:
        return "draw"
    beats = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    return "you" if beats[you] == her else "her"
