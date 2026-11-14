"""mod.json - what a mod is, and every check a mod has to pass before Capri uses it.

    {
      "id": "neon-ice",                     lower case letters, digits, - _ . (2-40)
      "name": "Neon Ice",
      "version": "1.0.0",
      "author": "you",
      "description": "Ice-blue hair and cyan chrome.",
      "type": "skin",                       one of TYPES
      "category": "Skins",                  optional (defaults from the type)
      "tags": ["blue", "cold"],
      "capri": ">=2.4.0",                   the Capri versions it works with (">=x.y.z", "<x.y.z", both: ">=a,<b")
      "preview": "preview.png",             a picture for the store / mods list (optional)
      "conflicts": ["other-mod-id"],        mods it can't be on together with (optional)
      ...type-specific fields, below...
    }

Types and their fields:
    skin          "palette": {"hair": "#rrggbb", "accent": "#rrggbb", "outline": "#rrggbb", "body": "#rrggbb",
                               "eyes": "#rrggbb"}                       (her colours; any subset)
    cosmetic      "items": [{"image": "ears.png", "slot": "ears|hair|hat|face|neck|back|other",
                             "x": 0.5, "y": -0.1, "width": 1.2, "layer": "front|back"}]
                  (x / y: where its middle goes, in head widths / heights from the head's top-left;
                   width: in head widths). Stackable: several cosmetics at once, one per slot.
    animations    "animations": [{"name": "Hip sway", "seconds": 4, "loop": 2,
                                  "keys": [{"t": 0, "lean": 0.0}, {"t": 0.5, "lean": 0.12, "eyes": "happy"}, ...]}]
                  (pose fields: lean, reach, sweep, squat, wave, wag, stride, blink, mouth, energy;
                   eyes: "", "happy", "wink")
    personality   "personality": {"key": "noir", "label": "Noir", "prompt": "...", "remarks": [...],
                                  "chance": 0.3, "intro": "...", "emotion": "smirk"}
    behaviour     "settings": {"roaming": true, "glitches": 120, ...}  (only the keys in BEHAVIOUR_KEYS)
    lines         "lines": {"greet": [...], "pat": [...], "poke": [...], "ouch": [...], "done": [...],
                            "hello": [...], "bye": [...]}
    sounds        "sounds": {"wake": "wake.wav", "done": "done.wav", "error": "err.wav", "pat": "pat.wav",
                             "throw": "throw.wav", "greet": "hi.wav", "click": "click.wav"}  (16-bit PCM WAV)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .. import __version__

TYPES = ("skin", "cosmetic", "animations", "personality", "behaviour", "lines", "sounds", "look")
CATEGORY = {"skin": "Skins & outfits", "cosmetic": "Hair & accessories", "animations": "Animations & expressions",
            "personality": "Personalities", "behaviour": "Behaviour", "lines": "Greetings & reactions",
            "sounds": "Sound packs", "look": "Looks & models"}
SLOTS = ("ears", "hair", "hat", "face", "neck", "back", "other")
LINE_KEYS = ("greet", "pat", "poke", "ouch", "done", "hello", "bye")
SOUND_EVENTS = ("wake", "done", "error", "pat", "throw", "greet", "click")
POSE_FIELDS = ("lean", "reach", "sweep", "squat", "wave", "wag", "stride", "blink", "mouth", "energy")
# The settings a behaviour mod may change: her habits only - never your files, keys, privacy or anything risky
BEHAVIOUR_KEYS = {"roaming": bool, "idle_acts": bool, "idle_animation": bool, "glitches": int, "throwable": bool,
                  "head_pats": bool, "music_dance": bool, "slang": bool, "speech_expression": float,
                  "speech_speed": float, "speech_pitch": float, "speech_style": str, "nap_minutes": int,
                  "watch_every": int, "game_hype_encourage": bool}
# (2.4.1) The settings a look mod may change: which of her models / styles she uses - and the allowed values
LOOK_KEYS = {"body_style": ("flat", "full", "neon"), "lounge": (True, False), "character_style": ("body", "portrait",
             "classic"), "hair_style": ("storm", "classic"), "drone_look": ("disk", "mask"),
             "perch_windows": (True, False), "chat_skin": ("holocall", "netrunner", "arasaka", "neon", "braindance")}
FILE_TYPES = {".png": 2_000_000, ".jpg": 2_000_000, ".jpeg": 2_000_000, ".webp": 2_000_000, ".wav": 3_000_000,
              ".json": 200_000, ".txt": 100_000, ".md": 100_000}
MAX_FILES = 60
MAX_TOTAL = 20_000_000
ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
VERSION = re.compile(r"^\d+(?:\.\d+){0,3}$")


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:4]) or (0,)


def fits(spec: str, version: str = __version__) -> bool:
    """Does `version` satisfy ">=2.4.0" / "<3" / ">=2.4,<3" / "2.4.0" / "" (any)?"""
    v = parse_version(version)
    for part in [p.strip() for p in (spec or "").split(",") if p.strip()]:
        m = re.fullmatch(r"(>=|<=|>|<|==|=)?\s*(\d+(?:\.\d+){0,3})", part)
        if not m:
            return False
        op, want = m.group(1) or "==", parse_version(m.group(2))
        width = max(len(v), len(want))
        a, b = v + (0,) * (width - len(v)), want + (0,) * (width - len(want))
        if not {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b, "==": a == b, "=": a == b}[op]:
            return False
    return True


@dataclass
class Manifest:
    id: str
    name: str
    version: str
    type: str
    author: str = ""
    description: str = ""
    category: str = ""
    tags: list = field(default_factory=list)
    capri: str = ""
    preview: str = ""
    conflicts: list = field(default_factory=list)
    data: dict = field(default_factory=dict)          # the whole mod.json

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}"


class ModError(ValueError):
    """A mod that isn't right - the message says what, in plain words."""


def _need(cond: bool, problem: str) -> None:
    if not cond:
        raise ModError(problem)


def check(data: dict, files: dict[str, int] | None = None) -> Manifest:
    """Every check a mod.json has to pass (and its files, {name: size}, when given). Raises ModError."""
    _need(isinstance(data, dict), "mod.json isn't a JSON object")
    mod_id = str(data.get("id", ""))
    _need(bool(ID.match(mod_id)), "its id must be 2-40 lower-case letters, digits, - _ or .")
    name = str(data.get("name", "")).strip()
    _need(0 < len(name) <= 60, "it needs a name (up to 60 characters)")
    version = str(data.get("version", "")).strip()
    _need(bool(VERSION.match(version)), "its version must look like 1.0 or 1.0.0")
    kind = str(data.get("type", ""))
    _need(kind in TYPES, f"its type must be one of: {', '.join(TYPES)}")
    capri = str(data.get("capri", "") or "")
    if capri:
        _need(bool(re.fullmatch(r"\s*(?:(?:>=|<=|>|<|==|=)?\s*\d+(?:\.\d+){0,3}\s*,?\s*)+", capri)),
              "its \"capri\" versions must look like >=2.4.0 or >=2.4,<3")
    checking = files is not None                      # None: the files aren't known (only the JSON is checked)
    files = files or {}
    present = set(files)

    def has(path: str, what: str) -> None:
        _need(isinstance(path, str) and path in present, f"{what} \"{path}\" isn't in the mod")

    if kind == "skin":
        palette = data.get("palette")
        _need(isinstance(palette, dict) and palette, "a skin needs a \"palette\" of colours")
        for part, colour in palette.items():
            _need(part in ("hair", "accent", "outline", "body", "eyes"), f"unknown palette part \"{part}\"")
            _need(isinstance(colour, str) and bool(COLOR.match(colour)), f"\"{part}\" must be a colour like #ff2266")
    elif kind == "cosmetic":
        items = data.get("items")
        _need(isinstance(items, list) and 0 < len(items) <= 6, "a cosmetic needs 1-6 \"items\"")
        for item in items:
            _need(isinstance(item, dict), "each item must be an object")
            if checking:
                has(item.get("image", ""), "picture")
            _need(item.get("slot", "other") in SLOTS, f"a cosmetic's slot must be one of: {', '.join(SLOTS)}")
            for k, lo, hi in (("x", -2.0, 3.0), ("y", -3.0, 3.0), ("width", 0.05, 4.0)):
                v = item.get(k, 0.5 if k != "width" else 1.0)
                _need(isinstance(v, (int, float)) and lo <= float(v) <= hi, f"a cosmetic's {k} is out of range")
            _need(item.get("layer", "front") in ("front", "back"), "a cosmetic's layer must be front or back")
    elif kind == "animations":
        anims = data.get("animations")
        _need(isinstance(anims, list) and 0 < len(anims) <= 20, "an animation pack needs 1-20 \"animations\"")
        for a in anims:
            _need(isinstance(a, dict) and str(a.get("name", "")).strip(), "each animation needs a name")
            secs = a.get("seconds", 3)
            _need(isinstance(secs, (int, float)) and 0.3 <= secs <= 20, "an animation lasts 0.3-20 seconds")
            keys = a.get("keys")
            _need(isinstance(keys, list) and 2 <= len(keys) <= 60, "an animation needs 2-60 \"keys\"")
            for key in keys:
                _need(isinstance(key, dict) and isinstance(key.get("t"), (int, float)) and 0 <= key["t"] <= 1,
                      "each key needs a time \"t\" from 0 to 1")
                for f, v in key.items():
                    if f in ("t",):
                        continue
                    if f == "eyes":
                        _need(v in ("", "happy", "wink"), "eyes must be \"\", \"happy\" or \"wink\"")
                        continue
                    _need(f in POSE_FIELDS, f"unknown pose field \"{f}\"")
                    _need(isinstance(v, (int, float)) and -1.5 <= float(v) <= 1.5, f"\"{f}\" must be -1.5 to 1.5")
    elif kind == "personality":
        p = data.get("personality")
        _need(isinstance(p, dict), "a personality mod needs a \"personality\" object")
        _need(bool(ID.match(str(p.get("key", "")))), "its personality key must be a short id")
        _need(0 < len(str(p.get("label", ""))) <= 40, "its personality needs a label")
        _need(20 <= len(str(p.get("prompt", ""))) <= 1200, "its personality prompt must be 20-1200 characters")
        _need(isinstance(p.get("remarks", []), list) and len(p.get("remarks", [])) <= 40, "up to 40 remarks")
    elif kind == "behaviour":
        settings = data.get("settings")
        _need(isinstance(settings, dict) and settings, "a behaviour mod needs \"settings\"")
        for k, v in settings.items():
            _need(k in BEHAVIOUR_KEYS, f"a behaviour mod can't change \"{k}\"")
            want = BEHAVIOUR_KEYS[k]
            ok = isinstance(v, want) if want is not float else isinstance(v, (int, float))
            _need(ok and not (want is int and isinstance(v, bool)), f"\"{k}\" has the wrong kind of value")
    elif kind == "look":
        settings = data.get("settings")
        _need(isinstance(settings, dict) and settings, "a look mod needs \"settings\"")
        for k, v in settings.items():
            _need(k in LOOK_KEYS, f"a look mod can't change \"{k}\"")
            _need(any(v == a and type(v) is type(a) for a in LOOK_KEYS[k]),
                  f"\"{k}\" must be one of: {', '.join(str(a) for a in LOOK_KEYS[k])}")
    elif kind == "lines":
        lines = data.get("lines")
        _need(isinstance(lines, dict) and lines, "a lines pack needs \"lines\"")
        for k, v in lines.items():
            _need(k in LINE_KEYS, f"unknown line kind \"{k}\" (use: {', '.join(LINE_KEYS)})")
            _need(isinstance(v, list) and 0 < len(v) <= 80 and all(isinstance(x, str) and 0 < len(x) <= 200
                                                                  for x in v),
                  f"\"{k}\" must be a list of 1-80 short lines")
    elif kind == "sounds":
        sounds = data.get("sounds")
        _need(isinstance(sounds, dict) and sounds, "a sound pack needs \"sounds\"")
        for event, path in sounds.items():
            _need(event in SOUND_EVENTS, f"unknown sound event \"{event}\" (use: {', '.join(SOUND_EVENTS)})")
            _need(str(path).lower().endswith(".wav"), "sounds must be .wav files")
            if checking:
                has(path, "sound")
    if data.get("preview") and checking:
        has(data["preview"], "preview picture")
    conflicts = data.get("conflicts", [])
    _need(isinstance(conflicts, list) and all(isinstance(c, str) for c in conflicts), "conflicts must be a list of ids")
    if checking:
        _need(len(files) <= MAX_FILES, f"a mod can have at most {MAX_FILES} files")
        _need(sum(files.values()) <= MAX_TOTAL, "a mod can be at most 20 MB")
        for path, size in files.items():
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
            _need(ext in FILE_TYPES, f"\"{path}\": mods can only hold pictures, .wav sounds and text "
                                     f"(no programs or scripts)")
            _need(size <= FILE_TYPES[ext], f"\"{path}\" is too big")
    return Manifest(id=mod_id, name=name, version=version, type=kind, author=str(data.get("author", ""))[:60],
                    description=str(data.get("description", ""))[:400],
                    category=str(data.get("category") or CATEGORY[kind])[:40],
                    tags=[str(t)[:20] for t in data.get("tags", [])][:8] if isinstance(data.get("tags"), list) else [],
                    capri=capri, preview=str(data.get("preview", "")), conflicts=list(conflicts), data=data)


def load(text: str, files: dict[str, int] | None = None) -> Manifest:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ModError(f"mod.json isn't valid JSON ({exc})") from None
    return check(data, files)


def safe_path(name: str) -> bool:
    """A file name inside a mod that can't escape its folder ("../x", "C:/x", "/x" are refused)."""
    if not name or name.startswith(("/", "\\")) or ":" in name or "\\" in name:
        return False
    return all(part not in ("", ".", "..") for part in name.split("/"))
