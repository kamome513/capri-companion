# Capri Desktop Companion

A small, transparent Windows desktop overlay: Capri stands in the bottom-right
corner of your screen with a black, neon-purple terminal panel floating above her.

Built with **Python + PySide6 (Qt 6)**. Qt gives reliable per-pixel transparency,
frameless always-on-top windows, multi-monitor and per-monitor DPI support on
Windows 10/11, and uses very little CPU while idle (nothing redraws unless the
state changes).

## Download

**Just want to use her?** Grab `Capri-Setup-1.35.0.exe` from the
[Releases page](https://github.com/kamome513/capri-companion/releases) and run it.
No Python, no admin rights.

## Quick start

* **Easiest:** install Python 3.10+ (python.org, tick *Add to PATH*), run
  `build.bat` once, then run `dist\Capri-Setup-1.35.0.exe`.
  It installs Capri for your user, with no admin rights needed.
  * You need [Inno Setup 6](https://jrsoftware.org/isdl.php) for the
    installer step. Without it you get the ready-to-run `dist\Capri\` folder
    instead.
* **From source:** double-click `run.bat`. See *Run it on Windows* below.

## New in 1.35

* **"Open your settings" works.** So do "show me your settings" and just "settings". Plain "open settings"
  still opens Windows Settings.
* **"Change music to SoundCloud"** (and "switch my music app to ...", "set the music player to ...").
* **Songs: she plays the one you asked for.**
  * "Chicago by MJ" plays Michael Jackson's "Chicago", not "Chicago (Original Version)". Live, remix,
    remaster and other versions only win if you ask for them.
  * Initials work for artists ("MJ", "NF").
* **No more random clicks or "select all" when you say "play ... by ...".** She only types into
  Spotify, or clicks its Play button, when Spotify is really in front. Otherwise she uses Spotify's
  own search link, which needs no keyboard.
* **No more surprise websites.** A slow Spotify gets more time (25 s), then she shows the search
  inside Spotify. YouTube is only used when the Spotify app isn't installed.
* **"Can you ..." then a pause:** she waits for the rest instead of stopping at "can you".
* **Your "Also say" names come first.** If one sounds like one of her own phrases (her chat window,
  say), "open <your name>" opens your app.
* **Apps tab: easier, and it lists what's really on your PC.**
  * It no longer comes filled with games you might not have (Deadlock, Roblox, Minecraft...). An old
    list loses those once, and gains every game you've downloaded: Steam, plus Epic, Xbox, Riot,
    GOG, EA, Ubisoft and Battle.net through their Start-menu shortcuts.
  * **Add app or game...** opens a searchable list of everything installed. Tick and add; no file
    hunting. **Browse for a file...** is still there for anything not listed.
  * **Add my games** adds games you've installed since.
  * A **Found?** column says whether Capri can find each app: ✓ found, ✗ file missing / not installed
    in Steam / needs the full path, • she'll look it up in the Start menu.
  * Arguments, processes and "When closing" are behind **Show advanced**.
* **Parakeet hearing: best for heavy accents.** Settings → Wake word → *Download Parakeet* (about
  480 MB, once). Then pick **Parakeet** under Hearing and press Apply.
  * Parakeet is NVIDIA's speech model, run with sherpa-onnx. It's far better with strong accents,
    mumbling and cheap mics.
  * Vosk still catches "Hey Capri". Parakeet re-hears what you said after it, in about half a second.
  * It runs on your PC and nothing is sent anywhere.
  * It uses about 900 MB of RAM. While she's a drone in a game it unloads and Vosk hears you alone;
    it reloads after.
* **A private memory of you.**
  * Tell her "my name is Sam", "I love Deadlock", "my favourite food is ramen", "I'm from Glasgow"
    or "remember that my exam is Friday". Ask "what's my name?" or "what do you know about me?".
  * It's saved in `%LOCALAPPDATA%\Capri\about_you.json`: your user folder, never Capri's files or
    the installer.
  * **Anything personal is answered by her own chatbot on your PC, even with an AI set up.** It's not
    sent to the AI.
  * Nothing from her memory goes into the AI's instructions unless you tick *Let the AI know what
    Capri remembers about me* (Settings → Assistant).
  * Your Windows user name and user-folder paths are taken out of anything that does go to an AI.
  * "Forget that I like ..." removes one thing. "Forget everything about me" asks first, then deletes
    it all. There's also a button in Settings.

## New in 1.34

* **No more spikes on her legs.** Only her hair is drawn around her now.
* **Sitting on windows: she doesn't sit on a hidden window any more.** If the window she's on gets
  covered (say Discord maximised over Spotify), she moves after a moment. She hops onto the window
  you're using if she can sit on it, otherwise she goes home. A passing popup doesn't move her.
* **Closing the app she's sitting on:** she teleports home first, then zaps it closed from there.
  Before, it just closed with no zap.
* **Her neural "Capri" voice is back in Capri.exe.** Settings → Assistant → *Download Capri's voice*
  (about 120 MB, once). In the installed app it's saved to `%LOCALAPPDATA%\Capri\models\kokoro`, so it
  survives reinstalls. The installer is now about 60 MB.
* **"Choom", never "chom".**
  * Her neural voice reads "choom" right as it's written.
  * ElevenLabs, and Windows voices that refuse exact sounds, get a stretched "chooom" so they can't
    shorten it.
  * Windows voices still get the exact sounds when they accept them.
* **Smoother beeps.**
  * Every blip fades in and out (no clicks).
  * Each one glides from the last note instead of jumping.
  * They overlap a little like syllables, and the retro one's harsh square edge is rounded off.
* Her log now notes which voice she's speaking with, and any line she couldn't say (handy if a voice
  ever acts up).

## New in 1.33

* **She stays over your games.**
  * **The bug:** many full-screen games make their own window "always on top", and Windows then puts the
    game in front of her (and her drone), so she seemed to vanish.
  * **The fix:** while a game, or anything full screen, is in front, she puts herself back on top every
    1.5 s. She never takes focus, so your game keeps the keyboard and mouse. The rest of the time
    nothing extra runs.
  * **Exclusive full screen:** a game in exclusive full screen draws straight to the screen and nothing
    can show over it. She says so once in her log; set the game to borderless (or windowed) full screen.
  * **New setting, Settings → Character → In games:** "Stay as herself, over the game", or "Turn into
    the little drone" (as before, and still the default).

## New in 1.32

* **Hearing, tuned to you.**
  * **Teach her your voice** (Settings → Voice): say "Hey Capri" 4 times. She sets her wake-word threshold
    to your voice and mic, a little below your quietest "Capri", so she stops missing you. She also
    remembers how your mic makes her name sound, so that counts as her name.
  * **Fewer missed wakes:** every "Capri" already gets a second listen, so the first check can be less
    strict. A real but slightly unsure "Capri" now wakes her; a "happy" still doesn't.
  * **More accents count:** "cap free", "cap tree", "kapri", "copper e".
  * **Near-misses show in her log** ("Almost: capri (62%) - stayed asleep"), so you can see she heard something.
* **Two commands in one breath:** "close discord open spotify" (no "and"), "close discord an open spotify",
  and even three in a row. She only splits where both halves are real commands, so "search youtube for
  open source" stays one search.
* **Discord streaming:** Discord's screen-share window has tiles that only react to a real click. When
  Windows' "press" doesn't take, she clicks the control with the mouse.
  * She now checks the result on your voice panel (next to Mute), not on any "Stop Streaming" text
    anywhere. So stop streaming and leave call no longer say "didn't budge" when they worked.
* **Shut down / restart / sleep are quiet.** After your "yes", her goodbye is only written, and anything
  she was saying stops.
* **Her hair colour** now matches the reference picture: (249, 8, 84) with fewer, crisper speckles.
  * Lying down, the strands of her own hair beside her face are recoloured to match, so it reads as one
    head of hair.
* **Ollama / llama:**
  * If Ollama is running but the model isn't downloaded, or Ollama is your pick but isn't running, she
    says so once and shows it on Settings' "Last try" line. Before, she quietly used her built-in chat.
  * Small local models chat much better without her list of PC actions, so she only sends that list when
    you ask her to do something.
  * Llama 3.2 is a small model. For a smart conversation, a free Google Gemini key is a big step up.

## New in 1.31

* **Pick her hair.**
  * **Like the show** (the default): the zigzag pile traced from her picture.
  * **Classic spiky:** her first hair, the wide spiky block with fine stripes and a purple edge.
  * Choose in Settings → Character → Hair, or right-click her → Capri → Hair. Or say it: "change your hair"
    (swaps), "use your old hair", "classic hair", "new hair".
  * Every figure of her follows the choice: standing, lying down, the greeting, visits and teleports.
* **A real Windows app, Capri.exe, with an installer** (`Capri-Setup-1.31.0.exe`).
  * It installs for you only: no admin prompt, Start menu shortcut, optional desktop shortcut and
    "Start with Windows", and an uninstaller.
  * On first start she downloads her offline speech model herself (40 MB, once, into
    `%LOCALAPPDATA%\Capri\models`) and says so. Before, that needed `setup_voice.bat`.
  * Built with Qt 6.8. The whole test suite passes on Qt 6.8 too.
* **Fixed:** on PySide 6.8, screen-watching game affirmations stopped after their first check. A setting
  named `emit` clashed with Qt's own `emit`.

## New in 1.30

* **A real conversation with her AI, checked end to end.**
  * She was tested against a stand-in ChatGPT server using her real AI code and real web requests. Every
    sentence that isn't a command goes to the AI, which remembers the conversation.
  * After she answers, she keeps listening for your reply (no "Hey Capri" needed), up to 12 times in a row.
  * **When it can't answer, you see exactly why.** Settings → Assistant → AI now has a **Last try** line
    with the time and either her answer or the service's own error, e.g. "You exceeded your current quota".
    Every AI error is also written to `capri.log`.
  * Nothing fails silently any more: even an unexpected crash inside the AI is reported.
  * **No credit on your ChatGPT key?** The API is paid separately from ChatGPT Plus, and a new key starts
    with $0. Either add credit at platform.openai.com → Billing, or get a **free Google Gemini key** at
    aistudio.google.com and pick "Google Gemini" in her AI list. She tells you this when it happens.
* **Preview of her game affirmations.** In Settings → PC & chat → Game hype, **Preview** makes her say
  a run of lines (kill, headshot, double, death, triple, ace, round won, encouragement, match won) in her
  current personality, and lists them there too.
* Affirmations start a new sentence properly: "Yes! That's how it's done!" (not "Yes! that's...").
* **Linux:** `run.sh` starts her on Linux (see *Linux* below).

## Linux

`./run.sh` sets her up and starts her. It needs Python 3.10+ and PortAudio
(Debian/Ubuntu: `sudo apt install python3-venv libportaudio2`).

* **Works on Linux:**
  * Her figure, animations and hair.
  * The wake word and listening.
  * Her voices: neural voice, ElevenLabs, beeps.
  * Chat and the AI, timers, weather, time and date.
  * Web searches and websites.
  * The settings window.
* **Windows only:**
  * Opening and closing your installed apps and games (she finds them through the Windows Start Menu).
  * Typing.
  * Minimising windows.
  * Discord buttons and keybinds.
  * Media keys.
  * Global hotkeys.
  * Power commands (shut down, restart, sleep, lock).
  * Reading the screen.
  * Game hype.
  * Sitting on windows.
* On Linux those say "I can only do that on Windows" instead of pretending.
* **Wayland:** apps can't place their own windows, so she may not stay in her corner. An X11 session
  works best.
* This hasn't been tried on a real Linux desktop yet. The tests run on Linux, with no real screen,
  speakers or microphone.

## New in 1.29

* **Her hair, copied 1:1 from the picture of her.**
  * The outline is traced straight from the reference picture, including the black spiky crown above her
    face and the black spike down past her shoulder.
  * It's lined up to her face at the same scale.
  * Flat hot pink with crisp white speckles. It sways smoothly around her face and whips when she talks,
    but the shape itself never changes, so it stays sharp.
  * Her own built-in hair is hidden while it's on, so the gaps between strands show what's behind her,
    like in the picture.
* **"Call me ..." is gone.** She doesn't add a name or "good boy" to anything any more, and her AI isn't
  told one. The Settings box is gone too.

## New in 1.28

* **Her hair, redrawn to match the show.**
  * It's a ragged pile of zigzag strands, like torn paper or lightning, instead of the 1.27 spiky ball.
  * Big slabs sweep up to the picture's left, with a couple of long needles going up and zigzags hanging
    down and out beside her face.
  * Flat hot pink with dense white speckles. No glow, no purple outline.
  * It's on her standing figure, lying down, the greeting, visits and teleports, with the same blades at her feet.
  * Her window has more room above her head, so the tall strands aren't cut off.

## New in 1.27

* **New hair, on every figure of her.**
  * A wide, angular, hot-pink blaze with sharp shards breaking out of it: tall ones up top, long ones
    sweeping out to the sides. It has a purple edge, sparkles and a soft glow.
  * Blades come down her shins (green on one leg, pink on the other), with small shards round her feet.
  * It's on her standing figure, lying down, the greeting, her visits and her teleports. The portrait card is a
    close-up of her face and stays as it was.
  * **Smooth:** the hair sways continuously (15 frames a second at rest, 30 while she talks) instead
    of jumping a few times a second. It flares and whips when she talks.
* **Fewer false wake-ups.**
  * Her wake-word listener now also knows everyday words and sound-alikes ("happy", "copy", "carry",
    "sorry"...), so they're no longer forced onto "capri".
  * A "capri" too short to be the word (a click, a blip) is ignored.
  * Every "capri" gets a second listen by the full speech recogniser before she wakes. It has to
    sound like "capri" there too. That match is accent-tolerant: "kapree" or "cap re" still wake her.
* **Pasting an AI key does something now.**
  * As soon as you paste a ChatGPT or Claude key and click away, she saves it, switches to that AI and
    tries it.
  * She either answers through it, or tells you exactly what's wrong (no credit, bad key...).
  * In "Auto" the key boxes are shown too, so a pasted key always has a place.
  * Pasting an ElevenLabs key plays a test line in that voice straight away.
* **Mute / deafen mid-game without tabbing you out.**
  * While you're in a game, she never brings Discord to the front.
  * If you've set Discord keybinds (in Discord: User Settings → Keybinds → Toggle Mute / Toggle Deafen,
    with the same keys in her Settings → PC & chat), she presses those. They work from anywhere.
  * Otherwise she presses Discord's button in the background, without flying over your game. If even
    that can't reach Discord, she tells you to set the keybinds instead of tabbing you out.

## New in 1.26

* **Typing works now, and you can say where.**
  * "Type hi TikTok in Notepad", "write gg into the Discord chat", "in Notepad, type hello".
  * If that app isn't open, she opens it first and talks you through it.
  * "Open Notepad and type hi" types into the Notepad she just opened, not whatever window was in front.
    Before, Windows often kept a newly opened app behind, so her typing went nowhere.
  * Notepad and other classic text boxes: she writes straight into the text box, then checks the text arrived.
  * Other apps (Discord, browsers...): she brings the window to the front, checks it's really there, then types.
  * If it doesn't work, she says why ("Windows wouldn't let me bring it to the front", "it's running as
    administrator") instead of saying "typed it".
  * "Type something" with no app named still types into the window you're on. She never presses Enter.
* **Your AI key isn't silently ignored any more.**
  * Before, if ChatGPT refused (no credit, wrong key), she quietly answered with her built-in chat. So
    adding a key looked like it did nothing.
  * Now she tells you what's wrong, e.g. "My ChatGPT key has no credit. The API is paid separately from
    ChatGPT Plus: add a few dollars at platform.openai.com, under Billing."
  * Settings → Assistant → AI → **Test it** shows the real result: "Working (openai): ..." or the exact problem.
* **What she calls you.**
  * Say "call me good boy" (or anything, or your name), or set **She calls you** in Settings → Assistant.
  * She uses it now and then: "Alright, Notepad is open and your message is typed, good boy."
  * Her AI is told too, so it uses it naturally, especially when praising you.
  * "Stop calling me that" turns it off.
* **"How much RAM are you using?"**
  * She reports her own RAM and CPU, including the helper processes she started.
  * Before, that question gave your whole PC's RAM.
  * For a standalone app, run `build.bat`. You get `dist\Capri\Capri.exe` (and an installer if Inno Setup is
    installed), and Task Manager lists her as Capri instead of Python.

## New in 1.25

* **Several steps in one sentence, and she talks you through them.**
  * "Hey Capri, open Notepad and type hi, TikTok."
    * She says: "Wait a second while I open Notepad and type that in."
    * She opens Notepad, waits for its window to come to the front, and types "hi, TikTok".
    * Then: "Alright, Notepad is open and your message is typed."
  * Works with any of her commands chained with "and", "then", "and then", "after that" or commas.
  * If a step fails, she tells you which steps worked and what went wrong
    ("Notepad is open, but...").
  * "Open Discord and Spotify" still opens both at once, like before.
* **She can type for you.**
  * "Type hello there" / "write down buy milk" types into the window in front.
  * Your capitals and commas are kept.
  * She never presses Enter, so nothing gets sent or run without you.
* **The AI brain can chain actions too.**
  * When ChatGPT, Claude or Ollama is set up, one reply can do up to 4 of her own actions in order,
    with the same step-by-step talk.
  * The AI only ever picks from her own actions (open app, type text...).
    Its text is never run as a command.
* **"Are you a virus?"**
  * "I'm not a virus, I'm open source. You can literally read my code, dummy." (each personality says it her own way)

## New in 1.24

* **She understands a command however you say it.**
  * **Extra words:** "hey capri i'm done for today, shut down my computer", "could you please open up
    discord for me real quick", "the music is too loud, turn it down".
  * **Other words:** pc / laptop / rig, reboot, quit / exit / kill, increase / decrease, capture,
    vc / voice chat...
  * **Another order:** "shut steam down", "discord open it", "give my pc a restart".
  * **Tested on 527 ways of saying her commands** (four sets, the last written fresh to check it
    generalises), and 140 chat sentences that must stay chat. "Open the door", "close your eyes",
    "the time flies", "shut the front door" are never taken as commands.
  * Only filler words are ever left out, so "shut steam down" closes Steam and never shuts down your PC.
  * Something that names an app only counts if it's one of yours.
* **Smoother animations everywhere,** like the greeting:
  * Her standing figure eases from pose to pose (listening, thinking, happy, confused...) instead of
    snapping.
  * Blinks close and open smoothly.
  * Her mouth follows her voice continuously.
  * Happy ^ ^ eyes when something went well, and a wink when she's playful.
  * 60 fps while she talks or moves, back to a light frame rate when she's still, so idle CPU stays low.
  * Idle activities (gaming, watching, the call with D) run at 30 fps.
  * Dashing to a button: a wink as she pokes it, happy eyes on the way back, a blink as she lands.

## New in 1.23

* **A smooth greeting with a real wave.**
  * She glides in smoothly with a short glitch-in shimmer, and her hair flares as she arrives. No more
    bouncy pop-in.
  * She waves properly: her arm bends at the elbow (upper arm out, forearm up), the hand swings side to
    side, then the arm lowers.
  * **Expressions:** glowing happy ^ ^ eyes while she waves, a wink when she's playful, natural blinks,
    and a breath and a gentle sway.
  * When she talks, her grin opens with her voice, smoothed so it doesn't flicker.
  * At the end she hops home in an arc, shrinking into her corner with a faint motion trail. It's drawn
    live, not a frozen picture flying away.
  * It now runs at 60 fps for those few seconds.
* **No more waking up to Discord pings.**
  * After the recogniser hears "Capri", she checks the sound itself.
  * A chime or ping is a few pure tones; a voice spreads over many frequencies. Pings are rejected,
    even with room echo and a noisy mic.
  * Tested on many chime sounds and on loud, quiet, echoey and noisy voices: no mistakes.
  * Rejected sounds are noted in capri.log ("a chime / ping, not a voice").

## New in 1.22

* **Discord leave call / screen share, fixed properly.**
  * Discord's accessibility info isn't ready the first time she asks, so she often found nothing and
    did nothing.
  * She now asks by Discord's exact button names, the same way that finds Mute / Deafen, and keeps
    looking for up to 3 seconds.
  * Most reliable for leaving: in Discord, Settings -> Keybinds -> "Disconnect from Voice Channel".
    Then type the same keys in Capri's Settings -> PC & chat -> Discord call.
* **Mute / deafen lightning hits the button.** She waits for Discord to report where the button is,
  instead of guessing a spot too far left.
* **"Join call" has its own section:** Settings -> PC & chat -> Discord call. Paste the voice channel's
  link (right-click it -> Copy Link). There's also a "Join it now" button to test it.
* **One AI list.** Settings -> Assistant -> AI lists every choice: ChatGPT, Groq, Gemini, OpenRouter,
  DeepSeek, Mistral, xAI, LM Studio, Custom, Claude and Ollama. Only the boxes that choice needs are
  shown, so there's no Ollama model when you pick ChatGPT.
* **ElevenLabs voice.** Settings -> Assistant -> Voice:
  * Paste your ElevenLabs API key, and optionally a voice ID from their Voice Library.
  * She switches to it straight away.
  * If ElevenLabs fails (bad key, out of credit), she uses her normal voice and Settings says why.
  * Only the text of what she says is sent.
* **Beeps instead of words:** Voice -> "Beeps - retro" or "Beeps - cute". Chiptune blips like old
  handheld RPG text boxes. Her mouth still moves with them.
* **Game hype in any game.**
  * "Any game: watch my screen for kills": while a game is in front she reads the middle of the
    screen, on this PC, for "ELIMINATED", "HEADSHOT", "DOUBLE KILL", "VICTORY", "KILLED BY"... and
    cheers.
  * "Encourage me now and then": "you're doing great" every 6-12 minutes while you play.
  * Lines are put together from parts, so they almost never repeat.
  * A game in exclusive full screen can look black to screenshots. If she never reacts, set the game
    to borderless.
* **Much better hearing** for accents, bad mics and slurred words:
  * **Mic clean-up** (on by default, Settings -> Wake word): quiet or far-away mics are turned up to a
    steady level, desk rumble is cut, and hiss between words is turned down.
  * **Sounds-like matching:** what didn't come out right is matched by sound against her commands and
    your apps. It ignores what accents and mics change (most vowels, v/w, l/r, b/p, d/t...).
    "shot down my computa" -> shut down my computer, "lee call" -> leave call, "opun discort" -> open
    Discord. Normal chat is left alone.
  * **Whisper** installs with one button now. There's a new "distil-small" model (best for accents,
    quicker), and it retries unclear words.

## New in 1.21

* **Commands work again with "better hearing" (Whisper) on.**
  * Whisper writes punctuation ("Shut down my computer."), and the full stop broke almost every command:
    that came out as "close an app called computer.".
  * Punctuation, capitals, curly apostrophes and "a.m." are now ignored.
  * Every command is tested with and without them.
* **Any AI, including ChatGPT.** Settings -> Assistant -> AI -> "ChatGPT or any other AI":
  * Pick a service: ChatGPT, Groq, OpenRouter, Google Gemini, DeepSeek, Mistral, xAI, LM Studio, or any
    other address that works like ChatGPT's.
  * Paste your API key. For ChatGPT, get one at platform.openai.com.
  * The ChatGPT default model is **gpt-5-nano**, OpenAI's cheapest, so your credit lasts longest. You can
    type any other model.
  * "Auto" now picks an AI you've added a key for before Ollama.
  * "Set up your brain" checks the AI you picked and tells you exactly what's missing.
* **She doesn't question you.**
  * When you say something odd she reacts or says she didn't catch it. No more "why?" or "how come?".
  * Her AI is told the same. Misheard words get her best guess, not "what do you mean?".
* **Game hype:** "Nice kill!", "Headshot!", "Triple kill!", "ACE!", "GG!".
  * Turn it on in Settings -> PC & chat -> Game hype, or say "turn on game hype".
  * Works in Counter-Strike 2, Dota 2 and League of Legends: the games that report kills, through their
    official interfaces on your PC.
  * For CS2 / Dota 2 she adds a small config file to the game's folder. Restart the game once.
  * Optional: a line when you die.
  * Valorant, Fortnite and Apex don't share kills, so she can't cheer for those.
* **Discord:**
  * **"Join call":** paste your voice channel's link in Settings -> PC & chat -> Your call (right-click
    the channel -> Copy Link). She opens it and presses Join Voice.
  * Stream / stop streaming / leave call now find Discord's buttons much more loosely: any case, any
    kind of control, with retries.
  * If a button still can't be found, the names of the buttons she *did* see go into capri.log, so the
    exact problem can be fixed.
* **Teach her buttons by pointing.** Put your mouse on a button and say, for example, "this red button
  makes me leave call".
  * From then on, "leave call" presses that button. What you teach her wins over her built-in version.
  * Other ways to say it: "when I say next episode, click this button", "learn this button as skip intro".
  * "Forget the leave call button" undoes it.
  * Skills are saved as data: the app, the button's name and where it is. They're never new code, so
    nothing she learns can run commands.
* **Tsundere says "hmph"** (like "humf"), not "H-M-P-H". "Tch" isn't spelled out either.
* **Calmer voice styles.** Holocall, Netrunner, Glitch, Android and Cyberspace are now a light flavour
  over her voice instead of a heavy filter. Glitch hiccups about once a second instead of breaking up.

## New in 1.20

* **Her voice goes up and down.** No more one steady tone:
  * Stressed words go up and quiet ones settle down, with gentle rises and falls in between.
  * A sentence drifts down at the end, and a question rises at the end.
  * Settings -> Assistant -> **Expression** sets how much (left = steady).
  * By voice: "be more expressive" / "be less expressive".
  * Each personality moves differently: deadpan barely, hype and silly a lot.
* **The music app setting sticks.** Picking an app in "Play music on" now takes effect straight away.
  * Before, the Assistant tab only saved when you pressed its Save button.
  * Closing Settings now saves the tabs you changed too.
  * Settings shows what you changed by voice (personality, music app, voice style...) so it can't undo it.
* **She plays the song, on every music app**, not just its search:
  * **YouTube Music:** she finds the song and opens it, and it starts playing.
  * **Deezer, Apple Music, Bandcamp:** she finds the song's page and presses its Play button.
  * **SoundCloud, Tidal, Amazon Music:** she opens their search and presses Play on the first result.
  * **YouTube:** "play X on YouTube" opens the video itself.
  * If she can't find the Play button, she tells you so.
* **A chatbot with real answers** (when there's no AI set up):
  * Sounds that aren't words ("ngnge") get "Sorry, I didn't catch that", not "Why's that?".
  * "What is a black hole" / "who was Napoleon" / "tell me about Minecraft": a short answer from Wikipedia.
  * Questions she can't answer: she offers to look them up. Say yes and she searches. Say something else
    and she does that instead.
  * She reacts to what you said: games, food, school, work, pets...
  * Bad news gets sympathy and good news gets a cheer ("I won my match!").
  * "What should I eat / play / watch", "who made you", "are you there", "flip a coin", "roll a dice" all
    get proper answers.
  * For real ChatGPT-style conversation, set up her AI brain ("set up your brain"): free local AI with
    Ollama, or Claude with an API key.
* **Discord calls:**
  * "Stream my screen" / "share my screen" / "go live": Share Your Screen, then your screen, then Go Live.
  * "Stop streaming".
  * "Leave call" / "hang up": the Disconnect button in the voice panel, never one in Discord's settings.
  * She checks Discord afterwards and says what really happened.
* **Fixes from a full sweep:**
  * "Stop talking" / "shut up" / "be quiet" stop her mid-sentence. Before, "stop talking" tried to close
    an app called "talking", and "be quiet" changed her personality.
  * "Show my desktop" clears your screen again (it was being heard as "stream my screen").
  * "Turn it down a bit", "too loud" and "turn the sound up a little" change the volume.
  * "Search YouTube for cat videos" searches YouTube.
  * "What's your name" is answered, not searched.
* **New:**
  * Timers, reminders and alarms: "set a timer for 5 minutes", "remind me in 10 minutes to check the
    oven", "wake me up at 7am", "how long is left", "cancel my timer". They last while Capri is running.
  * Her voice by voice: "talk faster / slower", "speak up", "talk quieter", "higher / lower voice",
    "change your voice" (the next voice style).
  * "Sit on my window" / "get off the window".

## New in 1.19.3

* **Her voice and her words line up.** Before, the text popped up and her voice came a while later.
  * Her words now appear in her panel and the chat at the moment she starts saying them. Her
    questions work the same way.
  * If her voice ever fails, the text still shows within a few seconds.
  * She starts talking sooner: the first bit she says is kept short (one sentence, or up to a
    comma), because the voice engine makes short audio much faster.
  * No more pauses between sentences: the next one is made while she's saying this one.

## New in 1.19.2

* **"Preem" is one smooth syllable**, like the end of "supreme". It was coming out as "pree-um".

## New in 1.19.1

* **She does what you ask, however you say it.**
  * "Pull up Spotify", "bring up Discord", "pull Spotify up" and "get Steam going" all open the app.
  * So do "throw on Spotify", "hop on Discord", "take me to YouTube", "I need Opera", or just "Spotify".
  * "Get rid of Discord" closes it, "put some music on" plays music, and "listen to lofi" plays lofi.
  * She only acts when the name really is one of your apps, games, sites or folders. "Go to bed" and
    "I need a break" are still chat.
  * Her AI is told that casual wording like this is a real request: it opens the app instead of asking why.
* **Every personality sounds different.**
  * Each one has its own pitch, speed and voice colour: sarcastic is lower and warmer, silly is high
    and bouncy, tsundere is sharp, sweet and kuudere are soft and quieter, deadpan is flat, gremlin is
    raspy and hype is punchy.
  * Picking a personality in Settings makes her say its line straight away, in its voice.
  * Test voice uses her current personality's voice and line.
* **The Glitch voice really glitches.** Several times a second something breaks:
  * a repeated stutter ("b-b-b-");
  * a pitch jump;
  * a crushed, low-quality burst;
  * a reversed blip;
  * a cut-out;
  * a burst of digital buzz;
  * a skip back.

## New in 1.19

* **The call look.**
  * The chat window is always a Night City call now, like your picture: a name above a square
    call icon, and the line beside it on a dark glass plate like her message panel. There are
    TV lines across it all, and "..." while she's thinking.
  * The five skins (Holocall, Netrunner, Arasaka, Neon, Braindance) recolour it.
  * The call cards above her panel (Panel → Activity log style → Call cards) use the same look:
    what she understood you said on the right, her replies on the left, in your chat skin's
    colours. They fade out after 14 s.
* **Highlight any word.** She first asks the app for its own text (web pages, Word, Notepad, most
  text boxes): any word or phrase, found exactly, scrolled to and selected by the app itself.
  Anywhere else she reads the screen, which is now sharper: bigger, higher contrast, dark mode
  flipped, and common misreads fixed ("dead1ine" → "deadline").
* **Personalities, revamped.**
  * Each one has its own words for what you do most: opening, closing, playing, searching,
    clicking, screenshots, tabs. For example, Tsundere: "F-fine, I'm opening Discord. Not
    because you asked nicely or anything."
  * Three new ones: **Gremlin** (chaotic), **Hype** (your hype-man) and **Kuudere** (cool and
    quiet, softly caring).
* **Better hearing for accents (optional):** run **setup_hearing.bat** once, then Settings →
  Wake word → Hearing → **Whisper** → Apply.
  * Vosk still catches "Hey Capri", but what you say after it is re-heard by Whisper, which was
    trained on a huge range of accents.
  * It's nudged towards her words and your app names. It runs on your PC, and its model
    (~150 MB, or ~480 MB for "small") downloads the first time.
  * If it can't install on your Python version, she keeps her normal hearing.
* **She adapts to you:**
  * She ignores polite wrapping: "could you please open Discord for me", "I want you to...",
    "do me a favour and...", "would you mind playing...".
  * Your own shortcuts: "when I say gaming time, open Steam and Discord". Say "gaming time" and
    she does it ("... and then ..." runs commands one after another). "Forget the shortcut
    gaming time" removes it.
  * She learns from you: if she didn't get something and you then say it another way that works,
    she asks "Want me to remember that X means Y?"
* **Voice styles you can actually hear:** Capri, Natural, **Holocall** (phone line + static),
  Netrunner (digital double), Glitch, **Android** (robot ring) and **Cyberspace** (echo). Picking
  one takes effect straight away, and she says a line in it.
* **No more "Waiting for the wake word" while she's talking.** The panel waits until she's
  actually finished, including while her voice is still being made. Long replies start sooner:
  she says them a sentence at a time.
* **More music apps:** YouTube Music, SoundCloud, YouTube, Apple Music, Deezer, Tidal, Amazon
  Music and Bandcamp, alongside Spotify.
  * "Play let you down by NF on SoundCloud" / "play lofi on YT Music" for one song.
  * Or make one your default: Settings → Assistant → Music → *Play music on*, or say "use
    SoundCloud for music". Then "play ..." goes there.
  * Spotify plays the song itself. The others have no way for her to start a song, so she opens
    their own search for it in your browser, and you say "click" and the song (or "play the
    video").
  * Pause / next / volume work for all of them (media keys). Games you own still launch with
    "play deadlock".
* **Removed:** the "TV static on the panel" option (her panel lost its static earlier).

## New in 1.18

* **She can think: "set up your brain" / "is your AI working?"** Her AI (Ollama) only works when it's
  installed, running and its model is downloaded. If any one is missing, she drops to her offline
  chat. Now she finds which one and fixes it:
  * Not running: she starts Ollama herself. She also does this when Capri starts.
  * Model missing: she asks, then downloads it (about 2 GB), with the progress on her panel.
  * Not installed: she asks, then opens setup_ai.bat, which installs Ollama and the model.

  With a Claude key in Settings she thinks online instead. Only fixed, known steps run - never
  anything an AI wrote. When her brain is off, her offline chat tells you to say "set up your brain".
* **Hands on your screen:**
  * "highlight the word deadline" / "select the text due Friday": she finds the words on screen,
    zaps them and drags across to highlight them.
  * "copy the word ..." highlights it and copies it.
  * "double click ...", "right click ...", "scroll down" / "scroll up a bit" / "scroll down a lot".
  * Fixed key presses into the window you're using: "select all", "copy that", "paste it",
    "undo", "redo", "save it", "refresh the page", "back a page", "next page", "zoom in",
    "zoom out", "new tab", "close this tab", "reopen that tab", "next tab", "previous tab".
* **Clicking what you meant:** "click one thousand minus seven" finds your "1000-7" playlist, and
  "click dot mp three" finds ".mp3". She tries number words as digits, "minus" / "dash" / "dot"
  as symbols, spelled-out letters joined up, and the name without spaces or symbols. A single
  word like "seven" never clicks "1000-7".
* **Tabs switch, no more right-click menu:**
  * A browser tab is now switched by selecting it, or with a real left click - never with the
    action that opened its menu.
  * Playlists and other list items get a real left click.
  * Every click she makes respects Windows' "switch primary and secondary buttons" setting, so
    a left click never comes out as a right click.
* **"Repeat what I said"** says back what you just said. "Say that again" repeats her last line,
  and "repeat after me ..." makes her say anything.
* **Move her by voice:** "go to the bottom left", "move to the top right", "go to the left",
  "go to the middle", "go to my other monitor", "go home". In drone mode the drone flies there.
* **Stutters are sounded out.** "W-what?!" is said "wuh... what?!", with a tiny pause, instead of
  a letter or a skipped dash.
* **Energetic voice:** every personality talks a little quicker and brighter, and her AI is
  told to sound lively.
* **The chat window is a Night City call:** a header with her face and her real current state,
  bubbles in her colours, and five skins from the header (saved): **Holocall**, **Netrunner**
  (a green terminal), **Arasaka**, **Neon**, **Braindance**.

## New in 1.17

* **She always has a reply.** Capri has her own built-in chatbot now. When there's no AI set up
  (or Ollama is off, or the AI errors), she still answers instead of "Not sure what you mean":
  * small talk, and how you're feeling ("I'm stressed", "I'm hyped")
  * things you tell her, while she's running ("my name is Sam", "I like Deadlock", "what's my name?")
  * questions about her (favourite colour, "do you like cats", "are you real")
  * simple maths ("what's 12 times 8")
  * honest answers about what she can and can't do ("can you open Steam?" tells you how to say it)

  It runs on your PC and sends nothing anywhere. It isn't an AI, so it can't look things up:
  when it doesn't know, it says so and suggests the AI chat. With Ollama or Claude set up, chat
  still goes there.
* **Personalities:** Edgerunner (her normal self), **Sarcastic**, **Silly**, **Tsundere**,
  **Sweet** and **Deadpan**.
  * Pick one in right-click → Capri → Personality, or Settings → Assistant.
  * Or just say it: "be sarcastic", "change your personality to tsundere", "go back to normal",
    "what's your personality".
  * It changes her chat, her AI's style, and now and then a remark after a command ("Done.
    I-it's not like I did it for you!").
  * It never changes what a command does, her safety questions or her error messages.
* **Shutting down:** she now asks "Look up there, think we can make it?" Say yes to shut down.
* **Ask about your PC:** "what's using up all my RAM?", "how am I using 10 GB of RAM right now?",
  "why is my CPU so high?", "how much storage do I have left?", "how long has my PC been on?",
  "what's my battery?", "why is my computer so slow?"
  * She reads it live and groups apps by program (all of Opera's processes count as one), like
    Task Manager.
  * Example: "You're using 10.2 of 15.9 GB of RAM, 64 percent. The biggest: Opera GX 3.1 GB,
    Deadlock 2.2 GB, Discord 900 MB."
  * The AI can use it too.
* **"Take a screenshot"** captures every monitor. **"Screenshot this window"** captures just the
  window you're using.
  * It's saved in **Pictures\Screenshots** and copied to your clipboard.
  * She steps out of the picture while it's taken, then the screen flashes like a camera.
* **"Preem"** is now said "pr-eeee-mm": a long "ee", drawn out. Windows voices slow down for just
  that word; other voices read it as "preeem".
* **Search mode** shows her message panel in inverted colours while it's on.
* **Picking a design switches straight to it.** Choosing Portrait (or Classic, or a Look) while she's
  lying on the panel gets her up by itself, with no need to turn "Lie on the panel" off first.

## New in 1.16.2

* **Lying down, no gap in her hair:** the gap between the hair and her own hair (bottom left)
  is filled with hair. The thin hanging strands that made it are gone there.

## New in 1.16.1

* **Sitting on windows, redone from your new picture.**
  * Her perched pose is now the one from the picture of her on the window's title bar, at full
    resolution with smooth edges and clean flat colours.
  * **Both legs swing**, out of step: the black one from its knee and the red one from its knee.
    The parts each leg hid are painted in, so nothing comes apart or shows a gap.
  * **She keeps up when you drag the window.** While she sits, she checks the window's position
    every frame instead of five times a second.
  * **Turning the option on sends her straight onto your window**, and so does starting Capri
    with it on. No more waiting.
* **Lying down:** her hair flows straight into her. No blue-purple line where it meets her face
  and shoulder.
* **Look: Hair Storm is removed.** If you had it picked, she goes back to her full body.

## New in 1.16

* **Sit on windows** (right-click → Capri → *Sit on windows*, or Settings → Character).
  * She hops onto the window you're using and sits on its top edge, swinging her leg.
  * She follows the window if you move it, and hops to another window once you've used it
    for a moment.
  * The message panel stays home in its corner.
  * Close, minimise or maximise that window and she teleports back onto the panel, with a
    red flash.
  * Drag her off a window and she stays where you drop her (she won't jump straight back on).
  * "Get up" / "stand up" also brings her home.
  * Off by default. Full-screen apps and games are never sat on.
  * Her sitting pose is made from your picture. The leg is its own layer, filled in behind
    the hair strand, so it never comes apart or shows a gap as it swings.
* **Activity log as call cards (optional):** right-click → Panel → *Activity log style* →
  *Call cards above the panel*.
  * "Heard", "Launch" and so on show as Night City call cards stacked above the panel, and
    each fades out after ~14 s.
  * The default stays the classic look: the lines under her message, inside the panel.
* **Settings is a cyberdeck:** black chassis, crimson trim and numbered slots ("01 // APPS").
  * The header chips show your real settings: voice, mic, spoken replies, chatbot, apps.
* **Right-click menu in folders:**
  * **Voice**
  * **Capri**: Design (every style and look), Lie on the panel, Sit on windows, Compact,
    Do something
  * **Panel**
  * **Drone**: now, in games, Look
  * **Window**: always on top, click-through, reset
* **"Switch tabs on Opera"** (or Chrome / Edge / Firefox / Brave / Vivaldi).
  * She reads your tab names and asks which one: *"Which tab? I see Gmail, Twitch and YouTube."*
  * Answer like *"the twitch one"*, *"youtube"* or *"the second one"*. She zaps it and the
    browser comes to the front.
  * *"Switch to the twitch tab"* goes straight there.
* **"Play the video" / "pause the video"** (also "resume the stream", "stop the video").
  * She finds the player's own Play / Pause button (YouTube, Twitch...) in the window you're
    on and zaps it.
  * If it's already playing, she says so.
  * If she can't see a player button, she presses the play/pause media key and tells you she
    did.
* **Drone:**
  * The mask drone is smoother (60 fps, pre-scaled art).
  * Where the fin sways from its base, plain green now shows instead of a see-through gap.
  * Drag the drone anywhere; it stays there. (The corner options are gone.)
* **Looks:**
  * The panel sits right above the Glitch and Grin cards.
  * Hair Storm's white patches are gone and its hair moves more smoothly.
  * The "spikes" hair style and the wild-hair slider are gone (always full storm).

## New in 1.15

* **New looks, animated.** Settings → Character → Style now has **Look: Stare**, **Look:
  Glitch**, **Look: Grin** and **Look: Hair Storm**, made from your pictures of her. Each
  one comes alive:
  * her red hair sways (more when she talks) and sparkles
  * she breathes and bobs, and bounces with her voice
  * her eyes blink (found by their blue irises)
  * **Grin's** teeth open and close as she talks
  * now and then the picture glitches: red/cyan split and torn slices

  Hair Storm stands free (its white background is cut out). The close-ups sit in a neon
  card. See `docs/v115_looks.png`.
* **Add your own:** drop pictures of her (png / webp / jpg) into the **`looks`** folder
  next to `run.bat` and restart. Each becomes "Look: <file name>" and gets the same
  animation automatically.
* **Mask drone:** Settings → Character → *Drone look* (or menu → *Drone look*) → **Mask**.
  In game mode she becomes her green visor:
  * her eyes look around and blink
  * the fin on top wiggles
  * the zigzag mouth opens as she talks
  * it glows green with her voice

  The shard disk is still the default.
* **Cost:** a few ms a frame at 15 fps, only while she's shown. "Idle animation" off stops
  it.

## New in 1.14

* **Fix what she mishears.** When she keeps hearing a word wrong ("discord" → "to school"),
  teach her:
  * **Settings → Wake word → *Fix what she mishears*:** put what she hears on the left
    ("to school") and what you meant on the right ("discord"). From then on she reads it
    that way, before working out the command, so "open to school" opens Discord.
  * **"Fix what she just heard"** fills in the last thing she heard (shown next to the
    button), so you only type what you meant.
  * **Or just tell her:** "when I say to school I mean discord" (also "if you hear ... it
    means ..."). Saying it again with something else replaces the old fix.
  * Whole words only: "to school" won't touch "to schoolbag". The longest fix wins, and
    your fixes come before her built-in ones.
  * Fixes are saved with your settings. Remove one in the table.

  See `docs/v114_fix_mishearings.png`.

## New in 1.13

* **She's a chatbot that also takes commands.** Talk to her about anything: your day,
  games, music, questions, jokes. Commands ("open discord", "mute me", "play ... by ...")
  work exactly as before, in the middle of a chat too.
  * Chat is **on by default**: Settings → Assistant → AI, *Auto*. She uses **Ollama** on
    your PC if it's running (free, private, nothing leaves your PC). Otherwise she uses
    **Claude** if you've given her an API key. With neither, she falls back to her
    built-in small talk instead of failing.
  * **`setup_ai.bat`** sets up the free local AI: it installs Ollama with winget and
    downloads the `llama3.2` model (about 2 GB). Ollama frees that model's RAM 3 minutes
    after you stop chatting.
  * After she replies, she keeps listening for your answer without "Hey Capri", for up
    to 12 turns. A silence ends the chat. Typing still never counts as talking to her.
  * The AI can click things on screen for you too (see below).
* **"Click that button".** She looks at your screen when you ask, and only then. Nothing
  is recorded or sent anywhere.
  * **"click subscribe"**, **"click the next button"**, **"press the skip button"**,
    **"click on the downloads tab"**:
    * she finds it by name among the buttons, links, tabs and menu items of the window
      you're using (the same accessibility info screen readers use)
    * if the app doesn't name its buttons (games, some launchers), she reads the window
      with Windows' built-in text recognition and finds the words on screen
  * **"click that"** / **"click it"** / **"click here"**: whatever you're pointing at with
    the mouse.
  * **She zaps it from where she lies.** Lying on the panel, she fires red lightning from
    her hand straight at it (no dashing about), and it's clicked as the bolt lands. It
    works on your other monitor too. See `docs/v113_click_zap.png`.
  * It uses the button's own "press" where it can, so your mouse doesn't move. Otherwise
    it's a quick click, and your pointer goes straight back.
  * **Risky buttons are asked about first:** delete, uninstall, buy, pay, send, submit,
    sign out... "Click 'Delete account'? Say yes or no."
* **Chatterbox is gone completely.**
  * Its code, scripts, voice clip and settings are all removed.
  * The next time you start Capri with `run.bat`, it uninstalls PyTorch and the other
    packages only Chatterbox used, and deletes its downloaded model. That frees several
    GB of disk space.
  * She's back to her Kokoro voice.

## New in 1.12.1

* **Drone mode whenever you're in a game**, including games you start yourself. Every
  few seconds she looks at the window in front (a cheap check). It counts as a game if:
  * it runs from a game library (Steam, Epic, Riot, Xbox, GOG, EA, Ubisoft, Rockstar...)
  * Windows reports a full-screen Direct3D game
  * it's a borderless full-screen window that isn't a browser, video player, Office,
    Discord, an editor...

  She stays a drone until that game closes, even when you alt-tab. Say "normal mode"
  mid-game and she leaves that game alone. Menu → *Drone mode when I'm in a game* turns
  it off.
* **Less RAM:**
  * Her pre-drawn images are dropped while she's a drone.
  * Every 10 minutes, and when a game starts, she gives idle memory back to Windows.
  * If you downloaded the bigger speech model (`vosk-model-en-us-0.22-lgraph`), that alone
    uses about 1 GB. Deleting its folder in `models\` goes back to the small one, which
    uses about 100–200 MB.

## New in 1.11.4

* **Typing isn't talking.** After she speaks, asks you something, or is in search mode,
  she listens for a while without needing "Hey Capri". During that time the mic can pick
  up your keyboard, and the recogniser turns the clatter into "words". In search mode,
  each one became a Google search in your default browser, so it kept jumping to the
  front while you typed.
  * While she listens like that, she now notices if you're typing. Input with the mouse
    standing still means typing; just moving the mouse doesn't count. She never sees
    which keys you press.
  * Anything she "hears" then is ignored, and search mode switches itself off ("You're
    typing - search mode off.").
  * Search mode also skips junk like "the", "uh" or single letters.
  * "Hey Capri ..." always works, typing or not.
* While she lies on the panel, she's only raised above it when it actually moves, not on
  every status update.

## New in 1.11.3

* **"Go into drone mode" works.**
  * Only "drone mode" / "go drone mode" / "switch to drone mode" used to be understood.
    Now "go into / go in to / get into / switch to / enter / activate drone mode" (and
    "game mode") all work.
  * "Drone mode" misheard as **drive / droid / drawn / throne mode** is corrected. That
    only happens before "mode", so "drive to the shop" isn't touched.
  * "Exit / leave / get out of drone mode" turns it off.
* **The AI doesn't guess actions any more.** Unrecognised phrases go to the AI, which
  had turned "drive mode" into "minimise every window". It's now told that speech
  recognition mishears, so it asks what you meant instead of guessing an action. It
  also knows about drone mode now.

## New in 1.11.2

* **"Play ___ by ___" by voice now does exactly what Test Spotify does.**
  * She finds the exact track (with Spotify's own search when you're connected), opens it
    in the Spotify app on this PC, and checks it's really playing.
  * Before, with Premium connected, voice commands used Spotify's remote-play API
    instead. That can start the song on another device (or nowhere) while reporting
    success.
* **Dashes go to your other monitor.** For Discord's Mute / Deafen, minimise and
  Explorer, she now lands on the monitor the target is on.
  * Before, her spot was clamped to her own screen, so she stopped at its edge.
  * The dash is drawn on every monitor it crosses, one window per monitor, so each
    uses its own scaling. See `docs/v1112_second_monitor.png`.
* **Minimise: she flies up to the button.** She hovers right beside the window's
  minimise button and zaps it from there, even on a maximised window, instead of
  firing from the bottom of the screen.

## New in 1.11 (1.11.1)

* **Full body when she's standing.** The body style now shows her whole figure from the
  character sheet: legs, claws and the hair storm. It's about 250 px tall (140 px in
  compact mode).
  * It's drawn from the sheet's high-resolution art, scaled down once, so it stays sharp.
  * She blinks, her mouth moves when she talks, her hair flares with her voice, she leans
    in when listening, and she throws an arm out when she's happy.
  * See `docs/v111_full_body.png`.
* **The panel stays on her.**
  * It sits right on top of her hair, not on her window's empty margin.
  * If her window is ever hidden while the panel is up, she's put back (or her drone,
    in game mode).
  * If drawing her ever fails, she's drawn plainly instead of disappearing, and the
    error goes in the log.
* **Drone position.** Game mode's disk now parks in the very **bottom-right** corner by
  default.
  * Say "move the drone to the left" / "drone right", or use the menu → *Drone position*:
    bottom left, bottom right, or where Capri stands.
  * Her messages pop up just above it.
  * See `docs/v111_drone_corners.png`.
* **Idle activities while lying down:** she glitches, plays her holo game in front of
  her face, watches a screen floating over her back, and calls D. See
  `docs/v111_idle_lying.png`.
* **Video calls with D.** The call is now a holo video feed showing D from his picture
  (`assets/d/d.png`, his head and shoulders). He's animated from that one picture:
  * he talks: his mouth moves with his voice bars, and his head nods and tilts, with the
    odd shake
  * while she talks, he listens: a slow head tilt, nodding along, a glance aside
  * he breathes and blinks
  * Capri hears him through her implant (her ear glows blue) and her mouth moves on her
    turn

  To use another picture of him, replace `assets/d/d.png`; it needs to be drawn facing
  you, head at the top. See `docs/v111_d_call.png` and `docs/v111_d_animated.png`.
* **Dashes while lying down.** For minimise, "go into downloads" and Discord, she gets
  up off the panel, dashes over, zaps it, comes back and lies down again. The panel
  stays where it is.
* **"Unmute me" / "deafen me": she dashes right up to the button.**
  * She lands beside Discord's Mute / Deafen button and fires a short bolt into it,
    which presses it.
  * If the button can't be seen, she goes to Discord's bottom-left corner (where those
    buttons are), or its taskbar icon.
  * **A real bug fixed:** with a second monitor, the button's position was converted
    wrongly, so the lightning missed. Windows reports positions in physical pixels, and
    Qt keeps each screen's top-left corner unscaled, but Capri was scaling it. See
    `docs/v111_discord_dash.png`.
* **Spotify: she presses Play herself.** If opening the song doesn't start it, and
  Windows can't see Spotify's Play button, she looks for it on screen.
  * She screenshots Spotify's window and finds the big green round button with the
    black triangle in the middle (not the green heart, not album art). She clicks it,
    puts your mouse back, and returns you to the window you were in.
  * Spotify Free playing an ad first now counts as playing.
  * Every step is in the **Test Spotify** report.

## New in 1.10

* **Search mode, fixed.** "Hey Capri, switch to search mode" (or "go into
  search mode") turns it on:
  * She now waits **15 seconds** for you to start talking (it was 6, which is
    why it seemed to drop out).
  * If you pause, she asks "Still there?" once before turning it off.
  * The panel shows **[SEARCH MODE]** the whole time, so you can see it's on.
* **"Go into downloads"** (or "go into my download folder", documents,
  pictures...): she opens File Explorer, dashes over to it with red lag
  lightning, and zaps **Downloads** in its sidebar, which opens it. If the
  sidebar entry can't be found, the folder just opens normally.
* **"Minimise Discord"** (or any app): she dashes over, lands on the window's
  top edge, and zaps its **minimise** button. The window minimises when the
  bolt hits, then she dashes home. See `docs/v110_minimise_visit.png`.
* **Chat window:** right-click → *Chat with Capri...*, or say "open chat".
  * Type anything you'd say: commands, answers to her questions, searches
    while in search mode, or just chat.
  * Everything she says appears there too.
  * The history stays in memory only and isn't saved.
* **The panel is a cyberpunk message now, with no static:**
  * a dark red-to-black card with fine scanlines
  * a red frame, a cyan underline and corner brackets
  * a "CAPRI // MESSAGE" header

  See `docs/v110_message_panel.png`.
* **Game mode: she becomes a little flying disk.** When she launches a Steam
  game, she turns into a broken ring of her red / green / black shards
  spinning around her eye:
  * The eye blinks and looks around, sparks jump off it, and it glows when she
    talks.
  * The panel only pops up when she has something to say.
  * She turns back once the game's own processes have closed (checked every
    5 s).
  * You can also say "drone mode" / "normal mode", or use the menu.
  * Turn it off with menu → *Drone mode (games)*. See `docs/v110_drone.png`.
* **Idle activities.** Every minute or so, while you leave her alone, she
  does something:
  * **glitches:** red/cyan split, torn slices, a jolt
  * **plays a game:** a holo handheld with a tiny pixel runner, ending in a
    "HIGH SCORE!" cheer
  * **watches something:** a holo screen of night-city scenes whose light
    flickers over her
  * **is on a call with D:** hand at her ear, a call card with a running
    timer, and voice bars as they take turns

  D's avatar is a generic yellow-jacket silhouette, not show art. She stops
  the moment you talk to her. Trigger one yourself with menu → *Do
  something*, or turn them off in Settings → Character → *Idle activities*.
  See `docs/v111_idle_activities.png`.

## New in 1.9

* **Searching only happens in search mode.** "Search cats" / "google ..." /
  "look up ..." outside search mode doesn't open anything. It switches search
  mode on and asks what to search. (The AI can't search behind your back
  either.)
* **Weather is just the facts:** "Manchester today: 14° now and light rain.
  High 15°, low 9°, 80% chance of rain." No advice, and the chance of rain is
  always included.
* **No wave** on the greeting.
* **No teleport.** Instead, mute / unmute / deafen / undeafen **zap Discord's
  actual button with red lag lightning**:
  * She finds the button on screen, a bolt hits it with a shock ring, and the
    button is pressed on impact.
  * If Discord is minimised, she aims at its window or its taskbar icon
    instead.
  * Closing apps still blasts their window.
* **Shutdown cyberpsychosis.** After you say yes to "shut down my PC", every
  screen glitches out for about 3.5 s:
  * torn slices, red/cyan split and static
  * then shaking, red heartbeat pulses, inverted flickers and warnings
    ("CYBERPSYCHOSIS DETECTED", "NEURAL LINK UNSTABLE", "SANDEVISTAN
    OVERLOAD"...)
  * then FLATLINE and an old-TV collapse to black, with a glitch / flatline
    sound

  Then the PC really shuts down. It's drawn on a snapshot of your screen, so
  nothing is touched until the shutdown. If Windows refuses, your screen comes
  back and she says so. See `docs/v19_cyberpsychosis_preview.png`.
* **She understands you better.**
  * She uses the recogniser's runner-up guesses. It returns its top 4 guesses
    for what you said; if the best one isn't a command but a runner-up is
    ("oh pen this cord" vs "open discord"), she goes with the command. Yes/no
    answers work the same way.
  * Common mishearings are fixed before anything else looks at them: "spot a
    fly" → Spotify, "this cord" → Discord, "you tube", "p c", "dead lock",
    "row blocks" → Roblox, "the whether" → the weather...
  * **Optional, more accurate speech model:** Settings → Wake word →
    *Download the more accurate speech model* (128 MB, Vosk's
    `en-us-0.22-lgraph`), then restart Capri. It gets noticeably more words
    right but uses more memory, so it's your choice. From a terminal:
    `.venv\Scripts\python tools\download_model.py --better`.
* **Spotify, fixed further.**
  * **A real bug:** to check a song was playing she read Spotify's window
    title, but Spotify has hidden helper windows with titles ("Default IME",
    "MSCTFIME UI"). She could read one of those instead of the main window, so
    she couldn't tell whether the song was playing. She now only reads
    Spotify's real main window.
  * **Finding the song** now uses proper music catalogs first. iTunes' public
    song search (free, no key) picks the exact song and artist, then song.link
    gives its Spotify track. Deezer is the backup, then web search (Bing's
    links are now read properly too).
  * **Starting it:** if opening the track doesn't start it, she presses the big
    Play button on the track's own page. She never uses the media Play key,
    which would resume the old song.
  * **Settings → Assistant → Test Spotify** plays a song and shows every step:
    where the track was found, what Spotify's title said, and whether the Play
    button was found. A **Copy** button lets you send it to me if it still
    misbehaves.

## New in 1.8

* **Spotify, done properly: "play ___ by ___" plays that exact song.** No
  Premium or developer account needed.
  1. **Find the exact track.** She uses Spotify's own search if you connected
     Spotify in Settings (any account). Otherwise she does a web search for the
     song's `open.spotify.com/track/...` page: only the song and artist are
     sent, to DuckDuckGo, then Bing. Each result's real name is checked
     (Spotify's public oEmbed), so the actual song beats a piano cover.
  2. **Make sure Spotify is running:** start it and wait for its window.
  3. **Open the track** with Spotify's own link (`spotify:track:<id>`).
  4. **Check it's really playing.** While Spotify plays, its window title is
     "Artist - Song". If the title doesn't change, she presses Play once and
     checks again.

  She only says "Playing NF - Let You Down." when the title shows it.
  Otherwise she says "Opened Let You Down in Spotify. Hit play." With Premium
  and Spotify connected, she plays straight through Spotify's API as before.
  Every step is logged in `capri.log` (lines starting with `spotify:`).
* **Real lightning.** Bolts are built by midpoint displacement, the fractal
  zig-zag of real lightning, with forks branching off. Every frame they're
  redrawn so they crackle and flicker. They have a dim glow, a red body and a
  white-hot core. Behind her dash, short branching arcs crackle between points
  of her trail at head-to-foot height (the teleport was removed in 1.9).
* **No more bending over.** At the taskbar she stands a step beside the app's
  icon, raises her hand at it and zaps it with a red bolt (that's the click).
  Then she dashes home.
* **She blasts apps she closes.** "Close Discord":
  * Sparks gather at her hand.
  * A forked bolt leaps from her to Discord's window.
  * The window flashes red, with arcs crawling over its edges and glitch
    slices, and it closes on impact.
  * Apps that need a yes first are blasted only after you say yes.
  * See `docs/v18_close_zap_preview.png`.
* **Search mode.**
  1. Say "Hey Capri, go into search mode" (or just "search", or "I want to
     search something").
  2. She asks "What do you want to search?"
  3. Answer without the wake word: "funny cats on YouTube", "search best
     Deadlock builds", "nf songs on Opera", or just the words for Google.
  4. She searches, then asks "Anything else to search?"

  Say "that's all" / "stop", or just stay quiet, to leave search mode. It
  also ends by itself after 6 searches.
* **A sharp greeting.** The big hello was blowing up a tiny sprite. It now uses
  her full-size figure from the character sheet, so it's crisp at greeting
  size, and she waves at you with her storm hair flaring as she talks. Her hair
  is also drawn at full sharpness on 125% / 150% scaled displays (see
  `docs/v18_greeting_sharp.png`).

## New in 1.7

The teleport is now a real animation of her whole body, not a picture of her
sliding around (the teleport was removed in 1.9):

* **Her full-body figure from the character sheet, rigged.** The big standing
  Capri is cut into her legs, torso + head, each arm and her face. The arms are
  found from the picture itself, so they come off cleanly at the shoulder.
  Everything above the waist bends; each arm swings from its shoulder.
* **The whole move, smooth at 60 fps:**
  1. She crouches.
  2. She dashes to the icon in an arc, arms swept back, red volts and red lag
     afterimages trailing.
  3. She lands, knees giving.
  4. She **bends down at the waist and reaches her arm out to the icon**. She
     stands on the screen's bottom edge, placed so her claw ends up right over
     the app's taskbar icon.
  5. She pokes it: a red spark jumps from her claw to the icon, with a ripple.
     That's when the real action runs.
  6. She straightens up and dashes home the same way.
* **Crazy hair all the way:** the storm hair boils about twice as fast as
  usual and flares the whole time.
* **Kept light.** Her hair is drawn once per boil step and reused, the
  afterimages are half-resolution, the overlay only covers the area she moves
  through, and only the thin core of each volt is smoothed. A dash frame took
  about 12 ms on this (slow) test machine, so 60 fps leaves room to spare on a
  normal PC. When she isn't teleporting, none of it runs.

## New in 1.6

The taskbar teleport, redone (the teleport was removed in 1.9):

* **She zips to the app's icon on your taskbar as her full body.** It's the
  full-size, full-body her even if you use compact mode or the portrait style.
  She arcs over in about 0.3 s.
* **Red lag volts behind her.** Red lightning, in her own crimson with the
  blue-purple fringe from her hair, crackles along the path she just took at
  head, chest and hip height. It's re-jagged every frame so it flickers, and
  red afterimages of her ("lag") fade out behind her. The same happens on the
  way back.
* **She leans down to click it.** She stands beside the icon on the taskbar's
  edge, bends at the hips toward it with her knees giving a little, and clicks
  (a red ripple on the icon). That click is when the real action happens.
  Then she straightens up and zips home.
* `capri.log` now says which taskbar button she found for each app (lines
  starting with `teleport:`), or that she used the Start button instead.

## New in 1.5

* **A real AI to talk to, for free.** Settings → Assistant → AI now has two
  choices:
  * **On this PC (Ollama)**, the default. It's free and private: nothing
    leaves your PC.
    1. Install Ollama from [ollama.com](https://ollama.com). It runs in the
       background by itself.
    2. Open a terminal and run `ollama pull llama3.2` once (about 2 GB).
    3. Tick **Talk with an AI** and press **Test AI**. If something's missing,
       it tells you exactly what.
  * **Claude**: smarter, but needs your own Anthropic API key and is paid per
    use.
  * Either way she chats like a person and asks things back. "Can you get
    Discord up" also works: the AI picks one of Capri's own commands, which
    goes through the same rules and yes/no questions. It can never run
    anything else.
* **"I'm soo bored" works without AI too.** She ignores emphasis ("soo",
  "really", "kinda", "af", stretched-out words like "boooored") and picks up
  feeling words in any short sentence ("this is boring", "I feel sad").
  Real commands always win.
* **She teleports to your taskbar.** When she opens or closes an app, mutes
  or deafens you on Discord, plays music or searches in a browser:
  * A bolt of lightning strikes where she stands and she vanishes.
  * Another strikes your taskbar and she's standing on that app's icon. She
    "clicks" it (a ripple on the icon); that's when the real action happens.
  * Then she strikes back home.
  * She finds the icon through the same Windows accessibility interface. If
    the app isn't on your taskbar, she lands on the Start button.
  * It takes about 2 seconds, and everything is click-through.
  * Turn it off in Settings → PC & chat.
* **"Play ___ by ___", attempt three.** Spotify ignores its search link in some
  versions, so she now:
  1. Brings Spotify to the front and clicks into its own search box ("What do
     you want to play?"). If she can't find the box, she uses Spotify's
     Ctrl+L.
  2. Types the song and presses Enter.
  3. Presses Play on the best-matching result and checks it's playing.

  What she found and did at each step is written to `capri.log`, lines
  starting with `spotify:`. If it still doesn't play, those lines show where
  it stops.

## New in 1.4

* **Discord mute / deafen press Discord's real buttons.** Keyboard shortcuts
  turned out to be unreliable: Discord can react to the same shortcut twice
  (once as a keybind, once in its window), so "deafen me" clicked on and off
  and "mute me" seemed to do nothing.
  * Capri now finds the **Mute** and **Deafen** buttons in Discord's window
    through Windows UI Automation (the screen-reader interface) and presses
    them exactly once. There's no focus switch and no keys.
  * She also reads the buttons' state, before and after, so what she says is
    true:
    * "Muted you on Discord." or "You're already muted."
    * "Unmuted. You're live." or "Your mic's already on."
    * "I pressed it, but Discord didn't change."
  * "Unmute me" while you're deafened undeafens you, which is what actually
    turns your mic back on.
  * If the buttons can't be found (Discord closed to the tray, or not in
    English), she falls back to the keyboard shortcuts, as before.
* **"Play ___ by ___" plays the song without a Spotify developer account.**
  * If Spotify isn't running, she starts it and waits for it. The search link
    used to be ignored while Spotify was still starting, which is why it only
    opened Spotify.
  * Then she searches and presses **Play** on the result that best matches
    what you said.
  * She checks the player actually switched to "Pause" before saying
    "Playing Let You Down by NF.". Otherwise she says the search is up and
    you can hit play.
  * With Spotify connected in Settings (Premium), she still plays through
    Spotify's API first.

## New in 1.3

* **Unmute works properly.** "Unmute" and "mute" used to be the same toggle;
  now she knows which one you asked for:
  * "Unmute me" (or what the speech model hears instead: "on meet", "and mute
    me", "on mute") presses unmute.
  * If **she deafened you**, "unmute me" undeafens you instead. While you're
    deafened, Discord keeps your mic off whatever the mute key does, so
    undeafening is what brings your mic back. She only does this when she knows
    it was her who deafened you; if you undeafened by clicking in Discord, say
    "undeafen me" / "unmute me" as usual.
  * Two phrases that are always heard right, because they use ordinary words:
    **"turn my mic on"** / **"turn my mic off"** and **"take me off mute"** /
    **"put me on mute"**.
  * "Undeafen" ("on deafen", "undefined"...) is its own command too.
* **"Search up ___ on Opera"** (or Chrome, Edge, Firefox, Brave):
  * Opens a Google search in *that* browser. The browser is started from its
    own program file, with the search address as its only argument.
  * If that browser isn't on your PC, she uses your default browser and says
    so.
* **"Search up ___ on Google / YouTube / Wikipedia / Reddit / Amazon / Twitch /
  Bing / GitHub"** opens that site's own search. "Search up ___",
  "search for ___", "look up ___", "google ___" and "search on opera for ___"
  all work.

## New in 1.2

* **"Unmute me on Discord" works.** The speech model doesn't know the words
  "unmute" or "deafen", so it writes down the nearest words it does know:
  * "on meet on discord", "and mute me" for unmute
  * "the fan me", "defend me", "undefined" for deafen

  Capri now recognises those sound-alikes. A sound-alike only counts when it
  names you or Discord: "meet me" is still mute, but "the fan" on its own
  isn't.
* **She can open almost any app.** Besides your list, Steam and Start-menu
  shortcuts, she now reads Windows' own **All apps** list (the Applications
  folder). That's where Microsoft Store apps live, which have no shortcut file:
  * Clipchamp, Calculator, Photos and Settings
  * the new Outlook, WhatsApp and Xbox
  * PowerPoint / Word / Excel from Microsoft 365
  * Say "open clip champ" or "open power point". They're launched the way the
    Start menu does it (`shell:AppsFolder\<app id>`), using the id Windows
    gives the app, never words from speech.
  * "Close Clipchamp" works too.
  * They're all listed in Settings → Found on this PC.
* **Folders:**
  * "open downloads", "open my documents folder", "open file explorer",
    "open this PC" and "open the recycle bin".
  * "open homework" or "open my essay" opens one of your own folders or
    documents if no app has that name. She only searches your Desktop,
    Documents, Downloads, Pictures, Videos, Music and OneDrive.
  * She never *runs* a program she found this way; she just shows you where
    it is.
* **"Show me X in File Explorer"**, "where is my essay", "find my minecraft
  screenshots": opens File Explorer with it selected.
  * Store apps (like Clipchamp) have no normal folder (Windows keeps them
    locked away), so for those she opens your Apps folder and tells you so.

## New in 1.1

| Say "Hey Capri, ..." | What happens |
|---|---|
| **"shut down my PC"**, "restart", "put my PC to sleep" | She asks "Shut down the PC? Say yes or no." Only a clear *yes* does it; anything else (or silence) keeps it on. Then she says bye and does it. |
| **"lock my PC"** | Locks straight away (Windows' own Win+L lock). |
| **"minimise everything"** / "minimise my screens" / "show desktop" | Minimises every app window, but not her. **"bring them back"** restores exactly those windows. |
| **"minimise Discord"**, "minimise this" | Minimises one app, or the window in front. |
| **"mute me"**, "unmute me", **"deafen me"**, "undeafen" | Presses Discord's mute / deafen key. These are toggles, so she says "Toggled your Discord mic" and doesn't claim a state she can't see. More below. |
| **"play let you down by NF"**, "play songs by NF" | Searches Spotify for that exact song by that artist, and also does a looser search (speech recognition spells names its own way, e.g. "the weekend"). She plays whichever result *sounds* closest to what you said, so a cover version doesn't win. |
| **"how are you"**, "tell me a joke", "I'm bored", "thanks", "good night"... | Small talk. When she asks you something back, she **keeps listening for your answer, with no wake word needed**. She stops after a few turns, or as soon as you go quiet. With AI chat on, Claude does the talking, prompted to chat like a friend. |

* **Her voice is much less robotic.** Two things made her sound like a robot:
  * The Windows voices themselves.
  * The old "Capri" style. Its ring-mod shimmer, comb-filter double and
    bit-crush are what gave her the metallic edge.

  What changed:
  * **The "Capri" style is now clean:** it only trims the boom and adds a
    little air. The digital effects stay in Netrunner / Glitch if you want them.
  * **She has a neural voice:** Kokoro, which is natural and expressive and
    runs fully offline. "Capri" is a blend of two of its brightest young female
    voices, lifted ~1.5–2.5 semitones with tape-style pitching. That raises the
    formants too, so the timbre is lighter and younger, more anime girl, with
    none of a pitch-shifter's warble.
  * `run.bat` installs the voice engine (`requirements-voice.txt`, optional:
    if it fails she still runs, with the Windows voices) and downloads the
    voice by itself once (about 120 MB). Works on Python 3.10 to 3.14. There's also a
    **Download Capri's voice** button in Settings → Assistant, which needs no
    restart. Voice **Default** uses it.
  * The Windows voices are still there as a fallback.
* **Her hair** is now the same crimson as the rest of her (sampled from her
  body art), not the separate orange-red it was.
* **Starts with Windows by default.** It's switched on once, on first run, and
  the installer box is ticked by default. Turn it off in the tray menu or
  Settings → PC & chat, and it stays off.
* **She greets you when you sign in, unlock or wake the PC.** She appears big
  in the middle of the screen with a neon caption ("Morning, choom! Ready to
  take on the day?"), lip-synced. Then she shrinks back into her corner. If
  she asked you something, she listens for your answer.
  * The greeting is click-through and never takes focus, so it can't get in
    the way.
  * Turn it off, or make it a small greeting in the corner, in
    **Settings → PC & chat**. There's a **Preview greeting** button there too.

### Discord mute / deafen

Discord's own shortcuts (Ctrl+Shift+M mute, Ctrl+Shift+D deafen) only work
while Discord is the window in front. Out of the box, Capri brings Discord to
the front for a split second, presses the key and puts your window back. Two
catches:

* It can't reach Discord while Discord is **closed to the tray**. She tells
  you so.
* It can blip a full-screen game.

**Recommended one-time setup** (works from anywhere, no focus switch):

1. In Discord go to User Settings → **Keybinds** → Add a Keybind →
   **Toggle Mute**.
2. Record a combo nothing else uses, e.g. **Ctrl+Alt+Shift+M**.
3. Do the same for **Toggle Deafen** (e.g. Ctrl+Alt+Shift+D).
4. Type the same combos in Capri's **Settings → PC & chat**.

## Status: all 6 stages done

| Stage | What | State |
|---|---|---|
| 1 | Transparent overlay, Capri bottom-right, status panel above her | Done |
| 2 | Dragging, compact mode, always-on-top toggle, saved settings/position, tray icon | Done |
| 3 | Local wake word ("Capri" / "Hey Capri"), command capture, push-to-talk, mute | Done |
| 4 | Commands: open / close apps, Steam games, websites, search, widget modes + Settings window | Done |
| 5 | Her voice + speaking animation, music, weather, optional AI conversation, character-sheet art, emotions | **Done** |
| 6 | Polish, performance, log file, packaged `.exe` + installer | **Done** |

### The overlay

* Capri and her panel are two separate frameless, transparent windows that act as
  one companion. No title bar, no taskbar button, no Alt+Tab entry, and they
  never take keyboard focus from a game.
* First launch puts her in the bottom-right of the primary monitor's work area
  (above the taskbar).
* The panel shows her icon, `CAPRI / SYSTEM`, a green status badge, a status
  message and an activity log, like the reference. Its tail always points at her.
* States: `STANDBY`, `LISTENING`, `PROCESSING`, `LAUNCHING`, `SPEAKING`, `DONE`,
  `ERROR` (red). The badge pulses while listening or processing. Her frame turns
  green when listening and red on an error. Poses switch per state.

### Controls (Stage 2)

* **Drag** Capri *or* the panel with the left mouse button. They move together.
  She can stand right against any screen edge: only *her body* is kept on
  screen, and her hair may spill off it.
* **Multiple monitors**: drag her onto any monitor. She remembers which one.
  If that monitor is unplugged she moves to the primary one, and goes back when
  it returns. Resolution, scaling or taskbar changes keep her the same distance
  from the bottom-right corner.
* Near the top of a screen the panel **flips below her** automatically.
* **Right-click** Capri or the panel, or use the **tray icon**, for the menu:

| Menu item | What it does |
|---|---|
| Hide / Show Capri | Hides everything until you show her again. Left-clicking the tray icon does the same. This is temporary: she's visible again on the next launch. |
| Show status panel | Panel on/off. Capri stays visible. |
| Show activity log | The log rows under the message (not shown in compact mode). |
| Compact mode | Much smaller Capri (105 px) and a one-line panel. Her feet stay where they were. |
| Always on top | Keep her above other windows, or let other windows cover her. |
| Listen now (Ctrl+Alt+C) | Push-to-talk: she listens for one command without the wake word. |
| Voice activation (wake word) | Listen for "Capri" / "Hey Capri". Off = microphone closed (push-to-talk still works). |
| Mute microphone | Hard mute. The microphone is closed and nothing can open it, including push-to-talk. |
| Microphone | Choose which input device she listens to. |
| Click-through (Ctrl+Alt+Shift+C) | Every click passes through Capri and the panel. You can't drag or right-click her while it's on, so turn it off with **Ctrl+Alt+Shift+C** or from the **tray icon** (click the **^** next to the clock if it's hidden). |
| Reset position | Back to the default bottom-right corner of the primary monitor. |
| Settings... | Your app list, everything found on this PC, and voice options. See below. |
| Start with Windows | Adds or removes Capri in your user's startup list (registry `HKCU\...\Run`, no admin needed). |
| Exit Capri | Quit. |

* Every option and her position are saved automatically to
  `%LOCALAPPDATA%\Capri\settings.json`. Delete that file to reset everything.
* Only one Capri runs at a time. Starting a second copy just exits.

**Why you can't click through her by default:** she has to catch clicks so you
can drag her and right-click her. With the current art she's an opaque card, so
the whole card catches clicks. Only the fully transparent area around her lets
clicks through. Turn on **Click-through** when you want her purely decorative.

## Voice (Stage 3)

Say **"Capri"** or **"Hey Capri"**, then your command, either in one breath
("Hey Capri, open Discord") or with a pause ("Capri." ... "open Discord").

1. Her frame turns green and the panel shows `LISTENING`, with your words
   appearing as you speak.
2. The command is transcribed and shown, e.g. `Heard: "open discord"`.
3. She goes back to `STANDBY` / `Waiting for wake word...`.

What she can do with it is in **Commands** below.

**How she decides you called her:**

* A Vosk recogniser that knows only three things listens all the time:
  `capri`, `hey capri`, and "something else". It doesn't transcribe anything
  else you say.
* It only counts as a wake-up when your sentence **starts** with "Capri" or
  "Hey Capri". "I went to Capri last year" is ignored.
* Vosk's confidence in the word must be at least `wake_threshold` (default
  0.80). If she isn't sure, she ignores it. Near-misses are printed in the
  console as `ignored possible wake word: ... confidence 0.62`, which helps
  with tuning.
* Only after a wake-up is the following speech transcribed, with the full
  English model. That also runs on your PC.
* If you say "Capri" and then nothing, she gives up after 6 seconds
  (`Didn't catch that.`).

**Microphone and privacy:**

* While voice activation is on, **the microphone is open continuously**. Any
  wake word works this way, and Windows will show its mic-in-use icon.
* All audio is processed **on this PC**. Nothing is sent to any server, saved to
  disk, or logged. To catch "Capri, open Discord" said in one breath, the last
  20 seconds of audio are kept in memory and constantly overwritten.
* **Mute microphone** or turning off **Voice activation** closes the microphone
  completely. With voice activation off, push-to-talk opens it for one command,
  then closes it again.
* If the microphone disappears (unplugged, or after the PC wakes from sleep)
  she reopens it automatically. The panel shows `No microphone available.` until
  it's back.

**Tuning** (in `%LOCALAPPDATA%\Capri\settings.json`, while Capri is closed):

| Setting | Default | Meaning |
|---|---|---|
| `wake_threshold` | `0.8` | Raise it (e.g. `0.9`) if she wakes up by mistake. Lower it (e.g. `0.7`) if she misses you. |
| `hotkey_listen` | `"ctrl+alt+c"` | Push-to-talk. Format: `ctrl`/`alt`/`shift`/`win` + a key, e.g. `"ctrl+shift+f9"`. |
| `hotkey_click_through` | `"ctrl+alt+shift+c"` | Toggle click-through. |

If a hotkey is already used by another app, the panel says so
(`Hotkey: Ctrl+Alt+C is already used by another app`). Pick another one.

## Commands (Stage 4)

| Say | What happens |
|---|---|
| "Capri, open Deadlock" / "launch ..." / "start ..." / "play ..." | Opens an app, Steam game, Start-menu shortcut or website |
| "Hey Capri, open Discord and Spotify" | Several at once |
| "Capri, close Discord" / "quit ..." / "shut down ..." | Closes it (see below) |
| "Capri, close Discord and Deadlock" | Several at once |
| "Capri, open YouTube" / "open twitch dot tv" | Website in your default browser |
| "Capri, search for deadlock builds" / "google ..." | Web search in your default browser |
| "Capri, what time is it" / "what's the date" | Shows the time or date |
| "Capri, switch to compact mode" / "normal mode" | Compact mode on or off |
| "Capri, hide the status panel" / "show the status panel" | Panel on or off |
| "Capri, hide" / "come back" | Hide or show her (she still listens while hidden) |
| "Capri, lie down" / "get up" | Lie on the status panel, or stand again |
| "Capri, never mind" | Cancel |

### What she can open, with no setup

1. **Your app list** (Settings → Apps). It comes pre-filled with Discord,
   Spotify, Chrome, Opera GX, Deadlock, Minecraft, Bloxstrap, Roblox and Steam.
   Paths are filled in only where they were actually found on your PC.
2. **Every installed Steam game**, read from your Steam libraries.
3. **Everything in your Start menu.**
4. A few well-known websites (YouTube, Twitch, Reddit, GitHub...), or
   "something dot com".

### "Blocks strap" → Bloxstrap

The speech model only knows dictionary words, so it will always hear "Bloxstrap"
as "blocks strap". Capri compares names by **how they sound**: "blocks strap",
"blox strap" and "Bloxstrap" all reduce to the same key, and so do "counter
strike two" and "Counter-Strike 2". The panel shows the match
(`Match: "blocks strap" → Bloxstrap`). If a name still doesn't match, add what
she hears to that app's **Also say** column.

### Closing apps

Each app has a **When closing** setting:

| Setting | What "close X" does | Default for |
|---|---|---|
| **Like clicking X** | Asks the app to close, like its X button, so it can save or ask you itself. If it's still running 4 s later, she asks: *"X is still running. Force close it?"* | most apps |
| **Ask me first** | *"Close Deadlock? Say yes or no."* Only a clear "yes" closes it (so you don't abandon a match by accident). | games: Deadlock, Minecraft, Roblox, any Steam game |
| **Force quit** | Ends it immediately, no questions. | Discord, Spotify. Their X only hides them to the tray, so "close" has to quit them for real. |

* For yes/no questions she listens straight away, without the wake word.
  Silence, "no" or anything unclear counts as **no**.
* She can only close **your own programs**. Windows system processes
  (explorer, svchost...) and Capri herself are protected.
* Steam games are recognised by their install folder. Other apps are matched
  by their process name (e.g. `Discord.exe`).

### Safety

* No command line is ever built from what you say (or from what the AI says).
  Capri can only run one of these fixed actions:
  * launch an entry from the lists above (programs start with an argument
    list, never through a shell)
  * open a `steam://` game id
  * open an `https://` link or an allowed app link (`spotify:`, `discord:`...).
    `file:`, script and other links are refused.
  * close matching processes
  * press media keys, or call Spotify's playback API
  * change her own display
* Unknown phrases get `Not sure what you mean.` and nothing happens.

### Settings window (right-click → Settings...)

* **Apps:** name, *Also say* (other ways she might hear it), type (Program /
  Steam game / Website), path or Steam id or URL, arguments, process names, and
  *When closing*.
  * **Browse for program...** fills in the path and process name for you.
  * **Test launch** really launches the selected entry.
  * **Save** applies the changes immediately.
  * **Try a command:** type e.g. `open blocks strap` or `close discord and
    deadlock` to see exactly what would happen, including the match
    percentage. Nothing runs.
* **Found on this PC:** every Steam game and Start-menu shortcut she can open,
  with a Rescan button.
* **Wake word:** wake-word confidence slider, push-to-talk and click-through
  hotkeys.
* **Assistant:** her voice, weather, Spotify and AI (see the next section).

Stored in `%LOCALAPPDATA%\Capri\apps.json`.

## Assistant (Stage 5)

### More things to say

| Say | What happens |
|---|---|
| "Hey Capri, play Let You Down by NF" | Plays it on Spotify (see the Spotify notes below) |
| "Capri, play ... on YouTube" | Opens a YouTube search for it |
| "Capri, play Deadlock" | If the name is a game or app you have, she launches it instead |
| "Capri, pause" / "resume" / "next song" / "previous song" | Controls whatever is playing |
| "Capri, turn it up" / "turn it down" | Volume ±10% |
| "Capri, what's playing?" | Song and artist (needs Spotify connected) |
| "Hey Capri, what's the weather today?" | Weather for your home city |
| "... tomorrow" / "... in Tokyo" | Tomorrow's forecast, or another city |
| "Capri, is it going to rain?" / "do I need an umbrella?" | Chance of rain |
| Anything else ("tell me a joke", "how far is the moon?") | AI answer, if you turned it on |

### Her look: the character sheet (Settings → Character)

Your character sheet is cut into transparent sprites (`assets/capri_v2/`):
the full-body frames, 8 expressions, 16 mouth shapes and the lying-down pose.
Pick a **Style**:

| Style | What you see |
|---|---|
| **Full body** (default) | Her sheet frames, picked per state: idle, listening, thinking (while working), speaking, happy (on success), confused (on errors, with a red flicker). |
| **Portrait** | A talking head in a neon card on a dark screen with red sparkles. Her expressions change with her emotion and **all 16 mouth shapes** follow her words. |
| **Classic** | The first screenshots in the portrait card, as before. |

* **Idle animation** (on by default): she breathes and sways slightly, blinks
  every few seconds, and looks around now and then, using the sheet's idle,
  blink and look-around frames.
* **Hair** (Settings → Character → Hair):
  * **Storm** (default) is her hair as it looks in the show: one big, wide,
    jagged mass of red with twinkling sparkles and fine stripes. It has a
    blue-purple edge offset down-left, spikes shooting sideways, and strands
    hanging down on her right.
    * It covers the sheet's pink bob, and her face (the green mask and black
      lower face) is drawn back on top, so it peeks out of the mass like in the
      anime.
    * The outline "boils" 8 times a second like hand-drawn animation. It flares
      when she talks, and now and then a slice of it glitches sideways.
  * **Spikes** adds faceted shards *behind* her sheet hair instead.
  * The **Wild hair** slider sets the size; 0 gives her plain sheet hair.
* **Lie on the panel:** she lies along the top of the status panel in the
  sheet's lying-down pose, breathing slowly. Say "Capri, lie down" / "get up",
  or use the menu or Settings.
* **Her face is in the panel icon:** her current expression, and mouth shapes
  while she talks.
* **Message panel:** the status panel is styled as a cyberpunk message:
  * a dark red-to-black card with fine scanlines
  * a red frame and a cyan underline

  The old TV static was removed in 1.10.
* **CPU:** the animation runs at 20 fps only while she's visible. Hidden, or
  with idle animation and wild hair both off, she uses nothing at idle.
* To re-import an edited sheet:
  `.venv\Scripts\pip install pillow` then
  `.venv\Scripts\python tools\import_sheet.py path\to\sheet.webp`.
  It removes the light checkerboard background, including gaps enclosed
  between arm and body, without touching her eye highlights.

### Night City slang

She talks like a local, with a few phrasings for each line so she doesn't
repeat herself:

* "Preem. Launching Deadlock."
* "Couldn't find photoshop. Total gonk moment, choom."
* "Discord flatlined."
* "Flatline Deadlock? Say yes or no."
* "Searching the Net for..."

AI answers are told to use the slang too: one or two words per reply, still
easy to understand.

The words: choom (friend), preem (top-notch), nova (cool), gonk (idiot; she
only ever means it affectionately), delta (leave), flatline / zero (kill),
eddies (money), chrome (cyberware), jack in (connect), corpo.

Turn it off with **Night City slang** in Settings → Assistant to get plain
lines ("Launching Deadlock.").

### Emotions

Everything she says carries an emotion: **neutral, happy, playful, smirk,
surprised, confused, serious, sad, angry**. It changes:

* her **face**: the matching expression in Portrait style and in the panel
  icon. In Full body style happy and playful show the waving pose, and
  confused or surprised show the "?" pose.
* her **voice**: happy and playful are higher and quicker, sad is lower,
  slower and softer, angry is faster and a bit louder, serious is lower and
  steadier.

Where it comes from:
* **Results:** "Launching Deadlock." is happy, "Couldn't find photoshop." is
  confused, "Grab an umbrella." is sad, "Discord closed." is a smirk.
* **Questions:** "Close Deadlock?" is serious.
* **AI answers:** Claude picks the emotion for each reply. The tag is never
  read aloud.

### Her voice and animation

* She speaks her results out loud: "Launching Deadlock.", the weather, the
  time, AI answers and yes/no questions. She stays quiet for music commands so
  she doesn't talk over your song, and for status changes nobody asked about.
* **While she talks she animates:**
  * Her mouth follows each syllable. In Portrait style and the panel icon it
    uses the sheet's mouth shapes (A, E, O, M, TH...), worked out from the
    words she's saying. In Full body style it switches between the speaking
    pose and her emotion's pose.
  * She hops slightly, and loud moments throw a quick glitch: slices of her
    image jump sideways with neon scan lines.
  * Her frame glows green with her voice.
  * The panel badge turns into little voice bars, and the text types out as
    she says it.
* **Capri preset** (default, and a button in Settings → Assistant): a voice
  that follows her character. It's young, quick and bright: her neural
  "Capri" voice (see *New in 1.1*), raised a little, at a slightly quicker
  pace, with the clean "Capri" style (a touch of air, no robotic effects).
  * With only Windows voices, it uses Windows' pitch control, +3.4 semitones.
  * It's a sound-alike in spirit; it doesn't copy any real person's voice.
  * Tweak Pitch, Speed and Style from there.
* **Slang said right:** "choom" is pronounced *ch-oo-m* (rhymes with
  "room"), not "chum".
  * Windows voices get the exact phonemes (`ch uw m`).
  * Other engines get a respelling ("chewm") that they read correctly.
  * "preem", "gonk", "eddies" and "corpo" are covered too.
* **Quieter and higher by default:** volume 60%, through a gentle overall
  level so even 100% isn't loud. Pitch is raised about 2.5 semitones for a
  younger, girlier sound. With Windows voices this uses Windows' own pitch
  control, which sounds natural; otherwise it's a pitch shift that keeps her
  speed. **Pitch**, **Volume** and **Speed** sliders are in Settings →
  Assistant.
* **Voices:** her neural "Capri" voice once it's downloaded, else Windows'
  built-in voices (she picks a female one, Zira or Hazel, if you have it).
  Change it in **Settings → Assistant → Voice**. The other neural voices
  (`neural: af_bella`, `af_sky`, `bf_lily`...) are listed there too.
  * Piper voices work as well (also offline):
    `.venv\Scripts\pip install piper-tts`, then
    `.venv\Scripts\python tools\download_voice.py en_US-amy-medium`. Pick
    "piper: en_US-amy-medium" in Settings. Other options are listed in that
    script.
* **Style:**
  * **Capri** (default): clean and bright, with a little air on top.
  * **Netrunner**: brighter, with a light digital double and a touch of
    bit-crush, like a voice coming through a cyberdeck.
  * **Glitch**: Netrunner plus the odd stutter and signal drop-out.
  * **Natural**: the plain voice.
* Settings also has volume, speed, a **Test voice** button, and **Spoken
  replies** on/off. Voice commands keep working when it's off; it's also in
  the right-click menu.
* **She can't hear herself.** While she talks, microphone input is thrown
  away, so her own "...say yes or no" can't answer her question. She asks
  first, *then* listens.

### Music

* **Pause / next / previous / volume** work with any player (Spotify,
  YouTube, VLC...) through the Windows media keys. No setup needed.
* **"Play <song>":** Spotify only lets apps *start* a song for **Premium**
  accounts, and only after you connect Capri once:
  1. Go to <https://developer.spotify.com/dashboard>, create an app (any
     name), and add the redirect URI `http://127.0.0.1:8973/callback`.
  2. Paste its **Client ID** into **Settings → Assistant → Spotify** and press
     **Connect**, then approve in the browser window that opens.
  3. "Hey Capri, play ..." now starts the song. If Spotify isn't open she
     launches it first.
* Not connected, or no Premium: she opens that song's search in the Spotify
  app and you press play. No Spotify app at all: YouTube search.
* Sign-in uses Spotify's own login page (PKCE: no password or client secret
  ever reaches Capri). The access token is stored in
  `%LOCALAPPDATA%\Capri\secrets.json`. **Disconnect** removes it.

### Weather

Set your **home city** in **Settings → Assistant → Weather** (Celsius or
Fahrenheit). Data comes from **Open-Meteo**: free, no account. Only the city
name is sent; nothing about you or your location.

### AI conversation (optional, off by default)

* Turn it on in **Settings → Assistant → AI** with your own Anthropic API key
  from <https://console.anthropic.com>. It's paid per use; a quick question
  costs roughly half a cent to a cent.
* **What's sent:** only the *text* of a request Capri doesn't recognise as a
  built-in command (after the wake word), plus the last few turns of that
  conversation. Never audio, and never anything said without the wake word.
  She forgets the conversation after 5 minutes of quiet.
* It uses **Claude Opus 5.5** at low effort, for quick, short replies,
  answering in Capri's playful, slightly sarcastic personality. The request
  also opts into Anthropic's **server-side fallback**: if a request is
  declined, Anthropic retries it on another Claude model instead of failing.
* **Actions stay safe:** if the AI thinks you want something done ("open that
  blocky strap launcher"), it can only *suggest* an action like open_app or
  play_music. That suggestion goes through the same command system as your
  voice, with the same app list and the same "Close Deadlock?" questions. AI
  text is never run as a command. It also handles names the built-in matcher
  couldn't find.
* Without a key, everything else works exactly the same; unknown phrases just
  get `Not sure what you mean.`

### Sleep and the lock screen

* **Sleep / hibernate:** the processor is suspended, so no program can run or
  listen, Capri included. When the PC wakes she's still there and reconnects to
  the microphone by herself.
* **Lock screen:** Windows doesn't let normal apps draw on the lock screen; it's a
  protected desktop. Capri keeps running behind it and is right where you left
  her when you unlock.
* **After a restart:** Start with Windows is on by default, so she comes back
  (and says hi) every time you sign in.
* **Unlocking / waking:** Windows tells her when you sign back in, and she
  greets you (Settings → PC & chat).

## Run it on Windows

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/>
   (tick *"Add python.exe to PATH"* during install).
2. Copy this `capri-companion` folder anywhere, e.g. `C:\Users\you\capri-companion`.
3. Double-click **`run.bat`**. The first run does all the setup, and later runs
   start immediately:
   * creates `.venv`
   * installs PySide6, Vosk, sounddevice, numpy, psutil, comtypes and the
     Anthropic SDK (~150 MB)
   * downloads the offline speech model **once** (~40 MB, from
     alphacephei.com, the Vosk project) into `models\`
   If you're updating from an earlier stage, `run.bat` notices the new
   requirements and installs them.

Or by hand in PowerShell:

```powershell
cd C:\path\to\capri-companion
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python tools\download_model.py
.venv\Scripts\python -m capri
```

To see every panel state cycle through (header says `CAPRI / PREVIEW`, nothing is
launched or listened to):

```powershell
.venv\Scripts\python -m capri --preview     # or: run.bat --preview
```

To quit: right-click Capri (or the tray icon) → Exit Capri, or Ctrl+C in the console.

`run.bat` keeps a console window open, which is handy for seeing warnings. For
no console, start it with `.venv\Scripts\pythonw.exe capri_launcher.py`. **Start
with Windows** does that for you. If you move the project folder, untick and re-tick
**Start with Windows** so the startup entry points to the new location.

## Capri's artwork

Art lives in `assets/capri/` and is described by `manifest.json`:

```json
{
  "name": "Capri",
  "icon": "icon.png",
  "display": "auto",
  "poses": {
    "idle": "idle.png",
    "thinking": "idle.png",
    "speaking": "grin.png",
    "success": "grin.png"
  }
}
```

* Pose names used by the app: `idle`, `listening`, `thinking`, `speaking`,
  `success`, `error`. Only `idle` is required; any missing pose falls back to it.
  To add an expression, drop in a PNG and add a line.
* Images are only ever scaled with their aspect ratio kept - never stretched.
* `display`:
  * `"auto"` (default) - a PNG with a transparent background is drawn
    **free-standing** on your desktop (like the reference screenshot). An image
    without transparency is shown in an angled neon **portrait card**.
  * `"cutout"` / `"card"` to force one.

**About the current art:** the two images you sent are screenshots with Capri's
red sparkle background baked in. Capri herself is red, so removing "the red" would
also delete her body. I didn't colour-key them; they show in the portrait card
(`idle.png` from image 1, `grin.png` from image 2, and `icon.png` is a head crop
for the panel). Your originals are untouched in `assets/capri/source/`.

**For the free-standing look in your reference**, send or drop in a
**transparent PNG** of Capri (full body like the reference, around 400-800 px
tall). Cut her out in Photoshop, GIMP, Krita, or a background remover, then save as
`assets/capri/idle.png` (and `grin.png` etc. for other poses). The app detects
the transparency and switches to cut-out mode by itself, no code changes needed.

Check how art looks without launching the overlay:

```powershell
.venv\Scripts\python tools\render_preview.py preview
```

That writes one PNG per state into `preview\`.

## Packaging: Capri.exe and the installer

```powershell
build.bat
```

1. Installs the build tools and downloads the speech model if needed.
2. Runs PyInstaller with `packaging\capri.spec` and produces
   **`dist\Capri\Capri.exe`**:
   * a folder build, which starts much faster than a one-file exe
   * no console window
   * Windows version info and her icon
   * artwork, speech model and any Piper voices you installed, all bundled
3. If **Inno Setup 6** is installed, it builds
   **`dist\Capri-Setup-1.19.0.exe`** from `packaging\capri.iss`:
   * installs for your user only, into `%LOCALAPPDATA%\Programs\Capri` (no
     admin prompt)
   * Start menu shortcut, plus optional desktop shortcut and optional *Start
     with Windows*
   * the uninstaller removes the program and its startup entry, and asks
     whether to also delete your settings and keys

Windows SmartScreen may warn the first time ("Windows protected your PC"),
because the exe isn't code-signed. Click *More info → Run anyway*. Signing
needs a paid code-signing certificate.

## Polish (Stage 6)

* **Low CPU at idle:** she repaints only when something visible changes. That
  covers a blink, the 1-pixel breathing bob, a hair "boil" step (4 per second
  at rest), and a static frame. The hair and the panel's text are cached
  between those changes.
  * Measured: about **4% of one CPU core** with everything on (full body,
    Storm hair, idle animation, panel static), down from 34% before this
    stage.
  * About 2% without the panel static, and **0%** with animation off or while
    she's hidden.
  * About 110 MB of memory, including the speech model.
* **Log file:** `%LOCALAPPDATA%\Capri\capri.log`, also reachable from the menu
  with **Open log folder**.
  * Warnings, ignored near-miss wake words and any unexpected error are
    written there with details.
  * If something breaks she says "glitched - see capri.log" instead of
    disappearing.
* **Starting her twice** (Start menu, desktop, run.bat) doesn't make two
  Capris. It brings the running one back, even if she was hidden.
* **First run:** she greets you ("Hey choom. Say 'Hey Capri'...") and a tray
  note explains the wake word, settings and that mic audio stays on your PC.
* The version is shown in the menu (Capri 1.19.0).

## Troubleshooting

| Problem | Fix |
|---|---|
| She doesn't react to "Hey Capri" | Check the panel. "No microphone available" means picking the right one under right-click → Microphone. For "Voice model missing", run `setup_voice.bat`. If she hears you but ignores you, lower the wake-word confidence in Settings → Wake word. Near-misses are listed in `capri.log`. |
| She wakes up by mistake | Raise the wake-word confidence in Settings → Wake word. |
| A hotkey doesn't work | Another app has it. The panel says so; pick another in Settings → Wake word. |
| I can't click her / she's in the way | Use **Click-through** (Ctrl+Alt+Shift+C), compact mode, or "Capri, hide". |
| She can't find an app | Settings → Apps: add it with **Browse**, or add what she hears to *Also say*. **Try a command** shows exactly what she matches. |
| Voice too loud / too deep / wrong | Settings → Assistant: Volume, Pitch, Speed, Style, or the **Capri preset** button. |
| Her voice still sounds robotic | Her neural voice isn't installed yet: Settings → Assistant → **Download Capri's voice**, or run `setup_voice.bat`. Check Voice is **Default** or "neural: Capri". |
| "Mute me" doesn't work | Set your own Discord keybinds (see *Discord mute / deafen*). If Discord ignores Capri's key presses, run Discord and Capri at the same privilege level (both normal, not "as administrator"). |
| I don't want her to start with Windows | Tray → untick **Start with Windows** (it stays off). |
| She vanished | Click the tray icon (the **^** by the clock), or just start Capri again. |
| Something else | Right-click → **Open log folder** and look at `capri.log`. |


## Project layout

```
capri/
  app.py               entry point, CLI flags, single-instance lock, startup
  controller.py        CompanionController: current state, message, activity log
  states.py            State enum + badge text / pose / colour per state
  settings.py          saved settings + position (JSON)
  autostart.py         Start with Windows (HKCU Run key)
  hotkeys.py           global shortcuts (Windows RegisterHotKey)
  assistant.py         voice events -> Capri's states, panel text and speech; yes/no questions;
                       listening for your answer in a conversation
  chat.py              built-in small talk + the sign-in greeting
  session.py           notices sign-in / unlock (WTSRegisterSessionNotification)
  secrets.py           API key / Spotify token storage (secrets.json)
  emotions.py          emotions: face, pose and voice prosody for each
  lines.py             what she says: plain lines and Night City slang versions
  logs.py              capri.log + crash catching
  memory.py            gives idle memory back to Windows (and when a game starts)
  typing_watch.py      notices you typing (not which keys), so keyboard noise isn't taken as speech
  commands/
    parser.py          spoken text -> intent (open/close/search/...), plain patterns
    fuzzy.py           sound-alike name matching ("blocks strap" = Bloxstrap)
    apps.py            your app list (apps.json) + detected defaults
    discovery.py       installed Steam games, Start-menu shortcuts (.lnk reader)
    catalog.py         everything openable/closable, best match for a name
    router.py          carries out intents, asks before risky closes
    system.py          the only code that starts/stops processes (Windows)
    desktop.py         PC power, minimising windows, Discord keys - fixed actions only
    places.py          known folders + Windows places ("downloads", "file explorer", "recycle bin")
    files.py           finding your own files / folders by name (your folders only, time-limited)
    games.py           game mode: drone on when a game launches, off when its processes close
  speech/
    engines.py         text-to-speech: neural Kokoro ("Capri"), Windows SAPI, optional Piper, espeak (dev)
    effects.py         voice styles (capri / netrunner / glitch) + loudness track for lip-sync
    speaker.py         speech thread: synthesise, style, play; mutes the mic meanwhile
    pronounce.py       slang pronunciation ("choom" = ch-oo-m)
  integrations/
    weather.py         Open-Meteo weather
    spotify.py         Spotify Web API (PKCE sign-in, play, pause, now playing)
    media.py           Windows media keys
    uia.py             pressing apps' own buttons via Windows UI Automation
    app_buttons.py     Discord's Mute / Deafen and Spotify's Play buttons, read back after pressing
    spotify_app.py     "play X by Y" without Premium: exact track, open it, check the window title
    screen_targets.py  "click subscribe" / "click that": finds it on screen (UI Automation, then OCR)
    screen_click.py    finds Spotify's green Play button on screen and clicks it (when UI Automation can't)
    http.py            small JSON-over-HTTPS helper
  ai/
    claude.py          optional Claude conversation; tools map onto Capri's own intents
    local.py           the free local AI (Ollama), same tools and rules; picks Claude or local
  voice/
    wakeword.py        wake word + command capture (pure logic, no mic)
    service.py         microphone thread: open/close, mute, reconnect
    model.py           find / download the Vosk model
  ui/
    overlay_window.py  frameless, transparent, top-most, non-focus window + dragging
    character_window.py  Capri (cut-out or portrait card)
    status_panel.py    terminal-style panel (normal + compact, tail up/down)
    companion.py       keeps both windows together: placement, monitors, options
    tray.py            tray icon + the menu shared with right-click
    settings_window.py Settings: apps, found on this PC, wake word
    assistant_tab.py   Settings -> Assistant: voice, weather, Spotify, AI
    lipsync.py         voice loudness + words -> animation level and mouth shapes
    sprites.py         character-sheet art (body frames, expressions, visemes, lying)
    hair.py            Storm hair (the show's hair-storm) and Spikes
    static_fx.py       scanlines and glitch helpers for the panel (the static itself is off since 1.10)
    idle_acts.py       idle activities: glitching, gaming, watching, on a call with D
    looks.py           the animated pictures (Look: Stare / Glitch / Grin + your looks/ folder)
    contact.py         D on the video call, animated from one picture (mouth, nods, blinks, breathing)
    drone.py           game mode's little flying disk of shards around her eye
    chat_window.py     type to Capri instead of talking
    visit.py           the dash over + zap (folders in Explorer, minimise buttons)
    visit_actions.py   finds the minimise button / Explorer sidebar entry to zap
    look_tab.py        Settings -> Character
    pc_tab.py          Settings -> PC & chat: conversation, greeting, start-up, Discord keys
    greeting.py        the big sign-in hello and the shrink back to her corner
    rig.py             her full-body figure cut into parts (legs, torso, arms, face) so she can move
    lightning.py       branching red lightning (midpoint displacement), crackle along a trail
    zap.py             the lightning blast at a window she closes / a Discord button
    psychosis.py       the shutdown "cyberpsychosis" screen takeover
    screen_spots.py    where things are on screen (taskbar buttons, pixel scaling)
    art.py             manifest + pose loading, transparency detection
    theme.py           colours and fonts
tests/                 headless tests (overlay, wake word, voice, commands, settings)
models/                offline speech model (downloaded by run.bat / setup_voice.bat)
assets/capri/          classic artwork + manifest.json (originals in source/)
assets/capri_v2/       character-sheet sprites + manifest.json (your sheet in source/)
assets/reference/      your desktop reference screenshot
tools/render_preview.py  offline renders of every state
tools/download_voice.py  her neural voice (Kokoro), or an optional Piper voice
tools/import_sheet.py  cut the character sheet into transparent sprites
packaging/capri.spec   PyInstaller build (Capri.exe, version info, icon, bundled data)
packaging/capri.iss    Inno Setup installer (per-user, Start menu, optional autostart, uninstaller)
run.bat / setup_voice.bat / build.bat
```

The UI only *observes* `CompanionController`. Voice lives in `capri/voice` and
never touches widgets; `capri/commands` is the only path from speech to
actions. `capri/speech`, `capri/integrations` and `capri/ai` are separate
modules too. The AI module can never run a system command directly. Commands go through a
restricted allow-list of configured apps, URLs and Steam games.

## Testing notes

Developed in a Linux container (Qt offscreen renderer, two simulated monitors).
**184 automated tests pass:**

* **Earlier stages (98):** overlay, multiple monitors, wake word, microphone
  thread, commands, app matching, closing, Settings.
* **Stage 5 (57):**
  * **Parser:** play / pause / skip / volume / "what's playing" / weather /
    rain phrasings, and "yes or no" no longer counts as a yes.
  * **Voice effects:** all styles produce clean audio at even loudness, and the
    lip-sync loudness track follows the syllables. Tested with real synthesised
    speech (espeak) as well as test tones: 7-14 ms of processing per sentence.
  * **Speaker thread:** speaks and signals in order, honours "spoken replies
    off", lets a new line interrupt the old one, and runs callbacks on the UI
    thread.
  * **Microphone:** ignores audio while she talks, then works normally again.
    A confirmation question is spoken *before* she listens.
  * **Weather,** against canned Open-Meteo replies: today, tomorrow, rain,
    unknown city, offline.
  * **Spotify,** against a fake Spotify API:
    * play (search, then the right device, then start)
    * Premium required
    * Spotify app not open (she launches it and retries)
    * token refresh
    * the full PKCE sign-in, including the local redirect page
    * disconnect
  * **Router:** song on Spotify (silently), search fallback without a
    connection or without Premium, "play Deadlock" launching the game, media
    keys, weather with and without a city, AI answers, AI actions going through
    the normal launcher, and no AI loop on a made-up name.
  * **AI, against a fake Claude client:**
    * the exact request shape (model, fallback, low effort, strict tools,
      caching)
    * the weather tool round trip
    * an action becoming an intent with an append-only history
    * refusal, bad key and offline handling
    * forgetting the conversation after going quiet
    * the AI can't invent actions (`run_shell`, unknown options)
  * **Animation:** the mouth follows the voice (with hysteresis); typewriter
    text and the longer answer panel.

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest tests
```

**Character sheet, emotions and voice (18 more tests):**
* every sprite imported with real transparency
* body poses for each state and emotion; blink and look-around timing
* the animation stops when hidden or switched off
* wild hair making room and drawing
* portrait lip-sync with expressions between syllables
* lying on the panel: resting on its edge, fully on screen, no tail;
  Classic style refusing it
* the panel icon following her face and mouth
* switching styles without her moving
* emotion tags and guesses
* the default voice being higher and quieter
* emotions changing pitch, speed and loudness
* the pitch shift really raising pitch at the same length
* the AI's emotion tag being parsed and not spoken
* the Character tab controls
* Storm hair covering her hair while her face stays on top; the outline boiling
  in steps
* the panel's static really drawing, bursting on status changes, and stopping
  when hidden or off
* slang lines (every variant formats, and each has an emotion); the router
  using them; the AI getting slang instructions only when it's on
* "choom" pronunciation (respelling and SAPI phonemes, XML escaping)
* the Capri voice preset and style
* standing flush against a screen edge with her window hanging past it
* idle efficiency: no repaint unless something visible changed; Storm hair
  rendered once per boil step

**v1.9 checks (377 → 383 tests, Python 3.13 and 3.14):**
* Searches only in search mode.
* Weather wording.
* Spotify: the catalog route (iTunes → best match → song.link), Bing's
  wrapped links, main-window-only titles, and not restarting a song that's
  already playing.
* Reading the recogniser's alternatives, the runner-up winning when it's a
  command, and the assistant using it.
* Mishearing fixes.
* Shutdown going through the cyberpsychosis show before the real shutdown, and
  the show itself running on every screen.
* The Discord button being zapped before it's pressed.

Not testable here: the catalog / song.link lookups (blocked from this
sandbox), Spotify's real window, the bigger speech model (blocked download),
and grabbing your real screen.

**v1.8 checks (20 more tests, 377 in all, on Python 3.13 and 3.14):**
* Spotify, against a fake PC whose window title behaves like Spotify's:
  * track links read from search result pages (DuckDuckGo's encoded links,
    localised links, duplicates)
  * the real song chosen over a cover
  * Spotify started first when it's closed
  * Play pressed when opening alone didn't start it
  * "opened" reported honestly when it really didn't play
  * Spotify's own search used when connected
  * DuckDuckGo then Bing on no result
  * the router's messages, and the no-Premium fallback
* Bolts: they end where they should, have the fractal zig-zag and branches,
  and draw.
* Search mode: the phrasings; ask, search, ask again (YouTube and plain);
  "that's all"; silence; back to normal afterwards.
* The close blast: it's used for closing, the close happens at impact, and
  everything is hidden after.
* The teleport test: no bending, her hand raised, the zap hitting the icon,
  standing a step beside it.

Not testable here: the real song lookup on DuckDuckGo / Bing / oEmbed (those
sites are blocked from this sandbox), and Spotify's real window titles.

**v1.7 checks:**
* The rig: every part present.
* The claw position, worked out with the same transforms used to draw her, and
  moving out toward the icon as she bends and reaches, on either side.
* The head box used for the storm hair.
* The teleport test checks:
  * she stands on the bottom edge
  * her claw is within 25 px of the icon at the click
  * she's fully bent, reaching and poking, with wild hair
  * volts and afterimages were left behind
  * she comes back to exactly where she was
* 357 tests in all.
* Frame timings were measured, and the preview video was rendered from the
  real code.

**v1.6 checks:**
* The teleport test now checks that the full-body her stands beside the icon,
  on the taskbar's edge, fully bent over at the click, leaves a trail, and
  comes back to exactly where she was.
* A new test: full-size body even in compact / portrait.
* 357 tests in all, on Python 3.13 and 3.14.
* The preview video was rendered from the real code.

**v1.5 checks (26 more tests, 356 in all, on Python 3.13 and 3.14):**
* Forgiving small talk, and commands still winning over it.
* The local AI against a fake Ollama:
  * persona, emotion tag and tools sent
  * tool calls becoming Capri intents only (a made-up "run_shell" is dropped)
  * the info-tool loop
  * clear messages when Ollama or the model is missing
* Choosing between the AIs.
* Teleporting:
  * the right icon for each command
  * nothing happens until the "click"
  * no teleport for chat or the weather
  * she lands centred on the icon and comes back to exactly where she was
* Spotify typing into its search box, or falling back to Ctrl+L.
* The real app was started headless and shut down cleanly.

Rendered frames of the teleport were checked by eye.

Not testable here (Windows-only):
* finding taskbar icons through UI Automation
* typing into Spotify
* a real Ollama

**v1.4 checks (18 more tests, 330 in all, on Python 3.13 and 3.14):**
* Discord's button logic against a fake Discord that behaves like the real
  one (deafen mutes; unmuting while deafened undeafens). Each case gets exactly
  one press, "already" when nothing needs doing, and a check that the state
  changed.
* The router using the buttons, and falling back to keys.
* Spotify:
  * started when closed, searched once it's up
  * the best-matching Play pressed (not "Liked Songs", not a cover)
  * "Playing" only if the player really started.

The real UI Automation calls (`IUIAutomation` through comtypes) can't run here,
and Discord's / Spotify's button labels are their English ones.

**v1.3 checks (24 more tests, 312 in all, on Python 3.13 and 3.14):** mute /
unmute / deafen / undeafen phrasings and sound-alikes ("and mute me" = unmute);
unmute after she deafened you pressing undeafen, otherwise the mute key; search
phrasings with a site or browser; Opera started with the search address;
sites' own searches; falling back to the default browser.

**v1.2 checks (40 more tests, 288 in all, on Python 3.13 and 3.14):**
* Discord sound-alikes ("on meet on discord" → mute, "defend me" → deafen),
  and bare sound-alikes like "the fan" *not* counting.
* Reading Windows' app list:
  * web links and uninstallers are skipped
  * Store apps vs desktop apps told apart
  * a COM failure just means no extra apps
* "clip champ" / "power point" found by sound; launching via the Apps folder;
  closing a Store app by its WindowsApps folder.
* Folders and File Explorer; reveal for an app, a Store app and your own
  folder.
* The file finder skipping junk folders; documents opened by name, programs
  only shown, never started.

Not testable here (Windows-only):
* the real Applications-folder read (`Shell.Application` COM)
* `SHOpenFolderAndSelectItems`
* whether your speech model hears "unmute" exactly the way these lists expect.
  If she still misses it, the panel shows what she heard. Tell me and I'll add
  it.

**v1.1 checks (64 more tests, 248 in all):**
* Parsing:
  * shut down / restart / sleep / lock phrasings, and "shut down Discord"
    still closing the app
  * minimise all / this / an app, and bringing them back
  * mute / unmute / deafen / undeafen
  * "play X by Y", "songs by Y", "... on YouTube"
  * small-talk topics that never shadow a real command
* Shut down / restart / sleep happen **only after a spoken yes**. "No",
  mumbling and silence all keep the PC on, and an AI tool call still has to
  ask.
* Minimise all / app / restore, and Discord keys (its default keys in its
  window, your own keybind from anywhere, not running, closed to the tray).
* The Spotify artist search beating a cover version, and the router passing
  song and artist separately.
* Conversation: she listens for your answer after asking something, follows on
  ("how are you" → "good" → "Preem. Glad you're good."), goes quiet when you
  do, and stops after a few turns or when turned off.
* Start with Windows on by default exactly once (it stays off if you turn it
  off), with the `--startup` flag.
* The sign-in watcher, and the big greeting: centred, more than half the screen
  tall, caption shown, then back home with every extra window hidden.
* Hair red within a few shades of her body red.
* The clean Capri style adding no new frequencies (no ring-mod).
* The neural voice: blend, tape-style lift at the same length, "choom" said
  right, female voices only.
* The default voice choosing her neural voice, and a voice reload surviving
  new lines.

The neural voice was also run for real here, with the actual model files.
* A sentence takes ~1 s to synthesise on this CPU (the first one loads the model,
  done ahead of time at start-up).
* It uses about 260 MB of memory while loaded, and no CPU at rest.
* Sample renders of her new voice were made from the real pipeline.
* Animation frames of the big greeting were rendered and checked.

**Couldn't be tested here (Windows-only):** the real shutdown / sleep / lock
calls, minimising real windows, focusing Discord and whether Discord accepts the
injected key press, the sign-in / unlock notification, and the registry write
for Start with Windows. The code uses the documented Windows APIs for each:
* `shutdown.exe /s /t 0` from System32, and `SetSuspendState`
* `LockWorkStation`
* `ShowWindowAsync`
* `SetForegroundWindow` + `keybd_event`
* `WTSRegisterSessionNotification`
* the HKCU Run key

**Stage 6 checks:**
* The frozen app was built with `packaging\capri.spec` (here on Linux; same
  analysis) and started cleanly, with assets, Vosk's native library and the
  log file all working.
* A second launch handed over to the running one.
* Idle CPU was measured as above.
* The Windows-only parts weren't built here, because they need Windows:
  * the Inno Setup installer
  * the Windows version resource
  * comtypes/SAPI

Preview videos are rendered from the real code in `docs/`.

**Couldn't be tested here (needs your PC, accounts, or sites this sandbox
blocks):**

* Windows SAPI voices (Windows-only), and hearing the effects through real
  speakers.
* Real Spotify, Open-Meteo and Claude API calls. Only fakes of their
  documented responses were used. Spotify sign-in redirect handling was tested
  for real on 127.0.0.1.
* Piper neural voices (their download site is blocked here; the code matches
  piper-tts 1.8's API).
* Media keys (a Windows API).

Your earlier reports confirm the overlay, wake word, speech recognition and
app launching work on your PC.

## Credits

* Word list in `assets/words/english.txt` (used to tell when she misheard you): from
  [wordfreq](https://github.com/rspeer/wordfreq) by Robyn Speer, CC BY-SA 4.0.

## License

Capri's code is open source under the [MIT License](LICENSE). The Windows installer also bundles
other projects under their own licenses (two of them GPL-3.0), and the character art is fan art
that the MIT License doesn't cover. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
