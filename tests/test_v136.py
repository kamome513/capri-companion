"""v1.36: Ollama is found however it was installed (and whatever model it has), and Capri updates
herself from GitHub releases."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_v11 import FakeDesktop, rig  # noqa: E402

from capri import updater  # noqa: E402
from capri.ai import doctor as dr  # noqa: E402
from capri.ai import ollama_find  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.settings import Settings  # noqa: E402


# -- Ollama: found wherever it is ------------------------------------------------------------------------------------
@pytest.mark.parametrize("host, url", [
    ("", "http://127.0.0.1:11434"), ("0.0.0.0", "http://127.0.0.1:11434"), ("0.0.0.0:8080", "http://127.0.0.1:8080"),
    (":11500", "http://127.0.0.1:11500"), ("192.168.1.5:11434", "http://192.168.1.5:11434"),
    ("http://box.local:9000/", "http://box.local:9000"), ("[::1]:11434", "http://[::1]:11434"),
])
def test_ollama_host(host, url):
    assert ollama_find.url_from_host(host) == url


def test_ollama_host_from_windows_settings():
    assert ollama_find.default_url({}, lambda name: "0.0.0.0:8080" if name == "OLLAMA_HOST" else "") == \
        "http://127.0.0.1:8080"
    assert ollama_find.default_url({"OLLAMA_HOST": "127.0.0.1:9999"}, lambda n: "") == "http://127.0.0.1:9999"


def _exe(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ollama.exe").write_bytes(b"MZ")
    return folder / "ollama.exe"


def nothing(*a, **k):
    return None


def test_ollama_in_program_files(tmp_path):
    exe = _exe(tmp_path / "Program Files" / "Ollama")
    found = ollama_find.find_exe(nothing, {"ProgramFiles": str(tmp_path / "Program Files")}, lambda n: "",
                                 lambda: [], lambda: [])
    assert found == exe


def test_ollama_installed_after_capri_started(tmp_path):
    exe = _exe(tmp_path / "new")

    def which(cmd, path=None):
        return str(exe) if path and str(tmp_path / "new") in path else None
    assert ollama_find.find_exe(which, {}, lambda n: str(tmp_path / "new") if n == "PATH" else "",
                                lambda: [], lambda: []) == exe


def test_ollama_from_the_uninstall_list_or_its_running_process(tmp_path):
    exe = _exe(tmp_path / "D" / "Tools" / "Ollama")
    assert ollama_find.find_exe(nothing, {}, lambda n: "", lambda: [exe.parent], lambda: []) == exe
    assert ollama_find.find_exe(nothing, {}, lambda n: "", lambda: [], lambda: [exe.with_name("ollama app.exe")]) == exe
    assert ollama_find.find_exe(nothing, {}, lambda n: "", lambda: [], lambda: []) is None


def test_any_chat_model_will_do():
    assert ollama_find.pick_model(["llama3.2:latest", "qwen2.5:3b"], "llama3.2") == "llama3.2:latest"
    assert ollama_find.pick_model(["nomic-embed-text:latest", "mistral:7b"], "llama3.2") == "mistral:7b"
    assert ollama_find.pick_model(["nomic-embed-text:latest"], "llama3.2") == ""
    assert ollama_find.pick_model([], "llama3.2") == ""


def _doctor(fetch, find=lambda: None, running=lambda: False, **settings):
    s = Settings(ai_provider="local", **settings)
    return dr.AIDoctor(s, fetch=fetch, find=find, running=running)


def down(*a, **k):
    raise OSError("refused")


def test_doctor_tells_running_from_installed_from_missing(tmp_path):
    def mistral(method, url, **k):
        return {"models": [{"name": "mistral:7b"}]}
    assert _doctor(mistral).status()[0] == dr.READY                       # not llama3.2: still her brain
    assert "mistral:7b" in _doctor(mistral).status()[1]
    assert _doctor(down, running=lambda: True).status()[0] == dr.UNREACHABLE
    assert _doctor(down, find=lambda: tmp_path / "ollama.exe").status()[0] == dr.STOPPED
    code, words = _doctor(down).status()
    assert code == dr.NOT_INSTALLED and "can't find" in words


def test_doctor_uses_your_ollama_address():
    seen = []

    def fetch(method, url, **k):
        seen.append(url)
        return {"models": [{"name": "llama3.2"}]}
    _doctor(fetch, ollama_url="http://127.0.0.1:8080").status()
    assert seen[-1] == "http://127.0.0.1:8080/api/tags"


def test_unreachable_ollama_isnt_offered_an_install():
    class Doc:
        def status(self):
            return dr.UNREACHABLE, "Ollama's running, but it isn't answering."
    r = rig(FakeDesktop(), doctor=Doc())
    r.router.handle("set up your brain")
    from test_stage5 import settle
    assert settle(3, lambda: "isn't answering" in r.controller.message)
    assert "Install it?" not in r.controller.message


# -- updates: what's newer -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("latest, current, yes", [
    ("v1.36.0", "1.35.0", True), ("1.35.1", "1.35.0", True), ("1.35.0", "1.35.0", False), ("1.34.9", "1.35.0", False),
    ("Capri 1.40", "1.36.0", True), ("v2", "1.99.9", True), ("nonsense", "1.0.0", False),
])
def test_newer(latest, current, yes):
    assert updater.newer(latest, current) is yes


def release(version="1.37.0", name="Capri-Setup-1.37.0.exe", size=10, digest="", **extra):
    url = f"https://github.com/kamome513/capri-companion/releases/download/v{version}/{name}"
    return {"tag_name": f"v{version}", "html_url": "https://github.com/kamome513/capri-companion/releases/tag/x",
            "assets": [{"name": "notes.txt", "browser_download_url": url.replace(name, "notes.txt")},
                       {"name": name, "browser_download_url": url, "size": size, "digest": digest}], **extra}


def test_check_finds_the_installer():
    found = updater.check(lambda url: release(digest="sha256:ABC"), current="1.36.0")
    assert found.version == "1.37.0" and found.name == "Capri-Setup-1.37.0.exe" and found.size == 10
    assert found.sha256 == "abc"
    assert updater.check(lambda url: release("1.36.0"), current="1.36.0") is None
    assert updater.check(lambda url: release(prerelease=True), current="1.36.0") is None
    assert updater.check(lambda url: {"tag_name": "1.37.0", "assets": []}, current="1.36.0").url == ""


def test_only_capris_own_files_are_downloaded(tmp_path):
    bad = updater.Update("9.9.9", "https://evil.example.com/Capri-Setup-9.9.9.exe", "Capri-Setup-9.9.9.exe", 1)
    with pytest.raises(ValueError):
        updater.download(bad, tmp_path, opener=lambda *a, **k: None)
    sneaky = updater.Update("9.9.9", updater.DOWNLOADS + "v9/run.bat", "run.bat", 1)
    with pytest.raises(ValueError):
        updater.download(sneaky, tmp_path, opener=lambda *a, **k: None)


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def test_download_is_checked(tmp_path):
    data = b"MZ" + b"x" * 1000
    good = updater.Update("9.9.9", updater.DOWNLOADS + "v9.9.9/Capri-Setup-9.9.9.exe", "Capri-Setup-9.9.9.exe",
                          len(data), hashlib.sha256(data).hexdigest())
    path = updater.download(good, tmp_path, opener=lambda *a, **k: Response(data))
    assert path.read_bytes() == data
    assert updater.ready(tmp_path, current="1.36.0") == ("9.9.9", path)
    assert updater.ready(tmp_path, current="9.9.9") is None and not path.exists()     # installed: cleaned up

    tampered = updater.Update(good.version, good.url, good.name, good.size, "0" * 64)
    with pytest.raises(OSError):
        updater.download(tampered, tmp_path, opener=lambda *a, **k: Response(data))
    short = updater.Update(good.version, good.url, good.name, good.size + 5)
    with pytest.raises(OSError):
        updater.download(short, tmp_path, opener=lambda *a, **k: Response(data))
    assert updater.ready(tmp_path, current="1.36.0") is None


def test_a_changed_download_is_never_installed(tmp_path):
    data = b"MZ-good"
    u = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri-Setup-9.9.9.exe", "Capri-Setup-9.9.9.exe", len(data))
    path = updater.download(u, tmp_path, opener=lambda *a, **k: Response(data))
    path.write_bytes(b"MZ-evil")
    assert updater.ready(tmp_path, current="1.36.0") is None


def test_install_only_from_the_installed_app(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(updater, "frozen", lambda: False)
    assert updater.install(tmp_path / "Capri-Setup-9.exe", run=lambda *a, **k: ran.append(a)) is False
    monkeypatch.setattr(updater, "frozen", lambda: True)
    assert updater.install(tmp_path / "Capri-Setup-9.exe", run=lambda args, **k: ran.append(args)) is True
    assert "/SILENT" in ran[-1] and "/update=1" in ran[-1]


# -- updates: the app side -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["check for updates", "can you check for updates", "update yourself",
                                  "are there any updates", "is there a new version of you", "install the update",
                                  "are you up to date"])
def test_update_words(said):
    assert parse(said).kind is Kind.UPDATE


@pytest.mark.parametrize("said", ["open discord", "update my drivers please later", "check the weather"])
def test_not_update_words(said):
    assert parse(said).kind is not Kind.UPDATE


def _manager(**kw):
    from capri.controller import CompanionController
    from capri.ui.updates import UpdateManager
    calls = {"quit": 0, "installed": [], "opened": []}
    defaults = dict(check=lambda: None, download=lambda u: Path("x.exe"), ready=lambda: None,
                    install=lambda p: calls["installed"].append(p) or True, frozen=lambda: True,
                    open_page=calls["opened"].append, quit_app=lambda: calls.__setitem__("quit", calls["quit"] + 1),
                    confirm=lambda q: True)
    defaults.update(kw)
    m = UpdateManager(Settings(), CompanionController(), None, None, **defaults)
    m._background = lambda work, callback: callback(_try(work))     # no threads in tests
    return m, calls


def _try(work):
    try:
        return work()
    except Exception as exc:
        return exc


def test_new_version_downloads_in_the_background():
    new = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri-Setup-9.9.9.exe", "Capri-Setup-9.9.9.exe", 5)
    got = []
    m, calls = _manager(check=lambda: new, download=lambda u: got.append(u) or Path("x.exe"))
    m.check_now(quiet=True)
    assert got == [new] and "downloaded" in m.status and calls["installed"] == []    # installs next start


def test_auto_update_off_only_tells_you():
    new = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri-Setup-9.9.9.exe", "Capri-Setup-9.9.9.exe", 5)
    got = []
    m, _calls = _manager(check=lambda: new, download=lambda u: got.append(u))
    m.settings.auto_update = False
    m.check_now(quiet=True)                          # the daily timer: off
    assert got == []
    m.check_now()                                    # you asked: she fetches it, installs only on your yes
    assert got == [new] and "Restart to update" in m.status and "next time" not in m.status


def test_update_now_asks_installs_and_quits():
    m, calls = _manager(ready=lambda: ("9.9.9", Path("Capri-Setup-9.9.9.exe")))
    assert m.label() == "Restart to update (Capri 9.9.9)"
    m.menu_clicked()
    assert calls["installed"] == [Path("Capri-Setup-9.9.9.exe")] and calls["quit"] == 1
    m2, calls2 = _manager(ready=lambda: ("9.9.9", Path("Capri-Setup-9.9.9.exe")), confirm=lambda q: False)
    m2.menu_clicked()
    assert calls2["installed"] == [] and calls2["quit"] == 0     # you said no


def test_running_from_the_code_opens_the_release_page():
    new = updater.Update("9.9.9", updater.DOWNLOADS + "v/Capri-Setup-9.9.9.exe", "Capri-Setup-9.9.9.exe", 5)
    m, calls = _manager(check=lambda: new, frozen=lambda: False)
    m.check_now()
    assert "9.9.9 is out" in m.status
    m.menu_clicked()
    assert calls["opened"] == [new.page]


def test_offline_is_fine():
    def boom():
        raise OSError("no internet")
    m, _ = _manager(check=boom)
    m.check_now(quiet=True)
    assert not m.busy
    m.check_now()
    assert "Couldn't check GitHub" in m.status


def test_waiting_update_installs_at_startup():
    from capri.ui.updates import apply_waiting_update
    ran = []
    waiting = ("9.9.9", Path("Capri-Setup-9.9.9.exe"))
    assert apply_waiting_update(Settings(), lambda: waiting, lambda p: ran.append(p) or True, lambda: True)
    assert not apply_waiting_update(Settings(auto_update=False), lambda: waiting, ran.append, lambda: True)
    assert not apply_waiting_update(Settings(), lambda: waiting, ran.append, lambda: False)   # from the code
    assert ran == [waiting[1]]


def test_say_check_for_updates():
    class Updates:
        def __init__(self):
            self.calls = []

        def check_now(self, quiet=False):
            self.calls.append("check")

        def update_now(self):
            self.calls.append("now")
            return True
    u = Updates()
    r = rig(FakeDesktop(), updates=u)
    r.router.handle("check for updates")
    r.router.handle("update yourself")
    assert u.calls == ["check", "now"]


def test_the_installer_restarts_capri_after_an_update():
    iss = (Path(__file__).resolve().parent.parent / "packaging" / "capri.iss").read_text()
    assert "Check: IsCapriUpdate" in iss and "{param:update|0}" in iss


def test_release_workflow_builds_the_installer():
    wf = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"
    text = wf.read_text()
    assert "capri/__init__.py" in text and "Capri-Setup-" in text and "gh release create" in text
    json.dumps(text)   # (plain text, nothing binary)
