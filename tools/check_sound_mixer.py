"""Windows build check: Capri's sound-mixer reader (her Discord "Vibing to music") loads and runs without
crashing. Build machines have no speakers, so "no sound device" is fine; a crash fails the build."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from capri.integrations import now_doing as nd  # noqa: E402

nd._com()
print("mixer interfaces ok")
try:
    print("making sound right now:", nd.windows_sounding())
except OSError as exc:
    print("no speakers on this machine:", exc)

import soundcard  # noqa: E402,F401  (clips: speaker sound - its C headers must be there)
print("soundcard ok")
