"""Styles (2.6): appearance presets that are more than a recolour - each one has its own palette (a skin mod's
"palette"), plus a "style" section that brings it to life around her:

* aura          a soft glow around her that breathes
* outline       a coloured glow round her silhouette (steady, pulsing, flickering or shifting colour)
* eyes          her eyes glowing in the style's colour
* hair          extensions growing out of her hair (lightning, ice crystals, flames, thorns, leaves, clouds, petals,
                gears, glass fins, insect spikes, ornaments, sun rays, shadow wisps, paper layers, tendrils, pixels...)
                and a glowing edge along her hair
* materials     what she's made of, drawn on her (clipped to her shape): gloss, ice, glowing veins or cracks, Kintsugi
                gold, racing stripes, scanlines, film grain, water caustics, rainbow sheen, CRT, paper, porcelain,
                armour segments, android joints, gold ornaments...
* particles     a few small things drifting round her (sparks, snow, spores, embers, petals, stars, bubbles, gears...)
* events        now and then, at random: a lightning flash, an eclipse halo, a solar flare, a crescent moon, a jellyfish
                drifting past, a flower blooming, a film scratch, a transmission glitch...
* move          a trail when she moves (embers, frost, petals, light streaks, an afterimage)
* filters       RGB split, flicker, see-through

Everything is plain data in the mod (no code), drawn here with QPainter on her own window, on top of her normal
figure and animations. Particles are worked out from the time (no per-particle state), so a frame costs the same
however long she's been running. Settings -> Styles turns each kind of effect on or off and picks the quality.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF,
                           QRadialGradient)

PARTICLE_KINDS = ("spark", "snow", "crystal", "spore", "leaf", "pollen", "ember", "petal", "rose", "sakura", "star",
                  "moon", "pixel", "bubble", "droplet", "gear", "paper", "geo", "mist", "ink", "glyph", "dust",
                  "bud", "static", "fragment", "orb")
MOTIONS = ("rise", "fall", "drift", "orbit", "hover", "emit", "swirl", "ground")
HAIR_KINDS = ("lightning", "crystal", "flame", "thorn", "leaf", "cloud", "petal", "gear", "glass", "insect",
              "ornament", "sun", "shadow", "paper", "tendril", "static", "pixel", "fin", "rose", "frost")
MATERIALS = ("gloss", "ice", "veins", "cracks", "kintsugi", "stripes", "scan", "grain", "caustics", "rainbow", "crt",
             "paper", "porcelain", "segments", "joints", "ornament", "markings", "warm", "sheen", "shade", "facets")
EVENTS = ("flash", "arc", "crackle", "ice_form", "frost", "lens_flare", "solar_flare", "eclipse", "thorn_vine",
          "glitch", "scan_sweep", "fragments", "eye_flicker", "ink_burst", "transmission", "interference",
          "status_blink", "sparks_feet", "petal_burst", "gold_shimmer", "ripple", "film_scratch", "bloom",
          "warning", "chem_bubbles", "paper_fold", "gears", "afterimage", "vanish", "crescent", "constellation",
          "halo", "jellyfish", "cloud", "wings", "stained_glass", "distortion", "static_lines", "pulse",
          "frost_bloom", "clock_aura", "rings")
MOVES = ("trail", "ember", "frost", "petals", "afterimage", "rainbow", "sparks", "ink", "bubbles", "pixels")
OUTLINE_MODES = ("steady", "pulse", "flicker", "rainbow", "fade")
LAYERS = ("back", "front")
MAX_PARTICLES = 60


def colour(value, alpha: int | None = None, fallback: str = "#ffffff") -> QColor:
    c = QColor(str(value or fallback))
    if not c.isValid():
        c = QColor(fallback)
    if alpha is not None:
        c.setAlpha(max(0, min(255, int(alpha))))
    return c


@dataclass
class Ctx:
    """Where she is this frame (window coordinates)."""
    win: QRectF                       # her window
    body: QRectF                      # her figure (feet to the top of her head)
    head: QRectF                      # her head (with the sheet's hair box)
    eyes: list                        # [QPointF, QPointF] (may be [])
    feet: QPointF
    t: float                          # seconds (monotonic)
    scale: float = 1.0                # her height / 300
    hair: QPainterPath | None = None  # her hair's outline (when known)
    lying: bool = False
    moving: QPointF = field(default_factory=QPointF)   # her speed on screen (px/s)
    eye_r: float = 3.0
    hair_key: tuple = ()              # changes only when her hair's outline changes (so its glow can be reused)
    hair_fn: object = None            # () -> her hair's outline, worked out only when it's needed

    def hair_path(self):
        if self.hair is None and self.hair_fn is not None:
            self.hair = self.hair_fn()
            self.hair_fn = None
        return self.hair

    @property
    def around(self) -> QRectF:
        """The space round her the effects live in (her, her hair, a little air) - inside her window."""
        top = min(self.body.top(), self.head.top() - self.head.height() * 0.9)
        r = QRectF(self.body.left() - self.body.width() * 0.45, top, self.body.width() * 1.9,
                   self.body.bottom() - top)
        return r.intersected(self.win.adjusted(3, 3, -3, -3))

    @property
    def hair_centre(self) -> QPointF:
        return QPointF(self.head.center().x(), self.head.top() + self.head.height() * 0.05)


# -- shapes -----------------------------------------------------------------------------------------------------------
def _star_path(points: int, inner: float) -> QPainterPath:
    path = QPainterPath()
    for i in range(points * 2):
        a = math.pi * i / points - math.pi / 2
        r = 1.0 if i % 2 == 0 else inner
        pt = QPointF(math.cos(a) * r, math.sin(a) * r)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    return path


def _gear_path(teeth: int = 8) -> QPainterPath:
    path = QPainterPath()
    n = teeth * 4
    for i in range(n):
        a = math.tau * i / n
        r = 1.0 if (i % 4) in (1, 2) else 0.74
        pt = QPointF(math.cos(a) * r, math.sin(a) * r)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(QPointF(0, 0), 0.32, 0.32)
    return path.subtracted(hole)


def _petal_path() -> QPainterPath:
    path = QPainterPath(QPointF(0, -1))
    path.cubicTo(QPointF(0.75, -0.6), QPointF(0.55, 0.7), QPointF(0, 1))
    path.cubicTo(QPointF(-0.55, 0.7), QPointF(-0.75, -0.6), QPointF(0, -1))
    return path


def _leaf_path() -> QPainterPath:
    path = QPainterPath(QPointF(0, -1))
    path.quadTo(QPointF(0.8, 0), QPointF(0, 1))
    path.quadTo(QPointF(-0.8, 0), QPointF(0, -1))
    return path


def _moon_path() -> QPainterPath:
    a, b = QPainterPath(), QPainterPath()
    a.addEllipse(QPointF(0, 0), 1, 1)
    b.addEllipse(QPointF(0.45, -0.2), 0.88, 0.88)
    return a.subtracted(b)


def _drop_path() -> QPainterPath:
    path = QPainterPath(QPointF(0, -1.2))
    path.cubicTo(QPointF(0.7, -0.2), QPointF(0.75, 0.9), QPointF(0, 0.9))
    path.cubicTo(QPointF(-0.75, 0.9), QPointF(-0.7, -0.2), QPointF(0, -1.2))
    return path


def _diamond_path(long: float = 1.6) -> QPainterPath:
    return _poly([(0, -long), (0.5, 0), (0, long * 0.6), (-0.5, 0)])


def _poly(points) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(QPointF(x, y))
    path.closeSubpath()
    return path


STAR4, STAR5, GEAR, PETAL, LEAF, MOON, DROP, DIAMOND = (_star_path(4, 0.32), _star_path(5, 0.45), _gear_path(),
                                                         _petal_path(), _leaf_path(), _moon_path(), _drop_path(),
                                                         _diamond_path())
TRIANGLE = _poly([(0, -1), (0.87, 0.5), (-0.87, 0.5)])
SQUARE = _poly([(-0.7, -0.7), (0.7, -0.7), (0.7, 0.7), (-0.7, 0.7)])


def _shape(p: QPainter, path: QPainterPath, at: QPointF, size: float, angle: float, fill: QColor | None,
           pen: QColor | None = None, width: float = 1.0) -> None:
    p.save()
    p.translate(at)
    p.rotate(angle)
    p.scale(size, size)
    p.setPen(QPen(pen, width / max(0.01, size)) if pen is not None else Qt.PenStyle.NoPen)
    p.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.restore()


def _glow_dot(p: QPainter, at: QPointF, r: float, c: QColor, alpha: float) -> None:
    halo = QColor(c)
    halo.setAlphaF(max(0.0, min(1.0, 0.22 * alpha)))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(at, r * 2.6, r * 2.6)
    core = QColor(c)
    core.setAlphaF(max(0.0, min(1.0, alpha)))
    p.setBrush(core)
    p.drawEllipse(at, r, r)


def draw_particle(p: QPainter, kind: str, at: QPointF, size: float, c: QColor, alpha: float, angle: float,
                  t: float = 0.0) -> None:
    """One particle (alpha 0..1)."""
    if alpha <= 0.02:
        return
    col = QColor(c)
    col.setAlphaF(max(0.0, min(1.0, alpha * c.alphaF())))
    if kind in ("spark",):
        p.setPen(QPen(col, max(1.0, size * 0.35)))
        p.drawLine(at + QPointF(-size, 0), at + QPointF(size, 0))
        p.drawLine(at + QPointF(0, -size), at + QPointF(0, size))
        _glow_dot(p, at, size * 0.35, c, alpha)
    elif kind in ("snow", "dust", "pollen", "spore", "orb"):
        _glow_dot(p, at, size * (0.5 if kind == "dust" else 0.7), c, alpha * (0.8 if kind == "dust" else 1.0))
    elif kind == "crystal":
        _shape(p, DIAMOND, at, size, angle, col, QColor(255, 255, 255, int(200 * alpha)), 1.0)
    elif kind == "leaf":
        _shape(p, LEAF, at, size, angle, col)
    elif kind in ("petal", "rose", "sakura"):
        _shape(p, PETAL, at, size, angle, col)
    elif kind == "ember":
        tail = QColor(col)
        tail.setAlphaF(col.alphaF() * 0.4)
        p.setPen(QPen(tail, max(1.0, size * 0.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(at, at + QPointF(math.sin(angle * 0.05) * size, size * 2.4))
        _glow_dot(p, at, size * 0.55, c, alpha)
    elif kind == "star":
        twinkle = 0.6 + 0.4 * math.sin(t * 5 + angle)
        _shape(p, STAR4, at, size * twinkle, 0, col)
    elif kind == "moon":
        _shape(p, MOON, at, size, angle * 0.2, col)
    elif kind in ("pixel", "static", "fragment"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        s = size * (0.9 if kind == "pixel" else 0.6)
        p.drawRect(QRectF(at.x() - s / 2, at.y() - s / 2, s * (2.2 if kind == "fragment" else 1), s))
    elif kind == "bubble":
        p.setPen(QPen(col, max(1.0, size * 0.18)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(at, size, size)
        hi = QColor(255, 255, 255, int(200 * alpha))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hi)
        p.drawEllipse(at + QPointF(-size * 0.35, -size * 0.35), size * 0.22, size * 0.22)
    elif kind == "droplet":
        _shape(p, DROP, at, size, 0, col)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, int(170 * alpha)))
        p.drawEllipse(at + QPointF(-size * 0.25, -size * 0.1), size * 0.2, size * 0.28)
    elif kind == "gear":
        _shape(p, GEAR, at, size, angle * 3, col)
    elif kind == "paper":
        shadow = QColor(0, 0, 0, int(60 * alpha))
        _shape(p, SQUARE, at + QPointF(size * 0.25, size * 0.3), size, angle, shadow)
        _shape(p, SQUARE, at, size, angle, col)
    elif kind == "geo":
        path = (TRIANGLE, SQUARE)[int(abs(angle)) % 2]
        _shape(p, path, at, size, angle, None, col, 1.2)
    elif kind == "mist":
        g = QRadialGradient(at, size * 3)
        m = QColor(col)
        m.setAlphaF(col.alphaF() * 0.35)
        g.setColorAt(0, m)
        m2 = QColor(col)
        m2.setAlpha(0)
        g.setColorAt(1, m2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(at, size * 3, size * 1.6)
    elif kind == "ink":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(at, size, size * 0.8)
        p.drawEllipse(at + QPointF(size * 0.7, size * 0.4), size * 0.45, size * 0.4)
    elif kind == "glyph":
        p.setPen(QPen(col, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        k = int(abs(angle)) % 4
        if k == 0:
            p.drawRect(QRectF(at.x() - size, at.y() - size * 0.6, size * 2, size * 1.2))
        elif k == 1:
            p.drawEllipse(at, size, size)
            p.drawLine(at, at + QPointF(size * 0.8, -size * 0.5))
        elif k == 2:
            p.drawPolyline([at + QPointF(-size, -size), at + QPointF(-size * 1.4, 0), at + QPointF(-size, size)])
            p.drawPolyline([at + QPointF(size, -size), at + QPointF(size * 1.4, 0), at + QPointF(size, size)])
        else:
            p.drawLine(at + QPointF(-size, 0), at + QPointF(size, 0))
            p.drawLine(at + QPointF(0, -size), at + QPointF(0, size))
    elif kind == "bud":
        for i in range(5):
            a = math.tau * i / 5 + angle * 0.02
            _shape(p, PETAL, at + QPointF(math.cos(a), math.sin(a)) * size * 0.7, size * 0.55,
                   math.degrees(a) + 90, col)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 236, 140, int(230 * alpha)))
        p.drawEllipse(at, size * 0.3, size * 0.3)


# -- the style --------------------------------------------------------------------------------------------------------
@dataclass
class Toggles:
    particles: bool = True
    aura: bool = True                  # aura, outline glow and eye glow
    hair: bool = True
    materials: bool = True
    events: bool = True
    motion: bool = True
    light: bool = False                # light quality: half the particles, fewer frames


class StyleFX:
    def __init__(self, style: dict | None = None, seed: int = 7) -> None:
        self.style = style or {}
        self.seed = seed
        self.toggles = Toggles()
        self._rng = random.Random(seed)
        self._events: list[dict] = []
        self._active: list[tuple[dict, float, float, float]] = []   # (event, started, length, its seed)
        self._trail: list[tuple[QPointF, float, float]] = []                # (screen point, born, size)
        self._particles = self._make_particles()
        self._schedule_all(0.0)
        self.switched_at = -1e9            # for the change-over shimmer
        self.palette: dict = {}            # the skin's colours (her particles inside her use them)

    # -- setup -----------------------------------------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self.style)

    def set_style(self, style: dict | None, now: float, palette: dict | None = None) -> None:
        self.style = style or {}
        self.palette = dict(palette or {})
        self._particles = self._make_particles()
        self._active = []
        self._trail = []
        self._schedule_all(now)
        self.switched_at = now

    def _make_particles(self) -> list[tuple]:
        out = []
        rng = random.Random(self.seed * 31 + 5)
        for spec in self.style.get("particles", [])[:8]:
            kind = spec.get("kind", "dust")
            if kind not in PARTICLE_KINDS:
                continue
            colours = [colour(c) for c in (spec.get("colors") or ["#ffffff"])][:6]
            n = max(0, min(MAX_PARTICLES, int(spec.get("count", 10))))
            lo, hi = (spec.get("size") or [1.5, 3.5])[:2]
            motion = spec.get("motion", "drift") if spec.get("motion") in MOTIONS else "drift"
            speed = max(0.1, min(4.0, float(spec.get("speed", 1.0))))
            layer = spec.get("layer", "auto")
            for i in range(n):
                out.append((kind, motion, layer, rng.choice(colours), rng.uniform(float(lo), float(hi)),
                            rng.uniform(4.0, 9.0) / speed, rng.random(), rng.random(), rng.random(),
                            rng.uniform(-1, 1), rng.uniform(0, 360), i))
        return out

    def _schedule_all(self, now: float) -> None:
        self._events = []
        for e in self.style.get("events", [])[:8]:
            if e.get("kind") not in EVENTS:
                continue
            lo, hi = (e.get("every") or [8, 20])[:2]
            ev = dict(e, every=(max(1.5, float(lo)), max(float(lo), float(hi))))
            ev["next"] = now + self._rng.uniform(*ev["every"]) * 0.5
            self._events.append(ev)

    # -- time ------------------------------------------------------------------------------------------------------
    LENGTH = {"flash": 0.18, "arc": 0.28, "crackle": 0.4, "ice_form": 2.0, "frost": 1.8, "lens_flare": 1.4,
              "solar_flare": 2.2, "eclipse": 4.0, "thorn_vine": 3.0, "glitch": 0.28, "scan_sweep": 1.1,
              "fragments": 1.6, "eye_flicker": 0.5, "ink_burst": 1.4, "transmission": 0.35, "interference": 0.6,
              "status_blink": 1.2, "sparks_feet": 0.7, "petal_burst": 1.8, "gold_shimmer": 1.6, "ripple": 1.6,
              "film_scratch": 0.5, "bloom": 3.0, "warning": 2.2, "chem_bubbles": 2.4, "paper_fold": 1.6,
              "gears": 2.6, "afterimage": 0.9, "vanish": 0.7, "crescent": 4.0, "constellation": 3.2, "halo": 3.0,
              "jellyfish": 7.0, "cloud": 8.0, "wings": 2.4, "stained_glass": 2.6, "distortion": 0.45,
              "static_lines": 0.5, "pulse": 1.6, "frost_bloom": 2.0, "clock_aura": 2.4, "rings": 1.8}

    def tick(self, now: float, idle: bool = True) -> None:
        """Start the events that are due (only while she's idle: not mid-sentence or mid-move)."""
        self._active = [a for a in self._active if now - a[1] < a[2]]
        if not self.toggles.events:
            return
        for ev in self._events:
            if now >= ev["next"]:
                ev["next"] = now + self._rng.uniform(*ev["every"])
                if idle and len(self._active) < 2:          # never a pile-up: two at most at once
                    self._active.append((ev, now, self.LENGTH.get(ev["kind"], 1.5), self._rng.random()))

    def happening(self, kind: str, now: float) -> float | None:
        """How far into a `kind` event she is (0..1), or None."""
        for ev, start, length, _r in self._active:
            if ev["kind"] == kind:
                return min(1.0, (now - start) / length)
        return None

    def moved(self, at: QPointF, speed: float, now: float) -> None:
        """Her window moved (dragged, walking): leave a trail."""
        if not self.toggles.motion or not self.style.get("move") or speed < 60:
            return
        self._trail.append((QPointF(at), now, min(1.0, speed / 1500)))
        self._trail = [tr for tr in self._trail if now - tr[1] < 0.9][-40:]

    # -- painting ----------------------------------------------------------------------------------------------------
    def paint_back(self, p: QPainter, c: Ctx) -> None:
        if not self.active:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.toggles.aura:
            self._aura(p, c)
        if self.toggles.events:
            for ev, start, length, seed in self._active:
                k = min(1.0, (c.t - start) / length)
                getattr(self, "_ev_" + ev["kind"], lambda *a: None)(p, c, k, ev, random.Random(seed), "back")
        if self.toggles.particles:
            self._particles_paint(p, c, back=True)
        if self.toggles.hair:
            self._hair_fx(p, c)
        p.restore()

    def paint_front(self, p: QPainter, c: Ctx, origin: QPointF = QPointF()) -> None:
        """origin: her window's top-left on screen (for movement trails)."""
        if not self.active:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.toggles.hair:
            self._hair_edge(p, c)
        if self.toggles.aura:
            self._eye_glow(p, c)
        if self.toggles.particles:
            self._particles_paint(p, c, back=False)
        if self.toggles.events:
            for ev, start, length, seed in self._active:
                k = min(1.0, (c.t - start) / length)
                getattr(self, "_ev_" + ev["kind"], lambda *a: None)(p, c, k, ev, random.Random(seed), "front")
        if self.toggles.motion:
            self._trail_paint(p, c, origin)
        p.restore()

    def figure(self, img: QImage, c: Ctx) -> None:
        """Her own picture (window-sized, just her): materials drawn on her, clipped to her shape."""
        if not self.active:
            return
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        if self.toggles.particles:
            self._inner(q, c)
        if self.toggles.materials:
            for m in self.style.get("materials", [])[:6]:
                spec = m if isinstance(m, dict) else {"kind": m}
                if spec.get("kind") in MATERIALS:
                    getattr(self, "_mat_" + spec["kind"])(q, c, spec)
        if self.toggles.events:
            for ev, start, length, seed in self._active:
                k = min(1.0, (c.t - start) / length)
                fn = getattr(self, "_on_" + ev["kind"], None)
                if fn is not None:
                    fn(q, c, k, ev, random.Random(seed))
        q.end()

    def draw_figure(self, p: QPainter, img: QImage, c: Ctx) -> None:
        """Her picture onto her window - with the outline glow behind and the filters (RGB split, flicker...)."""
        f = self.style.get("filters", {}) if self.active else {}
        opacity = 1.0 - max(0.0, min(0.6, float(f.get("translucent", 0.0))))
        if self.active and f.get("flicker"):
            r = random.Random(int(c.t * 12))
            if r.random() < float(f["flicker"]) * 0.25:
                opacity *= r.uniform(0.45, 0.85)
        vanish = self.happening("vanish", c.t) if self.toggles.events else None
        if vanish is not None:
            opacity *= 0.35 + 0.65 * abs(math.cos(vanish * math.pi))
        if self.active and self.toggles.aura:
            self._outline(p, img, c)
        if self.active and f.get("rgb_split"):
            d = max(1.0, float(f["rgb_split"])) * c.scale
            self._tinted(p, img, QColor(255, 0, 90, 110), QPointF(-d, 0), opacity)
            self._tinted(p, img, QColor(0, 230, 255, 110), QPointF(d, 0), opacity)
        glitch = self.happening("glitch", c.t) if self.toggles.events else None
        trans = self.happening("transmission", c.t) if self.toggles.events else None
        dist = self.happening("distortion", c.t) if self.toggles.events else None
        p.save()
        p.setOpacity(opacity)
        if glitch is not None or trans is not None or dist is not None:
            self._sliced(p, img, c, glitch, trans, dist)
        else:
            p.drawImage(QPointF(0, 0), img)
        p.restore()
        after = self.happening("afterimage", c.t) if self.toggles.events else None
        if after is not None:
            p.save()
            p.setOpacity(0.35 * (1 - after))
            p.drawImage(QPointF(-c.body.width() * 0.25 * after, 0), img)
            p.restore()
        if c.t - self.switched_at < 0.7:                    # a new style: a bright line sweeps down over her
            self._switch_sweep(p, c, (c.t - self.switched_at) / 0.7)

    # -- aura, outline, eyes -------------------------------------------------------------------------------------
    def _aura(self, p: QPainter, c: Ctx) -> None:
        a = self.style.get("aura")
        if not a:
            return
        pulse = 0.75 + 0.25 * math.sin(c.t * math.tau / max(0.5, float(a.get("pulse", 3.0))))
        if self.happening("pulse", c.t) is not None:
            pulse = 1.25
        centre = QPointF(c.body.center().x(), c.body.top() + c.body.height() * 0.42)
        r = max(c.body.height() * 0.62, c.body.width()) * float(a.get("size", 1.0))
        g = QRadialGradient(centre, r)
        col = colour(a.get("color"), int(float(a.get("alpha", 70)) * pulse))
        g.setColorAt(0, col)
        mid = QColor(col)
        mid.setAlpha(col.alpha() // 3)
        g.setColorAt(0.55, mid)
        g.setColorAt(1, colour(a.get("color"), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.save()
        p.translate(centre)
        p.scale(0.62, 1.0)
        p.translate(-centre)
        p.drawEllipse(centre, r, r)
        p.restore()

    def _outline(self, p: QPainter, img: QImage, c: Ctx) -> None:
        o = self.style.get("outline")
        if not o:
            return
        mode = o.get("mode", "steady")
        col = colour(o.get("color"), int(o.get("alpha", 150)))
        if mode == "pulse":
            col.setAlphaF(col.alphaF() * (0.55 + 0.45 * math.sin(c.t * 2.4)))
        elif mode == "flicker":
            r = random.Random(int(c.t * 10))
            if r.random() < 0.18:
                col.setAlphaF(col.alphaF() * r.uniform(0.0, 0.4))
        elif mode == "rainbow":
            col = QColor.fromHsvF((c.t * 0.08) % 1.0, 0.7, 1.0, col.alphaF())
        elif mode == "fade":
            col.setAlphaF(col.alphaF() * (0.6 + 0.4 * math.sin(c.t * 0.9)))
        w = max(1.0, float(o.get("width", 2.0))) * max(0.7, c.scale)
        tint = self._tint_image(img, col)
        p.save()
        for dx, dy in ((w, 0), (-w, 0), (0, w), (0, -w)):
            p.drawImage(QPointF(dx, dy), tint)
        p.restore()

    def _eye_glow(self, p: QPainter, c: Ctx) -> None:
        e = self.style.get("eyes")
        if not e or not c.eyes:
            return
        alpha = 0.85 + 0.15 * math.sin(c.t * 3.1)
        fl = self.happening("eye_flicker", c.t)
        if fl is not None and int(fl * 10) % 2 == 0:
            alpha *= 0.15
        col = colour(e)
        for at in c.eyes:
            g = QRadialGradient(at, c.eye_r * 3.2)
            core = QColor(col)
            core.setAlphaF(0.95 * alpha)
            g.setColorAt(0, QColor(255, 255, 255, int(220 * alpha)))
            g.setColorAt(0.18, core)
            mid = QColor(col)
            mid.setAlphaF(0.35 * alpha)
            g.setColorAt(0.5, mid)
            g.setColorAt(1, colour(e, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(at, c.eye_r * 3.2, c.eye_r * 3.2)

    # -- hair --------------------------------------------------------------------------------------------------------
    def _hair_spots(self, c: Ctx, n: int, spread: float = 1.0) -> list[tuple[QPointF, float]]:
        """Points round the edge of her hair, with the outward direction (radians)."""
        centre = c.hair_centre
        rx, ry = c.head.width() * 0.95 * spread, c.head.height() * 1.15 * spread
        rng = random.Random(self.seed * 7 + n)
        out = []
        for i in range(n):
            a = math.radians(-172 + 164 * (i + rng.uniform(0.15, 0.85)) / n)
            if c.lying:
                a += math.radians(-12)
            out.append((QPointF(centre.x() + math.cos(a) * rx, centre.y() + math.sin(a) * ry), a))
        return out

    def _hair_fx(self, p: QPainter, c: Ctx) -> None:
        h = self.style.get("hair")
        if not h or h.get("kind") not in HAIR_KINDS:
            return
        kind = h["kind"]
        c1, c2 = colour(h.get("color"), 235), colour(h.get("color2", h.get("color")), 235)
        n = max(2, min(14, int(h.get("count", 7))))
        size = c.head.width() * float(h.get("size", 0.42))
        t = c.t
        if kind == "sun":                                 # rays fanning out from behind her head, turning slowly
            centre = c.hair_centre
            for i in range(14):
                a = math.radians(i * 360 / 14 + t * 6)
                ln = size * (2.0 + 0.4 * math.sin(t * 2 + i))
                path = _poly([(0, 0), (math.cos(a - 0.08) * ln, math.sin(a - 0.08) * ln),
                              (math.cos(a + 0.08) * ln, math.sin(a + 0.08) * ln)])
                g = QRadialGradient(QPointF(0, 0), ln)
                g.setColorAt(0, colour(h.get("color"), 150))
                g.setColorAt(1, colour(h.get("color2", h.get("color")), 0))
                p.save()
                p.translate(centre)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawPath(path)
                p.restore()
            return
        for i, (at, a) in enumerate(self._hair_spots(c, n)):
            sway = math.sin(t * 1.3 + i * 1.7)
            ang = math.degrees(a) + 90 + sway * 4
            ln = size * (0.8 + 0.35 * ((i * 37) % 7) / 7)
            p.save()
            p.translate(at)
            p.rotate(ang)                                  # local: pointing "up" = outward
            if kind == "lightning":
                r = random.Random(int(t * 7) + i * 13)
                pts = [QPointF(0, 0)]
                for k in range(1, 5):
                    pts.append(QPointF(r.uniform(-0.3, 0.3) * ln, -ln * k / 4))
                glow = QColor(c2)
                glow.setAlpha(90)
                p.setPen(QPen(glow, max(2.0, ln * 0.12), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPolyline(QPolygonF(pts))
                p.setPen(QPen(c1, max(1.0, ln * 0.045)))
                p.drawPolyline(QPolygonF(pts))
            elif kind in ("crystal", "frost"):
                _shape(p, DIAMOND, QPointF(0, -ln * 0.5), ln * 0.45, 0, colour(h.get("color"), 170),
                       QColor(255, 255, 255, 220), 1.2)
                _shape(p, DIAMOND, QPointF(ln * 0.25, -ln * 0.3), ln * 0.22, 25, colour(h.get("color2"), 150))
            elif kind == "flame":
                flick = 1 + 0.18 * math.sin(t * 9 + i * 2.3)
                path = QPainterPath(QPointF(-ln * 0.22, 0))
                path.cubicTo(QPointF(-ln * 0.3, -ln * 0.5 * flick), QPointF(ln * 0.1 * sway, -ln * 0.7 * flick),
                             QPointF(ln * 0.05 * sway, -ln * 1.05 * flick))
                path.cubicTo(QPointF(ln * 0.25, -ln * 0.55 * flick), QPointF(ln * 0.3, -ln * 0.2), QPointF(ln * 0.22, 0))
                path.closeSubpath()
                g = QLinearGradient(QPointF(0, 0), QPointF(0, -ln))
                g.setColorAt(0, c1)
                g.setColorAt(1, colour(h.get("color2"), 30))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawPath(path)
            elif kind in ("thorn", "insect", "fin"):
                bend = 0.25 if kind == "thorn" else (0.45 if kind == "insect" else -0.35)
                path = QPainterPath(QPointF(-ln * 0.12, 0))
                path.quadTo(QPointF(ln * bend * 0.5, -ln * 0.5), QPointF(ln * bend, -ln))
                path.quadTo(QPointF(ln * 0.2, -ln * 0.4), QPointF(ln * 0.12, 0))
                path.closeSubpath()
                p.setPen(QPen(c2, 1.2))
                p.setBrush(c1)
                p.drawPath(path)
                if kind == "insect":
                    p.setPen(QPen(c2, 1.0))
                    for k in (0.3, 0.55):
                        p.drawLine(QPointF(-ln * 0.08, -ln * k), QPointF(ln * 0.18, -ln * k))
            elif kind == "leaf":
                _shape(p, LEAF, QPointF(0, -ln * 0.5), ln * 0.5, sway * 8, c1, c2, 1.0)
                p.setPen(QPen(c2, 1.0))
                p.drawLine(QPointF(0, -ln * 0.05), QPointF(0, -ln * 0.95))
            elif kind == "cloud":
                puff = QColor(c1)
                for k, (dx, dy, rr) in enumerate(((0, -0.35, 0.42), (-0.32, -0.15, 0.3), (0.3, -0.18, 0.32))):
                    puff.setAlpha(200 - k * 20)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(puff)
                    p.drawEllipse(QPointF(dx * ln, dy * ln + math.sin(t + i) * 1.5), rr * ln, rr * ln)
            elif kind in ("petal", "rose"):
                for k in range(5 if kind == "petal" else 7):
                    aa = k * (72 if kind == "petal" else 51) + t * 4
                    p.save()
                    p.rotate(aa)
                    _shape(p, PETAL, QPointF(0, -ln * 0.22), ln * 0.2, 0, c1 if k % 2 else c2)
                    p.restore()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 236, 160, 220))
                p.drawEllipse(QPointF(0, 0), ln * 0.08, ln * 0.08)
            elif kind == "gear":
                _shape(p, GEAR, QPointF(0, -ln * 0.3), ln * 0.32, t * 40 * (1 if i % 2 else -1), c1, c2, 1.0)
            elif kind == "glass":
                g = QLinearGradient(QPointF(-ln * 0.2, 0), QPointF(ln * 0.2, -ln))
                g.setColorAt(0, colour(h.get("color"), 150))
                g.setColorAt(1, QColor(255, 255, 255, 60))
                path = _poly([(-ln * 0.16, 0), (0, -ln), (ln * 0.16, 0)])
                p.setPen(QPen(QColor(255, 255, 255, 170), 1.0))
                p.setBrush(g)
                p.drawPath(path)
            elif kind == "ornament":
                _shape(p, DIAMOND, QPointF(0, -ln * 0.35), ln * 0.18, 0, c1, c2, 1.0)
                p.setPen(QPen(c1, 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(-ln * 0.25, -ln * 0.3, ln * 0.5, ln * 0.5), 0, 180 * 16)
            elif kind == "shadow":
                path = QPainterPath(QPointF(-ln * 0.15, 0))
                path.cubicTo(QPointF(-ln * 0.3 + sway * 4, -ln * 0.5), QPointF(ln * 0.2, -ln * 0.6),
                             QPointF(sway * ln * 0.2, -ln * 1.1))
                path.cubicTo(QPointF(ln * 0.1, -ln * 0.5), QPointF(ln * 0.2, -ln * 0.2), QPointF(ln * 0.15, 0))
                p.setPen(QPen(c2, 1.2))
                p.setBrush(c1)
                p.drawPath(path)
            elif kind == "paper":
                for k in range(3):
                    sh = QColor(0, 0, 0, 50)
                    tri = _poly([(-ln * 0.2, 0), (ln * (0.05 + 0.1 * k), -ln * (0.75 - 0.15 * k)), (ln * 0.2, 0)])
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(sh)
                    p.drawPath(tri.translated(2, 2))
                    p.setBrush(c1 if k % 2 == 0 else c2)
                    p.drawPath(tri)
            elif kind == "tendril":
                path = QPainterPath(QPointF(0, 0))
                for k in range(1, 7):
                    path.lineTo(QPointF(math.sin(t * 1.6 + k * 0.9 + i) * ln * 0.18, -ln * k / 5))
                pen = QPen(colour(h.get("color"), 150), max(1.5, ln * 0.09), Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            elif kind in ("static", "pixel"):
                r = random.Random(int(t * (10 if kind == "static" else 4)) + i * 31)
                p.setPen(Qt.PenStyle.NoPen)
                for _k in range(4):
                    s = r.uniform(2, ln * 0.18)
                    p.setBrush(c1 if r.random() < 0.6 else c2)
                    p.drawRect(QRectF(r.uniform(-ln * 0.3, ln * 0.3), -r.uniform(0, ln * 0.8), s, s))
            p.restore()

    def _hair_edge(self, p: QPainter, c: Ctx) -> None:
        """A glowing line along her hair - drawn once per change of her hair's shape and reused (it's the
        costly part), breathing with the opacity."""
        e = self.style.get("hair_edge")
        if not e:
            return
        device = p.device()
        dpr = device.devicePixelRatioF() if device is not None else 1.0
        key = (c.hair_key, round(c.win.width()), round(c.win.height()), dpr, id(e))
        cached = getattr(self, "_edge_cache", None)
        if c.hair_key == () or cached is None or cached[0] != key:
            path = c.hair_path()
            if path is None:
                return
            col = colour(e.get("color"), int(e.get("alpha", 200)))
            w = max(1.0, float(e.get("width", 1.6))) * max(0.7, c.scale)
            img = QImage(max(1, round(c.win.width() * dpr)), max(1, round(c.win.height() * dpr)),
                         QImage.Format.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(0)
            q = QPainter(img)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            glow = QColor(col)
            glow.setAlphaF(col.alphaF() * 0.35)
            q.setPen(QPen(glow, w * 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            q.drawPath(path)
            q.setPen(QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            q.drawPath(path)
            q.end()
            self._edge_cache = cached = (key, img)
        p.save()
        p.setOpacity(0.7 + 0.3 * math.sin(c.t * 2.2))
        p.drawImage(QPointF(c.win.left(), c.win.top()), cached[1])
        p.restore()

    # -- particles ---------------------------------------------------------------------------------------------------
    def _particles_paint(self, p: QPainter, c: Ctx, back: bool) -> None:
        box = c.around
        if box.isEmpty():
            return
        bright = 1.4 if self.happening("pulse", c.t) is not None else 1.0
        body_c = QPointF(c.body.center().x(), c.body.top() + c.body.height() * 0.45)
        step = 2 if self.toggles.light else 1
        for idx, (kind, motion, layer, col, size, period, phase, x0, y0, wob, ang, i) in enumerate(self._particles):
            if idx % step:
                continue
            u = ((c.t / period) + phase) % 1.0
            fade = math.sin(math.pi * u)
            s = size * max(0.7, c.scale)
            spin = ang + c.t * 40 * wob
            depth_front = True
            if motion == "rise":
                at = QPointF(box.left() + x0 * box.width() + math.sin(math.tau * (u * 1.3 + phase)) * box.width() * 0.04,
                             box.bottom() - u * box.height())
            elif motion == "fall":
                at = QPointF(box.left() + x0 * box.width() + math.sin(math.tau * (u * 1.1 + phase)) * box.width() * 0.06,
                             box.top() + u * box.height())
            elif motion == "drift":
                at = QPointF(box.left() + ((x0 + u * 0.6 * (1 if wob > 0 else -1)) % 1.0) * box.width(),
                             box.top() + y0 * box.height() + math.sin(math.tau * (u * 2 + phase)) * box.height() * 0.03)
            elif motion == "orbit":
                a = math.tau * (u + phase)
                rx, ry = c.body.width() * (0.75 + 0.35 * x0), c.body.height() * (0.08 + 0.1 * y0)
                cy = c.body.top() + c.body.height() * (0.15 + 0.7 * y0)
                at = QPointF(body_c.x() + math.cos(a) * rx, cy + math.sin(a) * ry)
                depth_front = math.sin(a) > 0
                fade = 0.85
            elif motion == "hover":
                at = QPointF(box.left() + x0 * box.width() + math.sin(c.t * 0.7 + i) * 3,
                             box.top() + y0 * box.height() + math.cos(c.t * 0.9 + i) * 3)
                fade = 0.5 + 0.5 * math.sin(c.t * 1.4 + i * 1.7)
            elif motion == "emit":
                a = math.tau * x0
                start = QPointF(body_c.x() + math.cos(a) * c.body.width() * 0.35,
                                body_c.y() + math.sin(a) * c.body.height() * 0.45)
                at = start + QPointF(math.cos(a), math.sin(a) - 0.4) * u * c.body.width() * 0.7
                fade = 1 - u
            elif motion == "swirl":
                a = math.tau * (2 * u + phase)
                rr = c.body.width() * (0.9 - 0.4 * u)
                at = QPointF(body_c.x() + math.cos(a) * rr, c.body.bottom() - u * c.body.height() * 1.05)
                depth_front = math.sin(a) > 0
            else:  # ground
                at = QPointF(c.feet.x() + (x0 - 0.5) * c.body.width() * 2.2 + math.sin(c.t * 0.4 + i) * 8,
                             c.feet.y() - c.body.height() * 0.04 * (0.3 + y0))
                fade = 0.6 + 0.4 * math.sin(c.t * 0.5 + i)
            if layer == "back":
                front = False
            elif layer == "front":
                front = True
            else:
                front = depth_front if motion in ("orbit", "swirl") else (i % 3 != 0)
            if front == back:
                continue
            if not box.adjusted(-20, -20, 20, 20).contains(at):
                continue
            draw_particle(p, kind, at, s, col, fade * bright, spin, c.t)

    def _trail_paint(self, p: QPainter, c: Ctx, origin: QPointF) -> None:
        m = self.style.get("move")
        if not m or not self._trail:
            return
        kind = m.get("kind", "trail")
        col = colour(m.get("color"))
        for k, (pt, born, amount) in enumerate(self._trail):
            age = (c.t - born) / 0.9
            if age >= 1:
                continue
            local = pt - origin
            a = (1 - age) * amount
            if kind in ("trail", "rainbow"):
                cc = QColor.fromHsvF((born * 0.6) % 1.0, 0.75, 1.0) if kind == "rainbow" else QColor(col)
                cc.setAlphaF(0.55 * a)
                p.setPen(QPen(cc, max(2.0, c.body.width() * 0.05 * (1 - age)), Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap))
                for frac in (0.3, 0.55, 0.8):
                    y = local.y() - c.body.height() * frac
                    p.drawLine(QPointF(local.x(), y), QPointF(local.x() - (c.moving.x() * 0.05 or 10), y))
            else:
                r = random.Random(int(born * 1000) + k)
                pk = {"ember": "ember", "frost": "crystal", "petals": "petal", "sparks": "spark", "ink": "ink",
                      "bubbles": "bubble", "pixels": "pixel", "afterimage": "mist"}.get(kind, "spark")
                for _j in range(3):
                    at = local + QPointF(r.uniform(-1, 1) * c.body.width() * 0.4,
                                         -r.uniform(0.05, 1.0) * c.body.height() - age * 20)
                    draw_particle(p, pk, at, r.uniform(2, 4) * max(0.7, c.scale), col, a, r.uniform(0, 360), c.t)

    INNER_KIND = {"spark": "spark", "snow": "snow", "spore": "spore", "ember": "ember", "petal": "petal",
                  "rose": "petal", "sakura": "petal", "star": "star", "pixel": "pixel", "static": "pixel",
                  "bubble": "orb", "droplet": "orb", "gear": "dust", "paper": "dust", "geo": "star", "orb": "orb",
                  "dust": "dust", "pollen": "pollen", "fragment": "pixel", "glyph": "pixel", "crystal": "spark",
                  "ink": "dust", "mist": "dust", "leaf": "spore", "moon": "star", "bud": "petal"}

    def _inner(self, q: QPainter, c: Ctx) -> None:
        """Little particles inside her, in her style's colours, drifting up through her (only on her - SourceAtop)."""
        inner = self.style.get("inner") or {}                # a style can say what floats inside her (2.6)
        first = (self.style.get("particles") or [{}])[0].get("kind", "spark")
        kind = inner.get("kind") if inner.get("kind") in PARTICLE_KINDS else self.INNER_KIND.get(first, "spark")
        lo, hi = (inner.get("size") or [1.2, 2.6])[:2]
        pal = self.palette or {}
        cols = [colour(x) for x in (pal.get("hair"), pal.get("accent"), self.style.get("eyes"),
                                    self.style.get("sparkle")) if x]
        cols = [cc.lighter(135) for cc in cols] or [QColor(255, 255, 255)]
        if inner.get("colors"):
            cols = [colour(x) for x in inner["colors"][:6]]
        n = max(4, min(60, int(inner.get("count", 30))))
        if self.toggles.light:
            n //= 2
        b = c.body.united(c.head.adjusted(-c.head.width() * 0.6, -c.head.height() * 0.9, c.head.width() * 0.6, 0))
        rng = random.Random(self.seed * 13 + 3)
        for i in range(n):
            x0, period, phase = rng.random(), rng.uniform(5.0, 10.0), rng.random()
            size = rng.uniform(float(lo), float(hi)) * max(0.7, c.scale)
            u = ((c.t / period) + phase) % 1.0
            at = QPointF(b.left() + x0 * b.width() + math.sin(math.tau * (u * 1.6 + phase)) * b.width() * 0.03,
                         b.bottom() - u * b.height())
            twinkle = math.sin(math.pi * u) * (0.55 + 0.45 * math.sin(c.t * 3.3 + i * 1.9))
            draw_particle(q, kind, at, size, cols[i % len(cols)], min(1.0, twinkle * 1.15), rng.uniform(0, 360) + c.t * 30, c.t)

    # -- materials (drawn on her picture, SourceAtop) --------------------------------------------------------------------
    def _mat_gloss(self, q: QPainter, c: Ctx, spec: dict) -> None:
        x = c.body.left() + ((c.t * 0.12) % 1.6 - 0.3) * c.body.width() * 1.4
        g = QLinearGradient(QPointF(x - 30, c.body.top()), QPointF(x + 30, c.body.top() + 40))
        g.setColorAt(0, QColor(255, 255, 255, 0))
        g.setColorAt(0.5, colour(spec.get("color", "#ffffff"), int(spec.get("alpha", 90))))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        q.fillRect(c.win, g)

    def _mat_sheen(self, q: QPainter, c: Ctx, spec: dict) -> None:
        g = QLinearGradient(c.body.topLeft(), c.body.bottomRight())
        g.setColorAt(0, colour(spec.get("color", "#ffffff"), int(spec.get("alpha", 70))))
        g.setColorAt(0.5, QColor(0, 0, 0, 0))
        g.setColorAt(1, colour(spec.get("color2", spec.get("color", "#ffffff")), int(spec.get("alpha", 70)) // 2))
        q.fillRect(c.win, g)

    def _mat_shade(self, q: QPainter, c: Ctx, spec: dict) -> None:
        g = QLinearGradient(QPointF(0, c.body.top()), QPointF(0, c.body.bottom()))
        g.setColorAt(0, colour(spec.get("color", "#000000"), 0))
        g.setColorAt(1, colour(spec.get("color", "#000000"), int(spec.get("alpha", 120))))
        q.fillRect(c.win, g)

    def _mat_ice(self, q: QPainter, c: Ctx, spec: dict) -> None:
        q.fillRect(c.win, colour(spec.get("color", "#bff4ff"), 60))
        self._mat_facets(q, c, {"color": "#ffffff", "alpha": 120})

    def _mat_facets(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "facets", lambda p: self._draw_facets(p, c, spec))

    def _draw_facets(self, q: QPainter, c: Ctx, spec: dict) -> None:
        r = random.Random(self.seed * 3 + 1)
        q.setPen(QPen(colour(spec.get("color", "#ffffff"), int(spec.get("alpha", 100))), 1.0))
        for _i in range(16):
            x, y = c.body.left() + r.random() * c.body.width(), c.body.top() + r.random() * c.body.height()
            ln = c.body.width() * r.uniform(0.1, 0.3)
            a = r.uniform(0, math.pi)
            q.drawLine(QPointF(x, y), QPointF(x + math.cos(a) * ln, y + math.sin(a) * ln))

    def _lines(self, c: Ctx, n: int, seed: int, length: float = 0.3, kink: float = 0.6) -> list[list[QPointF]]:
        """Jagged lines over her body, made the same every frame (veins, cracks, gold repairs)."""
        r = random.Random(self.seed * 101 + seed)
        out = []
        for _i in range(n):
            x, y = r.uniform(0.25, 0.75), r.uniform(0.18, 0.95)
            pts = [QPointF(c.body.left() + x * c.body.width(), c.body.top() + y * c.body.height())]
            a = r.uniform(0, math.tau)
            for _k in range(r.randint(3, 6)):
                a += r.uniform(-kink, kink)
                step = c.body.height() * length / 5
                last = pts[-1]
                pts.append(QPointF(last.x() + math.cos(a) * step * 0.6, last.y() + math.sin(a) * step))
            out.append(pts)
        return out

    def _glow_lines(self, q: QPainter, lines, col: QColor, width: float, pulse: float) -> None:
        glow = QColor(col)
        glow.setAlphaF(col.alphaF() * 0.35 * pulse)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(glow, width * 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for pts in lines:
            q.drawPolyline(QPolygonF(pts))
        core = QColor(col)
        core.setAlphaF(col.alphaF() * pulse)
        q.setPen(QPen(core, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for pts in lines:
            q.drawPolyline(QPolygonF(pts))

    def _layer(self, q: QPainter, c: Ctx, name: str, draw, opacity: float = 1.0) -> None:
        """A pattern that only depends on her size (veins, cracks, gold lines, plates...): drawn once into its own
        picture, then just placed on her each frame (moving with her) - much cheaper than drawing it every time."""
        device = q.device()
        dpr = device.devicePixelRatioF() if device is not None else 1.0
        pad = 24.0
        key = (name, round(c.body.width()), round(c.body.height()), round(c.head.width()), dpr)
        cache = self.__dict__.setdefault("_layers", {})
        if cache.get(name, (None,))[0] != key:
            w, h = c.body.width() + pad * 2, c.body.height() + pad * 2 + c.head.height()
            img = QImage(max(1, round(w * dpr)), max(1, round(h * dpr)), QImage.Format.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(0)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            origin = QPointF(c.body.left() - pad, c.body.top() - pad - c.head.height())
            p.translate(-origin)
            draw(p)
            p.end()
            cache[name] = (key, img)
        img = cache[name][1]
        q.save()
        q.setOpacity(opacity)
        q.drawImage(QPointF(c.body.left() - pad, c.body.top() - pad - c.head.height()), img)
        q.restore()

    def _mat_veins(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "veins", lambda p: self._glow_lines(
            p, self._lines(c, int(spec.get("count", 9)), 1, 0.35, 0.9), colour(spec.get("color", "#7dff3a"), 210),
            max(1.0, c.scale), 1.0), 0.6 + 0.4 * math.sin(c.t * 1.8))

    def _mat_cracks(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "cracks", lambda p: self._glow_lines(
            p, self._lines(c, int(spec.get("count", 7)), 2, 0.28, 1.2), colour(spec.get("color", "#ff3b1f"), 230),
            max(1.0, c.scale * 1.2), 1.0), 0.55 + 0.45 * math.sin(c.t * 1.3 + 1))

    def _mat_kintsugi(self, q: QPainter, c: Ctx, spec: dict) -> None:
        lines = self._lines(c, int(spec.get("count", 8)), 3, 0.32, 1.0)
        gold = colour(spec.get("color", "#f2c14e"), 240)
        self._layer(q, c, "kintsugi", lambda p: self._glow_lines(p, lines, gold, max(1.2, c.scale * 1.3), 0.95))
        shine = self.happening("gold_shimmer", c.t)
        if shine is not None:                              # a bright spark running along each repair
            for pts in lines:
                k = min(len(pts) - 1.001, shine * (len(pts) - 1))
                i = int(k)
                at = pts[i] + (pts[i + 1] - pts[i]) * (k - i)
                _glow_dot(q, at, 2.2 * max(1.0, c.scale), QColor(255, 248, 210), 1.0)

    def _mat_stripes(self, q: QPainter, c: Ctx, spec: dict) -> None:
        col = colour(spec.get("color", "#ffffff"), int(spec.get("alpha", 170)))
        q.save()
        q.translate(c.body.center())
        q.rotate(-14)
        w = c.body.width() * 0.07
        for k, off in enumerate((-w * 2.2, -w * 0.6)):
            q.fillRect(QRectF(off, -c.body.height(), w * (1 if k else 0.5), c.body.height() * 2), col)
        q.restore()

    def _mat_scan(self, q: QPainter, c: Ctx, spec: dict) -> None:
        col = colour(spec.get("color", "#000000"), int(spec.get("alpha", 60)))
        step = max(2.0, 3 * c.scale)
        y = c.body.top() - c.body.height() * 0.3 + (c.t * 12) % step
        while y < c.body.bottom():
            q.fillRect(QRectF(c.win.left(), y, c.win.width(), 1), col)
            y += step

    def _mat_grain(self, q: QPainter, c: Ctx, spec: dict) -> None:
        r = random.Random(int(c.t * 18))
        q.setPen(Qt.PenStyle.NoPen)
        a = int(spec.get("alpha", 60))
        for _i in range(int(140 * (0.5 if self.toggles.light else 1))):
            x, y = r.uniform(c.body.left() - 20, c.body.right() + 20), r.uniform(c.body.top() - 40, c.body.bottom())
            q.setBrush(QColor(255, 255, 255, a) if r.random() < 0.5 else QColor(0, 0, 0, a))
            q.drawRect(QRectF(x, y, 1.4, 1.4))

    def _mat_caustics(self, q: QPainter, c: Ctx, spec: dict) -> None:
        col = colour(spec.get("color", "#7ff3ff"), int(spec.get("alpha", 70)))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(col, max(1.0, c.scale * 1.4)))
        for k in range(7):
            path = QPainterPath()
            y0 = c.body.top() + c.body.height() * (k + 0.5) / 7
            for j in range(13):
                x = c.body.left() - 20 + (c.body.width() + 40) * j / 12
                y = y0 + math.sin(c.t * 1.2 + j * 0.9 + k * 1.7) * c.body.height() * 0.025
                path.moveTo(x, y) if j == 0 else path.lineTo(x, y)
            q.drawPath(path)

    def _mat_rainbow(self, q: QPainter, c: Ctx, spec: dict) -> None:
        g = QLinearGradient(c.body.topLeft(), c.body.bottomRight())
        shift = c.t * 0.07
        a = int(spec.get("alpha", 90))
        for k in range(6):
            g.setColorAt(k / 5, QColor.fromHsvF((shift + k / 6) % 1.0, 0.8, 1.0, a / 255))
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        q.fillRect(c.win, g)

    def _mat_crt(self, q: QPainter, c: Ctx, spec: dict) -> None:
        q.fillRect(c.win, colour(spec.get("color", "#ffb000"), int(spec.get("alpha", 50))))
        self._mat_scan(q, c, {"color": "#1a0e00", "alpha": 80})

    def _mat_warm(self, q: QPainter, c: Ctx, spec: dict) -> None:
        g = QLinearGradient(QPointF(c.body.left(), c.body.top()), QPointF(c.body.right(), c.body.bottom()))
        g.setColorAt(0, colour(spec.get("color", "#ffd8a0"), int(spec.get("alpha", 60))))
        g.setColorAt(1, colour(spec.get("color2", "#6b3a1f"), int(spec.get("alpha", 60))))
        q.fillRect(c.win, g)

    def _mat_paper(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "paper", lambda p: self._draw_paper(p, c, spec))

    def _draw_paper(self, q: QPainter, c: Ctx, spec: dict) -> None:
        r = random.Random(self.seed * 5)
        q.setPen(Qt.PenStyle.NoPen)
        for _i in range(90):
            x, y = r.uniform(c.body.left(), c.body.right()), r.uniform(c.body.top() - 30, c.body.bottom())
            q.setBrush(QColor(255, 250, 235, 30) if r.random() < 0.5 else QColor(120, 90, 60, 22))
            q.drawEllipse(QPointF(x, y), r.uniform(1, 3), r.uniform(1, 3))
        q.setPen(QPen(QColor(90, 60, 40, 60), 1.0))
        for _i in range(10):                                # cut lines
            x, y = r.uniform(c.body.left(), c.body.right()), r.uniform(c.body.top(), c.body.bottom())
            q.drawLine(QPointF(x, y), QPointF(x + r.uniform(-12, 12), y + r.uniform(4, 14)))

    def _mat_porcelain(self, q: QPainter, c: Ctx, spec: dict) -> None:
        g = QRadialGradient(QPointF(c.body.center().x() - c.body.width() * 0.15, c.body.top() + c.body.height() * 0.3),
                            c.body.height() * 0.6)
        g.setColorAt(0, QColor(255, 255, 255, 80))
        g.setColorAt(1, QColor(200, 205, 215, 0))
        q.fillRect(c.win, g)

    def _mat_segments(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "segments", lambda p: self._draw_segments(p, c, spec))

    def _draw_segments(self, q: QPainter, c: Ctx, spec: dict) -> None:
        col = colour(spec.get("color", "#000000"), int(spec.get("alpha", 120)))
        hi = colour(spec.get("color2", "#ffffff"), 70)
        for k in range(14):
            y = c.body.top() + c.body.height() * (0.2 + 0.78 * k / 14)
            q.fillRect(QRectF(c.win.left(), y, c.win.width(), max(1.0, c.scale)), col)
            q.fillRect(QRectF(c.win.left(), y + max(1.0, c.scale), c.win.width(), 1), hi)

    def _joint_points(self, c: Ctx) -> list[QPointF]:
        b = c.body
        return [QPointF(b.left() + b.width() * fx, b.top() + b.height() * fy) for fx, fy in
                ((0.33, 0.22), (0.67, 0.22), (0.24, 0.38), (0.76, 0.38), (0.42, 0.72), (0.58, 0.72), (0.5, 0.45))]

    def _mat_joints(self, q: QPainter, c: Ctx, spec: dict) -> None:
        ring = colour(spec.get("color", "#c8d2dc"), 200)
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.setPen(QPen(ring, max(1.0, c.scale)))
        for i, at in enumerate(self._joint_points(c)):
            q.drawEllipse(at, 3.2 * max(0.8, c.scale), 3.2 * max(0.8, c.scale))
            blink = self.happening("status_blink", c.t)
            on = (blink is not None and (int(blink * 8) + i) % 2 == 0) or int(c.t * 0.8 + i) % 5 == 0
            if on:
                _glow_dot(q, at, 1.6 * max(0.8, c.scale), colour(spec.get("light", "#3fd8ff")), 1.0)

    def _mat_ornament(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "ornament", lambda p: self._draw_ornament(p, c, spec))

    def _draw_ornament(self, q: QPainter, c: Ctx, spec: dict) -> None:
        gold = colour(spec.get("color", "#d4a64a"), int(spec.get("alpha", 200)))
        q.setPen(QPen(gold, max(1.0, c.scale)))
        q.setBrush(Qt.BrushStyle.NoBrush)
        b = c.body
        cx = b.center().x()
        for k, fy in enumerate((0.3, 0.42, 0.55)):
            y = b.top() + b.height() * fy
            w = b.width() * (0.22 - 0.04 * k)
            q.drawArc(QRectF(cx - w, y - w * 0.4, w, w * 0.8), 0, 180 * 16)
            q.drawArc(QRectF(cx, y - w * 0.4, w, w * 0.8), 0, 180 * 16)
            _shape(q, DIAMOND, QPointF(cx, y), 2.2 * max(0.8, c.scale), 0, gold)

    def _mat_markings(self, q: QPainter, c: Ctx, spec: dict) -> None:
        self._layer(q, c, "markings", lambda p: self._draw_markings(p, c, spec))

    def _draw_markings(self, q: QPainter, c: Ctx, spec: dict) -> None:
        col = colour(spec.get("color", "#b6ff3a"), 220)
        pulse = 1.0
        b = c.body
        lines = [[QPointF(b.left() + b.width() * x, b.top() + b.height() * y) for x, y in pts] for pts in
                 (((0.4, 0.28), (0.5, 0.36), (0.6, 0.28)), ((0.38, 0.52), (0.46, 0.6), (0.4, 0.68)),
                  ((0.62, 0.52), (0.54, 0.6), (0.6, 0.68)), ((0.45, 0.8), (0.5, 0.86), (0.55, 0.8)))]
        self._glow_lines(q, lines, col, max(1.0, c.scale), pulse)

    # -- events --------------------------------------------------------------------------------------------------------
    # (_ev_<kind>(p, c, k, ev, rng, layer): drawn round her; _on_<kind>(q, c, k, ev, rng): drawn on her)
    def _on_flash(self, q, c, k, ev, r) -> None:
        q.fillRect(c.win, colour(ev.get("color", "#ffffff"), int(170 * (1 - k))))

    def _ev_flash(self, p, c, k, ev, r, layer) -> None:
        if layer == "back":
            g = QRadialGradient(c.body.center(), c.body.height())
            g.setColorAt(0, colour(ev.get("color", "#ffffff"), int(90 * (1 - k))))
            g.setColorAt(1, colour(ev.get("color", "#ffffff"), 0))
            p.fillRect(c.win, g)

    def _bolt(self, p, a: QPointF, b: QPointF, r: random.Random, col: QColor, width: float, alpha: float) -> None:
        pts = [a]
        for i in range(1, 7):
            f = i / 7
            mid = a + (b - a) * f
            nx, ny = -(b - a).y(), (b - a).x()
            ln = math.hypot(nx, ny) or 1
            off = r.uniform(-0.18, 0.18) * ln
            pts.append(mid + QPointF(nx / ln * off * 0.25, ny / ln * off * 0.25))
        pts.append(b)
        glow = QColor(col)
        glow.setAlphaF(0.35 * alpha)
        p.setPen(QPen(glow, width * 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPolyline(QPolygonF(pts))
        core = QColor(255, 255, 255)
        core.setAlphaF(alpha)
        p.setPen(QPen(core, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPolyline(QPolygonF(pts))

    def _ev_arc(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(c.t * 20) + int(r.random() * 1000))
        a = QPointF(c.hair_centre.x() + rr.uniform(-1, 1) * c.head.width() * 0.8, c.head.top() + rr.uniform(0, 1) * c.head.height())
        b = QPointF(c.body.center().x() + rr.uniform(-1, 1) * c.body.width() * 0.25,
                    c.body.top() + c.body.height() * rr.uniform(0.3, 0.7))
        self._bolt(p, a, b, rr, colour(ev.get("color", "#b388ff")), max(1.0, c.scale), 1 - k)

    def _ev_crackle(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(c.t * 25) + 7)
        for _i in range(3):
            a = QPointF(c.hair_centre.x() + rr.uniform(-1.2, 1.2) * c.head.width(), c.head.top() + rr.uniform(-0.6, 0.8) * c.head.height())
            b = a + QPointF(rr.uniform(-1, 1) * c.head.width() * 0.6, rr.uniform(-1, 1) * c.head.height() * 0.6)
            self._bolt(p, a, b, rr, colour(ev.get("color", "#b388ff")), max(0.8, c.scale * 0.8), (1 - k) * 0.9)

    def _spot(self, c: Ctx, r: random.Random) -> QPointF:
        b = c.around
        return QPointF(b.left() + r.uniform(0.1, 0.9) * b.width(), b.top() + r.uniform(0.15, 0.85) * b.height())

    def _ev_ice_form(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        at = self._spot(c, random.Random(int(r.random() * 99999)))
        grow = min(1.0, k * 3)
        a = math.sin(math.pi * k)
        for j in range(5):
            _shape(p, DIAMOND, at, 7 * grow * max(0.8, c.scale), j * 72, colour(ev.get("color", "#cdf6ff"), int(200 * a)),
                   QColor(255, 255, 255, int(220 * a)), 1.0)

    def _ev_frost(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        a = math.sin(math.pi * k)
        col = colour(ev.get("color", "#dff8ff"), int(200 * a))
        p.setPen(QPen(col, 1.0))
        rr = random.Random(int(r.random() * 1000))
        for _i in range(9):
            x = c.feet.x() + rr.uniform(-1, 1) * c.body.width() * 0.9
            y = c.feet.y() - rr.uniform(0, 6)
            ln = rr.uniform(6, 14) * max(0.8, c.scale) * min(1.0, k * 2.5)
            for aa in (-60, -90, -120):
                d = math.radians(aa)
                p.drawLine(QPointF(x, y), QPointF(x + math.cos(d) * ln, y + math.sin(d) * ln))

    _ev_frost_bloom = _ev_ice_form

    def _ev_lens_flare(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        a = math.sin(math.pi * k)
        start = QPointF(c.head.right(), c.head.top())
        d = QPointF(-c.body.width() * 0.8, c.body.height() * 0.8)
        for j, (f, rr) in enumerate(((0.0, 9), (0.3, 4), (0.55, 7), (0.8, 3))):
            col = colour(ev.get("color", "#ffd27a"), int(110 * a))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(start + d * f, rr * max(0.8, c.scale), rr * max(0.8, c.scale))
        _shape(p, STAR4, start, 14 * a * max(0.8, c.scale), 0, colour("#fff6d8", int(220 * a)))

    def _ev_solar_flare(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        a = math.sin(math.pi * k)
        centre = c.hair_centre
        path = QPainterPath()
        rad = c.head.width() * (1.0 + 0.6 * k)
        a0 = r.uniform(200, 340)
        path.arcMoveTo(QRectF(centre.x() - rad, centre.y() - rad, rad * 2, rad * 2), a0)
        path.arcTo(QRectF(centre.x() - rad, centre.y() - rad, rad * 2, rad * 2), a0, 70)
        col = colour(ev.get("color", "#ff8a00"), int(200 * a))
        p.setBrush(Qt.BrushStyle.NoBrush)
        glow = QColor(col)
        glow.setAlpha(int(70 * a))
        p.setPen(QPen(glow, 10 * max(0.8, c.scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(col, 3 * max(0.8, c.scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)

    def _ring_behind_head(self, p, c, k, col: QColor, fill: QColor | None, size: float, width: float) -> None:
        a = math.sin(math.pi * k)
        centre = c.hair_centre
        rad = c.head.width() * size
        if fill is not None:
            f = QColor(fill)
            f.setAlphaF(fill.alphaF() * a)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(f)
            p.drawEllipse(centre, rad, rad)
        cc = QColor(col)
        cc.setAlphaF(col.alphaF() * a)
        glow = QColor(cc)
        glow.setAlphaF(cc.alphaF() * 0.3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(glow, width * 4))
        p.drawEllipse(centre, rad, rad)
        p.setPen(QPen(cc, width))
        p.drawEllipse(centre, rad, rad)

    def _ev_eclipse(self, p, c, k, ev, r, layer) -> None:
        if layer == "back":
            self._ring_behind_head(p, c, k, colour(ev.get("color", "#dfe6ee"), 230), QColor(4, 2, 10, 230), 1.05,
                                   2.0 * max(0.8, c.scale))

    def _ev_halo(self, p, c, k, ev, r, layer) -> None:
        if layer == "back":
            self._ring_behind_head(p, c, k, colour(ev.get("color", "#f2c14e"), 220), None, 0.95, 1.6 * max(0.8, c.scale))

    def _ev_clock_aura(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        self._ring_behind_head(p, c, k, colour(ev.get("color", "#d4a64a"), 200), None, 1.25, 1.2 * max(0.8, c.scale))
        a = math.sin(math.pi * k)
        centre = c.hair_centre
        for j in range(12):
            d = math.radians(j * 30 + k * 30)
            rad = c.head.width() * 1.25
            p.setPen(QPen(colour(ev.get("color", "#d4a64a"), int(200 * a)), 1.5))
            p.drawLine(centre + QPointF(math.cos(d), math.sin(d)) * rad * 0.9,
                       centre + QPointF(math.cos(d), math.sin(d)) * rad)

    def _ev_rings(self, p, c, k, ev, r, layer) -> None:
        if layer == "back":
            for j in range(3):
                kk = (k + j / 3) % 1.0
                self._ring_behind_head(p, c, kk, colour(ev.get("color", "#ffffff"), 160), None, 0.5 + kk, 1.2)

    def _ev_crescent(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        a = math.sin(math.pi * k)
        at = QPointF(c.hair_centre.x() + c.head.width() * 0.3, c.hair_centre.y() - c.head.height() * 0.2)
        g = QRadialGradient(at, c.head.width() * 1.6)
        g.setColorAt(0, colour(ev.get("color", "#e6ecff"), int(50 * a)))
        g.setColorAt(1, colour(ev.get("color", "#e6ecff"), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(at, c.head.width() * 1.6, c.head.width() * 1.6)
        _shape(p, MOON, at, c.head.width() * 0.95, -20, colour(ev.get("color", "#e6ecff"), int(180 * a)))

    def _ev_constellation(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        a = math.sin(math.pi * k)
        rr = random.Random(int(r.random() * 1000))
        b = c.around
        pts = [QPointF(b.left() + rr.uniform(0.05, 0.95) * b.width(), b.top() + rr.uniform(0.05, 0.6) * b.height())
               for _i in range(6)]
        col = colour(ev.get("color", "#cfd8ff"), int(150 * a))
        p.setPen(QPen(col, 1.0))
        shown = int(len(pts) * min(1.0, k * 2.5))
        for i in range(max(0, shown - 1)):
            p.drawLine(pts[i], pts[i + 1])
        for pt in pts[:shown]:
            _shape(p, STAR4, pt, 4 * max(0.8, c.scale), 0, colour(ev.get("color", "#ffffff"), int(230 * a)))

    def _ev_thorn_vine(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        a = min(1.0, (1 - k) * 3)
        side = -1 if r.random() < 0.5 else 1
        base = QPointF(c.body.center().x() + side * c.body.width() * 0.55, c.feet.y())
        grow = min(1.0, k * 2)
        path = QPainterPath(base)
        n = 12
        pts = []
        for i in range(1, int(n * grow) + 1):
            f = i / n
            pt = QPointF(base.x() + side * math.sin(f * 7) * c.body.width() * 0.12, base.y() - f * c.body.height() * 0.6)
            path.lineTo(pt)
            pts.append(pt)
        col = colour(ev.get("color", "#3a0b14"), int(240 * a))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, 2.2 * max(0.8, c.scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)
        for j, pt in enumerate(pts[::2]):
            _shape(p, TRIANGLE, pt + QPointF(3 * (1 if j % 2 else -1), 0), 3 * max(0.8, c.scale), 90 * (1 if j % 2 else -1), col)

    def _ev_fragments(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(r.random() * 1000))
        out = math.sin(math.pi * k)                        # out and back again
        for _i in range(10):
            a = rr.uniform(0, math.tau)
            start = QPointF(c.body.center().x() + math.cos(a) * c.body.width() * 0.3,
                            c.body.top() + c.body.height() * rr.uniform(0.1, 0.9))
            at = start + QPointF(math.cos(a), math.sin(a)) * out * c.body.width() * 0.5
            draw_particle(p, "fragment", at, rr.uniform(2, 5) * max(0.8, c.scale),
                          colour(rr.choice(ev.get("colors", ["#39ff88", "#ff2bd6", "#ffffff"]))), 0.9, 0)

    def _ev_ink_burst(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(r.random() * 1000))
        for _i in range(8):
            a = rr.uniform(0, math.tau)
            at = c.body.center() + QPointF(math.cos(a), math.sin(a)) * c.body.width() * (0.4 + k * 0.6)
            draw_particle(p, "ink", at, rr.uniform(2, 5) * max(0.8, c.scale), colour(ev.get("color", "#0a0a0a")), 1 - k, 0)

    def _ev_interference(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(c.t * 30))
        col = colour(ev.get("color", "#ffffff"), int(120 * (1 - k)))
        for _i in range(4):
            y = c.around.top() + rr.random() * c.around.height()
            path = QPainterPath()
            for j in range(15):
                x = c.around.left() + c.around.width() * j / 14
                yy = y + math.sin(j * 1.3 + c.t * 20) * 2
                path.moveTo(x, yy) if j == 0 else path.lineTo(x, yy)
            p.setPen(QPen(col, 1.0))
            p.drawPath(path)

    def _ev_static_lines(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(c.t * 30))
        for _i in range(5):
            y = c.around.top() + rr.random() * c.around.height()
            p.fillRect(QRectF(c.around.left(), y, c.around.width(), rr.uniform(1, 3)),
                       colour(ev.get("color", "#ffffff"), int(rr.uniform(60, 160) * (1 - k))))

    def _ev_film_scratch(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(c.t * 14))
        for _i in range(2):
            x = c.around.left() + rr.random() * c.around.width()
            p.setPen(QPen(colour(ev.get("color", "#f4e6c8"), int(rr.uniform(70, 150))), 1.0))
            p.drawLine(QPointF(x, c.around.top()), QPointF(x + rr.uniform(-3, 3), c.around.bottom()))

    def _ev_sparks_feet(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(r.random() * 1000))
        for _i in range(8):
            a = math.radians(rr.uniform(-160, -20))
            sp = rr.uniform(20, 60) * max(0.8, c.scale)
            at = c.feet + QPointF(rr.uniform(-1, 1) * c.body.width() * 0.3, 0) + QPointF(math.cos(a), math.sin(a)) * sp * k
            at += QPointF(0, 40 * k * k)
            draw_particle(p, "spark", at, 2.5 * max(0.8, c.scale), colour(ev.get("color", "#ff3030")), 1 - k, 0)

    def _ev_petal_burst(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(r.random() * 1000))
        for _i in range(10):
            a = rr.uniform(0, math.tau)
            at = c.body.center() + QPointF(math.cos(a), math.sin(a) - 0.3) * c.body.width() * (0.3 + k)
            draw_particle(p, ev.get("particle", "sakura"), at, rr.uniform(3, 5) * max(0.8, c.scale),
                          colour(rr.choice(ev.get("colors", ["#ffb7d0", "#ffffff"]))), 1 - k, rr.uniform(0, 360) + k * 200)

    def _ev_ripple(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        at = QPointF(c.feet.x() + (r.random() - 0.5) * c.body.width() * 1.4, c.feet.y() - 3)
        for j in range(3):
            kk = k - j * 0.15
            if 0 < kk < 1:
                p.setPen(QPen(colour(ev.get("color", "#7ff3ff"), int(180 * (1 - kk))), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(at, c.body.width() * 0.5 * kk, c.body.width() * 0.12 * kk)

    def _ev_bloom(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        at = QPointF(c.feet.x() + (0.35 + r.random() * 0.3) * c.body.width() * (1 if r.random() < 0.5 else -1),
                     c.feet.y() - 4)
        open_ = min(1.0, k * 2.5)
        a = min(1.0, (1 - k) * 3)
        p.setPen(QPen(colour("#4f7d4a", int(220 * a)), 1.5))
        p.drawLine(at, at + QPointF(0, -10 * max(0.8, c.scale)))
        draw_particle(p, "bud", at + QPointF(0, -12 * max(0.8, c.scale)), 6 * open_ * max(0.8, c.scale),
                      colour(ev.get("color", "#ffc4d6")), a, 0)

    def _ev_warning(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        a = math.sin(math.pi * k) * (0.6 + 0.4 * (int(c.t * 6) % 2))
        rr = random.Random(int(r.random() * 1000))
        for _i in range(2):
            at = self._spot(c, rr)
            s = 7 * max(0.8, c.scale)
            _shape(p, TRIANGLE, at, s, 0, None, colour(ev.get("color", "#ffe600"), int(230 * a)), 1.6)
            p.setPen(QPen(colour(ev.get("color", "#ffe600"), int(230 * a)), 1.6))
            p.drawLine(at + QPointF(0, -s * 0.45), at + QPointF(0, s * 0.1))

    def _ev_chem_bubbles(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(r.random() * 1000))
        for _i in range(7):
            x = c.feet.x() + rr.uniform(-1, 1) * c.body.width() * 0.5
            at = QPointF(x + math.sin(k * 8 + x) * 3, c.feet.y() - k * c.body.height() * rr.uniform(0.3, 0.8))
            draw_particle(p, "bubble", at, rr.uniform(2, 4) * max(0.8, c.scale), colour(ev.get("color", "#7dff3a")),
                          1 - k, 0)

    def _ev_paper_fold(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        at = self._spot(c, random.Random(int(r.random() * 1000)))
        s = 8 * max(0.8, c.scale)
        fold = abs(math.cos(k * math.pi * 2))
        p.save()
        p.translate(at)
        p.scale(fold, 1.0)
        _shape(p, TRIANGLE, QPointF(0, 0), s, 180, colour(ev.get("color", "#fff4e0"), int(230 * (1 - k * 0.6))),
               QColor(120, 90, 70, 120), 1.0)
        p.restore()

    def _ev_gears(self, p, c, k, ev, r, layer) -> None:
        if layer != "front":
            return
        rr = random.Random(int(r.random() * 1000))
        a = math.sin(math.pi * k)
        for j in range(3):
            at = self._spot(c, rr)
            draw_particle(p, "gear", at, rr.uniform(4, 8) * max(0.8, c.scale), colour(ev.get("color", "#c89b3c")), a,
                          k * 120 * (1 if j % 2 else -1))

    def _ev_jellyfish(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        b = c.around
        x = b.left() + b.width() * (1.05 - 1.1 * k)
        y = b.top() + b.height() * (0.3 + 0.1 * math.sin(k * 6))
        a = min(1.0, math.sin(math.pi * k) * 1.6) * 0.8
        s = c.body.width() * 0.22
        col = colour(ev.get("color", "#7ff3ff"), int(110 * a))
        p.setPen(QPen(colour(ev.get("color", "#7ff3ff"), int(170 * a)), 1.0))
        p.setBrush(col)
        p.drawChord(QRectF(x - s, y - s * 0.6, s * 2, s * 1.4), 0, 180 * 16)
        for j in range(5):
            tx = x - s * 0.7 + j * s * 0.35
            path = QPainterPath(QPointF(tx, y + s * 0.1))
            for q in range(1, 5):
                path.lineTo(QPointF(tx + math.sin(c.t * 2 + j + q) * 3, y + s * 0.1 + q * s * 0.35))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def _ev_cloud(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        b = c.around
        x = b.left() - b.width() * 0.2 + b.width() * 1.4 * k
        y = b.top() + b.height() * 0.25
        a = math.sin(math.pi * k) * 0.8
        col = colour(ev.get("color", "#ffffff"), int(130 * a))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        s = c.body.width() * 0.2
        for dx, dy, rr in ((0, 0, 1), (-0.9, 0.2, 0.7), (0.9, 0.2, 0.75), (0.4, -0.3, 0.7)):
            p.drawEllipse(QPointF(x + dx * s, y + dy * s), rr * s, rr * s * 0.8)

    def _ev_wings(self, p, c, k, ev, r, layer) -> None:
        if layer != "back":
            return
        a = math.sin(math.pi * k)
        s = (c.body.height() * 0.32) if not c.lying else c.head.height() * 0.9   # her size, not her width
        flap = math.sin(c.t * 14) * s * 0.06
        base = (QPointF(c.body.center().x(), c.body.top() + c.body.height() * 0.28) if not c.lying
                else QPointF(c.head.center().x() + c.head.width() * 0.6, c.head.bottom()))
        col = colour(ev.get("color", "#b6ff3a"), int(80 * a))
        edge = colour(ev.get("color", "#b6ff3a"), int(200 * a))
        for side in (-1, 1):
            path = QPainterPath(base)
            tip = base + QPointF(side * s * 0.95, -s * 0.55 + flap)
            path.quadTo(base + QPointF(side * s * 0.55, -s * 0.85 + flap), tip)
            path.quadTo(base + QPointF(side * s * 0.6, -s * 0.05), base)
            p.setPen(QPen(edge, 1.2))
            p.setBrush(col)
            p.drawPath(path)

    def _on_stained_glass(self, q, c, k, ev, r) -> None:
        a = math.sin(math.pi * k)
        rr = random.Random(int(r.random() * 1000))
        for _i in range(5):
            col = QColor(rr.choice(ev.get("colors", ["#e0a030", "#b02040", "#3060c0", "#40a060"])))
            col.setAlpha(int(90 * a))
            x, y = c.body.left() + rr.random() * c.body.width(), c.body.top() + rr.random() * c.body.height()
            s = c.body.width() * rr.uniform(0.15, 0.3)
            path = _poly([(x, y - s), (x + s * 0.6, y), (x, y + s), (x - s * 0.6, y)])
            q.fillPath(path, col)

    def _on_scan_sweep(self, q, c, k, ev, r) -> None:
        y = c.body.top() - c.body.height() * 0.3 + (c.body.height() * 1.35) * k
        g = QLinearGradient(QPointF(0, y - 10), QPointF(0, y + 2))
        g.setColorAt(0, colour(ev.get("color", "#7ff3ff"), 0))
        g.setColorAt(1, colour(ev.get("color", "#7ff3ff"), 170))
        q.fillRect(QRectF(c.win.left(), y - 10, c.win.width(), 12), g)

    # -- helpers --------------------------------------------------------------------------------------------------------
    def _tint_image(self, img: QImage, col: QColor) -> QImage:
        out = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        out.setDevicePixelRatio(img.devicePixelRatio())
        out.fill(0)
        q = QPainter(out)
        q.drawImage(0, 0, img)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        q.fillRect(out.rect(), col)
        q.end()
        return out

    def _tinted(self, p: QPainter, img: QImage, col: QColor, off: QPointF, opacity: float) -> None:
        p.save()
        p.setOpacity(opacity)
        p.drawImage(off, self._tint_image(img, col))
        p.restore()

    def _sliced(self, p: QPainter, img: QImage, c: Ctx, glitch, trans, dist) -> None:
        dpr = img.devicePixelRatio() or 1.0
        rr = random.Random(int(c.t * 30))
        h = img.height() / dpr
        y = 0.0
        while y < h:
            band = rr.uniform(3, 14)
            shift = 0.0
            if glitch is not None and rr.random() < 0.35:
                shift = rr.choice((-1, 1)) * rr.uniform(3, 12) * c.scale
            if trans is not None and abs(y - (c.body.top() + c.body.height() * rr.random())) < 30:
                shift += rr.uniform(-18, 18) * c.scale
            if dist is not None:
                shift += math.sin(y * 0.08 + c.t * 25) * 4 * c.scale * (1 - dist)
            src = QRectF(0, y * dpr, img.width(), band * dpr)
            p.drawImage(QRectF(shift, y, img.width() / dpr, band), img, src)
            y += band
        if trans is not None:
            p.fillRect(QRectF(c.around.left(), c.body.top() + c.body.height() * rr.random(), c.around.width(), 2),
                       QColor(255, 255, 255, 140))

    def _switch_sweep(self, p: QPainter, c: Ctx, k: float) -> None:
        y = c.around.top() + (c.body.bottom() - c.around.top()) * k
        g = QLinearGradient(QPointF(0, y - 18), QPointF(0, y))
        col = colour((self.style.get("aura") or {}).get("color") or "#ffffff")
        col.setAlpha(0)
        g.setColorAt(0, col)
        col2 = QColor(col)
        col2.setAlpha(200)
        g.setColorAt(1, col2)
        p.fillRect(QRectF(c.around.left(), y - 18, c.around.width(), 20), g)
        for i in range(6):
            draw_particle(p, "spark", QPointF(c.around.left() + c.around.width() * (i + 0.5) / 6, y),
                          2.5, col2, 1 - k, 0)


def ctx_for_rig(rig, feet: QPointF, height: float, pose, win: QRectF, t: float, hair_path: bool = True) -> Ctx:
    """The Ctx for her full-body figure drawn with `rig` at `feet`, `height` px tall."""
    from .rig import EYES
    tr = rig.head_transform(feet, height, pose)
    head = tr.mapRect(QRectF(rig.head))
    s = height / rig.h
    body = QRectF(feet.x() - rig.w * s / 2, feet.y() - height, rig.w * s, height)
    eyes = [tr.map(QPointF(fx * rig.w, fy * rig.h)) for (fx, fy), _r in EYES]
    eye_r = EYES[0][1] * rig.w * s
    c = Ctx(win, body, head, eyes, feet, t, height / 300.0, None, False, QPointF(), eye_r)
    if hair_path and getattr(rig, "hair", None) is not None and hasattr(rig.hair, "shape"):
        intensity = round(pose.wild * (0.85 + 0.15 * pose.energy), 2)
        energy = round(pose.energy, 1)
        try:
            step = rig.hair.step(pose.t, energy)[1]
        except Exception:
            step = int(pose.t * 15)
        c.hair_key = (step, intensity, energy, round(feet.x()), round(feet.y()), round(height),
                      round(pose.lean, 3), round(pose.squat, 3))

        def outline():
            try:
                return tr.map(rig.hair.shape(rig.head, pose.t, intensity, energy))
            except Exception:
                return None
        c.hair_fn = outline
    return c


def validate(style: dict) -> str:
    """Why a mod's "style" section isn't right ("" = fine). Only plain data - nothing in it is ever run."""
    if not isinstance(style, dict):
        return "\"style\" must be an object"
    allowed = {"aura", "outline", "eyes", "hair", "hair_edge", "materials", "particles", "events", "move",
               "filters", "hair2", "sparkle", "description2", "theme", "inner"}
    for k in style:
        if k not in allowed:
            return f"unknown style part \"{k}\""
    for p in style.get("particles", []) if isinstance(style.get("particles", []), list) else [None]:
        if not isinstance(p, dict) or p.get("kind") not in PARTICLE_KINDS:
            return "each particle needs a known \"kind\""
        if int(p.get("count", 0)) > MAX_PARTICLES:
            return f"at most {MAX_PARTICLES} of a particle"
    for e in style.get("events", []) if isinstance(style.get("events", []), list) else [None]:
        if not isinstance(e, dict) or e.get("kind") not in EVENTS:
            return "each event needs a known \"kind\""
    for m in style.get("materials", []) if isinstance(style.get("materials", []), list) else [None]:
        kind = m.get("kind") if isinstance(m, dict) else m
        if kind not in MATERIALS:
            return f"unknown material \"{kind}\""
    h = style.get("hair")
    if h is not None and (not isinstance(h, dict) or h.get("kind") not in HAIR_KINDS):
        return "\"hair\" needs a known \"kind\""
    mv = style.get("move")
    if mv is not None and (not isinstance(mv, dict) or mv.get("kind") not in MOVES):
        return "\"move\" needs a known \"kind\""
    return ""
