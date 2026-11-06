# Install Capri on Linux

Runs on most 64-bit distros from the last few years: Ubuntu 22.04+, Linux Mint 21+, Debian 12+,
Fedora 36+, Arch, Pop!_OS, openSUSE and others.

## 1. Download and start her

1. Open the [latest release](https://github.com/kamome513/capri-companion/releases/latest) and download
   **`Capri-x86_64.AppImage`**.
2. Make it runnable: right-click it → **Properties** → **Permissions** → tick **Allow executing file as
   program**. Or in a terminal: `chmod +x Capri-x86_64.AppImage`
3. Double-click it.

She adds herself to your apps menu. On the first start she downloads her speech model (about 40 MB, once).
Keep the AppImage in a folder you own (your home folder, Downloads, `~/Applications`) so she can update it.

## If it doesn't open

- **Ubuntu 24.04 and newer:** `sudo apt install libfuse2t64`
- **Older Ubuntu / Debian:** `sudo apt install libfuse2`
- Or skip FUSE entirely: `./Capri-x86_64.AppImage --appimage-extract-and-run`

## Optional extras

- **Her proper voice:** Settings → **Assistant** → **Download Capri's voice** (120 MB, once). Until then she
  uses espeak-ng.
- **Reading the screen** ("click subscribe"): `sudo apt install tesseract-ocr` (or `dnf` / `pacman`).
- **Media controls:** install `playerctl`.

## X11 and Wayland

On **X11** everything works. On **Wayland** she runs through XWayland and still stands in her corner, but
Wayland doesn't let apps control other apps' windows:
- **Typing** needs `wtype` (Sway, Hyprland...) or `ydotool`.
- **Sitting on windows, minimising and clicking things** only work with apps that also run through
  XWayland (many games, Steam and Discord do).
- **Push-to-talk:** add a keyboard shortcut in your desktop settings that runs
  `/path/to/Capri-x86_64.AppImage --listen`.

For everything, pick an **X11 / Xorg** session on your login screen (the gear icon).

## Uninstall

Exit her (right-click → **Exit Capri**), delete the AppImage, and delete `~/.config/Capri` to remove her
settings and downloads.
