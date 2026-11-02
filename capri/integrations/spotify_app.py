"""Playing a song in the Spotify app - no Premium or developer account needed.

1. Find the exact track, trying in order:
   * Spotify's own search, if you connected Spotify in Settings (any account);
   * iTunes' public song search (free, no key) for the exact song + artist, turned
     into the Spotify track by song.link (also free, no key);
   * the same through Deezer's public search;
   * a web search (DuckDuckGo, then Bing) for the song's open.spotify.com page.
   Only the song and artist names are sent.
2. Make sure Spotify is running (start it and wait for its main window).
3. Open the track in the app with Spotify's own link (spotify:track:<id>).
4. Check it's really playing: while Spotify plays, its main window's title is
   "Artist - Song" ("Spotify ..." while paused). If the track opened but didn't
   start, press the big Play button on its page and check again. (Never the media
   Play key: that would resume whatever was playing before.)

What she says is what Spotify's title shows, so "Playing X" is never a guess.
Every step is logged to capri.log (lines starting with "spotify:").
"""

from __future__ import annotations

import base64
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

log = logging.getLogger("capri")

TRACK_LINK = re.compile(r"open\.spotify\.com(?:%2F|/)(?:intl-[a-z]{2}(?:%2F|/))?track(?:%2F|/)([A-Za-z0-9]{22})")
BING_REDIRECT = re.compile(r"[?&;]u=a1([A-Za-z0-9_\-]+)")          # Bing wraps result links in base64
ITUNES = "https://itunes.apple.com/search?entity=song&limit=8&term={}"
DEEZER = "https://api.deezer.com/search?limit=8&q={}"
SONGLINK = "https://api.song.link/v1-alpha.1/links?userCountry=US&url={}"
SEARCHES = [
    "https://html.duckduckgo.com/html/?q={}",
    "https://www.bing.com/search?q={}",
]
OEMBED = "https://open.spotify.com/oembed?url=https%3A%2F%2Fopen.spotify.com%2Ftrack%2F{}"
PAUSED_TITLES = ("spotify", "spotify free", "spotify premium")
AD_TITLES = ("advertisement", "spotify advertisement", "spotify - advertisement")   # Free: an ad plays first
START_WAIT = 25.0          # seconds for a closed Spotify to open its window (slow PCs take a while)
PLAY_WAIT = 4.0            # seconds for the title to show the song


@dataclass
class Played:
    status: str            # playing | opened | not_found | no_spotify (slow to open) | not_installed
    title: str = ""        # what Spotify shows ("NF - Let You Down"), or the song we opened


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# Other versions of a song - only wanted when you asked for one ("chicago" by MJ is "Chicago", not "Chicago
# (Original Version)"; "...live" or "...remix" picks those).
VERSION_WORDS = re.compile(r"\b(original version|version|remix|mix|live|demo|instrumental|karaoke|acoustic|sped up|"
                           r"slowed|reverb|nightcore|cover|tribute|edit|remaster(?:ed)?|extended|re-?recorded|"
                           r"radio edit|mono|stereo|8d|bass boosted|a cappella|acapella)\b", re.I)


def version_penalty(title: str, query: str) -> float:
    """0, or 0.4 when the title is a special version ("(Original Version)", "- Remix", "(Live)") you didn't
    ask for. Applied to every candidate, so the plain song wins when it's there."""
    extra = re.findall(r"[\(\[]([^\)\]]*)[\)\]]|\s-\s(.+)$", title)
    words = " ".join(a or b for a, b in extra)
    found = {w.lower() for w in VERSION_WORDS.findall(words)}
    return 0.4 if found and not any(w in query.lower() for w in found) else 0.0


def artist_score(who: str, artist: str) -> float:
    """How well a result's artist(s) fit what you said - by sound, or by initials ("mj" = Michael Jackson,
    "xxx" = XXXTentacion's own name is matched by sound)."""
    if not artist:
        return 1.0
    best = 0.0
    said = re.sub(r"[^a-z]", "", artist.lower())
    for a in re.split(r",|&| and | feat\.? | x ", who):
        a = a.strip()
        if not a:
            continue
        best = max(best, similar(a, artist))
        initials = "".join(w[0] for w in re.findall(r"[a-z0-9]+", a.lower()))
        if 2 <= len(said) <= 4 and said == initials:
            best = 1.0
    return best


def looks_like_initials(artist: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{2,3}|(?:[a-z]\.? ?){2,3}", artist.strip().lower())) and " " not in artist.strip()


def _clean(title: str) -> str:
    """'Let You Down (feat. X) - Remastered 2011' -> 'Let You Down' for comparing."""
    return re.split(r"\s+[-(\[]\s*(?:feat|ft|with|remaster|live|from|radio|single|explicit)", title, flags=re.I)[0].strip()


def track_ids_from_page(html: str) -> list[str]:
    """Track ids in a search results page, in order, no repeats - including Bing's base64 links."""
    found = [m.group(1) for m in TRACK_LINK.finditer(html)]
    for m in BING_REDIRECT.finditer(html):
        try:
            url = base64.urlsafe_b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4)).decode("utf-8", "ignore")
        except ValueError:
            continue
        found += [t.group(1) for t in TRACK_LINK.finditer(url)]
    seen: list[str] = []
    for tid in found:
        if tid not in seen:
            seen.append(tid)
    return seen


def main_window_titles(desktop, pids: list[int]) -> list[str]:
    """Titles of Spotify's real main window only (it's Chromium-based) - not its hidden helper
    windows ("Default IME", "MSCTFIME UI"...), whose titles would look like a song."""
    out = []
    for hwnd in desktop.windows_for(pids):
        cls = desktop.window_class(hwnd)
        if cls.startswith("Chrome_WidgetWin") or cls == "SpotifyMainWindow":
            out.append(desktop.window_title(hwnd))
    return out


class SpotifyApp:
    def __init__(self, open_item: Callable[[str], None], spotify_pids: Callable[[], list[int]],
                 window_titles: Callable[[list[int]], list[str]],
                 press_play: Callable[[list[int], str], bool] | None,
                 fetch_text: Callable[[str], str], fetch_json: Callable[[str], dict],
                 api_search: Callable[[str, str], str | None] | None = None,
                 click_play: Callable[[list[int]], bool] | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
        self.open_item, self.spotify_pids, self.window_titles = open_item, spotify_pids, window_titles
        self.press_play, self.fetch_text, self.fetch_json = press_play, fetch_text, fetch_json
        self.api_search, self.click_play = api_search, click_play
        self.sleep, self.clock = sleep, clock

    # -- 1. which track ---------------------------------------------------------------------------
    def find_track(self, query: str, artist: str) -> tuple[str, str] | None:
        """(track id, its name - "" if unknown) or None."""
        for source in (self._from_spotify, self._from_catalog, self._from_web):
            try:
                found = source(query, artist)
            except Exception as exc:                     # one source down: try the next
                log.info("spotify: %s failed: %s", source.__name__.lstrip("_"), exc)
                continue
            if found:
                return found
        return None

    def _from_spotify(self, query: str, artist: str) -> tuple[str, str] | None:
        if self.api_search is None:
            return None
        uri = self.api_search(query, artist)
        if uri:
            log.info("spotify: Spotify's search found %s", uri)
            return uri.split(":")[-1], ""
        return None

    def _score(self, name: str, who: str, query: str, artist: str) -> float:
        title = similar(_clean(name), query) if query else 1.0
        return title + artist_score(who, artist) - version_penalty(name, query)

    def _from_catalog(self, query: str, artist: str) -> tuple[str, str] | None:
        """iTunes' (then Deezer's) public song search -> the exact song -> song.link -> Spotify."""
        # initials ("mj") aren't searchable: search the title alone, then match the initials ourselves
        said = (query,) if query and looks_like_initials(artist) else (query, artist)
        words = urllib.parse.quote_plus(" ".join(w for w in said if w))
        candidates: list[tuple[float, str, str]] = []           # (score, song page url, track name)
        data = self.fetch_json(ITUNES.format(words)) or {}
        for r in data.get("results", []):
            if r.get("trackViewUrl"):
                candidates.append((self._score(r.get("trackName", ""), r.get("artistName", ""), query, artist),
                                   r["trackViewUrl"], r.get("trackName", "")))
        if not candidates:
            data = self.fetch_json(DEEZER.format(words)) or {}
            for r in data.get("data", []):
                if r.get("link"):
                    candidates.append((self._score(r.get("title", ""), (r.get("artist") or {}).get("name", ""),
                                                   query, artist), r["link"], r.get("title", "")))
        candidates.sort(key=lambda c: -c[0])
        for score, page, name in candidates[:2]:
            if score < 1.2:                                       # not really the song asked for
                break
            links = self.fetch_json(SONGLINK.format(urllib.parse.quote(page, safe=""))) or {}
            url = ((links.get("linksByPlatform") or {}).get("spotify") or {}).get("url", "")
            m = TRACK_LINK.search(url)
            if m:
                log.info("spotify: found %r (match %.2f) -> %s", name, score, m.group(1))
                return m.group(1), _clean(name)
        log.info("spotify: song catalogs found no Spotify link")
        return None

    def _from_web(self, query: str, artist: str) -> tuple[str, str] | None:
        words = " ".join(w for w in (query, artist) if w)
        q = urllib.parse.quote_plus(f"site:open.spotify.com/track {words}")
        for template in SEARCHES:
            url = template.format(q)
            try:
                ids = track_ids_from_page(self.fetch_text(url))
            except Exception as exc:
                log.info("spotify: web search %s failed: %s", url.split("/")[2], exc)
                continue
            log.info("spotify: web search %s found %d track(s)", url.split("/")[2], len(ids))
            best = self._best(ids[:5], query)
            if best:
                return best
        return None

    def _best(self, ids: list[str], query: str) -> tuple[str, str] | None:
        """Check each result's real name (Spotify's public oEmbed) and keep the closest."""
        scored = []
        for i, tid in enumerate(ids):
            try:
                title = str((self.fetch_json(OEMBED.format(tid)) or {}).get("title", ""))
            except Exception:
                title = ""
            score = (similar(_clean(title), query) - version_penalty(title, query)) if (title and query) else 0.5
            scored.append((score, -i, tid, title))
            if score > 0.9:
                break
        if not scored:
            return None
        score, _i, tid, title = max(scored)
        log.info("spotify: picked %s %r (match %.2f)", tid, title, score)
        return tid, _clean(title)

    # -- 2-4. open it and check ----------------------------------------------------------------------
    def _title(self, pids: list[int]) -> str:
        titles = [t for t in self.window_titles(pids) if t.strip()]
        playing = [t for t in titles if t.strip().lower() not in PAUSED_TITLES]
        return (playing or titles or [""])[0]

    def _is_it(self, title: str, name: str, before: str) -> bool:
        if not title or title.strip().lower() in PAUSED_TITLES:
            return False
        if title.strip().lower() in AD_TITLES:
            return before.strip().lower() not in AD_TITLES      # Spotify Free started it with an ad
        song = _clean(title.split(" - ", 1)[-1])
        return similar(song, name) > 0.7 if name else title != before

    def _playing(self, pids: list[int], name: str, before: str) -> str:
        """The window title once it shows the song (or any new song when we don't know the name)."""
        deadline = self.clock() + PLAY_WAIT
        while True:
            title = self._title(pids)
            if self._is_it(title, name, before):
                return title
            if self.clock() >= deadline:
                return ""
            self.sleep(0.25)

    def play(self, query: str, artist: str = "") -> Played:
        found = self.find_track(query, artist)
        if found is None:
            log.info("spotify: couldn't find %r by %r anywhere", query, artist)
            return Played("not_found")
        tid, name = found
        pids = self.spotify_pids()
        if not pids or not self._title(pids):
            log.info("spotify: starting Spotify")
            try:
                self.open_item("spotify:")
            except OSError:
                log.info("spotify: the Spotify app isn't installed")
                return Played("not_installed")
            deadline = self.clock() + START_WAIT
            while not pids or not self._title(pids):
                if self.clock() >= deadline:
                    log.info("spotify: Spotify didn't open a window")
                    return Played("no_spotify")
                self.sleep(0.5)
                pids = self.spotify_pids()
            self.sleep(2.5)                                 # let it finish loading before the link
        before = self._title(pids)
        if name and self._is_it(before, name, ""):
            log.info("spotify: it's already playing")
            return Played("playing", before)
        log.info("spotify: opening spotify:track:%s (window says %r)", tid, before)
        self.open_item(f"spotify:track:{tid}")
        title = self._playing(pids, name, before)
        if not title and self.press_play is not None:
            log.info("spotify: opened, not playing yet - pressing the track's Play button")
            pressed = False
            try:
                pressed = self.press_play(pids, name)
            except Exception as exc:
                log.info("spotify: Play button failed: %s", exc)
            if pressed:
                title = self._playing(pids, name, before)
            else:
                log.info("spotify: couldn't find the track's Play button")
        if not title and self.click_play is not None:
            log.info("spotify: still not playing - looking for the green Play button on screen")
            try:
                if self.click_play(pids):
                    title = self._playing(pids, name, before)
                else:
                    log.info("spotify: no green Play button on screen")
            except Exception as exc:
                log.info("spotify: clicking Play failed: %s", exc)
        if title:
            log.info("spotify: playing %r", title)
            if title.strip().lower() in AD_TITLES:
                return Played("playing", name or query)         # an ad first, then the song
            return Played("playing", title)
        log.info("spotify: opened the track, window says %r", self._title(pids))
        return Played("opened", name or query)
