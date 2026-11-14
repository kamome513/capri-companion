"""Screen intelligence (2.4): she explains what's on your screen, finds errors and says how to fix them, reads charts,
and draws on the things she's talking about. And she can tell you what changed since she last looked.

* "explain this" / "what am I looking at"     - the app, what's going on, what the main parts do
* "what's wrong" / "find the error" / "help me fix this"   - the error / warning, why, and 1-3 steps to fix it
* "read this chart" / "what does this graph show"          - what it shows, the key numbers and trends
    -> her AI answers with what to say AND where the things are; she circles them on screen (labelled)
* "remember my screen" then later "what changed"           - the parts of the screen that changed, circled
    (done on your PC by comparing the two pictures - no AI needed)

Uses the same look as "what do you see?" (screen_watch.py): never at private windows, explains a black screenshot.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable

log = logging.getLogger("capri")

TASKS = {
    "explain": "Explain this screen to the user: which app it is, what's going on, and what the main parts or "
               "buttons they'd use are for.",
    "error": "Look for an error, warning, crash or anything that's gone wrong on this screen. If there is one, say "
             "what it means in plain words, the likely cause, and 1-3 concrete steps to fix it. If nothing's wrong, "
             "say so.",
    "chart": "Read the chart, graph, table or picture on this screen: what it shows, the important numbers and the "
             "trend. Be specific.",
}
FORMAT = """
Reply with ONLY a JSON object, nothing else:
{{"say": "<what you tell the user: 2-4 short spoken sentences, in your own voice>",
  "marks": [{{"label": "<1-3 words>", "x": <left edge, 0-1 across the picture>, "y": <top edge, 0-1 down>,
             "w": <width, 0-1>, "h": <height, 0-1>}}]}}
"marks": the 1-4 most important things you mention (where they are in the picture), or [] if none.
{extra}"""


def parse_answer(text: str) -> tuple[str, list[dict]]:
    """The AI's answer -> (what to say, [{label, x, y, w, h}]) - plain text answers still work (no marks)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            say = str(data.get("say") or "").strip()
            marks = []
            for mk in data.get("marks", [])[:4] if isinstance(data.get("marks"), list) else []:
                try:
                    x, y = float(mk["x"]), float(mk["y"])
                    w, h = float(mk.get("w", 0.05)), float(mk.get("h", 0.05))
                except (KeyError, TypeError, ValueError):
                    continue
                if 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1:
                    marks.append({"label": str(mk.get("label", ""))[:30], "x": x, "y": y,
                                  "w": min(w, 1 - x), "h": min(h, 1 - y)})
            if say:
                return say, marks
        except ValueError:
            pass
    return re.sub(r"\s+", " ", re.sub(r"```\w*|```", "", text or "")).strip(), []


# -- what changed: comparing two pictures on this PC ---------------------------------------------------------------
GRID = (32, 18)


def thumb(image):
    """A small grey copy of a screenshot (for comparing), or None."""
    try:
        import numpy as np
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        if image is None or image.isNull():
            return None
        small = image.scaled(GRID[0] * 6, GRID[1] * 6, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
        a = np.frombuffer(small.constBits(), np.uint8).reshape(small.height(), small.bytesPerLine())[:, :GRID[0] * 6]
        return a.astype(np.int16)
    except Exception:
        return None


def changed_regions(before, after, threshold: float = 0.12) -> list[tuple[float, float, float, float]]:
    """The parts of the screen that changed: [(x, y, w, h) as fractions], biggest first (up to 5)."""
    import numpy as np
    if before is None or after is None or before.shape != after.shape:
        return []
    gx, gy = GRID
    diff = np.abs(before - after) > 24
    cells = diff.reshape(gy, 6, gx, 6).mean(axis=(1, 3)) > threshold
    seen = np.zeros_like(cells)
    regions = []
    for y in range(gy):
        for x in range(gx):
            if not cells[y, x] or seen[y, x]:
                continue
            stack, xs, ys = [(y, x)], [], []
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                xs.append(cx)
                ys.append(cy)
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < gy and 0 <= nx < gx and cells[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            regions.append((len(xs), min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    regions.sort(reverse=True)
    return [(x0 / gx, y0 / gy, (x1 - x0) / gx, (y1 - y0) / gy) for _n, x0, y0, x1, y1 in regions[:5]]


class ScreenIntel:
    def __init__(self, watch, grab: Callable, area: Callable, annotate: Callable[[list], None],
                 private: Callable[[], bool] = lambda: False) -> None:
        """watch: the ScreenWatch (its look). grab(): a screenshot (QImage). area(): where that screenshot is on
        screen (QRectF, logical pixels). annotate([(QRectF, label)]): circle those on screen."""
        self.watch, self.grab, self.area, self.annotate, self.private = watch, grab, area, annotate, private
        self.snapshot = None

    def _to_screen(self, marks: list[dict]) -> list:
        from PySide6.QtCore import QRectF
        a = self.area()
        return [(QRectF(a.x() + m["x"] * a.width(), a.y() + m["y"] * a.height(), m["w"] * a.width(),
                        m["h"] * a.height()), m["label"]) for m in marks]

    def look(self, task: str, question: str, then: Callable[[str, str], None]) -> None:
        """Explain / find the error / read the chart -> then(answer, emotion), and circle what she talks about."""
        extra = f'The user asked: "{question.strip()}".' if question.strip() else ""
        prompt = TASKS.get(task, TASKS["explain"]) + FORMAT.format(extra=extra)

        def answered(reply) -> None:
            if reply is None:
                return then("I won't look while that's on screen - it looks private.", "neutral")
            if getattr(reply, "missing", False):
                return then("I need an AI that can see to do that - Settings, Assistant (Intelligence: Medium).",
                            "confused")
            if getattr(reply, "error", False):
                return then(reply.text or "I couldn't see it right now.", "confused")
            say, marks = parse_answer(reply.text)
            if marks:
                try:
                    self.annotate(self._to_screen(marks))
                except Exception:
                    log.info("intel: couldn't draw the marks", exc_info=True)
            then(say or "Hm. I can't make sense of that one.", reply.emotion or ("serious" if task == "error"
                                                                                 else "neutral"))
        self.watch._look(prompt, answered)
        self.remember()                                     # (also the "before" for "what changed")

    def remember(self) -> bool:
        if self.private():
            return False
        try:
            self.snapshot = thumb(self.grab())
        except Exception:
            self.snapshot = None
        return self.snapshot is not None

    def changes(self) -> tuple[str, int]:
        """(what to say, how many parts changed) - circled on screen."""
        if self.snapshot is None:
            self.remember()
            return "I've taken a picture of your screen. Ask me “what changed” later.", 0
        if self.private():
            return "I won't look while that's on screen - it looks private.", 0
        now = thumb(self.grab())
        regions = changed_regions(self.snapshot, now)
        self.snapshot = now
        if not regions:
            return "Nothing's changed since I last looked.", 0
        marks = [{"label": f"changed {i + 1}", "x": x, "y": y, "w": w, "h": h} for i, (x, y, w, h) in enumerate(regions)]
        try:
            self.annotate(self._to_screen(marks))
        except Exception:
            log.info("intel: couldn't draw the changes", exc_info=True)
        n = len(regions)
        return (f"{n} part{'s' if n > 1 else ''} of your screen changed - I've circled "
                f"{'them' if n > 1 else 'it'}."), n
