---
license: mit
tags:
  - knowledge-graph
  - symbolic-ai
  - deterministic
  - retrieval
  - agent-memory
  - mcp
language:
  - en
pretty_name: Verantyx Vera — Base Knowledge Store
size_categories:
  - 100M<n<1B
---

# Verantyx Vera — Base Knowledge Store

The shippable artifact of a **deterministic** knowledge engine. Vera has no
weights and no embeddings: what ships is the *store* — a stereo-cross index of
cores and facets built by pouring text through the engine's own ingestion path.

Code: **https://github.com/Ag3497120/Verantyx** (engine lives in `engine/`)

```bash
git clone https://github.com/Ag3497120/Verantyx.git
cd Verantyx/engine
python3.11 -m verantyx.cli fetch-store            # this dataset, ~209 MB
python3.11 -m verantyx.cli --store vera_store.json ask "valkyria"
```

Nothing is downloaded implicitly. If a store is missing, the engine says so and
names the command that would fix it:

```json
{"verdict": "UNKNOWN_NO_STORE", "how_to_close": "vera fetch-store --repo kofdai/Verantyx-Vera-base-store"}
```

## What is actually in it

| | |
|---|---|
| Source | `hf:imdb` — English film, biography and geography prose |
| Cores | 889,241 |
| Facet links | 9,778,919 |
| Sentences ingested | 5,663,792 |
| Size | ~209 MB JSON |

## What it is good for, measured

Ask it about something the corpus holds and you get a typed `ANSWER` with the
core it answered from. Ask about something it never read and you get
`UNKNOWN_NO_EVIDENCE` **with a reason** — not the nearest paragraph. That
refusal is the point: a neighbour search always returns something, and a
generator always mixes in words the corpus never contained.

## What it is *not* good for — please read before judging it

Measured on 2026-08-22, on this exact store:

* **It is English film prose, not a technical or domain corpus.** Coverage of
  a coding assistant's vocabulary: 絵文字 0, テスト 0, 型注釈 0, print文 0,
  TypeScript 0, JavaScript 0. There is no Japanese in it at all.
* **Several apparent hits are false friends.** `print` here means *printed
  matter* — its structural siblings are online / magazine / newspaper.
  `console` is a games console. `black` is a colour.
* Sibling inference ("the substitution nobody wrote down") only works where
  the corpus put two alternatives **side by side on the same line**. Statutes
  do that; prose does not. Measured recovery on technical pairs: 1 of 6.

So: use this store to see the engine's behaviour — typed refusals,
order-invariance, provenance — not as domain knowledge. For real work, pour
your own:

```bash
python3.11 -m verantyx.cli --store mine.json documents ~/your-docs/
```

Pouring is measured to be **non-interfering**: adding documents does not change
answers that were already grounded, and the ingestion order does not change any
answer (6-permutation check, part of the repository's 50-measurement suite).

## Everything published here

| file | what it is | size |
|---|---|---|
| `vera_store.json` | the base store — English film/biography prose (`hf:imdb`), 889,241 cores | 209 MB |
| `stores/guard_store_technical_ja_en.json` | a technical ja+en store built from 549 local documents (4.9 M chars), used to measure whether a domain corpus fixes instruction reading — **it does not**, and that negative result is the point | 55 MB |
| `stores/guard_store_manifest.json` | exactly which files went in, so the store can be rebuilt or disputed | 142 KB |
| `stores/ide_default_store.json` | the small store the macOS app ships against (ja definitions) | 6 MB |
| `corpora/*.json` | the ingestion corpora: e-gov statutes, Japanese/English Wikipedia field sets, Aozora speech, disaster-domain probes | 1.1 MB |

Every one of them is an artifact of a measurement written up in the code
repository, not a curated dataset. The manifest exists so a reader can dispute
the corpus rather than take the numbers on faith.

## Provenance and licence

The store is a structural index derived from the public `imdb` dataset on this
Hub. It contains cores and facet counts, not reproduced documents. The MIT
licence above covers this derived index; the underlying corpus keeps its own
terms.

## Reproduce every claim on this page

```bash
python3.11 engine/experiments/guard/verify_all.py
# forks 89/89 / 測定 50/50
```

Each number above traces to a pre-registered measurement in
`engine/experiments/` — written **before** the measurement ran.
