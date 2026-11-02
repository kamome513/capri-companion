"""Persistent user settings, stored as JSON.

Windows: %LOCALAPPDATA%\\Capri\\settings.json
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from PySide6.QtCore import QStandardPaths

log = logging.getLogger("capri")


@dataclass
class SavedPosition:
    """Where Capri stands, relative to the bottom-right of a screen's work area.

    Storing an offset from the corner (rather than absolute pixels) keeps her
    in the same spot when the resolution or taskbar changes.
    """
    screen: str
    right: int    # gap between Capri's right edge and the work area's right edge
    bottom: int   # gap between Capri's bottom edge and the work area's bottom edge


@dataclass
class Settings:
    always_on_top: bool = True
    compact: bool = False
    show_panel: bool = True
    show_log: bool = True
    log_style: str = "panel"           # activity log: "panel" (lines under her message) | "cards" (call cards above)
    click_through: bool = False
    position: SavedPosition | None = None
    # your fixes for words she mishears: [["to school", "discord"], ...] (Settings -> Wake word)
    corrections: list = field(default_factory=list)
    shortcuts: list = field(default_factory=list)     # [phrase, command]: "gaming time" -> "open steam and discord"
    learned_buttons: list = field(default_factory=list)   # {"phrase", "app", "name", "x", "y"}: "leave call" ->
                                                          # Discord's red button (taught by pointing at it)
    hearing: str = "vosk"              # "vosk" (light, quick) | "parakeet" (best for heavy accents, 480 MB download)
                                       # | "whisper" (better with accents - setup_hearing.bat)
    mic_cleanup: bool = True           # turn quiet mics up, cut rumble and hiss before she listens
    whisper_size: str = "base.en"      # base.en | small.en (best for strong accents, slower)
    # Voice (Stage 3)
    voice_enabled: bool = True         # listen for the wake word
    mic_muted: bool = False            # hard mute: microphone fully closed
    input_device: str = ""             # microphone name, "" = Windows default
    wake_threshold: float = 0.80       # 0-1, raise it if she wakes up by mistake
    wake_variants: list = field(default_factory=list)   # how she hears your voice say "Capri" (Teach her your voice)
    hotkey_listen: str = "ctrl+alt+c"  # push-to-talk: listen for one command
    hotkey_click_through: str = "ctrl+alt+shift+c"
    # Speech (Stage 5)
    speech_enabled: bool = True        # spoken replies (voice commands work either way)
    speech_voice: str = ""             # voice name, "" = Windows default
    speech_style: str = "capri"        # capri | natural | netrunner | glitch
    speech_volume: float = 0.6
    speech_speed: float = 0.6          # 0 = slow, 0.5 = normal, 1 = fast
    speech_pitch: float = 0.78         # 0 = deep, 0.5 = the voice's own pitch, 1 = very high
    speech_expression: float = 0.6     # how much her voice goes up and down (0 = a steady tone)
    elevenlabs_voice: str = ""         # ElevenLabs voice ID ("" = a standard one); the key is kept in secrets
    # Assistant (Stage 5)
    weather_city: str = ""             # home city for "what's the weather"
    weather_units: str = "metric"      # metric | imperial
    music_service: str = "spotify"     # where "play <song>" goes: spotify | youtube_music | soundcloud | youtube |
                                       #   apple_music | deezer | tidal | amazon_music | bandcamp
    spotify_client_id: str = ""        # your Spotify developer app (for "play <song>")
    share_memory_with_ai: bool = False # what she remembers about you goes to the AI too (off: it stays on your PC)
    ai_enabled: bool = True            # a chatbot: chat (and anything that isn't a command) goes to an AI
    ai_provider: str = "auto"          # auto | openai (ChatGPT or any OpenAI-style AI) | claude | local (Ollama)
    openai_preset: str = "openai"      # which service (ai/openai_compat.py PRESETS): openai, groq, gemini...
    openai_url: str = ""               # "" = the preset's address
    openai_model: str = ""             # "" = the preset's suggestion (ChatGPT: gpt-5-nano, the cheapest)
    chatbot_switched: bool = False     # turned the chatbot on once (1.13)
    ollama_model: str = "llama3.2"
    ollama_url: str = ""               # "" = http://127.0.0.1:11434
    slang: bool = True                 # talk like Night City: choom, preem, gonk...
    personality: str = "edgerunner"    # how she talks: edgerunner | sarcastic | silly | tsundere | sweet | deadpan
    chat_skin: str = "holocall"        # the typing chat window's look: holocall | netrunner | arasaka | neon | braindance
    # Look (Stage 5)
    character_style: str = "body"      # body (new sheet) | portrait (talking head) | classic (first art)
    idle_animation: bool = True        # breathing, blinking, looking around
    drone_look: str = "disk"           # game mode's drone: "disk" (shards round her eye) | "mask" (her green visor)
    drone_spot: str = ""               # where you dragged the drone: "screen|right|bottom" ("" = the very bottom-right)
    idle_acts: bool = True             # now and then: glitching, gaming, watching, on a call with D
    wild_hair: float = 1.0             # her hair storm: always at full (the slider is gone)
    hair_style: str = "storm"          # "storm" (traced from the show) | "classic" (her first spiky one)
    lounge: bool = False               # lie on top of the status panel
    perch_windows: bool = False        # sit on the window you're using; back onto the panel when it closes
    panel_static: bool = True          # TV static + glitches on the status panel
    # Conversation, start-up and PC control (v1.1)
    conversation: bool = True          # after she asks you something, listen for the answer (no wake word)
    auto_game_drone: bool = True       # ...and when she spots a game in front that you started yourself
    game_drone: bool = True            # turn into the little flying disk while a game she launched runs
    teleport: bool = True              # red lightning effects (zapping Discord's buttons, blasting closed windows)
    auto_update: bool = True           # check GitHub daily; download a new Capri, install it on the next start
    greet_on_login: bool = True        # say hi when Windows starts / you sign back in
    big_greeting: bool = True          # ...big, in the middle of the screen
    autostart_default_done: bool = False   # Start with Windows gets switched on once, on first run
    discord_mute_key: str = ""         # your Discord "Toggle Mute" keybind ("" = Discord's Ctrl+Shift+M)
    discord_deafen_key: str = ""       # your Discord "Toggle Deafen" keybind ("" = Discord's Ctrl+Shift+D)
    discord_leave_key: str = ""        # your Discord "Disconnect from Voice Channel" keybind ("" = press the button)
    discord_call: str = ""             # "join call": your voice channel's link (right-click it -> Copy Link)
    game_hype: bool = False            # "nice kill!": cheer for kills in CS2 / Dota 2 / League (writes their GSI cfg)
    game_hype_deaths: bool = False     # ...and say something when you die
    game_hype_screen: bool = False     # ...in any game: she reads the middle of the game screen (on this PC) for kills
    game_hype_encourage: bool = False  # ..."you're doing great" now and then while you play
    game_hype_token: str = ""          # the secret the games send back, so only they can talk to her

    @staticmethod
    def path() -> Path:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
        return Path(base) / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        path = cls.path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            log.warning(f"ignoring unreadable settings file {path}: {exc}")
            return cls()

        settings = cls()
        for f in fields(cls):
            if f.name == "position" or f.name not in raw:
                continue
            value, default = raw[f.name], getattr(settings, f.name)
            if isinstance(default, bool):
                if isinstance(value, bool):
                    setattr(settings, f.name, value)
            elif isinstance(default, float):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    setattr(settings, f.name, min(1.0, max(0.0, float(value))))
            elif isinstance(default, str) and isinstance(value, str):
                setattr(settings, f.name, value)
            elif f.name == "wake_variants" and isinstance(value, list):
                setattr(settings, f.name, [str(v)[:40] for v in value if isinstance(v, str) and v.strip()][:12])
            elif f.name == "learned_buttons" and isinstance(value, list):
                setattr(settings, f.name, [{k: (v if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
                                            for k, v in p.items() if k in ("phrase", "app", "name", "x", "y")}
                                           for p in value if isinstance(p, dict) and p.get("phrase")])
            elif isinstance(default, list) and isinstance(value, list):
                setattr(settings, f.name, [[str(p[0]), str(p[1])] for p in value
                                           if isinstance(p, (list, tuple)) and len(p) == 2])
        settings.wild_hair = 1.0                                     # always the full storm (the slider is gone)
        if settings.hair_style not in ("storm", "classic"):
            settings.hair_style = "storm"
        pos = raw.get("position")
        if isinstance(pos, dict):
            try:
                settings.position = SavedPosition(str(pos["screen"]), int(pos["right"]), int(pos["bottom"]))
            except (KeyError, TypeError, ValueError):
                pass
        return settings

    def save(self) -> None:
        path = self.path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            os.replace(tmp, path)   # atomic: never leaves a half-written file
        except OSError as exc:
            log.warning(f"could not save settings to {path}: {exc}")
