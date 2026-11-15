"""2.6.3: macOS support - the parts that can be checked without a Mac (the system calls themselves run on the
Mac build in CI)."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capri.mac import apps, desktop, hotkeys, quartz  # noqa: E402


def test_keys_read_the_mac_way():
    assert quartz.parse_combo("ctrl+shift+m") == (quartz.KEYCODES["m"], 0x100000 | 0x20000)   # Ctrl = Command
    assert quartz.parse_combo("alt+f4") == (quartz.KEYCODES["f4"], 0x80000)                   # Alt = Option
    assert quartz.parse_combo("control+c")[1] == 0x40000                                      # real Control
    assert quartz.parse_combo("ctrl+nonsense") is None
    assert hotkeys.parse("ctrl+alt+shift+c") == (quartz.KEYCODES["c"], 0x100000 | 0x80000 | 0x20000)
    assert hotkeys.parse("c") is None                           # a shortcut needs a modifier


def test_hotkey_matching_ignores_other_flags():
    hk = hotkeys.MacHotkeys()
    hk._start = lambda: None
    hit = []
    assert hk.register("ctrl+alt+shift+c", lambda: hit.append(1))
    fn = hk.matches(quartz.KEYCODES["c"], 0x100000 | 0x80000 | 0x20000 | 0x100)   # + a device bit
    assert fn is not None
    fn()
    assert hit == [1] and hk.matches(quartz.KEYCODES["c"], 0x100000) is None


def test_shortcuts_shown_with_mac_symbols():
    from capri.hotkeys import pretty
    assert pretty("ctrl+alt+shift+c", mac=True) == "⌘⌥⇧C"
    assert pretty("ctrl+alt+shift+c", mac=False) == "Ctrl+Alt+Shift+C"


def test_apps_found_from_their_bundles(tmp_path):
    for name, info in (("Discord.app", {"CFBundleName": "Discord", "CFBundleExecutable": "Discord",
                                        "CFBundleIdentifier": "com.hnc.Discord"}),
                       ("Visual Studio Code.app", {"CFBundleDisplayName": "Code", "CFBundleExecutable": "Electron"}),
                       ("Broken.app", None)):
        c = tmp_path / name / "Contents"
        c.mkdir(parents=True)
        if info is not None:
            (c / "Info.plist").write_bytes(plistlib.dumps(info))
    found = {a.name: a for a in apps.installed_apps([tmp_path])}
    assert set(found) == {"Discord", "Code", "Broken"}
    assert found["Code"].executable == "Electron" and found["Discord"].bundle_id == "com.hnc.Discord"
    from capri.commands.discovery import mac_shortcuts
    sc = {s.name: s for s in mac_shortcuts([tmp_path])}
    assert sc["Discord"].names == ("discord",) and sc["Discord"].path.suffix == ".app"


def test_apps_open_the_mac_way(tmp_path):
    calls = []
    system = desktop.MacSystem(popen=lambda argv, **kw: calls.append(argv))
    app = tmp_path / "Discord.app"
    (app / "Contents").mkdir(parents=True)
    system.launch_program(str(app), [])
    system.launch_program(str(app), ["--minimized"])
    system.open_item("spotify:track:1")
    (tmp_path / "notes.txt").write_text("hi")
    system.reveal(str(tmp_path / "notes.txt"))
    assert calls[0] == ["open", "-a", str(app)]
    assert calls[1] == ["open", "-a", str(app), "--args", "--minimized"]
    assert calls[2] == ["open", "spotify:track:1"]
    assert calls[3] == ["open", "-R", str(tmp_path / "notes.txt")]


def test_power_commands_are_fixed_and_mac_ones():
    for action in ("shutdown", "restart", "sleep", "lock"):
        for argv in desktop.POWER_COMMANDS[action]:
            assert argv[0] in ("osascript", "pmset") and all(isinstance(a, str) for a in argv)
    assert "dock" in desktop.MAC_PROTECTED and "finder" in desktop.MAC_PROTECTED


def test_start_at_login_is_a_launch_agent(tmp_path):
    text = desktop.agent_text(["/usr/bin/open", "-a", "/Applications/Capri.app", "--args", "--startup"])
    data = plistlib.loads(text.encode())
    assert data["Label"] == "com.capri.companion" and data["RunAtLoad"] is True
    assert data["ProgramArguments"][-1] == "--startup"
    assert desktop.agent_file(tmp_path) == tmp_path / "Library" / "LaunchAgents" / "com.capri.companion.plist"


def test_updater_knows_the_mac_app(monkeypatch):
    from capri import updater
    monkeypatch.setattr(updater, "MAC", True)
    monkeypatch.setattr(updater, "LINUX", False)
    assert updater.asset_pattern() is updater.MAC_ASSET and updater.MAC_ASSET.match("Capri-macOS.zip")
    info = {"version": "99.0.0", "file": "Capri-Setup-99.0.0.exe", "size": 1, "sha256": "a",
            "linux": {"file": "Capri-x86_64.AppImage", "size": 2, "sha256": "b"},
            "mac": {"file": "Capri-macOS.zip", "size": 3, "sha256": "c"}}
    got = updater._from_latest_json(info, "2.6.2")
    assert got and got.name == "Capri-macOS.zip" and got.size == 3


def test_mac_words():
    import importlib
    import capri.words as words
    monkey = sys.platform
    try:
        sys.platform = "darwin"
        importlib.reload(words)
        assert words.FILE_MANAGER == "Finder" and "Applications" in words.START_MENU
    finally:
        sys.platform = monkey
        importlib.reload(words)
