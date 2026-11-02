"""Capri's shard (her "thumb drive" from the show) for Discord: red body, green circuit traces, silver ends."""
import sys
from PySide6.QtWidgets import QApplication
app = QApplication([])
from PySide6.QtGui import QImage, QPainter, QColor, QPainterPath, QPen, QLinearGradient, QRadialGradient, QPolygonF
from PySide6.QtCore import QPointF, QRectF, Qt

N = 1024
img = QImage(N, N, QImage.Format.Format_ARGB32)
img.fill(QColor(12, 11, 14))
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)

glow = QRadialGradient(QPointF(512, 512), 560)
glow.setColorAt(0, QColor(150, 20, 40, 120)); glow.setColorAt(1, QColor(0, 0, 0, 0))
p.setPen(Qt.PenStyle.NoPen); p.setBrush(glow); p.drawRect(0, 0, N, N)

p.translate(512, 512); p.rotate(38); p.scale(1.1, 1.1)   # held at an angle, like the photo; filling the frame


def poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def metal(x0, x1):
    g = QLinearGradient(QPointF(x0, 0), QPointF(x1, 0))
    for at, c in ((0, (120, 126, 136)), (0.18, (232, 236, 242)), (0.45, (176, 182, 192)),
                  (0.7, (214, 218, 226)), (1, (110, 116, 126))):
        g.setColorAt(at, QColor(*c))
    return g


W = 92                                            # half width of the body
# soft shadow
p.setBrush(QColor(0, 0, 0, 110))
p.drawPolygon(poly((-W + 22, -400), (W + 22, -400), (W + 22, 470), (-W + 22, 470)))

# -- top connector: a silver plug with fine pins ---------------------------------------------------------
p.setBrush(metal(-48, 48))
p.drawPolygon(poly((-48, -470), (48, -470), (48, -360), (-48, -360)))
p.setBrush(QColor(60, 64, 72))
for i in range(6):                                 # the pins' slots
    x = -40 + i * 15
    p.drawRect(QRectF(x, -470, 6, 70))
p.setBrush(metal(-62, 62))                         # stepped shoulder
p.drawPolygon(poly((-62, -365), (62, -365), (62, -330), (-62, -330)))

# -- silver collar with angular notches --------------------------------------------------------------------
p.setBrush(metal(-W, W))
p.drawPolygon(poly((-W + 14, -335), (W - 14, -335), (W, -315), (W, -270), (-W, -270), (-W, -315)))
p.setBrush(QColor(40, 42, 48))
p.drawPolygon(poly((-W, -300), (-W + 16, -300), (-W + 16, -284), (-W, -284)))
p.drawPolygon(poly((W - 16, -300), (W, -300), (W, -284), (W - 16, -284)))

# -- the red body -------------------------------------------------------------------------------------------
body = poly((-W, -272), (W, -272), (W, -90), (W - 10, -76), (W - 10, 30), (W, 44), (W, 300), (-W, 300),
            (-W, 160), (-W + 12, 146), (-W + 12, 60), (-W, 46))
red = QLinearGradient(QPointF(-W, 0), QPointF(W, 0))
for at, c in ((0, (120, 18, 22)), (0.15, (214, 52, 44)), (0.5, (196, 38, 36)), (0.85, (214, 56, 46)),
              (1, (110, 16, 20))):
    red.setColorAt(at, QColor(*c))
p.setBrush(red); p.drawPolygon(body)
# raised inner panel with a darker outline
panel = poly((-W + 18, -252), (W - 18, -252), (W - 18, 280), (-W + 18, 280))
p.setPen(QPen(QColor(120, 16, 20), 3)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPolygon(panel)
p.setPen(Qt.PenStyle.NoPen)

# -- green circuit traces ------------------------------------------------------------------------------------
traces = [
    [(-40, -245), (-40, -170), (-12, -142), (-12, -40), (-38, -14), (-38, 120), (-14, 144), (-14, 270)],
    [(0, -245), (0, -200), (26, -174), (26, -60), (4, -38), (4, 60), (30, 86), (30, 200), (8, 222), (8, 270)],
    [(38, -245), (38, -120), (52, -106), (52, 20)],
    [(-52, -120), (-52, 40), (-30, 62)],
    [(-30, 170), (-52, 192), (-52, 260)],
    [(44, 140), (52, 148), (52, 262)],
]
for glow_w, colour in ((14, QColor(60, 255, 150, 60)), (5, QColor(96, 255, 160))):
    pen = QPen(colour, glow_w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    for t in traces:
        path = QPainterPath(QPointF(*t[0]))
        for pt in t[1:]:
            path.lineTo(QPointF(*pt))
        p.drawPath(path)
p.setPen(Qt.PenStyle.NoPen)
for t in traces:                                   # little pads at the ends
    for x, y in (t[0], t[-1]):
        if -245 < y < 270:
            p.setBrush(QColor(96, 255, 160)); p.drawEllipse(QPointF(x, y), 7, 7)
            p.setBrush(QColor(20, 90, 50)); p.drawEllipse(QPointF(x, y), 3, 3)

# a light along the left edge (the red catches the light)
p.setBrush(QColor(255, 140, 120, 70))
p.drawPolygon(poly((-W + 4, -268), (-W + 10, -268), (-W + 10, 296), (-W + 4, 296)))

# -- bottom silver cap with a window and notches ------------------------------------------------------------
cap = poly((-W, 296), (W, 296), (W, 420), (W - 26, 448), (-W + 26, 448), (-W, 420))
p.setBrush(metal(-W, W)); p.drawPolygon(cap)
p.setBrush(QColor(28, 28, 34))
p.drawPolygon(poly((-30, 330), (30, 330), (30, 392), (-30, 392)))             # the window
p.setBrush(QColor(196, 38, 36))
p.drawPolygon(poly((-18, 342), (18, 342), (18, 380), (-18, 380)))             # red inside it
p.setBrush(QColor(60, 62, 70))
for y in (318, 404):
    p.drawPolygon(poly((-W, y), (-W + 14, y), (-W + 14, y + 10), (-W, y + 10)))
    p.drawPolygon(poly((W - 14, y), (W, y), (W, y + 10), (W - 14, y + 10)))
p.end()
img.save(sys.argv[1])
print("saved")
