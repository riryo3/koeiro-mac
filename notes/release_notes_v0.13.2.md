# Koeiro v0.13.2: Windows は setup.exe 配布、実行ファイル版の自動更新が実際に効く

## 🌟 ハイライト

* **実行ファイル版（`Koeiro.exe`）の自動更新が、初めて動く作りになりました**
  従来は配布アセットがソースツリーの zip だけで、凍結バンドルをその zip で差し替えに
  いく設計でした。実行中の `Koeiro.exe` と `_internal\*.dll` は Windows にロックされて
  フォルダごと退避できない上、ソースツリーを当てると exe 自体が消えるため、
  **この経路は一度も成功し得ませんでした**。今はアプリ本体だけを同梱した
  `koeiro-<tag>-windows-setup.exe` をリリースへ添付し、アプリがそれを検証して無対話適用します。
* **BOOTH 等のダウンロード販売に出せる形**になりました（1ファイル 46.3 MB・後述の実測）。

---

## 🛠 追加・修正

### 実行ファイル版の更新（Windows）

* 更新の確認で、凍結ビルドは `-windows-setup.exe` と `-windows-checksums.txt` を選びます。
  ソースツリーの zip は**選ぶ対象から除外**しました（間違えて当てるとインストール先を壊すため）。
* ダウンロードした setup.exe は **sha256 を検証してから**実行します。検証情報が無い版・
  一致しない版は適用しません（「自動更新できません」と出して止まります）。
* 検証を通った setup は `/VERYSILENT /NORESTART /SUPPRESSMSGBOXES` で起動し、アプリ側は
  終了します。アプリを閉じて新版を起動し直すのはインストーラの仕事にしました。
* インストーラ側は `CloseApplications=yes` で起動中のアプリを検出して閉じ、最後に
  `{app}\Koeiro.exe` を起動します。Inno の `RestartApplications` は実機で復帰しなかったため、
  起動は `[Run]` 側で保証しています。
* 更新の試行と失敗は `%LOCALAPPDATA%\Koeiro\logs\update.log`（アプリ本体の失敗は
  同じフォルダの `app.log`）に残ります。今までヘルパーの出力は破棄されていて、
  失敗すると「アプリが閉じるだけ」でした。
* インストール済み版が更新先を見つけられないときの原因が伝わるように、リリースに
  インストーラが無い版では「この版には実行ファイル用のインストーラがありません」と出します。

### インストーラ（配布物）

* `installer\Koeiro.iss`（Inno Setup 6）と `tools\build_windows_setup.py` を追加。
  既定のインストール先は `%LOCALAPPDATA%\Programs\Koeiro`（ユーザー単位・管理者権限を要求しない）。
  Program Files を避けたのは、サイレント更新が同意を要求されないようにするためです。
* 配布ステージから `koeiro-root.txt`（ビルド元の絶対パス）を除きます。除いた実体は
  **インストール先フォルダ**を AI環境の置き場所として探すので、AI環境は exe の隣に置く形になります。
* `LICENSE.txt`・`README.md`・`THIRD_PARTY_NOTICES.md` をインストール先に入れます。
* デスクトップのショートカットは既定OFF（サイレント更新で、消したアイコンが復活しないように）。
* ビルドツールは、`src` より古い `dist` の exe で setup を作ろうとすると止まります
  （`--rebuild` か `--allow-stale` で明示）。`settings.json`・`logs`・`recordings` が
  ステージに混入していても止めます。

### 開発者向け

* ソースツリー配布（`release-dir`）の更新は従来の差し替え経路のままです。凍結ビルドから
  その経路が呼ばれると明示的に断る門番を入れました。

---

## ⚠️ 既知の制限

* **setup.exe には AI がありません。** AI Voice は引き続き `tools/setup_release.py`
  （Python 3.12・git・uv が必要）か、これから作る AIパックでの導入になります。
  Original と Female DSP は setup 単体で動きます。
* 自動更新が使えるのは **setup.exe を添付した版から**です。Actions はソースツリーしか
  作らないので、タグ push 後に手元で setup を作って `gh release upload` する順が必要です。
* 配布物に Authenticode 署名は入れていません。sha256 検証は破損・途中切れの検知で、
  リポジトリが乗っ取られた場合の防御ではありません。

---

## ✅ この版で実測したこと

* `koeiro-v0.13.1-windows-setup.exe` 46.3 MB（BOOTH の1ファイル上限 1.2 GB に対して余裕あり）
* クリーンインストール → インストール先に `koeiro-root.txt` が無いこと、163 MB、
  `Koeiro.exe --smoke-test` が exit 0（AI環境は「見つかりません」と丁寧に出て停止しない）
* **起動中のアプリへ `/VERYSILENT` で上書き** → RestartManager が `Koeiro.exe` を検出・閉鎖 →
  ファイル差し替え成功 → `[Run]` で新プロセスが自動復帰（PID と起動時刻 07:53:12 を確認）
* `sha256sum` と `koeiro-<tag>-windows-checksums.txt` の値が一致
* テスト: 1189 passed / 11 skipped（更新機構と setup ビルドに18本追加）
* **0.13.1 → 0.13.2 の通し更新を実ネットワークで確認**（2026-10-13 08:23 JST）
  * 更新確認と同じ `check_now` が v0.13.2 を「インストーラあり」で返し、
    `koeiro-v0.13.2-windows-setup.exe` 48,597,793 バイトを落として sha256 検証を通った
  * `/VERYSILENT` 適用後、`%LOCALAPPDATA%\Programs\Koeiro\Koeiro.exe` がこの場で作り直した
    0.13.2 と一致（sha256 先頭16桁 `b7eef92c005b7798`）。インストール先に `koeiro-root.txt` は無い
  * インストーラが更新後のアプリを起動し、PID が入れ替わった（`Koeiro.exe` 18032）
  * `%LOCALAPPDATA%\Koeiro\logs\update.log` に `verified` / `launching installer` が残った
  * 駆動は venv の Python で `sys.frozen` を立てて行いました。GUI のボタン押下そのものは
    オフスクリーンのテストで分岐のみ検証しています（実クリックの目視確認はしていません）
