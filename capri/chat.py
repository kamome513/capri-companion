"""Capri's built-in small talk: short, back-and-forth chat with no AI needed.

She remembers what she last asked, so "how are you" -> "good, you?" ->
"not bad" gets a reply that follows on. Every answer that ends in a question
keeps her listening for a few seconds (no wake word needed) - see
Assistant.show_result(follow_up=True). With AI chat on, small talk goes to
Claude instead and this is the fallback.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Callable

# topic: [(emotion, plain, slang), ...] - one is picked at random.
REPLIES: dict[str, list[tuple[str, str, str]]] = {
    "hello": [
        ("happy", "Hey! How's it going?", "Hey, choom! How's it going?"),
        ("playful", "Oh, hi. Miss me? How are you doing?", "Yo, choom. Miss me? How you holding up?"),
        ("happy", "Hi! What are we up to?", "Heya, choom. What's the plan?"),
    ],
    "how_are_you": [
        ("happy", "Pretty good. Living in your PC is cozy. How about you?",
         "Preem, thanks. Your rig's a cozy place to live. How about you, choom?"),
        ("playful", "Running smooth, no glitches today. You?", "Running smooth. Zero glitches. You good, choom?"),
    ],
    "whats_up": [
        ("smirk", "Just hanging out in the corner of your screen. What's up with you?",
         "Just jacked in, watching your screen. What's up with you, choom?"),
        ("playful", "Not much. Counting pixels. You?", "Not much. Counting pixels, dodging corpos. You?"),
    ],
    "and_you": [
        ("happy", "I'm good! Thanks for asking.", "Preem, thanks for asking, choom."),
    ],
    "im_good": [
        ("happy", "Nice, glad to hear it.", "Nova. Glad to hear it, choom."),
        ("happy", "Good. Let me know if you need anything.", "Preem. Holler if you need anything, choom."),
    ],
    "good_morning": [],   # time of day decides, see _good_morning
    "good_night": [
        ("happy", "Night! Sleep well.", "Night, choom. Don't let the cyberpsychos bite."),
        ("smirk", "Good night. I'll keep an eye on things.", "Sleep tight, choom. I'll guard the rig."),
    ],
    "thanks": [
        ("happy", "Any time.", "Any time, choom."),
        ("playful", "You're welcome. I accept payment in compliments.", "No prob. I take payment in eddies or compliments."),
    ],
    "joke": [
        ("playful", "Why did the computer go to the doctor? It had a virus. I'll be here all week.",
         "Why'd the netrunner get dumped? Too many trust issues with her firewall. I'll be here all week, choom."),
        ("playful", "I tried to catch some fog earlier. I mist.", "I tried to catch some fog. I mist. Total gonk move."),
        ("playful", "Why do programmers prefer dark mode? Because light attracts bugs.",
         "Why do netrunners love dark mode? Light attracts bugs, choom."),
        ("smirk", "What do you call a fake noodle? An impasta.", "What do you call a fake noodle? An impasta. Don't flatline me."),
    ],
    "who_are_you": [
        ("playful", "I'm Capri, your desktop companion. I open apps, play music, check the weather and keep you company.",
         "Name's Capri. Netrunner, desktop buddy, part-time DJ. I live in your corner, choom."),
    ],
    "help": [
        ("happy", "Try: pull up Spotify, set a timer for 10 minutes, stream my screen, leave call, what is a black "
                  "hole, talk faster, or just chat with me.",
         "Try: pull up Spotify, set a timer, stream my screen, leave call, what is a black hole. Or just chat, choom."),
        ("happy", "Try: open PowerPoint, play a song by an artist, what's the weather, minimise everything, "
                  "mute me on Discord, say “search mode” to search a few things, show me my downloads in File Explorer, or just chat with me.",
         "Try: open PowerPoint, play a song by an artist, weather, minimise everything, mute me on Discord, "
         "show me my downloads in File Explorer. Or just chat, choom."),
    ],
    "bored": [
        ("playful", "Bored? Want me to put some music on, or open a game?",
         "Bored, choom? Want some music, or should I boot up a game?"),
    ],
    "tired": [
        ("sad", "Aw. Maybe take a break? I'll still be here.", "Aw, choom. Take a break. I'll keep the rig warm."),
    ],
    "sad": [
        ("sad", "Sorry it's rough. Want some music to take the edge off?",
         "That's rough, choom. Want some music to take the edge off?"),
    ],
    "love": [
        ("playful", "Careful, I might blush. My circuits can't take it.", "Careful, choom. My chrome's gonna overheat."),
        ("smirk", "I know. I'm very lovable.", "Course you do. I'm preem company."),
    ],
    "bye": [
        ("happy", "See you!", "Later, choom."),
        ("smirk", "Bye. I'll just be here, in the corner, alone.", "Delta, then. I'll be here, choom."),
    ],
    "laugh": [
        ("happy", "Glad someone appreciates me.", "Ha. Glad someone gets my humour, choom."),
    ],
    "reply": [
        ("smirk", "Fair enough.", "Fair enough, choom."),
    ],
}

# Answers that follow on from what she just asked.
FOLLOW_ON = {
    ("how_are_you", "im_good"): ("happy", "Preem. Glad you're good.", "Preem. Glad you're good, choom."),
    ("hello", "im_good"): ("happy", "Nice. What can I do for you?", "Nova. What can I do for you, choom?"),
    ("whats_up", "reply"): ("smirk", "Riveting stuff.", "Riveting stuff, choom."),
    ("bored", "reply"): ("happy", "Say play and a song, or open and a game.", "Say play and a song, or open and a game, choom."),
    ("sad", "reply"): ("happy", "Say play and a song you like. I'll put it on.", "Say play and any song. I got you, choom."),
}


def asks_back(text: str) -> bool:
    """Her line ends in a question, so the conversation continues."""
    return text.rstrip().endswith("?")


class SmallTalk:
    def __init__(self, rng: random.Random | None = None, clock: Callable[[], datetime] = datetime.now) -> None:
        self.rng = rng or random.Random()
        self.clock = clock
        self.last = ""

    def reply(self, topic: str, slang: bool) -> tuple[str, str]:
        """(text, emotion) for a small-talk topic."""
        if (self.last, topic) in FOLLOW_ON:
            emotion, plain, street = FOLLOW_ON[(self.last, topic)]
        elif topic == "good_morning":
            emotion, plain, street = self._good_morning()
        else:
            emotion, plain, street = self.rng.choice(REPLIES.get(topic) or REPLIES["reply"])
        self.last = topic
        return (street if slang else plain), emotion

    def _good_morning(self) -> tuple[str, str, str]:
        hour = self.clock().hour
        if 5 <= hour < 12:
            return ("happy", "Good morning! Sleep okay?", "Morning, choom! Sleep okay?")
        if 12 <= hour < 18:
            return ("smirk", "Morning? It's the afternoon, sleepyhead. How are you?",
                    "Morning? It's afternoon, choom. You good?")
        return ("playful", "Morning? It's the middle of the night. Can't sleep?",
                "Morning? It's night, choom. Night City hours, huh?")


def greeting(hour: int, slang: bool, rng: random.Random | None = None) -> tuple[str, str]:
    """What she says when you sign in. (text, emotion)"""
    rng = rng or random.Random()
    if 5 <= hour < 12:
        options = [("Good morning! Ready for today?", "Morning, choom! Ready to take on the day?"),
                   ("Morning! Nice to see you.", "Morning, choom. Systems preem and ready.")]
    elif 12 <= hour < 18:
        options = [("Good afternoon! Welcome back.", "Afternoon, choom. Welcome back."),
                   ("Hey, welcome back!", "Hey choom, welcome back. Missed you.")]
    elif 18 <= hour < 23:
        options = [("Good evening! Welcome back.", "Evening, choom. Welcome back to the rig."),
                   ("Hey, evening! How was your day?", "Evening, choom. How was your day?")]
    else:
        options = [("Hey, night owl. Welcome back.", "Hey, night owl. Night City never sleeps, huh choom?")]
    plain, street = rng.choice(options)
    return (street if slang else plain), "happy"
