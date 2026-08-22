# Design — why Vera is shaped like this

## Origin

Vera descends from a geometric thought experiment: the human brain runs at a
low clock rate with massive parallelism, so what data shape suits "many slow
cores"? The answer explored here is the **stereo cross**: a center cube with
six arms, five exposed faces per arm. A concept's core meaning sits on the
arm tip; its constitutive facts sit on the side faces. Structures connect
face-to-face; queries injected at the outer edges shift each node's energy
ratio and thereby the paths toward the center — **the path change is the
inference**.

The engine in this repo is the operational distillation of that vision:

| Vision | Implementation |
|--------|----------------|
| cross = concept (tip core + facet faces) | `CrossStore`: core → {facet: count} |
| query shifts energy ratios | `axis_energy` = mass × query-match × facet overlap |
| explore from multiple cut faces toward center | multi-frontier sections in `consensus.py` |
| answer = where independent explorations meet, stably | the ANSWER gate (below) |
| tilt / rotate for nuance | sense clusters + specifier-word selection |
| matryoshka nesting = deeper reasoning | disagreement handed to upper layers |
| words carry gravity | deterministic mass from occurrence counts |

## The one non-negotiable: typed refusal

An answer ships **only** through this gate:

```text
ANSWER ⟺ NoImprovingMove ∧ AllSectionsAgree ∧ EvidenceComplete
        ∧ QueryGrounded ∧ NoContradiction
```

Everything else is a *typed* verdict (`UNKNOWN_NO_EVIDENCE`,
`UNKNOWN_SECTION_DISAGREEMENT`, `AMBIGUOUS`, …) carrying the reason. Three
design rules follow:

1. **No majority votes.** Sections share the same store, so their votes are
   not independent evidence; agreement is required, ties stay AMBIGUOUS.
   (Twice during development a hidden majority-vote leak appeared — once in
   matryoshka handoffs, once in ungrounded high-mass retrieval — both are
   now guarded by regression forks.)
2. **Lexicographic acceptance, never weighted sums.** Search moves are
   accepted by (contradiction ↓, evidence deficit ↓, agreement ↑,
   relevance ↑, cost ↓) in strict order, so relevance can never buy its way
   past missing evidence.
3. **Local stability is a flag, not a licence.** "No proposal improves" only
   stops the search; shipping additionally requires the agreement and
   evidence gates.

## Determinism as a feature

Same store + same query + same config → identical output, always. This buys:
reproducible bugs, meaningful self-tests (41 forks in `vera lab`), auditable
answers (facet counts + provenance), and real deletion (`forget` removes the
data; there are no weights for it to hide in).

The only optional nondeterminism is a local LLM's *wording* in hybrid chat —
and the router guarantees it never touches proven values (math/code) and
never resolves an AMBIGUOUS verdict.

## One substrate, many faculties

The same cross + gate machinery hosts every capability, which is the point
of the original "one geometry" vision:

- **Knowledge QA** — retrieve candidate crosses, consensus over arms
- **Memory** — the store *is* the memory; counts grow with use; provenance
  timestamps + `key:value` contradiction detection make it an audit log
- **Sense disambiguation** — facet co-occurrence clusters, selected by
  specifier words (the operational form of "tilting the axis for nuance")
- **Math** — digits on arms, carry as current: exact by construction;
  parenthesis depth = matryoshka layer
- **Symbolic rules** — term rewriting where **rules are data** poured like
  knowledge (`rule:` crosses)
- **Modal logic** — Kripke worlds as crosses, `R` as joins, `□` as the
  agreement gate itself
- **Code reasoning** — functions as crosses (`fn:`), calls as facets;
  bug cause asserted only when traceback / diff / failing-test sections
  agree (`debug_consensus`)
- **Languages** — segmentation is per-language, the gates are not: the
  Japanese consensus path feeds script-runs into the same three gates

## What Vera deliberately is not

- Not a text generator: fluency is bought, labeled, from an optional local
  LLM under Vera's control — never claimed as Vera's own.
- Not a theorem prover or a creative writer: open search spaces without
  external verification are outside the covenant.
- Not magic scale: quality tracks corpus quality; junk in produces
  *visible, deletable* junk — the honest failure mode.

## Passive memory from AI output (quarantined)

An assistant's own output can be fed back into Vera as candidate memory —
useful in an agent/IDE loop where you don't want to type `remember`
manually for every fact that comes up. This is deliberately **not** a
direct write path, because an LLM's text (even final, non-thinking text)
can be wrong, hedged, or exploratory, and the entire point of this project
is that Vera never presents an unverified claim as fact. Passively
absorbing an LLM's own guesses into a "verified, counted" store would
launder hallucination into trusted memory — the one thing this project
exists to prevent.

So `verantyx.ai_ingest` never writes to the trusted `CrossStore` directly:

1. Only an assistant's **final** reply text is accepted — never a
   thinking/chain-of-thought block, which is provisional by nature and
   often self-corrects mid-stream.
2. Hedge-worded sentences ("might", "probably", "I think", "seems", "not
   sure", …) are dropped before they reach quarantine — a sentence the
   model itself is unsure of should not become a fact candidate.
3. Meta-commentary about the assistant's own process ("let me check",
   "I'll now run", "as an AI") is dropped — it isn't world knowledge.
4. Everything else lands in `AiFactQuarantine`, a separate file from the
   trusted store. Nothing there is queryable via `ask` until a human
   explicitly promotes it (`vera review-ai-facts` / MCP's
   `accept_ai_fact`) — the only path from quarantine into real memory.

This mirrors the project's contradiction-detection philosophy: a fact isn't
trusted just because *something* said it — it's trusted once a human (or,
for user-taught facts, the act of teaching itself) has vouched for it.

## Reversible obfuscation, keyed by personal state

A recurring request during design discussions was code obfuscation that
"only Vera can decode" or "requires the same puzzle-reasoning process to
break." Every version of that idea shared one flaw: it tried to make the
*process* secret, but Vera's process is public (MIT, on GitHub) — so is
any conceivable "6-axis isolation" or "consensus-search" scheme once
described or open-sourced. Kerckhoffs's principle: an algorithm cannot be
the secret if it's known (or knowable by inspection/reverse-engineering);
only a **key** can be. "Requires multi-frontier search to solve" is not a
hardness guarantee — Vera's consensus search is explicitly polynomial-time
and deterministic, the opposite of what a real puzzle-hardness claim would
need, and dressing it up as one repeats the exact over-claiming pattern
this project exists to refuse (see the JCross critique, same principle).

The version that *does* hold up: two people running the identical public
code accumulate **different CrossStore state** — different facets, counts,
and insertion order, shaped by what each person actually poured and in
what sequence. That path-dependent residue is real, personal, and not
reconstructible by an outsider without the same history. Used as key
material (`obfuscate.fingerprint_store` → PBKDF2 → AES-256-GCM), it's a
legitimate instance of "your personal secret, not the algorithm, is the
key" — the same principle behind a password or a keyfile, just derived
from a richer, evolving structure instead of a memorized string. The
actual hardness guarantee comes entirely from the vetted cryptographic
primitive (AES-256-GCM via `cryptography`), never from home-grown math.

## Roadmap markers

Sharded/parallel pouring for 100M+ row corpora, richer information
extraction (facet quality is the current ceiling), debug-consensus
benchmarked against LLM baselines on real repos, and the IDE bridge
(spawning `vera` as a memory harness subprocess).
