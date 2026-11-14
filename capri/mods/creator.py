"""Mod maker tools: a ready-to-edit mod folder for each kind of mod ("Make a mod..." in Settings -> Mods), with
working example files - edit them, press Validate, then Install or Export to share.

Also used to draw the pictures and sounds of the mods that come with Capri (tools/make_starter_mods.py), so all
of them are original and made here.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

from .manifest import CATEGORY, TYPES

README = """{name} - a Capri mod ({type})

Files:
  mod.json     what the mod is (see "How to make mods" in Capri's guides: docs/modding.md)
{files}
Steps:
  1. Edit mod.json (and the pictures / sounds).
  2. Settings -> Mods -> Validate a folder...  (it tells you what's wrong, if anything)
  3. Settings -> Mods -> Import mod...         (pick this folder) to try it on Capri
  4. Export it as a .capri-mod file to share it.
Mods can only hold pictures (.png/.jpg/.webp), .wav sounds and text - no programs.
"""


def new_mod(folder: Path, kind: str, mod_id: str, name: str, author: str = "") -> Path:
    """Create a mod folder of this kind with working example content. Returns the folder."""
    if kind not in TYPES:
        raise ValueError(kind)
    folder = Path(folder) / mod_id
    folder.mkdir(parents=True, exist_ok=True)
    data: dict = {"id": mod_id, "name": name, "version": "1.0.0", "author": author, "type": kind,
                  "description": f"My {CATEGORY[kind].lower()} mod.", "category": CATEGORY[kind], "tags": [],
                  "capri": ">=2.4.0", "preview": "preview.png"}
    files = ["  preview.png  the picture shown in the mods list"]
    if kind == "skin":
        data["palette"] = {"hair": "#33e0ff", "accent": "#ff3fbf", "outline": "#2a6cff", "body": "#101a2a"}
        swatch(folder / "preview.png", [data["palette"][k] for k in ("hair", "accent", "outline", "body")])
    elif kind == "cosmetic":
        draw_ears(folder / "ears.png", "#ff2a6d")
        data["items"] = [{"image": "ears.png", "slot": "ears", "x": 0.5, "y": -0.05, "width": 1.25, "layer": "back"}]
        draw_ears(folder / "preview.png", "#ff2a6d")
        files.append("  ears.png     the cosmetic (transparent PNG)")
    elif kind == "animations":
        data["animations"] = [{"name": "Little wave", "seconds": 2.4, "loop": 1, "keys": [
            {"t": 0, "wave": 0}, {"t": 0.25, "wave": 1, "eyes": "happy"}, {"t": 0.5, "wave": 1, "wag": 1},
            {"t": 0.75, "wave": 1, "wag": -1}, {"t": 1, "wave": 0}]}]
        swatch(folder / "preview.png", ["#ff2a6d", "#00e2ff"])
    elif kind == "personality":
        data["personality"] = {"key": mod_id.replace(".", "-")[:30], "label": name[:30],
                               "prompt": "Personality: describe how she talks here - her mood, her style, what she "
                                         "finds funny. Keep her kind to the user.",
                               "remarks": ["Done. Obviously.", "Easy."], "chance": 0.3,
                               "intro": "New me. Like it?", "emotion": "smirk"}
        swatch(folder / "preview.png", ["#7a2aff", "#ff2a6d"])
    elif kind == "behaviour":
        data["settings"] = {"roaming": True, "glitches": 90}
        swatch(folder / "preview.png", ["#00ff9c", "#101a2a"])
    elif kind == "look":
        data["settings"] = {"body_style": "neon"}
        swatch(folder / "preview.png", ["#0e0816", "#ff285a", "#32ff8c"])
    elif kind == "lines":
        data["lines"] = {"greet": ["Welcome back to the grid, choom."], "pat": ["Pat logged. Thanks."],
                         "ouch": ["Hey! Careful with the chrome!"]}
        swatch(folder / "preview.png", ["#ffe600", "#ff2a6d"])
    elif kind == "sounds":
        tone(folder / "done.wav", [880, 1320], 0.18)
        tone(folder / "wake.wav", [660, 990], 0.14)
        data["sounds"] = {"done": "done.wav", "wake": "wake.wav"}
        files.append("  done.wav / wake.wav   the sounds (16-bit WAV, a few seconds at most)")
        swatch(folder / "preview.png", ["#00e2ff", "#ff2a6d", "#ffe600"])
    (folder / "mod.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (folder / "README.txt").write_text(README.format(name=name, type=kind, files="\n".join(files)), encoding="utf-8")
    return folder


# -- pictures and sounds (all drawn / made here) ------------------------------------------------------------------
def _canvas(w: int, h: int):
    from PySide6.QtGui import QImage, QPainter
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return img, p


def swatch(path: Path, colours: list[str], size: int = 256) -> None:
    """A neon card of colour shards: a preview for mods without a picture of their own."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QPainterPath, QPen
    img, p = _canvas(size, size)
    p.fillRect(QRectF(0, 0, size, size), QColor(10, 8, 14))
    n = max(1, len(colours))
    for i, c in enumerate(colours):
        path_ = QPainterPath(QPointF(size * i / n, size))
        path_.lineTo(QPointF(size * (i + 0.5) / n + size * 0.18, 0))
        path_.lineTo(QPointF(size * (i + 1) / n + size * 0.18, 0))
        path_.lineTo(QPointF(size * (i + 1) / n, size))
        path_.closeSubpath()
        p.fillPath(path_, QColor(c))
    p.setPen(QPen(QColor(255, 42, 109), 4))
    p.drawRect(QRectF(2, 2, size - 4, size - 4))
    p.end()
    img.save(str(path))


def draw_ears(path: Path, colour: str, size: int = 256) -> None:
    """Two angular neon cat ears (for a cosmetic: drawn behind her head)."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPainterPath, QPen
    img, p = _canvas(size, size // 2)
    for side in (-1, 1):
        cx = size / 2 + side * size * 0.3
        ear = QPainterPath(QPointF(cx - side * size * 0.17, size * 0.48))
        ear.lineTo(QPointF(cx + side * size * 0.06, size * 0.02))
        ear.lineTo(QPointF(cx + side * size * 0.15, size * 0.48))
        ear.closeSubpath()
        p.setPen(QPen(QColor(255, 255, 255), 3))
        p.fillPath(ear, QColor(colour))
        p.drawPath(ear)
        inner = QPainterPath(QPointF(cx - side * size * 0.08, size * 0.45))
        inner.lineTo(QPointF(cx + side * size * 0.05, size * 0.14))
        inner.lineTo(QPointF(cx + side * size * 0.09, size * 0.45))
        inner.closeSubpath()
        p.fillPath(inner, QColor(20, 6, 18))
    p.end()
    img.save(str(path))


def tone(path: Path, freqs: list[float], seconds: float = 0.2, rate: int = 22050) -> None:
    """A short synth blip (a few notes, quick fade) as a 16-bit WAV."""
    frames = []
    per = seconds / max(1, len(freqs))
    for f in freqs:
        n = int(rate * per)
        for i in range(n):
            env = math.sin(math.pi * i / n) ** 0.6
            v = 0.45 * env * (math.sin(2 * math.pi * f * i / rate) + 0.3 * math.sin(4 * math.pi * f * i / rate))
            frames.append(struct.pack("<h", int(max(-1, min(1, v)) * 32767)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(frames))
