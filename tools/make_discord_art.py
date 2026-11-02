"""Capri's Discord pictures.

* capri.png - her shard (her "thumb drive" from the show): red body, green circuit traces, silver ends.
  For the Developer Portal's Rich Presence art.
* capri.gif - the same shard, animated: energy runs along the circuits, a light sweeps over her, she floats.
* gaming.gif / music.gif - small animated badges shown in the corner while you game / listen to music.

Run:  python tools/make_discord_art.py assets/discord      (needs PySide6 and Pillow)
"""
import math
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from PySide6.QtGui import QImage, QPainter, QColor, QPainterPath, QPen, QLinearGradient, QRadialGradient, QPolygonF
from PySide6.QtCore import QPointF, QRectF, Qt

W = 92                                            # half width of the body
TRACES = [
    [(-40, -245), (-40, -170), (-12, -142), (-12, -40), (-38, -14), (-38, 120), (-14, 144), (-14, 270)],
    [(0, -245), (0, -200), (26, -174), (26, -60), (4, -38), (4, 60), (30, 86), (30, 200), (8, 222), (8, 270)],
    [(38, -245), (38, -120), (52, -106), (52, 20)],
    [(-52, -120), (-52, 40), (-30, 62)],
    [(-30, 170), (-52, 192), (-52, 260)],
    [(44, 140), (52, 148), (52, 262)],
]
GREEN = QColor(96, 255, 160)


def poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def metal(x0, x1):
    g = QLinearGradient(QPointF(x0, 0), QPointF(x1, 0))
    for at, c in ((0, (120, 126, 136)), (0.18, (232, 236, 242)), (0.45, (176, 182, 192)),
                  (0.7, (214, 218, 226)), (1, (110, 116, 126))):
        g.setColorAt(at, QColor(*c))
    return g


def path_of(points):
    path = QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    return path


def shard(p: QPainter, t: float | None = None) -> None:
    """The shard, centred on (0, 0) in shard units. t in [0, 1): the animation's moment (None = still)."""
    pulse = 1.0 if t is None else 0.75 + 0.25 * math.sin(t * 2 * math.pi)
    p.setPen(Qt.PenStyle.NoPen)
    # soft shadow
    p.setBrush(QColor(0, 0, 0, 110))
    p.drawPolygon(poly((-W + 22, -400), (W + 22, -400), (W + 22, 470), (-W + 22, 470)))

    # -- top connector: a silver plug with fine pins ---------------------------------------------------
    p.setBrush(metal(-48, 48))
    p.drawPolygon(poly((-48, -470), (48, -470), (48, -360), (-48, -360)))
    p.setBrush(QColor(60, 64, 72))
    for i in range(6):                                 # the pins' slots
        p.drawRect(QRectF(-40 + i * 15, -470, 6, 70))
    p.setBrush(metal(-62, 62))                         # stepped shoulder
    p.drawPolygon(poly((-62, -365), (62, -365), (62, -330), (-62, -330)))

    # -- silver collar with angular notches ----------------------------------------------------------------
    p.setBrush(metal(-W, W))
    p.drawPolygon(poly((-W + 14, -335), (W - 14, -335), (W, -315), (W, -270), (-W, -270), (-W, -315)))
    p.setBrush(QColor(40, 42, 48))
    p.drawPolygon(poly((-W, -300), (-W + 16, -300), (-W + 16, -284), (-W, -284)))
    p.drawPolygon(poly((W - 16, -300), (W, -300), (W, -284), (W - 16, -284)))

    # -- the red body ---------------------------------------------------------------------------------------
    body = poly((-W, -272), (W, -272), (W, -90), (W - 10, -76), (W - 10, 30), (W, 44), (W, 300), (-W, 300),
                (-W, 160), (-W + 12, 146), (-W + 12, 60), (-W, 46))
    red = QLinearGradient(QPointF(-W, 0), QPointF(W, 0))
    for at, c in ((0, (120, 18, 22)), (0.15, (214, 52, 44)), (0.5, (196, 38, 36)), (0.85, (214, 56, 46)),
                  (1, (110, 16, 20))):
        red.setColorAt(at, QColor(*c))
    p.setBrush(red)
    p.drawPolygon(body)
    panel = poly((-W + 18, -252), (W - 18, -252), (W - 18, 280), (-W + 18, 280))
    p.setPen(QPen(QColor(120, 16, 20), 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(panel)
    p.setPen(Qt.PenStyle.NoPen)

    # -- green circuit traces (glowing a little brighter and dimmer) ---------------------------------------------
    for glow_w, alpha in ((14, int(60 * pulse)), (5, 255)):
        colour = QColor(60, 255, 150, alpha) if glow_w > 5 else QColor(
            int(70 + 26 * pulse), 255, int(130 + 30 * pulse))
        pen = QPen(colour, glow_w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for tr in TRACES:
            p.drawPath(path_of(tr))
    p.setPen(Qt.PenStyle.NoPen)
    for tr in TRACES:                                  # little pads at the ends
        for x, y in (tr[0], tr[-1]):
            if -245 < y < 270:
                p.setBrush(GREEN)
                p.drawEllipse(QPointF(x, y), 7, 7)
                p.setBrush(QColor(20, 90, 50))
                p.drawEllipse(QPointF(x, y), 3, 3)

    # -- energy running along the circuits ------------------------------------------------------------------------
    if t is not None:
        for k, tr in enumerate(TRACES):
            path = path_of(tr)
            for spark in range(2 if path.length() > 300 else 1):
                at = (t + k * 0.37 + spark * 0.5) % 1.0
                pt = path.pointAtPercent(at)
                glow = QRadialGradient(pt, 26)
                glow.setColorAt(0, QColor(220, 255, 230, 255))
                glow.setColorAt(0.25, QColor(120, 255, 170, 200))
                glow.setColorAt(1, QColor(60, 255, 150, 0))
                p.setBrush(glow)
                p.drawEllipse(pt, 26, 26)

    # a light along the left edge (the red catches the light)
    p.setBrush(QColor(255, 140, 120, 70))
    p.drawPolygon(poly((-W + 4, -268), (-W + 10, -268), (-W + 10, 296), (-W + 4, 296)))

    # a sheen sweeping down the body
    if t is not None:
        y = -300 + ((t * 1.6) % 1.0) * 900
        sheen = QLinearGradient(QPointF(0, y - 60), QPointF(0, y + 60))
        sheen.setColorAt(0, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.5, QColor(255, 230, 220, 70))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(sheen)
        p.drawPolygon(body)

    # -- bottom silver cap with a window and notches ------------------------------------------------------
    cap = poly((-W, 296), (W, 296), (W, 420), (W - 26, 448), (-W + 26, 448), (-W, 420))
    p.setBrush(metal(-W, W))
    p.drawPolygon(cap)
    p.setBrush(QColor(28, 28, 34))
    p.drawPolygon(poly((-30, 330), (30, 330), (30, 392), (-30, 392)))             # the window
    blink = 1.0 if t is None else 0.55 + 0.45 * max(0.0, math.sin(t * 4 * math.pi))
    p.setBrush(QColor(int(120 + 120 * blink), int(30 + 30 * blink), int(30 + 20 * blink)))
    p.drawPolygon(poly((-18, 342), (18, 342), (18, 380), (-18, 380)))             # her light inside it
    p.setBrush(QColor(60, 62, 70))
    for y in (318, 404):
        p.drawPolygon(poly((-W, y), (-W + 14, y), (-W + 14, y + 10), (-W, y + 10)))
        p.drawPolygon(poly((W - 14, y), (W, y), (W, y + 10), (W - 14, y + 10)))


def background(p: QPainter, n: int, strength: float = 1.0) -> None:
    glow = QRadialGradient(QPointF(n / 2, n / 2), n * 0.55)
    glow.setColorAt(0, QColor(150, 20, 40, int(120 * strength)))
    glow.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawRect(0, 0, n, n)


def shard_image(n: int, t: float | None) -> QImage:
    img = QImage(n, n, QImage.Format.Format_ARGB32)
    img.fill(QColor(12, 11, 14))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    background(p, n, 1.0 if t is None else 0.8 + 0.25 * math.sin(t * 2 * math.pi))
    bob = 0.0 if t is None else math.sin(t * 2 * math.pi) * n * 0.012
    p.translate(n / 2, n / 2 + bob)
    p.rotate(38 + (0.0 if t is None else math.sin(t * 2 * math.pi) * 1.5))
    p.scale(1.1 * n / 1024, 1.1 * n / 1024)
    shard(p, t)
    p.end()
    return img


def badge(n: int, t: float, kind: str) -> QImage:
    """A round badge: a game controller with blinking buttons, or bouncing equaliser bars."""
    img = QImage(n, n, QImage.Format.Format_ARGB32)
    img.fill(QColor(16, 14, 20))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = n / 2
    ring = 0.5 + 0.5 * math.sin(t * 2 * math.pi)
    p.setPen(QPen(QColor(int(150 + 80 * ring), 30, 44), n * 0.06))
    p.setBrush(QColor(28, 24, 34))
    p.drawEllipse(QPointF(c, c), n * 0.44, n * 0.44)
    p.setPen(Qt.PenStyle.NoPen)
    if kind == "gaming":
        bob = math.sin(t * 2 * math.pi) * n * 0.02
        p.translate(c, c + bob)
        p.rotate(math.sin(t * 2 * math.pi) * 6)
        s = n / 128
        pad = QPainterPath()
        pad.addRoundedRect(QRectF(-40 * s, -18 * s, 80 * s, 36 * s), 16 * s, 16 * s)
        pad.addEllipse(QPointF(-30 * s, 12 * s), 14 * s, 14 * s)
        pad.addEllipse(QPointF(30 * s, 12 * s), 14 * s, 14 * s)
        pad.setFillRule(Qt.FillRule.WindingFill)
        body = QLinearGradient(QPointF(0, -18 * s), QPointF(0, 26 * s))
        body.setColorAt(0, QColor(222, 58, 48))
        body.setColorAt(1, QColor(130, 18, 24))
        p.setBrush(body)
        p.drawPath(pad.simplified())
        p.setBrush(QColor(235, 238, 244))                                 # d-pad
        p.drawRect(QRectF(-30 * s, -4 * s, 16 * s, 6 * s))
        p.drawRect(QRectF(-25 * s, -9 * s, 6 * s, 16 * s))
        for i, (x, y) in enumerate(((22, -2), (30, -9), (30, 5), (38, -2))):
            lit = int((t * 8) % 4) == i
            p.setBrush(QColor(140, 255, 190) if lit else QColor(40, 150, 90))
            p.drawEllipse(QPointF(x * s, y * s), (4.6 if lit else 3.6) * s, (4.6 if lit else 3.6) * s)
    else:
        bars, width = 5, n * 0.085
        for i in range(bars):
            h = n * (0.12 + 0.22 * abs(math.sin((t * 2 + i * 0.23) * math.pi * (1 + (i % 2) * 0.5))))
            x = c + (i - (bars - 1) / 2) * width * 1.45 - width / 2
            g = QLinearGradient(QPointF(0, c + n * 0.2), QPointF(0, c + n * 0.2 - h))
            g.setColorAt(0, QColor(214, 46, 44))
            g.setColorAt(1, QColor(110, 255, 170))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(x, c + n * 0.2 - h, width, h), width / 2.5, width / 2.5)
    p.end()
    return img


def to_pil(img: QImage):
    from PIL import Image
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA", 0, 1)


def save_gif(frames, path: Path, ms: int) -> None:
    from PIL import Image
    pal = [f.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
           for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=ms, loop=0, optimize=True, disposal=1)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    shard_image(1024, None).save(str(out / "capri.png"))
    save_gif([to_pil(shard_image(320, i / 30)) for i in range(30)], out / "capri.gif", 70)
    save_gif([to_pil(badge(128, i / 24, "gaming")) for i in range(24)], out / "gaming.gif", 80)
    save_gif([to_pil(badge(128, i / 24, "music")) for i in range(24)], out / "music.gif", 80)
    for name in ("capri.png", "capri.gif", "gaming.gif", "music.gif"):
        print(name, (out / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "assets/discord"))
