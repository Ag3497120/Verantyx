---
license: mit
language:
- ja
- en
tags:
- knowledge-base
- retrieval
- deterministic
- no-llm
- japanese-law
- sqlite
pretty_name: Vera α — a knowledge structure that refuses in types
---

# Vera α

Not a language model. No weights, no sampling, no training: 1,200 Japanese
statutes and 2,591 encyclopedia articles are read into a federation of
cross-shaped nodes, and the same question always produces the same answer.

The artifact is **one SQLite file**. Nothing is unpickled, and every number
below can be checked against the file itself.

```bash
sqlite3 vera.db "SELECT facet, count FROM facets WHERE core='正当防衛'
                 ORDER BY count DESC LIMIT 5"
# 成立|4  行為|4  防衛|4  他人|3  必要|3
```

## What it does

Answers with the source it read, and when it cannot answer, says **which
kind of not-knowing** it is — because the kinds need different things done
about them.

| question | verdict | |
|---|---|---|
| `正当防衛とは` | `SEEDED` | 正当防衛 → 成立 → 行為 → 防衛 → 他人 |
| `negligence` | `ANSWER` | negligence → comparative → contributory → criminal |
| `今日の天気は` | `UNKNOWN_TIME_DEPENDENT` | does **not** close by registration — the store has no clock |
| `こんにちは` | `UNKNOWN_NO_EVIDENCE` | closes by registering sentences about the subject |

## Measured on this file

Reproduce all of it with `python3 -m verantyx.card_numbers --db vera.db`.

| | |
|---|---|
| size / load | 140.0 MB / 2.8 s, one CPU core |
| Japanese sovereign | 86,992 cores, 1,145,326 facets, 6,037 leaves |
| English sovereign | 15,268 cores, 133,389 facets, 764 articles |
| closure — symbols emitted that the store holds | **60 / 60** |
| determinism — same question, shuffled, 3 rounds | **34 / 34 identical** |
| latency | 32.6 ms median, 36.1 ms max |
| self-test forks | 141 / 141 |

## The limitation that matters

Closure guarantees the store never emits a symbol it does not hold. It
guarantees **nothing about the subject**, and the first release showed it:
on 200 invented compounds, 77% were answered about a recognised substring —
ヒュペリオン数人 answered about 数人 — with the unknown element dropped
without a word.

The current release gates the seed on the asked subject. A seed passes only
when it is the subject, contains it, or holds it on its own cross's faces;
a held subject the staircase overlooked replaces the seed; anything else
refuses by name:

    ヴォルフガング粒子とは → UNKNOWN_NOT_PRESENT
                            subject: ヴォルフガング粒子, nearest held: ヴォルフガング

Measured: invented compounds answered **77% → 4%** (the residue enters
through direct Latin-substring retrieval, not the staircase); wrong-subject
answers on suffixed questions (〜の要件は, 〜について教えて) **43–71% → 0–7%**;
correct-subject answers *rose* at every suffix (57%→86% bare, 29%→36% worst
case) because a held subject now displaces a worse seed. The gate is
conservative and it does lose borderline coarsenings — 不法行為とは now
refuses with a pointer to 不法 instead of answering from it.

Still true and unchanged: it cannot explain a word it never read (0.0% —
the same closure that produces the 60/60), summarise, or chain inferences
past one step.

Also absent: explaining a word it never read, summarising, chaining
inferences past one step, and fluent prose. The first follows from the same
closure that produces the 60/60; the others are stated with their
measurements in the module docstrings.

## Sources and licence

The **code** is MIT. The **built structure** in `vera.db` is derived from two
corpora with different terms:

- **e-Gov statute XML** — 1,200 laws, 70% of the leaves. Japanese statutes
  are not subject to copyright (著作権法13条).
- **Wikipedia (ja, en)** — 1,827 Japanese leaves and 764 English articles,
  **CC BY-SA 4.0**. A derived structure inherits attribution and share-alike,
  so `vera.db` is offered under **CC BY-SA 4.0**, not MIT.

`vera_edges.db` (87MB, optional) holds same-sentence facet pairs — the
edges of the cross, where a face holds an item and an edge holds the
relation one sentence actually wrote. The engine answers identically
without it; with it, evidence-tied cores may speak the pairs a sentence
attested (25 of 97 silenced cores recover speech). Same licence as
vera.db.

`corpora/*.json` pin name, url, sha256 and byte count for all 3,958
documents, with the selection rule recorded beside them. That is what makes
the figures above checkable rather than quotable:

```bash
python3 -m verantyx.corpus_fetch --manifest corpora/egov_bulk_2026.json --out ./bulk
python3 -m verantyx.build_ja --root .      # federation
python3 -m verantyx.build_en --root .      # English sovereign
python3 -m verantyx.export_sqlite --verify # vera.db, and that it answers the same
```

Full platform document (structure, signals, governed evolution, versioning, participation): <https://github.com/Ag3497120/Verantyx-Vera-alpha/blob/main/docs/PLATFORM.md>

Code: <https://github.com/Ag3497120/Verantyx-Vera-alpha>
