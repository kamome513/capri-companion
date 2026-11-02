"""Windows' own OCR, kept running: one PowerShell process that reads screenshots on request.

windows_ocr() (screen_targets.py) starts PowerShell for every read - fine for "click subscribe"
now and then, but about a second each time. Game hype reads the game every second or two, so it
uses this instead: PowerShell starts once, then each read is a fraction of a second. It only
reads image files Capri saved itself; nothing it reads is ever run.
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("capri")

LOOP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
[Console]::Out.WriteLine('"ready"'); [Console]::Out.Flush()
while ($true) {
    $path = [Console]::In.ReadLine()
    if ($path -eq $null) { break }
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $stream.Dispose()
        $text = ($result.Lines | ForEach-Object { $_.Text }) -join ' | '
        [Console]::Out.WriteLine((ConvertTo-Json -InputObject ([string]$text) -Compress))
    } catch { [Console]::Out.WriteLine('""') }
    [Console]::Out.Flush()
}
"""


class PersistentOcr:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._folder = Path(tempfile.mkdtemp(prefix="capri_hype_"))
        self._image = self._folder / "screen.png"

    def _start(self) -> bool:
        if sys.platform != "win32":
            return False
        script = self._folder / "ocr_loop.ps1"
        script.write_text(LOOP_SCRIPT, encoding="utf-8")
        self._proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                       "-File", str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=0x08000000)
        self._lines = queue.Queue()
        threading.Thread(target=self._pump, args=(self._proc, self._lines), daemon=True).start()
        try:
            return self._lines.get(timeout=20) == '"ready"'
        except queue.Empty:
            self.stop()
            return False

    @staticmethod
    def _pump(proc: subprocess.Popen, lines: queue.Queue) -> None:
        for line in proc.stdout:
            lines.put(line.strip())

    def read(self, image) -> str:
        """Text in a QImage ('' if none / not on Windows). Blocking - call from a worker thread."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                if not self._start():
                    return ""
            image.save(str(self._image))
            try:
                self._proc.stdin.write(str(self._image) + "\n")
                self._proc.stdin.flush()
                reply = self._lines.get(timeout=8)
            except (OSError, queue.Empty):
                self.stop()
                return ""
        try:
            text = json.loads(reply)
        except ValueError:
            return ""
        return text if isinstance(text, str) else ""

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
