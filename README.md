# Capri

A cyberpunk desktop companion. Capri stands in the corner of your screen, listens for
**"Hey Capri"**, and opens your apps and games, plays music, controls Discord, chats with you and more.
Everything she hears is processed on your PC.

---

## Windows

### Install (easiest)

1. Go to the [Releases page](https://github.com/kamome513/capri-companion/releases) and download
   `Capri-Setup-1.35.0.exe`.
2. Run it. It installs for your user only, with no admin rights and no Python needed.
3. If Windows shows **"Windows protected your PC"**, click **More info**, then **Run anyway**. The
   installer isn't code-signed, so Windows doesn't recognise it.
4. Capri starts in the bottom-right corner. On the first start she downloads her speech model
   (about 40 MB, once).
5. Say **"Hey Capri, open Chrome"** (or any app you have).

Works on Windows 10 and 11.

### Run from the code instead

1. Install [Python 3.10 or newer](https://www.python.org/downloads/). In its installer, tick
   **Add python.exe to PATH**.
2. Download this project (green **Code** button → **Download ZIP**) and unzip it.
3. Double-click `run.bat`. The first start takes a few minutes while it installs what she needs.

To make your own `Capri.exe` and installer, double-click `build.bat`. The installer step needs
[Inno Setup 6](https://jrsoftware.org/isdl.php).

---

## Linux

1. Install Python 3.10+ and PortAudio. On Debian/Ubuntu:
   `sudo apt install python3-venv libportaudio2`
2. Download this project and open a terminal in its folder.
3. Run `./run.sh`. It sets her up the first time, then starts her.

**What works on Linux:** her look and animations, "Hey Capri" and listening, her voices, chatting
and the AI, timers, weather, time and date, web searches and websites, and the Settings window.

**Windows only:** opening and closing installed apps and games, typing, minimising windows,
Discord controls, media keys, hotkeys, shutting down / restarting / sleeping / locking, clicking
things on your screen, game hype, and sitting on windows. On Linux she says "I can only do that on
Windows" instead of pretending.

**Tips:**
- She stays in her corner best in an **X11** session. On Wayland, apps can't place their own
  windows.
- Linux support hasn't been tried on a real Linux desktop yet, so expect rough edges.

---

## Manual

### Talking to her

Say **"Capri"** or **"Hey Capri"**, then what you want. You can say it in one breath ("Hey Capri,
open Chrome") or pause after her name. Her frame turns green while she's listening.

- **Push-to-talk:** press **Ctrl+Alt+C**, then speak. No wake word needed.
- **Type instead:** right-click her → **Chat with Capri...**
- **Two things at once:** "close Chrome and open Notepad", or "open Notepad then type hello".
- **Stop her talking:** "stop talking" / "shut up".
- **Cancel:** "never mind".

### What she does

**Apps, games and websites**

| Say | What happens |
|---|---|
| "open Chrome" / "launch Fortnite" / "start Minecraft" | Opens any app or game you have installed, or a website |
| "close Chrome" / "quit Fortnite" | Closes it. For games she asks "yes or no?" first |
| "open YouTube" / "open twitch dot tv" | Opens the website |
| "search for easy pasta recipes" / "search YouTube for lofi" | Web search (Google, YouTube, Reddit, Wikipedia...) |
| "go into search mode" | She keeps asking what to search next |
| "show me Chrome in File Explorer" / "open my downloads" | Opens the folder |
| "switch tabs on Chrome" / "play the video" | Browser tabs and the video on the page |

**Music**

| Say | What happens |
|---|---|
| "play Bohemian Rhapsody by Queen" | Plays the song (Spotify by default) |
| "play lofi on YouTube" / "on SoundCloud" | Plays it on another music app, just this once |
| "change music to SoundCloud" | Changes where "play ..." goes from now on |
| "pause" / "resume" / "next song" / "previous song" | Controls whatever is playing |
| "turn it up" / "turn it down" | Volume |
| "what's playing?" | Song and artist (needs Spotify connected in Settings) |

**Discord**

| Say | What happens |
|---|---|
| "mute me" / "unmute me" / "deafen me" / "undeafen me" | Mute and deafen, even mid-game without tabbing you out |
| "join call" | Joins the voice channel you saved in Settings |
| "leave call" | Leaves the call |

**Your PC**

| Say | What happens |
|---|---|
| "minimise everything" / "bring them back" | Hides all windows, then restores them |
| "minimise Chrome" / "minimise this" | Minimises one window |
| "lock my PC" | Locks it |
| "shut down" / "restart" / "put my PC to sleep" | Asks you first. Only a clear "yes" does it |
| "take a screenshot" / "screenshot this window" | Saves it to Pictures\Screenshots |
| "what's using all my RAM?" / "how much storage is left?" / "battery?" | Live PC stats |
| "type hello in Notepad" / "type hello" | Types it for you. She never presses Enter |
| "click subscribe" / "click that" | Clicks a button you can see on screen |
| "highlight hello" / "copy that" / "right click that" / "scroll down" | Hands on your screen |

**Timers, time and weather**

| Say | What happens |
|---|---|
| "set a timer for 5 minutes" / "wake me up at 7:30" | Timers and alarms |
| "how long is left?" / "cancel the timer" | Checks or stops it |
| "what time is it?" / "what's the date?" | Time and date |
| "what's the weather?" / "tomorrow" / "in Tokyo" | Weather (set your home city in Settings) |
| "is it going to rain?" | Chance of rain |

**Chatting**

Just talk: "how are you", "tell me a joke", "what is a black hole", "flip a coin", "what's 12 times 8".
She has her own chatbot that always answers. If you add an AI in Settings (ChatGPT, Gemini,
Claude, Ollama...), she chats like a real conversation.

**Her memory of you (private)**

| Say | What happens |
|---|---|
| "my name is Alex" / "I love pizza" / "my favourite movie is Shrek" / "I'm from London" | She remembers it |
| "remember that my exam is Friday" | She remembers that too |
| "what's my name?" / "what do you know about me?" | She tells you |
| "forget that I love pizza" | Forgets one thing |
| "forget everything about me" | Asks first, then deletes it all |

It's saved only on your PC. Personal things are answered by her own chatbot and never sent to the
AI, unless you tick *Let the AI know what Capri remembers about me* in Settings → Assistant.

**Teaching her**

| Say | What happens |
|---|---|
| "when I say study time, open Chrome and Notepad" | Your own shortcut |
| "forget the shortcut study time" | Deletes it |
| "when I say note bad I mean Notepad" | Fixes a word she keeps mishearing |
| "this button makes me skip ad" (pointing at it with the mouse) | She learns that button |
| "forget the skip ad button" | Forgets it |

**Her look and mood**

| Say | What happens |
|---|---|
| "be sarcastic" / "be sweet" / "what's your personality?" | Changes how she talks |
| "talk faster" / "talk slower" / "talk louder" / "talk softer" / "talk higher" / "talk lower" | Changes her voice |
| "change your hair" | Swaps between her two hairstyles |
| "lie down" / "get up" | Lies on her panel, or stands up |
| "sit on my window" / "stop sitting on windows" | She sits on top of the window you're using |
| "go to the bottom left" | Moves her to another corner |
| "compact mode" / "normal size" | Small or normal size |
| "hide" / "come back" | Hides her (she still listens) |
| "drone mode" / "normal mode" | Turns her into a little flying drone, and back |
| "turn on game hype" / "turn off game hype" | Cheers when you get kills |
| "repeat what I said" / "say that again" | Repeats you, or herself |
| "open your settings" | Opens her Settings |

### Right-click menu (or the tray icon by the clock)

| Item | What it does |
|---|---|
| **Hide Capri** | Hides her until you show her again (clicking the tray icon does too) |
| **Chat with Capri...** | A window to type to her |
| **Listen now** | Push-to-talk: she listens for one command (Ctrl+Alt+C) |
| **Voice → Voice activation** | Listen for "Hey Capri". Off closes the microphone (push-to-talk still works) |
| **Voice → Mute microphone** | Fully closes the mic. Nothing can open it, not even push-to-talk |
| **Voice → Spoken replies** | She talks out loud, or only writes |
| **Voice → Microphone** | Pick which microphone she uses |
| **Capri → Design** | Her art style (full body, portrait, classic, or an animated picture) |
| **Capri → Lie on the panel** | She lies on top of her message panel |
| **Capri → Sit on windows** | She hops onto the window you're using |
| **Capri → Compact mode** | Small Capri, one-line panel |
| **Capri → Hair** | "Like the show" or "Classic spiky" |
| **Capri → Personality** | Edgerunner, Sarcastic, Silly, Tsundere, Sweet, Deadpan, Gremlin, Hype, Kuudere |
| **Capri → Do something** | Glitch, play a game, watch something, or call D |
| **Panel → Show status panel** | Her message panel on or off |
| **Panel → Show activity log** | The log lines under her message |
| **Panel → Activity log style** | Log inside the panel, or as call cards above it |
| **Drone → Drone mode now** | Turn into the little drone right now |
| **Drone → Drone mode when I'm in a game** | Turn into the drone automatically while you play |
| **Drone → Look** | Disk or Mask (green visor) |
| **Window → Always on top** | Keep her above other windows |
| **Window → Click-through** | Clicks go straight through her (Ctrl+Alt+Shift+C toggles it) |
| **Window → Reset position** | Back to the bottom-right corner |
| **Start with Windows** | Starts Capri when you sign in |
| **Settings...** | Opens Settings (below) |
| **Open log folder** | Opens `capri.log`, handy if something goes wrong |
| **Exit Capri** | Quits |

You can **drag** Capri or her panel anywhere, on any monitor.

### Settings

**Apps tab:** the apps and games she opens and closes by name.

| Button / column | What it does |
|---|---|
| **Name (say this)** | What you say: "open *Name*" |
| **Also say** | Other words for it, separated by commas (e.g. *my browser* for Chrome) |
| **Type** | Program, Steam game, or Website / link |
| **Where it is** | The program's path, the Steam game's number, or the link |
| **Found?** | ✓ she can find it, ✗ it's missing (and why), • she'll look it up in the Start menu |
| **Add app or game...** | Pick from everything installed on your PC. Tick as many as you like |
| **Add my games** | Adds every game you've downloaded (Steam, Epic, Xbox, Riot, GOG, EA, Ubisoft...) |
| **Change path...** | Point the selected app at a different program file |
| **Remove** | Takes the selected app off the list |
| **Test launch** | Opens the selected app now |
| **Show advanced** | Shows arguments, process names, and what "close" does (like clicking X / ask me first / force quit) |
| **Save** | Saves your changes |
| **Try a command** | Type what you'd say and see what she'd do. Nothing actually runs |

**Found on this PC tab:** everything she can open without setup. **Rescan** looks again after you
install something.

**Wake word tab:** how she hears you.

| Button / setting | What it does |
|---|---|
| **Wake word confidence** | Higher = fewer false wake-ups. Lower = she hears you more easily |
| **Teach her your voice** | Say "Hey Capri" 4 times so she learns how you say it |
| **Download the more accurate speech model** | Better understanding (128 MB) |
| **Hearing** | Vosk (quick and light), Parakeet (best for heavy accents) or Whisper |
| **Download Parakeet** | Gets the accent-friendly model (480 MB, once). Runs offline. Uses about 900 MB of RAM, freed while you game |
| **Install Whisper** | Another accent-friendly option |
| **Clean up my mic** | Turns a quiet mic up and cuts rumble and hiss |
| **Push-to-talk / Click-through hotkey** | Change the keyboard shortcuts |
| **Apply** | Uses the changes |
| **Fix what she mishears** (Add / Remove / Fix what she just heard) | "When she hears *note bad*, read it as *notepad*" |

**Character tab:** her look.

| Setting | What it does |
|---|---|
| **Style** | Full body, portrait, classic, or an animated picture. Drop your own pictures in the `looks` folder |
| **Hair** | Like the show, or Classic spiky |
| **In games** | Stay herself over the game, or turn into the drone |
| **Drone look** | Disk or Mask |
| **Idle animation** | Breathing, blinking, looking around |
| **Lie on the panel** / **Sit on windows** / **Idle activities** | Same as in the right-click menu |

**Assistant tab:** her voice, weather, music and AI.

| Button / setting | What it does |
|---|---|
| **Spoken replies** | Talk out loud or not |
| **Night City slang** | "Preem, choom." On or off |
| **Personality** | How she talks |
| **Voice** | Her neural "Capri" voice, Windows voices, ElevenLabs or beeps |
| **Download Capri's voice** | Her neural voice (120 MB, once) |
| **ElevenLabs key / voice** | Use an ElevenLabs voice (needs their key) |
| **Style, Volume, Speed, Pitch, Expression** | Tune how she sounds |
| **Test voice** / **Capri preset** | Hear her / reset to her default sound |
| **Home city, Units, Test weather** | For "what's the weather" |
| **Play music on** | Spotify, YouTube Music, SoundCloud, YouTube... |
| **Client ID, Connect, Disconnect, Test Spotify** | Connect Spotify (Premium) so she can start exact songs and say what's playing |
| **Chatbot** | Chat with her about anything |
| **AI, Address, Model, API key** | Pick an AI and paste its key. A free Google Gemini key works |
| **Test AI** / **Last try** | Checks the AI works, and shows what happened last time |
| **Let the AI know what Capri remembers about me** | Off by default: your memory stays on your PC |
| **She knows** / **Forget everything about me** | What she remembers, and a button to wipe it |
| **Save** | Saves your changes |

**PC & chat tab:**

| Setting | What it does |
|---|---|
| **Keep chatting** | After she asks you something, she listens for the answer without "Hey Capri" |
| **Red lag lightning** | Her zap effects when she presses Discord buttons or closes windows |
| **Greet me when I sign in** / **Big, in the middle** / **Preview greeting** | Her hello when you sign in or wake the PC |
| **Start Capri with Windows** | Same as the menu item |
| **Game hype** (cheer for kills, say something when I die, watch my screen, encourage me) / **Preview** | Hype while you play: CS2, Dota 2 and League directly, any game by reading your screen |
| **Toggle Mute / Deafen keybind** | Your Discord keybinds, if you changed Discord's defaults |
| **Your voice channel** / **Leave call keybind** / **Join it now** | For "join call" and "leave call". Right-click the channel in Discord → Copy Link |
| **Save** | Saves your changes |

### Privacy

- She only listens for "Hey Capri". That runs on your PC, and audio is never recorded or uploaded.
- Your settings, apps list and memory of you are kept in your own user folder
  (`%LOCALAPPDATA%\Capri` on Windows). Delete `settings.json` there to reset her.
- Only what you say to the AI (if you set one up) goes to that AI. Personal things don't, and your
  Windows user name is removed from anything that does.
- She never runs commands an AI makes up. She can only do the fixed actions in this manual, and
  shutting down, restarting or sleeping always asks you first.

### Something wrong?

| Problem | Fix |
|---|---|
| She doesn't react to "Hey Capri" | Check the right microphone is picked (right-click → Voice → Microphone). Try **Teach her your voice**, or lower the wake word confidence |
| She wakes up by mistake | Raise the wake word confidence |
| She mishears your accent | Settings → Wake word → **Download Parakeet**, then pick it under Hearing |
| She can't find an app | Settings → Apps → **Add app or game...**, or add what she hears to **Also say** |
| "Mute me" doesn't work | Put your Discord keybinds in Settings → PC & chat. Don't run Discord "as administrator" |
| Her voice sounds robotic | Settings → Assistant → **Download Capri's voice** |
| She vanished | Click the tray icon by the clock, or start Capri again |
| Can't click her | Click-through is on: press Ctrl+Alt+Shift+C |
| Anything else | Right-click → **Open log folder** and look at `capri.log` |

---

## License

Capri's code is open source under the [MIT License](LICENSE). The installer also bundles other
projects under their own licenses, and the character art is fan art that the MIT License doesn't
cover. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
