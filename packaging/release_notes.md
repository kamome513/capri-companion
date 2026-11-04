**Windows:** download **`Capri.exe`** below. That one file is the whole app: put it anywhere and double-click it. If you already have Capri, she updates herself. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (it isn't code-signed). `Capri-Setup-2.2.0.exe` is still here too.

**Linux:** download `Capri-x86_64.AppImage` below, make it executable (right-click → Properties → Permissions → *Allow executing file as program*), and double-click it. If you have 1.37.0 or newer, it updates itself.

**What's in this one**
- **"AI error 400" fixed.** She now reads every AI service's error properly (NVIDIA's included), and fixes what it complains about by herself: a setting it doesn't take, a broken chat history, or tools it doesn't support. If it still can't answer, she tells you the actual reason.
- **"What do you see?" works with any AI.** If your model can't look at pictures, she uses that service's own model that can (NVIDIA, Groq, Mistral, xAI, OpenAI, OpenRouter, Gemini). She looks at the monitor your window is on, and if the screenshot comes out black (a game in exclusive fullscreen, or Wayland) she tries the window itself, then tells you why instead of sending the AI a black picture.
- **Fish Audio sounds like it does on their site.** Capri asks for Fish's full-quality voice instead of the faster, rougher one, and keeps the speed and volume steady instead of changing them with her mood.
- **Her tools:**
  - "Put Chrome on the left and Discord on the right", "Spotify full screen", "Chrome and Discord side by side".
  - "Turn Discord down", "make Spotify louder", "set Chrome to 30%": only that app's volume.
  - "Why is my game lagging?": CPU, memory, graphics card, heat, disk and ping, with the most likely cause first.
  - "How's my internet?": ping and a quick download speed test.
  - Your AI can now also set timers, arrange windows, change one app's volume and change her own settings (size, text box, music bar, roaming, glitches...) when you ask it to.
- **She vibes to your music.** While music plays she bounces and sways to it, and stops when you pause. Turn it off in Settings → Extras.
- **The music bar's pause button** switches to play straight away, and the bar waits for you while it's paused.
- **If she crashes**, she says so the next time she starts and tells you where `crash.log` is, so it can be sent in and fixed.

Join the Capri Discord: https://discord.gg/FBxdDSCaA7
