"""Global shortcuts on a Mac: an AppKit event monitor (macOS asks once for Accessibility / Input Monitoring).

Shortcuts are written as on Windows ("ctrl+alt+shift+c") and work the Mac way: Ctrl is Command, Alt is Option."""

from __future__ import annotations

import logging
from typing import Callable

from .quartz import FLAGS, KEYCODES

log = logging.getLogger("capri")
MODIFIER_MASK = 0x100000 | 0x40000 | 0x20000 | 0x80000         # command, control, shift, option


def parse(combo: str) -> tuple[int, int] | None:
    flags, key = 0, None
    for part in combo.lower().replace(" ", "").split("+"):
        if part in FLAGS:
            flags |= FLAGS[part]
        elif part in KEYCODES:
            key = KEYCODES[part]
        else:
            return None
    return (key, flags) if key is not None and flags else None


class MacHotkeys:
    def __init__(self) -> None:
        self._combos: dict[tuple[int, int], Callable[[], None]] = {}
        self._monitors: list = []

    def register(self, combo: str, callback: Callable[[], None]) -> bool:
        got = parse(combo)
        if got is None:
            return False
        self._combos[got] = callback
        self._start()
        return True

    def clear(self) -> None:
        self._combos.clear()

    def matches(self, keycode: int, flags: int) -> Callable[[], None] | None:
        return self._combos.get((int(keycode), int(flags) & MODIFIER_MASK))

    def _start(self) -> None:
        if self._monitors:
            return
        try:
            from AppKit import NSEvent
            mask = 1 << 10                                            # NSEventMaskKeyDown

            def handle(event):
                fn = self.matches(event.keyCode(), event.modifierFlags())
                if fn is not None:
                    try:
                        fn()
                    except Exception:
                        log.exception("hotkeys: a shortcut failed")
                return event
            self._monitors.append(NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, handle))
            self._monitors.append(NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, handle))
        except Exception:
            log.info("hotkeys: global shortcuts aren't available on this Mac", exc_info=True)

    def stop(self) -> None:
        try:
            from AppKit import NSEvent
            for m in self._monitors:
                if m is not None:
                    NSEvent.removeMonitor_(m)
        except Exception:
            pass
        self._monitors = []
