"""v1.37.1: "Set up Ollama for me" / "set up your brain" installs Ollama, downloads a model that suits the
PC and switches her chat to it - no terminal needed (Linux: Ollama's own installer in a terminal, for your
password)."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ai import ollama_setup as osetup  # noqa: E402
from capri.settings import Settings  # noqa: E402


class FakeOllama:
    """The doctor's view of Ollama: installed? answering? which models? pulls."""

    def __init__(self, installed=False, running=False, models=()):
        self.is_installed, self.running, self.models = installed, running, list(models)
        self.started = self.pulled = 0
        self.pull_model = ""
        self.settings = None

    def ollama_exe(self):
        return Path("/x/ollama") if self.is_installed else None

    def _base(self):
        return "http://127.0.0.1:11434"

    def fetch(self, method, url, body=None, timeout=3.0):
        if not self.running:
            raise OSError("refused")
        return {"models": [{"name": m} for m in self.models]}

    def start(self):
        self.started += 1
        self.running = self.is_installed
        return True

    def pull(self, progress):
        self.pulled += 1
        self.pull_model = self.settings.ollama_model
        for p in (0.0, 0.5, 1.0):
            progress(p)
        self.models.append(self.settings.ollama_model)


def setup(ollama, platform="win32", which=None, run=None, popen=None, opener=None, ram=16.0, monkeypatch=None):
    s = Settings(ai_provider="auto", ai_enabled=False, ollama_model="")
    ollama.settings = s
    said = []
    if monkeypatch is not None:
        monkeypatch.setattr(osetup, "ram_gb", lambda: ram)
    clock = [0.0]

    def sleep(t):
        clock[0] += t
    o = osetup.OllamaSetup(ollama, s, said.append, run=run or (lambda *a, **k: SimpleNamespace(returncode=0)),
                           popen=popen or (lambda *a, **k: None), opener=opener, sleep=sleep, clock=lambda: clock[0],
                           platform=platform, which=which or (lambda name: None))
    return o, s, said


def test_windows_with_winget(monkeypatch):
    ollama = FakeOllama()
    ran = []

    def run(argv, **kw):
        ran.append(argv)
        ollama.is_installed = True
        return SimpleNamespace(returncode=0)
    o, s, said = setup(ollama, which=lambda n: "C:/winget.exe" if n == "winget" else None, run=run,
                       monkeypatch=monkeypatch)
    message = o.run_all()
    assert ran == [["C:/winget.exe", "install", "-e", "--id", "Ollama.Ollama", "--silent",
                    "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]]
    assert ollama.started == 1 and ollama.pull_model == "llama3.2"
    assert (s.ai_provider, s.ai_enabled, s.ollama_model) == ("local", True, "llama3.2")
    assert "llama3.2" in message and any("100%" in line for line in said)


class Download(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def test_windows_without_winget_uses_ollamas_installer(monkeypatch):
    ollama = FakeOllama()
    ran, asked = [], []

    def run(argv, **kw):
        ran.append(argv)
        ollama.is_installed = True
        return SimpleNamespace(returncode=0)

    def opener(req, timeout):
        asked.append(req.full_url)
        return Download(b"MZ" * 1000)
    o, s, said = setup(ollama, run=run, opener=opener, monkeypatch=monkeypatch)
    o.run_all()
    assert asked == [osetup.WINDOWS_INSTALLER]
    assert ran[0][0].endswith("OllamaSetup.exe") and "/VERYSILENT" in ran[0]
    assert not Path(ran[0][0]).exists()                         # the installer is cleaned up
    assert any("Downloading Ollama... 100%" in line for line in said)


def test_linux_opens_a_terminal_with_ollamas_installer(monkeypatch):
    ollama = FakeOllama()
    opened = []

    def popen(argv, **kw):
        opened.append(argv)
        ollama.is_installed = True                              # you typed your password; it installed
    o, s, said = setup(ollama, platform="linux", popen=popen,
                       which=lambda n: "/usr/bin/gnome-terminal" if n == "gnome-terminal" else None,
                       monkeypatch=monkeypatch)
    o.run_all()
    assert opened == [["/usr/bin/gnome-terminal", "--", "sh", "-c", osetup.LINUX_INSTALL]]
    assert "curl -fsSL https://ollama.com/install.sh | sh" in osetup.LINUX_INSTALL
    assert "password" in said[0]


def test_linux_without_a_terminal_says_what_to_run(monkeypatch):
    o, _s, _said = setup(FakeOllama(), platform="linux", monkeypatch=monkeypatch)
    with pytest.raises(OSError) as caught:
        o.run_all()
    assert "install.sh" in str(caught.value)


def test_small_pc_gets_the_small_model(monkeypatch):
    ollama = FakeOllama(installed=True, running=True)
    o, s, _said = setup(ollama, ram=8.0, monkeypatch=monkeypatch)
    o.run_all()
    assert s.ollama_model == "llama3.2:1b" and ollama.pull_model == "llama3.2:1b"


def test_a_model_you_already_have_is_used(monkeypatch):
    ollama = FakeOllama(installed=True, running=True, models=["nomic-embed-text", "mistral:7b"])
    o, s, _said = setup(ollama, monkeypatch=monkeypatch)
    o.run_all()
    assert ollama.pulled == 0 and s.ollama_model == "mistral:7b" and s.ai_provider == "local"


def test_installed_but_wont_start(monkeypatch):
    ollama = FakeOllama(installed=True)
    ollama.start = lambda: True                                  # never answers
    o, _s, _said = setup(ollama, monkeypatch=monkeypatch)
    with pytest.raises(OSError) as caught:
        o.run_all()
    assert "won't start" in str(caught.value)


def test_set_up_your_brain_does_it_all():
    from test_stage5 import settle
    from test_v11 import FakeDesktop, rig
    from capri.ai import doctor as dr

    class Doc:
        def status(self):
            return dr.NOT_INSTALLED, "I can't find Ollama on this PC."

    ran = []

    class Setup:
        def __init__(self, progress):
            self.progress = progress

        def run_all(self):
            self.progress("Downloading her brain (llama3.2)... 50%")
            ran.append(1)
            return "All set: I'm thinking with Ollama (llama3.2)."
    r = rig(FakeDesktop(), doctor=Doc(), ollama_setup=Setup)
    r.router.handle("set up your brain")
    assert settle(3, lambda: "Want me to set it up?" in r.controller.message)
    r.service.command.emit("yes")
    assert settle(5, lambda: ran == [1] and "All set" in r.controller.message)


def test_settings_button_shows_for_ollama_and_auto():
    from test_v11 import FakeDesktop, rig
    from capri.ui.assistant_tab import AssistantTab
    r = rig(FakeDesktop(), ollama_setup=lambda progress: None)
    r.assistant.speaker.say = lambda *a, **k: True
    r.assistant.speaker.voices = lambda: []
    tab = AssistantTab(r.assistant, r.router, None)
    tab.show()
    for picked, visible in (("local", True), ("auto", True), ("openai:gemini", False), ("claude", False)):
        tab.ai_pick.setCurrentIndex(tab.ai_pick.findData(picked))
        assert tab.ollama_setup_btn.isHidden() is not visible, picked
