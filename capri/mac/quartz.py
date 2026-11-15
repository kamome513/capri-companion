"""The macOS system calls Capri uses, through pyobjc (Quartz, AppKit, ApplicationServices). Everything here fails
softly: without pyobjc - or without the permission macOS asks for (Accessibility for keys and windows, Screen
Recording for window titles) - each call just reports that it couldn't.

Coordinates are macOS "global" points: top-left of the main display, y down - the same as Qt's logical pixels."""

from __future__ import annotations

import time

KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12, "w": 13,
    "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
    "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "enter": 36,
    "return": 36, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46,
    ".": 47, "tab": 48, "space": 49, "`": 50, "backspace": 51, "esc": 53, "escape": 53, "delete": 117,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
    "f11": 103, "f12": 111, "left": 123, "right": 124, "down": 125, "up": 126, "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121,
}
# Windows' Ctrl is the Mac's Command (Ctrl+C -> Cmd+C), Alt is Option, the Windows key is Command too.
FLAGS = {"cmd": 0x100000, "command": 0x100000, "ctrl": 0x100000, "control": 0x40000, "win": 0x100000,
         "shift": 0x20000, "alt": 0x80000, "option": 0x80000, "opt": 0x80000, "fn": 0x800000}
MEDIA = {"play_pause": 16, "next": 17, "previous": 18, "volume_up": 0, "volume_down": 1, "mute": 7}


def available() -> bool:
    try:
        import Quartz  # noqa: F401
        return True
    except Exception:
        return False


def parse_combo(combo: str) -> tuple[int, int] | None:
    """"ctrl+shift+m" -> (keycode, flags) - Ctrl read as Command, as Mac apps expect."""
    flags, key = 0, None
    for part in combo.lower().replace(" ", "").split("+"):
        if part in FLAGS:
            flags |= FLAGS[part]
        elif part in KEYCODES:
            key = KEYCODES[part]
        else:
            return None
    return (key, flags) if key is not None else None


def press_combo(combo: str) -> bool:
    import Quartz
    got = parse_combo(combo)
    if got is None:
        return False
    key, flags = got
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, key, down)
        Quartz.CGEventSetFlags(ev, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.01)
    return True


def type_text(text: str) -> int:
    """Types the text (never presses Enter: line breaks become spaces). Returns how many characters went."""
    import Quartz
    text = text.replace("\r", "").replace("\n", " ")
    sent = 0
    for i in range(0, len(text), 16):
        chunk = text[i:i + 16]
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(ev, len(chunk), chunk)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        sent += len(chunk)
        time.sleep(0.008)
    return sent


def media_key(name: str) -> bool:
    """The keyboard's media keys (play / pause, next, volume...), as the Mac's own keys send them."""
    from AppKit import NSEvent
    import Quartz
    key = MEDIA.get(name)
    if key is None:
        return False
    for down in (True, False):
        state = 0xA if down else 0xB
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14, (0, 0), state << 8, 0, 0, None, 8, (key << 16) | (state << 8), -1)
        Quartz.CGEventPost(0, ev.CGEvent())
    return True


# -- windows ------------------------------------------------------------------------------------------------------
def windows() -> list[dict]:
    """Normal app windows on screen, front to back: id, pid, owner (app name), title, rect (x0, y0, x1, y1)."""
    import Quartz
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    out = []
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if int(w.get("kCGWindowLayer", 1)) != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        x, y, wd, ht = (int(b.get(k, 0)) for k in ("X", "Y", "Width", "Height"))
        if wd < 40 or ht < 40:
            continue
        out.append({"id": int(w.get("kCGWindowNumber", 0)), "pid": int(w.get("kCGWindowOwnerPID", 0)),
                    "owner": str(w.get("kCGWindowOwnerName") or ""), "title": str(w.get("kCGWindowName") or ""),
                    "rect": (x, y, x + wd, y + ht)})
    return out


def frontmost_pid() -> int:
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return int(app.processIdentifier()) if app is not None else 0


def activate(pid: int) -> bool:
    from AppKit import NSRunningApplication
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        return False
    return bool(app.activateWithOptions_(1 << 1))           # NSApplicationActivateIgnoringOtherApps


def running_app(pid: int):
    from AppKit import NSRunningApplication
    return NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)


def regular_apps() -> list:
    """The apps you can see (Dock apps), not background helpers."""
    from AppKit import NSWorkspace
    return [a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.activationPolicy() == 0]


def _ax_windows(pid: int) -> list:
    from ApplicationServices import AXUIElementCopyAttributeValue, AXUIElementCreateApplication
    err, wins = AXUIElementCopyAttributeValue(AXUIElementCreateApplication(pid), "AXWindows", None)
    return list(wins or []) if err == 0 else []


def _ax_rect(win) -> tuple[int, int, int, int] | None:
    from ApplicationServices import AXUIElementCopyAttributeValue, AXValueGetValue
    e1, pos = AXUIElementCopyAttributeValue(win, "AXPosition", None)
    e2, size = AXUIElementCopyAttributeValue(win, "AXSize", None)
    if e1 or e2:
        return None
    ok1, p = AXValueGetValue(pos, 1, None)                     # kAXValueCGPointType
    ok2, s = AXValueGetValue(size, 2, None)                    # kAXValueCGSizeType
    if not (ok1 and ok2):
        return None
    return int(p.x), int(p.y), int(p.x + s.width), int(p.y + s.height)


def ax_window_for(pid: int, rect: tuple[int, int, int, int] | None):
    """The Accessibility handle of one of an app's windows (the one at `rect`, else its first)."""
    wins = _ax_windows(pid)
    if not wins:
        return None
    if rect is not None:
        for w in wins:
            r = _ax_rect(w)
            if r is not None and all(abs(a - b) <= 4 for a, b in zip(r, rect)):
                return w
    return wins[0]


def ax_set_minimized(win, on: bool) -> bool:
    from ApplicationServices import AXUIElementSetAttributeValue
    return AXUIElementSetAttributeValue(win, "AXMinimized", bool(on)) == 0


def ax_press_close(win) -> bool:
    from ApplicationServices import AXUIElementCopyAttributeValue, AXUIElementPerformAction
    err, button = AXUIElementCopyAttributeValue(win, "AXCloseButton", None)
    return err == 0 and button is not None and AXUIElementPerformAction(button, "AXPress") == 0


def ax_raise(win) -> bool:
    from ApplicationServices import AXUIElementPerformAction
    return AXUIElementPerformAction(win, "AXRaise") == 0


def idle_seconds() -> float:
    """Seconds since you last touched the keyboard or mouse."""
    import Quartz
    return float(Quartz.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF))   # combined session, any event


def trusted() -> bool:
    """Has Capri been allowed to control the computer (System Settings > Privacy & Security > Accessibility)?"""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


# -- her own windows: the Mac way ---------------------------------------------------------------------------------
def float_everywhere(widget) -> None:
    """One of her windows: on every Space and over full-screen apps, no shadow, never in the window cycle."""
    try:
        import objc
        from AppKit import NSFloatingWindowLevel
        view = objc.objc_object(c_void_p=int(widget.winId()))
        win = view.window()
        if win is None:
            return
        # canJoinAllSpaces | stationary | ignoresCycle | fullScreenAuxiliary
        win.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 6) | (1 << 8))
        win.setHasShadow_(False)
        win.setLevel_(NSFloatingWindowLevel + 1)
    except Exception:
        pass


def accessory_app() -> None:
    """No Dock icon: she lives in the menu bar (and on your desktop)."""
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(1)    # NSApplicationActivationPolicyAccessory
    except Exception:
        pass
