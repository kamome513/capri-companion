"""v1.26: typing where you say ("type hi in notepad" - opened first if needed, written straight into its
text box), the AI telling you why it isn't answering (no credit, bad key), and her own RAM."""

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

from capri.commands.catalog import ProcessInfo  # noqa: E402
from capri.commands.parser import Kind, parse, type_where  # noqa: E402


class TypingDesktop(FakeDesktop):
    """Windows by pid (pid 50 = Notepad's window 500), and where things got typed."""

    def __init__(self, how="typed"):
        super().__init__()
        self.typed, self.how = [], how

    def windows_for(self, pids):
        return [p * 10 for p in pids]

    def type_into(self, hwnd, text):
        self.typed.append((hwnd, text))
        return self.how


def _rig(processes=(), how="typed", front=None):
    d = TypingDesktop(how)
    r = rig(d, processes=[ProcessInfo(10, "Discord.exe"), *processes])
    r.router.services.front = lambda: front
    return r, d


# -- saying where ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("said, words, where", [
    ("type hi tiktok in notepad", "hi tiktok", "notepad"), ("Type Hi, TikTok in Notepad please", "Hi, TikTok", "notepad"),
    ("write gg into the discord chat", "gg", "discord"), ("type hello on discord", "hello", "discord"),
])
def test_where_to_type_comes_from_the_end(said, words, where):
    assert type_where(parse(said).query) == (words, where)


@pytest.mark.parametrize("said, words, where", [("in notepad type hi", "hi", "notepad"),
                                                ("on discord, write gg ez", "gg ez", "discord")])
def test_where_to_type_at_the_start(said, words, where):
    intent = parse(said)
    assert intent.kind is Kind.TYPE and intent.query == words and intent.targets == (where,)


def test_type_hello_there_keeps_there():
    assert parse("type hello there").query == "hello there"


def test_types_into_the_app_you_named_when_it_is_open():
    r, d = _rig([ProcessInfo(50, "Notepad.exe")], front=999)
    r.router.handle("type hi tiktok in notepad")
    assert settle(3, lambda: r.controller.state.value == "success")
    assert d.typed == [(500, "hi tiktok")]                              # Notepad's window, not the one in front
    assert r.controller.message == "Typed it in Notepad."


def test_not_a_place_so_it_is_all_words():
    r, d = _rig(front=777)
    r.router.handle("type I live in London")
    assert settle(3, lambda: r.controller.state.value == "success")
    assert d.typed == [(777, "I live in London")]


def test_opens_the_app_first_when_it_is_not_running():
    r, d = _rig(front=1)
    launched = r.system.launch_program

    def launch(path, args):                                            # Notepad starts when she opens it
        launched(path, args)
        r.system.procs[50] = ProcessInfo(50, "Notepad.exe")
    r.system.launch_program = launch
    r.system.open_item = lambda target: launch(str(target), [])
    r.router.handle("type hi tiktok in notepad")
    assert r.speaker.lines[-1] == "Wait a second while I open Notepad and type that in."
    assert settle(12, lambda: r.controller.message.startswith("Alright"))
    assert d.typed == [(500, "hi tiktok")]
    assert r.controller.message == "Alright, Notepad is open and your message is typed."


def test_open_then_type_goes_into_what_she_opened():
    r, d = _rig([ProcessInfo(50, "Notepad.exe")], front=1)              # the window in front isn't Notepad
    r.router.handle("Open Notepad and type Hi, TikTok.")
    assert settle(12, lambda: r.controller.message.startswith("Alright"))
    assert d.typed == [(500, "Hi, TikTok.")]


def test_type_with_no_place_goes_into_the_window_in_front():
    r, d = _rig(front=321)
    r.router.handle("type good morning")
    assert settle(3, lambda: r.controller.state.value == "success")
    assert d.typed == [(321, "good morning")] and r.controller.message == "Typed it."


def test_no_window_to_type_in_is_said():
    r, d = _rig(front=None)
    r.router.handle("type good morning")
    assert r.controller.state.value == "error" and "no window" in r.controller.message
    assert d.typed == []


@pytest.mark.parametrize("how, says", [("no_focus", "didn't type anything"), ("blocked", "administrator")])
def test_typing_problems_are_said_honestly(how, says):
    r, d = _rig([ProcessInfo(50, "Notepad.exe")], how=how)
    r.router.handle("type hi in notepad")
    assert settle(3, lambda: r.controller.state.value == "error")
    assert says in r.controller.message


# -- the AI says why it isn't answering ---------------------------------------------------------------------
def _ai_rig(reply):
    from capri.settings import Settings

    class Brain:
        asked = []

        def ask(self, text):
            Brain.asked.append(text)
            return reply

        def which(self):
            return "openai"
    return rig(FakeDesktop(), settings=Settings(ai_enabled=True, slang=False), brain=Brain()), Brain


def test_no_credit_is_said_not_hidden():
    from capri.ai.claude import AIReply
    from capri.states import State
    r, _ = _ai_rig(AIReply("My ChatGPT key has no credit.", error=True))
    r.service.command.emit("tell me a joke")
    assert settle(2, lambda: r.controller.state is State.ERROR)
    assert r.controller.message.startswith("My ChatGPT key has no credit.")
    r.service.command.emit("tell me another joke")                      # not every time: her own chat meanwhile
    assert settle(2, lambda: r.controller.state is State.SPEAKING)


def test_settings_test_button_reports_what_really_happened():
    from capri.ai.claude import AIReply
    r, _ = _ai_rig(AIReply("[happy] Hey you!", emotion="happy"))
    got = []
    r.router.test_ai(got.append)
    assert settle(2, lambda: bool(got))
    assert got[0].startswith("Working (openai)")
    r, _ = _ai_rig(AIReply("My ChatGPT key doesn't work.", error=True))
    got = []
    r.router.test_ai(got.append)
    assert settle(2, lambda: bool(got)) and got[0] == "My ChatGPT key doesn't work."


def test_openai_quota_explains_billing():
    from capri.ai.openai_compat import OpenAIBrain
    from capri.integrations.http import HttpError

    def fetch(*a, **k):
        raise HttpError(429, '{"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}')
    brain = OpenAIBrain(lambda: "openai", lambda: "", lambda: "gpt-5-nano", lambda: "sk-x", {}, fetch=fetch)
    text = brain.ask("hi").text
    assert "no credit" in text and "ChatGPT Plus" in text


# -- "call me ..." was taken out again (v1.29: you asked her to stop) ---------------------------------------------
def test_she_never_calls_you_good_boy():
    from capri.ai.claude import system_prompt
    r = rig(FakeDesktop())
    r.router.handle("call me good boy")
    assert not hasattr(r.assistant.settings, "call_me")
    r.assistant.show_result(r.controller.state.__class__.SUCCESS, "Typed it in Notepad.")
    assert r.controller.message == "Typed it in Notepad."
    assert "good boy" not in system_prompt(False, "edgerunner").lower()


# -- her own RAM / CPU -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["how much ram are you using", "how much cpu are you using", "what are your stats",
                                  "hey capri how much memory are you taking up", "how heavy are you"])
def test_asking_about_her_own_usage(said):
    intent = parse(said)
    assert intent.kind is Kind.PC_INFO and intent.query == "self"


@pytest.mark.parametrize("said", ["how much ram am i using", "whats using all my ram"])
def test_asking_about_the_pc_is_still_the_pc(said):
    assert parse(said).query == "ram"


def test_own_usage_adds_up_her_helpers():
    from types import SimpleNamespace

    from capri.integrations import pc_stats

    class Proc:
        def __init__(self, mb, cpu, kids=()):
            self.mb, self.cpu, self.kids = mb, cpu, list(kids)

        def children(self, recursive=False):
            return self.kids

        def cpu_percent(self, _):
            return self.cpu

        def memory_info(self):
            return SimpleNamespace(rss=self.mb * 1024 ** 2)
    me = Proc(180, 8.0, [Proc(40, 0.0)])
    ps = SimpleNamespace(Process=lambda pid: me, cpu_count=lambda: 8)
    assert pc_stats.own_usage(ps, sleep=lambda s: None) == (220 * 1024 ** 2, 1.0, 2)
    line = pc_stats.own_report(ps, sleep=lambda s: None)
    assert line == "I'm using 220 megabytes of RAM and 1 percent of your CPU right now, across 2 processes."
