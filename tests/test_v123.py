"""v1.23: a smooth greeting with a real wave and expressions; no more waking up to Discord pings."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.voice.voicecheck import voice_check  # noqa: E402

RATE = 16000
rng = np.random.default_rng(3)


def _pcm(x):
    return np.clip(x, -32767, 32767).astype(np.int16).tobytes()


def _ping(notes, dur=0.35, decay=8.0, harmonics=(1,)):
    t = np.arange(int(RATE * dur)) / RATE
    return np.concatenate([sum(np.sin(2 * np.pi * f * k * t) / k ** 1.5 for k in harmonics) * np.exp(-t * decay) * 9000
                           for f in notes])


def _echo(x, t60=0.4):
    n = int(RATE * t60)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / RATE * 6.9 / t60)
    ir[0] = 1
    y = np.convolve(x, ir)[: len(x) + n // 2]
    return y / np.abs(y).max() * np.abs(x).max()


@pytest.mark.parametrize("notes, harmonics", [([880, 1320], (1,)), ([1500], (1,)), ([660, 990], (1, 4)),
                                              ([1047], (1, 2, 3)), ([2000, 2400], (1,))])
@pytest.mark.parametrize("room", ["dry", "echo"])
@pytest.mark.parametrize("noise", [100, 600])
def test_pings_and_chimes_dont_wake_her(notes, harmonics, room, noise):
    x = _ping(notes, harmonics=harmonics)
    x = _echo(x) if room == "echo" else x
    ok, why = voice_check(_pcm(x + rng.standard_normal(len(x)) * noise), RATE)
    assert not ok and "chime" in why


def _spoken(voice, text):
    raw = subprocess.run(["espeak-ng", "-v", voice, "-s", "160", "--stdout", text], capture_output=True).stdout
    with wave.open(io.BytesIO(raw)) as w:
        r = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    return np.interp(np.arange(int(len(a) * RATE / r)) * r / RATE, np.arange(len(a)), a)


@pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="needs espeak-ng to speak")
@pytest.mark.parametrize("voice", ["en-us", "en-us+f3", "en-us+m3", "en-gb", "en-sc"])
@pytest.mark.parametrize("room", ["dry", "echo"])
@pytest.mark.parametrize("level, noise", [(12000, 100), (2500, 100), (12000, 600)])
def test_a_person_saying_capri_still_wakes_her(voice, room, level, noise):
    for text in ("Capri", "Hey Capri"):
        a = _spoken(voice, text)
        a = a / np.abs(a).max() * level
        a = _echo(a) if room == "echo" else a
        ok, _why = voice_check(_pcm(a + rng.standard_normal(len(a)) * noise), RATE)
        assert ok, (voice, text)


def test_the_listener_rejects_a_ping_that_sounded_like_capri():
    from fake_vosk import RATE as FAKE_RATE, FakeRecognizer, speak  # noqa: F401
    from capri.voice.wakeword import Rejected, Wake, WakeWordListener
    from capri.voice import voicecheck
    listener = WakeWordListener(lambda rate: FakeRecognizer(rate, True), lambda rate: FakeRecognizer(rate, False),
                                sample_rate=FAKE_RATE)
    listener.voice_check = lambda audio, rate: (False, "a chime / ping, not a voice")
    events = [e for chunk in speak("capri", 1.0) for e in listener.feed(chunk)]
    assert not any(isinstance(e, Wake) for e in events)
    assert any(isinstance(e, Rejected) and "chime" in e.text for e in events)
    assert voicecheck.voice_check is voice_check


# -- the greeting: smooth, a real wave, expressions -----------------------------------------------------------
def _figure(emotion="happy"):
    from PySide6.QtGui import QColor, QImage
    from capri.ui.greeting import RigFigure
    from capri.ui.rig import Rig
    img = QImage(200, 600, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    from PySide6.QtGui import QPainter
    p = QPainter(img)                                     # a stand-in figure: body, two arms, a face
    p.fillRect(70, 20, 60, 560, QColor(200, 30, 60))
    p.fillRect(30, 140, 30, 230, QColor(60, 20, 90))
    p.fillRect(140, 140, 30, 230, QColor(60, 20, 90))
    p.end()
    fig = RigFigure(Rig(img), 400, seed=1)
    fig.emotion = emotion
    return fig


def test_she_waves_properly_raises_swings_and_lowers():
    fig = _figure()
    poses = {t: fig.pose_at(t) for t in (0.1, 0.6, 1.2, 1.5, 2.0, 3.5)}
    assert poses[0.1].wave == 0 and poses[3.5].wave == 0             # arm down before and after
    assert poses[1.2].wave == 1.0 and poses[2.0].wave == 1.0         # up while waving
    wags = [fig.pose_at(t).wag for t in np.arange(1.0, 2.6, 0.05)]
    assert max(wags) > 0.8 and min(wags) < -0.8                       # the hand swings both ways
    steps = [abs(fig.pose_at(t + 0.016).wave - fig.pose_at(t).wave) for t in np.arange(0.3, 3.4, 0.016)]
    assert max(steps) < 0.08                                          # smooth: no jumps between frames


def test_expressions_during_the_greeting():
    fig = _figure("playful")
    eyes = {fig.pose_at(t).eyes for t in np.arange(0.3, 3.0, 0.05)}
    assert {"happy", "wink"} <= eyes
    sad = _figure("sad")
    assert "happy" not in {sad.pose_at(t).eyes for t in np.arange(0.3, 3.0, 0.05)}
    blinks = [fig.pose_at(t).blink for t in np.arange(0, 12, 0.02)]
    assert max(blinks) > 0.9                                          # she blinks


def test_her_mouth_follows_her_voice_smoothly():
    fig = _figure()
    fig.talking = True
    levels = []
    for i in range(30):
        fig.level = 1.0 if (i // 3) % 2 else 0.0                        # a choppy voice
        levels.append(fig.pose_at(0.5).mouth)
    assert max(levels) > 0.6 and max(abs(a - b) for a, b in zip(levels, levels[1:])) < 0.5


def test_the_face_moves_draw_without_errors():
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtCore import QPointF
    from capri.ui.rig import Pose
    fig = _figure()
    img = QImage(300, 500, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    for pose in (Pose(eyes="happy", mouth=0.5), Pose(eyes="wink"), Pose(blink=1.0), Pose(wave=1.0, wag=0.7)):
        fig.rig.paint(p, QPointF(150, 480), 450, pose, "right")
    p.end()
