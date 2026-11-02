"""Pressing an app's own on-screen buttons through Windows UI Automation - the same
interface screen readers use. Used for Discord's Mute / Deafen buttons,
Spotify's Play buttons, and "click subscribe" / "click that" (screen_targets.py).

Why not keyboard shortcuts: Discord can react to a shortcut twice (once as a
global keybind, once in its window), which turns "deafen" into deafen-undeafen.
A button press happens exactly once, needs no focus change, and the button
also says whether it's on, so Capri can report your real state.

Read-only apart from pressing the button asked for. Windows only.
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Protocol

TREE_DESCENDANTS = 4
NAME_PROPERTY = 30005
CONTROL_TYPE_PROPERTY = 30003
BUTTON_CONTROL = 50000
EDIT_CONTROL = 50004
RECT_PROPERTY = 30001
INVOKE_PATTERN = 10000
TOGGLE_PATTERN = 10015
SELECTION_ITEM_PATTERN = 10010
TOGGLE_ON = 1
IS_OFFSCREEN_PROPERTY = 30022
TEXT_PATTERN = 10014
IS_TEXT_PATTERN_AVAILABLE = 30040
# what "click X" can click: button, check box, combo box, hyperlink, list item, menu item, radio button,
# tab item, tree item, split button
CLICKABLE_TYPES = (50000, 50002, 50003, 50005, 50007, 50011, 50013, 50019, 50024, 50031)
TAB_ITEM = 50019
# pressed through their own "press" (no mouse needed): button, check box, hyperlink, menu item, radio, split button.
# Tabs are switched by selecting them; list / tree items (Spotify's playlists) and combo boxes get a real left
# click - their "press" can open a menu or do nothing in some apps (a browser tab's opened its menu).
PRESSABLE = (50000, 50002, 50005, 50011, 50013, 50031)


class Button(Protocol):
    name: str

    def toggled(self) -> bool | None: ...
    def press(self) -> None: ...


class UI(Protocol):
    def buttons(self, hwnd: int, names: set[str] | None = None) -> list[Button]: ...


class _Button:
    def __init__(self, element, name: str, rect: tuple[int, int, int, int] | None = None, kind: int = 0) -> None:
        self._el = element
        self.name = name
        self.rect = rect               # (left, top, right, bottom) in screen pixels, when asked for
        self.kind = kind               # UI Automation control type (0 = unknown)

    def focus(self) -> None:
        self._el.SetFocus()

    def toggled(self) -> bool | None:
        """On/off for switch-style buttons (Discord's mic: on = muted). None = not a switch."""
        from comtypes.gen import UIAutomationClient as UIA
        try:
            unknown = self._el.GetCurrentPattern(TOGGLE_PATTERN)
            if unknown:
                return unknown.QueryInterface(UIA.IUIAutomationTogglePattern).CurrentToggleState == TOGGLE_ON
        except Exception:
            pass
        return None

    def press(self) -> None:
        """Its own action. Raises OSError when it should get a real mouse click instead."""
        from comtypes.gen import UIAutomationClient as UIA
        if self.kind == TAB_ITEM:                      # a tab: select it - never its "press"
            unknown = self._el.GetCurrentPattern(SELECTION_ITEM_PATTERN)
            if unknown:
                unknown.QueryInterface(UIA.IUIAutomationSelectionItemPattern).Select()
                return
            raise OSError(f"the {self.name} tab needs a click")
        if self.kind and self.kind not in PRESSABLE:
            raise OSError(f"{self.name} needs a real click")
        unknown = self._el.GetCurrentPattern(INVOKE_PATTERN)
        if unknown:
            unknown.QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
            return
        unknown = self._el.GetCurrentPattern(TOGGLE_PATTERN)
        if unknown:
            unknown.QueryInterface(UIA.IUIAutomationTogglePattern).Toggle()
            return
        unknown = self._el.GetCurrentPattern(SELECTION_ITEM_PATTERN)     # e.g. File Explorer's sidebar
        if unknown:
            unknown.QueryInterface(UIA.IUIAutomationSelectionItemPattern).Select()
            return
        raise OSError(f"the {self.name} button can't be pressed")


class TextHit:
    """Words found in an app's own text (a web page, a document, a text box) - selected by the
    app itself, exactly, like you dragged over them."""

    def __init__(self, text_range, name: str, rect: tuple[int, int, int, int]) -> None:
        self._range, self.name, self.rect = text_range, name, rect

    def select_text(self) -> None:
        self._range.Select()

    def press(self) -> None:                      # "click" on found text = select it
        self.select_text()


def _range_rect(text_range) -> tuple[int, int, int, int] | None:
    """The union of a text range's on-screen rectangles (empty = scrolled out of view)."""
    try:
        flat = list(text_range.GetBoundingRectangles() or ())
    except Exception:
        return None
    boxes = [flat[i:i + 4] for i in range(0, len(flat) - 3, 4) if flat[i + 2] > 0 and flat[i + 3] > 0]
    if not boxes:
        return None
    return (int(min(b[0] for b in boxes)), int(min(b[1] for b in boxes)),
            int(max(b[0] + b[2] for b in boxes)), int(max(b[1] + b[3] for b in boxes)))


class WindowsUI:
    """The real thing (comtypes + UIAutomationCore)."""

    def _automation(self):
        if sys.platform != "win32":
            raise OSError("UI Automation is only available on Windows")
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()          # per thread; fine to repeat
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA
        return comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)

    def buttons(self, hwnd: int, names: set[str] | None = None, control: int = BUTTON_CONTROL,
                with_rects: bool = False) -> list[Button]:
        """Buttons (or other controls) in the window, in screen-reader order. With `names`, only
        those (exact names, any control type)."""
        auto = self._automation()
        root = auto.ElementFromHandle(hwnd)
        if names:
            conditions = [auto.CreatePropertyCondition(NAME_PROPERTY, n) for n in sorted(names)]
            condition = conditions[0]
            for c in conditions[1:]:
                condition = auto.CreateOrCondition(condition, c)
        else:
            condition = auto.CreatePropertyCondition(CONTROL_TYPE_PROPERTY, control)
        cache = auto.CreateCacheRequest()
        cache.AddProperty(NAME_PROPERTY)
        if with_rects:
            cache.AddProperty(RECT_PROPERTY)
        found = root.FindAllBuildCache(TREE_DESCENDANTS, condition, cache)
        out = []
        for i in range(found.Length if found else 0):
            element = found.GetElement(i)
            rect = None
            if with_rects:
                r = element.CachedBoundingRectangle
                rect = (r.left, r.top, r.right, r.bottom)
            out.append(_Button(element, element.CachedName or "", rect, 0 if names else control))
        return out

    def edits(self, hwnd: int) -> list[Button]:
        """Text boxes (e.g. Spotify's search box)."""
        return self.buttons(hwnd, control=EDIT_CONTROL)

    def clickables(self, hwnd: int) -> list[Button]:
        """Everything clickable that's on screen in the window: buttons, links, tabs, menu items,
        list items, check boxes... with their names and screen rectangles."""
        auto = self._automation()
        root = auto.ElementFromHandle(hwnd)
        types = [auto.CreatePropertyCondition(CONTROL_TYPE_PROPERTY, t) for t in CLICKABLE_TYPES]
        any_type = types[0]
        for c in types[1:]:
            any_type = auto.CreateOrCondition(any_type, c)
        visible = auto.CreatePropertyCondition(IS_OFFSCREEN_PROPERTY, False)
        cache = auto.CreateCacheRequest()
        cache.AddProperty(NAME_PROPERTY)
        cache.AddProperty(RECT_PROPERTY)
        cache.AddProperty(CONTROL_TYPE_PROPERTY)
        found = root.FindAllBuildCache(TREE_DESCENDANTS, auto.CreateAndCondition(any_type, visible), cache)
        out = []
        for i in range(found.Length if found else 0):
            element = found.GetElement(i)
            r = element.CachedBoundingRectangle
            if r.right - r.left > 2 and r.bottom - r.top > 2:
                out.append(_Button(element, element.CachedName or "", (r.left, r.top, r.right, r.bottom),
                                   element.CachedControlType))
        return out

    def find_text(self, hwnd: int, text: str) -> TextHit | None:
        """Find words in the window's own text (any word on a web page, in a document or a text
        box), case-insensitive. Scrolls it into view if it's further down. None = not there, or
        the app doesn't share its text (then she reads the screen instead)."""
        from comtypes.gen import UIAutomationClient as UIA
        auto = self._automation()
        root = auto.ElementFromHandle(hwnd)
        found = root.FindAll(TREE_DESCENDANTS, auto.CreatePropertyCondition(IS_TEXT_PATTERN_AVAILABLE, True))
        elements = [root] + [found.GetElement(i) for i in range(min(found.Length if found else 0, 60))]
        for element in elements:
            try:
                unknown = element.GetCurrentPattern(TEXT_PATTERN)
                if not unknown:
                    continue
                pattern = unknown.QueryInterface(UIA.IUIAutomationTextPattern)
                hit = pattern.DocumentRange.FindText(text, False, True)      # forwards, ignore case
            except Exception:
                continue
            if not hit:
                continue
            rect = _range_rect(hit)
            if rect is None:                                                  # further down: scroll to it
                try:
                    hit.ScrollIntoView(True)
                    time.sleep(0.25)
                except Exception:
                    pass
                rect = _range_rect(hit)
            if rect is not None:
                return TextHit(hit, text, rect)
        return None

    def element_at(self, x: int, y: int) -> Button | None:
        """The clickable thing at a screen point (physical pixels) - walking up from whatever is
        exactly there (a button's label, an icon) to the button / link it belongs to."""
        from comtypes.gen import UIAutomationClient as UIA
        auto = self._automation()
        element = auto.ElementFromPoint(UIA.tagPOINT(int(x), int(y)))
        walker = auto.ControlViewWalker
        for _ in range(6):
            if element is None:
                return None
            if element.CurrentControlType in CLICKABLE_TYPES:
                r = element.CurrentBoundingRectangle
                return _Button(element, element.CurrentName or "", (r.left, r.top, r.right, r.bottom),
                               element.CurrentControlType)
            element = walker.GetParentElement(element)
        return None


def find_buttons(ui: UI, windows: list[int], names: set[str] | None, accept: Callable[[list[Button]], bool],
                 timeout: float, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> list[Button]:
    """Look until `accept(buttons)` (apps built on Chromium switch their accessibility on
    when first asked, so the first look can come back empty)."""
    deadline = clock() + timeout
    while True:
        for hwnd in windows:
            try:
                found = ui.buttons(hwnd, names)
            except Exception:
                continue
            if accept(found):
                return found
        if clock() >= deadline:
            return []
        sleep(0.3)
