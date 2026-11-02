"""Turns a transcribed command into an Intent. Plain pattern matching, no AI.

Input is Vosk output: lowercase words, no punctuation, numbers spelled out.
Anything that doesn't match a known pattern becomes ``UNKNOWN``; nothing is
ever executed from free text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Kind(Enum):
    OPEN = "open"
    CLOSE = "close"
    SEARCH = "search"             # query = what; targets = () (Google) or (site / browser,) e.g. ("opera",)
    TIME = "time"
    DATE = "date"
    COMPACT_ON = "compact_on"
    COMPACT_OFF = "compact_off"
    PANEL_HIDE = "panel_hide"
    PANEL_SHOW = "panel_show"
    HIDE = "hide"
    SHOW = "show"
    LOUNGE_ON = "lounge_on"       # lie down on the panel
    LOUNGE_OFF = "lounge_off"
    CANCEL = "cancel"
    PLAY = "play"                 # query = song / artist (or an app or game: "play deadlock")
    MEDIA = "media"               # query = pause | resume | next | previous | volume_up | volume_down
    NOW_PLAYING = "now_playing"
    WEATHER = "weather"           # query = place ("" = home), day = today | tomorrow
    RAIN = "rain"
    POWER = "power"               # query = shutdown | restart | sleep | lock
    MINIMIZE = "minimize"         # targets = app names; () = every window; ("this",) = the one in front
    RESTORE = "restore"           # bring back what "minimise everything" hid
    DISCORD = "discord"           # query = mute | unmute | deafen | undeafen
    CHAT = "chat"                 # small talk; query = topic (see chat.py)
    DRONE_ON = "drone_on"         # game mode: the little flying disk
    DRONE_OFF = "drone_off"
    DRONE_CORNER = "drone_corner"   # "move the drone to the left": targets = ("left",) / ("right",)
    CLICK = "click"               # "click subscribe": targets = (label,); ("",) = "click that" (under the mouse)
    CORRECTION = "correction"     # "when I say to school I mean discord": targets = (heard, meant)
    CHAT_WINDOW = "chat_window"   # "open chat": the typing window
    SEARCH_MODE = "search_mode"   # "go into search mode": she asks what to search, again and again
    REVEAL = "reveal"             # targets = what to show in File Explorer (an app, a folder, one of your files)
    MUSIC_SERVICE = "music_service"   # "use soundcloud for music": targets = (service,)
    SETTINGS = "settings"         # "open your settings": her own Settings window
    UPDATE = "update"             # "check for updates" / "update yourself": a newer Capri from GitHub
    RESTART_APP = "restart_app"   # "restart yourself": Capri closes and starts again (not the PC!)
    SHORTCUT = "shortcut"         # "when I say gaming time, open steam and discord": targets = (phrase, command)
    FORGET = "forget"             # "forget the shortcut gaming time": targets = (phrase,)
    TAB = "tab"                   # "switch tabs on opera": targets = (browser,) or (); query = the tab ("" = ask)
    VIDEO = "video"               # "play the video" / "pause the video": query = play | pause
    PC_INFO = "pc_info"           # "what's using all my ram": query = ram | cpu | disk | uptime | battery | overview
    SCREENSHOT = "screenshot"     # "take a screenshot": query = screen | window
    PERSONALITY = "personality"   # "be sarcastic": targets = (key,); () = "what's your personality"
    SCREEN = "screen"             # hands on your screen: query = highlight | copy | double_click | right_click |
                                  #   scroll_up | scroll_down | a key action ("select_all", "undo"...); targets = (words,)
    REPEAT = "repeat"             # "repeat what I said" (query "you") / "say that again" (query "me") /
                                  #   "repeat after me hello" (query "after", targets = ("hello",))
    MOVE = "move"                 # "go to the bottom left": targets = (spot,)
    AI_SETUP = "ai_setup"         # "set up your brain" / "is your AI working"
    HAIR = "hair"                 # "change your hair" / "use your old hair": query = storm | classic | "" (swap)
    TYPE = "type"                 # "type hi tiktok": query = the words, exactly as said (typed into the window in front)
    LEARN_BUTTON = "learn_button"   # "this red button makes me leave call" (pointing at it): targets = (phrase,)
    FORGET_BUTTON = "forget_button"  # "forget the leave call button": targets = (phrase,)
    QUIET = "quiet"               # "stop talking" / "shut up": she stops mid-sentence, no reply
    VOICE = "voice"               # "talk faster": query = faster | slower | louder | softer | higher | lower |
                                  #   next_style | more_expressive | less_expressive
    TIMER = "timer"               # query = add (targets = (seconds, label)) | alarm (targets = ("H:MM", label)) |
                                  #   cancel | left
    HYPE_ON = "hype_on"           # "turn on game hype": she cheers for your kills
    HYPE_OFF = "hype_off"
    PERCH_ON = "perch_on"         # "sit on my window"
    PERCH_OFF = "perch_off"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Intent:
    kind: Kind
    targets: tuple[str, ...] = field(default_factory=tuple)
    query: str = ""
    day: str = "today"
    artist: str = ""              # PLAY: "play let you down by nf" -> query "let you down", artist "nf"


POLITE = (r"would you mind|would you please|could you please|can you please|i would like you to|id like you to|"
          r"i d like you to|i want you to|i need you to|do me a favou?r and|go ahead and|make sure to|try to|"
          r"please|pls|kindly|can you|can u|could you|would you|will you|just|i wanna|you can|quickly")
FILLER_START = rf"^(?:(?:hey capri|okay capri|ok capri|yo capri|hey|yo|capri|{POLITE}|and|um|uh|okay|ok|so)\s+)+"
FILLER_END = (r"(?:\s+(?:please|pls|for me|for me please|now|right now|thanks|thank you|thx|real quick|quickly|"
              r"if you can|if you could|if you don t mind|if you dont mind|capri))+$")

OPEN_VERBS = (r"(?:open(?: up)?|launch|start(?: up)?|run|load(?: up)?|fire up|boot(?: up)?|pull up|bring up|"
              r"get up|put up|crack open)")
# "pull spotify up", "get discord open", "get steam going"
OPEN_AROUND = (r"(?:pull|bring|get|load|fire|boot|start|open) (?!(?:me|us|it|this|that|them|him|her)\b)(.+?) "
               r"(?:up|open|going|running|started)")
LOUDER_UP = r"(?:pull|bring|put|get) (?:up )?(?:the )?(?:volume|sound)(?: up)?"
CLOSE_VERBS = r"(?:close|quit|exit|kill|shut down|shutdown|end|stop|terminate)"

# "when I say to school I mean discord" / "if you hear to school it means discord"
LEARN_FIX = (r"(?:when(?:ever)?|if) (?:i say|i said|you hear|you heard)(?: the word)? (.+?),? (?:i mean|i meant|i m saying|"
             r"it means|that means|you should hear|that s|thats|its|it s|change it to|correct it to|make it) (.+)"
             r"|(?:remember|learn)(?: that)? (.+?) means (.+)")
# Music services: "play X on soundcloud", "use youtube music for music"
MUSIC_SERVICES = {   # key: (spoken names, how she says it)
    "spotify": (r"spotify", "Spotify"),
    "youtube_music": (r"(?:you ?tube|yt|y t) music|youtube ?music", "YouTube Music"),
    "youtube": (r"you ?tube", "YouTube"),
    "soundcloud": (r"sound ?cloud|sound clouds?", "SoundCloud"),
    "apple_music": (r"apple music|itunes", "Apple Music"),
    "deezer": (r"deezer|deez?er", "Deezer"),
    "tidal": (r"tidal", "Tidal"),
    "amazon_music": (r"amazon music|amazon", "Amazon Music"),
    "bandcamp": (r"band ?camp", "Bandcamp"),
}
MUSIC_NAMES = "|".join(pattern for pattern, _label in MUSIC_SERVICES.values())


def music_service(spoken: str) -> str:
    for key, (pattern, _label) in MUSIC_SERVICES.items():
        if re.fullmatch(pattern, spoken.strip()):
            return key
    return "spotify"


MUSIC_DEFAULT = (rf"(?:(?:can you |could you |please )*(?:change|switch|set|swap|move|put) (?:my |the |your )?(?:music|songs)"
                 rf"(?: (?:app|player|service|thing))? (?:to|over to|onto|on) (?:the |my )?(?P<svc3>{MUSIC_NAMES})(?: app)?"
                 rf"(?: from now on| instead| please)*)"
                 rf"|(?:use(?= .* (?:for|as) )|switch to|set|make it|change it to|play (?:my )?music (?:on|from|with)) "
                 rf"(?:the |my )?(?P<svc>{MUSIC_NAMES})(?: app)?(?: (?:for|as) (?:my |the )?(?:music|songs|music app|"
                 rf"default music))?(?: from now on)?"
                 rf"|(?:use|play) (?:my )?(?:music|songs) (?:on|from|with|through) (?P<svc2>{MUSIC_NAMES})(?: from now on)?")
# "when I say gaming time, open steam and discord" - your own shortcut (the command part starts with a verb)
SHORTCUT_VERBS = (r"open|launch|start|run|boot|close|quit|kill|play|put on|search|google|look up|minimi[sz]e|"
                  r"restore|mute|unmute|deafen|undeafen|take|switch|go|move|turn|show|hide|lock|pause|resume|skip|"
                  r"next|click|select|highlight|copy|paste|scroll|zoom|refresh|be|act|tell|check|what|whats|lie|get|"
                  r"stand|reveal|find")
SHORTCUT = (rf"(?:when(?:ever)?|if) i (?:ever )?say (.+?)(?:,| then)? (?:i want you to |you should |you |please |"
            rf"can you |just |go ahead and )?((?:{SHORTCUT_VERBS})\b.*)")
FORGET = (r"(?:forget|delete|remove|drop) (?:the |my )?(?:shortcut|command|phrase)(?: for| called)? (.+)"
          r"|forget what (.+?) means|stop doing (.+?) when i say (.+)")
# "click subscribe", "click on the next button", "press the skip button", "click that"
CLICK_KINDS = r"(?: button| link| tab| icon| option| box| thing| one)"
CLICK_HERE = rf"(?:click|press|tap|hit)(?: on)?(?: the| that| this| it| here| there)?{CLICK_KINDS}?(?: there| here)?"
CLICK_NAMED = (rf"(?:click|left click)(?: on)?(?: the| that| this| a)? (.+?){CLICK_KINDS}?"
               rf"|(?:press|tap|hit)(?: on)?(?: the| that| this)? (.+?){CLICK_KINDS}")
# "switch tabs on opera", "change tab", "switch to the twitch tab", "go to the youtube tab in chrome"
BROWSER_NAMES = (r"(?P<opera>opera(?: g x| gx| gee x| jx| g ex)?|oprah(?: g x| gx)?)|(?P<chrome>(?:google )?chrome)"
                 r"|(?P<edge>(?:microsoft )?edge)|(?P<firefox>fire ?fox)|(?P<brave>brave)|(?P<vivaldi>vivaldi)|browser")
TAB_ON = rf"(?: (?:on|in) (?:the |my )?(?:{BROWSER_NAMES}))?"
TAB_SWITCH = (rf"(?:switch|change|swap|flip|cycle)(?: the| my)? tabs?{TAB_ON}"
              rf"(?: to (?:the |my )?(?P<to>.+?)(?: tab| one)?)?{TAB_ON.replace('?P<', '?P<b_')}"
              rf"|(?:switch|change|go|flip|move|jump)(?: over| back)? to (?:the |my |a )?(?P<named>.+?) tab{TAB_ON.replace('?P<', '?P<c_')}"
              rf"|(?:go to |open )?(?:the )?(?:other|another|different) tab{TAB_ON.replace('?P<', '?P<d_')}")
VIDEO_WORDS = r"(?:the |this |my |that )?(?:video|vid|stream|clip|episode|show|movie|youtube video|twitch stream)"
VIDEO = [(rf"(?:play|resume|unpause|un pause|start|continue|restart)(?: playing)? {VIDEO_WORDS}(?: again| back up)?"
          r"|press play(?: on (?:the |this )?(?:video|stream))", "play"),
         (rf"(?:pause|stop|freeze|hold)(?: playing)? {VIDEO_WORDS}", "pause")]
# "what's using all my ram", "how am i using 10 gb of ram", "why is my cpu so high", "how much storage do i have left"
PC_ASK = (r"\b(?:what|whats|which|who|how|why|check|show|tell|is|are|am|much|using|use|usage|eating|hogging|taking|"
          r"full|high|left|free|space|status|slow|lagging|laggy|level|percent)\b")
PC_TOPICS = [
    ("ram", r"\b(?:ram|memory|gigs of ram|gb of ram)\b"),
    ("cpu", r"\b(?:cpu|processor|cpu usage)\b"),
    ("disk", r"\b(?:storage|disk space|hard drive|hard disk|ssd|drive space|disk|space left|space on my)\b"),
    ("battery", r"\bbattery\b"),
    ("uptime", r"\bhow long (?:has|have) (?:my |the |this )?(?:pc|computer|laptop|rig) been (?:on|running|up)\b|\buptime\b"),
    ("overview", r"\bwhy is (?:my |the |this )?(?:pc|computer|laptop|rig) (?:so )?(?:slow|laggy|lagging|loud|hot)\b"
                 r"|\bwhat(?: s| is) (?:slowing|lagging) (?:down )?(?:my |the )?(?:pc|computer|laptop|rig)\b"),
]
SCREENSHOT = (r"(?:take|grab|snap|get|make|do|capture|save)(?: me)?(?: a| an| the)? (?:quick )?"
              r"(?:screen ?shot|screen ?cap|screen capture|snapshot|picture of (?:my |the )?screen|screen grab)"
              r"(?: of (?:this|the|my) (?P<w1>window|app|program|tab))?(?: for me)?"
              r"|(?:screen ?shot|screen ?cap)(?: (?:this|the|my) (?P<w2>window|app|program|tab)| this| that| it| my screen| the screen)?"
              r"|(?:take|grab|snap) (?:a )?(?:screen ?shot|picture) of (?:this|the|my) (?P<w3>window|app|program|tab)")
# "be sarcastic", "be more silly", "change your personality to tsundere", "act tsundere", "go back to normal"
PERSONALITY = (r"(?:be|act|talk|go|switch to|turn|become|set your personality to|change your personality to|"
               r"switch your personality to|personality|your personality is now|use the|use your)(?: (?:more|a lot more|a bit))?"
               r"(?: like)?(?: a| an)? (?P<p>[a-z ]+?)(?: personality| mode| again| now)?"
               r"|(?:change|switch|set) (?:your )?personality(?: to)? (?:a |an )?(?P<p2>[a-z ]+?)(?: mode)?")
PERSONALITY_ASK = r"what(?:s| s| is) your personality(?: right now| now)?|which personality (?:are you|is this)|what personality are you"
# hands on your screen
SCREEN_WORDS = r"(?: the| that| this)?(?: words?| text| line| phrase| sentence| bit that says| part that says)?"
SCREEN_TEXT = [
    (rf"(?:highlight|select|mark){SCREEN_WORDS} (?!all\b)(.+)", "highlight"),
    (rf"copy{SCREEN_WORDS} (?!that$|this$|it$)(.+)", "copy"),
    (r"double ?click(?: on)?(?: the| that)? (.+)", "double_click"),
    (r"right ?click(?: on)?(?: the| that)? (.+)", "right_click"),
]
SCREEN_KEYS = {   # fixed key presses into the window you're using - nothing else
    "select_all": (r"select (?:all|everything)(?: of it)?|highlight (?:all|everything)", "ctrl+a", "Selected everything."),
    "copy_it": (r"copy(?: that| this| it)?(?: for me)?", "ctrl+c", "Copied."),
    "paste": (r"paste(?: it| that| this)?(?: here| in| for me)?", "ctrl+v", "Pasted."),
    "cut": (r"cut(?: that| this| it)", "ctrl+x", "Cut."),
    "undo": (r"undo(?: that| it)?|take that back", "ctrl+z", "Undone."),
    "redo": (r"redo(?: that| it)?", "ctrl+y", "Redone."),
    "save": (r"save(?: it| this| that| the file| my work)", "ctrl+s", "Saved."),
    "refresh": (r"(?:refresh|reload)(?: the| this)?(?: page| tab| site)?", "ctrl+r", "Refreshed."),
    "page_back": (r"(?:go )?back a page|previous page|go to the previous page|page back", "alt+left", "Back a page."),
    "page_forward": (r"(?:go )?forward a page|next page|go to the next page|page forward", "alt+right", "Forward a page."),
    "zoom_in": (r"zoom in(?: a bit| more)?", "ctrl+plus", "Zoomed in."),
    "zoom_out": (r"zoom out(?: a bit| more)?", "ctrl+minus", "Zoomed out."),
    "zoom_reset": (r"reset (?:the )?zoom|normal zoom", "ctrl+0", "Zoom reset."),
    "new_tab": (r"(?:open )?(?:a )?new tab", "ctrl+t", "New tab."),
    "close_tab": (r"close (?:this|the|my) tab", "ctrl+w", "Closed the tab."),
    "reopen_tab": (r"reopen (?:the |that |my )?(?:closed |last )?tab|bring back (?:that|the) tab", "ctrl+shift+t", "Tab's back."),
    "next_tab": (r"next tab", "ctrl+tab", "Next tab."),
    "previous_tab": (r"previous tab|last tab", "ctrl+shift+tab", "Previous tab."),
}
SCROLL = (r"scroll(?: the page| this| it)? (?P<dir>up|down)(?: a (?P<little>bit|little))?(?: a (?P<lot>lot))?"
          r"|(?P<dir2>up|down) a (?:bit|little)")
# "repeat what I said" / "what did I say" / "say that again" / "repeat after me ..."
REPEAT_YOU = r"(?:repeat|say back|say) what i (?:just )?said|what did i (?:just )?say|repeat (?:what i said|me)|say what i said"
REPEAT_ME = r"(?:say|repeat) that again|repeat that|what did you (?:just )?say|come again|pardon|sorry what"
REPEAT_AFTER = r"(?:repeat after me|say after me|say this|repeat this|repeat)[ ,:]+(.+)"
# "go to the bottom left", "move to the top right", "go to my other monitor", "go to the middle"
MOVE_SPOTS = {"bottom left": "bottom_left", "bottom right": "bottom_right", "top left": "top_left",
              "top right": "top_right", "left": "bottom_left", "right": "bottom_right", "middle": "middle",
              "center": "middle", "centre": "middle", "top": "top_right", "bottom": "bottom_right",
              "other screen": "other_screen", "other monitor": "other_screen", "second screen": "other_screen",
              "second monitor": "other_screen", "main screen": "main_screen", "main monitor": "main_screen",
              "left side": "bottom_left", "right side": "bottom_right", "corner": "bottom_right",
              "left corner": "bottom_left", "right corner": "bottom_right", "home": "bottom_right"}
MOVE = (r"(?:go|move|teleport|tp|jump|head|get|fly|walk|run|scoot)(?: over| yourself| your self)?(?: to| into| onto| on)"
        r"(?: the| my| your)? (?P<spot>(?:bottom|top) (?:left|right)|left side|right side|left corner|right corner|"
        r"left|right|middle|center|centre|top|bottom|other screen|other monitor|second screen|second monitor|"
        r"main screen|main monitor|corner)(?: of (?:the|my) screen| corner| of the monitor)?")
AI_SETUP = (r"(?:set ?up|install|download|get|fix|turn on|start|connect|wake up|boot up|load)(?: up)? (?:your|the|my|an?)"
            r" (?:ai|a i|brain|online brain|ai brain|thinking|chat ?bot|llama|ollama)(?: brain)?"
            r"|(?:is|why is|whats wrong with) your (?:ai|brain|ai brain)(?: not)?(?: working| on| online| broken| offline)?"
            r"|why (?:cant|can t|don t|dont) you think|can you think|are you online|is (?:ollama|the llama|llama) working")
DRONE_CORNER = (r"(?:move|put|send|park|fly|take) (?:the |your |my )?(?:drone|disk|disc)(?: over)?(?: to| in| into| on)?"
                r"(?: the)?(?: bottom)?(?: |-)?(left|right)(?: hand)?(?: corner| side)?"
                r"|(?:drone|disk|disc) (?:to the |on the )?(?:bottom )?(left|right)(?: corner| side)?")

SIMPLE: list[tuple[str, Kind]] = [
    (r"(?:turn on|enable|start|switch on) (?:the )?(?:game hype|kill (?:calls|cheers|callouts)|hype mode for games)"
     r"|(?:cheer|hype me up) (?:for|when i get) (?:my )?kills|game hype on", Kind.HYPE_ON),
    (r"(?:turn off|disable|stop|switch off) (?:the )?(?:game hype|kill (?:calls|cheers|callouts))"
     r"|stop cheering(?: for my kills)?|game hype off", Kind.HYPE_OFF),
    (r"(?:stop|quit) (?:talking|speaking|yapping|rambling)|shut up|be quiet|quiet|hush|shush|zip it|shh+|sh+"
     r"|enough(?: talking)?|(?:ok|okay) stop|stop it capri|that s enough|thats enough|silence", Kind.QUIET),
    (r"(?:sit|perch|hop|go) on (?:my |the |a |your )?windows?|(?:turn on|enable|start) (?:window sitting|"
     r"sitting on windows)", Kind.PERCH_ON),
    (r"(?:stop sitting|get off|hop off|jump off|come off|stop perching)(?: on)? (?:my |the |a )?windows?"
     r"|(?:turn off|disable|stop) (?:window sitting|sitting on windows)", Kind.PERCH_OFF),
    (r"(?:(?:go|get|switch|turn|change|put (?:yourself|you))(?: in| into| in to| to| on)?|enter|turn on|become)?"
     r"(?: the| your| a)? ?(?:drone|game|gaming)(?: mode)?(?: on| now)?"
     r"|(?:start|activate|enable|use)(?: the| your)? (?:drone|game|gaming) mode"
     r"|(?:turn|transform|change) into (?:a |the |your )?(?:drone|disk|disc)",
     Kind.DRONE_ON),
    (r"(?:stop|exit|leave|end|turn off|quit|get out of|come out of) (?:the |your )?(?:drone|game|gaming|disk|disc)(?: mode)?"
     r"|(?:drone|game|gaming) mode off|(?:turn|change) back(?: to normal)?|normal mode|human mode|back to normal",
     Kind.DRONE_OFF),
    (r"(?:switch to |go |enable |turn on |use |go into )?compact(?: mode)?(?: on)?", Kind.COMPACT_ON),
    (r"(?:switch to |go |use |back to )?(?:normal|full|full size|big|large|regular)(?: mode| size)?"
     r"|(?:exit|leave|disable|turn off) compact(?: mode)?", Kind.COMPACT_OFF),
    (r"(?:hide|close|turn off|remove) (?:the |your )?(?:status )?panel", Kind.PANEL_HIDE),
    (r"(?:show|open|turn on|bring back) (?:the |your )?(?:status )?panel", Kind.PANEL_SHOW),
    (r"(?:lie|lay|lie down|lay down|get comfy|relax|chill|take a (?:nap|break)|rest)"
     r"(?: down)?(?: on (?:the |your )?(?:panel|window|status panel))?", Kind.LOUNGE_ON),
    (r"(?:get|stand|sit|wake|wake up and get) up|stand|wake up|stop lying(?: down)?", Kind.LOUNGE_OFF),
    (r"hide(?: yourself)?|go away|disappear|vanish", Kind.HIDE),
    (r"show yourself|come back|appear|reappear", Kind.SHOW),
    (r"never mind|nevermind|cancel|forget it|nothing", Kind.CANCEL),
    (r"(?:what(?: is|s)? )?(?:the )?time(?: is it)?(?: now)?|what time is it", Kind.TIME),
    (r"(?:what(?: is|s)? )?(?:the |today s |todays )?date(?: today)?|what day is it(?: today)?", Kind.DATE),
]

MUSIC = r"(?:the |some |my )?(?:music|song|track|spotify|playback|tunes)"
BIT = r"(?: a (?:bit|little|tad|lot|little bit|bit more|little more)| some| more| please)?"
MEDIA: list[tuple[str, str]] = [
    (rf"(?:pause|stop|halt|hold)(?: {MUSIC})?|(?:pause|stop) (?:it|this|that)(?: song| track)?|{MUSIC} (?:off|stop)"
     rf"|stop playing(?: {MUSIC})?", "pause"),
    (rf"(?:resume|unpause|continue|keep playing|resume playing)(?: {MUSIC})?|play(?: {MUSIC})?(?: again)?"
     rf"|(?:start|put) {MUSIC} (?:again|back on)|keep (?:the )?(?:music|it|song|songs) (?:going|playing|on)", "resume"),
    (rf"(?:next|skip)(?: {MUSIC})?|skip(?: this| it)?(?: song| track)?|next one"
     rf"|(?:play|go to|skip to|put on) (?:the )?next (?:song|track|one)|skip (?:this|that) one", "next"),
    (rf"(?:previous|last|go back)(?: {MUSIC})?|play the (?:previous|last) (?:song|track)|go back (?:a|one) (?:song|track)",
     "previous"),
    (rf"(?:turn (?:it|the (?:music|volume|sound)) up|volume up|louder|turn up the (?:music|volume|sound)|"
     rf"(?:raise|increase|boost|pump up|crank up) the (?:volume|sound|music)|make it louder|crank it(?: up)?|"
     rf"pump it up|up the volume|(?:bring|put|get) (?:the )?(?:volume|sound|music) up|"
     rf"make (?:it|the music|the sound|this) louder){BIT}", "volume_up"),
    (rf"(?:turn (?:it|the (?:music|volume|sound)) down|volume down|quieter|turn down the (?:music|volume|sound)|"
     rf"(?:lower|decrease|reduce) the (?:volume|sound|music)|make it quieter|lower it|bring it down|too loud|"
     rf"its too loud|it s too loud|(?:bring|put|get) (?:the )?(?:volume|sound|music) down|"
     rf"make (?:it|the music|the sound|this) (?:quieter|softer|less loud)){BIT}", "volume_down"),
]
NOW_PLAYING = r"(?:what(?: is|s)? (?:this song|this|playing|the song|the song playing|playing right now)" \
              r"|what song is (?:this|playing)|who (?:sings|is singing) this|whats this song)"
DAY = r"(?: (?:for )?(?:today|tonight|tomorrow|right now|now|this week))?"
PLACE = r"(?: (?:in|at|for) [a-z ]+?)?"
WEATHER = [
    r"(?:what(?: is|s)?|hows|how is) (?:the )?(?:weather|forecast)(?: like)?" + DAY + PLACE + DAY,
    r"(?:weather|forecast)" + DAY + PLACE + DAY,
    r"how (?:hot|cold|warm) is it(?: outside)?" + DAY + PLACE,
    r"(?:whats|what is) the temperature(?: outside)?" + PLACE,
]
RAIN = r"(?:is it|will it|is it going to|its going to|does it look like its going to) (?:rain|snow)" + DAY + PLACE + DAY \
       + r"|do i need an umbrella" + DAY + PLACE

PC = r"(?:the |my |this |my whole |the whole |this whole )?(?:pc|computer|system|laptop|rig|machine|desktop)"
POWER: list[tuple[str, str]] = [
    (rf"(?:shut ?down|shut off|power (?:off|down))(?: {PC})?|(?:turn|switch|shut|power) off {PC}"
     rf"|(?:shut|turn|switch|power) {PC} (?:down|off)|(?:shut ?down|turn off) every ?thing|shut (?:it all|everything) down"
     rf"|(?:kill|nuke) {PC}", "shutdown"),
    (rf"(?:restart|reboot)(?: {PC})?|(?:do|give {PC}) a (?:restart|reboot)", "restart"),
    (rf"(?:put |send )?{PC} to sleep|(?:go to )?sleep(?: mode)?|sleep {PC}|(?:put|send) it to sleep"
     rf"|{PC} sleep", "sleep"),
    (rf"lock(?: {PC}| (?:the |my )?screen)?|lock (?:it|up)", "lock"),
]
WINDOWS = r"(?:all |every |my |the |all the |all my )?(?:windows?|screens?|apps|tabs|programs)"
MINIMIZE_VERB = r"(?:minimi[sz]e|minimum (?:eyes|ize)|mini mize|minimise)"
MINIMIZE_ALL = (rf"{MINIMIZE_VERB}(?: (?:all|everything|every thing|it all|{WINDOWS}))?"
                rf"|(?:hide|clear) (?:all|everything|{WINDOWS})|clear (?:my |the )?screen"
                rf"|show (?:me )?(?:the |my )?desktop")
MINIMIZE_THIS = rf"{MINIMIZE_VERB} (?:this|that|it|this one|this window|that window|the window)"
RESTORE = (rf"(?:restore|bring back|unminimi[sz]e|un minimi[sz]e|show|reopen) (?:all |every |everything|{WINDOWS})"
           rf"(?: back)?|bring (?:them|it all|everything|{WINDOWS}) back|undo (?:that|minimi[sz]e)")
# Discord. The speech model doesn't know "unmute" or "deafen", so it writes the nearest
# words it does know: "unmute me on discord" arrives as "on meet on discord", "deafen"
# as "the fan" or "defend". These lists are those sound-alikes.
ME = r"(?:me|myself|my mic|my microphone|my mike|mic|microphone|mike|my self)"
DISCORD_WORD = r"(?:discord|disc ord|dis cord|discard|this cord|the scored|disco|discords)"
MUTE_SOUND = r"(?:mute|mutes|muted|meet|meat|moot|mood|mutt|newt|mewt|meets|muse|mutant)"
UN_SOUND = r"(?:un|on|an|and|in|a|under|um|uh|own|un a)"
DEAF_SOUND = (r"(?:deafen|deafened|deafens|defend|defending|defense|deaf|deaf and|deaf in|deaf on|death and|"
              r"death in|deaf fun|def in|def and|the fan|the fin|the phone|the finn|definite|definitely)")
ON_DISCORD = rf"(?: (?:on|in|from|for) (?:{DISCORD_WORD}|this call|the call|call))?"
MIC = r"(?:my )?(?:mic|microphone|mike|mic rophone)"
DISCORD = [
    # plain words she can't mishear: "turn my mic on", "take me off mute"
    (rf"(?:turn|switch|put) (?:on {MIC}|{MIC} (?:back )?on)(?: please)?{ON_DISCORD}|{MIC} on{ON_DISCORD}"
     rf"|take (?:me|myself) off mute{ON_DISCORD}|(?:i m |im )?off mute", "unmute"),
    (rf"(?:turn|switch) (?:off {MIC}|{MIC} off){ON_DISCORD}|{MIC} off{ON_DISCORD}"
     rf"|put (?:me|myself) on mute{ON_DISCORD}", "mute"),
    (rf"(?:{UN_SOUND}|i m|im|uh|oh) ?{MUTE_SOUND}(?: {ME})?{ON_DISCORD}|un ?mute(?: {ME})?{ON_DISCORD}"
     rf"|{DISCORD_WORD} (?:{UN_SOUND}|im) ?mute", "unmute"),
    (rf"{MUTE_SOUND}(?: {ME})?{ON_DISCORD}|silence {ME}{ON_DISCORD}|{DISCORD_WORD} mute|toggle (?:my )?mute", "mute"),
    (rf"(?:{UN_SOUND}|i m|im) ?{DEAF_SOUND}(?: {ME})?{ON_DISCORD}|undefined(?: {ME})?{ON_DISCORD}"
     rf"|{DISCORD_WORD} (?:{UN_SOUND}) ?deafen", "undeafen"),
    (rf"{DEAF_SOUND}(?: {ME})?{ON_DISCORD}|go deaf{ON_DISCORD}|{DISCORD_WORD} deafen|toggle (?:my )?deafen", "deafen"),
]


# Discord calls: "stream my screen", "stop streaming", "leave call"
CALL = r"(?: (?:on|in|from|to) (?:discord|the call|this call|my call|the vc|vc|voice|the voice channel))?"
DISCORD_CALL = [
    (rf"(?:stop|end|quit|kill|turn off|cancel) (?:my )?(?:stream(?:ing)?|screen ?share|screen sharing|"
     rf"sharing(?: my screen)?|go live|live)(?: my screen)?{CALL}|(?:stop|end) the (?:screen ?share|screen sharing){CALL}|(?:unshare|stop sharing) (?:my |the )?screen{CALL}"
     rf"|stop showing (?:them |everyone )?my screen{CALL}", "stop_stream"),
    (rf"(?:start )?(?:stream|share|screen ?share) (?:my |the )?(?:screen|desktop|monitor){CALL}|go live{CALL}"
     rf"|start (?:a |the )?stream(?:ing)?{CALL}|screen ?share{CALL}|start screen ?shar(?:e|ing){CALL}"
     rf"|(?:stream|share) (?:it |this )?(?:on|to|in) discord", "stream"),
    (r"(?:join|hop in|hop into|hop on|get in|get into|jump in|jump into|go in|go into|connect to|enter)"
     r" (?:the |my |our |a )?(?:call|vc|voice call|voice chat|voice channel|discord call|discord vc|discord voice)"
     r"(?: on discord)?|(?:call|ring) the (?:boys|squad|gang|crew)|join (?:the )?(?:boys|squad|gang|crew)", "join"),
    (rf"(?:leave|exit|quit|hang up|end|get out of|disconnect from|drop|bail on)(?: from)? (?:the |my |this |our )?"
     rf"(?:call|vc|voice call|voice chat|voice channel|discord call|discord vc|voice)(?: on discord)?"
     rf"|hang up(?: the call)?{CALL}|disconnect(?: me)?(?: from discord)?{CALL}", "leave"),
]


# Her voice, by voice: "talk faster", "speak up", "change your voice"
VOICE_ASKS = [
    (r"(?:talk|speak) (?:a (?:bit|little) )?(?:faster|quicker|quick)|speed up(?: your (?:voice|talking))?", "faster"),
    (r"(?:talk|speak) (?:a (?:bit|little) )?(?:slower|more slowly|slowly)|slow down(?: your (?:voice|talking))?",
     "slower"),
    (r"(?:talk|speak) (?:a (?:bit|little) )?(?:louder|up)|speak up|i can t hear you|i cant hear you", "louder"),
    (r"(?:talk|speak) (?:a (?:bit|little) )?(?:quieter|softer|more quietly|more softly)|lower your voice", "softer"),
    (r"(?:talk|speak) (?:in )?(?:a )?(?:higher|squeakier)(?: voice| pitch)?|higher (?:voice|pitch)", "higher"),
    (r"(?:talk|speak) (?:in )?(?:a )?(?:lower|deeper)(?: voice| pitch)?|(?:lower|deeper) (?:voice|pitch)", "lower"),
    (r"change (?:your|ur) voice(?: style)?|(?:try|use) (?:a )?(?:different|another|new) voice(?: style)?"
     r"|next voice(?: style)?", "next_style"),
    (r"(?:be|sound|talk) more (?:expressive|animated|lively|excited)|more expression", "more_expressive"),
    (r"(?:be|sound|talk) (?:less (?:expressive|animated)|more (?:flat|monotone|steady|calm))|less expression",
     "less_expressive"),
]
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
                "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90, "a couple of": 2, "a couple": 2,
                "a few": 3, "couple of": 2, "few": 3}
_NUM_WORD = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
AMOUNT = rf"(?:\d+(?:\.\d+)?|(?:{_NUM_WORD})(?: (?:one|two|three|four|five|six|seven|eight|nine))?|half an?|half)"
UNIT = r"(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)"
DURATION = rf"((?:{AMOUNT}) {UNIT}(?:(?: and)? (?:{AMOUNT}) {UNIT})?(?: and a half)?)"
CLOCK = r"(\d{1,2})(?:(?: |:)?(\d{2}))? ?(am|pm|a m|p m|in the morning|in the evening|at night|tonight)?"
TIMERS = [
    (rf"(?:set |start |make |put )?(?:a |an |me a )?(?:timer|countdown) (?:for |of |on )?{DURATION}", "add"),
    (rf"(?:set |start |make )?(?:a |an )?{DURATION} (?:timer|countdown)", "add"),
    (rf"remind me (?:to |about |that )?(.+?) in {DURATION}", "remind_after"),
    (rf"remind me in {DURATION} (?:to |about |that )?(.+)", "remind_in"),
    (rf"(?:set |make )?(?:an |my |the )?alarm (?:for |at )?{CLOCK}|wake me(?: up)? (?:at )?{CLOCK}", "alarm"),
    (r"(?:cancel|stop|delete|clear|turn off|remove|kill) (?:the |my |all |all my |that )?(?:timers?|alarms?|"
     r"reminders?|countdowns?)", "cancel"),
    (r"how (?:long|much time)(?: is)? left(?: on (?:the |my )?(?:timer|alarm|countdown))?|(?:check|how s|hows) "
     r"(?:the |my )?(?:timer|countdown)|time left", "left"),
]


def amount(text: str) -> float | None:
    text = text.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    if text in ("half", "half a", "half an"):
        return 0.5
    parts = text.split(" ")
    if text in NUMBER_WORDS:
        return float(NUMBER_WORDS[text])
    if len(parts) == 2 and parts[0] in NUMBER_WORDS and parts[1] in NUMBER_WORDS:
        return float(NUMBER_WORDS[parts[0]] + NUMBER_WORDS[parts[1]])      # "twenty five"
    return None


def seconds(duration: str) -> int:
    """'5 minutes' / 'an hour and a half' / 'one minute 30 seconds' -> seconds (0 = didn't get it)."""
    total = 0.0
    for value, unit in re.findall(rf"({AMOUNT}) ({UNIT})", duration):
        n = amount(value)
        if n is None:
            return 0
        scale = 3600 if unit.startswith(("hour", "hr")) else 60 if unit.startswith("min") else 1
        total += n * scale
    if duration.endswith("and a half"):
        last = re.findall(rf"({UNIT})", duration)[-1:]
        total += (1800 if last and last[0].startswith(("hour", "hr")) else 30 if last and last[0].startswith("min")
                  else 0)
    return int(total)


def timer_intent(t: str) -> Intent | None:
    for pattern, kind in TIMERS:
        m = re.fullmatch(pattern, t)
        if not m:
            continue
        if kind == "add":
            n = seconds(m.group(1))
            return Intent(Kind.TIMER, (str(n), ""), query="add") if n > 0 else None
        if kind in ("remind_after", "remind_in"):
            label, duration = (m.group(1), m.group(2)) if kind == "remind_after" else (m.group(2), m.group(1))
            n = seconds(duration)
            return Intent(Kind.TIMER, (str(n), label.strip()), query="add") if n > 0 else None
        if kind == "alarm":
            g = [x for x in m.groups()]
            hour, minute, half = (g[0], g[1], g[2]) if g[0] else (g[3], g[4], g[5])
            h, mi = int(hour), int(minute or 0)
            if half and half.replace(" ", "") in ("pm", "intheevening", "atnight", "tonight") and h < 12:
                h += 12
            if half and half.replace(" ", "") in ("am", "inthemorning") and h == 12:
                h = 0
            if not (0 <= h < 24 and 0 <= mi < 60):
                return None
            return Intent(Kind.TIMER, (f"{h}:{mi:02d}", ""), query="alarm")
        return Intent(Kind.TIMER, query=kind)
    return None


def discord_action(t: str) -> str:
    """'mute' / 'unmute' / 'deafen' / 'undeafen' / ''. A bare sound-alike ("meet", "the fan")
    only counts when it names you or Discord, so "meet me" is still mute, "the fan" alone isn't."""
    for pattern, action in DISCORD_CALL:
        if re.fullmatch(pattern, t):
            return action
    for pattern, action in DISCORD:
        if not re.fullmatch(pattern, t):
            continue
        bare = re.fullmatch(rf"(?:(?:{UN_SOUND}|i m|im|uh|oh) ?)?(?:{MUTE_SOUND}|{DEAF_SOUND})", t)
        if bare and not re.fullmatch(rf"(?:(?:{UN_SOUND}|i m|im) ?)?(?:mute|deafen)", t):
            return ""          # "meet", "on the fan", "definitely": too likely to be something else
        return action
    if re.search(rf"\b{DISCORD_WORD}\b", t) and not re.match(r"(?:open|launch|start|close|quit|kill|play|show|minimi)", t):
        words = f" {t} "       # anything else with "discord" in it: listen for the sound of the words
        if re.search(rf" (?:{UN_SOUND}|im) ?{MUTE_SOUND} ", words):
            return "unmute"
        if re.search(rf" {MUTE_SOUND} ", words):
            return "mute"
        if re.search(rf" (?:{UN_SOUND}|im) ?{DEAF_SOUND} ", words):
            return "undeafen"
        if re.search(rf" {DEAF_SOUND} ", words):
            return "deafen"
    return ""


EXPLORER = r"(?:the |my )?(?:file explorer|files|explorer|file manager|my files|windows explorer|folders?)"
REVEAL = [
    rf"(?:show|find|open|locate|reveal|pull up|bring up|take me to|go to|get)(?: me)?(?: where)? (.+?)(?: is| are)?"
    rf" (?:in|on|inside|with|using|through|from) {EXPLORER}",
    r"where(?: is| s| are| did i put| d i put| can i find) (?:my |the )?(.+?)"
    r"(?: (?:on|in) (?:my |the |this )?(?:pc|computer|laptop|files|rig))?",
    r"(?:find|locate) (?:me )?(?:my |the )?(.+?)(?: (?:on|in) (?:my |the |this )?(?:pc|computer|laptop|files|rig))?",
]
OPEN_FOLDER = r"(?:open|show me|show|go to|go into|go in|get into|take me to)(?: up)? (?:my |the )?(.+?) folder"
FOLDER_WORDS = r"downloads?|documents?|desktop|pictures|photos|videos|music|file explorer|this pc|recycle bin|onedrive"
GO_INTO = rf"(?:go|get|take me|jump) (?:in|into|to|inside) (?:my |the )?({FOLDER_WORDS})"

CHAT_WINDOW = (r"(?:open|show|start|bring up|pull up)(?: up)? (?:the |your |a |our )?(?:chat|text)(?: window| box| app)?"
               r"|chat window|chat box|let s (?:chat|text)|i (?:want|wanna) to (?:chat|type|text)(?: to you)?"
               r"|text chat|type to you|can i type")
SEARCH_MODE = (r"(?:(?:go|get|switch|jump|turn)(?: into| in| to| on)?|enter|start|activate|open|use|enable)"
               r"(?: the)? search(?:ing)? mode(?: on)?|search(?:ing)? mode(?: on| please)?"
               r"|i (?:want|wanna|need) to (?:search|look up|google)(?: something| some stuff| a few things)?"
               r"|(?:can you |could you )?(?:search|look up|google) (?:something|some stuff|a few things)(?: for me)?"
               r"|search|let s search|do a search|search for me|switch to search(?:ing)?|search time|time to search")
SEARCH = (r"(?:search(?: it)?(?: up| for| the web for| the web| google for| online for| online)?|google|look up|look for"
          r"|find(?: me)? information on|search(?: up)? on the web for)\s+(.+)")
# where to search: a site's own search, or a browser of yours
SEARCH_WHERE = {
    "google": r"google(?: dot com)?", "youtube": r"you ?tube", "bing": r"bing", "duckduckgo": r"duck ?duck ?go",
    "wikipedia": r"wikipedia|wiki", "reddit": r"reddit|read it", "amazon": r"amazon", "twitch": r"twitch",
    "github": r"git ?hub",
    "opera": r"opera(?: g x| gx| gee x| jx| g ex)?|oprah(?: g x| gx)?", "chrome": r"(?:google )?chrome",
    "edge": r"(?:microsoft )?edge", "firefox": r"fire ?fox", "brave": r"brave",
}
WHERE = "|".join(f"(?P<{key}>{pattern})" for key, pattern in SEARCH_WHERE.items())


def _search(query: str) -> Intent:
    """'cats on opera' -> query "cats", targets ("opera",). 'youtube for cats' -> the same way round."""
    m = re.fullmatch(rf"(?:the |my )?(?:{WHERE})(?: browser| app| website)? for (?P<what>.+)", query)
    if m:
        where = next(k for k in SEARCH_WHERE if m.group(k))
        return Intent(Kind.SEARCH, (where,), query=m.group("what").strip())
    m = re.fullmatch(rf"(.+?) (?:on|in|with|using|through|from|into|in the) (?:the |my )?(?:{WHERE})"
                     rf"(?: browser| app| website| please)?", query)
    if m:
        where = next(k for k in SEARCH_WHERE if m.group(k))
        return Intent(Kind.SEARCH, (where,), query=m.group(1).strip())
    return Intent(Kind.SEARCH, query=query)
ARTICLE = r"^(?:the|my)\s+"


# Same, but keeping a leading "and" / "um" / "uh": for Discord those are often the "un" of "unmute".
FILLER_START_KEEP_UN = r"^(?:(?:please|can you|could you|would you|will you|go ahead and|just|okay|ok)\s+)+"


# Words the speech model reliably gets wrong, fixed before anything else looks at them.
CORRECTIONS = [
    (r"\bspot (?:a|of|if|ify|if i|if eye|the) ?(?:fly|fi|fire|five|why|i)\b|\bspotty (?:fly|fi)\b|\bspot ify\b", "spotify"),
    (r"\b(?:this|dis|disc|the) cord\b|\bdisk ord\b", "discord"),
    (r"\b(?:you|u) tube\b", "youtube"),
    (r"\bp c\b|\bpea see\b|\bp see\b", "pc"),
    (r"\bopera (?:g x|gee x|jeep x|g ex|gx|j x)\b", "opera gx"),
    (r"\bdead lock\b", "deadlock"),
    # "drone" is often heard as drive / droid / drawn / throne... - only before "mode", so "drive" stays drive
    (r"\b(?:drive|droid|drawn|drown|drowned|throne|crone|drones|drome|dron|droned|drew in|grown|groan|drain|brain)"
     r" mode\b", "drone mode"),
    (r"\b(?:drive|droid|drawn|throne) (?:a |the )?(?:disc|disk)\b", "drone"),
    (r"\b(?:roe|row|rob|raw) (?:blocks|locks|lux)\b", "roblox"),
    (r"\bmine craft\b", "minecraft"),
    (r"\bthe whether\b", "the weather"),
    (r"\bshut (?:dawn|town|done)\b|\bshot down\b", "shut down"),
    (r"\bcapris?\b|\bcaprice\b", "capri"),
]


# Your own fixes (Settings -> Wake word -> "Fix what she mishears", or "when I say to school I mean
# discord"): applied first, whole words / phrases only.
CUSTOM: list[tuple[re.Pattern, str]] = []


def plain(text: str) -> str:
    """Lowercase words and spaces - how she sees what she heard."""
    text = re.sub(r"[^a-z0-9 .]+", " ", text.lower().replace("'", ""))
    return re.sub(r"\s+", " ", text).strip()


def set_corrections(pairs) -> int:
    """[(heard, meant), ...] from your settings. Longer phrases first, so "open to school" wins over
    "to school". Returns how many are in use."""
    CUSTOM.clear()
    seen = set()
    for heard, meant in sorted(((plain(str(h)), plain(str(m))) for h, m in pairs or []), key=lambda p: -len(p[0])):
        if heard and meant and heard != meant and heard not in seen:
            seen.add(heard)
            CUSTOM.append((re.compile(r"(?<![a-z0-9])" + re.escape(heard) + r"(?![a-z0-9])"), meant))
    return len(CUSTOM)


def correct(text: str) -> str:
    for pattern, fix in CUSTOM:
        text = pattern.sub(fix, text)
    for pattern, fix in CORRECTIONS:
        text = re.sub(pattern, fix, text)
    return text


GERUNDS = {"playing": "play", "opening": "open", "closing": "close", "launching": "launch", "searching": "search",
           "minimising": "minimise", "minimizing": "minimize", "pausing": "pause", "taking": "take",
           "switching": "switch", "clicking": "click", "highlighting": "highlight", "starting": "start",
           "putting on": "put on", "turning": "turn", "showing": "show"}


def normalise(text: str, filler: str = FILLER_START, fix: bool = True) -> str:
    text = text.lower().replace("'", "").replace("\u2019", "").replace("\u2018", "")   # Whisper writes ’
    text = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", text)                        # "7 a.m." -> "7 am"
    text = re.sub(r"[^a-z0-9 .]+", " ", text)
    text = re.sub(r"\.(?![a-z0-9])|(?<![a-z0-9])\.", " ", text)          # full stops go; "twitch.tv" / "10.5" stay
    text = re.sub(r"\s+", " ", text).strip()
    if fix:
        text = correct(text)
    text = re.sub(filler, "", text)
    text = re.sub(FILLER_END, "", text)
    for ing, base in GERUNDS.items():                 # "would you mind playing ..." -> "play ..."
        if text.startswith(ing + " "):
            text = base + text[len(ing):]
            break
    return text.strip()


def split_targets(text: str) -> tuple[str, ...]:
    """'discord and deadlock' -> ('discord', 'deadlock')."""
    parts = re.split(r"\s+(?:and|also|plus)\s+|\s*,\s*", text)
    cleaned = []
    for part in parts:
        part = re.sub(r"^(?:down|out|out of|up)\s+", "", part.strip())          # "close out discord"
        part = re.sub(r"\s+(?:on|from|in) (?:my|the|this) (?:computer|pc|laptop)$", "", part)
        part = re.sub(ARTICLE, "", part.strip())
        part = re.sub(r"\s+(?:app|application|program|game)$", "", part)
        if part:
            cleaned.append(part)
    return tuple(cleaned)


def _day(t: str) -> str:
    return "tomorrow" if re.search(r"\btomorrow\b", t) else "today"


def _place(t: str) -> str:
    m = re.search(r"\b(?:in|at|for) ([a-z ]+?)(?: (?:for )?(?:today|tonight|tomorrow|right now|now|this week))?$", t)
    place = m.group(1).strip() if m else ""
    return "" if place in ("today", "tonight", "tomorrow", "now", "right now", "this week") else place


# Teaching her a button by pointing at it with the mouse
_COLOUR = r"(?: (?:red|green|blue|grey|gray|white|black|little|big|small|round))*"
THIS_BUTTON = rf"(?:this|that|the){_COLOUR} (?:button|icon|thing|one|switch)"
STRICT_BUTTON = rf"(?:this|that|the){_COLOUR} (?:button|icon|switch)"
LEARN_BUTTON = [
    rf"{THIS_BUTTON}(?: here)? (?:makes me|lets me|is (?:for|how (?:i|you))|is to) (?:me |us |you )?(.+)",
    rf"{STRICT_BUTTON}(?: here)? (?:will|does|means|is|=) (?:me |us |you )?(.+)",
    rf"(?:learn|remember)(?: that)? {THIS_BUTTON} (?:is|means|for|as|makes me|lets me) (?:me |us )?(.+)",
    rf"when i say (.+?),? (?:press|click|hit|push) {THIS_BUTTON}",
    rf"(?:press|click|hit|push) {THIS_BUTTON} when(?:ever)? i say (.+)",
    rf"(?:to|for) (.+?),? (?:press|click|hit|push) {THIS_BUTTON}",
]
FORGET_BUTTON = r"(?:forget|unlearn|delete|remove) (?:the |my )?(.+?) (?:button|icon)"


TYPE_VERB = r"(?:type(?: out| in| up)?|write(?: down| out)?)"
TYPE_END = r"(?:[\s,.!]+(?:please|for me|thanks|thank you|in there|in it|into it|in here))+[\s.!]*$"
# "type hi in notepad" / "write gg into the discord chat": where to type it (only if that's one of your apps -
# the router checks, so "type I live in London" stays all words).
TYPE_WHERE = (r"(?i)^(.+?)[\s,]+(?:in|into|inside|on|onto|over in|over on|to)\s+(?:the |my |a new )?"
              r"([\w' .-]+?)(?:\s+(?:app|window|chat|tab|box|doc|document|file|channel|dms?|server))?[\s.!]*$")
TYPE_AT_START = r"(?:in|into|on|inside|over in|over on) (?:the |my )?(.+?)(?: app| window| chat)?,? (?:please )?(?:type|write)\b.*"


def typed_words(text: str) -> str | None:
    """'Open Notepad and type Hi, TikTok.' -> 'Hi, TikTok.' - your words exactly (capitals, commas),
    or None if it isn't a "type ..." command. "write me a poem" isn't one (that's for her AI)."""
    m = re.search(rf"(?i)(?:^|\b)(?:hey capri,? |capri,? |please |can you |could you )*{TYPE_VERB}\s+(?:the words? |this: ?|"
                  r"that: ?)?(.+)$", text.strip())
    if not m or re.match(r"(?i)(?:me|a|an|my|your|an?other|some|about|it|that|this)\b", m.group(1)):
        return None
    words = re.sub(rf"(?i){TYPE_END}", "", m.group(1)).strip().strip('"\u201c\u201d')
    words = re.sub(r"[\r\n]+", " ", words)                  # one line: typing never presses Enter
    return words[:2000] or None


HAIR_WORD = r"(?:hair|hairstyle|hair style|hairdo|haircut)"
HAIR_OLD = r"(?:old|classic|first|original|spiky|previous|other|boxy)"
HAIR_NEW = r"(?:new|show|traced|zigzag|current|latest|normal)"
HAIR = (rf"(?:(?:can you |could you |please |hey )*)(?:(?:change|switch|swap|flip|toggle) (?:up )?your {HAIR_WORD}"
        rf"(?: (?:back|to (?:the |your )?(?P<to>{HAIR_OLD}|{HAIR_NEW})(?: one| {HAIR_WORD})?))?"
        rf"|(?:use|wear|put on|go back to|switch to|change to|swap to|do|try|give me|bring back) (?:your |the |that )?"
        rf"(?P<which>{HAIR_OLD}|{HAIR_NEW}) {HAIR_WORD}"
        rf"|(?P<bare>{HAIR_OLD}|{HAIR_NEW}) {HAIR_WORD}(?: please)?)")


def hair_style_for(word: str) -> str:
    """'old' -> classic, 'new' -> storm, '' -> '' (swap to the other one)."""
    if not word:
        return ""
    return "classic" if re.fullmatch(HAIR_OLD, word) else "storm"


SETTINGS_WORDS = r"(?:settings|options|preferences|setup|config|configuration|control panel)"
OPEN_SETTINGS = (rf"(?:(?:can you |could you |would you |please |hey |yo )*)(?:(?:open|show|bring up|pull up|go to|take me to|"
                 rf"launch|get|show me|let me see|i want|i need)(?: me)?(?: up)? )?"
                 rf"(?:your|capri s|capris|capri|her|the capri) {SETTINGS_WORDS}(?: window| page| menu)?(?: please| for me)*")


def type_where(words: str) -> tuple[str, str] | None:
    """'hi tiktok in notepad' -> ('hi tiktok', 'notepad'): the words, and the app named at the end."""
    m = re.match(TYPE_WHERE, words.strip())
    if not m or not m.group(1).strip(" ,"):
        return None
    return m.group(1).strip(" ,"), m.group(2).strip().lower()


UPDATE_WORDS = (r"(?:(?:can you |could you |would you |please |hey |yo )*)"
                r"(?:check (?:for |if there (?:are|s|is) )?(?:any |an |a |new )*updates?(?: for (?:yourself|you|capri))?"
                r"|(?:are there|is there|got) (?:any |an |a )?(?:new )?(?:updates?|versions?)(?: for (?:you|capri))?"
                r"|update (?:yourself|capri|you|now)|install (?:the |your |an? )?update"
                r"|(?:get|download) (?:the |your )?(?:latest|newest|new) (?:version|update)(?: of (?:you|capri|yourself))?"
                r"|is there a new(?:er)? (?:version of )?(?:you|capri)|are you up to date)(?: please| for me)*")


RESTART_SELF = (r"(?:(?:can you |could you |please |hey |yo )*)(?:restart|reboot|reload|relaunch|refresh) "
                r"(?:yourself|capri|you|the app|your app|your program)(?: please| for me| now)*")


RESTART_HER = re.compile(r"\b(?:restart|reboot|relaunch|reload)\s+(?:yourself|capri|the app|your app|your program)\b")


def parse(text: str) -> Intent:
    if RESTART_HER.search((text or "").lower()):
        return Intent(Kind.RESTART_APP)          # "restart capri" - her, not the PC (before her name is dropped)
    t = normalise(text)
    if not t:
        return Intent(Kind.UNKNOWN)
    if re.match(rf"{TYPE_VERB} ", t) and (words := typed_words(text)) is not None:
        return Intent(Kind.TYPE, query=words)
    if re.fullmatch(RESTART_SELF, t):
        return Intent(Kind.RESTART_APP)                            # "restart yourself": her, not the PC
    if re.fullmatch(UPDATE_WORDS, t):
        return Intent(Kind.UPDATE)                                 # "check for updates": a newer Capri on GitHub
    if re.fullmatch(OPEN_SETTINGS, t) or re.fullmatch(rf"(?:capri )?{SETTINGS_WORDS}(?: please)?", t):
        return Intent(Kind.SETTINGS)                               # "open your settings": hers, not Windows'
    m = re.fullmatch(HAIR, t)
    if m:
        return Intent(Kind.HAIR, query=hair_style_for(m.group("to") or m.group("which") or m.group("bare") or ""))
    m = re.fullmatch(TYPE_AT_START, t)
    if m and (words := typed_words(text)) is not None:            # "in notepad, type hi"
        return Intent(Kind.TYPE, (m.group(1).strip(),), query=words)
    for pattern in LEARN_BUTTON:
        m = re.fullmatch(pattern, t)
        if m:
            return Intent(Kind.LEARN_BUTTON, (m.group(1).strip(),))
    m = re.fullmatch(FORGET_BUTTON, t)
    if m and not re.fullmatch(r"(?:the )?(?:shortcut|word)s?.*", m.group(1)):
        return Intent(Kind.FORGET_BUTTON, (m.group(1).strip(),))
    m = re.fullmatch(LEARN_FIX, normalise(text, fix=False))     # your words exactly as she heard them
    if m:
        heard, meant = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        return Intent(Kind.CORRECTION, (heard.strip(), meant.strip()))
    m = re.fullmatch(SHORTCUT, normalise(text, fix=False))
    if m:
        return Intent(Kind.SHORTCUT, (m.group(1).strip(), m.group(2).strip()))
    m = re.fullmatch(FORGET, t)
    if m:
        return Intent(Kind.FORGET, ((m.group(1) or m.group(2) or m.group(4) or "").strip(),))
    if re.fullmatch(CLICK_HERE, t):
        return Intent(Kind.CLICK, ("",))
    m = re.fullmatch(CLICK_NAMED, t)
    if m:
        label = (m.group(1) or m.group(2) or "").strip()
        if label in ("that", "this", "it", "here", "there"):
            label = ""
        return Intent(Kind.CLICK, (label,))
    m = re.fullmatch(TAB_SWITCH, t)
    if m:
        groups = {k: v for k, v in m.groupdict().items() if v}
        browser = next((k.split("_")[-1] for k in groups if k.split("_")[-1] in
                        ("opera", "chrome", "edge", "firefox", "brave", "vivaldi")), "")
        name = (groups.get("to") or groups.get("named") or "").strip()
        if name in ("next", "other", "another", "different", "a different"):
            name = ""
        return Intent(Kind.TAB, (browser,) if browser else (), query=name)
    for pattern, action in DISCORD_CALL:            # before videos: "stop my stream" is yours, not a video
        if re.fullmatch(pattern, t):
            return Intent(Kind.DISCORD, query=action)
    for pattern, action in VIDEO:
        if re.fullmatch(pattern, t):
            return Intent(Kind.VIDEO, query=action)
    m = re.fullmatch(SCREENSHOT, t)
    if m:
        window = any(m.group(g) for g in ("w1", "w2", "w3"))
        return Intent(Kind.SCREENSHOT, query="window" if window else "screen")
    topic = pc_topic(t)
    if topic:
        return Intent(Kind.PC_INFO, query=topic)
    if re.fullmatch(r"go(?: back)? home|go back to your (?:corner|spot|place)", t):
        return Intent(Kind.MOVE, ("bottom_right",))
    if re.fullmatch(AI_SETUP, t):
        return Intent(Kind.AI_SETUP)
    m = re.fullmatch(MOVE, t)
    if m:
        return Intent(Kind.MOVE, (MOVE_SPOTS[m.group("spot")],))
    if re.fullmatch(REPEAT_YOU, t):
        return Intent(Kind.REPEAT, query="you")
    if re.fullmatch(REPEAT_ME, t):
        return Intent(Kind.REPEAT, query="me")
    m = re.fullmatch(REPEAT_AFTER, normalise(text, fix=False))
    if m and m.group(1).strip():
        return Intent(Kind.REPEAT, (m.group(1).strip(),), query="after")
    m = re.fullmatch(SCROLL, t)
    if m:
        direction = m.group("dir") or m.group("dir2")
        return Intent(Kind.SCREEN, ("lot" if m.group("lot") else "bit" if m.group("little") or m.group("dir2") else "",),
                      query="scroll_" + direction)
    for key, (pattern, _combo, _line) in SCREEN_KEYS.items():
        if re.fullmatch(pattern, t):
            return Intent(Kind.SCREEN, query=key)
    for pattern, action in SCREEN_TEXT:
        m = re.fullmatch(pattern, t)
        if m:
            return Intent(Kind.SCREEN, (m.group(1).strip(),), query=action)
    m = re.fullmatch(DRONE_CORNER, t)
    if m:
        return Intent(Kind.DRONE_CORNER, (m.group(1) or m.group(2),))
    for pattern, kind in SIMPLE:
        if re.fullmatch(pattern, t):
            return Intent(kind)
    for pattern, ask in VOICE_ASKS:
        if re.fullmatch(pattern, t):
            return Intent(Kind.VOICE, query=ask)
    timer = timer_intent(t)
    if timer is not None:
        return timer
    # personalities after the fixed commands, so "switch to normal mode" stays what it was
    if re.fullmatch(PERSONALITY_ASK, t):
        return Intent(Kind.PERSONALITY)
    m = re.fullmatch(PERSONALITY, t)
    if m:
        from ..personality import resolve
        key = resolve((m.group("p") or m.group("p2") or "").strip())
        if key:
            return Intent(Kind.PERSONALITY, (key,))
    if re.fullmatch(SEARCH_MODE, t):
        return Intent(Kind.SEARCH_MODE)
    if re.fullmatch(CHAT_WINDOW, t):
        return Intent(Kind.CHAT_WINDOW)
    m = re.fullmatch(rf"(?:search|look up|google)(?: on| in| with| using) (?:the |my )?(?:{WHERE})(?: for)? (.+)", t)
    if m:                                            # "search on opera for cats"
        return Intent(Kind.SEARCH, (next(k for k in SEARCH_WHERE if m.group(k)),), query=m.group(m.lastindex).strip())
    m = re.fullmatch(SEARCH, t)
    if m:
        query = re.sub(r"^up\s+", "", m.group(1).strip())
        query = re.sub(r"\s+up$", "", query) if t.startswith("search ") else query   # "search cats up"
        if query:
            return _search(query)
    for pattern in REVEAL:
        m = re.fullmatch(pattern, t)
        if m and m.group(1).strip() not in ("it", "that", "them", "this"):
            targets = split_targets(re.sub(r"\s+(?:file|folder|files)$", "", m.group(1).strip()))
            if targets:
                return Intent(Kind.REVEAL, targets[:1])
    m = re.fullmatch(OPEN_FOLDER, t) or re.fullmatch(GO_INTO, t)
    if m:
        return Intent(Kind.OPEN, split_targets(m.group(1))[:1])
    for pattern, action in MEDIA:
        if re.fullmatch(pattern, t):
            return Intent(Kind.MEDIA, query=action)
    if re.fullmatch(NOW_PLAYING, t):
        return Intent(Kind.NOW_PLAYING)
    for pattern in WEATHER:
        m = re.fullmatch(pattern, t)
        if m:
            return Intent(Kind.WEATHER, query=_place(t), day=_day(t))
    m = re.fullmatch(RAIN, t)
    if m:
        return Intent(Kind.RAIN, query=_place(t), day=_day(t))
    m = re.fullmatch(MUSIC_DEFAULT, t)
    if m:
        return Intent(Kind.MUSIC_SERVICE, (music_service(m.group("svc") or m.group("svc2") or m.group("svc3")),))
    m = re.fullmatch(rf"play (.+?) (?:on|in|using|with|from)(?: the| my)? (?P<svc>{MUSIC_NAMES})(?: app| website| site)?", t)
    if m:
        service = music_service(m.group("svc"))
        intent = _play(m.group(1).strip(), on_youtube=service == "youtube")
        return intent if service in ("spotify", "youtube") else Intent(Kind.PLAY, (service,), intent.query, intent.day,
                                                                         intent.artist)
    m = re.fullmatch(r"play (.+?)(?: on spotify| on youtube)?", t)
    if m:
        return _play(m.group(1).strip(), on_youtube=t.endswith(" on youtube"))
    for pattern, action in POWER:
        if re.fullmatch(pattern, t):
            return Intent(Kind.POWER, query=action)
    if re.fullmatch(MINIMIZE_ALL, t):
        return Intent(Kind.MINIMIZE)
    if re.fullmatch(MINIMIZE_THIS, t):
        return Intent(Kind.MINIMIZE, ("this",))
    if re.fullmatch(RESTORE, t):
        return Intent(Kind.RESTORE)
    m = re.fullmatch(MINIMIZE_VERB + r"\s+(.+)", t)
    if m:
        return Intent(Kind.MINIMIZE, split_targets(m.group(1)))
    action = discord_action(t)
    if action in ("mute", "deafen") and discord_action(normalise(text, FILLER_START_KEEP_UN)) == "un" + action:
        action = "un" + action                     # "and mute me" = "unmute me"
    if action:
        return Intent(Kind.DISCORD, query=action)
    topic = chat_topic(t)
    if topic:
        return Intent(Kind.CHAT, query=topic)
    if re.fullmatch(LOUDER_UP, t):
        return Intent(Kind.MEDIA, query="volume_up")
    m = re.fullmatch(OPEN_VERBS + r"\s+(.+)", t) or re.fullmatch(OPEN_AROUND, t)
    if m:
        if re.fullmatch(r"(?:the )?(?:weather|forecast)(?: (?:for|in|at) .+)?", m.group(1)):
            return Intent(Kind.WEATHER, query=_place(t), day=_day(t))     # "pull up the weather"
        return Intent(Kind.OPEN, split_targets(m.group(1)))
    m = re.fullmatch(CLOSE_VERBS + r"\s+(.+)", t) or re.fullmatch(r"(?:shut|turn|switch) (.+?) (?:down|off)", t)
    if m:
        return Intent(Kind.CLOSE, split_targets(m.group(1)))
    topic = chat_topic(t, keywords=True)
    if topic:
        return Intent(Kind.CHAT, query=topic)
    return Intent(Kind.UNKNOWN, query=t)


SELF_STATS = (r"(?:how much (?:ram|memory|cpu|power|resources?|space)(?: (?:are|do|does|is))? (?:you|capri)"
              r"(?: (?:using|use|take|taking|eat|eating|need|hog|hogging)(?: up)?)?(?: right now| rn)?|"
              r"(?:what|whats|what s|what are|show me|tell me) (?:are )?your (?:stats|ram|memory|cpu|usage|resource usage)|"
              r"your (?:stats|usage)|how (?:heavy|light|resource heavy) are you|are you (?:heavy|lagging my pc|slowing my pc)|"
              r"(?:is|are) (?:capri|you) using (?:a lot of|much|too much) (?:ram|memory|cpu|resources)|"
              r"how much (?:ram|memory|cpu) (?:does|is) capri (?:use|using|take|taking)(?: up)?)")


def pc_topic(t: str) -> str:
    """'what's eating my ram' -> 'ram'. Needs a question / usage word too, so "memory lane" isn't one.
    About her ("how much ram are you using") -> 'self'."""
    if len(t.split()) > 16:
        return ""
    if re.fullmatch(SELF_STATS, re.sub(r"^(?:hey |yo |so |and )?(?:capri )?", "", t)):
        return "self"
    for topic, pattern in PC_TOPICS:
        if re.search(pattern, t) and (topic in ("uptime", "overview", "battery") or re.search(PC_ASK, t)):
            return topic
    return ""


def _play(what: str, on_youtube: bool = False) -> Intent:
    """'let you down by nf' -> song "let you down", artist "nf". Titles with "by" in them
    ("stand by me") still work: the router falls back to the whole phrase.

    targets = ("youtube",) for "... on youtube".
    """
    where = ("youtube",) if on_youtube else ()
    m = re.fullmatch(r"(?:songs|music|something|anything|some songs|a song|tracks) (?:by|from) (.+)", what)
    if m:
        return Intent(Kind.PLAY, where, query="", artist=m.group(1).strip())
    m = re.fullmatch(r"(?:the song |the track |song |track )?(.+?) by (?:the artist |artist )?(.+)", what)
    if m:
        return Intent(Kind.PLAY, where, query=m.group(1).strip(), artist=m.group(2).strip())
    return Intent(Kind.PLAY, where, query=what)


# Small talk (chat.py has her answers). Checked after every real command, so
# "how are you" never shadows an action.
CHAT: list[tuple[str, str]] = [
    (r"(?:hi|hello|hey|hiya|yo|sup|howdy|hey there|hi there|hello there)(?: capri| girl| babe)?", "hello"),
    (r"good (?:morning|afternoon|evening)(?: capri)?|morning(?: capri)?", "good_morning"),
    (r"good ?night(?: capri)?|night night|im (?:going to bed|off to bed|going to sleep|heading to bed)"
     r"|(?:i m |im )?(?:going|off) to (?:bed|sleep)", "good_night"),
    (r"how are (?:you|ya|u)(?: doing| feeling)?(?: today)?|how(?: s| is) it going|how you doing|hows life"
     r"|how(?: s| is) your day|you (?:good|okay|ok|alright)|are you (?:okay|ok|good|alright)", "how_are_you"),
    (r"what(?: s| is)? up|whats up|wassup|what are you (?:doing|up to)|whatcha doing", "whats_up"),
    (r"(?:thank you|thanks|thank u|cheers|ta|thanks a lot|thank you so much|appreciate it)(?: capri)?"
     r"|(?:good|nice|great) (?:job|work)(?: capri)?|you(?: re| are)? (?:the best|amazing|awesome)", "thanks"),
    (r"(?:tell me|say|know any|got any) (?:a )?(?:joke|jokes|something funny)|make me laugh", "joke"),
    (r"who are you|what(?: s| is| are) you(?:r name)?|whats your name|what s ur name|whats ur name|your name"
     r"|what do (?:they|people) call you|introduce yourself", "who_are_you"),
    (r"what can you do|what do you do|help|help me|what are your (?:commands|skills)", "help"),
    (r"(?:i m|im|i am) (?:bored|so bored)|entertain me", "bored"),
    (r"(?:i m|im|i am) (?:tired|exhausted|sleepy|so tired)", "tired"),
    (r"(?:i m|im|i am) (?:sad|down|upset|not okay|not ok|having a bad day|stressed)|bad day|today sucked", "sad"),
    (r"(?:i m|im|i am) (?:good|great|fine|okay|ok|alright|doing (?:good|well|great|fine|okay)|not bad|well)"
     r"|(?:good|great|fine|not bad|pretty good|alright|okay|doing good|doing well|all good)"
     r"(?: thanks| thank you)?(?: and you| you)?", "im_good"),
    (r"i love you|love you|i like you|youre cute|you(?: re| are) (?:cute|pretty|beautiful)", "love"),
    (r"(?:bye|goodbye|see you|see ya|later|cya|talk later|im leaving|gotta go)(?: capri)?", "bye"),
    (r"(?:and )?(?:you|what about you|how about you|and you)", "and_you"),
    (r"(?:lol|haha|ha ha|hahaha|thats funny|funny|lmao|nice one)", "laugh"),
    (r"(?:yes|yeah|yep|sure|okay|ok|no|nope|nah|maybe|i guess)", "reply"),
]


# "I'm soo bored", "I'm really really tired", "kinda sad ngl": the feeling words matter, the rest is
# emphasis. Stretched words lose their extra letters first ("sooo" -> "so", "borrred" -> "bored").
INTENSIFIERS = (r"\b(?:so|soo|really|rly|very|super|kinda|kind of|sort of|pretty|extremely|totally|literally|"
                r"honestly|just|like|a bit|a little|a little bit|quite|too|actually|lowkey|highkey|ngl|tbh|"
                r"right now|today|rn|getting|feeling|feel|so so|as hell|af|mad|hella|bro|man|dude|capri)\b")
KEYWORDS = [   # a short sentence with one of these is that topic, however it's said
    (r"\bbored\b|\bboring\b|nothing to do", "bored"),
    (r"\b(?:tired|sleepy|exhausted|knackered)\b", "tired"),
    (r"\b(?:sad|depressed|upset|lonely|stressed|down bad|crying)\b|bad day", "sad"),
    (r"\bjoke\b|make me laugh|something funny", "joke"),
    (r"\b(?:thanks|thank you|thank u|cheers)\b", "thanks"),
    (r"\b(?:love you|like you|youre cute|you are cute)\b", "love"),
    (r"^(?:good )?(?:night|nite)\b|going to (?:bed|sleep)", "good_night"),
    (r"how are (?:you|ya|u)|hows it going|how you doing", "how_are_you"),
    (r"^(?:bye|goodbye|see ya|see you|later|cya)\b", "bye"),
]


def _squeeze(t: str) -> str:
    """'sooo' -> 'so', 'borrred' -> 'bored', 'hiii' -> 'hi' (3+ of a letter = 1; 'soo' -> 'so')."""
    t = re.sub(r"(\w)\1{2,}", r"\1", t)
    return re.sub(r"\bso+\b", "so", t)


def chat_topic(t: str, keywords: bool = False) -> str:
    """Small-talk topic. keywords=True also accepts any short sentence with a feeling word in it
    (checked last, after every real command)."""
    t = re.sub(r"^(?:hey|so|well|oh|um|uh)\s+(?=\w)", "", t) if " " in t else t
    for candidate in (t, _squeeze(t), re.sub(r"\s+", " ", re.sub(INTENSIFIERS, " ", _squeeze(t))).strip()):
        for pattern, topic in CHAT:
            if candidate and re.fullmatch(pattern, candidate):
                return topic
    if keywords and len(t.split()) <= 7:
        for pattern, topic in KEYWORDS:
            if re.search(pattern, _squeeze(t)):
                return topic
    return ""


YES = {"yes", "yeah", "yep", "yup", "sure", "do it", "confirm", "go ahead", "affirmative", "okay", "ok",
       "yes please", "please do", "force it", "force close", "kill it"}
NO = {"no", "nope", "nah", "cancel", "stop", "dont", "do not", "never mind", "nevermind", "leave it",
      "negative", "no thanks", "forget it"}


def parse_yes_no(text: str) -> bool | None:
    t = normalise(text)
    t = re.sub(r"^(?:capri|hey capri)\s+", "", t)
    words = set(t.split())
    if words & {"yes", "yeah", "yep"} and words & {"no", "nope"}:
        return None   # "yes or no" - e.g. her own question echoing back
    if t in YES or t.split(" ")[0] in ("yes", "yeah", "yep", "yup"):
        return True
    if t in NO or t.split(" ")[0] in ("no", "nope", "nah"):
        return False
    return None
