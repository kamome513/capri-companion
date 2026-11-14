"""The mod store: the mods that come with Capri (assets/mods/*.capri-mod) plus the online list.

The online list is a JSON file (Settings: mod_index_url, by default the mods/index.json on Capri's GitHub):
    {"mods": [{"id", "name", "version", "type", "category", "author", "description", "rating", "ratings",
               "url", "sha256", "size", "preview_url", "capri"}]}
Downloads only come from GitHub (https) and must match their sha256 and size - and every mod is checked again
by the manager before it's installed. If the list can't be reached, the store shows the built-in mods.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .manifest import ModError, fits, load, parse_version

log = logging.getLogger("capri")
DEFAULT_INDEX = "https://raw.githubusercontent.com/kamome513/capri-companion/main/mods/index.json"
ALLOWED_HOSTS = ("https://raw.githubusercontent.com/", "https://github.com/", "https://objects.githubusercontent.com/")
MAX_DOWNLOAD = 20_000_000


def builtin_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / "mods"


@dataclass
class Listing:
    id: str
    name: str
    version: str
    type: str
    category: str = ""
    author: str = ""
    description: str = ""
    rating: float = 0.0
    ratings: int = 0
    capri: str = ""
    tags: list = field(default_factory=list)
    url: str = ""                 # online mods: where to download it
    sha256: str = ""
    size: int = 0
    preview_url: str = ""
    file: Path | None = None      # built-in mods: the .capri-mod that comes with Capri
    preview: bytes = b""          # the preview picture (built-in: from the file; online: downloaded on demand)

    @property
    def builtin(self) -> bool:
        return self.file is not None

    @property
    def fits(self) -> bool:
        return fits(self.capri)


def _http_get(url: str, limit: int = MAX_DOWNLOAD, timeout: float = 20.0) -> bytes:
    import urllib.request
    if not url.startswith(ALLOWED_HOSTS):
        raise ModError("mods can only be downloaded from Capri's GitHub")
    from .. import __version__
    req = urllib.request.Request(url, headers={"User-Agent": f"Capri/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ModError("that download is too big for a mod")
    return data


class Store:
    def __init__(self, index_url: Callable[[], str] = lambda: DEFAULT_INDEX, fetch: Callable = _http_get,
                 folder: Path | None = None) -> None:
        self.index_url, self.fetch = index_url, fetch
        self.folder = folder or builtin_dir()
        self.online_error = ""

    def builtin(self) -> list[Listing]:
        out = []
        ratings = {}
        try:
            ratings = json.loads((self.folder / "catalog.json").read_text(encoding="utf-8")).get("ratings", {})
        except (OSError, ValueError, AttributeError):
            pass
        for f in sorted(self.folder.glob("*.capri-mod")) if self.folder.is_dir() else []:
            try:
                with zipfile.ZipFile(f) as z:
                    files = {i.filename: i.file_size for i in z.infolist() if not i.is_dir() and i.filename != "mod.json"}
                    m = load(z.read("mod.json").decode("utf-8-sig"), files)
                    preview = z.read(m.preview) if m.preview else b""
            except (OSError, KeyError, zipfile.BadZipFile, ModError, UnicodeDecodeError) as exc:
                log.info("mods: built-in %s skipped (%s)", f.name, exc)
                continue
            r = ratings.get(m.id, {})
            out.append(Listing(m.id, m.name, m.version, m.type, m.category, m.author, m.description,
                               float(r.get("rating", 0)), int(r.get("ratings", 0)), m.capri, m.tags,
                               file=f, preview=preview))
        return out

    def online(self) -> list[Listing]:
        """The online list (blocking). [] with self.online_error set if it can't be reached."""
        self.online_error = ""
        url = (self.index_url() or "").strip()
        if not url:
            return []
        try:
            data = json.loads(self.fetch(url, 2_000_000).decode("utf-8-sig"))
            items = data.get("mods", []) if isinstance(data, dict) else []
        except Exception as exc:
            self.online_error = f"the online mod list isn't reachable ({str(exc)[:60]}) - showing the built-in mods"
            return []
        out = []
        for d in items:
            if not isinstance(d, dict) or not str(d.get("url", "")).startswith(ALLOWED_HOSTS):
                continue
            try:
                out.append(Listing(str(d["id"]), str(d["name"]), str(d["version"]), str(d.get("type", "")),
                                   str(d.get("category", "")), str(d.get("author", "")),
                                   str(d.get("description", ""))[:400], float(d.get("rating", 0) or 0),
                                   int(d.get("ratings", 0) or 0), str(d.get("capri", "")),
                                   [str(t) for t in d.get("tags", [])][:8], url=str(d["url"]),
                                   sha256=str(d.get("sha256", "")).lower(), size=int(d.get("size", 0) or 0),
                                   preview_url=str(d.get("preview_url", ""))))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def listings(self, online: bool = True) -> list[Listing]:
        """Everything in the store: online mods replace a built-in one with the same id when they're newer."""
        found = {m.id: m for m in self.builtin()}
        for m in (self.online() if online else []):
            have = found.get(m.id)
            if have is None or parse_version(m.version) > parse_version(have.version):
                found[m.id] = m
        return sorted(found.values(), key=lambda m: (m.category, m.name.lower()))

    def download(self, listing: Listing) -> bytes:
        """The .capri-mod's bytes (built-in: from the file; online: downloaded and checked against its sha256)."""
        if listing.builtin:
            return listing.file.read_bytes()
        data = self.fetch(listing.url, MAX_DOWNLOAD)
        if listing.size and len(data) != listing.size:
            raise ModError("the download is the wrong size")
        if not listing.sha256 or hashlib.sha256(data).hexdigest() != listing.sha256:
            raise ModError("the download doesn't match its checksum, so it wasn't installed")
        return data

    def preview_of(self, listing: Listing) -> bytes:
        if listing.preview or not listing.preview_url:
            return listing.preview
        try:
            listing.preview = self.fetch(listing.preview_url, 2_000_000)
        except Exception:
            listing.preview = b""
        return listing.preview


def updates(store_listings: list[Listing], installed: dict[str, str]) -> list[Listing]:
    """The store mods that are newer than the version you have installed ({id: version})."""
    return [m for m in store_listings if m.id in installed and m.fits
            and parse_version(m.version) > parse_version(installed[m.id])]


def update_all(manager, store: Store, online: bool = True) -> list[str]:
    """Install every newer version of the store mods you have (blocking). Returns the names updated."""
    have = {m.id: m.manifest.version for m in manager.installed() if m.source in ("store", "")}
    done = []
    for listing in updates(store.listings(online), have):
        try:
            manager.install_bytes(store.download(listing), source="store", enable=False)
            done.append(f"{listing.name} {listing.version}")
        except Exception as exc:
            log.warning("mods: couldn't update %s: %s", listing.id, exc)
    return done


def preview_image(data: bytes):
    from PySide6.QtGui import QImage
    img = QImage()
    if data:
        img.loadFromData(data)
    return img


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in files.items():
            z.writestr(name, blob)
    return buf.getvalue()
