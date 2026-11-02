"""API keys and tokens, kept apart from settings.json so they're never shared by accident.

Stored in %LOCALAPPDATA%\\Capri\\secrets.json (your Windows user folder).
Never logged, never shown in the panel.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_lock = threading.Lock()


def path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    return Path(base) / "secrets.json"


def _read() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def get(key: str) -> str:
    with _lock:
        value = _read().get(key, "")
        return value if isinstance(value, str) else ""


def set_many(values: dict[str, str]) -> None:
    with _lock:
        data = _read()
        data.update(values)
        _write(data)


def delete(*keys: str) -> None:
    with _lock:
        data = _read()
        for key in keys:
            data.pop(key, None)
        _write(data)
