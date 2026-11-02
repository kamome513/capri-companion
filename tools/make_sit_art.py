"""Builds her "sitting on a window" sprite (assets/perch/) from the picture of her perched on
a window's title bar against a blue sky: cuts her out and splits off the parts that move.

    python tools/make_sit_art.py <picture>

Out (full resolution, smooth edges, her flat colours cleaned of compression noise):
  base.png      her, minus both lower legs (with what they hid painted back in)
  black.png     the black lower leg, swinging from its knee (the bit behind the red leg filled in)
  red.png       the red lower leg and shoe, swinging from its knee - drawn in front
  sit.json      where she sits and where each knee bends
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "assets" / "perch"
SEAT = 868                     # the window's top edge in the picture: she sits on it
BLACK_KNEE = (379, 872)
BLACK_FOOT = (468, 1022)
RED_KNEE = (377, 730)
RED_FOOT = (356, 1020)
RED_CUT = 752                  # the red leg's own part starts below here
BLACK_CUT = 880
KEEP = 46                      # px of each shin's top also kept in the body
PALETTE = np.array([[238, 18, 68], [12, 8, 16], [24, 232, 110]])   # her crimson, black and neon green


def grow(m: np.ndarray, n: int = 1) -> np.ndarray:
    from capri.ui.looks import _grow
    for _ in range(n):
        m = _grow(m)
    return m


def shrink(m: np.ndarray, n: int = 1) -> np.ndarray:
    return ~grow(~m, n)


def regions(mask: np.ndarray):
    from capri.ui.looks import flood
    seen = np.zeros_like(mask)
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        s = np.zeros_like(mask)
        s[y, x] = True
        r = flood(s, mask, limit=8000)
        seen |= r
        yield r


def cut_out(a: np.ndarray) -> np.ndarray:
    """Her: everything that isn't sky, cloud or window, connected to her body."""
    from capri.ui.looks import flood
    rgb = a[..., :3].astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    background = (((b > r + 40) & (b > 140) & (mx >= 75)) | ((mn > 150) & (sat < 0.25))
                  | ((r > 170) & (g > 170) & (b > 140))
                  | ((b > r + 25) & (b > g + 10) & (r < 40)))          # the title bar's dark blue edge
    her = ~background
    box = np.zeros_like(her)
    box[240:1060, 30:580] = True
    her &= box
    seed = np.zeros_like(her)
    for x, y in ((300, 450), BLACK_FOOT, RED_FOOT, (250, 830)):
        seed[y, x] = True
    fig = flood(seed, her, limit=8000)
    for region in regions(~fig & ~flood(~box | _edge(fig), ~fig, limit=8000)):
        if region.sum() < 500:                                       # specks inside her: her eye, glints
            fig |= region
    return fig


def _edge(m: np.ndarray) -> np.ndarray:
    e = np.zeros_like(m)
    e[0, :] = e[-1, :] = e[:, 0] = e[:, -1] = True
    return e


def clean_colours(a: np.ndarray, fig: np.ndarray) -> np.ndarray:
    """Flat colours like the show: pixels close to her crimson / black / green snap to it."""
    out = a.copy()
    rgb = a[..., :3].astype(int)
    d = np.linalg.norm(rgb[:, :, None, :] - PALETTE[None, None], axis=-1)
    near, which = d.min(-1), d.argmin(-1)
    snap = fig & ((near < 60) | ((which == 0) & (near < 120)))      # her crimson, even blurred toward the sky
    out[snap, :3] = PALETTE[which[snap]]
    # her outline takes the colour just inside it (no sky-blue fringe)
    ring = fig & ~shrink(fig)
    inside = fig & ~ring
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        src = np.roll(np.roll(inside, dy, 0), dx, 1)
        take = ring & src
        out[take, :3] = np.roll(np.roll(out, dy, 0), dx, 1)[take, :3]
    return out


def soft_alpha(fig: np.ndarray) -> np.ndarray:
    """Anti-aliased edges: the mask, lightly blurred."""
    f = fig.astype(np.float32)
    k = np.zeros_like(f)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            k += np.roll(np.roll(f, dy, 0), dx, 1) * (2 if dy == dx == 0 else 1)
    alpha = np.clip(k / 10 * 1.6 - 0.3, 0, 1)
    return (np.where(fig, np.maximum(alpha, 0.45), 0) * 255).astype(np.uint8)    # nothing outside her: no fringe


def main(picture: str) -> None:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from capri.ui.looks import flood, to_array, to_image
    a = to_array(QImage(picture))
    fig = cut_out(a)
    h, w = fig.shape
    yy, xx = np.mgrid[0:h, 0:w]
    col = clean_colours(a, fig)
    rgb = col[..., :3].astype(int)
    dark = fig & (rgb.max(-1) < 80)
    red = fig & (rgb[..., 0] > 120) & (rgb[..., 1] < 90)

    seed = np.zeros_like(fig)
    seed[RED_FOOT[1], RED_FOOT[0]] = True
    red_leg = flood(seed, red & (yy >= RED_CUT - 14) & (xx >= 200) & (xx <= 405), limit=4000)
    red_leg = grow(red_leg, 2) & fig & ~dark & (yy >= RED_CUT - 14)                       # its soft outline too
    seed = np.zeros_like(fig)
    seed[BLACK_FOOT[1], BLACK_FOOT[0]] = True
    black_leg = flood(seed, dark & (yy >= BLACK_CUT - 14) & (xx >= 345), limit=4000)
    black_leg = grow(black_leg, 2) & fig & ~red & (yy >= BLACK_CUT - 14) & (xx >= 345)   # its soft outline too
    # the black shin behind the red leg, painted in (so it's whole when they swing apart)
    behind = shrink(grow(black_leg, 12), 12) & (yy >= BLACK_CUT - 14) & (xx >= 345) & ~black_leg
    black_leg_full = black_leg | behind
    black_leg_full = grow(black_leg_full) & (black_leg_full | fig) & (yy >= BLACK_CUT - 14) & ~grow(red_leg) \
        | black_leg_full

    alpha = soft_alpha(fig)
    out = col.copy()
    out[..., 3] = alpha
    black = np.zeros_like(out)
    black[black_leg_full] = out[black_leg_full]
    black[black_leg_full, :3] = PALETTE[1]
    black[behind, 3] = 255
    redl = np.zeros_like(out)
    red_all = grow(red_leg) & (out[..., 3] > 0) & (yy >= RED_CUT - 14) & ~black_leg
    redl[red_all] = out[red_all]

    base = out.copy()
    # the top of each lower leg stays in the body as well: as the leg swings, the knee never opens
    gone = (red_all & (yy >= RED_CUT + KEEP)) | (black_leg & (yy >= BLACK_CUT + KEEP))
    base[gone, 3] = 0
    # the top of the black shin carries on behind the red leg: painted in, so it's there when the red leg swings
    hidden = behind & (yy < BLACK_CUT + KEEP) & (base[..., 3] < 255) | (behind & red_all & (yy < BLACK_CUT + KEEP))
    base[hidden, :3] = PALETTE[1]
    base[hidden, 3] = 255
    for y in range(BLACK_KNEE[1], BLACK_CUT + KEEP):             # and right up against the red leg's edge
        xs = np.flatnonzero(red_all[y])
        if len(xs) and dark[y, xs.max() + 1:xs.max() + 4].any():
            base[y, max(xs.min(), xs.max() - 12):xs.max() + 1, :3] = PALETTE[1]
            base[y, max(xs.min(), xs.max() - 12):xs.max() + 1, 3] = 255
    # what the red leg hid: her black thigh runs on behind it - paint it in, row by row
    for y in range(RED_CUT + KEEP, h):
        row = gone[y] & red_all[y]
        if not row.any():
            continue
        xs = np.flatnonzero(row)
        left, right = xs.min(), xs.max()
        lx = np.flatnonzero(dark[y, max(0, left - 30):left] & ~gone[y, max(0, left - 30):left])
        rx = np.flatnonzero(dark[y, right + 1:right + 31] & ~gone[y, right + 1:right + 31])
        if len(lx) and len(rx):
            base[y, left:right + 1, :3] = PALETTE[1]
            base[y, left:right + 1, 3] = 255

    ys, xs = np.nonzero(fig)
    x0, y0, x1, y1 = (int(v) for v in (xs.min() - 12, ys.min() - 12, xs.max() + 13, ys.max() + 13))
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    for name, img in (("base", base), ("black", black), ("red", redl)):
        to_image(np.ascontiguousarray(img[y0:y1, x0:x1])).save(str(OUT / f"{name}.png"))
    info = {"size": [int(x1 - x0), int(y1 - y0)], "seat": SEAT - y0,
            "black_knee": [BLACK_KNEE[0] - x0, BLACK_KNEE[1] - y0], "red_knee": [RED_KNEE[0] - x0, RED_KNEE[1] - y0]}
    (OUT / "sit.json").write_text(json.dumps(info, indent=1))
    print("wrote", OUT, info)


if __name__ == "__main__":
    main(sys.argv[1])
