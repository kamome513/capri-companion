"""Log file + crash catching.

The packaged Capri.exe has no console, so warnings and errors go to
%LOCALAPPDATA%\\Capri\\capri.log (3 x 1 MB, rotated). An unexpected error
is logged with its traceback instead of silently killing her.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QStandardPaths

log = logging.getLogger("capri")


def log_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))


def setup(on_crash: Callable[[str], None] | None = None) -> Path:
    path = log_dir() / "capri.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:                       # running from a console (run.bat): show there too
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("[capri] %(message)s"))
        root.addHandler(console)

    def excepthook(kind, value, tb) -> None:
        log.error("Unexpected error", exc_info=(kind, value, tb))
        if on_crash is not None:
            try:
                on_crash(f"{kind.__name__}: {value}")
            except Exception:
                pass

    sys.excepthook = excepthook
    threading.excepthook = lambda args: excepthook(args.exc_type, args.exc_value, args.exc_traceback)
    global last_crash
    last_crash = _unreported_crash(path.parent / "crash.log")
    if last_crash:
        log.error("Capri crashed last time:\n%s", last_crash[-4000:])
    _native_crashes(path.parent / "crash.log")
    _qt_messages()
    return path


last_crash = ""          # what crash.log says about a crash since the last start (shown once, then marked seen)


def _unreported_crash(where: Path) -> str:
    """A crash written to crash.log since she last mentioned one ("" if none). Marks it as mentioned."""
    seen = where.with_name("crash.seen")
    try:
        size = where.stat().st_size
    except OSError:
        return ""
    try:
        told = int(seen.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        told = 0
    if size <= told:
        return ""
    try:
        with open(where, "rb") as f:
            f.seek(told if told < size else 0)
            text = f.read().decode("utf-8", "replace").strip()
        seen.write_text(str(size), encoding="utf-8")
    except OSError:
        return ""
    return text


_crash_file = None


def _native_crashes(where: Path) -> None:
    """A hard crash (Qt aborting, a segfault) never reaches Python's error handling: have Python write where it
    was to crash.log on the way down, so the next one can be fixed."""
    global _crash_file
    try:
        import faulthandler
        _crash_file = open(where, "a", encoding="utf-8")
        faulthandler.enable(_crash_file, all_threads=True)
    except Exception:
        pass


def _qt_messages() -> None:
    """Qt's own warnings and errors (e.g. "The X11 connection broke") into capri.log, not just the console."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:
        return
    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}
    qt_log = logging.getLogger("capri.qt")

    def handler(kind, context, message) -> None:
        level = levels.get(kind, logging.WARNING)
        if level >= logging.WARNING:
            qt_log.log(level, "Qt: %s", message)
            if level >= logging.CRITICAL:
                for h in logging.getLogger().handlers:
                    try:
                        h.flush()
                    except Exception:
                        pass
    qInstallMessageHandler(handler)
