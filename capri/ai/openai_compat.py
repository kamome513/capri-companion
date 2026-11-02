"""Any AI with an OpenAI-style chat API: ChatGPT itself, or Groq, OpenRouter, Google Gemini,
DeepSeek, Mistral, xAI, LM Studio on your PC... (Settings -> Assistant -> AI -> "ChatGPT or any AI").

You give it the service (or its web address), a model and your API key. Default: ChatGPT with
gpt-5-nano - OpenAI's cheapest model, so your credit lasts the longest.

What is sent: only the text of a request Capri didn't recognise as a command, plus the last few
turns of the conversation - never audio. Same safety as Claude / Ollama: the AI can only *suggest*
actions through the same tools, which become Capri's own intents and go through the same
CommandRouter (catalog, confirmations). Generated text is never executed.
"""

from __future__ import annotations

import json
import re
import logging
import time
from typing import Callable

from .. import emotions
from ..about_you import scrub
from ..integrations import http
from .claude import CONVERSATION_IDLE, INFO_TOOLS, MAX_ACTIONS, MAX_TURNS, TOOLS, AIReply, system_prompt, to_intent

# key: (label, web address, suggested model, needs a key). Models are only suggestions - type any.
PRESETS = {
    "openai": ("ChatGPT (OpenAI)", "https://api.openai.com/v1", "gpt-5-nano", True),
    "groq": ("Groq (free tier, very fast)", "https://api.groq.com/openai/v1", "llama-3.1-8b-instant", True),
    "openrouter": ("OpenRouter (hundreds of models)", "https://openrouter.ai/api/v1", "openai/gpt-5-nano", True),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-latest", True),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", True),
    "mistral": ("Mistral", "https://api.mistral.ai/v1", "mistral-small-latest", True),
    "xai": ("xAI (Grok)", "https://api.x.ai/v1", "grok-3-mini", True),
    "lmstudio": ("LM Studio (on this PC)", "http://127.0.0.1:1234/v1", "", False),
    "custom": ("Custom (any OpenAI-compatible address)", "", "", True),
}
DEFAULT_PRESET = "openai"
log = logging.getLogger(__name__)
FREE_TIP = " Or use a free Google Gemini key (aistudio.google.com) - pick Google Gemini in my Settings."
TIMEOUT = 30.0
OPENAI_TOOLS = [{"type": "function",
                 "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
                for t in TOOLS]


def _portable(schema: dict) -> dict:
    """A tool's inputs in the plainest JSON schema every service accepts: Gemini rejects
    "additionalProperties" and "strict"; nobody minds them missing."""
    out = {}
    for key, value in schema.items():
        if key in ("additionalProperties", "strict"):
            continue
        out[key] = {k: _portable(v) if isinstance(v, dict) else v for k, v in value.items()} \
            if key == "properties" and isinstance(value, dict) else value
    return out


def portable_tools() -> list[dict]:
    """Her tools for any service: no strict-mode extras, and no empty input list (Gemini: "properties
    should be non-empty for OBJECT type") - a tool that takes nothing just has no parameters."""
    tools = []
    for t in TOOLS:
        fn = {"name": t["name"], "description": t["description"]}
        params = _portable(t["input_schema"])
        if params.get("properties"):
            fn["parameters"] = params
        tools.append({"type": "function", "function": fn})
    return tools


PORTABLE_TOOLS = portable_tools()
TOOL_TROUBLE = ("tool", "function", "additionalproperties", "unknown name", "invalid json payload", "schema",
                "parameters", "strict")


def tool_trouble(status: int, text: str) -> bool:
    """The service didn't like her tools (or doesn't do tools with this model) - not a missing model."""
    t = text.lower()
    return status in (400, 404, 422) and any(word in t for word in TOOL_TROUBLE)


# Models that can't hold a conversation (pictures, speech, search vectors...): never picked as a stand-in.
NOT_CHAT = ("embed", "image", "imagen", "veo", "tts", "audio", "transcribe", "whisper", "dall-e", "moderation",
            "realtime", "live", "aqa", "search", "computer-use", "robotics", "guard", "rerank", "native-audio")


def model_missing(status: int, detail: str) -> bool:
    """The service says the model doesn't exist (retired, renamed, a typo)."""
    d = detail.lower()
    return status == 404 or "model" in d and any(w in d for w in ("not exist", "not found", "not supported",
                                                                  "is not available", "no longer", "deprecated",
                                                                  "decommissioned", "invalid model"))


def pick_stand_in(available: list[str], wanted: str) -> str:
    """The available chat model closest to the one asked for: same family words ("flash", "lite", "mini"),
    stable before preview, newest version first. "" if there's none."""
    words = set(re.split(r"[-_.:/ ]+", wanted.lower())) - {""}
    best, best_key = "", None
    for name in available:
        low = name.lower()
        if not low or any(w in low for w in NOT_CHAT):
            continue
        parts = set(re.split(r"[-_.:/ ]+", low)) - {""}
        version = tuple(int(n) for n in re.findall(r"\d+", low)[:3])
        stable = not any(w in low for w in ("preview", "exp", "experimental", "beta", "alpha"))
        fast = bool(parts & {"flash", "mini", "lite", "small", "instant", "turbo", "chat", "nano", "haiku"})
        key = (len(words & parts), stable, fast, version, -len(low))
        if best_key is None or key > best_key:
            best, best_key = name, key
    return best


def _text(content) -> str:
    """A reply's words: a plain string, or (some services) a list of parts."""
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return (content or "").strip() if isinstance(content, str) else ""


def reasoning_model(model: str) -> bool:
    """OpenAI's thinking models (gpt-5..., o3...): told to think as little as possible - quick replies."""
    m = model.lower().split("/")[-1]
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


class OpenAIBrain:
    def __init__(self, preset: Callable[[], str], url: Callable[[], str], model: Callable[[], str],
                 api_key: Callable[[], str], info: dict[str, Callable[[dict], str]], fetch: Callable = http.request,
                 clock: Callable[[], float] = time.monotonic, slang: Callable[[], bool] = lambda: False,
                 persona: Callable[[], str] = lambda: "edgerunner") -> None:
        self._preset, self._url, self._model, self._key = preset, url, model, api_key
        self._info, self._fetch, self._clock, self._slang, self._persona = info, fetch, clock, slang, persona
        self._skip: set[str] = set()          # options this service turned out not to accept
        self.stand_in = ""                    # the model she switched to when yours doesn't exist (any more)
        self.reset()

    # -- which service ---------------------------------------------------------------------------
    def preset(self) -> tuple[str, str, str, bool]:
        return PRESETS.get(self._preset() or DEFAULT_PRESET, PRESETS["custom"])

    def label(self) -> str:
        return self.preset()[0].split(" (")[0] if self._preset() != "custom" else "my AI"

    def base(self) -> str:
        return ((self._url() or "").strip() or self.preset()[1]).rstrip("/")

    def model(self) -> str:
        return self.stand_in or (self._model() or "").strip() or self.preset()[2]

    def list_models(self) -> list[str]:
        """The models this key can use (the service's own /models list). Blocking."""
        key = self._key().strip()
        data = self._fetch("GET", self.base() + "/models", headers={"Authorization": f"Bearer {key}"} if key else {},
                           timeout=TIMEOUT) or {}
        items = data.get("data", []) if isinstance(data, dict) else []
        return [str(m.get("id", "")).split("models/")[-1] for m in items if isinstance(m, dict) and m.get("id")]

    def _swap_model(self) -> bool:
        """Her model doesn't exist (any more): switch to the closest one the service has. True if she did."""
        if self.stand_in:                                 # already swapped once: don't go round in circles
            return False
        wanted = self.model()
        try:
            stand_in = pick_stand_in(self.list_models(), wanted)
        except Exception as exc:
            log.warning("ai: couldn't list %s's models: %s", self.label(), exc)
            return False
        if not stand_in or stand_in == wanted:
            return False
        log.info("ai: %s has no model %r - using %r instead", self.label(), wanted, stand_in)
        self.stand_in = stand_in
        return True

    def has_key(self) -> bool:
        return bool(self._key().strip()) or not self.preset()[3]

    def ready(self) -> tuple[bool, str]:
        if not self.base():
            return False, "Type your AI's web address in Settings -> Assistant -> AI."
        if not self.model():
            return False, "Type a model name in Settings -> Assistant -> AI."
        if not self.has_key():
            return False, f"Add your {self.label()} API key in Settings -> Assistant -> AI."
        return True, f"My brain's online: {self.label()}, {self.model()}."

    def reset(self) -> None:
        self.messages: list[dict] = []
        self._last = -1e9

    # -- asking ------------------------------------------------------------------------------------
    def ask(self, text: str) -> AIReply:
        """Blocking (network) - call from a worker thread."""
        ok, message = self.ready()
        if not ok:
            return AIReply(message, error=True, missing=not self.has_key())
        if self._clock() - self._last > CONVERSATION_IDLE or len(self.messages) >= MAX_TURNS * 2:
            self.reset()
        self._last = self._clock()
        self.messages.append({"role": "user", "content": scrub(text)})
        try:
            return self._loop()
        except http.HttpError as exc:
            self.reset()
            detail = self._detail(exc)
            log.warning("ai: %s %s: HTTP %s %s", self.label(), self.model(), exc.status, detail or exc.body[:300])
            return AIReply(self._problem(exc), error=True, detail=f"HTTP {exc.status}: {detail or exc.body[:160]}")
        except (OSError, ValueError) as exc:
            self.reset()
            log.warning("ai: %s at %s unreachable: %r", self.label(), self.base(), exc)
            return AIReply(f"Can't reach {self.label()} right now.", error=True, detail=str(exc)[:200])
        except Exception as exc:              # never fail silently: say what broke
            self.reset()
            log.exception("ai: %s failed", self.label())
            return AIReply(f"{self.label()} glitched out.", error=True, detail=repr(exc)[:200])

    @staticmethod
    def _detail(exc: http.HttpError) -> str:
        data = exc.json()
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get("message", ""))[:300]
        if isinstance(data, list) and data and isinstance(data[0], dict):      # (Gemini wraps it in a list)
            inner = data[0].get("error")
            return str(inner.get("message", "") if isinstance(inner, dict) else inner or "")[:300]
        return str(err or "")[:300]

    def _problem(self, exc: http.HttpError) -> str:
        detail = self._detail(exc).lower()
        official = "api.openai.com" in self.base()
        if exc.status == 401:
            return (f"My {self.label()} key doesn't work. Copy it again from platform.openai.com/api-keys "
                    f"into Settings." if official else f"My {self.label()} key doesn't work. Check it in Settings.")
        if exc.status == 429 and official and ("quota" in detail or "billing" in detail or "credit" in detail):
            return ("My ChatGPT key has no credit. The API is paid separately from ChatGPT Plus: add a few "
                    "dollars at platform.openai.com, under Billing." + FREE_TIP)
        if model_missing(exc.status, detail):
            return (f"{self.label()} says there's no model called {self.model()}, and I couldn't find one to "
                    f"use instead. Clear the Model box in Settings, Assistant, or type one your key has.")
        if exc.status == 429:
            return (f"{self.label()} says I'm out of credit." if "quota" in detail or "credit" in detail else
                    f"{self.label()}'s rate limited. Give it a minute.")
        said = self._detail(exc).strip().rstrip(".")
        return f"{self.label()} refused: {said[:120]}." if said else f"{self.label()} glitched out ({exc.status})."

    def _tools(self) -> list[dict] | None:
        """OpenAI itself: her strict tools. Everyone else: the portable ones. A service that refused
        both: none (she just chats - commands still work, you say them to her directly)."""
        if "tools" in self._skip:
            return None
        if "api.openai.com" in self.base() and "portable" not in self._skip:
            return OPENAI_TOOLS
        return PORTABLE_TOOLS

    def _body(self, system: str) -> dict:
        model = self.model()
        body = {"model": model, "messages": [{"role": "system", "content": system}] + self.messages}
        tools = self._tools()
        if tools:
            body["tools"] = tools
        official = "api.openai.com" in self.base()
        if official and "max_completion_tokens" not in self._skip:
            body["max_completion_tokens"] = 1500 if reasoning_model(model) else 400
        elif "max_tokens" not in self._skip:
            body["max_tokens"] = 1024             # room for "thinking" models (Gemini 2.5...) to still answer
        if reasoning_model(model) and "reasoning_effort" not in self._skip:
            body["reasoning_effort"] = "minimal"
        return body

    def _post(self, system: str) -> dict:
        key = self._key().strip()
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        for _ in range(6):                    # a service that rejects something: adapt and ask again
            try:
                return self._fetch("POST", self.base() + "/chat/completions", json_body=self._body(system),
                                   headers=headers, timeout=TIMEOUT) or {}
            except http.HttpError as exc:
                body = exc.body.lower()
                detail = self._detail(exc) or body
                if self._tools() is not None and tool_trouble(exc.status, detail):
                    if self._tools() is OPENAI_TOOLS:
                        self._skip.add("portable")        # plainer tools
                    else:
                        self._skip.add("tools")           # this model doesn't do tools: just chat
                    log.info("ai: %s refused her tools (%s) - %s", self.label(), detail[:120],
                             "plainer ones" if "tools" not in self._skip else "chatting without them")
                    continue
                if model_missing(exc.status, detail) and self._swap_model():
                    continue                              # retired / renamed model: ask again with the new one
                dropped = next((o for o in ("reasoning_effort", "max_completion_tokens", "max_tokens")
                                if o in body and o not in self._skip and exc.status == 400), None)
                if dropped is None:
                    raise
                self._skip.add(dropped)
        return self._fetch("POST", self.base() + "/chat/completions", json_body=self._body(system),
                           headers=headers, timeout=TIMEOUT) or {}

    def _loop(self) -> AIReply:
        system = system_prompt(self._slang(), self._persona())
        for _ in range(4):                    # at most a few info-tool round trips per question
            data = self._post(system)
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            said = _text(message.get("content"))
            calls = message.get("tool_calls") or []
            if not said and not calls and choice.get("finish_reason") in ("length", "max_tokens") \
                    and "max_tokens" not in self._skip:
                # A "thinking" model spent the whole allowance thinking: ask again without a limit.
                self._skip.update({"max_tokens", "max_completion_tokens"})
                log.info("ai: %s used every token thinking - asking again without a limit", self.label())
                continue
            self.messages.append({"role": "assistant", "content": said or None,
                                  **({"tool_calls": calls} if calls else {})})
            feeling, said = emotions.split_tag(said)
            said = said.strip()
            if not calls:
                return AIReply(said or "...", emotion=feeling)
            intents = []
            for call in calls:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
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
                self.messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                      "content": scrub(str(content))})
            if intents:
                return AIReply(said, intents[0], emotion=feeling, intents=intents)
        return AIReply("Lost myself in my own circuits. Try again?", error=True)
