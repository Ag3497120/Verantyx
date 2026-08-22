# 事前登録: junk門を役割タガーへ繋ぎ、逆方向の帯にも適用する

日付: 2026-08-19 / 実測前に登録

## 発端(実測済み)
前セッションが REVERSE_UNIQUE の初誤答を観測(1/181、英字 junk 核)。
機序を測ると2つの穴が重なっていた:

1. **`is_junk_core` が役割タガーを参照していない**。139語の手書き
   STOP_CORES しか見ておらず、基本的な英語機能語 26/27 が素通り —
   `the` は ja 店で **6,074面** を持つ核として立っている。
   ところが同じモジュールの `_cap_content` は既に
   `is_function_role(tag_role(...))` を使っており、**タガーは全部
   正しく知っている**(the=DET, of=ADP, is=AUX … 25/25 機能語判定、
   内容語8/8は非機能語、日本語核15/15も非機能語で誤爆なし)。
   実装済みで、この関数からだけ未到達。

2. **`direction_band` が junk 門を一度も参照していない**。
   ja の facet 後退路(consensus_store:716)は `is_junk_core` を通すが、
   帯は通さない。REVERSE_UNIQUE / REVERSE_SPECIFIC の答えは全部帯から
   出るので、junk 核が帯を取ると誤答になる。

## 変分(2つ、同時)
A. `is_junk_core` に `is_function_role(tag_role(tok))` を足す
   (STOP_CORES は残す — 手書きの列を捨てるのではなく、タガーを重ねる)
B. `direction_band` が junk 核を帯に入れない

## 判定(事前)
採用条件(エンジン端300探針、seed 42 固定):
  - 誤答(ANSWER誤 + REVERSE_UNIQUE誤 + REVERSE_SPECIFIC誤)が増えない
  - 正解が減らない(238 以上)
  - forks 158/158
  - 既知正答(正当防衛/時効/傷害罪/言語とは)不変
別集合(seed 4242)でも誤答が増えないことを確認する。
