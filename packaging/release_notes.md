**Windows:** download `Capri-Setup-1.37.0.exe` below and run it. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed). If you have 1.36 or newer, Capri updates herself.

**Linux:** download `Capri-x86_64.AppImage` below, make it executable (right-click → Properties → Permissions → *Allow executing file as program*, or `chmod +x Capri-x86_64.AppImage`), and double-click it. Nothing to install. Instructions and troubleshooting are on the main page.

**New in 1.37: Capri works properly on Linux.**
- **Apps:** she opens and closes any app in your apps menu (including Flatpak and Snap), plus Steam, Lutris, Heroic and itch games.
- **Your PC:** she types into apps (any letter, even emoji), minimises windows and brings them back, sits on windows, and shuts down / restarts / sleeps / locks (asking first, as always).
- **Media and hotkeys:** media controls (pause, next, volume) and push-to-talk on Ctrl+Alt+C.
- **The screen:** "click subscribe" and "highlight ..." read the screen with Tesseract.
- **Voice and start-up:** she has a voice out of the box (espeak-ng; download her neural voice from Settings), starts when you log in if you want, greets you when you unlock, and turns into a drone when you play.
- **Wayland:** she runs through XWayland so she can stay in her corner. Bind `Capri-x86_64.AppImage --listen` to a keyboard shortcut for push-to-talk.
- **Updates:** the AppImage updates itself.

Running from the code? `./run.sh` now tells you exactly which packages your distro needs.
