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
  "Capri" voice (Kokoro, downloaded from Settings), raised a little, at a slightly quicker
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
