# Koeiro v0.13.3: Linux 版が出た、一括変換-最速の全体RTFを下げた、クリーン環境のセットアップが通る

## 🌟 ハイライト

* **Linux の実行ファイル版**を作れるようにしました。凍結アプリ（`Koeiro` + `_internal`）と
  AI ボイスパック（凍結 `KoeiroWorker` + モデル、BOOTH の1ファイル上限に合わせて2分割）、
  sha256 の検証情報が揃い、アプリ内蔵の自動更新も新版バンドルの差し替えで動きます。
* **一括変換-最速の全体 RTF を下げました**。同一計測ウィンドウで **1.58 → 0.94**
  （音声1秒の処理に1秒かからなくなる＝逐次変換のリアルタイム予算の内側）。
* **ソースツリー版の初回セットアップが、からっぽの機械で通るようになりました**。
  重りのダウンロードURLが3件分壊れていて、手元はすでに重りがあるので気づいていませんでした。

---

## 🛠 追加・修正

### 一括変換-最速（AI Voice）

* 一括＋最速だけ、まとめ推論（6ブロック・vocoder 36フレーム）＋ソルバ1ステップに変えました。
  前の最速は 1ブロック推論＋vocoder 逐次デコードで、それは逐次変換向けの「最初の音まで」を
  縮める構成でした。発話全体が揃ってから変換する一括ルートでは単なるスループット損失でした。
* スレッド下限を2に上げました（N150 で 1 は約20%遅く、4 は 2 より速くない）。
* 1ステップソルバは `steps_allowed` を明示した呼び出ししか通しません。逐次変換では選ばれません。
* 引き換えに声色の精度が落ちます。UI の説明も「声色の精度は落ちます」に書き換えました。

### Linux 版（配布物）

* `tools/build_linux_bundles.py` を追加。経路は2つで出てくるものは同じです。
  * 手元（Windows + Docker Desktop）: `--engine docker`、出来た tar だけを stdout に流して受け取る
  * Linux 上（CI ランナー・WSL）: `--engine local`（Docker 不要）
* アセット名（変えないこと）: `koeiro-<tag>-linux-app.tar.gz`、
  `koeiro-<tag>-linux-ai-pack-1.tar.gz` / `-2.tar.gz`、`koeiro-<tag>-linux-checksums.txt`
* AIパックに `install-ai-pack.sh` を同梱。`Koeiro` のあるフォルダへ2つの tar を展開します。
* 実行ファイル版の自動更新は、Windows のようなインストーラが無いので
  **新版バンドルを落として sha256 検証 → 解凍 → インストール先ディレクトリごと差し替え → 再起動**。
  `vc_models`（AIパック）と `recordings` は差し替え後も残ります。
* Debian/Ubuntu 系の要求ライブラリ: `libportaudio2` と Qt の実行ライブラリ
  （`libgl1 libegl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 fontconfig`）。

### GitHub Actions（`linux-assets`）

* `workflow_dispatch` 限定・既定 dry_run で、Linux の凍結ビルドを CI 上で作れるようにしました。
  ビルドは ubuntu-22.04、**起動確認は一段古い Debian bookworm のコンテナ**で行います
  （ビルドした機械の glibc が買い手の下限になるため。24.04 で作ると Debian 12 が起動できませんでした）。

### 配布物を壊していた不具合

* MeanVC2 の重り5件のダウンロードURLが 404。HF repo は重りをルートに直置きで、コードが読む
  のは git repo の階層なのに、URL に行き先の階層をそのまま書いていました。手元は重りが
  既にあるので `already satisfied` で隠れ、クリーン環境のセットアップだけが壊れていました。
* ECAPA finetune（声の登録が使う）も同じ。Google Drive の `uc?export=download` は大きい
  ファイルで confirm ページが返るので、`drive.usercontent.google.com/...&confirm=t` に変えました。
* lock の `torch==2.5.1+cpu` に対して PyTorch の extra index を渡すようにしました
  （+cpu の wheel は PyPI に無い。torch が既に入っている機械では見えない不具合でした）。
* `Koeiro.spec` が存在しない `koeiro-root.txt` を常に同梱対象へ入れていて、clean checkout の
  ビルドが失敗していました（配布物からはどちらみち削除するファイル）。
* NTFS に実行ビットが無いので、Windows 上で pack を tar すると `KoeiroWorker` が 0666 で
  格納され、買い手が `Permission denied` で起動できませんでした。名前で 0755 を戻します。
* `install-ai-pack.sh` が、同じフォルダに無い app tar の行まで `sha256sum -c` に通そうとして
  `set -e` でインストールを止めていました。パック2ファイル分だけ検証します。
* CI の app ジョブと pack ジョブが同じ名前の checksums をリリースへ上げて、後勝ちで
  app タールの行が消える組み合わせになっていました。パックだけのビルドは
  `koeiro-<tag>-linux-ai-pack-checksums.txt` へ出すようにしました。

---

## ⚠️ 既知の制限

* **Linux の RTF はこの版で申告できる値を持っていません。** Docker Desktop のコンテナ内で
  1.245 と 1.45 を1回ずつ見ただけで、同じ機械の Windows 実測と同条件ではありません。
* Linux の音声デバイス（マイク・出力）を使った実機確認はしていません。確認したのは
  オフスクリーンの `--smoke-test` と、保存 WAV を通した app↔worker の RPC 変換までです。
* 声の登録は Linux の凍結ビルドでは出来ません（AI 環境が必要で、登録専用の
  `wavlm_large*.pt` はパックに入れていない）。変換は動きます。Windows も同じ作りです。
* `setup.exe` と Linux の凍結ビルドに Authenticode / GPG 署名は入れていません。
  sha256 検証は破損・途中切れの検知で、リポジトリが乗っ取られた場合の防御ではありません。
* 実行ファイル版の自動更新は GitHub Releases を見にいくので、ネットワークが要ります。

---

## ✅ この版で実測したこと

* 配布物のサイズ（CI が作った Linux 版）: app tar **101.7 MB**、AIパック **406.0 MB + 360.8 MB**
  （ステージング 6,158 ファイル 1,673.3 MB、インストール済み **1.9 GB**）。3ファイルとも
  BOOTH の1ファイル上限 1.2 GB に対して余裕あり。Windows は setup 46.3 MB、
  AIパック 2.8 MB + 664.4 MB（インストール済み 1.6 GB）
* **sha256 が3点とも GitHub の計算した digest と一致**（アップロード後に突き合わせた）
* CI が作った Linux アプリは自分で `Koeiro v0.13.3` と報告する（凍結ビルドに版数が乗っていて、
  自分自身へ更新をかけない）
* 買い手と同じ手順を Debian bookworm のコンテナで通した: `install-ai-pack.sh`（ハッシュ検証込み）
  → インストール先の `KoeiroWorker`（0755 で起動可）→ 一括変換-最速 + LavaSR で
  保存 WAV 13.756 秒 → **660,288 サンプル、peak 0.95、enhancer フォールバックなし**。
  `--smoke-test` も同じコンテナで exit 0
* Windows 側: venv ワーカーと新生の凍結ワーカーの出力が**ビット同一**
  （`voice_demo_original.wav` 3.439 秒、一括変換-最速 + LavaSR、max_abs_diff 0.0）
* 一括変換-最速の RTF は同一ウィンドウの A/B で **1.58（旧最速）→ 0.94（一括構成）**。
  凍結ワーカーでは 0.91（42.4秒 wall）。この機械は他のビルドと同時だと2.4倍振れるので、
  絶対値は「ビルドを止めた窓」の値として読んでください
* exe版の自動更新: 0.13.2 の立場から更新確認すると `koeiro-v0.13.3-windows-setup.exe` が
  選ばれ、48,585,532 バイトを落として sha256（`c0d500b5df46c3a9…`）が通って
  `/VERYSILENT /NORESTART /SUPPRESSMSGBOXES /SP-` のコマンドまで組みました。
  **適用そのものは今回回していません**（0.13.1 → 0.13.2 の通し更新は v0.13.2 で実測済み）
* CI の所要: app **1m39s** / pack **7m26s**（ubuntu-22.04、dry_run）
* テスト: **1213 passed / 11 skipped / 1 failed**。落ちて1件は
  `tests/test_ai_gui.py::test_first_run_guide_waits_for_the_splash_instead_of_covering_it` で、
  単独実行は 3.6秒で pass（通し実行だけのタイミング揺れ、既知のもう1件と同じ性質）
* **聴いた判定はしていません。** 音色・遅延の官能評価は別途、実機で短时間の範囲でやる必要があります
