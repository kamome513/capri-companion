"""Red "lag" lightning: real branching bolts, re-drawn every frame so they crackle.

A bolt is made by midpoint displacement - split the line, push the middle sideways,
repeat on each half with less push - which gives lightning's sharp, fractal zig-zag.
Branches fork off at random midpoints. It's drawn as a wide dim glow, a red body
and a thin white-hot core (only the core is antialiased: smoothing the wide glow
costs a lot and doesn't show).
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

RED = QColor(236, 16, 70)          # her red
HOT = QColor(255, 170, 190)        # the white-hot core
EDGE = QColor(110, 91, 191)        # the blue-purple fringe from her hair


def bolt(start: QPointF, end: QPointF, rng: random.Random, roughness: float = 0.22, depth: int = 5,
         branch: float = 0.35) -> list[list[QPointF]]:
    """[main path, branch, branch...] from start to end."""
    paths: list[list[QPointF]] = []

    def split(a: QPointF, b: QPointF, push: float, level: int, out: list[QPointF], branches: bool) -> None:
        if level == 0:
            out.append(b)
            return
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        offset = rng.uniform(-push, push) * length
        mid = QPointF((a.x() + b.x()) / 2 + nx * offset, (a.y() + b.y()) / 2 + ny * offset)
        split(a, mid, push * 0.92, level - 1, out, branches)
        if branches and level >= 2 and rng.random() < branch:
            angle = math.atan2(dy, dx) + rng.choice((-1, 1)) * rng.uniform(0.35, 0.9)
            reach = length * rng.uniform(0.25, 0.55)
            tip = QPointF(mid.x() + math.cos(angle) * reach, mid.y() + math.sin(angle) * reach)
            fork = [mid]
            split(mid, tip, push, max(1, level - 2), fork, False)
            paths.append(fork)
        split(mid, b, push * 0.92, level - 1, out, branches)

    main = [start]
    split(start, end, roughness, depth, main, True)
    return [main] + paths


def draw(p: QPainter, paths: list[list[QPointF]], strength: float = 1.0, width: float = 1.0) -> None:
    """Glow, body and core for a bolt (branches thinner). strength 0..1 fades it."""
    if strength <= 0 or not paths:
        return
    main = QPainterPath()
    side = QPainterPath()
    for i, pts in enumerate(paths):
        target = main if i == 0 else side
        target.moveTo(pts[0])
        for pt in pts[1:]:
            target.lineTo(pt)
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    for shape, scale in ((main, 1.0), (side, 0.55)):
        for color, w, alpha, smooth in ((EDGE, 11, 50, False), (RED, 5.5, 190, False), (HOT, 1.8, 255, True)):
            c = QColor(color)
            c.setAlpha(int(alpha * max(0.0, min(1.0, strength))))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, smooth)
            p.setPen(QPen(c, max(1.0, w * scale * width), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.BevelJoin))
            p.drawPath(shape)
    p.restore()


def crackle(p: QPainter, trail: list[tuple[float, QPointF]], now: float, life: float, heights: list[float],
            rng: random.Random, arcs: int = 6) -> None:
    """Lightning crackling along the path she just took: short branching arcs between
    nearby points of her trail, at body heights, flickering and fading with age."""
    live = [(t, pt) for t, pt in trail if now - t < life]
    if len(live) < 2:
        return
    for _ in range(arcs):
        i = rng.randrange(len(live) - 1)
        j = min(len(live) - 1, i + rng.randint(2, 6))
        (ta, a), b = live[i], live[j][1]
        age = (now - ta) / life
        if rng.random() < 0.15:                      # flicker: an arc skips a frame now and then
            continue
        up_a, up_b = rng.choice(heights), rng.choice(heights)
        start = a - QPointF(rng.uniform(-14, 14), up_a)
        end = b - QPointF(rng.uniform(-14, 14), up_b)
        draw(p, bolt(start, end, rng, roughness=0.28, depth=4, branch=0.4), (1 - age) * rng.uniform(0.7, 1.0),
             width=0.9 + 0.4 * (1 - age))
