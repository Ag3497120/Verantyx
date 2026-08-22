# Pre-registration — B″3, the joint measured against the verb's own surface

**Registered 2026-08-16, after the third attempt hit P7 and before any
measurement of the fourth.**

## Why the third attempt stopped

B′3 asked whether the text left of the negation ends in て/で followed by
one or two kana. The て branch was right; every prediction it was given
in advance came true:

```
彼は来ない。        ¬来る   restored
我は行かぬ。        ¬行く   restored
問題ない。          ¬ある   survives   (predicted in advance)
まだ開いていない。   ¬いる   stops      (predicted in advance)
ごみを捨てない。    ¬捨てる  not false-blocked
旗を立てない。      ¬立てる  not false-blocked
```

The で branch was wrong:

```
今はできません。    left = 「今はでき」  → で+き matched
作業ができない。    left = 「作業ができ」 → で+き matched
```

**できる begins with で.** The rule scanned raw characters and mistook the
verb's own first syllable for a conjunctive joint.

## B″3 — subtract what is known before scanning

The scan was reading characters that were never in question. The lemma of
the negated verb is already in hand, and so is its conjugated surface, so
the verb's own text can be removed before anything is looked for:

```
まだ開いてい|ない   surface い   → remainder 「まだ開いて」 ends て → joint
今はでき|ません     surface でき → remainder 「今は」       no て/で → content
作業ができ|ない     surface でき → remainder 「作業が」     no て/で → content
ごみを捨て|ない     surface 捨て → remainder 「ごみを」     no て/で → content
```

**B″3** — strip the negated verb's own conjugated surface from the text
left of the negation; the verb is an auxiliary only if the *remainder*
ends in て or で.

This is not a narrower character rule. It removes the class of error
entirely: no verb's own spelling can ever be read as the joint, because
its spelling is subtracted first. B′1 (part of speech) and B′2 (single
token) are carried unchanged.

## A reading that must be corrected, not carried

The third measurement reported "untaggable 50" as fragments B′2 was
catching. That was wrong: `りする` tags as a single 動詞 and passes every
gate. Whatever produced those 50 was not what the report claimed, and
this run must report the blocked counts by actual cause rather than
repeating the earlier attribution.

## Frozen pass lines

- **P1** — zero fabricated lemmas.
- **P5″** — zero stored lemmas whose `pos1` is 助動詞 / 接続詞 / 名詞 /
  助詞 / 副詞.
- **P7″** — 来る **and** 行く **and** できる are all restored. Any content
  verb still cut stops the run.
- **P6″** — the only bank movements permitted are the two already
  predicted and observed (`問題ない` keeps `¬ある`; `まだ開いていない`
  loses `¬いる`). Any third movement stops the run and is reported.
- **P8 (new)** — the false-block probes must all survive:
  捨てない / 立てない / 流れない / 消さないで / 見えない.
- **P3** — the 50-item commonsense bank still returns WRONG = 0.

## Quantities to be measured (not predicted)

1. Facets surviving on the same 10,000 slice, before / after B″.
2. The 20 most frequent surviving lemmas.
3. Cores gaining at least one mark.
4. Blocked counts **by actual cause** (pos, multi-token, joint).

## Stop conditions

- P7″ fails → the discriminator is still wrong after three attempts;
  stop and report rather than attempt a fourth variant in the same run.
- P6″ shows a third movement → stop.
- P8 fails → the joint test has become too eager; stop, do not exempt
  individual verbs.
- Surviving facets fall to zero → report, do not loosen.

## Standing limit, restated a third time

`ちる` passes every gate: 動詞,一般, one token, no joint before it. A
fragment that happens to spell a real verb cannot be separated by
grammar. It is named again so it is not patched with an exclusion list.

## Note on what has already been learned

Three attempts, three stops, all on conditions written before the data
was seen — and none of them visible on W1a's own 97/97 hand-written
banks. The banks were not wrong; they were small. That is the finding
this document exists to preserve if the fourth attempt also stops.
