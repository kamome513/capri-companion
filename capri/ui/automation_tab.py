"""Settings -> Automations: the visual editor. Your automations on the left; on the right, the one you picked: its
name, what starts it (and which app / time / words), and its steps - each one a command, something to say or a
wait. Templates to start from, Test run, and Delete (asks first)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .. import automation as auto


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


VALUE_HINT = {"app_open": "the app's name, e.g. Spotify", "app_close": "the app's name, e.g. Discord",
              "game_open": "the game's name (empty = any game)", "game_close": "the game's name (empty = any game)",
              "time": "HH:MM, e.g. 18:30", "startup": "(nothing needed)", "away": "minutes, e.g. 15",
              "back": "(nothing needed)", "phrase": "the words you'll say, e.g. gaming time"}
STEP_HINT = {"command": "anything you'd say to her: open discord, quiet mode, draw a heart...",
             "say": "what she says", "wait": "seconds (up to 600)"}


class StepRow(QWidget):
    def __init__(self, step: dict, remove: Callable[["StepRow"], None], move: Callable[["StepRow", int], None]):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.kind = QComboBox()
        for key, label in auto.ACTIONS.items():
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(step.get("type", "command"))))
        self.value = QLineEdit(step.get("value", ""))
        self.kind.currentIndexChanged.connect(lambda *_: self.value.setPlaceholderText(STEP_HINT[self.kind.currentData()]))
        self.value.setPlaceholderText(STEP_HINT[self.kind.currentData()])
        up, down, rm = QPushButton("Up"), QPushButton("Down"), QPushButton("Remove")
        for b, w in ((up, 54), (down, 54), (rm, 72)):
            b.setFixedWidth(w)
        up.clicked.connect(lambda: move(self, -1))
        down.clicked.connect(lambda: move(self, 1))
        rm.clicked.connect(lambda: remove(self))
        row.addWidget(self.kind)
        row.addWidget(self.value, 1)
        for b in (up, down, rm):
            row.addWidget(b)

    def step(self) -> dict:
        return {"type": self.kind.currentData(), "value": self.value.text().strip()}


class AutomationTab(QWidget):
    def __init__(self, settings, engine=None, apps: Callable[[], list[str]] = lambda: []) -> None:
        super().__init__()
        self.settings, self.engine, self.apps = settings, engine, apps
        self.items: list[auto.Automation] = auto.load(settings)
        self.current: int = -1
        root = QVBoxLayout(self)
        root.addWidget(_hint("<b>Automations</b>: when something happens, Capri does things for you. Each step is "
                             "something you could ask her yourself, so automations can't do anything you couldn't "
                             "- and risky things (like shutting down) still ask you first."))
        row = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._pick)
        left.addWidget(self.list, 1)
        self.template = QComboBox()
        self.template.addItem("New from a template...", -1)
        for i, t in enumerate(auto.TEMPLATES):
            self.template.addItem(t.name, i)
        self.template.activated.connect(self._from_template)
        new = QPushButton("New automation")
        new.clicked.connect(lambda: self._add(auto.Automation("My automation", "phrase", "", [])))
        left.addWidget(new)
        left.addWidget(self.template)
        row.addLayout(left, 2)
        self.editor = QWidget()
        form = self._form = QFormLayout(self.editor)
        self.name = QLineEdit()
        self.enabled = QCheckBox("On")
        self.trigger = QComboBox()
        for key, label in auto.TRIGGERS.items():
            self.trigger.addItem(label, key)
        self.trigger.currentIndexChanged.connect(self._trigger_changed)
        self.value = QComboBox()
        self.value.setEditable(True)
        self.days = []
        days_row = QHBoxLayout()
        for i, d in enumerate(auto.DAYS):
            box = QCheckBox(d)
            self.days.append(box)
            days_row.addWidget(box)
        self.days_widget = QWidget()
        self.days_widget.setLayout(days_row)
        form.addRow("Name", self.name)
        form.addRow("", self.enabled)
        form.addRow("Starts", self.trigger)
        form.addRow("Which", self.value)
        form.addRow("Days", self.days_widget)
        self.steps_box = QVBoxLayout()
        steps_holder = QWidget()
        steps_holder.setLayout(self.steps_box)
        form.addRow("Steps", steps_holder)
        add_step = QPushButton("+ Add a step")
        add_step.clicked.connect(lambda: self._add_step({"type": "command", "value": ""}))
        form.addRow("", add_step)
        buttons = QHBoxLayout()
        for text, fn in (("Save", self._save), ("Test run", self._test), ("Delete...", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            buttons.addWidget(b)
        holder = QWidget()
        holder.setLayout(buttons)
        form.addRow("", holder)
        self.status = _hint("")
        form.addRow(self.status)
        row.addWidget(self.editor, 3)
        root.addLayout(row)
        self.step_rows: list[StepRow] = []
        self._fill_list()

    # -- list ------------------------------------------------------------------------------------------------------
    def _fill_list(self, select: int = 0) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for a in self.items:
            problem = a.problem()
            item = QListWidgetItem(f"{'ON ' if a.enabled else 'off'}  {a.name}\n{auto.TRIGGERS[a.trigger]}"
                                   + (f" {a.value}" if a.value else "") + (f"  (!) {problem}" if problem else ""))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.editor.setEnabled(bool(self.items))
        if self.items:
            self.list.setCurrentRow(max(0, min(select, len(self.items) - 1)))
            self._pick(self.list.currentRow())
        else:
            self.current = -1
            self.status.setText("No automations yet - make one, or start from a template.")

    def _add(self, a: auto.Automation) -> None:
        self.items.append(auto.Automation.from_dict(a.to_dict()))
        auto.save(self.settings, self.items)
        self._fill_list(len(self.items) - 1)

    def _from_template(self, index: int) -> None:
        i = self.template.itemData(index)
        if i is not None and i >= 0:
            self._add(auto.TEMPLATES[i])
            self.status.setText("Added from a template - change it as you like, then Save.")
        self.template.setCurrentIndex(0)

    # -- editor ----------------------------------------------------------------------------------------------------
    def _pick(self, row: int) -> None:
        if not 0 <= row < len(self.items):
            return
        self.current = row
        a = self.items[row]
        self.name.setText(a.name)
        self.enabled.setChecked(a.enabled)
        self.trigger.setCurrentIndex(max(0, self.trigger.findData(a.trigger)))
        self._trigger_changed()
        self.value.setEditText(a.value)
        for i, box in enumerate(self.days):
            box.setChecked(i in a.days)
        for r in self.step_rows:
            r.setParent(None)
        self.step_rows = []
        for step in a.actions:
            self._add_step(step)
        self.status.setText(a.problem() and f"Not ready: {a.problem()}." or "")

    def _trigger_changed(self, *_a) -> None:
        kind = self.trigger.currentData()
        keep = self.value.currentText()
        self.value.clear()
        if kind in ("app_open", "app_close", "game_open", "game_close"):
            try:
                self.value.addItems(sorted(set(self.apps())))
            except Exception:
                pass
        self.value.setEditText(keep)
        self.value.lineEdit().setPlaceholderText(VALUE_HINT[kind])
        self.value.setEnabled(kind not in ("startup", "back"))
        self._form.setRowVisible(self.days_widget, kind == "time")

    def _add_step(self, step: dict) -> None:
        if len(self.step_rows) >= auto.MAX_ACTIONS:
            return
        row = StepRow(step, self._remove_step, self._move_step)
        self.step_rows.append(row)
        self.steps_box.addWidget(row)

    def _remove_step(self, row: StepRow) -> None:
        self.step_rows.remove(row)
        row.setParent(None)

    def _move_step(self, row: StepRow, by: int) -> None:
        i = self.step_rows.index(row)
        j = max(0, min(len(self.step_rows) - 1, i + by))
        if i == j:
            return
        self.step_rows.insert(j, self.step_rows.pop(i))
        for r in self.step_rows:
            self.steps_box.removeWidget(r)
        for r in self.step_rows:
            self.steps_box.addWidget(r)

    def edited(self) -> auto.Automation:
        days = [i for i, box in enumerate(self.days) if box.isChecked()]
        a = auto.Automation(self.name.text().strip() or "Automation", self.trigger.currentData(),
                            self.value.currentText().strip(), [r.step() for r in self.step_rows if r.step()["value"]],
                            self.enabled.isChecked(), days)
        return auto.Automation.from_dict(a.to_dict())

    def _save(self) -> None:
        if self.current < 0:
            return
        a = self.edited()
        problem = a.problem()
        self.items[self.current] = a
        auto.save(self.settings, self.items)
        self._fill_list(self.current)
        self.status.setText(f"Saved, but not ready: {problem}." if problem else "Saved.")

    def _test(self) -> None:
        a = self.edited()
        problem = a.problem()
        if problem:
            return self.status.setText(f"Not ready: {problem}.")
        if self.engine is None:
            return self.status.setText("Automations aren't running here.")
        self.engine.run(a, force=True)
        self.status.setText(f"Running “{a.name}” now.")

    def _delete(self) -> None:
        if self.current < 0:
            return
        a = self.items[self.current]
        if QMessageBox.question(self, "Delete automation", f"Delete “{a.name}”?") \
                != QMessageBox.StandardButton.Yes:
            return
        del self.items[self.current]
        auto.save(self.settings, self.items)
        self._fill_list(self.current)
