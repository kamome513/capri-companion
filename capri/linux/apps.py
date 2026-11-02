"""Linux apps: found through their menu entries (.desktop files), launched without a shell.

Where they come from (XDG, plus Flatpak and Snap):
  ~/.local/share/applications, /usr/local/share/applications, /usr/share/applications,
  ~/.local/share/flatpak/exports/share/applications, /var/lib/flatpak/exports/share/applications,
  /var/lib/snapd/desktop/applications - and $XDG_DATA_DIRS.

Launching reads the entry's Exec line by the Desktop Entry rules (quotes, escapes, % codes) into an
argument list and starts it directly - the same thing your app menu does. Nothing said and nothing an
AI writes ever becomes part of it: only the entry's own Exec line runs.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKIP_NAMES = re.compile(r"uninstall|readme|release notes|\bhelp\b|manual|documentation|license|changelog|"
                        r"\bsettings daemon\b|\bfor developers\b", re.I)


def application_dirs(env: dict | None = None) -> list[Path]:
    env = os.environ if env is None else env
    home = Path(env.get("HOME") or Path.home())
    data_home = Path(env.get("XDG_DATA_HOME") or home / ".local" / "share")
    dirs = [data_home / "applications", data_home / "flatpak" / "exports" / "share" / "applications"]
    for base in (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if base:
            dirs.append(Path(base) / "applications")
    dirs += [Path("/var/lib/flatpak/exports/share/applications"), Path("/var/lib/snapd/desktop/applications"),
             Path("/usr/local/share/applications"), Path("/usr/share/applications")]
    seen, out = set(), []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


@dataclass(frozen=True)
class DesktopEntry:
    name: str
    path: Path
    exec_line: str
    categories: tuple[str, ...] = ()
    wm_class: str = ""
    terminal: bool = False
    workdir: str = ""
    generic: str = ""
    keywords: tuple[str, ...] = field(default=())

    @property
    def is_game(self) -> bool:
        return "Game" in self.categories

    def argv(self) -> list[str]:
        return exec_argv(self.exec_line, self.path, self.name)

    def program(self) -> Path | None:
        """The program it runs, resolved ("firefox" -> /usr/lib/firefox/firefox), or None (Flatpak...)."""
        argv = self.argv()
        if not argv:
            return None
        first = argv[0]
        if Path(first).name in ("env", "flatpak", "snap", "sh", "bash", "gtk-launch", "gio"):
            return None
        found = shutil.which(first) if not os.path.isabs(first) else first
        if not found:
            return None
        try:
            return Path(os.path.realpath(found))
        except OSError:
            return Path(found)

    def process_names(self) -> tuple[str, ...]:
        """Names its processes / windows are likely to have: the program's file name, StartupWMClass,
        and for Flatpak / Snap the app's own name (com.discordapp.Discord -> discord)."""
        names = set()
        argv = self.argv()
        if self.wm_class:
            names.add(self.wm_class.lower())
        if argv:
            names.add(Path(argv[0]).name.lower())
            prog = self.program()
            if prog is not None:
                names.add(prog.name.lower())
            if Path(argv[0]).name in ("flatpak", "snap"):
                for arg in argv[1:]:
                    if arg.startswith("--command="):
                        names.add(Path(arg.split("=", 1)[1]).name.lower())
                    elif not arg.startswith("-") and arg != "run":
                        names.add(arg.split(".")[-1].lower())
                        break
        names.discard("")
        return tuple(sorted(names - {"env", "flatpak", "snap", "sh", "bash"}))


def _unescape_value(value: str) -> str:
    """The .desktop string escapes: \\s \\n \\t \\r \\\\."""
    out, i = [], 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}.get(nxt, "\\" + nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_desktop_file(path: Path, lang: str = "") -> DesktopEntry | None:
    """The [Desktop Entry] of a file, if it's an app you'd launch (not hidden, its program exists)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields: dict[str, str] = {}
    in_main = False
    lang = lang or (os.environ.get("LANG", "").split(".")[0])
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            in_main = line == "[Desktop Entry]"
            continue
        if not in_main or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if "[" in key:                                    # Name[de]=...: only your language
            base, loc = key[:-1].split("[", 1) if key.endswith("]") else (key, "")
            if loc and lang and (loc == lang or loc == lang.split("_")[0]) and base in ("Name", "GenericName"):
                fields[base + "@local"] = value.strip()
            continue
        fields[key] = value.strip()
    if fields.get("Type", "Application") != "Application":
        return None
    if fields.get("NoDisplay", "").lower() == "true" or fields.get("Hidden", "").lower() == "true":
        return None
    exec_line = _unescape_value(fields.get("Exec", ""))
    name = fields.get("Name@local") or fields.get("Name", "")
    if not exec_line or not name or SKIP_NAMES.search(name):
        return None
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if fields.get("OnlyShowIn") and desktop and not set(desktop.split(":")) & set(fields["OnlyShowIn"].split(";")):
        return None
    if fields.get("NotShowIn") and desktop and set(desktop.split(":")) & set(fields["NotShowIn"].split(";")):
        return None
    try_exec = fields.get("TryExec", "")
    if try_exec and not (shutil.which(try_exec) if not os.path.isabs(try_exec) else os.access(try_exec, os.X_OK)):
        return None
    return DesktopEntry(name=name, path=path, exec_line=exec_line,
                        categories=tuple(c for c in fields.get("Categories", "").split(";") if c),
                        wm_class=fields.get("StartupWMClass", ""), terminal=fields.get("Terminal", "").lower() == "true",
                        workdir=fields.get("Path", ""), generic=fields.get("GenericName@local") or fields.get("GenericName", ""),
                        keywords=tuple(k for k in fields.get("Keywords", "").split(";") if k))


def exec_argv(exec_line: str, path: Path | None = None, name: str = "") -> list[str]:
    """An Exec line -> argument list, by the Desktop Entry rules: double quotes group (with \\" \\` \\$ \\\\
    escapes inside), % codes for files/URLs are dropped (she opens apps, not files), %% is a %."""
    args, cur, quoted, have, i = [], [], False, False, 0
    s = exec_line
    while i < len(s):
        ch = s[i]
        if quoted:
            if ch == "\\" and i + 1 < len(s) and s[i + 1] in '"`$\\':
                cur.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                quoted = False
            else:
                cur.append(ch)
        elif ch == '"':
            quoted, have = True, True
        elif ch.isspace():
            if cur or have:
                args.append("".join(cur))
            cur, have = [], False
        else:
            cur.append(ch)
        i += 1
    if cur or have:
        args.append("".join(cur))
    out = []
    for arg in args:
        if arg in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m", "%i"):
            continue
        if arg == "%c":
            out.append(name)
            continue
        if arg == "%k":
            out.append(str(path or ""))
            continue
        cleaned = re.sub(r"%(%|[fFuUdDnNvmick])", lambda m: "%" if m.group(1) == "%" else "", arg)
        if cleaned or cleaned == arg:                     # keep a deliberate "" (not one that was only a % code)
            out.append(cleaned)
    return out


def installed_entries(dirs: list[Path] | None = None) -> list[DesktopEntry]:
    """Every app in your menus. A user's own entry wins over the system one with the same id."""
    found: dict[str, DesktopEntry] = {}
    for base in dirs if dirs is not None else application_dirs():
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.desktop")):
            desktop_id = str(path.relative_to(base)).replace(os.sep, "-")
            if desktop_id in found:
                continue
            entry = parse_desktop_file(path)
            if entry is not None:
                found[desktop_id] = entry
    by_name: dict[str, DesktopEntry] = {}
    for entry in found.values():
        by_name.setdefault(entry.name.lower(), entry)
    return sorted(by_name.values(), key=lambda e: e.name.lower())


def launch_entry(entry: DesktopEntry, popen=subprocess.Popen) -> None:
    """Start an app from its menu entry, detached from Capri."""
    argv = entry.argv()
    if not argv:
        raise OSError(f"{entry.name} has nothing to run")
    if entry.terminal:
        term = next((t for t in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "kitty",
                                 "alacritty", "xterm") if shutil.which(t)), None)
        if term is None:
            raise OSError(f"{entry.name} needs a terminal and none was found")
        argv = [term, "-e", *argv] if term != "gnome-terminal" else [term, "--", *argv]
    cwd = entry.workdir if entry.workdir and os.path.isdir(entry.workdir) else str(Path.home())
    popen(argv, cwd=cwd, start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch_desktop_file(path: str | Path, popen=subprocess.Popen) -> None:
    entry = parse_desktop_file(Path(path))
    if entry is None:
        raise OSError(f"{Path(path).name} isn't an app she can start")
    launch_entry(entry, popen)
