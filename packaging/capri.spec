# PyInstaller spec for Capri.  Build with:  build.bat   (or: pyinstaller packaging/capri.spec)
# Produces dist/Capri/Capri.exe - a folder build (starts much faster than a one-file exe).

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from capri import __version__  # noqa: E402

datas = [(str(ROOT / "assets"), "assets")]
if (ROOT / "models").is_dir():                 # offline speech model (+ optional Piper voices)
    datas.append((str(ROOT / "models"), "models"))
binaries = []
hiddenimports = collect_submodules("anthropic")
hiddenimports += ["truststore", "certifi"]       # net.py imports them at start-up: secure downloads on every PC

# Vosk ships its native library (libvosk.dll) inside the package.
v_datas, v_binaries, v_hidden = collect_all("vosk")
datas += v_datas
binaries += v_binaries
hiddenimports += v_hidden
if sys.platform == "win32":
    hiddenimports += collect_submodules("comtypes")     # Windows voices (SAPI)

# Her neural voice (Kokoro): ONNX runtime + the espeak-ng phonemiser it ships with.
# Parakeet hearing (sherpa-onnx; the 480 MB model itself downloads from Settings).
for package in ("kokoro_onnx", "onnxruntime", "espeakng_loader", "phonemizer", "language_tags", "segments", "csvw",
                "sherpa_onnx"):
    try:
        p_datas, p_binaries, p_hidden = collect_all(package)
    except Exception:
        continue                                          # not installed: Capri falls back to Windows voices
    datas += p_datas
    binaries += p_binaries
    hiddenimports += p_hidden

if sys.platform.startswith("linux"):
    # Linux: talking to the desktop (X11) - python-xlib loads its extension modules by name.
    hiddenimports += collect_submodules("Xlib") + collect_submodules("capri.linux")
    hiddenimports += ["PySide6.QtDBus"]     # media players (Discord "Vibing to music"), lock screen greeting
    # The microphone / speaker library, so nothing has to be installed (capri/linux/audio.py finds it).
    import ctypes.util
    import glob
    for candidate in [ctypes.util.find_library("portaudio")] + glob.glob("/usr/lib/x86_64-linux-gnu/libportaudio.so.2*"):
        if candidate:
            path = candidate if os.path.isabs(candidate) else next(
                iter(glob.glob(f"/usr/lib/*/{candidate}") + glob.glob(f"/usr/lib/{candidate}")), "")
            if path and os.path.exists(path):
                binaries.append((os.path.realpath(path), "."))
                break

a = Analysis(
    [str(ROOT / "capri_launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "PIL", "scipy", "setuptools",
              "onnxruntime.transformers", "onnxruntime.quantization", "onnxruntime.tools"],   # model-making tools
    noarchive=False,
)
# Smaller download, nothing she uses: Qt's software-OpenGL fallback (~20 MB - she draws with plain QPainter),
# its spare display plugins (Windows uses qwindows) and Qt's own translations (her words are her own).
UNUSED = {"opengl32sw.dll", "qdirect2d.dll", "qoffscreen.dll", "qminimal.dll",
          "libqoffscreen.so", "libqminimal.so", "libqlinuxfb.so", "libqvnc.so", "libqvkkhrdisplay.so",
          "libqeglfs.so", "libqminimalegl.so"}
a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in UNUSED]
if sys.platform.startswith("linux"):              # the PortAudio copy under the name sounddevice looks for
    a.binaries = [(("libportaudio.so.2" if Path(dest).name.startswith("libportaudio.so") else dest), src, kind)
                  for dest, src, kind in a.binaries]
a.datas = [d for d in a.datas if "translations" not in Path(d[0]).parts]
# her neural voice speaks English: espeak's dictionaries for the 100+ other languages stay out (~18 MB)
a.datas = [d for d in a.datas if not (Path(d[0]).name.endswith("_dict") and "espeak-ng-data" in Path(d[0]).parts
                                      and Path(d[0]).name != "en_dict")]
pyz = PYZ(a.pure)

version_file = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    nums = tuple(int(n) for n in __version__.split(".")) + (0,)
    version_file = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", "Capri desktop companion"),
            StringStruct("ProductName", "Capri"),
            StringStruct("FileVersion", __version__),
            StringStruct("ProductVersion", __version__),
            StringStruct("OriginalFilename", "Capri.exe"),
        ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
    )

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Capri",
    console=False,                              # no console window; problems go to capri.log
    icon=str(ROOT / "assets" / "capri" / "icon.ico"),
    version=version_file,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Capri")
