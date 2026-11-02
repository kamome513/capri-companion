"""Finding what to click when you say "click subscribe" / "click the next button" / "click that".

She looks at the window you're using (not her own) when you ask - nothing is watched or kept
in between, and nothing leaves your PC:

1. "click that" / "click it" / "click here": whatever button or link is under your mouse.
2. "click <name>": the window's own buttons, links, tabs, menu items... by name, through
   Windows UI Automation (what screen readers use).
3. Still nothing: she reads the window with Windows' built-in text recognition (OCR) and finds
   the words on screen - for apps that don't name their buttons (games, some launchers).

Clicking: the button's own "press" when UI Automation offers it (no mouse needed), otherwise a
mouse click on it - your pointer is put straight back. Risky labels (delete, buy, send...) are
asked about first, by the router.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..commands.fuzzy import similarity

log = logging.getLogger("capri")

MATCH = 0.78                  # how close a name has to be
RISKY = re.compile(r"\b(?:delete|remove|uninstall|erase|wipe|format|reset|buy|purchase|pay|checkout|check out|"
                   r"place order|order|send|submit|transfer|confirm|discard|don.?t save|sign out|log out|"
                   r"deactivate|permanently|empty recycle bin|end task|shut ?down|restart)\b", re.IGNORECASE)


@dataclass
class Target:
    name: str
    rect: tuple[int, int, int, int]           # left, top, right, bottom - physical screen pixels
    how: str                                  # "mouse" (under your pointer) / "ui" (by name) / "text" (OCR)
    element: object | None = None             # UI Automation element to press, if any
    score: float = 1.0

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2

    @property
    def risky(self) -> bool:
        return bool(RISKY.search(self.name))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", text.lower())).strip()


NUMBER_WORDS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
                "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
SYMBOL_WORDS = {"minus": "-", "dash": "-", "hyphen": "-", "dot": ".", "period": ".", "point": ".", "plus": "+",
                "slash": "/", "underscore": "_", "hashtag": "#", "hash": "#", "ampersand": "&", "percent": "%",
                "dollar": "$", "colon": ":", "star": "*", "asterisk": "*", "equals": "="}


def _digits(words: list[str]) -> list[str]:
    """['one', 'thousand', 'minus', 'seven'] -> ['1000', 'minus', '7'] (number words to digits)."""
    out, total, current, in_number = [], 0, 0, False
    for w in words + [""]:
        if w in NUMBER_WORDS and not (w == "oh" and not in_number):
            current += NUMBER_WORDS[w]
            in_number = True
        elif w in SCALES and in_number:
            current = max(current, 1) * SCALES[w]
            if SCALES[w] >= 1000:
                total, current = total + current, 0
        elif w == "and" and in_number:
            continue
        else:
            if in_number:
                out.append(str(total + current))
                total, current, in_number = 0, 0, False
            if w:
                out.append(w)
    return out


def spoken_variants(label: str) -> list[str]:
    """Ways what you said might be written on screen: "one thousand minus seven" -> "1000-7",
    "dot m p three" -> ".mp3", "track two" -> "track 2"."""
    words = label.lower().split()
    digits = _digits(words)
    symbols = [SYMBOL_WORDS.get(w, w) for w in digits]
    joined = "".join(w for w in symbols)                               # ".mp3", "1000-7"
    glued = re.sub(r"(?<=\b\w) (?=\w\b)", "", " ".join(symbols))      # spelled-out letters: "m p 3" -> "mp3"
    plain = re.sub(r"\s+(?:playlist|song|album|track|button|tab|link|one|folder|file|chat|channel)$", "", label.strip())
    seen, out = set(), []
    for v in (label, " ".join(digits), " ".join(symbols), glued, joined, plain, *spoken_variants_of(plain, label)):
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def spoken_variants_of(plain: str, label: str) -> list[str]:
    """The same conversions for the label without its trailing kind-word ("... playlist")."""
    if plain == label.strip():
        return []
    return [v for v in spoken_variants(plain) if v != plain]


def _squash(text: str) -> str:
    """Letters and digits only: "1000-7" -> "10007", ".mp3 playlist" -> "mp3playlist"."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def name_score(label: str, name: str) -> float:
    """How well a button's name matches what you said (0..1). Also tries the ways it might be
    written ("one thousand minus seven" -> "1000-7") - those only count as a whole match, so
    "seven" never clicks "1000-7"."""
    best = _name_score(label, name)
    for variant in spoken_variants(label)[1:]:
        best = max(best, _squash_score(variant, name))
    return best


def _squash_score(variant: str, name: str) -> float:
    sa, sb = _squash(variant), _squash(name)
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 0.97
    first = _squash(re.split(r"[\s\u2022|,(]", name.strip(), maxsplit=1)[0]) if name.strip() else ""
    if len(sa) >= 3 and first == sa:
        return 0.9                                         # ".mp3 Playlist - you"
    return 0.0


def _name_score(label: str, name: str) -> float:
    squashed = _squash_score(label, name)                  # "1000 7" vs "1000-7", "mp3" vs ".mp3"
    if squashed:
        return squashed
    a, b = _clean(label), _clean(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    words = b.split()
    if a in words or b.startswith(a + " "):                  # "subscribe" ~ "Subscribe to MrBeast"
        return 0.9 - 0.02 * max(0, len(words) - len(a.split()))
    if len(b) <= len(a) * 3 and a in b:
        return 0.85
    if abs(len(a) - len(b)) > max(3, len(a) * 0.4):     # "play" isn't "Playlist settings"
        return 0.0
    return similarity(a, b)


def best_match(label: str, things: list[tuple[str, tuple[int, int, int, int], object]]) -> Target | None:
    best = None
    for name, rect, element in things:
        score = name_score(label, name)
        if score >= MATCH and (best is None or score > best.score):
            best = Target(name, rect, "ui", element, score)
    return best


@dataclass
class Word:
    text: str
    line: int
    rect: tuple[int, int, int, int]           # physical screen pixels


OCR_MIXUPS = [(r"(?<=[a-z])0|0(?=[a-z])", "o"), (r"(?<=[a-z])[1|!]|[1|!](?=[a-z])", "l"), (r"rn", "m"),
              (r"(?<=[a-z])5(?=[a-z])", "s"), (r"vv", "w"), (r"(?<=[a-z])8(?=[a-z])", "b")]


def _ocr_fixed(text: str) -> str:
    """Undo common screen-reading mix-ups: "dead1ine" -> "deadline", "rnodern" -> "modern"."""
    for pattern, fix in OCR_MIXUPS:
        text = re.sub(pattern, fix, text)
    return text


def match_words(label: str, words: list[Word]) -> Target | None:
    """Find what you said among words read off the screen (runs of words on one line)."""
    want = _clean(label)
    n = max(1, len(want.split()))
    lines: dict[int, list[Word]] = {}
    for w in words:
        lines.setdefault(w.line, []).append(w)
    best = None
    for line in lines.values():
        for size in {max(1, n - 1), n, n + 1}:
            for i in range(0, max(1, len(line) - size + 1)):
                run = line[i:i + size]
                if not run:
                    continue
                text = " ".join(w.text for w in run)
                read = _clean(text)
                score = 1.0 if read == want else max(similarity(want, read), similarity(want, _ocr_fixed(read)))
                for variant in spoken_variants(label):                 # "1000-7" read off the screen
                    if _squash(variant) and _squash(variant) == _squash(text):
                        score = max(score, 0.97)
                if score >= MATCH and (best is None or score > best.score):
                    rect = (min(w.rect[0] for w in run), min(w.rect[1] for w in run),
                            max(w.rect[2] for w in run), max(w.rect[3] for w in run))
                    best = Target(text, rect, "text", None, score)
    return best


class Finder:
    def __init__(self, ui, window: Callable[[], int | None], window_rect: Callable[[int], tuple | None],
                 cursor: Callable[[], tuple[int, int]], ocr: Callable[[tuple], list[Word]] | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.ui, self.window, self.window_rect, self.cursor, self.ocr = ui, window, window_rect, cursor, ocr
        self.sleep = sleep or __import__("time").sleep

    def find(self, label: str) -> Target | None:
        """Blocking (UI Automation / OCR) - call from a worker thread."""
        if not label.strip():
            return self.under_mouse()
        hwnd = self.window()
        if not hwnd:
            return None
        for attempt in range(2):                            # Chromium apps wake their accessibility on the first ask
            try:
                things = [(b.name, b.rect, b) for b in self.ui.clickables(hwnd) if b.rect]
            except Exception as exc:
                log.info("click: UI Automation failed: %s", exc)
                things = []
            found = best_match(label, things)
            if found is not None:
                log.info("click: %r -> %r (%s, %.2f)", label, found.name, found.how, found.score)
                return found
            if attempt == 0 and things:
                break
            self.sleep(0.4)
        if self.ocr is not None:
            rect = self.window_rect(hwnd)
            if rect:
                try:
                    found = match_words(label, self.ocr(rect))
                except Exception as exc:
                    log.info("click: OCR failed: %s", exc)
                    found = None
                if found is not None:
                    log.info("click: %r -> read %r on screen (%.2f)", label, found.name, found.score)
                    return found
        log.info("click: couldn't find %r", label)
        return None

    def find_text(self, label: str) -> Target | None:
        """Any words on screen ("highlight the word deadline"). Blocking. In order:
        1. the app's own text (web pages, documents, text boxes): exact, selected by the app itself;
        2. reading the window (OCR) - for everything else;
        3. a button / link with that name."""
        hwnd = self.window()
        if not hwnd:
            return None
        if hasattr(self.ui, "find_text"):
            for words in spoken_variants(label):
                try:
                    hit = self.ui.find_text(hwnd, words)
                except Exception as exc:
                    log.info("highlight: the app's text isn't readable: %s", exc)
                    break
                if hit is not None:
                    log.info("highlight: %r found in the app's own text", words)
                    return Target(hit.name, hit.rect, "text", hit)
        if self.ocr is not None:
            rect = self.window_rect(hwnd)
            if rect:
                try:
                    found = match_words(label, self.ocr(rect))
                except Exception as exc:
                    log.info("highlight: OCR failed: %s", exc)
                    found = None
                if found is not None:
                    return found
        return self.find(label)

    def under_mouse(self) -> Target | None:
        x, y = self.cursor()
        try:
            element = self.ui.element_at(x, y)
        except Exception as exc:
            log.info("click: nothing readable under the mouse: %s", exc)
            element = None
        if element is not None and element.rect:
            return Target(element.name or "that", element.rect, "mouse", element)
        return Target("that", (x - 12, y - 12, x + 12, y + 12), "mouse", None)   # click right where you point


def click(target: Target, mouse: Callable[[int, int], None]) -> None:
    """Press it: the button's own press if it has one, else a mouse click on it."""
    element = target.element
    if element is not None:
        try:
            element.press()
            return
        except Exception as exc:
            log.info("click: %r can't be pressed directly (%s) - clicking it", target.name, exc)
    mouse(*target.center)


# -- Windows plumbing ----------------------------------------------------------------------------------
def target_window() -> int | None:
    """The window you're using - or, if that's one of Capri's (her chat window), the one behind it."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    me = os.getpid()

    def usable(hwnd: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return False
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.right - r.left > 120 and r.bottom - r.top > 80
    front = user32.GetForegroundWindow()
    if front and usable(front):
        return front
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if usable(hwnd) and not user32.GetWindow(hwnd, 4):     # top-level, no owner (GW_OWNER)
            found.append(hwnd)
            return False                                       # z-order: the first one is in front
        return True
    user32.EnumWindows(each, 0)
    return found[0] if found else None


def cursor_pos() -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


OCR_SCRIPT = r"""
param([string]$Path)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$i = 0
$words = foreach ($line in $result.Lines) { $i++; foreach ($w in $line.Words) {
    [pscustomobject]@{ t = $w.Text; l = $i; x = $w.BoundingRect.X; y = $w.BoundingRect.Y;
                       w = $w.BoundingRect.Width; h = $w.BoundingRect.Height } } }
ConvertTo-Json -InputObject @($words) -Compress
"""


def prepare_for_ocr(rgb):
    """Help Windows' text reader: grey, stretched contrast, and dark mode flipped to dark text
    on light (it misses light-on-dark text far more often)."""
    import numpy as np
    grey = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114).astype(np.float32)
    if grey.mean() < 110:                                  # mostly dark: a dark-mode app
        grey = 255 - grey
    lo, hi = np.percentile(grey, 2), np.percentile(grey, 98)
    if hi - lo > 10:
        grey = np.clip((grey - lo) * 255.0 / (hi - lo), 0, 255)
    g = grey.astype(np.uint8)
    return np.dstack([g, g, g])


def windows_ocr(rect: tuple[int, int, int, int]) -> list[Word]:
    """Words in a screen rectangle, read by Windows' own OCR (runs through Windows PowerShell)."""
    import numpy as np
    from PySide6.QtGui import QImage

    from .screen_click import grab
    shot = grab(rect)
    if shot is None:
        return []
    shot = prepare_for_ocr(shot)
    h, w = shot.shape[:2]
    scale = 2 if max(w, h) * 2 <= 9000 else 1            # small text reads far better bigger
    rgba = np.dstack([shot, np.full((h, w), 255, np.uint8)])
    img = QImage(np.ascontiguousarray(rgba).tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888)
    if scale != 1:
        from PySide6.QtCore import Qt
        img = img.scaled(w * scale, h * scale, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    folder = Path(tempfile.mkdtemp(prefix="capri_ocr_"))
    png, script = folder / "screen.png", folder / "ocr.ps1"
    try:
        img.save(str(png))
        script.write_text(OCR_SCRIPT, encoding="utf-8")
        run = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-File", str(script), str(png)], capture_output=True, text=True, timeout=20,
                             creationflags=0x08000000)
        data = json.loads(run.stdout.strip() or "[]")
    finally:
        for f in (png, script):
            f.unlink(missing_ok=True)
        folder.rmdir()
    left, top = rect[0], rect[1]
    words = []
    for d in data if isinstance(data, list) else [data]:
        x, y, ww, hh = (float(d[k]) / scale for k in ("x", "y", "w", "h"))
        words.append(Word(str(d["t"]), int(d["l"]), (int(left + x), int(top + y), int(left + x + ww), int(top + y + hh))))
    return words
