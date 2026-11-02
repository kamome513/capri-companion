"""Setting up Ollama for you, start to finish: "Set up Ollama for me" (Settings -> Assistant) or
"Hey Capri, set up your brain".

1. Install Ollama if it isn't there:
   * Windows: winget (built into Windows 10/11) installs Ollama's official package; without winget, Ollama's
     own installer (ollama.com/download/OllamaSetup.exe) is downloaded and run quietly. Per-user: no admin.
   * Linux: Ollama's official install command needs your password (it installs a system service), so a
     terminal window opens running it - you type your password there. Capri waits for it to finish.
2. Start it (it then starts with your PC by itself).
3. Download a chat model that suits your PC: llama3.2 (2 GB), or the small llama3.2:1b (1.3 GB) on PCs
   with 8 GB of RAM or less. A model you already have is used instead.
4. Switch her chat to Ollama.

Only these fixed steps run - nothing typed, said or written by an AI ever becomes a command. You're
asked before anything is installed or downloaded.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger("capri")

WINDOWS_INSTALLER = "https://ollama.com/download/OllamaSetup.exe"
LINUX_INSTALL = ('echo "Installing Ollama for Capri (it asks for your password)..."; '
                 'curl -fsSL https://ollama.com/install.sh | sh; '
                 'echo; echo "Done - you can close this window. Capri carries on by herself."; sleep 20')
BIG_MODEL, SMALL_MODEL = "llama3.2", "llama3.2:1b"
WAIT_INSTALL = 30 * 60           # seconds to wait for an installer
WAIT_START = 90                  # seconds for Ollama to start answering


def ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / 1024 ** 3
    except Exception:
        return 16.0


def model_for_this_pc(ram: float | None = None) -> str:
    """llama3.2 (3B) needs ~4 GB free while she thinks; on an 8 GB PC (games, a browser...) the 1B is kinder."""
    return SMALL_MODEL if (ram if ram is not None else ram_gb()) <= 8.5 else BIG_MODEL


class OllamaSetup:
    def __init__(self, doctor, settings, progress: Callable[[str], None] = lambda text: None,
                 run: Callable = subprocess.run, popen: Callable = subprocess.Popen,
                 opener=urllib.request.urlopen, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, platform: str = sys.platform,
                 which: Callable[[str], str | None] = shutil.which) -> None:
        self.doctor, self.settings, self.progress = doctor, settings, progress
        self.run, self.popen, self.opener, self.sleep, self.clock = run, popen, opener, sleep, clock
        self.platform, self.which = platform, which

    # -- where things stand ---------------------------------------------------------------------------
    def installed(self) -> bool:
        return self.doctor.ollama_exe() is not None

    def models(self) -> list[str] | None:
        """Ollama's models, or None if it isn't answering."""
        try:
            tags = self.doctor.fetch("GET", self.doctor._base() + "/api/tags", timeout=4.0) or {}
        except TypeError:
            try:
                tags = self.doctor.fetch("GET", self.doctor._base() + "/api/tags") or {}
            except Exception:
                return None
        except Exception:
            return None
        return [m.get("name", "") for m in tags.get("models", [])]

    def _wait(self, check: Callable[[], bool], seconds: float, every: float = 2.0) -> bool:
        end = self.clock() + seconds
        while self.clock() < end:
            if check():
                return True
            self.sleep(every)
        return check()

    # -- 1. install --------------------------------------------------------------------------------------
    def install(self) -> None:
        if self.platform == "win32":
            return self._install_windows()
        if self.platform.startswith("linux"):
            return self._install_linux()
        raise OSError("install Ollama from ollama.com, then try again")

    def _winget(self) -> str | None:
        found = self.which("winget")
        if found:
            return found
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "winget.exe"
        return str(local) if os.environ.get("LOCALAPPDATA") and local.exists() else None

    def _install_windows(self) -> None:
        winget = self._winget()
        if winget:
            self.progress("Installing Ollama (winget)... this takes a few minutes.")
            try:
                result = self.run([winget, "install", "-e", "--id", "Ollama.Ollama", "--silent",
                                   "--accept-package-agreements", "--accept-source-agreements",
                                   "--disable-interactivity"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=WAIT_INSTALL, creationflags=0x08000000)
                if result.returncode == 0 or self.installed():
                    return
                log.info("ollama setup: winget said %s - trying Ollama's own installer", result.returncode)
            except (OSError, subprocess.SubprocessError) as exc:
                log.info("ollama setup: winget failed (%s) - trying Ollama's own installer", exc)
        setup = self._download(WINDOWS_INSTALLER, "OllamaSetup.exe")
        self.progress("Installing Ollama... this takes a few minutes.")
        try:
            self.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=WAIT_INSTALL)
        finally:
            try:
                setup.unlink()
            except OSError:
                pass
        if not self._wait(self.installed, 30):
            raise OSError("Ollama's installer didn't finish")

    def _download(self, url: str, name: str) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="capri_ollama_"))
        target = folder / name
        req = urllib.request.Request(url, headers={"User-Agent": "Capri"})
        with self.opener(req, timeout=60) as response, open(target, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done, shown = 0, -1
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else -1
                if pct != shown and pct >= 0:
                    shown = pct
                    self.progress(f"Downloading Ollama... {pct}%")
        return target

    def _terminal(self) -> list[str] | None:
        for name, args in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
                           ("xfce4-terminal", ["-x"]), ("mate-terminal", ["-x"]), ("tilix", ["-e"]),
                           ("kitty", []), ("alacritty", ["-e"]), ("foot", []), ("xterm", ["-e"])):
            exe = self.which(name)
            if exe:
                return [exe, *args]
        return None

    def _install_linux(self) -> None:
        term = self._terminal()
        if term is None:
            raise OSError("open a terminal and run:  curl -fsSL https://ollama.com/install.sh | sh")
        self.progress("A terminal opened to install Ollama - type your password there.")
        self.popen([*term, "sh", "-c", LINUX_INSTALL], start_new_session=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not self._wait(lambda: self.installed() or self.models() is not None, WAIT_INSTALL, every=3.0):
            raise OSError("Ollama didn't get installed (was the terminal closed?)")

    # -- 2. start ----------------------------------------------------------------------------------------
    def start(self) -> None:
        if self.models() is not None:
            return
        self.progress("Starting Ollama...")
        self.doctor.start()
        if not self._wait(lambda: self.models() is not None, WAIT_START):
            raise OSError("Ollama is installed but won't start - restart your PC and try again")

    # -- 3. the model --------------------------------------------------------------------------------------
    def model(self) -> str:
        from .ollama_find import chat_models
        have = chat_models(self.models() or [])
        wanted = (getattr(self.settings, "ollama_model", "") or "").strip()
        if wanted and any(n == wanted or n.split(":")[0] == wanted.split(":")[0] for n in have):
            return next(n for n in have if n == wanted or n.split(":")[0] == wanted.split(":")[0])
        if have:
            return have[0]                                   # use the one you've got
        model = model_for_this_pc()
        self.settings.ollama_model = model
        self.progress(f"Downloading her brain ({model})...")
        last = [-1]

        def pulled(fraction: float) -> None:
            pct = int(fraction * 100)
            if pct != last[0]:
                last[0] = pct
                self.progress(f"Downloading her brain ({model})... {pct}%")
        self.doctor.pull(pulled)
        return model

    # -- all of it -----------------------------------------------------------------------------------------
    def run_all(self) -> str:
        """Blocking (minutes). Returns what to tell you; raises OSError with the reason if a step failed."""
        if not self.installed() and self.models() is None:
            self.install()
        self.start()
        model = self.model()
        s = self.settings
        s.ollama_model = model
        s.ai_provider = "local"
        s.ai_enabled = True
        try:
            s.save()
        except Exception:
            pass
        log.info("ollama setup: done, using %s", model)
        return f"All set: I'm thinking with Ollama ({model}), right here on your PC. Ask me anything!"
