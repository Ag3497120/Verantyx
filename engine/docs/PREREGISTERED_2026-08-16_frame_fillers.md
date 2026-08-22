# Pre-registration — what fills each case slot

**Registered 2026-08-16, before the noun side is extracted.**

## What is missing

`case_frames.json` (10,237 verbs, C1′ PASS) records **which** cases a verb
takes and discards **what** filled them:

```
have:  科す → に 0.31  を 0.62
lack:  に = who (person / organisation)   を = what (刑 / 罰)
```

A sentence cannot be built from slots alone, and an unknown noun cannot
be typed without knowing which nouns normally occupy the slot it landed
in. This is the third discard of the same shape found today: the
predicate pass threw away 助詞, the frame pass threw away the サ変 stem,
and this one throws away the noun.

## The change

The same pass, keeping the noun each case particle attached to:

```
verb → case → Counter(noun)
```

Nouns are taken as the contiguous 名詞 run immediately preceding the
particle. A サ変 stem already consumed into a verb (存在 in 存在する) is
**not** also counted as a noun — double-counting the same token on both
sides would inflate exactly the slots the C1′ work just cleaned.

## Frozen pass lines

- **N1 — the slots separate.** For the ten C1′ transitives
  (含む/持つ/使う/作る/与える/決める/示す/求める/設ける/定める), the most
  frequent noun in the に slot must differ from the most frequent noun in
  the を slot, for **at least 8 of 10**. If a verb's に and を are filled
  by the same noun, the extractor is recording adjacency noise rather
  than argument structure, and nothing downstream may use it.
- **N2 — absence is not a negative filler.** A noun never observed in a
  slot produces no entry. There is no "cannot fill" record. Carried from
  the meaning-layers defence line 1.
- **N3 — the thin side decides.** Slots are reported as ratios with the
  observation count beside them. A slot below the count floor abstains
  with `INSUFFICIENT_FILLERS` rather than reporting a ratio over a
  handful.
- **N4 — no double counting.** `存在` must not appear as a filler of
  `存在する`'s own slots. Checked directly on the ten サ変 verbs that
  C1′ restored.

## Quantities to be measured (not predicted)

1. Distinct nouns recorded; file size on disk.
2. Mean distinct fillers per (verb, case).
3. Mean Jaccard overlap between the top-20 に and top-20 を fillers, over
   the ten test verbs. Reported, **not** gated — N1 is the pass line, and
   adding a second threshold after seeing a distribution is the trap this
   session stopped seven times for.
4. Wall time.

## Stop conditions

- N1 fails (fewer than 8 of 10 separate) → the extraction is capturing
  position, not structure. Stop; nothing is written.
- N4 fails → the サ変 stem is being counted twice. Stop and repair before
  anything downstream reads the file.
- Output exceeds what can be held → report the size and stop rather than
  silently truncating; a cap chosen after seeing the size is a cap fitted
  to the data.

## Recorded before measuring

The frames already look linguistically right (位置する に0.87, 科す
を0.62/に0.31, 贈る に0.74), so N1 is expected to pass. Written down so a
pass counts as a confirmation rather than a discovery.

## Limit, restated

This gives which nouns were **observed** in a slot, never a type. 「人が
入る」 is a generalisation over observed fillers and remains a separate
question; the store holds the fillers, not the class.
