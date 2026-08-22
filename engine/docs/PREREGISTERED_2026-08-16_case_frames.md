# Pre-registration — case frames as the base model

**Registered 2026-08-16, before any extraction is run.**

## What is missing, measured

`predicate_profile` stores `noun → predicates that took it as subject`
and throws the case particles away:

```
流れる → {流れる:1, である:3, 踏まえる:1, 描く:1, きる:1, 傑作である:1}
```

Who did what to whom is gone. Nothing in the repository holds argument
structure — `grep` for case_frame / valency / 項構造 returns nothing.

This is why generation is template concatenation, why an unknown noun
gets reach but no type, and why the instruction table is 48 hand-written
verbs. For a system with no weights, **the base model is a grammar with
valency**, and it does not exist yet.

## What is proposed

One pass over the same 1,419,406 lead sentences, with fugashi, keeping
the 助詞 instead of discarding them:

```
流れる:  [Nが] 流れる
科す:    [Nが] [Nに] [Nを] 科す
```

No new corpus, no new dependency. The same machine as the predicate
pass (620s measured), minus one discard.

## Frozen pass lines

- **C1 — transitivity separates.** Ten known intransitives
  (流れる/存在する/生まれる/始まる/変わる/届く/残る/起こる/伝わる/至る) and
  ten known transitives
  (科す/含む/持つ/使う/作る/def:与える/決める/示す/求める/設ける) are checked.
  Every transitive must show a を rate above every intransitive's を rate,
  with no overlap between the two groups. **This is the pass line that
  can actually fail** — it is a fact about Japanese the extraction must
  reproduce, not a number the extraction defines. Overlap means the
  extraction is broken and nothing downstream may use it.
- **C2 — absence is not a negative frame.** A case that was never
  observed is recorded as unobserved, never as "this verb does not take
  it". Japanese drops arguments freely; an unwritten を is silence.
  Defense line 1 of the meaning-layers spec, applied again.
- **C3 — the thin side decides.** Frames are compared as ratios, never
  raw counts, and a verb whose observed frame count falls below the
  minimum abstains with `INSUFFICIENT_FRAME`. Coverage is reported on
  both sides of any comparison.
- **C4 — informativeness, not just presence.** が/を/に appear with
  nearly every verb. The global mass table built today
  (1,419,407 cores / 93,110 tokens) supplies the discriminating power,
  the same way it separates 果実 from のこと. A frame slot that every
  verb has distinguishes nothing.

## Quantities to be measured (deliberately not predicted)

1. Verbs with at least one observed frame; verbs reaching C3's minimum.
2. Mean observed arity.
3. Distribution over が / を / に / で / へ / と / から / まで.
4. `INSUFFICIENT_FRAME` rate.
5. Wall time for the pass.

## Stop conditions

- C1 overlaps → the extraction is wrong. Stop; do not proceed to
  generation on frames that cannot tell 流れる from 科す.
- C2 violated anywhere → a negative frame has been written; stop and
  ledger every one, as the 103,599-claim repair was ledgered.
- Verbs reaching C3's minimum falls to near zero → the corpus's lead
  sentences are too short to carry arguments; report that rather than
  lowering the minimum.

## Known limits, recorded before measuring

- **項の省略.** Japanese omits arguments constantly. What is extractable
  is the frame *as written*, never the verb's true valency. Every
  downstream consumer must read it as "these cases were observed", not
  "these are the cases".
- **リード文一段落.** The extractor sees one lead sentence per title.
  The抽出器 experiment already showed this is an information ceiling
  that a better tagger did not lift; there is no reason to expect frames
  to escape it.
- **格フレームは常識を作らない.** 「氷は冷たい」 stays at 9/50. Frames
  give structure, not world knowledge.

## Why this and not more polarity

Polarity stopped four times today, each time because a sentence-final
character rule was asked to decide something that lives in the argument
structure. Frames are upstream of it: 「〜してはならない」 is a frame with
a modal, not a suffix. Building the base first is expected to make the
fifth polarity attempt a different problem rather than the same one — an
expectation, recorded here as an expectation and not as a result.
