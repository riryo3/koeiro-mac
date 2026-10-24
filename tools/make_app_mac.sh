#!/bin/bash
# Build a personal Koeiro.app next to this checkout (Apple Silicon).
# The app is a thin launcher: it runs this folder's .venv python from inside the bundle,
# so macOS shows it as "Koeiro" (Dock name, icon, microphone permission).
# Needs .venv (see MAC.md). Moving the folder is fine; rerun this script if .venv is rebuilt.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
[ -x .venv/bin/python ] || { echo ".venv がありません。MAC.md の手順で作ってください。"; exit 1; }
PY="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' .venv/bin/python)"
VER="$(sed -n 's/^APP_VERSION *= *"\(.*\)".*/\1/p' src/version.py | head -1)"
VER="${VER:-0.13.5}"
APP="$ROOT/Koeiro.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/lib/python3.12"
cp assets/Koeiro.icns "$APP/Contents/Resources/Koeiro.icns"
ln -s "$PY" "$APP/Contents/MacOS/python"
ln -s ../../../../.venv/lib/python3.12/site-packages "$APP/Contents/lib/python3.12/site-packages"
cat > "$APP/Contents/pyvenv.cfg" <<CFG
home = $(dirname "$PY")
implementation = CPython
version_info = 3.12
include-system-site-packages = false
CFG
cat > "$APP/Contents/MacOS/Koeiro" <<'LAUNCH'
#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/../../.." && pwd)"
cd "$SRC" || exit 1
exec "$HERE/python" app.py
LAUNCH
chmod +x "$APP/Contents/MacOS/Koeiro"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Koeiro</string>
  <key>CFBundleDisplayName</key><string>Koeiro</string>
  <key>CFBundleIdentifier</key><string>local.koeiro.mac</string>
  <key>CFBundleExecutable</key><string>Koeiro</string>
  <key>CFBundleIconFile</key><string>Koeiro</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VER</string>
  <key>CFBundleVersion</key><string>$VER</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Koeiro はマイクの声を変換するために、マイクを使います。</string>
  <key>NSAppleEventsUsageDescription</key><string>Audio MIDI設定を開いて、機器のサンプルレートを変更できるようにするために使います。</string>
</dict>
</plist>
PLIST
echo "作りました: $APP"
