# Code reasoning — repos as cross networks

Code is where explicit structure lives: calls, files, classes, arguments.
Vera ingests a Python repo deterministically (stdlib `ast`, no LM) into one
cross per function:

```text
core   fn:simplify
facets file:verantyx/rewrite_kernel.py · arg:expr · arg:rules ·
       calls:parse_term · calls:_step · calls:term_to_str · …
```

## Commands

```bash
vera --store code.json code ingest path/to/repo
vera --store code.json code ask "who calls wire_add"
vera --store code.json code ask "what does simplify call"
vera --store code.json code ask "impact of parse_term"
```

- **who calls X** — reverse call edges (your blast-radius surface)
- **what does X call** — forward edges + defining files
- **impact of X** — BFS over reverse edges with per-depth layers: everything
  that may break when X changes

Unknown names return `UNKNOWN_NO_EVIDENCE`. No fuzzy matching, no guessed
symbols.

## Python API

```python
from verantyx import CrossStore, ingest_python_repo, who_calls, impact
store = CrossStore()
ingest_python_repo(store, "myrepo/")
impact(store, "parse_term")   # {'impacted': [...], 'layers': [[...], ...]}
```

## Scope & honesty (v0)

- Call resolution is by **name**, not by type: `a.run()` and `b.run()` both
  count as `calls:run`. This over-approximates impact — acceptable for
  blast-radius questions, wrong for precise call graphs.
- Python only; other languages need their own AST front-end.
- Re-ingesting accumulates counts (edges seen in more places rank higher);
  use a fresh store per snapshot if you want exact per-commit graphs.

## Where this is going

The debugging workflow this enables: pour error logs, test results, and
recent-change facts into the same store as the call graph, then let the
multi-frontier consensus demand that **error section, call-path section and
test section agree on the same cause** before proposing a fix — and say
UNKNOWN otherwise. The consensus machinery is already in place; the log/test
ingestors are the missing (planned) piece.
