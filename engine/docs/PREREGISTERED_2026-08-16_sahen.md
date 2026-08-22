# Pre-registration — restoring サ変動詞, test set unchanged

**Registered 2026-08-16, after C1′ stopped on TEST_SET_TOO_THIN.**

## What was found

```
存在する   0 occurrences
位置する   0 occurrences
```

fugashi splits them as 存在(名詞) + する(動詞), and the extractor recorded
only the 動詞 token. So every サ変動詞 in the corpus collapsed into one
`する` node. The same defect explains `する` ranking first (54) in today's
polarity measurement, where it was not recognised as a defect at all.

Structurally this is the family that produced the 103,599 fabricated
claims: a compound is split and one fragment is kept as if it were the
whole.

## The change

When a 動詞 token folds to `する`, and the token immediately before it is
a 名詞 that unidic marks サ変可能, the lemma is the compound: 名詞+する.
Otherwise `する` stands alone, as it should in 「勉強をする」.

The dictionary decides again — サ変可能 is unidic's own field, not a list
and not a threshold.

## The test set does NOT change

C1′'s ten-and-ten stay exactly as registered. This is the third time the
extraction is being adjusted; adjusting the ruler alongside it would end
any claim that something is being measured. What changes is the
extractor; what judges it is unchanged.

## Frozen pass lines

- **S1** — 存在する and 位置する both reach the FLOOR of 100 occurrences.
  They are at 0 now, so this is a real test of whether the restoration
  fires at all.
- **S2** — the bare `する` node's occurrence count **decreases**. By how
  much is deliberately not predicted; that it must fall is the claim.
- **S3** — 「勉強をする」-shaped cases still yield bare `する`: a を
  between the noun and する blocks the compound. Checked on probes, not
  assumed.
- **C1′ (carried, unchanged)** — every surviving transitive's を-rate
  exceeds every surviving intransitive's, no overlap, floor of 100
  applied first, at least 8 verbs per arm.

## Quantities to be measured (not predicted)

1. Occurrences of 存在する / 位置する after restoration.
2. Bare `する` occurrences, before and after.
3. Verbs with a frame, before and after.
4. The C1′ table.

## Stop conditions

- S1 fails (either verb still under the floor) → the restoration is not
  firing; stop and report rather than widening the trigger.
- S2 fails → compounds are being added without the fragment shrinking,
  which means the same evidence is being counted twice. Stop.
- C1′ overlaps → report and stop. The extraction has been revised three
  times; a fourth revision in the same session would be tuning to the
  test, and the honest move at that point is to hand over.

## Recorded before measuring

Five of five surviving intransitives already sat at ≤0.0153 against five
transitives at ≥0.2212 — a 14× gap with no overlap. The signal is
expected to survive restoration. Written down so a pass counts as a
confirmation, not a discovery.
