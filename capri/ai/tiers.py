"""Her intelligence: Low / Medium / High (2.3.8) - one setting that picks the model on whatever AI you use.

* Low    - the quickest, cheapest model (or the small one on this PC). Fine for chat and commands.
* Medium - a capable model that can see: free with a Google Gemini or NVIDIA key. Good at games and your screen.
* High   - the smartest model your AI has. Slower, and on paid AIs it costs more per message.

A model you typed yourself (Settings -> Assistant -> Model) always wins. If a service has renamed a model, she
switches to the closest one it has (OpenAIBrain._swap_model), so an old name here can't break her.
"""

from __future__ import annotations

LEVELS = ("low", "medium", "high")
DEFAULT = "medium"
LABELS = {"low": "Low - quick (or the small AI on this PC)",
          "medium": "Medium - smart, sees your screen (free key)",
          "high": "High - the smartest (slower)"}
SHORT = {"low": "Low", "medium": "Medium", "high": "High"}

# The model she chats with, per service and level
CHAT = {
    "gemini": {"low": "gemini-flash-lite-latest", "medium": "gemini-flash-latest", "high": "gemini-pro-latest"},
    "nvidia": {"low": "meta/llama-3.1-8b-instruct", "medium": "meta/llama-3.3-70b-instruct",
               "high": "meta/llama-3.1-405b-instruct"},
    "openai": {"low": "gpt-5-nano", "medium": "gpt-5-mini", "high": "gpt-5"},
    "groq": {"low": "llama-3.1-8b-instant", "medium": "meta-llama/llama-4-scout-17b-16e-instruct",
             "high": "meta-llama/llama-4-maverick-17b-128e-instruct"},
    "openrouter": {"low": "openai/gpt-5-nano", "medium": "google/gemini-2.5-flash", "high": "google/gemini-2.5-pro"},
    "deepseek": {"low": "deepseek-chat", "medium": "deepseek-chat", "high": "deepseek-reasoner"},
    "mistral": {"low": "mistral-small-latest", "medium": "mistral-medium-latest", "high": "mistral-large-latest"},
    "xai": {"low": "grok-3-mini", "medium": "grok-3-mini", "high": "grok-4"},
}
# The model she looks with (your screen, playing games), per service and level - all of these can see
VISION = {
    "gemini": {"low": "gemini-flash-lite-latest", "medium": "gemini-flash-latest", "high": "gemini-pro-latest"},
    "nvidia": {"low": "meta/llama-3.2-11b-vision-instruct", "medium": "meta/llama-4-maverick-17b-128e-instruct",
               "high": "meta/llama-3.2-90b-vision-instruct"},
    "openai": {"low": "gpt-5-nano", "medium": "gpt-5-mini", "high": "gpt-5"},
    "groq": {"low": "meta-llama/llama-4-scout-17b-16e-instruct", "medium": "meta-llama/llama-4-scout-17b-16e-instruct",
             "high": "meta-llama/llama-4-maverick-17b-128e-instruct"},
    "openrouter": {"low": "openai/gpt-5-nano", "medium": "google/gemini-2.5-flash", "high": "google/gemini-2.5-pro"},
    "mistral": {"low": "pixtral-12b-2409", "medium": "mistral-medium-latest", "high": "pixtral-large-latest"},
    "xai": {"low": "grok-4", "medium": "grok-4", "high": "grok-4"},
}
CLAUDE = {"low": "claude-haiku-5-5", "medium": "claude-sonnet-5-5", "high": "claude-opus-5-5"}
# On this PC (Ollama): the first of these you have downloaded
LOCAL = {"low": ("llama3.2", "llama3.2:1b", "gemma3:1b"),
         "medium": ("gemma3:4b", "gemma3", "qwen2.5vl:7b", "llava", "llama3.2"),
         "high": ("gemma3:12b", "gemma3:27b", "qwen2.5vl:7b", "llama3.1:8b", "gemma3:4b", "gemma3", "llama3.2")}
LOCAL_DOWNLOAD = {"low": "llama3.2", "medium": "gemma3:4b", "high": "gemma3:12b"}   # what "set up your brain" gets
FREE_KEY_URL = "https://aistudio.google.com/apikey"      # Google Gemini: free, can see - Medium and High


def level(value: str | None) -> str:
    return value if value in LEVELS else DEFAULT


def chat_model(preset: str, value: str | None) -> str:
    return CHAT.get(preset or "", {}).get(level(value), "")


def vision_model(preset: str, value: str | None) -> str:
    return VISION.get(preset or "", {}).get(level(value), "")


def claude_model(value: str | None) -> str:
    return CLAUDE[level(value)]


def local_model(value: str | None, downloaded: list[str]) -> str:
    """The best model you've downloaded for this level ("" if none of them)."""
    have = {n: n for n in downloaded}
    have.update({n.split(":")[0]: n for n in downloaded if n.endswith(":latest")})
    for name in LOCAL[level(value)]:
        if name in have:
            return have[name]
    return ""


def find(text: str) -> str:
    """'high' / 'max' / 'smartest' / 'low' / 'medium'... -> a level, or ""."""
    t = (text or "").lower()
    if any(w in t for w in ("high", "max", "maximum", "smartest", "best", "big brain", "full", "genius")):
        return "high"
    if any(w in t for w in ("medium", "mid", "middle", "normal", "default", "balanced")):
        return "medium"
    if any(w in t for w in ("low", "min", "minimum", "basic", "dumb", "quick", "fast", "cheap", "offline", "small")):
        return "low"
    return ""


def has_cloud_key() -> bool:
    from .. import secrets
    return bool((secrets.get("openai_api_key") or "").strip() or (secrets.get("anthropic_api_key") or "").strip())


def apply(settings, value: str) -> tuple[str, bool]:
    """Set her intelligence. Returns (what she says, whether you need a free key first). A model you typed
    yourself is cleared, so the level really takes effect. Medium / High with no AI key: Google Gemini is picked
    and she asks you for its free key."""
    value = level(value)
    settings.intelligence = value
    settings.openai_model = ""
    settings.ai_enabled = True
    needs_key = value != "low" and not has_cloud_key()
    if needs_key:
        settings.openai_preset, settings.ai_provider = "gemini", "openai"
    settings.save()
    if needs_key:
        return (f"Intelligence {SHORT[value]}! That needs a free Google key: I opened the page - click Create API "
                f"key, copy it, then paste it in my Settings, Assistant, API key. Google Gemini is already picked."), True
    words = {"low": "Low intelligence: quick and light. Ask for Medium when you want me sharp again.",
             "medium": "Medium intelligence: smart, and I can see your screen properly.",
             "high": "High intelligence: my biggest brain. A little slower, a lot smarter."}
    return words[value], False


def describe(settings) -> str:
    value = level(getattr(settings, "intelligence", DEFAULT))
    return f"My intelligence is on {SHORT[value]}. Say “set your intelligence to high” (or low, or medium)."
