# Something wrong?

## Her log folder

Right-click her → **Open log folder**. Inside:
- `capri.log` - what she's been doing (the newest lines are at the bottom).
- `crash.log` - only there if she crashed. She tells you the next time she starts.

It's `%LOCALAPPDATA%\Capri` on Windows and `~/.config/Capri` on Linux. When you ask for help in the
[Capri Discord](https://discord.gg/FBxdDSCaA7), send these two files.

## Common problems

| Problem | Fix |
|---|---|
| "Windows protected your PC" | **More info** → **Run anyway**. See [Install on Windows](install-windows.md) |
| Antivirus deleted Capri.exe | Restore it from quarantine and allow it. See [Install on Windows](install-windows.md#4-if-your-antivirus-deletes-her) |
| She doesn't react to "Hey Capri" | Right-click → **Voice** → **Microphone**: pick yours. Allow desktop apps to use the mic in Windows. Try **Teach her your voice**, or lower **Wake word confidence** (Settings → Wake word) |
| She wakes up by mistake | Raise **Wake word confidence** |
| She mishears you | Settings → **Wake word** → **Hearing** → **Parakeet**. **Clean up my mic** helps quiet mics |
| She talks but you can't hear her | Check the volume slider (Settings → Assistant), and that Windows' sound mixer hasn't muted Capri |
| Her voice sounds robotic | Settings → **Assistant** → **Download Capri's voice** |
| Changing language changed her voice | Settings → **Wake word** → tick **Keep her voice when I change language** |
| "AI error 400" / "it turned that down" | She retries by herself first. If it keeps happening, the reason she reads out says why: usually the model can't see pictures or use her tools. Pick another model. See [Set up her AI](ai.md#when-something-goes-wrong) |
| ElevenLabs / Fish Audio errors | See [ElevenLabs](voice-elevenlabs.md#if-it-doesnt-work) / [Fish Audio](voice-fish-audio.md#if-it-doesnt-work) |
| "Mute me" doesn't work | Set your Discord keybinds in both apps. See [Discord](discord.md). Don't run Discord as administrator |
| A download fails ("certificate verify failed") | Your antivirus is scanning HTTPS. Allow Capri, or turn off its "HTTPS scanning" / "web shield" for a minute |
| She can't find an app | Settings → **Apps** → **Add app or game...**, or add what she hears to **Also say** |
| Your game looks black to her | Switch the game to **borderless** / windowed fullscreen |
| Scrolling in Settings changed a setting | Fixed in 2.3.2: update her |
| She vanished | Click her icon by the clock, or start Capri again. Right-click → **Reset position** |
| You can't click her | Click-through is on: press **Ctrl+Alt+Shift+C** |
| Reset everything | Exit her and delete `settings.json` in her log folder |
