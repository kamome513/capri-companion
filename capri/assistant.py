"""Connects the voice service to Capri's states and panel.

This is the only place that decides what Capri *says in the panel* about
voice. Commands are handed to ``command_handler`` (the CommandRouter).
Yes/no questions ("Force close Discord?") go through ``confirm``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QTimer, Signal

from . import emotions, lines
from .commands.parser import parse_yes_no
from .controller import CompanionController
from .hotkeys import pretty
from .settings import Settings
from .states import State
from .voice.service import Status, VoiceService

log = logging.getLogger("capri")

if TYPE_CHECKING:
    from .speech.speaker import Speaker

RESULT_SECONDS = 4.0   # how long a result stays up before returning to standby
SHOW_WITHIN = 4.0      # her words wait for her voice to start, but never longer than this
ASK_WAIT = 15.0         # seconds to start answering when she asks you something
CONVERSATION_TURNS = 12 # follow-ups without the wake word (a silence ends it sooner), then "Hey Capri" again

STATUS_TEXT = {
    Status.READY: (State.IDLE, "Waiting for wake word..."),
    Status.MUTED: (State.IDLE, "Mic muted."),
    Status.MIC_ERROR: (State.ERROR, "No microphone available."),
    Status.MODEL_MISSING: (State.ERROR, "Voice model missing."),
    Status.MODEL_DOWNLOADING: (State.PROCESSING, "Getting my ears ready (one-time download)..."),
    Status.ENGINE_MISSING: (State.ERROR, "Voice engine not installed."),
    Status.MODEL_ERROR: (State.ERROR, "Voice model problem."),
}


class Assistant(QObject):
    settings_changed = Signal()
    replied = Signal(str, str)        # what she said / asked (text, emotion) - for the chat window

    def __init__(self, controller: CompanionController, settings: Settings, service: VoiceService,
                 speaker: Speaker | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.settings = settings
        self.service = service
        self.speaker = speaker
        self._talking = False
        self._unshown: tuple | None = None   # (line, generation, state, message, emotion): waiting for her voice
        self.collect: list | None = None      # while doing several steps: each step's result, said together at the end
        if speaker is not None:
            speaker.speaking_changed.connect(self._on_speaking)
            if hasattr(speaker, "began"):
                speaker.began.connect(self._on_began)
        self.command_handler: Callable[[str], None] | None = None
        # Picks the best of the recogniser's guesses (the router: the first that's a real command).
        self.choose: Callable[[list[str]], str] | None = None
        self._alternatives: list[str] = []
        self.status = ""
        self._idle = (State.IDLE, "Starting voice...")
        self._busy = False        # between wake word and result
        self._generation = 0      # invalidates pending return-to-standby timers
        self._told_stage4 = False
        self._told_local = False
        self._pending: tuple[str, Callable[[bool], None]] | None = None
        self._asking: Callable[[str | None], None] | None = None   # waiting for a free answer (ask())
        self._follow_up = False   # listening for a reply in a conversation (no wake word)
        self._turns = 0
        # Set by the app (Windows): notices you typing while she listens without the wake word, so
        # the mic picking up your keyboard isn't taken as an answer / a search / a follow-up.
        self.typing = None
        self.last_heard = ""
        self._listen_started = 0.0
        self.interrupted_by_typing = False   # the last answer was ignored because you were typing

        service.status_changed.connect(self._on_status)
        service.wake.connect(self._on_wake)
        service.partial.connect(self._on_partial)
        service.alternatives.connect(self._on_alternatives)
        service.command.connect(self._on_command)
        service.no_command.connect(self._on_no_command)
        service.rejected.connect(self._on_rejected)

    # -- controls (menu / hotkeys) --------------------------------------------
    def listen_now(self) -> None:
        self.service.listen_now()

    def set_voice_enabled(self, on: bool) -> None:
        self.settings.voice_enabled = on
        self.service.set_enabled(on)
        self._save()

    def set_muted(self, on: bool) -> None:
        self.settings.mic_muted = on
        self.service.set_muted(on)
        self._save()

    def set_speech_enabled(self, on: bool) -> None:
        self.settings.speech_enabled = on
        if not on and self.speaker is not None:
            self.speaker.stop()
        self._save()

    def set_device(self, name: str) -> None:
        self.settings.input_device = name
        self.service.set_device(name)
        self.controller.log("Mic", name or "Windows default")
        self._save()

    def _save(self) -> None:
        self.settings.save()
        self.settings_changed.emit()

    # -- voice events ---------------------------------------------------------------
    def _on_status(self, status: str, detail: str) -> None:
        previous, self.status = self.status, status
        if status == Status.VOICE_OFF:
            self._idle = (State.IDLE, f"Voice off. {pretty(self.settings.hotkey_listen)} to talk.")
        else:
            self._idle = STATUS_TEXT.get(status, (State.IDLE, ""))
        if status == Status.READY and previous != Status.READY:
            self.controller.log("Mic", detail or "default")
            if not self._told_local:
                self.controller.log("Local", "audio never leaves this PC")
                self._told_local = True
        elif status == Status.MIC_ERROR:
            self.controller.log("Error", detail or "microphone unavailable, retrying")
        elif status == Status.MODEL_MISSING:
            self.controller.log("Fix", detail or "run setup_voice.bat")
        elif status == Status.MODEL_DOWNLOADING:
            self.controller.log("Setup", "downloading my speech model (40 MB, once)")
        elif status in (Status.ENGINE_MISSING, Status.MODEL_ERROR):
            self.controller.log("Error", detail)
        if not self._busy:
            self.controller.set_state(*self._idle)

    # -- confirmations --------------------------------------------------------------
    def confirm(self, question: str, answer: Callable[[bool], None]) -> None:
        """Ask a yes/no question out loud-ish and listen for the reply.

        Anything other than a clear yes (silence, "no", mumbling) counts as no.
        """
        self._pending = (question, answer)
        self._busy = True
        self._generation += 1
        self.controller.log("Ask", question)
        # Say the question first, *then* listen - the mic ignores her while she talks.
        if not self._say_and_show(State.LISTENING, question, "serious", then=self._listen_without_wake):
            self._listen_without_wake()

    def ask(self, question: str, answer: Callable[[str | None], None], emotion: str = "playful",
            wait: float = ASK_WAIT, label: str = "") -> None:
        """Ask something and pass on whatever you say next (no wake word needed). You get `wait`
        seconds to start talking. None = you said nothing. `label` stays in the panel meanwhile."""
        self._asking = answer
        self._busy = True
        self._generation += 1

        def listen() -> None:
            self._listen_without_wake(wait)
        self.interrupted_by_typing = False
        if not self._say_and_show(State.LISTENING, question, emotion, then=listen, panel=f"{label}{question}"):
            listen()

    def _answer(self, yes: bool) -> None:
        _question, answer = self._pending
        self._pending = None
        self.controller.log("Answer", "yes" if yes else "no")
        answer(yes)

    def _on_wake(self, phrase: str, confidence: float) -> None:
        self._busy = True
        self._unshown = None
        self._generation += 1
        if self._pending is not None or self._asking is not None:
            return   # keep showing the question while she listens for the answer
        if self._follow_up:
            self.controller.set_state(State.LISTENING, "I'm listening...")
            return
        self._turns = 0   # a fresh "Hey Capri" starts a new conversation
        if phrase == "push-to-talk":
            self.controller.log("Talk", "push-to-talk")
        else:
            self.controller.log("Wake", f'"{phrase}" {confidence:.0%}')
        self.controller.set_state(State.LISTENING, "Listening...")

    def _on_partial(self, text: str) -> None:
        if self._pending is None:
            self.controller.set_state(State.LISTENING, f'"{text}"')

    def typed(self, text: str) -> None:
        """Something typed in the chat window: handled exactly like something said - a command,
        an answer to her question, or chat."""
        text = text.strip()
        if not text:
            return
        if self.typing is not None:
            self.typing.stop()
            self._listen_started = time.monotonic() + 1e9   # typing *to her* isn't "you were typing"
        self.service.cancel_listen()          # it's answered: stop waiting for a spoken one
        self._follow_up = False
        self._alternatives = []
        self._on_command(text)

    def _on_alternatives(self, texts: list) -> None:
        self._alternatives = [str(t) for t in texts]

    def _on_command(self, text: str) -> None:
        self._unshown = None                    # you've moved on: her last words won't pop up now
        guesses = [text] + [t for t in self._alternatives if t != text]
        self._alternatives = []
        if self._you_were_typing():
            self.controller.log("Ignored", f'"{text[:30]}" - you were typing')
            self.interrupted_by_typing = True
            return self._on_no_command()
        if self._pending is not None:
            answer = next((a for a in (parse_yes_no(g) for g in guesses) if a is not None), None)
            return self._answer(answer is True)
        if self.choose is not None and len(guesses) > 1:
            picked = self.choose(guesses)
            if picked != text:
                self.controller.log("Heard", f'"{text}" -> "{picked}"')
                text = picked
        if self._asking is not None:
            answer, self._asking = self._asking, None
            self.controller.log("Heard", f'"{text}"')
            return answer(text)
        self._follow_up = False
        self.controller.log("Heard", f'"{text}"')
        self.last_heard = text                  # Settings -> Wake word -> "Fix this"
        if self.command_handler is not None:
            self.controller.set_state(State.PROCESSING, "Processing command...")
            self.command_handler(text)
            return
        # Stage 3: no actions yet. Say so instead of pretending.
        if not self._told_stage4:
            self.controller.log("Note", "actions arrive in stage 4")
            self._told_stage4 = True
        self.show_result(State.IDLE, f'Heard: "{text}"')

    def _on_no_command(self) -> None:
        if self.typing is not None:
            self.typing.stop()
        if self._pending is not None:
            return self._answer(False)   # no reply = no
        if self._asking is not None:
            answer, self._asking = self._asking, None
            return answer(None)
        if self._follow_up:              # you didn't answer: the chat's over, no fuss
            self._follow_up = False
            self._busy = False
            self.controller.set_state(*self._idle)
            return
        if self.settings.mic_muted:
            self.show_result(State.IDLE, "Mic is muted.")
        else:
            text, emotion = lines.line("didnt_catch", self.settings.slang)
            self.show_result(State.IDLE, text, emotion=emotion)

    NEAR_MISS_GAP = 20.0      # seconds between "heard something like Capri" notes in her log

    def _on_rejected(self, text: str, confidence: float) -> None:
        """Not for her, or too unsure: she stays asleep. A near miss goes in her log now and then, so
        you can see she heard *something* (and why it didn't count) - not silently ignored."""
        log.info(f"ignored possible wake word: {text!r} confidence {confidence:.2f}")
        now = time.monotonic()
        if confidence >= 0.5 and now - getattr(self, "_near_miss_at", -1e9) > self.NEAR_MISS_GAP:
            self._near_miss_at = now
            self.controller.log("Almost", f"{text[:34]} ({round(confidence * 100)}%) - stayed asleep")

    # -- results -------------------------------------------------------------------
    def show_result(self, state: State, message: str, speak: bool = True, emotion: str = "",
                    follow_up: bool = False, translated: bool = False) -> None:
        """Show an outcome (and say it, with feeling), then fall back to standby after she's done.
        In another language her built-in lines are translated first (translated=True: already in it, e.g. the AI's).

        follow_up: it's a conversation - once she's finished talking she listens for your
        reply for a few seconds, no wake word needed (up to CONVERSATION_TURNS times).
        """
        if self.collect is not None:                    # one step of several: noted, said at the end
            self.collect.append((state, message))
            self.controller.set_state(State.PROCESSING, message)
            return
        translator = getattr(self, "translator", None)
        if not translated and translator is not None and message and translator.cached(message) != message:
            known = translator.cached(message)
            if known is not None:
                message = known
            elif translator.wanted(message):
                generation = self._generation
                return translator.translate(message, lambda text: self.show_result(
                    state, text, speak, emotion, follow_up, translated=True) if self._generation == generation
                    else None)
        self._busy = False
        self._generation += 1
        generation = self._generation
        emotion = emotion if emotion in emotions.EMOTIONS else emotions.guess(message, state)
        follow_up = follow_up and self._turns < CONVERSATION_TURNS and not self.settings.mic_muted
        then = self.listen_for_reply if follow_up else None
        if follow_up:
            self._turns += 1
        if speak:
            spoken = self._say_and_show(state, message, emotion, then=then)
        else:
            self._unshown = None
            self._show(state, message, emotion)
            spoken = False
        if not spoken and then is not None:
            QTimer.singleShot(1200, then)   # not spoken: give you a moment to read it
        QTimer.singleShot(int(RESULT_SECONDS * 1000), lambda: self._back_to_idle(generation))

    def _say_and_show(self, state: State, text: str, emotion: str, then: Callable[[], None] | None = None,
                      panel: str | None = None) -> bool:
        """Say it, and show it in her panel / the chat as her voice starts - synthesis takes a
        moment, and words popping up long before she says them feels laggy. False = not spoken
        (shown straight away)."""
        panel = text if panel is None else panel
        in_sync = bool(text) and self.speaker is not None and hasattr(self.speaker, "began")
        self._unshown = None
        if not in_sync:
            self._show(state, panel, emotion, text)
        spoken = self.say(text, then=then, emotion=emotion)
        if in_sync and spoken:
            line = self.speaker.line
            self._unshown = (line, self._generation, state, panel, emotion, text)
            QTimer.singleShot(int(SHOW_WITHIN * 1000), lambda: self._on_began(line))   # a very slow voice
        elif in_sync:
            self._show(state, panel, emotion, text)
        return spoken

    def _show(self, state: State, message: str, emotion: str, said: str | None = None) -> None:
        self.controller.set_state(state, message, emotion)
        said = message if said is None else said
        if said:
            self.replied.emit(said, emotion)

    def _on_began(self, line: int) -> None:
        """Her voice for `line` started (or never will): show its words now - unless something
        newer has taken over the panel since (a new command, a question)."""
        waiting = self._unshown
        if waiting is None or waiting[0] != line:
            return
        self._unshown = None
        _line, generation, state, panel, emotion, said = waiting
        if generation == self._generation:
            self._show(state, panel, emotion, said)

    def listen_for_reply(self) -> None:
        if self._busy or self._pending is not None:
            return   # something else took over meanwhile
        self._follow_up = True
        self._listen_without_wake()

    def _listen_without_wake(self, wait: float | None = None) -> None:
        """Listen for an answer / a follow-up (no wake word) - watching for you typing meanwhile."""
        self._listen_started = time.monotonic()
        if self.typing is not None:
            self.typing.start()
        if wait is None:
            self.service.listen_now()
        else:
            self.service.listen_now(wait)

    def _you_were_typing(self) -> bool:
        """Did you type during this listen (or just before it)? Then what she 'heard' was most
        likely your keyboard, or you talking to yourself - not her."""
        watch = self.typing
        if watch is None:
            return False
        watch.stop()
        if not (self._asking is not None or self._follow_up or self._pending is not None):
            return False                          # "Hey Capri ..." is always for her
        watch.sample()
        return watch.typed_at >= self._listen_started - 1.0

    def say(self, text: str, then: Callable[[], None] | None = None, emotion: str = "neutral") -> bool:
        """Speak if spoken replies are on. False = not spoken (muted / no voice)."""
        if self.speaker is None:
            return False
        spoken = text.replace("\u201c", "").replace("\u201d", "").replace('"', "")
        return self.speaker.say(spoken, then=then, emotion=emotion)

    def _on_speaking(self, on: bool) -> None:
        self._talking = on
        self.service.set_speaking(on)

    def _back_to_idle(self, generation: int) -> None:
        if generation != self._generation or self._busy:
            return
        busy = getattr(self.speaker, "busy", None)
        if self._talking or (callable(busy) and busy()):   # still talking, or about to: check again shortly
            QTimer.singleShot(400, lambda: self._back_to_idle(generation))
            return
        self.controller.set_state(*self._idle)
