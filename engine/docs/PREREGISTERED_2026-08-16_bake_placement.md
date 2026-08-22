# Pre-registration — bake the placement that was measured and never applied

**Registered 2026-08-16, before any placement is computed or compared.**

## What this is

`verantyx/placement.py` (699 lines) decides which four facets occupy an
arm's faces. Its own docstring records the measurement that motivated it,
made before the module existed:

> across 120 queries, changing which four facets were placed changed the
> answer text 120/120 times and the verdict 0/120 times — placement
> decides WHAT COMES OUT, not whether anything comes out

and the defect it exists to fix:

> frequency ordering puts the same generic word on every competing arm.
> In a six-core probe every single arm led with the same facet

Measured today, the shipped store carries **no baked placement at all**:

```
vera.db  ja  89,369 cores   placement: 0 entries
vera.db  en  15,268 cores   placement: 0 entries
```

So the engine falls back to `top_facets(core, k=4)` — the frequency rule
this module was written to replace. The most load-bearing choice in the
geometry is currently being made by the line it was meant to supersede.

This registers the application of what is already built. It is not a new
mechanism.

## The gate is not being invented here

`placement.accept()` already encodes the criterion, frozen in code before
today:

- the answer rate must not fall
- uncovered query terms must not rise
- and then something must improve: fewer uncovered terms, or fewer lead
  collisions

**It is used unmodified.** If it rejects, nothing is baked. Rewriting a
gate after seeing what it rejects is the one move this whole practice
exists to prevent.

## Protocol, frozen

1. **Store** — the `ja` sovereign of the published `vera.db` (89,369
   cores). It is the one that answers Japanese questions; `en` is out of
   scope for this run and is stated so now rather than after.
2. **Queries** — `placement.derive_split(store, n=200, demand="zipf")`,
   train and test disjoint. Zipf because a uniform demand model treats a
   term nobody asks for as worth the same as one everybody does.
3. **Weight** — `DISCRIM_WEIGHT` ships at 0.0, i.e. discrimination is off
   and `simulated` currently reduces to demand alone. It is swept over
   `(0.0, 0.25, 0.5, 1.0, 2.0)` **on TRAIN ONLY**, and the choice is
   frozen before the test set is touched. Selection rule, fixed now:
   largest reduction in uncovered terms; ties to fewer lead collisions;
   ties to the smaller weight.
4. **Comparison** — `placement.compare` on TEST with the frozen weight.
5. **Decision** — `placement.accept()` verbatim.
6. **Baking** — into a COPY of the published build. The shipped
   `vera.db` is not overwritten by this run; whether it is replaced is
   the operator's call, made after reading the numbers.

## Frozen pass lines

- **P1 — `accept()` returns ACCEPTED on the held-out test split.** This
  is the decision. A REJECTED verdict means the placement is not baked
  and the honest report is that the frequency rule was not beaten.
- **P2 — WRONG stays 0** on the frozen 50-item commonsense bank
  (`tools/commonsense_bank_2026-08-14.json`). Placement can only reorder
  and select among facts the store already holds, so a fabrication here
  would mean something other than placement changed.
- **P3 — the refusal rate on that bank does not rise.** Placement decides
  what comes out, not whether anything does (0/120 verdict changes); if
  refusals rise, that premise is wrong for this store and the run stops.
- **P4 — the verdict is unchanged on the six session probes**
  (りんごとは / 傷害罪とは / りんごと電気の違いは / 3+4は / semiconj /
  ファイルを消して). Their door and verdict must not move; only the text
  of the composed answer may.

## Quantities to be measured (not predicted)

1. The swept weights and their train numbers, all five listed.
2. `compare`'s full delta on test: answer rate, uncovered terms, lead
   collisions.
3. How many cores received a placement differing from frequency, and the
   share of the store that is.
4. The bank's before/after triple (correct / typed refusal / wrong).
5. Answer text that changed on the six probes, verbatim, before and after.

## Stop conditions

- **P1 REJECTED** → do not bake. Report the null. Do not sweep more
  weights, do not enlarge n, do not switch demand model — each of those
  is choosing the experiment that passes.
- **P2 fails** → stop and ledger. A placement cannot invent a fact, so a
  WRONG appearing means the change was not confined to placement.
- **P3 fails** → the 0/120 verdict-invariance does not hold here. Stop
  and report that, because it contradicts the measurement this whole
  module rests on.

## Recorded before measuring

The expected gain is a **more distinctive answer, not a more correct
one**. Placement selects among facts already held, so the ceiling is
bounded: the worst outcome it can produce is an uninformative true
answer, never a false one, and the best is that competing arms stop
leading with the same generic word.

Written down so a small delta is read as the honest outcome, and so a
large one is inspected for something other than placement having moved.

## Not in scope

The census, the grammar, the federation's membership, `jawiki_shallow`'s
atlas-only clause. No model is called. The `en` sovereign is untouched.

---

## Measured 2026-08-16 — P1 REJECTED. Nothing was baked.

### Protocol deviation, recorded before the numbers

`derive_split(ja, 200)` returned train=600 / test=200 with **39 queries
in both**. The protocol above froze them as disjoint, so the 39 were
dropped from TRAIN (train 600 → 561), leaving TEST at the declared 200.
Removing from train rather than test keeps the judged set the size that
was registered, and can only reduce what the placement is able to
memorise.

### Quantity 1 — the sweep, on train

| weight | answer rate | lead collisions | uncovered terms |
|---|---|---|---|
| 0.0 | 0.9983 | 0.0067 | 0.0083 |
| 0.25 | 0.9983 | 0.0067 | 0.0083 |
| 0.5 | 0.9983 | 0.0067 | 0.0083 |
| 1.0 | 0.9983 | 0.0067 | 0.0083 |
| 2.0 | 0.9983 | 0.0067 | 0.0083 |

**All five identical.** The discrimination weight changes nothing on this
store. By the frozen tie rule (smaller weight wins) the choice is 0.0,
which is what ships — so `simulated` here reduces to demand alone.

Train baseline (frequency): uncovered terms **0.88**; simulated
**0.0083**. On its own training questions the policy looks decisive.

### Quantity 2 — the test delta

```
                answer rate   lead collisions   uncovered terms
frequency          1.0            0.0               0.925
simulated          1.0            0.0               0.970
delta              0.0            0.0              +0.045
```

`accept()` — used verbatim, not rewritten:

```
REJECTED
  uncovered query terms rose by 0.0450
  nothing improved: uncovered terms +0.0450, lead collisions +0.0000
```

**The train-set advantage does not survive the split.** 0.88 → 0.0083 on
questions the placement was computed from; 0.925 → 0.970 on questions it
was not. That is the memorisation `compare`'s own docstring warns about,
observed rather than avoided: the simulated policy takes demand straight
from the questions it is shown.

### Quantity 3 — how much the policy actually moves

Sample of 3,000 cores: **4 differ (0.1%)**, 2,561 identical, 435 have too
few facets to fill four faces.

This is the finding that explains the rest. On 99.9% of cores the two
policies choose the same four facets, so there was almost nothing for the
gate to accept. mean_arms measured 1.0 on test — every query resolved on
a single arm, and lead collisions cannot exist with one arm, which
removes the entire second improvement route the gate offers.

### Quantities 4 and 5 — not measured, and why

P2 / P3 / P4 exist to catch damage from baking. Nothing was baked, the
published store is byte-identical, and running the bank against an
unchanged store would report the standing numbers as if they were a
result. They are left unmeasured rather than presented.

## What this run establishes

**Simulated placement does not beat frequency on held-out questions when
the questions are derived from the store rather than observed from
operators.** That is the exact condition the module's docstring names as
its weaker case:

> When the operator supplies the queries the system will actually be
> asked, demand is measured against those instead

`derive_queries` manufactures questions from the store's own zipf tail,
so demand computed from them is a re-description of the corpus. There is
no independent signal for the simulation to find.

Under the stop conditions this run does not get a second attempt with a
larger n, another demand model, or more weights. **Real query traffic is
a different experiment and needs its own pre-registration**, and it needs
traffic that does not exist yet — which is itself the honest finding
about why the most load-bearing choice in the geometry has never been
applied.

The 120/120 measurement quoted at the top is not contradicted. Placement
changes the answer text when the placement changes; measured here, on
this store, the simulated policy almost never changes it (0.1%).
