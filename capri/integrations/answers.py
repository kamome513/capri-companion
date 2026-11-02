"""Quick answers for "what is a black hole" / "who was Napoleon" when there's no AI: the first
couple of sentences of the Wikipedia article (Wikipedia's free public API - no account).

Only the article's plain-text summary is used, cut down to something short enough to say.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Callable

USER_AGENT = "CapriDesktopCompanion/1.20 (desktop voice assistant; quick answers)"
SEARCH = ("https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&namespace=0&format=json&search={}")
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
MAX_WORDS = 45


def _get(url: str, timeout: float = 6.0) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def speakable(extract: str, max_words: int = MAX_WORDS) -> str:
    """'Napoleon Bonaparte (born Napoleone di Buonaparte; 15 August 1769 - 5 May 1821) was ...'
    -> without the brackets, one or two sentences, short enough to say."""
    text = re.sub(r"\s*\([^()]*\)", "", extract)            # pronunciations, dates, other names
    text = re.sub(r"\s*\[[^\]]*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    out = sentences[0] if sentences else ""
    if len(sentences) > 1 and len((out + " " + sentences[1]).split()) <= max_words:
        out += " " + sentences[1]
    words = out.split()
    if len(words) > max_words:
        out = " ".join(words[:max_words]).rstrip(",;:") + "..."
    return out


def lookup(subject: str, get: Callable[[str], dict | list] = _get) -> str | None:
    """A short spoken answer about `subject`, or None (nothing found / ambiguous / offline)."""
    subject = subject.strip()
    if not subject:
        return None
    try:
        found = get(SEARCH.format(urllib.parse.quote(subject)))
        titles = found[1] if isinstance(found, list) and len(found) > 1 else []
        if not titles:
            return None
        page = get(SUMMARY.format(urllib.parse.quote(titles[0].replace(" ", "_"), safe="")))
    except Exception:
        return None
    if not isinstance(page, dict) or page.get("type") == "disambiguation":
        return None
    answer = speakable(str(page.get("extract") or ""))
    return answer or None
