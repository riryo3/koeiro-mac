# Koeiro for Mac (Apple Silicon) — 非公式の Mac 対応ブランチ

[heynegix/koeiro](https://github.com/heynegix/koeiro)（MIT License）を Mac で動かすための変更です。
本家の作者とは関係のない、非公式の対応です。元の `LICENSE` と `THIRD_PARTY_NOTICES.md` はそのまま残しています。

## 動作確認した環境
Mac mini (M4) / macOS / Python 3.12 / **CPU のみ**（MPS は使っていません。120ms の処理が約 33ms で終わるため不要でした）

## 確認できたこと
- GUI の起動、マイク → AI 声変換（MeanVC2）→ 出力、モニター（ヘッドフォン）
- BlackHole 2ch 経由で別アプリ（QuickTime など）へ変換後の声を送る
- 一括変換モードの LavaSR（CPU）

## セットアップ（確認した手順）
1. `xcode-select --install`、`brew install uv`
2. 仮想環境（GUI 用と AI 用）を作る
   ```bash
   uv venv --python 3.12 .venv
   uv venv --python 3.12 vc_models/meanvc2/.venv
   uv pip install --python .venv/bin/python -r requirements.txt
   uv pip install --python vc_models/meanvc2/.venv/bin/python torch torchaudio
   # lock は Windows/Linux 用の `+cpu` 固定と win32 専用の行があるので除いて入れる
   grep -vE '^(torch|torchaudio|torchvision)==|win32-setctime' vc_models/meanvc2/requirements.lock.txt > /tmp/req.lock.txt
   uv pip install --python vc_models/meanvc2/.venv/bin/python -r /tmp/req.lock.txt torchvision
   # torch と torchaudio のバージョンを揃える（例: どちらも 2.6.0）
   ```
3. Female DSP のネイティブライブラリをビルド: `tools/build_native_mac.sh`
4. モデル取得（約 2GB。`tools/setup_release.py` の `fetch_models` を使う）と LavaSR
   ```bash
   python3 -c "import sys; sys.path.insert(0,'tools'); import setup_release as s; from pathlib import Path; s.fetch_models(Path('.').resolve(), False)"
   PATH="$HOME/.local/bin:$PATH" .venv/bin/python tools/install_lavasr.py
   ```
   ※ `tools/setup_release.py` 全体の Mac での実行は未確認です。
5. 仮想マイク: `brew install --cask blackhole-2ch` のあと `sudo killall coreaudiod`（または再起動）
6. 起動: `.venv/bin/python app.py`

## 変更点
**Mac 対応（コミット 1）**
- `app.py`: darwin を許可
- `src/processors/native/female_dsp.cpp`: x86 専用の `_mm_getcsr/_mm_setcsr`（FTZ/DAZ）を ARM64 の FPCR に置き換え、非 Windows で `__declspec` を使わない
- `src/processors/native_backend.py`: macOS では `female_dsp_arm64.dylib` を読む
- `src/audio/monitor.py`: モニターは出力専用の `OutputStream` を使う（入力のない出力機器で「Invalid number of channels」になっていた）
- `src/audio/engine.py`: モニター機器が入力機器と同じで、サンプルレートが違うときは開始しない（Core Audio で入力が止まるため）。同じ 48kHz なら動く

**画面と挙動の改善（コミット 2）** — 好みが分かれるので別コミットにしています
- 3 列レイアウト、縦の dB メーター（ピークホールド・ゲート表示）、コピーできるエラーダイアログ、メニューバー（Mac のみ）、Mac 標準のウィンドウ枠
- 出力ゲート（MeanVC2 は無音を入れても約 -37 dBFS の雑音を出すため）
- 登録した声の削除（ゴミ箱へ移動）、スライダーの「おすすめ」ボタン
- 初回ガイドの位置ずれ・二重表示の修正、Mac 向けの文言
- Apple Silicon では、遅延を減らす推論設定（まとめ処理なし）を既定にする

## 既知の制限
- 自動更新（`src/app_update.py`）は Mac 未対応のままです
- `.app` 化（配布用ビルド）は未対応です
- MPS（Mac の GPU）は未対応です
