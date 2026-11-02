"""v1.36.3: every AI service works with her (Gemini 2.5 refused her tool list; thinking models ran out of
room), "check for updates" doesn't depend on GitHub's rate-limited API, an update can't loop, and
"Restart Capri"."""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_v11 import FakeDesktop, rig  # noqa: E402

from capri import net, updater  # noqa: E402


@pytest.fixture(autouse=True)
def _windows_updates(monkeypatch):
    monkeypatch.setattr(updater, "LINUX", False)      # these test the Windows installer flow (test_linux: AppImage)
from capri.ai import openai_compat as oc  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations import http  # noqa: E402
from capri.settings import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# -- every AI: tools they accept ---------------------------------------------------------------------------------------
def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def test_portable_tools_are_plain():
    tools = oc.PORTABLE_TOOLS
    assert {t["function"]["name"] for t in tools} == {t["function"]["name"] for t in oc.OPENAI_TOOLS}
    for d in _walk(tools):
        assert "additionalProperties" not in d and "strict" not in d
    get_time = next(t["function"] for t in tools if t["function"]["name"] == "get_time")
    assert "parameters" not in get_time                       # nothing to pass: no empty object


def gemini_rules(body):
    """What Google's OpenAI-style endpoint refuses (the errors people hit)."""
    for d in _walk(body.get("tools", [])):
        if "additionalProperties" in d:
            raise http.HttpError(400, json.dumps([{"error": {"code": 400, "message":
                "Invalid JSON payload received. Unknown name \"additionalProperties\" at "
                "'tools[0].function_declarations[0].parameters': Cannot find field."}}]))
        if d.get("type") == "object" and "properties" in d and not d["properties"]:
            raise http.HttpError(400, json.dumps([{"error": {"code": 400, "message":
                "* GenerateContentRequest.tools[0].function_declarations[10].parameters.properties: "
                "should be non-empty for OBJECT type"}}]))


class Service:
    def __init__(self, rules=None, replies=None):
        self.rules, self.replies, self.bodies = rules, list(replies or []), []

    def __call__(self, method, url, params=None, data=None, json_body=None, headers=None, timeout=10.0):
        if url.endswith("/models"):
            return {"data": [{"id": "gemini-3-flash"}]}
        self.bodies.append(json.loads(json.dumps(json_body)))
        if self.rules:
            self.rules(json_body)
        reply = self.replies.pop(0) if self.replies else {"role": "assistant", "content": "[happy] Hey choom!"}
        if isinstance(reply, Exception):
            raise reply
        finish = reply.pop("finish_reason", "stop") if isinstance(reply, dict) else "stop"
        return {"choices": [{"message": reply, "finish_reason": finish}]}


def brain(fake, preset="gemini", model="gemini-2.5-flash"):
    return oc.OpenAIBrain(lambda: preset, lambda: "", lambda: model, lambda: "key", {}, fetch=fake)


def test_gemini_2_5_answers():
    fake = Service(gemini_rules)
    reply = brain(fake).ask("hi")
    assert not reply.error and reply.text == "Hey choom!"
    assert len(fake.bodies) == 1 and fake.bodies[0]["model"] == "gemini-2.5-flash"    # right first time


def test_gemini_can_still_do_things():
    call = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "open_app", "arguments": '{"names": ["Chrome"]}'}}]}
    reply = brain(Service(gemini_rules, [call])).ask("open chrome")
    assert reply.intent is not None and reply.intent.kind is Kind.OPEN and reply.intent.targets == ("Chrome",)


def test_a_thinking_model_that_ran_out_of_room_is_asked_again():
    fake = Service(None, [{"role": "assistant", "content": None, "finish_reason": "length"}])
    reply = brain(fake).ask("hi")
    assert reply.text == "Hey choom!" and len(fake.bodies) == 2
    assert "max_tokens" in fake.bodies[0] and "max_tokens" not in fake.bodies[1]


def test_reply_in_parts():
    reply = brain(Service(None, [{"role": "assistant", "content": [{"type": "text", "text": "[smirk] Hi "},
                                                                     {"type": "text", "text": "there."}]}])).ask("hi")
    assert reply.text == "Hi there." and reply.emotion == "smirk"


@pytest.mark.parametrize("preset, error", [
    ("openrouter", http.HttpError(404, '{"error": {"message": "No endpoints found that support tool use."}}')),
    ("deepseek", http.HttpError(400, '{"error": {"message": "deepseek-reasoner does not support Function Calling"}}')),
    ("lmstudio", http.HttpError(400, '{"error": {"message": "This model does not support tools"}}')),
])
def test_models_without_tools_just_chat(preset, error):
    fake = Service(None, [error])
    b = brain(fake, preset, "some-model")
    reply = b.ask("hi")
    assert not reply.error and reply.text == "Hey choom!"
    assert "tools" in fake.bodies[0] and "tools" not in fake.bodies[-1]
    assert b.stand_in == ""                                            # a tools problem isn't a missing model


def test_openai_keeps_strict_tools_then_backs_off():
    strict_no = http.HttpError(400, '{"error": {"message": "Invalid schema for function \'open_app\'"}}')
    fake = Service(None, [strict_no])
    reply = brain(fake, "openai", "gpt-5-nano").ask("hi")
    assert not reply.error
    assert fake.bodies[0]["tools"] == oc.OPENAI_TOOLS and fake.bodies[1]["tools"] == oc.PORTABLE_TOOLS


def test_ollama_model_without_tools_just_chats():
    from capri.ai.local import LocalBrain
    calls = []

    def fetch(method, url, json_body=None, **k):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama2:latest"}]}
        calls.append(dict(json_body))
        if json_body.get("tools"):
            raise http.HttpError(400, '{"error":"registry.ollama.ai/library/llama2:latest does not support tools"}')
        return {"message": {"role": "assistant", "content": "[happy] Sure thing."}}
    b = LocalBrain(lambda: "", lambda: "llama2", {}, fetch=fetch)
    reply = b.ask("can you open chrome")
    assert not reply.error and reply.text == "Sure thing." and b.no_tools
    assert "tools" in calls[0] and "tools" not in calls[1]


# -- updates: no rate limit, no loops ------------------------------------------------------------------------------
LATEST = {"version": "9.9.9", "file": "Capri-Setup-9.9.9.exe", "size": 123, "sha256": "ABCD"}


def test_latest_json_first():
    asked = []

    def fetch(url):
        asked.append(url)
        return LATEST
    found = updater.check(fetch, current="1.36.3")
    assert asked == [updater.LATEST_JSON]
    assert found.url == updater.DOWNLOADS + "v9.9.9/Capri-Setup-9.9.9.exe" and found.sha256 == "abcd"
    assert updater.check(lambda url: LATEST, current="9.9.9") is None


def test_api_is_the_backup():
    def fetch(url):
        if url == updater.LATEST_JSON:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)    # an old release without the file
        return {"tag_name": "v9.9.9", "assets": [{"name": "Capri-Setup-9.9.9.exe", "size": 5,
                                                  "browser_download_url": updater.DOWNLOADS + "v9.9.9/Capri-Setup-9.9.9.exe"}]}
    assert updater.check(fetch, current="1.36.3").version == "9.9.9"


def test_neither_answers_says_why():
    def fetch(url):
        raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
    with pytest.raises(urllib.error.HTTPError) as caught:
        updater.check(fetch, current="1.36.3")
    assert "busy" in net.friendly(caught.value)


def test_certificate_trouble_tries_the_fallbacks(monkeypatch):
    handler = net.FallbackHTTPSHandler()
    used = []

    def first(self, req):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))

    def do_open(http_class, req, **kw):
        used.append(kw.get("context"))
        return "response"
    monkeypatch.setattr(net.urllib.request.HTTPSHandler, "https_open", first)
    monkeypatch.setattr(handler, "do_open", do_open)
    monkeypatch.setattr(net, "FALLBACKS", (("a", lambda: None), ("b", lambda: "context-b")))
    class Req:
        host = "github.com"
    assert handler.https_open(Req()) == "response" and used == ["context-b"]


def test_other_network_errors_arent_retried(monkeypatch):
    handler = net.FallbackHTTPSHandler()

    def first(self, req):
        raise urllib.error.URLError(OSError("getaddrinfo failed"))
    monkeypatch.setattr(net.urllib.request.HTTPSHandler, "https_open", first)
    with pytest.raises(urllib.error.URLError):
        handler.https_open(object())


def _waiting(tmp_path, tries=0, started=0.0):
    from capri.ui.updates import apply_waiting_update
    ran = []
    result = apply_waiting_update(Settings(), ready=lambda: ("9.9.9", tmp_path / "Capri-Setup-9.9.9.exe"),
                                  install=lambda p: ran.append(p) or True, frozen=lambda: True,
                                  tries=lambda: (tries, started), now=lambda: 1000.0,
                                  installing=lambda: False)
    return result, ran


def test_an_update_that_didnt_take_isnt_tried_forever(tmp_path):
    assert _waiting(tmp_path, tries=0) == (True, [tmp_path / "Capri-Setup-9.9.9.exe"])
    assert _waiting(tmp_path, tries=1, started=100.0)[0] is True              # one more go
    assert _waiting(tmp_path, tries=2, started=100.0) == (False, [])          # stop: she starts normally


def test_opening_her_again_during_an_install_doesnt_start_a_second_one(tmp_path):
    from capri.ui.updates import apply_waiting_update
    ran = []
    common = dict(ready=lambda: ("9.9.9", tmp_path / "x.exe"), install=lambda p: ran.append(p) or True,
                  frozen=lambda: True, tries=lambda: (1, 990.0), now=lambda: 1000.0)
    assert apply_waiting_update(Settings(), installing=lambda: True, **common) is True and ran == []
    assert apply_waiting_update(Settings(), installing=lambda: False, **common) is True and len(ran) == 1


def test_install_updates_the_copy_youre_running(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "frozen", lambda: True)
    args = []
    (tmp_path / "ready.json").write_text(json.dumps({"version": "9.9.9", "file": "Capri-Setup-9.9.9.exe"}))
    assert updater.install(tmp_path / "Capri-Setup-9.9.9.exe", run=lambda a, **k: args.append(a),
                           folder=tmp_path, app_dir=r"D:\Games\Capri")
    assert r"/DIR=D:\Games\Capri" in args[0] and "/update=1" in args[0]
    assert updater.tries(tmp_path)[0] == 1


def test_stuck_update_is_explained():
    from capri.controller import CompanionController
    from capri.ui.updates import UpdateManager
    m = UpdateManager(Settings(), CompanionController(), ready=lambda: ("9.9.9", Path("x.exe")),
                      frozen=lambda: True, tries=lambda: (2, 0.0))
    m.check_now()
    assert "didn't install by itself" in m.status and m.label() == "Restart to update (Capri 9.9.9)"


def test_the_installer_waits_for_capri_to_close():
    iss = (ROOT / "packaging" / "capri.iss").read_text()
    assert "function InitializeSetup" in iss and "CheckForMutexes('CapriCompanionRunning')" in iss
    app_py = (ROOT / "capri" / "app.py").read_text()
    assert 'RUNNING_MUTEX = "CapriCompanionRunning"' in app_py


def test_the_release_has_latest_json():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "dist/latest.json" in wf and "Get-FileHash" in wf


# -- Restart Capri -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["restart yourself", "can you restart capri", "reboot yourself", "restart the app"])
def test_restart_her(said):
    assert parse(said).kind is Kind.RESTART_APP


@pytest.mark.parametrize("said", ["restart", "restart my computer", "restart my pc"])
def test_restart_the_pc_is_still_the_pc(said):
    assert parse(said).kind is Kind.POWER


def test_restart_yourself_restarts_her():
    from test_stage5 import settle
    done = []
    r = rig(FakeDesktop(), restart=lambda: done.append(1))
    r.router.handle("restart yourself")
    assert settle(3, lambda: done == [1])


def test_restart_command():
    from capri.app import restart_command
    program, args, folder = restart_command()
    assert program == sys.executable and args == ["-m", "capri"] and Path(folder) == ROOT


def test_restart_in_the_menu_and_settings():
    from capri.ui.pc_tab import PcTab
    tab = PcTab(Settings(), lambda: None, lambda: None, restart=lambda: None)
    assert tab.restart_btn.isEnabled()
    tray = (ROOT / "capri" / "ui" / "tray.py").read_text()
    assert 'QAction("Restart Capri"' in tray
