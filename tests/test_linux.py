"""Linux support: apps from .desktop files, the X11 desktop (windows, typing, keys, hotkeys, clicks, OCR),
power / media / autostart, games, and the wiring that picks the Linux versions.

The X11 tests start their own private Xvfb + openbox (skipped where those aren't installed)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.linux import apps as lapps  # noqa: E402
from capri.linux import desktop as ldesk  # noqa: E402

linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux")


# -- .desktop files ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("line, argv", [
    ("firefox %u", ["firefox"]),
    ('env "FOO=a b" /usr/bin/app --name="x y" %U', ["env", "FOO=a b", "/usr/bin/app", "--name=x y"]),
    ("/usr/bin/flatpak run --branch=stable --command=discord com.discordapp.Discord @@u %U @@",
     ["/usr/bin/flatpak", "run", "--branch=stable", "--command=discord", "com.discordapp.Discord", "@@u", "@@"]),
    ('sh -c "echo \\"hi\\" \\$HOME"', ["sh", "-c", 'echo "hi" $HOME']),
    ("app 100%% --file=%f", ["app", "100%", "--file="]),
    ('app ""', ["app", ""]),
])
def test_exec_lines(line, argv):
    assert lapps.exec_argv(line) == argv


def _entry(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[Desktop Entry]\n" + body)
    return path


def test_which_entries_count(tmp_path):
    d = tmp_path / "applications"
    _entry(d, "a.desktop", "Type=Application\nName=Alpha\nExec=sh %U\nCategories=Game;\nStartupWMClass=AlphaWin\n")
    _entry(d, "hidden.desktop", "Type=Application\nName=Hidden\nExec=sh\nNoDisplay=true\n")
    _entry(d, "link.desktop", "Type=Link\nName=A link\nURL=https://x\n")
    _entry(d, "gone.desktop", "Type=Application\nName=Gone\nExec=nope\nTryExec=/definitely/not/here\n")
    _entry(d, "help.desktop", "Type=Application\nName=Alpha Help\nExec=sh\n")
    _entry(d, "sub/b.desktop", "Type=Application\nName=Beta\nName[de]=Beta DE\nExec=sh -c 'x'\nTerminal=true\n")
    entries = lapps.installed_entries([d])
    assert [e.name for e in entries] == ["Alpha", "Beta"]
    alpha = entries[0]
    assert alpha.is_game and alpha.wm_class == "AlphaWin" and "alphawin" in alpha.process_names()
    assert entries[1].terminal


def test_a_users_entry_wins(tmp_path):
    user, system = tmp_path / "user", tmp_path / "system"
    _entry(user, "app.desktop", "Type=Application\nName=Mine\nExec=sh\n")
    _entry(system, "app.desktop", "Type=Application\nName=System\nExec=sh\n")
    assert [e.name for e in lapps.installed_entries([user, system])] == ["Mine"]


def test_flatpak_names():
    e = lapps.DesktopEntry("Discord", Path("/x.desktop"),
                           "/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=com.discordapp.Discord com.discordapp.Discord")
    names = e.process_names()
    assert "discord" in names and e.program() is None


def test_launch_is_an_argument_list_never_a_shell(tmp_path):
    calls = []
    path = _entry(tmp_path, "x.desktop", 'Type=Application\nName=X\nExec=sh -c "echo; rm -rf /tmp/nope" %F\n')
    lapps.launch_desktop_file(path, lambda argv, **kw: calls.append((argv, kw)))
    argv, kw = calls[0]
    assert argv == ["sh", "-c", "echo; rm -rf /tmp/nope"] and kw.get("shell") is None and kw["start_new_session"]


def test_application_dirs_include_flatpak_and_snap():
    dirs = [str(d) for d in lapps.application_dirs({"HOME": "/home/u", "XDG_DATA_DIRS": "/usr/share"})]
    assert "/home/u/.local/share/applications" in dirs and "/var/lib/flatpak/exports/share/applications" in dirs
    assert "/var/lib/snapd/desktop/applications" in dirs


# -- power, media, autostart -------------------------------------------------------------------------------------------
class Ran:
    def __init__(self, codes=None):
        self.argvs, self.codes = [], codes or {}

    def __call__(self, argv, **kw):
        self.argvs.append(argv)
        return SimpleNamespace(returncode=self.codes.get(Path(argv[0]).name, 0))


def test_power_uses_systemd(monkeypatch):
    monkeypatch.setattr(ldesk.shutil, "which", lambda name: f"/usr/bin/{name}")
    ran = Ran()
    ldesk.power("shutdown", ran)
    assert ran.argvs == [["/usr/bin/systemctl", "poweroff"]]
    ran = Ran({"loginctl": 1})
    ldesk.power("lock", ran)                                  # loginctl said no: the next way
    assert ran.argvs[-1] == ["/usr/bin/xdg-screensaver", "lock"]
    with pytest.raises(ValueError):
        ldesk.power("format", ran)


def test_media_prefers_playerctl_then_x11_keys(monkeypatch):
    monkeypatch.setattr(ldesk.shutil, "which", lambda name: "/usr/bin/playerctl" if name == "playerctl" else None)
    ran = Ran()
    ldesk.media("next", ran)
    assert ran.argvs == [["/usr/bin/playerctl", "next"]]
    monkeypatch.setattr(ldesk.shutil, "which", lambda name: None)
    pressed = []
    monkeypatch.setattr(ldesk.x11mod, "shared", lambda: SimpleNamespace(press_keysyms=pressed.append))
    ldesk.media("volume_up", ran)
    assert pressed == [["XF86AudioRaiseVolume"]]


def test_autostart_entry(tmp_path, monkeypatch):
    from capri import autostart
    if not autostart.LINUX:
        pytest.skip("Linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPIMAGE", "/home/u/Apps/Capri x86_64.AppImage")
    autostart.set_enabled(True)
    text = (tmp_path / "autostart" / "capri.desktop").read_text()
    assert 'Exec="/home/u/Apps/Capri x86_64.AppImage" --startup' in text and autostart.is_enabled()
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))[5:]
    assert lapps.exec_argv(exec_line) == ["/home/u/Apps/Capri x86_64.AppImage", "--startup"]
    autostart.set_enabled(False)
    assert not autostart.is_enabled()


# -- games, processes --------------------------------------------------------------------------------------------------
def test_linux_games_are_recognised():
    from capri.commands.games import Front, looks_like_game
    assert looks_like_game(Front(5, "/home/u/.local/share/Steam/steamapps/common/Celeste/Celeste", False)) == "library"
    assert looks_like_game(Front(5, "/usr/lib/firefox/firefox", True)) == ""
    assert looks_like_game(Front(5, "/opt/somegame/game.x86_64", True)) == "fullscreen"
    assert looks_like_game(Front(5, "/opt/x/app", False), ["/opt/x"]) == "library"


def test_closing_finds_linux_processes():
    from capri.commands.apps import AppEntry
    from capri.commands.catalog import Catalog, Target
    from capri.commands.discovery import Shortcut
    from capri.commands.system import ProcessInfo
    procs = [ProcessInfo(1, "Discord", "/opt/discord/Discord"), ProcessInfo(2, "firefox", "/usr/lib/firefox/firefox"),
             ProcessInfo(3, "bash", "/usr/bin/bash")]
    entry = AppEntry("Discord", processes=["Discord.exe"])
    assert Catalog._pids_for(Target("Discord", "app", entry=entry), procs) == [1]
    sc = Shortcut("Firefox", Path("/usr/share/applications/firefox.desktop"), Path("/usr/bin/firefox-wrapper"),
                  ("firefox",))
    assert Catalog._pids_for(Target("Firefox", "shortcut", shortcut=sc), procs) == [2]


def test_discord_on_linux_is_found():
    from capri.commands.desktop import DISCORD_EXES
    assert {"discord", "vesktop"} <= DISCORD_EXES


def test_protected_on_linux():
    assert {"gnome-shell", "pipewire", "systemd", "xwayland"} <= ldesk.LINUX_PROTECTED


def test_xwayland_on_wayland(monkeypatch):
    from capri.app import use_xwayland
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    use_xwayland()
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")                # you chose native Wayland: left alone
    use_xwayland()
    assert os.environ["QT_QPA_PLATFORM"] == "wayland"


def test_restart_from_the_appimage(monkeypatch):
    from capri.app import restart_command
    monkeypatch.setenv("APPIMAGE", "/home/u/Capri.AppImage")
    assert restart_command()[0] == "/home/u/Capri.AppImage"


def test_wayland_typing_falls_back(monkeypatch):
    monkeypatch.setattr(ldesk.shutil, "which", lambda name: "/usr/bin/wtype" if name == "wtype" else None)
    ran = Ran()
    assert ldesk.wayland_type("hi\nthere", ran)
    assert ran.argvs == [["/usr/bin/wtype", "--", "hi there"]]                # never presses Enter


def test_tesseract_tsv():
    from capri.linux.screen import parse_tsv
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t20\t40\t100\t30\t95.1\tSubscribe\n"
           "5\t1\t1\t1\t1\t2\t200\t40\t90\t30\t12.0\tjunk\n"
           "5\t1\t2\t1\t1\t1\t20\t140\t80\t30\t90\tCancel\n")
    words = parse_tsv(tsv, (1000, 500), 2)
    assert [(w.text, w.line, w.rect) for w in words] == [("Subscribe", 0, (1010, 520, 1060, 535)),
                                                          ("Cancel", 1, (1010, 570, 1050, 585))]


def test_hotkey_parse_linux():
    from capri.linux.hotkeys import parse
    assert parse("ctrl+alt+c") == (4 | 8, "c")
    assert parse("ctrl+shift+f9") == (4 | 1, "F9")
    with pytest.raises(ValueError):
        parse("c")


# -- the real X11 desktop ------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def xdesk():
    if not sys.platform.startswith("linux") or not shutil.which("Xvfb") or not shutil.which("openbox") \
            or not shutil.which("xterm"):
        pytest.skip("needs Xvfb, openbox and xterm")
    display = f":{90 + os.getpid() % 300}"
    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x800x24"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    env = dict(os.environ, DISPLAY=display)
    wm = subprocess.Popen(["openbox"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    from capri.linux.x11 import X11
    from Xlib import display as xdisplay
    x = X11(xdisplay.Display(display))
    yield SimpleNamespace(x=x, env=env, display=display)
    for p in (wm, xvfb):
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def _xterm(xd, title, tmp_path, out=None, geometry="70x10+100+100"):
    cmd = f"stty -icanon; cat > '{out}'" if out else "sleep 30"
    p = subprocess.Popen(["xterm", "-u8", "-T", title, "-geometry", geometry, "-e", "sh", "-c", cmd],
                         env=dict(xd.env, LC_ALL="C.UTF-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        wins = [w for w in xd.x.windows() if xd.x.title(w) == title]
        if wins:
            return p, wins[0]
        time.sleep(0.1)
    p.kill()
    pytest.fail("xterm didn't appear")


def test_windows_focus_minimise_close(xdesk, tmp_path):
    x = xdesk.x
    p1, a = _xterm(xdesk, "Win A", tmp_path)
    p2, b = _xterm(xdesk, "Win B", tmp_path, geometry="70x10+500+400")
    assert x.pid(a) == p1.pid and x.wm_class(a)[1] == "XTerm"
    assert x.activate(a) and x.active() == a
    x.minimize(a)
    time.sleep(0.3)
    assert x.is_minimized(a) and a not in x.windows(include_minimized=False)
    assert x.activate(a) and not x.is_minimized(a)
    g = x.geometry(b)
    assert x.window_at((g[0] + g[2]) // 2, (g[1] + g[3]) // 2) == b
    x.close(a)
    x.close(b)
    assert p1.wait(timeout=5) is not None and p2.wait(timeout=5) is not None


def test_typing_any_letter(xdesk, tmp_path):
    out = tmp_path / "typed.txt"
    p, w = _xterm(xdesk, "Typing", tmp_path, out)
    assert xdesk.x.activate(w)
    text = "Hello, World! héllo wörld ☺ Привет €"
    assert xdesk.x.type_text(text + "\nnever enter") == len(text) + len("never enter")
    time.sleep(0.6)
    assert out.read_text(encoding="utf-8") == text + "never enter"
    p.kill()


def test_hotkeys_live(xdesk):
    from Xlib import display as xdisplay
    from capri.linux.hotkeys import X11Hotkeys
    got = []
    h = X11Hotkeys(got.append, xdisplay.Display(xdesk.display))
    try:
        assert h.register("ctrl+alt+c", 7) is None
        xdesk.x.press_combo("ctrl+alt+x")
        xdesk.x.press_combo("ctrl+alt+c")
        for _ in range(20):
            if got:
                break
            time.sleep(0.05)
        assert got == [7]
        h2 = X11Hotkeys(lambda i: None, xdisplay.Display(xdesk.display))
        assert "already used" in h2.register("ctrl+alt+c", 1)
        h2.stop()
    finally:
        h.stop()


def test_media_key_without_a_media_keyboard(xdesk):
    xdesk.x.press_keysyms(["XF86AudioPlay"])            # Xvfb has no media keys: a spare key is borrowed


@pytest.mark.skipif(not shutil.which("tesseract"), reason="needs tesseract")
def test_reading_the_screen(xdesk, tmp_path, monkeypatch):
    from capri.linux import screen, x11
    monkeypatch.setattr(x11, "shared", lambda: xdesk.x)
    p = subprocess.Popen(["xterm", "-fa", "Monospace", "-fs", "14", "-T", "Read me", "-geometry", "60x8+50+50", "-e",
                          "sh", "-c", 'printf "\\n   Subscribe     Download\\n"; sleep 30'], env=xdesk.env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2.0)
        w = next(w for w in xdesk.x.windows() if xdesk.x.title(w) == "Read me")
        words = [wd.text for wd in screen.ocr(xdesk.x.geometry(w))]
        assert "Subscribe" in words and "Download" in words
    finally:
        p.kill()


def test_linux_desktop_and_system_together(xdesk, tmp_path, monkeypatch):
    from capri.linux import x11
    monkeypatch.setattr(x11, "shared", lambda: xdesk.x)
    desk = ldesk.LinuxDesktop(xdesk.x)
    system = ldesk.LinuxSystem(popen=lambda argv, **kw: subprocess.Popen(argv, env=xdesk.env, **{
        k: v for k, v in kw.items() if k != "env"}), desktop=desk)
    entry = _entry(tmp_path / "apps", "t.desktop",
                   'Type=Application\nName=Test Term\nExec=xterm -T "Test Term" -geometry 60x8+80+80 -e sleep 30\n')
    system.open_item(str(entry))
    pid = None
    for _ in range(50):
        wins = [w for w in xdesk.x.windows() if xdesk.x.title(w) == "Test Term"]
        if wins:
            pid = xdesk.x.pid(wins[0])
            break
        time.sleep(0.1)
    assert pid and desk.main_window([pid]) == wins[0] and desk.window_rect([pid])
    assert desk.minimize_all() >= 1 and desk.restore() >= 1
    assert system.request_close([pid]) == 1
    for _ in range(50):
        if not system.running([pid]):
            break
        time.sleep(0.1)
    assert not system.running([pid])


# -- the AppImage: updates, apps menu ------------------------------------------------------------------------------------
@pytest.fixture
def linux_updates(monkeypatch, tmp_path):
    from capri import updater
    image = tmp_path / "Apps" / "Capri-x86_64.AppImage"
    image.parent.mkdir()
    image.write_bytes(b"old capri")
    monkeypatch.setattr(updater, "LINUX", True)
    monkeypatch.setenv("APPIMAGE", str(image))
    return updater, image


def test_appimage_reads_its_own_entry_in_latest_json(linux_updates):
    updater, _image = linux_updates
    info = {"version": "9.9.9", "file": "Capri-Setup-9.9.9.exe", "size": 5, "sha256": "aa",
            "linux": {"file": "Capri-x86_64.AppImage", "size": 7, "sha256": "BB"}}
    found = updater.check(lambda url: info, current="1.37.0")
    assert found.name == "Capri-x86_64.AppImage" and found.size == 7 and found.sha256 == "bb"
    assert found.url == updater.DOWNLOADS + "v9.9.9/Capri-x86_64.AppImage"
    assert updater.frozen()                                          # an AppImage in a folder you own


def test_appimage_without_its_entry_asks_the_api(linux_updates):
    updater, _image = linux_updates

    def fetch(url):
        if url == updater.LATEST_JSON:
            return {"version": "9.9.9", "file": "Capri-Setup-9.9.9.exe"}         # Windows only (so far)
        return {"tag_name": "v9.9.9", "assets": [
            {"name": "Capri-Setup-9.9.9.exe", "browser_download_url": updater.DOWNLOADS + "v9.9.9/Capri-Setup-9.9.9.exe"},
            {"name": "Capri-x86_64.AppImage", "size": 3,
             "browser_download_url": updater.DOWNLOADS + "v9.9.9/Capri-x86_64.AppImage"}]}
    assert updater.check(fetch, current="1.37.0").name == "Capri-x86_64.AppImage"


def test_appimage_update_replaces_the_file_and_restarts(linux_updates, tmp_path):
    import hashlib
    import json as _json
    updater, image = linux_updates
    data = b"new capri"
    folder = tmp_path / "updates"

    import io

    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(data)
            self.headers = {"Content-Length": str(len(data))}
    u = updater.Update("9.9.9", updater.DOWNLOADS + "v9.9.9/Capri-x86_64.AppImage", "Capri-x86_64.AppImage",
                       len(data), hashlib.sha256(data).hexdigest())
    path = updater.download(u, folder, opener=lambda *a, **k: Response())
    assert updater.ready(folder, current="1.37.0") == ("9.9.9", path)
    started = []
    assert updater.install(path, run=lambda argv, **kw: started.append(argv), folder=folder)
    assert image.read_bytes() == data and os.access(image, os.X_OK)
    assert started == [[str(image), "--after-update"]]
    assert updater.ready(folder, current="1.37.0") is None            # nothing waiting any more
    _json.dumps(started)


def test_appimage_adds_itself_to_the_apps_menu(tmp_path):
    env = {"APPIMAGE": "/home/u/Apps/Capri-x86_64.AppImage", "XDG_DATA_HOME": str(tmp_path), "HOME": str(tmp_path)}
    icon = Path(__file__).resolve().parent.parent / "assets" / "capri" / "icon.png"
    assert ldesk.ensure_menu_entry(icon, env) == "added"
    entry = tmp_path / "applications" / "capri.desktop"
    assert "Exec=/home/u/Apps/Capri-x86_64.AppImage" in entry.read_text()
    assert (tmp_path / "icons" / "hicolor" / "128x128" / "apps" / "capri.png").is_file()
    assert ldesk.ensure_menu_entry(icon, env) == ""                    # already right: left alone
    env["APPIMAGE"] = "/home/u/Downloads/Capri-x86_64.AppImage"        # you moved it
    assert ldesk.ensure_menu_entry(icon, env) == "updated"


def test_release_builds_the_appimage():
    wf = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml").read_text()
    assert "build_appimage.sh" in wf and "Capri-x86_64.AppImage" in wf and ".linux = {file" in wf
    assert "xvfb-run" in wf                                             # she has to start before it ships
