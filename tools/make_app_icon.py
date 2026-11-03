"""Capri's app icon: her shard (the red "thumb drive" with green circuits) on a dark neon tile, slightly tilted,
with a glow behind it and one torn glitch slice. The big sizes get the full shard; the small ones (16 - 32 px, the
taskbar and tray) a bolder, simpler one so it still reads as her shard and not a smudge.

Makes assets/capri/app_icon.ico (16 - 256 px) and app_icon.png (256 px).
Run:  python tools/make_app_icon.py      (needs PySide6, numpy and Pillow)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_discord_art as art  # noqa: E402  (her shard drawing, and the QApplication)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient  # noqa: E402

TILT = 38
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def tile(p: QPainter, n: float) -> QPainterPath:
    """The dark rounded tile with a neon-red rim. Returns its shape (to clip to)."""
    inset = n * 0.04
    rect = QRectF(inset, inset, n - 2 * inset, n - 2 * inset)
    shape = QPainterPath()
    shape.addRoundedRect(rect, n * 0.22, n * 0.22)
    g = QLinearGradient(QPointF(0, 0), QPointF(n, n))
    g.setColorAt(0, QColor(30, 18, 34))
    g.setColorAt(1, QColor(8, 6, 12))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(shape)
    glow = QRadialGradient(QPointF(n * 0.5, n * 0.5), n * 0.5)
    glow.setColorAt(0, QColor(230, 30, 60, 120))
    glow.setColorAt(0.6, QColor(140, 20, 50, 40))
    glow.setColorAt(1, QColor(0, 0, 0, 0))
    p.setBrush(glow)
    p.drawPath(shape)
    return shape


def rim(p: QPainter, n: float, shape: QPainterPath) -> None:
    p.setBrush(Qt.BrushStyle.NoBrush)
    for width, alpha in ((0.05, 60), (0.022, 255)):
        p.setPen(QPen(QColor(255, 46, 86, alpha), max(1.0, n * width)))
        p.drawPath(shape)


def simple_shard(p: QPainter) -> None:
    """Her shard with only what survives at 16 - 32 px: silver plug, red body, one bright green trace, silver cap."""
    W = art.W
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(art.metal(-60, 60))
    p.drawRect(QRectF(-56, -470, 112, 150))
    p.setBrush(QColor(214, 48, 44))
    p.drawRect(QRectF(-W - 30, -330, 2 * W + 60, 640))
    p.setBrush(art.metal(-W, W))
    p.drawPolygon(art.poly((-W - 30, 300), (W + 30, 300), (W + 30, 420), (W - 10, 460), (-W + 10, 460),
                           (-W - 30, 420)))
    pen = QPen(QColor(110, 255, 170), 44)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(art.path_of([(-30, -270), (-30, -120), (30, -60), (30, 270)]))


def shard_layer(n: int) -> QImage:
    """Just her shard, on a clear layer the size of the icon."""
    layer = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
    layer.fill(0)
    p = QPainter(layer)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    small = n <= 32
    p.translate(n / 2, n / 2)
    p.rotate(TILT)
    scale = (0.96 if small else 0.80) * n / 880
    p.scale(scale, scale)
    if small:
        simple_shard(p)
    else:
        art.shard(p, None)
    p.end()
    return layer


def tinted(img: QImage, colour: QColor) -> QImage:
    out = QImage(img)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), colour)
    p.end()
    return out


def icon(n: int) -> QImage:
    img = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = tile(p, n)
    p.setClipPath(shape)
    her = shard_layer(n)
    if n < 48:
        p.drawImage(0, 0, her)
    else:                                               # one torn slice: a band of her, shifted, with a cyan ghost
        top, h = round(n * 0.56), max(2, round(n * 0.075))
        p.setClipRect(QRectF(0, 0, n, top))
        p.setClipPath(shape, Qt.ClipOperation.IntersectClip)
        p.drawImage(0, 0, her)
        p.setClipRect(QRectF(0, top + h, n, n))
        p.setClipPath(shape, Qt.ClipOperation.IntersectClip)
        p.drawImage(0, 0, her)
        p.setClipRect(QRectF(0, top, n, h))
        p.setClipPath(shape, Qt.ClipOperation.IntersectClip)
        p.drawImage(QPointF(-n * 0.03, 0), tinted(her, QColor(40, 230, 255, 140)))
        p.drawImage(QPointF(n * 0.06, 0), her)
        p.setClipPath(shape)
        for y in range(0, n, max(3, n // 64)):          # faint scanlines
            p.fillRect(QRectF(0, y, n, max(1.0, n / 256)), QColor(0, 0, 0, 38))
    p.setClipping(False)
    rim(p, n, shape)
    p.end()
    return img


def main(out: Path) -> None:
    from PIL import Image
    images = {n: art.to_pil(icon(n).convertToFormat(QImage.Format.Format_ARGB32)) for n in SIZES}
    images[256].save(out / "app_icon.png")
    images[256].save(out / "app_icon.ico", sizes=[(n, n) for n in SIZES],
                     append_images=[images[n] for n in SIZES if n != 256])
    for name in ("app_icon.png", "app_icon.ico"):
        print(name, (out / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "assets/capri"))
