# Onboarding — build your own Vera in an afternoon

This guide is for someone who has never touched the codebase and wants a
customized, working instance: your data, your domain, your store. Everything
here is deterministic — if you run the same commands on the same data, you
get byte-identical behavior.

## 0. Sanity check (2 minutes)

```bash
git clone https://github.com/Ag3497120/Verantyx-Vera-alpha.git
cd Verantyx-Vera-alpha && pip install -e .
vera lab                      # 41 self-test forks — must be all green
vera remember "The bright apple is sweet ."
vera ask "what is apple"      # ANSWER
vera ask "what is xylospongia" # UNKNOWN_NO_EVIDENCE — this refusal is the product
```

If `vera lab` is green, every capability documented here is verified on your
machine, including the refusal behaviors.

## 1. Choose your data path (current best practice)

There are three ways to get knowledge in, ranked by quality per sentence:

| Rank | Method | When |
|------|--------|------|
| 1 | **structured `key:value` facets** via `store.add` | records you control (tickets, inventory, configs) |
| 2 | **definitional corpora** (encyclopedia abstracts) | broad knowledge — DBpedia pours best |
| 3 | **free text** (news, articles, notes) | volume; noisier facets, still countable/deletable |

Rules of thumb learned from real pours (WikiText-2/103, ag_news, DBpedia,
SQuAD, IMDB — ~1M cores total):

- **Definitional sentences beat narrative** ("X is a Y that Z"). If you can
  choose corpora, choose abstracts over prose.
- **Volume is evidence**: facets are votes; 50 repetitions outrank 1. Don't
  curate single perfect sentences — pour everything relevant.
- **Always keep two-pass on** (default): pass 1 collects capitalization
  statistics so names route to their own sense channel; without it, frequent
  entities pollute common nouns.
- **Domain-specific stores beat one mega-store** when domains collide on
  vocabulary ("sun" astronomy vs Sun Microsystems). Use separate `--store`
  files per domain; they are just files.

## 2. Pouring (computed placement, not dumping)

```bash
# any HuggingFace dataset: hf:<name>[#config][:text_field]
vera --store mydomain.json pour --source "hf:dbpedia_14:content" --max-rows 560000
# your own corpus, one document per line
vera --store mydomain.json pour --source file:my_docs.txt
```

"Computed placement" means every sentence deterministically passes:
junk-core filtering → proper-noun compounding ("Sun Tzu" → one node) →
sense-channel routing (`bush#p` ≠ `bush`) → count accumulation. You never
hand-place nodes for text corpora; you *choose and order the corpora*, which
is where your judgment enters. Pours are cumulative and resumable — the
store file is the checkpoint.

For records, place directly (this **is** hand-computed placement, and it
unlocks contradiction detection):

```python
from verantyx import CrossStore
st = CrossStore(track_provenance=True)
st.add("server:prod-1", ["os:ubuntu", "region:tokyo"], source="infra sheet 7/24")
st.add("server:prod-1", ["os:debian"], source="slack 7/25")
st.contradictions("server:prod-1")   # → db key "os" holds two values, with sources
st.save("infra.json")
```

Structured `key:value` records are reachable both ways: exact lookup
(`store.top_facets("server:prod-1")`) **and** natural-language questions
that include the record's name (`ask("what is server:prod-1")`) — the
query parser preserves `word:word` identifiers instead of losing the colon
to tokenization.

## 3. Verify what went in

```bash
vera --store mydomain.json stats                 # cores, links, top concepts
vera --store mydomain.json ask "what is <your top core>"
```

Inspect a concept's raw accumulated evidence from Python with
`store.top_facets("concept", 20)` — if the top facets look wrong, your
corpus (not the engine) said so; `vera forget <core>` and re-pour better data.

## 4. Scale up

- JSON store is fine to ~200 MB. Beyond that, or for frequent writes
  (agent memory), convert to SQLite:

```python
from verantyx import CrossStore
from verantyx.store_sqlite import save_sqlite, load_sqlite
save_sqlite(CrossStore.load("mydomain.json"), "mydomain.db")
st = load_sqlite("mydomain.db")            # or cores_like="fn:%" for a slice
```

- `SqliteSync` gives delta-flush writes (only dirty cores hit disk).

## 5. Wire into your workflow

- **Chat**: `vera chat` (deterministic) or
  `vera chat --mode hybrid --llm <ollama-model>` (a local LLM speaks, Vera
  controls allocation and never lets it touch proven values).
- **MCP**: `vera --store memory.json mcp` → 8 tools for Claude/Cursor
  (docs/MCP.md).
- **Code**: `vera code ingest .` then `vera code ask "impact of <fn>"`;
  bug localization by multi-section agreement lives in
  `verantyx.debug_consensus.locate_bug` (traceback + diff + failing tests
  must agree before a cause is asserted).

## 6. Extend the engine itself

Everything is rule-data or small deterministic modules:

| Want | Touch |
|------|-------|
| new language | `lang.py` — add a segmenter + function stoplist |
| new math/logic rules | `RuleStore.add("?a * 2", "?a + ?a")` — rules are data |
| new node type | just a namespaced core (`ticket:`, `fn:`, `rule:`…) |
| new evidence section for debugging | a function returning candidate lists in `debug_consensus.py` |
| new gate / verdict | `consensus.py` — add to the gate chain, add a fork |

**House rule: every change ships with a fork** (a falsifiable self-test in
`*_forks.py`, registered in `vera lab`). If you cannot write the failing
case, the feature is not defined yet. This rule is why `vera lab` being
green means something.
