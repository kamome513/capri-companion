"""Finding the song you asked for on your music app, so she can play it - not just open a
search page and leave the clicking to you.

* YouTube Music: its own search (songs only), the same request music.youtube.com makes; backup:
  the top video of a normal YouTube search. music.youtube.com/watch?v=<id> starts playing by itself.
* Deezer, Apple Music: their public search APIs (no account needed) give the song's own page.
* Bandcamp: the first track in its search results.
* SoundCloud, Tidal, Amazon Music: no public search without an account - their search page.

The router then opens the page and presses its Play button (router._press_play). Only checked
links on that service's own site are ever opened - nothing from the web becomes a command.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Callable

from .http import BROWSER_UA, get_text

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
MUSIC_SEARCH = "https://music.youtube.com/youtubei/v1/search?prettyPrint=false"
SONGS_ONLY = "EgWKAQIIAWoKEAkQBRAKEAMQBA%3D%3D"      # YouTube Music's "Songs" filter
MUSIC_CLIENT = {"clientName": "WEB_REMIX", "clientVersion": "1.20240918.01.00", "hl": "en", "gl": "US"}
RESULTS = "https://www.youtube.com/results?search_query={}"
MUSIC_WATCH = "https://music.youtube.com/watch?v={}"
WATCH = "https://www.youtube.com/watch?v={}"


def _post_json(url: str, body: dict, timeout: float = 8.0) -> str:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"User-Agent": BROWSER_UA, "Content-Type": "application/json",
                                          "Origin": "https://music.youtube.com", "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def song_id_from_music(reply: str) -> str | None:
    """The first song in a YouTube Music search reply."""
    m = re.search(r'"musicResponsiveListItemRenderer".*?"videoId":\s*"([A-Za-z0-9_-]{11})"', reply, re.S)
    if m is None:
        m = re.search(r'"videoId":\s*"([A-Za-z0-9_-]{11})"', reply)
    return m.group(1) if m else None


def video_id_from_results(page: str) -> str | None:
    """The first real video on a YouTube results page (not an ad, not a Short)."""
    m = re.search(r'"videoRenderer":\s*\{\s*"videoId":\s*"([A-Za-z0-9_-]{11})"', page)
    return m.group(1) if m else None


def find_song(query: str, post: Callable[[str, dict], str] = _post_json,
              fetch: Callable[[str], str] = get_text) -> str | None:
    """YouTube Music first, then a YouTube search. None = couldn't find it (or offline)."""
    try:
        found = song_id_from_music(post(MUSIC_SEARCH, {"context": {"client": MUSIC_CLIENT}, "query": query,
                                                       "params": urllib.parse.unquote(SONGS_ONLY)}))
        if found and VIDEO_ID.fullmatch(found):
            return found
    except Exception:
        pass
    return find_video(query, fetch)


def find_video(query: str, fetch: Callable[[str], str] = get_text) -> str | None:
    try:
        found = video_id_from_results(fetch(RESULTS.format(urllib.parse.quote_plus(query))))
    except Exception:
        return None
    return found if found and VIDEO_ID.fullmatch(found) else None


# -- every music app ----------------------------------------------------------------------------------
AUTOPLAYS = {"youtube_music"}          # opening the song starts it; the rest need Play pressed
TRACK_PAGES = {                        # what a found song's address must look like, per service
    "youtube_music": re.compile(r"https://music\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}"),
    "deezer": re.compile(r"https://www\.deezer\.com/(?:[a-z]{2}/)?track/\d+"),
    "apple_music": re.compile(r"https://music\.apple\.com/[a-z]{2}/(?:album|song)/[^\s\"'<>]+"),
    "bandcamp": re.compile(r"https://[a-z0-9-]+\.bandcamp\.com/track/[a-z0-9-]+"),
}


def _get_json(url: str) -> dict:
    return json.loads(get_text(url))


def find_track(service: str, query: str, fetch: Callable[[str], str] = get_text,
               post: Callable[[str, dict], str] = _post_json) -> str | None:
    """The song's own page on that service, or None (not found / offline / no public search)."""
    q = urllib.parse.quote_plus(query)
    try:
        if service == "youtube_music":
            found = find_song(query, post, fetch)
            url = MUSIC_WATCH.format(found) if found else None
        elif service == "deezer":
            data = json.loads(fetch(f"https://api.deezer.com/search?q={q}&limit=1")).get("data") or []
            url = data[0].get("link") if data else None
        elif service == "apple_music":
            data = json.loads(fetch(f"https://itunes.apple.com/search?term={q}&entity=song&limit=1"))
            results = data.get("results") or []
            url = results[0].get("trackViewUrl") if results else None
        elif service == "bandcamp":
            m = re.search(r'href="(https://[a-z0-9-]+\.bandcamp\.com/track/[a-z0-9-]+)',
                          fetch(f"https://bandcamp.com/search?q={q}&item_type=t"))
            url = m.group(1) if m else None
        else:
            return None
    except Exception:
        return None
    pattern = TRACK_PAGES.get(service)
    return url if isinstance(url, str) and pattern is not None and pattern.match(url) else None
