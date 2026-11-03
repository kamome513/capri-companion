"""v1.39: clips - "hey Capri, clip that" saves the last seconds of your screen and sound as a video."""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations import clips  # noqa: E402
from capri.settings import Settings  # noqa: E402

SCREEN = clips.Screen(0, 0, 2560, 1440)


# -- what she understands -------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,seconds", [
    ("clip that", ""), ("hey capri clip that", ""), ("clip it", ""), ("capri clip that please", ""),
    ("clip the last 30 seconds", "30"), ("clip the last minute", "60"), ("save the last two minutes", "120"),
    ("record the last 45 seconds", "45"), ("that was clip worthy", ""), ("save that clip", ""),
])
def test_clip_that(text, seconds):
    intent = parse(text)
    assert intent.kind is Kind.CLIP and intent.query == seconds


def test_save_that_is_not_a_clip():
    assert parse("save that").kind is not Kind.CLIP          # (that's saving a file)


# -- the recording command -------------------------------------------------------------------------------------
def test_windows_records_with_desktop_duplication_and_piped_sound(tmp_path):
    cmd = clips.record_command("ffmpeg.exe", "ddagrab", SCREEN, 60, 1080, "h264_nvenc", tmp_path, "pipe")
    line = " ".join(cmd)
    assert "ddagrab=output_idx=0:framerate=60" in line and "hwdownload,format=bgra,scale=-2:1080" in line
    assert "-f s16le -ar 48000 -ac 2 -i pipe:0" in line and "-c:a aac" in line and "h264_nvenc" in line
    assert "-segment_time 2" in line and f"-segment_wrap {120 // 2 + 4}" in line and "pieces.csv" in line


def test_gdi_records_just_your_main_screen(tmp_path):
    line = " ".join(clips.record_command("ffmpeg", "gdigrab", clips.Screen(-1920, 0, 1920, 1080), 30, 0,
                                         "libx264", tmp_path, ""))
    assert "-offset_x -1920 -offset_y 0 -video_size 1920x1080 -i desktop" in line
    assert "scale=trunc(iw/2)*2:trunc(ih/2)*2" in line and "-c:a" not in line and "libx264" in line


def test_linux_records_x11_and_pulse(tmp_path):
    line = " ".join(clips.record_command("ffmpeg", "x11grab", clips.Screen(0, 0, 1920, 1080), 30, 720,
                                         "libx264", tmp_path, "pulse", display=":1"))
    assert "-f x11grab" in line and "-i :1+0,0" in line and "-f pulse -i @DEFAULT_MONITOR@" in line
    assert "scale=-2:720" in line


def test_the_newest_pieces_make_the_clip():
    csv = "".join(f"piece{i:03d}.ts,{i * 2}.0,{i * 2 + 2}.0\n" for i in range(10))
    pieces = clips.finished_pieces(csv)
    assert len(pieces) == 10 and pieces[0] == ("piece000.ts", 2.0)
    names, extra = clips.newest(pieces, 5)
    assert names == ["piece007.ts", "piece008.ts", "piece009.ts"] and extra == pytest.approx(1.0)
    wrapped = pieces + [("piece000.ts", 2.0)]                       # the ring reused a name: never twice
    names, _ = clips.newest(wrapped, 60)
    assert names[0] == "piece001.ts" and len(names) == 10


def test_ffmpeg_on_windows_is_capris_own(tmp_path):
    assert clips.find_ffmpeg("win32", which=lambda n: None, tools=tmp_path) is None
    (tmp_path / "ffmpeg.exe").write_bytes(b"MZ")
    assert clips.find_ffmpeg("win32", which=lambda n: None, tools=tmp_path) == str(tmp_path / "ffmpeg.exe")
    assert clips.find_ffmpeg("linux", which=lambda n: "/usr/bin/ffmpeg") == "/usr/bin/ffmpeg"


# -- the Windows download -----------------------------------------------------------------------------------------
class Download(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def wheel() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(clips.FFMPEG_WHEEL[2], b"MZ-ffmpeg")
    return buf.getvalue()


def test_ffmpeg_download_is_checked_and_unpacked(tmp_path, monkeypatch):
    data = wheel()
    monkeypatch.setattr(clips, "FFMPEG_WHEEL", (clips.FFMPEG_WHEEL[0], hashlib.sha256(data).hexdigest(),
                                               clips.FFMPEG_WHEEL[2], len(data)))
    asked, seen = [], []
    path = clips.download_ffmpeg(seen.append, opener=lambda req, timeout: asked.append(req.full_url) or Download(data),
                                 tools=tmp_path)
    assert Path(path).read_bytes() == b"MZ-ffmpeg" and asked[0].startswith("https://files.pythonhosted.org/")
    assert seen[-1] == 100 and not (tmp_path / "ffmpeg-download.part").exists()


def test_a_damaged_download_is_refused(tmp_path):
    with pytest.raises(OSError) as caught:
        clips.download_ffmpeg(opener=lambda req, timeout: Download(wheel()), tools=tmp_path)
    assert "didn't match" in str(caught.value) and not (tmp_path / "ffmpeg.exe").exists()


# -- sound ---------------------------------------------------------------------------------------------------------
class Sink:
    def __init__(self):
        self.data = bytearray()

    def write(self, b):
        self.data += b

    def flush(self):
        pass


def test_silence_is_filled_in_so_sound_stays_in_step():
    class Quiet:                                        # Windows' loopback sends nothing while nothing plays
        def record(self, numframes):
            time.sleep(0.02)
            return np.zeros((0, 2), np.float32)
    sink = Sink()
    feed = clips.LoopbackFeed(sink, source=Quiet)
    feed.start()
    time.sleep(0.6)
    feed.stop()
    feed.thread.join(2)
    seconds = len(sink.data) / 4 / clips.AUDIO_RATE
    assert 0.4 < seconds < 0.75


def test_no_speakers_means_a_silent_track():
    def broken():
        raise RuntimeError("no device")
    sink = Sink()
    feed = clips.LoopbackFeed(sink, source=broken)
    feed.start()
    time.sleep(0.4)
    feed.stop()
    feed.thread.join(2)
    assert len(sink.data) > 0 and not any(sink.data)


# -- the recorder ---------------------------------------------------------------------------------------------------
class FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd, self.kw = cmd, kw
        self.stdin = Sink() if kw.get("stdin") == subprocess.PIPE else None
        self.code = None

    def poll(self):
        return self.code

    def terminate(self):
        self.code = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.code = -9


def recorder(tmp_path, platform="linux", **settings):
    started = []

    def popen(cmd, **kw):
        started.append(FakeProc(cmd, **kw))
        return started[-1]
    s = Settings(clips=True, clip_folder=str(tmp_path / "out"), **settings)
    rec = clips.ClipRecorder(s, ffmpeg=lambda: "ffmpeg", popen=popen, run=lambda *a, **k: SimpleNamespace(returncode=1),
                             screen=lambda: SCREEN, platform=platform, workdir=tmp_path / "work",
                             feed=lambda sink: SimpleNamespace(start=lambda: None, stop=lambda: None))
    return rec, started


def test_windows_starts_with_desktop_duplication_and_falls_back_to_gdi(tmp_path):
    rec, started = recorder(tmp_path, platform="win32")
    assert rec.start() and rec.method == "ddagrab" and rec.encoder == "libx264" and rec.audio == "pipe"
    assert started[0].kw["stdin"] == subprocess.PIPE
    started[0].code = 1                                   # it didn't work on this PC
    rec.check()
    assert rec.method == "gdigrab" and len(started) == 2 and rec.recording


def test_linux_without_a_sound_server_records_without_sound(tmp_path):
    rec, started = recorder(tmp_path)
    assert rec.start() and rec.audio == "pulse"
    started[0].code = 1
    rec.check()
    assert rec.audio == "" and rec.method == "x11grab" and len(started) == 2


def test_no_ffmpeg_says_so(tmp_path):
    rec, _ = recorder(tmp_path)
    rec.ffmpeg = lambda: None
    assert not rec.start() and "ffmpeg" in rec.problem


def test_the_graphics_card_encoder_when_it_works(tmp_path):
    rec, _ = recorder(tmp_path)
    rec.run = lambda cmd, **k: SimpleNamespace(returncode=0 if "h264_amf" in cmd else 1)
    assert rec.pick_encoder("ffmpeg") == "h264_amf"


def test_nothing_recorded_yet(tmp_path):
    rec, _ = recorder(tmp_path)
    with pytest.raises(OSError) as caught:
        rec.save(30, wait=lambda s: None)
    assert "haven't recorded" in str(caught.value)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_a_real_clip(tmp_path, monkeypatch):
    """Real ffmpeg, a test picture and a test tone instead of your screen and speakers."""
    monkeypatch.setattr(clips, "capture_args", lambda method, screen, fps, display="":
                        ["-re", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate={fps}"])
    s = Settings(clips=True, clip_folder=str(tmp_path / "out"), clip_sound=True)

    class Tone:
        def __init__(self):
            self.t = 0

        def record(self, numframes):
            time.sleep(numframes / 48000)
            x = np.arange(self.t, self.t + numframes) / 48000
            self.t += numframes
            wave = (0.3 * np.sin(2 * np.pi * 440 * x)).astype(np.float32)
            return np.stack([wave, wave], 1)
    rec = clips.ClipRecorder(s, screen=lambda: clips.Screen(0, 0, 640, 360), platform="win32",
                             workdir=tmp_path / "work", feed=lambda sink: clips.LoopbackFeed(sink, source=Tone))
    rec.methods = lambda: ["test"]
    rec._encoder_cache = "libx264"
    assert rec.start() and rec.audio == "pipe"
    try:
        time.sleep(7)
        out = rec.save(4)
    finally:
        rec.stop()
    assert out.exists() and out.parent == tmp_path / "out" and out.name.startswith("Capri clip ")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.split()
    assert "video" in probe and "audio" in probe
    duration = float([p for p in probe if p[0].isdigit()][0])
    assert 4 <= duration <= 6.5


# -- the router ---------------------------------------------------------------------------------------------------------
def router():
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    r.router.services.settings = r.assistant.settings
    return r


def test_clips_off_she_offers_to_turn_them_on():
    from test_stage5 import settle
    r = router()
    r.assistant.settings.clips = False
    turned = []
    r.router.services.clips = SimpleNamespace(recording=False, problem="")
    r.router.services.clips_turn_on = lambda progress: (progress("Downloading the clip recorder... 50%"),
                                                        turned.append(1))
    r.router.handle("clip that")
    assert settle(3, lambda: "Want me to start" in r.controller.message)
    r.service.command.emit("yes")
    assert settle(5, lambda: turned and "Clips are on" in r.controller.message)


def test_clip_that_saves_it():
    from test_stage5 import settle
    r = router()
    r.assistant.settings.clips = True
    asked = []
    r.router.services.clips = SimpleNamespace(recording=True, problem="",
                                              save=lambda secs: asked.append(secs) or Path("/x/Capri clip.mp4"))
    r.router.handle("clip the last minute")
    assert settle(5, lambda: "Clipped! The last minute," in r.controller.message) and asked == [60]
    r.router.handle("clip that")
    assert settle(5, lambda: asked[-1] == r.assistant.settings.clip_length)


def test_not_in_a_game_nothing_to_clip():
    r = router()
    r.assistant.settings.clips = True
    r.router.services.clips = SimpleNamespace(recording=False, problem="")
    r.router.handle("clip that")
    assert "only record while you're in a game" in r.controller.message


def test_clip_and_watch_numbers_are_kept_after_a_restart(tmp_path, monkeypatch):
    import json
    from capri import settings as settings_mod
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod.Settings, "path", classmethod(lambda cls: path))
    path.write_text(json.dumps({"clip_length": 90, "clip_fps": 60, "watch_every": 300}))
    s = settings_mod.Settings.load()
    assert (s.clip_length, s.clip_fps, s.watch_every) == (90, 60, 300)
    path.write_text(json.dumps({"clip_length": 9999, "watch_every": 1, "clip_fps": True}))
    s = settings_mod.Settings.load()
    assert (s.clip_length, s.clip_fps, s.watch_every) == (120, 30, 30)
