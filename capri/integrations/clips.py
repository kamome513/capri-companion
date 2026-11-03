"""Clips: "Hey Capri, clip that" saves the last 30 seconds (up to two minutes) of your screen and sound.

How: while it's on, ffmpeg records your main screen into short 2-second pieces in a temp folder, and only
the last couple of minutes are kept (older pieces are written over). "Clip that" waits for the piece being
recorded to finish, then joins the newest pieces into one video in your clips folder (Videos/Capri Clips).
Nothing is uploaded anywhere.

* Windows: ffmpeg is downloaded once (~31 MB, from the imageio-ffmpeg package on PyPI, checked against its
  published SHA-256) when you turn clips on. Screen: Windows' Desktop Duplication (works over full-screen
  games), else GDI. Sound: what your speakers / headphones play (WASAPI loopback, through the soundcard
  package), piped into ffmpeg.
* Linux: your own ffmpeg (sudo apt install ffmpeg). Screen: X11 (on Wayland only X11 apps show). Sound:
  PulseAudio / PipeWire's monitor of your speakers.
* Video: your graphics card's encoder if it has one (NVIDIA / AMD / Intel), else x264 (CPU).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger("capri")

SEGMENT = 2                       # seconds per piece
MAX_LENGTH = 120                  # the most "clip that" can save
LENGTHS = (15, 30, 60, 90, 120)
FPS = (30, 60)
RESOLUTIONS = {"auto": 1080, "720p": 720, "1080p": 1080, "full": 0}     # max height; 0 = as your screen is
FFMPEG_WHEEL = ("https://files.pythonhosted.org/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/"
                "imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl",
                "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a",
                "imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe", 31246824)
HW_ENCODERS = ("h264_nvenc", "h264_amf", "h264_qsv")
AUDIO_RATE, AUDIO_CHANNELS = 48000, 2
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def tools_dir() -> Path:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    return Path(base or tempfile.gettempdir()) / "tools"


def default_folder() -> Path:
    from PySide6.QtCore import QStandardPaths
    videos = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or str(Path.home())
    return Path(videos) / "Capri Clips"


def find_ffmpeg(platform: str = sys.platform, which: Callable[[str], str | None] = shutil.which,
                tools: Path | None = None) -> str | None:
    """Capri's own ffmpeg (Windows, downloaded), else one on your PATH."""
    if platform == "win32":
        own = (tools or tools_dir()) / "ffmpeg.exe"
        if own.exists():
            return str(own)
    return which("ffmpeg")


def download_ffmpeg(progress: Callable[[int], None] = lambda pct: None, opener=urllib.request.urlopen,
                    tools: Path | None = None) -> str:
    """Windows: fetch ffmpeg once (the imageio-ffmpeg wheel from PyPI), check it, unpack ffmpeg.exe."""
    url, sha, member, size = FFMPEG_WHEEL
    folder = tools or tools_dir()
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / "ffmpeg-download.part"
    digest, done, shown = hashlib.sha256(), 0, -1
    req = urllib.request.Request(url, headers={"User-Agent": "Capri"})
    try:
        with opener(req, timeout=60) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or size)
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                pct = min(100, done * 100 // max(1, total))
                if pct != shown:
                    shown = pct
                    progress(pct)
        if digest.hexdigest() != sha:
            raise OSError("the download didn't match (damaged?) - try again")
        target = folder / "ffmpeg.exe"
        with zipfile.ZipFile(part) as wheel, wheel.open(member) as src, open(target.with_suffix(".part"), "wb") as out:
            shutil.copyfileobj(src, out, 1 << 20)
        target.with_suffix(".part").replace(target)
        return str(target)
    finally:
        try:
            part.unlink()
        except OSError:
            pass


@dataclass
class Screen:
    """The screen to record, in real (device) pixels."""
    x: int
    y: int
    width: int
    height: int


def primary_screen() -> Screen:
    from PySide6.QtGui import QGuiApplication
    s = QGuiApplication.primaryScreen()
    g, r = s.geometry(), s.devicePixelRatio()
    return Screen(round(g.x() * r), round(g.y() * r), round(g.width() * r), round(g.height() * r))


def scale_filter(max_height: int, height: int) -> str:
    """Even sizes for the encoder; smaller if the screen is taller than the chosen resolution."""
    if max_height and height > max_height:
        return f"scale=-2:{max_height}"
    return "scale=trunc(iw/2)*2:trunc(ih/2)*2"


def capture_args(method: str, screen: Screen, fps: int, display: str = "") -> list[str]:
    """ffmpeg's input for your screen."""
    if method == "ddagrab":                      # Windows Desktop Duplication: also full-screen games
        return ["-f", "lavfi", "-i", f"ddagrab=output_idx=0:framerate={fps}:draw_mouse=1"]
    if method == "gdigrab":
        return ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "1", "-offset_x", str(screen.x),
                "-offset_y", str(screen.y), "-video_size", f"{screen.width}x{screen.height}", "-i", "desktop"]
    if method == "x11grab":
        return ["-f", "x11grab", "-framerate", str(fps), "-draw_mouse", "1",
                "-video_size", f"{screen.width}x{screen.height}", "-i", f"{display or ':0'}+{screen.x},{screen.y}"]
    raise ValueError(method)


def encoder_args(encoder: str, fps: int) -> list[str]:
    gop = ["-g", str(fps * SEGMENT), "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT})"]
    if encoder == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-crf", "24",
                "-pix_fmt", "yuv420p"] + gop
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-pix_fmt", "yuv420p"] + gop
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24",
                "-pix_fmt", "yuv420p"] + gop
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "24", "-pix_fmt", "nv12"] + gop
    raise ValueError(encoder)


def record_command(ffmpeg: str, method: str, screen: Screen, fps: int, max_height: int, encoder: str,
                   folder: Path, audio: str, display: str = "") -> list[str]:
    """The whole ffmpeg command: screen (+ sound) -> 2 s pieces, written over in a ring.
    audio: "pipe" (raw PCM on stdin - Windows), "pulse" (Linux), or "" (no sound)."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats", "-y"]
    cmd += capture_args(method, screen, fps, display)
    if audio == "pipe":
        cmd += ["-f", "s16le", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS), "-i", "pipe:0"]
    elif audio == "pulse":
        cmd += ["-f", "pulse", "-i", "@DEFAULT_MONITOR@"]
    vf = scale_filter(max_height, screen.height)
    if method == "ddagrab":
        vf = "hwdownload,format=bgra," + vf
    cmd += ["-vf", vf, "-map", "0:v"]
    if audio:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "160k"]
    cmd += encoder_args(encoder, fps)
    wrap = math.ceil(MAX_LENGTH / SEGMENT) + 4
    cmd += ["-f", "segment", "-segment_time", str(SEGMENT), "-segment_wrap", str(wrap), "-reset_timestamps", "1",
            "-segment_format", "mpegts", "-segment_list", str(folder / "pieces.csv"), "-segment_list_type", "csv",
            str(folder / "piece%03d.ts")]
    return cmd


def finished_pieces(csv_text: str) -> list[tuple[str, float]]:
    """The pieces ffmpeg has finished, oldest first: (file name, length in seconds)."""
    out = []
    for line in csv_text.splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 3:
            try:
                out.append((parts[0].strip('"'), float(parts[2]) - float(parts[1])))
            except ValueError:
                continue
    return out


def newest(pieces: list[tuple[str, float]], seconds: float) -> tuple[list[str], float]:
    """The newest pieces that add up to at least `seconds` (each name once - the ring reuses names), and how
    much longer than `seconds` they are together (to trim off the start)."""
    chosen, total, seen = [], 0.0, set()
    for name, length in reversed(pieces):
        if name in seen:
            break
        seen.add(name)
        chosen.append(name)
        total += length
        if total >= seconds:
            break
    chosen.reverse()
    return chosen, max(0.0, total - seconds)


def clip_name(now: float | None = None) -> str:
    return time.strftime("Capri clip %Y-%m-%d %H-%M-%S.mp4", time.localtime(now))


class LoopbackFeed:
    """Windows: what your speakers play, as raw 16-bit PCM into ffmpeg's stdin. Silence is filled in by the
    clock (Windows sends nothing while nothing plays), so the sound stays in step with the picture."""

    def __init__(self, sink, source: Callable[[], object] | None = None, clock: Callable[[], float] = time.monotonic):
        self.sink, self.clock = sink, clock
        self.source = source or self._soundcard
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="capri-clip-sound")

    @staticmethod
    def _soundcard():
        import soundcard as sc
        speaker = sc.default_speaker()
        mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        return mic.recorder(samplerate=AUDIO_RATE, channels=AUDIO_CHANNELS, blocksize=AUDIO_RATE // 50)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import numpy as np
        try:
            recorder = self.source()
            enter = getattr(recorder, "__enter__", None)
            rec = enter() if enter else recorder
        except Exception as exc:
            log.info("clips: no speaker sound (%s) - recording silence", exc)
            rec = None
        start, sent = self.clock(), 0
        try:
            while not self._stop.is_set():
                if rec is not None:
                    try:
                        data = rec.record(numframes=AUDIO_RATE // 50)
                    except Exception as exc:
                        log.info("clips: speaker sound stopped (%s)", exc)
                        rec = None
                        continue
                    frames = np.asarray(data, dtype=np.float32).reshape(-1, AUDIO_CHANNELS) if len(data) else \
                        np.zeros((0, AUDIO_CHANNELS), np.float32)
                else:
                    time.sleep(0.02)
                    frames = np.zeros((0, AUDIO_CHANNELS), np.float32)
                due = int((self.clock() - start) * AUDIO_RATE)
                if sent + len(frames) < due - AUDIO_RATE // 10:               # gap: fill it with silence
                    frames = np.vstack([np.zeros((due - sent - len(frames), AUDIO_CHANNELS), np.float32), frames])
                if len(frames):
                    pcm = (np.clip(frames, -1, 1) * 32767).astype("<i2").tobytes()
                    self.sink.write(pcm)
                    self.sink.flush()
                    sent += len(frames)
        except (OSError, ValueError):
            pass                                                              # ffmpeg stopped
        finally:
            exit_ = getattr(rec, "__exit__", None) if rec is not None else None
            if exit_:
                try:
                    exit_(None, None, None)
                except Exception:
                    pass


class ClipRecorder:
    """Keeps the last two minutes recording while it should, and saves clips on request."""

    def __init__(self, settings, ffmpeg: Callable[[], str | None] = find_ffmpeg,
                 popen: Callable = subprocess.Popen, run: Callable = subprocess.run,
                 screen: Callable[[], Screen] = primary_screen, platform: str = sys.platform,
                 workdir: Path | None = None, feed: Callable = LoopbackFeed) -> None:
        self.settings, self.ffmpeg, self.popen, self.run = settings, ffmpeg, popen, run
        self.screen, self.platform, self.feed_factory = screen, platform, feed
        self.workdir = workdir or Path(tempfile.gettempdir()) / "capri-clips"
        self.proc = None
        self.feed = None
        self.started = 0.0
        self.method = ""
        self.encoder = ""
        self.audio = ""
        self.problem = ""
        self._failed_methods: set[str] = set()
        self._no_sound = False
        self._encoder_cache: str | None = None
        self._lock = threading.Lock()

    # -- what this PC can do ------------------------------------------------------------------------------
    def _works(self, ffmpeg: str, args: list[str]) -> bool:
        try:
            r = self.run([ffmpeg, "-hide_banner", "-loglevel", "error", *args], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, creationflags=NO_WINDOW)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def pick_encoder(self, ffmpeg: str) -> str:
        """The graphics card's encoder if it really works on this PC, else x264."""
        if self._encoder_cache:
            return self._encoder_cache
        test = ["-f", "lavfi", "-i", "color=c=black:s=320x240:r=30", "-frames:v", "5", "-f", "null", "-"]
        for enc in HW_ENCODERS:
            if self._works(ffmpeg, test[:6] + ["-c:v", enc] + test[6:]):
                self._encoder_cache = enc
                return enc
        self._encoder_cache = "libx264"
        return "libx264"

    def methods(self) -> list[str]:
        if self.platform == "win32":
            return [m for m in ("ddagrab", "gdigrab") if m not in self._failed_methods]
        return [m for m in ("x11grab",) if m not in self._failed_methods]

    # -- recording ------------------------------------------------------------------------------------------
    @property
    def recording(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> bool:
        with self._lock:
            if self.recording:
                return True
            ffmpeg = self.ffmpeg()
            if not ffmpeg:
                self.problem = "no ffmpeg" if self.platform != "win32" else "the recorder isn't downloaded"
                return False
            methods = self.methods()
            if not methods:
                self.problem = "your screen can't be recorded here"
                return False
            s = self.settings
            self.method, self.encoder = methods[0], self.pick_encoder(ffmpeg)
            sound = s.clip_sound and not self._no_sound
            self.audio = ("pipe" if self.platform == "win32" else "pulse") if sound else ""
            shutil.rmtree(self.workdir, ignore_errors=True)
            self.workdir.mkdir(parents=True, exist_ok=True)
            cmd = record_command(ffmpeg, self.method, self.screen(), int(s.clip_fps),
                                 RESOLUTIONS.get(s.clip_resolution, 1080), self.encoder, self.workdir, self.audio,
                                 os.environ.get("DISPLAY", ""))
            err = open(self.workdir / "ffmpeg.log", "wb")
            try:
                self.proc = self.popen(cmd, stdin=subprocess.PIPE if self.audio == "pipe" else subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=err, creationflags=NO_WINDOW)
            except OSError as exc:
                self.problem = f"ffmpeg wouldn't start ({exc})"
                return False
            finally:
                err.close()
            if self.audio == "pipe":
                self.feed = self.feed_factory(self.proc.stdin)
                self.feed.start()
            self.started = time.monotonic()
            self.problem = ""
            log.info("clips: recording (%s, %s, sound: %s)", self.method, self.encoder, self.audio or "none")
            return True

    def stop(self) -> None:
        with self._lock:
            if self.feed is not None:
                self.feed.stop()
                self.feed = None
            if self.proc is not None:
                try:
                    if self.proc.stdin:
                        self.proc.stdin.close()
                except OSError:
                    pass
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                self.proc = None

    def check(self) -> None:
        """ffmpeg quit by itself (that way of recording doesn't work here): try the next way, and say why."""
        if self.proc is None or self.proc.poll() is None:
            return
        why = ""
        try:
            why = (self.workdir / "ffmpeg.log").read_text(errors="replace").strip().splitlines()[-1][:200]
        except (OSError, IndexError):
            pass
        log.info("clips: the recorder stopped (%s): %s", self.method, why)
        quick = time.monotonic() - self.started < 10
        if quick and self.audio == "pulse":
            self._no_sound = True                                  # no sound server: record without sound
        elif quick:
            self._failed_methods.add(self.method)                  # e.g. no Desktop Duplication: try GDI
        self.proc = None
        if self.feed is not None:
            self.feed.stop()
            self.feed = None
        self.start()

    def pieces(self) -> list[tuple[str, float]]:
        try:
            return finished_pieces((self.workdir / "pieces.csv").read_text())
        except OSError:
            return []

    def recorded_seconds(self) -> float:
        return sum(length for _name, length in self.pieces())

    # -- clip that -------------------------------------------------------------------------------------------
    def save(self, seconds: float, folder: Path | None = None, wait: Callable[[float], None] = time.sleep) -> Path:
        """Save the last `seconds` (blocking: up to ~3 s for the current piece, then a fast copy). Raises OSError
        with what to tell you."""
        ffmpeg = self.ffmpeg()
        if not ffmpeg:
            raise OSError("I'm not recording - turn on Clip my games first")
        seconds = max(5.0, min(float(seconds), MAX_LENGTH))
        if self.recording:                                      # the piece being recorded right now goes in too
            before = len(self.pieces())
            for _ in range(int(SEGMENT / 0.1) + 15):
                if len(self.pieces()) > before:
                    break
                wait(0.1)
        pieces = self.pieces()
        if not pieces:
            raise OSError("I haven't recorded anything yet")
        names, extra = newest(pieces, seconds)
        names = [n for n in names if (self.workdir / n).exists()]
        if not names:
            raise OSError("I haven't recorded anything yet")
        folder = Path(folder or self.settings.clip_folder or default_folder())
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / clip_name()
        listing = self.workdir / "clip.txt"
        listing.write_text("".join(f"file '{(self.workdir / n).as_posix()}'\n" for n in names))
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
        # (no trimming to the exact second: a stream copy can only cut at a keyframe, and that would make it
        # shorter than you asked - so it's up to one piece longer instead)
        cmd += ["-c", "copy", "-movflags", "+faststart", str(target)]
        r = self.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120,
                     creationflags=NO_WINDOW)
        if r.returncode != 0 or not target.exists() or target.stat().st_size < 1000:
            log.info("clips: joining failed: %s", (r.stderr or b"")[-300:])
            raise OSError("the clip didn't save")
        log.info("clips: saved %s (%.0f s)", target, min(seconds, sum(l for n, l in pieces if n in names)))
        return target
