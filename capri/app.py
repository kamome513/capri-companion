"""Application entry point."""

from __future__ import annotations

import argparse
import os
import itertools
import logging
import threading
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QRect, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import __version__, autostart, chat, logs, secrets
from .ai.claude import ClaudeBrain
from .ai.local import Brains, LocalBrain
from .ai.openai_compat import OpenAIBrain
from .assistant import Assistant
from .commands.apps import load_apps
from .commands.catalog import Catalog
from .commands.desktop import WindowsDesktop
from .commands.games import GameWatch
from .commands import parser as command_parser, places
from .commands.discovery import installed_apps, shortcuts, steam_games
from .commands.router import CommandRouter, Services
from .commands.system import WindowsSystem
from .controller import CompanionController
from .hotkeys import SUPPORTED as hotkeys_supported
from .hotkeys import HotkeyManager, pretty
from .integrations import http, media
from .integrations.spotify_app import SpotifyApp, main_window_titles
from .integrations.app_buttons import DiscordButtons, DiscordCall, SpotifyButtons
from .integrations.game_hype import GameHype
from .integrations.ocr_worker import PersistentOcr
from .integrations.screen_hype import ScreenWatcher, grab_image
from .commands.games import looks_like_game
from .ai import doctor as ai_doctor
from .ai.doctor import AIDoctor
from .voice.whisper import WhisperEars
from .voice.whisper import installed as whisper_installed
from .voice import parakeet
from .about_you import AboutYou
from .ui.updates import UpdateManager, apply_waiting_update
from .ai import claude as claude_brain
from .integrations import pc_stats
from .integrations.browser_tabs import BrowserTabs
from .integrations.uia import WindowsUI
from .integrations.spotify import Spotify
from .integrations.weather import Weather
from .session import SessionWatcher
from .settings import Settings
from .states import State
from .speech.engines import ElevenLabsEngine, FishAudioEngine, VoiceBox
from .speech.speaker import Speaker
from .ui.art import CharacterArt
from .ui.assistant_tab import AssistantTab
from .ui.chat_window import ChatWindow
from .ui.companion import Companion
from .ui.greeting import GreetingShow
from .ui.screen_spots import taskbar_icon, to_logical
from .ui.psychosis import PsychosisShow
from .integrations.screen_click import ScreenHands, click_at, click_spotify_play
from .integrations.screen_targets import Finder, cursor_pos, target_window, windows_ocr
from .integrations.screen_targets import click as click_on_screen
from .typing_watch import TypingWatch
from . import memory
from .ui.extras_tab import ExtrasTab
from .ui.visit import VisitShow
from .ui.visit_actions import VisitActions
from .ui.zap import ZapShow
from .ui.lipsync import LipSync
from .ui.look_tab import LookTab
from .ui.pc_tab import PcTab
from .ui.sprites import SpriteArt
from .ui.settings_window import SettingsWindow
from .ui.screenshot import Screenshotter
from .ui.tray import CompanionMenu
from .voice.service import VoiceService


INSTANCE_NAME = "capri-desktop-companion"
log = logging.getLogger("capri")


def asset_root() -> Path:
    # Works both from source and from a PyInstaller bundle (sys._MEIPASS).
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets"


PREVIEW_SEQUENCE = [
    (State.IDLE, "Waiting for wake word...", None),
    (State.LISTENING, "Listening...", ("Wake", '"hey capri"')),
    (State.PROCESSING, "Processing command...", ("Heard", '"open deadlock"')),
    (State.LAUNCHING, "Opening Deadlock...", ("Launch", "steam://rungameid/1422450")),
    (State.SUCCESS, "Deadlock launched.", ("Done", "Deadlock running")),
    (State.ERROR, "Application not found.", ("Error", '"open photoshop"')),
]


def start_preview(controller: CompanionController) -> QTimer:
    """Cycle through every state with sample text, for checking the visuals.

    Clearly labelled PREVIEW in the panel header: nothing is listened to or launched.
    """
    controller.channel = "PREVIEW"
    steps = itertools.cycle(PREVIEW_SEQUENCE)

    def advance() -> None:
        state, message, entry = next(steps)
        if entry:
            controller.log(*entry)
        controller.set_state(state, message)

    timer = QTimer(interval=2500)
    timer.timeout.connect(advance)
    advance()
    timer.start()
    return timer


RUNNING_MUTEX = "CapriCompanionRunning"     # packaging/capri.iss waits for it when updating


def _running_mutex():
    """A Windows named mutex that exists while Capri runs (released by Windows when she exits)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32.CreateMutexW(None, False, RUNNING_MUTEX)
    except Exception:
        return None


def _linux_spotify_play() -> bool:
    from .linux.desktop import spotify_play
    return spotify_play()


def use_xwayland() -> None:
    """Linux on Wayland: run through XWayland (every Wayland desktop has it). On native Wayland an app
    can't put its own windows where it wants or stay on top - Capri's whole point - and can't see or
    type into other apps. You can still force native Wayland with QT_QPA_PLATFORM=wayland."""
    if not sys.platform.startswith("linux") or os.environ.get("QT_QPA_PLATFORM"):
        return
    if (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland") \
            and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def restart_command() -> tuple[str, list[str], str]:
    """(program, arguments, folder) that start Capri again: Capri.exe, or python -m capri from the code."""
    if os.environ.get("APPIMAGE"):                 # Linux AppImage: the file itself, not its unpacked insides
        return os.environ["APPIMAGE"], [], str(Path(os.environ["APPIMAGE"]).parent)
    from . import portable
    if portable.exe():                             # the one-file Capri.exe: start that, not the unpacked copy
        return portable.exe(), [], str(Path(portable.exe()).parent)
    if getattr(sys, "frozen", False):
        return sys.executable, [], str(Path(sys.executable).parent)
    root = Path(__file__).resolve().parent.parent
    return sys.executable, ["-m", "capri"], str(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capri", description="Capri desktop companion")
    parser.add_argument("--preview", action="store_true",
                        help="cycle through all panel/character states with sample text")
    parser.add_argument("--art", type=Path, default=None,
                        help="folder containing manifest.json and Capri's images")
    parser.add_argument(autostart.STARTUP_FLAG, action="store_true",
                        help="started by Windows at sign-in: greet the user")
    parser.add_argument("--listen", action="store_true",
                        help="tell the running Capri to listen now (push-to-talk) - bind it to a keyboard shortcut")
    parser.add_argument("--toggle-click-through", action="store_true",
                        help="tell the running Capri to turn click-through on / off")
    parser.add_argument("--after-update", action="store_true", help=argparse.SUPPRESS)   # wait for the old Capri
    args = parser.parse_args(argv)
    use_xwayland()                    # Linux on Wayland: X11 through XWayland, so she can place her windows
    if sys.platform.startswith("linux"):
        from .linux.audio import use_bundled_portaudio
        use_bundled_portaudio()       # the AppImage's own PortAudio (microphone + speaker)
    from . import net
    net.use_system_certificates()     # downloads work on PCs whose antivirus / network checks HTTPS

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # let Ctrl+C in the console quit
    app = QApplication(sys.argv[:1])
    try:                              # Qt switches numbers to your language's format (1,5 in German...):
        import locale                 # keep C-style numbers, which the speech recogniser's results rely on
        locale.setlocale(locale.LC_NUMERIC, "C")
    except Exception:
        pass
    app.setApplicationName("Capri")
    app.setOrganizationName("")   # settings live in ...\AppData\Local\Capri
    app.setQuitOnLastWindowClosed(False)
    from .ui.app_icon import app_icon
    app.setWindowIcon(app_icon())   # her USB shard, in the taskbar

    # Only one Capri at a time. Starting her again (Start menu, run.bat) just brings her back.
    lock_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
    lock = QLockFile(str(lock_dir / "capri-companion.lock"))
    if not lock.tryLock(10_000 if args.after_update else 100):
        socket = QLocalSocket()
        socket.connectToServer(INSTANCE_NAME)
        if socket.waitForConnected(1000):
            socket.write(b"listen" if args.listen else b"click-through" if args.toggle_click_through else b"show")
            socket.waitForBytesWritten(1000)
        print("[capri] already running - brought her back to the front.")
        return 0

    app.running_mark = _running_mutex()   # the installer waits for this to go before it updates her
    if os.environ.get("APPIMAGE") and sys.platform.startswith("linux"):
        try:
            from .linux.desktop import ensure_menu_entry
            ensure_menu_entry(asset_root() / "capri" / "app_icon.png")   # Capri in your apps menu
        except Exception:
            pass
    first_run = not Settings.path().exists()
    settings = Settings.load()
    from . import languages
    languages.set_current(settings.language)          # before her ears, brain and voice are set up
    languages.keep_voice = settings.keep_voice
    if not args.preview and apply_waiting_update(settings):   # a downloaded update: install it, then she restarts
        return 0
    if not args.preview:
        did = autostart.ensure_default(settings)      # on by default (once); the tray turns it off
        if did:
            log.info("start with Windows: %s", did)
    if settings.click_through and not QSystemTrayIcon.isSystemTrayAvailable():
        settings.click_through = False   # no tray = no way to turn it back off

    art = CharacterArt.load(args.art or asset_root() / "capri")
    sprites = SpriteArt.load(asset_root() / "capri_v2")      # the character sheet (optional)
    controller = CompanionController()
    log_path = logs.setup(on_crash=lambda message: controller.log("Error", "glitched - see capri.log"))
    log.info("Capri %s starting (log: %s)", __version__, log_path)
    from . import portable
    if portable.exe():
        log.info("one-file Capri.exe: %s (unpacked in %s)", portable.exe(), Path(sys.executable).parent)
    companion = Companion(controller, art, settings, sprites)
    d_picture = asset_root() / "d" / "d.png"                 # D, for her video calls (idle activity)
    if d_picture.is_file():
        companion.character.acts.contact = QImage(str(d_picture))

    # A second launch asks this one to show herself again.
    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE_NAME)
    server.listen(INSTANCE_NAME)

    remote = {}                        # "capri --listen" from a keyboard shortcut -> set once she's ready

    def on_second_launch() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def received() -> None:
            what = bytes(conn.readAll()).strip()
            action = remote.get(what.decode("ascii", "ignore"))
            if action is not None:
                log.info("second launch: %s", what)
                return action()
            companion.set_hidden(False)
            controller.log("Hi", "already running - here I am")
            log.info("second launch: showing the running Capri")
        conn.readyRead.connect(received)
    server.newConnection.connect(on_second_launch)

    if args.preview:
        menu = CompanionMenu(companion, art.icon)
        app._preview_timer = start_preview(controller)  # keep a reference alive
        companion.show()
        return app.exec()

    screen = companion.screen
    size = screen.size()
    controller.log("Boot", "overlay online")
    controller.log("Display", f"{size.width()}x{size.height()} {screen.name()}")
    controller.set_state(State.IDLE, "Starting voice...")

    service = VoiceService(settings.voice_enabled, settings.mic_muted, settings.input_device,
                           settings.wake_threshold)
    service.set_learned(settings.wake_variants)          # how she hears your voice say her name (taught)
    ElevenLabsEngine.key = staticmethod(lambda: secrets.get("elevenlabs_api_key"))
    ElevenLabsEngine.voice_id = staticmethod(lambda: settings.elevenlabs_voice)
    FishAudioEngine.key = staticmethod(lambda: secrets.get("fish_audio_api_key"))
    FishAudioEngine.voice_id = staticmethod(lambda: settings.fish_voice)
    speaker = Speaker(settings, VoiceBox)
    assistant = Assistant(controller, settings, service, speaker)
    assistant.typing = TypingWatch()          # ignores what the mic "hears" while you're typing
    speaker.failed.connect(lambda message: controller.log("Voice", message))

    # Her animation follows her voice: mouth, glitches, voice bars, typewriter text.
    lipsync = LipSync()
    speaker.started.connect(lipsync.start)
    speaker.finished.connect(lipsync.stop)
    for window in (companion.character, companion.panel):
        lipsync.level.connect(window.set_voice_level)
        lipsync.talking.connect(window.set_talking)
    lipsync.progress.connect(companion.panel.set_progress)
    lipsync.talking.connect(companion.set_talking)
    lipsync.viseme.connect(companion.set_viseme)              # mouth shapes (character-sheet art)
    greeting = GreetingShow(companion)                        # her big hello at sign-in
    lipsync.level.connect(greeting.set_voice_level)
    lipsync.talking.connect(greeting.set_talking)
    lipsync.viseme.connect(greeting.set_viseme)
    lipsync.progress.connect(greeting.set_progress)

    # Commands: only catalog entries (your apps, Steam games, Start menu) can be launched.
    linux = sys.platform.startswith("linux")
    if linux:
        from .linux.desktop import LinuxDesktop, LinuxSystem
        desktop = LinuxDesktop()        # X11 windows, keys, typing; systemd power - fixed actions only
        system = LinuxSystem(desktop=desktop)
    else:
        system = WindowsSystem()
    catalog = Catalog(load_apps, steam_games, shortcuts,
                      load_installed=installed_apps, load_places=places.places)   # + Store apps, folders
    weather = Weather(settings.weather_units)
    spotify = Spotify(lambda: settings.spotify_client_id, open_url=system.open_item,
                      launch_app=lambda: system.open_item("spotify:"))

    def ai_weather(args: dict) -> str:
        place = (args.get("place") or settings.weather_city).strip()
        if not place:
            return "The user hasn't set a home city. Ask them to add it in Capri's Settings, Assistant tab."
        weather.units = settings.weather_units
        return weather.report(place, args.get("day", "today"))

    info = {"get_weather": ai_weather, "get_time": lambda args: datetime.now().strftime("%A %d %B %Y, %H:%M"),
            "get_pc_stats": pc_stats.ai_tool}
    command_parser.set_corrections(settings.corrections)   # your fixes for words she mishears
    if not settings.chatbot_switched:         # 1.13: she's a chatbot that also takes commands
        settings.ai_enabled, settings.chatbot_switched = True, True
        if settings.ai_provider == "local":
            settings.ai_provider = "auto"     # Ollama if it's running, else Claude with a key
        settings.save()
    brain = Brains(settings,
                   ClaudeBrain(lambda: secrets.get("anthropic_api_key"), info=info, slang=lambda: settings.slang,
                               persona=lambda: settings.personality),
                   LocalBrain(lambda: settings.ollama_url, lambda: settings.ollama_model, info,
                              slang=lambda: settings.slang, persona=lambda: settings.personality),
                   OpenAIBrain(lambda: settings.openai_preset, lambda: settings.openai_url,
                               lambda: settings.openai_model, lambda: secrets.get("openai_api_key"), info,
                               slang=lambda: settings.slang, persona=lambda: settings.personality))
    if not linux:
        desktop = WindowsDesktop()      # power, minimising, Discord keys - fixed actions only
    ui = WindowsUI()               # presses apps' own buttons (Discord's Mute, Spotify's Play)
    about = AboutYou()              # what she remembers about you: %LOCALAPPDATA%\Capri only, never the AI
    claude_brain.ABOUT_USER = lambda: about.for_ai() if settings.share_memory_with_ai else ""
    services = Services(settings, weather, spotify, media.press, brain, desktop,
                        file_roots=places.search_roots,     # "find my ..." looks in your own folders only
                        discord_buttons=DiscordButtons(ui, desktop.windows_for) if sys.platform == "win32" else None,
                        discord_call=DiscordCall(ui, desktop.windows_for, click=click_at) if sys.platform == "win32" else None,
                        spotify_buttons=SpotifyButtons(ui, desktop.windows_for, desktop=desktop)
                        if sys.platform == "win32" else None, about_you=about)
    def spotify_titles(pids: list[int]) -> list[str]:
        return main_window_titles(desktop, pids)

    def spotify_api_search(query: str, artist: str) -> str | None:
        if not spotify.connected:
            return None
        track = spotify.search(query, artist)
        return track.uri if track else None

    def press_track_play(pids: list[int], name: str) -> bool:
        buttons = services.spotify_buttons
        buttons.log = []
        try:
            return buttons.press_track_play(pids, name)
        finally:
            for note in buttons.log:                       # into the Test Spotify report
                logging.getLogger("capri").info("spotify: %s", note)

    services.spotify_app = SpotifyApp(
        system.open_item,
        lambda: [p.pid for p in system.processes() if p.name.lower() in ("spotify.exe", "spotify")],
        spotify_titles, press_track_play if not linux else (lambda pids, name: _linux_spotify_play()), http.get_text,
        lambda url: http.request("GET", url), api_search=spotify_api_search,
        click_play=(lambda pids: click_spotify_play(desktop, pids, services.spotify_buttons.log)) if not linux
        else None) if sys.platform == "win32" or linux else None
    def window_rect(pids: list[int]):
        r = desktop.window_rect(pids)
        return to_logical(r) if r else None
    zapper = ZapShow(companion, window_rect)
    services.zap = lambda name, pids, then: zapper.zap(name, pids, then) if settings.teleport else then()

    visit_show = VisitShow(companion)

    def figure_rig():                          # her full-body figure at her current size (dash, throw, walk)
        visit_show.fh = companion.character.figure_height()
        return visit_show.rig()
    from .ui.fling import ThrowShow
    throw_show = ThrowShow(companion, figure_rig, lambda text, emotion: assistant.remark(text, emotion=emotion),
                           enabled=lambda: settings.throwable)
    companion.on_throw = throw_show.throw     # flick her and let go: she flies (and slams into the wall)
    app._throw_show = throw_show
    import random as _random
    PATS = {"head": ["Hehe. Okay, that's nice.", "Pat accepted.", "Mm. Again.", "Don't mess up my hair. ...Fine, once more.",
                     "Purring in binary.", "You're sweet, choom."],
            "body": ["Hey! Rude.", "That tickles.", "Poke me again and I bite.", "What? I'm working.", "Yes? Need something?"]}

    def patted(where: str) -> None:           # click her head: a pat; anywhere else: a poke
        if assistant._busy or controller.state in (State.LISTENING, State.PROCESSING):
            return
        line = _random.choice(PATS[where])
        controller.log("Pat" if where == "head" else "Poke", line)
        controller.set_state(State.SUCCESS, line, emotion="happy" if where == "head" else "surprised")
        assistant.remark(line, emotion="happy" if where == "head" else "surprised")
    companion.patted.connect(patted)
    companion.character.set_body_look(settings.body_style)       # full colour / neon
    companion.character.glitch_every = settings.glitches          # random glitches (off unless you turn them on)
    companion.character.real_glitch.rescheduled()

    def glitch_setting() -> None:
        if companion.character.glitch_every != settings.glitches:
            companion.character.glitch_every = settings.glitches
            companion.character.real_glitch.rescheduled()
    assistant.settings_changed.connect(glitch_setting)
    from .speech import speaker as speaker_mod
    speaker_mod.mic_device = lambda: settings.mic_voice_device     # "Her voice in your mic"
    from .ui.roam import RoamShow
    roam_show = RoamShow(companion, figure_rig, enabled=lambda: settings.roaming,
                         idle=lambda: not assistant._busy and not throw_show.active and not visit_show.active,
                         quiet=lambda: in_game())            # never while you're in (or starting) a game
    roam_show.start()                         # a little walk along the bottom of the screen now and then
    services.roam = roam_show
    app._roam_show = roam_show

    def zap_button(rect, pids: list[int], then, kind: str = "mute") -> None:
        """She dashes right up to Discord's Mute / Deafen button and zaps it (pressed on impact).
        Button not on screen: Discord's bottom-left corner (where those buttons live), else its
        taskbar icon."""
        if not settings.teleport:
            return then()
        window = window_rect(pids)
        if rect is not None:
            target = to_logical(rect)
        elif window is not None:                  # Discord's user panel, bottom left: mic, then headphones
            target = QRect(window.left() + (196 if kind == "mute" else 228), window.bottom() - 44, 32, 32)
        else:
            target = taskbar_icon(ui, "Discord")
        if target is None:
            return zapper.zap_at(None, then, small=True)
        visit_show.visit(target, then, window=window, near=True)
    services.zap_at = zap_button
    from .ui.her_cursor import HerCursor
    her_cursor = HerCursor()                   # her little pink pointer: wherever she clicks or types (2.3.4)
    app._her_cursor = her_cursor

    class _PointBridge(QObject):
        point = Signal(int, int)               # (physical screen x, y) - from her worker threads
    point_bridge = _PointBridge()
    app._point_bridge = point_bridge

    def show_point(x: int, y: int) -> None:
        r = to_logical((x, y, x + 1, y + 1))
        her_cursor.glide(r.x(), r.y())
    point_bridge.point.connect(show_point)

    def click(target, how):                    # her cursor glides to it, then she clicks
        try:
            x0, y0, x1, y1 = target.rect
            point_bridge.point.emit(int((x0 + x1) / 2), int((y0 + y1) / 2))
            time.sleep(0.28)
        except Exception:
            pass
        return click_on_screen(target, how)
    services.point_at = lambda x, y: point_bridge.point.emit(int(x), int(y))
    if linux:                                  # "click subscribe": read the window (Tesseract), click it
        from .linux import screen as linux_screen
        services.screen = Finder(linux_screen.NoAccessibility(), target_window, desktop.hwnd_rect, cursor_pos,
                                 ocr=linux_screen.ocr if linux_screen.ocr_available() else None)
        services.click_at = lambda target: click(target, linux_screen.click_at)
        services.front = target_window

        def linux_front_rect():
            wid = target_window()
            return desktop.hwnd_rect(wid) if wid else None
        services.hands = linux_screen.LinuxHands(linux_front_rect)
    if sys.platform == "win32":               # "click subscribe" / "click that"
        services.screen = Finder(ui, target_window, desktop.hwnd_rect, cursor_pos, ocr=windows_ocr)
        services.click_at = lambda target: click(target, click_at)
        services.tabs = BrowserTabs(ui, desktop, system.processes, target_window)   # tabs, the video player
        services.front = target_window                  # "open notepad and type hi": wait for its window

        def front_rect():
            hwnd = target_window()
            return desktop.hwnd_rect(hwnd) if hwnd else None
        services.hands = ScreenHands(front_rect)      # highlight / double / right click / scroll

    def window_to_shoot():
        hwnd = target_window()
        return desktop.hwnd_rect(hwnd) if hwnd else None
    shooter = Screenshotter(companion.windows, window_to_shoot)
    services.screenshot = shooter.take                 # "take a screenshot"
    services.pc_info = pc_stats.report                 # "what's using all my ram"
    services.doctor = AIDoctor(settings, brain.claude.has_key, openai=brain.openai)   # "set up your brain"
    from .ai.ollama_setup import OllamaSetup
    services.ollama_setup = lambda progress: OllamaSetup(services.doctor, settings, progress)   # installs it all

    def wake_ollama() -> None:                        # installed but not running: start it, so she can think
        try:
            if settings.ai_enabled and services.doctor.status()[0] == ai_doctor.STOPPED:
                services.doctor.start()
                log.info("ai: started Ollama")
        except Exception:
            log.exception("ai: couldn't check / start Ollama")
    threading.Thread(target=wake_ollama, daemon=True).start()
    # she zaps it from where she is (lying on the panel or standing) and it's clicked on impact
    services.zap_rect = lambda rect, then: zapper.zap_at(to_logical(rect), then, small=True) if settings.teleport \
        else then()
    services.psychosis = PsychosisShow(lambda: settings.speech_volume)
    services.games = GameWatch(companion.set_drone, system.processes, enabled=lambda: settings.game_drone,
                               game_dirs=lambda: [str(g.install_dir) for g in catalog.games if g.install_dir],
                               auto=lambda: settings.auto_game_drone)
    services.games.watch()                    # spots games you start yourself, too
    from .ui.stay_on_top import TopmostKeeper
    keeper = TopmostKeeper(services.games.front, in_game=lambda: services.games.active,
                           enabled=lambda: settings.always_on_top and not companion.hidden,
                           note=lambda text: controller.log("Games", text[:60]))
    keeper.start()                            # over full-screen games: back on top every 1.5 s (no focus taken)
    app._keep_on_top = keeper
    def own_remark(text: str, emotion: str) -> None:
        """Something she'd say by herself: not in quiet mode (Ctrl+Alt+P / "quiet mode") - she still answers you."""
        if not settings.quiet_mode:
            assistant.remark(text, emotion=emotion)
    hype = GameHype(settings, lambda text: (controller.log("Hype", text), own_remark(text, "happy")),
                    lambda: catalog.games, system.processes, busy=lambda: assistant._busy)
    hype.apply()                              # "nice kill!" - only if it's on in Settings
    assistant.settings_changed.connect(hype.apply)
    ocr = PersistentOcr()

    def in_game() -> bool:
        games = services.games
        try:
            return bool(games.active or looks_like_game(games.front(), games.game_dirs()))
        except Exception:
            return False

    services.in_game = in_game                # Discord mute / deafen mid-game: never tab you out
    from .away import NapWatch, PcWarnings, idle_seconds_source

    def may_nap() -> bool:
        return (controller.state is State.IDLE and not assistant._busy and not companion.hidden
                and not companion.drone and not in_game())
    nap = NapWatch(idle_seconds_source(), lambda: settings.nap_minutes, may_nap, companion.character.set_napping)
    controller.changed.connect(lambda: nap.napping and nap.check())   # she hears you: awake at once
    app._nap = nap
    app._pc_warnings = PcWarnings(lambda: settings.pc_warnings and not settings.quiet_mode and not in_game(),
                                  lambda text: (controller.log("PC", text[:50]), own_remark(text, "serious")))

    def game_rect():
        hwnd = target_window()
        return desktop.hwnd_rect(hwnd) if hwnd else None
    watcher = ScreenWatcher(settings, in_game, game_rect, ocr.read, hype._got, grab_image)
    watcher.apply()                           # any game: reads the middle of the screen for "ELIMINATED"...
    assistant.settings_changed.connect(watcher.apply)
    app.aboutToQuit.connect(ocr.stop)

    def game_mode(on: bool) -> None:
        if on:
            QTimer.singleShot(1500, memory.trim)  # her idle memory back to Windows for your game
    companion.drone_changed.connect(game_mode)
    from .integrations.discord_presence import DiscordPresence
    presence = DiscordPresence(enabled=lambda: settings.discord_presence)   # "Playing Capri" on Discord
    presence.start()
    companion.drone_changed.connect(lambda on: presence.set_state("drone" if on else "desktop"))
    assistant.settings_changed.connect(presence.refresh)
    app.aboutToQuit.connect(presence.close)
    from .integrations import now_doing

    def front_game() -> int | None:           # the game in front right now (its process id), if any
        games = services.games
        front = games.front()
        return front.pid if front and looks_like_game(front, games.game_dirs()) else None
    from .commands.games import _pid_alive
    gaming = now_doing.GameSeen(lambda: services.games.active, front_game, _pid_alive)

    def game_title() -> str:
        """The game you're in, for her Discord status: its name in your Steam library, else its program's name."""
        pid = gaming.pid or front_game()
        if not pid:
            return ""
        exe = ""
        try:
            for p in system.processes():
                if p.pid == pid:
                    exe = p.exe or p.name or ""
                    break
        except Exception:
            return ""
        return now_doing.game_title(exe, [(g.name, str(g.install_dir)) for g in catalog.games if g.install_dir])
    presence.game_name = game_title
    sounding = now_doing.sounding_for_platform()
    music = now_doing.MusicWatch(sounding, lambda: now_doing.browser_titles(system.processes, desktop)) \
        if sounding else None
    # Her music deck: a neon bar she stands on while music plays (media keys for the buttons)
    from .ui.music_deck import DeckKeeper, MusicDeck, song_from
    music_deck = MusicDeck()
    def deck_button(name: str) -> None:
        try:
            media.press(name)
        except OSError as exc:
            controller.log("Music", f"couldn't press {name}: {exc}"[:60])
    music_deck.pressed.connect(deck_button)

    def playing_title() -> str:               # from the music app's window ("Artist - Song"), else a music site
        try:
            procs = system.processes()
            players = [p for p in procs if now_doing.is_music_app(p.name or Path(p.exe or "").name)]
            song = song_from(desktop.window_title(w) for w in desktop.windows_for([p.pid for p in players]))
            if song:
                return song
            song = song_from(t for t in now_doing.browser_titles(system.processes, desktop)
                             if now_doing.music_site([t]))
            if song:
                return song
        except Exception:
            pass
        return "Now playing"
    deck_keeper = DeckKeeper(music_deck, companion, playing_title, lambda: settings.music_deck,
                             groove=lambda on: companion.character.set_grooving(on and settings.music_dance))
    app._music_deck = (music_deck, deck_keeper)

    def doing(mode: str) -> None:
        presence.set_doing(mode)
        deck_keeper.music_changed(mode == "music")
    status = now_doing.StatusWatch(doing, gaming, music,
                                   wanted=lambda: (settings.discord_presence and presence.available)
                                   or settings.music_deck)
    services.games.changed.connect(lambda on: status.tick())   # a game opened / closed: right away
    # Clips: the last two minutes of your game, on disk, while it should be recording ("clip that" saves it)
    from .integrations import clips as clipmod
    clips = clipmod.ClipRecorder(settings)
    services.clips = clips
    clip_state = {"starting": False}

    def clips_tick() -> None:
        try:
            want = settings.clips and (settings.clip_when == "always" or gaming())
        except Exception:
            want = False
        clips.check()
        if want and not clips.recording and not clip_state["starting"]:
            clip_state["starting"] = True

            def go() -> None:
                try:
                    clips.start()
                finally:
                    clip_state["starting"] = False
            threading.Thread(target=go, daemon=True, name="capri-clips-start").start()
        elif not want and clips.recording:
            clips.stop()
    clip_timer = QTimer(app)
    clip_timer.setInterval(4000)
    clip_timer.timeout.connect(clips_tick)
    clip_timer.start()
    app.aboutToQuit.connect(clips.stop)

    def clips_turn_on(progress) -> None:      # (a background thread) the recorder first, if it's missing
        if not clipmod.find_ffmpeg():
            if sys.platform != "win32":
                raise OSError("install ffmpeg first (sudo apt install ffmpeg), then try again")
            progress("Downloading the clip recorder... 0%")
            clipmod.download_ffmpeg(lambda pct: progress(f"Downloading the clip recorder... {pct}%"))
        settings.clips = True
        settings.save()
    services.clips_turn_on = clips_turn_on

    def big_moment(what: str) -> None:        # "Save big moments": a few seconds later (so the moment's in it)
        if not (settings.clips and settings.clip_moments and clips.recording):
            return

        def save() -> None:
            try:
                path = clips.save(30)
                log.info("clips: saved a big moment (%s): %s", what, path.name)
            except OSError as exc:
                log.info("clips: couldn't save a big moment: %s", exc)
        QTimer.singleShot(4000, lambda: threading.Thread(target=save, daemon=True).start())
    hype.on_big_moment = big_moment

    # Watch my screen: a glance now and then (to your AI, which must be able to see pictures), and "what do you see?"
    from .integrations.screen_watch import ScreenWatch, SeenMemory, tesseract_text

    def rgb_image(rgb):
        from PySide6.QtGui import QImage
        if rgb is None:
            return QImage()
        import numpy as np
        h, w = rgb.shape[:2]
        rgba = np.ascontiguousarray(np.dstack([rgb, np.full((h, w), 255, np.uint8)]))
        return QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()

    def screen_picture():
        """The screen your window is on (not always the main one: a game on your second monitor too)."""
        from PySide6.QtGui import QCursor, QGuiApplication, QImage
        if sys.platform == "win32":
            from .integrations.screen_click import grab, monitor_of
            try:
                rect = monitor_of(desktop.foreground())
            except Exception:
                rect = None
            if rect is None:
                sc = clipmod.primary_screen()
                rect = (sc.x, sc.y, sc.x + sc.width, sc.y + sc.height)
            return rgb_image(grab(rect))
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return screen.grabWindow(0).toImage() if screen is not None else QImage()

    def window_picture():
        """Just the window in front, drawn by itself - for when the screenshot came out black."""
        if sys.platform != "win32":
            from PySide6.QtGui import QImage
            return QImage()
        from .integrations.screen_click import grab_window
        try:
            return rgb_image(grab_window(desktop.foreground()))
        except Exception:
            from PySide6.QtGui import QImage
            return QImage()

    def front_title() -> str:
        try:
            return desktop.window_title(desktop.foreground())
        except Exception:
            return ""
    from .logs import log_dir
    watch = ScreenWatch(settings, brain, screen_picture, front_title,
                        lambda text, emotion: (controller.log("Watch", text[:60]), own_remark(text, emotion)),
                        busy=lambda: assistant._busy or controller.state in (State.LISTENING, State.PROCESSING),
                        memory=SeenMemory(log_dir() / "seen.json"),
                        notice=lambda text: assistant.show_result(State.ERROR, text, emotion="confused"),
                        grab_window=window_picture,
                        read_text=ocr.read if sys.platform == "win32" else tesseract_text)
    watch.start()
    services.screen_watch = watch

    # She plays your game ("play this for me"): looks (vision AI) -> moves (keys / camera / clicks), Esc stops her
    from .integrations import game_agent as gamemod
    from .integrations.game_hands import game_hands
    class _GameBridge(QObject):
        said = Signal(str)
        done = Signal(str)
        cursor = Signal(int, int)
    game_bridge = _GameBridge()
    app._game_bridge = game_bridge
    game_bridge.said.connect(lambda text: (controller.log("Game", text[:60]), assistant.remark(text, emotion="playful")))
    game_bridge.done.connect(lambda why: (controller.log("Game", why), assistant.show_result(
        State.SUCCESS if why in ("done", "stopped", "escape") else State.ERROR, gamemod.ending(why))))

    def to_screen(x: int, y: int) -> None:
        r = to_logical((x, y, x + 1, y + 1))
        her_cursor.glide(r.x(), r.y())
    game_bridge.cursor.connect(to_screen)

    def game_window(hwnd: int):
        if not hwnd or desktop.pid_of(hwnd) == os.getpid():          # never Capri herself
            return None
        r = desktop.hwnd_rect(hwnd)
        return gamemod.Rect(r[0], r[1], r[2] - r[0], r[3] - r[1]) if r else None

    def game_picture(rect):
        from PySide6.QtGui import QGuiApplication, QImage
        if sys.platform == "win32":
            from .integrations.screen_click import grab
            rgb = grab((rect.x, rect.y, rect.x + rect.w, rect.y + rect.h))
            if rgb is None:
                return None
            import numpy as np
            h, w = rgb.shape[:2]
            rgba = np.ascontiguousarray(np.dstack([rgb, np.full((h, w), 255, np.uint8)]))
            return QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
        screen = QGuiApplication.primaryScreen()
        return screen.grabWindow(0, rect.x, rect.y, rect.w, rect.h).toImage() if screen is not None else None
    services.game_agent = gamemod.GameAgent(brain, game_hands, game_picture, desktop.foreground, game_window,
                                            game_bridge.said.emit, game_bridge.done.emit,
                                            cursor=lambda x, y: game_bridge.cursor.emit(int(x), int(y)),
                                            title=desktop.window_title,
                                            lessons=gamemod.GameLessons(log_dir() / "game_lessons.json"))
    app.aboutToQuit.connect(services.game_agent.stop)
    status.start()                            # music -> her Discord status; gaming -> she steps aside for your game
    app._status_watch = status
    app.aboutToQuit.connect(status.stop)
    QTimer.singleShot(60_000, memory.trim)    # once she's settled in
    trim_timer = QTimer(app)
    trim_timer.setInterval(10 * 60_000)       # and every 10 minutes: idle memory back to Windows
    trim_timer.timeout.connect(memory.trim)
    trim_timer.start()
    lipsync.level.connect(companion.drone_window.set_voice_level)
    if sys.platform == "win32":
        visits = VisitActions(visit_show, desktop, ui, system.open_item)
        services.minimize_visit = lambda name, pids, then: visits.minimize(name, pids, then) if settings.teleport \
            else then()
        services.open_folder = lambda label, path: visits.open_folder(label, path) if settings.teleport \
            else system.open_item(path)
    router = CommandRouter(assistant, companion, catalog, system, services)
    QTimer.singleShot(9000, router.watch_reminders)   # reminders you set before (and any missed while she was closed)
    for window in (companion.character, companion.sit_window, companion.panel, companion.drone_window):
        if hasattr(window, "file_dropped"):
            window.file_dropped.connect(router.read_file)   # drop a file on her: she reads it
    assistant.command_handler = router.handle
    assistant.choose = router.choose
    from .logs import log_dir as _log_dir
    from .translate import LineTranslator
    assistant.translator = LineTranslator(brain.look if brain is not None else None, _log_dir(),
                                          available=router._ai_available)   # her lines in your language
    QTimer.singleShot(1500, catalog.rescan)   # find Steam games / shortcuts once she's on screen

    windows = {}

    def open_settings() -> None:
        if "settings" not in windows:
            windows["settings"] = SettingsWindow(router, settings, art.icon, apply_voice,
                                                 [(LookTab(companion), "Character"),
                                                  (AssistantTab(assistant, router, spotify), "Assistant"),
                                                  (PcTab(settings, assistant.settings_changed.emit,
                                                         lambda: greet(preview=True), game_hype=hype,
                                                         join_now=lambda: router.handle("join call"),
                                                         updates=services.updates,
                                                         restart=services.restart), "PC && chat"),
                                                  (ExtrasTab(settings, lambda: (assistant.settings_changed.emit(),
                                                                                companion._apply_visibility()),
                                                             services.clips_turn_on), "Extras")])
        win = windows["settings"]
        win.load_rows()
        win.show()
        win.raise_()
        win.activateWindow()
    services.open_settings = open_settings           # "open your settings"

    def open_chat() -> None:
        if "chat" not in windows:
            windows["chat"] = ChatWindow(assistant, art.icon)
        windows["chat"].open()
    services.open_chat = open_chat

    assistant.replied.connect(companion.feed.add_reply)        # her lines in the call cards
    menu = CompanionMenu(companion, art.icon, assistant, open_settings, open_chat)
    updates = UpdateManager(settings, controller, assistant, menu.tray)    # new versions from GitHub
    services.updates = updates
    menu.add_updates(updates)
    from .commands.parser import Intent as _Intent, Kind as _Kind
    menu.add_languages(lambda code: router.dispatch(_Intent(_Kind.LANGUAGE, (code,))))   # right-click -> Language

    def restart_capri() -> None:
        """Start a fresh Capri, then quit this one. A downloaded update installs as she starts."""
        from PySide6.QtCore import QProcess
        program, arguments, folder = restart_command()
        log.info("restarting Capri")
        lock.unlock()                                  # the new Capri mustn't think one's already running
        server.close()
        if not QProcess.startDetached(program, arguments, folder):
            lock.tryLock(100)
            controller.log("Error", "couldn't restart - start me again yourself")
            return
        app.quit()
    services.restart = restart_capri
    menu.add_restart(restart_capri)
    if settings.last_version != __version__:          # "Updated to 1.36.3" once, after an update
        if settings.last_version and not first_run:
            controller.log("Update", f"updated to Capri {__version__}")
            QTimer.singleShot(4000, lambda: assistant.show_result(
                State.SUCCESS, f"I've updated myself to Capri {__version__}.", speak=False, emotion="happy"))
        settings.last_version = __version__
        settings.save()
    if logs.last_crash:                               # a hard crash last time: say where the details are, once
        controller.log("Error", "I crashed last time - see crash.log")
        QTimer.singleShot(5000, lambda: assistant.show_result(
            State.ERROR, "I crashed last time. The details are in crash.log in my log folder (tray menu, Open log "
            "folder). Send it to the Capri Discord so it can be fixed.", speak=False, emotion="sad"))
    updates.start()

    # Global shortcuts: work even while a game has focus.
    hotkeys = HotkeyManager()

    def toggle_click_through() -> None:
        on = not settings.click_through
        companion.set_click_through(on)
        controller.log("Click", "through ON (locked)" if on else "through off")
    remote["listen"] = assistant.listen_now
    companion.panel.chat_bits = settings.panel_chat             # "YOU >" + TYPE / TALK on her text box
    companion.panel.type_clicked.connect(open_chat)
    companion.panel.talk_clicked.connect(assistant.listen_now)

    def chat_bits() -> None:
        if companion.panel.chat_bits != settings.panel_chat:
            companion.panel.chat_bits = settings.panel_chat
            companion.panel.refresh()
            companion._place_panel()
    assistant.settings_changed.connect(chat_bits)
    remote["click-through"] = toggle_click_through

    def toggle_quiet() -> None:
        settings.quiet_mode = not settings.quiet_mode
        settings.save()
        assistant.settings_changed.emit()
        controller.log("Quiet", "on" if settings.quiet_mode else "off")
        assistant.show_result(State.SUCCESS, "Quiet mode." if settings.quiet_mode else "Quiet mode off.", speak=False)

    def register_hotkeys() -> list[str]:
        hotkeys.unregister_all()
        errors = []
        for combo, action in ((settings.hotkey_listen, assistant.listen_now),
                              (settings.hotkey_click_through, toggle_click_through),
                              (settings.hotkey_quiet, toggle_quiet),
                              (settings.hotkey_hide, lambda: companion.set_hidden(not companion.hidden)),
                              (settings.hotkey_chat, open_chat)):
            if not combo or (sys.platform.startswith("linux") and combo.lower() == "ctrl+alt+t"):
                continue                      # (Linux: Ctrl+Alt+T opens the terminal - not taken from you)
            error = hotkeys.register(combo, action)
            if error and hotkeys_supported:
                controller.log("Hotkey", error)
                errors.append(error)
        return errors

    ears = WhisperEars(lambda: settings.whisper_size,
                       lambda: [a.name for a in catalog.apps] + [g.name for g in catalog.games][:30])

    parakeet_ears = parakeet.ParakeetEars()

    def parakeet_rest(on: bool) -> None:
        if (settings.hearing == "parakeet" or settings.language != "en") and parakeet.ready():
            parakeet_ears.rest(on)        # ~900 MB back to your game; Vosk hears you meanwhile
    companion.drone_changed.connect(parakeet_rest)

    def apply_hearing() -> list[str]:
        """Whisper re-hears your commands (better with accents) when it's picked and installed. In another
        language than English, Parakeet v3 hears every command (her quick ears only speak English)."""
        from . import languages
        languages.set_current(settings.language)
        languages.keep_voice = settings.keep_voice
        service.cleanup = settings.mic_cleanup
        service.any_language = not languages.english()
        if not languages.english():
            if parakeet.ready():
                service.refine = parakeet_ears.transcribe
                parakeet_ears.preload()
                return []
            service.refine = None
            return [f"To hear you in {languages.get().name}, Capri needs Parakeet: Settings -> Wake word -> "
                    f"Download Parakeet ({parakeet.model_mb()} MB). Typing to her works meanwhile."]
        if settings.hearing == "parakeet":
            if parakeet.ready():
                service.refine = parakeet_ears.transcribe
                parakeet_ears.preload()
                return []
            service.refine = None
            if not parakeet.installed():
                return ["Parakeet's engine (sherpa-onnx) isn't installed - using Vosk."]
            return ["Parakeet isn't downloaded yet - Settings -> Wake word -> Download Parakeet (using Vosk until then)."]
        if settings.hearing == "whisper" and whisper_installed():
            service.refine = ears.transcribe
            return []
        service.refine = None
        if settings.hearing == "whisper":
            return ["Whisper isn't installed yet - run setup_hearing.bat (using Vosk until then)."]
        return []

    def apply_voice() -> list[str]:
        service.set_threshold(settings.wake_threshold)
        return register_hotkeys() + apply_hearing()

    register_hotkeys()
    apply_hearing()
    services.language_changed = apply_hearing

    # Saying hi when you sign in (Windows start-up, unlocking, waking from sleep).
    last_greeting = [-1e9]

    def greet(preview: bool = False) -> None:
        if greeting.active or (not preview and (not settings.greet_on_login
                                                or time.monotonic() - last_greeting[0] < 60)):
            return
        last_greeting[0] = time.monotonic()
        text, emotion = chat.greeting(datetime.now().hour, settings.slang)
        router.small_talk.last = "hello"
        controller.log("Hi", "welcome back")
        controller.set_state(State.SPEAKING, text, emotion)
        if not (settings.big_greeting and not companion.hidden):
            return assistant.show_result(State.SPEAKING, text, emotion=emotion,
                                         follow_up=settings.conversation and chat.asks_back(text))
        greeting.play(text, emotion)

        def after() -> None:
            if not (settings.conversation and chat.asks_back(text)):
                return greeting.done_talking()
            if greeting.active:      # she asked you something: listen once she's back in her corner
                greeting.finished.connect(assistant.listen_for_reply, Qt.ConnectionType.SingleShotConnection)
                greeting.done_talking()
            else:
                assistant.listen_for_reply()
        if not assistant.say(text, then=after, emotion=emotion):
            greeting.done_talking()

    session = SessionWatcher()
    session.signed_in.connect(lambda: QTimer.singleShot(1500, greet))   # let the desktop appear first

    def shutdown() -> None:
        session.stop()
        hotkeys.unregister_all()
        speaker.shutdown()
        service.stop()

    app.aboutToQuit.connect(shutdown)
    companion.show()
    service.start()
    if args.startup:
        QTimer.singleShot(2500, greet)
    if first_run:
        controller.set_state(State.IDLE, "Hey choom. Say \u201cHey Capri\u201d and tell me what you need.")
        if menu.tray:
            menu.tray.showMessage(
                "Capri is online",
                "Say \u201cHey Capri, open Discord\u201d. Right-click me (or this tray icon) for settings. "
                "Your microphone audio is processed on this PC only.",
                QSystemTrayIcon.MessageIcon.Information, 8000)
    if settings.click_through and menu.tray:
        menu.tray.showMessage(
            "Capri", f"Click-through is on. Press {pretty(settings.hotkey_click_through)} "
                     "or use this tray icon to turn it off.",
            QSystemTrayIcon.MessageIcon.Information, 5000)
    return app.exec()
