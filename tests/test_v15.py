"""v1.5: forgiving small talk, the free local AI (Ollama), teleporting to the taskbar with
lightning, and typing a search into the Spotify app."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRect, QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

import random  # noqa: E402

from capri.ai.local import OLLAMA_TOOLS, Brains, LocalBrain  # noqa: E402
from capri.commands.parser import Intent, Kind, parse  # noqa: E402
from capri.integrations import http  # noqa: E402
from capri.integrations.app_buttons import SpotifyButtons  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402
from capri.ui.screen_spots import taskbar_icon  # noqa: E402


# -- small talk that doesn't need the exact words ----------------------------------------------------
@pytest.mark.parametrize("text, topic", [
    ("im soo bored", "bored"), ("im sooo bored", "bored"), ("i am so so bored", "bored"),
    ("im really bored right now", "bored"), ("im bored af", "bored"), ("this is boring", "bored"),
    ("im kinda tired", "tired"), ("im getting really sleepy", "tired"), ("i feel sad", "sad"),
    ("tell me a joke capri", "joke"), ("hiii", "hello"), ("im so good", "im_good"),
])
def test_forgiving_small_talk(text, topic):
    assert parse(text) == Intent(Kind.CHAT, query=topic)


def test_feelings_never_beat_commands():
    assert parse("open discord").kind is Kind.OPEN
    assert parse("play something boring").kind is Kind.PLAY
    assert parse("whats the weather").kind is Kind.WEATHER


def test_so_bored_gets_an_answer_not_confusion():
    r = rig(FakeDesktop())
    r.service.command.emit("im soo bored")
    assert r.controller.state is State.SPEAKING and "bored" in r.speaker.lines[-1].lower()


# -- the local AI ------------------------------------------------------------------------------------------
class FakeOllama:
    def __init__(self, replies, models=("llama3.2:latest",)):
        self.replies, self.models, self.calls = list(replies), models, []

    def __call__(self, method, url, params=None, data=None, json_body=None, headers=None, timeout=10.0):
        self.calls.append((method, url, json_body))
        if url.endswith("/api/tags"):
            return {"models": [{"name": m} for m in self.models]}
        return {"message": self.replies.pop(0)}


def brain(fake, model="llama3.2"):
    return LocalBrain(lambda: "", lambda: model, {"get_time": lambda a: "Monday 10:00"}, fetch=fake)


def test_local_ai_chats_with_her_persona_and_emotion():
    fake = FakeOllama([{"role": "assistant", "content": "[playful] Bored? Let's fix that. Game or music?"}])
    reply = brain(fake).ask("im soo bored")
    assert reply.text == "Bored? Let's fix that. Game or music?" and reply.emotion == "playful"
    chats = [c for c in fake.calls if c[1].endswith("/api/chat")]
    body = chats[0][2]
    assert chats[0][1] == "http://127.0.0.1:11434/api/chat" and body["model"].startswith("llama3.2")
    assert body["messages"][0]["role"] == "system" and "Capri" in body["messages"][0]["content"]
    assert "tools" not in body and body["stream"] is False      # v1.32: plain chat - small models talk better
    fake = FakeOllama([{"role": "assistant", "content": "[happy] On it."}])
    brain(fake).ask("can you open discord")
    assert [c for c in fake.calls if c[1].endswith("/api/chat")][0][2]["tools"] == OLLAMA_TOOLS             # asking her to do something: the tools go along


def test_local_ai_actions_become_capri_intents_only():
    fake = FakeOllama([{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "open_app", "arguments": {"names": ["Discord"]}}}]}])
    reply = brain(fake).ask("can you get discord up")
    assert reply.intent == Intent(Kind.OPEN, ("Discord",))
    fake2 = FakeOllama([{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "run_shell", "arguments": {"cmd": "del C:\\\\"}}}]},
        {"role": "assistant", "content": "Can't do that."}])
    reply2 = brain(fake2).ask("delete everything")
    assert reply2.intent is None and reply2.text == "Can't do that."


def test_local_ai_info_tools_loop():
    fake = FakeOllama([{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "get_time", "arguments": {}}}]},
        {"role": "assistant", "content": "It's 10 on Monday."}])
    reply = brain(fake).ask("what time is it roughly")
    assert reply.text == "It's 10 on Monday."
    chats = [c for c in fake.calls if c[1].endswith("/api/chat")]
    assert chats[1][2]["messages"][-1] == {"role": "tool", "content": "Monday 10:00", "tool_name": "get_time"}


def test_local_ai_says_what_is_missing():
    assert brain(FakeOllama([], models=())).available()[0] is False
    assert "ollama pull llama3.2" in brain(FakeOllama([], models=("nomic-embed-text",))).available()[1]
    other = brain(FakeOllama([], models=("qwen2.5:3b",)))          # v1.35.1: any chat model you've got
    assert other.available() == (True, "Ollama is ready with qwen2.5:3b.") and other.chosen == "qwen2.5:3b"
    assert brain(FakeOllama([])).available()[0] is True

    def down(*a, **k):
        raise OSError("refused")
    assert brain(down).ask("hi").error and "can't reach Ollama" in brain(down).available()[1]

    def missing(*a, **k):
        raise http.HttpError(404, "model not found")
    assert "ollama pull" in brain(missing).ask("hi").text


def test_brains_follow_the_setting():
    class Named:
        def __init__(self, name):
            self.name = name

        def ask(self, text):
            return self.name

        def reset(self):
            pass
    s = Settings(ai_provider="local")
    b = Brains(s, Named("claude"), Named("local"))
    assert b.ask("x") == "local"
    s.ai_provider = "claude"
    assert b.ask("x") == "claude"


# -- teleporting --------------------------------------------------------------------------------------------



def test_taskbar_lookup_off_windows():
    assert taskbar_icon(object(), "Discord") is None


# -- Spotify: typing the search ---------------------------------------------------------------------------
class Box:
    def __init__(self, name):
        self.name, self.focused = name, False

    def focus(self):
        self.focused = True


class SpotifyUI:
    def __init__(self, edits):
        self._edits = edits

    def edits(self, hwnd):
        return self._edits

    def buttons(self, hwnd, names=None):
        return []


class Keyboard:
    def __init__(self):
        self.calls = []

    def bring_to_front(self, hwnd):
        self.calls.append(("front", hwnd))
        return True

    def press_keys(self, combo):
        self.calls.append(("keys", combo))

    def type_text(self, text):
        self.calls.append(("type", text))

    def press_enter(self):
        self.calls.append(("enter",))


def test_spotify_types_into_its_search_box():
    box = Box("What do you want to play?")
    kb = Keyboard()
    s = SpotifyButtons(SpotifyUI([Box("Filter"), box]), lambda pids: [9], sleep=lambda x: None, desktop=kb)
    assert s.search([7], "let you down nf")
    assert box.focused
    assert kb.calls == [("front", 9), ("keys", "ctrl+a"), ("type", "let you down nf"), ("enter",)]


def test_spotify_search_box_fallback_shortcut():
    kb = Keyboard()
    s = SpotifyButtons(SpotifyUI([]), lambda pids: [9], sleep=lambda x: None, desktop=kb)
    assert s.search([7], "blinding lights")
    assert ("keys", "ctrl+l") in kb.calls and ("type", "blinding lights") in kb.calls
    assert not SpotifyButtons(SpotifyUI([]), lambda pids: [], sleep=lambda x: None, desktop=kb).search([7], "x")


def test_full_body_rig_moves_like_a_body():
    """Her full-body figure, cut into parts: arms come off cleanly and swing from the shoulder."""
    from capri.app import asset_root
    from capri.ui.rig import Pose, Rig
    from capri.ui.sprites import SpriteArt
    r = Rig(SpriteArt.load(asset_root() / "capri_v2").frame("standing"))
    for part in (r.upper, r.lower, r.arms["left"], r.arms["right"], r.face):
        assert not part.isNull()
    feet = QPointF(500, 600)
    rest = r.hand_tip(feet, 270, Pose(), "right")
    bent = r.hand_tip(feet, 270, Pose(lean=1, reach=1, squat=1), "right")
    assert rest.x() > feet.x() and rest.y() < feet.y()            # right claw hangs by her right side
    assert bent.x() > rest.x() + 60                                 # bending + reaching moves it out to the icon
    assert r.hand_tip(feet, 270, Pose(lean=-1, reach=1, squat=1), "left").x() < feet.x() - 60
    assert r.head.width() > 50 and r.head.bottom() < r.h * 0.25     # hair box is her head, for the storm
