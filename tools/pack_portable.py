"""Zip Capri's built app folder (dist/Capri) for the one-file Capri.exe launcher to carry inside it.

Run:  python tools/pack_portable.py dist/Capri build/capri.zip
Every file goes in under "Capri/" (the launcher unpacks it to %LOCALAPPDATA%\\Capri\\app\\<version>\\Capri\\).
"""
import sys
import zipfile
from pathlib import Path


def pack(folder: Path, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, "Capri/" + path.relative_to(folder).as_posix())
                count += 1
    return count


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if not (src / ("Capri.exe" if sys.platform == "win32" else "Capri")).is_file():
        sys.exit(f"no built Capri in {src}")
    n = pack(src, dst)
    print(f"{n} files -> {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
