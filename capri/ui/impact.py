"""Vibe impacts (2.6.3): when she's thrown and slams into the edge of the screen, her vibe answers it - its own
short impact animation at the exact spot, and its own crack in the "wall" that stays where it happened and fades
away after a few seconds.

A vibe describes both in its style's "impact" section (plain data, checked by validate() - nothing is ever run):

    "impact": {
      "burst": [ {"kind": "shockwave", "colors": [...], ...}, {"kind": "particles", "shape": "gear", ...}, ... ],
      "crack": {"color": "#...", "glow": "#...", "branches": 7, "jag": 0.5, "deco": ["gears", "ticks"], ...}
    }

Burst layers are drawn from analytic motion (position, scale, fade worked out from the time since the hit), so
they're smooth at any frame rate: drag-eased velocities, gravity, spin that settles, eased growth and fades. The
crack grows out from the hit in a fraction of a second, is then drawn once into a picture and reused - only its
living details (turning gears, a hue that shifts, flickering static...) are drawn each frame.

Each impact lives in its own small, click-through window at the hit point: above the desktop, never catching
your mouse, never touching your windows, gone once it has faded. Reduced motion: no particles or shockwaves -
the crack just fades in and out, softly.
"""

from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient

from .overlay_window import OverlayWindow

BURST_KINDS = ("shockwave", "particles", "flare", "lightning", "dark", "shark", "glitch", "scan", "streaks",
               "bloom", "vines", "symbols", "mist", "gold", "ink", "ripple", "holo", "flash")
CRACK_DECOS = ("gears", "ticks", "bubbles", "bolts", "frost", "thorns", "geo", "scan", "rainbow", "marks", "gold",
               "flowers", "stars", "hazard", "fold", "ghost", "static", "segments", "kintsugi", "blossoms",
               "ripples", "rgb", "magma", "film", "ink", "dots", "ornament", "holo", "petals")
ANIMATED_DECOS = {"gears", "bubbles", "bolts", "rainbow", "ghost", "static", "rgb", "magma", "holo", "film"}
SHAPES = ("spark", "snow", "crystal", "spore", "leaf", "pollen", "ember", "petal", "rose", "sakura", "star", "moon",
          "pixel", "bubble", "droplet", "gear", "paper", "geo", "mist", "ink", "glyph", "dust", "bud", "static",
          "fragment", "orb")

BURST_TIME = 1.15          # seconds the impact animation lasts
CRACK_GROW = 0.22          # the crack runs out from the hit
CRACK_HOLD = 2.6           # ...stays
CRACK_FADE = 1.9           # ...and fades away
LIFE = CRACK_GROW + CRACK_HOLD + CRACK_FADE


# (2.6.4) her own impact, with no vibe on: her crimson and cyan - a glitchy shockwave, shards and an RGB-split crack
DEFAULT_IMPACT = {
    "burst": [{"kind": "shockwave", "colors": ["#ec1046", "#28e6ff"], "count": 2, "width": 3},
              {"kind": "particles", "shape": "fragment", "colors": ["#ec1046", "#28e6ff", "#ffffff"], "count": 20,
               "speed": [240, 700], "size": [2, 4], "life": [0.4, 0.8], "gravity": 300},
              {"kind": "glitch", "colors": ["#ec1046", "#28e6ff"], "count": 10}],
    "crack": {"color": "#12060c", "glow": "#ec1046", "light": "#28e6ff", "deco": ["rgb"], "jag": 0.7},
}


def colour(value, alpha: int | None = None, fallback: str = "#ffffff") -> QColor:
    c = QColor(str(value or fallback))
    if not c.isValid():
        c = QColor(fallback)
    if alpha is not None:
        c.setAlpha(max(0, min(255, int(alpha))))
    return c


def with_alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(max(0.0, min(1.0, c.alphaF() * a)))
    return out


def ease_out(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


def ease_in_out(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def validate(spec) -> str:
    """Why an "impact" section isn't right ("" = fine)."""
    if not isinstance(spec, dict):
        return "\"impact\" must be an object"
    for k in spec:
        if k not in ("burst", "crack", "shake"):
            return f"unknown impact part \"{k}\""
    burst = spec.get("burst", [])
    if not isinstance(burst, list) or len(burst) > 8:
        return "\"burst\" must be a list of up to 8 layers"
    for layer in burst:
        if not isinstance(layer, dict) or layer.get("kind") not in BURST_KINDS:
            return "each burst layer needs a known \"kind\""
        if layer.get("kind") == "particles" and layer.get("shape", "spark") not in SHAPES:
            return "a particles layer needs a known \"shape\""
        if int(layer.get("count", 0) or 0) > 80:
            return "a burst layer can have at most 80 pieces"
    crack = spec.get("crack", {})
    if not isinstance(crack, dict):
        return "\"crack\" must be an object"
    for d in crack.get("deco", []) or []:
        if d not in CRACK_DECOS:
            return f"unknown crack detail \"{d}\""
    return ""


def os_reduce_motion() -> bool:
    """Has the computer itself been asked for less motion? (Windows: animations off; macOS: Reduce motion;
    GNOME: animations off.) Never raises."""
    try:
        if sys.platform == "win32":
            import ctypes
            on = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0):   # client-area anims
                return not bool(on.value)
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                                 capture_output=True, text=True, timeout=2)
            return out.stdout.strip() == "1"
        else:
            import subprocess
            out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
                                 capture_output=True, text=True, timeout=2)
            return out.stdout.strip() == "false"
    except Exception:
        pass
    return False


# -- the crack's shape -------------------------------------------------------------------------------------------
@dataclass
class Branch:
    points: list                 # QPointF, from where it starts outward
    width: float
    start: float                 # how far from the hit it starts (for growing out)
    depth: int


def make_crack(rng: random.Random, out_angle: float, radius: float, spec: dict) -> list[Branch]:
    """Branching fractures fanning out from the hit (into the screen, away from the wall)."""
    n = max(3, min(12, int(spec.get("branches", 6))))
    jag = float(spec.get("jag", 0.5))                 # 0 smooth / organic .. 1 jagged
    straight = bool(spec.get("straight", False))      # long straight runs with sharp turns (racing, technical)
    curve = float(spec.get("curve", 0.0))             # organic curl
    spread = float(spec.get("spread", 1.35))          # radians either side of straight out
    length = float(spec.get("length", 1.0))
    split = float(spec.get("split", 0.3))
    width = float(spec.get("width", 2.2))
    out: list[Branch] = []

    def grow(start: QPointF, ang: float, ln: float, w: float, dist: float, depth: int) -> None:
        pts = [QPointF(start)]
        steps = 3 if straight else 7
        seg = ln / steps
        a = ang
        d = dist
        for i in range(steps):
            if straight:
                a += rng.choice((-1, 1)) * rng.uniform(0.25, 0.6) * (1 if i else 0.3)
            else:
                a += rng.uniform(-0.55, 0.55) * jag + curve * 0.25 * math.sin(i * 1.3 + depth)
            nxt = pts[-1] + QPointF(math.cos(a) * seg, math.sin(a) * seg)
            pts.append(nxt)
            d += seg
            if depth < 3 and rng.random() < split * (0.85 if depth else 1.0) and i < steps - 1:
                side = rng.choice((-1, 1))
                grow(nxt, a + side * rng.uniform(0.45, 1.0), ln * rng.uniform(0.3, 0.55), w * 0.6, d, depth + 1)
        out.append(Branch(pts, w, dist, depth))

    for i in range(n):
        ang = out_angle + (i / max(1, n - 1) - 0.5) * 2 * spread + rng.uniform(-0.12, 0.12)
        ln = radius * length * rng.uniform(0.55, 1.0)
        grow(QPointF(), ang, ln, width * rng.uniform(0.8, 1.2), 0.0, 0)
    return out


def _branch_path(b: Branch, upto: float | None = None) -> QPainterPath:
    """The branch as a path; `upto` = how far from the hit it has grown so far."""
    path = QPainterPath(b.points[0])
    d = b.start
    if upto is not None and upto <= d:
        return QPainterPath()
    for a, c in zip(b.points, b.points[1:]):
        seg = math.hypot(c.x() - a.x(), c.y() - a.y())
        if upto is not None and d + seg > upto:
            k = max(0.0, (upto - d) / max(1e-6, seg))
            path.lineTo(a + (c - a) * k)
            return path
        path.lineTo(c)
        d += seg
    return path


def _gear(p: QPainter, at: QPointF, r: float, turn: float, fill: QColor, edge: QColor | None = None) -> None:
    path = QPainterPath()
    teeth = 8
    for i in range(teeth * 2):
        a = math.pi * i / teeth + math.radians(turn)
        rr = r if i % 2 == 0 else r * 0.75
        pt = at + QPointF(math.cos(a) * rr, math.sin(a) * rr)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(at, r * 0.32, r * 0.32)
    p.setPen(QPen(edge, 1.0) if edge is not None else Qt.PenStyle.NoPen)
    p.setBrush(fill)
    p.drawPath(path.subtracted(hole))


def _trefoil(p: QPainter, at: QPointF, r: float, turn: float, col: QColor) -> None:
    """A little three-bladed hazard mark (drawn here, not copied from anywhere)."""
    p.save()
    p.translate(at)
    p.rotate(turn)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    for k in range(3):
        p.save()
        p.rotate(k * 120)
        blade = QPainterPath()
        blade.moveTo(0, 0)
        blade.arcTo(QRectF(-r, -r, 2 * r, 2 * r), 60, 60)
        blade.closeSubpath()
        hole = QPainterPath()
        hole.addEllipse(QPointF(0, 0), r * 0.32, r * 0.32)
        p.drawPath(blade.subtracted(hole))
        p.restore()
    p.drawEllipse(QPointF(0, 0), r * 0.18, r * 0.18)
    p.restore()


def _shark(p: QPainter, at: QPointF, length: float, heading: float, col: QColor, rim: QColor) -> None:
    """A sleek shark-like shadow (simple original silhouette)."""
    L = length
    path = QPainterPath(QPointF(L * 0.5, 0))
    path.cubicTo(QPointF(L * 0.3, -L * 0.13), QPointF(-L * 0.15, -L * 0.14), QPointF(-L * 0.35, -L * 0.04))
    path.lineTo(QPointF(-L * 0.52, -L * 0.2))                 # tail, top lobe
    path.lineTo(QPointF(-L * 0.45, 0))
    path.lineTo(QPointF(-L * 0.52, L * 0.16))                 # tail, bottom lobe
    path.lineTo(QPointF(-L * 0.35, L * 0.04))
    path.cubicTo(QPointF(-L * 0.1, L * 0.12), QPointF(L * 0.3, L * 0.1), QPointF(L * 0.5, 0))
    fin = QPainterPath(QPointF(L * 0.05, -L * 0.12))
    fin.lineTo(QPointF(-L * 0.08, -L * 0.32))
    fin.lineTo(QPointF(-L * 0.12, -L * 0.12))
    fin.closeSubpath()
    p.save()
    p.translate(at)
    p.rotate(math.degrees(heading))
    p.setPen(QPen(rim, max(1.0, L * 0.02)))
    p.setBrush(col)
    p.drawPath(path.united(fin))
    p.restore()


# -- one impact ----------------------------------------------------------------------------------------------------
@dataclass
class Piece:
    vel: QPointF
    life: float
    size: float
    colour: QColor
    spin: float
    angle: float
    drag: float
    gravity: float
    delay: float
    shape: str
    unfold: bool = False


@dataclass
class Impact:
    """One hit: where (in its window), which way is "out" (away from the wall), the vibe's spec, her size."""
    at: QPointF
    normal: QPointF
    spec: dict
    scale: float                         # her height in px (the effect is sized to her)
    seed: int = 1
    reduced: bool = False
    born: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.out = math.atan2(self.normal.y(), self.normal.x())
        self.radius = self.scale * 0.62
        crack = self.spec.get("crack", {}) or {}
        self.crack_spec = crack
        self.branches = make_crack(random.Random(self.seed * 7 + 3), self.out, self.radius * 0.62, crack)
        self.reach = max((b.start + sum(math.hypot(c.x() - a.x(), c.y() - a.y()) for a, c in zip(b.points,
                          b.points[1:])) for b in self.branches), default=1.0)
        self._crack_img: QImage | None = None
        self.pieces: dict[int, list[Piece]] = {}
        for i, layer in enumerate(self.spec.get("burst", []) or []):
            if layer.get("kind") in ("particles", "symbols", "bloom"):
                self.pieces[i] = self._make_pieces(layer)
        self.nodes = [pt for b in self.branches if b.depth < 2 for pt in b.points[2::3]]
        self._upto: float | None = None
        self.ends = [b.points[-1] for b in self.branches]

    # pieces flying out, worked out once
    def _make_pieces(self, layer: dict) -> list[Piece]:
        r = random.Random(self.seed * 13 + len(self.pieces))
        cols = [colour(c) for c in (layer.get("colors") or ["#ffffff"])]
        n = max(1, min(80, int(layer.get("count", 18))))
        lo, hi = layer.get("speed", [220, 620])[:2] if isinstance(layer.get("speed"), list) else (220, 620)
        spread = float(layer.get("spread", 1.3))
        s0, s1 = layer.get("size", [2.0, 4.0])[:2] if isinstance(layer.get("size"), list) else (2.0, 4.0)
        life = layer.get("life", [0.5, 1.0])[:2] if isinstance(layer.get("life"), list) else (0.5, 1.0)
        k = self.scale / 300.0
        out = []
        for _i in range(n):
            a = self.out + r.uniform(-spread, spread)
            v = r.uniform(lo, hi) * max(0.6, k)
            out.append(Piece(QPointF(math.cos(a) * v, math.sin(a) * v), r.uniform(*life),
                             r.uniform(s0, s1) * max(0.7, k), r.choice(cols), r.uniform(-500, 500),
                             r.uniform(0, 360), float(layer.get("drag", 3.2)), float(layer.get("gravity", 260)) * k,
                             r.uniform(0, float(layer.get("stagger", 0.06))), str(layer.get("shape", "spark")),
                             bool(layer.get("unfold", False))))
        return out

    def alive(self, now: float) -> bool:
        return now - self.born < LIFE

    def busy_burst(self, now: float) -> bool:
        return not self.reduced and now - self.born < BURST_TIME

    # -- painting -------------------------------------------------------------------------------------------------
    def paint(self, p: QPainter, now: float) -> None:
        t = now - self.born
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_crack(p, t)
        if not self.reduced and t < BURST_TIME:
            self._paint_core(p, t)
            for i, layer in enumerate(self.spec.get("burst", []) or []):
                lt = t - float(layer.get("delay", 0.0))
                if lt < 0:
                    continue
                fn = getattr(self, "_b_" + layer.get("kind", ""), None)
                if fn is not None:
                    p.save()
                    fn(p, lt, layer, i)
                    p.restore()
        elif self.reduced and t < 0.6:                    # reduced motion: one soft glow, nothing flying
            g = QRadialGradient(self.at, self.radius * 0.5)
            col = colour(self.crack_spec.get("glow", "#ffffff"))
            g.setColorAt(0, with_alpha(col, 0.35 * (1 - t / 0.6)))
            g.setColorAt(1, with_alpha(col, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(self.at, self.radius * 0.5, self.radius * 0.5)

    def _paint_core(self, p: QPainter, t: float) -> None:
        """The moment of the hit: a hot point that pinches in (anticipation), pops, and is gone."""
        if t > 0.22:
            return
        col = colour(self.crack_spec.get("glow", "#ffffff"))
        if t < 0.04:
            r, a = self.scale * (0.12 - t * 1.6), 0.6 + t * 8
        else:
            k = (t - 0.04) / 0.18
            r, a = self.scale * (0.06 + 0.2 * ease_out(k)), (1 - k) ** 2
        g = QRadialGradient(self.at, max(1.0, r))
        g.setColorAt(0, QColor(255, 255, 255, int(230 * a)))
        g.setColorAt(0.35, with_alpha(col, 0.85 * a))
        g.setColorAt(1, with_alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(self.at, max(1.0, r), max(1.0, r))

    # crack ---------------------------------------------------------------------------------------------------------
    def _crack_alpha(self, t: float) -> float:
        if t < CRACK_GROW:
            return ease_out(t / CRACK_GROW) if self.reduced else 1.0
        if t < CRACK_GROW + CRACK_HOLD:
            return 1.0
        return 1.0 - ease_in_out((t - CRACK_GROW - CRACK_HOLD) / CRACK_FADE)

    def _paint_crack(self, p: QPainter, t: float) -> None:
        a = self._crack_alpha(t)
        if a <= 0.0:
            return
        spec = self.crack_spec
        deco = list(spec.get("deco", []) or [])
        if t < CRACK_GROW and not self.reduced:          # running out from the hit
            upto = self.reach * ease_out(t / CRACK_GROW)
            self._upto = upto
            p.save()
            p.translate(self.at)
            self._draw_static(p, upto, deco, t)
            p.restore()
        else:
            self._upto = None
            if self._crack_img is None:
                self._crack_img = self._render_static(deco, t)
            img, origin = self._crack_img
            p.save()
            p.setOpacity(a * self._ghost(deco, t))
            p.drawImage(origin, img)
            p.restore()
        p.save()
        p.translate(self.at)
        p.setOpacity(a)
        self._draw_live(p, deco, t)
        p.restore()

    def _ghost(self, deco: list, t: float) -> float:
        if "ghost" in deco:
            return 0.72 + 0.28 * math.sin(t * 5.3) * math.sin(t * 2.1)
        return 1.0

    def _render_static(self, deco: list, t: float):
        pad = self.radius * 1.2
        dev = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
        dpr = getattr(self, "dpr", 1.0)
        size = round(2 * pad * dpr)
        img = QImage(max(1, size), max(1, size), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(0)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.translate(pad, pad)
        self._draw_static(q, None, deco, t)
        q.end()
        del dev
        return img, QPointF(self.at.x() - pad, self.at.y() - pad)

    def _crack_colours(self, t: float):
        spec = self.crack_spec
        core = colour(spec.get("color", "#1a1a1a"), 235)
        glow = colour(spec.get("glow", "#ffffff"), int(spec.get("glow_alpha", 150)))
        light = colour(spec.get("light", spec.get("glow", "#ffffff")), 220)
        return core, glow, light

    def _draw_static(self, p: QPainter, upto, deco: list, t: float) -> None:
        """The crack itself (glow, dark core, a bright edge) and the details that don't move."""
        core, glow, light = self._crack_colours(t)
        animated_colour = "rainbow" in deco or "magma" in deco
        s = max(0.7, self.scale / 300)
        paths = [(_branch_path(b, upto), b) for b in self.branches]
        segmented = "segments" in deco
        if "fold" in deco:                                          # paper: a soft shadow under each fold
            for path, b in paths:
                p.setPen(QPen(QColor(0, 0, 0, 60), b.width * s * 2.2, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPath(path.translated(1.5 * s, 2 * s))
        if not animated_colour:
            for path, b in paths:                                    # the glow
                p.setPen(QPen(with_alpha(glow, 0.45), b.width * s * 4.2, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPath(path)
        for path, b in paths:                                        # the dark core
            pen = QPen(core, b.width * s * 1.25, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.MiterJoin if self.crack_spec.get("straight") else Qt.PenJoinStyle.RoundJoin)
            if segmented:
                pen.setDashPattern([3.0, 0.8])
            p.setPen(pen)
            p.drawPath(path)
        if not animated_colour:
            for path, b in paths:                                    # a bright, thin edge
                p.setPen(QPen(light, max(0.6, b.width * s * 0.4), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(path.translated(-0.6 * s, -0.6 * s))
        if upto is None:
            r = random.Random(self.seed * 5 + 1)
            for d in deco:
                if d not in ANIMATED_DECOS:
                    fn = getattr(self, "_d_" + d, None)
                    if fn is not None:
                        fn(p, r, s, core, glow, light)

    def _draw_live(self, p: QPainter, deco: list, t: float) -> None:
        core, glow, light = self._crack_colours(t)
        s = max(0.7, self.scale / 300)
        r = random.Random(self.seed * 5 + 2)
        for d in deco:
            if d in ANIMATED_DECOS:
                if self._upto is not None and d in ("gears", "bubbles", "bolts", "static", "holo", "film"):
                    continue                                    # (they appear once the crack has run out)
                fn = getattr(self, "_d_" + d, None)
                if fn is not None:
                    fn(p, r, s, core, glow, light, t)

    # crack details (static) --------------------------------------------------------------------------------------
    def _d_ticks(self, p, r, s, core, glow, light) -> None:
        rr = self.radius * 0.28
        p.setPen(QPen(glow, 1.2 * s))
        for k in range(12):
            a = self.out - math.pi / 2 + math.pi * k / 11
            inner = rr * (0.82 if k % 3 else 0.7)
            p.drawLine(QPointF(math.cos(a) * inner, math.sin(a) * inner), QPointF(math.cos(a) * rr, math.sin(a) * rr))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(-rr, -rr, 2 * rr, 2 * rr), int(-math.degrees(self.out) * 16 - 90 * 16), 180 * 16)

    def _d_frost(self, p, r, s, core, glow, light) -> None:
        p.setPen(QPen(with_alpha(light, 0.85), 0.8 * s))
        for pt in self.nodes[::2] + self.ends:
            for k in range(2):
                a = r.uniform(0, math.tau)
                ln = r.uniform(3, 6) * s
                tip = pt + QPointF(math.cos(a) * ln, math.sin(a) * ln)
                p.drawLine(pt, tip)
                for side in (-0.6, 0.6):
                    p.drawLine(pt + (tip - pt) * 0.55, pt + (tip - pt) * 0.55 +
                               QPointF(math.cos(a + side) * ln * 0.35, math.sin(a + side) * ln * 0.35))

    def _d_thorns(self, p, r, s, core, glow, light) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(core)
        for b in self.branches:
            for a, c in zip(b.points, b.points[1:]):
                mid = (a + c) / 2
                d = c - a
                ln = math.hypot(d.x(), d.y()) or 1
                nx, ny = -d.y() / ln, d.x() / ln
                side = r.choice((-1, 1))
                h = r.uniform(3, 6) * s
                tri = QPainterPath(mid - QPointF(d.x() / ln * 2 * s, d.y() / ln * 2 * s))
                tri.lineTo(mid + QPointF(d.x() / ln * 2 * s, d.y() / ln * 2 * s))
                tri.lineTo(mid + QPointF(nx * h * side + d.x() / ln * 3 * s, ny * h * side + d.y() / ln * 3 * s))
                tri.closeSubpath()
                p.drawPath(tri)

    def _d_geo(self, p, r, s, core, glow, light) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(light, 1.0 * s))
        for pt in self.ends[::2]:
            sz = r.uniform(3, 6) * s
            p.save()
            p.translate(pt)
            p.rotate(r.uniform(0, 90))
            if r.random() < 0.5:
                p.drawRect(QRectF(-sz, -sz, 2 * sz, 2 * sz))
            else:
                p.drawPolygon([QPointF(0, -sz * 1.2), QPointF(sz, sz * 0.7), QPointF(-sz, sz * 0.7)])
            p.restore()

    def _d_scan(self, p, r, s, core, glow, light) -> None:
        """CRT scanlines running along the cracks (short lines at each bend - no costly clipping)."""
        p.setPen(QPen(with_alpha(glow, 0.32), 1.0))
        for b in self.branches:
            if b.depth > 1:
                continue
            for pt in b.points:
                for k in (-4, -1, 2, 5):
                    y = pt.y() + k * s
                    p.drawLine(QPointF(pt.x() - 8 * s, y), QPointF(pt.x() + 8 * s, y))

    def _d_marks(self, p, r, s, core, glow, light) -> None:
        p.setPen(QPen(light, 0.9 * s))
        for b in self.branches:
            if b.depth:
                continue
            for a, c in zip(b.points, b.points[1:]):
                d = c - a
                ln = math.hypot(d.x(), d.y()) or 1
                nx, ny = -d.y() / ln * 4 * s, d.x() / ln * 4 * s
                for f in (0.25, 0.5, 0.75):
                    m = a + d * f
                    p.drawLine(m - QPointF(nx, ny), m + QPointF(nx, ny))
            end = b.points[-1]
            p.drawRect(QRectF(end.x() - 2 * s, end.y() - 2 * s, 4 * s, 4 * s))

    def _d_gold(self, p, r, s, core, glow, light) -> None:
        gold = colour(self.crack_spec.get("gold", "#d8b04a"), 230)
        for b in self.branches:
            if b.depth > 1:
                continue
            p.setPen(QPen(gold, max(0.8, b.width * s * 0.35)))
            p.drawPath(_branch_path(b).translated(1.1 * s, 0.9 * s))

    def _d_flowers(self, p, r, s, core, glow, light) -> None:
        for pt in self.ends[::2]:
            self._flower(p, pt, r.uniform(3, 5) * s, r.uniform(0, 72), light, glow)

    def _d_blossoms(self, p, r, s, core, glow, light) -> None:
        for pt in self.ends:
            if r.random() < 0.6:
                self._flower(p, pt, r.uniform(3.5, 5.5) * s, r.uniform(0, 72), colour("#ffd6e4"), colour("#ff8fb3"))

    def _flower(self, p, at, rr, turn, petal, centre) -> None:
        p.save()
        p.translate(at)
        p.rotate(turn)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(petal)
        for k in range(5):
            a = k * math.tau / 5
            p.drawEllipse(QPointF(math.cos(a) * rr * 0.55, math.sin(a) * rr * 0.55), rr * 0.45, rr * 0.45)
        p.setBrush(centre)
        p.drawEllipse(QPointF(), rr * 0.3, rr * 0.3)
        p.restore()

    def _d_petals(self, p, r, s, core, glow, light) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.nodes[::3]:
            p.setBrush(with_alpha(light, 0.8))
            p.save()
            p.translate(pt)
            p.rotate(r.uniform(0, 360))
            p.drawEllipse(QRectF(-3 * s, -1.4 * s, 6 * s, 2.8 * s))
            p.restore()

    def _d_stars(self, p, r, s, core, glow, light) -> None:
        pts = self.ends[: min(6, len(self.ends))]
        p.setPen(QPen(with_alpha(light, 0.5), 0.7 * s))
        for a, c in zip(pts, pts[1:]):
            p.drawLine(a, c)
        p.setPen(Qt.PenStyle.NoPen)
        for pt in pts:
            p.setBrush(with_alpha(light, 0.9))
            p.drawEllipse(pt, 1.8 * s, 1.8 * s)

    def _d_hazard(self, p, r, s, core, glow, light) -> None:
        rr = self.radius * 0.22
        p.save()
        p.rotate(math.degrees(self.out) + 90)
        clip = QPainterPath()
        clip.addRect(QRectF(-rr, 2 * s, 2 * rr, 5 * s))
        p.setClipPath(clip)
        p.fillRect(QRectF(-rr, 2 * s, 2 * rr, 5 * s), QColor(20, 20, 10, 200))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colour(self.crack_spec.get("hazard", "#f2d23a"), 200))
        x = -rr
        while x < rr:
            p.drawPolygon([QPointF(x, 2 * s), QPointF(x + 4 * s, 2 * s), QPointF(x + 2 * s, 7 * s),
                           QPointF(x - 2 * s, 7 * s)])
            x += 8 * s
        p.restore()

    def _d_fold(self, p, r, s, core, glow, light) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.ends[::2]:
            sz = r.uniform(5, 9) * s
            p.setBrush(QColor(255, 255, 255, 140))
            p.save()
            p.translate(pt)
            p.rotate(r.uniform(0, 360))
            p.drawPolygon([QPointF(0, 0), QPointF(sz, 0), QPointF(0, sz)])
            p.setBrush(QColor(0, 0, 0, 50))
            p.drawPolygon([QPointF(sz, 0), QPointF(0, sz), QPointF(sz * 0.8, sz * 0.8)])
            p.restore()

    def _d_kintsugi(self, p, r, s, core, glow, light) -> None:
        gold = colour(self.crack_spec.get("gold", "#f2c14e"))
        for b in self.branches:
            path = _branch_path(b)
            p.setPen(QPen(with_alpha(gold, 0.35), b.width * s * 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
            p.setPen(QPen(gold, max(1.0, b.width * s * 0.8), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)

    def _d_ripples(self, p, r, s, core, glow, light) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(3):
            rr = self.radius * (0.25 + 0.2 * k)
            p.setPen(QPen(with_alpha(light, 0.45 - 0.12 * k), 1.0 * s))
            p.drawEllipse(QPointF(), rr, rr * 0.8)

    def _d_ink(self, p, r, s, core, glow, light) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(core)
        for pt in self.ends:
            if r.random() < 0.6:
                rr = r.uniform(2, 4.5) * s
                p.drawEllipse(pt, rr, rr * r.uniform(0.7, 1.0))

    def _d_dots(self, p, r, s, core, glow, light) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.ends[::2]:
            g = QRadialGradient(pt, 3 * s)
            g.setColorAt(0, with_alpha(light, 0.95))
            g.setColorAt(1, with_alpha(light, 0.0))
            p.setBrush(g)
            p.drawEllipse(pt, 3 * s, 3 * s)

    def _d_ornament(self, p, r, s, core, glow, light) -> None:
        gold = colour(self.crack_spec.get("gold", "#c9a24a"), 220)
        p.setPen(QPen(gold, 1.0 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for pt in self.ends[::2]:
            rr = r.uniform(3, 5) * s
            for k in range(3):
                a = k * math.tau / 3 - math.pi / 2
                p.drawEllipse(pt + QPointF(math.cos(a) * rr * 0.6, math.sin(a) * rr * 0.6), rr * 0.5, rr * 0.5)

    def _d_segments(self, p, r, s, core, glow, light) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(light)
        for pt in self.nodes:
            p.drawEllipse(pt, 1.6 * s, 1.6 * s)

    # crack details (alive) -----------------------------------------------------------------------------------------
    def _d_gears(self, p, r, s, core, glow, light, t) -> None:
        gold = colour(self.crack_spec.get("gold", "#c99a3a"), 230)
        for i, pt in enumerate(self.ends[: 5]):
            rr = r.uniform(4, 8) * s
            _gear(p, pt, rr, t * (40 if i % 2 else -55) + i * 13, with_alpha(gold, 0.85), with_alpha(core, 0.9))

    def _d_bubbles(self, p, r, s, core, glow, light, t) -> None:
        from .style_fx import draw_particle
        for i, pt in enumerate(self.nodes[: 10]):
            phase = (t * 0.45 + i * 0.37) % 1.0
            at = pt + QPointF(math.sin(t * 2 + i) * 2 * s, -phase * 18 * s)
            draw_particle(p, "bubble", at, (1.5 + 1.5 * r.random()) * s, light, 0.8 * (1 - phase), 0, t)

    def _d_bolts(self, p, r, s, core, glow, light, t) -> None:
        rr = random.Random(int(t * 14) + self.seed)
        p.setPen(QPen(light, 1.0 * s))
        for pt in self.nodes:
            if rr.random() < 0.25:
                a = rr.uniform(0, math.tau)
                pts = [pt]
                for _k in range(3):
                    a += rr.uniform(-0.9, 0.9)
                    pts.append(pts[-1] + QPointF(math.cos(a) * 4 * s, math.sin(a) * 4 * s))
                p.drawPolyline(pts)

    def _d_rainbow(self, p, r, s, core, glow, light, t) -> None:
        for i, b in enumerate(self.branches):
            hue = (t * 0.18 + i * 0.09) % 1.0
            c = QColor.fromHsvF(hue, 0.65, 1.0, 0.85)
            p.setPen(QPen(with_alpha(c, 0.35), b.width * s * 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            path = _branch_path(b, self._upto)
            p.drawPath(path)
            p.setPen(QPen(c, max(0.7, b.width * s * 0.45), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path.translated(-0.6 * s, -0.6 * s))

    def _d_magma(self, p, r, s, core, glow, light, t) -> None:
        cool = min(1.0, max(0.0, (t - 0.3) / (CRACK_HOLD + 0.6)))       # bright and cooling to a dull red
        hot = QColor.fromRgbF(1.0, 0.75 - 0.5 * cool, 0.25 - 0.2 * cool, 0.9 - 0.4 * cool)
        for b in self.branches:
            path = _branch_path(b, self._upto)
            p.setPen(QPen(with_alpha(hot, 0.4), b.width * s * 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
            p.setPen(QPen(hot, max(0.7, b.width * s * 0.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)

    def _d_static(self, p, r, s, core, glow, light, t) -> None:
        rr = random.Random(int(t * 24) + self.seed)
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.nodes:
            for _k in range(3):
                q = pt + QPointF(rr.uniform(-6, 6) * s, rr.uniform(-6, 6) * s)
                p.setBrush(QColor(255, 255, 255, rr.randint(60, 200)) if rr.random() < 0.6 else QColor(0, 0, 0, 160))
                p.drawRect(QRectF(q.x(), q.y(), 1.6 * s, 1.6 * s))

    def _d_rgb(self, p, r, s, core, glow, light, t) -> None:
        rr = random.Random(int(t * 12) + self.seed)
        off = (1.5 + 2.5 * rr.random()) * s
        for col, dx in ((QColor(255, 30, 90, 150), -off), (QColor(30, 200, 255, 150), off)):
            p.setPen(QPen(col, 1.0 * s))
            for b in self.branches:
                if b.depth < 2:
                    p.drawPath(_branch_path(b, self._upto).translated(dx, 0))
        for _k in range(4):                                         # glitch fragments
            pt = rr.choice(self.nodes) if self.nodes else QPointF()
            p.fillRect(QRectF(pt.x(), pt.y(), rr.uniform(4, 12) * s, rr.uniform(1.5, 3) * s),
                       QColor(255, 43, 214, 140) if rr.random() < 0.5 else QColor(40, 200, 255, 140))

    def _d_ghost(self, p, r, s, core, glow, light, t) -> None:
        drift = QPointF(math.sin(t * 1.3) * 2 * s, -t * 3 * s)
        for b in self.branches[::2]:
            p.setPen(QPen(with_alpha(light, 0.18), b.width * s * 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(_branch_path(b, self._upto).translated(drift))

    def _d_holo(self, p, r, s, core, glow, light, t) -> None:
        k = (t * 0.6) % 1.4 - 0.2
        rr = self.reach * k
        if rr <= 0:
            return
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(with_alpha(light, 0.55 * max(0.0, 1 - k)), 1.2 * s))
        p.drawEllipse(QPointF(), rr, rr)

    def _d_film(self, p, r, s, core, glow, light, t) -> None:
        rr = random.Random(int(t * 10) + self.seed)
        p.setPen(QPen(QColor(255, 240, 210, 90), 0.8))
        for _k in range(2):
            x = rr.uniform(-self.radius, self.radius)
            p.drawLine(QPointF(x, -self.radius), QPointF(x + rr.uniform(-4, 4), self.radius))

    # burst layers -----------------------------------------------------------------------------------------------
    def _cols(self, layer: dict, default="#ffffff") -> list[QColor]:
        return [colour(c) for c in (layer.get("colors") or [default])]

    def _b_shockwave(self, p, t, layer, i) -> None:
        cols = self._cols(layer)
        count = max(1, min(4, int(layer.get("count", 2))))
        life = float(layer.get("life", 0.55))
        for k in range(count):
            lt = t - k * float(layer.get("gap", 0.08))
            if lt < 0 or lt > life:
                continue
            q = lt / life
            rr = self.radius * float(layer.get("size", 1.0)) * ease_out(q) * (1 - 0.18 * k)
            col = cols[k % len(cols)]
            a = (1 - q) ** 1.6
            if layer.get("fill"):
                g = QRadialGradient(self.at, max(1.0, rr))
                g.setColorAt(0, with_alpha(col, 0.0))
                g.setColorAt(0.75, with_alpha(col, 0.22 * a))
                g.setColorAt(1, with_alpha(col, 0.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(self.at, rr, rr)
            if layer.get("iridescent"):
                col = QColor.fromHsvF((t * 0.9 + k * 0.2) % 1.0, 0.6, 1.0, 1.0)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(col, a), max(0.8, float(layer.get("width", 3.0)) * (1 - q * 0.7))))
            p.drawEllipse(self.at, rr, rr)

    def _b_particles(self, p, t, layer, i) -> None:
        from .style_fx import draw_particle
        for pc in self.pieces.get(i, []):
            lt = t - pc.delay
            if lt <= 0 or lt > pc.life:
                continue
            k = lt / pc.life
            ex = (1 - math.exp(-pc.drag * lt)) / pc.drag          # drag-eased travel: quick out, gliding to a stop
            at = self.at + pc.vel * ex + QPointF(0, 0.5 * pc.gravity * lt * lt)
            spin = pc.angle + pc.spin * ex
            grow = ease_out(min(1.0, lt / 0.12)) * (1 - 0.35 * k)
            alpha = (1 - ease_in_out(max(0.0, (k - 0.45) / 0.55)))
            if pc.unfold:                                           # paper opening out as it flies
                p.save()
                p.translate(at)
                p.rotate(spin)
                p.scale(max(0.08, abs(math.cos(min(1.0, lt * 2.4) * math.pi * 0.5 - math.pi * 0.5))), 1.0)
                p.rotate(-spin)
                draw_particle(p, pc.shape, QPointF(), pc.size * grow, pc.colour, alpha, spin, t)
                p.restore()
            else:
                draw_particle(p, pc.shape, at, pc.size * grow, pc.colour, alpha, spin, t)

    def _b_symbols(self, p, t, layer, i) -> None:
        for pc in self.pieces.get(i, []):
            lt = t - pc.delay
            if lt <= 0 or lt > pc.life:
                continue
            k = lt / pc.life
            ex = (1 - math.exp(-pc.drag * lt)) / pc.drag
            at = self.at + pc.vel * ex
            alpha = 1 - ease_in_out(max(0.0, (k - 0.4) / 0.6))
            sz = pc.size * ease_out(min(1.0, lt / 0.15)) * 1.6
            if layer.get("shape") == "moon":
                from .style_fx import draw_particle
                draw_particle(p, "moon", at, sz, pc.colour, alpha, pc.angle + pc.spin * ex * 0.3, t)
            else:
                _trefoil(p, at, sz, pc.angle + pc.spin * ex * 0.4, with_alpha(pc.colour, alpha))

    def _b_bloom(self, p, t, layer, i) -> None:
        """A flower opening at the hit, its petals then lifting away."""
        cols = self._cols(layer, "#ffc8d6")
        n = 7
        open_ = ease_out(min(1.0, t / 0.35))
        rr = self.scale * 0.11 * open_
        for k in range(n):
            a = self.out + (k - (n - 1) / 2) * 0.42
            drift = max(0.0, t - 0.35)
            at = self.at + QPointF(math.cos(a) * (rr + drift * 60), math.sin(a) * (rr + drift * 60) - drift * drift * 30)
            alpha = 1 - ease_in_out(max(0.0, (t - 0.45) / 0.6))
            p.save()
            p.translate(at)
            p.rotate(math.degrees(a) + 90 + drift * 80)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(cols[k % len(cols)], alpha))
            p.drawEllipse(QRectF(-rr * 0.35, -rr * 0.6, rr * 0.7, rr * 1.2))
            p.restore()
        from .style_fx import draw_particle
        for pc in self.pieces.get(i, []):                          # pollen
            lt = t - pc.delay - 0.1
            if 0 < lt < pc.life:
                ex = (1 - math.exp(-pc.drag * lt)) / pc.drag
                draw_particle(p, "pollen", self.at + pc.vel * ex * 0.6, pc.size * 0.7, colour("#fff1a0"),
                              1 - lt / pc.life, 0, t)

    def _b_flare(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#ffd25a")
        k = min(1.0, t / 0.7)
        a = (1 - k) ** 1.4
        n = int(layer.get("count", 12))
        ln = self.radius * float(layer.get("size", 1.1)) * ease_out(min(1.0, t / 0.3))
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(n):
            ang = self.out + (j / n - 0.5) * math.pi * 1.6 + t * 0.4
            w = 0.07 + 0.04 * ((j * 7) % 3)
            g = QRadialGradient(self.at, max(1.0, ln))
            g.setColorAt(0, with_alpha(cols[0], 0.85 * a))
            g.setColorAt(1, with_alpha(cols[-1], 0.0))
            ray = QPainterPath(self.at)
            ray.lineTo(self.at + QPointF(math.cos(ang - w) * ln, math.sin(ang - w) * ln))
            ray.lineTo(self.at + QPointF(math.cos(ang + w) * ln * (0.6 + 0.4 * (j % 2)),
                                         math.sin(ang + w) * ln * (0.6 + 0.4 * (j % 2))))
            ray.closeSubpath()
            p.setBrush(g)
            p.drawPath(ray)
        core = QRadialGradient(self.at, self.radius * 0.35)
        core.setColorAt(0, QColor(255, 250, 220, int(230 * a)))
        core.setColorAt(1, with_alpha(cols[0], 0.0))
        p.setBrush(core)
        p.drawEllipse(self.at, self.radius * 0.35, self.radius * 0.35)

    def _b_lightning(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#c38bff")
        n = int(layer.get("count", 5))
        for j in range(n):
            start = j * 0.05
            lt = t - start
            if lt < 0 or lt > 0.32:
                continue
            flicker = 0.55 + 0.45 * (1 if int(lt * 40 + j) % 3 else 0.2)
            a = (1 - lt / 0.32) * flicker
            rr = random.Random(self.seed * 31 + j)
            ang = self.out + rr.uniform(-1.2, 1.2)
            ln = self.radius * rr.uniform(0.6, 1.1)
            pts = [self.at]
            for k in range(1, 7):
                base = self.at + QPointF(math.cos(ang) * ln * k / 6, math.sin(ang) * ln * k / 6)
                jit = rr.uniform(-1, 1) * ln * 0.09
                pts.append(base + QPointF(-math.sin(ang) * jit, math.cos(ang) * jit))
            col = cols[j % len(cols)]
            p.setPen(QPen(with_alpha(col, 0.35 * a), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPolyline(pts)
            p.setPen(QPen(with_alpha(QColor(255, 255, 255), a), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPolyline(pts)

    def _b_dark(self, p, t, layer, i) -> None:
        """A dark disc swelling out of the hit, a faint rim of light round it, then closing up."""
        cols = self._cols(layer, "#7a3ad8")
        k = min(1.0, t / 0.9)
        size = math.sin(math.pi * k) * self.radius * float(layer.get("size", 0.55))
        if size <= 1:
            return
        wob = QPainterPath()
        for j in range(25):
            a = j / 24 * math.tau
            rr = size * (1 + 0.05 * math.sin(a * 5 + t * 9))
            pt = self.at + QPointF(math.cos(a) * rr, math.sin(a) * rr)
            wob.moveTo(pt) if j == 0 else wob.lineTo(pt)
        wob.closeSubpath()
        g = QRadialGradient(self.at, size)
        g.setColorAt(0, QColor(0, 0, 0, int(230 * (1 - k * 0.4))))
        g.setColorAt(0.85, QColor(5, 0, 12, int(200 * (1 - k * 0.4))))
        g.setColorAt(1, with_alpha(cols[0], 0.0))
        p.setPen(QPen(with_alpha(cols[0], 0.8 * (1 - k)), 2.0))
        p.setBrush(g)
        p.drawPath(wob)

    def _b_shark(self, p, t, layer, i) -> None:
        """A shadow gliding through the shockwave, round the hit."""
        cols = self._cols(layer, "#0a1a2a")
        k = min(1.0, t / 1.05)
        a = math.sin(math.pi * k)
        ang = self.out - 1.3 + 2.6 * ease_in_out(k)
        rr = self.radius * 0.55
        at = self.at + QPointF(math.cos(ang) * rr, math.sin(ang) * rr)
        heading = ang + math.pi / 2
        _shark(p, at, self.scale * 0.28, heading, with_alpha(cols[0], 0.75 * a),
               with_alpha(cols[-1], 0.7 * a))

    def _b_glitch(self, p, t, layer, i) -> None:
        if t > 0.55:
            return
        cols = self._cols(layer, "#ff2bd6")
        rr = random.Random(int(t * 30) + self.seed)
        a = 1 - t / 0.55
        for _k in range(int(layer.get("count", 14))):
            x = self.at.x() + rr.uniform(-1, 1) * self.radius * 0.8
            y = self.at.y() + rr.uniform(-1, 1) * self.radius * 0.6
            w, h = rr.uniform(6, 30) * self.scale / 300, rr.uniform(2, 7) * self.scale / 300
            p.fillRect(QRectF(x, y, w, h), with_alpha(rr.choice(cols), 0.8 * a))

    def _b_scan(self, p, t, layer, i) -> None:
        if t > 0.6:
            return
        col = self._cols(layer, "#ffffff")[0]
        rr = random.Random(int(t * 20) + self.seed)
        a = 1 - t / 0.6
        for _k in range(int(layer.get("count", 6))):
            y = self.at.y() + rr.uniform(-1, 1) * self.radius * 0.7
            w = self.radius * rr.uniform(0.6, 1.6)
            p.fillRect(QRectF(self.at.x() - w / 2 + rr.uniform(-10, 10), y, w, rr.uniform(1, 3)), with_alpha(col, 0.6 * a))

    def _b_streaks(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#ff2a2a")
        n = int(layer.get("count", 10))
        for j in range(n):
            rr = random.Random(self.seed * 17 + j)
            ang = self.out + rr.uniform(-0.6, 0.6)
            lt = t - rr.uniform(0, 0.08)
            if lt < 0 or lt > 0.45:
                continue
            k = lt / 0.45
            head = self.radius * 1.3 * ease_out(k)
            tail = head * (0.25 + 0.5 * k)
            a = (1 - k) ** 1.2
            p1 = self.at + QPointF(math.cos(ang) * tail, math.sin(ang) * tail)
            p2 = self.at + QPointF(math.cos(ang) * head, math.sin(ang) * head)
            p.setPen(QPen(with_alpha(cols[j % len(cols)], a), 2.2 * (1 - k * 0.5), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawLine(p1, p2)

    def _b_vines(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#2a0a10")
        grow = ease_out(min(1.0, t / 0.4))
        a = 1 - ease_in_out(max(0.0, (t - 0.55) / 0.55))
        for j in range(int(layer.get("count", 6))):
            rr = random.Random(self.seed * 23 + j)
            ang = self.out + rr.uniform(-1.2, 1.2)
            ln = self.radius * rr.uniform(0.5, 0.9) * grow
            path = QPainterPath(self.at)
            mid = self.at + QPointF(math.cos(ang + 0.5) * ln * 0.5, math.sin(ang + 0.5) * ln * 0.5)
            end = self.at + QPointF(math.cos(ang) * ln, math.sin(ang) * ln)
            path.quadTo(mid, end)
            col = cols[j % len(cols)]
            p.setPen(QPen(with_alpha(col, a), 2.2 * self.scale / 300, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(col, a))
            for f in (0.3, 0.55, 0.8):
                pt = path.pointAtPercent(f)
                d = path.angleAtPercent(f)
                p.save()
                p.translate(pt)
                p.rotate(-d)
                p.drawPolygon([QPointF(-2, 0), QPointF(2, 0), QPointF(0.5, -5 if j % 2 else 5)])
                p.restore()

    def _b_mist(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#e8f0ff")
        k = min(1.0, t / BURST_TIME)
        a = math.sin(math.pi * min(1.0, k * 1.2)) * float(layer.get("alpha", 0.4))
        for j in range(5):
            rr = random.Random(self.seed * 3 + j)
            ang = self.out + rr.uniform(-1.2, 1.2)
            dist = self.radius * (0.15 + 0.5 * ease_out(k)) * rr.uniform(0.6, 1.0)
            at = self.at + QPointF(math.cos(ang) * dist, math.sin(ang) * dist)
            size = self.radius * (0.18 + 0.25 * k) * rr.uniform(0.7, 1.2)
            g = QRadialGradient(at, size)
            g.setColorAt(0, with_alpha(cols[j % len(cols)], a))
            g.setColorAt(1, with_alpha(cols[j % len(cols)], 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(at, size, size)

    def _b_gold(self, p, t, layer, i) -> None:
        """Golden repair lines glowing into the cracks a moment after the hit."""
        gold = self._cols(layer, "#f2c14e")[0]
        k = (t - 0.25) / 0.6
        if k <= 0:
            return
        a = min(1.0, k * 2) * (1 - max(0.0, (t - 0.85) / 0.3))
        upto = self.reach * ease_out(min(1.0, k))
        p.translate(self.at)
        for b in self.branches:
            if b.depth > 1:
                continue
            path = _branch_path(b, upto)
            p.setPen(QPen(with_alpha(gold, 0.5 * a), b.width * 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
            p.setPen(QPen(with_alpha(QColor(255, 244, 200), a), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)

    def _b_ink(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#0a0a0a")
        k = ease_out(min(1.0, t / 0.35))
        a = 1 - ease_in_out(max(0.0, (t - 0.5) / 0.6))
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(int(layer.get("count", 9))):
            rr = random.Random(self.seed * 41 + j)
            ang = self.out + rr.uniform(-1.3, 1.3)
            dist = self.radius * rr.uniform(0.2, 0.8) * k
            at = self.at + QPointF(math.cos(ang) * dist, math.sin(ang) * dist)
            size = self.scale * rr.uniform(0.012, 0.04) * (0.4 + 0.6 * k)
            p.setBrush(with_alpha(cols[j % len(cols)], a))
            p.drawEllipse(at, size, size * rr.uniform(0.6, 1.0))

    def _b_ripple(self, p, t, layer, i) -> None:
        cols = self._cols(layer, "#9ff7ff")
        for k in range(3):
            lt = t - k * 0.12
            if lt < 0 or lt > 0.8:
                continue
            q = lt / 0.8
            rr = self.radius * 0.9 * ease_out(q)
            col = QColor.fromHsvF((t * 0.8 + k * 0.25) % 1.0, 0.55, 1.0, 1.0) if layer.get("iridescent") else \
                cols[k % len(cols)]
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(col, (1 - q) ** 1.3), 2.0 * (1 - q * 0.6)))
            p.drawEllipse(self.at, rr, rr * 0.78)
            p.setPen(QPen(with_alpha(QColor(255, 255, 255), 0.5 * (1 - q)), 0.8))
            p.drawEllipse(self.at, rr * 0.96, rr * 0.74)

    def _b_holo(self, p, t, layer, i) -> None:
        col = self._cols(layer, "#9fefff")[0]
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(3):
            lt = t - k * 0.1
            if lt < 0 or lt > 0.7:
                continue
            q = lt / 0.7
            rr = self.radius * (0.3 + 0.7 * ease_out(q))
            p.setPen(QPen(with_alpha(col, 0.8 * (1 - q)), 1.2))
            p.drawEllipse(self.at, rr, rr)
            span = 40 * 16
            p.setPen(QPen(with_alpha(col, 1 - q), 2.6))
            start = int((math.degrees(-self.out) + t * 220 + k * 120) * 16)
            p.drawArc(QRectF(self.at.x() - rr, self.at.y() - rr, 2 * rr, 2 * rr), start, span)

    def _b_flash(self, p, t, layer, i) -> None:
        col = self._cols(layer, "#fff4dc")[0]
        if t > 0.4:
            return
        flick = 1.0 if int(t * 30) % 3 else 0.45
        a = (1 - t / 0.4) * flick
        g = QRadialGradient(self.at, self.radius * 1.1)
        g.setColorAt(0, with_alpha(col, 0.8 * a))
        g.setColorAt(1, with_alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(self.at, self.radius * 1.1, self.radius * 1.1)


# -- on screen ---------------------------------------------------------------------------------------------------------
class ImpactWindow(OverlayWindow):
    """One impact, in its own small click-through window round the hit (so it stays where it happened)."""

    def __init__(self, impact: Impact, screen_at: QPointF, always_on_top: bool = True) -> None:
        super().__init__(always_on_top)
        self.set_click_through(True)
        self.impact = impact
        half = int(impact.radius * 1.35) + 8
        self.setGeometry(QRect(round(screen_at.x() - half), round(screen_at.y() - half), 2 * half, 2 * half))
        impact.at = QPointF(half, half)
        impact.dpr = 1.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def showEvent(self, event) -> None:
        self.impact.dpr = self.devicePixelRatioF()
        super().showEvent(event)

    def _tick(self) -> None:
        now = time.monotonic()
        if not self.impact.alive(now):
            self._timer.stop()
            self.hide()
            self.deleteLater()
            return
        want = 16 if self.impact.busy_burst(now) or now - self.impact.born < CRACK_GROW + 0.05 else 33
        if self._timer.interval() != want:
            self._timer.setInterval(want)                       # smooth for the burst, lighter while it fades
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        try:
            self.impact.paint(p, time.monotonic())
        except Exception:
            import logging
            logging.getLogger("capri").exception("impact: a frame failed to draw")
        finally:
            p.end()


class Impacts:
    """Starts vibe impacts. One per throw (the first slam); a few may still be fading at once."""

    MAX = 3

    def __init__(self) -> None:
        self.windows: list[ImpactWindow] = []
        self._seed = random.Random()

    def spawn(self, screen_at: QPointF, normal: QPointF, spec: dict, height: float, reduced: bool = False):
        if not spec or validate(spec):
            return None
        self.windows = [w for w in self.windows if w.isVisible()]
        while len(self.windows) >= self.MAX:
            old = self.windows.pop(0)
            old.hide()
            old.deleteLater()
        imp = Impact(QPointF(), normal, spec, height, self._seed.randrange(1, 10 ** 6), reduced)
        w = ImpactWindow(imp, screen_at)
        w.show()
        w.raise_()
        self.windows.append(w)
        return w
