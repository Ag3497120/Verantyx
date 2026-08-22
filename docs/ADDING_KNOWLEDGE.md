# Adding knowledge to Vera

Knowledge in Vera is **data you can see**: one cross per concept, holding a
core plus `{facet: count}` accumulated from every sentence you feed it.
Nothing is baked into weights, so adding, inspecting, and deleting are all
first-class operations.

## 1. Teach single facts (`remember`)

```bash
vera remember "The bright apple is sweet ."
# → core=apple, facets [bright, sweet]
vera remember "The red apple grows on a tree ."
# → same cross accumulates: bright, sweet, red, tree
```

Repetition matters: counts are evidence. A facet seen 50 times outranks one
seen once. In `vera chat`, use `:remember <sentence>`.

Python API:

```python
from verantyx import CrossStore
store = CrossStore()
store.ingest_sentence("The bright apple is sweet .")
store.add("apple", ["fruit"])          # direct, bypasses the classifier
store.top_facets("apple")              # [('bright',1), ('fruit',1), ('sweet',1)]
store.save("vera_store.json")
```

## 2. Pour corpora (bulk)

```bash
vera pour --source "hf:dbpedia_14:content" --max-rows 560000
```

What happens per sentence, deterministically:

1. **Sentence split + elementary grammar classify** → one core candidate +
   nearby content facets. Function words are skipped; junk cores
   ("however", "two", digits, HTML fragments) are filtered.
2. **Proper-noun compounding** — consecutive capitalized words merge:
   "Sun Tzu" → `sun_tzu#p`.
3. **Sense channels** — mid-sentence capitalized names go to a proper
   channel (`bush#p`), common nouns stay in the common channel (`bush`
   the plant would be separate). A **two-pass capitalization scan** routes
   sentence-initial names correctly (pass 1 collects statistics, pass 2
   ingests). This is why pouring reads the source twice.
4. **Accumulate** into `core → {facet: count}`.

Pouring is cumulative and resumable: the `--store` JSON is a checkpoint;
pour a second corpus on top and counts merge.

## 3. Sense channels and disambiguation

Same surface, different meanings:

```bash
vera ask "what is the sun"            # default: highest-count facets
vera ask "what is the sun newspaper"  # specifier word selects a sense cluster
```

Specifier words (non-head content words) select among **facet co-occurrence
clusters** computed at query time from the store itself — no extra storage,
so every new pour automatically sharpens clusters.

## 4. Deleting and correcting

```bash
vera forget apple          # deletes the cross (both channels), immediately
```

To correct a wrong facet: `forget` the core and re-teach, or outweigh it by
repetition (counts are the ranking). Deletion is real — there is no residual
representation anywhere, which is something weight-based models cannot offer.

## 5. What makes knowledge "good" here

- **Definitional sentences** beat narrative ones ("X is a Y that Z" is ideal —
  encyclopedia abstracts like DBpedia pour very well).
- **Volume of relevant sentences** beats single perfect sentences: facets are
  votes.
- Noisy corpora produce noisy facets. They stay visible (`vera stats`,
  `recall`) and deletable — garbage in, *auditable* garbage out.

## 6. Adding new node types

A "node" is just a core string with a namespace prefix. Built-in examples:

| Prefix | Meaning | Added by |
|--------|---------|----------|
| (none) | common-sense concept | `remember` / `pour` |
| `#p` suffix | proper-name sense channel | automatic |
| `fn:` | Python function | `vera code ingest` |
| `rule:` | rewriting rule | `RuleStore.pour_into` |

You can invent your own the same way:

```python
store.add("ticket:ABC-123", ["status:open", "owner:kai", "component:auth"])
```

Facets with `key:value` shape survive filtering and give you a queryable,
countable, deletable record store on the same consensus machinery.
