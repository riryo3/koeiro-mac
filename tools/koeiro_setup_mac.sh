#!/bin/bash
# First-run setup for the distributable Koeiro.app (Apple Silicon).
# Run with the unpacked source as the working directory. Safe to rerun: finished
# steps are skipped. Needs internet (about 2 GB) and the Xcode command line tools (git).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

say() { printf '\n== %s\n' "$*"; }

say "1/6 git の確認"
if ! command -v git >/dev/null 2>&1 || ! git --version >/dev/null 2>&1; then
  echo "git（Xcode コマンドラインツール）が必要です。出てきた画面で「インストール」を押し、"
  echo "終わったら、もう一度 Koeiro を開いてください。"
  xcode-select --install 2>/dev/null || true
  exit 1
fi

say "2/6 uv（Python の管理ツール）"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv --version

say "3/6 仮想環境（GUI 用と AI 用）"
[ -x .venv/bin/python ] || uv venv --python 3.12 .venv
[ -x vc_models/meanvc2/.venv/bin/python ] || uv venv --python 3.12 vc_models/meanvc2/.venv

say "4/6 部品のインストール（数分かかります）"
uv pip install --python .venv/bin/python -r requirements.txt
uv pip install --python vc_models/meanvc2/.venv/bin/python torch==2.6.0 torchaudio==2.6.0
LOCK="$(mktemp)"
grep -vE '^(torch|torchaudio|torchvision)==|win32-setctime' vc_models/meanvc2/requirements.lock.txt > "$LOCK"
uv pip install --python vc_models/meanvc2/.venv/bin/python -r "$LOCK" torchvision==0.21.0
rm -f "$LOCK"

say "5/6 AI モデルの取得（約 2GB。時間がかかります）"
.venv/bin/python -c "
import sys; sys.path.insert(0, 'tools')
import setup_release as s
from pathlib import Path
s.fetch_models(Path('.').resolve(), False)
"
.venv/bin/python tools/install_lavasr.py

say "6/6 仕上げ"
if [ ! -f src/processors/native/female_dsp_arm64.dylib ]; then
  bash tools/build_native_mac.sh
fi
touch .setup-done
echo
echo "準備ができました。"
echo "※ 変換後の声を Discord などに送るには、BlackHole 2ch が別に必要です:"
echo "   brew install --cask blackhole-2ch   （入れたあと、再起動してください）"
