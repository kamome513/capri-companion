"""Finding Ollama on this PC, wherever and however it was installed.

"It says I don't have Ollama installed, but I do" happened when Ollama was:
* installed for all users (C:\\Program Files\\Ollama) instead of the usual per-user folder,
* installed after Capri started (her PATH was from before, so `ollama` wasn't on it),
* moved to another address with OLLAMA_HOST (so 127.0.0.1:11434 didn't answer),
* installed with a different model than llama3.2 (she only looked for llama3.2).

So she looks everywhere: her own PATH, the PATH Windows has now, the usual folders, the
uninstall entries in the registry, and Ollama's running process. She reads OLLAMA_HOST for its
address, and uses whatever chat model you've got when llama3.2 isn't there. Read-only.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

DEFAULT_PORT = 11434
DEFAULT_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
EXE_NAMES = ("ollama.exe", "ollama app.exe", "ollama")
NOT_CHAT = ("embed", "bge-", "minilm", "rerank", "nomic-embed", "snowflake-arctic-embed", "mxbai")


# -- Windows' current environment (Capri's own copy can be older) ------------------------------
def _registry_env(name: str) -> str:
    """A user / system environment variable as Windows has it *now* (one set after Capri
    started isn't in her own os.environ)."""
    if sys.platform != "win32":
        return ""
    import winreg
    values = []
    for root, key in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                value, _kind = winreg.QueryValueEx(k, name)
                if value:
                    values.append(os.path.expandvars(str(value)))
        except OSError:
            continue
    return ";".join(values) if name.upper() == "PATH" else (values[0] if values else "")


def ollama_host(env: dict | None = None, registry: Callable[[str], str] = _registry_env) -> str:
    env = os.environ if env is None else env
    return (env.get("OLLAMA_HOST") or "").strip() or (registry("OLLAMA_HOST") or "").strip()


def url_from_host(host: str) -> str:
    """OLLAMA_HOST ('0.0.0.0', ':8080', '192.168.1.5:11434', 'http://box:11434') -> a URL to talk to."""
    host = (host or "").strip().strip('"')
    if not host:
        return DEFAULT_URL
    parts = urlsplit(host if "://" in host else "http://" + host)
    scheme = parts.scheme if parts.scheme in ("http", "https") else "http"
    try:
        port = parts.port or DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    name = parts.hostname or ""
    if name in ("", "0.0.0.0", "::", "*"):                 # "listen everywhere": we're on this PC
        name = "127.0.0.1"
    if ":" in name:
        name = f"[{name}]"
    return f"{scheme}://{name}:{port}"


def default_url(env: dict | None = None, registry: Callable[[str], str] = _registry_env) -> str:
    """Where Ollama answers: OLLAMA_HOST if you set one, else 127.0.0.1:11434."""
    return url_from_host(ollama_host(env, registry))


# -- the program ------------------------------------------------------------------------------
def _uninstall_folders() -> list[Path]:
    """InstallLocation / DisplayIcon folders of anything called Ollama in Windows' installed programs."""
    if sys.platform != "win32":
        return []
    import winreg
    out: list[Path] = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for base in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                     r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
            try:
                with winreg.OpenKey(root, base) as k:
                    count = winreg.QueryInfoKey(k)[0]
                    for i in range(count):
                        try:
                            with winreg.OpenKey(k, winreg.EnumKey(k, i)) as app:
                                name = str(winreg.QueryValueEx(app, "DisplayName")[0])
                                if not name.lower().startswith("ollama"):
                                    continue
                                for field in ("InstallLocation", "DisplayIcon"):
                                    try:
                                        value = str(winreg.QueryValueEx(app, field)[0]).split(",")[0].strip('"')
                                    except OSError:
                                        continue
                                    if value:
                                        p = Path(os.path.expandvars(value))
                                        out.append(p if p.suffix.lower() != ".exe" else p.parent)
                        except OSError:
                            continue
            except OSError:
                continue
    return out


def _running_exes() -> list[Path]:
    """Ollama's own running processes - if it's running, it's installed."""
    try:
        import psutil
    except ImportError:
        return []
    out = []
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in EXE_NAMES and proc.info.get("exe"):
                out.append(Path(proc.info["exe"]))
        except Exception:
            continue
    return out


def is_running(running: Callable[[], list[Path]] = _running_exes) -> bool:
    try:
        return bool(running())
    except Exception:
        return False


def find_exe(which: Callable[..., str | None] = shutil.which, env: dict | None = None,
             registry: Callable[[str], str] = _registry_env,
             folders: Callable[[], Iterable[Path]] = _uninstall_folders,
             running: Callable[[], list[Path]] = _running_exes) -> Path | None:
    """ollama.exe, wherever it is (None = really not on this PC)."""
    env = os.environ if env is None else env
    found = which("ollama")
    if found:
        return Path(found)
    fresh_path = registry("PATH")
    if fresh_path:                                         # installed after Capri started
        try:
            found = which("ollama", path=fresh_path)
        except TypeError:
            found = None
        if found:
            return Path(found)
    places = []
    for var, sub in (("LOCALAPPDATA", r"Programs\Ollama"), ("ProgramFiles", "Ollama"),
                     ("ProgramW6432", "Ollama"), ("ProgramFiles(x86)", "Ollama"),
                     ("USERPROFILE", r"AppData\Local\Programs\Ollama")):
        if env.get(var):
            places.append(Path(env[var]) / sub)
    try:
        places += list(folders())
    except Exception:
        pass
    for folder in places:
        for exe in ("ollama.exe", "ollama app.exe"):
            candidate = folder / exe
            if candidate.is_file():
                return folder / "ollama.exe" if (folder / "ollama.exe").is_file() else candidate
    try:
        procs = running()
    except Exception:
        procs = []
    for exe in procs:
        cli = exe.with_name("ollama.exe")
        return cli if cli.is_file() else exe
    return None


# -- the model --------------------------------------------------------------------------------
def chat_models(names: Iterable[str]) -> list[str]:
    return [n for n in names if n and not any(word in n.lower() for word in NOT_CHAT)]


def pick_model(names: Iterable[str], wanted: str) -> str:
    """The model to use: the one you picked if it's there, else any chat model you have ("" = none)."""
    names = [n for n in names if n]
    wanted = (wanted or "").strip()
    for n in names:
        if wanted and (n == wanted or n.split(":")[0] == wanted.split(":")[0]):
            return n
    chats = chat_models(names)
    return chats[0] if chats else ""
