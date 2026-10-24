# BOOTH 出品の下書き（v0.13.4）

実測値だけ入れてあります。文体・販促の言い回しはここで調整してください。
ファイルの sha256 は手元で計算した値です（GitHub へ上げた後の突き合わせは未実施）。

---

## 1. 何を出すか（商品構成）

**おすすめは1商品・10ファイル。** AIパックはアプリ本体と同じフォルダへ展開する作りのため、
アプリ本体とAIパックを別商品にすると設置の手順が2本に割れて事故が増えます。

| ファイル | 大きさ | 中身 |
|---|---|---|
| `koeiro-v0.13.4-windows-setup.exe` | 46.3 MB | Windows のアプリ本体（AI同梱なし） |
| `koeiro-v0.13.4-windows-checksums.txt` | 99 B | 上の sha256（アプリの自動更新が読む） |
| `koeiro-v0.13.4-ai-pack.exe` | 2.8 MB | Windows 用 AIパックのインストーラ本体 |
| `koeiro-v0.13.4-ai-pack-1.bin` | 664.4 MB | 同上・分割データ（インストーラと同じフォルダに置く） |
| `koeiro-v0.13.4-ai-pack-checksums.txt` | 188 B | 上の sha256 |
| `koeiro-v0.13.4-linux-app.tar.gz` | 96.6 MB | Linux のアプリ本体（凍結 `Koeiro` + `_internal`） |
| `koeiro-v0.13.4-linux-ai-pack-1.tar.gz` | 430.4 MB | Linux 用 AIパック（凍結 `KoeiroWorker` + `_internal_worker` + `install-ai-pack.sh`） |
| `koeiro-v0.13.4-linux-ai-pack-2.tar.gz` | 360.9 MB | 同上・モデルデータ（MeanVC2 / LavaSR / 標準ボイス） |
| `koeiro-v0.13.4-linux-checksums.txt` | 306 B | Linux 3点の sha256（`sha256sum -c` 形式） |

* 合計 **約1.60 GB**（BOOTH の合計上限 10 GB に対して余裕）
* 最大ファイル 664.4 MB（BOOTH の1ファイル上限 1.2 GB を超えないことを計算で確認）
* 2商品に割るなら: Windows 5ファイル 713.6 MB / Linux 4ファイル 887.9 MB。ただし版数を出すたびに
  両方の商品を更新することになります
* 数字は MiB（1024 基準）です。BOOTH の画面が出すサイズは 10 進なので少し大きく見えます。
  アップロード後は、表示サイズではなく同梱の `-checksums.txt` と突き合わせてください

---

## 2. そのまま貼れる文章

### タイトル案

```
Koeiro v0.13.4 – 声帯域復元つきリアルタイムボイスチェンジャー（Windows / Linux）
```

### 概要

```
マイクの声を、その場で別の声に置き換えるデスクトップアプリです。
Original・Female DSP・AI Voice の3つのスロットを同時に使えます。
AI Voice は MeanVC2 + LavaSR で、音声を送って戻すのではなく手元で処理します。
Windows と Linux の実行ファイル版を同梱しています。
v0.13.4 は、実機で出ていた不具合の修正が中心です
（音声処理の例外、モード切替、声フォルダの読み取り、自動更新の案内）。
```

### できること

```
- 3つの出力スロット: Original（無処理）/ Female DSP（DSPのみ）/ AI Voice（MeanVC2 + LavaSR）
- 一括変換（発話ごとにまとめて変換）と逐次変換（リアルタイム）の2ルート
- Discord などへの仮想マイク出力（WASAPI 48 kHz / 256 フレーム固定）
- 標準ボイス1種同梱。声の登録は AI 開発環境のある機械で追加できます
- 起動後の自動更新（GitHub Releases を見るため、ネットワークが要ります）
```

### 必要環境

```
Windows: Windows 10 / 11 の 64bit。インストール後 約1.6 GB
Linux:   Debian 12 / Ubuntu 22.04 系。インストール後 約1.9 GB。
         システムライブラリとして libportaudio2 と Qt の実行ライブラリ
         （libgl1 libegl1 libglib2.0-0 libxkbcommon0 libdbus-1-3 fontconfig）が必要
CPU の目安: 一括変換-最速で Intel N150（論理4）が RTF 0.94（v0.13.3 の同一ウィンドウ実測。
         この版で AI の計算そのものは変えていません）
メモリ: AI ワーカーが約 0.9 GB（実測 869 MB）
```

### 設置手順

```
【Windows】
1. setup.exe を実行（ユーザー単位・管理者権限不要。既定は %LOCALAPPDATA%\Programs\Koeiro）
2. ai-pack.exe を実行し、インストール先を 1 と同じフォルダに向ける
   （ai-pack-1.bin を同じフォルダに置いてから起動してください）
3. Koeiro.exe を起動

【Linux】
1. koeiro-v0.13.4-linux-app.tar.gz を展開 → `Koeiro/Koeiro`
2. ai-pack-1 と ai-pack-2 と checksums を同じフォルダに集めて
   `sh install-ai-pack.sh <1で展開した Koeiro フォルダ>`
3. ./Koeiro/Koeiro を起動
```

### 注意事項

```
- 声の登録（自分の声を作りに足す機能）は、凍結ビルドだけでは動きません。AI 開発環境
  （Python 3.12・git・uv が入った `tools/setup_release.py` の通る環境）のある機械で
  登録して、出来た声をフォルダごと持って来る形になります。変換は凍結ビルドだけで動きます
- AI Voice は「声を別の声に寄せる」処理で、音声品質はCPU性能に依存します。
  一括変換-最速は待ち時間を優先するため、声色の精度が落ちます
- 配布物にコード署名は入れていません。アプリ内蔵の検証は sha256 による
  破損・途中切れの検知で、配布元が乗っ取られた場合の防御ではありません
- 他人の声無断作成・なりすましには使わないでください
```

### ライセンス表記

```
アプリ: この商品の作成者が権利を持つ部分については購入者1名分の利用許可
AIモデル: MeanVC2（Apache-2.0）、LavaSR（Apache-2.0）、WavLM-Large / ECAPA の
前処理チェックポイント（帰属表示は同梱の THIRD_PARTY_NOTICES.md に列挙）
GUI基盤: PySide6（LGPLv3、動的リンクで再リンク可能性を維持、ライセンス文同梱）
同梱文書: LICENSE.txt / README.md / THIRD_PARTY_NOTICES.md
```

---

## 3. 試聴ファイル

```
promo/public/audio/voice_demo_original.wav   330,222 B  48 kHz mono 3.44 秒
promo/public/audio/voice_demo_converted.wav  314,574 B  48 kHz mono 3.44 秒
```

既存のプロモ用資産で、このペアを「元 / AI Voice」の説明に載せられます。**作成者の耳で
確認して採用してください。** この版の実測メモは「開発環境のワーカーと凍結ワーカーの
出力がビット同一」という計算の一致までで、音の良し悪しの判定は含めていません。

---

## 4. 出品前に埋める／確かめる

* [ ] 価格・決済後の案内文・サポート窓口・返品の扱い（BOOTH 側の変更事項を含む）
* [ ] 年齢表示・カテゴリ指定
* [ ] 「動作確認済み」の範囲を実態に合わせて書く（下記の実測／未確認をそのまま使う）
* [ ] 更新のお知らせ導線（GitHub リリースページのURL、または BOOTH での再配布方針）
* [ ] `PUBLISHING.md` の「公開前チェックリスト」を v0.13.4 で通す（同梱物・LGPL・既定声以外
      の声が入っていないこと）

---

## 5. 実測済み／未確認（このまま書ける線引き）

**実測**

* Windows: 0.13.1 → 0.13.2 の通し更新（setup.exe 検証 → /VERYSILENT 適用 → 新プロセス起動）。
  v0.13.3 以降の更新適用は回していません
* Windows: 凍結 AI ワーカーと開発環境ワーカーの変換結果がビット同一（max_abs_diff 0.0）。
  v0.13.4 の凍結ワーカーで再確認済み（`voice_demo_original.wav` 3.439 秒、一括変換 + LavaSR）
* Windows: 凍結アプリが `--smoke-test` で exit 0、`--help` が `Koeiro v0.13.4` と報告
* Linux: Debian bookworm のコンテナで、`install-ai-pack.sh`（ハッシュ検証込み）→
  インストール先の `KoeiroWorker`（実行ビットあり）→ 一括変換 + LavaSR で 3.439 秒の
  保存音声を 165,072 サンプルに出力（帯域復元のフォールバックなし）
* Linux: オフスクリーンでの `--smoke-test` 成功、バンドルが自分で `v0.13.4` と報告すること
* Linux: 配布物3点の `sha256sum -c` が手元で通り、アプリの `--help` と合わせて確認済み
* テスト一式: 1239 passed / 11 skipped（`-X dev`、ResourceWarning 0 件）

**未確認（書かない／「未確認」と書く）**

* Linux の実機デスクトップで、マイクとスピーカーを使った通話／Discord 運用
* Linux での RTF（コンテナ内の1回の計測だけで、Windows と同条件ではない）
* Windows の AIパックを実際にインストールしての起動（`%LOCALAPPDATA%` の実環境を
  書き換えるため、v0.13.4 では回していない）
* 官能評価（音色・残響・ブレスの自然さ）— 誰が聞いても良いと思った記録はありません
* Windows 10 での動作（開発・検証は Windows 11 の実機）
* 配布物3点の sha256 と GitHub の digest の突き合わせ（アップロード後に確認する）
