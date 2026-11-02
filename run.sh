#!/usr/bin/env bash
# Linux: creates a local virtual environment on first run, then starts Capri.
# Needs Python 3.10+ and PortAudio (Debian/Ubuntu: sudo apt install python3-venv libportaudio2).
# Windows-only parts (opening your installed apps, typing, window and Discord control, media keys,
# hotkeys) say so instead of working - see "Linux" in README.md.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/requirements.installed
fi
# Her neural voice. Optional: without it she uses the beeps or ElevenLabs.
if ! cmp -s requirements-voice.txt .venv/voice.installed; then
    if .venv/bin/python -m pip install -r requirements-voice.txt && \
       .venv/bin/python -m pip install --no-deps --ignore-requires-python "kokoro-onnx>=0.5,<1"; then
        cp requirements-voice.txt .venv/voice.installed
    else
        echo "[capri] Couldn't install her neural voice - she'll use another voice for now."
    fi
fi
.venv/bin/python tools/download_model.py
[ -f models/kokoro/kokoro-v1.0.int8.onnx ] || .venv/bin/python tools/download_voice.py || true
exec .venv/bin/python -m capri "$@"
