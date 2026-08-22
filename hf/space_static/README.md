---
title: Ask Vera
emoji: ➕
colorFrom: gray
colorTo: indigo
sdk: static
app_file: index.html
pinned: false
license: mit
---

# Vera α — 型で拒否する知識構造

言語モデルではありません。重みも標本抽出もなく、同じ問いは常に同じ答えを返し、
答えられないときは**どの種類の「わからない」か**を型で返します。

このページは静的 Space ですが、飾りではありません。「エンジンを起動」を押すと
**Pyodide 上の CPython が本物の `verantyx` を読み込み、ブラウザの中で推論します**
— サーバはありません。JS で書き直した別実装ではなく、公開しているのと同じ
Python コードが、同じ SQLite を読みます。

ブラウザ版 (`vera_web.db`, 85.7MB) は核を一つも落とさず、面だけを **24**
— 十字の容量 (6腕 × 4面) — に切ってあります。34 問で主語の一致 100%、
判定 97%。上位核に削る版は `窃盗罪とは` が殺人罪について答えたため採りませんでした。

完全版: [kofdai/vera-alpha](https://huggingface.co/kofdai/vera-alpha) ·
コード: [GitHub](https://github.com/Ag3497120/Verantyx-Vera-alpha)

`vera_web.db` と `writer.json` は Wikipedia の二次的著作物のため **CC BY-SA 4.0**。
コードは MIT。
