# Pre-registration — wiring observed negation into ingest

**Registered 2026-08-16, before any measurement of the change.**

## What is being proposed

`observe_negation` (W1a, committed `e0c35b0`) is fully implemented and
scores 97/97 on its own banks. It has never been called by ingest.
Measured on the published store today:

```
極性が取り込みから呼ばれている箇所   0
整合検査が呼ばれている箇所           0
vera.db の ¬ を含む面                0 件
```

So every downstream organ that depends on a written negation is running
dry. `connective_render` reported 「しかし」 firing **0 times** across the
30-pair bank and called it an honest zero; it was honest, but the cause
was an empty tank rather than an absence of oppositions in the corpus.

The proposal is that `ja_ingest_sentence` additionally write `¬<lemma>`
facets for each `ObservedNegation` the reader returns.

## Why this needs pre-registration

A ¬ facet is a facet. It joins the census, adds mass to a core, and
therefore can move quorum counts and demote or promote verdicts. This is
not a sidecar and not hand-off only — it touches the thing that votes.
The project's standing rule applies: adding to the merge requires its own
pre-registration, and thresholds are frozen before results are seen.

## Environment gate (stated before measuring, because it is a trap)

The existence gate `_lemma_is_real` asks unidic whether a folded lemma is
a real 動詞/形容詞. Without fugashi the raw fallback knows only
ある/いる/する/できる/来る/である plus `_NAI_LEX`. Measured today:

```
python3     水が流れない。 → positive, observed ()          ← silent total loss
python3.11  水が流れない。 → negative, observed (¬流れる)
```

A wiring that runs under an interpreter without fugashi does nothing and
looks exactly like a wiring that had no effect. So:

**Gate G0** — the measurement run must assert `fugashi` is importable and
record the interpreter. A run without it is void, not a null result.

## Frozen pass lines

All four must hold. Failing any one means the wiring is NOT enabled on
the main path; the code may still land behind an off-by-default flag.

- **P1 — no fabrication.** Every `¬X` facet written has `X` confirmed by
  the existence gate. Zero facets whose lemma unidic does not know as a
  standalone 動詞/形容詞. (`大人げる` must never appear.)
- **P2 — purely additive.** No existing facet is removed, renamed, or
  re-cored. The diff between before/after stores contains additions only.
- **P3 — the federation still does not lie.** Re-run the frozen 50-item
  commonsense bank (`tools/commonsense_bank_2026-08-14.json`). WRONG must
  stay **0**. The post-repair baseline is 9 correct / 41 typed refusal /
  0 wrong; correct may move in either direction, WRONG may not rise.
- **P4 — 「しかし」 is licensed or absent.** If the connective fires at
  all, 100% of its uses carry the `observed-negation` license with a
  named ¬/assert pair. A single unlicensed 「しかし」 fails the wiring.

## Quantities to be measured (values deliberately not predicted)

Fixing the pass lines above without predicting these, because a predicted
rate that is then "confirmed" is not a measurement:

1. ¬ facet生成率 on a 10,000-sentence slice of the jawiki leads.
2. The 20 most frequent ¬ lemmas produced.
3. Count of cores that gain at least one ¬ facet.
4. 「しかし」 firing count on the existing 30-pair diff bank, after.

## Stop conditions

- P1 fails → the existence gate is not doing its job; stop and repair the
  gate, do not weaken P1.
- P2 fails → the write path is mutating rather than adding; stop.
- P3 fails → the wiring has re-introduced false testimony; revert and
  ledger every ¬ facet involved, the same way the 103,599-claim repair
  was ledgered.
- G0 unmet → the run is void. Do not report "no effect".

## Known limits recorded in advance

Two behaviours are already observed and are NOT counted as failures here,
because they are properties of the reader rather than of the wiring:

- 「ファイルを消さないで。」 folds to `verdict=positive` while carrying
  `observed=(¬消す,)`. The imperative negation is not sentence-final, so
  a consumer on the instruction side must read `observed`, never
  `verdict`. Recorded so the instruction wiring does not later read the
  wrong field and call it a bug in polarity.
- 「まだ開いていない。」 yields `¬いる`, not `¬開く` — the ない attaches
  to the auxiliary. Structurally correct, semantically not what a reader
  wants. Left as a named limit rather than special-cased, because the
  special case is exactly the kind of open-class rule this project has
  twice measured itself unable to close.
