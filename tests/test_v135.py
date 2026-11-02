"""v1.35: "open your settings", "change music to ...", your own app names first, "can you ... <pause> ...",
exact songs ("Chicago by MJ" isn't "Chicago (Original Version)"), no blind keys or clicks in Spotify, the
apps list only shows what's on your PC (plus your games, and a picker instead of a file hunt), Parakeet
hearing, and a private memory of you that stays out of the AI."""

from __future__ import annotations

import io
import json
import sys
import tarfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

import fake_vosk  # noqa: E402
from test_stage5 import FakeBrain, settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri import about_you  # noqa: E402
from capri.about_you import AboutYou, is_personal, scrub  # noqa: E402
from capri.commands import apps as apps_mod  # noqa: E402
from capri.commands.apps import (CLOSE_ASK, PROGRAM, STEAM, WEBSITE, AppEntry, add_found_games,  # noqa: E402
                                 entry_status, found_games, load_apps, save_apps)
from capri.commands.discovery import Shortcut, SteamGame  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.settings import Settings  # noqa: E402


# -- "open your settings" ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["open your settings", "open capri's settings", "show me your settings",
                                  "can you open your settings", "open your options", "settings"])
def test_her_settings(said):
    assert parse(said).kind is Kind.SETTINGS


def test_plain_open_settings_is_still_windows_settings():
    assert parse("open settings").kind is Kind.OPEN


def test_her_settings_open():
    opened = []
    r = rig(FakeDesktop(), open_settings=lambda: opened.append(1))
    r.router.handle("open your settings")
    assert opened == [1]


# -- "change music to ..." -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("said, service", [
    ("change music to soundcloud", "soundcloud"), ("can you change music to youtube music", "youtube_music"),
    ("switch my music app to spotify", "spotify"), ("set the music player to soundcloud", "soundcloud"),
])
def test_change_music_to(said, service):
    intent = parse(said)
    assert intent.kind is Kind.MUSIC_SERVICE and intent.targets == (service,)


# -- your "also say" names beat her built-in phrases -----------------------------------------------------------------
def test_your_also_say_name_opens_your_app():
    r = rig(FakeDesktop())
    r.router.catalog.apps.append(AppEntry("Notes", PROGRAM, r"C:\notes.exe", aliases=["my chat"]))
    intent = r.router._own_app_command("can you open my chat please")
    assert intent.kind is Kind.OPEN and intent.targets == ("notes",)
    assert r.router._own_app_command("close my chat").kind is Kind.CLOSE
    assert r.router._own_app_command("my chat").kind is Kind.OPEN          # an alias alone opens it
    assert r.router._own_app_command("tell me a joke") is None


# -- "can you ..." <pause> "... open discord" -----------------------------------------------------------------------
def test_can_you_then_a_pause_waits_for_the_rest(monkeypatch):
    from test_wakeword import make, run
    from capri.voice.wakeword import Command
    monkeypatch.setitem(fake_vosk.WORDS, 9, "can")
    monkeypatch.setitem(fake_vosk.WORDS, 10, "you")
    monkeypatch.setitem(fake_vosk.MARK, "can", 9)
    monkeypatch.setitem(fake_vosk.MARK, "you", 10)
    listener = make()
    events = run(listener, fake_vosk.speak(0.3, "capri", 0.6, "can", "you", 1.2, "open", "discord", 1.5))
    commands = [e for e in events if isinstance(e, Command)]
    assert commands and commands[-1].text == "can you open discord"


# -- exact songs ------------------------------------------------------------------------------------------------------
def test_versions_you_didnt_ask_for_score_lower():
    from capri.integrations.spotify_app import artist_score, version_penalty
    assert version_penalty("Chicago", "chicago") == 0
    assert version_penalty("Chicago (Original Version)", "chicago") > 0
    assert version_penalty("Chicago - Live", "chicago") > 0
    assert version_penalty("Chicago (Live)", "chicago live") == 0       # you asked for it
    assert artist_score("Michael Jackson", "mj") == 1.0                 # initials
    assert artist_score("Michael Jackson", "michael jackson") == 1.0
    assert artist_score("Sufjan Stevens", "mj") < 0.5


# -- Spotify: no keys or clicks unless it's really in front -----------------------------------------------------------
class NoFrontDesktop:
    def __init__(self, front=False):
        self.front, self.calls = front, []

    def bring_to_front(self, hwnd):
        return self.front

    def press_keys(self, combo):
        self.calls.append(("keys", combo))

    def type_text(self, text):
        self.calls.append(("type", text))

    def press_enter(self):
        self.calls.append(("enter",))


class NoUI:
    def edits(self, hwnd):
        return []


def test_spotify_search_never_types_into_another_window():
    from capri.integrations.app_buttons import SpotifyButtons
    d = NoFrontDesktop(front=False)
    buttons = SpotifyButtons(NoUI(), lambda pids: [77], desktop=d)
    buttons.sleep = lambda t: None
    assert buttons.search([5], "chicago michael jackson") is False
    assert d.calls == []                                   # no Ctrl+A, no typing, no Enter


def test_spotify_search_stops_if_something_jumps_in_front():
    from capri.integrations.app_buttons import SpotifyButtons
    d = NoFrontDesktop(front=True)
    d.foreground = lambda: 999                             # another app took the focus
    buttons = SpotifyButtons(NoUI(), lambda pids: [77], desktop=d)
    buttons.sleep = lambda t: None
    assert buttons.search([5], "chicago") is False
    assert ("enter",) not in d.calls and not any(c[0] == "type" for c in d.calls)


def test_no_spotify_app_means_youtube_but_slow_spotify_stays_in_spotify():
    from capri.integrations.spotify_app import SpotifyApp

    def refuse(link):
        raise OSError("no app for spotify:")
    app_ = SpotifyApp.__new__(SpotifyApp)
    app_.find_track = lambda q, a: ("4fixebDZAVToLbUCuEloa2", "Chicago")
    app_.spotify_pids = lambda: []
    app_._title = lambda pids: ""
    app_.open_item = refuse
    assert app_.play("chicago", "michael jackson").status == "not_installed"

    r = rig(FakeDesktop())
    opened = []
    r.router.system.open_item = lambda item: opened.append(item)

    class Slow:
        def play(self, q, a):
            return types.SimpleNamespace(status="no_spotify", title="")
    r.router.services.spotify_app = Slow()
    r.router._spotify_app_play("chicago", "michael jackson", "chicago by michael jackson")
    assert settle(3, lambda: opened)
    assert opened[-1].startswith("spotify:search:") and not any("youtube" in o for o in opened)


# -- the apps list -----------------------------------------------------------------------------------------------------
GAMES = [SteamGame("1422450", "Deadlock", Path("/lib/steamapps/common/Deadlock")),
         SteamGame("730", "Counter-Strike 2", Path("/lib/steamapps/common/cs2"))]
SHORTS = [Shortcut("Fortnite", Path("/start/Fortnite.lnk"), Path(r"C:\Program Files\Epic Games\Fortnite\FortniteLauncher.exe")),
          Shortcut("Notepad", Path("/start/Notepad.lnk"), Path(r"C:\Windows\notepad.exe")),
          Shortcut("Epic Games Launcher", Path("/start/Epic.lnk"),
                   Path(r"C:\Program Files\Epic Games\Launcher\EpicGamesLauncher.exe"))]


def test_found_games_are_your_downloaded_games():
    games = found_games(GAMES, SHORTS)
    names = [g.name for g in games]
    assert names == ["Counter-Strike 2", "Deadlock", "Fortnite"]        # not Notepad, not the launcher
    deadlock = next(g for g in games if g.name == "Deadlock")
    assert (deadlock.launch_type, deadlock.target, deadlock.close) == (STEAM, "1422450", CLOSE_ASK)
    assert "dead lock" in deadlock.aliases
    fortnite = next(g for g in games if g.name == "Fortnite")
    assert fortnite.launch_type == PROGRAM and fortnite.target.endswith("Fortnite.lnk")


def test_add_my_games_skips_what_is_listed():
    listed = [AppEntry("Dead lock game", STEAM, "1422450"), AppEntry("Fortnite", PROGRAM, "x")]
    assert [g.name for g in add_found_games(listed, found_games(GAMES, SHORTS))] == ["Counter-Strike 2"]


def test_found_column(tmp_path):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ")
    assert entry_status(AppEntry("A", PROGRAM, str(exe)))[0] is True
    assert entry_status(AppEntry("A", PROGRAM, str(tmp_path / "gone.exe"))) == (False, "File not found here")
    assert entry_status(AppEntry("A", PROGRAM, "game.exe"))[0] is False             # needs the full path
    assert entry_status(AppEntry("A", PROGRAM, ""))[0] is None                      # she looks it up
    assert entry_status(AppEntry("A", STEAM, "1422450"), {"730"}) == (False, "Not installed in Steam")
    assert entry_status(AppEntry("A", STEAM, "730"), {"730"})[0] is True
    assert entry_status(AppEntry("A", WEBSITE, "https://x.com"))[0] is True


def test_an_old_list_loses_apps_you_dont_have_and_gains_your_games(monkeypatch):
    monkeypatch.setattr(apps_mod, "_installed_steam_ids", lambda: {"730"})
    monkeypatch.setattr(apps_mod, "found_games", lambda *a, **k: found_games(GAMES[1:], []))
    old = {"apps": [  # an apps.json from v1.34 (no "version")
        {"name": "Deadlock", "launch_type": "steam", "target": "1422450", "close": "ask"},
        {"name": "Roblox", "launch_type": "program", "target": ""},
        {"name": "Bloxstrap", "launch_type": "program", "target": r"%LOCALAPPDATA%\Bloxstrap\Bloxstrap.exe"},
        {"name": "My thing", "launch_type": "program", "target": r"C:\mine.exe", "aliases": ["thing"]}]}
    apps_mod.apps_path().parent.mkdir(parents=True, exist_ok=True)
    apps_mod.apps_path().write_text(json.dumps(old))
    try:
        names = [a.name for a in load_apps()]
        assert names == ["My thing", "Counter-Strike 2"]
        assert json.loads(apps_mod.apps_path().read_text())["version"] == apps_mod.APPS_VERSION
        assert [a.name for a in load_apps()] == names                  # only once
    finally:
        apps_mod.apps_path().unlink()


def test_add_app_picker_lists_whats_installed(rig_parts=None):
    from capri.assistant import Assistant
    from capri.commands.catalog import Catalog
    from capri.commands.router import CommandRouter
    from capri.ui.settings_window import AppPicker, SettingsWindow
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from test_v11 import FakeCompanion, FakeSpeaker, FakeSystem
    from capri.controller import CompanionController
    from capri.voice.service import VoiceService
    save_apps([AppEntry("Discord", PROGRAM, r"C:\d.exe")])
    try:
        catalog = Catalog(load_apps, lambda: GAMES, lambda: SHORTS)
        assistant = Assistant(CompanionController(), Settings(), VoiceService(True, False, "", 0.8), FakeSpeaker())
        router = CommandRouter(assistant, FakeCompanion(), catalog, FakeSystem([]))
        win = SettingsWindow(router, Settings(), QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [])
        assert win.table.isColumnHidden(5)                           # advanced columns tucked away
        choices = win.installed_choices()
        names = [c.name for c in choices]
        assert names[:3] == ["Counter-Strike 2", "Deadlock", "Fortnite"] and "Notepad" in names
        picker = AppPicker(win, choices, {"discord"})
        picker.search.setText("dead")
        visible = [picker.list.item(i).text() for i in range(picker.list.count()) if not picker.list.isRowHidden(i)]
        assert len(visible) == 1 and visible[0].startswith("Deadlock")
        item = next(picker.list.item(i) for i in range(picker.list.count())
                    if picker.list.item(i).text().startswith("Deadlock"))
        item.setCheckState(Qt.CheckState.Checked)
        assert win.add_entries(picker.chosen()) == 1
        r = win.table.rowCount() - 1
        assert win.table.item(r, 0).text() == "Deadlock" and win.table.item(r, 3).text() == "1422450"
        assert "Steam" in win.table.item(r, 4).text()
        win.add_my_games()                                            # the other two games
        assert win.table.rowCount() == 4
        win.save()
        assert [a.name for a in load_apps()] == ["Discord", "Deadlock", "Counter-Strike 2", "Fortnite"]
    finally:
        apps_mod.apps_path().unlink(missing_ok=True)


# -- what she remembers about you -------------------------------------------------------------------------------------
def test_memory_is_saved_in_your_user_folder_and_read_back(tmp_path):
    path = tmp_path / "about_you.json"
    me = AboutYou(path)
    assert me.handle("my name is sam") == ("told_name", "Sam")
    assert me.handle("I love deadlock")[0] == "told_likes"
    assert me.handle("my favourite food is ramen") == ("told_favorite", "food|ramen")
    assert me.handle("remember that my exam is on friday")[0] == "told_notes"
    again = AboutYou(path)                                          # next time Capri starts
    assert again.handle("what's my name") == ("ask_name", "Sam")
    assert again.handle("what's my favourite food") == ("ask_favorite", "food|ramen")
    assert "deadlock" in again.handle("what do you know about me")[1]
    assert again.handle("forget that i love deadlock")[0] == "forgot"
    assert "deadlock" not in again.summary()
    assert again.handle("forget everything about me") == ("forget_ask", "")
    assert again.handle("yes") == ("forget_done", "")
    assert not path.exists() and again.empty()


def test_the_default_memory_file_is_not_in_capris_folder():
    path = about_you.memory_path()
    project = Path(__file__).resolve().parent.parent
    assert project not in path.parents and path.name == "about_you.json"


@pytest.mark.parametrize("said, personal", [
    ("my name is sam", True), ("i'm from glasgow", True), ("what do you know about me", True),
    ("forget everything about me", True), ("i love you", False), ("open discord", False),
    ("tell me a joke", False), ("what's the weather", False),
])
def test_what_counts_as_personal(said, personal):
    assert is_personal(said) is personal


def test_personal_things_never_reach_the_ai():
    brain = FakeBrain(types.SimpleNamespace(text="hi", intent=None, intents=[], error=False, missing=False,
                                            emotion="happy"))
    r = rig(FakeDesktop(), settings=Settings(slang=False, ai_enabled=True), brain=brain)
    r.router.handle("my name is sam")
    r.router.handle("what's my name")
    assert brain.asked == []
    assert "Sam" in r.speaker.lines[-1]
    r.router.handle("tell me something cool")                      # not personal: the AI gets it
    assert settle(3, lambda: brain.asked == ["tell me something cool"])


def test_forget_everything_asks_first():
    r = rig(FakeDesktop())
    memory = r.router.chatbot.memory
    memory.learn("name", "sam")
    r.service.command.emit("forget everything about me")
    assert not memory.empty()
    r.service.command.emit("no")
    assert not memory.empty()
    r.service.command.emit("forget everything about me")
    r.service.command.emit("yes")
    assert memory.empty()


def test_the_ai_gets_your_memory_only_if_you_say_so():
    from capri.ai import claude
    me = AboutYou(None)
    me.learn("name", "sam")
    try:
        claude.ABOUT_USER = lambda: ""
        assert "Sam" not in claude.system_prompt(False)
        claude.ABOUT_USER = me.for_ai
        assert "Sam" in claude.system_prompt(False)
    finally:
        claude.ABOUT_USER = lambda: ""


def test_scrub_takes_your_user_name_out():
    text = r"Saved to C:\Users\samuel\Pictures\Screenshots and /home/samuel/x - hi samuel"
    out = scrub(text, ["samuel"])
    assert "samuel" not in out.lower() and r"C:\Users\you\Pictures" in out and "/home/you/x" in out


def test_ai_requests_are_scrubbed(monkeypatch):
    from capri.ai import openai_compat
    monkeypatch.setattr(openai_compat, "scrub", lambda t: t.replace("samuel", "you"))
    brain = openai_compat.OpenAIBrain.__new__(openai_compat.OpenAIBrain)
    brain.messages, brain._last, brain._clock = [], 0.0, lambda: 0.0
    brain.ready = lambda: (True, "")
    brain._loop = lambda: None
    try:
        brain.ask("open C:\\Users\\samuel\\cv.pdf")
    except Exception:
        pass
    assert brain.messages and "samuel" not in json.dumps(brain.messages)


# -- Parakeet ---------------------------------------------------------------------------------------------------------
def test_parakeet_text_looks_like_voskes():
    from capri.voice.parakeet import plain
    assert plain("Hey Capri, open Discord.") == "hey capri open discord"
    assert plain("Play Chicago by M.J.!") == "play chicago by m j"
    assert plain("I'm here") == "i'm here"


class FakeSherpa:
    made = []

    class OfflineRecognizer:
        @staticmethod
        def from_transducer(**kw):
            FakeSherpa.made.append(kw)
            return FakeSherpa.Rec()

    class Rec:
        def create_stream(self):
            s = types.SimpleNamespace(result=types.SimpleNamespace(text=""), got=None)
            s.accept_waveform = lambda rate, audio: setattr(s, "got", (rate, len(audio)))
            self.stream = s
            return s

        def decode_stream(self, s):
            s.result.text = "Open Discord." if s.got and s.got[0] == 16000 else "?"


def test_parakeet_ears(monkeypatch, tmp_path):
    from capri.voice import parakeet
    for f in parakeet.FILES:
        (tmp_path / f).write_text("x")
    monkeypatch.setitem(sys.modules, "sherpa_onnx", FakeSherpa)
    ears = parakeet.ParakeetEars(lambda: tmp_path, threads=2)
    pcm = (np.sin(np.arange(48000) / 10) * 8000).astype(np.int16).tobytes()     # 1 s at 48 kHz
    assert ears.transcribe(pcm, 48000) == "open discord"                         # resampled to 16 kHz
    kw = FakeSherpa.made[-1]
    assert kw["model_type"] == "nemo_transducer" and kw["encoder"].endswith("encoder.int8.onnx")
    ears.rest(True)                                                             # in a game: Vosk alone
    assert ears.transcribe(pcm, 48000) == "" and ears._recognizer is None
    assert ears.transcribe(b"\0\0" * 100, 16000) == ""                          # too short


def _tarball(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def test_parakeet_download(tmp_path):
    from capri.voice import parakeet
    root = parakeet.MODEL_NAME
    data = _tarball({f"{root}/{f}": b"x" for f in parakeet.FILES} | {f"{root}/test_wavs/0.wav": b"RIFF"})
    seen = []
    target = parakeet.download(lambda done, total: seen.append((done, total)), dest=tmp_path,
                               opener=lambda url, timeout: FakeResponse(data))
    assert target == tmp_path / root and all((target / f).is_file() for f in parakeet.FILES)
    assert not (target / "test_wavs").exists() and seen[-1][0] == seen[-1][1]


def test_parakeet_download_refuses_unsafe_archives(tmp_path):
    from capri.voice import parakeet
    data = _tarball({"../evil.txt": b"x"})
    with pytest.raises(RuntimeError):
        parakeet.download(dest=tmp_path, opener=lambda url, timeout: FakeResponse(data))
    assert not (tmp_path.parent / "evil.txt").exists()
