"""What the enabled mods change - one place the rest of Capri reads from (mods.effects.EFFECTS).

* palette      her colours (skin mods): her figure is recoloured, and her storm hair
* cosmetics    pictures on her (ears, hats, glasses...), one per slot, stacked in the order you turned them on
* animations   extra moves she does by herself now and then, or when you ask ("do the hip sway")
* personalities extra personalities in her list
* lines        extra greetings, pat / poke / ouch reactions, "done" lines
* sounds       sound effects for her events
* behaviour    her habits (a behaviour mod's settings; your own values come back when you turn it off)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("capri")


@dataclass
class Cosmetic:
    image_path: Path
    slot: str
    x: float
    y: float
    width: float
    layer: str
    mod: str
    _image: object = None

    def image(self):
        """The picture in her current colours (a skin mod recolours cosmetics too, so they match her - 2.4.1)."""
        gen = EFFECTS.generation
        if self._image is None or getattr(self, "_gen", None) != gen:
            from PySide6.QtGui import QImage
            self._image = recolor(QImage(str(self.image_path)), EFFECTS.palette)
            self._gen = gen
        return self._image


@dataclass
class Effects:
    palette: dict = field(default_factory=dict)
    cosmetics: list = field(default_factory=list)
    animations: list = field(default_factory=list)
    lines: dict = field(default_factory=dict)
    sounds: dict = field(default_factory=dict)
    personalities: list = field(default_factory=list)
    style: dict = field(default_factory=dict)  # (2.6) the skin's "style": aura, particles, hair, materials, events...
    style_id: str = ""
    generation: int = 0                      # bumped on every reload (windows redraw / re-cut her figure)

    def line(self, kind: str, rng: random.Random | None = None) -> str | None:
        options = self.lines.get(kind)
        return (rng or random).choice(options) if options else None

    def mix(self, kind: str, own: list[str]) -> list[str]:
        """Her own lines for something, plus the enabled packs' ones."""
        return list(own) + list(self.lines.get(kind, []))


EFFECTS = Effects()
_MOD_PERSONALITIES: set[str] = set()


def reload(manager) -> Effects:
    """Read the enabled mods again (after anything changes) and apply what they change."""
    e = Effects(generation=EFFECTS.generation + 1)
    slots: dict[str, Cosmetic] = {}
    for mod in manager.enabled():
        m, data = mod.manifest, mod.manifest.data
        if m.type == "skin":
            e.palette = dict(data.get("palette", {}))
            e.style = dict(data.get("style") or {})              # (2.6) a style: effects round her too
            e.style_id = m.id
        elif m.type == "cosmetic":
            for item in data.get("items", []):
                c = Cosmetic(mod.folder / item["image"], item.get("slot", "other"), float(item.get("x", 0.5)),
                             float(item.get("y", 0.0)), float(item.get("width", 1.0)), item.get("layer", "front"), m.id)
                key = c.slot if c.slot != "other" else f"other:{m.id}:{item['image']}"
                slots[key] = c                                   # one per slot: the newest wins
        elif m.type == "animations":
            for a in data.get("animations", []):
                e.animations.append({"name": str(a["name"]), "seconds": float(a.get("seconds", 3)),
                                     "loop": max(1, min(6, int(a.get("loop", 1)))), "keys": sorted(
                                         a["keys"], key=lambda k: k["t"]), "mod": m.id})
        elif m.type == "personality":
            e.personalities.append(dict(data["personality"]))
        elif m.type == "lines":
            for kind, items in data.get("lines", {}).items():
                e.lines.setdefault(kind, []).extend(items)
        elif m.type == "sounds":
            for event, path in data.get("sounds", {}).items():
                e.sounds[event] = mod.folder / path
    e.cosmetics = list(slots.values())
    _apply_personalities(e.personalities)
    _apply_hair(e.palette, e.style)
    EFFECTS.__dict__.update(e.__dict__)
    return EFFECTS


def _apply_personalities(items: list[dict]) -> None:
    from .. import personality
    for key in list(_MOD_PERSONALITIES):
        personality.PERSONALITIES.pop(key, None)
    _MOD_PERSONALITIES.clear()
    for p in items:
        key = str(p["key"])
        if key in personality.PERSONALITIES:                 # never replaces one of hers
            continue
        personality.PERSONALITIES[key] = personality.Personality(
            key, str(p["label"])[:40] + " (mod)", str(p["prompt"]),
            tuple(str(r) for r in p.get("remarks", []))[:40], chance=float(p.get("chance", 0.3)),
            emotion=str(p.get("emotion", "")), intro=str(p.get("intro", "")))
        _MOD_PERSONALITIES.add(key)


def _apply_hair(palette: dict, style: dict | None = None) -> None:
    try:
        from PySide6.QtGui import QColor
        from ..ui import hair
        two, sparkle = (style or {}).get("hair2"), (style or {}).get("sparkle")
        hair.set_hair_colour(QColor(palette["hair"]) if palette.get("hair") else None,
                             QColor(two) if two else None, QColor(sparkle) if sparkle else None)
    except Exception:
        log.info("mods: couldn't recolour her hair", exc_info=True)


# -- recolouring her figure (skin mods) ----------------------------------------------------------------------------
def recolor(image, palette: dict):
    """Her picture in a skin's colours: her red, green, purple outline, dark body and blue eyes each move to the
    skin's colour, keeping their light and shade. Returns a new QImage (the same one if there's nothing to do)."""
    if not palette:
        return image
    import numpy as np
    from PySide6.QtGui import QColor, QImage
    src = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = src.width(), src.height()
    a = np.frombuffer(src.constBits(), np.uint8).reshape(h, src.bytesPerLine())[:, : w * 4].reshape(h, w, 4).copy()
    rgb = a[..., :3].astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    solid = a[..., 3] > 0
    masks = {
        "hair": solid & (r > 120) & (r > g * 1.8) & (r >= b * 1.1) & (sat > 0.35),
        "accent": solid & (g > 110) & (g > r * 1.4) & (g > b * 1.15),
        "outline": solid & (b > 90) & (b > g * 1.3) & (r > g * 1.05) & (r < b * 1.1),
        "eyes": solid & (b > 150) & (g > 120) & (b > r * 1.4),
        "body": solid & (mx < 60),
    }
    refs = {"hair": (249, 8, 84), "accent": (40, 230, 110), "outline": (110, 60, 200), "eyes": (60, 170, 255),
            "body": (24, 18, 28)}
    for part, mask in masks.items():
        if part not in palette or not mask.any():
            continue
        target = QColor(palette[part])
        t = np.array([target.red(), target.green(), target.blue()], np.float32)
        ref_luma = max(1.0, 0.3 * refs[part][0] + 0.59 * refs[part][1] + 0.11 * refs[part][2])
        luma = 0.3 * r[mask] + 0.59 * g[mask] + 0.11 * b[mask]
        k = (luma / ref_luma)[:, None]
        if part == "body":                                   # dark parts: tinted, never brightened much
            k = np.clip(k, 0.3, 1.6)
        rgb[mask] = np.clip(t[None, :] * k, 0, 255)
    a[..., :3] = rgb.astype(np.uint8)
    return QImage(a.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


# -- animations: keyframes -> pose values ---------------------------------------------------------------------------
def animation_moves(anim: dict, elapsed: float) -> tuple[dict, str] | None:
    """The pose values ({lean: .., wave: ..}, eyes) of an animation `elapsed` seconds in, or None once it's over."""
    total = anim["seconds"] * anim["loop"]
    if elapsed < 0 or elapsed >= total:
        return None
    t = (elapsed % anim["seconds"]) / anim["seconds"]
    keys = anim["keys"]
    before = max((k for k in keys if k["t"] <= t), key=lambda k: k["t"], default=keys[0])
    after = min((k for k in keys if k["t"] >= t), key=lambda k: k["t"], default=keys[-1])
    span = max(1e-6, after["t"] - before["t"])
    f = 0.0 if after is before else (t - before["t"]) / span
    f = f * f * (3 - 2 * f)                                  # eased
    moves = {}
    for name in set(before) | set(after):
        if name in ("t", "eyes"):
            continue
        a, b = float(before.get(name, 0.0)), float(after.get(name, 0.0))
        moves[name] = a + (b - a) * f
    eyes = before.get("eyes", "") if f < 0.5 else after.get("eyes", "")
    return moves, eyes


# -- behaviour mods ----------------------------------------------------------------------------------------------------
def apply_behaviour(settings, manager) -> list[str]:
    """Behaviour mods' settings on (your own values kept, and put back when the mod is turned off).
    Returns the setting names that changed."""
    state = manager._state.setdefault("behaviour", {})        # {setting: your value before a mod changed it}
    wanted: dict = {}
    for mod in manager.enabled():
        if mod.manifest.type in ("behaviour", "look"):
            wanted.update(mod.manifest.data.get("settings", {}))
        elif mod.manifest.type == "personality":            # (2.4.1) a personality mod on: she IS that one
            wanted["personality"] = str(mod.manifest.data.get("personality", {}).get("key", ""))
    changed = []
    for key in list(state):                                   # a mod turned off: your value back
        if key not in wanted:
            setattr(settings, key, state.pop(key))
            changed.append(key)
    for key, value in wanted.items():
        if not hasattr(settings, key):
            continue
        if key not in state:
            state[key] = getattr(settings, key)
        if getattr(settings, key) != value:
            setattr(settings, key, value)
            changed.append(key)
    manager._save_state()
    if changed:
        settings.save()
    return changed
