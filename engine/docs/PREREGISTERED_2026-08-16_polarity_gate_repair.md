# Pre-registration — repairing the existence gate (second attempt)

**Registered 2026-08-16, after the first attempt failed P1 and before any
measurement of the repair.**

## What failed, and what may not be done about it

The first wiring attempt
(`PREREGISTERED_2026-08-16_polarity_ingest.md`) failed pass line P1 on a
10,000-sentence slice of real jawiki leads:

```
P1 FAIL — fabricated lemmas: ふく, ます
¬facets that would be written  370   on 327 cores
top lemmas   する 54 / である 50 / いる 45   = 40% of everything written
```

Two defects, and the second is the larger:

1. `ふく` is tagged 名詞,普通名詞 by unidic. It is not a verb at all, so
   the existence gate let through something it was written to stop.
2. The gate asks whether a lemma is REAL. It never asks whether the
   lemma SAYS anything. `する`, `いる`, `である` are perfectly real and
   carry no information: a core marked `¬する` has learned nothing.

The stop condition written in advance forbids the obvious fix. Adding
ふく and ます to an exclusion list is the same move that got W1a rejected
twice, for the same reason: the class is open, and a list that must grow
forever is a list that is already wrong.

## The repair — ask the dictionary a second question

The final form of W1a won by making unidic the verifier rather than
maintaining a list. The repair extends that, and deliberately does NOT
introduce a frequency threshold: this session has already seen the
distribution, so any cut-off chosen now would be fitted to data already
observed. A grammatical fact is not.

Measured on the tagger just now:

```
ます     助動詞,*,*            ← not a verb
である    接続詞,*,*            ← not a verb
ふく     名詞,普通名詞,一般     ← not a verb
する     動詞,非自立可能,*      ← the dictionary itself says it may not stand alone
いる     動詞,非自立可能,*
ある     動詞,非自立可能,*
持つ     動詞,一般,*           ← content
流れる    動詞,一般,*
含む     動詞,一般,*
```

**Gate A (unchanged)** — the folded lemma is known to unidic.
**Gate B (new)** — `pos1` is 動詞 or 形容詞 **and** `pos2` is 一般.
非自立可能 / 助動詞 / 接続詞 / 名詞 produce no testimony.

No list. No threshold. The dictionary's own part-of-speech judgement,
the same instrument that already decides Gate A.

## Frozen pass lines

- **P1 (carried over)** — zero fabricated lemmas: every stored `¬X` has
  `X` known to unidic.
- **P5 (new)** — zero stored lemmas whose `pos2` is 非自立可能, or whose
  `pos1` is 助動詞 / 接続詞 / 名詞 / 助詞.
- **P6 (bank conflict, named in advance)** — W1a's frozen banks (60 + 20
  + 17) are re-run. **It is already expected that 「問題ない。」 → `¬ある`
  will stop firing, because ある is 非自立可能.** That is a direct
  conflict between two frozen banks: W1a's bank requires the mark, this
  gate forbids it. The conflict is NOT to be resolved by weakening either
  side inside this measurement. Every changed item is listed by id and
  handed to the human to decide. A silently reconciled bank is a bank
  that no longer measures anything.
- **P3 (carried over)** — the 50-item commonsense bank still returns
  WRONG = 0.

## Quantities to be measured (not predicted)

1. ¬facets that would be written, after both gates, on the same 10,000
   slice — and the same figure before, for comparison.
2. The 20 most frequent surviving lemmas.
3. Cores gaining at least one mark.
4. W1a bank items whose verdict changes, listed by id.

## Known limit, recorded before measuring

`ちる` is tagged 動詞,一般 (散る) and will pass both gates even when it
arrived as a fragment. Two gates cannot separate a real verb from a
fragment that happens to spell one. This is named now so a later reader
does not mistake it for an oversight, and so it is not quietly patched
with the exclusion list this document exists to avoid.

## Stop conditions

- P5 fails → the POS reading is not being applied where testimony is
  built; repair that, do not relax P5.
- P6 shows changes beyond the anticipated 非自立可能 family → stop and
  report; an unexpected bank movement means the gate is cutting
  something it was not designed to cut.
- Surviving facet count falls to zero → the gate is too strict and the
  wiring has no content; report rather than loosen.
