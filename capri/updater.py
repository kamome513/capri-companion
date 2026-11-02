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
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__

log = logging.getLogger("capri")

REPO = "kamome513/capri-companion"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
# A tiny file attached to every release (the release workflow makes it). It comes from GitHub's normal
# download servers, which - unlike the API above (60 questions an hour per internet connection) - don't
# say no when you check a lot. The API is only the backup.
LATEST_JSON = f"https://github.com/{REPO}/releases/latest/download/latest.json"
MAX_TRIES = 2              # the same update not taking twice at start-up: stop and say so (no loop)
INSTALLING_SECONDS = 120   # an installer started this recently is still running: don't start another
PAGE = f"https://github.com/{REPO}/releases/latest"
DOWNLOADS = f"https://github.com/{REPO}/releases/download/"
WINDOWS_ASSET = re.compile(r"^Capri-Setup-[\w.\-]+\.exe$", re.I)
LINUX_ASSET = re.compile(r"^Capri-x86_64\.AppImage$")      # Linux: one AppImage, same name every release
ASSET = WINDOWS_ASSET
LINUX = sys.platform.startswith("linux")             # which release file this Capri updates from
CHECK_EVERY = 24 * 3600


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.36.0' / 'capri 1.36' / '1.35.0' -> (1, 36, 0). () if there's no version in it."""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    width = max(len(a), len(b))
    return bool(a) and a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def appimage() -> str:
    """Linux: the AppImage file Capri runs from ("" otherwise)."""
    return os.environ.get("APPIMAGE", "") if LINUX else ""


def frozen() -> bool:
    """A Capri that can update itself: the installed Capri.exe, or the Linux AppImage (not run from the code)."""
    if LINUX:
        path = appimage()
        return bool(path) and os.path.isfile(path) and os.access(os.path.dirname(path) or ".", os.W_OK)
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def asset_pattern():
    return LINUX_ASSET if LINUX else WINDOWS_ASSET


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
        return json.loads(r.read().decode("utf-8-sig"))


def _from_latest_json(info: dict, current: str) -> Update | None | bool:
    """latest.json -> an Update / None (up to date) / False (not a latest.json - ask the API)."""
    if not isinstance(info, dict) or "version" not in info or "file" not in info:
        return False
    if LINUX:                                            # the AppImage's own entry
        section = info.get("linux")
        if not isinstance(section, dict) or "file" not in section:
            return False
        info = {"version": info["version"], **section}
    version = ".".join(map(str, parse_version(str(info["version"]))))
    if not version:
        return False
    if not newer(version, current):
        return None
    name = str(info["file"])
    if not asset_pattern().match(name):
        return False
    return Update(version, f"{DOWNLOADS}v{version}/{name}", name, int(info.get("size") or 0),
                  str(info.get("sha256") or "").lower(), f"https://github.com/{REPO}/releases/tag/v{version}")


def check(fetch: Callable[[str], dict] = _get_json, current: str = __version__) -> Update | None:
    """The newest release if it's newer than this Capri, else None. Blocking (network).
    Raises the first problem if neither latest.json nor the API answered."""
    problem: Exception | None = None
    try:
        found = _from_latest_json(fetch(LATEST_JSON), current)
        if found is not False:
            return found
    except Exception as exc:                  # (releases before 1.36.3 have no latest.json)
        problem = exc
        log.info("update: latest.json unavailable (%s) - asking GitHub's API", exc)
    try:
        info = fetch(API)
    except Exception as exc:
        log.info("update: GitHub's API didn't answer either (%s; latest.json: %s)", exc, problem)
        raise
    if not isinstance(info, dict) or info.get("draft") or info.get("prerelease"):
        return None
    version = ".".join(map(str, parse_version(info.get("tag_name", "") or info.get("name", ""))))
    if not version or not newer(version, current):
        return None
    for asset in info.get("assets") or []:
        name, url = str(asset.get("name", "")), str(asset.get("browser_download_url", ""))
        if asset_pattern().match(name) and url.startswith(DOWNLOADS):
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
    if not update.url.startswith(DOWNLOADS) or not asset_pattern().match(update.name):
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
    if not newer(str(info.get("version", "")), current) or not asset_pattern().match(path.name) or not path.is_file():
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
        if p.is_file() and (WINDOWS_ASSET.match(p.name) or LINUX_ASSET.match(p.name) or p.suffix == ".part"
                            or p.name == "ready.json"):
            try:
                p.unlink()
            except OSError:
                pass


def _state_file(folder: Path | None = None) -> Path:
    return (folder or updates_dir()) / "ready.json"


def tries(folder: Path | None = None) -> tuple[int, float]:
    """(times the waiting update was started, when the last one started)."""
    try:
        info = json.loads(_state_file(folder).read_text(encoding="utf-8"))
        return int(info.get("tries", 0)), float(info.get("started", 0.0))
    except (OSError, ValueError, TypeError):
        return 0, 0.0


def _note_try(folder: Path | None = None, now: float | None = None) -> None:
    path = _state_file(folder)
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        info["tries"] = int(info.get("tries", 0)) + 1
        info["started"] = time.time() if now is None else now
        path.write_text(json.dumps(info), encoding="utf-8")
    except (OSError, ValueError, TypeError):
        pass


def _install_appimage(new: Path, run: Callable, folder: Path | None) -> bool:
    """Linux: put the checked new AppImage in place of the one you run (Linux lets you replace a running
    program's file), then start it. It waits for this Capri to close first (--after-update)."""
    target = appimage()
    _note_try(folder or new.parent)
    tmp = target + ".new"
    try:
        shutil.copyfile(new, tmp)
        os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    except OSError as exc:
        log.warning("update: couldn't replace %s: %s", target, exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    try:
        run([target, "--after-update"], close_fds=True, start_new_session=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("update: replaced, but couldn't start the new Capri: %s", exc)
    clear(folder or new.parent)                     # installed: nothing waiting any more
    return True


def installer_running() -> bool:
    """Is a Capri-Setup installer running right now? (Inno Setup runs as Capri-Setup-x.exe / .tmp)"""
    try:
        import psutil
    except ImportError:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower().startswith("capri-setup"):
                return True
        except Exception:
            continue
    return False


def install(installer: Path, run: Callable = subprocess.Popen, folder: Path | None = None,
            app_dir: str | None = None) -> bool:
    """Start the installer quietly; it waits for this Capri to close, updates the copy you're running
    (her own folder, wherever that is) and starts her again. The caller quits Capri straight after.
    False if it couldn't start."""
    if not frozen():
        return False
    if LINUX:
        return _install_appimage(installer, run, folder)
    app_dir = app_dir or os.path.dirname(sys.executable)
    _note_try(folder or installer.parent)
    try:
        run([str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/update=1",
             f"/DIR={app_dir}"], close_fds=True, creationflags=0x00000008)   # DETACHED_PROCESS: outlives Capri
        return True
    except OSError as exc:
        log.warning("update: couldn't start the installer: %s", exc)
        return False
