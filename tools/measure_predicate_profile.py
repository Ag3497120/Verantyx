"""Held-out prediction: does a subject's kin-family profile recover its predicates?

Protocol (SPEC_2026-08-14_meaning_layers 納品1). Subjects with ≥3
predicates; 20% of (subject, predicate) pairs held out (seed 20260814).
The predictor never reads the subject's own remaining profile — only the
mean of its lattice-kin family, built on the remainder. Baseline is the
global-frequency ranking (no type). Ties at a cutoff abstain; a subject
with no kin, or a family with no remaining mass, abstains with a type.

## Measured — jawiki leads, heuristic extractor, seed 20260814

    subjects                         1,419,406
    subjects with ≥3 predicates      547,735   coverage 0.3859
    (subject, predicate) pairs       2,704,120  (eligible) / 3,414,003 (all)
    held-out                         540,824
    lattice                          527,175 words, 787,333 slots

    kin family average
        hit@5    0.2052     7,328 / 35,716 answered
        hit@10   0.2155     3,162 / 14,674 answered
        abstain  NO_KIN 371,585   TIE 165,508   INSUFFICIENT_PROFILE 77
    global-frequency baseline (all held-out; never abstains)
        hit@5    0.1621    87,678 / 540,824
        hit@10   0.1941   104,964 / 540,824
    same-pool baseline (only the pairs kin answered)
        hit@5    0.1357    on 35,716
        hit@10   0.1620    on 14,674

Kin beats the untyped baseline both globally and on the same pool
(+51% relative at hit@5 on the pairs it will answer). The win is real
and small, and most of the mass is silence: 371,585 held-out pairs
have no lattice kin (titles outside length 2–5, or no shared-unit
family), and another 165,508 hit a tied cutoff. The profile carries
type structure where kin can be drawn; it does not cover the long
tail of titles the lattice cannot split.

## Measured — jawiki leads, fugashi extractor, seed 20260814

    subjects                         1,419,406
    subjects with ≥3 predicates      340,486   coverage 0.2399
    (subject, predicate) pairs       1,500,191  (eligible) / 2,248,356 (all)
    held-out                         300,038
    lattice                          527,175 words, 787,333 slots

    kin family average
        hit@5    0.3155     7,396 / 23,440 answered
        hit@10   0.3297     3,810 / 11,556 answered
        abstain  NO_KIN 196,749   TIE 99,774   INSUFFICIENT_PROFILE 126
    global-frequency baseline (all held-out; never abstains)
        hit@5    0.2667    80,022 / 300,038
        hit@10   0.3270    98,100 / 300,038
    same-pool baseline (only the pairs kin answered)
        hit@5    0.2430    on 23,440
        hit@10   0.3113    on 11,556

Kin still beats the same-pool baseline (+30% relative at hit@5).
Absolute hit@5 rose against the heuristic run (0.2052 → 0.3155);
coverage fell (0.3859 → 0.2399) and the answered pool shrank
(35,716 → 23,440). The global baseline also rose (0.1621 → 0.2667)
— cleaner lemmas concentrate mass on frequent predicates. Silence
is still most of the mass: 196,749 NO_KIN, 99,774 TIE.
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.lattice import build, kin
from verantyx.predicate_profile import OUT, load

SEED = 20260814
HOLD = 0.20
MIN_PREDS = 3


def unique_topk(scores, k):
    """Top-k by score. A tie that straddles the cutoff abstains (TIE)."""
    if not scores:
        return None, "INSUFFICIENT_PROFILE"
    items = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(items) <= k:
        return [p for p, _n in items], None
    if items[k - 1][1] == items[k][1]:
        return None, "TIE"
    return [p for p, _n in items[:k]], None


def kin_average(lat, remain, subject):
    """Mean remaining profile of ``subject``'s kin. Typed silence on failure."""
    families = kin(lat, subject)
    if not families:
        return None, "NO_KIN"
    members = []
    seen = set()
    for fam in families.values():
        for w in fam:
            if w in seen:
                continue
            seen.add(w)
            members.append(w)
    weights = {}
    used = 0
    for w in members:
        preds = remain.get(w) or {}
        if not preds:
            continue
        used += 1
        for p, n in preds.items():
            weights[p] = weights.get(p, 0) + n
    if used == 0 or not weights:
        return None, "INSUFFICIENT_PROFILE"
    return {p: n / used for p, n in weights.items()}, None


def score_hits(held, predict):
    """predict(subject) -> (scores_or_None, abstain_type).

    Rankings are computed once per subject (or once globally when the
    predictor is constant). Re-sorting a large score table per pair is
    what made the first draft hang on the baseline.
    """
    hits5 = hits10 = answered5 = answered10 = 0
    abstain = Counter()
    pred_cache = {}
    rank_cache = {}
    answered_pairs5 = []
    answered_pairs10 = []
    for subj, pred in held:
        if subj not in pred_cache:
            pred_cache[subj] = predict(subj)
        scores, why = pred_cache[subj]
        if why:
            abstain[why] += 1
            continue
        key = id(scores)
        if key not in rank_cache:
            rank_cache[key] = (unique_topk(scores, 5), unique_topk(scores, 10))
        (top5, w5), (top10, w10) = rank_cache[key]
        if w5:
            abstain[w5] += 1
        else:
            answered5 += 1
            answered_pairs5.append((subj, pred))
            if pred in top5:
                hits5 += 1
        if w10:
            if w5 != w10:
                abstain[w10] += 1
        else:
            answered10 += 1
            answered_pairs10.append((subj, pred))
            if pred in top10:
                hits10 += 1
    return {
        "hit@5": round(hits5 / answered5, 4) if answered5 else None,
        "hit@10": round(hits10 / answered10, 4) if answered10 else None,
        "answered@5": answered5,
        "answered@10": answered10,
        "hits@5": hits5,
        "hits@10": hits10,
        "abstain": dict(sorted(abstain.items())),
        "abstain_n": int(sum(abstain.values())),
        "_answered5": answered_pairs5,
        "_answered10": answered_pairs10,
    }


def main() -> None:
    extractor, profiles = load(OUT)
    n_subj = len(profiles)
    ge3 = {s: r for s, r in profiles.items()
           if len(r["predicates"]) >= MIN_PREDS}
    pairs = [(s, p) for s, r in ge3.items() for p in r["predicates"]]
    pairs.sort()
    rng = random.Random(SEED)
    rng.shuffle(pairs)
    n_hold = int(len(pairs) * HOLD)
    held = pairs[:n_hold]
    held_set = set(held)

    remain = {}
    for s, r in profiles.items():
        keep = {p: n for p, n in r["predicates"].items()
                if (s, p) not in held_set}
        if keep:
            remain[s] = keep

    glob = Counter()
    for preds in remain.values():
        glob.update(preds)
    global_scores = dict(glob)

    lat = build(profiles)
    print("lattice:", json.dumps(lat.report()),
          "held", len(held), "remain_subjects", len(remain), flush=True)

    def pred_kin(subject):
        return kin_average(lat, remain, subject)

    def pred_base(_subject):
        if not global_scores:
            return None, "INSUFFICIENT_PROFILE"
        return global_scores, None

    print("scoring kin…", flush=True)
    kin_row = score_hits(held, pred_kin)
    print("scoring baseline…", flush=True)
    base_row = score_hits(held, pred_base)
    # Same-pool baseline: hit rate on the pairs kin actually answered.
    # The global ranker never abstains, so this is the fair contrast.
    matched5 = score_hits(kin_row.pop("_answered5"), pred_base)
    matched10 = score_hits(kin_row.pop("_answered10"), pred_base)
    base_row.pop("_answered5", None)
    base_row.pop("_answered10", None)
    matched5.pop("_answered5", None)
    matched5.pop("_answered10", None)
    matched10.pop("_answered5", None)
    matched10.pop("_answered10", None)

    out = {
        "extractor": extractor,
        "subjects": n_subj,
        "subjects_ge3": len(ge3),
        "coverage_ge3": round(len(ge3) / n_subj, 4) if n_subj else None,
        "pairs": len(pairs),
        "held_out": len(held),
        "seed": SEED,
        "lattice": lat.report(),
        "kin": kin_row,
        "baseline": base_row,
        "baseline_on_kin_answered@5": {
            "hit@5": matched5["hit@5"],
            "answered": matched5["answered@5"],
        },
        "baseline_on_kin_answered@10": {
            "hit@10": matched10["hit@10"],
            "answered": matched10["answered@10"],
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
