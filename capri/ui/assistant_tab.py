"""Settings -> Assistant: Capri's voice, weather, Spotify and optional AI."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from .. import personality, secrets
from ..commands.parser import Intent, Kind
from ..speech.effects import CAPRI_PRESET, STYLES

if TYPE_CHECKING:
    from ..assistant import Assistant
    from ..commands.router import CommandRouter
    from ..integrations.spotify import Spotify

TEST_LINE = "Hey choom. Capri online. Systems preem. Try not to break anything."
SPOTIFY_HELP = ("One-time setup (Premium needed to start songs):  1. Create an app at developer.spotify.com/dashboard  "
                "2. Add the redirect URI  http://127.0.0.1:8973/callback  3. Paste its Client ID here and press Connect.")
AI_HELP = ("Chat, and anything that isn't one of her commands, goes as text (never audio) to the AI you pick. "
           "Easiest: pick ChatGPT and paste your API key.")


def voice_label(name: str) -> str:
    """How a voice shows in the list."""
    if name.startswith("beeps: "):
        kind = name.split(": ", 1)[1]
        return f"Beeps - {kind} (no words, like old Pok\u00e9mon games)"
    if name.startswith("elevenlabs: "):
        return "ElevenLabs (online, your key)"
    return name


class _Signals(QObject):
    spotify_done = Signal(str)
    spotify_test_done = Signal(str)
    voice_progress = Signal(str)
    models_done = Signal(object, object)       # (which box, [model names] or a problem)


class ModelBox(QComboBox):
    """A model name you can type, or pick from the list of models your AI actually has."""

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumContentsLength(22)
        self.setText(text)

    def text(self) -> str:
        return self.currentText()

    def setText(self, text: str) -> None:
        self.setEditText(text or "")

    def setPlaceholderText(self, text: str) -> None:
        self.lineEdit().setPlaceholderText(text)

    def set_models(self, names: list[str]) -> None:
        keep = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems(names)
        self.setEditText(keep)
        self.blockSignals(False)


def _slider(value: float) -> QSlider:
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(0, 100)
    s.setValue(round(value * 100))
    return s


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class AssistantTab(QWidget):
    def __init__(self, assistant: Assistant, router: CommandRouter, spotify: Spotify | None) -> None:
        super().__init__()
        self.assistant, self.router, self.spotify = assistant, router, spotify
        self.settings = assistant.settings
        self._signals = _Signals()
        self._signals.spotify_done.connect(self._spotify_finished)
        s = self.settings
        root = QVBoxLayout(self)

        # -- voice --
        voice = QGroupBox("Capri's voice")
        form = QFormLayout(voice)
        self.spoken = QCheckBox("Spoken replies (voice commands keep working when this is off)")
        self.spoken.setChecked(s.speech_enabled)
        form.addRow(self.spoken)
        self.slang = QCheckBox("Night City slang (\u201cPreem, choom.\u201d \u201cTotal gonk moment.\u201d)")
        self.slang.setChecked(s.slang)
        form.addRow(self.slang)
        self.personality = QComboBox()
        for p in personality.PERSONALITIES.values():
            self.personality.addItem(p.label, p.key)
        self.personality.setCurrentIndex(max(0, self.personality.findData(s.personality)))
        self.personality.setToolTip("How she talks - her chat, her AI and her remarks. Or say “be sarcastic”.")
        self.personality.currentIndexChanged.connect(self._personality_picked)   # hear it right away
        form.addRow("Personality", self.personality)
        self.voice = QComboBox()
        self.voice.addItem("Default", "")
        for name in (assistant.speaker.voices() if assistant.speaker else []):
            self.voice.addItem(voice_label(name), name)
        self.voice.setCurrentIndex(max(0, self.voice.findData(s.speech_voice)))
        form.addRow("Voice", self.voice)
        # ElevenLabs: your own key (and a voice ID from their Voice Library) - then pick it as her voice
        self.eleven_key = QLineEdit(secrets.get("elevenlabs_api_key"))
        self.eleven_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.eleven_key.setPlaceholderText("ElevenLabs API key (elevenlabs.io -> Developers -> API keys)")
        self.eleven_key.editingFinished.connect(self._eleven_key_entered)    # pasted a key: hear it right away
        form.addRow("ElevenLabs key", self.eleven_key)
        self.eleven_voice = QLineEdit(s.elevenlabs_voice)
        self.eleven_voice.setPlaceholderText("voice ID (Voice Library -> a voice -> copy its ID); empty = a standard voice")
        form.addRow("ElevenLabs voice", self.eleven_voice)
        # Her neural voice: natural and expressive instead of the robotic Windows voices.
        self.neural_status = QLabel()
        self.neural_status.setObjectName("hint")
        self.neural_btn = QPushButton("Download Capri's voice (120 MB)")
        self.neural_btn.clicked.connect(self._download_voice)
        self._signals.voice_progress.connect(self._voice_progress)
        row = QHBoxLayout()
        row.addWidget(self.neural_btn)
        row.addWidget(self.neural_status, 1)
        form.addRow(row)
        self._refresh_neural()
        self.style_box = QComboBox()
        for key, label in STYLES.items():
            self.style_box.addItem(label, key)
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(s.speech_style)))
        self.style_box.currentIndexChanged.connect(self._style_picked)   # takes effect right away
        form.addRow("Style", self.style_box)
        self.volume = _slider(s.speech_volume)
        self.speed = _slider(s.speech_speed)
        self.pitch = _slider(s.speech_pitch)
        form.addRow("Volume", self.volume)
        form.addRow("Speed", self.speed)
        form.addRow("Pitch", self.pitch)
        self.expression = _slider(s.speech_expression)
        self.expression.setToolTip("How much her voice goes up and down - left: a steady tone, right: very animated")
        form.addRow("Expression", self.expression)
        test = QPushButton("Test voice")
        test.clicked.connect(self._test_voice)
        self.voice_result = QLabel("")
        self.voice_result.setObjectName("hint")
        self.voice_result.setWordWrap(True)
        if hasattr(assistant.speaker, "spoke"):
            assistant.speaker.spoke.connect(self._spoke)
            assistant.speaker.failed.connect(lambda msg: self.voice_result.setText(f"Couldn't speak: {msg}"))
        preset = QPushButton("Capri preset")
        preset.setToolTip("Her character's sound: her neural voice (if installed), higher, quicker and bright")
        preset.clicked.connect(self._capri_preset)
        row = QHBoxLayout()
        row.addWidget(preset)
        row.addWidget(test, 1)
        form.addRow(row)
        form.addRow(self.voice_result)
        root.addWidget(voice)

        # -- weather --
        weather = QGroupBox("Weather")
        form = QFormLayout(weather)
        self.city = QLineEdit(s.weather_city)
        self.city.setPlaceholderText("e.g. Manchester")
        form.addRow("Home city", self.city)
        self.units = QComboBox()
        self.units.addItem("Celsius, km/h", "metric")
        self.units.addItem("Fahrenheit, mph", "imperial")
        self.units.setCurrentIndex(max(0, self.units.findData(s.weather_units)))
        form.addRow("Units", self.units)
        test = QPushButton("Test weather")
        test.clicked.connect(lambda: (self.apply(), self.router.dispatch(Intent(Kind.WEATHER))))
        form.addRow(test, _hint("Free, from Open-Meteo. Only the city name is sent."))
        root.addWidget(weather)

        # -- spotify (and the other music apps) --
        sp = QGroupBox("Music  (“Hey Capri, play ...”)")
        form = QFormLayout(sp)
        from ..commands.parser import MUSIC_SERVICES
        self.music_service = QComboBox()
        for key, (_pattern, label) in MUSIC_SERVICES.items():
            self.music_service.addItem(label, key)
        self.music_service.setCurrentIndex(max(0, self.music_service.findData(s.music_service)))
        self.music_service.currentIndexChanged.connect(self._music_picked)    # takes effect right away
        form.addRow("Play music on", self.music_service)
        form.addRow(_hint("Or say \u201cuse SoundCloud for music\u201d - or \u201cplay X on YouTube Music\u201d for one song. "
                          "Spotify plays the song itself; the others open their search for it in your browser "
                          "(then say \u201cclick\u201d and the song). Pause / skip / volume work for all of them."))
        form.addRow(_hint(SPOTIFY_HELP))
        self.client_id = QLineEdit(s.spotify_client_id)
        self.client_id.setPlaceholderText("Client ID from your Spotify developer app")
        form.addRow("Client ID", self.client_id)
        row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._spotify_connect)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._spotify_disconnect)
        self.spotify_status = QLabel()
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        row.addWidget(self.spotify_status, 1)
        form.addRow(row)
        self.test_song = QLineEdit("let you down by nf")
        test_play = QPushButton("Test Spotify")
        test_play.setToolTip("Plays this song the way “Hey Capri, play ...” does, and shows every step")
        test_play.clicked.connect(self._test_spotify)
        self._signals.spotify_test_done.connect(self._show_spotify_test)
        row2 = QHBoxLayout()
        row2.addWidget(self.test_song, 1)
        row2.addWidget(test_play)
        form.addRow("Test a song", row2)
        form.addRow(_hint("Not connected (or no Premium)? “Play ...” opens the song's search in Spotify "
                          "instead, and pause / next / volume still work through the media keys."))
        root.addWidget(sp)

        # -- AI --
        ai = QGroupBox("AI conversation (optional)")
        form = QFormLayout(ai)
        form.addRow(_hint(AI_HELP))
        self.ai_on = QCheckBox("Chatbot: chat with her about anything (commands still work as usual)")
        self.ai_on.setChecked(s.ai_enabled)
        form.addRow(self.ai_on)
        # One list: every AI she can use. Only the boxes that AI needs are shown.
        from ..ai.openai_compat import PRESETS
        self.ai_pick = QComboBox()
        self.ai_pick.addItem("Auto - whichever one below you've set up", "auto")
        for key, (label, _url, _model, _needs) in PRESETS.items():
            self.ai_pick.addItem(label, f"openai:{key}")
        self.ai_pick.addItem("Claude (Anthropic)", "claude")
        self.ai_pick.addItem("Ollama (free, on this PC - needs a strong PC)", "local")
        self.ai_pick.currentIndexChanged.connect(self._ai_picked)
        form.addRow("AI", self.ai_pick)
        self.ai_url = QLineEdit(s.openai_url)
        form.addRow("Address", self.ai_url)
        self.ai_model = ModelBox(s.openai_model)
        self.ai_model.setToolTip("Pick one of the models your key has (press Show my models), or type any model "
                                 "name. Empty = the one shown.")
        self.ai_models_btn = QPushButton("Show my models")
        self.ai_models_btn.setToolTip("Ask the AI service which models your key can use (add your key first)")
        self.ai_models_btn.clicked.connect(lambda: self._list_models("openai"))
        self.ai_model_row = self._with_button(self.ai_model, self.ai_models_btn)
        form.addRow("Model", self.ai_model_row)
        self.ai_key = QLineEdit(secrets.get("openai_api_key"))
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key.editingFinished.connect(lambda: self._ai_key_entered("openai"))   # checked straight away
        form.addRow("API key", self.ai_key)
        self.api_key = QLineEdit(secrets.get("anthropic_api_key"))
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-ant-...  (from console.anthropic.com)")
        self.api_key.editingFinished.connect(lambda: self._ai_key_entered("claude"))
        form.addRow("Claude API key", self.api_key)
        self.ollama_model = ModelBox(s.ollama_model)
        self.ollama_model.setPlaceholderText("llama3.2")
        self.ollama_models_btn = QPushButton("Show my models")
        self.ollama_models_btn.setToolTip("The models you've downloaded in Ollama")
        self.ollama_models_btn.clicked.connect(lambda: self._list_models("local"))
        self.ollama_model_row = self._with_button(self.ollama_model, self.ollama_models_btn)
        form.addRow("Ollama model", self.ollama_model_row)
        self._signals.models_done.connect(self._models_listed)
        self.ai_hint = _hint("")
        form.addRow(self.ai_hint)
        self.ai_last = _hint("")                  # what happened the last time she used it - never a mystery
        self.ai_last.setWordWrap(True)
        self.ai_last.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Last try", self.ai_last)
        self._show_ai_last()
        self._ai_form = form
        self._select_ai(s)
        test = QPushButton("Test AI")
        test.clicked.connect(self._test_ai)
        form.addRow(test)
        root.addWidget(ai)

        # -- what she remembers about you: on this PC only --
        mem = QGroupBox("What Capri remembers about you (private)")
        form = QFormLayout(mem)
        form.addRow(_hint("Tell her things like “my name is Sam”, “I love Deadlock”, “my favourite "
                          "food is ramen” or “remember that my exam is Friday”. It's saved in your own "
                          "user folder on this PC only - never in Capri's files - and personal things are answered "
                          "by her own chatbot, not sent to the AI. “Forget everything about me” wipes it."))
        self.share_memory = QCheckBox("Let the AI know what Capri remembers about me")
        self.share_memory.setChecked(s.share_memory_with_ai)
        self.share_memory.setToolTip("Off (recommended): nothing personal goes into what's sent to the AI.")
        form.addRow(self.share_memory)
        self.memory_view = _hint("")
        self.memory_view.setWordWrap(True)
        form.addRow("She knows", self.memory_view)
        row = QHBoxLayout()
        forget = QPushButton("Forget everything about me")
        forget.clicked.connect(self._forget_me)
        row.addWidget(forget)
        row.addStretch(1)
        form.addRow(row)
        self._show_memory()
        root.addWidget(mem)

        row = QHBoxLayout()
        row.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        row.addWidget(self.status)
        save = QPushButton("Save")
        save.clicked.connect(lambda: (self.apply(), self.status.setText("Saved.")))
        row.addWidget(save)
        root.addLayout(row)
        self._refresh_spotify()

    # -- actions ----------------------------------------------------------------------
    def apply(self) -> None:
        s = self.settings
        s.speech_enabled = self.spoken.isChecked()
        s.slang = self.slang.isChecked()
        s.personality = self.personality.currentData()
        from ..speech.engines import ElevenLabsEngine
        new_key = self.eleven_key.text().strip()
        if new_key != secrets.get("elevenlabs_api_key"):
            secrets.set_many({"elevenlabs_api_key": new_key})
            if new_key and self.voice.findData(ElevenLabsEngine.NAME) < 0:
                self.voice.addItem(voice_label(ElevenLabsEngine.NAME), ElevenLabsEngine.NAME)
            if new_key:                                # you just added a key: that's the voice you want
                self.voice.setCurrentIndex(self.voice.findData(ElevenLabsEngine.NAME))
        s.elevenlabs_voice = self.eleven_voice.text().strip()
        s.speech_voice = self.voice.currentData()
        s.speech_style = self.style_box.currentData()
        s.speech_volume = self.volume.value() / 100
        s.speech_speed = self.speed.value() / 100
        s.speech_pitch = self.pitch.value() / 100
        s.speech_expression = self.expression.value() / 100
        s.weather_city = self.city.text().strip()
        s.weather_units = self.units.currentData()
        s.spotify_client_id = self.client_id.text().strip()
        s.music_service = self.music_service.currentData()
        s.ai_enabled = self.ai_on.isChecked()
        s.share_memory_with_ai = self.share_memory.isChecked()
        picked = self.ai_pick.currentData() or "auto"
        s.ai_provider = "openai" if picked.startswith("openai:") else picked
        if picked.startswith("openai:"):
            s.openai_preset = picked.split(":", 1)[1]
        s.openai_url = self.ai_url.text().strip()
        s.openai_model = self.ai_model.text().strip()
        if self.ai_key.text().strip() != secrets.get("openai_api_key"):
            secrets.set_many({"openai_api_key": self.ai_key.text().strip()})
        s.ollama_model = self.ollama_model.text().strip() or "llama3.2"
        key = self.api_key.text().strip()
        if key != secrets.get("anthropic_api_key"):
            secrets.set_many({"anthropic_api_key": key})
        s.save()
        self.assistant.settings_changed.emit()

    def _memory(self):
        return getattr(getattr(self.router, "chatbot", None), "memory", None)

    def _show_memory(self) -> None:
        memory = self._memory()
        if memory is None:
            return self.memory_view.setText("Not available.")
        self.memory_view.setText(memory.summary() or "Nothing yet.")
        path = getattr(memory, "path", None)
        self.memory_view.setToolTip(f"Saved in {path}" if path else "Kept in memory only")

    def _forget_me(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        memory = self._memory()
        if memory is None or memory.empty():
            return self.memory_view.setText("Nothing to forget.")
        sure = QMessageBox.question(self, "Capri", "Delete everything Capri remembers about you? This can't be undone.")
        if sure == QMessageBox.StandardButton.Yes:
            memory.forget_all()
            self._show_memory()

    def _style_picked(self) -> None:
        """A new voice style: saved now, and she says a line in it so you hear the difference."""
        self.settings.speech_style = self.style_box.currentData()
        self.settings.save()
        if self.assistant.speaker is not None:
            self.assistant.speaker.say("This is how I sound now.", emotion="playful", force=True)

    def _select_ai(self, s) -> None:
        data = f"openai:{s.openai_preset}" if s.ai_provider == "openai" else s.ai_provider
        self.ai_pick.blockSignals(True)
        self.ai_pick.setCurrentIndex(max(0, self.ai_pick.findData(data)))
        self.ai_pick.blockSignals(False)
        self._ai_picked()

    def _ai_picked(self) -> None:
        """Only the boxes the chosen AI needs: no Ollama model when you picked ChatGPT, and so on."""
        from ..ai.openai_compat import PRESETS
        picked = self.ai_pick.currentData() or "auto"
        preset = picked.split(":", 1)[1] if picked.startswith("openai:") else ""
        _label, url, model, needs_key = PRESETS.get(preset, PRESETS["custom"])
        auto = picked == "auto"                  # auto: both key boxes, so a pasted key always has a place
        show = {self.ai_url: preset in ("custom", "lmstudio"), self.ai_model_row: bool(preset),
                self.ai_key: (bool(preset) and needs_key) or auto, self.api_key: picked == "claude" or auto,
                self.ollama_model_row: picked == "local"}
        for widget, visible in show.items():
            self._ai_form.setRowVisible(widget, visible)
        self.ai_url.setPlaceholderText(url or "https://.../v1")
        self.ai_model.setPlaceholderText(model or "the model's name")
        self.ai_key.setPlaceholderText("your API key (ChatGPT: platform.openai.com -> API keys)"
                                       if preset in ("openai", "") else "your API key from the service's website")
        self.ai_hint.setText({
            "auto": "Uses ChatGPT (or another service) if you've added its key, else Claude with a key, else Ollama.",
            "claude": "Your own key from console.anthropic.com. Paid per use.",
            "local": "Free and private, but slow unless your PC is strong. Say \u201cset up your brain\u201d to install it.",
        }.get(picked, "Press Show my models to pick from the ones your key has - or leave Model empty to use "
                      "the one shown." if preset else ""))

    @staticmethod
    def _with_button(box: QWidget, button: QPushButton) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(box, 1)
        lay.addWidget(button)
        return row

    def _list_models(self, which: str) -> None:
        """Show my models: ask the picked AI (with the key typed here, saved or not) what it has."""
        button = self.ai_models_btn if which == "openai" else self.ollama_models_btn
        button.setEnabled(False)
        button.setText("Asking...")
        picked = self.ai_pick.currentData() or "auto"
        preset = picked.split(":", 1)[1] if picked.startswith("openai:") else "openai"
        url, key = self.ai_url.text().strip(), self.ai_key.text().strip()

        def run() -> None:
            try:
                if which == "openai":
                    from ..ai.openai_compat import OpenAIBrain
                    brain = OpenAIBrain(lambda: preset, lambda: url, lambda: "", lambda: key, {})
                    names = brain.list_models()
                else:
                    from ..ai.ollama_find import default_url
                    from ..integrations import http
                    base = (self.settings.ollama_url or default_url()).rstrip("/")
                    tags = http.request("GET", base + "/api/tags", timeout=8.0) or {}
                    names = [m.get("name", "") for m in tags.get("models", [])]
                self._signals.models_done.emit(which, names)
            except Exception as exc:
                self._signals.models_done.emit(which, exc)
        threading.Thread(target=run, daemon=True).start()

    def _models_listed(self, which: str, result) -> None:
        from ..ai.openai_compat import NOT_CHAT
        box, button = ((self.ai_model, self.ai_models_btn) if which == "openai"
                       else (self.ollama_model, self.ollama_models_btn))
        button.setEnabled(True)
        button.setText("Show my models")
        if isinstance(result, Exception):
            status = getattr(result, "status", None)
            self.ai_hint.setText("That key doesn't work - check it." if status in (401, 403) else
                                 "Couldn't get the list: is Ollama running?" if which == "local" else
                                 f"Couldn't get the list ({str(result)[:80]}). Add your key first.")
            return
        chat = sorted({n for n in result if n and not any(w in n.lower() for w in NOT_CHAT)})
        if not chat:
            self.ai_hint.setText("No chat models found." + (" Run: ollama pull llama3.2" if which == "local" else ""))
            return
        box.set_models(chat)
        if not box.text():
            box.setText(chat[0])
        box.showPopup()
        self.ai_hint.setText(f"{len(chat)} model{'s' * (len(chat) != 1)} found - pick one, then Save.")

    def _show_ai_last(self) -> None:
        last = getattr(self.router, "ai_status", None)
        if not last:
            return self.ai_last.setText("Not used yet. Press Test AI, or just talk to her.")
        when, ok, text = last
        self.ai_last.setText(f"{when} - " + (f"worked: \u201c{text}\u201d" if ok else f"didn't work: {text}"))

    def _ai_key_entered(self, which: str) -> None:
        """You pasted an AI key: save it, make sure that AI is the one she uses, and try it right
        away - she answers through it, or says exactly what's wrong (no credit, bad key...)."""
        box, secret = (self.ai_key, "openai_api_key") if which == "openai" else (self.api_key, "anthropic_api_key")
        key = box.text().strip()
        if key == secrets.get(secret):
            return
        picked = self.ai_pick.currentData() or "auto"
        if key and which == "openai" and not picked.startswith("openai:"):
            self.ai_pick.setCurrentIndex(max(0, self.ai_pick.findData("openai:openai")))     # a key = ChatGPT
        elif key and which == "claude" and picked != "claude":
            self.ai_pick.setCurrentIndex(max(0, self.ai_pick.findData("claude")))
        self.ai_on.setChecked(True)
        self.apply()
        if not key:
            return self.status.setText("Key removed.")
        self.status.setText("Key saved - checking it...")
        self.router.test_ai(self._ai_tested)

    def _ai_tested(self, result: str) -> None:
        self.status.setText(result.split("\n")[0])
        self._show_ai_last()

    def _eleven_key_entered(self) -> None:
        """You pasted an ElevenLabs key: switch her to that voice and let you hear it (or why not)."""
        if self.eleven_key.text().strip() == secrets.get("elevenlabs_api_key"):
            return
        self.apply()
        if self.eleven_key.text().strip():
            self._test_voice()

    def _music_picked(self) -> None:
        key = self.music_service.currentData()
        if key and key != self.settings.music_service:
            self.settings.music_service = key
            self.settings.save()
            self.status.setText(f"Music plays on {self.music_service.currentText()} now.")

    def _personality_picked(self) -> None:
        """A new personality: saved now, and she says its line in its voice so you hear the difference."""
        key = self.personality.currentData()
        if not key or key == self.settings.personality:
            return
        self.settings.personality = key
        self.settings.save()
        if self.assistant.speaker is not None:
            p = personality.get(key)
            self.assistant.speaker.say(p.intro or TEST_LINE, emotion=p.emotion or "playful", force=True)

    def showEvent(self, event) -> None:
        """Changed something by voice or the tray (personality, music app, voice style...)? Show
        what's really set now - so Save / closing Settings doesn't undo it."""
        self.reload()
        super().showEvent(event)

    def reload(self) -> None:
        s = self.settings
        pick = lambda box, value: box.setCurrentIndex(max(0, box.findData(value)))   # noqa: E731
        widgets = (self.spoken, self.slang, self.personality, self.voice, self.style_box, self.volume, self.speed,
                   self.pitch, self.expression, self.city, self.units, self.client_id, self.music_service, self.ai_on,
                   self.ai_pick, self.ollama_model, self.ai_url, self.ai_model)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.spoken.setChecked(s.speech_enabled)
            self.slang.setChecked(s.slang)
            pick(self.personality, s.personality)
            if self.voice.findData(s.speech_voice) >= 0:
                pick(self.voice, s.speech_voice)
            pick(self.style_box, s.speech_style)
            self.volume.setValue(round(s.speech_volume * 100))
            self.speed.setValue(round(s.speech_speed * 100))
            self.pitch.setValue(round(s.speech_pitch * 100))
            self.expression.setValue(round(s.speech_expression * 100))
            self.city.setText(s.weather_city)
            pick(self.units, s.weather_units)
            self.client_id.setText(s.spotify_client_id)
            pick(self.music_service, s.music_service)
            self.ai_on.setChecked(s.ai_enabled)
            self.ollama_model.setText(s.ollama_model)
            self.ai_url.setText(s.openai_url)
            self.ai_model.setText(s.openai_model)
            self._select_ai(s)
            self._show_ai_last()
        finally:
            for w in widgets:
                w.blockSignals(False)

    def _capri_preset(self) -> None:
        p = CAPRI_PRESET
        self.voice.setCurrentIndex(max(0, self.voice.findData(p["speech_voice"])))
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(p["speech_style"])))
        self.pitch.setValue(round(p["speech_pitch"] * 100))
        self.speed.setValue(round(p["speech_speed"] * 100))
        self.apply()
        self.assistant.say(TEST_LINE, emotion="playful")

    def _test_voice(self) -> None:
        """Say the test line with the voice picked here - even with spoken replies off - and show
        which voice really said it."""
        self.apply()
        speaker = self.assistant.speaker
        if speaker is None:
            return self.voice_result.setText("No text-to-speech on this PC.")
        p = personality.get(self.settings.personality)          # in her current personality's voice
        line = TEST_LINE if p.key == "edgerunner" else f"{TEST_LINE.split('.')[0]}. {p.intro}"
        emotion = p.emotion or "playful"
        try:
            speaker.say(line, emotion=emotion, force=True)
        except TypeError:                                       # an older speaker without force
            speaker.say(line, emotion=emotion)
        self.voice_result.setText("Speaking..." if self.settings.speech_enabled else
                                  "Speaking... (spoken replies are off, so she'll only talk for tests)")

    def _spoke(self, voice: str, note: str) -> None:
        if not self.isVisible():
            return
        label = voice.split(": ", 1)[-1] if voice else "the default voice"
        self.voice_result.setText(f"Said with {label}" + (f" - {note}." if note else "."))

    def _refresh_neural(self) -> None:
        from ..speech.engines import KokoroEngine
        try:
            import kokoro_onnx  # noqa: F401
            package = True
        except ImportError:
            package = False
        if KokoroEngine.installed() and package:
            self.neural_status.setText("Her neural voice is installed (restart Capri if it isn't in the list).")
            self.neural_btn.setVisible(False)
        elif not package:
            import sys
            self.neural_status.setText(
                "Not in the Capri.exe version (that keeps the download small) - pick a Windows voice, "
                "ElevenLabs or the beeps." if getattr(sys, "frozen", False) else
                "Neural voice engine missing: run run.bat again to install it.")
            self.neural_btn.setEnabled(False)
        else:
            self.neural_status.setText("Sounds far more natural than the Windows voices. Runs offline.")

    def _download_voice(self) -> None:
        from ..speech.engines import download_kokoro
        self.neural_btn.setEnabled(False)

        def run() -> None:
            last = [-1]

            def progress(name: str, done: int, total: int) -> None:
                pct = int(done * 100 / total) if total else 0
                if pct != last[0]:
                    last[0] = pct
                    self._signals.voice_progress.emit(f"Downloading {name}: {pct}%")
            try:
                download_kokoro(progress=progress)
                self._signals.voice_progress.emit("done")
            except Exception as exc:   # shown to you; nothing half-installed is left behind
                self._signals.voice_progress.emit(f"Download failed: {str(exc)[:60]}")
        threading.Thread(target=run, daemon=True).start()

    def _voice_progress(self, message: str) -> None:
        if message == "done":
            self.neural_btn.setVisible(False)
            speaker = self.assistant.speaker
            if speaker is None:
                return self.neural_status.setText("Installed.")
            speaker.reload_voices()
            self.neural_status.setText("Installed - that's her new voice. (Voice: Default uses it.)")
            self.voice.addItem("neural: Capri", "neural: Capri")
            self.assistant.say(TEST_LINE, emotion="playful")
            return
        self.neural_status.setText(message)
        if message.startswith("Download failed"):
            self.neural_btn.setEnabled(True)

    def _test_ai(self) -> None:
        self.apply()
        if not self.settings.ai_enabled:
            self.status.setText("Tick “Talk with an AI” first.")
            return
        brain = self.router.services.brain
        local = getattr(brain, "local", None)
        openai = getattr(brain, "openai", None)
        if self.settings.ai_provider == "openai" and openai is not None:
            ok, message = openai.ready()
            if not ok:
                self.status.setText(message)
                return
        if self.settings.ai_provider == "local" and local is not None:
            ok, message = local.available()        # quick check, so a missing Ollama says so plainly
            if not ok:
                self.status.setText(message)
                return
        self.status.setText("Asking...")
        self.ai_last.setText("Asking...")
        self.router.test_ai(self._ai_tested)

    def _test_spotify(self) -> None:
        """Run the real 'play a song' steps and show what happened at each one."""
        import logging
        from ..commands.parser import parse
        app = getattr(self.router.services, "spotify_app", None)
        if app is None:
            return self._show_spotify_test("Spotify control is only available on Windows.")
        intent = parse("play " + self.test_song.text())
        query, artist = intent.query, intent.artist
        steps: list[str] = []

        class Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                message = record.getMessage()
                if message.startswith("spotify:"):
                    steps.append(message[len("spotify:"):].strip())

        def run() -> None:
            handler = Collect()
            log = logging.getLogger("capri")
            log.addHandler(handler)
            try:
                result = app.play(query or artist, artist if query else "")
                outcome = f"Result: {result.status} {result.title}".strip()
            except Exception as exc:
                outcome = f"Result: error - {exc}"
            finally:
                log.removeHandler(handler)
            self._signals.spotify_test_done.emit(f"Asked for: {query!r} by {artist!r}\n\n" +
                                                 "\n".join(f"• {s}" for s in steps) + "\n\n" + outcome)
        threading.Thread(target=run, daemon=True).start()
        self.spotify_status.setText("Testing... watch Spotify.")

    def _show_spotify_test(self, report: str) -> None:
        from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPlainTextEdit
        self.spotify_status.setText("")
        dialog = QDialog(self)
        dialog.setWindowTitle("Spotify test")
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(report)
        text.setReadOnly(True)
        text.setMinimumSize(560, 300)
        layout.addWidget(text)
        buttons = QDialogButtonBox()
        copy = buttons.addButton("Copy", QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(report))
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        close.clicked.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.show()
        self._test_dialog = dialog

    def _refresh_spotify(self) -> None:
        connected = bool(self.spotify and self.spotify.connected)
        self.spotify_status.setText("Connected." if connected else "Not connected.")
        self.disconnect_btn.setEnabled(connected)
        self.connect_btn.setEnabled(self.spotify is not None)

    def _spotify_connect(self) -> None:
        self.apply()
        self.connect_btn.setEnabled(False)
        self.spotify_status.setText("Approve Capri in the browser window...")

        def run() -> None:
            try:
                self.spotify.connect()
                message = "Connected."
            except Exception as exc:   # shown to you, nothing else happens
                message = str(exc) or "Couldn't connect."
            self._signals.spotify_done.emit(message)
        threading.Thread(target=run, daemon=True).start()

    def _spotify_finished(self, message: str) -> None:
        self._refresh_spotify()
        self.spotify_status.setText(message)

    def _spotify_disconnect(self) -> None:
        if self.spotify:
            self.spotify.disconnect()
        self._refresh_spotify()
