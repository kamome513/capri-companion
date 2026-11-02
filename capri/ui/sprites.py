"""The character-sheet art (assets/capri_v2): body frames, expressions, mouth shapes, lying pose."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage

# Which letters make which mouth shape (the sheet's 16 visemes).
VISEME_FOR = {
    "a": "A", "e": "E", "i": "I", "y": "I", "o": "O", "u": "O", "w": "O", "l": "L", "m": "M", "b": "M",
    "p": "P", "f": "F", "v": "V", "t": "T", "d": "D", "n": "N", "s": "S", "z": "S", "c": "S", "k": "D",
    "g": "D", "r": "E", "h": "A", "q": "O", "x": "S", "j": "J",
}
DIGRAPHS = {"th": "TH", "ch": "CH", "sh": "CH"}


def visemes_for_text(text: str) -> list[str]:
    """'Launching' -> ['L','A','O','N','CH','I','N','D']: a rough mouth-shape sequence for lip-sync."""
    out, t, i = [], text.lower(), 0
    while i < len(t):
        pair = t[i:i + 2]
        if pair in DIGRAPHS:
            out.append(DIGRAPHS[pair])
            i += 2
            continue
        if t[i] in VISEME_FOR:
            out.append(VISEME_FOR[t[i]])
        i += 1
    return out


@dataclass
class SpriteArt:
    root: Path
    body: dict[str, QImage] = field(default_factory=dict)
    head_box: dict[str, QRectF] = field(default_factory=dict)   # normalised 0..1
    anchor: dict[str, float] = field(default_factory=dict)
    expressions: dict[str, QImage] = field(default_factory=dict)
    visemes: dict[str, QImage] = field(default_factory=dict)
    lying: QImage | None = None
    face_layer: dict[str, QImage] = field(default_factory=dict)   # just her face, for the "storm" hair

    @classmethod
    def load(cls, root: Path) -> "SpriteArt | None":
        path = root / "manifest.json"
        if not path.is_file():
            return None
        m = json.loads(path.read_text(encoding="utf-8"))
        art = cls(root)

        def img(rel: str) -> QImage | None:
            q = QImage(str(root / rel))
            return None if q.isNull() else q.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

        for group, target in (("body", art.body), ("expressions", art.expressions), ("visemes", art.visemes),
                              ("face_layer", art.face_layer)):
            for name, rel in m.get(group, {}).items():
                q = img(rel)
                if q is not None:
                    target[name] = q
        if m.get("lying"):
            art.lying = img(m["lying"])
        for name, box in m.get("head_box", {}).items():
            art.head_box[name] = QRectF(*box)
        art.anchor = {k: float(v) for k, v in m.get("anchor", {}).items()}
        if "idle" not in art.body or "neutral" not in art.expressions:
            return None
        return art

    def frame(self, name: str) -> QImage:
        return self.body.get(name) or self.body["idle"]

    def face(self, name: str) -> QImage:
        return self.expressions.get(name) or self.expressions["neutral"]

    def mouth(self, viseme: str) -> QImage:
        return self.visemes.get(viseme) or self.face("neutral")
