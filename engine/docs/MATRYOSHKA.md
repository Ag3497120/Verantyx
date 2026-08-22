# Matryoshka layers — growing the structure upward

Vera's answer gate is strict: **no improving move ∧ all sections agree ∧
evidence complete ∧ query-grounded ∧ no contradiction**. When layer 0 cannot
satisfy it, the disagreement is not voted away — it is **handed upward** to a
fresh layer whose only job is resolving that disagreement.

```text
layer 0: narrow views disagree (apple vs stone)
   │  handoff R_h = (candidates, paths, disagreement map, locks, unexplored)
   ▼
layer 1: only the competing arms are replicated; wider view; carry-mode query
   │  still ambiguous? hand up again
   ▼
layer N: agree → ANSWER   |   never agree → typed UNKNOWN / AMBIGUOUS
```

This is the "matryoshka" of the original design: stacking layers = adding
reasoning depth, not adding parameters.

## Using it

```python
from verantyx import CrossStore, matryoshka_consensus
from verantyx.consensus_store import build_shell_from_store, candidates_for_query

store = CrossStore.load("vera_store.json")
cores = candidates_for_query(store, "what is apple")
shell = build_shell_from_store(store, cores)

out = matryoshka_consensus(shell, "what is apple", carry="A", n_layers=3)
print(out["verdict"], out["resolved_at"], len(out["layers"]))
```

**Increasing the matryoshka** = raising `n_layers`. Each extra layer costs one
more consensus run only when lower layers fail, so deep stacks are cheap on
easy queries and spent exactly on hard ones.

## Carry modes (what query does an upper layer see?)

| Mode | Rule | Behavior |
|------|------|----------|
| **A** | full query at every layer | query relevance can break ties upstairs — resolves most |
| **B** | query only at layer 0 | upper layers judge on evidence alone — evidenced ties stay AMBIGUOUS (most conservative) |
| **C** | intent head only, content decays | keeps the topic, drops noise — between A and B |

All three are deterministic; pick per use case (A for QA, B for auditing
whether evidence alone suffices, C for long noisy queries).

## Important honesty note

An upper layer receives **all competing hypotheses** (from the global
hypothesis list, not just section votes). Early versions leaked rivals out of
the handoff, letting an upper layer "resolve" a tie simply by never seeing
the loser — a disguised majority vote. The fork `MATRYOSHKA_CARRY_MODES`
guards against this regression: mode B must *stay* AMBIGUOUS on genuinely
tied evidence.

## Other places the same idea appears

- **Math**: parenthesis depth = layer; inner expression results are handed
  upward (`eval_expr` layer trace).
- **Digit growth (planned)**: numbers beyond 6 digits by stacking digit
  layers, the arithmetic version of "clone the structure to grow capability".
