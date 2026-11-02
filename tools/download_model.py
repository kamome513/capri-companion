"""Download Capri's offline speech model (once, ~40 MB) into models/.

Usage:  python tools/download_model.py            the standard model (~40 MB)
        python tools/download_model.py --better   the more accurate model (~128 MB): fewer misheard words
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capri.voice.model import BETTER_MODEL, BETTER_URL, MODEL_NAME, MODEL_URL, download_model, find_model  # noqa: E402

if __name__ == "__main__":
    better = "--better" in sys.argv
    name, url = (BETTER_MODEL, BETTER_URL) if better else (MODEL_NAME, MODEL_URL)
    existing = find_model()
    if existing and "--force" not in sys.argv and (not better or existing.name == BETTER_MODEL):
        print(f"Speech model already installed: {existing}")
        sys.exit(0)
    try:
        path = download_model(url=url)
    except Exception as exc:   # network, disk, bad archive - say what happened
        print(f"\nCould not download {name}: {exc}")
        print("You can also download it by hand from https://alphacephei.com/vosk/models")
        print("and unzip it into the 'models' folder next to run.bat.")
        sys.exit(1)
    print(f"Installed speech model: {path}")
