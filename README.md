<p align="center">
  <img src="assets/icon.png" alt="Koeiro Icon" width="160" style="border-radius: 50%;">
</p>

<h1 align="center">Koeiro（声彩）</h1>

<p align="center">
  <strong>登録した声へリアルタイムに変換する次世代AIボイスチェンジャー</strong><br>
  Windows 10/11 & Linux 対応 ｜ MeanVC2 + LavaSR 帯域復元 ｜ Discord RPC 連携
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-0078D6" alt="Platform">
  <img src="https://img.shields.io/badge/PyTorch-CPU%20%2F%20CUDA%2012-EE4C2C?logo=pytorch&logoColor=white" alt="PyTorch">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

> 🍎 **非公式の Mac（Apple Silicon）版**: 本家 [heynegix/koeiro](https://github.com/heynegix/koeiro)（MIT License）のフォークです。本家の作者とは別の人が、個人で作っている非公式の対応です。名前・ロゴ・標準ボイスは、本家の作者の許可を得て使っています。
>
> - 使い方: [USAGE_MAC.md](USAGE_MAC.md) ／ 入れ方と変更点: [MAC.md](MAC.md)
> - 本家への Mac 対応の提案は、[PR #4](https://github.com/heynegix/koeiro/pull/4) で進んでいます（このフォークとは別です）。
> - このフォークの変更は、AI（Claude）の支援を受けて作りました。Mac mini (M4) の実機（CPU のみ）で動作を確認しています。画面のレイアウトの変更は個人の好みによるもので、本家のデザインへの批判ではありません。

---

## 📖 概要

**Koeiro（声彩 / こえいろ）** は、マイクから入力された音声をリアルタイムで目的の声へと変換するAIボイスチェンジャーです。

最先端の軽量音声変換モデル **MeanVC2** に加え、高品質な超解像・帯域復元技術 **LavaSR** を統合。配信（OBS）、通話（Discord / Zoom）、VRプラットフォームなどに向けて、低遅延かつ高品位なボイス変換を提供します。

GUIとAI推論ワーカーをプロセス分離する設計を採用しており、GUI側の軽快な動作とAI処理の安定稼働を両立しています。

---

## ✨ 主な機能

- **複数の変換モードを用途に合わせて選択可能**
  - **逐次変換（Streaming）**: 発話を話しながら順次低遅延で変換。リアルタイムな通話・ゲームプレイに最適。
  - **一括変換（LavaSR 高音質）**: 0.8秒の無音区間で発話を自動分割し、文全体を変換後に LavaSR で高域を復元（最大60秒）。数秒待つ代わりに極めて自然で明瞭な音質を実現。
  - **一括変換 - 最速**: 判定待ち時間を約0.6秒まで短縮したレスポンス重視のバッチ変換モード。
  - **Original / Female DSP**: AIを介さない素通し（スルー）モードおよび軽量なDSPフォルマント・ピッチ加工。
- **直感的な声の登録 & 切り替え**
  - 数十秒〜数分の音声ファイルを登録するだけで、自分好みの声色・キャラクターボイスを即座に作成・選択可能。
- **Discord Rich Presence（アクティビティ表示）対応**
  - Discord のステータス欄に「Koeiro で変換中」「使用中のボイス名」をリアルタイム表示。
- **柔軟な推論デバイス対応**
  - NVIDIA GPU（CUDA）での高速推論に対応。GPU非搭載環境でも自動でCPUフォールバック動作。
  - 品質のブレを防ぐため TF32 を明示的に無効化し、再現性の高い音声出力を維持。
- **GUI完結の自動アップデート & 初回ガイド**
  - 初回起動時のスポットライトガイドを搭載（説明する操作だけを明るく残します）。
  - 「調整 → アプリ」から GitHub Releases の最新版をワンクリックで更新可能。
- **話し方の演出（抑揚プリセット / ノイズ除去 / 音量の自動均一化 / 出力の仕上げ / AI出力のフォルマント）**
  - Auto Intonation に**感情・抑揚プリセット**（Calm / Gentle / Energetic / Sad、Anime Light / Anime Expressive / Feminine）を追加。元の抑揚に補正を加えます。既定のプリセットは Anime Light のままです。
  - 定常ノイズ（ファン・サー音）を抑える**ノイズ除去**（スペクトル方式・実験的・既定OFF）。
  - **音量の自動均一化**（既定OFF・「入力の整え」）: 小声を変換モデルが掴める音量まで持ち上げ、無音は上げません。停止中も変換中も切り替えできます。
  - 変換後のつなぎ目のノイズと耳に刺さる息の音を抑える**出力の仕上げ**（最大3dB・穏やか・既定OFF、Originalには掛かりません）。
  - **AI出力のフォルマント**（既定OFF・「AI出力のフォルマント」）: AIの声の高さ（F0）は動かさず、共振だけを高域へ寄せて明るくします。AI Voice にだけ掛かり、後段の処理ぶん（low_latency で 2048 samples ≒ +42.7 ms）の遅延が増えます。
- **配信・通話をもっと速く（シーン / ホットキー / 音声コマンド）**
  - **シーン（設定プロファイル）**: マイク・声・ルート・加工・抑揚を名前を付けて保存し、1クリックで切替。
  - **A/B 即時切替ホットキー**: `Ctrl+1/2/3` で変換モードを直接、`Ctrl+D` で Original ↔ 直前の変換をトグル、`Ctrl+F` で開いている引き出し内を検索（アプリ内ショートカット）。
  - **音声コマンド（β）**: ウェイクワード「コエイロ」+「止めて」「次の声」などで操作。ローカル日本語ASRを使うため標準ボイス以外で有効。
- **ステージ1枚＋引き出しの画面**
  - 常設面はステージ（入力レベル・3点リレー・遅延・Start・AIの状態と声名の大表示）だけ。設定は右上の「調整」、追加機能は「実験」の引き出しに収納し、開いてもステージを押しのけません。
  - 声リストは右に常駐し、ヘッダのボタンで幅0に畳めます。「調整」「実験」には検索と目次（グループへのジャンプ）付き。
- **実験室（すべて既定OFF・本体の変換には影響なし）**
  - ①レイテンシ・ガバナ（計測して品質を提案、反映は任意・停止中のみ）、②同時通訳ボイス（発話を認識してその文を英語TTSで読み上げる・48 kHz専用・ASR/TTSの導入が必要・翻訳モデルは未実装で文面はそのまま）、③囁きモード（囁きを自動検出して周期成分を付与）、④分散推論（LANのGPU機に合成・翻訳を依頼）、⑤複数話者の自動振り分け（高さと明るさで分離、識別テスト付き）。
  - 「実験機能有効」をONにすると各機能のON/OFFが効くようになり、使う機能だけ中身が開きます。
- **拡張パック（DLC）対応 & リアルタイム翻訳ボイス（β・骨格）**
  - 重量級の機能は本体に入れず、`models/packs/<id>/pack.json` の**拡張パック**として追加できます。
  - 翻訳ボイス（日本語→English など）は翻訳パイプラインの骨格を同梱。**実モデルは各自ダウンロード**します（現状は骨格、詳細は `notes/translation_pack.md`）。
- **音声合成（TTS・任意）**
  - 軽量な **Kokoro-82M**（Apache-2.0）を任意で導入可能。`tools/install_tts.py` でモデルを取得します。詳細は「🗣️ 音声合成（TTS・任意）」を参照。

---

## 🛠️ 動作要件

| 項目 | 要件 |
| :--- | :--- |
| **OS** | Windows 10 / 11, Linux (Ubuntu 22.04+ 推奨) |
| **Python** | 3.12 系 |
| **必要容量** | 空き容量 約8GB 以上（作業環境＋AIモデル群）<br>（任意のTTSを使う場合は +約150MB） |
| **外部ツール** | **FFmpeg**（音声読込用）、**git**、**uv** |
| **Linux 追加依存** | `libportaudio2`, `portaudio19-dev` |
| **仮想音声デバイス** | 変換音を出力するための仮想オーディオデバイス（任意）<br>・Windows: [VB-CABLE](https://vb-audio.com/Cable/) 等<br>・Linux: `snd-aloop`（ALSA Loopback）等 |

---

## 🚀 クイックスタート（推奨：リリース版）

一般ユーザー向けには、[GitHub Releases](https://github.com/heynegix/koeiro/releases) から配布されているパッケージの利用を推奨します。

### Windows の場合
1. Releases から `koeiro-vX.Y.Z-windows.zip` をダウンロードし、任意のフォルダ（※英数字のみのパス推奨）に展開。
2. PowerShell を開き、展開先ディレクトリで以下を実行（初回のみ）：
   ```powershell
   py -3.12 tools/setup_release.py
   ```
3. セットアップ完了後、アプリを起動：
   ```powershell
   .\.venv\Scripts\python app.py
   ```

### Linux の場合
1. Releases から `koeiro-vX.Y.Z-linux.tar.gz` をダウンロードして展開。
2. ターミナルで以下を実行（初回のみ）：
   ```bash
   sudo apt install -y libportaudio2 portaudio19-dev ffmpeg
   python3.12 tools/setup_release.py
   ```
3. セットアップ完了後、アプリを起動：
   ```bash
   .venv/bin/python app.py
   ```

> [!TIP]
> アプリ起動後は「調整」引き出しの **① 配線**で **入力デバイス（マイク）** と **出力デバイス（VB-CABLE やヘッドホン等）** を指定してください。

---

## 💽 ソフトとして使う（インストール不要の実行ファイル）

配布物はソースツリーです。AIは約8GB（torch・モデル）あり配布物の上限に収まらないため、
**AIワーカーは同梱していません**（理由は [PUBLISHING.md](PUBLISHING.md)）。したがって
**先に環境を作り、そのあと実行ファイルを起動します**。

### Windows（exe）

```powershell
# 1. 配布ZIPを展開し、そのフォルダで1回だけ環境を作る（Python 3.12・git・uv が必要）
py -3.12 tools/setup_release.py

# 2. 実行ファイルを作る（ビルド用の環境が要ります）
.\.venv\Scripts\python tools\write_build_root.py
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\python -m PyInstaller Koeiro.spec --noconfirm

# 3. 起動
.\dist\Koeiro\Koeiro.exe
```

- `dist\Koeiro\` をまるごと配れば、Pythonの入っていないPCでも起動できます
  （AIは同梱されないため、配布先でも初回は `tools/setup_release.py` が必要です）
- **AI環境の場所は実行ファイルが自分で見つけます。** `dist\Koeiro\` には `vc_models` が
  無いため、`tools/write_build_root.py` がビルド元のフォルダを
  `koeiro-root.txt` に記録し、`Koeiro.spec` がそれを同梱します。手動設定は不要です
- AIワーカーはそのフォルダを**作業ディレクトリ**にして起動します（`src.vc.service` を
  実行するため。同梱バンドル側にはGUI用の `src/gui` しか入っていません）。つまり
  **`src/` と `vc_models/` が実行ファイルの隣に必要**です。`Koeiro.exe` だけを別のPCへ
  移すとAIは動きません（その場合は `KOEIRO_ROOT` でKoeiroフォルダを指定）
- ログは配布物の中ではなく、書き込み可能な場所（Windows:
  `%LOCALAPPDATA%\Koeiro\logs\`）に出ます。`ai-worker.log` も同じ場所です。
  声の登録の失敗は同じフォルダの `voice-registration.log` に残ります（登録プログラム
  `tools/register_voice.py` はAI環境をセットアップしたインストール先ツリーから実行されます）
- タスクバーとウィンドウのアイコンはexeに埋め込まれます（`Koeiro.spec` の `icon=`）。
  完全凍結ビルド（`KoeiroWorker.exe` を同梱）では、起動時に `-u -m src.vc.service` を
  付けずにワーカーを直接起動します
- **二重起動しません。** 同じデータフォルダで `Koeiro.exe` をもう一度起動すると、新しい
  ウィンドウは開かず、起動中のウィンドウを前面に出してすぐ終了します。`--data-dir` を
  変えた別プロファイルは同時に起動でき、ヘッドレスの `--smoke-test` は常に実行されます

### Windows（setup.exe で配る・実行ファイル版の自動更新）

インストーラは Inno Setup 6 で作ります（`winget install --id JRSoftware.InnoSetup -e --scope user`）。

```powershell
.\.venv\Scripts\python tools\build_windows_setup.py --tag v0.13.2 --rebuild
# → dist\setup\koeiro-v0.13.2-windows-setup.exe と koeiro-v0.13.2-windows-checksums.txt
```

- インストール先は既定で `%LOCALAPPDATA%\Programs\Koeiro`。**ユーザー単位なので管理者権限を
  要求せず、自動更新の再適用が対話なしで成立します**
- setup.exe は **アプリ本体のみ**同梱です。AI は `koeiro-<tag>-ai-pack.exe`（＋分割物）を
  **同じフォルダに上書きインストール**で入ります（Python 不要・オフライン動作）。
  入らない場合は Original と Female DSP だけで動きます。AI環境を自前で組むなら
  `tools/setup_release.py`（Python 3.12 が必要）でも可
- AIパックの中身: `KoeiroWorker.exe`（torch ごと凍結した AI ワーカー）と変換に必要な
  チェックポイント・LavaSR・既定声のみ。**声の登録は AI環境が必要なまま**（要
  `tools/setup_release.py`）
- ビルド元の絶対パスを記録した `koeiro-root.txt` はステージングから除かれます。除いた
  実体は **インストール先フォルダ**を AI環境の置き場所として探すので、AI環境は
  `Koeiro.exe` の隣（`%LOCALAPPDATA%\Programs\Koeiro\vc_models`）に置く形になります
- **実行ファイル版の自動更新は setup.exe 経由**です（「調整 → アプリ → 更新を確認」）。
  アプリはリリースから `koeiro-<tag>-windows-setup.exe` と `-checksums.txt` を取り寄せ、
  sha256 を検証してから無対話で適用し、インストーラがアプリを閉じて新版を起動します。
  検証情報が無い／合わない版は適用しません。凍結バンドル内をファイル差し替えする方式は
  採れません（起動中の exe と `_internal\*.dll` は Windows にロックされるため）
- 更新の記録は `%LOCALAPPDATA%\Koeiro\logs\update.log` に出ます

### Linux（実行ファイルとタスクバー登録）

```sh
# 1. 配布TARを展開し、そのフォルダで1回だけ環境を作る
python3.12 tools/setup_release.py

# 2. 実行ファイルを作る
.venv/bin/python tools/write_build_root.py
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m PyInstaller Koeiro.spec --noconfirm

# 3. 起動
./dist/Koeiro/Koeiro
```

Linuxのタスクバーやドックは、exe埋め込みではなく**アプリ名でアイコンを探します**。
そのためアプリの入口（.desktop）とアイコンの登録が要ります。

```sh
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps
cp Koeiro.desktop ~/.local/share/applications/
cp assets/Koeiro-256.png ~/.local/share/icons/hicolor/256x256/apps/Koeiro.png
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

- アイコンは `assets/Koeiro-*.png`（16〜1024）です。使うサイズを
  `~/.local/share/icons/hicolor/<サイズ>x<サイズ>/apps/Koeiro.png` に置きます。
  作り直すときは `python tools/build_desktop.py`
- ウィンドウ内のアイコンはWindowsと同じ経路（Qtのウィンドウアイコン）なので、
  デスクトップ登録が無くても画面内は正常に出ます。出ないのはドック側だけです
- **Discordの表示はLinuxでも同じです。** アクティビティの画像はDiscord自身がURLから
  取得するため、OS側のアイコン設定とは無関係です（[notes/discord_presence_image.md](notes/discord_presence_image.md)）

### Linux（凍結版のバンドル）

Linux の実行ファイルも作れます。PyInstaller は動かした OS 用の物しか作れないので、
Docker Desktop を使ってコンテナ内でビルドします（手順は [PUBLISHING.md](PUBLISHING.md)）。

```sh
#ビルド側（Windows でも Linux でも、Docker Desktop が起動していること）
python tools/build_linux_bundles.py --tag v0.13.2 --kind app
python tools/build_linux_bundles.py --tag v0.13.2 --kind worker
# → dist/linux/koeiro-<tag>-linux-app.tar.gz と -linux-ai-pack-{1,2}.tar.gz
```

- 展開すると `Koeiro/`（`Koeiro` と `_internal`）が出ます。実行にはシステムの
  `libportaudio2` と Qt の実行ライブラリ（`libgl1 libegl1 libglib2.0-0 libxkbcommon0
  libdbus-1-3 fontconfig`）が必要です（空の Debian コンテナで `--smoke-test` を走らせて確認した一覧）
- AI は `koeiro-<tag>-linux-ai-pack-1.tar.gz` と `-2.tar.gz` を**同じフォルダに展開**して
  入ります（`sh install-ai-pack.sh <展開先>` が2つまとめて展開します）。Python 不要
- 凍結版の自動更新は新版バンドルを落として sha256 検証 → インストール先ごと差し替え →
  再起動です（Linux では実行中の exe があるフォルダの rename が通るので成立します。
  Windows はロックされるため setup.exe 経由）

---

## 🤖 AIエージェントによる自動セットアップ（Codex / Claude Code 用）

Claude Code や Codex などの自律型CLIエージェントをご利用の場合は、下記プロンプトをそのまま貼り付けることで環境構築から疎通確認までを自動実行できます。

<details>
<summary>📋 コピペ用プロンプトを開く</summary>

```text
https://github.com/heynegix/koeiro をセットアップしてください（ボイスチェンジャー Koeiro）。
まず作業用ディレクトリ（例：ホーム直下のkoeiro。英数字のみのパス推奨）に
`git clone https://github.com/heynegix/koeiro` して、そこを作業場所にしてください。
同名のディレクトリが既にある場合は中身を確認し、別名でcloneしてから報告してください。
特定の版が必要な場合のみ `git clone --branch vX.Y.Z` を使ってください。
OSを判定し、WindowsならPowerShell、Linuxならbashで実行してください。
[.venv, vc_models/*/.venv, settings.json, logs/, models/user_voices/] は消さない・壊さないこと。gitへのコミット・pushは禁止。

1. Python 3.12系があるか確認（Windows: `py -3.12 --version`、Linux: `python3.12 --version`）。
   無ければOS標準の方法で用意してください（Windows: python.org か `winget install Python.Python.3.12`、Linux: deadsnakes 等）。git と uv も必要です。無ければ同様に用意してください。
2. `tools/setup_release.py --dry-run` で手順全体を把握してから本実行してください
   （Windows: `py -3.12 tools/setup_release.py`、Linux: `python3.12 tools/setup_release.py`）。
   モデル取得（約2GB）も既定で含まれます。後回しにする場合だけ `--no-models` を付けてください。
3. 1ステップでも失敗したら中断し、実行コマンドと末尾30行の出力を報告して指示を仰いでください。
   自己判断で版の固定・手順の省略・別手段への切替をしないでください。
4. 成功したら起動確認をしてください。GUI用Python（Windows: `.venv\Scripts\python`、Linux: `.venv/bin/python`）で `app.py --smoke-test` を実行します（画面なしの場合は `QT_QPA_PLATFORM=offscreen` を先に設定。Windows: `$env:QT_QPA_PLATFORM='offscreen'`）。
   エラーなく終了することと `logs/app.log` の末尾を確認して報告してください。
```
</details>

---

## 💻 開発者向け手動セットアップ

Koeiro は **GUIフロントエンド用環境** と **AI推論ワーカー用環境** を独立した仮想環境として管理します。

### Windows (PowerShell)

```powershell
# 1. リポジトリのクローン
git clone https://github.com/heynegix/koeiro.git
cd koeiro

# 2. GUI用環境の構築
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 3. AIワーカー環境（MeanVC2 + LavaSR）の構築
py -3.12 -m venv vc_models\meanvc2\.venv
.\vc_models\meanvc2\.venv\Scripts\python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.\vc_models\meanvc2\.venv\Scripts\python -m pip install -r vc_models\meanvc2\requirements.lock.txt

# 4. モデルのダウンロード・配置（tools/setup_release.py を使うか手動配置）
py -3.12 tools/setup_release.py

# 5. アプリの起動
.\.venv\Scripts\python app.py
```

### Linux (Bash)

```bash
# 1. リポジトリのクローン
git clone https://github.com/heynegix/koeiro.git
cd koeiro

# 2. GUI用環境の構築
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 3. AIワーカー環境（MeanVC2 + LavaSR）の構築
python3.12 -m venv vc_models/meanvc2/.venv
vc_models/meanvc2/.venv/bin/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
# ※Linuxでは requirements.lock.txt 内の win32-setctime 行を除外してインストールしてください
grep -v "win32-setctime" vc_models/meanvc2/requirements.lock.txt > /tmp/req.lock.txt
vc_models/meanvc2/.venv/bin/python -m pip install -r /tmp/req.lock.txt

# 4. モデルの取得
python3.12 tools/setup_release.py

# 5. アプリの起動
.venv/bin/python app.py
```

### ⚡ GPU（CUDA）アクセラレーションの有効化

NVIDIA GPU を使用して低遅延変換を行う場合は、AIワーカー側の PyTorch を CUDA 版に差し替えます。

```bash
# Windows (PowerShell) - CUDA 12.6 の例
.\vc_models\meanvc2\.venv\Scripts\python -m pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu126

# Linux - CUDA 12.6 の例
vc_models/meanvc2/.venv/bin/python -m pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu126
```
> [!NOTE]
> 「調整」引き出しの「実行デバイス」を「GPU」に変更することで有効化されます。CUDA非対応環境で明示的に「GPU」を指定した場合は、安全のため起動時にエラーログを出力して停止します。

---

## 📦 AIモデルの手動配置

自動スクリプトを使用せず手動でモデルを配置する場合の配置ツリーです：

```text
koeiro/
└── vc_models/
    └── meanvc2/
        └── repo/  ← https://github.com/ASLP-lab/MeanVC2 を配置
            ├── ckpts/
            │   ├── pretrained_models/
            │   │   ├── meanvc2_40ms_40ms.safetensors
            │   │   └── meanvc2_120ms_40ms.safetensors
            │   └── vocos/
            │       └── vocos.pt
            └── preprocess/
                └── ckpts/
                    ├── fastu2pp_80ms.pt
                    └── fastu2pp_160ms.pt
```
*チェックポイントは Hugging Face [ASLP-lab/MeanVC2](https://huggingface.co/ASLP-lab/MeanVC2) より取得可能です。*

---

## 🗣️ 音声合成（TTS・任意 / 拡張パック）

翻訳ボイスなどの読み上げに使う、**軽量な音声合成**を任意で導入できます。モデルは
同梱せず、各自の環境でダウンロードします（本リポジトリの他のモデルと同じ方針）。

- **Kokoro-82M**（Apache-2.0）× **kokoro-onnx**（MIT）を採用。ライセンス的に問題なく、
  MIT の Koeiro にそのまま載せられます。重みは同梱せず、ユーザーが取得します。
- int8量子化で約110MB（＋声ファイル約28MB）。**低スペックPCでも動く軽さ**を優先した選定です。
- 低スペックでは遅く、実用速度は保証しません（読み上げ用途や GPU 機では快適）。

### 導入手順

```bash
# 1回だけ。モデル（約140MB）を models/tts/ に取得し、専用venv（vc_models/tts/.venv）を作ります
.venv/bin/python tools/install_tts.py            # Linux
.\\.venv\\Scripts\\python tools\\install_tts.py   # Windows

# 疎通確認：短い文を合成して WAV を書き出します（試聴用。処理時間とRTFを表示）
vc_models/tts/.venv/bin/python tools/verify_tts.py --text "Hello from Koeiro"
```

- モデルは `models/tts/kokoro/`、実行環境は `vc_models/tts/.venv` に入ります（どちらも git 管理外）。
- このビルドの kokoro-onnx は **英語（`en-us` / `en-gb`）** に対応します（翻訳ボイスの出力先）。
  他言語・日本語は別 G2P・別モデルが必要です。
- リポジトリを日本語パス（例: `D:\ボイチェン`）に置いても動くよう、espeak のデータは
  ASCII の一時フォルダ（`%TEMP%\koeiro-espeak`）へ自動ミラーします。
- `tools/verify_tts.py` が出す時間は**モデルのみ**の値で、エンドツーエンド遅延ではありません。
  聴感は WAV を実際に聴いて確認してください。N150実測: ロード約6秒・2.4秒の音声に約23秒
  （RTF≈10、低スペックでは実用速度を保証しません）。

---

## 🧪 スモークテスト & CI

GUIを立ち上げずに基本機能のヘルスチェックを行うことができます：

```bash
# ヘッドレス環境での疎通テスト
QT_QPA_PLATFORM=offscreen .venv/bin/python app.py --smoke-test
```
テストログは `logs/app.log` に出力されます。単体テストは `python -m pytest`（GUIはオフスクリーンで実行されます）。

---

## 📜 ライセンス & クレジット

本プロジェクトは **MIT License** のもとで公開されています。  
詳細は [LICENSE](LICENSE) および [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) をご参照ください。

### 謝辞 / Acknowledgments
Koeiro は以下のオープンソース技術・モデルの成果を活用しています：
- **[MeanVC2](https://github.com/ASLP-lab/MeanVC2)** (ASLP-lab) - ストリーミング・音声変換バックエンド
- **[LavaSR](https://github.com/LavaSR/LavaSR)** - 音声帯域復元・超解像モデル
- **[Vocos](https://github.com/gemelo-ai/vocos)** - ニューラルボコーダー
- **[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)** (hexgrad) - 軽量音声合成（Apache-2.0、任意導入）
- **[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)** (thewh1teagle) - Kokoro の ONNX 実行ランタイム（MIT）


<p align="center">
  <img src="assets/logo.png" alt="Koeiro Logo" width="520">
</p>
