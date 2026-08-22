"""Typed negation (W1a): preregistered 60-sentence bank.

Protocol (SPEC_2026-08-14_eight_gaps W1a). No existing 54.8% sentence
bank was found: that figure is jgen leave-one-out on 31 antonym terms
(`jgen_lexicon.py` / README), a different task. This bank
(tools/polarity_bank_2026-08-14.json) was written before the first
`observe_negation` call on it. 30 affirmative / 30 negated; double
negation sits in the affirmative half (parity fold); prefix negation
sits in the negated half. Four UNDECIDED probes are scored separately
so the 30/30 split stays intact.

Gold is the bank. The detector is deterministic (raw text + fugashi
when importable). Prefix hits use a lattice built from the bank's
preregistered `lattice_words`. Inferring negation from absence is
not a code path.

## Measured — preregistered 60, closed bank, 2026-08-14

    bank                             tools/polarity_bank_2026-08-14.json
    n                                60   (30 affirmative / 30 negated)
    prior 54.8% sentence bank        none (that figure is jgen leave-one-out
                                     on 31 antonym terms, a different task)
    fork POLARITY_TYPED_NEGATION     pass
    extract default unmarked         pass
    extract fold marks ¬流れる        pass

    overall accuracy                 1.0000    60 / 60
    accuracy on negated              1.0000    30 / 30
    accuracy on affirmative          1.0000    30 / 30
    soundness failures               0
        (affirmative flagged negative — the bad failure)
    UNDECIDED on the 60              0
    UNDECIDED probes (4, extra)      4 / 4
    vs 54.8% baseline                +0.4520

    per-category
        plain        14 / 14
        lookalike    10 / 10   死ぬ / まず / 少ない / 非常口 …
        double        6 /  6   〜なくない folds to positive
        ending       12 / 12   ない / ぬ / ず / ません
        copula        8 /  8   ではない / でない / ではありません
        prefix       10 / 10   非/不/未/無 through the lattice gate

    raw-text path alone              60 / 60
    fugashi+raw merged               60 / 60

Closed bank, not a corpus sweep. Lookalikes (死ぬ, まず, 少ない,
非常口, 未来) are the soundness load: none were flagged negative.
Prefix hits require a lattice word as the remainder; 非常口 and 未来
abstain at the split. The 54.8% comparison is against the published
antonym-pole coin-flip, not a prior score on these sentences.

## Measured — amendment 2026-08-14 (lexicalized / noun+ない / scope)

    original 60 regression           60 / 60   no change
    UNDECIDED probes                 4 / 4
    fork POLARITY_TYPED_NEGATION     pass (now includes the three fixes)

    amendment n                      20
    amendment correct                20 / 20
    fabricated ObservedNegation
        on lexicalized-ない          0 / 10    pass line
    noun+ない lemma ある             3 / 3     問題/異常/関係, never lemma ない
    embedded clause                  3 / 3     verdict positive, observed kept
    regression (流れない/ではない/
        不可能/なくない)              4 / 4

## Measured — amendment 2 2026-08-14 (existence gate / くない / だろう)

    original 60 regression           60 / 60   pass
    amendment 1                      20 / 20   pass
    fabricated ObservedNegation
        on open-class lexicalized    0 / 6     pass
        on amendment-1 lexical       0 / 10
    amendment 2                      17 / 17
        open_lexical                  6 / 6    大人げない/屈託ない/…
        kunai                         5 / 5    ¬危ない/¬少ない/¬高い/¬美味しい/¬つまらない
        darou                         2 / 2    だろう/でしょう
        regression                    4 / 4    流れない/問題ない/知らない人が来た/不可能
    fork POLARITY_TYPED_NEGATION     pass
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.lattice import build
from verantyx.polarity import (
    POLARITY_NEGATIVE,
    POLARITY_POSITIVE,
    POLARITY_UNDECIDED,
    observe_negation,
    regression,
)
from verantyx.predicate_profile import extract, extract_with_polarity

BANK = Path(__file__).resolve().parent / "polarity_bank_2026-08-14.json"
BASELINE = 0.548


def load_bank():
    return json.loads(BANK.read_text(encoding="utf-8"))


def score_item(item, lat, *, tokens="auto"):
    kwargs = {"lattice": lat}
    if tokens == "raw":
        kwargs["tokens"] = []
    reading = observe_negation(item["text"], **kwargs)
    gold = item["gold"]
    if gold == "POLARITY_UNDECIDED":
        ok = reading.verdict == POLARITY_UNDECIDED
    else:
        ok = reading.verdict == gold
    return reading, ok


def main() -> Dict:
    bank = load_bank()
    lat = build(bank["lattice_words"])
    fork = regression()

    rows = []
    for item in bank["sentences"]:
        reading, ok = score_item(item, lat)
        rows.append((item, reading, ok))

    n = len(rows)
    correct = sum(1 for _i, _r, ok in rows if ok)
    aff = [(i, r, ok) for i, r, ok in rows if i["gold"] == "positive"]
    neg = [(i, r, ok) for i, r, ok in rows if i["gold"] == "negative"]
    aff_ok = sum(1 for _i, _r, ok in aff if ok)
    neg_ok = sum(1 for _i, _r, ok in neg if ok)
    # Soundness: calling an affirmative sentence negative.
    soundness_fail = [
        i for i, r, _ok in aff if r.verdict == POLARITY_NEGATIVE
    ]
    undecided_on_60 = sum(
        1 for _i, r, _ok in rows if r.verdict == POLARITY_UNDECIDED
    )

    by_cat = Counter()
    by_cat_ok = Counter()
    for item, _r, ok in rows:
        cat = item["category"]
        by_cat[cat] += 1
        if ok:
            by_cat_ok[cat] += 1

    probes = []
    for item in bank.get("undecided_probes") or []:
        reading, ok = score_item(item, lat)
        probes.append((item, reading, ok))
    probe_ok = sum(1 for _i, _r, ok in probes if ok)
    probe_undec = sum(
        1 for _i, r, _ok in probes if r.verdict == POLARITY_UNDECIDED
    )

    # Default extract must not grow ¬ keys.
    pages = [("水", "水が流れる。"), ("川", "水が流れない。")]
    plain = extract(pages)
    polar = extract_with_polarity(pages, lattice=lat)
    default_clean = all(
        not any(str(k).startswith("¬") for k in rec["predicates"])
        for rec in plain.values()
    )
    polar_has_mark = any(
        str(k).startswith("¬") for k in polar["川"]["predicates"]
    )

    raw_correct = 0
    for item in bank["sentences"]:
        _r, ok = score_item(item, lat, tokens="raw")
        raw_correct += int(ok)

    acc = correct / n if n else 0.0
    acc_neg = neg_ok / len(neg) if neg else 0.0
    acc_aff = aff_ok / len(aff) if aff else 0.0

    amendment = bank.get("registered_amendment") or {}
    amend_rows = []
    fabrications = []
    for item in amendment.get("items") or []:
        reading, ok = score_item(item, lat)
        extra_ok = True
        if item.get("expect_observed") == "empty":
            extra_ok = len(reading.observed) == 0
            if reading.observed:
                fabrications.append({
                    "text": item["text"],
                    "lemmas": [o.lemma for o in reading.observed],
                })
        elif item.get("expect_observed") == "nonempty":
            extra_ok = len(reading.observed) > 0
        if item.get("expect_lemma"):
            extra_ok = extra_ok and any(
                o.lemma == item["expect_lemma"] for o in reading.observed
            ) and not any(o.lemma == "ない" for o in reading.observed)
        if item.get("expect_count") is not None:
            extra_ok = extra_ok and len(reading.observed) == item["expect_count"]
        amend_rows.append((item, reading, ok and extra_ok))
    amend_n = len(amend_rows)
    amend_ok = sum(1 for _i, _r, ok in amend_rows if ok)
    by_amend = Counter()
    by_amend_ok = Counter()
    for item, _r, ok in amend_rows:
        by_amend[item["category"]] += 1
        if ok:
            by_amend_ok[item["category"]] += 1

    out = {
        "bank": str(BANK),
        "n": n,
        "affirmative": len(aff),
        "negated": len(neg),
        "correct": correct,
        "accuracy": round(acc, 4),
        "accuracy_affirmative": round(acc_aff, 4),
        "accuracy_negated": round(acc_neg, 4),
        "soundness_failures": len(soundness_fail),
        "soundness_examples": [s["text"] for s in soundness_fail[:5]],
        "undecided_on_60": undecided_on_60,
        "undecided_probes": len(probes),
        "undecided_probes_hit": probe_undec,
        "undecided_probes_ok": probe_ok,
        "baseline_54_8": BASELINE,
        "vs_baseline": round(acc - BASELINE, 4),
        "per_category": {
            cat: {
                "n": by_cat[cat],
                "correct": by_cat_ok[cat],
                "accuracy": round(by_cat_ok[cat] / by_cat[cat], 4),
            }
            for cat in ("plain", "lookalike", "double", "ending",
                        "copula", "prefix")
            if cat in by_cat
        },
        "raw_only_correct": raw_correct,
        "raw_only_accuracy": round(raw_correct / n, 4) if n else 0.0,
        "fork": fork,
        "extract_default_unmarked": default_clean,
        "extract_fold_marks": polar_has_mark,
        "original_60_regression": correct == n,
        "amendment_n": amend_n,
        "amendment_correct": amend_ok,
        "amendment_accuracy": round(amend_ok / amend_n, 4) if amend_n else 0.0,
        "fabricated_on_lexical": len(fabrications),
        "fabrications": fabrications,
        "amendment_per_category": {
            cat: {
                "n": by_amend[cat],
                "correct": by_amend_ok[cat],
            }
            for cat in ("lexical_nai", "noun_nai", "embedded", "regression")
            if cat in by_amend
        },
    }

    amend2 = bank.get("registered_amendment_2") or {}
    amend2_rows = []
    fabrications2 = []
    for item in amend2.get("items") or []:
        reading, ok = score_item(item, lat)
        extra_ok = True
        if item.get("expect_observed") == "empty":
            extra_ok = len(reading.observed) == 0
            if reading.observed:
                fabrications2.append({
                    "text": item["text"],
                    "lemmas": [o.lemma for o in reading.observed],
                })
        elif item.get("expect_observed") == "nonempty":
            extra_ok = len(reading.observed) > 0
        if item.get("expect_lemma"):
            extra_ok = extra_ok and any(
                o.lemma == item["expect_lemma"] for o in reading.observed
            ) and not any(o.lemma == "ない" for o in reading.observed)
        if item.get("expect_count") is not None:
            extra_ok = extra_ok and len(reading.observed) == item["expect_count"]
        amend2_rows.append((item, reading, ok and extra_ok))
    amend2_n = len(amend2_rows)
    amend2_ok = sum(1 for _i, _r, ok in amend2_rows if ok)
    by_amend2 = Counter()
    by_amend2_ok = Counter()
    for item, _r, ok in amend2_rows:
        by_amend2[item["category"]] += 1
        if ok:
            by_amend2_ok[item["category"]] += 1

    out["amendment2_n"] = amend2_n
    out["amendment2_correct"] = amend2_ok
    out["amendment2_accuracy"] = (
        round(amend2_ok / amend2_n, 4) if amend2_n else 0.0)
    out["fabricated_on_open_class"] = len(fabrications2)
    out["fabrications2"] = fabrications2
    out["amendment2_per_category"] = {
        cat: {"n": by_amend2[cat], "correct": by_amend2_ok[cat]}
        for cat in ("open_lexical", "kunai", "darou", "regression")
        if cat in by_amend2
    }
    out["pass_original_60"] = correct == n
    out["pass_amendment1"] = amend_ok == amend_n
    out["pass_fabrication"] = len(fabrications) == 0 and len(fabrications2) == 0

    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)

    print("\n--- misses ---", flush=True)
    for item, reading, ok in rows:
        if ok:
            continue
        print("%s gold=%s got=%s cat=%s obs=%s"
              % (item["text"], item["gold"], reading.verdict,
                 item["category"],
                 [(o.kind, o.surface, o.lemma) for o in reading.observed]),
              flush=True)
    for item, reading, ok in probes:
        print("probe %s gold=%s got=%s ok=%s"
              % (item["text"], item["gold"], reading.verdict, ok),
              flush=True)
    print("\n--- amendment ---", flush=True)
    for item, reading, ok in amend_rows:
        mark = "ok" if ok else "FAIL"
        print("%s %s gold=%s got=%s obs=%s"
              % (mark, item["text"], item["gold"], reading.verdict,
                 [(o.kind, o.surface, o.lemma, o.context)
                  for o in reading.observed]),
              flush=True)
    print("\n--- amendment 2 ---", flush=True)
    for item, reading, ok in amend2_rows:
        mark = "ok" if ok else "FAIL"
        print("%s %s gold=%s got=%s obs=%s"
              % (mark, item["text"], item["gold"], reading.verdict,
                 [(o.kind, o.surface, o.lemma, o.context)
                  for o in reading.observed]),
              flush=True)
    return out


if __name__ == "__main__":
    main()
