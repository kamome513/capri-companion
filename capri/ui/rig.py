"""Capri's full-body figure (the big one from the character sheet), cut into parts so she
can really move: legs, torso + head, each arm (pivoting at the shoulder), and her face
(so the storm hair can boil around it). Used for the taskbar teleport.

The cut is worked out from the picture itself, once: below the shoulders each row of
pixels has separate runs for her arms and her body, so the arms come off cleanly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform

from .hair import make_hair

# Where things are on the sheet's standing figure, as fractions of its width / height.
WAIST = (0.45, 0.40)                       # she bends here
SHOULDER = {"right": (0.665, 0.225), "left": (0.31, 0.235)}   # right = the arm on the picture's right
ARM_ROWS = (0.25, 0.64)
LEG_SPLIT = 0.48                           # below this, the middle runs are legs
HEAD_ROWS = 0.205
HAND_TIP = {"right": (0.97, 0.615), "left": (0.03, 0.6)}     # her claws' tips
ELBOW = {"right": (0.80, 0.365), "left": (0.20, 0.37)}      # where each forearm bends (for a real wave)
FACE_BOX = (0.27, 0.075, 0.64, 0.188)      # x0, y0, x1, y1: her mask, eyes and jaw
EYES = (((0.341, 0.1311), 0.031), ((0.544, 0.1135), 0.035))    # (centre, radius as a share of width)
MOUTH = ((0.463, 0.1475), 0.13, -22.0)     # her zigzag grin: centre, length (share of width), angle


def _to_array(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    return np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w].copy()


def _to_image(a: np.ndarray) -> QImage:
    h, w = a.shape[:2]
    return QImage(np.ascontiguousarray(a).tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    xs = np.flatnonzero(row)
    if len(xs) == 0:
        return []
    cuts = np.flatnonzero(np.diff(xs) > 2)
    starts = np.r_[xs[0], xs[cuts + 1]]
    ends = np.r_[xs[cuts], xs[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def arm_masks(alpha: np.ndarray) -> dict[str, np.ndarray]:
    """Boolean masks of each arm, from where the opaque pixels are."""
    h, w = alpha.shape
    masks = {"right": np.zeros_like(alpha), "left": np.zeros_like(alpha)}
    # (The shoulder caps stay with her torso, under the storm hair; only the free arm swings.)
    for y in range(int(ARM_ROWS[0] * h), int(ARM_ROWS[1] * h)):
        runs = _runs(alpha[y])
        if y < LEG_SPLIT * h:
            body = next((r for r in runs if r[0] <= 0.45 * w <= r[1]), None)
            if body is None:
                continue
            right = [r for r in runs if r[0] > body[1]]
            left = [r for r in runs if r[1] < body[0]]
        else:
            right = [r for r in runs if r[0] > 0.76 * w]
            left = [r for r in runs if r[1] < 0.24 * w]
        for side, found in (("right", right), ("left", left)):
            for s, e in found:
                masks[side][y, s:e + 1] = alpha[y, s:e + 1]
    return masks


def split_legs(lower: np.ndarray, waist: int):
    """Her lower body cut into hips + a left and a right leg, from the gap between her legs.
    Returns (hips mask, {"left", "right": leg mask}, {"left", "right": hip joint}) or None."""
    h, w = lower.shape
    rows = [y for y in range(waist, h) if lower[y].any()]
    if not rows:
        return None
    centre = w / 2

    def gap(y: int) -> float | None:
        runs = _runs(lower[y])
        if len(runs) < 2:
            return None
        pairs = [(runs[i][1], runs[i + 1][0]) for i in range(len(runs) - 1)]
        best = min(pairs, key=lambda g: abs((g[0] + g[1]) / 2 - centre))
        mid = (best[0] + best[1]) / 2
        return mid if abs(mid - centre) < w * 0.2 else None
    crotch = None
    for y in rows:
        if all(gap(yy) is not None for yy in range(y, min(h, y + 12))):
            crotch = y
            break
    if crotch is None or crotch > rows[-1] - h * 0.2:
        return None
    overlap = max(3, int(h * 0.01))
    top_mid = gap(crotch)
    mids = np.full(h, top_mid)
    last = top_mid
    for y in range(crotch, h):
        g = gap(y)
        last = g if g is not None else last
        mids[y] = last
    xs = np.arange(w)[None, :]
    left_side = xs < mids[:, None]
    legs_rows = np.zeros_like(lower)
    legs_rows[crotch - overlap:] = True
    hips = lower.copy()
    hips[crotch + overlap:] = False
    left, right = lower & legs_rows & left_side, lower & legs_rows & ~left_side
    joints = {}
    for side, m in (("left", left), ("right", right)):
        cols = np.flatnonzero(m[crotch])
        if len(cols) == 0:
            return None
        joints[side] = QPointF(float(cols.mean()), float(crotch - overlap))
    return hips, {"left": left, "right": right}, joints


@dataclass
class Pose:
    lean: float = 0.0          # -1..1: bend at the waist (+ = toward the picture's right)
    reach: float = 0.0         # 0..1: the leading arm swings out toward what she's clicking
    poke: float = 0.0          # 0..1: the little jab of the click itself
    sweep: float = 0.0         # 0..1: arms swept back while she dashes
    squat: float = 0.0         # 0..1: knees give
    wave: float = 0.0          # 0..1: the leading arm raised, forearm up from the elbow, for a wave
    wag: float = 0.0           # -1..1: the waving hand's swing from side to side (at the elbow)
    eyes: str = ""             # "" | "happy" (smiling ^ ^ eyes) | "wink"
    energy: float = 0.0        # 0..1: how wild the hair is
    t: float = 0.0             # time, for the hair's boil
    wild: float = 1.0          # the hair storm's size (Settings -> Character -> Wild hair)
    blink: float = 0.0         # 0..1: eyes closing
    mouth: float = 0.0         # 0..1: mouth open (lip-sync)
    stride: float = 0.0        # -1..1: walking - which leg is up (+ = the picture's right leg), arms swinging


LEAN_DEGREES = 56
REACH_DEGREES = 55
POKE_DEGREES = 12
SWEEP_DEGREES = 28
UPPER_ARM_WAVE = 72          # a wave: the upper arm out to the side...
FOREARM_WAVE = 100           # ...the forearm straight up from the elbow...
WAG_DEGREES = 22             # ...and the hand swinging side to side
LEG_LIFT = 0.2               # walking: the raised leg is this much shorter (her knee comes up)
LEG_SWAY = 6                 # ...and both legs tilt a little with the step
ARM_SWING = 9                # her arms swing with her steps


class Rig:
    def __init__(self, standing: QImage, hair_style: str = "storm") -> None:
        a = _to_array(standing)
        h, w = a.shape[:2]
        self.w, self.h = w, h
        alpha = a[..., 3] > 40
        arms = arm_masks(alpha)
        rest = alpha & ~arms["right"] & ~arms["left"]
        waist = int(WAIST[1] * h)
        upper = rest.copy()
        upper[waist + 4:] = False                       # a little overlap, so the bend has no gap
        lower = rest.copy()
        lower[:waist - 2] = False

        def part(mask: np.ndarray) -> QImage:
            out = a.copy()
            out[~mask] = 0
            return _to_image(out)
        self.upper, self.lower = part(upper), part(lower)
        # her legs, each on its own below the crotch, so she can walk (None: this figure's legs don't separate)
        self.hips, self.legs, self.hip_joints = None, None, None
        split = split_legs(lower, waist)
        if split is not None:
            hips_mask, leg_masks, self.hip_joints = split
            self.hips = part(hips_mask)
            self.legs = {side: part(m) for side, m in leg_masks.items()}
        self.arms = {side: part(m) for side, m in arms.items()}
        # each arm again in two pieces, at the elbow, so a wave bends like a real arm
        self.upper_arms, self.forearms = {}, {}
        for side, m in arms.items():
            cut = int(ELBOW[side][1] * h)
            top, bottom = m.copy(), m.copy()
            top[cut + 3:] = False                       # a little overlap: no gap at the bend
            bottom[:cut - 3] = False
            self.upper_arms[side], self.forearms[side] = part(top), part(bottom)
        # her face, for the storm hair to boil around: the non-red pixels of her mask, eyes and jaw
        fx0, fy0, fx1, fy1 = (int(FACE_BOX[0] * w), int(FACE_BOX[1] * h), int(FACE_BOX[2] * w), int(FACE_BOX[3] * h))
        face = np.zeros_like(alpha)
        box = a[fy0:fy1, fx0:fx1].astype(int)
        hair_red = (box[..., 0] > 140) & (box[..., 1] < 90) & (box[..., 2] < 130)
        face[fy0:fy1, fx0:fx1] = alpha[fy0:fy1, fx0:fx1] & ~hair_red
        self.face = part(face)
        # her own (boxy) hair gone, for when the traced hair is drawn instead: everything in her head rows
        # but her face - so the gaps between its strands show what's behind her, like the picture
        head_rows = np.zeros_like(alpha)
        head_rows[: int(HEAD_ROWS * h)] = True
        head_rows[fy1:, fx0:fx1] = False                # (her neck, under her face, stays)
        self.upper_bald = part(upper & ~(head_rows & ~face))
        self.face_bare, self.eye_glows = self._erase_eyes(a, face)
        rows = np.flatnonzero(alpha[: int(HEAD_ROWS * h)].any(1))
        cols = np.flatnonzero(alpha[: int(HEAD_ROWS * h)].any(0))
        self.head = QRectF(float(cols[0]), float(rows[0]), float(cols[-1] - cols[0]), float(rows[-1] - rows[0]))
        feet_rows = np.flatnonzero(alpha.any(1))
        self.feet = QPointF(w * 0.5, float(feet_rows[-1]))
        self.hair_style = hair_style
        self.hair = make_hair(hair_style, seed=33)
        self._hair_cache: tuple | None = None

    def set_hair_style(self, style: str) -> None:
        """Settings -> Character -> Hair: "storm" (traced from the show) or "classic" (her first)."""
        if style != self.hair_style:
            self.hair_style, self.hair, self._hair_cache = style, make_hair(style, seed=33), None

    def _erase_eyes(self, a: np.ndarray, face: np.ndarray):
        """Her face without its painted eyes (filled in from the colours around them), and each
        eye's glow on its own - so she can blink, smile with her eyes and wink smoothly."""
        h, w = a.shape[:2]
        bare = a.copy()
        bare[~face] = 0
        glows = []
        yy, xx = np.mgrid[0:h, 0:w]
        for (fx, fy), fr in EYES:
            cx, cy, r = fx * w, fy * h, fr * w * 1.35
            near = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
            px = a.astype(int)
            glow = near & (px[..., 2] > 120) & (px[..., 2] >= px[..., 0] + 30) | \
                near & (px[..., :3].min(-1) > 175)                     # the blue glow and its white centre
            grown = glow.copy()                                        # and its soft edge
            for _ in range(2):
                grown[1:] |= grown[:-1]
                grown[:-1] |= grown[1:]
                grown[:, 1:] |= grown[:, :-1]
                grown[:, :-1] |= grown[:, 1:]
            grown &= near
            eye = np.zeros_like(a)
            eye[grown] = a[grown]
            glows.append((_to_image(eye), QPointF(cx, cy)))
            known = face & ~grown                                      # fill the hole from its edges inwards
            fill = bare.astype(np.float32)
            for _ in range(int(r) + 4):
                todo = grown & ~known
                if not todo.any():
                    break
                acc = np.zeros(fill.shape, np.float32)
                cnt = np.zeros(fill.shape[:2], np.float32)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    shifted_known = np.roll(known, (dy, dx), (0, 1))
                    acc += np.roll(fill, (dy, dx), (0, 1)) * shifted_known[..., None]
                    cnt += shifted_known
                ready = todo & (cnt > 0)
                fill[ready] = acc[ready] / cnt[ready][:, None]
                known |= ready
            bare = fill.astype(np.uint8)
            bare[..., 3][grown] = 255
        return _to_image(bare), glows

    def resized(self, height: int) -> "Rig":
        """The same cut-up figure, pre-scaled to `height` device pixels - sharp at small sizes
        (the parts are cut at full size, then each is scaled down smoothly)."""
        k = height / self.h
        out = Rig.__new__(Rig)
        out.w, out.h = max(1, round(self.w * k)), height

        def small(img: QImage) -> QImage:
            return img.scaled(out.w, out.h, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        out.upper, out.lower, out.face = small(self.upper), small(self.lower), small(self.face)
        out.upper_bald = small(self.upper_bald)
        out.face_bare = small(self.face_bare)
        out.eye_glows = [(small(img), QPointF(c.x() * height / self.h * self.w / self.w, c.y() * height / self.h))
                         for img, c in self.eye_glows]
        out.arms = {side: small(img) for side, img in self.arms.items()}
        out.upper_arms = {side: small(img) for side, img in self.upper_arms.items()}
        out.forearms = {side: small(img) for side, img in self.forearms.items()}
        kx, ky = out.w / self.w, out.h / self.h
        out.hips = small(self.hips) if self.hips is not None else None
        out.legs = {side: small(img) for side, img in self.legs.items()} if self.legs else None
        out.hip_joints = {side: QPointF(pt.x() * kx, pt.y() * ky) for side, pt in self.hip_joints.items()} \
            if self.hip_joints else None
        out.head = QRectF(self.head.x() * kx, self.head.y() * ky, self.head.width() * kx, self.head.height() * ky)
        out.feet = QPointF(self.feet.x() * kx, self.feet.y() * ky)
        out.hair_style, out.hair = self.hair_style, make_hair(self.hair_style, seed=33)
        out._hair_cache = None
        return out

    def body_box(self) -> QRectF:
        return QRectF(0, 0, self.w, self.h)

    def _base(self, feet: QPointF, height: float) -> QTransform:
        s = height / self.h
        return QTransform().translate(feet.x(), feet.y()).scale(s, s).translate(-self.feet.x(), -self.feet.y())

    def _upper(self, pose: Pose) -> QTransform:
        squash = 1 - 0.12 * pose.squat
        wx, wy = WAIST[0] * self.w, WAIST[1] * self.h
        pivot_y = self.feet.y() - (self.feet.y() - wy) * squash
        return QTransform().translate(wx, pivot_y).rotate(LEAN_DEGREES * pose.lean).translate(-wx, -wy)

    def _arm_angle(self, arm: str, pose: Pose, side: str) -> float:
        lead = 1 if side == "right" else -1
        out = 1 if arm == "right" else -1                      # which way is "away from her body"
        world = 0.0
        if arm == side:                                        # swings out toward the icon / up in a wave
            world -= lead * (REACH_DEGREES * pose.reach + POKE_DEGREES * pose.poke)
            world -= lead * pose.wave * UPPER_ARM_WAVE         # the upper arm lifts out to the side
        else:                                                  # the other arm tucks in a little
            world += out * -6 * pose.reach
        world += lead * SWEEP_DEGREES * pose.sweep             # both trail behind the dash
        world += ARM_SWING * pose.stride * (1 if arm == "right" else -1) * 0.6 + ARM_SWING * pose.stride * 0.4
        return world - LEAN_DEGREES * pose.lean * 0.92         # and hang with gravity, not the lean

    def _arm(self, arm: str, pose: Pose, side: str) -> QTransform:
        sx, sy = SHOULDER[arm][0] * self.w, SHOULDER[arm][1] * self.h
        return QTransform().translate(sx, sy).rotate(self._arm_angle(arm, pose, side)).translate(-sx, -sy)

    def _paint_hair(self, p: QPainter, pose: Pose, scale: float) -> None:
        """The storm, drawn once per boil step at screen size and reused in between (the boil
        only changes it a few times a second; redrawing its texture every frame was the slow part)."""
        intensity = round(pose.wild * (0.85 + 0.15 * pose.energy), 2)
        energy = round(pose.energy, 1)
        _rate, step = self.hair.step(pose.t, energy)
        device = p.device()
        dpr = device.devicePixelRatioF() if device is not None else 1.0   # sharp on 125% / 150% displays
        key = (step, intensity, energy, round(scale, 3), dpr)
        if self._hair_cache is None or self._hair_cache[0] != key:
            pad, hh = self.head.width() * 1.35, self.head.height()
            area = self.head.adjusted(-pad, -hh * 1.8, pad, hh * 0.8)
            px = scale * dpr
            img = QImage(max(1, round(area.width() * px)), max(1, round(area.height() * px)),
                         QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            q = QPainter(img)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.scale(px, px)
            q.translate(-area.topLeft())
            self.hair.paint(q, self.head, pose.t, intensity, energy)
            q.end()
            self._hair_cache = (key, img, area)
        _key, img, area = self._hair_cache
        p.drawImage(area, img)

    def _paint_face_moves(self, p: QPainter, pose: Pose) -> None:
        """Her eyes and mouth moving: drawn on her face with the painted eyes taken out, in her
        own glowing-blue style (in the figure's own coordinates)."""
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.w, self.h
        p.drawImage(QPointF(0, 0), self.face_bare)
        glow = QColor(110, 205, 255)
        for i, (((fx, fy), fr), (img, centre)) in enumerate(zip(EYES, self.eye_glows)):
            r = fr * w * 1.1
            shut = 1.0 if pose.eyes == "wink" and i == 0 else pose.blink
            if pose.eyes == "happy" and shut < 0.6:                  # smiling eyes: soft glowing arcs
                self._glow_line(p, [centre + QPointF(-r * 0.85, r * 0.3), centre + QPointF(0, -r * 0.5),
                                    centre + QPointF(r * 0.85, r * 0.3)], r, glow)
            elif shut >= 0.85:                                       # closed: a glowing lid line
                self._glow_line(p, [centre + QPointF(-r * 0.85, 0), centre + QPointF(0, r * 0.15),
                                    centre + QPointF(r * 0.85, 0)], r, glow)
            else:                                                    # open, or closing: the real eye, squashed
                p.save()
                p.translate(centre)
                p.scale(1.0, max(0.08, 1.0 - shut))
                p.translate(-centre)
                p.drawImage(QPointF(0, 0), img)
                p.restore()
        if pose.mouth > 0.02:                                        # talking: her grin opens
            (fx, fy), length, angle = MOUTH
            p.translate(fx * w, fy * h)
            p.rotate(angle)
            half, tall = length * w * 0.36, length * w * 0.34 * min(1.0, pose.mouth)
            shape = QPainterPath()
            shape.moveTo(-half, 0)
            shape.cubicTo(-half * 0.6, tall * 1.25, half * 0.6, tall * 1.25, half, 0)
            shape.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(28, 4, 14))
            p.drawPath(shape)
            p.setBrush(QColor(150, 22, 62, 170))                     # a hint of tongue
            p.drawEllipse(QPointF(0, tall * 0.68), half * 0.42, tall * 0.26)
            teeth = QPainterPath()                                   # her zigzag teeth along the top
            n = 7
            teeth.moveTo(-half * 0.92, 0)
            for k in range(1, n + 1):
                teeth.lineTo(-half * 0.92 + half * 1.84 * k / n, (tall * 0.2 + 1.2) * (k % 2))
            p.setPen(QPen(QColor(232, 225, 236), max(0.8, w * 0.007)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(teeth)
        p.restore()

    @staticmethod
    def _glow_line(p: QPainter, points: list, r: float, colour: QColor) -> None:
        halo = QColor(colour)
        halo.setAlpha(90)
        for pen_width, c in ((r * 0.75, halo), (r * 0.32, colour)):
            p.setPen(QPen(c, max(1.0, pen_width), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawPolyline(points)

    def hand_tip(self, feet: QPointF, height: float, pose: Pose, side: str = "right") -> QPointF:
        """Where the reaching claw's tip is, on screen, for this pose."""
        tip = QPointF(HAND_TIP[side][0] * self.w, HAND_TIP[side][1] * self.h)
        # Qt applies the transform set last first: arm, then the bend, then placement
        return (self._arm(side, pose, side) * self._upper(pose) * self._base(feet, height)).map(tip)

    def paint(self, p: QPainter, feet: QPointF, height: float, pose: Pose, side: str = "right",
              hair: bool = True) -> None:
        """Draw her with her feet at `feet`, `height` px tall. `side` = the arm that reaches."""
        base = self._base(feet, height)
        p.save()
        p.setTransform(base, True)
        squash = 1 - 0.12 * pose.squat
        p.save()                                        # legs: knees give a little
        p.translate(0, self.feet.y())
        p.scale(1, squash)
        p.translate(0, -self.feet.y())
        if pose.stride and self.legs:                   # walking: each leg on its own
            p.drawImage(QPointF(0, 0), self.hips)
            for side in ("left", "right"):
                up = max(0.0, pose.stride if side == "right" else -pose.stride)
                joint = self.hip_joints[side]
                p.save()
                p.translate(joint)
                p.rotate(LEG_SWAY * pose.stride)
                p.scale(1, 1 - LEG_LIFT * up)
                p.translate(-joint)
                p.drawImage(QPointF(0, 0), self.legs[side])
                p.restore()
        else:
            p.drawImage(QPointF(0, 0), self.lower)
        p.restore()
        p.setTransform(self._upper(pose), True)         # everything above the waist bends
        bald = hair and pose.wild > 0 and self.hair_style == "storm"   # (the traced hair replaces her own)
        p.drawImage(QPointF(0, 0), self.upper_bald if bald else self.upper)
        if hair and pose.wild > 0:
            self._paint_hair(p, pose, height / self.h)
            p.drawImage(QPointF(0, 0), self.face)
        if pose.blink > 0 or pose.mouth > 0 or pose.eyes:
            self._paint_face_moves(p, pose)
        for arm in ("left", "right"):
            p.save()
            p.setTransform(self._arm(arm, pose, side), True)
            if arm == side and pose.wave > 0:               # bent at the elbow, hand up and waving
                lead = 1 if side == "right" else -1
                ex, ey = ELBOW[arm][0] * self.w, ELBOW[arm][1] * self.h
                p.drawImage(QPointF(0, 0), self.upper_arms[arm])
                p.translate(ex, ey)
                bend = min(1.0, pose.wave * 1.6)            # the forearm comes up a little ahead of the arm
                p.rotate(-lead * bend * (FOREARM_WAVE + WAG_DEGREES * pose.wag))
                p.translate(-ex, -ey)
                p.drawImage(QPointF(0, 0), self.forearms[arm])
            else:
                p.drawImage(QPointF(0, 0), self.arms[arm])
            p.restore()
        p.restore()
