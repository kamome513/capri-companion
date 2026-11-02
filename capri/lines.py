"""What Capri says - plain lines, and Night City street-talk versions.

Slang (on by default, Settings -> Assistant): choom = friend, preem = top-notch,
nova = cool, gonk = idiot (said affectionately, mostly about herself), delta =
leave, flatline = kill / crash, zero = kill, eddies = money, chrome = cybernetics
/ hardware, jack in = connect, corpo = stiff corporate type, the Net = internet.

Every key has an emotion too, so her face and voice match the line.
"""

from __future__ import annotations

import random

# key: (emotion, plain line, [slang variants])
LINES: dict[str, tuple[str, str, list[str]]] = {
    "launch": ("happy", "Launching {name}.", [
        "Preem. Launching {name}.", "Jacking in. {name} is coming up.", "On it, choom. {name} incoming.",
        "{name}, coming right up. Nova."]),
    "launch_many": ("happy", "Opening {names}.", [
        "Opening {names}. Look at you, multitasking, choom.", "{names}, all jacking in at once. Preem."]),
    "not_found": ("confused", "Couldn't find {thing}.", [
        "Couldn't find {thing}. Total gonk moment, choom.", "Couldn't find {thing} anywhere on this rig, choom.",
        "Scanned the whole rig. Couldn't find {thing}."]),
    "not_set_up": ("confused", "{name} isn't set up yet.", [
        "{name} isn't set up yet, choom. Plug its path into Settings.", "{name} isn't set up yet. No path, no launch."]),
    "closed": ("smirk", "{names} closed.", [
        "{names} flatlined.", "{names} closed. Delta'd.", "Zeroed {names}. Clean exit."]),
    "not_running": ("smirk", "{name} isn't running.", [
        "{name} isn't even running, choom.", "{name} isn't running. Can't flatline what's already dead."]),
    "ask_close": ("serious", "Close {name}? Say yes or no.", [
        "Close {name}, choom? Say yes or no.", "Flatline {name}? Say yes or no."]),
    "ask_force": ("serious", "{name} is still running. Force close it?", [
        "{name} is still running. Won't take the hint. Force close it?",
        "{name} is still running, the gonk. Force close it?"]),
    "kept": ("neutral", "Leaving {name} open.", ["Leaving {name} open. Your call, choom."]),
    "cant_close": ("angry", "Couldn't close {name}.", ["Couldn't close {name}. Thing's got corpo-grade armor."]),
    "unknown": ("confused", "Not sure what you mean.", [
        "Not sure what you mean, choom.", "Not sure what you mean. My chrome didn't compute that one."]),
    "cancel": ("neutral", "Okay, never mind.", ["Okay, never mind. Forget it, choom.", "Okay, never mind. Deleted."]),
    "didnt_catch": ("confused", "Didn't catch that.", [
        "Didn't catch that, choom.", "Didn't catch that. Static on the line."]),
    "search_mode_ask": ("playful", "Search mode on. What do you want to search?", [
        "Search mode, choom. What are we looking up?"]),
    "search_mode_more": ("playful", "Anything else to search?", ["What else, choom?"]),
    "drone_on": ("playful", "Drone mode. I'll stay out of your way.", [
        "Drone mode, choom. Go wreck some gonks, I'll hover."]),
    "drone_off": ("happy", "Back to normal.", ["Back in my chrome, choom."]),
    "drone_corner": ("playful", "Drone parked bottom {side}.", ["Hovering bottom {side}, choom."]),
    "fix_learned": ("happy", "Got it. When I hear \"{query}\", I'll take it as \"{name}\".", [
        "Got it, choom. \"{query}\" means \"{name}\" from now on."]),
    "clicked": ("playful", "Zapped {name}.", ["Zapped {name}. Preem.", "{name}: fried and clicked."]),
    "click_not_found": ("confused", "I can't see \"{label}\" on your screen.", [
        "Can't see any \"{label}\" on your screen, choom."]),
    "click_nothing": ("confused", "There's nothing to click under your mouse.", [
        "Nothing to click under your mouse, choom. Point at it first."]),
    "click_cancelled": ("neutral", "Okay, not clicking it.", ["Okay, hands off. Not clicking it."]),
    "tab_which": ("playful", "Which tab? I see {names}.", ["Which tab, choom? I've got {names}."]),
    "tab_switched": ("playful", "Switched to {name}.", ["{name}. Jacked in, choom.", "Switched to {name}."]),
    "tab_not_found": ("confused", "I don't see a \"{label}\" tab.", ["No \"{label}\" tab in there, choom."]),
    "tab_no_browser": ("confused", "I can't find {name} open.", ["{name}'s not running, choom."]),
    "tab_none": ("confused", "I can't read the tabs in {name}.", ["{name} won't show me its tabs, choom."]),
    "tab_cancelled": ("neutral", "Okay, staying on this tab.", ["Okay, staying put."]),
    "video_played": ("playful", "Playing.", ["Rolling, choom.", "Playing."]),
    "video_paused": ("playful", "Paused.", ["Paused, choom.", "Freeze frame."]),
    "video_already_playing": ("neutral", "It's already playing.", ["Already rolling, choom."]),
    "video_already_paused": ("neutral", "It's already paused.", ["Already paused, choom."]),
    "video_key": ("neutral", "I couldn't find the player's button, so I pressed the play/pause media key.", [
        "Couldn't see the player's button, choom - hit the play/pause key instead."]),
    "screenshot_saved": ("playful", "Snap! Saved to Pictures, Screenshots, and copied to your clipboard.", [
        "Snap! Saved to Pictures, Screenshots, and it's on your clipboard, choom."]),
    "screenshot_failed": ("confused", "Couldn't take the screenshot.", ["Screenshot glitched out, choom."]),
    "personality_now": ("playful", "I'm in {name} mode right now.", ["{name} mode, choom. Want a different me?"]),
    "click_failed": ("confused", "Couldn't click {name}.", ["{name} wouldn't take the hit, choom."]),
    "ai_missing": ("playful", "I'd love to chat properly, but my AI brain isn't set up. Run setup_ai.bat.", [
        "Chat brain's offline, choom. Run setup_ai.bat and we can really talk."]),
    "chat_open": ("happy", "Chat's open. Type away.", ["Chat's open, choom. Type away."]),
    "search_mode_still": ("playful", "Still there? Tell me what to search, or say stop.", [
        "Still there, choom? What are we searching? Or say stop."]),
    "search_mode_off": ("neutral", "Search mode off.", ["Search mode off. Delta."]),
    "search_mode_typing": ("neutral", "You're typing - search mode off.", ["You're busy typing, choom. Search mode off."]),
    "search_in": ("happy", "Searching {where} for “{query}”.", ["Jacking into {where}: “{query}”."]),
    "search_default": ("confused", "Couldn't find {where}, so I searched “{query}” in your default browser.", [
        "No {where} on this rig, choom. Searched “{query}” in your default browser."]),
    "search": ("happy", "Searching for “{query}”.", [
        "Searching the Net for “{query}”.", "Jacking into the Net: “{query}”."]),
    "time": ("neutral", "It's {time}.", ["It's {time}, choom.", "Clock says {time}. Night City never sleeps."]),
    "date": ("neutral", "It's {date}.", ["It's {date}, choom."]),
    "compact_on": ("playful", "Compact mode on.", ["Compact mode on. Small chrome, big attitude."]),
    "compact_off": ("happy", "Back to full size.", ["Back to full size. All chrome, no compromise."]),
    "panel_hide": ("neutral", "Panel hidden.", ["Panel hidden. Going quiet, choom."]),
    "panel_show": ("happy", "Panel's back.", ["Panel's back. Miss me?"]),
    "hide": ("smirk", "Hiding. Say “Capri, come back”.", [
        "Going dark. Say “Capri, come back”."]),
    "show": ("happy", "I'm back.", ["I'm back, choom. Miss me?", "Back online. Preem."]),
    "lounge_on": ("smirk", "Don't mind me. Just lounging.", [
        "Don't mind me, choom. Just lounging.", "Taking five. Even netrunners need a break."]),
    "lounge_off": ("neutral", "Okay, okay, I'm up.", [
        "Okay, okay, I'm up. No need to get all corpo about it."]),
    "playing": ("happy", "Playing {track} by {artist}.", [
        "Playing {track} by {artist}. Preem taste, choom.", "Playing {track} by {artist}. Nova."]),
    "spotify_opened": ("playful", "Opened {name} in Spotify. Hit play.", [
        "Pulled up {name} in Spotify, choom. Hit play - it wouldn't start for me."]),
    "playing_found": ("happy", "Playing {label}.", ["Playing {label}. Preem taste, choom."]),
    "spotify_search": ("playful", "Pulled up {query} in Spotify. Hit play.", [
        "Pulled up {query} in Spotify. Hit play, choom."]),
    "music_site": ("happy", "Searching {service} for {query}. Say \u201cclick\u201d and the song to play it.", [
        "Jacking into {service} for {query}, choom. Say \u201cclick\u201d and the song to play it."]),
    "music_service": ("happy", "Got it. I'll play your music on {service} from now on.", [
        "{service} it is, choom. That's where your music plays now."]),
    "youtube": ("playful", "Searching YouTube for {query}.", ["Searching YouTube for {query}. Jacking in."]),
    "music_site_playing": ("happy", "Playing {query} on {service}.", [
        "Playing {query} on {service}. Turn it up, choom."]),
    "music_site_pressed": ("happy", "Opened {query} on {service} and pressed Play.", [
        "Opened {query} on {service} and hit Play, choom."]),
    "youtube_playing": ("happy", "Playing {query} on YouTube.", ["Playing {query} on YouTube. Jacking in."]),
    "need_city": ("confused", "Tell me your city first, in Settings.", [
        "Tell me your city first, in Settings, choom. Can't scan the sky over nowhere."]),
    "now_playing": ("happy", "That's {track} by {artist}.", ["That's {track} by {artist}. Preem pick, choom."]),
    "nothing_playing": ("neutral", "Nothing's playing.", ["Nothing's playing. Dead air, choom."]),
    "not_on_spotify": ("confused", "Couldn't find {query} on Spotify.", [
        "Couldn't find {query} on Spotify, choom. Try saying it another way?"]),
    # PC power (always confirmed out loud first)
    "ask_shutdown": ("serious", "Look up there, think we can make it?", ["Look up there, think we can make it?"]),
    "ask_restart": ("serious", "Restart the PC? Say yes or no.", ["Reboot the rig, choom? Say yes or no."]),
    "ask_sleep": ("serious", "Put the PC to sleep? Say yes or no.", ["Put the rig to sleep, choom? Say yes or no."]),
    "go_shutdown": ("angry", "Shutting down. Something's wrong with me...", [
        "Shutting down. Choom... my chrome's... cyberpsychosis... later...",
        "Powering down. Can't... hold it... flatlining, choom."]),
    "go_restart": ("happy", "Restarting. Back in a sec.", ["Rebooting. Back in a sec, choom."]),
    "go_sleep": ("happy", "Sleep mode. Night night.", ["Putting the rig to sleep. Sweet dreams, choom."]),
    "go_lock": ("smirk", "Locked.", ["Locked tight, choom."]),
    "power_kept": ("neutral", "Okay, leaving it on.", ["Okay, rig stays on, choom."]),
    "power_failed": ("confused", "Windows wouldn't let me do that.", ["Windows blocked me, choom. Corpo software."]),
    # windows
    "minimized_all": ("smirk", "Cleared your screen.", ["Screen cleared, choom. Just you and me now."]),
    "minimized": ("neutral", "Minimised {name}.", ["Tucked {name} away, choom."]),
    "minimized_this": ("neutral", "Minimised it.", ["Tucked it away, choom."]),
    "nothing_to_minimize": ("confused", "No windows to minimise.", ["Nothing open to hide, choom."]),
    "no_window": ("confused", "{name} has no window open.", ["{name} has no window open, choom."]),
    "restored": ("happy", "Windows are back.", ["Everything's back, choom."]),
    "nothing_to_restore": ("confused", "Nothing to bring back.", ["Nothing to bring back, choom."]),
    # File Explorer
    "revealed": ("happy", "Here's {name} in File Explorer.", ["Here's {name}, choom. Right there in File Explorer."]),
    "opened_file": ("happy", "Opening {name}.", ["Opening {name}, choom."]),
    "not_in_files": ("confused", "Couldn't find {thing} in your files.", [
        "Scanned your files, choom. No {thing} anywhere."]),
    "store_app_place": ("neutral", "{name} is a Store app, so it has no normal folder. It's in your Apps folder.", [
        "{name}'s a Store app, choom, no normal folder. It's in your Apps folder."]),
    "runnable_found": ("serious", "{name} is a program file, so I'll just show you where it is.", [
        "{name}'s a program file, choom. Not running random stuff, but here's where it is."]),
    # Discord (its keys toggle, so she says what she pressed, not what state it's in)
    "discord_mute": ("smirk", "Pressed mute on Discord.", ["Pressed mute on Discord, choom."]),
    "discord_unmute": ("happy", "Pressed unmute on Discord.", ["Pressed unmute on Discord, choom. Talk away."]),
    "discord_deafen": ("smirk", "Pressed deafen on Discord.", ["Pressed deafen on Discord, choom."]),
    "discord_undeafen": ("happy", "Pressed undeafen on Discord.", ["Pressed undeafen on Discord, choom."]),
    "discord_muted": ("smirk", "Muted you on Discord.", ["Muted on Discord, choom. Radio silence."]),
    "discord_unmuted": ("happy", "Unmuted. You're live on Discord.", ["Unmuted, choom. You're live."]),
    "discord_deafened": ("smirk", "Deafened you on Discord.", ["Deafened, choom. Peace and quiet."]),
    "discord_undeafened": ("happy", "Undeafened on Discord.", ["Undeafened, choom. Welcome back to the noise."]),
    "discord_already_muted": ("smirk", "You're already muted.", ["You're already muted, choom."]),
    "discord_already_unmuted": ("neutral", "You're not muted - your mic's on.", ["Your mic's already on, choom."]),
    "discord_already_deafened": ("smirk", "You're already deafened.", ["Already deafened, choom."]),
    "discord_already_undeafened": ("neutral", "You're not deafened.", ["You're not deafened, choom."]),
    "discord_failed": ("confused", "I pressed it, but Discord didn't change.", [
        "Pressed it, choom, but Discord didn't budge."]),
    "discord_undeafen_for_mic": ("happy", "You were deafened, so I undeafened you. Your mic's back.", [
        "You were deafened, choom, so I undeafened you. Mic's back."]),
    "quiet": ("neutral", "Okay.", ["Okay, going quiet."]),
    "voice_faster": ("playful", "Faster. Like this?", ["Overclocked. Like this, choom?"]),
    "voice_slower": ("neutral", "Slower. Better?", ["Slowing down. Better, choom?"]),
    "voice_louder": ("happy", "Louder. Can you hear me now?", ["Cranked it. Hear me now, choom?"]),
    "voice_softer": ("neutral", "Softer. Like this?", ["Bringing it down. Like this?"]),
    "voice_higher": ("playful", "Higher. How's this?", ["Higher. How's this, choom?"]),
    "voice_lower": ("neutral", "Lower. How's this?", ["Deeper. How's this, choom?"]),
    "voice_next_style": ("playful", "New voice: {style}. How do I sound?", ["New voice, {style}. How do I sound, choom?"]),
    "voice_more_expressive": ("happy", "More expressive! Can you hear the difference?", [
        "More expressive! Hear the difference, choom?"]),
    "voice_less_expressive": ("neutral", "Calmer. Steadier tone now.", ["Steadier now, choom."]),
    "voice_limit": ("smirk", "That's as far as that goes.", ["Maxed out, choom. That's as far as it goes."]),
    "timer_set": ("happy", "Timer set for {time}.", ["Timer's ticking, {time}, choom."]),
    "reminder_set": ("happy", "Okay. I'll remind you to {label} in {time}.", [
        "Got it, choom. I'll remind you to {label} in {time}."]),
    "alarm_set": ("happy", "Alarm set for {time}.", ["Alarm set for {time}, choom."]),
    "timer_done": ("surprised", "Time's up! That's your {time}.", ["Time's up, choom! That's your {time}."]),
    "reminder_done": ("surprised", "Reminder: {label}.", ["Hey choom, reminder: {label}."]),
    "alarm_done": ("surprised", "It's {time}. Time to get up!", ["It's {time}, choom. Rise and shine!"]),
    "timer_cancelled": ("neutral", "Cancelled your {what}.", ["{What} cancelled, choom."]),
    "timer_none": ("confused", "You don't have any timers or alarms.", ["No timers running, choom."]),
    "timer_left": ("neutral", "{time} left.", ["{time} left, choom."]),
    "hype_on": ("happy", "Game hype on. Get me some kills! Works in CS2, Dota 2 and League.", [
        "Game hype on, choom. Go frag something. CS2, Dota 2 and League."]),
    "hype_off": ("neutral", "Game hype off. I'll watch quietly.", ["Hype off, choom. Quiet mode."]),
    "perch_on": ("happy", "I'll sit on your windows.", ["Window-sitting mode, choom."]),
    "perch_off": ("neutral", "Okay, I'll stay on my panel.", ["Back to my panel, choom."]),
    "discord_joined": ("happy", "You're in the call.", ["You're in, choom."]),
    "discord_already_in_call": ("smirk", "You're already in that call.", ["Already in, choom."]),
    "discord_no_join_button": ("confused", "I opened your call, but couldn't find Discord's Join button. Click Join Voice.", [
        "Opened your call, choom, but Discord's Join button is hiding. Hit Join Voice."]),
    "discord_no_discord": ("confused", "Discord didn't open. Is it installed?", ["Discord didn't boot, choom."]),
    "discord_no_link": ("confused", "Tell me which call first: Settings, PC and chat, Your call. Right-click the voice channel, Copy Link, paste it there.", [
        "Which call, choom? Paste its link in Settings, PC and chat. Right-click the voice channel, Copy Link."]),
    "discord_no_share_button": ("confused", "You're in a call, but I can't find Discord's screen share button.", [
        "Can't find Discord's screen share button, choom."]),
    "discord_streaming": ("happy", "You're live. Streaming your screen on Discord.", [
        "You're live, choom. Your screen's on Discord."]),
    "discord_already_streaming": ("smirk", "You're already streaming.", ["You're already live, choom."]),
    "discord_picker": ("neutral", "I opened Discord's screen share. Pick what to share and hit Go Live.", [
        "Screen share's open, choom. Pick what to share and hit Go Live."]),
    "discord_no_call": ("confused", "You're not in a Discord call.", ["You're not in a call, choom."]),
    "discord_stopped": ("neutral", "Stopped streaming.", ["Stream's off, choom."]),
    "discord_not_streaming": ("confused", "You're not streaming.", ["You're not streaming, choom."]),
    "discord_left": ("neutral", "Left the call.", ["Out of the call, choom."]),
    "discord_call_failed": ("confused", "I pressed it, but Discord didn't change. Check Discord?", [
        "Pressed it, but Discord didn't budge, choom. Check it?"]),
    "discord_call_windows": ("confused", "I can only do that with the Discord app on Windows.", [
        "That needs the Discord app on Windows, choom."]),
    "discord_off": ("confused", "Discord isn't running.", ["Discord isn't even running, choom."]),
    "discord_in_game": ("confused", "I didn't want to tab you out of your game. Give Discord a Toggle Deafen and "
                                    "Toggle Mute keybind and put them in my Settings, then I can do it mid-game.", [
        "Not tabbing you out mid-fight, choom. Give Discord mute and deafen keybinds, put them in my "
        "Settings, and I've got you."]),
    "discord_hidden": ("confused", "Discord is in the tray, so I can't reach it. Set Discord keybinds in my Settings.", [
        "Discord's hiding in the tray, choom. Set its keybinds in my Settings and I can reach it."]),
}


def line(key: str, slang: bool, rng: random.Random | None = None, **fields) -> tuple[str, str]:
    """(text, emotion) for a line, in plain English or Night City slang."""
    emotion, plain, variants = LINES[key]
    template = (rng or random).choice(variants) if (slang and variants) else plain
    return template.format(**fields), emotion


SLANG_PROMPT = """Talk like a local from Night City in Cyberpunk: drop in street slang naturally - choom \
(friend), preem (excellent), nova (cool), gonk (idiot - affectionate, never cruel), delta (leave), \
flatline (kill or crash), zero (kill), eddies (money), chrome (cyberware or hardware), jack in (connect), \
corpo (stuffy corporate type), the Net (the internet). One or two per reply; stay easy to understand."""
