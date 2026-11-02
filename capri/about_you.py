"""What Capri remembers about you - kept on your PC only.

Things you tell her about yourself ("my name is Sam", "I love Deadlock", "my favourite food is
ramen", "remember that my exam is on Friday") are saved to about_you.json in your own user folder
(%LOCALAPPDATA%\\Capri on Windows) - never in Capri's program folder, the installer or the code.

Personal things stay out of the AI: when an AI chatbot is set up, anything about you (telling
her a fact, asking what she knows about you, "forget ...") is answered by her own chatbot on your
PC instead, and nothing from this file is put in what's sent to the AI - unless you switch on
Settings -> AI -> "Let the AI know what Capri remembers about me". On top of that, `scrub()` takes
your Windows user name and your user-folder paths out of anything that does go to an AI.

"Forget everything about me" asks first, then deletes the file.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("capri")

MAX_ITEMS = 40          # per list - it's a memory, not a diary


def memory_path() -> Path:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    return Path(base) / "about_you.json"


def _norm(text: str) -> str:
    text = re.sub(r"[^\w' ]+", " ", (text or "").lower()).replace("'", " ")
    return re.sub(r"\s+", " ", text).strip()


_THE = r"(?:the |my |a |an )?"
FAV = r"(?:favorite|favourite|fav|fave)"

# What counts as "about you" (kept local, never sent to an AI).
TELL = [
    ("name", r"(?:my name is|my names|my name s|i m called|im called|call me|i am called) (?P<v>\w+(?: \w+)?)"),
    ("favorite", rf"my {FAV} (?P<k>[\w ]+?) (?:is|s|are) (?P<v>.+)"),
    ("likes", r"i (?:really |kinda |also |do )?(?:like|love|enjoy|adore|am into|m into) (?P<v>(?!you\b).+)"),
    ("dislikes", r"i (?:really )?(?:hate|dont like|don t like|do not like|cant stand|can t stand) (?P<v>(?!you\b).+)"),
    ("home", r"(?:i live in|i m from|im from|i am from) (?P<v>.+)"),
    ("birthday", r"my (?:birthday|bday|b day) (?:is|s) (?:on )?(?P<v>.+)"),
    ("age", r"(?:i m|im|i am) (?P<v>\d{1,2})(?: years old| yrs old| year old)?"),
    ("notes", r"(?:remember|don t forget|dont forget) (?:that )?(?P<v>.+)"),
]
ASK = [
    ("name", r"(?:what s|whats|what is|do you (?:know|remember)) my name|who am i"),
    ("likes", r"what do i (?:like|love|enjoy)|do you (?:know|remember) what i like"),
    ("dislikes", r"what do i (?:hate|dislike|not like)"),
    ("home", r"where (?:do i live|am i from)"),
    ("birthday", r"when s my birthday|when is my birthday|whens my birthday|what s my birthday"),
    ("age", r"how old am i"),
    ("favorite", rf"(?:what s|whats|what is|what are) my {FAV} (?P<k>[\w ]+)"),
    ("all", r"what do you (?:know|remember) about me|what have you (?:learned|remembered) about me"
            r"|tell me (?:what you know )?about me|what s in your memory"),
]
FORGET_ALL = r"(?:forget|delete|wipe|erase|clear) (?:everything|all) (?:about me|you know about me|you remember)" \
             r"|(?:wipe|delete|clear|erase) (?:my|your) memory(?: of me)?|forget me"
FORGET_ONE = r"(?:forget|don t remember|stop remembering) (?:that |about )?(?P<v>.+)"
YES = r"(?:yes|yeah|yep|yup|sure|do it|go ahead|ok|okay|confirm|delete it)(?: please)?"


def is_personal(text: str) -> bool:
    """Is this about the user (so it stays on the PC)?"""
    s = _norm(text)
    if not s:
        return False
    if re.fullmatch(FORGET_ALL, s) or re.fullmatch(FORGET_ONE, s):
        return True
    return any(re.fullmatch(p, s) for _k, p in TELL + ASK)


class AboutYou:
    """Your facts, saved as data in your user folder. path=None keeps them in memory only (tests)."""

    def __init__(self, path: Path | None | str = "default") -> None:
        self.path = memory_path() if path == "default" else (Path(path) if path else None)
        self.data: dict = {"name": "", "home": "", "birthday": "", "age": "", "likes": [], "dislikes": [],
                           "favorites": {}, "notes": []}
        self.pending_forget = False
        self._load()

    # -- storage ---------------------------------------------------------------------------------
    def _load(self) -> None:
        if self.path is None:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.warning("about_you: ignoring unreadable %s: %s", self.path, exc)
            return
        if not isinstance(raw, dict):
            return
        for key in ("name", "home", "birthday", "age"):
            if isinstance(raw.get(key), str):
                self.data[key] = raw[key][:80]
        for key in ("likes", "dislikes", "notes"):
            if isinstance(raw.get(key), list):
                self.data[key] = [str(x)[:120] for x in raw[key] if isinstance(x, str)][-MAX_ITEMS:]
        if isinstance(raw.get("favorites"), dict):
            self.data["favorites"] = {str(k)[:40]: str(v)[:80] for k, v in raw["favorites"].items()
                                      if isinstance(v, str)}

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("about_you: couldn't save %s: %s", self.path, exc)

    def forget_all(self) -> None:
        self.data = {"name": "", "home": "", "birthday": "", "age": "", "likes": [], "dislikes": [],
                     "favorites": {}, "notes": []}
        if self.path is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("about_you: couldn't delete %s: %s", self.path, exc)

    # -- facts -------------------------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def likes(self) -> list[str]:
        return self.data["likes"]

    def empty(self) -> bool:
        d = self.data
        return not any((d["name"], d["home"], d["birthday"], d["age"], d["likes"], d["dislikes"],
                        d["favorites"], d["notes"]))

    def _add(self, key: str, value: str) -> None:
        items = self.data[key]
        if value in items:
            items.remove(value)
        items.append(value)
        del items[:-MAX_ITEMS]

    def learn(self, kind: str, value: str, key: str = "") -> None:
        value = value.strip()[:120]
        if not value:
            return
        if kind in ("name", "home", "birthday", "age"):
            self.data[kind] = value.title() if kind in ("name", "home") else value
        elif kind == "favorite":
            self.data["favorites"][key.strip()[:40]] = value
        elif kind in ("likes", "dislikes", "notes"):
            other = {"likes": "dislikes", "dislikes": "likes"}.get(kind)
            if other and value in self.data[other]:
                self.data[other].remove(value)          # changed your mind
            self._add(kind, value)
        self.save()

    def forget(self, thing: str) -> bool:
        """'forget that I like pizza' / 'forget my birthday'. True if something went."""
        t = _norm(thing)
        t = re.sub(r"^(?:that |about )?(?:i (?:like|love|hate|dont like|don t like) |my )", "", t).strip()
        gone = False
        for key in ("likes", "dislikes", "notes"):
            keep = [x for x in self.data[key] if t not in _norm(x)]
            gone |= len(keep) != len(self.data[key])
            self.data[key] = keep
        for key in ("name", "home", "birthday", "age"):
            if self.data[key] and (t == key or t in _norm(self.data[key])):
                self.data[key], gone = "", True
        for k in list(self.data["favorites"]):
            if t in (k, f"favorite {k}", f"favourite {k}") or t in _norm(self.data["favorites"][k]):
                del self.data["favorites"][k]
                gone = True
        if gone:
            self.save()
        return gone

    def summary(self) -> str:
        """A short spoken list of what she knows."""
        d, bits = self.data, []
        if d["name"]:
            bits.append(f"you're {d['name']}")
        if d["age"]:
            bits.append(f"you're {d['age']}")
        if d["home"]:
            bits.append(f"you live in {d['home']}")
        if d["birthday"]:
            bits.append(f"your birthday's {d['birthday']}")
        if d["likes"]:
            bits.append("you like " + " and ".join(d["likes"][-3:]))
        if d["dislikes"]:
            bits.append("you're not into " + " or ".join(d["dislikes"][-2:]))
        for k, v in list(d["favorites"].items())[-2:]:
            bits.append(f"your favourite {k} is {v}")
        if d["notes"]:
            bits.append("and " + d["notes"][-1])
        return ", ".join(bits)

    def for_ai(self) -> str:
        """Only used if you opted in: a line the AI's instructions get."""
        s = self.summary()
        return f"What the user has told you about themselves (kept on their PC): {s}." if s else ""

    # -- conversation ----------------------------------------------------------------------------
    def handle(self, text: str) -> tuple[str, str] | None:
        """(what happened, value) if this was about you, else None. Kinds: told_<kind>, ask_<kind>,
        ask_<kind>_unknown, all / all_empty, forget_ask / forget_done / forget_cancel, forgot / forgot_none."""
        s = _norm(text)
        if self.pending_forget:
            self.pending_forget = False
            if re.fullmatch(YES, s):
                self.forget_all()
                return "forget_done", ""
            if re.fullmatch(r"(?:no|nope|nah|cancel|don t|dont|never mind|nevermind|keep it)(?: .*)?", s):
                return "forget_cancel", ""
        if re.fullmatch(FORGET_ALL, s):
            self.pending_forget = True
            return "forget_ask", ""
        m = re.fullmatch(FORGET_ONE, s)
        if m:
            return ("forgot", m.group("v")) if self.forget(m.group("v")) else ("forgot_none", m.group("v"))
        for kind, pattern in ASK:
            m = re.fullmatch(pattern, s)
            if not m:
                continue
            if kind == "all":
                return ("all", self.summary()) if not self.empty() else ("all_empty", "")
            if kind == "favorite":
                k = m.group("k").strip()
                v = self.data["favorites"].get(k) or self.data["favorites"].get(k.rstrip("s"))
                return ("ask_favorite", f"{k}|{v}") if v else ("ask_favorite_unknown", k)
            value = self.data[kind]
            if isinstance(value, list):
                value = " and ".join(value[-3:])
            return (f"ask_{kind}", value) if value else (f"ask_{kind}_unknown", "")
        for kind, pattern in TELL:
            m = re.fullmatch(pattern, s)
            if not m:
                continue
            value = m.group("v").strip()
            if kind == "favorite":
                self.learn("favorite", value, m.group("k"))
                return "told_favorite", f"{m.group('k').strip()}|{value}"
            self.learn(kind, value)
            return f"told_{kind}", self.data[kind] if kind in ("name", "home") else value
        return None


# -- keeping you out of what goes to an AI -------------------------------------------------------
def _user_names() -> list[str]:
    names = set()
    for var in ("USERNAME", "USER"):
        if os.environ.get(var):
            names.add(os.environ[var])
    try:
        names.add(getpass.getuser())
    except Exception:
        pass
    return [n for n in names if len(n) >= 3 and n.lower() not in ("root", "user", "admin", "administrator")]


def scrub(text: str, names: list[str] | None = None) -> str:
    """Your Windows user name and user-folder paths out of text bound for an AI:
    'C:\\Users\\sam\\Downloads\\cv.pdf' -> 'C:\\Users\\you\\Downloads\\cv.pdf'."""
    if not text:
        return text
    text = re.sub(r"(?i)([a-z]:[\\/]+users[\\/]+)[^\\/\s\"']+", r"\1you", text)
    text = re.sub(r"(/home/|/Users/)[^/\s\"']+", r"\1you", text)
    for n in names if names is not None else _user_names():
        text = re.sub(rf"(?i)\b{re.escape(n)}\b", "you", text)
    return text
