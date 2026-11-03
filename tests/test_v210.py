"""v2.1: one app - the one-file Capri.exe that updates itself in place - and her new app icon (her USB shard)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def one_file(monkeypatch, tmp_path):
    from capri import portable, updater
    exe = tmp_path / "Desktop" / "Capri.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"old capri")
    monkeypatch.setattr(updater, "LINUX", False)
    monkeypatch.setattr(portable, "WINDOWS", True)
    monkeypatch.setenv("CAPRI_PORTABLE", str(exe))
    return updater, exe


LATEST = {"version": "9.9.9", "file": "Capri-Setup-9.9.9.exe", "size": 5, "sha256": "aa",
          "portable": {"file": "Capri.exe", "size": 7, "sha256": "CC"},
          "linux": {"file": "Capri-x86_64.AppImage", "size": 9, "sha256": "bb"}}


def test_one_file_capri_reads_its_own_entry(one_file):
    updater, _exe = one_file
    found = updater.check(lambda url: LATEST, current="2.0.1")
    assert found.name == "Capri.exe" and found.size == 7 and found.sha256 == "cc"
    assert found.url == updater.DOWNLOADS + "v9.9.9/Capri.exe" and updater.frozen()


def test_the_installed_capri_still_updates_with_the_installer(monkeypatch):
    from capri import portable, updater
    monkeypatch.setattr(updater, "LINUX", False)
    monkeypatch.setattr(portable, "WINDOWS", True)
    monkeypatch.delenv("CAPRI_PORTABLE", raising=False)
    assert updater.check(lambda url: LATEST, current="2.0.1").name == "Capri-Setup-9.9.9.exe"


def test_one_file_capri_falls_back_to_the_api(one_file):
    updater, _exe = one_file

    def fetch(url):
        if url == updater.LATEST_JSON:
            return {"version": "9.9.9", "file": "Capri-Setup-9.9.9.exe"}
        return {"tag_name": "v9.9.9", "assets": [
            {"name": "Capri-Setup-9.9.9.exe", "browser_download_url": updater.DOWNLOADS + "v9.9.9/Capri-Setup-9.9.9.exe"},
            {"name": "Capri.exe", "size": 3, "browser_download_url": updater.DOWNLOADS + "v9.9.9/Capri.exe"}]}
    assert updater.check(fetch, current="2.0.1").name == "Capri.exe"


def test_update_replaces_the_same_capri_exe_and_starts_it(one_file, tmp_path):
    updater, exe = one_file
    data = b"new capri"
    folder = tmp_path / "updates"

    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(data)
            self.headers = {"Content-Length": str(len(data))}
    u = updater.Update("9.9.9", updater.DOWNLOADS + "v9.9.9/Capri.exe", "Capri.exe", len(data),
                       hashlib.sha256(data).hexdigest())
    path = updater.download(u, folder, opener=lambda *a, **k: Response())
    assert updater.ready(folder, current="2.0.1") == ("9.9.9", path)
    started = []
    assert updater.install(path, run=lambda argv, **kw: started.append(argv), folder=folder)
    assert exe.read_bytes() == data                                   # same file, same place
    assert started == [[str(exe), "--after-update"]]
    assert updater.ready(folder, current="2.0.1") is None and not path.exists()


def test_restart_and_start_with_windows_use_the_one_file_capri(one_file):
    from capri import autostart
    from capri.app import restart_command
    _updater, exe = one_file
    assert restart_command() == (str(exe), [], str(exe.parent))
    assert autostart.launch_command() == f'"{exe}" --startup'


def test_not_one_file_on_linux_or_without_the_launcher(monkeypatch, tmp_path):
    from capri import portable
    exe = tmp_path / "Capri.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(portable, "WINDOWS", False)
    assert portable.exe({"CAPRI_PORTABLE": str(exe)}) == ""
    monkeypatch.setattr(portable, "WINDOWS", True)
    assert portable.exe({"CAPRI_PORTABLE": str(exe)}) == str(exe)
    assert portable.exe({"CAPRI_PORTABLE": str(tmp_path / "gone.exe")}) == "" and portable.exe({}) == ""


def test_payload_zip_puts_everything_under_capri(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import pack_portable
    src = tmp_path / "dist" / "Capri"
    (src / "_internal" / "assets").mkdir(parents=True)
    (src / "Capri.exe").write_bytes(b"core")
    (src / "_internal" / "assets" / "a.png").write_bytes(b"png")
    out = tmp_path / "capri.zip"
    assert pack_portable.pack(src, out) == 2
    assert sorted(zipfile.ZipFile(out).namelist()) == ["Capri/Capri.exe", "Capri/_internal/assets/a.png"]


def test_release_builds_and_checks_the_one_file_capri():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "CapriLauncher.cs" in wf and "--extract-only" in wf and "one-file Capri.exe" in wf
    assert "dist/portable/Capri.exe" in wf and "portable = @{ file = \"Capri.exe\"" in wf
    launcher = (ROOT / "packaging" / "launcher" / "CapriLauncher.cs").read_text()
    assert 'EnvironmentVariables["CAPRI_PORTABLE"]' in launcher and '"capri.zip"' in launcher


# -- her app icon ----------------------------------------------------------------------------------------------------
def test_app_icon_has_every_size():
    from PIL import Image
    ico = Image.open(ROOT / "assets" / "capri" / "app_icon.ico")
    assert {(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])
    from capri.ui.app_icon import app_icon
    assert not app_icon().isNull()


def test_exe_installer_and_appimage_use_the_new_icon():
    assert "app_icon.ico" in (ROOT / "packaging" / "capri.spec").read_text()
    assert "app_icon.ico" in (ROOT / "packaging" / "capri.iss").read_text()
    assert "app_icon.png" in (ROOT / "packaging" / "build_appimage.sh").read_text()
    assert "app_icon.ico" in (ROOT / ".github" / "workflows" / "release.yml").read_text()
    json.loads((ROOT / "assets" / "capri" / "manifest.json").read_text())         # her face stays for the text box


# -- AI "error 400": she says why, and gets past it -----------------------------------------------------------------
def _bad_request(message: str):
    import anthropic
    import httpx2 as httpx
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(400, request=req, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                             "message": message}})
    return anthropic.BadRequestError(message, response=resp, body={"error": {"message": message}})


def test_claude_drops_the_fallback_option_when_its_turned_down():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_stage5 import brain_with, reply, text_block
    b, client = brain_with([_bad_request("fallbacks: Extra inputs are not permitted"), reply(text_block("Hey.")),
                            reply(text_block("Again."))])
    assert b.ask("hi").text == "Hey." and "fallbacks" not in client.requests[1]
    assert b.ask("hi again").text == "Again." and "fallbacks" not in client.requests[2]   # remembered


def test_claude_starts_fresh_when_the_history_is_refused():
    from test_stage5 import brain_with, reply, text_block
    b, client = brain_with([reply(text_block("One.")), _bad_request("messages.1: unexpected tool_use_id"),
                            reply(text_block("Two."))])
    b.ask("first")
    assert b.ask("second").text == "Two."
    assert client.requests[2]["messages"] == [{"role": "user", "content": [{"type": "text", "text": "second"}]}]


def test_claude_says_the_real_reason():
    from test_stage5 import brain_with
    b, _client = brain_with([_bad_request("max_tokens: too large"), _bad_request("max_tokens: too large")])
    got = b.ask("hi")
    assert got.error and "400" in got.text and "max_tokens: too large" in got.text


def test_openai_style_services_never_get_an_empty_null_reply_back():
    from capri.ai.openai_compat import OpenAIBrain
    from capri.integrations import http
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        import copy
        sent.append(copy.deepcopy(json_body))
        if len(sent) == 1:
            return {"choices": [{"message": {"content": None, "tool_calls": [
                {"id": "c1", "function": {"name": "get_time", "arguments": "{}"}}]}}]}
        if len(sent) == 2:
            return {"choices": [{"message": {"content": "It's late."}}]}
        if len(sent) == 3:
            raise http.HttpError(400, '{"error": {"message": "Invalid message history"}}')
        return {"choices": [{"message": {"content": "Fresh."}}]}
    b = OpenAIBrain(lambda: "nvidia", lambda: "", lambda: "", lambda: "k", {"get_time": lambda a: "11pm"}, fetch=fetch)
    assert b.ask("what time").text == "It's late."
    assert all(m.get("content") is not None for m in sent[1]["messages"])            # "" not null
    assert b.ask("and now").text == "Fresh."                                           # refused: asked fresh
    assert [m["role"] for m in sent[3]["messages"]] == ["system", "user"]


def test_screen_watch_backs_off_after_a_problem():
    from types import SimpleNamespace
    from capri.integrations.screen_watch import ScreenWatch
    t = [1000.0]
    s = SimpleNamespace(watch_screen=True, watch_every=60, watch_remember=False)
    w = ScreenWatch(s, None, lambda: None, lambda: "", lambda *a: None, clock=lambda: t[0], background=False)
    w._glanced(SimpleNamespace(error=True, missing=False, blind=False, text="nope", emotion=""))
    w._glanced(SimpleNamespace(error=True, missing=False, blind=False, text="nope", emotion=""))
    assert w._last >= t[0] + 240                                   # waits longer each time


# -- text box: only when you say her name ----------------------------------------------------------------------------
def test_text_box_only_when_you_call_her():
    import time
    sys.path.insert(0, str(ROOT / "tests"))
    from test_v111 import companion
    from capri.states import State
    c = companion()
    s = c.settings
    s.show_panel, s.panel_popup, s.panel_on_name = True, True, True
    c.controller.set_state(State.IDLE, "Waiting for wake word...")
    c._popup_until = 0.0
    assert not c._panel_wanted()
    c.controller.set_state(State.SPEAKING, "Nice kill!")          # her own remark: no box
    c.set_talking(True)
    c._popup_check()
    assert not c._panel_wanted()
    c.set_talking(False)
    c.controller.set_state(State.IDLE, "Nice kill!")
    c.controller.set_state(State.LISTENING, "Listening...")      # "hey Capri"
    c._popup_check()
    assert c._panel_wanted()
    c.controller.set_state(State.SUCCESS, "Opened Chrome.")
    c._popup_check()
    c.controller.set_state(State.IDLE, "Opened Chrome.")
    assert c._panel_wanted()                                     # her answer stays up a moment
    c._popup_until = time.monotonic() - 1
    assert not c._panel_wanted()
    c.controller.set_state(State.SPEAKING, "Ooh, a creeper.")    # by herself again: still no box
    c._popup_check()
    assert not c._panel_wanted()


# -- the music bar shows the song that's actually playing --------------------------------------------------------------
@pytest.mark.parametrize("titles,song", [
    (["Default IME", "MSCTFIME UI", "GDI+ Window (Spotify.exe)", "Chase Atlantic - Consume"], "Chase Atlantic - Consume"),
    (["Spotify Premium", "Default IME"], ""),                               # paused: no song in the title
    (["(3) Blinding Lights - YouTube - Google Chrome"], "Blinding Lights"),
    (["▶ The Weeknd — Starboy"], "The Weeknd - Starboy"),
    (["Spotify", "Drake - God's Plan"], "Drake - God's Plan"),
])
def test_song_from_window_titles(titles, song):
    from capri.ui.music_deck import song_from
    assert song_from(titles) == song


def test_the_bar_follows_the_next_song():
    from capri.ui import music_deck as md
    from test_v111 import companion
    t, playing = [100.0], ["Artist - First Song"]
    deck = md.MusicDeck()
    keeper = md.DeckKeeper(deck, companion(), lambda: playing[0], lambda: True, clock=lambda: t[0])
    keeper.music_changed(True)
    assert deck.title == "Artist - First Song"
    playing[0] = "Artist - Next Song"
    t[0] += md.REFRESH + 0.1
    keeper.tick()
    assert deck.title == "Artist - Next Song"


# -- her size, from the right-click menu --------------------------------------------------------------------------------
def test_right_click_size_menu_resizes_her_and_keeps_her_feet_put():
    from test_v111 import companion
    from capri.ui.tray import CompanionMenu
    c = companion()
    c.place()
    feet, right = c.content_geometry().bottom(), c.content_geometry().right()
    normal = c.content_geometry().height()
    menu = CompanionMenu(c, QImage(8, 8, QImage.Format.Format_ARGB32))
    from PySide6.QtWidgets import QMenu
    size_menu = next(m for m in menu.menu.findChildren(QMenu) if m.title() == "Size")
    big = next(a for a in size_menu.actions() if a.text().startswith("Huge"))
    big.trigger()
    g = c.content_geometry()
    assert c.settings.size == 200 and g.height() > normal * 1.8
    assert g.bottom() == feet and g.right() == right                      # grows up from where she stands
    menu.sync()
    assert big.isChecked()
    next(a for a in size_menu.actions() if a.text() == "Smaller").trigger()
    assert c.settings.size == 150


def test_size_is_saved_and_kept_in_range(tmp_path, monkeypatch):
    from capri.settings import Settings
    path = tmp_path / "settings.json"
    monkeypatch.setattr(Settings, "path", staticmethod(lambda: path))
    path.write_text(json.dumps({"size": 999}))
    assert Settings.load().size == 200
    path.write_text(json.dumps({"size": 125}))
    assert Settings.load().size == 125


@pytest.mark.parametrize("said,size", [("make yourself bigger", "bigger"), ("make capri smaller", "smaller"),
                                       ("make yourself huge", "huge"), ("shrink a bit", "smaller"),
                                       ("reset your size", "normal")])
def test_size_by_voice(said, size):
    from capri.commands.parser import Kind, parse
    got = parse(said)
    assert got.kind == Kind.SIZE and got.query == size
