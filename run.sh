#!/usr/bin/env bash
# Linux: checks what Capri needs, creates a local Python environment on first run, then starts her.
#   ./run.sh                start Capri
#   ./run.sh --listen       tell the running Capri to listen (bind this to a keyboard shortcut on Wayland)
# Easiest of all: the AppImage from the Releases page needs none of this.
set -e
cd "$(dirname "$0")"

# -- what your system needs (only checked, never installed for you) --------------------------------
missing_pkgs=()
need() {   # need <what it's for> <check command...> -- debian fedora arch suse package names
    local why="$1"; shift
    local check=()
    while [ "$1" != "--" ]; do check+=("$1"); shift; done
    shift
    if ! "${check[@]}" >/dev/null 2>&1; then
        missing_pkgs+=("$why|$1|$2|$3|$4")
    fi
}
has_lib() { ldconfig -p 2>/dev/null | grep -q "$1" || ls /usr/lib*/"$1"* /usr/lib/*/"$1"* >/dev/null 2>&1; }

need "Python 3.10+"              python3 -c 'import sys; assert sys.version_info >= (3, 10)' -- python3 python3 python python3
need "Python venv"               python3 -c 'import venv, ensurepip'                        -- python3-venv python3 python python3
need "microphone + speaker"      has_lib libportaudio.so.2                                   -- libportaudio2 portaudio portaudio portaudio
need "her window (Qt xcb)"       has_lib libxcb-cursor.so.0                                  -- libxcb-cursor0 xcb-util-cursor xcb-util-cursor libxcb-cursor0

if [ ${#missing_pkgs[@]} -gt 0 ]; then
    echo "[capri] A few system packages are missing:"
    deb=(); fed=(); arch=(); suse=()
    for item in "${missing_pkgs[@]}"; do
        IFS='|' read -r why d f a s <<< "$item"
        echo "   - $why"
        deb+=("$d"); fed+=("$f"); arch+=("$a"); suse+=("$s")
    done
    if command -v apt >/dev/null; then echo "  Install them with:  sudo apt install ${deb[*]}"
    elif command -v dnf >/dev/null; then echo "  Install them with:  sudo dnf install ${fed[*]}"
    elif command -v pacman >/dev/null; then echo "  Install them with:  sudo pacman -S ${arch[*]}"
    elif command -v zypper >/dev/null; then echo "  Install them with:  sudo zypper install ${suse[*]}"
    fi
    echo "  Then run ./run.sh again."
    exit 1
fi

# Nice to have (she says what's missing when you use it):
optional=""
command -v tesseract >/dev/null || optional="$optional tesseract-ocr(\"click subscribe\": reading the screen)"
command -v playerctl >/dev/null || optional="$optional playerctl(pause/next for any player)"
if [ -n "$optional" ]; then
    echo "[capri] Optional extras not installed:$optional"
fi

# -- Wayland: Capri runs through XWayland (she needs to place her own windows) ----------------------
if [ -z "$QT_QPA_PLATFORM" ] && { [ -n "$WAYLAND_DISPLAY" ] || [ "$XDG_SESSION_TYPE" = "wayland" ]; } && [ -n "$DISPLAY" ]; then
    export QT_QPA_PLATFORM=xcb
fi

# -- her Python environment -------------------------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/requirements.installed
fi
# Her neural voice. Optional: without it she uses espeak-ng's voice, beeps or ElevenLabs.
if ! cmp -s requirements-voice.txt .venv/voice.installed; then
    if .venv/bin/python -m pip install -r requirements-voice.txt && \
       .venv/bin/python -m pip install --no-deps --ignore-requires-python "kokoro-onnx>=0.5,<1"; then
        cp requirements-voice.txt .venv/voice.installed
    else
        echo "[capri] Couldn't install her neural voice - she'll use another voice for now."
    fi
fi
# Parakeet hearing's engine (optional, ~20 MB): best for strong accents.
if [ ! -f .venv/hearing.installed ]; then
    .venv/bin/python -m pip install "sherpa-onnx>=1.12" && touch .venv/hearing.installed || \
        echo "[capri] Couldn't install Parakeet's engine - Vosk will hear you."
fi
# Qt's X11 libraries (a desktop normally has them; a minimal install may not): check what's really missing.
qxcb=$(.venv/bin/python -c "import PySide6, os; print(os.path.join(os.path.dirname(PySide6.__file__), 'Qt', 'plugins', 'platforms', 'libqxcb.so'))" 2>/dev/null || true)
if [ -n "$qxcb" ] && [ -f "$qxcb" ] && ldd "$qxcb" 2>/dev/null | grep -q "not found"; then
    echo "[capri] Qt needs a few X11 libraries that aren't installed:"
    ldd "$qxcb" | grep "not found" | awk '{print "   - " $1}' | sort -u
    if command -v apt >/dev/null; then
        echo "  Install them with:  sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 libxcb-image0 libxcb-render-util0 libxcb-shape0 libxcb-randr0 libxcb-xinerama0"
    elif command -v dnf >/dev/null; then
        echo "  Install them with:  sudo dnf install xcb-util-cursor libxkbcommon-x11 xcb-util-wm xcb-util-keysyms xcb-util-image xcb-util-renderutil"
    elif command -v pacman >/dev/null; then
        echo "  Install them with:  sudo pacman -S xcb-util-cursor libxkbcommon-x11 xcb-util-wm xcb-util-keysyms xcb-util-image xcb-util-renderutil"
    elif command -v zypper >/dev/null; then
        echo "  Install them with:  sudo zypper install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-image0 libxcb-render-util0"
    fi
    exit 1
fi
case " $* " in
    *" --listen "*|*" --toggle-click-through "*) ;;          # just a message to the running Capri
    *)
        .venv/bin/python tools/download_model.py
        [ -f models/kokoro/kokoro-v1.0.int8.onnx ] || .venv/bin/python tools/download_voice.py || true
        ;;
esac
exec .venv/bin/python -m capri "$@"
