"""v1.36.1: a model that doesn't exist (any more) - "gemini 2.5 flash lite doesn't exist" - is swapped for the
closest one the service has, and Settings lists the models your key can actually use."""

from __future__ import annotations

import json
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

from capri.ai import openai_compat as oc  # noqa: E402
from capri.integrations import http  # noqa: E402

GEMINI_MODELS = ["models/gemini-3-flash", "models/gemini-3-flash-lite", "models/gemini-3-pro-preview",
                 "models/gemini-embedding-001", "models/imagen-4.0-generate", "models/gemini-3-flash-tts",
                 "models/gemma-3-27b-it"]


@pytest.mark.parametrize("wanted, best", [
    ("gemini-2.5-flash-lite", "gemini-3-flash-lite"), ("gemini-2.5-flash", "gemini-3-flash"),
    ("gemini-1.5-pro", "gemini-3-pro-preview"), ("something-else", "gemini-3-flash"),
])
def test_stand_in_is_the_closest_chat_model(wanted, best):
    names = [n.split("models/")[-1] for n in GEMINI_MODELS]
    assert oc.pick_stand_in(names, wanted) == best


def test_never_a_picture_or_speech_model():
    assert oc.pick_stand_in(["imagen-4.0-generate", "gemini-embedding-001", "gemini-3-flash-tts"], "gemini") == ""


@pytest.mark.parametrize("status, detail, missing", [
    (404, "models/gemini-2.5-flash-lite is not found for API version v1beta", True),
    (400, "The model `gpt-9` does not exist or you do not have access to it.", True),
    (400, "model has been decommissioned", True),
    (400, "max_tokens is not supported", False), (401, "invalid api key", False),
])
def test_model_missing(status, detail, missing):
    assert oc.model_missing(status, detail) is missing


class FakeGemini:
    """Gemini's OpenAI-style API: no 2.5-flash-lite any more."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, params=None, data=None, json_body=None, headers=None, timeout=10.0):
        self.calls.append((method, url, (json_body or {}).get("model")))
        if url.endswith("/models"):
            return {"object": "list", "data": [{"id": m} for m in GEMINI_MODELS]}
        if json_body["model"] == "gemini-2.5-flash-lite":
            raise http.HttpError(404, json.dumps([{"error": {
                "code": 404, "message": "models/gemini-2.5-flash-lite is not found for API version v1beta"}}]))
        return {"choices": [{"message": {"role": "assistant", "content": "[happy] Hey choom!"}}]}


def brain(fake, model="gemini-2.5-flash-lite"):
    return oc.OpenAIBrain(lambda: "gemini", lambda: "", lambda: model, lambda: "AIza-test", {}, fetch=fake)


def test_a_retired_model_is_swapped_and_she_answers():
    fake = FakeGemini()
    b = brain(fake)
    reply = b.ask("hi")
    assert not reply.error and reply.text == "Hey choom!"
    assert b.model() == "gemini-3-flash-lite" and b.stand_in == "gemini-3-flash-lite"
    assert [c[2] for c in fake.calls if c[0] == "POST"] == ["gemini-2.5-flash-lite", "gemini-3-flash-lite"]
    b.ask("again")                                                     # no more lookups
    assert sum(1 for c in fake.calls if c[1].endswith("/models")) == 1


def test_no_stand_in_says_what_to_do():
    def fetch(method, url, json_body=None, **k):
        if url.endswith("/models"):
            return {"data": [{"id": "text-embedding-3-small"}]}
        raise http.HttpError(404, '{"error": {"message": "The model gpt-9 does not exist"}}')
    reply = brain(fetch, "gpt-9").ask("hi")
    assert reply.error and "Clear the Model box" in reply.text


def test_gemini_default_is_an_alias_that_keeps_up():
    assert oc.PRESETS["gemini"][2] == "gemini-flash-latest"


# -- Settings: pick from the models your key has ----------------------------------------------------------------------
def tab(**services):
    from capri.ui.assistant_tab import AssistantTab
    r = rig(FakeDesktop(), **services)
    r.assistant.speaker.say = lambda *a, **k: True
    r.assistant.speaker.voices = lambda: []
    return AssistantTab(r.assistant, r.router, None), r


def test_show_my_models_lists_what_your_key_has(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(oc.OpenAIBrain, "__init__", _with_fetch(oc.OpenAIBrain.__init__, fake))
    t, _r = tab()
    t.ai_pick.setCurrentIndex(t.ai_pick.findData("openai:gemini"))
    t.ai_key.setText("AIza-test")
    t._list_models("openai")
    assert settle(3, lambda: t.ai_model.count() > 0)
    names = [t.ai_model.itemText(i) for i in range(t.ai_model.count())]
    assert names == ["gemini-3-flash", "gemini-3-flash-lite", "gemini-3-pro-preview", "gemma-3-27b-it"]
    assert t.ai_models_btn.isEnabled() and "found" in t.ai_hint.text()
    t.ai_model.setCurrentIndex(1)
    t.apply()
    assert t.settings.openai_model == "gemini-3-flash-lite"


def test_show_my_models_with_a_bad_key(monkeypatch):
    def refuse(*a, **k):
        raise http.HttpError(401, "bad key")
    monkeypatch.setattr(oc.OpenAIBrain, "__init__", _with_fetch(oc.OpenAIBrain.__init__, refuse))
    t, _r = tab()
    t.ai_pick.setCurrentIndex(t.ai_pick.findData("openai:gemini"))
    t._list_models("openai")
    assert settle(3, lambda: "doesn't work" in t.ai_hint.text())


def test_ollama_models_are_listed(monkeypatch):
    monkeypatch.setattr(http, "request", lambda *a, **k: {"models": [{"name": "qwen2.5:3b"},
                                                                      {"name": "nomic-embed-text:latest"}]})
    t, _r = tab()
    t._list_models("local")
    assert settle(3, lambda: t.ollama_model.count() > 0)
    assert [t.ollama_model.itemText(i) for i in range(t.ollama_model.count())] == ["qwen2.5:3b"]


def _with_fetch(original, fake):
    def init(self, *args, **kwargs):
        kwargs["fetch"] = fake
        original(self, *args, **kwargs)
    return init
