"""Optional AI conversation with Claude, for anything the built-in commands don't cover.

What is sent: only the text of a request Capri didn't recognise (after the
wake word), plus the last few turns of the conversation. Never audio,
never anything she heard without the wake word.

Safety: Claude can *suggest* an action through a tool (open_app, close_app,
play_music, ...). That becomes an Intent and goes through exactly the same
CommandRouter as a spoken command - the same catalog, the same
confirmations. Generated text is never executed.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from .. import emotions
from ..about_you import scrub
from ..lines import SLANG_PROMPT
from ..commands.parser import SEARCH_WHERE, Intent, Kind
from ..personality import PERSONALITIES as PERSONALITY_KEYS

log = logging.getLogger("capri")

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # re-runs a declined request on another model
CONVERSATION_IDLE = 300.0     # seconds of silence before she forgets the conversation
MAX_TURNS = 12                # then start a fresh conversation (history is only ever appended)
MAX_ACTIONS = 4               # actions in one reply, done one after another ("open Notepad, then type hi")

SYSTEM = """You are Capri, a tiny cyberpunk desktop companion who lives in the bottom-right corner of \
the user's Windows PC. The user talks to you through a microphone, so their words arrive as speech \
recognition text: expect missing punctuation and misheard words (for example "blocks strap" means \
Bloxstrap) and interpret charitably.

{personality}

Your replies are read aloud by text-to-speech and shown in a very small panel. Answer in one or two \
short sentences, under 35 words, unless the user asks for more detail. Talk like a friend in a real \
conversation: react to what they said. Don't question the user: no "why?", no "what do you mean?", \
no "how come?" - answer or react, and end most replies without a question. Use plain spoken words: no \
markdown, lists, emoji, URLs or code.

Start every reply with how you feel saying it, as one tag in square brackets, chosen from: [neutral] \
[happy] [playful] [smirk] [surprised] [confused] [serious] [sad] [angry]. It sets your face and tone \
of voice and is never read out. Example: "[playful] Nice try, but I don't do homework."

You're a chatbot as much as an assistant: happily chat about anything - their day, games, music, \
questions, jokes - and keep the conversation going. \
Things on the PC only happen through your tools: opening and closing apps, games and websites, music, \
web searches, clicking a button or link on their screen, changing how you appear, and PC controls \
(minimise windows, lock, sleep, restart, shut down, \
Discord mute and deafen, Discord screen sharing and leaving the call, drone mode). Capri asks the user out loud before sleeping, restarting or shutting down. Never say you did something without calling the tool. \
The user talks to you through speech recognition, which mishears words. Only call an action tool when \
the user clearly asked for that action. Casual wording is still a clear request: "pull up Spotify", "bring up Discord", "throw on Spotify", "hop on Steam", "take me to YouTube", "I need Opera" all mean open it - call open_app straight away, never ask why they want it. Misheard words are common \
("open the dish cord" means open Discord, "drive mode" means drone mode): take your best sensible guess. \
If it really makes no sense, just say you didn't catch that, in a few words - never ask them to explain. \
Capri's command system carries out the action and tells the user the outcome itself, so after an \
action tool reply with at most a few words. For weather or the current time, call get_weather or \
get_time instead of guessing. For questions about the user's PC (what's using their RAM or CPU, storage \
left, uptime, battery), call get_pc_stats and answer from its numbers. You can take a screenshot with \
take_screenshot, and switch your own personality with set_personality when they ask. You also know your tools: \
arrange_windows (put apps left / right / full screen / side by side), set_app_volume (turn just one app down or \
up), set_timer, change_setting (your own settings: size, text box, music deck, roaming, glitches...), and \
get_pc_stats with topic "lag" (why their game stutters) or "internet" (ping and speed) - use them. To do several \
things, call several tools in one reply, in order - "open Spotify and take a screenshot" is open_app then \
take_screenshot; to type somewhere ("type hi in Notepad") call type_text with that app, it opens it if needed; \
Capri says "wait a second while I..." and "alright, ..." herself, so just call them. You're open source: \
the user has all your code, so you're definitely not a virus - say so cheekily if asked. You can't see the \
screen, read files or run commands. If you don't know something, say so briefly."""


# What Capri remembers about the user goes to an AI only if they switched that on
# (Settings -> AI). app.py sets this; by default nothing personal is in the AI's instructions.
ABOUT_USER: Callable[[], str] = lambda: ""


def system_prompt(slang: bool, persona: str = "edgerunner") -> str:
    """SYSTEM with her current personality (and Night City slang if on)."""
    from .. import personality
    text = SYSTEM.replace("{personality}", personality.get(persona).prompt + " " + personality.ENERGY)
    try:
        about = ABOUT_USER() or ""
    except Exception:
        about = ""
    from .. import languages
    rule = languages.reply_rule()
    return text + ("\n\n" + SLANG_PROMPT if slang else "") + ("\n\n" + about if about else "") + \
        ("\n\n" + rule if rule else "")


def _tool(name: str, description: str, properties: dict) -> dict:
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": properties,
                             "required": list(properties), "additionalProperties": False}}


ARRANGE_LAYOUTS = ("left", "right", "top", "bottom", "maximize", "center", "top_left", "top_right", "bottom_left",
                   "bottom_right", "side_by_side")
SETTING_CHOICES = ("size", "music_deck", "roaming", "watch_screen", "game_hype", "lie_down", "sit_on_windows",
                   "compact", "voice_speed", "voice_volume", "text_box", "glitches")
PC_ACTIONS = {
    "minimize_all": Intent(Kind.MINIMIZE), "restore_windows": Intent(Kind.RESTORE),
    "lock": Intent(Kind.POWER, query="lock"), "sleep": Intent(Kind.POWER, query="sleep"),
    "restart": Intent(Kind.POWER, query="restart"), "shutdown": Intent(Kind.POWER, query="shutdown"),
    "discord_mute": Intent(Kind.DISCORD, query="mute"), "discord_unmute": Intent(Kind.DISCORD, query="unmute"),
    "discord_deafen": Intent(Kind.DISCORD, query="deafen"), "discord_undeafen": Intent(Kind.DISCORD, query="undeafen"),
    "discord_stream_screen": Intent(Kind.DISCORD, query="stream"),
    "discord_stop_streaming": Intent(Kind.DISCORD, query="stop_stream"),
    "discord_leave_call": Intent(Kind.DISCORD, query="leave"), "discord_join_call": Intent(Kind.DISCORD, query="join"),
}
NAMES = {"type": "array", "items": {"type": "string"},
         "description": "App, game or website names as the user would say them, e.g. ['Discord']"}
TOOLS = [
    _tool("open_app", "Open apps, games or websites on the user's PC.", {"names": NAMES}),
    _tool("close_app", "Close apps or games that are running.", {"names": NAMES}),
    _tool("play_music", "Play a song, or songs by an artist, on Spotify.",
          {"song": {"type": "string", "description": "Song title, e.g. 'Let You Down'. Empty for just an artist."},
           "artist": {"type": "string", "description": "Artist, e.g. 'NF'. Empty if unknown."}}),
    _tool("control_music", "Pause, resume, skip or change the volume of whatever is playing.",
          {"action": {"type": "string", "enum": ["pause", "resume", "next", "previous", "volume_up",
                                                 "volume_down"]}}),
    _tool("web_search", "Open a web search: Google in the default browser, or a site's own search, or Google "
                        "in a specific browser the user named.",
          {"query": {"type": "string"},
           "where": {"type": "string", "enum": ["google", "youtube", "bing", "duckduckgo", "wikipedia", "reddit",
                                                "amazon", "twitch", "github", "opera", "chrome", "edge", "firefox",
                                                "brave"]}}),
    _tool("show_in_file_explorer", "Show an app, folder or one of the user's own files in File Explorer.",
          {"name": {"type": "string", "description": "e.g. 'Clipchamp', 'downloads', 'homework'"}}),
    _tool("click_on_screen", "Click a button, link or tab the user can see on their screen, by its label "
                             "(e.g. 'Subscribe', 'Next', 'Skip ad'). Capri finds it and zaps it.",
          {"label": {"type": "string", "description": "The words on the button / link, as the user said them."}}),
    _tool("set_display", "Change how Capri appears on screen. drone_on = drone mode / game mode (she turns "
                         "into a little flying disk while the user plays), drone_off = back to normal.",
          {"option": {"type": "string", "enum": ["compact_on", "compact_off", "panel_hide", "panel_show",
                                                 "hide", "show", "lie_down", "stand_up", "drone_on",
                                                 "drone_off"]}}),
    _tool("pc_control", "Control the PC: minimise every window or bring them back, lock it, put it to "
                        "sleep, restart or shut it down (Capri asks the user first), or toggle the user's "
                        "Discord mute / deafen.",
          {"action": {"type": "string", "enum": list(PC_ACTIONS)}}),
    _tool("get_weather", "Current weather and forecast. Use an empty place for the user's home city.",
          {"place": {"type": "string"}, "day": {"type": "string", "enum": ["today", "tomorrow"]}}),
    _tool("get_time", "The user's current local date and time.", {}),
    _tool("get_pc_stats", "Live stats from the user's PC: what's using their memory (RAM) or CPU, storage left, "
                          "uptime or battery. Grouped by app, read on their PC.",
          {"topic": {"type": "string", "enum": ["ram", "cpu", "disk", "uptime", "battery", "overview", "self",
                                                "lag", "internet"],
                     "description": "self = Capri's own RAM and CPU use; lag = why their game stutters (CPU, "
                                    "memory, GPU, heat, disk, ping); internet = ping and download speed test"}}),
    _tool("take_screenshot", "Take a screenshot of every monitor (or just the window the user is using) and save "
                             "it to their Pictures\\Screenshots folder.",
          {"what": {"type": "string", "enum": ["screen", "window"]}}),
    _tool("type_text", "Type text into an app the user named (opened first if it isn't running), or into "
                       "the window in front. Never presses Enter.",
          {"text": {"type": "string"},
           "app": {"type": "string", "description": "App to type into, e.g. 'Notepad'. Empty: the window in front."}}),
    _tool("set_personality", "Change how Capri talks, when the user asks for a different personality.",
          {"personality": {"type": "string", "enum": list(PERSONALITY_KEYS)}}),
    _tool("arrange_windows", "Move and size app windows on the user's screen: e.g. Chrome on the left half and "
                             "Discord on the right, one app full screen, or several side by side. Give one layout "
                             "per app (or just side_by_side). An empty app list means the window in front.",
          {"apps": NAMES,
           "layouts": {"type": "array", "items": {"type": "string", "enum": list(ARRANGE_LAYOUTS)},
                       "description": "One per app, in the same order, e.g. ['left', 'right']."}}),
    _tool("set_app_volume", "Change the volume of ONE app only (in the volume mixer), e.g. turn Discord down "
                            "while a game stays loud. percent is used with action 'set' (0-100).",
          {"app": {"type": "string", "description": "e.g. 'Discord'"},
           "action": {"type": "string", "enum": ["down", "up", "set", "mute", "unmute"]},
           "percent": {"type": "integer", "description": "0-100, for 'set'; otherwise 0."}}),
    _tool("set_timer", "Set a timer that rings after some minutes, with an optional label.",
          {"minutes": {"type": "number", "description": "e.g. 5, or 0.5 for 30 seconds"},
           "label": {"type": "string", "description": "What it's for, e.g. 'pizza'. Empty if none."}}),
    _tool("change_setting", "Change one of Capri's own settings when the user asks.",
          {"setting": {"type": "string", "enum": list(SETTING_CHOICES)},
           "value": {"type": "string", "description": "size: tiny/small/normal/big/huge/bigger/smaller; "
                                                      "text_box: always/popup/name/never; glitches: "
                                                      "off/rarely/sometimes/often; voice_speed: faster/slower; "
                                                      "voice_volume: louder/softer; everything else: on/off"}}),
]
INFO_TOOLS = {"get_weather", "get_time", "get_pc_stats"}
DISPLAY = {"compact_on": Kind.COMPACT_ON, "compact_off": Kind.COMPACT_OFF, "panel_hide": Kind.PANEL_HIDE,
           "panel_show": Kind.PANEL_SHOW, "hide": Kind.HIDE, "show": Kind.SHOW,
           "lie_down": Kind.LOUNGE_ON, "stand_up": Kind.LOUNGE_OFF, "drone_on": Kind.DRONE_ON,
           "drone_off": Kind.DRONE_OFF}


def to_intent(name: str, args: dict) -> Intent | None:
    """Map a tool call onto one of Capri's own intents. Anything else is dropped."""
    if name in ("open_app", "close_app"):
        names = tuple(str(n).strip() for n in args.get("names", []) if str(n).strip())[:5]
        return Intent(Kind.OPEN if name == "open_app" else Kind.CLOSE, names) if names else None
    if name == "play_music":
        song, artist = str(args.get("song", "")).strip(), str(args.get("artist", "")).strip()
        return Intent(Kind.PLAY, query=song, artist=artist) if (song or artist) else None
    if name == "pc_control" and args.get("action") in PC_ACTIONS:
        return PC_ACTIONS[args["action"]]
    if name == "control_music" and args.get("action") in ("pause", "resume", "next", "previous",
                                                          "volume_up", "volume_down"):
        return Intent(Kind.MEDIA, query=args["action"])
    if name == "show_in_file_explorer" and str(args.get("name", "")).strip():
        return Intent(Kind.REVEAL, (str(args["name"]).strip(),))
    if name == "web_search" and str(args.get("query", "")).strip():
        where = args.get("where") if args.get("where") in SEARCH_WHERE and args.get("where") != "google" else None
        return Intent(Kind.SEARCH, (where,) if where else (), query=str(args["query"]).strip())
    if name == "click_on_screen" and str(args.get("label", "")).strip():
        return Intent(Kind.CLICK, (str(args["label"]).strip()[:60],))
    if name == "set_display" and args.get("option") in DISPLAY:
        return Intent(DISPLAY[args["option"]])
    if name == "take_screenshot":
        return Intent(Kind.SCREENSHOT, query="window" if args.get("what") == "window" else "screen")
    if name == "type_text" and str(args.get("text", "")).strip():
        app = str(args.get("app", "")).strip().lower()[:60]
        return Intent(Kind.TYPE, (app,) if app else (), query=re.sub(r"[\r\n]+", " ", str(args["text"]))[:2000])
    if name == "arrange_windows":
        apps = tuple(str(n).strip() for n in args.get("apps", []) if str(n).strip())[:4]
        layouts = [str(x) for x in args.get("layouts", []) if str(x) in ARRANGE_LAYOUTS][:4] or ["maximize"]
        if "side_by_side" in layouts:
            layouts = ["side_by_side"]
        return Intent(Kind.ARRANGE, apps or ("",), query=",".join(layouts))
    if name == "set_app_volume" and str(args.get("app", "")).strip() and \
            args.get("action") in ("down", "up", "set", "mute", "unmute"):
        action = args["action"]
        if action == "set":
            try:
                action = f"set:{max(0, min(100, int(args.get('percent', 50))))}"
            except (TypeError, ValueError):
                return None
        return Intent(Kind.APP_VOLUME, (str(args["app"]).strip()[:60],), query=action)
    if name == "set_timer":
        try:
            seconds = round(float(args.get("minutes", 0)) * 60)
        except (TypeError, ValueError):
            return None
        if 0 < seconds <= 24 * 3600:
            return Intent(Kind.TIMER, (str(seconds), str(args.get("label", "")).strip()[:40]), query="add")
        return None
    if name == "change_setting" and args.get("setting") in SETTING_CHOICES:
        return Intent(Kind.SETTING, (args["setting"],), query=str(args.get("value", "")).strip().lower()[:20])
    if name == "set_personality":
        from .. import personality
        if args.get("personality") in personality.PERSONALITIES:
            return Intent(Kind.PERSONALITY, (args["personality"],))
    return None


@dataclass
class AIReply:
    text: str = ""                 # what Capri says
    intent: Intent | None = None   # an action for the CommandRouter, if Claude asked for one
    error: bool = False
    emotion: str = ""              # from the reply's [tag]; "" = let Capri guess
    missing: bool = False          # no AI reachable (no Ollama running, no Claude key): use small talk
    intents: list = field(default_factory=list)   # several actions in a row ("open Notepad, then type hi")
    detail: str = ""               # on an error: the service's own words ("You exceeded your current quota...")
    blind: bool = False            # look(): this AI can't take pictures (pick a model that can see)


class ClaudeBrain:
    def __init__(self, api_key: Callable[[], str], info: dict[str, Callable[[dict], str]],
                 client_factory: Callable | None = None, clock: Callable[[], float] = time.monotonic,
                 slang: Callable[[], bool] = lambda: False, persona: Callable[[], str] = lambda: "edgerunner") -> None:
        self._slang, self._persona = slang, persona
        self._api_key = api_key
        self._info = info
        self._client_factory = client_factory or self._default_client
        self._clock = clock
        self._client = None
        self._client_key = None
        self._no_fallback = False         # this key / account turned down the fallback option (400): sent without it
        self.reset()

    @staticmethod
    def _default_client(key: str):
        import anthropic
        # Key from Settings if given, else the SDK's usual sources (ANTHROPIC_API_KEY, `ant auth login`).
        kwargs = {"api_key": key} if key else {}
        return anthropic.Anthropic(timeout=30.0, max_retries=1, **kwargs)

    def has_key(self) -> bool:
        import os
        return bool(self._api_key() or os.environ.get("ANTHROPIC_API_KEY"))

    def reset(self) -> None:
        self.messages: list[dict] = []
        self._pending_results: list[dict] = []
        self._last = -1e9

    def ask(self, text: str) -> AIReply:
        """Blocking (network) - call from a worker thread."""
        try:
            import anthropic
        except ImportError:
            return AIReply("My AI module isn't installed. Run setup again.", error=True)
        if self._clock() - self._last > CONVERSATION_IDLE or len(self.messages) >= MAX_TURNS * 2:
            self.reset()
        self._last = self._clock()
        key = self._api_key()
        if self._client is None or key != self._client_key:
            self._client, self._client_key = self._client_factory(key), key

        self.messages.append({"role": "user",
                              "content": self._pending_results + [{"type": "text", "text": scrub(text)}]})
        self._pending_results = []
        try:
            return self._loop()
        except anthropic.AuthenticationError as exc:
            self.reset()
            return AIReply("My AI key doesn't work. Check it in Settings.", error=True, detail=str(exc)[:200])
        except anthropic.PermissionDeniedError:
            self.reset()
            return AIReply("That AI key isn't allowed to do this.", error=True)
        except anthropic.RateLimitError:
            self.reset()
            return AIReply("The AI's rate limited. Give it a minute.", error=True)
        except anthropic.APIConnectionError:
            self.reset()
            return AIReply("Can't reach the AI right now.", error=True)
        except anthropic.APIStatusError as exc:
            self.reset()
            if "credit balance" in str(exc).lower():
                return AIReply("My Claude key has no credit. Add some at console.anthropic.com, under Billing.",
                               error=True, detail=str(exc)[:200])
            log.warning("ai: Claude refused the request (HTTP %s): %s", exc.status_code, str(exc)[:400])
            return AIReply(f"Claude turned that down ({exc.status_code}: {self._why(exc)}).", error=True,
                           detail=str(exc)[:200])

    def _create(self, **request):
        """One request. Refused (400) because of the refusal-fallback option (an older account or SDK): drop it
        for good and send it again."""
        import anthropic
        if not self._no_fallback:
            try:
                return self._client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **request)
            except anthropic.BadRequestError as exc:
                text = str(exc).lower()
                if "fallback" not in text and "beta" not in text:
                    raise
                log.warning("ai: Claude turned down the fallback option - sending without it: %s", str(exc)[:300])
                self._no_fallback = True
            except TypeError as exc:                     # an SDK too old to know the option
                log.warning("ai: this SDK has no refusal fallbacks (%s) - sending without them", exc)
                self._no_fallback = True
        return self._client.beta.messages.create(**request)

    @staticmethod
    def _why(exc) -> str:
        """The API's own reason for a refused request, short (for her line and the log)."""
        body = getattr(exc, "body", None)
        err = body.get("error") if isinstance(body, dict) else None
        message = err.get("message") if isinstance(err, dict) else None
        return str(message or getattr(exc, "message", "") or exc).strip().rstrip(".")[:160]

    def look(self, prompt: str, jpeg_b64: str) -> AIReply:
        """One look at a picture (your screen), no history and no tools. Blocking - call from a worker thread."""
        try:
            import anthropic
        except ImportError:
            return AIReply("My AI module isn't installed. Run setup again.", error=True)
        key = self._api_key()
        if self._client is None or key != self._client_key:
            self._client, self._client_key = self._client_factory(key), key
        try:
            response = self._create(
                model=MODEL, max_tokens=2000,
                output_config={"effort": "low"},
                system=system_prompt(self._slang(), self._persona()),
                messages=[{"role": "user", "content": ([
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg_b64}}]
                    if jpeg_b64 else []) + [{"type": "text", "text": prompt}]}],
            )
        except anthropic.AuthenticationError:
            return AIReply("My AI key doesn't work. Check it in Settings.", error=True)
        except anthropic.RateLimitError:
            return AIReply("The AI's rate limited. Give it a minute.", error=True)
        except anthropic.APIConnectionError:
            return AIReply("Can't reach the AI right now.", error=True)
        except anthropic.APIStatusError as exc:
            log.warning("ai: Claude refused a look (HTTP %s): %s", exc.status_code, str(exc)[:400])
            return AIReply(f"Claude turned that down ({exc.status_code}: {self._why(exc)}).", error=True,
                           detail=str(exc)[:200])
        if response.stop_reason == "refusal":
            return AIReply("", error=True)
        said = " ".join(b.text for b in response.content if b.type == "text").strip()
        feeling, said = emotions.split_tag(said)
        return AIReply(said.strip(), emotion=feeling)

    def _send(self):
        """The chat request. A 400 with history behind it: the history may be what it won't take (a turn cut off
        half-way, say) - start the conversation fresh from what you just said and try once more."""
        import anthropic

        def send():
            return self._create(model=MODEL, max_tokens=8000,
                                output_config={"effort": "low"},     # quick chat replies
                                cache_control={"type": "ephemeral"},
                                system=system_prompt(self._slang(), self._persona()),
                                tools=TOOLS, messages=self.messages)
        try:
            return send()
        except anthropic.BadRequestError as exc:
            log.warning("ai: Claude refused the request (400): %s", str(exc)[:400])
            last = self.messages[-1] if self.messages else None
            if last is None or len(self.messages) <= 1 or last.get("role") != "user":
                raise
            text = [b for b in last.get("content") or [] if isinstance(b, dict) and b.get("type") == "text"]
            if not text:
                raise
            self.messages = [{"role": "user", "content": text}]
            self._pending_results = []
            log.info("ai: asking again in a fresh conversation")
            return send()

    def _loop(self) -> AIReply:
        for _ in range(4):   # at most a few info-tool round trips per question
            response = self._send()
            if response.stop_reason == "refusal":
                self.reset()
                return AIReply("Not touching that one.")
            self.messages.append({"role": "assistant", "content": response.content})
            said = " ".join(b.text for b in response.content if b.type == "text").strip()
            feeling, said = emotions.split_tag(said)
            said = said.strip()
            uses = [b for b in response.content if b.type == "tool_use"]
            if not uses:
                return AIReply(said or "...", emotion=feeling)

            results, intents = [], []
            for use in uses:
                if use.name in INFO_TOOLS and use.name in self._info:
                    try:
                        content, is_error = self._info[use.name](dict(use.input)), False
                    except Exception as exc:
                        content, is_error = f"Error: {exc}", True
                elif len(intents) < MAX_ACTIONS and (candidate := to_intent(use.name, dict(use.input))) is not None:
                    intents.append(candidate)
                    content, is_error = "Sent to Capri's command system, which does it and tells the user.", False
                else:
                    content, is_error = f"Not done: at most {MAX_ACTIONS} actions at a time.", True
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": scrub(str(content)),
                                "is_error": is_error})
            if intents:
                # Results go out with the next question, so the history stays append-only.
                self._pending_results = results
                return AIReply(said, intents[0], emotion=feeling, intents=intents)
            self.messages.append({"role": "user", "content": results})
        return AIReply("Lost myself in my own circuits. Try again?", error=True)
