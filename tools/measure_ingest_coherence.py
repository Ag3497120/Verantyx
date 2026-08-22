"""Synthetic-anomaly protocol for ingest-time coherence (納品3).

Protocol (SPEC_2026-08-14_meaning_layers 納品3). Labels are known
because they are injected (機械オラクル). Seed 20260814.

1. Subjects with ≥3 predicates and a drawable kin family
   (family_members ≥ min_family=3).
2. Clean set: each subject's real profile; expected COHERENT.
3. Anomaly set: the same subjects wearing a randomly chosen subject's
   predicates from a DIFFERENT kin family (slot sets disjoint) —
   伝導するりんご.
4. Default threshold 0.70 was preregistered in
   verantyx/ingest_coherence.py before this sweep. The curve is
   reported; the default is not moved.

## Measured — jawiki leads, heuristic profiles, seed 20260814

    subjects                         1,419,406
    extractor                        heuristic
    lattice                          527,175 words, 787,333 slots
    eligible (≥3 preds + kin family) 158,302
    sampled                          800 clean + 800 swapped
    skipped (no disjoint donor)      0
    fork INGEST_COHERENCE_LEDGER     pass

    deviation (1−cosine)
        clean    mean 0.7498  median 0.7527  min 0.0242  max 1.0000
        anomaly  mean 0.7983  median 0.7833  min 0.3613  max 1.0000

    preregistered default threshold 0.70
        detection rate     0.6637    531 / 800
        false-positive     0.6025    482 / 800
        abstain            0

    threshold curve
        0.50   det 0.9587   fp 0.8675
        0.60   det 0.8588   fp 0.7525
        0.70   det 0.6637   fp 0.6025   ← default, not moved
        0.80   det 0.4838   fp 0.4512

The default does not separate. Clean and swapped sit 0.05 apart in
mean 1−cosine; every threshold on the curve has detection only about
six points above the false-positive rate. Thin heuristic profiles
(typical total ~4) plus character-position kin (元町@L pools a
cinema with a waterworks) make a real subject's own predicates
almost as far from the family mean as a borrowed profile. The
number stays visible; the registered 0.70 is not moved.

Examples at the default (swap protocol):
    元町映画館 ← 宮代町議会     0.760  COHERENCE_ANOMALY
    新表現主義 ← 角頭歩戦法     1.000  COHERENCE_ANOMALY
    上雄信内駅 ← 読売教育賞     0.673  COHERENT (miss)

## Measured — jawiki leads, fugashi extractor, seed 20260814

    subjects                         1,419,406
    extractor                        fugashi
    lattice                          527,175 words, 787,333 slots
    eligible (≥3 preds + kin family) 108,474
    sampled                          800 clean + 800 swapped
    skipped (no disjoint donor)      0
    fork INGEST_COHERENCE_LEDGER     pass

    deviation (1−cosine)
        clean    mean 0.3611  median 0.2622  min 0.0090  max 1.0000
        anomaly  mean 0.3952  median 0.2823  min 0.0464  max 1.0000

    preregistered default threshold 0.70
        detection rate     0.1575    126 / 800
        false-positive     0.1425    114 / 800
        abstain            0

    threshold curve
        0.50   det 0.2525   fp 0.2188
        0.60   det 0.1875   fp 0.1688
        0.70   det 0.1575   fp 0.1425   ← default, not moved
        0.80   det 0.1487   fp 0.1288

The default still does not separate. Clean and swapped sit 0.03
apart in mean 1−cosine (0.3611 vs 0.3952); every threshold on the
curve has detection only about two to three points above the
false-positive rate. Both means dropped versus the heuristic run
(0.75/0.80 → 0.36/0.40) — profiles sit closer to the family, and
である takes more of the mass — but the diagnostic gap did not
open. The registered 0.70 is not moved.

Examples at the default (swap protocol):
    橋本恵子 ← 再生産労働       1.000  COHERENCE_ANOMALY
    永井博弌 ← 岩崎吉太郎       0.986  COHERENCE_ANOMALY
    中部大学校 ← 認定専攻科     0.191  COHERENT (miss)
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.ingest_coherence import (
    DEFAULT_MIN_FAMILY,
    DEFAULT_THRESHOLD,
    MEASURE,
    VERDICT_ANOMALY,
    VERDICT_COHERENT,
    check,
    family_members,
    regression,
)
from verantyx.lattice import build
from verantyx.predicate_profile import OUT, load

SEED = 20260814
MIN_PREDS = 3
N_SAMPLE = 800
# Preregistered default plus three alternatives. The default is not
# chosen from this list after the fact; it is the module constant.
CURVE = (0.50, 0.60, 0.70, 0.80)


def _preds(rec):
    return dict(rec.get("predicates") or {})


def _verdict_at(deviation, threshold, reason):
    if reason:
        return reason
    if deviation is None:
        return "INSUFFICIENT_PROFILE"
    if deviation > threshold:
        return VERDICT_ANOMALY
    if deviation < threshold:
        return VERDICT_COHERENT
    return "TIE"


def _rates(rows, expected_anomaly, threshold):
    flagged = 0
    coherent = 0
    abstain = {}
    for row in rows:
        v = _verdict_at(row["deviation"], threshold, row["reason"])
        if v == VERDICT_ANOMALY:
            flagged += 1
        elif v == VERDICT_COHERENT:
            coherent += 1
        else:
            abstain[v] = abstain.get(v, 0) + 1
    n = len(rows)
    answered = flagged + coherent
    if expected_anomaly:
        detection_all = flagged / n if n else None
        detection_answered = flagged / answered if answered else None
        return {
            "n": n,
            "flagged": flagged,
            "coherent": coherent,
            "abstain": dict(sorted(abstain.items())),
            "abstain_n": int(sum(abstain.values())),
            "detection_rate": None if detection_all is None else round(detection_all, 4),
            "detection_rate_answered": (
                None if detection_answered is None else round(detection_answered, 4)
            ),
        }
    fp_all = flagged / n if n else None
    fp_answered = flagged / answered if answered else None
    return {
        "n": n,
        "flagged": flagged,
        "coherent": coherent,
        "abstain": dict(sorted(abstain.items())),
        "abstain_n": int(sum(abstain.values())),
        "false_positive_rate": None if fp_all is None else round(fp_all, 4),
        "false_positive_rate_answered": (
            None if fp_answered is None else round(fp_answered, 4)
        ),
    }


_KANJI = re.compile(r"[㐀-䶿一-鿿]")


def _moments(rows):
    xs = sorted(r["deviation"] for r in rows if r["deviation"] is not None)
    n = len(xs)
    if not n:
        return None
    mean = sum(xs) / n
    mid = xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])
    return {
        "n": n,
        "mean": round(mean, 4),
        "median": round(mid, 4),
        "min": round(xs[0], 4),
        "max": round(xs[-1], 4),
    }


def _readable_key(row):
    subject = row["subject"]
    donor = row.get("donor") or ""
    kan = len(_KANJI.findall(subject)) + len(_KANJI.findall(donor))
    return (-kan, len(subject) + len(donor), subject)


def _annotate(row):
    rec = dict(row["record"])
    rec["protocol"] = "swap"
    rec["expected"] = VERDICT_ANOMALY
    rec["donor"] = row["donor"]
    return rec


def _pick_examples(anomaly_rows):
    detected = [r for r in anomaly_rows if r["record"]["verdict"] == VERDICT_ANOMALY]
    missed = [r for r in anomaly_rows if r["record"]["verdict"] == VERDICT_COHERENT]
    detected.sort(key=lambda r: (_readable_key(r), -(r["deviation"] or 0)))
    missed.sort(key=lambda r: (_readable_key(r), r["deviation"] or 0))
    out = []
    for r in detected[:2]:
        out.append(_annotate(r))
    if missed:
        out.append(_annotate(missed[0]))
    elif detected:
        out.append(_annotate(detected[-1]))
    return out


def main() -> None:
    t0 = time.time()
    fork = regression()
    print("fork:", json.dumps(fork, ensure_ascii=False), flush=True)
    if not fork["pass"]:
        raise SystemExit("INGEST_COHERENCE_LEDGER failed")

    extractor, profiles = load(OUT)
    print("loaded profiles", len(profiles),
          "extractor", extractor,
          "%.1fs" % (time.time() - t0), flush=True)

    lat = build(profiles)
    print("lattice:", json.dumps(lat.report()),
          "%.1fs" % (time.time() - t0), flush=True)

    eligible = []
    for subject, rec in profiles.items():
        preds = _preds(rec)
        if len(preds) < MIN_PREDS:
            continue
        members, slots, why = family_members(
            subject, profiles=profiles, lattice=lat,
            min_family=DEFAULT_MIN_FAMILY,
        )
        if why or not members:
            continue
        eligible.append((subject, frozenset(slots), preds))
    eligible.sort(key=lambda x: x[0])
    print("eligible", len(eligible), "%.1fs" % (time.time() - t0), flush=True)

    rng = random.Random(SEED)
    pool = list(eligible)
    rng.shuffle(pool)
    wanted = min(N_SAMPLE, len(pool))

    clean_rows = []
    anomaly_rows = []
    skipped_no_donor = 0
    for subject, slots, preds in pool:
        if len(clean_rows) >= wanted:
            break
        donor = None
        donor_preds = None
        for _ in range(200):
            cand, cand_slots, cand_preds = pool[rng.randrange(len(pool))]
            if cand == subject:
                continue
            if not cand_slots.isdisjoint(slots):
                continue
            if set(cand_preds) == set(preds):
                continue
            donor = cand
            donor_preds = cand_preds
            break
        if donor is None:
            skipped_no_donor += 1
            continue
        clean = check(
            subject, preds, profiles=profiles, lattice=lat,
            min_family=DEFAULT_MIN_FAMILY, threshold=DEFAULT_THRESHOLD,
        )
        swapped = check(
            subject, donor_preds, profiles=profiles, lattice=lat,
            min_family=DEFAULT_MIN_FAMILY, threshold=DEFAULT_THRESHOLD,
        )
        clean_rows.append({
            "subject": subject,
            "deviation": clean["deviation"],
            "reason": clean["reason"],
            "record": clean,
        })
        anomaly_rows.append({
            "subject": subject,
            "donor": donor,
            "deviation": swapped["deviation"],
            "reason": swapped["reason"],
            "record": swapped,
        })

    curve = []
    for thr in CURVE:
        curve.append({
            "threshold": thr,
            "default": thr == DEFAULT_THRESHOLD,
            "clean": _rates(clean_rows, False, thr),
            "anomaly": _rates(anomaly_rows, True, thr),
        })

    default_row = next(c for c in curve if c["default"])
    examples = _pick_examples(anomaly_rows)

    out = {
        "extractor": extractor,
        "measure": MEASURE,
        "preregistered_threshold": DEFAULT_THRESHOLD,
        "min_family": DEFAULT_MIN_FAMILY,
        "seed": SEED,
        "subjects": len(profiles),
        "lattice": lat.report(),
        "eligible": len(eligible),
        "sampled": len(clean_rows),
        "skipped_no_donor": skipped_no_donor,
        "fork": {"name": fork["fork"], "pass": fork["pass"]},
        "deviation": {
            "clean": _moments(clean_rows),
            "anomaly": _moments(anomaly_rows),
        },
        "default": {
            "threshold": DEFAULT_THRESHOLD,
            "clean": default_row["clean"],
            "anomaly": default_row["anomaly"],
        },
        "curve": curve,
        "examples": examples,
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
