# Vera Platform — 全体系の文書 / The Whole System

構造(立体十字)から公開面(verantyx.ai / HF)・進化の統治までの一枚。全数値は
公開されている `vera.db` に対する実測で、`python3 -m verantyx.card_numbers`
で再現できます。

## 1. 構造 / Structure

```
立体十字 = 6腕 × 4面 = 容量24     (面に載らない語は経路 0/60 — 容量法則)
面   … 項目の席(核と facet)
辺   … 関係の席(同一文共起 — provenance から張る。203万辺)
表面 … 腕間の伝導(distinct_faces + route: 経路 0/52 → 52/52)
木   … conduct_tree(36法・二層降下 95%・誤0・蔵書外全棄権)
```

原理は一つ: **束ねず、重ねる**。二つの信号を一つの票にした 6 例は全て悪化、
一段の型付き出力を次段に渡した例は全て改善。

## 2. 判定 / Verdicts

答える: `ANSWER / SEEDED / ATTESTED / ANSWER_BY_INTERSECTION`
拒否する(9型・各型に remedy): `UNKNOWN_NOT_PRESENT / NO_EVIDENCE /
TIME_DEPENDENT / NO_SUBJECT / LANGUAGE_NOT_HELD / UNDERDETERMINED /
CONDITIONS_CONFLICT / INSUFFICIENT_EVIDENCE / NOT_ATTESTED`

**閉包**: 保持しない記号は出力できない(60/60)。代償として未知語の意味説明は
0% — 同じ性質の表裏。**同点は棄権**(決定論的に割ると一致が捏造される:
86件73.3% → 321件23.7% の測定)。

## 3. 答えに添う信号 / Signals Beside the Verdict

| 信号 | 意味 | 由来 |
|---|---|---|
| `grain` n/6 | 切り方違いの段の一致(構造の合意) | 粒度の階段 |
| `witnesses` n/m | 選定規則違いの独立到達(証拠の合意) | 5 証人 |
| `order_evidence` | ranked / arbitrary / aspect | 面の count |
| `facet_origin` | 各面の出典葉 | provenance |
| `tier` strong/medium/weak | 上記の合成階調(読者の割引率) | 較正表 |
| `known_gap` | 既知の欠落か(gap 十字 2,180 核) | vera_gaps.db |

二種の合意は**混ぜない**(混ぜると蔵書外 0→8)。tier は判定を変えず、
確からしさだけを言う。

## 4. 進化の統治 / Governed Evolution

**原則: AI は提案し、人間が承認する。** 黙って入るものは無い。

```
入口(3つ)                          承認
─ ブラウザの拒否/「取得 X」    →  提案→プレビュー→[承認して取り込む]
                                  (自動承認トグルON時も内容は都度表示)
─ 世界からの持ち寄り           →  GitHub Issue (label: vera-suggest)
   [Vera に情報を持ち寄る]ボタン     所有者が読む + release 実行 = 二重承認
─ IDE / CLI                   →  MCP: propose_ai_facts → accept_ai_fact
                                  (隔離キュー。承認まで ask に出ない)
```

取り込みは全て同じ正面玄関(`ingest_documents`)を通り、マニフェスト
(name/url/sha256/選定規則)に記録される。

## 5. 版とリリース / Versions & Releases — DB なしの蓄積基盤

```
vera-<構造世代>-<日付>      例: vera-A-20260811 (89,369核)
  A のまま = 幾何・門が不変、知識だけ成長
  B へ    = 構造の大改良。知識は A から引き継ぐ
```

```bash
python3 -m verantyx.release --notes "..."         # 承認後の一発
python3 -m verantyx.release --gen B --notes "..." # 構造リリース
```

一発で: issue+キュー取込 → 再構築 → **検証**(答え・形) → 日付版刻印 →
モデル repo(コミット履歴=チェックポイント履歴) → Space の `versions/`。
Space/verantyx.ai の**起動前トグル**で任意の版を選べる。ロールバック=旧版を
選ぶだけ。監査= issue 履歴+コミット履歴。**DB はこの版の列そのもの。**

## 6. 公開面 / Surfaces

| 面 | 内容 |
|---|---|
| https://verantyx.ai/vera3d/ | 3D+チャット+50手記憶(構造上の経路として描画)+承認制成長+版トグル |
| https://kofdai-ask-vera.static.hf.space/vera3d.html | 同一物 |
| 同 /(index) | 焼き込みバンク+簡易生エンジン |
| https://huggingface.co/kofdai/vera-alpha | vera.db(重み相当)・辺・writer・全マニフェスト |
| ローカル | `python3 -m verantyx.serve_view3d --page viewer` — SSE 実況・最速 |

ブラウザ実行は Pyodide 上の**本物の CPython + 本物の verantyx**(JS 再実装
なし)。転送 ~46MB(gz)。完全版との差は Yes/No が保守側に倒れる 1 点のみ
(24面切りの正直な代償)。

## 7. 参加の仕方 / How to Participate

- **ブラウザだけ**: 質問 → 拒否 → [取得して確認] → 承認。
  [記録をファイルへ] で会話と成長の記録を端末に JSONL 保存 —
  そのまま `grow --queue` が読める形式なので提出物になる
- **GitHub**: [Vera に情報を持ち寄る] → prefill された Issue
- **CLI**: `python3 -m verantyx.grow --queue mine.jsonl` /
  `--github` で公開提案も取り込み
- **IDE (MCP)**: `remember` / `propose_ai_facts` → 人間の `accept_ai_fact`

## 8. 既知の限界 / Honest Limits (measured)

- 未知語の**意味**説明 0%(閉包の代償)・要約 3.6%・連鎖は減衰(交差で代替)
- 文生成: 話す 6割・文法の粗さは SELECTION 密度 3.8観測/穴が上限
- 英語: 門・観点・真偽は同格化済み。**階段・writer・証人は未整備**
  (tier が weak と正直に言う)
- 同義語層なし・誤字耐性なし
