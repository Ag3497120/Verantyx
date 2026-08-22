"""Typo recovery as a typed hand-off — never a silent correction.

An out-of-vocabulary query is not rewritten. It is compared to the
lattice neighbourhood: vocabulary words that share a positional unit
with the query (the same (unit, L/R) slots `lattice.build` writes)
and sit at character edit distance ≤ 1 (Damerau-Levenshtein, so an
adjacent transposition counts as one). Those neighbours are returned
as `TYPO_CANDIDATE` with the overlap count that earned each row.
The caller decides whether to accept a candidate. This module does
not.

In-vocabulary queries do not fire. Returning a "correction" for a
word the vocabulary already holds is the bad failure — a real title
is not a typo. Queries that share no unit with any edit-1 neighbour,
or whose length has no split in the lattice inventory, return
`UNKNOWN_NO_CANDIDATE`. Both silences are typed.

Candidate generation walks the unit index (`lattice.up`), never the
full vocabulary. A common first character may still touch thousands
of kin; the edit-1 gate is O(length) per neighbour and is the only
filter after the index.

## Measured — profile subjects, lattice-indexed, seed 20260814

    vocab                            1,419,406  predicate_profiles.json subjects
    lattice                          527,175 words, 787,333 slots
    eligible (lattice, length ≥ 3)   495,155
    scored                           500
    collisions (mutation ∈ vocab)    5          unrecoverable; not scored
    recovery@1                       0.6800     340 / 500
    recovery@5                       0.8480     424 / 500
    UNKNOWN_NO_CANDIDATE             30         all length-6 (insert on a 5-char word;
                                                SPLITS has no row, so the index is silent)
    false-fire on 500 clean words    0 / 500    pass line PASS
    fork TYPO_RECOVERY_HANDOFF       pass
    timing, recovery queries         mean 2.151 ms   p50 0.366 ms   p95 5.653 ms
    timing, in-vocab short-circuit   mean 0.0002 ms

The 30 silences are structural, not ranking: a 5-character title plus one
insert leaves the split inventory, and a neighbourhood that cannot be
asked must not be guessed. Among the 470 queries the index could see,
@5 is 424 / 470. The remaining misses are crowded 2-character right-hand
slots (竹の → あの / ゆの / りの; 竹の丸 not in top 5) — the gate fired,
the original lost the sort.

    電荷密変 → 電荷密度     overlap 3  edit 1
    低蕾素食 → 低炭素食     overlap 3  edit 1
    涯天海角 → 天涯海角     overlap 2  edit 1
    戲アナキー駅            UNKNOWN_NO_CANDIDATE  (アナキー駅 + insert)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .granularity import SPLITS
from .lattice import Lattice

IN_VOCABULARY = "IN_VOCABULARY"
TYPO_CANDIDATE = "TYPO_CANDIDATE"
UNKNOWN_NO_CANDIDATE = "UNKNOWN_NO_CANDIDATE"

_MEMBERSHIP = (set, frozenset, dict)


def positional_units(term: str) -> List[Tuple[str, str]]:
    """The (unit, position) slots `lattice.build` would write for ``term``.

    Lengths outside the measured split inventory yield nothing — the
    lattice has no slot for them, so the index cannot be asked.
    """
    out: List[Tuple[str, str]] = []
    for a, _b in SPLITS.get(len(term), ()):
        out.append((term[:a], "L"))
        out.append((term[a:], "R"))
    return out


def edit_distance_le1(a: str, b: str) -> Optional[int]:
    """Damerau-Levenshtein, but only 0, 1, or None (meaning > 1).

    Adjacent transposition is 1; a non-adjacent swap is two substitutions
    and refuses. Length gap > 1 refuses without walking the strings.
    """
    if a == b:
        return 0
    na, nb = len(a), len(b)
    if abs(na - nb) > 1:
        return None
    if na == nb:
        diffs = [i for i in range(na) if a[i] != b[i]]
        if len(diffs) == 1:
            return 1
        if len(diffs) == 2:
            i, j = diffs
            if j == i + 1 and a[i] == b[j] and a[j] == b[i]:
                return 1
        return None
    if na > nb:
        a, b = b, a
    i = 0
    la = len(a)
    while i < la and a[i] == b[i]:
        i += 1
    if a[i:] == b[i + 1:]:
        return 1
    return None


def recover(term: str, *, lattice: Lattice, vocab: Any) -> Dict[str, Any]:
    """Hand-off for an out-of-vocabulary term. Never rewrites ``term``.

    ``vocab`` is the membership set (any container with ``in``). In-vocab
    terms return ``IN_VOCABULARY`` before the index is touched.
    """
    if not isinstance(vocab, _MEMBERSHIP):
        vocab = set(vocab)
    if term in vocab:
        return {"verdict": IN_VOCABULARY}

    units = positional_units(term)
    if not units:
        return {"verdict": UNKNOWN_NO_CANDIDATE}

    shared: Dict[str, Set[Tuple[str, str]]] = {}
    n = len(term)
    lo, hi = n - 1, n + 1
    for unit, pos in units:
        fam = lattice.up.get((unit, pos))
        if not fam:
            continue
        for w in fam:
            if w not in vocab:
                continue
            lw = len(w)
            if lw < lo or lw > hi:
                continue
            bucket = shared.get(w)
            if bucket is None:
                shared[w] = {(unit, pos)}
            else:
                bucket.add((unit, pos))

    candidates: List[Dict[str, Any]] = []
    for w, slots in shared.items():
        dist = edit_distance_le1(term, w)
        if dist is None:
            continue
        candidates.append({
            "word": w,
            "overlap_units": len(slots),
            "edit_distance": dist,
        })
    candidates.sort(key=lambda c: (-c["overlap_units"], c["edit_distance"],
                                   c["word"]))
    if not candidates:
        return {"verdict": UNKNOWN_NO_CANDIDATE}
    return {"verdict": TYPO_CANDIDATE, "candidates": candidates}


def regression() -> Dict[str, Any]:
    """Fork-equivalent: in-vocab silence, typed hand-off, no rewrite key."""
    from .lattice import build

    words = [
        "電荷密度", "電気", "電子", "密度", "電荷",
        "損害賠償", "賠償", "電荷密閉",
    ]
    lat = build(words)
    vocab = set(words)

    inside = recover("電荷密度", lattice=lat, vocab=vocab)
    typo = recover("電荷密変", lattice=lat, vocab=vocab)
    tops = [c["word"] for c in typo.get("candidates") or []]
    closed = recover("電荷密閉", lattice=lat, vocab=vocab)
    junk = recover("ｑｘｚｗ", lattice=lat, vocab=vocab)
    short = recover("密", lattice=lat, vocab=vocab)

    # Ranking: 電荷密度 and 電荷密閉 are both edit-1 from 電荷密変;
    # overlap is equal, so lexicographic order decides.
    ranked_ok = (
        typo.get("verdict") == TYPO_CANDIDATE
        and tops[:2] == ["電荷密度", "電荷密閉"]
        and all(c["edit_distance"] == 1 for c in typo["candidates"])
        and typo["candidates"][0]["overlap_units"]
        >= typo["candidates"][1]["overlap_units"]
    )
    ok = all([
        inside.get("verdict") == IN_VOCABULARY,
        "candidates" not in inside,
        "correction" not in inside,
        "correction" not in typo,
        typo.get("verdict") == TYPO_CANDIDATE,
        "電荷密度" in tops,
        ranked_ok,
        closed.get("verdict") == IN_VOCABULARY,
        junk.get("verdict") == UNKNOWN_NO_CANDIDATE,
        short.get("verdict") == UNKNOWN_NO_CANDIDATE,
        "correction" not in junk,
    ])
    return {
        "experiment": "typo_recovery",
        "fork": "TYPO_RECOVERY_HANDOFF",
        "pass": bool(ok),
        "result": {
            "in_vocab": inside.get("verdict"),
            "typo": typo.get("verdict"),
            "top": tops[:3],
            "junk": junk.get("verdict"),
            "closed_in_vocab": closed.get("verdict"),
        },
    }
