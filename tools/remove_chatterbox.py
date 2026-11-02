"""Removes Chatterbox (her old cloned voice) from Capri's environment - run once by run.bat.

Uninstalls PyTorch and the other packages only Chatterbox used (several GB), and deletes its
downloaded model (~2 GB in the Hugging Face cache) and Capri's models\\chatterbox folder.
Capri's own packages are left alone.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONLY_CHATTERBOX = ["chatterbox-tts", "torch", "torchaudio", "s3tokenizer", "diffusers", "transformers",
                   "resemble-perth", "conformer", "peft", "accelerate", "librosa", "numba", "llvmlite",
                   "pyloudnorm", "omegaconf", "tokenizers", "safetensors", "onnx", "spacy-pkuseg", "pykakasi",
                   "gradio"]


def main() -> int:
    print("Removing Chatterbox (her old cloned voice) - this frees a few GB...")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", *ONLY_CHATTERBOX], check=False)
    for folder in (ROOT / "models" / "chatterbox",
                   Path.home() / ".cache" / "huggingface" / "hub" / "models--ResembleAI--chatterbox-turbo",
                   Path.home() / ".cache" / "huggingface" / "hub" / "models--ResembleAI--chatterbox"):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            print(f"  deleted {folder}")
    for leftover in (ROOT / "capri_voice_test.wav",):
        leftover.unlink(missing_ok=True)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
