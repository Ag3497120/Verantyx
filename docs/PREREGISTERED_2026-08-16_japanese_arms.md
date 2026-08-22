# Pre-registration — arms for Japanese facts

**Registered 2026-08-16, before any cue is written or measured.**

## What is missing, measured

```
classify_arm("傷害罪は故意犯である")      → None
classify_arm("りんごは果実の一種である")    → None
classify_arm("電気は電荷の移動によって発生する") → None
```

`_CUES` is English only — `because` / `therefore` / `is a` / `for example`.
Every Japanese fact in the store is therefore **untagged**, and the arm
index is never persisted for the published store at all.

The consequence is the one that matters. A facet without an arm is not a
proposition: 「傷害罪 / 故意犯」 is two things side by side, not a claim
that one is a kind of the other. So judgement currently runs over a set of
facets rather than over claims, which is why 「傷害罪とは」 answers
`SEEDED 傷害罪 傷害 故意犯 狭義 204条` and a reader asks what was actually
established.

## What is proposed

A closed Japanese cue table, in the same shape and with the same
discipline as the English one: a cue assigns an arm, and a sentence with
no cue stays untagged. Nothing is inferred, and untagged remains a
first-class state rather than a failure to classify.

## The position rule, decided before any data is seen

Japanese has no word boundaries, so a bare substring match over-fires by
default. 「一種の冗談を言う」 contains 一種 and asserts nothing about a
kind. So a cue counts only when it sits in the **predicate region** — the
tail of the clause — and not merely somewhere in the string.

This is the same repair that finally worked for polarity: subtract what is
known, then look at the position, rather than scanning raw characters.

## Frozen pass lines

- **A1 — decoys stay untagged.** These ten contain a cue string and no
  such relation, and each must return `None`:

  ```
  一種の冗談を言う          規定によっては異なる
  ため息をつく             AとBの原因を調べる
  結果を待つ               支持する人が多い
  例えば話をする            分類の作業を行う
  反対の方向へ進む          一般の利用者
  ```

  **This is the pass line that can actually fail.** A cue table that
  cannot resist these is a table that will tag the corpus wrongly and
  quietly, and the wrong tag is worse than no tag because it makes a
  non-claim look like a claim.

- **A2 — genuine relations fire, with the right arm.** These ten must
  return the arm named:

  ```
  りんごは果実の一種である            kind-
  傷害罪は故意犯である                kind-
  電気は電荷の移動によって発生する      cause+
  地震によって建物が倒れる             cause+
  正当防衛は刑法36条に規定される        support+
  この点は判例に支持されている          support+
  ただし未成年はこの限りでない          support-
  本条は適用されない場合を除く          support-
  哺乳類は一般に胎生である             kind+
  例えばりんごは果物である             kind-
  ```

- **A3 — no fabrication.** Every arm assigned is independently re-checked:
  the cue it was assigned by must be present in the sentence's predicate
  region. An assignment whose cue cannot be found again fails.

- **A4 — untagged is not punished.** A sentence with no cue produces no
  arm and no error. Verified on probes, not assumed.

## Quantities to be measured (not predicted)

1. Share of the store's Japanese lead sentences that receive an arm.
2. Distribution over the six arms.
3. The twenty most frequent cues that fired.
4. Cores that gain at least one claim `(core, arm, facet)`.

## Stop conditions

- **A1 fails** → the position rule is not doing its work. Fix the rule.
  Do **not** add the decoys to an exclusion list: that is the move this
  session refused four times in polarity, and the class is open —
  一種の / ためらう / 結果的に / 例えるなら will keep arriving.
- **A2 fails on more than two** → the cues are too narrow to be worth the
  table; report rather than widen them after seeing which ones missed.
- **A3 fails at all** → stop. An arm that cannot be traced back to its cue
  is exactly the fabricated structure this table exists to avoid.

## Recorded before measuring

Coverage is expected to be low — Japanese definitions often assert a kind
relation with a bare 「である」 and no cue at all, and those must stay
untagged. A low number is the honest outcome here, not a failure: the
alternative is a tagger that guesses, and a guessed arm turns a facet into
a claim that nobody made.

## What this unblocks, and what it does not

Unblocks: judgement over claims rather than over facet sets, a `reason`
field that can say which arm carried which evidence, and composition from
a claim rather than from a token soup.

Does not touch: the ¬ facets (still 0), the store's votes, or any
threshold in the federation. This writes an interpretation layer beside
the facts, exactly as `arm_schema` was built to be — droppable without
touching what it interprets.

---

## Amendment 1 — the で of である is not a case particle

**Registered 2026-08-16, after A1 passed and A2 failed 10/10, and before
the corrected rule is measured.**

A1 passed with zero over-fires. A2 missed every single item, and the cause
is not the cues — it is the predicate region:

```
「りんごは果実の一種である」
  region = text after the LAST case particle
  である contains で, で is in the particle set
  → region = 「ある」, and every cue was cut away
```

The copula である was read as a case particle. That is the same shape as
every other defect found today — a functional element taken for something
it is not — and it is decided by grammar, not by which items missed:
で in である is the continuative of だ, not a case marker.

**The correction is to the region rule, not to the cues.** The cue table
is unchanged; widening it after seeing which items missed is what this
document's stop condition forbids, and it is not what is being done.

**Corrected rule.** The predicate region is the text after the last case
particle that is NOT part of a copula or auxiliary — concretely, a で
immediately followed by あ/は/も (である / では / でも) does not end the
region. Same for に immediately followed by よ in による-shaped forms,
which is a compound-particle head rather than a case marker.

**Pass lines are unchanged.** A1 must still be 0, A2 must now reach 8 of
10 or the cues genuinely are too narrow and the table is not worth having.
A3 and A4 are unchanged.

**Recorded before re-running:** the expectation is that A2 now passes,
because the cues were visible in the intended region all along. Written
down so a pass counts as a confirmation of the diagnosis rather than as a
discovery.
