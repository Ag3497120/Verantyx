# Pre-registration — C1′, with path-を and a floor on the test set

**Registered 2026-08-16, after C1 failed and before the revised test is
run.**

## Why C1 failed

```
自動詞  9 of 10 at ~0.00 を        流れる alone at 0.5968
他動詞  all 0.147 – 0.659
```

One outlier, and it has a name: **経路の を**. Motion verbs license a を
that marks a path, not a patient — 川を流れる, 道を歩く, 空を飛ぶ. The
extraction produced correct Japanese; the test set was linguistically
naive.

A second fault was mine and structural: `科す` occurred **10 times**. The
pre-registration's own C3 says the thin side decides, and the C1 test set
violated it.

## What may and may not be changed

Dropping 流れる because it scored badly would be fitting the criterion to
the result — the trap this project stopped four times for today. What is
legitimate is a **grammatical** exclusion stated before new numbers:

> The を-rate test asks whether a verb takes a patient. For motion verbs
> the question is malformed, because 経路の を marks a path. Motion verbs
> therefore cannot appear in either arm of a transitivity test.

That is a fact about Japanese, decided without reference to any measured
rate. It is applied to a **test set**, not to a production rule — a
hand-picked test set is legitimate; a hand-picked production table is the
failure mode this project has measured repeatedly.

## C1′ — revised test

**Occurrence floor, applied first.** Any test verb with fewer than **100**
observed occurrences is removed from the test set and named in the
output, before any rate is computed. A rate over 10 examples is not a
measurement.

**Intransitive arm (non-motion, 10):** 存在する / 生まれる / 始まる /
終わる / 変わる / 残る / 起こる / 異なる / 属する / 位置する

**Transitive arm (10):** 含む / 持つ / 使う / 作る / 与える / 決める /
示す / 求める / 設ける / 定める

**Excluded from both arms as motion verbs:** 流れる / 届く / 至る /
伝わる. Named here so their removal is on the record as grammatical, not
as score-driven — three of the four scored near zero and would have
helped the test pass.

**Pass line:** every surviving transitive's を-rate exceeds every
surviving intransitive's を-rate, with no overlap.

## は — collected, never merged

`が` appeared 44,434 times against `に` 175,703, because lead sentences
are definitional and mark their subject with は. The subject is largely
not in the case data at all.

は will be collected as **主題**, in a field of its own, and never added
to the case counts. It is not a case particle; folding it in would be the
pooling mistake (束ねず重ねる) applied to grammar. Both numbers are
reported side by side so a later reader can see the asymmetry rather than
inherit a merged figure.

## Quantities to be measured (not predicted)

1. Verbs with at least one observed frame; verbs above the floor.
2. Mean observed arity.
3. Case distribution, with は reported separately.
4. Test verbs dropped by the floor.

## Stop conditions

- C1′ overlaps → the extraction genuinely cannot separate patient from
  non-patient. Stop; nothing is written; do not revise the test set a
  third time in the same session.
- Fewer than 8 verbs survive the floor in either arm → the test set is
  too thin to decide anything; report and stop rather than lowering the
  floor.

## Recorded before measuring

Nine of ten intransitives already sat at ~0.00 with a single explicable
outlier. The expectation is therefore that C1′ passes. That expectation
is written down so that if it passes, nobody — including me — can claim
the revised test was a discovery rather than a confirmation.
