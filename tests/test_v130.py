"""v1.30: a real conversation with her AI, checked end to end against a stand-in ChatGPT server (the real
brain, the real web requests); when the AI can't answer, the service's own words are kept and shown in
Settings; a preview of her game affirmations; and a Linux launcher."""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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

from capri import secrets  # noqa: E402
from capri.ai.claude import ClaudeBrain  # noqa: E402
from capri.ai.local import Brains, LocalBrain  # noqa: E402
from capri.ai.openai_compat import FREE_TIP, OpenAIBrain  # noqa: E402
from capri.settings import Settings  # noqa: E402
from capri.states import State  # noqa: E402


class FakeOpenAI(BaseHTTPRequestHandler):
    """Answers like OpenAI's /chat/completions - and refuses what gpt-5 models refuse (max_tokens)."""
    mode = "ok"
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOpenAI.seen.append(body)

        def send(code, obj):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        if self.headers.get("Authorization") != "Bearer sk-test":
            return send(401, {"error": {"message": "Incorrect API key provided: sk-wrong."}})
        if FakeOpenAI.mode == "quota":
            return send(429, {"error": {"message": "You exceeded your current quota, please check your plan.",
                                        "code": "insufficient_quota"}})
        if FakeOpenAI.mode == "bad":
            return send(400, {"error": {"message": "Invalid value for 'tools[0]': something odd."}})
        if "max_tokens" in body:
            return send(400, {"error": {"message": "Unsupported parameter: 'max_tokens' is not supported with this "
                                                   "model. Use 'max_completion_tokens' instead."}})
        said = body["messages"][-1]["content"]
        send(200, {"choices": [{"message": {"role": "assistant", "content": f"[happy] You said {said}, choom."}}]})


@pytest.fixture
def ai():
    FakeOpenAI.mode, FakeOpenAI.seen = "ok", []
    server = HTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    s = Settings(slang=False)
    s.ai_enabled, s.ai_provider, s.openai_preset = True, "openai", "custom"
    s.openai_url, s.openai_model = f"http://127.0.0.1:{server.server_port}/v1", "gpt-5-nano"
    secrets.set_many({"openai_api_key": "sk-test"})
    brain = Brains(s, ClaudeBrain(lambda: "", info={}), LocalBrain(lambda: "http://127.0.0.1:1", lambda: "x", {}),
                   OpenAIBrain(lambda: s.openai_preset, lambda: s.openai_url, lambda: s.openai_model,
                               lambda: secrets.get("openai_api_key"), {}))
    r = rig(FakeDesktop(), settings=s, brain=brain)
    yield r
    server.shutdown()
    secrets.delete("openai_api_key")


def test_a_conversation_goes_to_the_ai(ai):
    for said in ("how was your day", "what do you think about cats", "i'm bored"):
        ai.service.command.emit(said)
        assert settle(5, lambda: ai.controller.message == f"You said {said}, choom.")
        assert ai.controller.state is State.SPEAKING
    history = FakeOpenAI.seen[-1]["messages"]
    assert [m["content"] for m in history if m["role"] == "user"][-3:] == \
        ["how was your day", "what do you think about cats", "i'm bored"]          # she remembers the chat
    assert ai.router.ai_status[1] is True


def test_no_credit_says_why_with_the_free_option_and_settings_shows_it(ai):
    FakeOpenAI.mode = "quota"
    ai.service.command.emit("tell me something cool")
    assert settle(5, lambda: ai.controller.state is State.ERROR)
    assert "out of credit" in ai.controller.message
    when, ok, text = ai.router.ai_status
    assert not ok and "exceeded your current quota" in text                          # the service's own words
    from capri.ui.assistant_tab import AssistantTab
    ai.assistant.speaker.voices = lambda: []
    tab = AssistantTab(ai.assistant, ai.router, None)
    assert "exceeded your current quota" in tab.ai_last.text()


def test_the_official_no_credit_message_points_to_a_free_key():
    from capri.integrations.http import HttpError

    def fetch(*a, **k):
        raise HttpError(429, '{"error": {"message": "You exceeded your current quota", "code": "insufficient_quota"}}')
    reply = OpenAIBrain(lambda: "openai", lambda: "", lambda: "gpt-5-nano", lambda: "sk-x", {}, fetch=fetch).ask("hi")
    assert reply.text.endswith(FREE_TIP) and "exceeded your current quota" in reply.detail


def test_any_other_refusal_is_said_in_the_services_words(ai):
    FakeOpenAI.mode = "bad"
    got = []
    ai.router.test_ai(got.append)
    assert settle(5, lambda: bool(got))
    assert "Invalid value for 'tools[0]'" in got[0]


def test_a_crash_inside_the_ai_is_never_silent():
    def fetch(*a, **k):
        raise KeyError("boom")
    reply = OpenAIBrain(lambda: "openai", lambda: "", lambda: "gpt-5-nano", lambda: "sk-x", {}, fetch=fetch).ask("hi")
    assert reply.error and "glitched" in reply.text and "boom" in reply.detail


# -- affirmations preview ----------------------------------------------------------------------------------------
def test_preview_says_a_run_of_affirmations():
    from capri.integrations.game_hype import GameHype
    said = []
    hype = GameHype(Settings(), said.append, lambda: [], lambda: [])
    hype.PREVIEW_GAP_MS = 10
    lines = hype.preview()
    assert len(lines) == len(GameHype.PREVIEW) and all(lines)
    assert settle(2, lambda: len(said) == len(lines)) and said == lines


def test_lines_start_a_new_sentence_properly():
    import random
    from capri.integrations.game_hype import line
    rng = random.Random(1)
    for _ in range(300):
        text = line("kill", "edgerunner", rng)
        for opener in ("Yes! ", "Ha! "):
            if text.startswith(opener):
                assert text[len(opener)].isupper() or not text[len(opener)].isalpha()


# -- Linux ----------------------------------------------------------------------------------------------------------
def test_there_is_a_linux_launcher():
    path = Path(__file__).resolve().parent.parent / "run.sh"
    assert path.exists() and os.access(path, os.X_OK)
    text = path.read_text()
    assert "python3 -m venv .venv" in text and "-m capri" in text
