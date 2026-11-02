**Download `Capri-Setup-1.36.3.exe` below and run it.** It installs for your user, with no admin rights or Python needed (Windows 10/11). If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed).

**Fixed in 1.36.3:**
- **Gemini (2.5 and newer) works.** Google refused the list of things Capri can do (her "tools"), so every Gemini model failed. She now sends each AI a version it accepts. If a model can't do tools at all (some OpenRouter, DeepSeek, LM Studio and Ollama models), she just chats with it.
- **"Thinking" models no longer reply with nothing.** If a model spends its whole answer allowance thinking, Capri asks again.
- **No more reinstalling every time you open Capri.** An update that doesn't take is tried at most twice, then she tells you. The installer waits until Capri has fully closed, and it updates the copy you actually run.
- **"Check for updates" works again.** It no longer relies on GitHub's rate-limited API, and if it can't check it says why.
- **Restart Capri.** Right-click her → **Restart Capri**, Settings → PC & chat → **Restart Capri**, or say "restart yourself". A downloaded update installs while she restarts.

If you're on 1.36.0–1.36.2 and the update keeps reinstalling, install this one by hand once.
