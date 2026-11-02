"""Application entry point."""

from __future__ import annotations

import argparse
import itertools
import logging
import threading
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QRect, QStandardPaths, Qt, QTimer
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
from .speech.engines import ElevenLabsEngine, VoiceBox
from .speech.speaker import Speaker
from .ui.art import CharacterArt
from .ui.assistant_tab import AssistantTab
from .ui.chat_window import ChatWindow
from .ui.companion import Companion
from .ui.greeting import GreetingShow
from .ui.screen_spots import taskbar_icon, to_logical
from .ui.psychosis import PsychosisShow
from .integrations.screen_click import ScreenHands, click_at, click_spotify_play
from .integrations.screen_targets import Finder, click, cursor_pos, target_window, windows_ocr
from .typing_watch import TypingWatch
from . import memory
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


def restart_command() -> tuple[str, list[str], str]:
    """(program, arguments, folder) that start Capri again: Capri.exe, or python -m capri from the code."""
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
    args = parser.parse_args(argv)
    from . import net
    net.use_system_certificates()     # downloads work on PCs whose antivirus / network checks HTTPS

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # let Ctrl+C in the console quit
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Capri")
    app.setOrganizationName("")   # settings live in ...\AppData\Local\Capri
    app.setQuitOnLastWindowClosed(False)

    # Only one Capri at a time. Starting her again (Start menu, run.bat) just brings her back.
    lock_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
    lock = QLockFile(str(lock_dir / "capri-companion.lock"))
    if not lock.tryLock(100):
        socket = QLocalSocket()
        socket.connectToServer(INSTANCE_NAME)
        if socket.waitForConnected(1000):
            socket.write(b"show")
            socket.waitForBytesWritten(1000)
        print("[capri] already running - brought her back to the front.")
        return 0

    app.running_mark = _running_mutex()   # the installer waits for this to go before it updates her
    first_run = not Settings.path().exists()
    settings = Settings.load()
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
    companion = Companion(controller, art, settings, sprites)
    d_picture = asset_root() / "d" / "d.png"                 # D, for her video calls (idle activity)
    if d_picture.is_file():
        companion.character.acts.contact = QImage(str(d_picture))

    # A second launch asks this one to show herself again.
    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE_NAME)
    server.listen(INSTANCE_NAME)

    def on_second_launch() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(lambda: (conn.readAll(), companion.set_hidden(False),
                                            controller.log("Hi", "already running - here I am"),
                                            log.info("second launch: showing the running Capri")))
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
        lambda: [p.pid for p in system.processes() if p.name.lower() == "spotify.exe"],
        spotify_titles, press_track_play, http.get_text,
        lambda url: http.request("GET", url), api_search=spotify_api_search,
        click_play=lambda pids: click_spotify_play(desktop, pids, services.spotify_buttons.log)
        ) if sys.platform == "win32" else None
    def window_rect(pids: list[int]):
        r = desktop.window_rect(pids)
        return to_logical(r) if r else None
    zapper = ZapShow(companion, window_rect)
    services.zap = lambda name, pids, then: zapper.zap(name, pids, then) if settings.teleport else then()

    visit_show = VisitShow(companion)

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
    hype = GameHype(settings, lambda text: (controller.log("Hype", text), assistant.say(text, emotion="happy")),
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
    assistant.command_handler = router.handle
    assistant.choose = router.choose
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
                                                         restart=services.restart), "PC && chat")])
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
    updates.start()

    # Global shortcuts: work even while a game has focus.
    hotkeys = HotkeyManager()

    def toggle_click_through() -> None:
        on = not settings.click_through
        companion.set_click_through(on)
        controller.log("Click", "through ON (locked)" if on else "through off")

    def register_hotkeys() -> list[str]:
        hotkeys.unregister_all()
        errors = []
        for combo, action in ((settings.hotkey_listen, assistant.listen_now),
                              (settings.hotkey_click_through, toggle_click_through)):
            error = hotkeys.register(combo, action)
            if error and hotkeys_supported:
                controller.log("Hotkey", error)
                errors.append(error)
        return errors

    ears = WhisperEars(lambda: settings.whisper_size,
                       lambda: [a.name for a in catalog.apps] + [g.name for g in catalog.games][:30])

    parakeet_ears = parakeet.ParakeetEars()

    def parakeet_rest(on: bool) -> None:
        if settings.hearing == "parakeet" and parakeet.ready():
            parakeet_ears.rest(on)        # ~900 MB back to your game; Vosk hears you meanwhile
    companion.drone_changed.connect(parakeet_rest)

    def apply_hearing() -> list[str]:
        """Whisper re-hears your commands (better with accents) when it's picked and installed."""
        service.cleanup = settings.mic_cleanup
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
