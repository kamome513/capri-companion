"""Cut Capri's character sheet into transparent sprites for the "Full body" / "Portrait" styles.

Usage:  python tools/import_sheet.py path/to/sheet.webp [out_dir]
        (needs: pip install pillow numpy)

The sheet's "transparent" look is a light checkerboard baked into the image.
Capri herself is saturated red / green / black, so the background is removed
by flood-filling *only light grey pixels connected to the sprite's edge* -
her eye highlights and teeth are enclosed and stay untouched. Edges are
un-blended from white so they don't get a pale fringe.

The sprite positions below match the 1536x1024 sheet layout (see
assets/capri_v2/source/). A different sheet needs new boxes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# (left, top, right, bottom) on the 1536x1024 sheet
STANDING = (10, 12, 268, 818)
LYING = (308, 82, 918, 368)
EXPR_X = [(936, 1072), (1087, 1223), (1236, 1370), (1381, 1512)]
EXPR_ROWS = [(52, 180, ["neutral", "happy", "smirk", "surprised"]),
             (219, 349, ["serious", "angry", "sad", "playful"])]
VIS_X = [(309, 443), (458, 594), (611, 746), (764, 900), (916, 1052), (1068, 1203), (1218, 1354), (1370, 1505)]
VIS_ROWS = [(450, 565, ["A", "E", "I", "O", "L", "M", "P", "F"]),
            (602, 721, ["V", "T", "D", "N", "S", "TH", "CH", "J"])]
FRAME_Y = (847, 974)      # just below the "ANIMATION FRAMES" label
FRAME_TOP = {"idle": 851, "blink": 851}   # these two sit right under the label's edge
FRAMES = {"idle": (30, 135), "blink": (165, 275), "look_around": (318, 420), "listening": (462, 558),
          "thinking": (600, 695), "speaking": (735, 835), "happy": (850, 955), "confused": (985, 1110)}
FRAME_SCALE = 2          # the small frames are upscaled 2x before cutting, for smoother edges


def is_background(rgb: np.ndarray) -> np.ndarray:
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    return (mx - mn < 45) & (mn > 175)


def components(mask: np.ndarray) -> list[np.ndarray]:
    """4-connected regions of a boolean mask (small images, so a simple flood is fine)."""
    seen = np.zeros_like(mask)
    regions = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        region = np.zeros_like(mask)
        region[y, x] = True
        while True:
            grown = region.copy()
            grown[1:, :] |= region[:-1, :]
            grown[:-1, :] |= region[1:, :]
            grown[:, 1:] |= region[:, :-1]
            grown[:, :-1] |= region[:, 1:]
            grown &= mask
            if (grown == region).all():
                break
            region = grown
        seen |= region
        regions.append(region)
    return regions


def checker_holes(rgb: np.ndarray, bg_like: np.ndarray, outside: np.ndarray) -> np.ndarray:
    """Enclosed background (e.g. between an arm and the body): it shows the checkerboard's grey
    squares. Her eye highlights and teeth are small and pure white, so they're kept."""
    holes = np.zeros_like(bg_like)
    grey = (rgb.min(axis=2) < 244) & (rgb.max(axis=2) - rgb.min(axis=2) < 20)
    for region in components(bg_like & ~outside):
        area = region.sum()
        if area >= 40 and (grey & region).sum() >= 0.15 * area:
            holes |= region
    return holes


def edge_flood(mask: np.ndarray) -> np.ndarray:
    """Background pixels reachable from the image border (4-connected)."""
    seen = np.zeros_like(mask)
    seen[0, :], seen[-1, :], seen[:, 0], seen[:, -1] = mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]
    while True:
        grown = seen.copy()
        grown[1:, :] |= seen[:-1, :]
        grown[:-1, :] |= seen[1:, :]
        grown[:, 1:] |= seen[:, :-1]
        grown[:, :-1] |= seen[:, 1:]
        grown &= mask
        if (grown == seen).all():
            return seen
        seen = grown


def cut(img: Image.Image, trim: bool = True) -> Image.Image:
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    bg_like = is_background(rgb.astype(int))
    bg = edge_flood(bg_like)
    bg |= checker_holes(rgb, bg_like, bg)
    alpha = np.where(bg, 0.0, 1.0)
    # Soft edge: pixels next to the background get alpha from how far they are from white.
    near = np.zeros_like(bg)
    near[1:, :] |= bg[:-1, :]
    near[:-1, :] |= bg[1:, :]
    near[:, 1:] |= bg[:, :-1]
    near[:, :-1] |= bg[:, 1:]
    edge = near & ~bg
    lightness = rgb.min(axis=2)
    a_edge = np.clip((255.0 - lightness) / 160.0, 0.0, 1.0)
    alpha[edge] = a_edge[edge]
    # un-blend from white: c = (c - (1 - a) * 255) / a
    a3 = np.maximum(alpha[..., None], 1e-3)
    color = np.clip((rgb - (1.0 - a3) * 255.0) / a3, 0, 255)
    out = np.dstack([color, alpha * 255.0]).astype(np.uint8)
    result = Image.fromarray(out, "RGBA")
    if trim:
        box = result.getbbox()
        if box:
            result = result.crop(box)
    return result


def head_box(sprite: Image.Image) -> list[float]:
    """Where her hair/head is (normalised x, y, w, h) - the wild-hair effect grows from here."""
    a = np.asarray(sprite).astype(int)
    r, g, b, alpha = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    red = (alpha > 128) & (r > 150) & (g < 110) & (b < 140)
    h = a.shape[0]
    top = red[: int(h * 0.42)]
    ys, xs = np.nonzero(top)
    if len(xs) == 0:
        return [0.25, 0.0, 0.5, 0.25]
    x0, x1 = np.percentile(xs, 2), np.percentile(xs, 98)
    y0, y1 = ys.min(), np.percentile(ys, 97)
    return [round(x0 / a.shape[1], 3), round(y0 / h, 3), round((x1 - x0) / a.shape[1], 3), round((y1 - y0) / h, 3)]


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(r):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def face_layer(sprite: Image.Image, box: list[float]) -> Image.Image:
    """Just her face (green mask, eyes, black lower face) - drawn back on top of the "storm" hair."""
    a = np.asarray(sprite).astype(int)
    r, g, b, alpha = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    h, w = alpha.shape
    solid = alpha > 100
    green = solid & (g > 140) & (r < 120)
    blue = solid & (b > 150) & (r < 120) & (g < 170)
    hair = solid & (r > 140) & (g < 120)
    x0, y0 = int(box[0] * w), int(box[1] * h)
    x1, y1 = int((box[0] + box[2]) * w), int((box[1] + box[3]) * h)
    region = np.zeros_like(solid)
    region[y0:y1 + int(0.10 * h), x0:x1] = True
    seed = (green | blue) & region
    if not seed.any():
        return Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    reach = max(2, int(0.07 * box[2] * w))
    near = _dilate(seed, reach)
    # her black lower face hangs below the green mask: reach further down for dark pixels
    dark = solid & (a[..., :3].max(axis=2) < 90)
    below = np.zeros_like(near)
    shift = max(2, int(0.06 * h))
    below[shift:, :] = near[:-shift, :]
    face = ((near & ~hair) | (below & dark)) & solid & region
    out = a.copy()
    out[..., 3] = np.where(face, a[..., 3], 0)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def anchor_x(sprite: Image.Image) -> float:
    """Horizontal centre of her torso (normalised), so poses with an arm out don't slide sideways."""
    a = np.asarray(sprite)[..., 3] > 128
    h = a.shape[0]
    band = a[int(h * 0.45): int(h * 0.75)]
    xs = np.nonzero(band)[1]
    return round(float(np.median(xs)) / a.shape[1], 3) if len(xs) else 0.5


def main() -> None:
    sheet_path = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "assets" / "capri_v2"
    sheet = Image.open(sheet_path).convert("RGB")
    if sheet.size != (1536, 1024):
        sys.exit(f"Expected a 1536x1024 sheet, got {sheet.size}. Update the boxes in this script.")
    for sub in ("body", "expressions", "visemes"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    manifest: dict = {"name": "Capri", "style": "sprites", "body": {}, "head_box": {}, "anchor": {},
                      "face_layer": {}, "expressions": {}, "visemes": {}}
    (out / "faces").mkdir(parents=True, exist_ok=True)

    standing = cut(sheet.crop(STANDING))
    standing.save(out / "body" / "standing.png")
    manifest["body"]["standing"] = "body/standing.png"
    manifest["head_box"]["standing"] = head_box(standing)
    manifest["anchor"]["standing"] = anchor_x(standing)

    for name, (x0, x1) in FRAMES.items():
        crop = sheet.crop((x0, FRAME_TOP.get(name, FRAME_Y[0]), x1, FRAME_Y[1]))
        crop = crop.resize((crop.width * FRAME_SCALE, crop.height * FRAME_SCALE), Image.LANCZOS)
        sprite = cut(crop)
        sprite.save(out / "body" / f"{name}.png")
        manifest["body"][name] = f"body/{name}.png"
        manifest["head_box"][name] = head_box(sprite)
        manifest["anchor"][name] = anchor_x(sprite)
        face_layer(sprite, manifest["head_box"][name]).save(out / "faces" / f"{name}.png")
        manifest["face_layer"][name] = f"faces/{name}.png"

    lying = cut(sheet.crop(LYING))
    lying.save(out / "lying.png")
    manifest["lying"] = "lying.png"
    manifest["head_box"]["lying"] = head_box(lying)
    face_layer(lying, manifest["head_box"]["lying"]).save(out / "faces" / "lying.png")
    manifest["face_layer"]["lying"] = "faces/lying.png"

    for (y0, y1, names) in EXPR_ROWS:
        for name, (x0, x1) in zip(names, EXPR_X):
            cut(sheet.crop((x0, y0, x1, y1)), trim=False).save(out / "expressions" / f"{name}.png")
            manifest["expressions"][name] = f"expressions/{name}.png"
    for (y0, y1, names) in VIS_ROWS:
        for name, (x0, x1) in zip(names, VIS_X):
            cut(sheet.crop((x0, y0, x1, y1)), trim=False).save(out / "visemes" / f"{name}.png")
            manifest["visemes"][name] = f"visemes/{name}.png"

    manifest["icon"] = "expressions/neutral.png"
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest['body'])} body frames, {len(manifest['expressions'])} expressions, "
          f"{len(manifest['visemes'])} mouth shapes and the lying pose to {out}")


if __name__ == "__main__":
    main()
