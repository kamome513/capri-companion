"""Free, private AI chat with a model running on your own PC, through Ollama.

Setup (once): install Ollama from https://ollama.com, then in a terminal run
    ollama pull llama3.2
(~2 GB). Then Settings -> Assistant -> AI: pick "On this PC (Ollama)".

Nothing leaves your PC: requests go to Ollama on 127.0.0.1. Same safety as the
Claude option - the model can only *suggest* actions through the same tools,
which become Capri's own intents and go through the same CommandRouter
(catalog, confirmations). Generated text is never executed.
"""

from __future__ import annotations

import re
import time
from typing import Callable

from .. import emotions
from ..about_you import scrub
from ..integrations import http
from .claude import CONVERSATION_IDLE, INFO_TOOLS, MAX_ACTIONS, MAX_TURNS, TOOLS, AIReply, system_prompt, to_intent

from .ollama_find import DEFAULT_URL, default_url, pick_model  # noqa: F401  (DEFAULT_URL: re-exported)
DEFAULT_MODEL = "llama3.2"        # 3B, ~2 GB, runs on most PCs; supports tools
TIMEOUT = 90.0                    # a small CPU-only PC can take a while on the first reply

OLLAMA_TOOLS = [{"type": "function",
                 "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
                for t in TOOLS]


ACTION_WORDS = re.compile(
    r"\b(?:open|close|launch|start|quit|exit|kill|play|pause|skip|mute|unmute|deafen|undeafen|search|google|look up|"
    r"find|type|click|press|minimi[sz]e|screenshot|weather|time|date|ram|cpu|storage|battery|timer|remind|alarm|"
    r"shut ?down|restart|reboot|lock|sleep|stream|join|leave|volume|turn (?:it )?(?:up|down)|set|switch|change|"
    r"can you|could you|would you|will you|please|pull up|bring up|put on|throw on)\b", re.IGNORECASE)


def wants_action(text: str) -> bool:
    """Does this sound like asking her to *do* something (vs. just talking)?"""
    return bool(ACTION_WORDS.search(text))


class LocalBrain:
    def __init__(self, url: Callable[[], str], model: Callable[[], str], info: dict[str, Callable[[dict], str]],
                 fetch: Callable = http.request, clock: Callable[[], float] = time.monotonic,
                 slang: Callable[[], bool] = lambda: False, persona: Callable[[], str] = lambda: "edgerunner") -> None:
        self._url, self._model, self._info = url, model, info
        self._fetch, self._clock, self._slang, self._persona = fetch, clock, slang, persona
        self.reset()

    def reset(self) -> None:
        self.messages: list[dict] = []
        self._last = -1e9

    chosen = ""                       # the model Ollama actually has that she uses (see available)

    def available(self) -> tuple[bool, str]:
        """(ok, message) - is Ollama answering, and has it got a model she can talk with?"""
        tags = None
        for wait in (4.0, 8.0):                         # a just-started Ollama can be slow to answer
            try:
                tags = self._fetch("GET", self._base() + "/api/tags", timeout=wait) or {}
                break
            except (http.HttpError, OSError):
                continue
        if tags is None:
            return False, (f"I can't reach Ollama at {self._base()}. Open the Ollama app (it sits by the "
                           f"clock), or say \u201cset up your brain\u201d.")
        names = [m.get("name", "") for m in tags.get("models", [])]
        wanted = self._model() or DEFAULT_MODEL
        model = pick_model(names, wanted)
        if not model:
            return False, f"Ollama's running, but a chat model isn't downloaded yet. Run:  ollama pull {wanted}"
        self.chosen = model
        return True, f"Ollama is ready with {model}."

    def _base(self) -> str:
        return (self._url() or default_url()).rstrip("/")

    def _use_model(self) -> str:
        if not self.chosen:
            try:
                self.available()                       # find out what Ollama has
            except Exception:
                pass
        return self.chosen or self._model() or DEFAULT_MODEL

    def ask(self, text: str) -> AIReply:
        """Blocking - call from a worker thread."""
        if self._clock() - self._last > CONVERSATION_IDLE or len(self.messages) >= MAX_TURNS * 2:
            self.reset()
        self._last = self._clock()
        self.messages.append({"role": "user", "content": scrub(text)})
        try:
            return self._loop()
        except http.HttpError as exc:
            self.reset()
            if exc.status == 404:
                self.chosen = ""                       # it was removed: look again next time
                return AIReply(f"My local AI model isn't downloaded. Run: ollama pull {self._model() or DEFAULT_MODEL}",
                               error=True)
            return AIReply(f"My local AI glitched ({exc.status}).", error=True)
        except OSError:
            self.reset()
            return AIReply(f"Can't reach Ollama at {self._base()}. Is the Ollama app running?", error=True)

    def _loop(self) -> AIReply:
        system = system_prompt(self._slang(), self._persona())
        last = next((m.get("content", "") for m in reversed(self.messages) if m.get("role") == "user"), "")
        # Small local models (llama 3.2...) chat far better without her whole list of PC actions in front of
        # them: hand them the tools only when you're asking for something to be done.
        tools = OLLAMA_TOOLS if wants_action(str(last)) else None
        for _ in range(4):
            body = {"model": self._use_model(),
                    "messages": [{"role": "system", "content": system}] + self.messages,
                    "stream": False, "options": {"temperature": 0.8}, "keep_alive": "3m"}   # RAM freed 3 min after
            if tools:
                body["tools"] = tools
            data = self._fetch("POST", self._base() + "/api/chat", timeout=TIMEOUT, json_body=body) or {}
            message = data.get("message") or {}
            said = (message.get("content") or "").strip()
            calls = message.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": said,
                                  **({"tool_calls": calls} if calls else {})})
            feeling, said = emotions.split_tag(said)
            said = said.strip()
            if not calls:
                return AIReply(said or "...", emotion=feeling)
            intents, results = [], []
            for call in calls:
                fn = call.get("function") or {}
                name, args = fn.get("name", ""), fn.get("arguments") or {}
                if not isinstance(args, dict):
                    args = {}
                if name in INFO_TOOLS and name in self._info:
                    try:
                        content = self._info[name](args)
                    except Exception as exc:
                        content = f"Error: {exc}"
                elif len(intents) < MAX_ACTIONS and (candidate := to_intent(name, args)) is not None:
                    intents.append(candidate)
                    content = "Sent to Capri's command system, which does it and tells the user."
                else:
                    content = f"Not done: at most {MAX_ACTIONS} actions at a time."
                results.append({"role": "tool", "content": scrub(str(content)), "tool_name": name})
            self.messages.extend(results)
            if intents:
                return AIReply(said, intents[0], emotion=feeling, intents=intents)
        return AIReply("Lost myself in my own circuits. Try again?", error=True)


class Brains:
    """Whichever AI is picked in Settings: ChatGPT or any other OpenAI-style AI (your API key),
    Claude (your API key), Ollama (free, on this PC), or "auto" - the first of those that's set up
    (a key you've added wins over Ollama). None set up: her built-in chatbot."""

    PROBE_SECONDS = 30.0           # how long "is Ollama running?" is remembered

    def __init__(self, settings, claude, local: LocalBrain, openai=None, clock: Callable[[], float] = time.monotonic) -> None:
        self.settings, self.claude, self.local, self.openai, self.clock = settings, claude, local, openai, clock
        self._probe = (-1e9, False, "")

    def _local_up(self) -> bool:
        at, ok, _why = self._probe
        if self.clock() - at > self.PROBE_SECONDS:
            ok, why = self.local.available()
            self._probe = (self.clock(), ok, why)
        return ok

    def _pick(self):
        """Blocking (may check Ollama) - call from a worker thread."""
        provider = getattr(self.settings, "ai_provider", "auto")
        if provider == "local":
            return self.local
        if provider == "claude":
            return self.claude
        if provider == "openai" and self.openai is not None:
            return self.openai
        if self.openai is not None and self.openai.has_key() and getattr(self.settings, "openai_preset", "") != "lmstudio":
            return self.openai
        if self.claude.has_key():
            return self.claude
        return self.local if self._local_up() else None

    def which(self) -> str:
        brain = self._pick()
        return ("local" if brain is self.local else "claude" if brain is self.claude else
                "openai" if brain is not None and brain is self.openai else "")

    def ask(self, text: str) -> AIReply:
        brain = self._pick()
        if brain is None:
            # Nothing reachable. Say why when you clearly meant to use Ollama (it's running but the model's
            # missing, or it's your pick) - not silently fall back to her built-in chat.
            why = self._probe[2]
            if "isn't downloaded" in why or getattr(self.settings, "ai_provider", "auto") == "local":
                return AIReply(f"{why} I'm on my built-in chat till then.", error=True, missing=True)
            return AIReply("", error=True, missing=True)
        return brain.ask(text)

    def reset(self) -> None:
        for brain in (self.claude, self.local, self.openai):
            if brain is not None:
                brain.reset()

    def refresh(self) -> None:
        """Check for Ollama again on the next question (it was just started / set up)."""
        self._probe = (-1e9, False, "")
