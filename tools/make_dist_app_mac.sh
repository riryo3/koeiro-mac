#!/bin/bash
# Build a small, shareable Koeiro.app (Apple Silicon): source + first-run setup.
# The app holds no Python and no models. On first launch it copies the source to
# ~/Library/Application Support/Koeiro/koeiro and runs tools/koeiro_setup_mac.sh in Terminal.
# Output: dist/Koeiro.app and dist/Koeiro-mac-<version>.zip. Not signed (ad-hoc only):
# the first open needs right-click > Open.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VER="$(sed -n 's/^APP_VERSION *= *"\(.*\)".*/\1/p' src/version.py | head -1)"
[ -f src/processors/native/female_dsp_arm64.dylib ] || bash tools/build_native_mac.sh
rm -rf dist && mkdir -p dist
APP="dist/Koeiro.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Source: tracked files at HEAD plus the built dylib. No venvs, models or settings.
STAGE="$(mktemp -d)"
git archive --prefix=koeiro/ HEAD | tar -x -C "$STAGE"
cp src/processors/native/female_dsp_arm64.dylib "$STAGE/koeiro/src/processors/native/"
tar -czf "$APP/Contents/Resources/koeiro-src.tar.gz" -C "$STAGE" koeiro
rm -rf "$STAGE"
echo "$VER-$(git rev-parse --short HEAD)" > "$APP/Contents/Resources/VERSION"
cp assets/Koeiro.icns "$APP/Contents/Resources/Koeiro.icns"

cat > "$APP/Contents/MacOS/Koeiro" <<'LAUNCH'
#!/bin/bash
BUNDLE="$(cd "$(dirname "$0")/../.." && pwd)"
RES="$BUNDLE/Contents/Resources"
DATA="${KOEIRO_HOME:-$HOME/Library/Application Support/Koeiro}"
SRC="$DATA/koeiro"
VER="$(cat "$RES/VERSION")"
mkdir -p "$DATA"

# New app version: refresh the source, keep .venv, models, voices and settings.
if [ "$(cat "$DATA/source-version" 2>/dev/null)" != "$VER" ]; then
  TMP="$(mktemp -d)"
  tar -xzf "$RES/koeiro-src.tar.gz" -C "$TMP"
  mkdir -p "$SRC"
  rsync -a "$TMP/koeiro/" "$SRC/"
  rm -rf "$TMP"
  echo "$VER" > "$DATA/source-version"
fi

# First run: set up Python and models in a Terminal window (progress is visible).
if [ ! -f "$SRC/.setup-done" ]; then
  if [ -z "${KOEIRO_NO_DIALOG:-}" ]; then
    osascript -e 'display dialog "Koeiro の初回の準備をします。\n\nインターネットから約 2GB をダウンロードします（10〜20 分ほど）。\nTerminal の画面が開くので、終わるまで閉じないでください。" with title "Koeiro" buttons {"やめる", "準備を始める"} default button "準備を始める" cancel button "やめる"' >/dev/null 2>&1 || exit 0
  fi
  RUN="$DATA/first-run.command"
  cat > "$RUN" <<RUNSH
#!/bin/bash
cd "$SRC" || exit 1
if bash tools/koeiro_setup_mac.sh; then
  open "$BUNDLE"
else
  echo; echo "準備が途中で止まりました。上のメッセージを確認して、もう一度 Koeiro を開いてください。"
  echo "（Enterキーで閉じます）"; read -r
fi
RUNSH
  chmod +x "$RUN"
  if [ -n "${KOEIRO_NO_TERMINAL:-}" ]; then bash "$RUN"; else open -a Terminal "$RUN"; fi
  exit 0
fi

# Run: a small runtime app lives outside this signed bundle, in Application Support, and
# its own python points at the venv, so macOS shows "Koeiro" (Dock name, icon, microphone
# permission). This bundle is never modified after signing.
RUNAPP="$DATA/Koeiro.app"
PY="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$SRC/.venv/bin/python")"
if [ "$(readlink "$RUNAPP/Contents/MacOS/python" 2>/dev/null)" != "$PY" ] || \
   [ "$(cat "$RUNAPP/Contents/Resources/VERSION" 2>/dev/null)" != "$VER" ]; then
  rm -rf "$RUNAPP"
  mkdir -p "$RUNAPP/Contents/MacOS" "$RUNAPP/Contents/Resources" "$RUNAPP/Contents/lib/python3.12"
  cp "$BUNDLE/Contents/Info.plist" "$RUNAPP/Contents/Info.plist"
  cp "$RES/Koeiro.icns" "$RES/VERSION" "$RUNAPP/Contents/Resources/"
  ln -s "$PY" "$RUNAPP/Contents/MacOS/python"
  ln -s "$SRC/.venv/lib/python3.12/site-packages" "$RUNAPP/Contents/lib/python3.12/site-packages"
  printf 'home = %s\nimplementation = CPython\nversion_info = 3.12\ninclude-system-site-packages = false\n' "$(dirname "$PY")" > "$RUNAPP/Contents/pyvenv.cfg"
  printf '#!/bin/bash\nHERE="$(cd "$(dirname "$0")" && pwd)"\ncd "%s" || exit 1\nexec "$HERE/python" app.py\n' "$SRC" > "$RUNAPP/Contents/MacOS/Koeiro"
  chmod +x "$RUNAPP/Contents/MacOS/Koeiro"
fi
if [ -n "${KOEIRO_NO_OPEN:-}" ]; then exit 0; fi
exec open "$RUNAPP"
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
codesign --force --deep -s - "$APP" 2>/dev/null || true
(cd dist && ditto -c -k --keepParent Koeiro.app "Koeiro-mac-$VER.zip")
echo "作りました: $ROOT/dist/Koeiro.app"
ls -lh dist
