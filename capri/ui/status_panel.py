"""The small black terminal-style status panel that floats above Capri."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QLinearGradient, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPaintEvent, QPen

from ..controller import CompanionController
from ..states import STATE_STYLES, State
from . import theme
from .art import CharacterArt
from .overlay_window import OverlayWindow
from .static_fx import StaticFX

GLOW = 6         # transparent margin for the neon glow
TAIL = 9         # height of the speech-bubble tail
STEP = 4         # height of the step in the top edge next to the badge
TAIL_HALF = 8    # half the width of the tail's base
ANSWER_LINES = 5 # an AI answer (SPEAKING) may use more lines than a status message
BARS = 4         # voice bars in the badge while she talks


@dataclass(frozen=True)
class PanelMetrics:
    width: int
    pad: int
    icon: int
    title_lines: int
    log: bool
    row_h: int
    verb_col: int
    f_header: QFont
    f_badge: QFont
    f_title: QFont
    f_log: QFont


def normal_metrics() -> PanelMetrics:
    return PanelMetrics(300, 10, 36, 2, True, 15, 52,
                        theme.mono(7.5, bold=True, spacing=1.2), theme.mono(7, bold=True, spacing=0.8),
                        theme.sans(10), theme.mono(8))


def compact_metrics() -> PanelMetrics:
    return PanelMetrics(210, 7, 24, 1, False, 13, 44,
                        theme.mono(6.5, bold=True, spacing=1.0), theme.mono(6, bold=True, spacing=0.6),
                        theme.sans(8.5), theme.mono(7))


class StatusPanel(OverlayWindow):
    type_clicked = Signal()               # the TYPE button: open the chat to type to her
    talk_clicked = Signal()               # the TALK button: she listens now (no "Hey Capri" needed)

    def __init__(self, controller: CompanionController, icon: QImage, always_on_top: bool = True) -> None:
        super().__init__(always_on_top)
        self.chat_bits = True              # the "YOU >" line and the TYPE / TALK buttons
        self._buttons: dict[str, QRectF] = {}
        self.clicked.connect(self._clicked)
        self.setWindowTitle("Capri - status")
        self.controller = controller
        self._icon_src = icon
        self._icon_cache: QImage | None = None
        self.m = normal_metrics()
        self.show_log = True
        self.tail_x = self.m.width * 0.8   # where the tail points, local coords; set by Companion
        self.tail_up = False               # True when the panel sits *below* Capri
        self.tail_visible = True           # no tail while she's lying on top of the panel
        self.talking = False
        self.level = 0.0
        self.reveal = 1.0                  # typewriter: share of the message shown

        # Badge pulse: only runs while listening/processing, so idle costs nothing.
        self._pulse = 1.0
        self._anim = QVariantAnimation(self, startValue=0.35, endValue=1.0, duration=700)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_pulse)

        # (The TV static is gone: the panel is a clean cyberpunk message now.)
        self.static = StaticFX()
        self._overlay: QImage | None = None
        self.inverted = False             # search mode: colours flipped
        self._overlay_key = None
        self.static_on = False
        self._last_state = None
        self._static_timer = QTimer(self)
        self._static_timer.setInterval(125)        # 8 fps is plenty for static
        self._static_timer.timeout.connect(self._static_tick)

        controller.changed.connect(self.refresh)
        self.refresh()

    # -- static ------------------------------------------------------------
    def set_static(self, on: bool) -> None:
        """Kept for old settings files: the message style has no static."""
        self.static_on = False
        self._update_static_timer()
        self.update()

    def _update_static_timer(self) -> None:
        running = False
        if running and not self._static_timer.isActive():
            self._static_timer.start()
        elif not running:
            self._static_timer.stop()

    def _static_tick(self) -> None:
        self.static.step()
        if not self.static_on and not self.static.bursting:
            self._static_timer.stop()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_static_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._static_timer.stop()      # hidden = no CPU

    # -- configuration -----------------------------------------------------
    @property
    def panel_width(self) -> int:
        return self.m.width

    def set_compact(self, compact: bool) -> None:
        self.m = compact_metrics() if compact else normal_metrics()
        self._icon_cache = None
        self.refresh()

    def set_show_log(self, show: bool) -> None:
        self.show_log = show
        self.refresh()

    # -- talking (driven by LipSync) ----------------------------------------
    def set_talking(self, on: bool) -> None:
        self.talking = on
        self.reveal = 0.0 if on else 1.0
        if not on:
            self.level = 0.0
        self.update()

    def set_voice_level(self, level: float) -> None:
        self.level = level
        self.update()

    def set_progress(self, progress: float) -> None:
        self.reveal = min(1.0, progress * 1.15)   # text runs slightly ahead of the voice
        self.update()

    def set_tail(self, x: float, up: bool, visible: bool = True) -> None:
        if up != self.tail_up:
            self.tail_up = up
            self.refresh()
        self.tail_x = x
        self.tail_visible = visible
        self.update()

    def set_icon_source(self, image: QImage) -> None:
        """Swap the icon art (e.g. her current expression or mouth shape)."""
        if image is not self._icon_src:
            self._icon_src = image
            self._icon_cache = None
            self.update()

    # -- layout -----------------------------------------------------------
    def _wrap_title(self, text: str, max_w: float) -> list[str]:
        fm = QFontMetricsF(self.m.f_title)
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if fm.horizontalAdvance(trial) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        limit = self.m.title_lines
        if self.controller.state is State.SPEAKING:
            limit = ANSWER_LINES if self.m.log else 2
        if len(lines) > limit:
            lines = lines[:limit - 1] + [fm.elidedText(" ".join(lines[limit - 1:]), Qt.TextElideMode.ElideRight, max_w)]
        return lines or [""]

    def _text_x(self) -> float:
        return self.m.pad + self.m.icon + self.m.pad

    def _header_h(self) -> float:
        return QFontMetricsF(self.m.f_header).height() + 4

    def refresh(self) -> None:
        c, m = self.controller, self.m
        style = STATE_STYLES[c.state]
        if style.pulse and self._anim.state() != QVariantAnimation.State.Running:
            self._anim.start()
        elif not style.pulse and self._anim.state() == QVariantAnimation.State.Running:
            self._anim.stop()
            self._pulse = 1.0

        self._title_lines = self._wrap_title(c.message, m.width - self._text_x() - m.pad)
        title_h = QFontMetricsF(m.f_title).height()
        self._you = self.heard() if self.chat_bits else ""
        you_h = QFontMetricsF(m.f_log).height() + 2 if self._you else 0.0
        head_block = max(m.icon, self._header_h() + you_h + title_h * len(self._title_lines))
        rows = len([e for e in c.entries if e[0] != "Heard"]) if (self.show_log and m.log) else 0
        buttons_h = (QFontMetricsF(m.f_badge).height() + 10) if self.chat_bits else 0.0
        body_h = m.pad + STEP + head_block + (8 + rows * m.row_h if rows else 0) + \
            (8 + buttons_h if buttons_h else 0) + m.pad
        self.setFixedSize(m.width + GLOW * 2, round(body_h + GLOW * 2 + TAIL))
        self._body = QRectF(GLOW, GLOW + (TAIL if self.tail_up else 0), m.width, body_h)
        if c.state is not self._last_state:
            if self._last_state is not None:
                self.static.burst()          # status changed: glitch!
            self._last_state = c.state
            self._update_static_timer()
        self.update()

    def heard(self) -> str:
        """What she last heard you say (from her activity log)."""
        for verb, detail in reversed(self.controller.entries):
            if verb == "Heard":
                return detail.split(" -> ")[0].strip().strip('"')
        return ""

    def _clicked(self, at) -> None:
        local = QPointF(self.mapFromGlobal(at))
        for name, rect in self._buttons.items():
            if rect.adjusted(-3, -3, 3, 3).contains(local):
                (self.type_clicked if name == "type" else self.talk_clicked).emit()
                return

    def _on_pulse(self, value: float) -> None:
        self._pulse = float(value)
        self.update()

    # -- painting ---------------------------------------------------------
    def _tail_center(self) -> float:
        r = self._body
        return min(max(self.tail_x, r.left() + 16), r.right() - 16)

    def _outline(self, badge_w: float) -> QPainterPath:
        r = self._body
        step_x = r.right() - badge_w - self.m.pad - 10
        tx = self._tail_center()
        low, high = r.top() + STEP, r.top()   # the two heights of the stepped top edge

        path = QPainterPath()
        path.moveTo(r.left(), low)
        if self.tail_up:
            # Keep the tail off the diagonal step: snap it to whichever flat part it is nearer.
            if step_x - TAIL_HALF - 4 < tx < step_x + STEP + TAIL_HALF + 4:
                tx = step_x - TAIL_HALF - 4 if tx < step_x + STEP / 2 else step_x + STEP + TAIL_HALF + 4
        if self.tail_up and tx < step_x:
            path.lineTo(tx - TAIL_HALF, low)
            path.lineTo(tx, r.top() - TAIL)
            path.lineTo(tx + TAIL_HALF, low)
        path.lineTo(step_x, low)
        path.lineTo(step_x + STEP, high)
        if self.tail_up and tx > step_x:
            path.lineTo(tx - TAIL_HALF, high)
            path.lineTo(tx, r.top() - TAIL)
            path.lineTo(tx + TAIL_HALF, high)
        path.lineTo(r.right(), high)
        path.lineTo(r.right(), r.bottom())
        if not self.tail_up and self.tail_visible:
            path.lineTo(tx + TAIL_HALF, r.bottom())
            path.lineTo(tx, r.bottom() + TAIL)
            path.lineTo(tx - TAIL_HALF, r.bottom())
        path.lineTo(r.left(), r.bottom())
        path.closeSubpath()
        return path

    def _icon(self) -> QImage:
        dpr = self.devicePixelRatioF()
        size = self.m.icon
        cache = self._icon_cache
        if cache is None or cache.devicePixelRatio() != dpr or cache.width() != round(size * dpr):
            self._icon_cache = CharacterArt.scaled(self._icon_src, size, size, dpr, cover=True)
        return self._icon_cache

    def set_inverted(self, on: bool) -> None:
        """Search mode: the whole panel in inverted colours."""
        if on != self.inverted:
            self.inverted = on
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self.inverted:
            p = QPainter(self)
            self._paint(p)
            p.end()
            return
        dpr = self.devicePixelRatioF()
        img = QImage(round(self.width() * dpr), round(self.height() * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(0)
        q = QPainter(img)
        self._paint(q)
        q.end()
        img = img.convertToFormat(QImage.Format.Format_ARGB32)         # straight alpha: only the colours flip
        img.invertPixels(QImage.InvertMode.InvertRgb)
        p = QPainter(self)
        p.drawImage(QPointF(0, 0), img)
        p.end()

    def _paint(self, p: QPainter) -> None:
        c, m = self.controller, self.m
        style = STATE_STYLES[c.state]
        accent = theme.ALERT if style.alert else theme.GREEN
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = self._body

        badge_text = f"● {style.badge}"
        fm_badge = QFontMetricsF(m.f_badge)
        badge_w = fm_badge.horizontalAdvance(badge_text) + 12
        if self.talking:
            badge_text = f"    {style.badge}"   # room for the voice bars instead of the dot
        path = self._outline(badge_w)

        # A cyberpunk message: dark glass with a crimson glow.
        p.setPen(QPen(theme.MSG_GLOW, 6))
        bg = QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0, theme.MSG_BG_TOP)
        bg.setColorAt(1, theme.MSG_BG_BOTTOM)
        p.setBrush(bg)
        p.drawPath(path)
        # Everything else (borders, icon, text) only changes when the content does: cache it,
        # so a static frame is just noise + one image copy.
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, c.state, c.message, c.channel, tuple(c.entries), self._pulse,
               self.level, self.reveal, self.talking, self.tail_x, self.tail_up, self.tail_visible,
               self._icon_src.cacheKey(), m.width, self.show_log, self.chat_bits, getattr(self, "_you", ""))
        if key != self._overlay_key:
            overlay = QImage(round(self.width() * dpr), round(self.height() * dpr),
                             QImage.Format.Format_ARGB32_Premultiplied)
            overlay.setDevicePixelRatio(dpr)
            overlay.fill(0)
            q = QPainter(overlay)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self._paint_overlay(q, c, m, style, accent, r, path, badge_text, fm_badge, badge_w)
            q.end()
            self._overlay, self._overlay_key = overlay, key
        p.drawImage(QPointF(0, 0), self._overlay)

    def _paint_overlay(self, p: QPainter, c, m, style, accent, r: QRectF, path, badge_text: str,
                       fm_badge, badge_w: float) -> None:
        # faint fixed scanlines (no noise)
        p.save()
        p.setClipPath(path)
        y = r.top()
        while y < r.bottom():
            p.fillRect(QRectF(r.left(), y, r.width(), 1), theme.MSG_SCANLINE)
            y += 3
        p.restore()
        # crimson frame, cyan underline, heavy left edge
        p.setPen(QPen(theme.MSG_RED, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(QPen(theme.MSG_CYAN, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        base_y = r.bottom() - 0.5
        if self.tail_up or not self.tail_visible:
            p.drawLine(QPointF(r.left() + 10, base_y), QPointF(r.right() - 24, base_y))
        else:
            tx = self._tail_center()
            p.drawLine(QPointF(r.left() + 10, base_y), QPointF(max(r.left() + 10, tx - TAIL_HALF), base_y))
            p.drawLine(QPointF(min(r.right() - 24, tx + TAIL_HALF), base_y), QPointF(r.right() - 24, base_y))
        p.setPen(QPen(theme.MSG_RED, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawLine(QPointF(r.left() + 1.5, r.top() + STEP), QPointF(r.left() + 1.5, r.bottom()))
        # corner brackets
        p.setPen(QPen(theme.MSG_CYAN, 1.5))
        k = 7
        p.drawPolyline([QPointF(r.right() - 3, r.bottom() - k - 3), QPointF(r.right() - 3, r.bottom() - 3),
                        QPointF(r.right() - k - 3, r.bottom() - 3)])
        p.drawPolyline([QPointF(r.left() + 6, r.top() + STEP + k + 3), QPointF(r.left() + 6, r.top() + STEP + 3),
                        QPointF(r.left() + k + 6, r.top() + STEP + 3)])

        # Character icon.
        top = r.top() + STEP + m.pad
        icon_rect = QRectF(r.left() + m.pad, top, m.icon, m.icon)
        p.drawImage(icon_rect.topLeft(), self._icon())
        p.setPen(QPen(theme.MSG_RED, 1))
        p.drawRect(icon_rect)

        # Header: "CAPRI / SYSTEM".
        text_x = r.left() + self._text_x()
        p.setFont(m.f_header)
        fm_head = QFontMetricsF(m.f_header)
        name = "CAPRI"
        p.setPen(theme.TEXT_HEADER)
        p.drawText(QPointF(text_x, top + fm_head.ascent()), name)
        p.setPen(theme.MSG_RED)
        p.drawText(QPointF(text_x + fm_head.horizontalAdvance(name + " "), top + fm_head.ascent()),
                   f"// {'MESSAGE' if c.channel == 'SYSTEM' else c.channel}")

        # Status badge in the raised top-right tab.
        badge = QRectF(r.right() - m.pad - badge_w, r.top() + 5, badge_w, fm_badge.height() + 3)
        fill = QColor(accent)
        fill.setAlphaF(self._pulse)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRect(badge)
        p.setPen(theme.BADGE_TEXT)
        p.setFont(m.f_badge)
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, badge_text)
        if self.talking:
            # Little equaliser bars, bouncing with her voice.
            bar_w, gap = 2.0, 1.5
            bx = badge.left() + 6
            for i in range(BARS):
                wobble = (0.55, 1.0, 0.75, 0.9)[i]
                bh = max(1.5, (badge.height() - 5) * min(1.0, self.level * wobble + 0.12))
                p.fillRect(QRectF(bx + i * (bar_w + gap), badge.center().y() + (badge.height() - 5) / 2 - bh,
                                  bar_w, bh), theme.BADGE_TEXT)

        # What you said, dim, above her answer.
        y = top + self._header_h()
        if getattr(self, "_you", ""):
            p.setFont(m.f_log)
            fm_you = QFontMetricsF(m.f_log)
            p.setPen(theme.MSG_CYAN)
            p.drawText(QPointF(text_x, y + fm_you.ascent()), "YOU \u203a")
            p.setPen(theme.TEXT_LOG)
            width = r.right() - m.pad - text_x - fm_you.horizontalAdvance("YOU \u203a ")
            p.drawText(QPointF(text_x + fm_you.horizontalAdvance("YOU \u203a "), y + fm_you.ascent()),
                       fm_you.elidedText(self._you, Qt.TextElideMode.ElideRight, width))
            y += fm_you.height() + 2

        # Title / status message.
        p.setFont(m.f_title)
        p.setPen(theme.TEXT_TITLE)
        fm_title = QFontMetricsF(m.f_title)
        budget = round(sum(len(line) for line in self._title_lines) * self.reveal)
        for line in self._title_lines:
            shown = line[:max(0, budget)]                 # typewriter while she speaks
            budget -= len(line)
            p.drawText(QPointF(text_x, y + fm_title.ascent()), shown)
            y += fm_title.height()

        # Activity log: green verb column, grey detail column.
        if self.show_log and m.log and c.entries:
            p.setFont(m.f_log)
            fm_log = QFontMetricsF(m.f_log)
            y = max(top + m.icon, y) + 8
            detail_w = r.right() - m.pad - (text_x + m.verb_col)
            for verb, detail in c.entries:
                if verb == "Heard":
                    continue                                   # (it's the "YOU >" line now)
                base = y + fm_log.ascent()
                p.setPen(accent if verb.upper() == "ERROR" else theme.GREEN)
                p.drawText(QPointF(text_x, base), verb)
                p.setPen(theme.TEXT_LOG)
                p.drawText(QPointF(text_x + m.verb_col, base),
                           fm_log.elidedText(detail, Qt.TextElideMode.ElideRight, detail_w))
                y += m.row_h

        # TYPE / TALK: angled chips along the bottom edge
        self._buttons = {}
        if self.chat_bits:
            fm_b = QFontMetricsF(m.f_badge)
            bh = fm_b.height() + 6
            by = r.bottom() - m.pad - bh
            x = r.right() - m.pad
            p.setFont(m.f_badge)
            for name, label, colour in (("talk", "\u25c9 TALK", theme.MSG_RED), ("type", "\u2328 TYPE", theme.MSG_CYAN)):
                bw = fm_b.horizontalAdvance(label) + 18
                rect = QRectF(x - bw, by, bw, bh)
                chip = QPainterPath()
                chip.moveTo(rect.left() + 6, rect.top())
                chip.lineTo(rect.right(), rect.top())
                chip.lineTo(rect.right(), rect.bottom() - 6)
                chip.lineTo(rect.right() - 6, rect.bottom())
                chip.lineTo(rect.left(), rect.bottom())
                chip.lineTo(rect.left(), rect.top() + 6)
                chip.closeSubpath()
                fill = QColor(colour)
                fill.setAlpha(40)
                p.setBrush(fill)
                p.setPen(QPen(colour, 1.2))
                p.drawPath(chip)
                p.setPen(colour)
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
                self._buttons[name] = rect
                x -= bw + 8
