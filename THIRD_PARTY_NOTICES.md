# Third-party notices

Capri's own code is under the MIT License (see `LICENSE`). It uses, and the Windows installer
bundles, other people's work under their own licenses:

| Part | License | Notes |
| --- | --- | --- |
| PySide6 / Qt | LGPL-3.0 | The windows and graphics. |
| Vosk | Apache-2.0 | Wake word and everyday hearing. The speech model downloads on first start. |
| sherpa-onnx | Apache-2.0 | Runs Parakeet. |
| NVIDIA Parakeet TDT 0.6B v2 | CC-BY-4.0 | Speech model, downloaded from Settings (not bundled). |
| ONNX Runtime | MIT | Runs the neural voice and Parakeet. |
| Kokoro voice model / kokoro-onnx | Apache-2.0 / MIT | Neural voice, downloaded from Settings (not bundled). |
| espeak-ng (via espeakng-loader) | GPL-3.0 | Pronunciation for the neural voice. Bundled in Capri.exe. |
| phonemizer | GPL-3.0 | Pronunciation for the neural voice. Bundled in Capri.exe. |
| NumPy, psutil, sounddevice, comtypes, anthropic | BSD / MIT | Helpers. |
| soundcard | BSD-3-Clause | Clips: the sound your speakers play (Windows). |
| FFmpeg (via the imageio-ffmpeg package) | GPL-3.0 | Clips. Not bundled: on Windows it downloads from PyPI when you turn clips on; on Linux your own ffmpeg is used. |

Because espeak-ng and phonemizer are GPL-3.0, the **Windows installer as a whole** is shared
under the GPL-3.0's terms: its full source is this repository, and anyone may rebuild it with
`build.bat`. The MIT License applies to Capri's own source files.

## Artwork

The character art in `assets/` is fan art. The MIT License does not cover it, and anyone
reusing it should check they're allowed to.
