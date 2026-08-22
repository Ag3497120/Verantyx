# 事前登録: attest_claim の極性配線 — 否定盲の修理

日付: 2026-08-20。**この文書を書き終えてから実装・測定する。**

## 欠陥(実測済み・二者独立)

隔離環境での実測(就業規則1文を load_documents 後):

    attest_claim(会社, 「…実費を支給する」)   -> ANSWER support=1.0
    attest_claim(会社, 「…実費を支給しない」) -> ANSWER support=1.0   ← 完全同点

第三者のブラインド評価も独立に発見(そちらでは否定のほうが高得点)。

**機序(コードで確定)**: `attest_llm._RUN` は漢字・カタカナの連のみを
抽出する。「支給**する**」と「支給**しない**」の差はひらがなにあり、
**構成上見えない**。語の重なりしか見ていない、という指摘は正確。

## 設計(思想からの導出 — 新しい賢さを持ち込まない)

過去4回の極性の失敗は全て「品詞ラベルを、それが答えられない問いに
使った」型。成功した修理は**位置を見る**ことだった(polarity.py の
`_JA_NEG_AFTER`: 語の直後の接尾を読む)。それをそのまま使う。

三つの結果を混ぜない(この製品の一番古い線):

    CONTRADICTED_BY_CORPUS      店が反対の極を**証拠として持つ** —
                                極性 facet(aspect:not_value / ¬x)を名指す
    UNKNOWN_POLARITY_UNJUDGED   店は語を持つが**極性を記録していない** —
                                支持率は肯定と否定を同点にするので、
                                その数字は主張できない(黙らない拒否)
    ANSWER / UNSUPPORTED        極性の争点が無いときのみ、従来どおり

## 実装(既存部品のみ)

- 主張側の極性: `polarity._JA_NEG_AFTER`(語の直後・位置で読む)+
  英語は閉じた否定語表を節内で。**語彙外の語でも明示的否定は読める**。
- 店側の極性: 主題の cross の `aspect:value` / `aspect:not_value`
  (ingest_polar_ja が実際に書く形式)と `¬x` 記法。
- 判定の順序: CONTRADICTED > UNJUDGED > 従来の支持率。
  (証拠があるものが、判定不能に勝つ)

## 採択基準(完了基準5点)

- K1 正: 測定済みの4例で**肯定と否定の verdict が分かれる**
- K2 反証: 極性証拠を持つ店(ingest_polar_ja で構築)で、反対極の主張が
  **CONTRADICTED_BY_CORPUS + 名指しされた facet**で落ちる
- K3 拒否: 極性証拠の無い店では **UNKNOWN_POLARITY_UNJUDGED**
  (黙って同点にしない)。極性の争点が無い主張は従来どおり
- K4 順序: 文の並び順を変えても verdict 一致
- K5 退行なし: 既存の肯定文 ANSWER・UNKNOWN_SUBJECT_NOT_HELD・
  UNKNOWN_SUBJECT_TOO_THIN が不変。fork で固定(肯定と否定が同じ
  verdict になったら落ちる検査)。forks 全緑。

## 停止条件

K5違反(退行)→ 棄却して記録。K1が「分かれるが理由が極性でない」形で
通ったら失格(理由を検査に含める)。
