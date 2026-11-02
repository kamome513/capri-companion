"""Capri on your Discord profile: "Playing Capri" (Discord Rich Presence).

Talks to the Discord app on this PC through its local connection (a named pipe on Windows, a socket on
Linux - including Flatpak / Snap Discord). No login, no internet, no token: Discord itself shows the
activity to your friends, and its own setting (User Settings -> Activity Privacy -> "Share your detected
activities with others") still decides who sees it. Turn it off in Capri: Settings -> PC & chat.

What's shown: that Capri is open and for how long, plus what she's doing with you -
* "Plugged in" on your desktop,
* "Vibing to music" while music plays (never which song),
* "Drone mode" / "Hiding".
While you're in a game she steps aside (clears her status): Discord's member list / DMs show only one
"Playing ..." line and would pick hers over your game's. She's back when the game closes.
Never what you say to her or your other apps. Her picture is animated (a GIF from Capri's GitHub page -
Discord shows GIFs from a link, not uploaded ones), with a small animated badge for music.

Discord needs an Application ID (from discord.com/developers/applications): APP_ID below.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
import sys
import threading
import time
import uuid
from typing import Callable


log = logging.getLogger("capri")

APP_ID = "1566821023926452306"                    # Capri's Discord application (its name, "Capri", is what Discord shows)
PAGE = "https://github.com/kamome513/capri-companion"
INVITE = "https://discord.gg/FBxdDSCaA7"    # Capri's Discord server: the "Join her Discord" button
ART = "https://raw.githubusercontent.com/kamome513/capri-companion/main/assets/discord/"   # her animated pictures
ART_VERSION = "2"              # bump when the pictures change: Discord keeps a copy of each link for a while


def art(name: str) -> str:
    return f"{ART}{name}?v={ART_VERSION}"
OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
RETRY_SECONDS = 20.0           # Discord closed / not running: look again this often
MIN_GAP = 4.5                  # Discord allows 5 activity updates per 20 s


def socket_paths(env: dict | None = None) -> list[str]:
    """Where Discord listens on Linux (normal, Flatpak, Snap, Vesktop), discord-ipc-0..9 each."""
    env = os.environ if env is None else env
    bases = [env.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")] + ["/tmp"]
    subs = ["", "app/com.discordapp.Discord", "app/com.discordapp.DiscordCanary", "snap.discord",
            "snap.discord-canary", ".flatpak/dev.vencord.Vesktop/xdg-run", "app/dev.vencord.Vesktop"]
    out = []
    for base in bases:
        if not base:
            continue
        for sub in subs:
            for i in range(10):
                path = os.path.join(base, sub, f"discord-ipc-{i}")
                if path not in out:
                    out.append(path)
    return out


class _Pipe:
    """Windows: Discord's named pipe, opened like a file."""

    def __init__(self, handle) -> None:
        self.h = handle

    def send(self, data: bytes) -> None:
        self.h.write(data)
        self.h.flush()

    def recv(self, n: int) -> bytes:
        return self.h.read(n)

    def close(self) -> None:
        self.h.close()


class _Sock:
    def __init__(self, s: socket.socket) -> None:
        self.s = s

    def send(self, data: bytes) -> None:
        self.s.sendall(data)

    def recv(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise OSError("Discord closed the connection")
            buf += chunk
        return buf

    def close(self) -> None:
        self.s.close()


def connect_to_discord(paths: list[str] | None = None):
    """The Discord app's local connection, or None if Discord isn't running."""
    if sys.platform == "win32":
        for i in range(10):
            try:
                return _Pipe(open(rf"\\?\pipe\discord-ipc-{i}", "r+b", buffering=0))
            except OSError:
                continue
        return None
    for path in paths if paths is not None else socket_paths():
        if not os.path.exists(path):
            continue
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5.0)
        try:
            s.connect(path)
            return _Sock(s)
        except OSError:
            s.close()
    return None


def frame(op: int, payload: dict) -> bytes:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", op, len(data)) + data


def read_frame(conn) -> tuple[int, dict]:
    op, length = struct.unpack("<II", conn.recv(8))
    return op, json.loads(conn.recv(length).decode("utf-8") or "{}")


def activity(state: str, started: int, invite: str = "", doing: str = "") -> dict:
    """What your friends see under your name: Capri - Plugged in - 0:34, and her buttons.
    state: her look ("desktop" / "drone" / "hidden"); doing: what you're up to ("music" / "")."""
    assets = {"large_image": art("capri.gif"), "large_text": "Capri - a cyberpunk desktop companion"}
    if doing == "music":
        details, line = "Vibing to music", "Headphones on"
        assets.update(small_image=art("music.gif"), small_text="Listening to music")
    else:
        details = "Plugged in"
        line = {"drone": "Drone mode", "hidden": "Hiding"}.get(state, "")
    act = {
        "details": details,
        "timestamps": {"start": started},
        "assets": assets,
        "buttons": [{"label": "Get Capri", "url": PAGE}],
        "instance": False,
    }
    if line:
        act["state"] = line
    if invite.startswith(("https://discord.gg/", "https://discord.com/invite/")):
        act["buttons"].append({"label": "Join her Discord", "url": invite})
    return act


class DiscordPresence:
    """Keeps "Playing Capri" on your Discord profile while she runs (a background thread; never blocks her)."""

    def __init__(self, app_id: str = APP_ID, enabled: Callable[[], bool] = lambda: True,
                 connect: Callable[[], object] = connect_to_discord, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], float] = time.time) -> None:
        self.app_id, self.enabled, self._connect, self.clock = app_id, enabled, connect, clock
        self.started = int(now())
        self.state = "desktop"
        self.doing = ""
        self.conn = None
        self.shown = False                # what Discord shows right now: our activity, or nothing
        self._sent: tuple | None = None
        self._last_send = -1e9
        self._next_try = 0.0
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return bool(self.app_id)

    def start(self) -> None:
        if not self.available or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="capri-discord-presence")
        self._thread.start()

    def set_state(self, state: str) -> None:
        """"desktop" / "drone" / "hidden"."""
        self.state = state
        self._wake.set()

    def set_doing(self, doing: str) -> None:
        """"gaming" / "music" / "" - from StatusWatch. Gaming: she steps aside so your game shows."""
        self.doing = doing
        self._wake.set()

    def refresh(self) -> None:
        """The setting changed: show / clear now."""
        self._next_try = 0.0
        self._wake.set()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        with self._lock:
            if self.conn is not None:
                try:
                    if self.shown:
                        self._send_activity(None)
                    self.conn.send(frame(OP_CLOSE, {}))
                except Exception:
                    pass
                self._drop()

    # -- the work ----------------------------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception as exc:                    # Discord quit / restarted: start over later
                log.info("discord presence: %s", exc)
                with self._lock:
                    self._drop()
                self._next_try = self.clock() + RETRY_SECONDS
            self._wake.wait(timeout=RETRY_SECONDS / 2)
            self._wake.clear()

    def step(self) -> None:
        """One go: connect if needed, then make Discord show (or stop showing) the right thing."""
        with self._lock:
            # in a game: off Discord entirely, so your game is what Discord shows ("Playing <your game>")
            want = bool(self.enabled()) and self.doing != "gaming"
            if not want and self.conn is None:
                return
            if self.conn is None:
                if self.clock() < self._next_try:
                    return
                self.conn = self._connect()
                if self.conn is None:                   # Discord isn't running
                    self._next_try = self.clock() + RETRY_SECONDS
                    return
                self._handshake()
            # her look ("drone" / "hidden") only shows when you're not listening to music
            wanted = ("desktop" if self.doing else self.state, self.doing) if want else None
            if wanted == self._sent:
                return
            if self.clock() - self._last_send < MIN_GAP:
                self._wake.set()                         # rate limit: next time round
                time.sleep(0.5)
                return
            if want:
                state, doing = wanted
                self._send_activity(activity(state, self.started, INVITE, doing))
            else:
                self._send_activity(None)
            self._sent = wanted
            self.shown = want
            if not want:
                self.conn.send(frame(OP_CLOSE, {}))
                self._drop()

    def _handshake(self) -> None:
        self.conn.send(frame(OP_HANDSHAKE, {"v": 1, "client_id": self.app_id}))
        op, data = read_frame(self.conn)
        if op == OP_CLOSE or data.get("evt") == "ERROR":
            raise OSError(f"Discord said no: {data.get('message') or data.get('data', {}).get('message', data)}")
        log.info("discord presence: connected to %s", (data.get("data") or {}).get("user", {}).get("username", "Discord"))
        self._sent = None

    def _send_activity(self, act: dict | None) -> None:
        self.conn.send(frame(OP_FRAME, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": act},
                                        "nonce": str(uuid.uuid4())}))
        op, data = read_frame(self.conn)
        self._last_send = self.clock()
        if op == OP_CLOSE or data.get("evt") == "ERROR":
            raise OSError(f"Discord refused the activity: {data.get('data', data)}")

    def _drop(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None
        self._sent = None
        self.shown = False
