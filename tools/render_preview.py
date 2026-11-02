"""Render the overlay for every state into PNGs without opening real windows.

Usage:  python tools/render_preview.py [output_dir] [art_folder]

Useful for checking the look after changing art or theme. Each image shows
the bottom-right corner of a screen with Capri and her panel composited on a
neutral wallpaper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from capri.app import PREVIEW_SEQUENCE, asset_root  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.ui.art import CharacterArt  # noqa: E402
from capri.ui.companion import Companion  # noqa: E402


def grab(widget: QWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "preview")
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    controller = CompanionController()
    art = CharacterArt.load(Path(sys.argv[2]) if len(sys.argv) > 2 else asset_root() / "capri")
    companion = Companion(controller, art, Settings())   # defaults; never touches your saved settings
    companion.place()
    area: QRect = companion.screen.availableGeometry()

    for state, message, entry in PREVIEW_SEQUENCE:
        if entry:
            controller.log(*entry)
        controller.set_state(state, message)
        app.processEvents()

        crop = QRect(area.right() - 460, area.bottom() - 420, 460, 420)
        canvas = QImage(crop.size(), QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(canvas)
        wall = QLinearGradient(0, 0, crop.width(), crop.height())
        wall.setColorAt(0, QColor(70, 70, 76))
        wall.setColorAt(1, QColor(150, 150, 156))
        p.fillRect(canvas.rect(), wall)
        for w in (companion.character, companion.panel):
            p.drawImage(w.pos() - crop.topLeft(), grab(w))
        p.end()
        path = out / f"{state.value}.png"
        canvas.save(str(path))
        print("wrote", path)


if __name__ == "__main__":
    main()
