"""Her "Neon" body look: her own figure redrawn dark, with her red and green shards as thin glowing edges and
her purple limbs kept - a sleek, outlined look instead of the full-colour fill. (Settings -> Character -> Body.)

Made from her own picture at start-up (numpy, ~20 ms), so every move she makes - standing, dashing, being
thrown, teleporting - uses it. Her face (mask and eyes) is left exactly as it is.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

DARK = np.array([14.0, 8.0, 22.0])
RED = np.array([255.0, 40.0, 90.0])
GREEN = np.array([50.0, 255.0, 140.0])
LOOKS = {"neon": "Neon (dark, glowing edges)", "full": "Full colour"}


def _shift_any(mask: np.ndarray, r: int) -> np.ndarray:
    """Grow a mask by r pixels (a square neighbourhood)."""
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy or dx:
                out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def _shrink(mask: np.ndarray, r: int) -> np.ndarray:
    return ~_shift_any(~mask, r)


def neon_array(a: np.ndarray, face_box: tuple[float, float, float, float] | None = None) -> np.ndarray:
    """RGBA (h, w, 4) uint8 -> the neon version (same size, same alpha)."""
    rgb, alpha = a[..., :3].astype(float), a[..., 3]
    sil = alpha > 40
    diff = np.zeros(rgb.shape[:2])
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        diff = np.maximum(diff, np.abs(rgb - np.roll(np.roll(rgb, dy, 0), dx, 1)).sum(-1))
    border = sil & ~_shrink(sil, 1)
    edge = _shift_any((diff > 140) | border, max(1, round(a.shape[0] / 400))) & sil    # ~2 px at her real size
    thin = sil & ~_shrink(sil, 4)                                  # narrow bits (fingers, spikes) stay bright
    r, g = rgb[..., 0], rgb[..., 1]
    red, green = (r > 150) & (g < 110), (g > 150) & (r < 140)
    out = np.empty_like(rgb)
    out[:] = DARK * 0.8 + rgb * 0.2                                # the body: dark, a hint of its colour
    lit = (edge | (thin & (red | green))) & sil
    neon = rgb.copy()
    neon[red], neon[green] = RED, GREEN
    out[lit] = neon[lit]
    result = np.dstack([out.clip(0, 255), alpha.astype(float)]).astype(np.uint8)
    if face_box is not None:                                       # her face exactly as drawn
        h, w = alpha.shape
        x0, y0, x1, y1 = (int(face_box[0] * w), int(face_box[1] * h), int(face_box[2] * w), int(face_box[3] * h))
        result[y0:y1, x0:x1] = a[y0:y1, x0:x1]
    return result


def neon_image(image: QImage) -> QImage:
    from .rig import FACE_BOX, _to_array, _to_image
    return _to_image(neon_array(_to_array(image), FACE_BOX))


def body_image(image: QImage, look: str) -> QImage:
    """Her standing figure in the chosen body look."""
    return neon_image(image) if look == "neon" else image
