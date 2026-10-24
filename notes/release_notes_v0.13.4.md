# Koeiro v0.13.4: 実機ログに出ていた障害を直し、配布物の作り方をスクリプトに寄せた

## 🌟 ハイライト

* **実機ログにだけ出ていた障害を直しました。** 音声 callback の中で例外になっていた経路
  （ノイズ除去の短いブロック、無限大が来たときの自動均一化、リングの足りない読み）と、
  Qt が slot の例外を飲み込むせいで緑のスイートに何版も隠れていた経路（モード切替、
  ゲインの範囲）です。症状はすべて実機ログの Traceback から起こしています。
* **アプリが起動しなくなる系統を塞ぎました。** 声フォルダの `profile.json` や配布マーカーが
  深く入れ子だと、`json.loads` の再帰制限で例外が import を抜け、パッケージ版には自救手段が
  ありませんでした。壊れた1件を skip する形に変えています。
* **BOOTH 用 ZIP を再現できるようにしました。** 手順は PUBLISHING.md にありましたが
  スクリプトが無く、v0.13.3 の2枚は手作業の産物でした。`tools/build_booth_zip.py` が
  中身の検査（同梱 checksums との突合・容量上限・フラット・無圧縮）ごと作ります。

---

## 🛠 追加・修正

### 音声 callback で例外になっていた経路

* **ノイズ除去**: `blocksize` より短いブロックが来ると `ValueError: could not broadcast` が
  callback 内で出ていました。`prepare()` の bins 数で確保した作業領域を、そのまま短い
  ブロックの spectrum に当てていたためです。1024 のときの数値は変わりません。
* **自動均一化**: 上流が非有限（無限大）のブロックを出すと `log10(0)` で raise していました。
  非有限のときは追従値を据え置きます。
* **リング（同時通訳の駆動）**: 足りない読みで周回したときに、書き込んでいない範囲まで
  広げて代入していました。実際に持っている分だけを書きます。
* **AI ワーカーの停止**: `bridge.stop()` が失敗すると、その例外が音声停止処理全体を中断して
  いました。例外はログに残して続行し、ワーカー側の状態（`worker_state = 'Error'`）は UI に
  出ます。

### 緑のスイートに隠れていた経路

* **モード切替**: 削除済みの属性を slot が読んでいて、毎回 `AttributeError` が出ていました。
  Qt がこれを `sys.excepthook` へ回して飲み込むため、テストは緑のままでした。
* **ゲイン**: スライダーが -30 dB まで動くのに、エンジンと設定は -20..+20 dB しか受け付けず、
  画面の数字と実際の利得が食い違っていました。範囲を -20.0..+12.0 dB に揃えました。
* 同じ形の不一致が他に無いかをウィジェット全数で往復検査し、0 件であることを確認しています。

### 起動しなくなる系統

* `src/vc/voice_library.py` の `discover()` は `src.vc.models` の import 中に走るため、
  1 つの声の `profile.json` が読めないとアプリ全体が起動しませんでした。壊れた1件を skip。
* 同じ経路の配布マーカー（`bundle.json`）も、中身が dict でない場合を `{}`（制限なし）に
  正規化します。`settings.manager` などには既にあった `RecursionError` の扱いに揃えました。
* 声パネルは、読めなかったときに前の声の表示を残さず、その旨を出します。

### 表示とログの正直さ

* 発話ルート（一括変換）は仕様上、AI エラー後に無音のままです。ログだけが「Original に
  戻った」と名乗っていたのを直しました。**音の挙動は変えていません。**
* 声の詳細、LAN ワーカーの無通信終了、更新チェックの上流ゴミなど、症状が消えるだけで
  気づけない経路にログ・テストを足しました。

### 配布物・CI

* `tools/build_booth_zip.py` と `tests/test_booth_zip.py` を追加。検査内容は、同梱
  checksums と各メンバーの sha256、1ファイル 1.2 GB / 1商品 10 GB の上限、ルートの
  フラットさ、無圧縮（stored）、メンバー重複です。
* `pytest.ini` で `ResourceWarning` を失敗にし、オフライン一式を **windows-latest** で回す
  `tests.yml` を追加しました（`-X dev` は `__del__` 由来の警告を実際に発生させます）。
  release ワークフローの self テストも同じゲートに乗せています。
* `tools/build_brand.py` / `build_desktop.py` / `write_build_root.py` は `--help` が
  仕事を実行して追跡済みアセットを上書きしていました。追加のアセットビルダも含めて、
  引数を先に解釈する形にしました。
* `linux-assets` の apt 一覧が 2 箇所に複製されていたのを、`RUNTIME_APT` の単一出所へ。
* リリースの配布物づくりを `release` ワークフロー1本にまとめました（ソースツリー、Windows の
  `setup.exe` と AIパック、Linux の凍結バンドルと AIパックを、`tools/verify_release_assets.py`
  の検査ごと作って添付します）。BOOTH ZIP はこれまでどおり手元で作ります。
* README を書き直し、Linux のソース利用手順に Qt の実行ライブラリ
  （`libgl1 libegl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 fontconfig`）を明記しました。

### 開発者向け

* AI Voice の CPU スレッド初期値を 2 にそろえました。推奨設定は同梱ボイスで既に 2 を
  選ぶのに、初期値だけ 1 で始まっていました（保存済みの選択はそのまま尊重します）。
* `lab/actions.py` の `load_wav` は、docstring が約束する `ValueError` を実際に返すように
  しました（float 符号 WAV、切り詰めファイル、音声ゼロ長を明示的に拒否）。
* `src/vc/utterance.py` の重複定義と `phrase_prosody.py` の未使用残骸を削除（音は不変）。

---

## ⚠️ 既知の制限

* **この版でも実機の通話確認はしていません。** マイクと出力を使った変換、Discord 経由の
  確認、実聴による音質・遅延の評価は未実施です。確認したのは保存 WAV を通した変換までです。
* **Windows の AI ボイスパックを実際にインストールしての起動確認は、この版では回して
  いません**（`%LOCALAPPDATA%` の実環境を書き換えるため）。凍結ワーカーが venv ワーカーと
  同じ計算に乗っていることまでは検証しています。
* Linux の RTF はこの版でも申告できる値を持っていません（コンテナ内の1回の計測のみ）。
* 声の登録は凍結ビルドでは出来ません（AI 環境が必要で、登録専用の重りはパックに
  入れていません）。Linux・Windows ともに同じ作りです。
* `setup.exe` と Linux の凍結ビルドに Authenticode / GPG 署名は入れていません。sha256 は
  破損・途中切れの検知で、配布元が乗っ取られた場合の防御ではありません。
* 実行ファイル版の自動更新は GitHub Releases を見にいくので、ネットワークが必要です。
  **この版でも適用そのものは回していません**（0.13.1 → 0.13.2 の通し更新は v0.13.2 で実測済み）。

---

## ✅ この版で実測したこと

* テスト一式: **1239 passed / 11 skipped**（`.venv/Scripts/python.exe -X dev -m pytest -q`、
  5分27秒、`ResourceWarning` 0 件）。回帰テストを追加しており、うち範囲の2件（ゲインの
  上下限と、設定の検証範囲）は修正前の値に戻すと実際に落ちることを確かめています。
* ソースツリー版の配布資産（この版で作ったもの）:
  * `koeiro-v0.13.4-windows.zip` **6,762,017 バイト**（504 メンバー、最大は既定声の
    `reference.wav` 1,807,404 バイト）。sha256 `789d7e5099d50f7b…`
  * `koeiro-v0.13.4-linux.tar.gz` **6,562,365 バイト**（504 メンバー）。sha256 `1c83d081dee6d1a5…`
  * どちらも `release.json`（`{"app": "Koeiro", "version": "0.13.4", ...}`）を同梱し、
    中に `src/version.py` の `APP_VERSION = "0.13.4"` が入っています
  * 展開したツリーで `tools/setup_release.py --dry-run` が **exit 0**
* Windows の凍結版: `Koeiro.exe --smoke-test` が exit 0、`--help` が `Koeiro v0.13.4` と報告。
  `setup.exe` は **48,588,892 バイト**（sha256 `cf280a555ef224c6…`）、AIパックは
  **2.8 MB + 664.4 MB**（ステージング 6,650 ファイル 1,385.6 MB）。
* 凍結ワーカー（Windows）: venv ワーカーと同一の保存 WAV（`voice_demo_original.wav` 3.439 秒、
  一括変換 + LavaSR）で **max_abs_diff 0.0 / identical: true**。
* Linux の買い手と同じ手順を Debian bookworm のコンテナで通しました:
  `sha256sum -c` が3点とも OK → `install-ai-pack.sh`（ハッシュ検証込み）→ 設置 →
  `QT_QPA_PLATFORM=offscreen ./Koeiro --smoke-test` が **exit 0**、`--help` が
  `Koeiro v0.13.4` と報告 → 凍結ワーカーが保存 WAV 3.439 秒を変換し
  **165,072 サンプル（48 kHz）**、enhancer は lavasr、フォールバックなし
  （レポートは `dist/linux-install-verify-0134/report.json`、3.44 秒の音声に対して
  wall 25.18 秒）。
* Linux の配布物サイズ（Docker 経路で作成、表示は `tools` と同じ MiB 基準）: app tar
  **96.6 MB**、AIパック **430.4 MB + 360.9 MB**（ステージング 6,158 ファイル 1,673.3 MB）。
  3点の sha256 は `koeiro-v0.13.4-linux-checksums.txt` にあります。
* BOOTH 用の2枚: `Koeiro_v0.13.4_Windows.zip` **748,246,799 バイト**、
  `Koeiro_v0.13.4_Linux.zip` **931,060,549 バイト**（どちらも無圧縮・フラット・入手案内が先頭）。
  `tools/build_booth_zip.py --check` が exit 0。
* **聴いた判定はしていません。** 音色・遅延の官能評価は実機で別途行う必要があります。

---

## 📦 アップデート

* 実行ファイル版（Windows）: アプリ内蔵の更新、または新しい `setup.exe` の再適用。
  設定・AI 環境・録音は引き継がれます。
* 実行ファイル版（Linux）: 新しいアプリバンドルを展開し直すか、アプリ内蔵の更新
  （新版バンドルを落として sha256 検証 → インストール先ごと差し替え）。`vc_models` と
  `recordings` は差し替え後も残ります。**この版で通しの適用は回していない**ので、
  うまくいかない場合は展開し直してください。
* ソースツリー版 / BOOTH 版: 新しい ZIP を展開し直してください。AIパックの設置は
  Windows は `ai-pack.exe`（`-1.bin` と同じフォルダ）、Linux は `install-ai-pack.sh` です。
