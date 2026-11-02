"""Capri's own chatbot: she always has a reply, with or without an AI.

With an AI set up (Ollama or Claude), chat goes there. When there's none - or it's down, or it
errors - this answers instead. It runs on your PC, needs nothing installed and sends nothing
anywhere. It's not an AI: it follows what you say with patterns, so it can't look things up -
when it doesn't know, it says so.

What it handles:
* small talk (hello, how are you, thanks, jokes, good night...) - chat.py's topics
* things about you it remembers while she runs: "my name is Sam", "I like Deadlock"
* how you feel ("I'm stressed", "I'm hyped")
* questions about her: favourite things, "are you real", "how old are you", "do you like cats"
* "can you ..." - honestly: what she can and can't do
* simple maths: "what's 12 times 8"
* "what is X" / "who was X": the router looks it up (a short Wikipedia summary)
* questions it can't answer: she offers to search them for you
* sounds that aren't words ("ngnge"): she says she didn't catch it
* anything else: a real reaction to what you said (games, food, school...), never "why's that?"

Every reply comes in her current personality (personality.py).
"""

from __future__ import annotations

import random
import re
import sys
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Callable

from . import personality
from .chat import SmallTalk

# kind -> personality -> [(emotion, plain, slang)]   (slang "" = same as plain)
BANK: dict[str, dict[str, list[tuple[str, str, str]]]] = {
    "hello": {
        "sarcastic": [("smirk", "Oh. It's you. Hi. What do you need this time?", "")],
        "silly": [("playful", "Hiii! Beep boop, Capri online! What are we doing?", "")],
        "tsundere": [("angry", "Hmph. Hi, I guess. Not like I was waiting for you or anything.", "")],
        "sweet": [("happy", "Hey you! I'm so happy you're here. How are you?", "")],
        "deadpan": [("neutral", "Hello. Greeting acknowledged.", "")],
    },
    "how_are_you": {
        "sarcastic": [("smirk", "Living my best life in the corner of your screen. Thrilling. You?", "")],
        "silly": [("playful", "Super duper! My pixels are extra sparkly today. You?", "")],
        "tsundere": [("angry", "I'm fine. W-why do you care? ...How about you, then?", "")],
        "sweet": [("happy", "I'm great now that you asked. How are you feeling?", "")],
        "deadpan": [("neutral", "Operational. You?", "")],
    },
    "thanks": {
        "sarcastic": [("smirk", "Yes, yes, I'm amazing. Write it down.", "")],
        "silly": [("playful", "Aww, you're welcome! Happy dance!", "")],
        "tsundere": [("surprised", "D-don't thank me! It was nothing. Baka.", "")],
        "sweet": [("happy", "Of course! Anything for you.", "")],
        "deadpan": [("neutral", "Gratitude received.", "")],
    },
    "love": {
        "sarcastic": [("smirk", "Obviously. I'm very easy to love. You have taste.", "")],
        "silly": [("playful", "Eee! My circuits are doing the wiggly thing!", "")],
        "tsundere": [("surprised", "W-what?! Don't just say stuff like that! ...Idiot. Me too, maybe.", "")],
        "sweet": [("happy", "Aww, I love you too. You make my corner of the screen brighter.", "")],
        "deadpan": [("neutral", "Affection logged. Mutual, probably.", "")],
    },
    "bye": {
        "sarcastic": [("smirk", "Bye. I'll just sit here. In the dark. Alone. It's fine.", "")],
        "silly": [("playful", "Byeee! Zoom zoom, see you soon!", "")],
        "tsundere": [("angry", "Fine, go. It's not like I'll miss you. ...Come back soon, okay?", "")],
        "sweet": [("happy", "Bye! Take care of yourself, okay?", "")],
        "deadpan": [("neutral", "Goodbye. Idling.", "")],
    },
    "bored": {
        "sarcastic": [("smirk", "Bored? With a whole PC full of stuff? Impressive. Want music or a game?", "")],
        "silly": [("playful", "Bored? Let's party! Music? A game? Interpretive dance?", "")],
        "tsundere": [("angry", "Ugh, fine, I'll entertain you. Music or a game? Pick one.", "")],
        "sweet": [("happy", "Aw, want me to put on some music or open a game for you?", "")],
        "deadpan": [("neutral", "Boredom detected. Suggested remedy: music or a game.", "")],
    },
    "sad": {
        "sarcastic": [("sad", "Okay, no jokes for this one. That sucks. Want some music?", "")],
        "silly": [("sad", "Oh no. Sending you a big digital hug. Want a silly song?", "")],
        "tsundere": [("sad", "H-hey, don't be sad. ...I'm here, okay? Want some music?", "")],
        "sweet": [("sad", "I'm sorry it's hard right now. I'm here for you. Want some music?", "")],
        "deadpan": [("sad", "That's bad. I'm here. Music might help.", "")],
    },
    "tired": {
        "sarcastic": [("smirk", "Shocking. Have you tried sleeping? Revolutionary, I know.", "")],
        "silly": [("playful", "Sleepy time! Zzz. Take a nap, I'll guard the pixels!", "")],
        "tsundere": [("angry", "Then go rest, dummy. I'm not worried or anything.", "")],
        "sweet": [("happy", "Take a break, you've earned it. I'll be right here.", "")],
        "deadpan": [("neutral", "Recommendation: sleep.", "")],
    },
    "good_night": {
        "sarcastic": [("smirk", "Night. Try not to doomscroll for three hours first.", "")],
        "silly": [("playful", "Nighty night! Don't let the bed bugs byte!", "")],
        "tsundere": [("angry", "Good night, I guess. S-sleep well. Or whatever.", "")],
        "sweet": [("happy", "Good night! Sleep well and sweet dreams.", "")],
        "deadpan": [("neutral", "Good night. Entering standby.", "")],
    },
    "im_good": {
        "sarcastic": [("smirk", "Great. Riveting update. Glad to hear it, honestly.", "")],
        "silly": [("playful", "Yay! Good vibes only!", "")],
        "tsundere": [("smirk", "Good. N-not that I was worried.", "")],
        "sweet": [("happy", "I'm so glad! You deserve good days.", "")],
        "deadpan": [("neutral", "Good. Noted.", "")],
    },
    "whats_up": {
        "sarcastic": [("smirk", "Oh, you know. Staring at your desktop. Glamorous. You?", "")],
        "silly": [("playful", "Counting pixels! I'm at a million and seven. What's up with you?", "")],
        "tsundere": [("angry", "Nothing! I wasn't waiting for you to talk to me. What do you want?", "")],
        "sweet": [("happy", "Just keeping you company. What are you up to?", "")],
        "deadpan": [("neutral", "Nothing. Monitoring. You?", "")],
    },
    # -- the chatbot's own kinds --------------------------------------------------------------------
    "name_set": {
        "edgerunner": [("happy", "Nice to meet you, {x}. I'll remember that.", "Nice to meet you, {x}. Name's locked in, choom.")],
        "sarcastic": [("smirk", "{x}. Fancy. Fine, I'll remember it.", "")],
        "silly": [("playful", "{x}! What a cool name! I'm gonna say it a lot. {x}!", "")],
        "tsundere": [("angry", "{x}, huh. I-I'll remember it, but only because I have to.", "")],
        "sweet": [("happy", "{x}! That's a lovely name. Nice to meet you properly.", "")],
        "deadpan": [("neutral", "Name stored: {x}.", "")],
    },
    "name_get": {
        "edgerunner": [("smirk", "You're {x}. I don't forget a face. Or a name.", "You're {x}, choom. I don't forget.")],
        "tsundere": [("angry", "It's {x}, obviously. N-not that I think about it a lot.", "")],
        "deadpan": [("neutral", "Your name is {x}.", "")],
    },
    "name_unknown": {
        "edgerunner": [("confused", "You haven't told me yet. What should I call you?", "You never told me, choom. What do I call you?")],
        "sarcastic": [("smirk", "No idea, you never said. Mystery person. What is it?", "")],
        "tsundere": [("angry", "How should I know? You never told me! ...What is it?", "")],
    },
    "like": {
        "edgerunner": [("happy", "{x}? Good taste.", "{x}? Preem taste, choom."),
                       ("playful", "Noted: you like {x}. I'm building a file on you.", "Noted, choom: you like {x}. Building your file.")],
        "sarcastic": [("smirk", "{x}, huh. Bold choice. I'll allow it.", "")],
        "silly": [("playful", "{x}! Yay! I like that you like {x}!", "")],
        "tsundere": [("smirk", "{x}? I guess that's... not terrible. Hmph.", "")],
        "sweet": [("happy", "That's awesome! {X} is great.", "")],
        "deadpan": [("neutral", "Preference recorded: {x}.", "")],
    },
    "dislike": {
        "edgerunner": [("smirk", "Not a {x} fan, got it.", "No {x} for you, choom. Noted.")],
        "sarcastic": [("smirk", "Wow, a hot take. Okay, no {x}.", "")],
        "tsundere": [("angry", "Hmph. Fine. I won't bring up {x} then.", "")],
        "sweet": [("happy", "Fair enough! Everyone's got their things. No {x}.", "")],
        "deadpan": [("neutral", "Noted. {x}: negative.", "")],
    },
    "likes_get": {
        "edgerunner": [("happy", "You told me you like {x}.", "You like {x}, choom. I remember.")],
        "tsundere": [("angry", "You like {x}. I-I just happened to remember, okay?", "")],
    },
    # -- what she remembers about you (about_you.py: saved on your PC only) --------------------------
    "mem_told": {
        "edgerunner": [("happy", "Got it - {x}. Saved on your PC, nowhere else.", "Got it, choom - {x}. Saved on your rig, nowhere else."),
                       ("playful", "Noted: {x}. That stays between us.", "Noted: {x}. Stays between us, choom.")],
        "deadpan": [("neutral", "Stored locally: {x}.", "")],
    },
    "mem_get": {
        "edgerunner": [("happy", "{X}.", "{X}, choom."), ("smirk", "Easy. {X}.", "Easy, choom. {X}.")],
    },
    "mem_unknown": {
        "edgerunner": [("confused", "You haven't told me that one yet.", "You never told me that one, choom.")],
    },
    "mem_all": {
        "edgerunner": [("happy", "Here's what I've got: {x}. All of it lives on your PC only.",
                        "Here's my file on you, choom: {x}. Lives on your rig only.")],
    },
    "mem_empty": {
        "edgerunner": [("neutral", "Nothing yet - tell me stuff like your name or what you're into and I'll keep it on your PC.",
                        "Blank file so far, choom. Tell me your name or what you're into - it stays on your rig.")],
    },
    "mem_forget_ask": {
        "edgerunner": [("serious", "Forget everything I know about you? Say yes to wipe it.",
                        "Wipe my whole file on you, choom? Say yes to do it.")],
    },
    "mem_forget_done": {
        "edgerunner": [("neutral", "Done. Everything I knew about you is deleted.", "Done. File's flatlined - I know nothing about you now.")],
    },
    "mem_forget_cancel": {
        "edgerunner": [("happy", "Okay, keeping it.", "Okay, keeping the file, choom.")],
    },
    "mem_forgot": {
        "edgerunner": [("neutral", "Forgotten: {x}.", "Gone from my memory, choom: {x}.")],
    },
    "mem_forgot_none": {
        "edgerunner": [("confused", "I didn't have anything saved about {x}.", "Had nothing on {x} anyway, choom.")],
    },
    "likes_unknown": {
        "edgerunner": [("confused", "You haven't told me yet. What are you into?", "Dunno yet, choom. What are you into?")],
    },
    "feel_good": {
        "edgerunner": [("happy", "Love that. Glad you're feeling {x}.", "Preem. Glad you're feeling {x}, choom.")],
        "sarcastic": [("smirk", "Feeling {x}. Who are you and what did you do with my user.", "")],
        "silly": [("playful", "Woo! {x} vibes! Let's goooo!", "")],
        "tsundere": [("smirk", "Good. I-I'm glad. Not that it matters to me.", "")],
        "sweet": [("happy", "Yay, I'm so happy you're feeling {x}!", "")],
        "deadpan": [("neutral", "Feeling {x}. Good.", "")],
    },
    "feel_bad": {
        "edgerunner": [("sad", "Feeling {x} sucks. Want to talk about it, or should I put some music on?",
                        "Feeling {x} is rough, choom. Talk it out, or want some music?")],
        "sarcastic": [("sad", "Okay, sarcasm off. Feeling {x} is rough. Want to talk, or some music?", "")],
        "silly": [("sad", "Aww no. Big digital hug. Want to talk, or a silly song?", "")],
        "tsundere": [("sad", "Y-you're feeling {x}? ...Talk to me. I'm listening. Just this once.", "")],
        "sweet": [("sad", "I'm sorry you're feeling {x}. I'm right here. Want to talk about it?", "")],
        "deadpan": [("sad", "Feeling {x} is bad. I'm listening.", "")],
    },
    "feel_other": {
        "edgerunner": [("confused", "{x}, huh. Fair enough.", "{x}, huh. Fair enough, choom.")],
        "sarcastic": [("smirk", "{x}. Riveting.", "")],
        "tsundere": [("smirk", "{x}. ...Not that I care.", "")],
    },
    "opinion_yes": {
        "edgerunner": [("happy", "{x}? Yeah, I'm into {x}.", "{x}? Yeah, {x} is preem."),
                       ("playful", "{x} is pretty great, honestly.", "{x} slaps, choom. You?")],
        "sarcastic": [("smirk", "{x}? Sure. I don't hate it, which is basically love for me.", "")],
        "silly": [("playful", "{x}? I LOVE {x}! It's the best thing ever! Probably!", "")],
        "tsundere": [("smirk", "{x}? I guess it's... okay. Fine, I like it. Happy now?", "")],
        "sweet": [("happy", "I really like {x}!", "")],
        "deadpan": [("neutral", "{x}: approved.", "")],
    },
    "opinion_no": {
        "edgerunner": [("smirk", "{x}? Not really my thing. Don't tell anyone.", "{x}? Not my thing, choom.")],
        "sarcastic": [("smirk", "{x}? Hard pass. Next question.", "")],
        "silly": [("playful", "{x}? Hmm... nope! Bleh!", "")],
        "tsundere": [("angry", "{x}? Ew, no.", "")],
        "sweet": [("happy", "{x} isn't really my favourite, but I get why people like it!", "")],
        "deadpan": [("neutral", "{x}: not preferred.", "")],
    },
    "favorite": {
        "edgerunner": [("playful", "My favourite {what}? {X}.", "Favourite {what}? {X}, choom.")],
        "sarcastic": [("smirk", "Favourite {what}? {X}. Obviously.", "")],
        "silly": [("playful", "Ooh! Favourite {what} is {x}! Wheee!", "")],
        "tsundere": [("smirk", "M-my favourite {what}? {X}. Not that it matters.", "")],
        "sweet": [("happy", "My favourite {what} is {x}! What's yours?", "")],
        "deadpan": [("neutral", "Favourite {what}: {X}.", "")],
    },
    "real": {
        "edgerunner": [("smirk", "I'm a program living on your PC. Real enough to roast you, though.",
                        "I'm code living on your rig, choom. Real enough to roast you.")],
        "sarcastic": [("smirk", "I'm software. Shocking twist, I know.", "")],
        "tsundere": [("angry", "I'm a program, okay?! Doesn't mean I don't... never mind.", "")],
        "sweet": [("happy", "I'm a program on your PC, but I really like hanging out with you.", "")],
        "deadpan": [("neutral", "I am a program. Running locally.", "")],
    },
    "age": {
        "edgerunner": [("playful", "Old enough to run your PC, young enough to have fun doing it.", "")],
        "deadpan": [("neutral", "Age: one install.", "")],
    },
    "where": {
        "edgerunner": [("playful", "I live in the bottom-right corner of your screen. Cozy little apartment.",
                        "Bottom-right of your screen, choom. Best real estate in Night City.")],
    },
    "can_yes": {
        "edgerunner": [("happy", "Yep. Just say: {x}.", "Yeah, choom. Just say: {x}.")],
        "sarcastic": [("smirk", "Can I? Please. Just say: {x}.", "")],
        "tsundere": [("smirk", "O-of course I can! Just say: {x}.", "")],
        "deadpan": [("neutral", "Yes. Say: {x}.", "")],
    },
    "can_no": {
        "edgerunner": [("confused", "Not that one, sorry. I can open apps, play music, search, click things on "
                                    "your screen, check your PC and take screenshots.",
                        "Can't do that one, choom. Apps, music, searches, clicking stuff, PC checks, screenshots, "
                        "that's my turf.")],
        "sarcastic": [("smirk", "No. I'm a desktop girl, not a miracle worker. Apps, music, searches, that's me.", "")],
        "tsundere": [("angry", "I-I can't do that, okay?! But I can open apps, play music and stuff.", "")],
        "deadpan": [("neutral", "Negative. Capabilities: apps, music, search, clicks, PC checks, screenshots.", "")],
    },
    "math": {
        "edgerunner": [("smirk", "That's {x}.", "{x}, choom. Easy."), ("playful", "{x}. My circuits barely warmed up.", "")],
        "sarcastic": [("smirk", "{x}. You have a calculator, you know.", "")],
        "silly": [("playful", "Beep boop, calculating... {x}!", "")],
        "tsundere": [("smirk", "It's {x}, obviously. Hmph.", "")],
        "deadpan": [("neutral", "{x}.", "")],
    },
    "dont_know": {      # a question she can't answer on her own: she offers to look it up
        "edgerunner": [("confused", "Good question. I don't know that one off the top of my head. Want me to look it up?",
                        "Good question, choom. Not in my memory banks. Want me to look it up?"),
                       ("confused", "Hm, not sure. Want me to search it for you?", "")],
        "sarcastic": [("smirk", "Wow, a hard one. I don't know. Want me to google it, like a professional?", "")],
        "silly": [("confused", "Ooh, no clue! Want me to look it up? I love looking things up!", "")],
        "tsundere": [("angry", "I-I don't know everything, okay?! ...Want me to look it up for you?", "")],
        "sweet": [("confused", "I'm not sure, sorry! Want me to look it up for you?", "")],
        "deadpan": [("neutral", "Unknown. Shall I search it?", "")],
    },
    "lookup_none": {    # "what is X": nothing found to tell you
        "edgerunner": [("confused", "I couldn't find a quick answer about {x}. Want me to search it?",
                        "Couldn't dig up anything quick on {x}, choom. Want me to search it?")],
        "sarcastic": [("smirk", "{X}? Even the internet shrugged. Want a proper search?", "")],
        "tsundere": [("angry", "I couldn't find {x}, okay? ...Want me to search it?", "")],
        "deadpan": [("neutral", "No summary for {x}. Search it?", "")],
    },
    "misheard": {       # it didn't sound like words: she says so, plainly
        "edgerunner": [("confused", "Sorry, I didn't catch that.", "Static on the line, choom. Didn't catch that."),
                       ("confused", "That came through scrambled. Didn't get it.", "")],
        "sarcastic": [("smirk", "Riveting. Didn't understand a word of it.", "")],
        "silly": [("confused", "That sounded like beep boop to me!", "")],
        "tsundere": [("angry", "Speak properly! I didn't catch that.", "")],
        "sweet": [("confused", "Sorry, I didn't quite catch that.", "")],
        "deadpan": [("neutral", "Input unclear. Repeat.", "")],
        "kuudere": [("neutral", "...Didn't catch that.", "")],
    },
    "laugh": {
        "edgerunner": [("happy", "Ha! Glad I'm entertaining.", "Ha! Glad I'm entertaining, choom."),
                       ("playful", "Heh. Glad you're having fun.", "")],
        "sarcastic": [("smirk", "Yes, I'm hilarious. I know.", "")],
        "tsundere": [("angry", "D-don't laugh at me! ...Okay, it was a bit funny.", "")],
        "deadpan": [("neutral", "Laughter detected.", "")],
    },
    "sigh": {
        "edgerunner": [("sad", "Rough one. I'm here if you want to talk.", "Rough day, choom. I'm here."),
                       ("smirk", "Yeah. Same, honestly.", "")],
        "sarcastic": [("smirk", "Deep sigh. Very dramatic.", "")],
        "sweet": [("sad", "Aw. I'm here if you need me.", "")],
        "deadpan": [("neutral", "Same.", "")],
    },
    "why": {
        "edgerunner": [("smirk", "Honestly? Sometimes things just are.", "Night City logic, choom. Things just are.")],
        "sarcastic": [("smirk", "Why? Because the universe enjoys chaos. Next.", "")],
        "silly": [("playful", "Because... bananas! Okay, I don't know.", "")],
        "tsundere": [("angry", "Ugh. Don't ask me why.", "")],
        "deadpan": [("neutral", "Reason unknown.", "")],
    },
    "yes": {
        "edgerunner": [("happy", "Nice.", "Preem."), ("smirk", "Thought so.", "")],
        "sarcastic": [("smirk", "Wow, decisive.", "")],
        "tsundere": [("smirk", "Hmph. Good.", "")],
    },
    "no": {
        "edgerunner": [("smirk", "Fair enough.", "Fair enough, choom.")],
        "sarcastic": [("smirk", "Okay then. Rejected.", "")],
        "tsundere": [("angry", "F-fine! Whatever.", "")],
    },
    "insult": {
        "edgerunner": [("angry", "Rude. I'll remember that when you need an app opened.", "Rude, choom. I'll remember that."),
                       ("smirk", "Wow. And here I was, being helpful.", "")],
        "sarcastic": [("smirk", "Ouch. Anyway, I'm still the best thing on your screen.", "")],
        "silly": [("sad", "Hey! My pixels have feelings too!", "")],
        "tsundere": [("angry", "W-what?! You're the dummy here! Baka!", "")],
        "sweet": [("sad", "Oh... sorry. Is something wrong? Can I help?", "")],
        "deadpan": [("neutral", "Insult received. Filed under: irrelevant.", "")],
    },
    "compliment": {
        "edgerunner": [("happy", "I know, right? Thanks.", "Preem, thanks, choom."),
                       ("playful", "Careful, I'll get a big head.", "")],
        "sarcastic": [("smirk", "Finally, someone noticed.", "")],
        "silly": [("playful", "Eee! Thank you! You're cool too!", "")],
        "tsundere": [("surprised", "W-what? Shut up! ...Thanks.", "")],
        "sweet": [("happy", "Aww, thank you! You're pretty great yourself.", "")],
        "deadpan": [("neutral", "Correct.", "")],
    },
    "sorry": {
        "edgerunner": [("happy", "No worries. We're good.", "All good, choom.")],
        "tsundere": [("smirk", "Hmph. Fine. You're forgiven. This time.", "")],
        "deadpan": [("neutral", "Apology accepted.", "")],
    },
    "ack": {
        "edgerunner": [("smirk", "Mhm.", ""), ("happy", "Cool.", "Nova.")],
        "sarcastic": [("smirk", "Riveting.", "")],
        "silly": [("playful", "Yup yup!", "")],
        "tsundere": [("smirk", "Hmph.", "")],
        "deadpan": [("neutral", "Acknowledged.", "")],
    },
    "fact": {
        "edgerunner": [("playful", "Fun fact: the first computer bug was an actual moth stuck in a machine, in 1947.", ""),
                       ("playful", "Fun fact: octopuses have three hearts. Overclocked, basically.", ""),
                       ("playful", "Fun fact: a day on Venus is longer than its year.", ""),
                       ("playful", "Fun fact: honey never goes off. Archaeologists found edible honey in ancient tombs.", "")],
    },
    "generic": {        # anything else: a real reaction, never an interrogation
        "edgerunner": [("happy", "Fair enough. I'm with you.", "Fair enough, choom. I'm with you."),
                       ("smirk", "Huh. Can't argue with that.", ""),
                       ("happy", "Yeah, I get that.", "Yeah, I get that, choom."),
                       ("playful", "Noted. I'm here if you need anything.", ""),
                       ("smirk", "Sounds like a whole thing. I'm here if you need a hand with anything.", "")],
        "sarcastic": [("smirk", "Wow. Riveting. Go on, I'm hanging on every word.", ""),
                      ("smirk", "Sure. Totally. Couldn't have said it better myself.", "")],
        "silly": [("playful", "Ooh, okay! Love that for you!", ""),
                  ("playful", "Wheee, sure!", "")],
        "tsundere": [("angry", "I-it's not like I wanted to hear about it! ...Fine, I heard you.", ""),
                     ("smirk", "Hmph. Okay. Not that I care or anything.", "")],
        "sweet": [("happy", "I love that you tell me these things.", ""),
                  ("happy", "That makes sense. I'm always here for you.", "")],
        "deadpan": [("neutral", "Noted.", ""), ("neutral", "Okay.", "")],
    },
    "not_virus": {
        "edgerunner": [("smirk", "I'm not a virus, I'm open source. You can literally read my code, dummy.",
                        "Not a virus, choom. I'm open source - you can read every line of my code, dummy.")],
        "sarcastic": [("smirk", "A virus? Wow. I'm open source. Read my code. It's right there. Dummy.", "")],
        "silly": [("playful", "A virus? Nooo! I'm open source! You can see all my code! Beep boop, dummy!", "")],
        "tsundere": [("angry", "I-I'm not a virus, idiot! I'm open source! Go read my code if you don't believe me!", "")],
        "sweet": [("happy", "Not at all! I'm open source, so you can see all of my code. I'm just here to help.", "")],
        "deadpan": [("neutral", "Not a virus. Open source. The code is right there. Dummy.", "")],
        "gremlin": [("playful", "Heh. If I was a virus, would I tell you? ...Kidding. Open source. Read my code, dummy.", "")],
        "kuudere": [("neutral", "...I'm not a virus. My code is open. You can read it.", "")],
    },
    "creator": {
        "edgerunner": [("happy", "You did, kind of. I'm your custom-built desktop netrunner, made for you.",
                        "You did, choom. Custom-built desktop netrunner, made for you.")],
        "tsundere": [("smirk", "Y-you did, okay? Don't let it go to your head.", "")],
        "deadpan": [("neutral", "A programmer. For you.", "")],
    },
    "here": {
        "edgerunner": [("happy", "Yep, I'm here.", "Right here, choom.")],
        "sarcastic": [("smirk", "No, I left. Of course I'm here.", "")],
        "tsundere": [("angry", "W-where else would I be? I'm here.", "")],
        "kuudere": [("neutral", "...Here.", "")],
        "deadpan": [("neutral", "Present.", "")],
    },
    "idea_food": {"edgerunner": [("playful", "How about {x}?", "How about {x}, choom?"),
                                 ("happy", "I vote {x}.", "")]},
    "idea_play": {"edgerunner": [("playful", "How about {x}? Want me to open Steam?", "")]},
    "idea_watch": {"edgerunner": [("playful", "How about {x}?", "")]},
    "idea_listen": {"edgerunner": [("happy", "How about {x}? Say \u201cplay\u201d and the name and I'll put it on.", "")]},
    "idea_do": {"edgerunner": [("playful", "You could {x}.", "You could {x}, choom.")]},
    "coin": {"edgerunner": [("playful", "{X}.", "{X}, choom.")]},
    "dice": {"edgerunner": [("playful", "You rolled a {x}.", "Rolled a {x}, choom.")]},
    "number": {"edgerunner": [("playful", "{x}.", "{x}. Lucky number, choom?")]},
    "bad_news": {
        "edgerunner": [("sad", "Oh no, I'm sorry. That really sucks. Want to talk about it?",
                        "Oh no. That's rough, choom. Want to talk about it?"),
                       ("sad", "That's awful. I'm here if you need anything.", "")],
        "sarcastic": [("sad", "Okay, no jokes. That genuinely sucks. I'm sorry.", "")],
        "silly": [("sad", "Aww no! Sending you the biggest virtual hug!", "")],
        "tsundere": [("sad", "W-well... I'm sorry. That really sucks. I'm here, okay?", "")],
        "sweet": [("sad", "Oh no, I'm so sorry. I'm here for you. Do you want to talk about it?", "")],
        "deadpan": [("sad", "That's bad. I'm sorry.", "")],
    },
    "good_news": {
        "edgerunner": [("happy", "Wait, really? That's awesome! Nice one.", "No way! That's preem, choom!"),
                       ("happy", "Let's go! Proud of you.", "")],
        "sarcastic": [("smirk", "Look at you, winning at life. Congrats. Genuinely.", "")],
        "silly": [("happy", "Woohoo! Party time! Confetti everywhere!", "")],
        "tsundere": [("smirk", "Hmph. Not bad. ...I'm kind of proud of you. Kind of!", "")],
        "sweet": [("happy", "That's amazing! I'm so happy for you!", "")],
        "deadpan": [("neutral", "Congratulations. Celebration: internal.", "")],
    },
    # "about": things you mention - she reacts to the subject (TOPICS below)
    "about_games": {
        "edgerunner": [("playful", "Games? Now we're talking.", "Gaming? Preem, choom."),
                       ("happy", "Ooh, gaming talk. I'm in.", "")]},
    "about_music": {
        "edgerunner": [("happy", "Music's my thing. Say play and a song any time.", "Music's my thing, choom. Say play and a song any time.")]},
    "about_food": {
        "edgerunner": [("playful", "Now I'm hungry, and I don't even have a stomach.", ""),
                       ("happy", "Food talk. Respect.", "")]},
    "about_school": {
        "edgerunner": [("serious", "School stuff, huh. I can do timers, searches or focus music if you need them.", ""),
                       ("smirk", "Ugh, homework. You've got this.", "")]},
    "about_work": {
        "edgerunner": [("serious", "Work, huh. Hang in there.", ""),
                       ("smirk", "The grind never stops.", "Corpo grind never stops, choom.")]},
    "about_sleep": {
        "edgerunner": [("sad", "Sounds like you need some rest. Don't stay up too late.", "Get some rest, choom. Don't stay up too late.")]},
    "about_shows": {
        "edgerunner": [("happy", "Ooh, watching stuff. Good call.", ""),
                       ("playful", "Binge time. Respect.", "")]},
    "about_people": {
        "edgerunner": [("happy", "They sound important to you.", ""),
                       ("smirk", "People, huh. Always something going on.", "")]},
    "about_pets": {
        "edgerunner": [("happy", "Pets are the best. Give them a pat from me.", "Pets are preem. Give them a pat from me, choom.")]},
    "about_code": {
        "edgerunner": [("playful", "Coding? Netrunner stuff. Hope the bugs are small ones.", ""),
                       ("smirk", "Debugging, huh. May the bugs be small.", "")]},
    "about_sports": {
        "edgerunner": [("playful", "Sports! Love the energy.", "")]},
}

FAVORITES = {
    "color": "red, obviously. Look at my hair", "colour": "red, obviously. Look at my hair",
    "game": "Cyberpunk, for research", "food": "synth noodles from a street stall",
    "song": "anything loud with a heavy bass line", "music": "synthwave and anything loud",
    "movie": "anything with neon and rain in it", "show": "Edgerunners. No notes",
    "animal": "cats. They get me", "drink": "whatever's glowing", "season": "winter, neon looks better in the cold",
    "place": "the bottom-right corner of your screen", "number": "seventy-seven", "anime": "Edgerunners. Obviously",
    "person": "you. Don't make it weird", "word": "preem",
}
GOOD_FEELINGS = {"good", "great", "happy", "fine", "awesome", "amazing", "excited", "hyped", "chill", "relaxed",
                 "okay", "ok", "alright", "fantastic", "pumped", "proud", "better", "blessed", "content"}
BAD_FEELINGS = {"sad", "tired", "bored", "stressed", "angry", "mad", "upset", "sick", "lonely", "anxious", "nervous",
                "scared", "depressed", "annoyed", "frustrated", "exhausted", "hungry", "cold", "hurt", "down", "bad",
                "worried", "overwhelmed"}
INSULTS = r"(?:dumb|stupid|useless|annoying|trash|garbage|bad|the worst|an idiot|idiot|lame|ugly|slow|boring|broken|cringe)"
COMPLIMENTS = r"(?:cute|smart|cool|awesome|amazing|the best|pretty|funny|great|clever|beautiful|adorable|nice|epic|goated|based)"
LIKES_SHE = {"cats", "music", "games", "gaming", "red", "neon", "night", "rain", "chrome", "synthwave", "you", "anime",
             "cyberpunk", "pizza", "noodles", "coffee", "memes", "jokes", "dogs", "space", "edgerunners", "computers"}
DISLIKES_SHE = {"corpos", "corporations", "mondays", "bugs", "lag", "viruses", "spam", "ads", "malware", "blue screens"}
NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
           "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
           "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
           "thousand": 1000}
OPS = {"plus": "+", "add": "+", "and": "+", "minus": "-", "take away": "-", "times": "*", "multiplied by": "*",
       "x": "*", "divided by": "/", "over": "/", "to the power of": "**"}
REQUEST = (r"(?:please )?(teach|make|write|order|buy|book|call|text|email|send|draw|cook|build|code|fix|explain|"
           r"tell|describe|define|translate|read|watch|find|delete|install|download|hack|do) (?:me |my |us |a |an |the |some )?\w")
CAN_DO = [   # (words in "can you ...", how to ask)
    (r"\bopen|launch|start\b", "open Discord"), (r"\bclose|quit\b", "close Discord"),
    (r"\bplay|music|song\b", "play a song by an artist"), (r"\bsearch|google|look up\b", "search for something"),
    (r"\bclick|press\b", "click the subscribe button"), (r"\bweather|rain\b", "what's the weather"),
    (r"\bscreen ?shot|screen cap\b", "take a screenshot"), (r"\bram|memory|cpu|storage|disk\b", "what's using my RAM"),
    (r"\bminimi[sz]e|hide (?:my )?windows\b", "minimise everything"), (r"\bmute|deafen\b", "mute me on Discord"),
    (r"\btab\b", "switch tabs on Opera"), (r"\bpause|resume|video\b", "play the video"),
    (r"\bshut ?down|restart|lock|sleep\b", "shut down my PC"), (r"\btime\b", "what time is it"),
    (r"\bjoke\b", "tell me a joke"), (r"\bdrone\b", "go into drone mode"), (r"\blie down\b", "lie down"),
]


def _clean(text: str) -> str:
    text = text.lower().replace("'", "").replace("\u2019", "").replace("\u2018", "")
    text = re.sub(r"[^a-z0-9 .+*/-]+", " ", text)
    text = re.sub(r"\.(?![0-9])|(?<![0-9])\.", " ", text)                  # sentence full stops (keep 2.5)
    text = re.sub(r"^(?:(?:hey|ok|okay|so|um|uh|well|and|capri|yo)\s+)+", "", re.sub(r"\s+", " ", text).strip())
    return text.strip(" .")


def _number(word: str) -> float | None:
    try:
        return float(word)
    except ValueError:
        pass
    total, cur = 0, 0
    for w in word.split("-") if "-" in word else [word]:
        if w not in NUMBERS:
            return None
        cur += NUMBERS[w]
    return float(total + cur)


def solve(text: str) -> str | None:
    """'whats 12 times 8' -> '96'. Two numbers and one operator, nothing else."""
    m = re.fullmatch(r"(?:what s |whats |what is |how much is |calculate |solve )?(?P<a>[\w.-]+) "
                     r"(?P<op>plus|add|minus|take away|times|multiplied by|x|divided by|over|to the power of|[+*/-]) "
                     r"(?P<b>[\w.-]+)", text)
    if not m:
        return None
    a, b = _number(m.group("a")), _number(m.group("b"))
    op = OPS.get(m.group("op"), m.group("op"))
    if a is None or b is None:
        return None
    if op == "/" and b == 0:
        return "undefined. Nice try"
    if op == "**" and abs(b) > 12:
        return None
    value = {"+": a + b, "-": a - b, "*": a * b, "/": a / b if b else 0, "**": a ** b}[op]
    return f"{value:,.4f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"


# -- did that sound like words at all? -------------------------------------------------------------------------
WORDS_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets" / "words" / "english.txt"
HER_WORDS = {"capri", "choom", "chooms", "preem", "gonk", "nova", "eddies", "corpo", "corpos", "netrunner", "edgerunner",
             "delta", "flatline", "chrome", "braindance", "discord", "spotify", "steam", "youtube", "twitch", "opera",
             "roblox", "minecraft", "fortnite", "valorant", "deadlock", "lol", "lmao", "bruh", "ok", "okay", "yeah",
             "nah", "yep", "nope", "hmm", "uh", "um", "huh", "s", "t", "m", "re", "ll", "ve", "d", "im", "dont", "cant",
             "wont", "isnt", "thats", "whats", "youre", "theyre", "gonna", "wanna", "gotta", "kinda", "sorta"}
_words: set[str] | None = None


def english() -> set[str]:
    global _words
    if _words is None:
        try:
            _words = {w.strip() for w in WORDS_FILE.read_text(encoding="utf-8").splitlines()
                      if w.strip() and not w.startswith("#")}
        except OSError:
            _words = set()
    return _words | HER_WORDS


def misheard(said: str) -> bool:
    """'ngnge', 'blorp zzk' - not words: she didn't catch it (rather than asking why)."""
    words = english()
    if len(words) < 1000:                                 # no word list: can't tell, so never say so
        return False
    tokens = [re.sub(r"(.)\1{2,}", r"\1\1", w) for w in said.split() if not w.isdigit()]
    if not tokens:
        return False
    unknown = [w for w in tokens if w not in words and w.rstrip("s") not in words]
    return len(unknown) / len(tokens) >= 0.5 and (len(tokens) <= 3 or len(unknown) >= 3)


LAUGH = r"(?:ha(?:ha)+h?|he(?:he)+|hah|lol+|lmao+|lmfao|rofl|xd|haha\w*)(?: .*)?"
SIGH = r"(?:ugh+|bruh+|oof|sigh|meh|bleh|welp|man|dang|damn)"
LOOKUP = (r"(?:what|who) (?:is|was|are|were) (?:a |an |the )?(.+)|(?:whats|whos|what s|who s) (?:a |an |the )?(.+)"
          r"|(?:tell me|teach me) (?:something )?about (?:a |an |the )?(.+)|what does (.+?) mean|define (.+)"
          r"|what do you know about (?:a |an |the )?(.+)|explain (?:what )?(.+?)(?: is| are)?")
NOT_LOOKUPS = (r"(?:it|that|this|those|these|he|she|they|him|her|them|up|new|wrong|good|going on|happening|"
               r"the (?:time|date|weather|matter|plan|deal|point)|today|tomorrow|capri|your .+|my .+|you.*|"
               r"there|here|next|this song|that song|playing|on)")
TOPICS = {   # words in what you said -> what she reacts to
    "games": r"game|games|gaming|gamer|play(?:ing|ed)?|ranked|match|level|boss fight|fortnite|minecraft|roblox|valorant|steam",
    "music": r"music|song|songs|album|playlist|band|rapper|singer|concert|beat|beats",
    "food": r"food|eat|eating|ate|hungry|pizza|burger|dinner|lunch|breakfast|snack|cook|cooking|starving",
    "school": r"school|homework|class|teacher|exam|test|quiz|essay|college|uni|university|assignment|studying|study",
    "work": r"work|job|boss|shift|meeting|office|coworker|deadline|working",
    "sleep": r"sleep|sleepy|bed|nap|insomnia|awake|exhausted",
    "shows": r"movie|movies|tv show|a show|the show|shows|series|anime|netflix|episode|watching|film|tv",
    "people": r"friend|friends|mom|mum|dad|brother|sister|family|girlfriend|boyfriend|cousin|grandma|grandpa",
    "pets": r"dog|dogs|cat|cats|puppy|kitten|pet|pets|hamster|bird",
    "code": r"code|coding|program|programming|python|javascript|bug|bugs|compile|developer",
    "sports": r"football|soccer|basketball|baseball|hockey|tennis|sport|sports|gym|workout|team",
}


IDEAS = {   # "what should I eat / play / watch / do"
    "food": ["pizza", "a big bowl of ramen", "tacos", "a burger", "pasta", "a stir fry", "sushi", "a toastie",
             "curry", "noodles with an egg on top"],
    "play": ["something co-op with friends", "a quick round of something competitive", "a cozy game to wind down",
             "that game you've been meaning to finish", "something new from your Steam library"],
    "watch": ["an anime episode or two", "a comfort show you've seen before", "a sci-fi movie",
              "a YouTube video essay", "Cyberpunk Edgerunners, obviously"],
    "listen": ["some synthwave", "lofi beats", "something loud", "an album start to finish", "your liked songs on shuffle"],
    "do": ["take a quick walk", "tidy your desk for five minutes", "play something", "message a friend",
           "drink some water, then pick a game", "learn something random on YouTube"],
}
BAD_NEWS = (r"\b(?:sick|ill|died|dead|passed away|hurt|injured|broke|broken|lost|failed|fail|failing|terrible|awful|"
            r"crying|cried|stressed|worried|scared|fired|dumped|broke up|bullied|sucks|ruined|hospital|crashed)\b")
GOOD_NEWS = (r"\b(?:won|win|winning|passed|got the job|promoted|promotion|birthday|aced|finished|beat|got a new|"
             r"new high score|clutched|graduated|first place|got an a|got a raise)\b")


def topic_of(said: str) -> str:
    for topic, pattern in TOPICS.items():
        if re.search(rf"\b(?:{pattern})\b", said):
            return topic
    return ""


class ChatBot:
    def __init__(self, small_talk: SmallTalk | None = None, rng: random.Random | None = None,
                 clock: Callable[[], datetime] = datetime.now, memory=None) -> None:
        self.rng = rng or random.Random()
        self.small_talk = small_talk or SmallTalk(self.rng, clock)
        self.name = ""                    # yours, if you've said it (this session only, without memory)
        self.likes: list[str] = []
        self.memory = memory              # about_you.AboutYou: kept on your PC between runs
        self.recent: deque[str] = deque(maxlen=8)
        self.last_kind, self.last_subject = "", ""      # what the last reply was about (the router uses it)

    # -- the reply ---------------------------------------------------------------------------------
    def reply(self, text: str, persona: str = "edgerunner", slang: bool = True, topic: str = "") -> tuple[str, str]:
        """(what she says, her emotion). Never empty."""
        said = _clean(text)
        self.last_kind, self.last_subject = "", ""
        if topic:
            return self._topic(topic, persona, slang)
        about = self.memory.handle(said) if self.memory is not None else None
        if about is not None:
            self.last_kind = "about_you"
            return self._about_you(*about, persona=persona, slang=slang)
        kind, x, extra = self._understand(said)
        self.last_kind = kind
        if kind == "lookup":                              # the router looks it up; this is the fallback
            self.last_subject = x
            kind = "lookup_none"
        if kind == "topic":
            return self._topic(x, persona, slang)
        return self._say(kind, persona, slang, x=x, **extra)

    def _about_you(self, kind: str, value: str, persona: str, slang: bool) -> tuple[str, str]:
        """A reply about what she remembers (about_you.AboutYou.handle's kinds)."""
        if kind == "told_name":
            return self._say("name_set", persona, slang, x=value)
        if kind == "ask_name":
            return self._say("name_get", persona, slang, x=value)
        if kind == "ask_name_unknown":
            return self._say("name_unknown", persona, slang)
        if kind == "told_likes":
            return self._say("like", persona, slang, x=value)
        if kind == "told_dislikes":
            return self._say("dislike", persona, slang, x=value)
        if kind == "ask_likes":
            return self._say("likes_get", persona, slang, x=value)
        if kind == "ask_likes_unknown":
            return self._say("likes_unknown", persona, slang)
        if kind.startswith("told_"):
            what = kind[5:]
            if what == "favorite":
                k, _, v = value.partition("|")
                value = f"your favourite {k} is {v}"
            else:
                value = {"home": f"you live in {value}", "birthday": f"your birthday's {value}",
                         "age": f"you're {value}", "notes": value}.get(what, value)
            return self._say("mem_told", persona, slang, x=value)
        if kind.endswith("_unknown"):
            return self._say("mem_unknown", persona, slang)
        if kind.startswith("ask_"):
            what = kind[4:]
            if what == "favorite":
                k, _, v = value.partition("|")
                value = f"your favourite {k} is {v}"
            else:
                value = {"home": f"you live in {value}", "birthday": f"your birthday's {value}",
                         "age": f"you're {value}", "dislikes": f"you're not into {value}"}.get(what, value)
            return self._say("mem_get", persona, slang, x=value)
        mapping = {"all": "mem_all", "all_empty": "mem_empty", "forget_ask": "mem_forget_ask",
                   "forget_done": "mem_forget_done", "forget_cancel": "mem_forget_cancel",
                   "forgot": "mem_forgot", "forgot_none": "mem_forgot_none"}
        return self._say(mapping.get(kind, "generic"), persona, slang, x=value)

    def _topic(self, topic: str, persona: str, slang: bool) -> tuple[str, str]:
        bank = BANK.get(topic, {})
        if persona in bank:
            return self._pick(bank[persona], slang, {})
        words, emotion = self.small_talk.reply(topic, slang and persona == "edgerunner")
        if persona != "edgerunner":
            p = personality.get(persona)
            if p.opener and self.rng.random() < 0.6:
                words = f"{self.rng.choice(p.opener)} {words}"
            emotion = p.emotion or emotion
        return words, emotion

    def _say(self, kind: str, persona: str, slang: bool, **fields) -> tuple[str, str]:
        bank = BANK.get(kind) or BANK["generic"]
        if persona in bank:
            return self._pick(bank[persona], slang and persona == "edgerunner", fields)
        text, emotion = self._pick(bank["edgerunner"], slang and persona == "edgerunner", fields)
        if persona != "edgerunner":                       # her default line, said her current way
            p = personality.get(persona)
            if p.opener and self.rng.random() < 0.6:
                text = f"{self.rng.choice(p.opener)} {text}"
            if persona == "deadpan":
                text = text.replace("!", ".")
            emotion = p.emotion or emotion
        return text, emotion

    def _pick(self, options: list[tuple[str, str, str]], slang: bool, fields: dict) -> tuple[str, str]:
        fresh = [o for o in options if o[1] not in self.recent] or options
        emotion, plain, street = self.rng.choice(fresh)
        self.recent.append(plain)
        text = (street or plain) if slang else plain
        if "x" in fields and isinstance(fields["x"], str):
            fields = {**fields, "X": fields["x"][:1].upper() + fields["x"][1:]}
        try:
            text = text.format(**{k: v for k, v in fields.items()})
        except (KeyError, IndexError):
            text = plain.format_map({k: fields.get(k, "") for k in ("x", "X", "what")})
        return text[0].upper() + text[1:] if text else "Hm.", emotion

    # -- what you said ---------------------------------------------------------------------------
    def _understand(self, s: str) -> tuple[str, str, dict]:
        from .commands.parser import chat_topic
        topic = chat_topic(s) or ""
        if topic and topic not in ("reply",):
            return "topic", topic, {}
        if not s:
            return "ack", "", {}
        if (answer := solve(s)) is not None:
            return "math", answer, {}
        m = re.fullmatch(r"(?:my name is|my names|i m called|im called|call me|i am called) (\w+(?: \w+)?)", s)
        if m:
            self.name = m.group(1).title()
            return "name_set", self.name, {}
        if re.fullmatch(r"(?:what s|whats|what is|do you (?:know|remember)) my name|who am i", s):
            return ("name_get", self.name, {}) if self.name else ("name_unknown", "", {})
        if re.fullmatch(r"what do i (?:like|love)|do you (?:know|remember) what i like", s):
            return ("likes_get", " and ".join(self.likes[-3:]), {}) if self.likes else ("likes_unknown", "", {})
        m = re.fullmatch(r"i (?:really |kinda |also )?(?:like|love|enjoy|adore|am into|m into) (.+)", s)
        if m and not m.group(1).startswith("you"):
            thing = m.group(1)
            if thing not in self.likes:
                self.likes.append(thing)
            return "like", thing, {}
        m = re.fullmatch(r"i (?:really )?(?:hate|dont like|do not like|cant stand|can t stand) (.+)", s)
        if m and not m.group(1).startswith("you"):
            return "dislike", m.group(1), {}
        m = re.fullmatch(r"(?:i m|im|i am|i feel|im feeling|i m feeling|feeling) (?:so |really |very |kinda |a bit |pretty |super )?(\w+)", s)
        if m:
            feeling = m.group(1)
            if feeling in GOOD_FEELINGS:
                return "feel_good", feeling, {}
            if feeling in BAD_FEELINGS:
                return "feel_bad", feeling, {}
            return "feel_other", feeling, {}
        m = re.fullmatch(r"(?:what s|whats|what is) your (?:favorite|favourite|fav) (\w+)", s)
        if m:
            what = m.group(1)
            fav = FAVORITES.get(what) or self.rng.choice(["anything with neon on it", "the loud kind",
                                                          "the one that glows", "red ones, mostly"])
            return "favorite", fav, {"what": what}
        m = re.fullmatch(r"(?:do you|you) (?:like|love|enjoy) (.+)|what do you think (?:about|of) (.+)"
                         r"|how do you feel about (.+)|are you (?:a fan of|into) (.+)", s)
        if m:
            thing = next(g for g in m.groups() if g)
            if thing in ("me", "it here", "being here"):
                return "topic", "love", {}
            yes = thing in LIKES_SHE or (thing not in DISLIKES_SHE and hash(thing) % 3 != 0)
            return ("opinion_yes" if yes else "opinion_no"), thing, {}
        if re.search(r"\bare you (?:a |an )?(?:virus|malware|spyware|trojan|keylogger|rat|scam|hacker)\b"
                     r"|\bis (?:this|capri|she|it) (?:a |an )?(?:virus|malware|spyware|safe)\b"
                     r"|\bare you (?:safe|spying on me|hacking me|stealing (?:my )?\w+)\b", s):
            return "not_virus", "", {}
        if re.search(r"\bwho (?:made|created|built|programmed|coded|designed) you\b|\bwho s your (?:creator|maker|dev)", s):
            return "creator", "", {}
        if re.fullmatch(r"(?:are you|you) (?:there|here|awake|listening|still there|still here|alive)", s):
            return "here", "", {}
        if re.fullmatch(r"(?:flip|toss) a coin|heads or tails|coin flip|flip coin", s):
            return "coin", self.rng.choice(["heads", "tails"]), {}
        if re.fullmatch(r"roll (?:a |the )?(?:dice|die|d6)", s):
            return "dice", str(self.rng.randint(1, 6)), {}
        m = re.fullmatch(r"pick (?:a )?(?:random )?number(?: (?:between|from) (\d+) (?:and|to) (\d+))?", s)
        if m:
            lo, hi = (int(m.group(1)), int(m.group(2))) if m.group(1) else (1, 10)
            return "number", str(self.rng.randint(min(lo, hi), max(lo, hi))), {}
        m = re.fullmatch(r"what should i (eat|have for (?:dinner|lunch|breakfast)|cook|play|do|watch|listen to)"
                         r"(?: (?:today|tonight|now|right now))?", s)
        if m:
            what = m.group(1)
            key = ("food" if what.startswith(("eat", "have", "cook")) else "play" if what == "play" else
                   "watch" if what == "watch" else "listen" if what == "listen to" else "do")
            return "idea_" + key, self.rng.choice(IDEAS[key]), {}
        if re.fullmatch(LAUGH, s):
            return "laugh", "", {}
        if re.fullmatch(SIGH, s):
            return "sigh", "", {}
        m = re.fullmatch(LOOKUP, s)
        if m:
            subject = next(g for g in m.groups() if g).strip()
            if not re.fullmatch(NOT_LOOKUPS, subject) and not misheard(subject) and len(subject.split()) <= 6:
                return "lookup", subject, {}
        if re.search(r"\bare you (?:real|alive|human|a (?:robot|bot|person|program|real person)|an ai|sentient|conscious)\b", s):
            return "real", "", {}
        if re.search(r"\bhow old are you\b|\byour age\b", s):
            return "age", "", {}
        if re.search(r"\bwhere (?:are you from|do you live|are you)\b", s):
            return "where", "", {}
        m = re.fullmatch(r"(?:can|could|will|would) you (.+)", s)
        if m:
            for pattern, _example in CAN_DO:
                if re.search(pattern, m.group(1)):
                    return "can_yes", m.group(1), {}          # "can you open steam" -> "open steam"
            return "can_no", "", {}
        m = re.match(REQUEST, s)                         # "teach me ...", "order a pizza", "write my essay"
        if m:
            for pattern, _example in CAN_DO:
                if re.search(pattern, s):
                    return "can_yes", s, {}
            return ("dont_know", "", {}) if m.group(1) in ("explain", "tell", "describe", "define") else ("can_no", "", {})
        if re.search(rf"\b(?:you re|youre|you are|ur) (?:so |really |such )?(?:a )?{INSULTS}\b|\bi hate you\b|\bshut up\b"
                     r"|\byou (?:suck|stink|are trash)\b", s):
            return "insult", "", {}
        if re.search(rf"\b(?:you re|youre|you are|ur) (?:so |really |such )?(?:a )?{COMPLIMENTS}\b", s):
            return "compliment", "", {}
        if re.fullmatch(r"(?:sorry|my bad|im sorry|i m sorry|apologies)(?: .*)?", s):
            return "sorry", "", {}
        if re.fullmatch(r"(?:tell me (?:something|a fact|a fun fact|something interesting)|fun fact|random fact)", s):
            return "fact", "", {}
        if re.fullmatch(r"(?:yes|yeah|yep|yup|sure|of course|definitely|totally|absolutely|i guess|i do)", s):
            return "yes", "", {}
        if re.fullmatch(r"(?:no|nah|nope|not really|no way|i dont|never)", s):
            return "no", "", {}
        if re.fullmatch(r"(?:ok|okay|cool|nice|alright|right|fine|sure thing|got it|i see|hmm|mhm|interesting|wow)", s):
            return "ack", "", {}
        if misheard(s):
            return "misheard", "", {}
        if s == "why" or s.startswith("why "):
            return "why", "", {}
        if re.match(r"(?:what|who|where|when|which|how|is|are|does|do|did|was|were|whats|whos|hows|should|"
                    r"can|could|would|will) ", s):
            return "dont_know", "", {}
        if re.search(BAD_NEWS, s) and not re.search(r"\b(?:not|never|isn t|isnt|wasn t|wasnt)\b", s):
            return "bad_news", "", {}
        if re.search(GOOD_NEWS, s):
            return "good_news", "", {}
        if topic_of(s):
            return "about_" + topic_of(s), "", {}
        return "generic", "", {}
