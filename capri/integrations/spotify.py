"""Spotify: play a song by name, pause/skip, "what's playing".

Spotify only lets apps *start playback* for Premium accounts, through its
Web API. One-time setup (Settings -> Assistant -> Spotify):
  1. Create a free app at https://developer.spotify.com/dashboard
  2. Add the redirect URI  http://127.0.0.1:8973/callback
  3. Paste its Client ID into Capri and press Connect, then approve in the browser.
Sign-in uses PKCE: there is no client secret, and the login happens on
Spotify's own page. Capri stores only the access/refresh token, in
%LOCALAPPDATA%\\Capri\\secrets.json.
"""

from __future__ import annotations

import base64
import hashlib
import secrets as pysecrets
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

from .. import secrets
from . import http

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
REDIRECT_PORT = 8973
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"


class SpotifyError(Exception):
    pass


class NotConnected(SpotifyError):
    pass


class PremiumRequired(SpotifyError):
    pass


class NoDevice(SpotifyError):
    pass


@dataclass
class Track:
    name: str
    artist: str
    uri: str


class Spotify:
    def __init__(self, client_id: Callable[[], str], fetch: Callable = http.request,
                 open_url: Callable[[str], None] | None = None,
                 launch_app: Callable[[], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._client_id = client_id
        self._fetch = fetch
        self._open_url = open_url
        self._launch_app = launch_app
        self._sleep = sleep

    # -- auth ---------------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return bool(secrets.get("spotify_refresh_token"))

    def disconnect(self) -> None:
        secrets.delete("spotify_access_token", "spotify_refresh_token", "spotify_expires_at")

    def connect(self, timeout: float = 180.0) -> None:
        """Open Spotify's login page and wait for the redirect back. Blocking (run off the UI thread)."""
        client_id = self._client_id().strip()
        if not client_id:
            raise SpotifyError("Paste your Spotify app's Client ID first.")
        verifier = pysecrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = pysecrets.token_urlsafe(16)
        result: dict[str, str] = {}
        done = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server API
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if urllib.parse.urlparse(self.path).path == "/callback":
                    result.update({k: v[0] for k, v in query.items()})
                    done.set()
                ok = "code" in result and result.get("state") == state
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                msg = "Capri is connected to Spotify. You can close this tab." if ok else \
                      "Spotify sign-in didn't complete. You can close this tab and try again."
                self.wfile.write(f"<html><body style='background:#0a0a0c;color:#3fe06e;font-family:monospace;"
                                 f"padding:40px'>{msg}</body></html>".encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
        server.timeout = 1.0
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256", "code_challenge": challenge, "scope": SCOPES, "state": state})
        try:
            if self._open_url:
                self._open_url(url)
            deadline = time.monotonic() + timeout
            while not done.is_set() and time.monotonic() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if not done.is_set():
            raise SpotifyError("Spotify sign-in timed out.")
        if result.get("state") != state or "code" not in result:
            raise SpotifyError(f"Spotify sign-in failed: {result.get('error', 'no code returned')}.")
        token = self._fetch("POST", TOKEN_URL, data={
            "grant_type": "authorization_code", "code": result["code"], "redirect_uri": REDIRECT_URI,
            "client_id": client_id, "code_verifier": verifier})
        self._store(token)

    def _store(self, token: dict) -> None:
        values = {"spotify_access_token": token["access_token"],
                  "spotify_expires_at": str(time.time() + int(token.get("expires_in", 3600)) - 60)}
        if token.get("refresh_token"):
            values["spotify_refresh_token"] = token["refresh_token"]
        secrets.set_many(values)

    def _access_token(self, force_refresh: bool = False) -> str:
        refresh = secrets.get("spotify_refresh_token")
        if not refresh:
            raise NotConnected("Spotify isn't connected.")
        token = secrets.get("spotify_access_token")
        if token and not force_refresh and time.time() < float(secrets.get("spotify_expires_at") or 0):
            return token
        try:
            new = self._fetch("POST", TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": refresh,
                                                      "client_id": self._client_id().strip()})
        except http.HttpError as exc:
            if exc.status in (400, 401):
                self.disconnect()
                raise NotConnected("Spotify sign-in expired. Connect again in Settings.") from exc
            raise SpotifyError("Spotify is unreachable.") from exc
        self._store(new)
        return new["access_token"]

    def _api(self, method: str, path: str, params: dict | None = None, body=None):
        for attempt in (0, 1):
            headers = {"Authorization": f"Bearer {self._access_token(force_refresh=attempt == 1)}"}
            try:
                return self._fetch(method, API + path, params=params, json_body=body, headers=headers)
            except http.HttpError as exc:
                if exc.status == 401 and attempt == 0:
                    continue
                err = exc.json().get("error")
                reason = err.get("reason", "") if isinstance(err, dict) else ""
                if exc.status == 403 and (reason == "PREMIUM_REQUIRED" or "premium" in exc.body.lower()):
                    raise PremiumRequired("Playing a specific song needs Spotify Premium.") from exc
                if exc.status == 404 and (reason == "NO_ACTIVE_DEVICE" or "device" in exc.body.lower()):
                    raise NoDevice("Spotify isn't open anywhere.") from exc
                raise SpotifyError(f"Spotify said no ({exc.status}).") from exc
            except OSError as exc:
                raise SpotifyError("Spotify is unreachable.") from exc

    # -- playback ---------------------------------------------------------------------------
    def _tracks(self, q: str, limit: int) -> list[Track]:
        data = self._api("GET", "/search", params={"q": q, "type": "track", "limit": limit}) or {}
        return [Track(t["name"], ", ".join(a["name"] for a in t.get("artists", [])[:2]), t["uri"])
                for t in (data.get("tracks") or {}).get("items") or []]

    def search(self, query: str, artist: str = "") -> Track | None:
        """Best track for what was said. With an artist ("let you down" by "nf") it asks Spotify
        for exactly that, then also searches loosely - speech recognition spells names its own
        way ("the weekend") - and keeps whichever result sounds most like the request."""
        if not artist:
            found = self._tracks(query, 8)                # a few, so the plain song beats "(Live)" and remixes
            return max(enumerate(found), key=lambda ic: (_match(ic[1], query, ""), -ic[0]))[1] if found else None
        exact = f"track:{query} artist:{artist}" if query else f"artist:{artist}"
        candidates = self._tracks(exact, 5) + self._tracks(f"{query} {artist}".strip(), 10)
        if not candidates:
            return self.search(f"{query} by {artist}") if query else None   # "stand by me"
        return max(enumerate(candidates), key=lambda ic: (_match(ic[1], query, artist), -ic[0]))[1]

    def _device(self) -> str:
        for attempt in range(24):                     # ~12 s for a freshly launched app to appear
            devices = (self._api("GET", "/me/player/devices") or {}).get("devices") or []
            if devices:
                pick = next((d for d in devices if d.get("is_active")), None) or \
                       next((d for d in devices if d.get("type") == "Computer"), None) or devices[0]
                return pick["id"]
            if attempt == 0 and self._launch_app:
                self._launch_app()                    # open the Spotify app, then wait for it
            self._sleep(0.5)
        raise NoDevice("Spotify isn't open anywhere.")

    def play(self, query: str, artist: str = "") -> Track:
        track = self.search(query, artist)
        if track is None:
            wanted = f"{query} by {artist}" if query and artist else (query or artist)
            raise SpotifyError(f"Couldn't find {wanted} on Spotify.")
        device = self._device()
        self._api("PUT", "/me/player/play", params={"device_id": device}, body={"uris": [track.uri]})
        return track

    def pause(self) -> None:
        self._api("PUT", "/me/player/pause")

    def resume(self) -> None:
        self._api("PUT", "/me/player/play")

    def next(self) -> None:
        self._api("POST", "/me/player/next")

    def previous(self) -> None:
        self._api("POST", "/me/player/previous")

    def now_playing(self) -> Track | None:
        data = self._api("GET", "/me/player/currently-playing")
        if not data or not data.get("item"):
            return None
        t = data["item"]
        return Track(t["name"], ", ".join(a["name"] for a in t.get("artists", [])[:2]), t.get("uri", ""))


def _match(track: Track, query: str, artist: str) -> float:
    """How well a result fits "<query> by <artist>", 0..2 (title + artist, by sound or initials), less a
    bit for a special version you didn't ask for ("Chicago (Original Version)" when you said "Chicago")."""
    from ..commands.fuzzy import similarity
    from .spotify_app import artist_score, version_penalty
    title = similarity(query, track.name) if query else 1.0
    return title + artist_score(track.artist, artist) - version_penalty(track.name, query)
