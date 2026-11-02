"""Stage 4: command parsing, name matching, discovery, and the router (fake system)."""

from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.assistant import Assistant  # noqa: E402
from capri.commands import apps as apps_mod  # noqa: E402
from capri.commands import router as router_mod  # noqa: E402
from capri.commands.apps import (CLOSE_ASK, CLOSE_FORCE, CLOSE_NORMAL, PROGRAM, STEAM,  # noqa: E402
                                 AppEntry, load_apps, save_apps)
from capri.commands.catalog import Catalog, spoken_website, url_is_safe  # noqa: E402
from capri.commands.discovery import Shortcut, SteamGame, lnk_target, shortcuts, steam_games  # noqa: E402
from capri.commands.fuzzy import similarity, sound_key  # noqa: E402
from capri.commands.parser import Kind, parse, parse_yes_no  # noqa: E402
from capri.commands.router import CommandRouter  # noqa: E402
from capri.commands.system import ProcessInfo  # noqa: E402
from capri.controller import CompanionController  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402
from capri.voice.service import VoiceService  # noqa: E402


# -- parser ------------------------------------------------------------------------
@pytest.mark.parametrize("text,kind,targets", [
    ("open discord", Kind.OPEN, ("discord",)),
    ("please launch dead lock", Kind.OPEN, ("deadlock",)),
    ("can you open up blocks strap for me", Kind.OPEN, ("blocks strap",)),
    ("start the minecraft launcher", Kind.OPEN, ("minecraft launcher",)),
    ("open discord and spotify", Kind.OPEN, ("discord", "spotify")),
    ("close discord", Kind.CLOSE, ("discord",)),
    ("close discord and deadlock", Kind.CLOSE, ("discord", "deadlock")),
    ("quit the spotify app", Kind.CLOSE, ("spotify",)),
    ("shut down chrome", Kind.CLOSE, ("chrome",)),
    ("kill roblox", Kind.CLOSE, ("roblox",)),
])
def test_parse_open_close(text, kind, targets):
    intent = parse(text)
    assert intent.kind is kind and intent.targets == targets


@pytest.mark.parametrize("text,kind", [
    ("what time is it", Kind.TIME), ("whats the time", Kind.TIME), ("what is the date", Kind.DATE),
    ("switch to compact mode", Kind.COMPACT_ON), ("compact mode", Kind.COMPACT_ON),
    ("switch to normal mode", Kind.COMPACT_OFF), ("exit compact mode", Kind.COMPACT_OFF),
    ("hide the status panel", Kind.PANEL_HIDE), ("close the panel", Kind.PANEL_HIDE),
    ("show the status panel", Kind.PANEL_SHOW), ("hide", Kind.HIDE), ("come back", Kind.SHOW),
    ("never mind", Kind.CANCEL), ("make me a sandwich", Kind.UNKNOWN), ("", Kind.UNKNOWN),
])
def test_parse_other(text, kind):
    assert parse(text).kind is kind


def test_parse_search():
    i = parse("search for best deadlock builds")
    assert i.kind is Kind.SEARCH and i.query == "best deadlock builds"
    assert parse("google cyberpunk edgerunners").query == "cyberpunk edgerunners"


def test_yes_no():
    for yes in ("yes", "yeah", "yep do it", "sure", "capri yes", "do it"):
        assert parse_yes_no(yes) is True, yes
    for no in ("no", "nope", "cancel", "leave it", "no thanks"):
        assert parse_yes_no(no) is False, no
    assert parse_yes_no("banana") is None


# -- fuzzy matching ------------------------------------------------------------------
@pytest.mark.parametrize("heard,name", [
    ("blocks strap", "Bloxstrap"), ("blox strap", "Bloxstrap"), ("dead lock", "Deadlock"),
    ("counter strike two", "Counter-Strike 2"), ("mine craft", "Minecraft"), ("rob locks", "Roblox"),
    ("opera", "Opera GX"), ("chrome", "Google Chrome"),
])
def test_sounds_alike(heard, name):
    assert similarity(heard, name) >= 0.8


@pytest.mark.parametrize("heard,name", [
    ("discord", "Deadlock"), ("spotify", "Steam"), ("chrome", "Roblox"), ("steam", "Spotify"),
])
def test_different_names_dont_match(heard, name):
    assert similarity(heard, name) < 0.6


def test_sound_key():
    assert sound_key("Bloxstrap") == sound_key("blocks strap")


# -- catalog -------------------------------------------------------------------------
DISCORD = AppEntry("Discord", PROGRAM, r"C:\Users\me\AppData\Local\Discord\Update.exe",
                   ["--processStart", "Discord.exe"], processes=["Discord.exe"], close=CLOSE_FORCE)
BLOX = AppEntry("Bloxstrap", PROGRAM, r"C:\bx\Bloxstrap.exe", processes=["Bloxstrap.exe"])
DEADLOCK = AppEntry("Deadlock", STEAM, "1422450", processes=["deadlock.exe"], close=CLOSE_ASK)
OPERA = AppEntry("Opera GX", PROGRAM, "", processes=["opera.exe"])
GAME = SteamGame("730", "Counter-Strike 2", Path(r"D:\Steam\steamapps\common\Counter-Strike Global Offensive"))
SHORT = Shortcut("Notepad++", Path(r"C:\Start\Notepad++.lnk"), Path(r"C:\Program Files\Notepad++\notepad++.exe"))
ROBLOX_SC = Shortcut("Roblox Player", Path(r"C:\Start\Roblox Player.lnk"), None)


def make_catalog(apps=None):
    return Catalog(lambda: list(apps if apps is not None else [DISCORD, BLOX, DEADLOCK, OPERA]),
                   lambda: [GAME], lambda: [SHORT, ROBLOX_SC])


def test_catalog_finds_configured_discovered_and_sites():
    c = make_catalog()
    assert c.find("blocks strap").target.entry is BLOX
    assert c.find("discord").target.entry is DISCORD
    assert c.find("counter strike two").target.game == GAME
    assert c.find("notepad").target.shortcut == SHORT
    assert c.find("youtube").target.url == "https://www.youtube.com"
    assert c.find("twitch dot tv").target.url == "https://twitch.tv"
    assert c.find("photoshop") is None


def test_unconfigured_entry_falls_back_to_shortcut():
    roblox = AppEntry("Roblox", PROGRAM, "", processes=["RobloxPlayerBeta.exe"])
    c = make_catalog([roblox])
    assert c.find("roblox").target.shortcut == ROBLOX_SC      # usable shortcut beats empty entry
    c2 = make_catalog([OPERA])
    m = c2.find("opera gx")
    assert m.target.entry is OPERA and not OPERA.is_configured()   # reported as "not set up"


def test_running_for():
    procs = [ProcessInfo(10, "Discord.exe"), ProcessInfo(11, "Discord.exe"),
             ProcessInfo(20, "cs2.exe", r"D:\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\cs2.exe"),
             ProcessInfo(30, "notepad++.exe", r"C:\Program Files\Notepad++\notepad++.exe"),
             ProcessInfo(40, "vlc.exe", r"C:\VLC\vlc.exe")]
    c = make_catalog()
    assert c.running_for("discord", procs) == ("Discord", [10, 11], CLOSE_FORCE)
    if os.name == "nt":   # matching by install folder needs real Windows paths
        assert c.running_for("counter strike two", procs) == ("Counter-Strike 2", [20], CLOSE_ASK)
        assert c.running_for("notepad", procs) == ("Notepad++", [30], CLOSE_NORMAL)


def test_running_for_uses_process_names_when_unlisted():
    procs = [ProcessInfo(40, "vlc.exe", "/opt/vlc"), ProcessInfo(41, "obs64.exe")]
    c = make_catalog()
    assert c.running_for("vlc", procs) == ("vlc", [40], CLOSE_NORMAL)
    name, pids, _ = c.running_for("deadlock", procs)
    assert name == "Deadlock" and pids == []


def test_url_safety():
    assert url_is_safe("https://youtube.com") and url_is_safe("spotify:") and url_is_safe("steam://run/1")
    for bad in ("file:///C:/Windows/System32/cmd.exe", "javascript:alert(1)", "vbscript:x", "cmd.exe",
                "ms-msdt:/id", "C:\\evil.bat"):
        assert not url_is_safe(bad), bad
    assert spoken_website("youtube dot com") == "https://youtube.com"
    assert spoken_website("www dot github dot com") == "https://github.com"
    assert spoken_website("discord") is None


# -- discovery -----------------------------------------------------------------------
def test_steam_games(tmp_path):
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    other = tmp_path / "Games" / "SteamLibrary"
    (other / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n "1"\n {\n  "path" "%s"\n }\n}\n'
        % (str(root).replace("\\", "\\\\"), str(other).replace("\\", "\\\\")))
    (root / "steamapps" / "appmanifest_1422450.acf").write_text(
        '"AppState"\n{\n "appid" "1422450"\n "name" "Deadlock"\n "installdir" "Deadlock"\n}\n')
    (other / "steamapps" / "appmanifest_228980.acf").write_text(
        '"AppState"\n{\n "appid" "228980"\n "name" "Steamworks Common Redistributables"\n "installdir" "x"\n}\n')
    (other / "steamapps" / "appmanifest_730.acf").write_text(
        '"AppState"\n{\n "appid" "730"\n "name" "Counter-Strike 2"\n "installdir" "Counter-Strike Global Offensive"\n}\n')
    games = steam_games(root)
    assert [(g.appid, g.name) for g in games] == [("730", "Counter-Strike 2"), ("1422450", "Deadlock")]
    assert games[1].install_dir == root / "steamapps" / "common" / "Deadlock"


def make_lnk(path: Path, target: str) -> None:
    """Minimal valid .lnk: header + LinkInfo with a LocalBasePath (MS-SHLLINK)."""
    clsid = bytes.fromhex("0114020000000000c000000000000046")
    header = struct.pack("<I16sI", 0x4C, clsid, 0x02)        # flags: HasLinkInfo
    header += b"\x00" * (76 - len(header))
    hdr = 0x1C
    base = target.encode("latin-1") + b"\x00"
    size = hdr + len(base) + 1
    info = struct.pack("<IIIIIII", size, hdr, 0x01, hdr, hdr, 0, hdr + len(base)) + base + b"\x00"
    path.write_bytes(header + info)


def test_lnk_and_shortcut_scan(tmp_path):
    progs = tmp_path / "Programs" / "Bloxstrap"
    progs.mkdir(parents=True)
    make_lnk(progs / "Bloxstrap.lnk", r"C:\Users\me\AppData\Local\Bloxstrap\Bloxstrap.exe")
    make_lnk(progs / "Uninstall Bloxstrap.lnk", r"C:\x\uninstall.exe")
    (progs / "Bloxstrap Website.url").write_text("[InternetShortcut]\nURL=https://example.com\n")
    (tmp_path / "Programs" / "Steam game.url").write_text("[InternetShortcut]\nURL=steam://rungameid/1\n")
    found = shortcuts([tmp_path / "Programs"])
    names = [s.name for s in found]
    assert names == ["Bloxstrap", "Steam game"]
    assert str(found[0].target).endswith("Bloxstrap.exe")
    assert lnk_target(tmp_path / "Programs" / "Steam game.url") is None
    garbage = tmp_path / "bad.lnk"
    garbage.write_bytes(b"not a shortcut")
    assert lnk_target(garbage) is None


def test_apps_json_round_trip_and_defaults():
    apps_mod.apps_path().unlink(missing_ok=True)
    first = load_apps()                       # creates defaults: only what's on this PC (nothing here)
    assert not {"Deadlock", "Bloxstrap", "Minecraft", "Roblox"} & {a.name for a in first}
    assert all(a.target for a in first)
    custom = first + [AppEntry("Notes", PROGRAM, r"%WINDIR%\notepad.exe", aliases=["note pad"])]
    save_apps(custom)
    again = load_apps()
    assert again[-1] == custom[-1]
    apps_mod.apps_path().write_text('{"apps": [{"name": "X", "launch_type": "rm -rf", "close": "nuke"}, 5]}')
    weird = load_apps()
    assert len(weird) == 1 and weird[0].launch_type == PROGRAM and weird[0].close == CLOSE_NORMAL
    apps_mod.apps_path().unlink()


# -- router ---------------------------------------------------------------------------
class FakeSystem:
    def __init__(self, procs=None, stubborn=()):
        self.procs = {p.pid: p for p in (procs or [])}
        self.stubborn = set(stubborn)      # pids that ignore WM_CLOSE
        self.calls = []

    def launch_program(self, path, args):
        self.calls.append(("program", path, tuple(args)))
        if "missing" in path:
            raise FileNotFoundError(path)

    def open_item(self, target):
        self.calls.append(("open", target))

    def processes(self):
        return list(self.procs.values())

    def request_close(self, pids):
        self.calls.append(("close", tuple(pids)))
        for pid in pids:
            if pid not in self.stubborn:
                self.procs.pop(pid, None)
        return len(pids)

    def terminate(self, pids):
        self.calls.append(("terminate", tuple(pids)))
        for pid in pids:
            self.procs.pop(pid, None)

    def running(self, pids):
        return [p for p in pids if p in self.procs]

    def reveal(self, path):
        self.calls.append(("reveal", str(path)))


class FakeCompanion:
    def __init__(self):
        self.compact = self.panel = self.hidden = None

    def set_compact(self, on): self.compact = on
    def set_show_panel(self, on): self.panel = on
    def set_hidden(self, on): self.hidden = on
    def set_lounge(self, on): self.lounge = on


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(router_mod, "GRACEFUL_WAIT", 0.5)
    monkeypatch.setattr(router_mod, "FORCE_WAIT", 0.5)
    controller = CompanionController()
    service = VoiceService(True, False, "", 0.8)
    service.listen_now = lambda *a: None       # confirmations: we answer by emitting commands
    assistant = Assistant(controller, Settings(), service)
    system = FakeSystem([ProcessInfo(10, "Discord.exe"), ProcessInfo(20, "deadlock.exe"),
                         ProcessInfo(30, "Bloxstrap.exe")], stubborn={30})
    companion = FakeCompanion()
    router = CommandRouter(assistant, companion, make_catalog(), system)
    assistant.command_handler = router.handle

    def say(text):
        service.command.emit(text)

    def settle(seconds=1.5, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until and until():
                return
            time.sleep(0.01)

    return controller, service, system, companion, say, settle


def test_open_bloxstrap_from_blocks_strap(rig):
    controller, service, system, companion, say, settle = rig
    say("open blocks strap")
    assert system.calls == [("program", r"C:\bx\Bloxstrap.exe", ())]
    assert controller.state is State.SUCCESS and "Bloxstrap" in controller.message
    assert ("Match", '"blocks strap" \u2192 Bloxstrap') in controller.entries


def test_open_steam_game_and_several_apps(rig):
    controller, service, system, companion, say, settle = rig
    say("open deadlock and discord")
    assert ("open", "steam://rungameid/1422450") in system.calls
    assert ("program", DISCORD.target, ("--processStart", "Discord.exe")) in system.calls
    assert controller.message == "Opening Deadlock and Discord."


def test_open_unknown_and_unconfigured(rig):
    controller, service, system, companion, say, settle = rig
    say("open photoshop")
    assert controller.state is State.ERROR and controller.message == "Couldn't find photoshop."
    say("open opera gx")
    assert controller.message == "Opera GX isn't set up yet." and system.calls == []


def test_close_force_mode_discord(rig):
    controller, service, system, companion, say, settle = rig
    say("close discord")
    settle(until=lambda: controller.state is State.SUCCESS)
    assert ("terminate", (10,)) in system.calls
    assert controller.message == "Discord closed."


def test_close_asks_first_for_games(rig):
    controller, service, system, companion, say, settle = rig
    say("close deadlock")
    assert controller.state is State.LISTENING and controller.message == "Close Deadlock? Say yes or no."
    assert system.calls == []                    # nothing happens before you answer
    say("no")
    assert 20 in system.procs and controller.message == "Leaving Deadlock open."
    say("close deadlock")
    say("yes")
    settle(until=lambda: controller.state is State.SUCCESS)
    assert ("close", (20,)) in system.calls and 20 not in system.procs
    assert controller.message == "Deadlock closed."


def test_silence_counts_as_no(rig):
    controller, service, system, companion, say, settle = rig
    say("close deadlock")
    service.no_command.emit()
    assert 20 in system.procs and controller.message == "Leaving Deadlock open."


def test_stubborn_app_asks_before_force(rig):
    controller, service, system, companion, say, settle = rig
    say("close blocks strap")
    settle(until=lambda: controller.state is State.LISTENING)
    assert controller.message == "Bloxstrap is still running. Force close it?"
    assert ("terminate", (30,)) not in system.calls
    say("yes")
    settle(until=lambda: controller.state is State.SUCCESS)
    assert ("terminate", (30,)) in system.calls and controller.message == "Bloxstrap closed."


def test_close_several_and_not_running(rig):
    controller, service, system, companion, say, settle = rig
    say("close discord and spotify")
    settle(until=lambda: controller.state is State.SUCCESS)
    assert controller.message == "Discord closed. spotify isn't running."


def test_widget_time_search_unknown(rig):
    controller, service, system, companion, say, settle = rig
    say("switch to compact mode")
    assert companion.compact is True and controller.message == "Compact mode on."
    say("hide the status panel")
    assert companion.panel is False
    say("what time is it")
    assert controller.state is State.SUCCESS and controller.message.startswith("It's ")
    say("search for deadlock patch notes")              # outside search mode: switches it on and asks
    assert controller.message == "Search mode on. What do you want to search?" and not system.calls
    say("deadlock patch notes")
    assert system.calls[-1] == ("open", "https://www.google.com/search?q=deadlock+patch+notes")
    say("make me a sandwich")                           # 1.17: her own chatbot answers - honestly
    assert controller.state is State.SPEAKING and "sandwich" not in controller.message.lower()
    assert any(w in controller.message.lower() for w in ("can't", "not that one", "can t"))


def test_explain_is_a_dry_run(rig):
    controller, service, system, companion, say, settle = rig
    router = CommandRouter(Assistant(controller, Settings(), service), companion, make_catalog(), system)
    text = router.explain("open blocks strap")
    assert "Bloxstrap" in text and "100%" in text
    assert "Discord" in router.explain("close discord")
    assert system.calls == [] and 10 in system.procs


def test_settings_window_smoke(rig, tmp_path):
    from capri.ui.settings_window import SettingsWindow
    controller, service, system, companion, say, settle = rig
    from PySide6.QtGui import QImage
    save_apps([DISCORD, BLOX, DEADLOCK, OPERA])
    catalog = Catalog(load_apps, lambda: [GAME], lambda: [SHORT])
    router = CommandRouter(Assistant(controller, Settings(), service), companion, catalog, system)
    win = SettingsWindow(router, Settings(), QImage(8, 8, QImage.Format.Format_ARGB32), lambda: [])
    assert win.table.rowCount() == 4
    win.try_box.setText("open blocks strap")
    assert "Bloxstrap" in win.try_result.text()
    win.add_row()
    r = win.table.rowCount() - 1
    win.table.item(r, 0).setText("Notes")
    win.table.item(r, 1).setText("note pad, notepad")
    win.table.item(r, 3).setText(r"%WINDIR%\notepad.exe")
    win.save()
    saved = load_apps()
    assert saved[-1].name == "Notes" and saved[-1].aliases == ["note pad", "notepad"]
    assert router.catalog.find("note pad").target.entry.name == "Notes"
    win.table.selectRow(r)
    win.test_launch()
    assert system.calls[-1][0] == "program"
    apps_mod.apps_path().unlink()
