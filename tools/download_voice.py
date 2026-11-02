"""Download a neural voice for Capri (runs offline once downloaded).

Usage:  python tools/download_voice.py              her "Capri" voice (Kokoro, ~120 MB) - recommended
        python tools/download_voice.py <piper voice> an optional Piper voice (~60 MB), e.g.
            en_US-amy-medium, en_GB-jenny_dioco-medium, en_US-hfc_female-medium
            (browse more: https://rhasspy.github.io/piper-samples/)

Kokoro needs:  the packages in requirements-voice.txt + kokoro-onnx (run.bat installs them)
Piper needs:   pip install piper-tts
Then restart Capri. Voice "Default" picks her neural voice automatically.
"""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capri.speech.engines import KOKORO_DIR, VOICES_DIR, download_kokoro  # noqa: E402

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def kokoro() -> None:
    def progress(name: str, done: int, total: int) -> None:
        print(f"\r  {name}: {done / 1e6:5.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print(f"Downloading Capri's neural voice into {KOKORO_DIR}")
    try:
        download_kokoro(progress=progress)
    except Exception as exc:
        print(f"\nFailed: {exc}")
        sys.exit(1)
    print("\nDone. Restart Capri to hear her new voice.")


def piper(name: str) -> None:
    lang, speaker, quality = name.split("-", 2)
    family = lang.split("_")[0]
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in (".onnx.json", ".onnx"):
        url = f"{BASE}/{family}/{lang}/{speaker}/{quality}/{name}{suffix}"
        target = VOICES_DIR / f"{name}{suffix}"
        print(f"Downloading {url}")
        try:
            urllib.request.urlretrieve(url, target)
        except Exception as exc:
            print(f"Failed: {exc}")
            sys.exit(1)
    print(f"Installed {name} in {VOICES_DIR}. Pick \"piper: {name}\" in Settings -> Assistant.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] not in ("capri", "kokoro"):
        piper(sys.argv[1])
    else:
        kokoro()
