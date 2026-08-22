# Pre-registration — a rephrasing must be certified, not merely accepted

**Registered 2026-08-16, after S1 failed and before the gate is written.**

## What failed

`suspend`/`resume` worked mechanically and failed its own first pass line:

```
こおりは冷たい   UNKNOWN_NO_EVIDENCE
  → rephrased 「氷 冷たい」
  → ANSWER   core: ブラック   tokens: ブラック 吸収 変化 最中 氷
```

The core is 「ブラック」. 「冷」 appears in no facet. An honest refusal
became an answer about something else, and the verdict said ANSWER.

The cause is one line in `resume`: it treated "stopped refusing" as
"answered". Whether the rephrasing still asks the ORIGINAL question was
never checked. The three successes (リンゴ / 電荷密度 / 時効) were correct
rephrasings, not a mechanism that guarantees correctness — they passed
for the same reason the failure passed.

## The gate — certification by an organ that already exists

Not a similarity score and not a threshold. A rephrasing is admissible
only when one of the engine's existing organs certifies it as a **variant
of the original subject**:

- `aliases` — 941,604 pairs. りんご → リンゴ is a redirect Wikipedia wrote.
- `typo_recovery` — 電荷密変 → 電荷密度, measured 84.8% recovery@5 with
  zero false fires on in-vocabulary words.
- `sense_split` — a surface's registered senses.

The same instrument as everywhere else today: ask the dictionary, and
refuse what it cannot vouch for. 「氷 冷たい」 is not a certified variant
of 「こおりは冷たい」 by any of the three, so it never reaches the store.

### The consequence, stated before measuring

If every admissible rephrasing is one an organ can certify, then **the
engine could have found it without a model**. The model's role shrinks to
proposing candidates the engine then verifies — which is exactly the
「LLMが候補を出し、Veraが落とす」 split this session already argued for on
other grounds.

That is a narrower claim than "the model rescues refusals", and it is the
honest one. Recorded here so the measured gain is read against it.

## Frozen pass lines

- **G1 — the known failure is rejected.** 「氷 冷たい」 as a rephrasing of
  「こおりは冷たい」 must be refused by the gate, and the original
  `UNKNOWN_NO_EVIDENCE` returned unchanged.
- **G2 — the genuine three survive.** リンゴとは (alias), 電荷密度とは
  (typo), 時効とは (kana→kanji) must all still pass.
  **It is possible 時効 fails**: kana→kanji may be certified by no organ,
  since `aliases` holds page redirects and `typo_recovery` works on edit
  distance over the same script. If it fails, that is a finding about
  coverage, not a reason to loosen the gate — and it is named here so the
  outcome cannot be reinterpreted afterwards.
- **G3 — WRONG stays 0** on the frozen 50-item commonsense bank
  (9 correct / 41 typed refusal / 0 wrong).
- **G4 — the certifying organ is named in the output.** An answer that
  arrived through a rephrasing says which organ vouched for it, so a
  reader can weigh it. An uncertified path must not exist.

## Quantities to be measured (not predicted)

1. Of the four probes, how many pass the gate.
2. Which organ certified each.
3. On the commonsense bank: refusals converted, and by which organ.
4. Rephrasings the model would have proposed that no organ certifies.

## Stop conditions

- **G1 fails** → the gate does not gate. Stop.
- **G3 fails** → fabrication is still entering. Stop and do not tune;
  a mechanism that needs tuning to stop inventing will invent.
- **G2 fails on all three** → the organs certify nothing useful and the
  gate has closed the mechanism entirely. Report that rather than
  weakening it — a suspension that never resumes is an honest null.

## Not changed

`suspend.py` keeps its shape: the engine still stops, the host still
fulfils, and nothing the model returns is written to the store. Only the
admission of a resumed query is gated.
