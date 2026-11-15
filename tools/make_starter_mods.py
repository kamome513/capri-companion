"""Builds the mods that come with Capri (assets/mods/*.capri-mod). All their pictures and sounds are drawn / made
here (capri/mods/creator.py), so they're original. Run: python tools/make_starter_mods.py"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPainterPath, QPen  # noqa: E402

from capri.mods import creator  # noqa: E402
from capri.mods.manager import pack_folder  # noqa: E402

OUT = ROOT / "assets" / "mods"


# Her colours (the same ones her figure and hair use, so a skin mod recolours these too and they always match her)
HAIR, DARK, PURPLE, GREEN = QColor(249, 8, 84), QColor(12, 8, 20), QColor(110, 60, 200), QColor(40, 230, 110)


def _sparkle(p, shape: QPainterPath, box: QRectF, n: int = 60) -> None:
    """White specks like the ones in her hair, inside a shape."""
    import random
    rng = random.Random(7)
    p.save()
    p.setClipPath(shape)
    for _ in range(n):
        c = QColor(255, 255, 255, rng.randint(120, 230))
        p.fillRect(QRectF(box.x() + rng.random() * box.width(), box.y() + rng.random() * box.height(), 2, 2), c)
    p.restore()


def ears(path: Path) -> None:
    """Two jagged shard ears in her hair's red and speckles, a black inside with a green glint and a purple edge -
    their base is spiky like her hair, so they grow out of it instead of sitting on top."""
    img, p = creator._canvas(256, 128)
    for side in (-1, 1):
        cx = 128 + side * 74
        tip = QPointF(cx + side * 22, 6)
        pts = [QPointF(cx - side * 40, 118), QPointF(cx - side * 30, 96), QPointF(cx - side * 38, 84),
               QPointF(cx - side * 16, 52), tip, QPointF(cx + side * 30, 70), QPointF(cx + side * 24, 88),
               QPointF(cx + side * 36, 104), QPointF(cx + side * 22, 112), QPointF(cx + side * 14, 124)]
        outer = QPainterPath(pts[0])
        for q in pts[1:]:
            outer.lineTo(q)
        outer.closeSubpath()
        p.fillPath(outer, HAIR)
        _sparkle(p, outer, QRectF(cx - 45, 0, 90, 128))
        inner = QPainterPath(QPointF(cx - side * 14, 104))
        for q in (QPointF(cx - side * 2, 64), QPointF(cx + side * 16, 30), QPointF(cx + side * 16, 76),
                  QPointF(cx + side * 8, 102)):
            inner.lineTo(q)
        inner.closeSubpath()
        p.fillPath(inner, DARK)
        glint = QPainterPath(QPointF(cx + side * 4, 70))
        for q in (QPointF(cx + side * 13, 44), QPointF(cx + side * 11, 74)):
            glint.lineTo(q)
        glint.closeSubpath()
        p.fillPath(glint, GREEN)
        edge = QColor(PURPLE)
        edge.setAlpha(220)
        p.setPen(QPen(edge, 2.5))
        p.drawPolyline([pts[3], tip, pts[5]])
    p.end()
    img.save(str(path))


def visor(path: Path) -> None:
    """Cyber shades: two angular lenses - one over each eye - in a black frame with a bridge, tinted her mask's green
    with a glint. (The picture is laid so her eyes land in the middle of each lens: they're 0.53 of its width apart.)"""
    img, p = creator._canvas(256, 104)
    frame_col = QColor(DARK)
    for cx in (61, 195):                                   # each lens: wider at the top, angled down to the outside
        outer = 1 if cx > 128 else -1
        lens = QPainterPath(QPointF(cx - outer * 44, 30))
        for x, y in ((cx + outer * 52, 22), (cx + outer * 46, 66), (cx + outer * 20, 84), (cx - outer * 30, 80),
                     (cx - outer * 46, 58)):
            lens.lineTo(QPointF(x, y))
        lens.closeSubpath()
        p.setPen(QPen(frame_col, 9))                       # thick black rim
        p.setBrush(frame_col)
        p.drawPath(lens)
        tint = QColor(GREEN)
        tint.setAlpha(150)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint)
        p.drawPath(lens)
        p.save()                                           # dark at the top, lighter down the lens
        p.setClipPath(lens)
        p.fillRect(QRectF(cx - 60, 18, 120, 18), QColor(12, 8, 20, 120))
        glint = QPainterPath(QPointF(cx - outer * 30, 46))
        for x, y in ((cx - outer * 14, 36), (cx - outer * 2, 36), (cx - outer * 22, 54)):
            glint.lineTo(QPointF(x, y))
        glint.closeSubpath()
        p.fillPath(glint, QColor(255, 255, 255, 170))
        p.restore()
        edge = QColor(PURPLE)
        edge.setAlpha(230)
        p.setPen(QPen(edge, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(lens)
    p.setPen(QPen(frame_col, 8))                           # the bridge
    p.drawLine(QPointF(104, 34), QPointF(152, 34))
    p.setPen(QPen(frame_col, 7))                           # the arms, back toward her hair
    p.drawLine(QPointF(10, 26), QPointF(2, 22))
    p.drawLine(QPointF(246, 18), QPointF(254, 14))
    p.end()
    img.save(str(path))


def halo(path: Path) -> None:
    """A jagged, glitchy ring in her hair's red with a purple glow - like a shard of her hair floating up."""
    import math
    img, p = creator._canvas(256, 80)
    ring = QPainterPath()
    n = 28
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        r = 1.0 + (0.1 if i % 2 else -0.06)
        q = QPointF(128 + 104 * r * math.cos(a), 40 + 22 * r * math.sin(a))
        ring.moveTo(q) if i == 0 else ring.lineTo(q)
    for width, colour, alpha in ((14, PURPLE, 90), (7, HAIR, 235), (3, QColor(255, 190, 215), 255)):
        c = QColor(colour)
        c.setAlpha(alpha)
        p.setPen(QPen(c, width))
        p.drawPath(ring)
    p.end()
    img.save(str(path))


def preview_of(src: Path, dest: Path, bg: str = "#0a080e") -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    pic = QImage(str(src))
    img, p = creator._canvas(256, 256)
    p.fillRect(QRectF(0, 0, 256, 256), QColor(bg))
    s = pic.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    p.drawImage(QPointF((256 - s.width()) / 2, (256 - s.height()) / 2), s)
    p.setPen(QPen(QColor(255, 42, 109), 4))
    p.drawRect(QRectF(2, 2, 252, 252))
    p.end()
    img.save(str(dest))


MODS = [
    {"id": "neon-ice", "name": "Neon Ice", "type": "skin", "tags": ["blue", "cold"],
     "description": "Ice-blue hair, magenta chrome and a deep blue outline.",
     "palette": {"hair": "#33e0ff", "accent": "#ff3fbf", "outline": "#2a6cff", "body": "#0e1626"}},
    {"id": "toxic-glitch", "name": "Toxic Glitch", "type": "skin", "tags": ["green", "acid"],
     "description": "Acid-green hair with hazard-yellow chrome.",
     "palette": {"hair": "#7dff3a", "accent": "#ffe600", "outline": "#1f9e5a", "body": "#121a0e"}},
    {"id": "cyber-ears", "name": "Cyber Ears", "type": "cosmetic", "tags": ["ears", "cute"],
     "description": "Jagged shard ears that grow out of her hair (they take a skin's colours too).",
     "items": [{"image": "ears.png", "slot": "ears", "x": 0.5, "y": -0.62, "width": 1.9, "layer": "front"}]},
    {"id": "holo-visor", "name": "Holo Shades", "type": "cosmetic", "tags": ["glasses", "face"],
     "description": "Angular cyber shades: a lens over each eye, black frame, green tint.", "version": "1.2.0",
     "items": [{"image": "visor.png", "slot": "face", "x": 0.5, "y": 0.5, "width": 1.0, "layer": "front"}]},
    {"id": "glitch-halo", "name": "Glitch Halo", "type": "cosmetic", "tags": ["hat", "glow"],
     "description": "A jagged ring of her hair's red floating above her head.",
     "items": [{"image": "halo.png", "slot": "hat", "x": 0.5, "y": -1.05, "width": 1.45, "layer": "front"}]},
    {"id": "dance-floor", "name": "Dance Floor", "type": "animations", "tags": ["dance", "moves"],
     "description": "Three moves she busts out now and then: hip sway, victory wave and a big stretch.",
     "animations": [
         {"name": "Hip sway", "seconds": 1.6, "loop": 3, "keys": [
             {"t": 0, "lean": 0.0}, {"t": 0.25, "lean": 0.1, "squat": 0.15}, {"t": 0.5, "lean": 0.0},
             {"t": 0.75, "lean": -0.1, "squat": 0.15, "eyes": "happy"}, {"t": 1, "lean": 0.0}]},
         {"name": "Victory wave", "seconds": 2.6, "loop": 1, "keys": [
             {"t": 0, "wave": 0}, {"t": 0.2, "wave": 1, "eyes": "happy"}, {"t": 0.4, "wave": 1, "wag": 1},
             {"t": 0.6, "wave": 1, "wag": -1}, {"t": 0.8, "wave": 1, "wag": 1}, {"t": 1, "wave": 0}]},
         {"name": "Big stretch", "seconds": 3.0, "loop": 1, "keys": [
             {"t": 0, "sweep": 0, "squat": 0}, {"t": 0.4, "sweep": 1, "lean": -0.05, "blink": 1},
             {"t": 0.7, "sweep": 1, "lean": 0.05, "blink": 1}, {"t": 1, "sweep": 0}]}]},
    {"id": "noir", "name": "Noir Detective", "type": "personality", "tags": ["moody", "funny"],
     "description": "She narrates everything like a rain-soaked noir detective.",
     "personality": {"key": "noir", "label": "Noir", "emotion": "smirk", "chance": 0.4,
                     "intro": "The city was quiet. Too quiet. Then you called my name.",
                     "prompt": "Personality: a hard-boiled film-noir detective. You narrate what happens in moody "
                               "one-liners with rain, neon and cheap coffee metaphors, but you always help and you "
                               "clearly like the user.",
                     "remarks": ["Another case closed.", "The rain kept falling. The job got done.",
                                 "Just another night in the city.", "I've seen worse. Not much worse."]}},
    {"id": "cozy-chrome", "name": "Cozy Chrome", "type": "lines", "tags": ["greetings", "wholesome"],
     "description": "Warm greetings and softer reactions.",
     "lines": {"greet": ["Hey you. The grid's brighter with you on it.", "Welcome home, choom. Kettle's on.",
                         "There you are. I saved you a seat in the neon."],
               "pat": ["Pat accepted. Recharging happiness.", "Mm. Ten out of ten pat.", "Again. That's an order."],
               "poke": ["Poke detected. Retaliation pending.", "Boop received."],
               "ouch": ["Wheee - okay, that was kind of fun.", "Gentle with the chrome, choom!"]}},
    {"id": "synth-blips", "name": "Synth Blips", "type": "sounds", "tags": ["retro", "beeps"],
     "description": "Retro synth blips when she wakes up, finishes something, gets patted or thrown.",
     "sounds": {"wake": "wake.wav", "done": "done.wav", "error": "error.wav", "pat": "pat.wav",
                "throw": "throw.wav", "greet": "greet.wav", "click": "click.wav"}},
    {"id": "free-roam", "name": "Free Roam", "type": "behaviour", "tags": ["roam", "lively"],
     "description": "She roams around and does her idle things. Your own settings come back "
                    "when you turn it off.",
     "settings": {"roaming": True, "idle_acts": True, "idle_animation": True}},
]
def _personality_mods() -> list[dict]:
    """Each of her own personalities as a mod too (2.4.1): turn one on in Mods and she switches to it; turn it off
    and she's back to the one you had."""
    from capri import personality
    out = []
    for key, p in personality.PERSONALITIES.items():
        label = p.label.replace(" (default)", "")
        out.append({"id": f"{key}-personality", "name": f"{label} Capri", "type": "personality",
                    "tags": ["personality", "built-in"], "version": "1.0.0",
                    "description": f"Her {label.lower()} side: {p.intro or 'her usual self.'}",
                    "personality": {"key": key, "label": label, "emotion": p.emotion, "chance": p.chance,
                                    "intro": p.intro, "prompt": p.prompt, "remarks": list(p.remarks)}})
    return out


def _look_mods() -> list[dict]:
    """Her models and styles as mods (2.4.1): body looks, lying down, sitting on windows, portrait / classic, classic
    hair, the mask drone, and the chat window's skins. On: she switches; off: back to what you had."""
    from capri.ui.chat_window import SKINS
    looks = [
        ("flat-body", "Flat Body", {"body_style": "flat"}, "Her default: big bold shards with a purple rim.",
         ["#ff1654", "#24f578", "#0c0814", "#762ccd"]),
        ("full-colour-body", "Full Colour Body", {"body_style": "full"}, "Her body in its full, detailed colours.",
         ["#ff2a6d", "#28e66e", "#1a1020"]),
        ("neon-body", "Neon Body", {"body_style": "neon"}, "Dark body, glowing red and green edges.",
         ["#0e0816", "#ff285a", "#32ff8c"]),
        ("lying-down", "Lying Down", {"lounge": True}, "She lies along the top of her panel.",
         ["#ff2a6d", "#0e0816", "#00e2ff"]),
        ("sit-on-windows", "Sits On Windows", {"perch_windows": True},
         "She hops onto the window you're using, and back onto her panel when you close it.",
         ["#00e2ff", "#ff2a6d", "#0e0816"]),
        ("portrait-style", "Talking Portrait", {"character_style": "portrait"}, "Just her face, in a neon card.",
         ["#ff2a6d", "#00e2ff"]),
        ("classic-style", "Classic Capri", {"character_style": "classic"}, "Her very first art.",
         ["#ec1046", "#1a1020", "#ffffff"]),
        ("classic-hair", "Classic Spiky Hair", {"hair_style": "classic"}, "Her first hair: a wide spiky block.",
         ["#ec1046", "#ffbed6"]),
        ("mask-drone", "Mask Drone", {"drone_look": "mask"}, "In games she becomes her green visor instead of the disk.",
         ["#28e66e", "#0e0816"]),
    ]
    out = [{"id": i, "name": n, "type": "look", "tags": ["look", "model"], "version": "1.0.0", "description": d,
            "settings": st, "_swatch": sw} for i, n, st, d, sw in looks]
    for skin in SKINS.values():
        out.append({"id": f"{skin.key}-chat", "name": f"{skin.label} Chat Log", "type": "look",
                    "tags": ["chat", "log", "skin"], "version": "1.0.0",
                    "description": f"The chat window and its log in the {skin.label} style.",
                    "settings": {"chat_skin": skin.key}, "_swatch": [skin.accent, skin.panel, skin.text]})
    return out


def _style_mods() -> list[dict]:
    """Her styles (2.6): appearance presets - a palette and live effects (tools/styles_data.py)."""
    from styles_data import STYLES
    out = []
    for s in STYLES:
        style = dict(s["style"], theme=s["theme"])
        out.append({"id": s["id"], "name": s["name"], "type": "skin", "version": s.get("version", "1.0.0"),
                    "tags": ["style", s["theme"].lower()], "description": s["description"],
                    "palette": s["palette"], "style": style})
    return out


MODS += _personality_mods() + _look_mods()
SOUNDS = {"wake.wav": [660, 990], "done.wav": [880, 1320, 1760], "error.wav": [400, 300], "pat.wav": [1046, 1318],
          "throw.wav": [1600, 1200, 800, 500], "greet.wav": [523, 659, 784, 1046], "click.wav": [2000]}


def main() -> None:
    global MODS
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (QPainter needs it)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    MODS = MODS + _style_mods()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.capri-mod"):
        old.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        for spec in MODS:
            d = Path(tmp) / spec["id"]
            d.mkdir()
            data = {"version": spec.get("version", "1.1.0"), "author": "Capri", "capri": ">=2.4.0", "preview": "preview.png", **spec}
            import mod_previews as mp                        # (2.4.3) pictures of HER with each mod
            pv = d / "preview.png"
            kind = spec["type"]
            data.pop("_swatch", None)
            if kind == "skin":
                mp.skin(pv, spec["palette"], spec.get("style"))
            elif kind == "cosmetic":
                pic = spec["items"][0]["image"]
                {"ears.png": ears, "visor.png": visor, "halo.png": halo}[pic](d / pic)
                mp.cosmetic(pv, d, spec["items"])
            elif kind == "sounds":
                for name, notes in SOUNDS.items():
                    creator.tone(d / name, notes, 0.16 if len(notes) < 3 else 0.26)
                mp.sounds(pv)
            elif kind == "look":
                from capri.ui.chat_window import SKINS
                mp.look(pv, spec["settings"], SKINS.get(spec["settings"].get("chat_skin", "")))
            elif kind == "animations":
                mp.animation(pv, {**spec["animations"][0], "keys": sorted(spec["animations"][0]["keys"],
                                                                          key=lambda k: k["t"])})
            elif kind == "personality":
                mp.personality(pv, spec["personality"]["key"], spec["personality"]["label"])
            elif kind == "lines":
                mp.lines(pv)
            else:
                mp.behaviour(pv)
            (d / "mod.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            (OUT / f"{spec['id']}.capri-mod").write_bytes(pack_folder(d))
            print("made", spec["id"])
    (OUT / "catalog.json").write_text(json.dumps({"ratings": {}}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
