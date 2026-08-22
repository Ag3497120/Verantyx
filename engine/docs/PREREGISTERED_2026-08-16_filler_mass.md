# Pre-registration — discounting ubiquitous fillers

**Registered 2026-08-16, before the discount is applied.**

## Scope: fillers only, and why not the other two

The same defect appeared three times today:

```
diff only_a      のこと  df 23,631   outranked  果実  df 257
polarity ¬facets する / である / いる  = 40% of everything
frame fillers    に slot topped by ため in 4 of 10 test verbs
```

One mechanism fixes all three, but only one of them can be measured
honestly right now:

- **fillers** — written today, nothing reads it yet. Cheap and reversible.
- **diff ranking** — `vera_diff` is committed and carries a frozen
  30-question bank (11/30). Re-ranking it requires re-running that bank,
  and bundling it here would make a failure unattributable to either
  change. **Separate deliverable.**
- **polarity** — there are 0 ¬ facets in the store. There is nothing to
  re-rank. Applying a discount to an empty set and reporting a pass would
  be measuring nothing.

## The measure, named plainly

Slot frequency: in how many distinct `(verb, case)` slots does a noun
appear at all. ため appears in thousands; 周辺地域 in a handful.

```
score = (count in this slot / slot total) ÷ (slots holding noun / all slots)
```

This is tf-idf in shape and is named as such rather than dressed up. It
needs no new pass — the fillers file already contains everything.

The existing `global_mass` table is **not** reused: it counts predicates,
not nouns, and borrowing a denominator built over a different population
is the pooling mistake with arithmetic.

## Frozen pass lines

- **G1 — ubiquity falls.** For the ten C1′ transitives, none of
  ため / こと / とき / もの / ところ may hold the top-1 position in the
  に slot after discounting. They hold 4 of 10 now.
- **G2 — real arguments survive.** The three slots that already look
  right must keep a non-ubiquitous top-1:
  `与える に` (currently 者), `含む を` (currently 周辺地域),
  `持つ を` (currently 意味). **This is the pass line that can actually
  fail** — an over-eager discount destroys real fillers along with the
  noise, and G1 alone would happily report success on an empty result.
- **G3 — no slot empties.** Every slot that had a top-1 before still has
  one after. A discount that silences a slot has not ranked it.

## Quantities to be measured (not predicted)

1. The ten verbs' に and を top-1, before and after.
2. Count of distinct nouns whose top-1 position is lost.
3. The ten most-discounted nouns (highest slot frequency).
4. Wall time.

## Stop conditions

- G2 fails → the discount is too strong; stop and report, do not tune the
  exponent. Tuning a coefficient until the examples look right is fitting
  to the examples.
- G1 fails → the discount is too weak; stop and report. Do not add an
  exclusion list for ため — that is the move this session refused four
  times in polarity.
- G3 fails → report.

## Recorded before measuring

ため is expected to fall and 者/影響 to survive. Written down so a pass is
a confirmation, not a discovery.

## Limit

This ranks fillers by how much they distinguish. It does not give them a
type: 者 rising to the top of `与える に` does not tell the store that the
slot wants a person. Observed fillers stay observed fillers.
