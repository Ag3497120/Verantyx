# 事前登録: 転移の読む層 — 保留されていた較正段を、実データで埋める

日付: 2026-08-20。**この文書を書き終えてから測定を走らせる。**

## 経緯(モジュール自身が名指しした穴)

`transfer_outcomes.py` の docstring:

> This module deliberately does ONLY the recording. No calibration
> analysis ... those need real accumulated data to be anything but a
> guess, and were explicitly agreed to be a later step once this log has
> something in it.

棚卸し(EXPERIENCE_LEDGER_INVENTORY.md)の穴3つ目がこれ。今日、実データが
出た: harness_facts.json(3モデル×3変分の採否)と mathlib 輸入の可否。

## 設計(推測を持ち込まない — 機械は転移を報告し、理由は主張しない)

**機械が言えること**: 同じ事実が複数の文脈(モデル)で観測されたとき、
判定が全て一致すれば TRANSFERRED、割れれば CONTEXT_BOUND、
1文脈しか無ければ **UNKNOWN_SINGLE_CONTEXT**(予測しない)。

**機械が言ってはいけないこと**: 「なぜ転移したか」。次元(情報構造由来 /
モデル能力由来)は**人の仮説**で、それ自体が証拠を要する主張。台帳は
仮説を運ぶが、機械が生成はしない。

較正: 次元ごとの転移数を**数える**。観測が閾値(2文脈)未満の次元は
`UNKNOWN_TOO_FEW_CONTEXTS` — 数字を出さない(同点棄権の系譜)。

## 実装(既存部品のみ)

- verantyx/transfer_reading.py:
  - `unify()` — harness_facts の事実名を閉じた規則で正規化し
    (「hretry(f,3) が成功を増やす」と「hretry(f,3)」は同一事実)、
    文脈(モデル)ごとの判定表にする
  - `calibrate()` — TRANSFERRED / CONTEXT_BOUND / UNKNOWN_* を数える
  - 扉 `vera_transfer`(118→119扉)
- 正規化した名前と元の名前を**両方**残す(写像が読者に見える)

## 採択基準(完了基準5点)

- L1 正: 3モデルの9事実が3事実に畳まれ、**trunc64 が TRANSFERRED、
  retry3 と trunc400 が CONTEXT_BOUND** と機械が判定する
  (今日の実測と一致 — 手検算できること)
- L2 反証: 合成の偽転移記録(全文脈で一致していないのに TRANSFERRED と
  書いた行)を実観測と突き合わせて **CONTRADICTED** として検出
- L3 拒否: 1文脈しか無い事実は UNKNOWN_SINGLE_CONTEXT、閾値未満の
  次元は UNKNOWN_TOO_FEW_CONTEXTS(数字を出さない)
- L4 順序: 事実の読み込み順を反転しても較正結果が一致
- L5 独立: 出力の数字が harness_facts.json の生データと一致
  (第三者が手で数えられること)。fork で固定。

## 停止条件

L1違反(実測と機械の判定が食い違う)→ 正規化か判定の欠陥。修理してから
再測。L3違反(小さい n で数字を出す)→ **即棄却**(この製品が拒否のために
作った門を自分でくぐることになる)。
