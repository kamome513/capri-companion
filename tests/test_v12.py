"""v1.2: Discord sound-alikes ("on meet on discord"), every installed app incl. Store apps
(Clipchamp, PowerPoint...), folders, and "show me X in File Explorer"."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_commands import BLOX, DEADLOCK, DISCORD, GAME, OPERA, ROBLOX_SC, SHORT  # noqa: E402
from test_stage5 import FakeSpeaker, settle  # noqa: E402
from test_commands import FakeCompanion, FakeSystem  # noqa: E402

from capri.assistant import Assistant  # noqa: E402
from capri.commands import files  # noqa: E402
from capri.commands.catalog import Catalog  # noqa: E402
from capri.commands.discovery import InstalledApp, installed_apps  # noqa: E402
from capri.commands.parser import Intent, Kind, parse  # noqa: E402
from capri.commands.router import CommandRouter, Services  # noqa: E402
from capri.commands.system import ProcessInfo  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402
from capri.voice.service import VoiceService  # noqa: E402


# -- Discord: what the speech model actually writes down ---------------------------------------------------
@pytest.mark.parametrize("heard, action", [
    ("on meet on discord", "unmute"), ("on meet me on discord", "unmute"), ("unmute me on discord", "unmute"),
    ("on mute me", "unmute"), ("and mute me", "unmute"), ("on meat on discord", "unmute"),
    ("un mute me in discord", "unmute"), ("on mute", "unmute"), ("discord unmute", "unmute"), ("im mute me", "unmute"),
    ("turn my mic on", "unmute"), ("take me off mute", "unmute"), ("turn on my microphone", "unmute"),
    ("mute me", "mute"), ("put me on mute", "mute"), ("turn my mic off", "mute"), ("meet me", "mute"),
    ("the fan me", "deafen"), ("defend me on discord", "deafen"), ("deafen me", "deafen"),
    ("on deafen", "undeafen"), ("undefined", "undeafen"), ("on the fan on discord", "undeafen"),
    ("undeafen", "undeafen"), ("undeafen me", "undeafen"),
])
def test_discord_sound_alikes(heard, action):
    assert parse(heard) == Intent(Kind.DISCORD, query=action)


@pytest.mark.parametrize("heard", ["the fan", "meet", "definitely", "turn on the fan", "i will meet you"])
def test_sound_alikes_alone_are_not_discord(heard):
    assert parse(heard).kind is not Kind.DISCORD


def test_opening_and_closing_discord_still_work():
    assert parse("open discord").kind is Kind.OPEN
    assert parse("close discord").kind is Kind.CLOSE


# -- every installed app --------------------------------------------------------------------------------
APPS_FOLDER = [
    ("Clipchamp", "Clipchamp.Clipchamp_yxz26nhyzhsrt!App"),
    ("PowerPoint", r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"),
    ("Calculator", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    ("Notepad", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),          # also a Start-menu shortcut
    ("Microsoft Store website", "https://apps.microsoft.com"),             # web links are skipped
    ("Uninstall Thing", "Thing.Uninstall!App"),                            # uninstallers too
    ("", "Nameless!App"),
]


def test_installed_apps_from_windows_list():
    found = installed_apps(lambda: APPS_FOLDER)
    names = [a.name for a in found]
    assert names == ["Calculator", "Clipchamp", "Notepad", "PowerPoint"]
    clip = next(a for a in found if a.name == "Clipchamp")
    assert clip.store_package == "Clipchamp.Clipchamp" and clip.exe is None
    ppt = next(a for a in found if a.name == "PowerPoint")
    assert ppt.exe is not None and not ppt.store_package
    assert installed_apps(lambda: (_ for _ in ()).throw(OSError("no COM"))) == []


def places_for(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir(exist_ok=True)
    return {"downloads": str(downloads), "my downloads": str(downloads), "file explorer": r"C:\Windows\explorer.exe",
            "recycle bin": "shell:RecycleBinFolder"}


def catalog(tmp_path=None):
    return Catalog(lambda: [DISCORD, BLOX, DEADLOCK, OPERA], lambda: [GAME], lambda: [SHORT, ROBLOX_SC],
                   load_installed=lambda: installed_apps(lambda: APPS_FOLDER),
                   load_places=lambda: places_for(tmp_path) if tmp_path else {})


def test_catalog_finds_store_and_office_apps_by_sound():
    c = catalog()
    assert c.find("clip champ").target.installed.name == "Clipchamp"
    assert c.find("power point").target.installed.name == "PowerPoint"
    assert c.find("calculator").target.kind == "installed"
    assert c.find("notepad").target.shortcut == SHORT          # the shortcut wins a same-named app


def rig(tmp_path, roots=None, ai=False):
    controller = CompanionController()
    service = VoiceService(True, False, "", 0.8)
    service.listen_now = lambda *a: None
    speaker = FakeSpeaker()
    assistant = Assistant(controller, Settings(slang=False, ai_enabled=ai), service, speaker)
    system = FakeSystem([ProcessInfo(10, "Discord.exe"),
                         ProcessInfo(44, "Clipchamp.exe", os.sep.join(
                             ["C:", "Program Files", "WindowsApps", "Clipchamp.Clipchamp_2.9.1.0_x64__yxz26nhyzhsrt",
                              "Clipchamp.exe"]))])
    router = CommandRouter(assistant, FakeCompanion(), catalog(tmp_path), system,
                           Services(settings=assistant.settings,
                                    file_roots=(lambda: roots) if roots is not None else None))
    assistant.command_handler = router.handle
    return controller, service, system, router


def test_open_store_app_through_windows_app_list(tmp_path):
    controller, service, system, router = rig(tmp_path)
    service.command.emit("open clip champ")
    assert system.calls == [("open", "shell:AppsFolder\\Clipchamp.Clipchamp_yxz26nhyzhsrt!App")]
    assert controller.message == "Launching Clipchamp."
    service.command.emit("open power point")
    assert system.calls[-1][1].endswith("POWERPNT.EXE")


def test_close_store_app_by_its_package_folder(tmp_path):
    controller, service, system, router = rig(tmp_path)
    name, pids, mode = router.catalog.running_for("clipchamp", system.processes())
    assert (name, pids) == ("Clipchamp", [44])


def test_open_folders_and_explorer(tmp_path):
    controller, service, system, router = rig(tmp_path)
    service.command.emit("open my downloads folder")
    assert system.calls[-1] == ("open", str(tmp_path / "Downloads"))
    service.command.emit("open file explorer")
    assert system.calls[-1] == ("open", r"C:\Windows\explorer.exe")
    service.command.emit("open the recycle bin")
    assert system.calls[-1] == ("open", "shell:RecycleBinFolder")


# -- "show me X in File Explorer" -------------------------------------------------------------------------
@pytest.mark.parametrize("text, target", [
    ("show me clip champ on file explorer", "clip champ"), ("show me clipchamp in file explorer", "clipchamp"),
    ("open my homework folder in file explorer", "homework"), ("where is my essay", "essay"),
    ("where did i put my notes", "notes"), ("find my minecraft screenshots", "minecraft screenshots"),
    ("show downloads in explorer", "downloads"),
])
def test_parse_reveal(text, target):
    assert parse(text) == Intent(Kind.REVEAL, (target,))


def test_show_store_app_in_explorer_is_honest(tmp_path):
    controller, service, system, router = rig(tmp_path)
    service.command.emit("show me clip champ on file explorer")
    assert system.calls == [("open", "shell:AppsFolder")]
    assert "Store app" in controller.message


def test_show_a_real_program_selects_its_file(tmp_path):
    exe = tmp_path / "POWERPNT.EXE"
    exe.write_bytes(b"MZ")
    c = Catalog(lambda: [], lambda: [], lambda: [],
                load_installed=lambda: [InstalledApp("PowerPoint", str(exe), exe)])
    controller, service, system, router = rig(tmp_path)
    router.catalog = c
    service.command.emit("show me powerpoint in file explorer")
    assert system.calls == [("reveal", str(exe))]
    assert controller.message == "Here's PowerPoint in File Explorer."


def make_files(tmp_path):
    docs = tmp_path / "Documents"
    (docs / "School" / "Homework").mkdir(parents=True)
    (docs / "School" / "Homework" / "maths.docx").write_text("x")
    (docs / "Essay.docx").write_text("x")
    (docs / "node_modules" / "essay").mkdir(parents=True)        # skipped folder
    (tmp_path / "Downloads").mkdir(exist_ok=True)
    (tmp_path / "Downloads" / "cool game.exe").write_bytes(b"MZ")
    return [docs, tmp_path / "Downloads"]


def test_file_finder(tmp_path):
    roots = make_files(tmp_path)
    hit = files.find("homework", roots)
    assert hit.path.name == "Homework" and hit.is_dir
    assert files.find("essay", roots).path.name == "Essay.docx"
    assert files.find("cool game", roots).runnable
    assert files.find("photoshop", roots) is None


def test_reveal_one_of_your_folders(tmp_path):
    roots = make_files(tmp_path)
    controller, service, system, router = rig(tmp_path, roots)
    service.command.emit("show me my homework folder in file explorer")
    assert settle(3, lambda: controller.state is State.SUCCESS)
    assert system.calls == [("reveal", str(roots[0] / "School" / "Homework"))]


def test_open_a_document_by_name_but_never_run_a_program(tmp_path):
    roots = make_files(tmp_path)
    controller, service, system, router = rig(tmp_path, roots)
    service.command.emit("open essay")
    assert settle(3, lambda: controller.state is State.SUCCESS)
    assert system.calls == [("open", str(roots[0] / "Essay.docx"))]
    service.command.emit("open cool game")
    assert settle(3, lambda: len(system.calls) == 2)
    assert system.calls[-1][0] == "reveal"                     # shown, not started
    assert "program file" in controller.message


def test_missing_file_still_says_so(tmp_path):
    roots = make_files(tmp_path)
    controller, service, system, router = rig(tmp_path, roots)
    service.command.emit("where is my tax return")
    assert settle(3, lambda: controller.state is State.ERROR)
    assert controller.message == "Couldn't find tax return in your files."


# -- unmute while deafened -----------------------------------------------------------------------------
class Keys:
    def __init__(self):
        self.calls = []

    def press_in_window(self, pids, combo):
        self.calls.append(combo)
        return True

    def press_keys(self, combo):
        self.calls.append(combo)


def discord_rig():
    from test_v11 import rig as v11_rig
    keys = Keys()
    return keys, v11_rig(keys)


def test_unmute_presses_mute_normally():
    keys, r = discord_rig()
    r.service.command.emit("unmute me on discord")
    assert keys.calls == ["ctrl+shift+m"] and r.controller.message == "Pressed unmute on Discord."


def test_unmute_after_she_deafened_you_undeafens():
    keys, r = discord_rig()
    r.service.command.emit("deafen me")
    r.service.command.emit("unmute me")
    assert keys.calls == ["ctrl+shift+d", "ctrl+shift+d"]         # undeafen: Discord gives your mic back
    assert "undeafened" in r.controller.message
    r.service.command.emit("mute me")
    r.service.command.emit("unmute me")
    assert keys.calls[2:] == ["ctrl+shift+m", "ctrl+shift+m"]      # not deafened any more: plain mute key


def test_undeafen_then_unmute():
    keys, r = discord_rig()
    r.service.command.emit("deafen me")
    r.service.command.emit("undeafen me")
    r.service.command.emit("unmute me")
    assert keys.calls == ["ctrl+shift+d", "ctrl+shift+d", "ctrl+shift+m"]


# -- search up ___ on opera / google --------------------------------------------------------------------
@pytest.mark.parametrize("text, query, where", [
    ("search up cats on opera", "cats", ("opera",)), ("search up best deadlock builds on google", "best deadlock builds", ("google",)),
    ("search up how to fix my pc", "how to fix my pc", ()), ("search for dogs on youtube", "dogs", ("youtube",)),
    ("search on opera for funny videos", "funny videos", ("opera",)), ("look up nf songs on opera gx", "nf songs", ("opera",)),
    ("search the weather in chrome", "the weather", ("chrome",)), ("google how tall is mount everest", "how tall is mount everest", ()),
    ("search cats up", "cats", ()),
])
def test_parse_search_where(text, query, where):
    assert parse(text) == Intent(Kind.SEARCH, where, query=query)


def test_search_in_opera_opens_opera_with_the_search(tmp_path):
    from capri.commands.apps import PROGRAM, AppEntry
    exe = tmp_path / "launcher.exe"
    exe.write_bytes(b"MZ")
    controller, service, system, router = rig(tmp_path)
    router.catalog = Catalog(lambda: [AppEntry("Opera GX", PROGRAM, str(exe), processes=["opera.exe"])],
                             lambda: [], lambda: [])
    service.command.emit("search mode")
    service.command.emit("search up cats on opera")
    assert system.calls == [("program", str(exe), ("https://www.google.com/search?q=cats",))]
    assert controller.message == "Searching Opera GX for “cats”."


def test_search_on_google_and_sites(tmp_path):
    controller, service, system, router = rig(tmp_path)
    service.command.emit("search mode")
    service.command.emit("search up best deadlock builds on google")
    assert system.calls[-1] == ("open", "https://www.google.com/search?q=best+deadlock+builds")
    service.command.emit("search mode")
    service.command.emit("search for dogs on youtube")
    assert system.calls[-1] == ("open", "https://www.youtube.com/results?search_query=dogs")
    assert controller.message == "Searching YouTube for “dogs”."


def test_search_in_a_browser_you_dont_have_uses_the_default(tmp_path):
    controller, service, system, router = rig(tmp_path)
    service.command.emit("search mode")
    service.command.emit("search up cats on firefox")
    assert system.calls[-1] == ("open", "https://www.google.com/search?q=cats")
    assert "default browser" in controller.message
