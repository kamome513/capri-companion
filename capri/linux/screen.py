"""Reading and touching the screen on Linux: "click subscribe", "highlight the word deadline",
"right click that", "scroll down".

* Seeing: the window is captured through X11 and read with Tesseract (the open-source OCR engine:
  `sudo apt install tesseract-ocr`). Runs on your PC; nothing is uploaded.
* Touching: X11 mouse clicks / drags / scrolls (XTEST). The mouse goes back where it was.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import x11 as x11mod

log = logging.getLogger("capri")


def capture(rect: tuple[int, int, int, int]):
    """A screen rectangle (physical pixels) as an RGB numpy array, or None."""
    import numpy as np
    from Xlib import X
    x = x11mod.shared()
    if x is None:
        return None
    left, top, right, bottom = (int(v) for v in rect)
    screen = x.d.screen()
    left, top = max(0, left), max(0, top)
    right, bottom = min(screen.width_in_pixels, right), min(screen.height_in_pixels, bottom)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None
    with x._lock:
        try:
            image = x.root.get_image(left, top, w, h, X.ZPixmap, 0xFFFFFFFF)
        except Exception as exc:
            log.info("screen: capture failed: %s", exc)
            return None
    data = np.frombuffer(image.data, dtype=np.uint8)
    if data.size < w * h * 4:
        return None
    pixels = data[: w * h * 4].reshape(h, w, 4)
    return np.ascontiguousarray(pixels[..., [2, 1, 0]])          # BGRX -> RGB


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def parse_tsv(tsv: str, origin: tuple[int, int], scale: float) -> list:
    """Tesseract's TSV -> Words (screen coordinates), one `line` number per text line."""
    from ..integrations.screen_targets import Word
    words, lines = [], {}
    rows = tsv.splitlines()
    for row in rows[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        try:
            conf = float(cols[10])
            left, top, width, height = (int(c) for c in cols[6:10])
        except ValueError:
            continue
        if conf < 30:
            continue
        key = (cols[2], cols[3], cols[4])                      # block, paragraph, line
        line = lines.setdefault(key, len(lines))
        x0, y0 = origin[0] + round(left / scale), origin[1] + round(top / scale)
        words.append(Word(cols[11].strip(), line, (x0, y0, x0 + round(width / scale), y0 + round(height / scale))))
    return words


def ocr(rect: tuple[int, int, int, int]) -> list:
    """Words in a screen rectangle, read by Tesseract. [] if it isn't installed."""
    exe = shutil.which("tesseract")
    if exe is None:
        raise OSError("reading the screen needs Tesseract: sudo apt install tesseract-ocr")
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from ..integrations.screen_targets import prepare_for_ocr
    shot = capture(rect)
    if shot is None:
        return []
    grey = prepare_for_ocr(shot)
    if grey.ndim == 3:
        grey = grey[..., 0]
    h, w = grey.shape[:2]
    scale = 2 if max(w, h) * 2 <= 9000 else 1
    img = QImage(np.ascontiguousarray(grey.astype(np.uint8)).tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
    if scale != 1:
        img = img.scaled(w * scale, h * scale, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    folder = Path(tempfile.mkdtemp(prefix="capri_ocr_"))
    png = folder / "screen.png"
    try:
        img.save(str(png))
        run = subprocess.run([exe, str(png), "stdout", "--psm", "11", "tsv"], capture_output=True, text=True,
                             timeout=30, stdin=subprocess.DEVNULL)
        if run.returncode != 0:
            raise OSError(run.stderr.strip()[:200] or "tesseract failed")
        return parse_tsv(run.stdout, (int(rect[0]), int(rect[1])), scale)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _restore_pointer(x, was: tuple[int, int]) -> None:
    from Xlib import X
    from Xlib.ext import xtest
    with x._lock:
        xtest.fake_input(x.d, X.MotionNotify, x=was[0], y=was[1])
        x.d.sync()


def click_at(px: int, py: int, button: int = 1, double: bool = False) -> None:
    x = x11mod.shared()
    if x is None:
        raise OSError("no X11 display")
    was = x.pointer()
    x.click(px, py, button, double)
    time.sleep(0.05)
    _restore_pointer(x, was)


class NoAccessibility:
    """Linux: buttons are found by reading the screen (no accessibility tree), so this has none."""

    def clickables(self, _window) -> list:
        return []


class LinuxHands:
    """What "highlight / double click / right click / scroll" do with the mouse on Linux."""

    def __init__(self, window_rect) -> None:
        self.window_rect = window_rect

    def select(self, target) -> None:
        """A mouse drag across the words."""
        from Xlib import X
        from Xlib.ext import xtest
        x = x11mod.shared()
        if x is None:
            raise OSError("no X11 display")
        left, top, right, bottom = target.rect
        y = (top + bottom) // 2
        was = x.pointer()
        with x._lock:
            xtest.fake_input(x.d, X.MotionNotify, x=left + 1, y=y)
            x.d.sync()
            time.sleep(0.05)
            xtest.fake_input(x.d, X.ButtonPress, 1)
            x.d.sync()
            for step in range(1, 9):
                xtest.fake_input(x.d, X.MotionNotify, x=left + 1 + (right - left - 2) * step // 8, y=y)
                x.d.sync()
                time.sleep(0.015)
            xtest.fake_input(x.d, X.ButtonRelease, 1)
            x.d.sync()
        time.sleep(0.05)
        _restore_pointer(x, was)

    def double(self, target) -> None:
        click_at(*target.center, double=True)

    def right(self, target) -> None:
        click_at(*target.center, button=3)

    def scroll(self, notches: int) -> None:
        from Xlib import X
        from Xlib.ext import xtest
        x = x11mod.shared()
        if x is None:
            raise OSError("no X11 display")
        rect = self.window_rect()
        was = x.pointer()
        if rect:
            with x._lock:
                xtest.fake_input(x.d, X.MotionNotify, x=(rect[0] + rect[2]) // 2, y=(rect[1] + rect[3]) // 2)
                x.d.sync()
        x.scroll(notches > 0, abs(notches))
        if rect:
            _restore_pointer(x, was)
