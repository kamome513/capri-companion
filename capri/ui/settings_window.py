"""Settings window: apps Capri can open/close, and voice options."""

from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QScrollArea, QAbstractItemView, QCheckBox, QComboBox, QListWidgetItem, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSlider,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__, hotkeys
from ..net import friendly
from ..commands import parser
from ..commands.apps import (CLOSE_ASK, CLOSE_FORCE, CLOSE_NORMAL, PROGRAM, STEAM, WEBSITE, AppEntry,
                             add_found_games, entry_status, found_games, save_apps)
from ..commands.catalog import url_is_safe
from . import theme
from .deck import STYLE, DeckHeader, slot_title          # the settings window is a cyberdeck

log = logging.getLogger("capri")

if TYPE_CHECKING:
    from ..commands.router import CommandRouter
    from ..settings import Settings

TYPE_LABELS = {PROGRAM: "Program", STEAM: "Steam game", WEBSITE: "Website / link"}
CLOSE_LABELS = {CLOSE_NORMAL: "Like clicking X", CLOSE_ASK: "Ask me first", CLOSE_FORCE: "Force quit"}
COLUMNS = ["Name (say this)", "Also say", "Type", "Where it is (path / Steam id / link)", "Found?",
           "Arguments", "Processes", "When closing"]
C_NAME, C_ALIASES, C_TYPE, C_TARGET, C_STATUS, C_ARGS, C_PROCS, C_CLOSE = range(8)
ADVANCED = (C_ARGS, C_PROCS, C_CLOSE)




def _combo(labels: dict[str, str], value: str) -> QComboBox:
    box = QComboBox()
    for key, label in labels.items():
        box.addItem(label, key)
    box.setCurrentIndex(max(0, box.findData(value)))
    return box


def _split_list(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


class SettingsWindow(QDialog):
    def __init__(self, router: CommandRouter, settings: Settings, icon: QImage,
                 apply_voice: Callable[[], list[str]], extra_tabs: tuple = ()) -> None:
        super().__init__(None)
        self.router = router
        self.catalog = router.catalog
        self.settings = settings
        self.apply_voice = apply_voice
        self.setWindowTitle("Capri - Settings")
        self.setWindowIcon(QIcon(QPixmap.fromImage(icon)))
        self.setStyleSheet(STYLE)
        self.resize(1060, 600)

        self.header = DeckHeader(__version__, self._chips)
        tabs = self.tabs = QTabWidget()
        pages = [(self._apps_tab(), "Apps"), (self._found_tab(), "Found on this PC"), (self._voice_tab(), "Wake word")]
        self._extra = [widget for widget, _title in extra_tabs]
        self._dirty: set[int] = set()                 # tabs you changed something on
        for i, widget in enumerate(self._extra):
            self._watch(widget, i)
        for widget, title in extra_tabs:
            scroll = QScrollArea()                     # long tabs scroll instead of squashing
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(widget)
            pages.append((scroll, title))
        for n, (widget, title) in enumerate(pages, 1):
            tabs.addTab(widget, slot_title(n, title))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.header)
        layout.addWidget(tabs)
        self.load_rows()

    def _watch(self, tab, i: int) -> None:
        from PySide6.QtWidgets import QAbstractButton, QAbstractSlider, QLineEdit as _Line
        mark = lambda *_a, i=i: self._dirty.add(i)       # noqa: E731
        for box in tab.findChildren(QComboBox):
            box.currentIndexChanged.connect(mark)
        for button in tab.findChildren(QAbstractButton):
            if button.isCheckable():
                button.toggled.connect(mark)
        for slider in tab.findChildren(QAbstractSlider):
            slider.valueChanged.connect(mark)
        for line in tab.findChildren(_Line):
            line.textEdited.connect(mark)

    def hideEvent(self, event) -> None:
        """Closing Settings keeps what you changed on the other tabs too - no Save needed. (Only
        tabs you touched: the rest might be out of date if you changed things by voice meanwhile.)"""
        dirty, self._dirty = self._dirty, set()
        for i, widget in enumerate(self._extra):
            apply = getattr(widget, "apply", None)
            if i in dirty and callable(apply):
                try:
                    apply()
                except Exception as exc:                       # one tab's problem mustn't block closing
                    log.warning(f"settings: couldn't apply a tab: {exc}")
        super().hideEvent(event)

    def _chips(self) -> list[tuple[str, bool]]:
        """The header's readouts - straight from her settings."""
        s = self.settings
        return [("VOICE " + ("ON" if s.voice_enabled else "OFF"), s.voice_enabled),
                ("MIC " + ("MUTED" if s.mic_muted else "LIVE"), not s.mic_muted),
                ("REPLIES " + ("SPOKEN" if s.speech_enabled else "TEXT"), s.speech_enabled),
                ("CHATBOT " + ("ON" if s.ai_enabled else "OFF"), s.ai_enabled),
                (f"APPS {len(self.catalog.apps)}", True)]

    def showEvent(self, event) -> None:
        self.header.update()                           # readouts are fresh each time it opens
        super().showEvent(event)

    # -- Apps tab --------------------------------------------------------------------
    def _apps_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        hint = QLabel("<b>Apps and games Capri opens and closes for you.</b><br>"
                      "Say “open <i>Name</i>” or “close <i>Name</i>”. “Also say” = other words for it, "
                      "separated by commas (e.g. <i>blocks strap</i>). "
                      "“Found?” shows whether Capri can find it on this PC. "
                      "Click <b>Add app or game...</b> to pick from what's installed - no file hunting.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(C_TARGET, QHeaderView.ResizeMode.Stretch)
        for col, width in ((C_NAME, 130), (C_ALIASES, 120), (C_TYPE, 110), (C_STATUS, 250), (C_ARGS, 140),
                           (C_PROCS, 150), (C_CLOSE, 120)):
            self.table.setColumnWidth(col, width)
        self.table.itemChanged.connect(self._cell_changed)
        v.addWidget(self.table, 1)

        row = QHBoxLayout()
        for label, slot, tip in (
                ("Add app or game...", self.pick_app, "Pick from the apps and games installed on this PC"),
                ("Add my games", self.add_my_games, "Add every downloaded game Capri finds (Steam, Epic, Xbox...)"),
                ("Change path...", self.browse, "Point the selected app at a program file"),
                ("Remove", self.remove_row, "Take the selected app off the list"),
                ("Test launch", self.test_launch, "Open the selected app now")):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            row.addWidget(button)
        self.advanced = QCheckBox("Show advanced")
        self.advanced.setToolTip("Arguments, process names and what “close” does")
        self.advanced.toggled.connect(self._show_advanced)
        row.addWidget(self.advanced)
        row.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        row.addWidget(self.status)
        save = QPushButton("Save")
        save.clicked.connect(self.save)
        row.addWidget(save)
        v.addLayout(row)
        self._show_advanced(False)

        tryrow = QHBoxLayout()
        tryrow.addWidget(QLabel("Try a command:"))
        self.try_box = QLineEdit()
        self.try_box.setPlaceholderText("e.g.  open blocks strap   /   close discord and deadlock")
        self.try_box.textChanged.connect(self.explain)
        tryrow.addWidget(self.try_box, 1)
        v.addLayout(tryrow)
        self.try_result = QLabel("Type what you'd say. This only shows what would happen; nothing runs.")
        self.try_result.setObjectName("result")
        self.try_result.setWordWrap(True)
        v.addWidget(self.try_result)
        return page

    def _show_advanced(self, on: bool) -> None:
        for col in ADVANCED:
            self.table.setColumnHidden(col, not on)

    def load_rows(self) -> None:
        self.table.setRowCount(0)
        for entry in self.catalog.apps:
            self._append(entry)

    def _append(self, e: AppEntry) -> None:
        self.table.blockSignals(True)
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, C_NAME, QTableWidgetItem(e.name))
        self.table.setItem(r, C_ALIASES, QTableWidgetItem(", ".join(e.aliases)))
        kind = _combo(TYPE_LABELS, e.launch_type)
        kind.currentIndexChanged.connect(lambda _i, box=kind: self._type_changed(box))
        self.table.setCellWidget(r, C_TYPE, kind)
        self.table.setItem(r, C_TARGET, QTableWidgetItem(e.target))
        status = QTableWidgetItem("")
        status.setFlags(status.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, C_STATUS, status)
        self.table.setItem(r, C_ARGS, QTableWidgetItem(subprocess.list2cmdline(e.arguments)))
        self.table.setItem(r, C_PROCS, QTableWidgetItem(", ".join(e.processes)))
        self.table.setCellWidget(r, C_CLOSE, _combo(CLOSE_LABELS, e.close))
        self.table.blockSignals(False)
        self._update_status(r)

    def _steam_ids(self) -> set[str] | None:
        return {g.appid for g in self.catalog.games} if self.catalog.games else None

    def _update_status(self, r: int) -> None:
        item = self.table.item(r, C_STATUS)
        if item is None or self.table.cellWidget(r, C_TYPE) is None:
            return
        ok, words = entry_status(self._entry(r), self._steam_ids())
        self.table.blockSignals(True)
        item.setText(("✓ " if ok else "✗ " if ok is False else "• ") + words)
        item.setToolTip(words)
        item.setForeground(theme.GREEN if ok else theme.ALERT if ok is False else theme.TEXT_DIM)
        self.table.blockSignals(False)

    def _cell_changed(self, item: QTableWidgetItem) -> None:
        if item.column() in (C_TARGET, C_TYPE):
            self._update_status(item.row())

    def _type_changed(self, box: QComboBox) -> None:
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, C_TYPE) is box:
                self._update_status(r)

    def _names_listed(self) -> set[str]:
        return {self._text(r, C_NAME).lower() for r in range(self.table.rowCount())}

    def add_entries(self, entries: list[AppEntry]) -> int:
        """Add rows (skipping names already listed). Returns how many were added."""
        have, added = self._names_listed(), 0
        for e in entries:
            if e.name.lower() in have:
                continue
            self._append(e)
            have.add(e.name.lower())
            added += 1
        if added:
            self.table.selectRow(self.table.rowCount() - 1)
            self.table.scrollToBottom()
        return added

    def add_my_games(self) -> None:
        self.catalog.rescan(now=True)
        current = [self._entry(r) for r in range(self.table.rowCount())]
        games = add_found_games(current, found_games(self.catalog.games, self.catalog.shortcuts))
        added = self.add_entries(games)
        self.status.setText(f"Added {added} game{'s' * (added != 1)} - click Save to keep them." if added
                            else "No new games found (Steam, Epic, Xbox, Riot, GOG, EA, Ubisoft...).")

    def installed_choices(self) -> list[AppEntry]:
        """Everything installed that can go on the list: games first, then apps."""
        self.catalog.rescan()
        out = found_games(self.catalog.games, self.catalog.shortcuts)
        names = {e.name.lower() for e in out}
        for sc in self.catalog.shortcuts:
            if sc.name.lower() in names:
                continue
            target = sc.target
            procs = [target.name] if target is not None and target.suffix.lower() == ".exe" else []
            out.append(AppEntry(sc.name, PROGRAM, str(sc.path), processes=procs))
            names.add(sc.name.lower())
        for app in self.catalog.installed:
            if app.name.lower() in names:
                continue
            # Store apps have no file: an empty path makes her find it in Windows' app list by name.
            out.append(AppEntry(app.name, PROGRAM, str(app.exe) if app.exe else "",
                                processes=[app.exe.name] if app.exe else []))
            names.add(app.name.lower())
        return out

    def pick_app(self) -> None:
        picker = AppPicker(self, self.installed_choices(), self._names_listed())
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        if picker.browse_instead:
            return self.browse(new_row=True)
        added = self.add_entries(picker.chosen())
        if added:
            self.status.setText(f"Added {added} - click Save to keep {'it' if added == 1 else 'them'}.")

    def add_row(self) -> None:
        self._append(AppEntry("New app"))
        self.table.selectRow(self.table.rowCount() - 1)
        self.table.editItem(self.table.item(self.table.rowCount() - 1, C_NAME))

    def _selected(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def browse(self, new_row: bool = False) -> None:
        r = -1 if new_row else self._selected()
        if r < 0 and not new_row:
            self.status.setText("Select an app first (or use Add app or game...).")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose the program", "",
                                              "Programs and shortcuts (*.exe *.lnk *.url *.bat);;All files (*)")
        if not path:
            return
        if r < 0:
            self.add_row()
            r = self.table.rowCount() - 1
        p = Path(path)
        self.table.cellWidget(r, C_TYPE).setCurrentIndex(self.table.cellWidget(r, C_TYPE).findData(PROGRAM))
        self.table.item(r, C_TARGET).setText(str(p))
        if self._text(r, C_NAME) in ("", "New app"):
            self.table.item(r, C_NAME).setText(p.stem)
        if p.suffix.lower() == ".exe" and not self._text(r, C_PROCS):
            self.table.item(r, C_PROCS).setText(p.name)
        self._update_status(r)

    def remove_row(self) -> None:
        r = self._selected()
        if r >= 0:
            self.table.removeRow(r)

    def test_launch(self) -> None:
        r = self._selected()
        if r < 0:
            self.status.setText("Select an app first.")
            return
        e = self._entry(r)
        problem = self._problem(e) or self.router.launch_entry(e)
        self.status.setText(problem or f"Launched {e.name}.")

    def _text(self, r: int, c: int) -> str:
        item = self.table.item(r, c)
        return item.text().strip() if item else ""

    def _entry(self, r: int) -> AppEntry:
        try:
            args = shlex.split(self._text(r, C_ARGS), posix=False)
        except ValueError:
            args = self._text(r, C_ARGS).split()
        return AppEntry(
            name=self._text(r, C_NAME), launch_type=self.table.cellWidget(r, C_TYPE).currentData(),
            target=self._text(r, C_TARGET), arguments=[a.strip('"') for a in args],
            aliases=_split_list(self._text(r, C_ALIASES)), processes=_split_list(self._text(r, C_PROCS)),
            close=self.table.cellWidget(r, C_CLOSE).currentData())

    def _problem(self, e: AppEntry) -> str | None:
        if not e.name:
            return "Every app needs a name."
        if e.target and e.launch_type == STEAM and not e.target.isdigit():
            return f"{e.name}: a Steam id is a number (e.g. 1422450 for Deadlock)."
        if e.target and e.launch_type == WEBSITE and not url_is_safe(e.target):
            return f"{e.name}: links must start with https:// (or an app link like spotify:)."
        return None

    def save(self) -> None:
        entries = [self._entry(r) for r in range(self.table.rowCount())]
        for e in entries:
            problem = self._problem(e)
            if problem:
                QMessageBox.warning(self, "Capri", problem)
                return
        save_apps(entries)
        self.catalog.reload_apps()
        self.status.setText("Saved.")
        self.explain(self.try_box.text())

    def explain(self, text: str) -> None:
        if text.strip():
            self.try_result.setText(self.router.explain(text))

    # -- Found tab ---------------------------------------------------------------------
    def _found_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        hint = QLabel("Capri can open these without any setup. Say “Capri, open <name>”, or “show me <name> in File Explorer”.")
        hint.setObjectName("hint")
        v.addWidget(hint)
        self.found = QListWidget()
        v.addWidget(self.found, 1)
        rescan = QPushButton("Rescan")
        rescan.clicked.connect(lambda: self.fill_found(force=True))
        v.addWidget(rescan, 0, Qt.AlignmentFlag.AlignLeft)
        self.fill_found()
        return page

    def fill_found(self, force: bool = False) -> None:
        self.catalog.rescan(force=force, now=force)
        self.found.clear()
        for game in self.catalog.games:
            self.found.addItem(f"[Steam]  {game.name}")
        shortcut_names = set()
        for sc in self.catalog.shortcuts:
            shortcut_names.add(sc.name.lower())
            self.found.addItem(f"[Start]  {sc.name}")
        for app in self.catalog.installed:
            if app.name.lower() not in shortcut_names:
                self.found.addItem(f"[{'Store' if app.store_package else 'App'}]  {app.name}")
        names = sorted(n.title() if n.islower() else n for n in self.catalog.places)
        if names:
            self.found.addItem("[Folder]  " + ", ".join(names))
        if self.found.count() == 0:
            self.found.addItem("Nothing found (no Steam library, Start-menu shortcuts or installed apps detected).")

    def _refresh_model(self) -> None:
        from ..voice.model import BETTER_MODEL, find_model
        current = find_model()
        if current is not None and current.name == BETTER_MODEL:
            self.model_status.setText("Using the more accurate speech model.")
            self.model_btn.setVisible(False)
        else:
            self.model_status.setText("Mishears you a lot? The bigger model gets far more words right (it uses more "
                                      "memory). Restart Capri after it downloads.")

    def _download_better_model(self) -> None:
        import threading
        from ..voice.model import BETTER_URL, download_model
        self.model_btn.setEnabled(False)
        self.model_status.setText("Downloading... (this takes a minute)")

        def run() -> None:
            try:
                download_model(url=BETTER_URL, quiet=True)
                message = "Installed. Restart Capri (right-click → Exit, then start her) to use it."
            except Exception as exc:
                message = "Download failed: " + friendly(exc)
            QTimer.singleShot(0, self, lambda: (self.model_status.setText(message), self.model_btn.setEnabled(True)))
        threading.Thread(target=run, daemon=True).start()

    # -- teaching her your voice -------------------------------------------------------------
    TEACH_SECONDS = 45

    def _teach_voice(self) -> None:
        from ..voice.training import SAMPLES
        service = getattr(self.router.assistant, "service", None)
        if service is None or not hasattr(service, "set_training"):
            return self.teach_status.setText("Her hearing isn't running.")
        self._samples: list[tuple[float, str]] = []
        self._teaching = service
        service.heard.connect(self._taught_one)
        service.set_training(True)
        self.teach_btn.setEnabled(False)
        self.teach_status.setText(f"Say \u201cHey Capri\u201d now, like you normally would - 1 of {SAMPLES}.")
        self._teach_timer = QTimer(self)
        self._teach_timer.setSingleShot(True)
        self._teach_timer.timeout.connect(self._teach_done)
        self._teach_timer.start(self.TEACH_SECONDS * 1000)

    def _taught_one(self, confidence: float, said: str) -> None:
        from ..voice.training import SAMPLES
        self._samples.append((confidence, said))
        if len(self._samples) >= SAMPLES:
            return self._teach_done()
        self.teach_status.setText(f"Heard you. Again - {len(self._samples) + 1} of {SAMPLES}.")

    def _teach_done(self) -> None:
        from ..voice.training import learn
        service = getattr(self, "_teaching", None)
        if service is None:
            return
        self._teaching = None
        self._teach_timer.stop()
        try:
            service.heard.disconnect(self._taught_one)
        except (RuntimeError, TypeError):
            pass
        service.set_training(False)
        threshold, variants, note = learn(self._samples, list(self.settings.wake_variants))
        if threshold is not None:
            self.settings.wake_threshold = threshold
            self.threshold.setValue(round(threshold * 100))
            service.set_threshold(threshold)
        self.settings.wake_variants = variants
        service.set_learned(variants)
        self.settings.save()
        self.teach_btn.setEnabled(True)
        self.teach_status.setText(note)

    @staticmethod
    def _parakeet_words() -> str:
        from ..voice import parakeet
        if parakeet.ready():
            return ("Parakeet is downloaded. Press Apply to use it. It runs on your PC and uses about 900 MB of "
                    "RAM (given back to your game while she's in drone mode).")
        if not parakeet.installed():
            return "Parakeet's engine (sherpa-onnx) is missing from this copy of Capri."
        return ("Parakeet (NVIDIA's speech model) understands strong accents and mumbling far better. "
                "Press Download, then Apply. It runs on your PC - nothing you say is sent anywhere.")

    def _hearing_changed(self) -> None:
        """Only what the picked hearing needs: a download button, Whisper's size, a line about it."""
        from ..voice import parakeet, whisper
        picked = self.hearing.currentData()
        if getattr(self, "_parakeet_busy", False):
            return self._voice_form.setRowVisible(self.whisper_size, False)
        need_parakeet = picked == "parakeet" and not parakeet.ready() and parakeet.installed()
        need_whisper = picked == "whisper" and not whisper.installed()
        self.parakeet_btn.setVisible(need_parakeet)
        self.parakeet_btn.setEnabled(True)
        self.whisper_btn.setVisible(need_whisper)
        self._voice_form.setRowVisible(self._hearing_buttons, need_parakeet or need_whisper)
        self._voice_form.setRowVisible(self.whisper_size, picked == "whisper")
        self.parakeet_status.setText({
            "vosk": "Vosk is built in and light. Mishears you? Pick Parakeet - it's far better with accents.",
            "parakeet": self._parakeet_words(),
            "whisper": ("Whisper is installed. Press Apply to use it." if whisper.installed() else
                        "Whisper isn't installed yet - press Install Whisper (about a minute), then Apply."),
        }.get(picked, ""))

    def _download_parakeet(self) -> None:
        import threading
        from ..voice import parakeet
        if not parakeet.installed():
            self.parakeet_status.setText(self._parakeet_words())
            return
        self.parakeet_btn.setEnabled(False)
        self._parakeet_busy = True
        self._parakeet_progress = "Starting the download..."
        self.parakeet_status.setText(self._parakeet_progress)

        def progress(done: int, total: int) -> None:
            self._parakeet_progress = (f"Downloading Parakeet: {done / 1e6:.0f} / {total / 1e6:.0f} MB"
                                       if total else f"Downloading Parakeet: {done / 1e6:.0f} MB")

        def run() -> None:
            try:
                parakeet.download(progress)
                self._parakeet_progress = "done"
            except Exception as exc:
                log.warning("Parakeet download failed: %s", exc)
                self._parakeet_progress = f"failed: Download failed: {friendly(exc)}."

        def tick() -> None:
            text = self._parakeet_progress
            if text == "done":
                self._parakeet_busy = False
                self.hearing.setCurrentIndex(max(0, self.hearing.findData("parakeet")))
                self._hearing_changed()
                self.parakeet_status.setText("Parakeet is downloaded - press Apply to start using it.")
                return
            if text.startswith("failed: "):
                self._parakeet_busy = False
                self.parakeet_btn.setEnabled(True)
                self.parakeet_status.setText(text[8:])
                return
            self.parakeet_status.setText(text)
            QTimer.singleShot(400, tick)

        threading.Thread(target=run, daemon=True, name="parakeet-download").start()
        QTimer.singleShot(400, tick)

    def _install_whisper(self) -> None:
        """Runs setup_hearing.bat (it installs faster-whisper into Capri's own Python) in its window."""
        import sys
        from ..ai.doctor import NEW_CONSOLE, ROOT
        script = ROOT / "setup_hearing.bat"
        if sys.platform != "win32" or not script.exists():
            self.hearing_status.setText("Run setup_hearing.bat in Capri's folder.")
            return
        subprocess.Popen(["cmd.exe", "/c", str(script)], cwd=str(ROOT), creationflags=NEW_CONSOLE)
        self.hearing_status.setText("Installing in the window that opened. When it says Done, press Apply.")
        self.hearing.setCurrentIndex(max(0, self.hearing.findData("whisper")))

    # -- Voice tab -----------------------------------------------------------------------
    def _voice_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.threshold = QSlider(Qt.Orientation.Horizontal)
        self.threshold.setRange(50, 99)
        self.threshold.setValue(round(self.settings.wake_threshold * 100))
        self.threshold_label = QLabel()
        self.threshold.valueChanged.connect(
            lambda v: self.threshold_label.setText(f"{v}%  (higher = fewer false wake-ups, lower = hears you more easily)"))
        self.threshold.valueChanged.emit(self.threshold.value())
        form.addRow("Wake word confidence", self.threshold)
        form.addRow("", self.threshold_label)
        self.teach_btn = QPushButton("Teach her your voice (say \u201cHey Capri\u201d 4 times)")
        self.teach_btn.setToolTip("She tunes her wake word to your voice and mic: she stops missing you, and the "
                                  "way your mic makes her name sound counts as her name.")
        self.teach_btn.clicked.connect(self._teach_voice)
        self.teach_status = QLabel("")
        self.teach_status.setObjectName("hint")
        self.teach_status.setWordWrap(True)
        form.addRow("Your voice", self.teach_btn)
        form.addRow("", self.teach_status)
        self.hk_listen = QLineEdit(self.settings.hotkey_listen)
        self.hk_click = QLineEdit(self.settings.hotkey_click_through)
        self.model_status = QLabel()
        self.model_status.setObjectName("hint")
        self.model_status.setWordWrap(True)
        self.model_btn = QPushButton("Download the more accurate speech model (128 MB)")
        self.model_btn.clicked.connect(self._download_better_model)
        form.addRow("Understanding you", self.model_btn)
        form.addRow("", self.model_status)
        self._refresh_model()
        # -- how she hears you: Vosk (built in), Parakeet (download), Whisper (from the code only) --
        import sys as _sys
        from ..voice import parakeet, whisper
        self.hearing = QComboBox()
        self.hearing.addItem("Vosk - quick and light (built in)", "vosk")
        self.hearing.addItem(f"Parakeet - best for strong accents ({parakeet.MODEL_MB} MB download)", "parakeet")
        if whisper.installed() or not getattr(_sys, "frozen", False):   # the installed app can't add Whisper
            self.hearing.addItem("Whisper - good with accents", "whisper")
        self.hearing.setCurrentIndex(max(0, self.hearing.findData(self.settings.hearing)))
        form.addRow("Hearing", self.hearing)
        self.whisper_size = QComboBox()
        for key, label in whisper.SIZES.items():
            self.whisper_size.addItem(label, key)
        self.whisper_size.setCurrentIndex(max(0, self.whisper_size.findData(self.settings.whisper_size)))
        form.addRow("Whisper model", self.whisper_size)
        self.parakeet_btn = QPushButton(f"Download Parakeet ({parakeet.MODEL_MB} MB)")
        self.parakeet_btn.clicked.connect(self._download_parakeet)
        self.whisper_btn = QPushButton("Install Whisper")
        self.whisper_btn.clicked.connect(self._install_whisper)
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.parakeet_btn)
        row.addWidget(self.whisper_btn)
        row.addStretch(1)
        form.addRow("", buttons)
        self._hearing_buttons = buttons
        self.parakeet_status = QLabel("")             # what the picked hearing does, and how it's going
        self.parakeet_status.setObjectName("hint")
        self.parakeet_status.setWordWrap(True)
        self.hearing_status = self.parakeet_status
        form.addRow("", self.parakeet_status)
        self._voice_form = form
        self.hearing.currentIndexChanged.connect(lambda _i: self._hearing_changed())
        self._hearing_changed()
        from PySide6.QtWidgets import QCheckBox
        self.mic_cleanup = QCheckBox("Clean up my mic: turn a quiet mic up, cut rumble and hiss (on this PC)")
        self.mic_cleanup.setChecked(self.settings.mic_cleanup)
        form.addRow("", self.mic_cleanup)
        form.addRow("Push-to-talk hotkey", self.hk_listen)
        form.addRow("Click-through hotkey", self.hk_click)
        hint = QLabel("Hotkeys look like ctrl+alt+c or ctrl+shift+f9 (ctrl / alt / shift / win + a key).")
        hint.setObjectName("hint")
        form.addRow("", hint)
        apply = QPushButton("Apply")
        apply.clicked.connect(self.apply_voice_settings)
        self.voice_status = QLabel("")
        self.voice_status.setObjectName("hint")
        form.addRow(apply, self.voice_status)

        # -- your fixes for words she mishears ("to school" -> "discord") --
        title = QLabel("Fix what she mishears")
        title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        form.addRow(title)
        self.fixes = QTableWidget(0, 2)
        self.fixes.setHorizontalHeaderLabels(["When she hears", "Read it as"])
        self.fixes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fixes.verticalHeader().setVisible(False)
        self.fixes.setMinimumHeight(150)
        self._load_fixes()
        self.fixes.itemChanged.connect(lambda _item: self._save_fixes())
        form.addRow(self.fixes)
        add, remove = QPushButton("Add"), QPushButton("Remove")
        add.clicked.connect(lambda: self._add_fix(""))
        remove.clicked.connect(self._remove_fix)
        self.last_heard = QLabel()
        self.last_heard.setObjectName("hint")
        self.fix_last = QPushButton("Fix what she just heard")
        self.fix_last.clicked.connect(lambda: self._add_fix(getattr(self.router.assistant, "last_heard", "")))
        row = QHBoxLayout()
        for w in (add, remove, self.fix_last):
            row.addWidget(w)
        row.addWidget(self.last_heard, 1)
        form.addRow(row)
        hint = QLabel('Put the words she hears on the left ("to school") and what you meant on the right '
                      '("discord"); whole words only. Or just tell her: "when I say to school I mean discord".')
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        self._heard_timer = QTimer(self)
        self._heard_timer.setInterval(1000)
        self._heard_timer.timeout.connect(self._refresh_last_heard)
        self._heard_timer.start()
        self._refresh_last_heard()
        return page

    # -- fixes for misheard words ----------------------------------------------------------------
    def _load_fixes(self) -> None:
        self._loading = True
        self.fixes.setRowCount(0)
        for heard, meant in self.settings.corrections:
            r = self.fixes.rowCount()
            self.fixes.insertRow(r)
            self.fixes.setItem(r, 0, QTableWidgetItem(heard))
            self.fixes.setItem(r, 1, QTableWidgetItem(meant))
        self._loading = False
        self._shown = [list(p) for p in self.settings.corrections]

    def _save_fixes(self) -> None:
        if getattr(self, "_loading", False):
            return
        pairs = []
        for r in range(self.fixes.rowCount()):
            heard, meant = (self.fixes.item(r, c).text().strip() if self.fixes.item(r, c) else "" for c in (0, 1))
            if heard and meant:
                pairs.append([heard, meant])
        self.settings.corrections = pairs
        self._shown = [list(p) for p in pairs]
        self.settings.save()
        n = parser.set_corrections(pairs)
        self.voice_status.setText(f"{n} fix{'es' if n != 1 else ''} in use." if n else "")

    def _add_fix(self, heard: str) -> None:
        self._loading = True
        r = self.fixes.rowCount()
        self.fixes.insertRow(r)
        self.fixes.setItem(r, 0, QTableWidgetItem(heard))
        self.fixes.setItem(r, 1, QTableWidgetItem(""))
        self._loading = False
        self.fixes.setCurrentCell(r, 1 if heard else 0)
        self.fixes.editItem(self.fixes.item(r, 1 if heard else 0))

    def _remove_fix(self) -> None:
        rows = sorted({i.row() for i in self.fixes.selectedIndexes()} or {self.fixes.currentRow()}, reverse=True)
        for r in rows:
            if r >= 0:
                self.fixes.removeRow(r)
        self._save_fixes()

    def _refresh_last_heard(self) -> None:
        if not self.isVisible() and self.last_heard.text():
            return
        heard = getattr(self.router.assistant, "last_heard", "")
        self.last_heard.setText(f'She last heard: "{heard}"' if heard else "She hasn't heard anything yet.")
        self.fix_last.setEnabled(bool(heard))
        if self.settings.corrections != self._shown and self.fixes.state() != QAbstractItemView.State.EditingState:
            self._load_fixes()                    # a fix you added by voice while this was open

    def apply_voice_settings(self) -> None:
        for box in (self.hk_listen, self.hk_click):
            try:
                hotkeys.parse(box.text())
            except ValueError as exc:
                self.voice_status.setText(f"{box.text()!r}: {exc}")
                return
        self.settings.wake_threshold = self.threshold.value() / 100
        self.settings.hotkey_listen = self.hk_listen.text().strip().lower()
        self.settings.hotkey_click_through = self.hk_click.text().strip().lower()
        self.settings.hearing = self.hearing.currentData()
        self.settings.whisper_size = self.whisper_size.currentData()
        self.settings.mic_cleanup = self.mic_cleanup.isChecked()
        self.settings.save()
        errors = self.apply_voice()
        self.voice_status.setText("; ".join(errors) if errors else "Applied.")


class AppPicker(QDialog):
    """'Add app or game...': a searchable list of what's installed, so nobody has to dig
    through Program Files. A file browser is there too for anything not listed."""

    def __init__(self, parent, choices: list[AppEntry], listed: set[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add an app or game")
        self.setStyleSheet((parent.styleSheet() if parent is not None else "") +
                           "QListWidget::indicator { width: 14px; height: 14px; border: 1px solid #844cff;"
                           " background: #101014; } QListWidget::indicator:checked { background: #39e66b; }"
                           " QListWidget::item { padding: 3px; }")
        self.resize(460, 520)
        self.browse_instead = False
        v = QVBoxLayout(self)
        hint = QLabel("Pick what Capri should open by name. Tick as many as you like. "
                      "Games come from Steam, Epic, Xbox, Riot and other launchers; apps from your Start menu.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        v.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...  (e.g. discord, minecraft)")
        self.search.textChanged.connect(self.filter)
        v.addWidget(self.search)
        self.list = QListWidget()
        self._entries: list[AppEntry] = []
        for e in choices:
            tag = "Game" if e.launch_type == STEAM or e.close == CLOSE_ASK else "App"
            item = QListWidgetItem(f"{e.name}    [{tag}]" + ("   - already listed" if e.name.lower() in listed else ""))
            item.setData(Qt.ItemDataRole.UserRole, len(self._entries))
            if e.name.lower() in listed:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
            self._entries.append(e)
            self.list.addItem(item)
        if not choices:
            self.list.addItem("Nothing installed was found - use “Browse for a file...” below.")
        self.list.itemDoubleClicked.connect(self._double)
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        browse = QPushButton("Browse for a file...")
        browse.setToolTip("For a program that isn't listed above")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        add = QPushButton("Add")
        add.setDefault(True)
        add.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(add)
        v.addLayout(row)

    def filter(self, text: str) -> None:
        words = text.lower().split()
        for i in range(self.list.count()):
            item = self.list.item(i)
            self.list.setRowHidden(i, not all(w in item.text().lower() for w in words))

    def _double(self, item: QListWidgetItem) -> None:
        if item.flags() & Qt.ItemFlag.ItemIsEnabled and item.data(Qt.ItemDataRole.UserRole) is not None:
            item.setCheckState(Qt.CheckState.Checked)
            self.accept()

    def _browse(self) -> None:
        self.browse_instead = True
        self.accept()

    def chosen(self) -> list[AppEntry]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            index = item.data(Qt.ItemDataRole.UserRole)
            if index is not None and item.checkState() == Qt.CheckState.Checked:
                out.append(self._entries[index])
        if not out:                                       # nothing ticked: the highlighted one
            item = self.list.currentItem()
            if item is not None and item.flags() & Qt.ItemFlag.ItemIsEnabled and \
                    item.data(Qt.ItemDataRole.UserRole) is not None and not self.list.isRowHidden(self.list.row(item)):
                out.append(self._entries[item.data(Qt.ItemDataRole.UserRole)])
        return out
