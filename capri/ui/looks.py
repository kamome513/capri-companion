"""Extra looks for Capri: pictures of her (assets/looks/, plus any you drop into the looks/
folder next to run.bat), each brought to life:

* her hair sways and sparkles (the red parts of the picture),
* she breathes and bobs, and bounces / flares with her voice,
* her eyes blink (found by their blue irises),
* a grin opens and closes as she talks (the white teeth below her eyes),
* now and then the picture glitches - red / cyan split, torn slices.

Pictures with a white background get it cut out (everything white that touches the edge),
so a figure stands free; full pictures are shown in a neon card. Nothing is needed but the
picture itself.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

LOOK_FILES = (".png", ".webp", ".jpg", ".jpeg")
MAX_SIDE = 640                 # pictures are kept at most this big (sharp at Capri's size on 4K)


def to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    return np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w].copy()


def to_image(a: np.ndarray) -> QImage:
    h, w = a.shape[:2]
    return QImage(np.ascontiguousarray(a).tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


def _grow(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def flood(seed: np.ndarray, allowed: np.ndarray, limit: int = 4000) -> np.ndarray:
    """Every `allowed` pixel connected to `seed` (4-way)."""
    region = seed & allowed
    for _ in range(limit):
        grown = _grow(region) & allowed
        if (grown == region).all():
            break
        region = grown
    return region


def cut_out_white(a: np.ndarray, threshold: int = 228) -> tuple[np.ndarray, float]:
    """Make the white background transparent: near-white pixels connected to the picture's edge.
    Returns (picture, share of it that became transparent)."""
    white = (a[..., :3] >= threshold).all(-1)
    edge = np.zeros_like(white)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    background = flood(edge, white)
    if background.mean() < 0.03:
        return a, 0.0
    # white patches trapped between her hair spikes are background too; small white bits
    # (teeth, the whites of her eyes, highlights) stay
    h, w = white.shape
    big = max(60, h * w // 700)
    left = white & ~background
    if background.mean() < 0.2:                 # a picture on a card, not a cut-out figure: its
        left[:] = False                         # white patches are teeth and eyes - keep them
    seen = np.zeros_like(white)
    for y in range(0, h, 3):
        for x in np.flatnonzero(left[y, ::3] & ~seen[y, ::3]) * 3:
            seed = np.zeros_like(white)
            seed[y, x] = True
            region = flood(seed, left, limit=2000)
            seen |= region
            if region.sum() >= big:
                background |= region
    out = a.copy()
    out[background, 3] = 0
    # soften the cut: two rings of pixels next to the background fade out
    ring1 = _grow(background) & ~background
    ring2 = _grow(background | ring1) & ~(background | ring1)
    out[ring1, 3] = np.minimum(out[ring1, 3], 120)
    out[ring2, 3] = np.minimum(out[ring2, 3], 215)
    return out, float(background.mean())


def blobs(mask: np.ndarray, min_pixels: int) -> list[tuple[float, float, float, int]]:
    """Connected regions of a mask: (cx, cy, radius, pixels), biggest first. Coarse - fine for eyes."""
    h, w = mask.shape
    step = max(1, max(h, w) // 200)
    small = mask[::step, ::step]
    seen = np.zeros_like(small)
    found = []
    ys, xs = np.nonzero(small)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        seed = np.zeros_like(small)
        seed[y, x] = True
        region = flood(seed, small, limit=400)
        seen |= region
        n = int(region.sum()) * step * step
        if n >= min_pixels:
            ry, rx = np.nonzero(region)
            cx, cy = (rx.mean() + 0.5) * step, (ry.mean() + 0.5) * step
            radius = max(rx.max() - rx.min(), ry.max() - ry.min()) * step / 2 + step
            found.append((float(cx), float(cy), float(radius), n))
    return sorted(found, key=lambda b: -b[3])


@dataclass
class Look:
    """A picture of her, ready to animate."""
    name: str
    image: QImage                                   # with its white background cut out (if it had one)
    cutout: bool                                    # stands free (True) / shown in a card (False)
    eyes: list[tuple[float, float, float]] = field(default_factory=list)        # (x, y, r) in image px
    mouth: tuple[int, int, int, int] | None = None   # teeth: x, y, w, h in image px
    sparkles: list[tuple[float, float, float]] = field(default_factory=list)    # hair points (x, y, phase)
    hair: QImage | None = None                       # just the red hair, for the sway

    @property
    def aspect(self) -> float:
        return self.image.width() / max(1, self.image.height())


def analyse(name: str, img: QImage, seed: int = 9) -> Look:
    if max(img.width(), img.height()) > MAX_SIDE:
        img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    a = to_array(img)
    if a[..., 3].min() < 250:                       # already see-through
        share = float((a[..., 3] < 20).mean())
    else:
        a, share = cut_out_white(a)
    cutout = share > 0.2
    rgb = a[..., :3].astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    opaque = a[..., 3] > 128
    h, w = r.shape
    # eyes: the two biggest blue blobs
    blue = opaque & (b > 150) & (r < 100) & (b > g + 40)
    eyes = [(x, y, rad) for x, y, rad, _n in blobs(blue, min_pixels=max(12, h * w // 6000))[:2]]
    # her hair: the red
    red = opaque & (r > 150) & (g < 110) & (b < 140)
    hair = None
    sparkles = []
    if red.mean() > 0.02:
        layer = a.copy()
        layer[~red, 3] = 0
        hair = to_image(layer)
        ys, xs = np.nonzero(red)
        rng = random.Random(seed)
        for i in rng.sample(range(len(xs)), min(70, len(xs))):
            sparkles.append((float(xs[i]), float(ys[i]), rng.uniform(0, math.tau)))
    # a grin: white teeth below the eyes, between them
    mouth = None
    if len(eyes) == 2:
        (x1, y1, r1), (x2, y2, r2) = eyes
        top = int(max(y1, y2) + max(r1, r2) * 1.2)
        left, right = int(min(x1, x2) - max(r1, r2)), int(max(x1, x2) + max(r1, r2))
        band = np.zeros_like(opaque)
        band[top:min(h, top + int(abs(x2 - x1) * 1.6) + 1), max(0, left):min(w, right)] = True
        teeth = opaque & band & (rgb >= 225).all(-1)
        found = blobs(teeth, min_pixels=max(20, h * w // 4000))
        if found:
            cx, cy, rad, _n = found[0]
            ys, xs = np.nonzero(teeth)
            near = (abs(xs - cx) <= rad * 1.3) & (abs(ys - cy) <= rad * 1.3)
            if near.any():
                x0, x1_, y0, y1_ = xs[near].min(), xs[near].max(), ys[near].min(), ys[near].max()
                mouth = (int(x0), int(y0), int(x1_ - x0 + 1), int(y1_ - y0 + 1))
    return Look(name, to_image(a), cutout, eyes, mouth, sparkles, hair)


def folders() -> list[Path]:
    """Built-in looks, then yours (a "looks" folder next to run.bat / Capri.exe)."""
    import sys
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    mine = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    return [base / "assets" / "looks", mine / "looks"]


_LOADED: dict[str, Look] = {}


def available() -> dict[str, Path]:
    return look_files(folders())


def load(name: str) -> Look | None:
    """A look by name (analysed once, then kept)."""
    if name not in _LOADED:
        path = available().get(name)
        if path is None:
            return None
        img = QImage(str(path))
        if img.isNull():
            return None
        _LOADED[name] = analyse(name, img)
    return _LOADED[name]


def look_files(folders: list[Path]) -> dict[str, Path]:
    """name -> picture, from the given folders (later folders win: yours over the built-in ones)."""
    found: dict[str, Path] = {}
    for folder in folders:
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in LOOK_FILES:
                    found[f.stem.replace("_", " ").replace("-", " ").strip().title()] = f
    return found


class LookPainter:
    """Draws a Look, alive. One per window; keeps pre-scaled copies for its size and screen."""

    def __init__(self, look: Look, seed: int = 3) -> None:
        self.look = look
        self.rng = random.Random(seed)
        self._next_blink, self._blink_at = 2.0, -10.0
        self._next_glitch, self._glitch_until = 6.0, -1.0
        self._cache: dict[tuple, QImage] = {}

    def _scaled(self, which: str, img: QImage, w: int, h: int) -> QImage:
        key = (which, w, h)
        if key not in self._cache:
            if len(self._cache) > 8:
                self._cache.clear()
            self._cache[key] = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
        return self._cache[key]

    def _tinted(self, img: QImage, color: QColor) -> QImage:
        key = ("tint", img.cacheKey(), color.rgba())
        if key not in self._cache:
            out = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
            out.setDevicePixelRatio(img.devicePixelRatio())
            out.fill(0)
            q = QPainter(out)
            q.drawImage(0, 0, img)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            q.fillRect(out.rect(), color)
            q.end()
            self._cache[key] = out
        return self._cache[key]

    def blinking(self, t: float) -> float:
        if t > self._next_blink:
            self._blink_at, self._next_blink = t, t + self.rng.uniform(2.5, 6.0)
        k = (t - self._blink_at) / 0.16
        return 1 - abs(2 * k - 1) if 0 <= k < 1 else 0.0

    def paint(self, p: QPainter, rect: QRectF, t: float, level: float = 0.0, talking: bool = False,
              dpr: float = 1.0, wild: float = 1.0) -> None:
        """Draw the picture filling `rect` (its aspect is the caller's business)."""
        L = self.look
        energy = level if talking else 0.0
        sx, sy = rect.width() / L.image.width(), rect.height() / L.image.height()
        bob = math.sin(t * 1.6) * 1.4 - 3.0 * energy
        r = rect.translated(0, bob)
        W, H = max(1, round(r.width() * dpr)), max(1, round(r.height() * dpr))
        base = self._scaled("base", L.image, W, H)
        # glitch now and then (and on loud syllables)
        if t > self._next_glitch:
            self._glitch_until = t + self.rng.uniform(0.12, 0.3)
            self._next_glitch = t + self.rng.uniform(5.0, 14.0)
        glitch = t < self._glitch_until or energy > 0.85
        if glitch:
            g = random.Random(int(t * 30))
            split = g.uniform(3, 8)
            p.save()
            p.setOpacity(0.55)
            p.drawImage(r.translated(-split, 0), self._tinted(base, QColor(236, 16, 70)))
            p.drawImage(r.translated(split, g.uniform(-1, 1)), self._tinted(base, QColor(0, 226, 255)))
            p.restore()
        p.drawImage(r, base)
        # her hair sways - more when she talks - in thin strips, each shifted a little
        if L.hair is not None and wild > 0:
            hair = self._scaled("hair", L.hair, W, H)
            strip = max(2, round(2 * dpr))                       # thin strips: a smooth wave
            amp = (1.3 + 3.0 * energy) * min(1.5, wild) * max(0.6, r.height() / 220)
            for y in range(0, H, strip):
                f = y / H
                dx = amp * math.sin(t * (1.3 + 2 * energy) + f * 5.0) * (1.0 - f) ** 1.2
                if abs(dx) < 0.3:
                    continue
                p.drawImage(QRectF(r.left() + dx, r.top() + y / dpr, r.width(), strip / dpr), hair,
                            QRectF(0, y, W, strip))
        # sparkles in her hair
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, phase in L.sparkles:
            a = max(0.0, math.sin(t * 2.1 + phase)) ** 8
            if a < 0.05:
                continue
            c = QPointF(r.left() + x * sx, r.top() + y * sy)
            size = 1.2 + 1.8 * a
            p.setBrush(QColor(255, 235, 245, int(230 * a)))
            p.drawEllipse(c, size, size)
            p.setPen(QPen(QColor(255, 255, 255, int(160 * a)), 0.8))
            p.drawLine(c - QPointF(size * 2.2, 0), c + QPointF(size * 2.2, 0))
            p.drawLine(c - QPointF(0, size * 2.2), c + QPointF(0, size * 2.2))
            p.setPen(Qt.PenStyle.NoPen)
        p.restore()
        # a grin that opens as she talks
        if L.mouth and talking and energy > 0.05:
            mx, my, mw, mh = L.mouth
            src = QRectF(mx * W / L.image.width(), my * H / L.image.height(),
                         mw * W / L.image.width(), mh * H / L.image.height()).adjusted(-2, -1, 2, 1)
            dst = QRectF(r.left() + mx * sx - 2 / dpr, r.top() + my * sy - 1 / dpr,
                         src.width() / dpr, src.height() / dpr * (1 + 0.6 * energy))
            p.drawImage(dst, base, src)
        # blinks
        shut = self.blinking(t)
        if shut > 0:
            p.save()
            for x, y, rad in L.eyes:
                c = QPointF(r.left() + x * sx, r.top() + y * sy)
                rx, ry = rad * sx * 1.25, rad * sy * 1.25
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(12, 8, 16))
                p.drawEllipse(QRectF(c.x() - rx, c.y() - ry, 2 * rx, 2 * ry * shut))
                if shut > 0.6:
                    p.setPen(QPen(QColor(40, 230, 120), max(1.0, rx * 0.12)))
                    p.drawLine(c + QPointF(-rx * 0.9, 0), c + QPointF(rx * 0.9, rx * 0.1))
            p.restore()
        if glitch:                                     # torn slices
            g = random.Random(int(t * 30) + 1)
            for _ in range(3):
                y = g.uniform(0, H - 8)
                hh = g.uniform(2, 10) * dpr
                dx = g.choice((-1, 1)) * g.uniform(4, 12)
                p.drawImage(QRectF(r.left() + dx, r.top() + y / dpr, r.width(), hh / dpr), base, QRectF(0, y, W, hh))
