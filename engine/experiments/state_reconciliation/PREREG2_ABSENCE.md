# 事前登録12: 「持っていない」と「持っているが確定が無い」を分ける

日付: 2026-08-22。**この文書を確定してから実装する。**

## 何が欠けていたか(実測)

状態突合の測定(PREREG.md、5/5)で、この装置の中心的な線が1箇所だけ
破れていた: **不在と否定を混ぜない**、が `deep_report` で守られていない。

```
在る核(争いあり) → confidence: "contested"
在る核(確定なし) → confidence: "unknown"
無い核           → confidence: "unknown"   ← 同じ
```

現場では意味がまったく違う。前者は「見たが言うことが無い」、後者は
**「その避難所は誰も報告していない — 見に行け」**。同じ顔で返すのは、
この企てが番人と単体の両方で禁じてきた形そのもの。

`contradictions()` も同様に両方 `[]` を返すが、あちらは矛盾の一覧を返す
関数であって不在を語る場所ではない。**報告の面である `deep_report` に
型を置く**。

## 変更(最小)

`deep_report` に `held: bool` を足し、核が店に無いときだけ
`confidence: "unknown_not_held"` を返す。**在る核の判定は一切変えない**。

## 保証(A1〜A3)

A1. 無い核 → `held: false`、`confidence: "unknown_not_held"`
A2. **在る核の判定は不変** — contested / updated / supported / unknown は
    今までと同じ値。既存の fork `structure_forks` の contested 主張が通る
A3. 扉 `deep_report` からも同じ型が見える(IDE と外の道具に届く)

## 測定(V49〜V51)

- V49 三つの状態(無い核 / 在るが確定なし / 在って争いあり)が別の値
- V50 回帰: `all_cross_geometry_forks()` と `structure_forks`、guard の
  測定 50本が全て緑のまま
- V51 扉経由でも `held` と `unknown_not_held` が返る

## 停止条件

- 在る核の `confidence` が1つでも変わったら差し戻す(報告の意味を
  静かに変えるのは、測定を嘘にする)
