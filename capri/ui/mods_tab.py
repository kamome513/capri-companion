"""Settings -> Mods: your mods, the mod store, and the mod maker tools.

Installed   turn mods on / off, rate them, export them to share, uninstall (asks first), import a .capri-mod
Store       the mods that come with Capri + the online list: previews, categories, ratings, install / update
Make mods   a ready-to-edit mod of any kind, a checker for your mod folder, and the guide
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..mods.manifest import CATEGORY, TYPES, ModError
from ..mods.store import preview_image

log = logging.getLogger("capri")
STARS = "★"


def _icon(data_or_path) -> QIcon:
    img = QImage(str(data_or_path)) if isinstance(data_or_path, (str, Path)) else preview_image(data_or_path or b"")
    if img.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(img.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)))


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class _Bridge(QObject):
    listed = Signal(object, str)          # (listings, problem)
    installed = Signal(object, str)       # (Installed or None, problem)


class ModsTab(QWidget):
    def __init__(self, manager, store, play_animation=None, guide_path: Path | None = None) -> None:
        super().__init__()
        self.manager, self.store, self.play_animation = manager, store, play_animation
        self.guide_path = guide_path
        self._bridge = _Bridge()
        self._bridge.listed.connect(self._listed)
        self._bridge.installed.connect(self._store_installed)
        self._listings = []
        root = QVBoxLayout(self)
        root.addWidget(_hint("<b>Mods</b> change how Capri looks, sounds, moves and talks: skins, cosmetics, "
                             "animation packs, personalities, greetings, sound packs and habits. Mods are only "
                             "pictures, sounds and text - nothing in a mod is ever run as a program."))
        tabs = self.tabs = QTabWidget()
        tabs.addTab(self._installed_page(), "Installed")
        tabs.addTab(self._store_page(), "Store")
        tabs.addTab(self._maker_page(), "Make mods")
        tabs.currentChanged.connect(lambda i: i == 1 and not self._listings and self.refresh_store())
        root.addWidget(tabs)
        self.status = _hint("")
        root.addWidget(self.status)
        manager.changed.append(self.refresh_installed)
        self.refresh_installed()

    def _say(self, text: str) -> None:
        self.status.setText(text)

    # -- Installed ----------------------------------------------------------------------------------------------
    def _installed_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        row = QHBoxLayout()
        self.installed_list = QListWidget()
        self.installed_list.setIconSize(QSize(64, 64))
        self.installed_list.currentItemChanged.connect(lambda *_: self._show_installed())
        row.addWidget(self.installed_list, 3)
        side = QVBoxLayout()
        self.detail = _hint("")
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        side.addWidget(self.detail)
        self.toggle_btn = QPushButton("Turn on")
        self.toggle_btn.clicked.connect(self._toggle)
        self.rating = QComboBox()
        self.rating.addItems(["Not rated"] + [STARS * n for n in range(1, 6)])
        self.rating.activated.connect(self._rate)
        self.play_btn = QPushButton("Play an animation")
        self.play_btn.clicked.connect(self._play)
        self.export_btn = QPushButton("Export to share...")
        self.export_btn.clicked.connect(self._export)
        self.uninstall_btn = QPushButton("Uninstall...")
        self.uninstall_btn.clicked.connect(self._uninstall)
        for w in (self.toggle_btn, QLabel("Your rating"), self.rating, self.play_btn, self.export_btn,
                  self.uninstall_btn):
            side.addWidget(w)
        side.addStretch(1)
        row.addLayout(side, 2)
        v.addLayout(row)
        bar = QHBoxLayout()
        for text, fn in (("Import mod...", self._import), ("Check for problems", self._check),
                         ("Open mods folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.manager.root))))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        v.addLayout(bar)
        return page

    def refresh_installed(self) -> None:
        keep = self._current_id()
        self.installed_list.clear()
        for mod in self.manager.installed():
            m = mod.manifest
            item = QListWidgetItem(_icon(mod.folder / m.preview) if m.preview else QIcon(),
                                   f"{m.name}  {m.version}\n{m.category} - {'ON' if mod.enabled else 'off'}")
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            self.installed_list.addItem(item)
            if m.id == keep:
                self.installed_list.setCurrentItem(item)
        if self.installed_list.currentItem() is None and self.installed_list.count():
            self.installed_list.setCurrentRow(0)
        if not self.installed_list.count():
            self.detail.setText("No mods yet. Get some in the <b>Store</b> tab, or import a .capri-mod file.")
        self._show_installed()

    def _current_id(self) -> str:
        item = self.installed_list.currentItem() if hasattr(self, "installed_list") else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else ""

    def _show_installed(self) -> None:
        mod = self.manager.get(self._current_id()) if self._current_id() else None
        for w in (self.toggle_btn, self.rating, self.export_btn, self.uninstall_btn):
            w.setEnabled(mod is not None)
        self.play_btn.setVisible(mod is not None and mod.manifest.type == "animations")
        if mod is None:
            return
        m = mod.manifest
        from ..mods.manifest import fits
        compat = "" if fits(m.capri) else f"<br><b>Needs Capri {m.capri}</b> - it stays off on this version."
        self.detail.setText(f"<b>{m.name}</b> {m.version}<br>by {m.author or 'unknown'} - {m.category}<br><br>"
                            f"{m.description}{compat}<br><br>Tags: {', '.join(m.tags) or '-'}")
        self.toggle_btn.setText("Turn off" if mod.enabled else "Turn on")
        self.rating.setCurrentIndex(mod.rating)

    def _toggle(self) -> None:
        mod = self.manager.get(self._current_id())
        if mod is None:
            return
        off = self.manager.set_enabled(mod.id, not mod.enabled)
        self._say(f"{mod.manifest.name} is {'off' if mod.enabled else 'on'}."
                  + (f" Turned off {', '.join(off)} (they can't be on together)." if off else ""))

    def _rate(self, index: int) -> None:
        if self._current_id():
            self.manager.rate(self._current_id(), index)
            self._say("Thanks - rating saved.")

    def _play(self) -> None:
        if self.play_animation is not None:
            name = self.play_animation("")
            self._say(f"Playing “{name}”." if name else "She can play animations in her full-body style "
                                                                    "(Settings -> Character), while she's idle.")

    def _export(self) -> None:
        mod = self.manager.get(self._current_id())
        if mod is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export mod", str(Path.home() / f"{mod.id}.capri-mod"),
                                              "Capri mods (*.capri-mod)")
        if path:
            try:
                out = self.manager.export(mod.id, path)
                self._say(f"Saved {out.name} - send it to anyone with Capri (Settings -> Mods -> Import mod).")
            except (ModError, OSError) as exc:
                self._say(f"Couldn't export it: {exc}")

    def _uninstall(self) -> None:
        mod = self.manager.get(self._current_id())
        if mod is None:
            return
        if QMessageBox.question(self, "Uninstall mod", f"Uninstall {mod.manifest.name}? Its files are deleted.") \
                != QMessageBox.StandardButton.Yes:
            return
        self.manager.uninstall(mod.id)
        self._say(f"{mod.manifest.name} uninstalled.")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import a mod", str(Path.home()),
                                              "Capri mods (*.capri-mod *.zip);;All files (*)")
        if path:
            self.install_path(path)

    def install_path(self, path: str) -> None:
        try:
            mod = self.manager.install_file(path)
            self._say(f"Installed {mod.manifest.label} and turned it on.")
        except ModError as exc:
            self._say(f"Not installed: {exc}.")

    def _check(self) -> None:
        problems = self.manager.compatibility()
        self._say(" ".join(problems) if problems else "All your mods work with this Capri and with each other.")

    # -- Store ----------------------------------------------------------------------------------------------------
    def _store_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        top = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItem("All categories", "")
        for kind in TYPES:
            self.category.addItem(CATEGORY[kind], CATEGORY[kind])
        self.category.currentIndexChanged.connect(lambda *_: self._fill_store())
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search mods...")
        self.search.textChanged.connect(lambda *_: self._fill_store())
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_store)
        updates = QPushButton("Update my mods")
        updates.clicked.connect(self._update_all)
        for w in (self.category, self.search, refresh, updates):
            top.addWidget(w)
        v.addLayout(top)
        row = QHBoxLayout()
        self.store_list = QListWidget()
        self.store_list.setIconSize(QSize(72, 72))
        self.store_list.currentItemChanged.connect(lambda *_: self._show_listing())
        row.addWidget(self.store_list, 3)
        side = QVBoxLayout()
        self.store_preview = QLabel()
        self.store_preview.setMinimumSize(160, 160)
        self.store_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_detail = _hint("")
        self.store_detail.setTextFormat(Qt.TextFormat.RichText)
        self.get_btn = QPushButton("Install")
        self.get_btn.clicked.connect(self._get)
        for w in (self.store_preview, self.store_detail, self.get_btn):
            side.addWidget(w)
        side.addStretch(1)
        row.addLayout(side, 2)
        v.addLayout(row)
        return page

    def refresh_store(self) -> None:
        self._say("Loading the mod store...")

        def work() -> None:
            try:
                found = self.store.listings(online=True)
                self._bridge.listed.emit(found, self.store.online_error)
            except Exception as exc:
                self._bridge.listed.emit(self.store.builtin(), f"the online mod list failed ({exc})")
        threading.Thread(target=work, daemon=True, name="capri-mod-store").start()

    def _listed(self, listings, problem: str) -> None:
        self._listings = listings
        self._say(problem.capitalize() + "." if problem else f"{len(listings)} mods in the store.")
        self._fill_store()

    def _fill_store(self) -> None:
        cat, words = self.category.currentData(), self.search.text().strip().lower()
        have = {m.id: m.manifest.version for m in self.manager.installed()}
        self.store_list.clear()
        from ..mods.manifest import parse_version
        for listing in self._listings:
            if cat and listing.category != cat:
                continue
            blob = " ".join([listing.name, listing.description, listing.author, " ".join(listing.tags)]).lower()
            if words and words not in blob:
                continue
            state = ("installed" if parse_version(have[listing.id]) >= parse_version(listing.version) else "update")\
                if listing.id in have else ""
            stars = f"{STARS} {listing.rating:.1f} ({listing.ratings})" if listing.ratings else "no ratings yet"
            item = QListWidgetItem(_icon(listing.preview), f"{listing.name}  {listing.version}   "
                                   f"{'[' + state + ']' if state else ''}\n{listing.category} - {stars}")
            item.setData(Qt.ItemDataRole.UserRole, listing.id)
            self.store_list.addItem(item)
        if self.store_list.count():
            self.store_list.setCurrentRow(0)
        self._show_listing()

    def _listing(self):
        item = self.store_list.currentItem()
        lid = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        return next((m for m in self._listings if m.id == lid), None)

    def _show_listing(self) -> None:
        listing = self._listing()
        self.get_btn.setEnabled(listing is not None)
        if listing is None:
            self.store_detail.setText("")
            self.store_preview.clear()
            return
        img = preview_image(self.store.preview_of(listing))
        self.store_preview.setPixmap(QPixmap.fromImage(img.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation))
                                     if not img.isNull() else QPixmap())
        have = self.manager.version_of(listing.id)
        from ..mods.manifest import parse_version
        self.get_btn.setText("Installed" if have and parse_version(have) >= parse_version(listing.version)
                             else "Update" if have else "Install")
        self.get_btn.setEnabled(not (have and parse_version(have) >= parse_version(listing.version)) and listing.fits)
        where = "Comes with Capri" if listing.builtin else "Online"
        compat = "" if listing.fits else f"<br><b>Needs Capri {listing.capri}</b>"
        self.store_detail.setText(f"<b>{listing.name}</b> {listing.version}<br>by {listing.author or 'unknown'} - "
                                  f"{listing.category}<br>{where}<br><br>{listing.description}{compat}")

    def _get(self) -> None:
        listing = self._listing()
        if listing is None:
            return
        self.get_btn.setEnabled(False)
        self._say(f"Getting {listing.name}...")

        def work() -> None:
            try:
                data = self.store.download(listing)
                self._bridge.installed.emit((listing, data), "")
            except Exception as exc:
                self._bridge.installed.emit(None, str(exc))
        threading.Thread(target=work, daemon=True, name="capri-mod-get").start()

    def _store_installed(self, got, problem: str) -> None:
        if got is None:
            self._say(f"Not installed: {problem}.")
            self._show_listing()
            return
        listing, data = got
        try:
            mod = self.manager.install_bytes(data, source="store")
            self._say(f"Installed {mod.manifest.label} - it's on (Installed tab to turn it off).")
        except ModError as exc:
            self._say(f"Not installed: {exc}.")
        self._fill_store()

    def _update_all(self) -> None:
        if not self._listings:
            return self.refresh_store()
        from ..mods.manifest import parse_version
        have = {m.id: m.manifest.version for m in self.manager.installed()}
        newer = [m for m in self._listings if m.id in have and parse_version(m.version) > parse_version(have[m.id])]
        if not newer:
            return self._say("Your mods are all up to date.")
        for listing in newer:
            self.store_list.setCurrentRow(next(i for i in range(self.store_list.count())
                                               if self.store_list.item(i).data(Qt.ItemDataRole.UserRole) == listing.id))
            self._get()

    # -- Make mods -------------------------------------------------------------------------------------------------
    def _maker_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(_hint("Make your own mod: pick what kind, give it a name, and Capri makes a folder with a working "
                          "example in it. Edit it, check it, then try it on Capri or export it to share."))
        row = QHBoxLayout()
        self.kind = QComboBox()
        for kind in TYPES:
            self.kind.addItem(CATEGORY[kind], kind)
        self.mod_name = QLineEdit()
        self.mod_name.setPlaceholderText("Your mod's name")
        make = QPushButton("Make a mod")
        make.clicked.connect(self._make)
        for w in (self.kind, self.mod_name, make):
            row.addWidget(w)
        v.addLayout(row)
        row2 = QHBoxLayout()
        for text, fn in (("Check a mod folder...", self._validate), ("Try a mod folder on Capri...", self._try_folder)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row2.addWidget(b)
        v.addLayout(row2)
        guide = QTextBrowser()
        guide.setOpenExternalLinks(True)
        try:
            guide.setMarkdown((self.guide_path or Path()).read_text(encoding="utf-8"))
        except OSError:
            guide.setPlainText("The modding guide comes with Capri (assets/mods/MODDING.md).")
        v.addWidget(guide, 1)
        return page

    def _make(self) -> None:
        import re
        from ..mods.creator import new_mod
        name = self.mod_name.text().strip() or "My mod"
        mod_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "my-mod"
        if len(mod_id) < 2:
            mod_id += "-mod"
        where = Path.home() / "Documents" / "Capri Mods"
        try:
            folder = new_mod(where, self.kind.currentData(), mod_id, name)
        except OSError as exc:
            return self._say(f"Couldn't make it: {exc}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self._say(f"Made {folder} - edit mod.json and its files, then press Check a mod folder.")

    def _pick_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Pick the mod's folder", str(Path.home() / "Documents" /
                                                                                  "Capri Mods"))

    def _validate(self) -> None:
        folder = self._pick_folder()
        if folder:
            from ..mods.manager import validate_folder
            ok, report = validate_folder(Path(folder))
            self._say(report)

    def _try_folder(self) -> None:
        folder = self._pick_folder()
        if folder:
            self.install_path(folder)
