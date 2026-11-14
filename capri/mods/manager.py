"""Installed mods: install / uninstall / enable / disable / import / export / update, and compatibility.

Mods live in her user folder, one folder each:  %LOCALAPPDATA%\\Capri\\mods\\<id>\\mod.json (+ its files).
Which ones are on, your ratings, and where each came from are in mods\\state.json.
A .capri-mod file is a zip of a mod's folder (mod.json at the top).
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .manifest import Manifest, ModError, check, fits, load, safe_path

log = logging.getLogger("capri")
EXT = ".capri-mod"


def default_root() -> Path:
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "mods"


@dataclass
class Installed:
    manifest: Manifest
    folder: Path
    enabled: bool
    source: str = ""                # "store", "file" or "made here"
    rating: int = 0                 # your stars, 0-5

    @property
    def id(self) -> str:
        return self.manifest.id


class ModManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.changed: list[Callable[[], None]] = []      # called after anything changes (effects re-read)
        self._state = self._read_state()

    # -- state ----------------------------------------------------------------------------------------------
    def _read_state(self) -> dict:
        try:
            data = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            (self.root / "state.json").write_text(json.dumps(self._state, indent=1), encoding="utf-8")
        except OSError as exc:
            log.warning("mods: couldn't save state: %s", exc)

    def _entry(self, mod_id: str) -> dict:
        return self._state.setdefault("mods", {}).setdefault(mod_id, {})

    def _notify(self) -> None:
        for fn in list(self.changed):
            try:
                fn()
            except Exception:
                log.exception("mods: a listener failed")

    # -- reading ------------------------------------------------------------------------------------------------
    def installed(self) -> list[Installed]:
        out = []
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            try:
                manifest = load((folder / "mod.json").read_text(encoding="utf-8"), _files_of(folder))
            except (OSError, ModError) as exc:
                log.info("mods: skipped %s (%s)", folder.name, exc)
                continue
            e = self._state.get("mods", {}).get(manifest.id, {})
            out.append(Installed(manifest, folder, bool(e.get("enabled", False)), str(e.get("source", "")),
                                 int(e.get("rating", 0) or 0)))
        return out

    def get(self, mod_id: str) -> Installed | None:
        return next((m for m in self.installed() if m.id == mod_id), None)

    def enabled(self) -> list[Installed]:
        """The mods that are on and fit this Capri, in the order you turned them on."""
        mods = [m for m in self.installed() if m.enabled and fits(m.manifest.capri)]
        order = self._state.get("order", [])
        return sorted(mods, key=lambda m: order.index(m.id) if m.id in order else len(order))

    # -- installing ----------------------------------------------------------------------------------------------
    def install_bytes(self, data: bytes, source: str = "file", enable: bool = True) -> Installed:
        """Install (or update) a mod from a .capri-mod file's bytes. Everything is checked first; nothing in it is
        ever run. Raises ModError with the reason if it isn't a proper mod."""
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ModError("that isn't a .capri-mod file (it's not a zip)") from None
        with z:
            names = [i for i in z.infolist() if not i.is_dir()]
            prefix = ""
            if "mod.json" not in [i.filename for i in names]:      # zipped with its folder: mod.json one level down
                tops = {i.filename.split("/", 1)[0] for i in names}
                if len(tops) == 1 and f"{next(iter(tops))}/mod.json" in [i.filename for i in names]:
                    prefix = next(iter(tops)) + "/"
                else:
                    raise ModError("there's no mod.json in it")
            files: dict[str, int] = {}
            for info in names:
                rel = info.filename[len(prefix):] if info.filename.startswith(prefix) else info.filename
                if rel == "mod.json":
                    continue
                if not safe_path(rel):
                    raise ModError(f"it has a file with an unsafe name: {info.filename}")
                files[rel] = info.file_size
            manifest = check(_json(z.read(prefix + "mod.json")), files)
            if not fits(manifest.capri):
                raise ModError(f"{manifest.name} needs Capri {manifest.capri} (you have a different version)")
            target = self.root / manifest.id
            tmp = self.root / (manifest.id + ".installing")
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            try:
                (tmp / "mod.json").write_bytes(z.read(prefix + "mod.json"))
                for rel in files:
                    out = tmp / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    blob = z.read(prefix + rel)
                    if len(blob) != files[rel]:
                        raise ModError(f"\"{rel}\" is damaged")
                    out.write_bytes(blob)
                was_on = self._state.get("mods", {}).get(manifest.id, {}).get("enabled")
                shutil.rmtree(target, ignore_errors=True)
                tmp.rename(target)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
        e = self._entry(manifest.id)
        e["source"] = source
        e["version"] = manifest.version
        if was_on is None and enable:
            for other in self.enabled():                     # (2.4.1) what it clashes with goes off, as when
                if other.id != manifest.id and clash(manifest, other.manifest):   # you switch it on yourself
                    self._set_enabled(other.id, False)
            self._set_enabled(manifest.id, True)
        self._save_state()
        log.info("mods: installed %s (%s)", manifest.label, source)
        self._notify()
        return self.get(manifest.id)

    def install_file(self, path: str | Path) -> Installed:
        p = Path(path)
        if p.is_dir():
            return self.install_bytes(pack_folder(p), source="file")
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise ModError(f"couldn't read it ({exc.strerror or exc})") from None
        return self.install_bytes(data, source="file")

    def uninstall(self, mod_id: str) -> bool:
        """Remove a mod completely (the caller asks you first)."""
        folder = self.root / mod_id
        if not folder.is_dir() or not safe_path(mod_id):
            return False
        shutil.rmtree(folder, ignore_errors=True)
        self._state.get("mods", {}).pop(mod_id, None)
        if mod_id in self._state.get("order", []):
            self._state["order"].remove(mod_id)
        self._save_state()
        log.info("mods: uninstalled %s", mod_id)
        self._notify()
        return True

    # -- on / off -------------------------------------------------------------------------------------------------
    def _set_enabled(self, mod_id: str, on: bool) -> None:
        self._entry(mod_id)["enabled"] = on
        order = self._state.setdefault("order", [])
        if mod_id in order:
            order.remove(mod_id)
        if on:
            order.append(mod_id)

    def set_enabled(self, mod_id: str, on: bool) -> list[str]:
        """Turn a mod on or off. Turning one on turns off what it conflicts with (another skin, a cosmetic in the
        same slot, a mod it names in "conflicts"); returns the names of the ones it turned off."""
        mod = self.get(mod_id)
        if mod is None:
            return []
        turned_off = []
        if on:
            for other in self.enabled():
                if other.id != mod_id and clash(mod.manifest, other.manifest):
                    self._set_enabled(other.id, False)
                    turned_off.append(other.manifest.name)
        self._set_enabled(mod_id, on)
        self._save_state()
        self._notify()
        return turned_off

    def rate(self, mod_id: str, stars: int) -> None:
        self._entry(mod_id)["rating"] = max(0, min(5, int(stars)))
        self._save_state()

    # -- sharing --------------------------------------------------------------------------------------------------
    def export(self, mod_id: str, dest: str | Path) -> Path:
        """Save a mod as a .capri-mod file to share."""
        mod = self.get(mod_id)
        if mod is None:
            raise ModError("that mod isn't installed")
        dest = Path(dest)
        if dest.suffix.lower() != EXT:
            dest = dest.with_suffix(EXT)
        dest.write_bytes(pack_folder(mod.folder))
        return dest

    def compatibility(self) -> list[str]:
        """Plain-words problems with the installed mods (empty = all good)."""
        problems = []
        mods = self.installed()
        for m in mods:
            if not fits(m.manifest.capri):
                problems.append(f"{m.manifest.name} needs Capri {m.manifest.capri} - it's switched off for now.")
        on = [m for m in mods if m.enabled]
        for i, a in enumerate(on):
            for b in on[i + 1:]:
                if clash(a.manifest, b.manifest):
                    problems.append(f"{a.manifest.name} and {b.manifest.name} can't both be on (the newer one wins).")
        return problems

    def version_of(self, mod_id: str) -> str:
        mod = self.get(mod_id)
        return mod.manifest.version if mod else ""


def clash(a: Manifest, b: Manifest) -> bool:
    """Two mods that can't be on together."""
    if a.id in b.conflicts or b.id in a.conflicts:
        return True
    if a.type == b.type == "skin":
        return True
    if a.type == b.type == "sounds":
        return set(a.data.get("sounds", {})) & set(b.data.get("sounds", {})) != set()
    if a.type == b.type == "cosmetic":
        slots_a = {i.get("slot", "other") for i in a.data.get("items", [])} - {"other"}
        slots_b = {i.get("slot", "other") for i in b.data.get("items", [])} - {"other"}
        return bool(slots_a & slots_b)
    if a.type == b.type == "look":                   # two looks that set the same thing (two body styles...)
        return bool(set(a.data.get("settings", {})) & set(b.data.get("settings", {})))
    if a.type == b.type == "personality":
        return True                                      # she has one personality at a time (2.4.1)
    return False


def _json(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ModError(f"mod.json isn't valid JSON ({exc})") from None


def _files_of(folder: Path) -> dict[str, int]:
    return {p.relative_to(folder).as_posix(): p.stat().st_size for p in folder.rglob("*")
            if p.is_file() and p.name != "mod.json"}


def pack_folder(folder: Path) -> bytes:
    """A mod folder -> .capri-mod bytes (checked first)."""
    folder = Path(folder)
    try:
        text = (folder / "mod.json").read_text(encoding="utf-8")
    except OSError:
        raise ModError("there's no mod.json in that folder") from None
    files = _files_of(folder)
    load(text, files)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mod.json", text)
        for rel in sorted(files):
            z.write(folder / rel, rel)
    return buf.getvalue()


def validate_folder(folder: Path) -> tuple[bool, str]:
    """For mod makers: (ok, a report in plain words)."""
    try:
        m = load((Path(folder) / "mod.json").read_text(encoding="utf-8"), _files_of(Path(folder)))
    except OSError:
        return False, "There's no mod.json in that folder."
    except ModError as exc:
        return False, f"Not ready yet: {exc}."
    note = "" if fits(m.capri) else f" (it says it needs Capri {m.capri} - this one won't use it)"
    return True, f"{m.label} ({m.type}) is a proper mod - ready to install or share{note}."
