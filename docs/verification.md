# Verification

photoloset does not test whether an invariant passes. It tests whether the
check for that invariant **can fail at all**.

That distinction is the whole engineering posture of this project, and it is
why development here is slower than a comparable AI application. This page
explains the machinery, shows what it has actually caught, and gives the
numbers.

## Why a garment tool needs this

The pipeline is `image → hypothesis → 3D → pattern → sewing`. Every stage is
a place where a plausible wrong answer can be produced and passed downstream
as if it were an observation. At the end of that chain somebody cuts cloth.

A conventional agent pipeline looks like this:

```
AI decides  →  next stage  →  AI decides  →  next stage  →  a finished thing
```

Nothing in that chain distinguishes "measured" from "guessed", so the output
is a garment that looks right and may be wrong in ways nobody can point at.

photoloset puts a deterministic layer between every pair of stages:

```
AI  →  hypothesis  →  store  →  OBSERVED / CONTESTED / INFERRED /
                                PROPOSED / UNKNOWN_NOT_OBSERVED  →  next AI
```

A claim that cannot be supported does not become a weaker claim. It becomes a
**typed refusal** carrying `how_to_close` — the thing somebody would have to
do to earn the answer. There are **127 distinct refusal types** in the engine.

## Three layers

### 1. Checks

Ordinary assertions over real behaviour: draft the reference coat, sew it,
read the store, compare against pinned literals. **139 checks.**

The check set is itself pinned by name. A check that disappears while the
total goes up is a specific failure this project has had, so
`no check went missing` reads what the run actually reported rather than what
the source looks like it should report, and a retirement has to be written
into a list, in a diff, with a reason.

### 2. Falsifiers

For each check, a mutation of the implementation that the check is supposed
to catch. The harness applies the mutation, runs the suite, and requires the
named check to go **red**. A mutation that leaves everything green is a
`MISS` — it means the check does not actually constrain the behaviour it
claims to.

**146 mutations**, in three banks:

| bank | entries | scored against |
|---|---|---|
| cross | 73 | the store's own sections, in process |
| loop | 31 | the retrieval loop's sections |
| whole suite | 42 | all 139 checks — these exist for the failure of a check *disappearing*, which by construction cannot be seen by running only the checks that still declare themselves |

### 3. The scanner

The layer above: a static and runtime analysis that reads the checks
themselves and asks whether each condition **could ever be false**. Eight
shapes, found repeatedly in this codebase:

| | |
|---|---|
| T1 | the same value on both sides of a comparison |
| T2 | `all()` / `any()` over a possibly-empty collection |
| T3 | the wrong object under test |
| T4 | a property that is true by construction |
| T5 | `len(a) == len(b)` where both are 0 |
| T6 | a detail line printing a number the condition never constrains |
| T7 | a served reader that can bypass its store |
| T8 | a harness guard too narrow to catch its own mutation |

T7 is a **runtime** probe, not a reading: it freezes each reader to a
constant, runs the suite, and sees whether anything reddens. The static
reading said 18 of 18 readers were pinned. The probe said **7 were
bypassable**.

Hits that are genuinely acceptable go on a list with a written reason.
Currently **5 entries**, each explaining why the shape is present and which
falsifier turns that check red anyway.

## What it has caught

Three real events, all from the same week.

### The scanner caught the author's own checks

New checks were written for the stable-numbering module. The scanner flagged
five hits — T1, T5 and T6 on one check, T2 on another. They were correct:

- two registries built in the same order agree whether or not the number is
  derived from the address, so comparing them proved nothing
- four addresses on four different edges are distinct **by construction**
- `all()` over a watch list is `True` when the list is empty

The rewritten check now builds the wrong implementation inline — numbering by
enumeration — runs both against the same revision, and **requires the naive
one to break**. Measured: a piece inserted at the front moves 21 of 21 edges
under enumeration, including `後身頃/e0` from 0 to 300, while the registry
moves 0. If enumeration had survived, the check would have been worthless.

### A falsifier that was a no-op scored MISS, not green

One of the new mutations replaced `self._bases[k] = self._next` with
`self._bases[k] = len(self._bases) * STRIDE`. At the moment of assignment `k`
is not in `_bases` yet, so those two expressions are **equal** — the mutation
changed nothing, and the check correctly stayed green.

The sweep scored it `MISS`. That is the entire reason the MISS column exists:
a falsifier that does not falsify is not evidence, and the harness will not
count it as such.

### The control layer found a design flaw before the geometry did

Darts are wedges cut out of a flat panel so the cloth can become a cone. The
obvious implementation writes the dart's legs into the panel outline as new
vertices.

That collides with stable numbering. Numbers are addressed as
`(piece, edge, position)`, and edge names come from the outline's vertex
order — so inserting one vertex makes `e1` a different segment while every
base stays put. The registry answers "nothing moved" and the numbers point
somewhere else.

This was measured before the refusal existed: after inserting one vertex,
numbers 100, 150, 250 and 300 all kept their edge *name* across the change.

The fix was architectural, not local: **outline and internal construction are
different address spaces.**

```
garment geometry
├── outline            ← stable, numbered, never edited by construction
│   ├── e0
│   └── ...
└── internal construction
    ├── dart
    ├── seam
    ├── fold
    └── ease
```

Darts became a separate layer addressed at `(piece, edge, t)` — the same
address the numbering uses — and `points.label()` now returns
`UNKNOWN_OUTLINE_RESHAPED`, naming the piece and its vertex count before and
after, when anything does reshape an outline.

A conventional implementation finds this when a pattern comes out wrong. Here
it surfaced as a refusal on the day the two features met.

## The numbers

```
139  checks, all passing
146  falsification mutations, all red, 0 MISS
127  distinct typed refusals in the engine
 32  engine modules, standard library only
  5  recorded tautology exemptions, each with a written reason
```

Sizes:

| | lines |
|---|---|
| engine | 14,412 |
| verification | 9,607 |

The verification code is **67% the size of the thing it verifies**.

One more measurement the project keeps: the reference coat's geometry digest
is `bbc1d025184d1cff58977def178faf49`, and it has not changed across the last
twelve commits. Every feature added in that span was added without moving the
garment that already worked. The script that computes it is in the repository
(`tests/coat_digest.py`) — an earlier digest had to be replaced because
nobody but its author could recompute it.

## Why this is slow, on purpose

Adding one feature looks like this:

```
add the feature
  → write the checks
    → falsify the checks
      → find the checks are tautological
        → rewrite them
          → add the mutations
            → find a collision with an existing invariant
              → change the design
                → sweep everything again
```

That is genuinely slower than shipping the feature. It is the cost of a
property most AI pipelines do not have: **a wrong intermediate state cannot
be passed downstream as if it were right.**

The sweep itself is no longer the bottleneck. Three fixes took it from an
estimated 65 minutes to a measured 8 minutes 11 seconds:

| cause | fix | effect |
|---|---|---|
| the tree copy carried 1.2 GB of Xcode build cache | exclude build artefacts | copy 1.3 GB → 30 MB, 0.17 s |
| the cloth solver recomputed the same drape once per mutation | memoize, keyed on the solver's **own source bytes** so a mutation misses the cache | suite 138.8 s → 29.7 s warm |
| the whole-suite phase ran serially | fan out over one tree copy per worker, after warming the cache once to avoid a stampede | 2.5× on the cores that were free |

The memo is the interesting one. A cache keyed on call arguments would be
blind to a `GRAVITY` edit — gravity is read from a module global inside the
function, never passed in — and would serve the previous answer under a
mutation meant to change it. Hashing the entire source text of both solver
files means any mutation misses the cache and the mutated code runs for real.
Measured with a **warm** cache: `GRAVITY -980 → -490` reddens 6 checks,
`STITCH_STIFFNESS_RATIO 16 → 4` reddens 2, and restoring returns all green.

## What this does not claim

- It does not claim the engine is correct. It claims that a specific list of
  properties is checked, and that each of those checks has been shown to fail
  when the property is broken.
- It does not claim the mutation set is complete. Mutations are written by
  hand; the ones nobody wrote are not covered, and the whole-suite bank exists
  precisely because that gap was found once already.
- It does not claim the garment is right. It claims the garment has not
  silently changed.
