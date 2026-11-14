"""Settings -> Styles (2.6): her appearance presets. Pick one to see its preview, palette and description; Apply
puts it on her (with a short shimmer as she changes), Default Capri takes it off. Below: which kinds of effects
to show (particles, aura and glow, hair, materials, the now-and-then moments, trails) and the quality.

A style is a skin mod with effects (capri/ui/style_fx.py), so styles also show up under Mods - and your own style
mods appear here too."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from ..mods.store import preview_image

THEMES = ("Elemental", "Digital", "Artistic", "Experimental", "Signature")
TOGGLES = (("style_particles", "Particles"), ("style_aura", "Aura, outline and eye glow"),
           ("style_hair", "Hair effects"), ("style_materials", "Materials"),
           ("style_events", "Special moments"), ("style_motion", "Trails when she moves"))


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class StylesTab(QWidget):
    def __init__(self, manager, store, settings, changed: Callable[[], None] = lambda: None) -> None:
        super().__init__()
        self.manager, self.store, self.settings, self.changed = manager, store, settings, changed
        self._data: dict[str, dict] = {}
        root = QVBoxLayout(self)
        root.addWidget(_hint("<b>Styles</b>: whole new looks for Capri - each with its own colours, materials, light "
                             "and little effects around her. Pick one, then <b>Apply</b>. Effects are drawn only "
                             "round her and never cover your other windows."))
        top = QHBoxLayout()
        self.theme = QComboBox()
        self.theme.addItem("All styles", "")
        for t in THEMES:
            self.theme.addItem(t, t)
        self.theme.currentIndexChanged.connect(lambda *_: self._fill())
        top.addWidget(self.theme)
        top.addStretch(1)
        default = QPushButton("Default Capri")
        default.setToolTip("Take her style off: her own colours, no effects.")
        default.clicked.connect(self.default)
        top.addWidget(default)
        root.addLayout(top)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(112, 112))
        self.list.setGridSize(QSize(132, 150))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(lambda *_: self._show())
        self.list.itemDoubleClicked.connect(lambda *_: self.apply())
        row.addWidget(self.list, 3)
        side = QVBoxLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(256, 256)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 18px; font-weight: bold;")
        side.addWidget(self.name)
        self.theme_label = _hint("")
        side.addWidget(self.theme_label)
        self.swatches = QHBoxLayout()
        holder = QWidget()
        holder.setLayout(self.swatches)
        side.addWidget(holder)
        self.description = _hint("")
        side.addWidget(self.description)
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply)
        side.addWidget(self.apply_button)
        self.status = _hint("")
        side.addWidget(self.status)
        side.addStretch(1)
        right = QWidget()
        right.setLayout(side)
        right.setFixedWidth(300)
        row.addWidget(right)
        root.addLayout(row, 1)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)
        fx = QHBoxLayout()
        self.master = QCheckBox("Effects on")
        self.master.setChecked(getattr(settings, "style_effects", True))
        self.master.toggled.connect(lambda on: self._set("style_effects", on))
        fx.addWidget(self.master)
        self.boxes = {}
        for key, label in TOGGLES:
            box = QCheckBox(label)
            box.setChecked(getattr(settings, key, True))
            box.toggled.connect(lambda on, k=key: self._set(k, on))
            self.boxes[key] = box
            fx.addWidget(box)
        root.addLayout(fx)
        q = QHBoxLayout()
        q.addWidget(QLabel("Quality"))
        self.quality = QComboBox()
        self.quality.addItem("Full (smoothest)", "full")
        self.quality.addItem("Light (fewer particles, less CPU)", "light")
        self.quality.setCurrentIndex(max(0, self.quality.findData(getattr(settings, "style_quality", "full"))))
        self.quality.currentIndexChanged.connect(lambda *_: self._set("style_quality", self.quality.currentData()))
        q.addWidget(self.quality)
        q.addStretch(1)
        root.addLayout(q)
        self._fill()

    # -- the list -----------------------------------------------------------------------------------------------------
    def styles(self) -> list:
        """Every style: the ones that come with her and any style mods you've installed."""
        out, seen = [], set()
        for listing in self.store.builtin():
            data = self._manifest(listing)
            if listing.type == "skin" and data.get("style"):
                out.append(listing)
                seen.add(listing.id)
        for mod in self.manager.installed():
            if mod.id not in seen and mod.manifest.type == "skin" and mod.manifest.data.get("style"):
                self._data[mod.id] = mod.manifest.data
                out.append(mod)
        return out

    def _manifest(self, listing) -> dict:
        if listing.id not in self._data:
            data = {}
            try:
                with zipfile.ZipFile(io.BytesIO(self.store.download(listing))) as z:
                    name = next(n for n in z.namelist() if n.endswith("mod.json"))
                    data = json.loads(z.read(name).decode("utf-8"))
            except Exception:
                data = {}
            self._data[listing.id] = data
        return self._data[listing.id]

    def _fill(self) -> None:
        want = self.theme.currentData()
        current = self.applied()
        self.list.clear()
        for s in self.styles():
            data = self._data.get(s.id, {})
            theme = (data.get("style") or {}).get("theme", "")
            if want and theme != want:
                continue
            name = data.get("name", s.id)
            item = QListWidgetItem(QIcon(self._pixmap(s, 112)), ("✓ " if s.id == current else "") + name)
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            item.setToolTip(data.get("description", ""))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._show()

    def _pixmap(self, s, size: int) -> QPixmap:
        try:
            raw = self.store.preview_of(s) if hasattr(s, "builtin") else b""
            img = preview_image(raw) if raw else QImage(str(s.folder / self._data.get(s.id, {}).get("preview", "")))
        except Exception:
            img = QImage()
        if img.isNull():
            img = QImage(size, size, QImage.Format.Format_ARGB32)
            img.fill(QColor(20, 14, 26))
        return QPixmap.fromImage(img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))

    def _picked(self):
        item = self.list.currentItem()
        if item is None:
            return None
        sid = item.data(Qt.ItemDataRole.UserRole)
        return next((s for s in self.styles() if s.id == sid), None)

    def _show(self) -> None:
        s = self._picked()
        while self.swatches.count():
            w = self.swatches.takeAt(0).widget()
            if w is not None:
                w.setParent(None)                       # gone now (not at the next event loop turn)
        if s is None:
            self.name.setText("")
            self.description.setText("No styles here.")
            self.apply_button.setEnabled(False)
            return
        data = self._data.get(s.id, {})
        self.preview.setPixmap(self._pixmap(s, 256))
        self.name.setText(data.get("name", s.id))
        self.theme_label.setText((data.get("style") or {}).get("theme", "") + " style")
        self.description.setText(data.get("description", ""))
        for col in list((data.get("palette") or {}).values())[:5]:
            chip = QLabel()
            chip.setFixedSize(34, 18)
            chip.setStyleSheet(f"background: {col}; border: 1px solid #555;")
            self.swatches.addWidget(chip)
        self.swatches.addStretch(1)
        on = s.id == self.applied()
        self.apply_button.setEnabled(not on)
        self.apply_button.setText("Applied" if on else "Apply")

    # -- applying -----------------------------------------------------------------------------------------------------
    def applied(self) -> str:
        """The style she's wearing now ("" = her own look)."""
        for mod in self.manager.enabled():
            if mod.manifest.type == "skin":
                return mod.id
        return ""

    def apply(self) -> None:
        s = self._picked()
        if s is None:
            return
        try:
            if self.manager.get(s.id) is None:
                self.manager.install_bytes(self.store.download(s), source="builtin")
            self.manager.set_enabled(s.id, True)
        except Exception as exc:
            self.status.setText(f"Couldn't apply it: {str(exc)[:80]}")
            return
        self.status.setText(f"She's wearing {self._data.get(s.id, {}).get('name', s.id)} now.")
        self._fill_keep(s.id)

    def default(self) -> None:
        for mod in list(self.manager.enabled()):
            if mod.manifest.type == "skin":
                self.manager.set_enabled(mod.id, False)
        self.status.setText("Back to her own look.")
        self._fill_keep("")

    def _fill_keep(self, sid: str) -> None:
        row = self.list.currentRow()
        self._fill()
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)

    def _set(self, key: str, value) -> None:
        setattr(self.settings, key, value)
        self.settings.save()
        self.changed()
