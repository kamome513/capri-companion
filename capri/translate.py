"""Her own built-in lines ("Opened Discord.", "Done!"...) in your language: translated by your AI the first time
each one comes up, then remembered on this PC (translations-<language>.json in her settings folder), so it's
instant after that. Without an AI she says them in English. Only her line is sent to the AI - nothing else.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from . import languages

log = logging.getLogger("capri")

PROMPT = ("Translate this short line from a desktop assistant into {language}. Keep names of apps, games, songs "
          "and people exactly as they are. Reply with ONLY the translation, no quotes:\n{line}")
WAIT_MS = 4000          # a translation that takes longer than this: she says it in English this time
MAX_CACHE = 3000


class LineTranslator(QObject):
    _ready = Signal(object, str)                # (then, translated) - back on the UI thread

    def __init__(self, brain_look: Callable[[str, str], object] | None, folder: Path | None,
                 available: Callable[[], bool] = lambda: True, background: bool = True) -> None:
        super().__init__()
        self.look, self.folder, self.available, self.background = brain_look, folder, available, background
        self._cache: dict[str, dict[str, str]] = {}
        self._ready.connect(lambda then, text: then(text))

    def _path(self, code: str) -> Path | None:
        return self.folder / f"translations-{code}.json" if self.folder is not None else None

    def _table(self, code: str) -> dict[str, str]:
        if code not in self._cache:
            table: dict[str, str] = {}
            path = self._path(code)
            try:
                if path is not None and path.is_file():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    table = {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
            except (OSError, ValueError):
                table = {}
            self._cache[code] = table
        return self._cache[code]

    def cached(self, line: str) -> str | None:
        if languages.english():
            return line
        return self._table(languages.current()).get(line)

    def wanted(self, line: str) -> bool:
        """Worth translating: not English mode, has letters, and there's an AI to ask."""
        return (not languages.english() and bool(re.search(r"[A-Za-z]{2}", line or "")) and self.look is not None
                and self.available())

    def translate(self, line: str, then: Callable[[str], None]) -> None:
        """then(line in your language) - from the memory at once, else asked of your AI (English if it fails or
        takes too long). Always calls `then` exactly once, on the UI thread."""
        known = self.cached(line)
        if known is not None or not self.wanted(line):
            return then(known if known is not None else line)
        code, lang = languages.current(), languages.get()
        done = threading.Event()

        def finish(text: str) -> None:
            if not done.is_set():
                done.set()
                then(text)
        if self.background:
            QTimer.singleShot(WAIT_MS, lambda: finish(line))

        def work() -> None:
            text = line
            try:
                reply = self.look(PROMPT.format(language=f"{lang.name} ({lang.native})", line=line), "")
                said = (getattr(reply, "text", "") or "").strip().strip('"').strip()
                if not getattr(reply, "error", False) and said:
                    text = said
                    self._remember(code, line, said)
            except Exception as exc:
                log.info("translate: couldn't translate a line: %s", exc)
            if self.background:
                self._ready.emit(finish, text)
            else:
                finish(text)
        if self.background:
            threading.Thread(target=work, daemon=True, name="capri-translate").start()
        else:
            work()

    def _remember(self, code: str, line: str, said: str) -> None:
        table = self._table(code)
        table[line] = said
        if len(table) > MAX_CACHE:
            for key in list(table)[: len(table) - MAX_CACHE]:
                del table[key]
        path = self._path(code)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(table, ensure_ascii=False, indent=0), encoding="utf-8")
        except OSError:
            pass
