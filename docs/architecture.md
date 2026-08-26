# Architecture

```
                 ┌──────────────────────────────────────┐
   photo/video → │  observation      what was seen      │
                 └───────────────┬──────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────┐
   corpora    →  │  retrieval        per PART, never    │  ← quarantined,
                 │                   per garment        │    kind="proposed"
                 └───────────────┬──────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────┐
                 │  the store        one address, one   │
                 │  (stereo cross)   claim; two values  │
                 │                   collide, and both  │
                 │                   are kept           │
                 └───────────────┬──────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────┐
                 │  construction     parts → graph →    │
                 │                   pattern → 3D       │
                 └───────────────┬──────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────┐
   a named    →  │  approval         the gate           │
   human         └───────────────┬──────────────────────┘
                                 │
                 ┌───────────────▼──────────────────────┐
                 │  sewing search    unreachable until  │
                 │                   the gate opens     │
                 └──────────────────────────────────────┘
```

## The store

Every claim lands at an address. An address is a *core* — the thing being
talked about — and a *key* — the aspect being claimed.

Six arms carry meaning, in three dualities: `support±`, `cause±`, `kind±`.
**The writer does not choose an arm.** The writer states a KIND — `measured`,
`cited`, `input`, `derived`, `feeds`, `generic`, `specific`, `declared`,
`proposed` — and the store derives the arm. `support-` is never written by
anyone; it emerges from collision.

Two values at one address is **CONTESTED**. Both are kept, neither is chosen,
and the disagreement is the output. This is not a conflict-resolution
strategy that failed to resolve; it is the honest answer when two sources
disagree and nothing available breaks the tie.

`kind+` and `kind-` share a key, so "this is common construction" and "this
traces to one specific work" collide by design rather than coexisting.

A generic claim requires **two independent sources** before it can be bought.

### What cannot be written

- **Absence.** A retrieval that ran and found nothing writes `kind="no_match"`,
  and the store refuses it with `UNKNOWN_ABSENCE_IS_NOT_A_CLAIM`. The fact
  that a search happened goes to the rights ledger with its scope; "searched
  nothing" cannot be recorded as "found nothing".
- **An anonymous adoption.** `Ledger.adopt` raises `UNKNOWN_NO_ADOPTER` on an
  empty name. That check lives in the ledger and not at the door, because an
  earlier version put it at the door and a measurement walked around it.

## Two address spaces

Outline and internal construction are deliberately separate.

```
garment geometry
├── outline               stable, numbered, never edited by construction
│   ├── e0 ─ e1 ─ ...
│   └── vertices fixed; a change is UNKNOWN_OUTLINE_RESHAPED
└── internal construction
    ├── dart              (piece, edge, t) + intake + apex
    ├── seam
    ├── fold
    └── ease
```

Pattern positions get numbers derived from the address:

```
number = registry.base(piece, edge) + round(t × (STRIDE − 1))
```

The registry is **append-only**. Allocating bases by enumerating the current
pieces is the obvious implementation and it is wrong — a piece inserted at the
front moves every number after it. Measured: 21 of 21 edges move under
enumeration; 0 move under the registry.

This matters because the agent loop is driven by the user pointing at
numbers — "loosen 30 to 35". If the numbering shifts between iterations, the
instruction changes meaning and the loop chases a target it moved itself.

## Retrieval is per part, never per garment

A single global embedding is one vector for the whole image. The question
"this collar resembles A's, this skirt resembles B's" is compositional, and
one vector cannot carry per-part correspondence.

This is enforced rather than documented: a whole-image backend asked a
per-part question returns `UNKNOWN_WHOLE_IMAGE_ONLY`, naming the missing
stage.

Retrieval results land as `kind="proposed"` — the only kind whose arm is
`None`, so it carries no weight into any arm and is not readable at the
part's own address until a named person adopts it.

**The key never carries the source.** If two backends wrote
`resembles:marqo` and `resembles:openclip`, those would be two addresses,
both would answer, and something downstream would sort them by score — a
ranking. Written to the same address they collide into CONTESTED.

## The gate

`sewing_search.methods_for(approval_id, corpus)` takes an approval id and a
corpus name **and nothing else**. The gate is the argument surface, not
discipline: there is no parameter into which an unapproved shape could be
passed. Measured: 9 parameters across 5 public callables checked against 30
forbidden names, 0 offenders.

An approval is unblocked by an adopted ledger entry carrying the approver's
name and a digest of the shape. Adjusting a zone by 0.1 cm recomposes to a
different digest and the old approval stops opening the search.

## No models are shipped

A fresh interpreter finds **0 backends, 0 segmenters, 0 corpora**. That is a
measurement in the check suite, not a claim in a README. An approved shape
reaches the search and stops at `UNKNOWN_NO_SEWING_CORPUS` — it queries
nothing today, and says so in a different sentence rather than returning an
empty list.

## Dependencies

Standard library only, 32 modules. There is a check that parses every module
and fails on a third-party import.
