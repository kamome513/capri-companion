"""v1.17: "preem" said "pr-e-mm", a chatbot that always answers, personalities, the new shutdown
question, "what's using all my RAM", screenshots, and search mode in inverted colours."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri import personality  # noqa: E402
from capri.chatbot import ChatBot, solve  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402


# -- "preem" ----------------------------------------------------------------------------------------------
def test_preem_is_said_pr_eeee_mm():
    from capri.speech.pronounce import WORDS, respell, sapi_xml
    assert respell("That's preem, choom.") == "That's preme, choom."          # one syllable for other voices
    assert WORDS["preem"][1] == "p r iy 1 m"                                     # a long "ee"...
    assert sapi_xml("so preem") == 'so <rate speed="-2"><pron sym="p r iy 1 m"/></rate>'   # ...said slowly
    assert '<rate' not in sapi_xml("choom")                                      # only that word


# -- the chatbot -----------------------------------------------------------------------------------------
ANYTHING = ["hi", "my name is sam", "what's my name", "i like deadlock", "do you like cats",
            "what's your favorite color", "i'm stressed", "whats 12 times 8", "can you order pizza",
            "can you open steam", "who won the world cup", "you're so stupid", "you're cute", "why is the sky blue",
            "i went to the shops today and bought a bike", "asdf qwerty", "ok", "no", "teach me quantum physics",
            "what do i like", "tell me a fun fact", "are you real", "sorry", "i'm hyped", "thanks", "bye", ""]


@pytest.mark.parametrize("persona", list(personality.PERSONALITIES))
def test_she_always_has_a_reply(persona):
    bot = ChatBot(rng=random.Random(3))
    for text in ANYTHING:
        words, emotion = bot.reply(text, persona, slang=True)
        assert words.strip() and emotion and "{" not in words, (persona, text, words)


def test_she_remembers_you_and_does_maths():
    bot = ChatBot(rng=random.Random(1))
    assert "Sam" in bot.reply("my name is sam")[0]
    assert "Sam" in bot.reply("what's my name")[0]
    bot.reply("i really like deadlock")
    assert "deadlock" in bot.reply("what do i like")[0].lower()
    assert "96" in bot.reply("whats 12 times 8")[0]
    assert solve("what s 7 plus 5") == "12" and solve("ten divided by four") == "2.5" and solve("hi there") is None


def test_she_is_honest_about_what_she_cant_do():
    bot = ChatBot(rng=random.Random(2))
    yes = bot.reply("can you open steam", "edgerunner", slang=False)[0]
    assert "open steam" in yes                                         # tells you how to say it
    no = bot.reply("can you order pizza", "edgerunner", slang=False)[0]
    assert "pizza" not in no.lower() and ("can't" in no or "Not that one" in no)
    unknown = bot.reply("who won the world cup", "edgerunner", slang=False)[0]
    assert "look it up" in unknown or "search" in unknown              # no made-up answer: offers to look it up


def test_without_an_ai_she_chats_instead_of_not_getting_it():
    r = rig(FakeDesktop())
    r.service.command.emit("i went to the shops and bought a bike")
    assert settle(2, lambda: r.controller.state is State.SPEAKING and r.speaker.lines)
    assert r.controller.message != "Not sure what you mean."


def test_when_the_ai_errors_her_own_chat_answers():
    from capri.ai.claude import AIReply

    class Broken:
        def ask(self, text):
            return AIReply("Can't reach the AI right now.", error=True)
    r = rig(FakeDesktop(), settings=Settings(ai_enabled=True, slang=False), brain=Broken())
    r.service.command.emit("i'm feeling great today")
    assert settle(2, lambda: r.controller.state is State.ERROR)      # first: why the AI isn't answering (v1.26)
    assert r.controller.message.startswith("Can't reach the AI right now.")
    r.service.command.emit("i'm feeling great today")
    assert settle(2, lambda: r.controller.state is State.SPEAKING)    # then her own chat, without repeating it
    assert "AI" not in r.controller.message


# -- personalities -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, key", [
    ("be sarcastic", "sarcastic"), ("be more silly", "silly"), ("change your personality to tsundere", "tsundere"),
    ("act like a tsundere", "tsundere"), ("be sweet", "sweet"), ("switch to deadpan mode", "deadpan"),
    ("go back to normal", "edgerunner"), ("be yourself again", "edgerunner"),
])
def test_personality_commands(text, key):
    intent = parse(text)
    assert intent.kind is Kind.PERSONALITY and intent.targets == (key,)


def test_old_phrases_keep_their_meaning():
    assert parse("switch to normal mode").kind is Kind.COMPACT_OFF
    assert parse("normal mode").kind is Kind.DRONE_OFF
    assert parse("whats your personality").kind is Kind.PERSONALITY


def test_switching_personality():
    s = Settings(slang=False)
    r = rig(FakeDesktop(), settings=s)
    r.service.command.emit("be tsundere")
    assert s.personality == "tsundere" and "tsundere" in r.speaker.lines[-1].lower()
    r.service.command.emit("hello")
    assert settle(2, lambda: r.controller.state is State.SPEAKING)
    assert r.controller.message == personality_bank("hello", "tsundere")
    assert Settings.load().personality == "tsundere"


def personality_bank(kind, key):
    from capri.chatbot import BANK
    return BANK[kind][key][0][1]


def test_remarks_after_commands_only_in_other_personalities():
    rng = random.Random(4)
    assert all(personality.flavor("Opened Discord.", "edgerunner", rng) == "Opened Discord." for _ in range(50))
    flavored = {personality.flavor("Opened Discord.", "tsundere", rng) for _ in range(50)}
    assert "Opened Discord." in flavored and any(f != "Opened Discord." for f in flavored)
    assert "!" not in personality.flavor("Done!", "deadpan", rng)


def test_the_ai_gets_her_personality_and_new_tools():
    from capri.ai.claude import TOOLS, system_prompt, to_intent
    assert personality.get("tsundere").prompt in system_prompt(False, "tsundere")
    assert personality.get("edgerunner").prompt in system_prompt(False)
    names = {t["name"] for t in TOOLS}
    assert {"get_pc_stats", "take_screenshot", "set_personality"} <= names
    assert to_intent("take_screenshot", {"what": "window"}).query == "window"
    assert to_intent("set_personality", {"personality": "silly"}).targets == ("silly",)


# -- the shutdown question -------------------------------------------------------------------------------------
def test_shutdown_asks_if_we_can_make_it():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("shut down my pc")
    assert r.speaker.lines[-1] == "Look up there, think we can make it?" and d.calls == []
    r.service.command.emit("yes")
    assert d.calls == [("power", "shutdown")]


# -- PC info -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, topic", [
    ("hey capri what is using up all my ram", "ram"), ("how am i using 10 gb of ram right now", "ram"),
    ("whats eating my memory", "ram"), ("why is my cpu so high", "cpu"), ("how much storage do i have left", "disk"),
    ("how long has my pc been on", "uptime"), ("whats my battery", "battery"), ("why is my computer so slow", "overview"),
])
def test_pc_questions(text, topic):
    intent = parse(text)
    assert intent.kind is Kind.PC_INFO and intent.query == topic


class FakePsutil:
    class P:
        def __init__(self, pid, name, rss, cpu=0.0):
            self.pid, self.info = pid, {"name": name, "memory_info": SimpleNamespace(rss=rss)}
            self._cpu = cpu

        def cpu_percent(self, interval=None):
            return self._cpu

    def __init__(self):
        g = 1024 ** 3
        self.procs = [self.P(1, "opera.exe", 1.5 * g, 40), self.P(2, "opera.exe", 1.6 * g, 20),
                      self.P(3, "Discord.exe", 0.9 * g, 4), self.P(4, "deadlock.exe", 2.2 * g, 80),
                      self.P(5, "System Idle Process", 0, 0)]

    def virtual_memory(self):
        g = 1024 ** 3
        return SimpleNamespace(total=16 * g, available=6 * g)

    def process_iter(self, attrs):
        return iter(self.procs)

    def cpu_percent(self, interval=None):
        return 37.0

    def cpu_count(self):
        return 8


def test_what_is_using_my_ram():
    from capri.integrations import pc_stats
    line = pc_stats.memory_report(FakePsutil())
    assert line.startswith("You're using 10.0 GB of 16.0 GB of RAM, 62 percent.")
    assert "Opera GX 3.1 GB" in line and line.index("Opera GX") < line.index("Deadlock")   # grouped, biggest first


def test_whats_using_my_cpu():
    from capri.integrations import pc_stats
    line = pc_stats.cpu_report(FakePsutil(), sleep=lambda s: None)
    assert line.startswith("Your CPU is at 37 percent.") and "Deadlock 10 percent" in line   # like Task Manager


def test_she_answers_pc_questions():
    asked = []
    r = rig(FakeDesktop(), pc_info=lambda topic: (asked.append(topic), "You're using 10 GB.")[1])
    r.service.command.emit("what is using all my ram")
    assert settle(2, lambda: r.controller.message == "You're using 10 GB.")
    assert asked == ["ram"]


# -- screenshots ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, which", [("take a screenshot", "screen"), ("screenshot", "screen"),
                                         ("capri take a screenshot please", "screen"),
                                         ("take a screenshot of this window", "window"),
                                         ("screenshot this window", "window")])
def test_screenshot_commands(text, which):
    intent = parse(text)
    assert intent.kind is Kind.SCREENSHOT and intent.query == which


class Win:
    def __init__(self):
        self.visible, self.log = True, []

    def isVisible(self):
        return self.visible

    def hide(self):
        self.visible = False
        self.log.append("hide")

    def show(self):
        self.visible = True
        self.log.append("show")


def test_a_screenshot_is_saved_without_her_in_it(tmp_path):
    from capri.ui.screenshot import Screenshotter
    her = Win()
    seen = []

    def grab(rect):
        seen.append(her.visible)                 # she's out of the picture while it's taken
        return np.full((20, 30, 3), 200, np.uint8)
    shooter = Screenshotter(lambda: [her], window_rect=lambda: (0, 0, 30, 20), grab=grab,
                            folder=lambda: tmp_path / "Screenshots", clipboard=False)
    results = []
    shooter.take("window", results.append)
    assert settle(3, lambda: results)
    path = results[0]
    assert isinstance(path, Path) and path.exists() and path.parent.name == "Screenshots"
    assert QImage(str(path)).size().toTuple() == (30, 20)
    assert seen == [False] and her.log == ["hide", "show"]


def test_she_says_where_the_screenshot_went():
    r = rig(FakeDesktop(), screenshot=lambda which, done: done(Path("C:/Pictures/Screenshots/shot.png")))
    r.service.command.emit("take a screenshot")
    assert settle(2, lambda: "Screenshots" in r.controller.message)


# -- search mode: inverted ------------------------------------------------------------------------------------------
def test_search_mode_inverts_her_panel():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings())
    c.show()
    app.processEvents()
    c.controller.set_state(State.IDLE, "Standing by.")
    normal = c.panel.grab().toImage()
    c.set_search_mode(True)
    inverted = c.panel.grab().toImage()
    x, y = normal.width() // 2, normal.height() // 2
    a, b = normal.pixelColor(x, y), inverted.pixelColor(x, y)
    assert abs((a.red() + b.red()) - 255) <= 3 and abs((a.blue() + b.blue()) - 255) <= 3
    c.set_search_mode(False)
    assert not c.panel.inverted


def test_the_router_turns_search_mode_colours_on_and_off():
    calls = []
    r = rig(FakeDesktop())
    r.router.companion.set_search_mode = calls.append
    r.service.command.emit("go into search mode")
    assert calls and calls[-1] is True
    r.service.command.emit("stop")
    assert settle(2, lambda: calls[-1] is False)


# -- designs ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("style", ["portrait", "classic", "look:Grin"])
def test_picking_another_design_gets_her_up(style):
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    s = Settings(lounge=True)
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), s,
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    assert c.character.mode == "lying"
    c.set_style(style)
    expected = {"portrait": "portrait", "classic": "classic"}.get(style, "look")
    assert c.character.mode == expected and not s.lounge          # straight to the design, no extra click
    c.set_style("body")
    assert c.character.mode == "body"
