# Metamorphic testing — how the parser finds bugs in its own reading

Vera reads government documents and reports when two sources contradict each
other about the same thing. It has bugs. Every new document format produces a
new one — five genres read so far, three defects each, and the rate is not
falling. That is not a flaw in the engine; a reading rule is a fact about a
language and a layout, and there are more layouts than anyone can enumerate.

So the release has to assume defects keep arriving. The question this document
answers is how to **find** them without a person reading the output, because
"is this reading correct?" needs somebody who knows what the document means.

## The question you can actually ask

There is a different question that needs no world knowledge:

```
not:  is this reading correct?
but:  do two readings of the SAME CONTENT agree?
```

If they disagree, one of them is wrong. That is a proof, not a heuristic, and
it costs no human, no network and no model.

This is metamorphic testing. The usual form gives you "these two runs
disagree" and stops. What makes it useful here is finding a transform where
you can argue the **direction** as well.

## The transform, and why direction is decidable

Japanese does not put spaces between words. So a space between two CJK
characters in running prose was put there by the PDF extractor, not by the
author. Which gives:

> **Layout cannot add information.**

If closing up an extractor's space makes a claim disappear, the claim was
manufactured by the whitespace. Not "suspicious" — spurious. No arrangement of
spaces is evidence that a town has water.

Concretely, from a ministry PDF:

```
「全 12 戸が断水しています」   → core: 全      ("all" — a fragment)
「全12戸が断水しています」     → core: 全12戸  ("all 12 households")
```

Nobody had to read either one to know that one of them is wrong.

`verantyx/metamorphic.py` implements three perturbations. Each carries the
argument for why it preserves meaning, because a transform whose meaning-
preservation cannot be argued produces disagreements that prove nothing:

| perturbation | argument |
|---|---|
| `counter_split` | A numeral and its counter are one word — 12戸, 15炉, 8金融機関. A space between them is column alignment, never grammar. |
| `layout_space` | Any single space between two CJK characters in prose. Table rows are excluded, because there the space is a column separator. |
| `digit_width` | ７ and 7 are the same digit. |

Only the **manufactured** direction is filed as proven: a claim present in the
noisy reading and absent in the clean one. The reverse is filed as suspected,
because a document whose layout carries structure can legitimately read
differently, and flattening a table is not a fix.

## What it found

Across five corpora of real published documents:

```
13  proven defects on two ministry PDF series
 0  on statutes, municipal HTML, operator press releases
```

Not typos. A claim about water restoration filed under 自治体 ("municipality",
the generic word) instead of the actual municipality's name; a service
disruption filed under 路線 ("route") instead of the line name. Anyone asking
about their own town or their own line got nothing back.

## The repair is mechanical, because the answer key is internal

Once a defect is proven, a fix can be proposed and **measured**. The gate in
`verantyx/self_evolve.py`:

- the planted test suite still passes (it has its own answer key)
- no confirmed detection across five corpora is lost
- coverage does not fall
- the count of proven defects strictly falls

Two candidates, and both outcomes happened — which is why both code paths
exist:

```
counter_split   ACCEPTED
  proven defects 13 → 12, coverage 73.39% → 73.39%,
  the same 9 confirmed detections, the same 18,460 sentences placed

layout_space    REJECTED
  removes every proven defect, and costs 79 sentences their core —
  of which only 8 were the spurious claims
```

The rejection is the more useful record. Without a ledger the same losing
candidate is re-derived on every run forever, because the ministry PDFs propose
it every time. `rejected_before()` reads the ledger and skips it.

Accepted repairs are written to the operator's own overlay, never to the
shipped grammar. `ja_grammar.json` ships with no normalizers and no
suppressions; an installation evolves from the documents **it** was given,
which is the only honest place for evidence that came from those documents.

## A second oracle: the output versus the engine's own rules

`polarity` carries guards that mean "if this pattern follows the term, the term
asserts nothing" — `_JA_UNTIL` (〜まで), `_JA_DEEMING` (〜と認める),
`_JA_CAUSE_MARK` (〜のため, 〜による).

So a placed claim whose tail one of those guards matches is an **internal
contradiction**. Both the output and the rules live in the same process, so no
world knowledge enters. `rule_conflicts()` found 7:

```
「災害復旧のため派遣された職員」  →  復旧 placed on 災害派遣手当
                                    ("disaster dispatch allowance")
```

A dispatch allowance is not a restored water main.

This is the class this project hit four separate times by hand — enumeration,
deeming, until, and now のため — always the same anatomy: a guard applied on
the prose path and skipped on the tabular path, found by a human every time.
So the fix was structural rather than another instance patch. Suppressions are
now consulted at the placement choke point, the one line every pole passes
through, which means the hole cannot reopen as a path-skip.

## Two mistakes worth keeping in the record

**A core is TEXT, so a transform renames it.** The naive set difference
reported the same claim twice — once manufactured, once destroyed. The first
run said 18 and 18 on one corpus: 18 renames and no defect at all. Comparing
modulo the transform is what makes a difference mean the reading changed rather
than the spelling. The same bug later rejected `counter_split` for "proving 9
new divergences" that were 11店舗, 12戸 and 13路線 — the very fragments it had
just attached their numerals to.

**Perturbing document text is not what the reading path does.** The path
normalizes only where the format was laid out, because a PDF's stray space and
an HTML table's cell separator are the same character and only the loader knows
which it has. Perturbing text directly reported four proven defects on
municipal HTML — and collapsing those spaces turned 「日時 開催場所 担当部署」,
three table headers, into one word. Nothing it showed was proven; the loop was
measuring a repair it would never make. `probe_paths()` toggles the real switch
and reloads, so probe and repair are one code path by construction.

## Where this stops

This does not make the parser self-improving in any general sense. It repairs
what the parser's own **reader** broke. It cannot tell you what a word it has
never seen MEANS — no transformation of a document reveals that — so new
vocabulary arrives as a queue with an approve button, and nothing in
`vocab_growth.py` or `proposal_verify.py` can write an overlay. The eval
asserts the absence.

The honest summary: metamorphic relations give an answer key for the class of
defect where the input was misread, and nothing at all for the class where the
parser is simply ignorant.

## Running it

```bash
vera self-audit  ./documents          # structural signals, no repair
vera self-evolve ./documents          # prove, repair, measure, keep
vera self-evolve ./documents --write  # and persist accepted repairs
```

`self-evolve` prints what it proposed, what it accepted, what it rejected and
why, and files anything still proven-but-unrepaired as a CRITICAL gap for a
person — with `observed_transition="proven"` rather than `"suspected"`, because
unlike a structural signal these are not guesses.

## Where the numbers come from

Every figure above was measured on published Japanese government disaster
documents and is recorded in the commit that introduced it:

| figure | commit |
|---|---|
| 13 proven defects, counter_split accepted, layout_space rejected | `Prove a defect from inside, repair it, keep the repair` |
| 7 guard conflicts, のため on the statutes | `Second internal oracle: the output must agree with the engine's own rules` |
| 79 sentences lost, 18,460 placed, 73.39% coverage | same two commits |

The corpora are public documents and are **not redistributed here** — they are
third-party publications, and disaster bulletins get revised, so a frozen copy
would quietly diverge from what the ministry is actually serving.

The original corpus was lost: it lived in a session temp directory that was
later cleaned, and the only thing that survived was the figures in the commit
messages. That is a thin thread to hang a number on, so
[../corpora/](../corpora/README.md) now holds manifests instead — source URL
and SHA-256 per file, with a fetch/verify tool:

```bash
python3 -m verantyx.corpus_fetch --manifest corpora/x.json --out ./corpora/x
python3 -m verantyx.corpus_fetch --manifest corpora/x.json --out ./corpora/x --verify
```

`--verify` exits non-zero and names every file whose checksum moved. A
mismatch is not automatically an error — a ministry issuing a correction looks
exactly like this — but it must never pass silently, because a changed corpus
invalidates every number measured on it.

To reproduce without a manifest, point `vera self-evolve` at any series of
numbered ministry reports. The defects it finds will be that corpus's, not
these.

## See also

- [DESIGN.md](DESIGN.md) — why the store is shaped like this
- `verantyx/metamorphic.py` — the probes and the rule-conflict oracle
- `verantyx/self_evolve.py` — the gate and the ledger
- `verantyx/proposal_verify.py` — three states for a vocabulary proposal
