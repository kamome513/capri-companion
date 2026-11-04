"""Watch my screen: every few minutes she glances at your screen and says something about what you're doing,
like a friend looking over your shoulder. And "hey Capri, what do you see?" / "look at my screen" any time.

The picture goes to the AI you picked in Settings -> Assistant (it has to be one that can see pictures: GPT-4o
mini, Gemini Flash, Claude, or on your own PC Ollama with gemma3 / llava / llama3.2-vision). With Ollama it never
leaves your PC; with an online AI it goes to that service. That's why this is off until you turn it on.

She doesn't look while a password manager, a bank, a sign-in page or a private browser window is in front, and
she's told never to read out names, messages, numbers or anything private. "Remember what she sees" keeps her
last few comments (on your PC only) so she can pick up where she left off ("still on that boss?").
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QImage

log = logging.getLogger("capri")

EVERY_CHOICES = (60, 120, 300, 600)        # seconds between looks
MAX_WIDTH = 1280                           # the picture is shrunk to this (enough to read, small to send)
MEMORY = 8                                 # comments she remembers
PRIVATE = ("password", "keepass", "1password", "bitwarden", "lastpass", "dashlane", "bank", "banking", "incognito",
           "inprivate", "private browsing", "sign in", "sign-in", "log in", "login", "credit card", "paypal",
           "authenticator", "2fa", "verification code", "secure checkout")
SKIP = "SKIP"

GLANCE = ("This is a picture of my screen right now. Say ONE short, natural thing about what I'm doing - like a friend "
          "glancing over my shoulder (max 25 words, in your own voice). React to it, don't describe the screen. Never "
          "read out private things: names, messages, emails, numbers, addresses, passwords. If there's nothing worth "
          "saying, reply with just SKIP.")
ASK = ("This is a picture of my screen right now. {question} Answer in one or two short sentences, in your own voice. "
       "Never read out private things: names, messages, emails, numbers, addresses, passwords.")


def is_private(title: str) -> bool:
    low = (title or "").lower()
    return any(word in low for word in PRIVATE)


def to_jpeg_b64(image: QImage, max_width: int = MAX_WIDTH, quality: int = 70) -> str:
    """The screen as a small JPEG, base64 (what the AIs take)."""
    if image.isNull():
        return ""
    if image.width() > max_width:
        image = image.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.convertToFormat(QImage.Format.Format_RGB888).save(buffer, "JPEG", quality)
    buffer.close()
    return base64.b64encode(bytes(data)).decode("ascii")


BLACK_SCREEN = ("All I get is a black screen. If it's a game in exclusive fullscreen, switch it to borderless "
                "or windowed and I can see it." if sys.platform == "win32" else
                "All I get is a black screen. On Wayland I can't take screenshots: log in with an X11 session "
                "(\"Ubuntu on Xorg\" or similar) and I can see it.")


def is_blank(image) -> bool:
    """A screenshot that came out (nearly) all one dark colour: nothing to show the AI."""
    if image is None or image.isNull() or image.width() < 2 or image.height() < 2:
        return True
    w, h = image.width(), image.height()
    values = []
    for gy in range(12):
        for gx in range(16):
            c = image.pixelColor(int((gx + 0.5) * w / 16), int((gy + 0.5) * h / 12))
            values.append(c.red() + c.green() + c.blue())
    return max(values) < 30 or (max(values) - min(values) < 6 and max(values) < 90)


def cleaned(text: str) -> str:
    """Her line, or "" for SKIP / nothing."""
    text = (text or "").strip().strip('"').strip()
    if not text or text.upper().rstrip(".!") == SKIP or text.upper().startswith(SKIP + " "):
        return ""
    return text


class SeenMemory:
    """Her last few comments about your screen (a small file in your user folder), so she can follow on."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.items: list[tuple[float, str]] = []
        if path is not None:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.items = [(float(t), str(s)[:200]) for t, s in raw if isinstance(s, str)][-MEMORY:]
            except (OSError, ValueError, TypeError):
                self.items = []

    def add(self, text: str, now: float | None = None) -> None:
        self.items.append((now if now is not None else time.time(), text[:200]))
        del self.items[:-MEMORY]
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.items), encoding="utf-8")
            except OSError:
                pass

    def recent(self, now: float | None = None, within: float = 3 * 3600) -> list[str]:
        now = now if now is not None else time.time()
        return [s for t, s in self.items if now - t < within][-3:]

    def clear(self) -> None:
        self.items = []
        if self.path is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


def glance_prompt(recent: list[str]) -> str:
    if not recent:
        return GLANCE
    return GLANCE + " Earlier you said: " + " / ".join(f'"{r}"' for r in recent) + \
        " - don't repeat yourself; follow on if it's the same thing."


class _Bridge(QObject):
    done = Signal(object, object)          # (callback, reply)


class ScreenWatch(QObject):
    def __init__(self, settings, brain, grab: Callable[[], QImage], front_title: Callable[[], str],
                 say: Callable[[str, str], None], busy: Callable[[], bool] = lambda: False,
                 memory: SeenMemory | None = None, notice: Callable[[str], None] = lambda text: None,
                 clock: Callable[[], float] = time.monotonic, background: bool = True,
                 grab_window: Callable[[], QImage] | None = None) -> None:
        super().__init__()
        self.grab_window = grab_window
        self.settings, self.brain, self.grab, self.front_title = settings, brain, grab, front_title
        self.say, self.busy, self.notice, self.clock = say, busy, notice, clock
        self.memory = memory or SeenMemory(None)
        self.background = background
        self.looking = False
        self._last = clock()
        self._told: set[str] = set()                    # problems already told to you (once each)
        self._fails = 0                     # AI problems in a row: she waits longer between glances
        self._bridge = _Bridge()
        self._bridge.done.connect(lambda then, reply: then(reply))
        self.timer = QTimer(self)
        self.timer.setInterval(15_000)
        self.timer.timeout.connect(self.tick)

    def start(self) -> None:
        self.timer.start()

    # -- now and then ---------------------------------------------------------------------------------------
    def tick(self) -> None:
        s = self.settings
        if not s.watch_screen or self.looking or self.busy():
            return
        if self.clock() - self._last < max(30, int(s.watch_every)):
            return
        self._last = self.clock()
        self._look(glance_prompt(self.memory.recent() if s.watch_remember else []), self._glanced)

    def _glanced(self, reply) -> None:
        if reply is None:
            return
        if self._problem(reply):
            self._fails += 1                         # a refusing AI isn't asked again every glance: back off
            self._last = self.clock() + min(1800, 60 * 2 ** self._fails)
            return
        self._fails = 0
        line = cleaned(reply.text)
        if not line:
            return
        if self.settings.watch_remember:
            self.memory.add(line)
        self.say(line, reply.emotion or "playful")

    # -- on request ------------------------------------------------------------------------------------------
    def ask(self, question: str, then: Callable[[str, str], None]) -> None:
        """"What do you see?" -> then(answer, emotion). The answer explains a problem when there is one."""
        def answered(reply) -> None:
            if reply is None:
                return then("I won't look while that's on screen - it looks private.", "neutral")
            if reply.missing:
                return then("I need an AI to see your screen. Pick one in my Settings, under Assistant.", "confused")
            if reply.error:
                return then(reply.text or "I couldn't see it right now.", "confused")
            line = cleaned(reply.text) or "Honestly? Nothing much going on there."
            if self.settings.watch_remember:
                self.memory.add(line)
            then(line, reply.emotion or "neutral")
        q = (question or "").strip() or "What do you see? React to it."
        self._look(ASK.format(question=q if q.endswith("?") else q + "."), answered)

    # -- the look itself -------------------------------------------------------------------------------------
    def _look(self, prompt: str, then: Callable) -> None:
        try:
            title = self.front_title() or ""
        except Exception:
            title = ""
        if is_private(title):
            log.info("watch: not looking - something private is in front")
            return then(None)
        try:
            picture = self.grab()
            if is_blank(picture) and self.grab_window is not None:
                picture = self.grab_window()                   # black: the window by itself (GPU-drawn apps)
            if is_blank(picture):
                log.info("watch: the screenshot came out black")
                from ..ai.claude import AIReply
                return then(AIReply(BLACK_SCREEN, error=True, blind=False))
            jpeg = to_jpeg_b64(picture)
        except Exception as exc:
            log.info("watch: couldn't take the picture: %s", exc)
            jpeg = ""
        if not jpeg:
            return then(None)
        self.looking = True
        bridge, brain = self._bridge, self.brain

        def work() -> None:
            try:
                reply = brain.look(prompt, jpeg)
            except Exception as exc:
                log.info("watch: the AI failed: %s", exc)
                from ..ai.claude import AIReply
                reply = AIReply("I couldn't see it right now.", error=True)
            self.looking = False
            bridge.done.emit(then, reply)
        if self.background:
            threading.Thread(target=work, daemon=True, name="capri-watch").start()
        else:
            work()

    def _problem(self, reply) -> bool:
        """An AI problem while watching by herself: tell you once (not every two minutes), then stay quiet."""
        if not (reply.error or reply.missing):
            return False
        key = "missing" if reply.missing else "blind" if getattr(reply, "blind", False) else "error"
        if key not in self._told:
            self._told.add(key)
            text = ("I'd love to watch your screen, but I need an AI that can see. Pick one in my Settings."
                    if key == "missing" else reply.text or "I couldn't see your screen just now.")
            self.notice(text)
        return True
