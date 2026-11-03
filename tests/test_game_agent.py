"""v2.0: she plays your game ("play this for me") - looks with the AI, moves with game-safe hands, Esc stops her."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ai.claude import AIReply  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations import game_agent as ga  # noqa: E402
from capri.integrations.game_hands import clean_key  # noqa: E402

WINDOW = ga.Rect(100, 50, 800, 600)


class Hands:
    def __init__(self, escape_after=None):
        self.did = []
        self.escape_after = escape_after

    def hold(self, key, seconds):
        self.did.append(("hold", key, seconds))

    def look(self, dx, dy):
        self.did.append(("look", dx, dy))

    def click(self, x, y, button="left", hold=0.0):
        self.did.append(("click", x, y, button, hold))

    def escape_pressed(self):
        return self.escape_after is not None and len(self.did) >= self.escape_after


class Brain:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def look(self, prompt, jpeg):
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else AIReply('{"say": "", "do": [], "done": true}')


def agent(brain, hands, foreground=lambda: 7, rect=WINDOW):
    said, done, cursor = [], [], []
    a = ga.GameAgent(brain, lambda: hands, lambda r: object(), foreground, lambda h: rect, said.append, done.append,
                     cursor=lambda x, y: cursor.append((x, y)), sleep=lambda s: None, jpeg=lambda img: "QUJD")
    return a, said, done, cursor


def test_she_plays_a_few_moves_and_says_so():
    brain = Brain(AIReply('Sure! {"say": "Heading for the tree.", "do": [{"key": "w", "hold": 1.2}, '
                          '{"look": [120, -20]}, {"click": [0.5, 0.5], "hold": 1.5}], "done": false}'),
                  AIReply('{"say": "Got the wood!", "do": [{"key": "space"}], "done": true}'))
    hands = Hands()
    a, said, done, cursor = agent(brain, hands)
    assert a.start("get some wood", background=False) == ""
    assert hands.did == [("hold", "w", 1.2), ("look", 120, -20), ("click", 100 + 400, 50 + 300, "left", 1.5),
                         ("hold", "space", 0.15)]
    assert cursor == [(500, 350)] and done == ["done"] and said[0] == "Heading for the tree."
    assert "get some wood" in brain.prompts[0] and "held w" in brain.prompts[1]          # she remembers her moves


@pytest.mark.parametrize("move", [{"key": "lwin"}, {"key": "alt"}, {"key": "return"}, {"key": "escape"},
                                  {"key": "f4"}, {"key": "ctrl+w"}, {"type": "hello"}, "w", {"click": "middle"}])
def test_she_cant_press_anything_dangerous(move):
    assert ga.checked(move, WINDOW) is None


def test_moves_are_kept_in_bounds():
    assert ga.checked({"key": "W", "hold": 60}, WINDOW) == ("key", "w", 3.0)
    assert ga.checked({"look": [9999, -9999]}, WINDOW) == ("look", 600, -600)
    assert ga.checked({"click": [2, -1], "button": "RIGHT"}, WINDOW) == ("click", 100 + 799, 50, "right", 0.0)
    assert ga.checked({"wait": 99}, WINDOW) == ("wait", 2.0)
    assert clean_key("Spacebar") == "space" and clean_key("super") is None


def test_escape_stops_her_at_once():
    brain = Brain(*[AIReply('{"do": [{"key": "w"}, {"key": "a"}, {"key": "s"}], "done": false}')] * 5)
    hands = Hands(escape_after=2)
    a, _s, done, _c = agent(brain, hands)
    a.start("walk", background=False)
    assert len(hands.did) == 2 and done == ["escape"]


def test_switching_away_stops_her():
    fg = iter([7, 7, 9, 9, 9, 9])
    brain = Brain(*[AIReply('{"do": [{"key": "w"}], "done": false}')] * 5)
    hands = Hands()
    a, _s, done, _c = agent(brain, hands, foreground=lambda: next(fg))
    a.start("walk", background=False)
    assert done == ["switched"] and len(hands.did) <= 1


def test_no_game_in_front():
    a, *_ = agent(Brain(), Hands(), foreground=lambda: 0)
    assert "game in front" in a.start("x", background=False)
    a, *_ = agent(Brain(), Hands(), rect=None)
    assert "game in front" in a.start("x", background=False)


def test_an_ai_that_cant_see_says_so():
    a, _s, done, _c = agent(Brain(AIReply("", error=True, missing=True)), Hands())
    a.start("x", background=False)
    assert done == ["no ai"] and "AI that can see" in ga.ending("no ai")


def test_a_rambling_answer_is_skipped_not_obeyed():
    brain = Brain(AIReply("I think you should press W."), AIReply('{"do": [{"key": "d"}], "done": true}'))
    hands = Hands()
    a, _s, done, _c = agent(brain, hands)
    a.start("x", background=False)
    assert hands.did == [("hold", "d", 0.15)] and done == ["done"]


def test_stops_after_five_minutes():
    t = [0.0]

    def clock():
        t[0] += 40
        return t[0]
    brain = Brain(*[AIReply('{"do": [{"wait": 1}], "done": false}')] * 50)
    a = ga.GameAgent(brain, Hands, lambda r: object(), lambda: 7, lambda h: WINDOW, lambda s: None,
                     (done := []).append, clock=clock, sleep=lambda s: None, jpeg=lambda i: "x")
    a.start("x", background=False)
    assert done == ["time"]


@pytest.mark.parametrize("text,goal", [("play this for me", ""), ("your turn", ""),
                                       ("take over and make me a pickaxe", "make me a pickaxe"),
                                       ("play this for me and get some wood", "get some wood")])
def test_what_starts_her(text, goal):
    intent = parse(text)
    assert intent.kind is Kind.PLAY_GAME and intent.query == goal


@pytest.mark.parametrize("text", ["stop playing the game", "my turn", "hands off", "let me play"])
def test_what_stops_her(text):
    assert parse(text).kind is Kind.STOP_GAME


def test_songs_and_games_still_mean_what_they_did():
    assert parse("play despacito").kind is Kind.PLAY
    assert parse("stop playing").kind is Kind.MEDIA                    # (pauses your music, as always)
    assert parse("play minecraft").kind is not Kind.PLAY_GAME


def test_off_until_you_say_yes():
    from test_stage5 import settle
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    r.router.services.settings = r.assistant.settings
    started = []
    r.router.services.game_agent = SimpleNamespace(start=lambda g: started.append(g) or "", running=False)
    r.assistant.settings.game_play = False
    r.router.handle("play this for me")
    assert settle(3, lambda: "Esc stops me" in r.controller.message)
    r.service.command.emit("yes")
    assert settle(5, lambda: started == [""] and r.assistant.settings.game_play)
