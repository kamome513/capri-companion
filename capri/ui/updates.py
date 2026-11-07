"""The update check, on a timer and on request (menu, Settings, "check for updates").

All network work happens on a worker thread; results come back to the UI thread through a signal.
See updater.py for what's checked and how the install works.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import __version__, updater
from ..net import friendly
from ..states import State

log = logging.getLogger("capri")

FIRST_CHECK_MS = 20_000          # soon after she starts (it used to be 90 s: a quick restart missed it)
IDLE_RETRY_MS = 60_000           # busy (talking, in a game): try installing again in a minute


class UpdateManager(QObject):
    _done = Signal(object, object)            # (callback, result) - back on the UI thread
    changed = Signal(str)                     # what to show in Settings / the menu

    def __init__(self, settings, controller, assistant=None, tray=None,
                 check: Callable = updater.check, download: Callable = updater.download,
                 ready: Callable = updater.ready, install: Callable = updater.install,
                 frozen: Callable[[], bool] = updater.frozen, open_page: Callable[[str], None] | None = None,
                 quit_app: Callable[[], None] | None = None, confirm: Callable[[str], bool] | None = None,
                 tries: Callable = updater.tries, idle: Callable[[], bool] = lambda: True) -> None:
        super().__init__()
        self.settings, self.controller, self.assistant, self.tray = settings, controller, assistant, tray
        self._check, self._download, self._ready, self._install = check, download, ready, install
        self._tries = tries
        self._idle = idle
        self._installing = False
        self._frozen = frozen
        self._open_page = open_page or _open_url
        self._quit = quit_app or QApplication.quit
        self._confirm = confirm or _ask_yes_no
        self._done.connect(lambda callback, result: callback(result))
        self.found: updater.Update | None = None
        self.busy = False
        self.status = f"You have Capri {__version__}."
        self.timer = QTimer(self)
        self.timer.setInterval(updater.CHECK_EVERY * 1000)
        self.timer.timeout.connect(lambda: self.check_now(quiet=True))

    def start(self) -> None:
        QTimer.singleShot(FIRST_CHECK_MS, lambda: self.check_now(quiet=True))
        self.timer.start()

    # -- worker thread plumbing ------------------------------------------------------------------
    def _background(self, work: Callable, callback: Callable) -> None:
        def run() -> None:
            try:
                result = work()
            except Exception as exc:              # network down, GitHub busy...: never crash her
                result = exc
            self._done.emit(callback, result)
        threading.Thread(target=run, daemon=True, name="capri-update").start()

    def _say(self, text: str, error: bool = False) -> None:
        self.status = text
        self.changed.emit(text)
        self.controller.log("Update", text[:60])
        if self.assistant is not None:
            self.assistant.show_result(State.ERROR if error else State.SUCCESS, text, speak=False)

    # -- checking ----------------------------------------------------------------------------------
    def check_now(self, quiet: bool = False) -> None:
        """quiet=True: the timer (only speaks up if there's something new)."""
        if self.busy:
            return
        if quiet and not getattr(self.settings, "auto_update", True):
            return
        ready = self._ready() if self._frozen() else None
        if ready is not None:                        # already downloaded and checked
            if self.stuck():
                return self._stuck(ready[0])
            if getattr(self.settings, "auto_update", True) and self.install_when_idle():
                return
            return self._offer(ready[0])
        self.busy = True
        if not quiet:
            self._say("Checking GitHub for a newer me...")
        self._background(self._check, lambda result: self._checked(result, quiet))

    def _checked(self, result, quiet: bool) -> None:
        self.busy = False
        if isinstance(result, Exception):
            log.info("update check failed: %s", result)
            if not quiet:
                self._say(f"Couldn't check GitHub for updates: {friendly(result)}.", error=True)
            return
        if result is None:
            if not quiet:
                self._say(f"I'm up to date - Capri {__version__} is the newest.")
            else:
                self.status = f"Capri {__version__} is the newest."
                self.changed.emit(self.status)
            return
        self.found = result
        if not self._frozen() or not result.url:
            self._say(f"Capri {result.version} is out! Download it from my GitHub page "
                      f"(right-click me, Update to {result.version}).")
            return
        if not getattr(self.settings, "auto_update", True) and quiet:
            self._say(f"Capri {result.version} is out. Right-click me, Update to {result.version}.")
            return
        self.busy = True
        self.controller.log("Update", f"downloading Capri {result.version}")
        self._background(lambda: self._download(result), self._downloaded)

    def _downloaded(self, result) -> None:
        self.busy = False
        if isinstance(result, Exception):
            log.warning("update download failed: %s", result)
            self._say(f"Couldn't download the update ({friendly(result)[:70]}). I'll try again later.", error=True)
            return
        if getattr(self.settings, "auto_update", True) and self.install_when_idle():
            return                                   # (2.3.7) right away, not only the next time she starts
        self._offer(self.found.version if self.found else "")

    def install_when_idle(self) -> bool:
        """Install the downloaded update now - as soon as she isn't busy (talking, you're in a game, she's
        playing for you); checked again every minute until then. False if there's nothing to install."""
        if self._installing:
            return True
        ready = self._ready() if self._frozen() else None
        if ready is None:
            return False
        try:
            idle = bool(self._idle())
        except Exception:
            idle = True
        if not idle:
            log.info("update: Capri %s is ready - waiting until I'm not busy", ready[0])
            QTimer.singleShot(IDLE_RETRY_MS, self.install_when_idle)
            return True
        version, installer = ready
        self._installing = True
        self._say(f"Updating myself to Capri {version}. Back in a few seconds!")
        log.info("update: installing Capri %s now", version)

        def go() -> None:
            if not self._install(installer):
                self._installing = False
                self._say("Couldn't start the update. I'll try again when I next start.", error=True)
                return
            self._quit()
        QTimer.singleShot(self.INSTALL_DELAY_MS, go)  # so you see (and hear) why she's going
        return True

    INSTALL_DELAY_MS = 2500

    def stuck(self) -> bool:
        """The waiting update already didn't take twice at start-up (so she won't keep trying by herself)."""
        return self._tries()[0] >= updater.MAX_TRIES

    def _stuck(self, version: str) -> None:
        self._say(f"Capri {version} didn't install by itself. Right-click me, Restart to update - or get it "
                  f"from my GitHub page.", error=True)

    def _offer(self, version: str) -> None:
        if getattr(self.settings, "auto_update", True):
            self._say(f"Capri {version} is downloaded. Right-click me, Restart to update - or it installs "
                      f"next time I start.")
        else:
            self._say(f"Capri {version} is downloaded. Right-click me, Restart to update, whenever you like.")
        if self.tray is not None:
            try:
                from PySide6.QtWidgets import QSystemTrayIcon
                self.tray.showMessage("Capri update ready", f"Capri {version} is ready. Right-click her and pick "
                                      "Restart to update.", QSystemTrayIcon.MessageIcon.Information, 6000)
            except Exception:
                pass

    # -- installing -------------------------------------------------------------------------------
    def label(self) -> str:
        """The menu item's words."""
        ready = self._ready() if self._frozen() else None
        if ready is not None:
            return f"Restart to update (Capri {ready[0]})"
        if self.found is not None:
            return f"Update to Capri {self.found.version}..."
        return "Check for updates"

    def menu_clicked(self) -> None:
        ready = self._ready() if self._frozen() else None
        if ready is not None:
            return self.update_now()
        if self.found is not None and (not self._frozen() or not self.found.url):
            return self._open_page(self.found.page)
        self.check_now()

    def update_now(self) -> bool:
        ready = self._ready() if self._frozen() else None
        if ready is None:
            self.check_now()
            return False
        version, installer = ready
        if not self._confirm(f"Restart Capri and update to {version} now? She'll close, update and start "
                             f"again (about half a minute)."):
            return False
        if not self._install(installer):
            self._say("Couldn't start the update. I'll try again when I next start.", error=True)
            return False
        log.info("update: installing Capri %s, quitting", version)
        self._quit()
        return True


def apply_waiting_update(settings, ready: Callable = updater.ready, install: Callable = updater.install,
                         frozen: Callable[[], bool] = updater.frozen, tries: Callable = updater.tries,
                         now: Callable[[], float] = time.time,
                         installing: Callable[[], bool] = updater.installer_running) -> bool:
    """At start-up: a downloaded update is waiting -> start its installer (Capri then exits).
    True = Capri should exit now (the installer is running and starts her again).

    Never a loop: if the same update already didn't take twice, she starts normally and tells you
    (UpdateManager.stuck); if one was started moments ago (you opened her again while it runs),
    she leaves it to finish."""
    if not frozen() or not getattr(settings, "auto_update", True):
        return False
    waiting = ready()
    if waiting is None:
        return False
    count, started = tries()
    if started and 0 <= now() - started < updater.INSTALLING_SECONDS and installing():
        log.info("update: Capri %s is being installed right now - leaving it to finish", waiting[0])
        return True
    if count >= updater.MAX_TRIES:
        log.warning("update: Capri %s didn't install after %d tries - starting normally", waiting[0], count)
        return False
    log.info("update: installing waiting Capri %s at start-up (try %d)", waiting[0], count + 1)
    return install(waiting[1])


def _open_url(url: str) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(url))


def _ask_yes_no(question: str) -> bool:
    return QMessageBox.question(None, "Capri", question) == QMessageBox.StandardButton.Yes
