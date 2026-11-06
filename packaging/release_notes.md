**Windows:** download **`Capri.exe`** below. That one file is the whole app: put it anywhere and double-click it. If you already have Capri, she updates herself. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (it isn't code-signed). `Capri-Setup-2.3.6.exe` is still here too.

**Linux:** download `Capri-x86_64.AppImage` below, make it executable (right-click → Properties → Permissions → *Allow executing file as program*), and double-click it. If you have 1.37.0 or newer, it updates itself.

**2.3.6: scrolling in Settings no longer crashes Capri.** The 2.3.2 fix that stopped scrolling from changing settings also caught the page's own scroll bar, which then passed the scroll to itself over and over until Capri crashed. Fixed.

**2.3.5: games.**
- **Tell her what to do in the game.** While a game is in front, "turn around", "turn left", "look up", "jump", "go forward", "go back", "crouch", "mine that", "place a block", "open inventory" and "slot 3" happen in the game.
- **"Play minecraft" / "play the game" / "play for me" make her play the game** in front - no more Spotify playing a song called "Minecraft". "Play minecraft for me" works from anywhere.
- Minecraft is recognised from any launcher (CurseForge, Prism...), by its window.
- If your game shows up black to her (exclusive fullscreen), she says so and tells you the fix (windowed or borderless) instead of playing blind.
- Every step she takes while playing goes in her log (what the AI saw and decided, each key and click), so when she gets stuck it's clear why.

**2.3.4: lots of new things.**
- **She plays Minecraft properly.** In games that steer the camera with the mouse she now clicks where the crosshair is instead of moving the pointer (that yanked the view), holds the button to mine, walks and turns at the same time, and knows the Minecraft basics. Minecraft from the Microsoft Store launcher counts as a game now too.
- **Her little pink cursor** shows where she's about to click or type, whenever she does something on screen.
- **Drop a file on her** (text, Word, PDF or a picture) and she tells you what's in it. Only your AI reads it, and nothing written in a file can make her do anything.
- **Reminders on a day or at a time** that survive a restart: "remind me tomorrow at 9 to call mum", "remind me on the 5th of December to pay rent".
- **Quiet mode** (Ctrl+Alt+P, right-click → Quiet mode, or say "quiet mode"): no comments by herself - she still answers you.
- **New hotkeys:** Ctrl+Alt+H hides or shows her, Ctrl+Alt+T opens the chat box from anywhere.
- **She naps** when you've been away 10 minutes, and wakes up when you're back (Settings → Extras).
- **Rock paper scissors:** "let's play rock paper scissors".
- **She warns you** when your PC is almost out of memory or disk space (Settings → Extras).
- **"Playing Roblox with Capri" works**, also with Bloxstrap or Fishstrap. If Bloxstrap's own *Show game activity* is on, Discord may show that one instead: turn it off in Bloxstrap → Integrations.
- **Typing once, not twice** (some apps, like Windows 11 Notepad, got your text twice).
- She's smaller when she sits on a window, with a normal foot.
- New voice style: **Studio (clean and clear)**, in Settings → Assistant → Style.

**2.3.3: her old sitting pose is back.** When she sits on a window she uses her drawn sitting picture again, like before 2.3.2.

**2.3.2: her own voice in all 25 languages.** Her neural voice used to speak only Spanish, French, Italian and Portuguese (with a different speaker); everything else fell back to a robotic voice. Now she speaks every language in her own voice, with that language's pronunciation. Also fixed: the Windows app was missing the pronunciation data for every language but English, which also made her hearing guess "English" more often.

**2.3.2 also:**
- **Scrolling in Settings no longer changes settings** when the mouse passes over a drop-down, a slider or a number box.
- **ElevenLabs "error 400" fixed:** she now repairs the request by herself, accepts a pasted voice link as well as the ID, and shows ElevenLabs' actual reason if it still fails.
- **Guides:** step-by-step [guides](https://github.com/kamome513/capri-companion/blob/main/docs/README.md) for installing her (and the "Windows protected your PC" screen), the AI, ElevenLabs, Fish Audio, languages, Discord and games. Right-click her → **Guides and help**.
- **Change what she hears without changing her voice:** Settings → Wake word → "Keep her voice when I change language".
- **Compact mode keeps her normal size**; it only makes her text box smaller. Her text box grows and shrinks with her Size.
- **Text box only when she's activated:** right-click her → **Panel → Text box opens** → *Only when you say her name* (or always, when she has something to say, or never).
- No more thin gap between her head and her hair.

**2.3.1: no more "error 400" when she plays your game or looks at your screen with the free local AI.** "Set up your brain" gives her llama3.2, which can't see pictures, so every look failed with a bare 400. Now she uses a model you have that can see (gemma3, llava, qwen2.5vl...), and if you don't have one she tells you so plainly: say **"give yourself eyes"** and she downloads gemma3 into Ollama (about 3 GB, once). Any other refusal now shows the actual reason instead of just a number.

**2.3.1 also:**
- **She talks again.** Some voices (Fish Audio especially) send their audio in a way Capri read as "no sound", so she showed her reply, said nothing and went back to listening. Fixed - and if an online voice ever sends nothing, her own voice says it instead.
- **See everything she says.** Long replies show in full in her text box (it grows), and the things she says by herself - game hype, comments on your screen, "ow!" - show there too, word by word as she says them.
- **Language button:** right-click her → **Language** to switch between her 25 languages.

**Capri 2.3: Capri speaks your language.** 25 of them: Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Russian, Slovak, Slovenian, Spanish, Swedish and Ukrainian.
- Pick yours in **Settings → Wake word → Language**, or say "speak German", "switch to French"...
- **She hears you** in it with NVIDIA's Parakeet v3 speech model (about 490 MB, downloaded once, runs on your PC). You still wake her with "Hey Capri".
- **Everyday commands work by themselves** in every one of these languages: open and close apps, play, pause, next, previous, louder, quieter, the time, the weather, screenshots. With an AI set up, she understands everything you say and answers in your language.
- **She talks in it.** Her neural voice speaks Spanish, French, Italian and Portuguese; for the others she uses a Windows voice for that language if you have one installed, or espeak-ng. ElevenLabs and Fish Audio voices speak them all.
- **Her own lines are in your language too** when an AI is set up: each one is translated the first time and remembered on your PC.

**Discord: "Playing Deadlock with Capri".** While you're in a game, her Discord status now says what you're playing, with Capri (the name comes from your Steam library, or the game's own program). Your friends see it right in the member list.

**Fixes**
- She stays in her corner. Roaming is off now unless you turn it on (Settings → Extras), and even then she never teleports while she's doing something for you, for a minute after, or while you're in a game, and she always comes back to her spot.
- Her voice no longer breaks up while a game is loading: when the PC is busy she gets the whole line ready before she starts talking.
- "What do you see?" and "play this for me" work with more AIs: some picture models refuse a separate system message next to a picture, so she asks those in one message instead.
- Throwing her into a wall no longer leaves two of her on screen (one at the wall and one back in her corner) when her text box is set to pop up.
- ElevenLabs: when your plan won't let Capri use the voice you picked (free plans can't use voices from the Voice Library), she uses ElevenLabs' own default voice instead of failing, and any other refusal shows ElevenLabs' actual reason.

Join the Capri Discord: https://discord.gg/FBxdDSCaA7
