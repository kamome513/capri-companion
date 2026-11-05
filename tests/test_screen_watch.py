"""v1.39: watch my screen - she glances at it now and then and comments (picture -> your AI), "what do you see?",
and the Extras welcome."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from capri.ai.claude import AIReply  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations import screen_watch as sw  # noqa: E402
from capri.settings import Settings  # noqa: E402


def picture(w=2560, h=1440) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(30, 120, 200))
    return img


class Brain:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = []

    def look(self, prompt, jpeg):
        self.asked.append((prompt, jpeg))
        return self.replies.pop(0) if self.replies else AIReply("SKIP")


def watcher(brain, title="Minecraft", settings=None, memory=None):
    said, notices = [], []
    clock = [1000.0]
    s = settings or Settings(watch_screen=True, watch_every=120, watch_remember=True)
    w = sw.ScreenWatch(s, brain, picture, lambda: title, lambda text, emotion: said.append((text, emotion)),
                       memory=memory or sw.SeenMemory(None), notice=notices.append, clock=lambda: clock[0],
                       background=False)
    return w, said, notices, clock


# -- the picture ------------------------------------------------------------------------------------------------
def test_the_picture_is_a_small_jpeg():
    data = base64.b64decode(sw.to_jpeg_b64(picture()))
    img = QImage.fromData(data, "JPEG")
    assert data[:2] == b"\xff\xd8" and img.width() == sw.MAX_WIDTH and img.height() == 720
    assert sw.to_jpeg_b64(QImage()) == ""


@pytest.mark.parametrize("title,private", [
    ("Bitwarden", True), ("Sign in - Google Accounts", True), ("New Incognito Tab", True), ("My Bank - Login", True),
    ("Minecraft 1.21", False), ("YouTube - Mozilla Firefox", False), ("", False),
])
def test_she_doesnt_look_at_private_things(title, private):
    assert sw.is_private(title) is private


@pytest.mark.parametrize("text,line", [("SKIP", ""), ("skip.", ""), ('"Ooh, a new world?"', "Ooh, a new world?"),
                                       ("", ""), ("SKIP - nothing new", "")])
def test_skip_means_say_nothing(text, line):
    assert sw.cleaned(text) == line


# -- now and then -------------------------------------------------------------------------------------------------
def test_she_glances_and_comments_every_couple_of_minutes():
    brain = Brain(AIReply("Diamond pickaxe already? Show-off.", emotion="playful"))
    w, said, _n, clock = watcher(brain)
    w.tick()
    assert not brain.asked                                      # not yet: two minutes from start
    clock[0] += 121
    w.tick()
    assert said == [("Diamond pickaxe already? Show-off.", "playful")]
    prompt, jpeg = brain.asked[0]
    assert "SKIP" in prompt and "private" in prompt and base64.b64decode(jpeg)[:2] == b"\xff\xd8"
    clock[0] += 30
    w.tick()
    assert len(brain.asked) == 1                                # and not again straight away


def test_nothing_to_say_is_silence():
    w, said, _n, clock = watcher(Brain(AIReply("SKIP")))
    clock[0] += 200
    w.tick()
    assert said == []


def test_a_private_window_isnt_looked_at():
    brain = Brain(AIReply("hi"))
    w, said, _n, clock = watcher(brain, title="KeePassXC - Passwords.kdbx")
    clock[0] += 200
    w.tick()
    assert brain.asked == [] and said == []


def test_off_means_no_looking():
    brain = Brain()
    w, said, _n, clock = watcher(brain, settings=Settings(watch_screen=False))
    clock[0] += 9999
    w.tick()
    assert brain.asked == []


def test_she_remembers_and_follows_on(tmp_path):
    memory = sw.SeenMemory(tmp_path / "seen.json")
    brain = Brain(AIReply("Building a castle?"), AIReply("Still on that castle, huh."))
    w, said, _n, clock = watcher(brain, memory=memory)
    clock[0] += 200
    w.tick()
    clock[0] += 200
    w.tick()
    assert "Building a castle?" in brain.asked[1][0]            # the second look knows the first
    assert [t for _ts, t in sw.SeenMemory(tmp_path / "seen.json").items] == ["Building a castle?",
                                                                            "Still on that castle, huh."]


def test_no_ai_or_a_blind_one_is_told_once():
    blind = AIReply("llama3.2 can't see pictures. Try: ollama pull gemma3", error=True, blind=True)
    brain = Brain(AIReply("", error=True, missing=True), AIReply("", error=True, missing=True), blind, blind)
    w, said, notices, clock = watcher(brain)
    for _ in range(3):
        clock[0] += 2000                                        # (she backs off after each problem)
        w.tick()
    assert said == [] and len(notices) == 2 and "need an AI that can see" in notices[0] and "gemma3" in notices[1]


# -- on request ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["what do you see", "look at my screen", "what am i doing", "what's on my screen",
                                  "hey capri what do you think of this", "can you see my screen"])
def test_what_do_you_see(text):
    assert parse(text).kind is Kind.LOOK


def test_watch_my_screen_by_voice():
    assert parse("watch my screen").kind is Kind.WATCH and parse("watch my screen").query == "on"
    assert parse("stop watching my screen").query == "off"


def test_asking_answers_your_question():
    brain = Brain(AIReply("A crafting table - put 3 diamonds on top, 2 sticks down the middle."))
    w, _said, _n, _c = watcher(brain)
    got = []
    w.ask("how do I make a pickaxe", lambda text, emo: got.append(text))
    assert "crafting table" in got[0] and "how do I make a pickaxe." in brain.asked[0][0]


def test_asking_with_no_ai_says_how_to_get_one():
    w, _s, _n, _c = watcher(Brain(AIReply("", error=True, missing=True)))
    got = []
    w.ask("what do you see", lambda text, emo: got.append(text))
    assert "Pick one in my Settings" in got[0]


def test_the_router_shows_her_answer():
    from test_v11 import FakeDesktop, rig
    r = rig(FakeDesktop())
    r.router.services.screen_watch = SimpleNamespace(ask=lambda q, then: then("Ooh, Minecraft.", "happy"))
    r.router.handle("what do you see")
    assert r.controller.message == "Ooh, Minecraft."
    r.router.services.settings = r.assistant.settings
    r.router.handle("watch my screen")
    assert r.assistant.settings.watch_screen is True and "Watching" in r.controller.message


# -- every AI can look -----------------------------------------------------------------------------------------------
def test_openai_style_ais_get_the_picture_as_an_image_url():
    from capri.ai.openai_compat import OpenAIBrain
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        sent.append((url, json_body, headers))
        return {"choices": [{"message": {"content": "[happy] Nice build!"}}]}
    brain = OpenAIBrain(lambda: "gemini", lambda: "", lambda: "", lambda: "key", {}, fetch=fetch)
    reply = brain.look("what is it", "QUJD")
    url, body, headers = sent[0]
    parts = body["messages"][1]["content"]
    assert url.endswith("/chat/completions") and headers["Authorization"] == "Bearer key"
    assert parts[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}}
    assert "tools" not in body and reply.text == "Nice build!" and reply.emotion == "happy"


def test_a_model_that_cant_see_is_said_plainly():
    from capri.ai.openai_compat import OpenAIBrain
    from capri.integrations import http

    def fetch(method, url, json_body=None, headers=None, timeout=None):
        raise http.HttpError(400, '{"error": {"message": "This model does not support image input"}}')
    reply = OpenAIBrain(lambda: "groq", lambda: "", lambda: "llama-3.1-8b-instant", lambda: "k", {},
                        fetch=fetch).look("hi", "QUJD")
    assert reply.error and reply.blind and "can't see pictures" in reply.text


def test_ollama_gets_the_picture_in_images():
    from capri.ai.local import LocalBrain
    sent = []

    def fetch(method, url, json_body=None, timeout=None, **k):
        sent.append(json_body)
        return {"message": {"content": "Cute cat."}}
    brain = LocalBrain(lambda: "http://127.0.0.1:11434", lambda: "gemma3", {}, fetch=fetch)
    brain.chosen = "gemma3"
    assert brain.look("what", "QUJD").text == "Cute cat."
    assert sent[0]["messages"][1]["images"] == ["QUJD"]


def test_claude_gets_a_base64_image_block():
    from capri.ai.claude import ClaudeBrain
    calls = []

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Looks fun.")])
    client = SimpleNamespace(beta=SimpleNamespace(messages=Messages()))
    brain = ClaudeBrain(lambda: "sk-ant-x", {}, client_factory=lambda key: client)
    assert brain.look("what", "QUJD").text == "Looks fun."
    block = calls[0]["messages"][0]["content"][0]
    assert block == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}}
    assert "tools" not in calls[0] and calls[0]["fallbacks"] == "default"


def test_brains_without_any_ai():
    from capri.ai.local import Brains
    brains = Brains(Settings(ai_provider="auto"), SimpleNamespace(has_key=lambda: False),
                    SimpleNamespace(available=lambda: (False, "no")))
    assert brains.look("hi", "x").missing


# -- Settings -> Extras (it used to be a welcome screen) ----------------------------------------------------------------
def test_the_extras_tab_turns_on_what_you_pick():
    from test_stage5 import settle
    from capri.ui.extras_tab import ExtrasTab
    s = Settings(watch_screen=False, clips=False, roaming=True, throwable=True, show_panel=True, panel_popup=False)
    s.save = lambda: None
    saved, turned = [], []

    def turn_on(progress):
        turned.append(1)
        s.clips = True
    tab = ExtrasTab(s, lambda: saved.append(1), turn_on)
    tab.watch_on.setChecked(True)
    tab.roam.setChecked(False)
    tab.clip_on.setChecked(True)
    tab.panel_mode.setCurrentIndex(tab.panel_mode.findData("popup"))
    tab.glitch_every.setCurrentIndex(tab.glitch_every.findData(0))
    tab.apply()
    assert settle(3, lambda: turned and s.clips)
    assert s.watch_screen and not s.roaming and saved and s.show_panel and s.panel_popup and s.glitches == 0
    tab.panel_mode.setCurrentIndex(tab.panel_mode.findData("never"))
    tab.apply()
    assert not s.show_panel


def test_no_welcome_screen_any_more():
    import importlib.util
    assert importlib.util.find_spec("capri.ui.extras") is None
