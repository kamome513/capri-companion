"""The pictures for the mods that come with Capri (2.4.3): each one shows HER with that mod - the skin on her, the
accessory on her head, her in that look, her face for a personality, a little chat window in that style... - in a
neon card. Drawn here from her own art (assets/capri_v2), so they're original. Used by make_starter_mods.py."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

ROOT = Path(__file__).resolve().parents[1]
SIZE = 256
BG_TOP, BG_BOTTOM = QColor(26, 12, 30), QColor(8, 6, 12)
CATEGORY_COLOUR = {"skin": "#ff2a6d", "cosmetic": "#00e2ff", "animations": "#ff2a6d", "personality": "#ffe600",
                   "behaviour": "#00ff9c", "lines": "#ffb3c7", "sounds": "#00e2ff", "look": "#b388ff"}
PERSONALITY_FACE = {"edgerunner": "smirk", "sarcastic": "smirk", "silly": "playful", "tsundere": "angry",
                    "sweet": "happy", "deadpan": "neutral", "gremlin": "playful", "hype": "surprised",
                    "kuudere": "serious", "noir": "serious"}

_sprites = None


def sprites():
    global _sprites
    if _sprites is None:
        from capri.ui.sprites import SpriteArt
        _sprites = SpriteArt.load(ROOT / "assets" / "capri_v2")
    return _sprites


def _card(accent: str) -> tuple[QImage, QPainter]:
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    shape = _chamfer(QRectF(2, 2, SIZE - 4, SIZE - 4), 22)
    bg = QLinearGradient(0, 0, 0, SIZE)
    bg.setColorAt(0, BG_TOP)
    bg.setColorAt(1, BG_BOTTOM)
    p.fillPath(shape, bg)
    glow = QRadialGradient(QPointF(SIZE / 2, SIZE * 0.55), SIZE * 0.55)
    c = QColor(accent)
    c.setAlpha(70)
    glow.setColorAt(0, c)
    c2 = QColor(c)
    c2.setAlpha(0)
    glow.setColorAt(1, c2)
    p.save()
    p.setClipPath(shape)
    p.fillRect(QRectF(0, 0, SIZE, SIZE), glow)
    for y in range(0, SIZE, 4):                                   # faint scanlines
        p.fillRect(QRectF(0, y, SIZE, 1), QColor(255, 255, 255, 8))
    p.restore()
    return img, p


def _finish(p: QPainter, accent: str) -> None:
    shape = _chamfer(QRectF(2, 2, SIZE - 4, SIZE - 4), 22)
    edge = QColor(accent)
    p.setPen(QPen(edge, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(shape)
    p.setPen(QPen(QColor(0, 226, 255), 3))                         # cyan corner brackets
    k = 22
    p.drawPolyline([QPointF(SIZE - 10, SIZE - 10 - k), QPointF(SIZE - 10, SIZE - 10), QPointF(SIZE - 10 - k, SIZE - 10)])
    p.end()


def _chamfer(r: QRectF, k: float) -> QPainterPath:
    path = QPainterPath(QPointF(r.left() + k, r.top()))
    path.lineTo(r.right(), r.top())
    path.lineTo(r.right(), r.bottom() - k)
    path.lineTo(r.right() - k, r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + k)
    path.closeSubpath()
    return path


def _rig(palette: dict | None = None, look: str = "flat", hair: str = "storm"):
    from capri.mods.effects import recolor
    from capri.ui.neon import body_image
    from capri.ui.rig import Rig
    plain = body_image(sprites().frame("standing"), look)
    frame = recolor(plain, palette or {})
    return Rig(frame, hair, masks_from=plain if frame is not plain else None)


def _her(p: QPainter, rig, height: float, feet: QPointF, pose=None, cosmetics: list | None = None,
         hair_colour: str | None = None) -> None:
    """Her figure (with these cosmetics on her, and her hair in this colour)."""
    from capri.mods.effects import EFFECTS
    from capri.ui import hair as hair_mod
    from capri.ui.character_window import paint_cosmetics
    from capri.ui.rig import Pose
    pose = pose or Pose(t=0.0)
    saved = list(EFFECTS.cosmetics)
    EFFECTS.cosmetics = cosmetics or []
    hair_mod.set_hair_colour(QColor(hair_colour) if hair_colour else None)
    try:
        paint_cosmetics(p, rig, feet, height, pose, "back")
        rig.paint(p, feet, height, pose, "right")
        paint_cosmetics(p, rig, feet, height, pose, "front")
    finally:
        EFFECTS.cosmetics = saved
        hair_mod.set_hair_colour(None)


def _portrait(p: QPainter, rig, cosmetics=None, hair_colour=None, pose=None, face: bool = False) -> None:
    """Her head big: a close-up on her face (shades...), or her head with room above it (ears, halo, hair)."""
    p.save()
    p.setClipPath(_chamfer(QRectF(2, 2, SIZE - 4, SIZE - 4), 22))
    if face:
        _her(p, rig, SIZE * 2.4, QPointF(SIZE * 0.5, SIZE * 2.65), pose, cosmetics, hair_colour)
    else:
        _her(p, rig, SIZE * 1.15, QPointF(SIZE * 0.5, SIZE * 1.67), pose, cosmetics, hair_colour)
    p.restore()


def _full(p: QPainter, rig, cosmetics=None, hair_colour=None, pose=None, height: float = SIZE * 0.6) -> None:
    p.save()
    p.setClipPath(_chamfer(QRectF(2, 2, SIZE - 4, SIZE - 4), 22))
    _her(p, rig, height, QPointF(SIZE * 0.5, SIZE - 14), pose, cosmetics, hair_colour)
    p.restore()


def _label(p: QPainter, text: str, accent: str) -> None:
    """A small tag along the bottom (a word or two)."""
    f = QFont()
    f.setPixelSize(22)
    f.setBold(True)
    p.setFont(f)
    w = p.fontMetrics().horizontalAdvance(text) + 24
    r = QRectF((SIZE - w) / 2, SIZE - 46, w, 32)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(8, 6, 12, 220))
    p.drawPath(_chamfer(r, 8))
    p.setPen(QColor(accent))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)


# -- one per kind --------------------------------------------------------------------------------------------------
def skin(path: Path, palette: dict, style: dict | None = None) -> None:
    accent = palette.get("hair", "#ff2a6d")
    img, p = _card(accent)
    if style:
        styled(p, _rig(palette), SIZE * 0.6, QPointF(SIZE * 0.5, SIZE - 14), palette, style)
    else:
        _full(p, _rig(palette), hair_colour=palette.get("hair"))
    _finish(p, accent)
    img.save(str(path))


def styled(p: QPainter, rig, height: float, feet: QPointF, palette: dict, style: dict, t: float = 4.2,
           size: float = SIZE) -> None:
    """Her in a style, with its effects as they'd be a few seconds in (one of its moments happening)."""
    from capri.ui import hair as hair_mod
    from capri.ui.rig import Pose
    from capri.ui.style_fx import StyleFX, ctx_for_rig
    fx = StyleFX(style)
    fx.palette = dict(palette)
    fx.switched_at = -1e9
    if fx._events:
        ev = fx._events[0]
        length = fx.LENGTH.get(ev["kind"], 1.5)
        fx._active = [(ev, t - length * 0.45, length, 0.37)]
    pose = Pose(t=t)
    two, sparkle = style.get("hair2"), style.get("sparkle")
    hair_mod.set_hair_colour(QColor(palette["hair"]) if palette.get("hair") else None,
                             QColor(two) if two else None, QColor(sparkle) if sparkle else None)
    try:
        c = ctx_for_rig(rig, feet, height, pose, QRectF(0, 0, size, size), t)
        p.save()
        p.setClipPath(_chamfer(QRectF(2, 2, size - 4, size - 4), 22))
        fx.paint_back(p, c)
        img = QImage(int(size), int(size), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rig.paint(q, feet, height, pose, "right")
        q.end()
        fx.figure(img, c)
        fx.draw_figure(p, img, c)
        fx.paint_front(p, c)
        p.restore()
    finally:
        hair_mod.set_hair_colour(None)


def cosmetic(path: Path, folder: Path, items: list[dict]) -> None:
    from capri.mods.effects import Cosmetic
    cos = [Cosmetic(folder / i["image"], i.get("slot", "other"), float(i.get("x", 0.5)), float(i.get("y", 0.0)),
                    float(i.get("width", 1.0)), i.get("layer", "front"), "preview") for i in items]
    for c in cos:
        c._gen = -1
        c._image = QImage(str(c.image_path))
    accent = CATEGORY_COLOUR["cosmetic"]
    img, p = _card(accent)
    _portrait(p, _rig(), cosmetics=cos, face=all(i.get("slot") == "face" for i in items))
    _finish(p, accent)
    img.save(str(path))


def animation(path: Path, anim: dict) -> None:
    from capri.mods.effects import animation_moves
    from capri.ui.rig import Pose
    peak = max(anim["keys"], key=lambda k: sum(abs(float(v)) for n, v in k.items() if n not in ("t", "eyes")))
    moves, eyes = animation_moves(anim, peak["t"] * anim["seconds"] * 0.999) or ({}, "")
    pose = Pose(t=0.3, eyes=eyes, **{k: v for k, v in moves.items() if k in Pose.__dataclass_fields__})
    accent = CATEGORY_COLOUR["animations"]
    img, p = _card(accent)
    _full(p, _rig(), pose=pose)
    _motion_lines(p, accent)
    _finish(p, accent)
    img.save(str(path))


def _motion_lines(p: QPainter, accent: str) -> None:
    c = QColor(accent)
    c.setAlpha(160)
    p.setPen(QPen(c, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for x, y, d in ((30, 120, 1), (40, 150, 1), (SIZE - 30, 110, -1), (SIZE - 42, 142, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + d * 22, y - 10))


def personality(path: Path, key: str, label: str) -> None:
    accent = CATEGORY_COLOUR["personality"]
    img, p = _card(accent)
    face = sprites().expressions.get(PERSONALITY_FACE.get(key, "neutral")) or sprites().expressions["neutral"]
    s = face.scaled(int(SIZE * 0.86), int(SIZE * 0.86), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
    p.save()
    p.setClipPath(_chamfer(QRectF(2, 2, SIZE - 4, SIZE - 4), 22))
    p.drawImage(QPointF((SIZE - s.width()) / 2, 8), s)
    p.restore()
    _label(p, label.upper()[:14], accent)
    _finish(p, accent)
    img.save(str(path))


def lines(path: Path) -> None:
    accent = CATEGORY_COLOUR["lines"]
    img, p = _card(accent)
    face = sprites().expressions["happy"].scaled(int(SIZE * 0.62), int(SIZE * 0.62), Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
    p.drawImage(QPointF(10, SIZE - face.height() - 10), face)
    bubble = _chamfer(QRectF(SIZE * 0.42, 26, SIZE * 0.5, 82), 12)
    p.setBrush(QColor(8, 6, 12, 230))
    p.setPen(QPen(QColor(accent), 3))
    p.drawPath(bubble)
    tail = QPainterPath(QPointF(SIZE * 0.5, 106))
    tail.lineTo(QPointF(SIZE * 0.44, 132))
    tail.lineTo(QPointF(SIZE * 0.6, 106))
    p.drawPath(tail)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(accent))
    for i in range(3):
        p.drawEllipse(QPointF(SIZE * 0.55 + i * 26, 67), 7, 7)
    _finish(p, accent)
    img.save(str(path))


def sounds(path: Path) -> None:
    accent = CATEGORY_COLOUR["sounds"]
    img, p = _card(accent)
    face = sprites().expressions["playful"].scaled(int(SIZE * 0.5), int(SIZE * 0.5), Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation)
    p.drawImage(QPointF((SIZE - face.width()) / 2, 14), face)
    bars = 15
    for i in range(bars):
        h = 18 + 62 * abs(math.sin(i * 0.9)) * (1 - abs(i - bars / 2) / bars)
        x = 28 + i * (SIZE - 56) / bars
        c = QColor(accent if i % 3 else "#ff2a6d")
        p.fillRect(QRectF(x, SIZE - 40 - h, (SIZE - 56) / bars - 4, h), c)
    _finish(p, accent)
    img.save(str(path))


def behaviour(path: Path) -> None:
    from capri.ui.rig import Pose
    accent = CATEGORY_COLOUR["behaviour"]
    img, p = _card(accent)
    _full(p, _rig(), pose=Pose(t=0.2, stride=0.8, lean=0.03))
    _motion_lines(p, accent)
    _finish(p, accent)
    img.save(str(path))


def look(path: Path, settings: dict, skin_def=None) -> None:
    """Her models / styles, and the chat window's skins."""
    accent = CATEGORY_COLOUR["look"]
    if "chat_skin" in settings and skin_def is not None:
        return _chat(path, skin_def)
    img, p = _card(accent)
    if "body_style" in settings:
        _full(p, _rig(look=settings["body_style"]))
    elif "hair_style" in settings:
        _portrait(p, _rig(hair=settings["hair_style"]))
    elif "lounge" in settings:
        lying = sprites().lying
        from capri.ui.neon import flat_image
        s = flat_image(lying, False).scaled(SIZE - 30, SIZE - 30, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
        p.fillRect(QRectF(16, SIZE * 0.72, SIZE - 32, 10), QColor(0, 226, 255, 160))   # her panel under her
        p.drawImage(QPointF((SIZE - s.width()) / 2, SIZE * 0.72 - s.height()), s)
    elif "perch_windows" in settings:
        win = QRectF(24, SIZE * 0.66, SIZE - 48, SIZE * 0.28)
        p.setPen(QPen(QColor(0, 226, 255), 3))
        p.setBrush(QColor(20, 24, 36))
        p.drawRect(win)
        p.fillRect(QRectF(win.left(), win.top(), win.width(), 16), QColor(0, 226, 255, 120))
        p.save()
        p.setClipRect(QRectF(0, 0, SIZE, win.top() + 2))
        _her(p, _rig(), SIZE * 0.5, QPointF(SIZE * 0.5, win.top() + 2))
        p.restore()
    elif settings.get("character_style") == "portrait":
        face = sprites().expressions["neutral"].scaled(int(SIZE * 0.7), int(SIZE * 0.7),
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
        r = QRectF((SIZE - face.width()) / 2 - 8, 26, face.width() + 16, face.height() + 16)
        p.setPen(QPen(QColor("#ff2a6d"), 3))
        p.setBrush(QColor(8, 6, 12))
        p.drawPath(_chamfer(r, 12))
        p.drawImage(QPointF(r.left() + 8, r.top() + 8), face)
    elif settings.get("character_style") == "classic":
        art = QImage(str(ROOT / "assets" / "capri" / "idle.png"))
        s = art.scaled(SIZE - 40, SIZE - 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawImage(QPointF((SIZE - s.width()) / 2, SIZE - 14 - s.height()), s)
    elif "drone_look" in settings:
        face = sprites().expressions["serious"].scaled(int(SIZE * 0.6), int(SIZE * 0.6), Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)
        p.setPen(QPen(QColor(40, 230, 110), 4))
        p.setBrush(QColor(40, 230, 110, 40))
        p.drawEllipse(QPointF(SIZE / 2, SIZE / 2), SIZE * 0.36, SIZE * 0.36)
        p.drawImage(QPointF((SIZE - face.width()) / 2, (SIZE - face.height()) / 2), face)
    _finish(p, accent)
    img.save(str(path))


def _chat(path: Path, s) -> None:
    """A tiny chat window in that skin: header, one line from you, one from her."""
    accent = s.accent
    img, p = _card(accent)
    win = QRectF(22, 30, SIZE - 44, SIZE - 60)
    p.setPen(QPen(QColor(accent), 3))
    p.setBrush(QColor(s.bg))
    p.drawPath(_chamfer(win, 12))
    p.fillRect(QRectF(win.left() + 3, win.top() + 3, win.width() - 6, 34), QColor(s.panel))
    face = sprites().expressions["happy"].scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
    p.drawImage(QPointF(win.left() + 10, win.top() + 6), face)
    f = QFont("monospace" if s.font else "")
    f.setPixelSize(16)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(s.text))
    p.drawText(QRectF(win.left() + 46, win.top() + 6, win.width() - 56, 28), Qt.AlignmentFlag.AlignVCenter,
               s.title[:14])
    for i, (who, col, w) in enumerate(((s.you_name, s.you, 0.62), (s.her_name, accent, 0.82))):
        y = win.top() + 58 + i * 62
        p.setPen(QColor(col))
        f.setPixelSize(14)
        p.setFont(f)
        p.drawText(QPointF(win.left() + 14, y), who[:8])
        p.fillRect(QRectF(win.left() + 14, y + 8, (win.width() - 28) * w, 12), QColor(col).darker(150))
        p.fillRect(QRectF(win.left() + 14, y + 26, (win.width() - 28) * w * 0.7, 12), QColor(s.dim))
    _finish(p, accent)
    img.save(str(path))
