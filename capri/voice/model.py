"""Finding (and downloading) the offline Vosk speech model."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MODEL_NAME = "vosk-model-small-en-us-0.15"     # ~40 MB, English, runs fine on any CPU
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
# Optional, more accurate (fewer misheard words), ~128 MB download, more memory. Used when present.
BETTER_MODEL = "vosk-model-en-us-0.22-lgraph"
BETTER_URL = f"https://alphacephei.com/vosk/models/{BETTER_MODEL}.zip"

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
MODELS_DIR = PROJECT_ROOT / "models"


def user_models_dir() -> Path:
    """Where she downloads the model herself on first start (the app's folder may not be writable):
    %LOCALAPPDATA%\\Capri\\models on Windows, ~/.local/share/capri/models elsewhere."""
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Capri" / "models"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "capri" / "models"


def _looks_like_model(path: Path) -> bool:
    return (path / "am").is_dir() and (path / "conf").is_dir()


def find_model() -> Path | None:
    """Model folder: $CAPRI_VOSK_MODEL, else models/<any vosk model> in the project."""
    override = os.environ.get("CAPRI_VOSK_MODEL")
    if override:
        return Path(override) if _looks_like_model(Path(override)) else None
    folders = [MODELS_DIR, user_models_dir()]
    for name in (BETTER_MODEL, MODEL_NAME):          # the accurate one wins once downloaded
        for folder in folders:
            if _looks_like_model(folder / name):
                return folder / name
    for folder in folders:                           # any other Vosk model the user dropped in
        if folder.is_dir():
            for candidate in sorted(folder.iterdir()):
                if candidate.is_dir() and _looks_like_model(candidate):
                    return candidate
    return None


def download_model(dest: Path = MODELS_DIR, url: str = MODEL_URL, quiet: bool = False) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.zip"

        def progress(blocks: int, block_size: int, total: int) -> None:
            if not quiet and total > 0:
                done = min(blocks * block_size, total)
                print(f"\r  {done / 1e6:5.1f} / {total / 1e6:.1f} MB", end="", flush=True)

        if not quiet:
            print(f"Downloading {url}")
        urllib.request.urlretrieve(url, archive, progress)
        if not quiet:
            print()
        with zipfile.ZipFile(archive) as zf:
            root = Path(tmp) / "unpacked"
            for member in zf.namelist():   # refuse paths that escape the folder
                if member.startswith("/") or ".." in Path(member).parts:
                    raise RuntimeError(f"unsafe path in archive: {member}")
            zf.extractall(root)
        inner = next((p for p in root.iterdir() if p.is_dir() and _looks_like_model(p)), None)
        if inner is None:
            raise RuntimeError("downloaded archive does not contain a Vosk model")
        target = dest / inner.name
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(inner), target)
    return target
