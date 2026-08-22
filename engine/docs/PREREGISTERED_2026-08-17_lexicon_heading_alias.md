# Pre-registration — a jgen embed table as a heading dictionary

**Registered 2026-08-17, before any threshold is chosen or any held-out
document is read.**

## What this is for

The structured-document stage answers 「必須要件は」 and 「要件は」 and
refuses 「指定された要件は」 — measured 2026-08-16, and recorded then as
the one gap that decides whether a 規程窓口 is usable, because nobody at
a counter asks in the document's own headings.

A jgen embedding table can rank. That boundary is already measured
(2026-08-08, qwen3.5:4b): nearest-known search USABLE, state-likeness
USABLE, **polarity FORBIDDEN at 54.8% — a coin flip**. This uses only the
ranking half, and the polarity half stays untouched and unused.

Reading a static table is not running a model. There is no sampling, no
temperature, no generation — a row lookup and a cosine, measured at 0–4 ms.
**Determinism is preserved**, which is the property this engine is not
trading for reach.

## The risk being controlled

A dictionary that maps a question to the wrong heading is worse than one
that refuses, because the reply then quotes the wrong section of a
regulation **with full confidence and a real citation**. So the threshold
is set to control false positives, and recall is what gets measured
afterwards rather than chosen.

Observed in the exploratory run that motivated this (0.5B stand-in, the
contest PDF): the unrelated word 「昼ごはん」 scored 0.306 against
「評価基準」 — higher than two genuine paraphrases scored against their
correct headings. **A bare nearest-match with no floor is not usable.**

## Protocol, frozen

1. **Lexicon** — the jgen embed table named by
   `~/.verantyx-audit/lexicon.json`. That path is currently stale (the
   4B lexicon file is gone), so the run states which file it actually
   opened and its parameter count. A stand-in is not the shipped article
   and the report must say so.
2. **Threshold document (fit)** — `2026年度前期三校合同コンテスト概要.pdf`,
   already indexed.
3. **Held-out document (judge)** — one of the network-lecture PDFs in
   `~/Downloads` (`01_ネットワークって何.pdf` …). **Its headings are not
   read before the threshold is frozen.**
4. **Negative controls, declared now, before any score is seen** — 20
   everyday words with no relation to either document's subject matter:

   昼ごはん / 天気 / 電車 / 洗濯 / 財布 / 犬 / 靴下 / 花瓶 / railway /
   おにぎり / 台風 / 眼鏡 / 階段 / 冷蔵庫 / 手袋 / 郵便 / 椅子 / 傘 /
   林檎 / 音楽

   These are the false positives the threshold exists to stop.
5. **Threshold rule, fixed now** — the floor is the smallest value that
   refuses **every** negative control on the FIT document, rounded up to
   two decimals. It is frozen before the held-out document is opened.
   Recall is then measured, never tuned.
6. **Wiring** — the dictionary proposes; `document_structure.lookup`
   still decides. A proposed heading is looked up exactly as if the
   person had typed it, so nothing downstream changes, and the reply
   names the substitution.

## Frozen pass lines

- **L1 — every negative control is refused on the HELD-OUT document.**
  Not the fit document, where the floor was derived. **This is the line
  that decides the mechanism**; a dictionary that answers 「昼ごはんは」
  with a section about evaluation criteria is unusable at a counter
  regardless of its recall.
- **L2 — 「指定された要件は」 reaches 必須要件** on the contest PDF, and
  the reply says the heading was reached through the dictionary.
- **L3 — no heading is EVER emitted that the document does not hold.**
  The dictionary may only propose a heading the index already contains;
  `lookup` decides. Checked mechanically.
- **L4 — WRONG stays 0** on the frozen 50-item commonsense bank. The
  dictionary sits in the document stage only and must not leak.
- **L5 — determinism holds.** The same query returns byte-identical
  output on three runs.

## Quantities to be measured (not predicted)

1. The floor the fit document produced, and the highest-scoring negative
   control on each document.
2. Recall on the held-out document: of its headings, how many are reached
   from a paraphrase, and which paraphrases fail.
3. Latency per lookup.
4. Which lexicon file was actually opened, and its dimensions.
5. Paraphrases that map to a WRONG heading above the floor, listed
   verbatim — the failure mode that matters most.

## Stop conditions

- **L1 fails** → the table cannot be given a floor that separates
  nonsense from paraphrase. Stop. Do not add a second threshold, do not
  add a margin term, do not swap the lexicon for a bigger one and re-run
  — each of those is choosing the experiment that passes.
- **L3 fails** → the dictionary is emitting headings the document does
  not have, which means it is no longer proposing but inventing. Stop.
- **L4 fails** → it leaked out of the document stage. Stop and ledger.

## Recorded before measuring

The expected recall is **partial, and low recall is the honest outcome
rather than a failure**. In the exploratory run three of eight
paraphrases mapped correctly (指定された要件, 要件, 禁止事項) and four
did not (締切, 加点, 出すもの, 使う言語). A static embedding is a
dictionary of contexts, not of meanings, and a counter will keep needing
`ask_back` for what it cannot resolve.

The claim on offer is narrow: **some paraphrases become answerable, and
nonsense stays refused**. It is not that the engine understands the
question.

## Not in scope

Polarity — forbidden by the 2026-08-08 measurement and not used here.
The census, the federation, generation. No model is run; only a table is
read.

---

## Measured 2026-08-17 — L1 FAILS. Withdrawn, not shipped.

**Lexicon actually opened:** `qwen_0.5b_full.jgen`, `embed_tokens`
151936×1024. A stand-in — the configured 4B lexicon file is gone from
`converted_models/`. The operator config was restored unchanged.

### What passed, in the form it was tested

Floor derived on the fit document: **0.42** (highest negative control
昼ごはん 0.419).

```
L1 (as tested)  20/20 single-word negatives refused on the held-out
                document; highest おにぎり 0.348          apparently PASS
recall          4 correct / 4 refused / 0 wrong on 8 frozen paraphrases
L2              指定された要件 → 必須要件 0.704            PASS
L3              only headings the index holds              PASS
L5              byte-identical over 3 runs                 PASS
```

Wired in, 「指定された要件は」 reached 必須要件 on the main path with the
substitution named. It looked finished.

### What actually happened

```
辞書なし   8 correct / 42 refusal / 0 wrong
辞書あり   6 correct / 44 refusal / 0 wrong
```

The two-answer difference was not a rounding artifact. Inspected item by
item, **29 of the 50 commonsense questions were being answered with a
section of the contest PDF**:

```
氷は冷たいですか      → 開発環境および指定ツール
    「原則として、授業で利用した以下の環境を用いて開発を行ってください。
      • バックエンド: Python, Flask モジュール」
針は鋭いですか        → テーマおよびシステム構造の設定
羽は軽いですか        → フロントエンド: HTML, CSS, Jinja2
```

### Two failures, and the second is mine

**1. The floor holds for words and not for sentences.** All twenty
declared negative controls were single words (昼ごはん, 電車, 傘). People
type sentences. A sentence's token average drifts toward a document's
general vector, so 「氷は冷たいですか」 clears a floor that 「昼ごはん」
does not. The pass line's own example was written 「昼ごはんは」 — with the
particle, i.e. the question form — and the control set I built to test it
was weaker than the line I wrote. That is a defect in the experiment, not
a loophole in the result.

**2. L4 was reported PASS and was not measured.** `is_asserting` and
`is_typed_refusal` are closed sets written before DOCUMENT_SECTION
existed, so 29 wrong answers fell through both and were counted as typed
refusals. **WRONG = 0 was an artifact of the scorer**, and it was
reported as a pass line before the control run exposed it. A metric that
cannot see a new verdict reports its arrival as silence.

### Stop condition, honoured

> L1 fails → the table cannot be given a floor that separates nonsense
> from paraphrase. Stop. Do not add a second threshold, do not add a
> margin term, do not swap the lexicon for a bigger one and re-run.

No second threshold was added. No sentence-negative floor was derived.
The 4B lexicon was not fetched. The wiring is removed from `engine.py`
and `propose_heading` carries a WITHDRAWN notice so the failure stays
legible. After removal: **0 of 50 commonsense questions reach a document
section**, and 「必須要件は」 still answers from the document.
「指定された要件は」 is refused again, which is where it was.

### What this establishes

A static embed table can rank **words** against a small key set. It
cannot be given a single global floor that also rejects **sentences**,
because the two live at different score scales against the same keys.
Any future attempt needs the scale difference addressed at the mechanism
level — normalising by length, or extracting the head before looking up —
and that is a different mechanism with its own pre-registration, not a
tuned threshold on this one.

The 2026-08-08 boundary is unchanged and was not contradicted: ranking
usable, polarity forbidden. This measured a third thing the boundary did
not cover — that ranking's usable range depends on the LENGTH of what is
ranked.
