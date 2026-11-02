"""v1.25: several things in one sentence, step by step ("open notepad and type hi tiktok"), typing,
her AI doing several actions in a row, and "are you a virus?"."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Kind, parse  # noqa: E402


@pytest.mark.parametrize("said, words", [
    ("type hi tiktok", "hi tiktok"), ("Type Hi, TikTok.", "Hi, TikTok."), ("type out hello world please", "hello world"),
    ("write down buy milk for me", "buy milk"), ("write hi there", "hi there"),
])
def test_typing_your_exact_words(said, words):
    intent = parse(said)
    assert intent.kind is Kind.TYPE and intent.query == words


@pytest.mark.parametrize("said", ["write me a poem", "type it", "typing is hard", "enter my password"])
def test_not_typing(said):
    assert parse(said).kind is not Kind.TYPE


def _typing_rig():
    d = FakeDesktop()
    r = rig(d)
    typed = []
    d.type_text = typed.append
    fronts = iter([1, 1, 1, 2])                                         # Notepad's window comes to the front
    r.router.services.front = lambda: next(fronts, 2)
    return r, typed


def test_open_notepad_and_type_step_by_step():
    r, typed = _typing_rig()
    r.router.handle("Open Notepad and type Hi, TikTok.")
    assert r.speaker.lines[-1] == "Wait a second while I open Notepad and type that in."
    assert settle(5, lambda: r.controller.message.startswith("Alright"))
    assert r.controller.message == "Alright, Notepad is open and your message is typed."
    assert typed == ["Hi, TikTok."] and any("Notepad" in str(c) for c in r.system.calls)


def test_one_step_sentences_stay_one_step():
    r, typed = _typing_rig()
    assert r.router._split_steps("open discord and spotify") == []       # two apps, one command
    assert r.router._split_steps("type hi and bye") == []                # all of it gets typed
    steps = r.router._split_steps("open notepad and type hi and bye")
    assert [i.kind for i, _ in steps] == [Kind.OPEN, Kind.TYPE] and steps[1][0].query == "hi and bye"
    steps = r.router._split_steps("mute me, then take a screenshot")
    assert [i.kind for i, _ in steps] == [Kind.DISCORD, Kind.SCREENSHOT]


def test_a_failed_step_is_said_plainly():
    d = FakeDesktop()                                                    # no keyboard here
    r = rig(d)
    r.router.handle("open notepad and type hi")
    assert settle(5, lambda: r.controller.state.value == "error")
    assert r.controller.message == "Notepad is open, but I can only type on Windows."


def test_typing_never_presses_enter():
    r, typed = _typing_rig()
    from capri.commands.parser import Intent
    r.router.dispatch(Intent(Kind.TYPE, query="del stuff" + chr(10) + "exit" + chr(13) + chr(10)), "")
    assert typed and chr(10) not in typed[0] and chr(13) not in typed[0]


def test_her_ai_can_do_several_things_in_a_row():
    from capri.ai.openai_compat import OpenAIBrain
    calls = [{"id": "1", "type": "function", "function": {"name": "open_app", "arguments": '{"names": ["Notepad"]}'}},
             {"id": "2", "type": "function", "function": {"name": "type_text", "arguments": '{"text": "Hi, TikTok"}'}}]
    brain = OpenAIBrain(lambda: "openai", lambda: "", lambda: "", lambda: "key", {},
                        fetch=lambda *a, **k: {"choices": [{"message": {"content": "", "tool_calls": calls}}]})
    reply = brain.ask("open notepad and say hi to tiktok")
    assert [i.kind for i in reply.intents] == [Kind.OPEN, Kind.TYPE] and reply.intents[1].query == "Hi, TikTok"


@pytest.mark.parametrize("said", ["are you a virus", "is this a virus", "are you malware", "are you spying on me"])
def test_are_you_a_virus(said):
    from capri.chatbot import ChatBot
    bot = ChatBot()
    text, _emotion = bot.reply(said)
    assert bot.last_kind == "not_virus" and "open source" in text and "code" in text
