"""v1.21: Whisper's punctuation no longer breaks commands, any AI (ChatGPT...), no more
questioning, game hype, Discord join call, learning buttons, hmph, calmer voice styles."""

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

from test_v11 import FakeDesktop, rig  # noqa: E402

from capri.commands.parser import Kind, parse  # noqa: E402

PHRASES = ["shut down my computer", "open discord", "close spotify", "whats using my ram", "mute me", "leave call",
           "what time is it", "play let you down by nf", "pull up spotify", "turn it down a bit",
           "set a timer for 5 minutes", "take a screenshot", "minimize everything", "stream my screen",
           "restart my computer", "go to the bottom left", "be sarcastic", "stop talking"]


@pytest.mark.parametrize("plain", PHRASES)
def test_whisper_style_punctuation_parses_the_same(plain):
    """Whisper (better hearing) writes "Shut down my computer." - capitals, full stops, commas,
    curly apostrophes. Every command must still work."""
    for written in (plain.capitalize() + ".", "Hey Capri, " + plain + ".", plain + "?", plain + "!",
                    plain.replace("whats", "What’s").capitalize() + "."):
        assert parse(written) == parse(plain), written


def test_dots_that_matter_stay():
    assert parse("open twitch.tv").targets == ("twitch.tv",)
    assert parse("Set an alarm for 7:30 a.m.").targets[0] == "7:30"


def test_shutdown_said_with_a_full_stop_still_asks_first():
    d = FakeDesktop()
    r = rig(d)
    r.service.command.emit("Shut down my computer.")
    assert r.speaker.lines[-1] == "Look up there, think we can make it?" and d.calls == []
    r.service.command.emit("Yes.")
    assert d.calls == [("power", "shutdown")]


# -- hmph, and calmer voice styles ------------------------------------------------------------------------------
def test_hmph_is_said_not_spelled():
    from capri.speech.pronounce import respell, sapi_xml
    assert respell("Hmph. Fine.") == "Humph. Fine." and respell("Tch.") == "Tsk."
    assert '<pron sym="hh ah 1 m f"/>' in sapi_xml("Hmph!")


def test_voice_styles_are_a_flavour_not_a_filter():
    import numpy as np
    from capri.speech.effects import Audio, apply_style
    rate = 22050
    t = np.arange(rate) / rate
    voice = ((np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(2 * np.pi * 2400 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)))
    voice = voice.astype(np.float32)
    plain = apply_style(Audio(voice, rate, pitched=True), "natural").samples
    for style in ("holocall", "netrunner", "android", "cyberspace"):
        y = apply_style(Audio(voice, rate, pitched=True), style, seed=1).samples
        n = min(len(y), len(plain))
        change = np.sqrt(np.mean((y[:n] - plain[:n]) ** 2)) / np.sqrt(np.mean(plain[:n] ** 2))
        assert change < 0.7, style


# -- ChatGPT, or any AI -------------------------------------------------------------------------------------------
def _gpt(replies, key="sk-test", preset="openai", model=""):
    from capri.ai.openai_compat import OpenAIBrain
    sent = []

    def fetch(method, url, json_body=None, headers=None, timeout=None, **k):
        sent.append((url, json_body, headers))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
    brain = OpenAIBrain(lambda: preset, lambda: "", lambda: model, lambda: key,
                        {"get_time": lambda args: "Tuesday 14:00"}, fetch=fetch)
    return brain, sent


def test_chatgpt_chats_on_the_cheapest_model_by_default():
    brain, sent = _gpt([{"choices": [{"message": {"content": "[happy] Hey! Doing great."}}]}])
    reply = brain.ask("how are you")
    assert reply.text == "Hey! Doing great." and reply.emotion == "happy" and not reply.error
    url, body, headers = sent[0]
    assert url == "https://api.openai.com/v1/chat/completions" and body["model"] == "gpt-5-nano"
    assert headers["Authorization"] == "Bearer sk-test" and body["reasoning_effort"] == "minimal"
    assert body["messages"][0]["role"] == "system" and body["tools"]


def test_chatgpt_actions_become_capris_own_commands():
    call = {"id": "c1", "type": "function", "function": {"name": "open_app", "arguments": '{"names": ["Spotify"]}'}}
    brain, sent = _gpt([{"choices": [{"message": {"content": "", "tool_calls": [call]}}]}])
    reply = brain.ask("pull up spotify")
    assert reply.intent is not None and reply.intent.kind is Kind.OPEN and reply.intent.targets == ("Spotify",)


def test_chatgpt_can_look_things_up_then_answer():
    call = {"id": "t1", "type": "function", "function": {"name": "get_time", "arguments": "{}"}}
    brain, sent = _gpt([{"choices": [{"message": {"content": None, "tool_calls": [call]}}]},
                        {"choices": [{"message": {"content": "It's 2pm."}}]}])
    assert brain.ask("what time is it").text == "It's 2pm."
    assert sent[1][1]["messages"][-1] == {"role": "tool", "tool_call_id": "t1", "content": "Tuesday 14:00"}


def test_problems_are_said_plainly():
    from capri.integrations.http import HttpError
    brain, _ = _gpt([HttpError(401, '{"error": {"message": "bad key"}}')])
    assert "key doesn't work" in brain.ask("hi").text
    brain, _ = _gpt([HttpError(404, '{"error": {"message": "The model `gpt-9` does not exist"}}')], model="gpt-9")
    assert "no model called gpt-9" in brain.ask("hi").text
    brain, _ = _gpt([HttpError(429, '{"error": {"message": "You exceeded your current quota"}}')])
    assert "no credit" in brain.ask("hi").text
    brain, _ = _gpt([], key="")
    reply = brain.ask("hi")
    assert reply.error and "API key" in reply.text


def test_a_service_that_rejects_an_option_still_works():
    from capri.integrations.http import HttpError
    brain, sent = _gpt([HttpError(400, '{"error": {"message": "Unsupported parameter: reasoning_effort"}}'),
                        {"choices": [{"message": {"content": "Hi."}}]}], preset="groq", model="gpt-5-nano-ish")
    assert brain.ask("hi").text == "Hi."
    assert "reasoning_effort" not in sent[1][1] and sent[1][0].startswith("https://api.groq.com/openai/v1")


def test_auto_prefers_the_ai_you_added_a_key_for_over_ollama():
    from types import SimpleNamespace
    from capri.ai.local import Brains
    settings = SimpleNamespace(ai_provider="auto", openai_preset="openai")
    claude = SimpleNamespace(has_key=lambda: False, reset=lambda: None)
    local = SimpleNamespace(available=lambda: (True, ""), reset=lambda: None)
    gpt, _ = _gpt([])
    assert Brains(settings, claude, local, gpt).which() == "openai"
    gpt_nokey, _ = _gpt([], key="")
    assert Brains(settings, claude, local, gpt_nokey).which() == "local"


def test_set_up_your_brain_with_chatgpt():
    from types import SimpleNamespace
    from capri.ai import doctor as dr
    gpt, _ = _gpt([])
    status = dr.AIDoctor(SimpleNamespace(ai_provider="openai"), openai=gpt).status()
    assert status[0] == dr.ONLINE and "ChatGPT" in status[1] and "gpt-5-nano" in status[1]
    gpt, _ = _gpt([], key="")
    status = dr.AIDoctor(SimpleNamespace(ai_provider="openai"), openai=gpt).status()
    assert status[0] == dr.NEEDS_KEY and "API key" in status[1]


# -- she doesn't question you ---------------------------------------------------------------------------------
NO_QUESTIONS = ["misheard", "generic", "why", "feel_other", "laugh", "sigh", "like", "dislike", "feel_good", "here",
                "about_games", "about_music", "about_food", "about_school", "about_work", "about_shows",
                "about_people", "about_code", "about_sports"]


def test_odd_things_you_say_dont_get_questioned():
    from capri.chatbot import BANK
    for kind in NO_QUESTIONS:
        for persona, options in BANK[kind].items():
            for _emotion, plain, street in options:
                assert "?" not in plain.rstrip("?")[-1:] and not plain.endswith("?"), (kind, persona, plain)
                assert not street.endswith("?"), (kind, persona, street)


@pytest.mark.parametrize("said", ["ngnge", "why", "i went outside", "lol", "ugh", "i feel weird", "i like trains"])
def test_replies_to_odd_input_end_without_a_question(said):
    import random

    from capri.chatbot import ChatBot
    for persona in ("edgerunner", "sarcastic", "tsundere", "sweet", "deadpan"):
        bot = ChatBot(rng=random.Random(7))
        text, _emotion = bot.reply(said, persona)
        assert not text.endswith("?"), (said, persona, text)


def test_the_ai_is_told_not_to_question_you():
    from capri.ai.claude import system_prompt
    prompt = system_prompt(False)
    assert "Don't question the user" in prompt and "never ask them to explain" in prompt
    assert "ask what they meant" not in prompt and "ask a short question back" not in prompt


# -- Discord: join your call ----------------------------------------------------------------------------------
@pytest.mark.parametrize("said", ["join call", "hey capri join the call", "hop in the vc", "join my call",
                                  "get in the call", "Join call."])
def test_join_call_commands(said):
    intent = parse(said)
    assert intent.kind is Kind.DISCORD and intent.query == "join"


def test_call_links():
    from capri.integrations.app_buttons import call_link
    assert call_link("https://discord.com/channels/111/222") == "discord://-/channels/111/222"
    assert call_link("https://ptb.discord.com/channels/111/222") == "discord://-/channels/111/222"
    assert call_link("hello") is None


def test_join_call_opens_your_call_and_presses_join():
    from test_stage5 import settle
    from test_v120 import FakeDiscordUI, _call
    from capri.commands.system import ProcessInfo
    r = rig(FakeDesktop(), processes=[ProcessInfo(10, "Discord.exe")])
    ui = FakeDiscordUI(in_call=False)
    ui.viewing = True                                       # the channel's page, with its Join Voice button
    r.router.services.discord_call = _call(ui)
    r.router.handle("join call")
    assert "Settings" in r.controller.message                  # which call? not set yet
    r.assistant.settings.discord_call = "https://discord.com/channels/111/222"
    r.router.handle("join call")
    assert settle(3, lambda: r.controller.message == "You're in the call.")
    assert ("open", "discord://-/channels/111/222") in r.system.calls and "Join Voice" in ui.pressed


def test_missing_buttons_are_logged_so_you_can_tell_me(caplog):
    import logging
    from test_v120 import FakeDiscordUI, _call
    ui = FakeDiscordUI(in_call=False)
    with caplog.at_level(logging.INFO, logger="capri"):
        assert _call(ui).leave([1]) == "no_call"
    assert "Saw: " in caplog.text and "Mute" in caplog.text


# -- teaching her a button by pointing at it ------------------------------------------------------------------
@pytest.mark.parametrize("said, phrase", [
    ("this red button makes me leave call", "leave call"), ("This red button makes me leave call.", "leave call"),
    ("learn this button as skip intro", "skip intro"), ("when i say next episode, click this button", "next episode"),
    ("press this button when i say mute the stream", "mute the stream"), ("this button is leave call", "leave call"),
])
def test_teaching_phrases(said, phrase):
    intent = parse(said)
    assert intent.kind is Kind.LEARN_BUTTON and intent.targets == (phrase,)


@pytest.mark.parametrize("said", ["that thing is cool", "this one is fun", "this game is fun", "this is my song"])
def test_chat_isnt_mistaken_for_teaching(said):
    assert parse(said).kind is not Kind.LEARN_BUTTON


class _Element:
    def __init__(self, name, rect):
        self.name, self.rect = name, rect

    def press(self):
        pass


def _teaching_rig():
    from types import SimpleNamespace
    from test_stage5 import settle
    from capri.commands.system import ProcessInfo
    from capri.integrations.screen_targets import Target
    r = rig(FakeDesktop(), processes=[ProcessInfo(10, "Discord.exe")])
    red = _Element("Disconnect", (210, 940, 240, 970))
    ui = SimpleNamespace(clickables=lambda hwnd: [_Element("Mute", (10, 1000, 40, 1030)), red])
    finder = SimpleNamespace(ui=ui, cursor=lambda: (225, 955),
                             under_mouse=lambda: Target("Disconnect", red.rect, "mouse", red))
    desktop = r.router.services.desktop
    desktop.window_at = lambda x, y: 77
    desktop.pid_of = lambda hwnd: 10
    desktop.hwnd_rect = lambda hwnd: (0, 0, 1000, 1080)
    desktop.windows_for = lambda pids: [77]
    pressed = []
    r.router.services.screen = finder
    r.router.services.click_at = lambda target: pressed.append(target.name)
    return r, pressed, settle


def test_she_learns_a_button_and_presses_it_when_you_say_it():
    r, pressed, settle = _teaching_rig()
    r.router.handle("this red button makes me leave call")
    assert settle(3, lambda: r.controller.message.startswith("Learned it."))
    assert "Disconnect" in r.controller.message and "Discord" in r.controller.message
    skill = r.assistant.settings.learned_buttons[0]
    assert skill["phrase"] == "leave call" and skill["app"] == "Discord.exe" and skill["name"] == "Disconnect"
    r.router.handle("leave call")                          # what you taught her wins over the built-in
    assert settle(3, lambda: pressed == ["Disconnect"])


def test_learned_buttons_are_saved_as_data_and_can_be_forgotten():
    from capri.settings import Settings
    r, pressed, settle = _teaching_rig()
    r.router.handle("this red button makes me leave call")
    settle(3, lambda: bool(r.assistant.settings.learned_buttons))
    assert Settings.load().learned_buttons[0]["name"] == "Disconnect"   # survives a restart
    r.router.handle("forget the leave call button")
    assert r.assistant.settings.learned_buttons == [] and "Forgotten" in r.controller.message


# -- game hype: "nice kill!" -----------------------------------------------------------------------------------
def _cs2(kills, round_kills=0, hs=0, deaths=0, team="CT", me="1", player="1", phase="live", map_phase="live",
         win=None, ct=0, t=0):
    return {"provider": {"steamid": me}, "player": {"steamid": player, "team": team,
                                                    "state": {"round_kills": round_kills, "round_killhs": hs},
                                                    "match_stats": {"kills": kills, "deaths": deaths}},
            "round": {"phase": phase, **({"win_team": win} if win else {})},
            "map": {"phase": map_phase, "team_ct": {"score": ct}, "team_t": {"score": t}}}


def test_cs2_kills_headshots_and_multikills():
    from capri.integrations.game_hype import CS2
    cs = CS2()
    assert cs.update(_cs2(0)) == []                                     # first look: just remember
    assert cs.update(_cs2(1, round_kills=1)) == ["kill"]
    assert cs.update(_cs2(2, round_kills=2, hs=1)) == ["double"]
    assert cs.update(_cs2(3, round_kills=3, hs=2)) == ["triple"]
    assert cs.update(_cs2(5, round_kills=5)) == ["ace"]
    assert cs.update(_cs2(5, round_kills=0, deaths=1)) == ["death"]
    assert cs.update(_cs2(5, deaths=1, phase="over", win="CT")) == ["round_win"]
    assert cs.update(_cs2(5, deaths=1, map_phase="gameover", ct=13, t=7)) == ["match_win"]


def test_cs2_headshot_and_no_cheering_for_someone_you_spectate():
    from capri.integrations.game_hype import CS2
    cs = CS2()
    cs.update(_cs2(0))
    assert cs.update(_cs2(1, round_kills=1, hs=1)) == ["headshot"]
    assert cs.update(_cs2(9, round_kills=3, player="2")) == []         # you're dead, watching a teammate


def test_league_events_for_you_only():
    from capri.integrations.game_hype import League
    lg = League()
    old = [{"EventID": 0, "EventName": "GameStart"}]
    assert lg.update(old, "Me#EUW") == []                               # joined: old events aren't cheered
    events = old + [{"EventID": 1, "EventName": "ChampionKill", "KillerName": "Me", "VictimName": "Them"},
                    {"EventID": 2, "EventName": "ChampionKill", "KillerName": "Them", "VictimName": "Me"},
                    {"EventID": 3, "EventName": "Multikill", "KillerName": "Me", "KillStreak": 3},
                    {"EventID": 4, "EventName": "ChampionKill", "KillerName": "Someone", "VictimName": "Else"},
                    {"EventID": 5, "EventName": "GameEnd", "Result": "Win"}]
    assert lg.update(events, "Me#EUW") == ["kill", "death", "triple", "match_win"]
    assert lg.update(events, "Me#EUW") == []                            # each event once


def test_dota2_kills_and_win():
    from capri.integrations.game_hype import Dota2
    d = Dota2()
    base = {"player": {"kills": 0, "deaths": 0, "kill_streak": 0, "team_name": "radiant"}, "map": {"win_team": "none"}}
    d.update(base)
    assert d.update({"player": {**base["player"], "kills": 1, "kill_streak": 1}, "map": {"win_team": "none"}}) == ["kill"]
    assert d.update({"player": {**base["player"], "kills": 1}, "map": {"win_team": "radiant"}}) == ["match_win"]


def test_she_says_the_best_line_once_for_a_burst(tmp_path):
    from types import SimpleNamespace
    from test_stage5 import settle
    from capri.integrations.game_hype import GameHype
    said = []
    s = SimpleNamespace(game_hype=False, game_hype_deaths=False, personality="edgerunner", game_hype_token="x",
                        save=lambda: None)
    hype = GameHype(s, said.append, lambda: [], lambda: [])
    for event in ("kill", "kill", "kill"):
        hype._got(event)
    from capri.integrations.game_hype import CORES
    assert settle(3, lambda: bool(said)) and len(said) == 1
    assert any(core.lower() in said[0].lower() for core in CORES["triple"])     # the best one: a triple
    hype._got("death")                                                  # deaths are off by default
    settle(1.5)
    assert len(said) == 1


def test_valves_config_file_goes_in_the_game_folder(tmp_path):
    from types import SimpleNamespace
    from capri.integrations.game_hype import GameHype, PORT
    game = SimpleNamespace(appid="730", install_dir=tmp_path / "Counter-Strike Global Offensive")
    s = SimpleNamespace(game_hype=False, game_hype_deaths=False, personality="edgerunner", game_hype_token="",
                        save=lambda: None)
    hype = GameHype(s, lambda t: None, lambda: [game], lambda: [])
    s.game_hype = True
    status = hype._setup_files()
    cfg = tmp_path / "Counter-Strike Global Offensive" / "game" / "csgo" / "cfg" / "gamestate_integration_capri.cfg"
    text = cfg.read_text()
    assert f"http://127.0.0.1:{PORT}/cs2" in text and s.game_hype_token in text and len(s.game_hype_token) == 32
    assert "Counter-Strike 2" in status


def test_game_hype_by_voice():
    r = rig(FakeDesktop())
    r.router.handle("turn on game hype")
    assert r.assistant.settings.game_hype and "Game hype on" in r.controller.message
    r.router.handle("stop cheering")
    assert not r.assistant.settings.game_hype


def test_the_game_talks_to_her_over_localhost():
    import json
    import urllib.request
    from types import SimpleNamespace
    from test_stage5 import settle
    from capri.integrations.game_hype import GameHype, PORT
    said = []
    s = SimpleNamespace(game_hype=True, game_hype_deaths=False, personality="edgerunner", game_hype_token="secret",
                        save=lambda: None)
    hype = GameHype(s, said.append, lambda: [], lambda: [])
    hype.apply()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def post(data, token="secret"):
        body = json.dumps({**data, "auth": {"token": token}}).encode()
        opener.open(urllib.request.Request(f"http://127.0.0.1:{PORT}/cs2", data=body, method="POST"), timeout=3).read()
    try:
        post(_cs2(0))
        post(_cs2(1, round_kills=1), token="wrong")                    # not from the game: ignored
        settle(1.5)
        assert said == []
        post(_cs2(1, round_kills=1))
        assert settle(3, lambda: bool(said))
    finally:
        s.game_hype = False
        hype.apply()
