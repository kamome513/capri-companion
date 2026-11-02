"""Notices when you sign in to Windows or unlock the PC (including waking it from sleep).

Windows sends WM_WTSSESSION_CHANGE to windows that ask for it with
WTSRegisterSessionNotification - only for *this* user's session. Nothing
is polled. Elsewhere it does nothing.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

SUPPORTED = sys.platform == "win32"
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOGON = 0x5
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0


class SessionWatcher(QWidget):
    """An invisible native window; emits ``signed_in`` on sign-in / unlock."""

    signed_in = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.registered = False
        if SUPPORTED:
            import ctypes
            try:
                self.registered = bool(ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                    int(self.winId()), NOTIFY_FOR_THIS_SESSION))
            except OSError:
                self.registered = False

    def stop(self) -> None:
        if self.registered:
            import ctypes
            ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(int(self.winId()))
            self.registered = False

    def handle(self, message: int, wparam: int) -> bool:
        if message == WM_WTSSESSION_CHANGE and wparam in (WTS_SESSION_LOGON, WTS_SESSION_UNLOCK):
            self.signed_in.emit()
            return True
        return False

    def nativeEvent(self, event_type, message):
        name = event_type.data() if hasattr(event_type, "data") else bytes(event_type)
        if SUPPORTED and bytes(name) == b"windows_generic_MSG":
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if self.handle(msg.message, msg.wParam):
                return True, 0
        return False, 0
