#!/usr/bin/env bash
# Linux: turns the PyInstaller build (dist/Capri) into one file, dist/Capri-x86_64.AppImage.
#   python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/capri.spec
#   packaging/build_appimage.sh
# Uses appimagetool (downloaded once into build/). Needs no root and no FUSE (it unpacks itself).
set -euo pipefail
cd "$(dirname "$0")/.."
DIST=${DIST:-dist}
WORK=${WORK:-build}
[ -x "$DIST/Capri/Capri" ] || { echo "Build Capri first (PyInstaller): $DIST/Capri/Capri is missing"; exit 1; }

APPDIR="$WORK/Capri.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a "$DIST/Capri" "$APPDIR/usr/lib/capri"
cp assets/capri/icon.png "$APPDIR/capri.png"
cp assets/capri/icon.png "$APPDIR/.DirIcon"

cat > "$APPDIR/capri.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Capri
GenericName=Desktop companion
Comment=A cyberpunk desktop companion
Exec=capri
Icon=capri
Terminal=false
Categories=Utility;
StartupNotify=false
EOF

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
# Capri's AppImage: start the app inside. (Wayland: Capri itself switches to XWayland.)
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/capri/Capri" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$WORK/appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
mkdir -p "$DIST"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$DIST/Capri-x86_64.AppImage"
ls -la "$DIST/Capri-x86_64.AppImage"
