"""v1.18: stutters sounded out, an energetic voice, hands on your screen, clicking what you
meant ("1000-7", ".mp3"), "repeat what I said", "go to the bottom left", fixing her AI brain,
tabs that switch (not right-click), and a cyberpunk chat window with skins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri import personality  # noqa: E402
from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations.screen_targets import Target, name_score  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402


# -- stutters and energy ------------------------------------------------------------------------------------
def test_stutters_are_sounded_out():
    from capri.speech.pronounce import respell, sapi_xml
    assert respell("W-what?! D-don't thank me.") == "Wuh... what?! Duh... don't thank me."
    assert respell("I-it's not like that") == "Ih... it's not like that"
    xml = sapi_xml("B-baka.")
    assert xml.startswith('<pron sym="b ah"/><silence msec="140"/>baka')
    assert respell("my e-mail and T-shirt") == "my e-mail and T-shirt"          # real hyphenated words stay


@pytest.mark.parametrize("key", list(personality.PERSONALITIES))
def test_every_personality_sounds_energetic(key):
    from capri.speech.speaker import prosody
    plain = Settings()
    plain.personality = key
    speed, pitch, _gain = prosody(plain, "neutral")
    lift, brighter = personality.get(key).voice
    assert lift > 0 and -3 <= brighter <= 6
    assert speed == pytest.approx(min(1.0, plain.speech_speed + lift))


def test_the_ai_is_told_to_be_energetic():
    from capri.ai.claude import system_prompt
    for key in personality.PERSONALITIES:
        assert personality.ENERGY in system_prompt(False, key)


# -- clicking what you meant ------------------------------------------------------------------------------
@pytest.mark.parametrize("said, name, good", [
    ("one thousand minus seven", "1000-7", True), ("1000 7", "1000-7", True), ("1000 7", "1000-7 Playlist • you", True),
    ("dot mp three", ".mp3", True), ("dot m p three", ".mp3 Playlist", True), ("dot mp3 playlist", ".mp3", True),
    ("mp3", ".mp3", True), ("subscribe", "Subscribe", True), ("seven", "1000-7", False), ("play", "Playlist settings", False),
])
def test_clicking_tries_how_it_might_be_written(said, name, good):
    assert (name_score(said, name) >= 0.78) is good


def test_click_1000_7_is_a_click():
    assert parse("click 1000-7").targets == ("1000 7",)
    assert parse("click one thousand minus seven").kind is Kind.CLICK


# -- tabs switch, list items get a real click, swapped mouse buttons -------------------------------------
class Pattern:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def QueryInterface(self, _iface):
        return self

    def Select(self):
        self.log.append("select")

    def Invoke(self):
        self.log.append("invoke")


class Element:
    def __init__(self, patterns):
        self.patterns, self.log = patterns, []

    def GetCurrentPattern(self, pid):
        from capri.integrations.uia import INVOKE_PATTERN, SELECTION_ITEM_PATTERN
        name = {INVOKE_PATTERN: "invoke", SELECTION_ITEM_PATTERN: "select"}.get(pid)
        return Pattern(self.log, name) if name in self.patterns else None


@pytest.fixture
def fake_uia(monkeypatch):
    import types
    gen = types.ModuleType("comtypes.gen")
    gen.UIAutomationClient = types.SimpleNamespace(IUIAutomationSelectionItemPattern=1, IUIAutomationInvokePattern=2,
                                                   IUIAutomationTogglePattern=3)
    monkeypatch.setitem(sys.modules, "comtypes", types.ModuleType("comtypes"))
    monkeypatch.setitem(sys.modules, "comtypes.gen", gen)


def test_a_tab_is_selected_not_pressed(fake_uia):
    from capri.integrations.screen_targets import click
    from capri.integrations.uia import TAB_ITEM, _Button
    el = Element({"invoke", "select"})
    tab = _Button(el, "Twitch", (0, 0, 100, 30), TAB_ITEM)
    mouse = []
    click(Target("Twitch", tab.rect, "ui", tab), lambda x, y: mouse.append((x, y)))
    assert el.log == ["select"] and mouse == []                     # never its "press" (that opened a menu)


def test_a_playlist_gets_a_real_left_click(fake_uia):
    from capri.integrations.screen_targets import click
    from capri.integrations.uia import _Button
    el = Element({"invoke", "select"})
    item = _Button(el, "1000-7", (0, 100, 200, 140), 50007)          # a list item, like Spotify's sidebar
    mouse = []
    click(Target("1000-7", item.rect, "ui", item), lambda x, y: mouse.append((x, y)))
    assert el.log == [] and mouse == [(100, 120)]


def test_swapped_mouse_buttons_still_left_click(monkeypatch):
    from capri.integrations import screen_click as sc
    monkeypatch.setattr(sc, "buttons_swapped", lambda: True)
    assert sc.button_events("left") == sc.RIGHT_EVENTS                # Windows swaps it back: a real left click
    assert sc.button_events("right") == sc.LEFT_EVENTS
    monkeypatch.setattr(sc, "buttons_swapped", lambda: False)
    assert sc.button_events("left") == sc.LEFT_EVENTS


# -- hands on your screen --------------------------------------------------------------------------------
@pytest.mark.parametrize("text, action, target", [
    ("highlight the word deadline", "highlight", "deadline"), ("select the text hello world", "highlight", "hello world"),
    ("copy the word password", "copy", "password"), ("double click readme", "double_click", "readme"),
    ("right click the desktop", "right_click", "desktop"), ("scroll down", "scroll_down", ""),
    ("select all", "select_all", None), ("undo", "undo", None), ("refresh the page", "refresh", None),
    ("zoom in", "zoom_in", None), ("close this tab", "close_tab", None),
])
def test_screen_commands(text, action, target):
    intent = parse(text)
    assert intent.kind is Kind.SCREEN and intent.query == action
    if target is not None:
        assert intent.targets[0] == target


class Finder:
    def __init__(self, target):
        self.target, self.asked = target, []

    def find_text(self, label):
        self.asked.append(("text", label))
        return self.target

    def find(self, label):
        self.asked.append(("ui", label))
        return self.target


class Hands:
    def __init__(self):
        self.done = []

    def select(self, t):
        self.done.append(("select", t.name))

    def double(self, t):
        self.done.append(("double", t.name))

    def right(self, t):
        self.done.append(("right", t.name))

    def scroll(self, n):
        self.done.append(("scroll", n))


def hands_rig(target=Target("deadline", (10, 10, 80, 30), "text")):
    d, hands, zaps = FakeDesktop(), Hands(), []
    r = rig(d, screen=Finder(target), hands=hands, zap_rect=lambda rect, then: (zaps.append(rect), then()))
    return r, d, hands, zaps


def test_she_highlights_words_on_screen():
    r, d, hands, zaps = hands_rig()
    r.service.command.emit("highlight the word deadline")
    assert settle(2, lambda: hands.done)
    assert hands.done == [("select", "deadline")] and zaps == [(10, 10, 80, 30)]
    assert r.router.services.screen.asked == [("text", "deadline")]     # read off the screen (any text)


def test_copy_highlights_then_copies():
    r, d, hands, zaps = hands_rig()
    r.service.command.emit("copy the word deadline")
    assert settle(2, lambda: ("keys", "ctrl+c") in d.calls)
    assert hands.done == [("select", "deadline")]


def test_key_actions_and_scrolling():
    r, d, hands, zaps = hands_rig()
    r.service.command.emit("select all")
    r.service.command.emit("zoom in")
    assert d.calls[-2:] == [("keys", "ctrl+a"), ("keys", "ctrl+plus")]
    r.service.command.emit("scroll down a lot")
    assert settle(2, lambda: hands.done == [("scroll", -15)])


def test_nothing_found_is_said_plainly():
    r, d, hands, zaps = hands_rig(target=None)
    r.service.command.emit("highlight the word unicorn")
    assert settle(2, lambda: "unicorn" in r.controller.message and r.controller.state is State.ERROR)
    assert hands.done == []


# -- repeat --------------------------------------------------------------------------------------------------
def test_repeat_what_i_said_and_after_me():
    r = rig(FakeDesktop())
    r.router.handle("open discord")
    r.router.handle("repeat what i said")
    assert "open discord" in r.controller.message
    r.router.handle("repeat after me I am the best")
    assert r.controller.message.lower() == "i am the best"
    r.router.handle("say that again")
    assert r.controller.message.lower() == "i am the best"


# -- moving her by voice ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, spot", [
    ("hey capri go to the bottom left", "bottom_left"), ("go to the top right", "top_right"),
    ("move to the left", "bottom_left"), ("go to the middle", "middle"), ("teleport to my other monitor", "other_screen"),
    ("go home", "bottom_right"),
])
def test_move_commands(text, spot):
    intent = parse(text)
    assert intent.kind is Kind.MOVE and intent.targets == (spot,)


def companion():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), Settings(),
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    app.processEvents()
    return c


def test_she_teleports_to_each_corner():
    c = companion()
    area = c.screen.availableGeometry()
    assert c.move_to("bottom_left")
    body = c.content_geometry()
    assert body.left() - area.left() <= 4 and area.bottom() - body.bottom() <= 4
    assert c.move_to("top_right")
    body = c.content_geometry()
    assert area.right() - body.right() <= 4 and body.top() - area.top() <= 4
    assert c.move_to("middle")
    assert abs(c.content_geometry().center().x() - area.center().x()) <= 4
    assert c.move_to("bottom_right")
    assert c.settings.position.right <= 4
    assert c.move_to("other_screen") is (len(QGuiApplication.screens()) > 1)


def test_the_drone_flies_there_instead():
    c = companion()
    c.set_drone(True)
    assert c.move_to("bottom_left")
    area = c.screen.availableGeometry()
    assert c.drone_window.geometry().left() <= area.left() + 8
    c.set_drone(False)


# -- her AI brain ----------------------------------------------------------------------------------------------------
class Tags:
    def __init__(self, models=None, error=False):
        self.models, self.error = models, error

    def __call__(self, method, url, body=None, timeout=3.0):
        if self.error:
            raise OSError("refused")
        return {"models": [{"name": m} for m in self.models]}


def doctor(fetch, exe=None, key=False, **kw):
    from capri.ai.doctor import AIDoctor
    return AIDoctor(Settings(), lambda: key, fetch=fetch, which=lambda name: exe, env={}, **kw)


@pytest.mark.parametrize("fetch, exe, key, code", [
    (Tags(["llama3.2:latest"]), None, False, "ready"), (Tags([]), None, False, "no_model"),
    (Tags(error=True), "C:/ollama/ollama.exe", False, "stopped"), (Tags(error=True), None, False, "not_installed"),
    (Tags(error=True), None, True, "claude"),
])
def test_she_knows_why_she_cant_think(fetch, exe, key, code):
    assert doctor(fetch, exe, key).status()[0] == code


def test_she_starts_ollama_herself(tmp_path):
    exe = tmp_path / "ollama.exe"
    exe.write_text("")
    ran = []
    d = doctor(Tags(error=True), str(exe), run=lambda args, **kw: ran.append(args))
    assert d.start() and ran == [[str(exe), "serve"]]
    (tmp_path / "ollama app.exe").write_text("")
    d.start()
    assert ran[-1] == [str(tmp_path / "ollama app.exe")]                  # its own tray app when there


def test_the_brain_download_reports_progress():
    lines = [json.dumps(x).encode() + b"\n" for x in (
        {"status": "pulling manifest"}, {"status": "downloading", "total": 100, "completed": 40},
        {"status": "downloading", "total": 100, "completed": 100}, {"status": "success"})]

    class Opener:
        def open(self, req, timeout=0):
            assert req.full_url.endswith("/api/pull") and json.loads(req.data)["model"] == "llama3.2"

            class R:
                def __enter__(self):
                    return iter(lines)

                def __exit__(self, *a):
                    return False
            return R()
    seen = []
    doctor(Tags([]), opener=lambda: Opener()).pull(seen.append)
    assert seen == [0.4, 1.0, 1.0]


class FakeDoctor:
    def __init__(self, code):
        self.code, self.pulled, self.installed, self.started = code, 0, 0, 0

    def status(self):
        return self.code, {"no_model": "My brain isn't downloaded yet.", "ready": "My AI brain's online.",
                           "not_installed": "I need Ollama to think."}.get(self.code, "")

    def model(self):
        return "llama3.2"

    def pull(self, progress):
        progress(0.5)
        progress(1.0)
        self.pulled += 1
        self.code = "ready"

    def install(self):
        self.installed += 1
        return True

    def start(self):
        self.started += 1
        return True


def test_set_up_your_brain_downloads_it_after_asking():
    doc = FakeDoctor("no_model")
    r = rig(FakeDesktop(), doctor=doc)
    r.service.command.emit("set up your brain")
    assert settle(2, lambda: r.speaker.lines and "Download it now?" in r.speaker.lines[-1])
    assert doc.pulled == 0
    r.service.command.emit("yes")
    assert settle(3, lambda: "Brain downloaded" in r.controller.message)
    assert doc.pulled == 1


def test_no_ollama_offers_to_install_it():
    doc = FakeDoctor("not_installed")
    r = rig(FakeDesktop(), doctor=doc)
    r.service.command.emit("why cant you think")
    assert settle(2, lambda: r.speaker.lines and "Install it?" in r.speaker.lines[-1])
    r.service.command.emit("no")
    assert doc.installed == 0
    r.service.command.emit("set up your ai")
    assert settle(2, lambda: "Install it?" in r.speaker.lines[-1])
    r.service.command.emit("yes")
    assert settle(2, lambda: doc.installed == 1)


def test_when_ready_she_says_so():
    r = rig(FakeDesktop(), doctor=FakeDoctor("ready"))
    r.service.command.emit("is your ai working")
    assert settle(2, lambda: r.controller.message == "My AI brain's online.")


# -- the chat window -------------------------------------------------------------------------------------------------
def test_the_chat_window_has_cyberpunk_skins():
    from capri.ui.chat_window import SKINS, ChatWindow
    s = Settings()
    r = rig(FakeDesktop(), settings=s)
    chat = ChatWindow(r.assistant, QImage(16, 16, QImage.Format.Format_ARGB32))
    assert {"holocall", "netrunner", "arasaka", "neon", "braindance"} <= set(SKINS)
    chat.input.setText("open discord")
    chat.send()
    for key, skin in SKINS.items():
        chat.set_skin(key)
        assert chat.header.skin is skin and skin.accent in chat.styleSheet()
        assert "You: open discord" in chat.log.text()                   # history kept across skins
        assert chat.log.colours is skin.call
        assert not chat.header.grab().isNull()
    chat.set_skin("netrunner")
    assert chat.send_button.text() == "EXEC"
    assert s.chat_skin == "netrunner" and Settings.load().chat_skin == "netrunner"
    assert all(len(line) == 2 for line in chat.lines)
