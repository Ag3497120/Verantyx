# Pre-registration — a document has structure, and the answer lives in it

**Registered 2026-08-16, before the ingest is written or measured.**

## What is broken, measured today

A contest PDF was loaded. The store holds it — 「必須要件」 appears sixteen
times — and the engine now reaches it (`door: store`). But the answer is
an index, not an answer:

```
問い   必須要件は
答え   本課題 必須要件
```

The document's actual answer is two lines the ingest never kept:

```
2. 必須要件
    データベースへのデータ登録（INSERT 処理）
    データベースからのデータ参照（SELECT 処理）
```

Sentence-level ingest read 51 of 68 lines. **The 17 it dropped are the
answer** — the requirement items, and the deadline
「2026 年 9 月 11 日（金）23:59」, are all bullets under a heading. A
bullet is not a sentence, so it was not placed.

## What is proposed

A document is read as **sections**: a heading, and the items under it.
Each item is placed as a facet of the heading's core, marked `item:<n>:`
so its position in the list survives — an unordered set of requirements
is a different document from a numbered list of them.

Answering 「Xは」 where X is a heading returns **the items, verbatim, in
order**. The engine quotes; it does not paraphrase. The only thing
composed is the joining sentence, from a closed template driven by the
item count (「Xは、A と B の2点です。」), and the items inside it are
substrings of the source or they do not appear at all.

## Why this is the structural answer and not a gate

Headings and items are not a rule about this PDF. A heading is a subject
and its items are what is said about that subject — the same relation
the store already holds as core→facets. Nothing new is invented; the
ingest stops throwing away a nesting the document already carries.

## Frozen pass lines

- **S1 — the requirement question is answered from the document.**
  「必須要件は」 returns both items, verbatim, in document order, with
  `door: store`.
- **S2 — the deadline is answered.** 「提出期限は」 returns
  「2026 年 9 月 11 日（金）23:59」 from the document, not from jawiki.
  It currently returns a Template:Long comment article.
- **S3 — no fabrication, checked mechanically.** Every emitted item must
  be a substring of the source document. **This is the line that decides
  the mechanism.** A composed sentence that names a requirement the
  document does not contain is worse than the index it replaces.
- **S4 — an empty heading refuses.** A heading with no items returns
  UNKNOWN_NO_ITEMS, never a sentence assembled from neighbouring text.
- **S5 — WRONG stays 0** on the frozen 50-item commonsense bank
  (`tools/commonsense_bank_2026-08-14.json`; baseline 9 correct / 41
  typed refusal / 0 wrong). Structured ingest must not leak into general
  answering.

## Quantities to be measured (not predicted)

1. Sections and items extracted from the contest PDF.
2. Of the document's headings, how many answer and how many refuse.
3. Lines still dropped, listed verbatim.
4. Whether the ordinal survives (item 1 before item 2).

## Stop conditions

- **S3 fails** → stop. Do not tune the template. A mechanism that needs
  tuning to stop inventing will invent.
- **S5 fails** → the ingest has changed general answering. Stop and
  ledger what entered.
- **S1 and S2 both fail** → the nesting is not what makes these
  answerable, and the diagnosis above is wrong. Report that rather than
  extending the extractor until something passes.

## Recorded before measuring

The expected gain is narrow and worth stating so a small number is not
read as failure. This makes **headed, listed** documents answerable —
contest rules, specifications, procedures, statutes. It does nothing for
prose that states its facts in running sentences, and it does not make
the engine understand the requirements; it makes it able to quote the
right two lines when asked about the heading they sit under.

That is a retrieval claim, not a comprehension one, and the wording of
every verdict must keep saying so.

## Not in scope

The census is untouched. `jawiki_shallow` remains atlas-and-witness only
under the unchangeable clause in
`docs/PREREGISTERED_2026-08-14_tree_and_shelf.md`. No model is called.

---

## Measured 2026-08-16, after the pass lines were frozen

The contest PDF, read by `load_paths` and indexed by
`document_structure`: **7 sections, 9 labels, 49 logical lines** (68
physical lines rejoined).

```
[1] テーマおよびシステム構造の設定    7行
[2] 必須要件                        5行
[3] 評価基準（加点要素）             7行
[4] 開発環境および指定ツール          3行
[5] 注意事項および禁止事項           9行
[6] 提出物および提出期限            12行
```

| line | result |
|---|---|
| S1 requirement question answered from the document, in order | **PASS** |
| S2 deadline answered from the document | **PASS** |
| S3 every emitted line a substring of the source | **PASS** |
| S4 empty heading refuses (UNKNOWN_NO_ITEMS) | **PASS** |
| S5 WRONG stays 0 on the 50-item bank | **PASS** |

S5 in full: **8 correct / 42 typed refusal / 0 wrong**, identical with
and without the document loaded. The pre-registered 2026-08-14 federation
baseline was 11 / 37 / 2; this route is the whole composition rather than
bare `vera_ask`, so it is a different measurement, not a regression — and
the direction that matters is that the two WRONGs are now typed refusals.

### Quantity 2 — headings that answer

All six. `提出物` and `要件` answer by containment (`要件` ⊂ `必須要件`);
`提出期限`, `バックエンド`, `フロントエンド`, `システム構造`, `画面構成`,
`時間`, `内容`, `注意`, `提出先` answer as labels.

### Quantity 3 — what still does not answer

**「指定された要件は」 — the question this work started from — still goes
to the federation** and returns 特定自然観光資源. The subject is a
modified noun phrase and its head (`要件`) is never extracted, so the
document stage is asked about 「指定された要件」, which is no heading.
「要件は」 and 「必須要件とは何ですか」 both answer correctly. Head
extraction from a modified noun phrase is the next thing, and it is not
claimed here.

### Two findings that changed the code, both from measurement

**Typo repair was moved from first to last.** Applied first, it rewrote
「提出物は」 to 「提出物件」 and the question stopped reaching a document
that had a 提出物 section. The organ's zero-false-fire figure was
measured on in-vocabulary words, and a word with a topic particle stuck
to it is not one. Every stage now answers the question as asked, and the
candidate is tried once only when all of them refuse, with the
substitution on the record.

**Wrap detection was measuring the wrong quantity.** In characters, a
wrapped line was 36 and an unwrapped item 35, so no ratio separated them.
The document mixes ASCII with Japanese and ASCII is half as wide; in
display columns the same lines are 67 and 57. The threshold was not
moved — the measurement was corrected.

### One defect NOT fixed, and it is upstream

`load_paths` emits 「…機能の実装o 画像ファイルの…」 as one physical line:
two bullet items welded by the PDF extractor before this module sees
them. Both are present verbatim so S3 holds, but the section shows them
joined. That belongs to the loader, not to this index.
