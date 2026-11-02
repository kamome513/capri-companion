"""v1.12: Test voice always speaks, drone mode in any game you play, and less RAM."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from capri.speech.engines import Audio  # noqa: E402


def test_test_voice_speaks_even_with_spoken_replies_off():
    from capri.settings import Settings
    from capri.speech.speaker import Speaker
    s = Settings()
    s.speech_enabled = False
    played = []

    class Box:
        last = ("neural: Capri", "")

        def synthesize(self, text, voice, speed, pitch=0.0):
            return Audio(np.sin(np.arange(12000) / 9).astype(np.float32) * 0.3, 24000, pitched=True)

        def voices(self):
            return []
    sp = Speaker(s, Box, player=lambda x, r: (played.append(len(x)), lambda: None)[1], sleep=lambda t: None)
    spoke = []
    sp.spoke.connect(lambda v, n: spoke.append(v))
    assert not sp.say("Hi.")                                              # normal lines: off
    assert sp.say("Hi.", force=True)                                      # the test: always
    deadline = time.monotonic() + 5
    while not (played and spoke) and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    sp.shutdown()
    assert played and spoke == ["neural: Capri"]


# -- game mode by itself, and less RAM -------------------------------------------------------------------
from capri.commands.games import Front, GameWatch, looks_like_game  # noqa: E402


@pytest.mark.parametrize("front, why", [
    (Front(10, r"C:\Program Files (x86)\Steam\steamapps\common\Deadlock\game\bin\win64\project8.exe"), "library"),
    (Front(11, r"C:\Riot Games\VALORANT\live\VALORANT.exe"), "library"),
    (Front(12, r"D:\Games\Celeste\Celeste.exe", fullscreen=True), "fullscreen"),
    (Front(13, r"D:\Games\Old\game.exe", d3d=True), "d3d"),
    (Front(14, r"C:\Program Files\Opera GX\opera.exe", fullscreen=True), ""),          # YouTube full screen
    (Front(15, r"C:\Program Files\VideoLAN\VLC\vlc.exe", fullscreen=True), ""),
    (Front(16, r"C:\Program Files (x86)\Steam\steam.exe"), ""),                         # the launcher
    (Front(17, r"C:\Windows\explorer.exe", fullscreen=True), ""),
    (Front(18, r"C:\Users\me\AppData\Local\Discord\app-1\Discord.exe"), ""),
])
def test_what_counts_as_a_game(front, why):
    assert looks_like_game(front) == why


class FakePC:
    def __init__(self):
        self.front = None
        self.running = set()


def watch(pc, states):
    return GameWatch(states.append, lambda: [], front=lambda: pc.front, alive=lambda pid: pid in pc.running)


def test_she_turns_into_the_drone_when_you_start_a_game_yourself():
    pc, states = FakePC(), []
    w = watch(pc, states)
    pc.front = Front(40, r"c:\program files (x86)\steam\steamapps\common\deadlock\project8.exe")
    pc.running.add(40)
    w.scan()
    assert states == [True]
    pc.front = Front(41, r"c:\program files\opera gx\opera.exe")       # alt-tab: still in the game
    w.scan()
    assert states == [True]
    pc.running.discard(40)                                               # the game closes
    w.scan()
    assert states == [True, False]


def test_full_screen_has_to_stay_in_front_a_moment():
    pc, states = FakePC(), []
    w = watch(pc, states)
    pc.front = Front(50, r"d:\games\celeste\celeste.exe", fullscreen=True)
    pc.running.add(50)
    w.scan()
    assert states == []
    w.scan()
    assert states == [True]


def test_normal_mode_mid_game_is_respected():
    pc, states = FakePC(), []
    w = watch(pc, states)
    pc.front = Front(60, r"c:\riot games\valorant\live\valorant.exe")
    pc.running.add(60)
    w.scan()
    w.stop()                                                             # "normal mode"
    w.scan()
    assert states == [True, False]                                       # not straight back into the drone
    pc.running.discard(60)
    w.scan()
    pc.front, pc.running = Front(61, r"c:\riot games\valorant\live\valorant.exe"), {61}
    w.scan()
    assert states[-1] is True                                            # the next game: drone again


def test_auto_drone_can_be_turned_off():
    pc, states = FakePC(), []
    w = GameWatch(states.append, lambda: [], front=lambda: pc.front, alive=lambda pid: True, auto=lambda: False)
    pc.front = Front(70, r"c:\riot games\valorant\live\valorant.exe")
    w.scan()
    assert states == []


def test_memory_trim_is_safe_anywhere():
    from capri import memory
    memory.trim()
