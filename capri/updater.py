"""Updating herself from GitHub releases.

Once a day (and when you ask: "check for updates", or the menu) she asks GitHub what the newest
release of Capri is. If it's newer than her:

* Installed Capri (Capri.exe): she downloads the new Capri-Setup-<version>.exe in the background,
  checks it's exactly the file GitHub lists (size, and its SHA-256 when GitHub gives one), and
  installs it the next time she starts - quietly, then starts again. "Update now" does it straight
  away. With Settings -> PC & chat -> "Update automatically" off, she only tells you.
* Running from the code (run.bat / run.sh): she can't replace your folder, so she tells you and
  opens the release page.

Only this project's own release files are ever downloaded (github.com/kamome513/capri-companion),
and nothing about you is sent - it's the same request a browser makes to look at the page.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__

log = logging.getLogger("capri")

REPO = "kamome513/capri-companion"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
DOWNLOADS = f"https://github.com/{REPO}/releases/download/"
ASSET = re.compile(r"^Capri-Setup-[\w.\-]+\.exe$", re.I)
CHECK_EVERY = 24 * 3600


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.36.0' / 'capri 1.36' / '1.35.0' -> (1, 36, 0). () if there's no version in it."""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    width = max(len(a), len(b))
    return bool(a) and a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def frozen() -> bool:
    """The installed Capri.exe (not run from the code)."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


@dataclass
class Update:
    version: str
    url: str            # the installer, on github.com
    name: str
    size: int
    sha256: str = ""    # from GitHub's asset digest, when it has one
    page: str = PAGE


def _get_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"Capri/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def check(fetch: Callable[[str], dict] = _get_json, current: str = __version__) -> Update | None:
    """The newest release if it's newer than this Capri, else None. Blocking (network)."""
    info = fetch(API)
    if not isinstance(info, dict) or info.get("draft") or info.get("prerelease"):
        return None
    version = ".".join(map(str, parse_version(info.get("tag_name", "") or info.get("name", ""))))
    if not version or not newer(version, current):
        return None
    for asset in info.get("assets") or []:
        name, url = str(asset.get("name", "")), str(asset.get("browser_download_url", ""))
        if ASSET.match(name) and url.startswith(DOWNLOADS):
            digest = str(asset.get("digest") or "")
            return Update(version, url, name, int(asset.get("size") or 0),
                          digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
                          str(info.get("html_url") or PAGE))
    return Update(version, "", "", 0, "", str(info.get("html_url") or PAGE))    # no installer attached (yet)


def updates_dir() -> Path:
    from .voice.model import user_models_dir
    return user_models_dir().parent / "updates"


def download(update: Update, folder: Path | None = None, progress: Callable[[int, int], None] | None = None,
             opener=urllib.request.urlopen) -> Path:
    """Fetch the installer and check it. Returns its path. Blocking (network)."""
    if not update.url.startswith(DOWNLOADS) or not ASSET.match(update.name):
        raise ValueError("not one of Capri's own release files")
    folder = folder or updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / update.name
    part = target.with_suffix(".part")
    digest = hashlib.sha256()
    done = 0
    req = urllib.request.Request(update.url, headers={"User-Agent": f"Capri/{__version__}"})
    with opener(req, timeout=60) as response, open(part, "wb") as out:
        total = int(response.headers.get("Content-Length") or update.size or 0)
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    problem = ""
    if update.size and done != update.size:
        problem = f"the download is the wrong size ({done} of {update.size} bytes)"
    elif update.sha256 and digest.hexdigest() != update.sha256:
        problem = "the download doesn't match GitHub's checksum"
    if problem:
        part.unlink(missing_ok=True)
        raise OSError(problem)
    os.replace(part, target)
    (folder / "ready.json").write_text(json.dumps({"version": update.version, "file": update.name,
                                                   "sha256": digest.hexdigest()}), encoding="utf-8")
    log.info("update: Capri %s downloaded and checked (%s)", update.version, target)
    return target


def ready(folder: Path | None = None, current: str = __version__) -> tuple[str, Path] | None:
    """(version, installer) of a checked download that's newer than this Capri, else None.
    Old leftovers are cleaned up."""
    folder = folder or updates_dir()
    try:
        info = json.loads((folder / "ready.json").read_text(encoding="utf-8"))
        path = folder / str(info["file"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not newer(str(info.get("version", "")), current) or not ASSET.match(path.name) or not path.is_file():
        clear(folder)
        return None
    if info.get("sha256"):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != info["sha256"]:
            clear(folder)
            return None
    return str(info["version"]), path


def clear(folder: Path | None = None) -> None:
    folder = folder or updates_dir()
    if not folder.is_dir():
        return
    for p in folder.iterdir():
        if p.is_file() and (ASSET.match(p.name) or p.suffix == ".part" or p.name == "ready.json"):
            try:
                p.unlink()
            except OSError:
                pass


def install(installer: Path, run: Callable = subprocess.Popen) -> bool:
    """Start the installer quietly; it closes this Capri, updates her and starts her again.
    The caller quits Capri straight after. False if it couldn't start."""
    if not frozen():
        return False
    try:
        run([str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/update=1"],
            close_fds=True, creationflags=0x00000008)           # DETACHED_PROCESS: outlives Capri
        return True
    except OSError as exc:
        log.warning("update: couldn't start the installer: %s", exc)
        return False
