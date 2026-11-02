"""v1.13: a chatbot that also takes commands, Chatterbox gone, and "click that button" -
found on your screen and zapped from where she lies."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QRect, QStandardPaths  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
app = QApplication.instance() or QApplication([])

from test_stage5 import settle  # noqa: E402
from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Kind, parse  # noqa: E402
from capri.integrations.screen_targets import Finder, Target, Word, best_match, click, match_words, name_score  # noqa: E402


# -- "click ..." -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, label", [
    ("click that button", ""), ("click that", ""), ("click it", ""), ("click here", ""), ("press that button", ""),
    ("hey capri click the subscribe button", "subscribe"), ("click on next", "next"), ("click skip ad", "skip ad"),
    ("press the play button", "play"), ("tap the accept button", "accept"), ("click on the downloads tab", "downloads"),
])
def test_click_commands(text, label):
    intent = parse(text)
    assert intent.kind is Kind.CLICK and intent.targets == (label,)


def test_press_play_is_still_music():
    assert parse("press play").kind is not Kind.CLICK


@pytest.mark.parametrize("label, name, good", [
    ("subscribe", "Subscribe", True), ("subscribe", "Subscribe to MrBeast", True), ("skip ad", "Skip Ad", True),
    ("next", "Next video", True), ("downloads", "Downloads", True), ("play", "Playlist settings", False),
    ("subscribe", "Settings", False),
])
def test_button_names_match_what_you_said(label, name, good):
    assert (name_score(label, name) >= 0.78) is good


def test_the_closest_button_wins():
    things = [("Settings", (0, 0, 10, 10), None), ("Subscribe", (50, 50, 90, 70), "sub"), ("Share", (0, 0, 5, 5), None)]
    found = best_match("subscribe", things)
    assert found.name == "Subscribe" and found.rect == (50, 50, 90, 70) and found.element == "sub"


def test_words_read_off_the_screen():
    words = [Word("Skip", 1, (100, 200, 130, 215)), Word("Ad", 1, (134, 200, 150, 215)),
             Word("Visit", 2, (100, 300, 140, 315)), Word("advertiser", 2, (144, 300, 220, 315))]
    found = match_words("skip ad", words)
    assert found is not None and found.rect == (100, 200, 150, 215) and found.how == "text"
    assert match_words("subscribe", words) is None


class Element:
    def __init__(self, name, rect):
        self.name, self.rect, self.pressed = name, rect, 0

    def press(self):
        self.pressed += 1


class UI:
    def __init__(self, things=(), at=None):
        self.things, self.at, self.asked = list(things), at, 0

    def clickables(self, hwnd):
        self.asked += 1
        return self.things

    def element_at(self, x, y):
        return self.at


def finder(ui, ocr=None, cursor=(400, 300)):
    return Finder(ui, lambda: 77, lambda hwnd: (0, 0, 800, 600), lambda: cursor, ocr=ocr, sleep=lambda s: None)


def test_finds_a_button_by_name():
    sub = Element("Subscribe", (500, 400, 600, 436))
    found = finder(UI([Element("Like", (0, 0, 10, 10)), sub])).find("subscribe")
    assert found.element is sub and found.how == "ui"


def test_reads_the_screen_when_the_app_doesnt_name_its_buttons():
    ocr = lambda rect: [Word("PLAY", 1, (300, 500, 360, 530))]          # e.g. a game's launcher
    found = finder(UI([]), ocr=ocr).find("play")
    assert found.how == "text" and found.center == (330, 515)


def test_click_that_is_what_youre_pointing_at():
    under = Element("Skip", (390, 290, 450, 320))
    found = finder(UI(at=under)).find("")
    assert found.element is under and found.how == "mouse"
    bare = finder(UI(at=None), cursor=(10, 20)).find("")                 # nothing readable: click right there
    assert bare.center == (10, 20)


def test_pressing_uses_the_button_else_the_mouse():
    mouse = []
    sub = Element("Subscribe", (0, 0, 100, 40))
    click(Target("Subscribe", sub.rect, "ui", sub), lambda x, y: mouse.append((x, y)))
    assert sub.pressed == 1 and mouse == []
    click(Target("PLAY", (300, 500, 360, 530), "text"), lambda x, y: mouse.append((x, y)))
    assert mouse == [(330, 515)]


class Screen:
    def __init__(self, target):
        self.target, self.asked = target, []

    def find(self, label):
        self.asked.append(label)
        return self.target


def click_rig(target):
    zaps, clicks = [], []
    r = rig(FakeDesktop(), screen=Screen(target), click_at=clicks.append,
            zap_rect=lambda rect, then: (zaps.append(rect), then()))
    return r, zaps, clicks


def test_she_zaps_it_then_it_is_clicked():
    target = Target("Subscribe", (500, 400, 600, 436), "ui")
    r, zaps, clicks = click_rig(target)
    r.service.command.emit("click the subscribe button")
    assert settle(2, lambda: clicks)
    assert zaps == [(500, 400, 600, 436)] and clicks == [target]
    assert settle(2, lambda: r.controller.message == "Zapped Subscribe.")


def test_risky_buttons_are_asked_about_first():
    target = Target("Delete account", (0, 0, 50, 20), "ui")
    r, zaps, clicks = click_rig(target)
    r.service.command.emit("click delete account")
    assert settle(2, lambda: r.speaker.lines and "Say yes or no" in r.speaker.lines[-1])
    assert clicks == []
    r.service.command.emit("no")
    assert clicks == [] and r.controller.message == "Okay, not clicking it."
    r.service.command.emit("click delete account")
    assert settle(2, lambda: "Say yes or no" in r.speaker.lines[-1])
    r.service.command.emit("yes")
    assert settle(2, lambda: clicks == [target])


def test_says_so_when_it_isnt_on_screen():
    r, zaps, clicks = click_rig(None)
    r.service.command.emit("click subscribe")
    assert settle(2, lambda: r.controller.message == 'I can\'t see "subscribe" on your screen.')
    assert zaps == clicks == []


def test_the_ai_can_click_too():
    from capri.ai.claude import to_intent
    intent = to_intent("click_on_screen", {"label": "Skip Ad"})
    assert intent.kind is Kind.CLICK and intent.targets == ("Skip Ad",)


def test_the_zap_comes_from_her_while_she_lies_on_the_panel():
    from capri.app import asset_root
    from capri.controller import CompanionController
    from capri.settings import Settings
    from capri.ui.art import CharacterArt
    from capri.ui.companion import Companion
    from capri.ui.sprites import SpriteArt
    from capri.ui.zap import ZapShow
    s = Settings()
    s.lounge = True
    c = Companion(CompanionController(), CharacterArt.load(asset_root() / "capri"), s,
                  SpriteArt.load(asset_root() / "capri_v2"))
    c.show()
    assert c.lounging()
    z = ZapShow(c, lambda pids: None)
    hit = []
    z.zap_at(QRect(100, 100, 40, 30), lambda: hit.append(1), small=True)
    body = c.content_geometry()
    assert body.left() <= z.fx.hand.x() <= body.left() + body.width() * 0.4      # her hand, by her face
    assert c.lounging() and c.character.isVisible()                              # she stays lying down
    assert settle(2, lambda: hit)


# -- the chatbot ----------------------------------------------------------------------------------------------
class Local:
    def __init__(self, up):
        self.up, self.asked = up, []

    def available(self):
        return self.up, ""

    def ask(self, text):
        from capri.ai.claude import AIReply
        self.asked.append(text)
        return AIReply("local says hi")


class Claude(Local):
    def __init__(self, key):
        super().__init__(True)
        self.key = key

    def has_key(self):
        return self.key


@pytest.mark.parametrize("local_up, key, which", [(True, True, "claude"), (True, False, "local"),   # v1.21: a key wins
                                                   (False, True, "claude"), (False, False, "")])
def test_auto_picks_the_ai_you_have(local_up, key, which):
    from capri.ai.local import Brains
    from capri.settings import Settings
    s = Settings()
    assert s.ai_enabled and s.ai_provider == "auto"                              # a chatbot by default
    brains = Brains(s, Claude(key), Local(local_up))
    assert brains.which() == which
    if not which:
        assert brains.ask("hi").missing


def test_with_no_ai_she_still_chats():
    from capri.ai.claude import AIReply

    class NoBrain:
        def ask(self, text):
            return AIReply("", error=True, missing=True)
    r = rig(FakeDesktop(), brain=NoBrain())
    r.service.command.emit("how are you")
    assert settle(2, lambda: r.speaker.lines)
    assert "fried" not in r.speaker.lines[-1] and r.controller.state.name != "ERROR"


def test_conversations_last_longer():
    from capri.assistant import CONVERSATION_TURNS
    assert CONVERSATION_TURNS >= 10


# -- Chatterbox is gone ---------------------------------------------------------------------------------------
def test_chatterbox_is_gone():
    root = Path(__file__).resolve().parent.parent
    for gone in ("capri/speech/chatterbox.py", "capri/speech/chatterbox_worker.py", "capri/speech/voice_lora.py",
                 "install_chatterbox.bat", "train_voice_lora.bat", "requirements-chatterbox.txt"):
        assert not (root / gone).exists(), gone
    assert (root / "tools" / "remove_chatterbox.py").exists()                    # run.bat frees its GBs once
    assert "remove_chatterbox" in (root / "run.bat").read_text()
