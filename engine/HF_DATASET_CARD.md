---
license: mit
tags:
  - knowledge-graph
  - symbolic-ai
  - deterministic
  - hallucination-free
  - mcp
  - agent-memory
language:
  - en
pretty_name: Verantyx Vera — Base Knowledge Store
size_categories:
  - 1M<n<10M
---

# Verantyx Vera — Base Knowledge Store

This is the **poured base knowledge store** for [Verantyx Vera](https://github.com/Ag3497120/Verantyx-Vera-alpha) —
a deterministic, LM-free knowledge & reasoning engine that **refuses to answer
rather than hallucinate**.

> **This is data, not a model.** Vera has no neural network and no weights.
> This file is a JSON store of accumulated facts (`core → {facet: count}`,
> ~889k concept nodes / 9.78M facet links), built by pouring WikiText-2,
> WikiText-103, ag_news, DBpedia, SQuAD, and IMDB through Vera's deterministic
> ingestion pipeline. There is nothing to fine-tune or run inference on here
> in the ML sense — it's the memory, not the brain.

## Get the engine and full docs

**➡️ Code, CLI, MCP server, setup guides:
[github.com/Ag3497120/Verantyx-Vera-alpha](https://github.com/Ag3497120/Verantyx-Vera-alpha)**

## Use this store

```bash
pip install -e "git+https://github.com/Ag3497120/Verantyx-Vera-alpha#egg=verantyx-vera"
vera setup   # set hf_store_repo = kofdai/Verantyx-Vera-base-store
vera ask "what is football"    # auto-fetches this store on first use
```

Or directly in Python:

```python
from huggingface_hub import hf_hub_download
from verantyx import CrossStore, consensus_over_store

path = hf_hub_download("kofdai/Verantyx-Vera-base-store", "vera_store.json",
                        repo_type="dataset")
store = CrossStore.load(path)
print(consensus_over_store(store, "what is football")["text"])
```

## What's inside

| Corpus | Rows poured |
|--------|------------:|
| WikiText-2 (train) | 23,767 |
| WikiText-103 (train) | ~1.8M |
| ag_news | 120,000 |
| DBpedia-14 | 560,000 |
| SQuAD (contexts) | ~90,000 |
| IMDB | 25,000 |

Every fact is a **counted, deletable, auditable** entry — inspect any concept
with `vera stats` / `vera --store ... ask "what is X"`, or delete it entirely
with `vera forget X`. Nothing is compressed into opaque weights.

## Honest limitations

- Facet extraction is a rule-based elementary grammar classifier, not a
  full NLP pipeline — noisy source text yields noisy (but visible, deletable)
  facets.
- English only. Domains collide on ambiguous vocabulary (see
  `docs/ADDING_KNOWLEDGE.md` in the repo for sense-channel disambiguation).
- This is a **research artifact**, not a vetted knowledge base — verify
  before relying on it for anything consequential.

## License

MIT — same as the engine.
