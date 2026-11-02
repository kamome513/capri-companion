"""Loads Capri's artwork from ``assets/capri/manifest.json``.

Each pose is an image file. Missing poses fall back to the ``idle`` pose,
so new expressions can be added later just by dropping in a file and adding
one line to the manifest.

Art with a real alpha channel (a cut-out PNG) is drawn free-standing on the
desktop. Art without transparency (e.g. a screenshot with the red sparkle
background) is never colour-keyed - that would also erase Capri's own red
body - so it is shown inside an angled "portrait card" frame instead.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

log = logging.getLogger("capri")

CUTOUT = "cutout"
CARD = "card"


def has_transparency(image: QImage) -> bool:
    """True if the image's border is mostly transparent (i.e. a cut-out)."""
    if not image.hasAlphaChannel():
        return False
    w, h = image.width(), image.height()
    step_x, step_y = max(1, w // 40), max(1, h // 40)
    samples = [(x, 0) for x in range(0, w, step_x)] + [(x, h - 1) for x in range(0, w, step_x)]
    samples += [(0, y) for y in range(0, h, step_y)] + [(w - 1, y) for y in range(0, h, step_y)]
    clear = sum(1 for x, y in samples if image.pixelColor(x, y).alpha() < 16)
    return clear >= len(samples) * 0.5


@dataclass
class CharacterArt:
    root: Path
    name: str = "Capri"
    icon: QImage = field(default_factory=QImage)
    poses: dict[str, QImage] = field(default_factory=dict)
    mode: str = CARD

    @classmethod
    def load(cls, root: Path) -> "CharacterArt":
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        art = cls(root=root, name=manifest.get("name", "Capri"))

        for pose, filename in manifest.get("poses", {}).items():
            image = QImage(str(root / filename))
            if image.isNull():
                log.warning(f"could not load pose '{pose}' from {root / filename}")
                continue
            art.poses[pose] = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

        if "idle" not in art.poses:
            raise FileNotFoundError(f"{manifest_path}: an 'idle' pose image is required")

        icon = QImage(str(root / manifest["icon"])) if manifest.get("icon") else QImage()
        art.icon = icon if not icon.isNull() else art.poses["idle"]

        requested = manifest.get("display", "auto")
        if requested in (CUTOUT, CARD):
            art.mode = requested
        else:
            art.mode = CUTOUT if has_transparency(art.poses["idle"]) else CARD
        return art

    def pose(self, name: str) -> QImage:
        return self.poses.get(name) or self.poses["idle"]

    @staticmethod
    def scaled(image: QImage, width: int, height: int, dpr: float, cover: bool) -> QImage:
        """Scale preserving aspect ratio (never stretched), at device resolution."""
        mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if cover else Qt.AspectRatioMode.KeepAspectRatio
        out = image.scaled(round(width * dpr), round(height * dpr), mode, Qt.TransformationMode.SmoothTransformation)
        out.setDevicePixelRatio(dpr)
        return out
