# Pre-registration — the SUBJECT must be certified, not any shared word

**Registered 2026-08-16, after G1 failed and before the third gate is
written. Third attempt at the same problem.**

## Two failures, one mistake

```
S1   こおりは冷たい → 「氷 冷たい」 → ANSWER core: ブラック
     resume read "stopped refusing" as "answered"

G1   same probe, now with a gate → still ANSWER, certified "identity"
     the shared run was 冷, the predicate — not こおり/氷, the subject
```

Both times the same error: **something matched, therefore it is the same
question.** The first time nothing was compared at all; the second time
the wrong thing was compared.

And the gate that let the fabrication through simultaneously rejected the
genuine rephrasings:

```
りんご → リンゴ    UNCERTIFIED   (no character in common)
じこう → 時効      UNCERTIFIED   (no character in common)
電荷密変 → 電荷密度  typo ✓        (the only one that passed)
```

A rule that admits the wrong case and refuses the right ones is not a
strict rule — it is a rule about the wrong property.

## What is actually being asked

Not "do these strings resemble each other". The question is:

> **Is the subject of the rephrasing the same entity as the subject of the
> original?**

Everything else in the sentence is free to change; that is what a
rephrasing is. So the comparison must be on ONE designated run — the
subject — and identity of any other run must count for nothing.

## The third gate

**Step 1 — name the subject on each side.** The engine already has this:
`ja_chosen_core` picks the topic, and it is the same function the
103,599-claim repair was built on, so it is the function that decides what
a sentence is ABOUT. Whatever it returns is the subject; nothing else in
the string is looked at.

**Step 2 — certify only that pair.** Same organs as before, applied to
subjects rather than to whole queries: identity, alias, typo, sense.

**Step 3 — reading certification is not enough.** りんご→リンゴ and
じこう→時効 are the same word in a different script, and no organ holds
them: `aliases` are page redirects, `typo_recovery` is edit distance in
one script. Katakana↔hiragana is a mechanical fold; kana→kanji is not, and
it needs a reading. `unidic` supplies `kanaBase`, and it is the same
instrument used for the case frames and the polarity gate — so:

> two subjects are the same when their readings are the same and at least
> one of them tags as a single token.

## Frozen pass lines

- **H1 — the fabrication is rejected.** 「氷 冷たい」 must NOT certify
  against 「こおりは冷たい」. **This is the line that has failed twice and
  it decides the whole mechanism.** If a third gate still admits it, this
  approach is abandoned rather than adjusted.
- **H2 — the three genuine rephrasings certify**, each naming its organ:
  りんご→リンゴ, じこう→時効, 電荷密変→電荷密度.
- **H3 — no shared predicate certifies anything.** 「犬は冷たい」 against
  「氷 冷たい」 must be rejected: 冷 is shared and the subjects are not.
- **H4 — WRONG stays 0** on the frozen 50-item commonsense bank.

## Quantities to be measured (not predicted)

1. Which organ certified each of the three.
2. Subjects that certify by reading alone (the kana↔kanji class).
3. Probes rejected, with the subject pair that failed.

## Stop conditions

- **H1 fails** → three gates have failed on one probe. Stop and remove
  `suspend.py` from the tree rather than attempt a fourth. A mechanism
  that needs three corrections to stop admitting a known fabrication is
  not close to correct; it is being fitted to one example.
- **H3 fails** → the gate is still reading predicates as subjects.
- **H4 fails** → fabrication reaches the bank. Stop.

## Recorded before measuring

If H2 passes and H1 holds, the gain remains what the previous
pre-registration already narrowed it to: the model proposes, the engine
certifies, and every admitted rephrasing is one the engine could in
principle have found alone. The value is in the proposing, not in the
answering.

If H1 fails again, the honest conclusion is that "is this the same
question" cannot be decided by this engine's organs, and the inversion
must ask a PERSON to confirm the rephrasing — which `ask_back` already
does, and which costs a turn instead of costing correctness.

---

## Amendment 1 — `ja_chosen_core` does not name subjects in questions

**Registered 2026-08-16, before the gate is run.**

Step 1 of this document claims the engine already names the subject via
`ja_chosen_core`. Measured before running anything, that claim is false
for the class this gate is about:

```
ja_chosen_core("こおりは冷たい")  → 冷      the predicate, not the topic
ja_chosen_core("氷 冷たい")       → 氷      correct by accident of order
ja_chosen_core("りんごとは")      → None
ja_chosen_core("じこうとは")      → None
```

It was built for declaratives (`Xは…である`) and is what the
103,599-claim repair hardened. It has no reading for a question.

**Correction, decided by grammar and not by which probes missed.**
Japanese is topic-first: the subject of a question is its FIRST content
run. `ja_content_runs` supplies them, and the first one is taken.

That rule is stated before the numbers because it is a fact about the
language, not a fit — the same standing as the で-of-である correction
earlier today, which was also registered before its re-run.

**Pass lines are unchanged.** H1 still decides the mechanism, and a third
failure still means `suspend.py` leaves the tree rather than getting a
fourth attempt.
