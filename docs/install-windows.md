# Install Capri on Windows

Works on Windows 10 and 11. No installer, no admin rights, no Python needed.

## 1. Download her

1. Open the [latest release](https://github.com/kamome513/capri-companion/releases/latest).
2. Under **Assets**, click **`Capri.exe`** to download it.
3. Move it wherever you like: Desktop, Documents, a "Games" folder... That one file is the whole app.

## 2. Start her

Double-click `Capri.exe`. The first time each version runs, a small window shows her setting herself up
for a few seconds. After that she starts straight away.

She appears in the bottom-right corner of your screen. On the very first start she downloads her speech
model (about 40 MB, once).

## 3. "Windows protected your PC"

Windows shows this blue screen for any app that isn't code-signed (signing costs hundreds of euros a
year, so small open-source apps usually aren't). It doesn't mean anything was found in her.

1. Click **More info** (the small text under the message).
2. Click **Run anyway**.

You only have to do this once per version.

**"Smart App Control blocked this"** (Windows 11): this one has no *Run anyway* button. Smart App Control
blocks every unsigned app. You can turn it off in Windows Security → App & browser control → Smart App
Control settings, but Windows won't let you turn it back on without resetting Windows, so decide for
yourself.

## 4. If your antivirus deletes her

One-file apps that unpack themselves (like `Capri.exe`) sometimes get flagged by mistake, especially
right after a new version comes out.

**Windows Defender:**
1. Open **Windows Security** → **Virus & threat protection** → **Protection history**.
2. Click the entry for Capri → **Actions** → **Restore** (or **Allow on device**).

**Other antivirus apps** (Avast, AVG, Norton, Bitdefender...): open its quarantine / chest, restore
`Capri.exe`, and add it (or its folder) to the exceptions.

Why it's safe to allow: all her code is public on this GitHub, and every `Capri.exe` is built from that
code by GitHub itself (the *Actions* tab shows each build).

## 5. Let her hear you

If she never reacts to "Hey Capri":
1. Windows **Settings** → **Privacy & security** → **Microphone**.
2. Turn on **Microphone access** and **Let desktop apps access your microphone**.
3. Right-click Capri → **Voice** → **Microphone** and pick the mic you talk into.

## Updates

She updates herself. Once a day she checks GitHub for a new version and downloads it. The next time she
starts, the new version replaces that same `Capri.exe`, so your shortcuts and "Start with Windows" keep
working. You can also right-click her and click the update item when there is one.

Turn automatic updates off in Settings → **PC & chat** → **Updates**.

## Start her with Windows

Settings → **PC & chat** → **When you sign in** → tick **Start Capri with Windows**.

## The installer instead

Prefer a normal install with a Start-menu entry? Every release also has `Capri-Setup-<version>.exe`.
It updates itself the same way.

## Uninstall

1. Right-click her → **Exit Capri**.
2. Delete `Capri.exe` (or uninstall *Capri* in Windows Settings → Apps, if you used the installer).
3. To remove her settings and downloads too, delete the folder `%LOCALAPPDATA%\Capri` (paste that into
   the File Explorer address bar).
