# MeanVC2 の入出力整合（実測）と legacy frontend の 50 ms

> このノートは `src/vc/meanvc2.py` の `buffer_frames_ms` / `frontend_latency_ms` /
> `algorithmic_buffer_ms` の分離と、`model_buffer_ms=1490` の根拠です。
> すべて**オフライン計算**で、音声デバイスは開いていません（AGENTS.md の音声検証方針の対象外）。

## 何を測ったか

モデルに入れた音が、どのくらい遅れて出てくるか。遅延はコードの前提値ではなく実測が必要です。
前提値が 50 ms 小さかったため、一括変換の出力が入力より 50 ms 遅れていました。

## 方法

- 環境: `vc_models/meanvc2/.venv`（torch 2.5.1+cpu）、CPU、`models/user_voices/<標準ボイス>`。
- 入力: `reference.wav`（16 kHz）の先頭 8 秒。`process_chunk` に 2560 サンプルずつ、リセット直後から投入。
- 遅延の推定: 入出力の**対数エネルギー包絡**（10 ms フレーム）の正規化相互相関のピーク位置。
- 計測器の検証: 既知の 600 ms シフトを与えると **600.0 ms** を返す（同一信号・同一長）。
- 有効桁: 10 ms。

```python
# 再現（作業ツリーのルートで）
vc_models/meanvc2/.venv/Scripts/python.exe <計測スクリプト>   # 参考: tools には未収録の一時スクリプト
```

## 結果（遅延線の計算値 = 修正前の前提値）

| frontend | group / vocoder | 実測 | 前提（修正前） | 差 |
|---|---|---|---|---|
| legacy  | 6 / 36（出荷構成） | 1490 ms | 1440 ms | **+50 ms** |
| legacy  | 1 / 1 | 530 ms | 480 ms | **+50 ms** |
| aligned | 6 / 36 | 1600 ms | 1600 ms | ±0 |
| aligned | 1 / 1 | 640 ms | 640 ms | ±0 |

同じ +50 ms が group 6 でも group 1 でも出るので、**grouping には比例しません**。
aligned 側は差が 0 で、既存コードの aligned 前提値（`naturalness_profiles.py` の
`model_buffer_ms=1600`）とも一致しました。つまりズレは legacy frontend 側だけです。

## 原因の分解

- **遅延線（buffer）**: `reset()` が `pending_audio` を確保する長さ。grouping が動かす部分。
- **frontend 固有**: legacy の 50 ms。`wave_tail`(240 サンプル) が fbank 窓に再入する
  ぶんの frame-origin のずれで、buffer には含まれていません。
- 合計（= 真の入出力遅延）: `buffer + frontend 固有`。

## 影響（実測）

修正前は一括変換のトリムが `algorithmic_buffer_ms + grid + phrase_extra` で、
真の遅延より 50 ms 短い値でした。結果:

- 一括変換の出力が入力に対して **残差 +50 ms**（`convert_utterance` → 入出力の相互相関）。
- `retrospective_repair` / `retrospective_pitch` / `utterance_metrics` は 40 ms フレームで
  入力と出力を同じ添字で比べるため、補正が**隣のフレーム**に乗っていました。
- 経路自身の指標で確認: `energy_correlation` **0.7873 → 0.9292**（同一入力・同一条件、
  トリムだけを実測値に合わせた before/after。スキャンは 0 ms で自分のピークに乗ります）。

補完ステージの整列だけを切り出した A/B（トリムは両腕とも実測値に固定）:

| 補完の整列 | energy_correlation | （参考）voice_f0_range_st |
|---|---|---|
| 1490 ms（実測） | 0.9292 | 5.160 |
| 1440 ms（旧前提） | 0.9083 | 7.867 |

`voice_f0_range_st` は記述値で、大きいほど良いという意味ではありません。

## 修正

- `buffer_frames_ms`（遅延線）/ `frontend_latency_ms`（実測 50 ms、aligned は 0）/
  `algorithmic_buffer_ms`（= 合計、トリム・整列・表示が使う値）に分離。
- `reset()` の `pending_audio` は `buffer_frames_ms` で確保（音声経路は変えない）。
- profile の `model_buffer_ms` を 1490 に更新（GUI がそのまま表示する数値）。

## 修正後の再測定

| 対象 | 結果 |
|---|---|
| legacy 6/36 | 実測 1490 == 前提 1490（差 0） |
| legacy 1/1 | 実測 530 == 前提 530（差 0） |
| 一括変換の残差 | **0 ms**（修正前 50 ms） |
| energy_correlation | **0.9292**（修正前 0.7873） |

音声経路そのもの（遅延線と合成結果）は変えていません。変わったのは、遅延の見積もりが
使われる 3 か所（一括変換のトリム・補完ステージの整列・表示）です。

## 未計測（このノートの限界）

- **聴感は未確認**です。指標が自分のピークに乗ったことまでしか言えません。
- GPU（CUDA）と他ボイス・他素材での再測定は未実施。遅延は構成依存なので、
  構成を変えたら再測定してください。
- 残差 ±20 ms 以内の metric グリッド量子化は残っています（40 ms フレームの指標）。
