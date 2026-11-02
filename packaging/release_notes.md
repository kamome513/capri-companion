**Download `Capri-Setup-1.36.2.exe` below and run it.** It installs for your user, with no admin rights or Python needed (Windows 10/11). If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed). If you already have 1.36.0 or newer, Capri updates herself.

**Fixed in 1.36.2:**
- **"The hey Capri" wakes her.** A breath or an "uh" before her name often gets heard as "the", "a", "uh" or "okay", and she ignored it. One little word in front of her name now still counts. "I went to Capri" still doesn't wake her.
- **Commands that start with "the"** ("the open Discord") work too.
- **"Download Parakeet" failing with CERTIFICATE_VERIFY_FAILED.** Capri now checks secure connections the way Windows and your browser do. That fixes downloads (Parakeet, her voice, the speech model, updates) on PCs with antivirus that scans HTTPS. If a download still fails, she says why in plain words.
- **A tidier Wake word page.** Pick a Hearing type and only its options show (Parakeet: just the Download button). The installed app no longer offers a Whisper install it can't do.
