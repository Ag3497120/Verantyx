# Pre-registration — Gate B′, decided by what precedes the verb

**Registered 2026-08-16, after the second attempt hit its stop condition
and before any measurement of the third.**

## Why the second attempt stopped

Gate B blocked any lemma unidic tags 非自立可能. Measured: 370 → 157
facets, P5 PASS, but P6 moved 15 bank items including

```
彼は来ない。    ¬来る  → 証言なし
我は行かぬ。    ¬行く  → 証言なし
今はできません。 ¬できる → 証言なし
```

来る / 行く / できる are content verbs in those sentences. The stop
condition fired as written.

The diagnosis is that **非自立可能 is a property of the lexeme, not of the
usage** — the dictionary is saying "this word CAN also serve as an
auxiliary" because 〜てくる and 〜ていく exist. Re-tagging the same word
inside its sentence does not change that label, so "ask the tagger in
context" is not by itself the repair.

## Gate B′ — the discriminator is the preceding token

What actually separates the two uses is what comes before:

```
開いて + いない     preceded by a て-form  → auxiliary  → no testimony
彼は   + 来ない     preceded by 助詞       → content    → testimony
作業が + できない    preceded by 助詞       → content    → testimony
問題   + ない       preceded by 名詞       → content    → testimony
```

So Gate B′ has three parts, and drops the 非自立可能 test entirely:

- **B′1** — `pos1` of the lemma must be 動詞 or 形容詞. 助動詞 / 接続詞 /
  名詞 / 助詞 / 副詞 produce no testimony. (This part of Gate B worked:
  it removed ます, である, ふく.)
- **B′2** — the lemma must tag as exactly one token standalone. (This
  part also worked: it removed 50 untaggable fragments such as りする,
  くむ, わする.)
- **B′3 (new)** — in the sentence, the negated verb must NOT be
  immediately preceded by a て-form or the 助詞 「て」/「で」 in its
  conjunctive use. A verb in that position is an auxiliary carrying the
  aspect of the verb before it, and the negation belongs to that earlier
  verb, not to this one.

No exclusion list. No frequency threshold. B′3 is a grammatical
adjacency the tagger can answer.

## Anticipated bank movements, named in advance

- **「問題ない。」 → `¬ある` is expected to SURVIVE.** ある is preceded by
  the noun 問題, not by a て-form. The conflict that the second
  pre-registration surfaced is therefore expected to resolve in favour of
  W1a's frozen bank, without either bank being weakened.
- **「まだ開いていない。」 → `¬いる` is expected to STOP.** いる is
  preceded by the て-form 開いて. This is the exact case recorded as a
  known limit in the first pre-registration — B′3 is expected to close
  it as a side effect rather than by special-casing it.

Both are predictions about which items move, not about how many facets
survive; the counts remain unpredicted.

## Frozen pass lines

- **P1** — zero fabricated lemmas (carried over).
- **P5′** — zero stored lemmas whose `pos1` is 助動詞 / 接続詞 / 名詞 /
  助詞 / 副詞, and zero lemmas that do not tag as a single token.
- **P7 (new)** — of the 15 items Gate B changed, the content-verb ones
  (来る / 行く / できる family) must be restored. If any content verb is
  still cut, B′ has the same defect as B and must stop.
- **P6′** — every remaining bank change is listed by id and handed over.
  Any movement outside the two anticipated cases above stops the run.
- **P3** — the 50-item commonsense bank still returns WRONG = 0.

## Quantities to be measured (not predicted)

1. Facets surviving on the same 10,000 slice, before / after B′.
2. The 20 most frequent surviving lemmas.
3. Cores gaining at least one mark.
4. Bank items changed, by id.

## Stop conditions

- P7 fails → the discriminator is still wrong; stop, do not add
  exceptions for 来る/行く.
- P6′ shows a movement outside the two anticipated cases → stop and
  report.
- Surviving facets fall to zero → report, do not loosen.

## Standing limit, restated

`ちる` still passes every gate (動詞,一般, tags as one token, not after a
て-form). A fragment that happens to spell a real verb cannot be
separated by grammar. Named again so it is not patched with a list.
