"""Wild hair: big jagged hair shards that grow out behind Capri's head and move.

Drawn *behind* the art, so her face and the original hair stay exactly as
drawn - the shards only make the silhouette wilder, like the hair-storm
around her in the show. Low-poly like the sheet: each shard has a lit and a
shaded facet, in colours sampled from her sprite.

* idle: a slow sway, like hair drifting in a data-stream
* talking: the shards flare and whip with her voice
* now and then a shard glitches sideways for a frame
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform

HAIR = QColor(249, 11, 68)
HAIR_SHADE = QColor(176, 4, 50)
HAIR_LIGHT = QColor(255, 64, 104)
OUTLINE = QColor(70, 0, 22)
EDGE = QColor(132, 76, 255)


@dataclass(frozen=True)
class Shard:
    angle: float      # degrees around the head, 90 = straight up
    lean: float       # extra tilt of the shard's direction, degrees
    length: float     # x head width
    width: float      # x head width (half-width at the base)
    fork: float       # 0 = single point, >0 = a smaller second point on one side
    phase: float
    speed: float


def make_shards(seed: int = 11) -> list[Shard]:
    rng = random.Random(seed)
    angles = [198, 172, 150, 128, 108, 90, 72, 52, 30, 8, -18]
    shards = []
    for a in angles:
        a += rng.uniform(-7, 7)
        side = math.cos(math.radians(a))                      # -1 left ... 1 right
        lean = -side * rng.uniform(10, 24)                    # side shards sweep upward, like flames
        length = rng.uniform(0.42, 0.62) + 0.22 * abs(side)
        shards.append(Shard(a, lean, length, rng.uniform(0.15, 0.24),
                            rng.choice((0.0, 0.0, rng.uniform(0.35, 0.55))),
                            rng.uniform(0, math.tau), rng.uniform(0.7, 1.4)))
    return shards


class WildHair:
    def __init__(self, seed: int = 11) -> None:
        self.shards = make_shards(seed)
        self._rng = random.Random(seed + 1)

    def margin(self, head_w: float, intensity: float) -> float:
        """How far the hair can reach outside the head box (to size the window)."""
        return head_w * 0.85 * intensity

    def paint(self, p: QPainter, head: QRectF, t: float, intensity: float, energy: float = 0.0) -> None:
        if intensity <= 0 or head.width() <= 0:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hw = head.width()
        cx, cy = head.center().x(), head.top() + head.height() * 0.48
        rx, ry = hw * 0.30, head.height() * 0.32               # bases sit inside the hair mass
        glitch_i = self._rng.randrange(len(self.shards)) if self._rng.random() < 0.03 + 0.2 * energy else -1
        pen = QPen(OUTLINE, max(1.0, hw * 0.01), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap,
                   Qt.PenJoinStyle.MiterJoin)
        for i, s in enumerate(self.shards):
            sway = 5 * math.sin(t * 0.9 * s.speed + s.phase) + 12 * energy * math.sin(t * 7.5 + s.phase)
            a = math.radians(s.angle)
            base = QPointF(cx + rx * math.cos(a), cy - ry * math.sin(a))
            da = math.radians(s.angle + s.lean + sway)
            d = QPointF(math.cos(da), -math.sin(da))                       # outward
            n = QPointF(-d.y(), d.x())                                     # sideways
            flare = 1 + 0.06 * math.sin(t * 1.5 * s.speed + s.phase) + 0.3 * energy
            length = s.length * hw * intensity * flare
            width = s.width * hw * (0.55 + 0.45 * intensity)
            tip = base + d * length
            if i == glitch_i:
                tip = tip + n * self._rng.uniform(-0.15, 0.15) * hw
            left, right = base + n * width, base - n * width
            knee = base + d * (length * 0.5) + n * (width * 0.55)          # a kink in one edge
            points = [left, knee, tip]
            if s.fork:
                fork_tip = base + d * (length * s.fork * 1.2) - n * (width * 1.4)
                points += [base + d * (length * 0.42) - n * (width * 0.15), fork_tip]
            points.append(right)
            p.setPen(pen)
            p.setBrush(HAIR)
            p.drawPolygon(QPolygonF(points))
            # shaded facet (low-poly look): the half from the centre line to the right edge
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(HAIR_SHADE)
            p.drawPolygon(QPolygonF([base, tip, right]))
            p.setBrush(HAIR_LIGHT)
            p.drawPolygon(QPolygonF([base, knee, base + d * (length * 0.75)]))
            if i % 4 == 0:                                                  # a thin neon edge here and there
                edge = QColor(EDGE)
                edge.setAlpha(150)
                p.setPen(QPen(edge, max(1.0, hw * 0.008)))
                p.drawLine(right, tip)
        p.restore()


# -- "storm": the hair as it looks in the show -------------------------------------------------
# A ragged pile of zigzag strands - like torn paper or lightning - blown up and out round her head,
# a few hanging down beside her face, gaps of sky between them at the edges. Flat hot pink with white
# speckles. Everything sways continuously (no stepped "boil"); talking makes the strands whip.
STORM_RED = QColor(249, 8, 84)           # hot pink-red, sampled from her reference picture
STORM_DEEP = QColor(178, 6, 56)
STORM_LIGHT = QColor(255, 132, 178)
STORM_DARK = QColor(22, 4, 16)           # the odd black spike
STORM_EDGE = QColor(110, 91, 191)        # (the blue-purple of her outline - the leg blades use it)
STORM_GLOW = QColor(255, 30, 100)
SPARKLE = QColor(255, 255, 255)


class StormHair:
    """Her hair: the outline traced from her reference picture (hair_shape.py), copied 1:1 - flat hot
    pink with white speckles, the black spiky crown above her face and the black spike past her
    shoulder. Drawn over her (her own sprite hair hidden where the figure allows), with her face put
    back on top. It sways continuously around her face - tips more than roots - and flares when she
    talks; the outline itself never changes, so it stays crisp."""

    MOVE_FPS = 30         # while she talks
    IDLE_MOVE_FPS = 15    # at rest: a slow, smooth sway

    def __init__(self, seed: int = 21, flow_in: bool = False) -> None:
        from . import hair_shape
        self.seed = seed
        self.flow_in = flow_in                   # lying down: also covers her own hair right down to her face
        self.points = hair_shape.HAIR
        self.shards: list = []                   # (nothing grows down into her: the traced outline is all)
        self._crown, self._spike, self._anchor = hair_shape.CROWN, hair_shape.SPIKE, hair_shape.ANCHOR
        rng = random.Random(seed + 7)
        self.sparkles = [(rng.random(), rng.random(), rng.uniform(0, math.tau), rng.uniform(1.0, 3.0))
                         for _ in range(2200)]
        self._cache_key = None
        self._cache_img: QImage | None = None
        self._textures: dict[tuple, list[QImage]] = {}

    def _texture(self, w: int, h: int, hw: float, n: int) -> QImage:
        """Flat pink with crisp white speckles, pre-rendered (3 twinkle variants), used as the fill brush."""
        key = (w, h, round(hw))
        if key not in self._textures:
            variants = []
            for v in range(3):
                img = QImage(max(1, w), max(1, h), QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(STORM_RED)
                q = QPainter(img)
                dot = max(1.0, round(hw * 0.012))
                for sx, sy, phase, speed in self.sparkles:
                    a = 0.5 + 0.5 * math.sin(v * 2.1 * speed + phase)
                    c = QColor(SPARKLE)
                    c.setAlpha(int(110 + 145 * a))
                    q.fillRect(QRectF(round(sx * w), round(sy * h), dot, dot), c)
                q.end()
                variants.append(img)
            if len(self._textures) >= 8:
                self._textures.pop(next(iter(self._textures)))
            self._textures[key] = variants
        return self._textures[key][n % 3]

    def margin(self, head_w: float, intensity: float) -> float:
        return head_w * 1.4 * (0.5 + 0.5 * intensity)

    def step(self, t: float, energy: float) -> tuple[int, int]:
        """Which frame of its motion we're on - the hair is only redrawn when this changes."""
        rate = self.MOVE_FPS if energy > 0 else self.IDLE_MOVE_FPS
        return rate, int(t * rate)

    def paint_cached(self, p: QPainter, head: QRectF, t: float, intensity: float, energy: float,
                     size: tuple[int, int], dpr: float) -> None:
        """At rest, render each frame of the sway once and reuse it until the next."""
        if energy > 0:
            return self.paint(p, head, t, intensity, energy)
        key = (self.step(t, 0.0), round(head.x()), round(head.y()), round(head.width()), round(head.height()),
               intensity, size, dpr)
        if key != self._cache_key:
            img = QImage(round(size[0] * dpr), round(size[1] * dpr), QImage.Format.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(0)
            q = QPainter(img)
            self.paint(q, head, t, intensity, 0.0)
            q.end()
            self._cache_key, self._cache_img = key, img
        p.drawImage(QPointF(0, 0), self._cache_img)

    # -- shape ---------------------------------------------------------------------------------------
    def _place(self, polys, head: QRectF, t: float, intensity: float, energy: float) -> list[QPolygonF]:
        """The traced outline on this head, swaying: each point turns a little round her face, the
        further out the more, in a slow wave that runs round the hair (and whips when she talks)."""
        hw, hh = head.width(), head.height()
        ax, ay = head.left() + self._anchor[0] * hw, head.top() + self._anchor[1] * hh
        size = (0.6 + 0.4 * intensity) * (1 + 0.05 * energy)
        out = []
        for poly in polys:
            pts = []
            for u, v in poly:
                dx, dy = (head.left() + u * hw - ax) * size, (head.top() + v * hh - ay) * size
                reach = min(1.6, math.hypot(dx / hw, dy / hh))
                around = math.atan2(dy, dx)
                turn = math.radians(reach * (2.2 * math.sin(t * 0.8 + around * 1.5)
                                             + 7 * energy * math.sin(t * 8.5 + around * 3)))
                c, s_ = math.cos(turn), math.sin(turn)
                pts.append(QPointF(ax + dx * c - dy * s_, ay + dx * s_ + dy * c))
            out.append(QPolygonF(pts))
        return out

    def mass(self, head: QRectF, t: float, intensity: float, energy: float) -> QPolygonF:
        """The main body of the hair (its biggest outline)."""
        polys = self._place(self.points, head, t, intensity, energy)
        return max(polys, key=lambda q: q.count())

    def shape(self, head: QRectF, t: float, intensity: float, energy: float) -> QPainterPath:
        """Her whole hair outline (gaps of sky between strands left open)."""
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        for poly in self._place(self.points, head, t, intensity, energy):
            path.addPolygon(poly)
            path.closeSubpath()
        return path

    # -- drawing ---------------------------------------------------------------------------------------
    def paint(self, p: QPainter, head: QRectF, t: float, intensity: float, energy: float = 0.0) -> None:
        if intensity <= 0 or head.width() <= 0:
            return
        hw, hh = head.width(), head.height()
        rate, n = self.step(t, energy)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(STORM_DARK)
        for poly in self._place(self._spike, head, t, intensity, energy):     # the black spike, behind
            p.drawPolygon(poly)
        hair = self.shape(head, t, intensity, energy)
        if self.flow_in:                                         # lying: her own hair is still drawn - cover it
            patch = QPainterPath()
            jag = [QPointF(head.left() - hw * 0.06 + hw * 1.12 * i / 8, head.top() + hh * (1.3 if i % 2 else 1.1))
                   for i in range(9)]                            # (her lying head box is cut to 80%: all of it)
            patch.addPolygon(QPolygonF([QPointF(head.left() - hw * 0.06, head.top()), *jag,
                                        QPointF(head.right() + hw * 0.06, head.top())]))
            patch.closeSubpath()
            hair = hair.united(patch)
        tw, th = int(hw * 5), int(hh * 5)
        p.setBrushOrigin(QPointF(round(head.center().x() - tw / 2), round(head.top() - th * 0.55)))
        p.setBrush(QBrush(self._texture(tw, th, hw, n // max(1, rate // 4))))
        p.drawPath(hair)
        p.setBrushOrigin(QPointF(0, 0))
        p.setBrush(STORM_DARK)
        # the black crown over her face - with a thick edge of its own colour, so no sliver of desktop shows
        # between it and her hair or the top of her head
        seam = QPen(STORM_DARK, max(2.0, hw * 0.07))
        seam.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(seam)
        for poly in self._place(self._crown, head, t, intensity, energy):
            p.drawPolygon(poly)
        p.setPen(Qt.PenStyle.NoPen)
        p.restore()


# -- "classic": her first hair-storm, as a style you can pick ------------------------------------------
CLASSIC_RED = QColor(236, 16, 70)
CLASSIC_STRIPE = QColor(110, 4, 36, 40)  # fine darker strands
CLASSIC_SPARKLE = QColor(255, 190, 214)


class ClassicStormHair:
    """The first hair-storm (1.0 - 1.26): one big, wide, jagged mass of red with sparkles. Pick it as "Classic spiky".

    Drawn over her sprite's own hair, with her face layer put back on top, so
    the green mask peeks out of the mass like in the anime. The outline
    "boils" (re-jitters 8 times a second, like hand-drawn animation), the
    strands on one side hang down, and talking makes it flare.
    """

    BOIL_FPS = 8          # while she talks
    IDLE_BOIL_FPS = 4     # calmer (and cheaper) at rest

    def __init__(self, seed: int = 21, flow_in: bool = False) -> None:
        self.seed = seed
        self.flow_in = flow_in                   # lying down: no edge line where the hair meets her body
        self._rng = random.Random(seed + 1)
        rng = random.Random(seed)
        # outline: walk round a wide box, alternating spikes and deep notches
        self.points: list[tuple[float, float, float]] = []     # (u, v, spike) in box units
        n = 22                                   # fewer, chunkier jags than a starburst
        for i in range(n):
            u = i / n
            spike = rng.uniform(0.30, 0.75) if i % 2 == 0 else -rng.uniform(0.15, 0.45)
            self.points.append((u, rng.uniform(-0.04, 0.04), spike))

        # long strands hang down on her right side only, like in the show
        self.drips = [(rng.uniform(0.72, 0.96), rng.uniform(0.7, 1.15), rng.uniform(0.05, 0.08)) for _ in range(3)]
        if flow_in:                              # lying down: none (they left gaps over her own hair)
            self.drips = []
        self.sparkles = [(rng.random(), rng.random(), rng.uniform(0, math.tau), rng.uniform(1.0, 3.0))
                         for _ in range(170)]

        self._cache_key = None
        self._cache_img: QImage | None = None
        self._textures: dict[tuple, list[QImage]] = {}

    def _texture(self, w: int, h: int, hw: float, n: int) -> QImage:
        """Red + fine stripes + sparkles, pre-rendered (3 twinkle variants), used as the fill brush."""
        key = (w, h, round(hw))
        if key not in self._textures:
            variants = []
            for v in range(3):
                img = QImage(max(1, w), max(1, h), QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(CLASSIC_RED)
                q = QPainter(img)
                stripe = CLASSIC_STRIPE
                step = max(2.0, hw * 0.03)
                xs = 0.0
                while xs < w:
                    q.fillRect(QRectF(xs, 0, max(1.0, step * 0.4), h), stripe)
                    xs += step
                dot = max(1.0, hw * 0.018)
                for sx, sy, phase, speed in self.sparkles:
                    a = 0.5 + 0.5 * math.sin(v * 2.1 * speed + phase)
                    c = QColor(CLASSIC_SPARKLE)
                    c.setAlpha(int(70 + 160 * a))
                    q.fillRect(QRectF(sx * w, sy * h, dot, dot), c)
                q.end()
                variants.append(img)
            if len(self._textures) >= 8:                # a few sizes: idle / blink / look frames differ
                self._textures.pop(next(iter(self._textures)))
            self._textures[key] = variants
        return self._textures[key][n % 3]

    def margin(self, head_w: float, intensity: float) -> float:
        return head_w * 1.1 * (0.5 + 0.5 * intensity)

    def step(self, t: float, energy: float) -> tuple[int, int]:
        """Which boil step we're on - the hair only changes when this does."""
        rate = self.BOIL_FPS if energy > 0 else self.IDLE_BOIL_FPS
        return rate, int(t * rate)

    def paint_cached(self, p: QPainter, head: QRectF, t: float, intensity: float, energy: float,
                     size: tuple[int, int], dpr: float) -> None:
        """At rest, render each boil step once and reuse it until the next step."""
        if energy > 0:
            return self.paint(p, head, t, intensity, energy)
        key = (self.step(t, 0.0), round(head.x()), round(head.y()), round(head.width()), round(head.height()),
               intensity, size, dpr)
        if key != self._cache_key:
            img = QImage(round(size[0] * dpr), round(size[1] * dpr), QImage.Format.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(0)
            q = QPainter(img)
            self.paint(q, head, t, intensity, 0.0)
            q.end()
            self._cache_key, self._cache_img = key, img
        p.drawImage(QPointF(0, 0), self._cache_img)

    @staticmethod
    def _perimeter(u: float) -> tuple[float, float, float, float]:
        """Point on a unit box's outline (clockwise from top-left) and its outward normal."""
        u = (u % 1.0) * 4
        if u < 1:
            return u, 0.0, 0.0, -1.0           # top edge
        if u < 2:
            return 1.0, u - 1, 1.0, 0.0        # right
        if u < 3:
            return 3 - u, 1.0, 0.0, 1.0        # bottom
        return 0.0, 4 - u, -1.0, 0.0           # left

    def shape(self, head: QRectF, t: float, intensity: float, energy: float) -> QPolygonF:
        hw, hh = head.width(), head.height()
        size = 0.75 + 0.45 * intensity + 0.12 * energy
        bw, bh = hw * 1.45 * size, hh * 1.25 * size              # a big block, a bit wider than tall
        left = head.center().x() - bw / 2
        top = head.top() - hh * 0.18 * size
        rate, n = self.step(t, energy)
        t = n / rate                                                   # everything moves in boil steps
        boil = random.Random(self.seed * 1000 + n)                      # jitter steps, not drifts
        spike_len = hw * 0.36 * size
        poly = []
        for u, wobble, spike in self.points:
            x, y, nx, ny = self._perimeter(u + wobble * 0.1)
            if ny > 0:                         # bottom edge: short, mostly hidden behind her face
                spike *= 0.35
                if self.flow_in:               # lying down: no notches cutting up into it - a solid bottom
                    spike = abs(spike)
            s = spike * (1 + 0.25 * energy) + boil.uniform(-0.06, 0.06)
            # spikes lean outward and a little up, like hair caught in a gust
            px = left + x * bw + nx * s * spike_len * 1.3
            py = top + y * bh + ny * s * spike_len - (abs(nx) * s * spike_len * 0.35)
            poly.append(QPointF(px, py))
        # long strands hanging down
        for du, length, width in self.drips:
            x = left + du * bw
            y = top + bh * 0.85
            sway = 0.04 * hw * math.sin(t * 1.3 + du * 9) + boil.uniform(-0.02, 0.02) * hw
            strand = [QPointF(x - width * hw, y), QPointF(x + sway, y + length * hh * size),
                      QPointF(x + width * hw, y)]
            # insert at the matching spot on the bottom edge
            best = min(range(len(poly)), key=lambda k: (poly[k].x() - x) ** 2 + (poly[k].y() - y) ** 2)
            poly[best + 1:best + 1] = strand
        return QPolygonF(poly)

    def paint(self, p: QPainter, head: QRectF, t: float, intensity: float, energy: float = 0.0) -> None:
        if intensity <= 0 or head.width() <= 0:
            return
        poly = self.shape(head, t, intensity, energy)
        rate, n = self.step(t, energy)
        t = n / rate
        step_rng = random.Random(self.seed * 7919 + n)
        hw = head.width()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # glitch: now and then a horizontal slice of the mass jumps sideways
        bands = []
        if step_rng.random() < 0.08 + 0.3 * energy:
            box = poly.boundingRect()
            y = box.top() + step_rng.uniform(0.1, 0.8) * box.height()
            bands.append((y, step_rng.uniform(3, 9) * hw / 60, step_rng.choice((-1, 1)) * hw * 0.07))
        offset = max(1.5, hw * 0.035)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(STORM_EDGE)
        p.save()
        if self.flow_in:                  # the edge only round the top: where the hair meets her it flows in
            outer = poly.boundingRect()
            p.setClipRect(QRectF(outer.left() - hw, outer.top() - hw * 2, outer.width() + 2 * hw,
                                 head.top() + head.height() * 0.15 - (outer.top() - hw * 2)))
        p.drawPolygon(poly.translated(-offset, offset), Qt.FillRule.WindingFill)   # blue-purple edge, offset down-left
        p.restore()
        # red with fine stripes and twinkling sparkles, like the texture of her hair in the show
        box = poly.boundingRect()
        # fixed-size texture tied to her head (not the jittering outline), so it's built once
        tw, th = int(hw * 4.2), int(head.height() * 4.0)
        brush = QBrush(self._texture(tw, th, hw, n))
        brush.setTransform(QTransform.fromTranslate(head.center().x() - tw / 2, head.top() - th * 0.45))
        p.setBrush(brush)
        if self.flow_in:                  # lying down: hair all the way down to her head, no gaps in between
            hh = head.height()
            p.drawPolygon(QPolygonF([QPointF(box.left() + box.width() * 0.08, head.top() + hh * 0.15),
                                     QPointF(box.right() - box.width() * 0.08, head.top() + hh * 0.15),
                                     QPointF(head.right(), head.top() + hh * 0.75),
                                     QPointF(head.left(), head.top() + hh * 0.85)]))
        p.drawPolygon(poly, Qt.FillRule.WindingFill)
        for y, h, dx in bands:
            p.setClipRect(QRectF(box.left() - hw, y, box.width() + 2 * hw, h))
            p.drawPolygon(poly.translated(dx, 0), Qt.FillRule.WindingFill)
        p.restore()


HAIR_STYLES = {"storm": "Like the show", "classic": "Classic spiky"}     # Settings -> Character -> Hair


def make_hair(style: str, seed: int = 21, flow_in: bool = False):
    """Her hair in a style: "storm" (traced from the show, the default) or "classic" (her first one)."""
    if style == "classic":
        return ClassicStormHair(seed=seed, flow_in=flow_in)
    return StormHair(seed=seed, flow_in=flow_in)


def tint_hair(img: QImage, box: QRectF, seed: int = 3) -> QImage:
    """Her own (sprite) hair inside `box` (0..1 of the picture) recoloured to match the traced hair:
    flat STORM_RED with white speckles - so strands the new outline doesn't cover still read as the same
    hair (lying down, her face picture keeps a few beside her face). Her green mask, eyes and the dark
    parts are left alone."""
    import numpy as np
    src = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = src.width(), src.height()
    a = np.frombuffer(src.constBits(), np.uint8, src.bytesPerLine() * h).reshape(h, src.bytesPerLine())[:, : w * 4]
    a = a.reshape(h, w, 4).copy()
    x0, y0 = max(0, int(box.left() * w)), max(0, int(box.top() * h))
    x1, y1 = min(w, int(box.right() * w) + 1), min(h, int(box.bottom() * h) + 1)
    region = a[y0:y1, x0:x1].astype(int)
    r, g, b, alpha = region[..., 0], region[..., 1], region[..., 2], region[..., 3]
    reddish = (alpha > 30) & (r > 70) & (r > 1.8 * g + 10) & (r > 1.15 * b)
    out = region.copy()
    out[reddish, 0], out[reddish, 1], out[reddish, 2] = STORM_RED.red(), STORM_RED.green(), STORM_RED.blue()
    rng = np.random.default_rng(seed)
    speck = reddish & (rng.random(reddish.shape) < 0.018)
    out[speck, 0:3] = 255
    a[y0:y1, x0:x1] = out.astype(np.uint8)
    result = QImage(a.tobytes(), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
