"""Synthetic-typo recovery and in-vocabulary silence (W2c).

Protocol (SPEC_2026-08-14_eight_gaps W2c). Vocabulary is the subject
keys of predicate_profiles.json — the same population
`measure_predicate_profile` builds the lattice from. Membership uses
every subject (a real title is never a typo). The lattice indexes the
length-2–5 slice; recovery samples from that slice at length ≥ 3 so a
1-character mutation is meaningful and the original is a lattice node.

Seed 20260814. 500 vocabulary words, one mutation each
(substitute / delete / insert / transpose, chosen and placed by the
RNG). A mutation that lands on another vocabulary word is COLLISION:
unrecoverable in principle, counted separately, not scored. Recovery@1
and @5 ask whether the original sits in the ranked candidate list.
A second 500, the same originals unmutated, must return IN_VOCABULARY
(pass line: 0 fires).

## Measured — profile subjects, lattice-indexed, seed 20260814

    vocab                            1,419,406  predicate_profiles.json subjects
    lattice                          527,175 words, 787,333 slots
    eligible (lattice, length ≥ 3)   495,155
    scored                           500
    collisions (mutation ∈ vocab)    5          unrecoverable; not scored
    recovery@1                       0.6800     340 / 500
    recovery@5                       0.8480     424 / 500
    UNKNOWN_NO_CANDIDATE             30         all length-6 (insert on a 5-char word)
    false-fire on 500 clean words    0 / 500    pass line PASS
    fork TYPO_RECOVERY_HANDOFF       pass
    timing, recovery queries         mean 2.151 ms   p50 0.366 ms   p95 5.653 ms
    timing, in-vocab short-circuit   mean 0.0002 ms

    電荷密変 → 電荷密度     overlap 3  edit 1
    低蕾素食 → 低炭素食     overlap 3  edit 1
    涯天海角 → 天涯海角     overlap 2  edit 1
    戲アナキー駅            UNKNOWN_NO_CANDIDATE  (アナキー駅 + insert)
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verantyx.lattice import build
from verantyx.predicate_profile import OUT, load
from verantyx.typo_recovery import (
    IN_VOCABULARY,
    TYPO_CANDIDATE,
    recover,
    regression,
)

SEED = 20260814
N = 500
OPS = ("substitute", "delete", "insert", "transpose")


def _alphabet(words: Sequence[str]) -> List[str]:
    chars: Set[str] = set()
    for w in words:
        chars.update(w)
    return sorted(chars)


def mutate(word: str, rng: random.Random, alphabet: Sequence[str]) -> str:
    """One 1-character mutation. May return ``word`` (no-op transpose)."""
    op = OPS[rng.randrange(4)]
    if op == "substitute":
        i = rng.randrange(len(word))
        choices = [c for c in alphabet if c != word[i]]
        if not choices:
            return word
        return word[:i] + rng.choice(choices) + word[i + 1:]
    if op == "delete":
        i = rng.randrange(len(word))
        return word[:i] + word[i + 1:]
    if op == "insert":
        i = rng.randrange(len(word) + 1)
        return word[:i] + rng.choice(alphabet) + word[i:]
    if len(word) < 2:
        return word
    i = rng.randrange(len(word) - 1)
    if word[i] == word[i + 1]:
        return word
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def _mutate_new(word: str, rng: random.Random, alphabet: Sequence[str],
                tries: int = 8) -> str:
    for _ in range(tries):
        typo = mutate(word, rng, alphabet)
        if typo != word:
            return typo
    return word


def main() -> int:
    fork = regression()
    if not fork["pass"]:
        print(json.dumps(fork, ensure_ascii=False, indent=1), flush=True)
        raise SystemExit("TYPO_RECOVERY_HANDOFF failed")

    extractor, profiles = load(OUT)
    vocab: Set[str] = set(profiles)
    del profiles
    lat = build(vocab)
    eligible = sorted(w for w in lat.words if len(w) >= 3)
    alphabet = _alphabet(eligible)

    rng = random.Random(SEED)
    pool = list(eligible)
    rng.shuffle(pool)

    trials: List[Tuple[str, str, str]] = []
    collisions = 0
    noop = 0
    i = 0
    while len(trials) < N and i < len(pool):
        word = pool[i]
        i += 1
        typo = _mutate_new(word, rng, alphabet)
        if typo == word:
            noop += 1
            continue
        if typo in vocab:
            collisions += 1
            continue
        trials.append((word, typo, ""))
    if len(trials) < N:
        raise SystemExit("could not assemble %d non-collision typos" % N)

    hit1 = hit5 = 0
    unknown = 0
    times: List[float] = []
    hits: List[Tuple[str, str, List[str]]] = []
    misses: List[Tuple[str, str, str, List[str]]] = []
    for word, typo, _ in trials:
        t0 = time.perf_counter()
        out = recover(typo, lattice=lat, vocab=vocab)
        times.append(time.perf_counter() - t0)
        cands = [c["word"] for c in out.get("candidates") or []]
        if out.get("verdict") != TYPO_CANDIDATE:
            unknown += 1
            if len(misses) < 8:
                misses.append((word, typo, out.get("verdict") or "", cands))
            continue
        if word in cands[:1]:
            hit1 += 1
            hit5 += 1
            if len(hits) < 8:
                hits.append((word, typo, cands[:5]))
        elif word in cands[:5]:
            hit5 += 1
            if len(hits) < 8:
                hits.append((word, typo, cands[:5]))
        else:
            if len(misses) < 8:
                misses.append((word, typo, out.get("verdict") or "", cands[:5]))

    fire_n = 0
    fire_examples: List[str] = []
    fire_times: List[float] = []
    clean = [w for w, _t, _ in trials]
    for word in clean:
        t0 = time.perf_counter()
        out = recover(word, lattice=lat, vocab=vocab)
        fire_times.append(time.perf_counter() - t0)
        if out.get("verdict") != IN_VOCABULARY:
            fire_n += 1
            if len(fire_examples) < 8:
                fire_examples.append(word)

    demo = None
    if "電荷密度" in vocab:
        t0 = time.perf_counter()
        demo = recover("電荷密変", lattice=lat, vocab=vocab)
        demo_ms = (time.perf_counter() - t0) * 1000.0
    else:
        demo_ms = None

    def _ms(xs: List[float]) -> Dict[str, float]:
        if not xs:
            return {"mean_ms": None, "p50_ms": None, "p95_ms": None}
        ys = sorted(x * 1000.0 for x in xs)
        n = len(ys)
        return {
            "mean_ms": round(sum(ys) / n, 4),
            "p50_ms": round(ys[n // 2], 4),
            "p95_ms": round(ys[min(n - 1, int(n * 0.95))], 4),
        }

    rec_ms = _ms(times)
    clean_ms = _ms(fire_times)
    all_ms = _ms(times + fire_times)

    out = {
        "vocab_source": "predicate_profiles.json subjects",
        "extractor": extractor,
        "seed": SEED,
        "vocab_n": len(vocab),
        "lattice": lat.report(),
        "eligible_n": len(eligible),
        "scored": len(trials),
        "collisions": collisions,
        "noop_mutations": noop,
        "recovery@1": round(hit1 / N, 4),
        "recovery@5": round(hit5 / N, 4),
        "hits@1": hit1,
        "hits@5": hit5,
        "unknown_no_candidate": unknown,
        "false_fire": fire_n,
        "false_fire_pass": fire_n == 0,
        "false_fire_examples": fire_examples,
        "timing_recovery_ms": rec_ms,
        "timing_in_vocab_ms": clean_ms,
        "timing_all_ms": all_ms,
        "fork": fork,
        "demo_電荷密変": demo,
        "demo_ms": None if demo_ms is None else round(demo_ms, 4),
        "verbatim_hits": [
            {"original": w, "typo": t, "top5": c} for w, t, c in hits[:3]
        ],
        "verbatim_miss": (
            {"original": misses[0][0], "typo": misses[0][1],
             "verdict": misses[0][2], "top5": misses[0][3]}
            if misses else None
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
    return 0 if fire_n == 0 and fork["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
