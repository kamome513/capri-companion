"""Why can't she think, and fixing it - "set up your brain", "is your AI working".

Her AI brain is Ollama (free, runs on your PC) or Claude (online, needs your API key). Ollama
only works when all three are true:
  1. it's installed,
  2. it's running (it normally starts with Windows),
  3. its model (llama3.2, ~2 GB) is downloaded.
Miss any one and she falls back to her own offline chatbot. The doctor finds which one and
fixes it - only fixed, known steps, never anything an AI wrote:
  * not running -> starts Ollama's own program,
  * no model -> asks Ollama (on 127.0.0.1) to download it, with progress,
  * not installed -> opens setup_ai.bat (installs Ollama with winget, then the model) - asked first.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from . import ollama_find
from .local import DEFAULT_MODEL

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
SETUP_SCRIPT = ROOT / "setup_ai.bat"
NO_WINDOW, NEW_CONSOLE, DETACHED = 0x08000000, 0x00000010, 0x00000008

READY, CLAUDE, STOPPED, NO_MODEL, NOT_INSTALLED = "ready", "claude", "stopped", "no_model", "not_installed"
UNREACHABLE = "unreachable"          # Ollama's running, but not answering where she looks
ONLINE, NEEDS_KEY = "online", "needs_key"          # ChatGPT / any OpenAI-style AI


class AIDoctor:
    def __init__(self, settings, claude_has_key: Callable[[], bool] = lambda: False,
                 fetch: Callable | None = None, openai=None, which: Callable[[str], str | None] = shutil.which,
                 run: Callable = subprocess.Popen, env: dict | None = None, opener: Callable | None = None,
                 find: Callable[[], Path | None] | None = None, running: Callable[[], bool] | None = None) -> None:
        self.settings, self.claude_has_key, self.openai = settings, claude_has_key, openai
        self.fetch = fetch or self._fetch
        self.which, self.run = which, run
        self.env = os.environ if env is None else env
        self._find = find or (lambda: ollama_find.find_exe(self.which, self.env))
        self._running = running or ollama_find.is_running
        self.opener = opener or (lambda: urllib.request.build_opener(urllib.request.ProxyHandler({})))  # never a proxy

    # -- where things are ----------------------------------------------------------------------
    def _base(self) -> str:
        return (getattr(self.settings, "ollama_url", "") or ollama_find.default_url(self.env)).rstrip("/")

    def model(self) -> str:
        return getattr(self.settings, "ollama_model", "") or DEFAULT_MODEL

    def ollama_exe(self) -> Path | None:
        """Wherever it's installed (Program Files, the usual per-user folder, a fresh PATH...)."""
        try:
            return self._find()
        except Exception:
            return None

    @staticmethod
    def _fetch(method: str, url: str, body: dict | None = None, timeout: float = 3.0) -> dict:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))    # 127.0.0.1: never a proxy
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")

    # -- what's wrong -----------------------------------------------------------------------------
    def status(self) -> tuple[str, str]:
        """(code, what to tell you). Blocking (a quick local check) - call from a worker thread."""
        provider = getattr(self.settings, "ai_provider", "auto")
        if self.openai is not None and (provider == "openai" or provider == "auto" and self.openai.has_key()):
            ok, message = self.openai.ready()
            return (ONLINE if ok else NEEDS_KEY), message
        if provider == "claude" and self.claude_has_key():
            return CLAUDE, "My brain's online through Claude."
        tags = None
        for wait in (4.0, 8.0):                               # a just-started Ollama can be slow
            try:
                tags = self.fetch("GET", self._base() + "/api/tags", timeout=wait) or {}
                break
            except TypeError:                                 # (a fetch without a timeout)
                try:
                    tags = self.fetch("GET", self._base() + "/api/tags") or {}
                    break
                except Exception:
                    continue
            except Exception:
                continue
        if tags is not None:
            names = [m.get("name", "") for m in tags.get("models", [])]
            model = ollama_find.pick_model(names, self.model())
            if model:
                return READY, f"My AI brain's online: Ollama with {model}. I'm thinking for real."
            if self.claude_has_key() and provider != "local":
                return CLAUDE, "My brain's online through Claude."
            return NO_MODEL, f"Ollama's running, but my brain - the {model} model - isn't downloaded yet."
        if self.claude_has_key() and provider != "local":
            return CLAUDE, "My brain's online through Claude."
        if self._running():
            return UNREACHABLE, (f"Ollama's running, but it isn't answering at {self._base()}. If you changed "
                                 f"its address, put it in Settings, Assistant, Address.")
        if self.ollama_exe() is not None:
            return STOPPED, "Ollama's installed but not running."
        return NOT_INSTALLED, ("I can't find Ollama on this PC. It's a free app that runs my brain here. "
                               "If you do have it, open it once and ask me again.")

    # -- fixing it -------------------------------------------------------------------------------
    def start(self) -> bool:
        """Start Ollama's own program in the background (no window)."""
        exe = self.ollama_exe()
        if exe is None:
            return False
        app = exe.with_name("ollama app.exe")
        args = [str(app)] if app.exists() else [str(exe), "serve"]
        flags = NO_WINDOW | DETACHED if sys.platform == "win32" else 0
        self.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        return True

    def pull(self, progress: Callable[[float], None] = lambda p: None, model: str = "") -> None:
        """Download a model (hers, or the one named) through Ollama's own API, reporting 0..1. Blocking (minutes)."""
        opener = self.opener()
        req = urllib.request.Request(self._base() + "/api/pull", method="POST",
                                     data=json.dumps({"model": model or self.model(), "stream": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=3600) as r:
            for line in r:
                if not line.strip():
                    continue
                msg = json.loads(line.decode())
                if msg.get("error"):
                    raise OSError(msg["error"])
                if msg.get("total"):
                    progress(min(1.0, msg.get("completed", 0) / msg["total"]))
                if msg.get("status") == "success":
                    progress(1.0)
                    return
        raise OSError("the download stopped early")

    def install(self) -> bool:
        """Open setup_ai.bat in its own window (winget installs Ollama, then the model)."""
        if sys.platform != "win32" or not SETUP_SCRIPT.exists():
            return False
        self.run(["cmd.exe", "/c", str(SETUP_SCRIPT)], cwd=str(ROOT), creationflags=NEW_CONSOLE)
        return True
