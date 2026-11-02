"""Notices when you sign in or unlock the PC (including waking it from sleep).

Windows sends WM_WTSSESSION_CHANGE to windows that ask for it with
WTSRegisterSessionNotification - only for *this* user's session. On Linux she listens on D-Bus for
the screen saver turning off (org.freedesktop.ScreenSaver / org.gnome.ScreenSaver ActiveChanged) and
for waking from sleep (logind's PrepareForSleep). Nothing is polled.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

LINUX = sys.platform.startswith("linux")
SUPPORTED = sys.platform == "win32" or LINUX
SCREENSAVERS = (("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver"),
                ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver"),
                ("org.mate.ScreenSaver", "/org/mate/ScreenSaver", "org.mate.ScreenSaver"),
                ("org.cinnamon.ScreenSaver", "/org/cinnamon/ScreenSaver", "org.cinnamon.ScreenSaver"))
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
        if LINUX:
            self.registered = self._linux_listen()
        elif SUPPORTED:
            import ctypes
            try:
                self.registered = bool(ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                    int(self.winId()), NOTIFY_FOR_THIS_SESSION))
            except OSError:
                self.registered = False

    def _linux_listen(self) -> bool:
        try:
            from PySide6.QtDBus import QDBusConnection
        except ImportError:
            return False
        ok = False
        session = QDBusConnection.sessionBus()
        if session.isConnected():
            for service, path, iface in SCREENSAVERS:
                ok |= session.connect(service, path, iface, "ActiveChanged", self, "_screensaver(bool)")
        system = QDBusConnection.systemBus()
        if system.isConnected():
            ok |= system.connect("org.freedesktop.login1", "/org/freedesktop/login1",
                                 "org.freedesktop.login1.Manager", "PrepareForSleep", self, "_sleep(bool)")
        return ok

    @Slot(bool)
    def _screensaver(self, active: bool) -> None:
        if not active:                       # the lock screen went away: you're back
            self.signed_in.emit()

    @Slot(bool)
    def _sleep(self, going: bool) -> None:
        if not going:                        # woke up (the lock screen, if any, comes first - fine either way)
            self.signed_in.emit()

    def stop(self) -> None:
        if LINUX:
            self.registered = False
            return
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
        if sys.platform == "win32" and bytes(name) == b"windows_generic_MSG":
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if self.handle(msg.message, msg.wParam):
                return True, 0
        return False, 0
