# Placement simulation — deciding what goes on the faces before shipping

An arm of the stereo cross has five faces: one core and four facts. A core in
a real store usually has more facts than that. In the reference store
(889,144 cores, 9.78M facet links) 18.5% of cores carry more than four, and
the largest carries 23,714.

So shipping a store is not just filling it. Every arm is a **choice of four**,
and until this module existed the choice was one line:

```python
store.top_facets(core, k=4)      # the four the corpus repeats most
```

Frequency is a rule about the corpus. The question is a different thing.

## First: does placement matter at all?

There is no point optimising a knob that does nothing, so this was measured
before anything was built. Three things can be varied independently.

| varied | queries | result |
|---|---|---|
| which core goes on which axis | 40 permutations | 1 distinct outcome — **no effect** |
| the order of 4 facts across 4 faces | 40 permutations | **no effect** |
| **which** 4 of N facts get placed | 120 real queries × 8 selections | verdict changed **0/120**, answer text changed **120/120** |

Axis order does nothing because energy is computed per arm. Face order does
nothing because `facts_on_axis` collects every non-empty face and the overlap
count is order-blind. Selection does everything, because a fact that is not
placed cannot be said.

So placement decides **what comes out**, not whether anything comes out.

### The measurement that was wrong first

An earlier version of this experiment reported that placement flipped
AMBIGUOUS into ANSWER. It did not. The test zipped facets against
`FACET_READ_ORDER`, whose first element is `tip` — so facet #1 overwrote the
core. The "ANSWER" it produced was a shell whose arm had a different core on
it. `FACET_FACES` is the four-element tuple; `FACET_READ_ORDER` is the
five-element read path, and they are not interchangeable.

## Second: the six-arm consensus is inert on this store

While measuring the above, a larger fact surfaced. Over 300 sampled queries:

```
arms filled per query:   1 → 298     2 → 2
```

`candidates_for_query` drops non-head content words as core candidates once
the head itself is in the store (the rule that stops a huge generic core from
displacing the head — the "tokyo vs film" fix). The consequence is that
retrieval hands the shell **one occupied arm**, so the six cross-sections all
see the same arm, agreement is 1.0 by construction, and the search machinery —
arm swaps, rotation, escape — has nothing to disagree about.

That is a fact about retrieval, not about the geometry, and it bounds what
placement can do: with one arm, arms cannot collide, so the only measurable
lever is whether the answer covers what the question asked.

## The policy

`simulated` scores each candidate fact of a core and keeps the best four:

```
demand(c,f)  = count(c,f) / mass(c)             corpus co-occurrence (prior)
             → 0.25·prior + 0.75·(asked(c,f)/asked(c))   when questions exist
discrim(f)   = log(N_cores / df(f))             how few other cores carry it
score        = demand · (1 + w·discrim)
```

Ties break lexicographically, so the order is total and two runs cannot
disagree.

Demand is **conditional on the core**. A flat token count was the first
version and cannot express what is being modelled: "outage" is a common word,
but whether someone asking about a particular town wants to hear about
outages is a fact about that town's arm, and a global count averages exactly
that away.

### `w` defaults to zero, because it was measured

`--sweep`, 200 held-out questions on the reference store:

| w | mean uncovered terms |
|---|---|
| frequency baseline | 0.805 |
| **0.00** | **0.700** |
| 0.25 | 0.715 |
| 0.50 | 0.715 |
| 1.00 | 0.715 |
| 2.00 | 0.720 |

The whole gain comes from observed demand; discrimination is a small tax.
That is not a refutation of it — discrimination exists to stop competing arms
leading with the same fact, and at one arm per query the benefit it targets
cannot occur while its cost still can. The parameter stays, at zero, with the
measurement attached.

## The result, and the condition it depends on

Placement is computed from a **training** set of anticipated questions and
judged on a **held-out** set. Without that split the policy reads demand off
the questions it is graded on, and the number is memorisation.

The training and test sets must also cover the **same cores**. The first
attempt split one-question-per-core into halves, which put disjoint cores on
each side and measured only that facts about `apple` do not predict facts
about `zebra`. Pre-simulation does not claim that. It claims past questions
about a body of knowledge predict future questions about the same body.

Reference store, 300 held-out questions, 900 training questions:

```
demand = zipf        (concentrated, stable — what a deployment looks like)
  uncovered query terms   0.8367  →  0.7233     −13.6%   ACCEPTED
  answer rate             1.000   →  1.000

demand = uniform     (every fact equally likely to be asked about)
  uncovered query terms   0.8333  →  0.8533     +2.4%    REJECTED
  answer rate             1.000   →  1.000
```

**Pre-simulation works exactly when demand is concentrated and stable, and
not otherwise.** Under uniform demand no query-independent placement can beat
any other: placing 4 of N covers the asked fact with probability 4/N whatever
the policy chooses. The uniform row is not a failure of this module; it is
the boundary of what it can do, measured rather than assumed.

Both rows are pinned as forks (`PLACEMENT_SIMULATION`), because a policy that
always looks like an improvement is one whose gate does not work.

## Mixed knowledge, several arms: placement changes the verdict

Everything above was measured where retrieval fills one arm. There is a
second regime, and it behaves differently.

A query whose words are *facts* rather than *topics* — "what has dosage
onset" instead of "what is clinica" — takes the facet-overlap path in
`candidates_for_query` and fills all six arms. This is the mode the whole
cross machinery was built for, and the mode a domain assistant is actually
used in.

Two clinics-and-shelters stores, twelve aspects per domain, each core
carrying a random eight of them, questions drawn from a concentrated stable
demand, 97 training questions and 68 held-out ones:

```
                        frequency    simulated
verdict changed             —          31/68
answers                    22            12
ambiguous                  43            55
```

Fewer answers looks like a regression. It is the opposite. Each question
names two aspects, so the answer key is decidable: an ANSWER is justified
only if exactly one candidate core carries both.

```
                     frequency   simulated
justified ANSWER          1           3
MANUFACTURED ANSWER      21           9
correct refusal          40          52
missed                    6           4

manufacture rate      30.9%       13.2%
```

Better in all four cells. The mechanism is worth stating because it is not
the obvious one: demand is shared across a domain, so simulation places the
*same* asked-about facts on every core, and cores that are genuinely
indistinguishable end up *looking* indistinguishable. The frequency rule
breaks ties alphabetically, which fabricates distinctions between arms that
are really the same, and those fabricated distinctions become confident
answers.

So placement's contribution here is not fluency. It is **calibration**.

Two caveats. This is a synthetic store with a planted answer key, not real
documents. And the matryoshka path was run alongside and returned results
**identical** to the single layer on all 68 questions — layered inference
escalated and resolved the same way, so it contributed nothing measurable
here.

### The failure this regime exposed

The first version of `demand_from_queries` credited each question's demand to
its **top** retrieved core. Against six clinics that all carry dosage and
onset, the whole question landed on whichever ranked first, that clinic alone
got those facts placed, its arm out-scored five identical rivals, and a
genuinely undecidable question came back as a confident ANSWER naming one
clinic. Frequency said AMBIGUOUS, correctly.

That is the worst thing this module can do — not a worse answer, but a
correct refusal converted into a wrong one — and no gate in `accept` catches
it, because the answer rate goes **up** and every check reads that as
improvement. It is pinned as a shape instead, by
`PLACEMENT_CANNOT_MANUFACTURE_CONFIDENCE`. All retrieved cores are now
credited, which is also just true: when a descriptive question matches six
things, all six are what the asker wants to hear about.

## The gate

`--write` refuses unless:

- the answer rate does not fall — a more specific answer that is also a
  refusal is not an improvement
- uncovered query terms do not rise
- and **something** improves: fewer uncovered terms, or fewer lead collisions

The two improvement routes are the one-arm and multi-arm cases, not
alternatives to taste. Requiring collisions to fall would reject every
placement on this store on a technicality; requiring neither would let a
no-op through.

## What it looks like

Forty cores, twelve facts each, all with equal corpus counts:

```
frequency   every one of the 40 cores:
              brightness colour crispness firmness

simulated   topicaa   origin flavour brightness colour
            topicab   colour redness texture brightness
            topicba   flavour crispness brightness colour
```

The frequency rule gave all forty arms the same four words — its tie-break is
alphabetical, so equal counts collapse to one answer repeated forty times.
39 of 40 cores changed under simulation.

## Determinism is preserved

This is a **build-time** stage. Nothing in it runs when a question is asked.
The output is data in the store (`placement`, `placement_meta`), the reading
path consults it, and the same store answers the same question the same way
forever.

A store with no `placement` key — every store built before this existed —
falls back to `top_facets` and behaves **identically**. That is pinned by
`PLACEMENT_BACKWARD_COMPATIBLE`, byte-for-byte on the answer text, because a
silent shift in every historical store's answers is the kind of regression
that surfaces months later as "the numbers in the README are wrong now".

Placement can only select among facts the store already holds. It cannot
invent one. The worst a bad policy can do is give an uninformative true
answer — never a false one.

## Running it

```bash
vera placement vera_store.json --queries operator_questions.txt
```

```bash
vera placement vera_store.json --queries operator_questions.txt --write vera_store.placed.json
```

```bash
vera placement vera_store.json --sweep
```

`--queries` takes one anticipated question per line and is strongly
preferred. Without it the tool synthesises questions from the store and says
so in its own output; the synthetic set is a stand-in for traffic, not a
substitute for it, and the demand model it assumes (`--demand zipf`) is the
assumption the whole result rests on.

Exit is non-zero when the gate refuses, so this is usable as a build step.

## See also

- `verantyx/placement.py` — the policies, the gate, the sweep
- `verantyx/cross_geometry_forks.py` — `PLACEMENT_SIMULATION`,
  `PLACEMENT_BACKWARD_COMPATIBLE`, `PLACEMENT_GRANULARITY`
- [METAMORPHIC.md](METAMORPHIC.md) — the other half of the loop: finding the
  defect rather than choosing the layout
