"""The vocabulary as a lattice — atoms to compounds, kin by shared units.

`granularity` reads one layer: a word and the units that open and close
it. This module makes that reading recursive and lateral, the shape the
conception names: 電荷密度 decomposes to 電荷+密度, those to 電+荷 and
密+度, and at every level the words sharing a unit AT A POSITION are kin
— 電荷, 電気, 電子 under 電@L. Analysis walks down the lattice, synthesis
walks up it, and kin walks across; all three are the same structure read
in three directions.

## Every node is attested — the gate applies at every level

A lattice node is a vocabulary word (attested standalone, MIN_ATTEST
independent occurrences) or an atomic character observed inside such
words. Fragments never enter: 事訴 (inside 民事訴訟法) is not a node
because no corpus writes it standalone, and a lattice that admitted it
would relate real words through a string that is nobody's word. This is
the same sieve `granularity.verify` earned (4.9x -> 15x by dropping
fragments) applied as a membership rule.

## Kin requires position

賠償 earns its right-hand slot from 損害賠償, not from any string ending
in those characters. Kin under (電, L) and kin under (電, R) are
different families, kept apart — pooling them would relate 電荷 to
発電 through a slot neither occupies.

## Hand-over only

Nothing here enters a verdict, a census, or the concord band. The
lattice supplies structure: analysis trees for the explanation layer,
kin sets for meaning-prediction, unit inventories for synthesis
(`granularity.propose_units` remains the composer, measured at 15-16x
over chance).

## Measured — kin predicting a held-out word's facets

Lattice over the 51,798-word vocabulary: 41,540 words in range, 57,217
positional slots, 2,449 atoms. Protocol: the 150 held-out cores
(reach's protocol, script preserved at tools/measure_lattice.py), each
core's own top-10 facets as ground truth, every predictor blind to that
cross; the number is recall of those facets within the predictor's
top-20.

    kin, all units (atoms in)     recall 0.043   covers 140 of 150
    single richest unit (reach)   recall 0.044   covers  86 of 150
    kin, units >= 2 chars only    recall 0.034   covers 117 of 150
    20 random vocabulary words    recall 0.004

Two honest readings. Association does NOT sharpen: at equal precision
with the single-unit landing, kin recovers no more of a word's specific
meaning — 4% of the true facets is the measured ceiling for meaning by
family, ten times chance and nowhere near comprehension. Association
WIDENS: 86 -> 140 of 150 terms get a prediction at all, because a term
whose units are not held as cores still has kin under its units'
slots. And the atoms earn their place here — dropping them costs both
coverage (140 -> 117) and precision (0.043 -> 0.034), the reverse of
what the bare-suffix lesson suggested; a single character relates
weakly but its FAMILY aggregated still points at the right
neighbourhood.

## The long window (added after the eight-gap wave)

Lengths 6..12 were not lattice nodes at all — 10,258 attested words
(テレビドラマ, 滋賀県警本部長) invisible to descent. They enter under
two rules that replace positional patterns: every cut position is
proposed, and a cut survives only when BOTH sides are attested words,
never a single character. Measured on the same vocabulary: 4,970 of
10,258 long words carry a licensed split (テレビ|ドラマ,
滋賀県警|本部長); the 150 held-out prediction is untouched (covers 135,
recall 0.0344 vs 0.0351 without the window, same repaired store —
single-item noise, and the held-out terms are all 3..5 chars). The
numbers above this section predate the federation repair; the protocol
script reproduces both eras.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .granularity import SPLITS

#: Word lengths the lattice can split. SPLITS is the measured inventory;
#: longer strings pass through unsplit rather than guessed at.
_LENGTHS = tuple(sorted(SPLITS))

#: The long window (6..12). Long compounds get no positional patterns —
#: a pattern at length 6 would propose cuts no corpus attested, and the
#: federation repair (4ea0b5b) just removed 103,599 facets born from
#: stealing single runs off long compounds. So two rules replace the
#: patterns: a cut is proposed at every position, and it survives only
#: if BOTH sides are attested words; and no side may be a single
#: character. タブレットコンピュータ splits where the vocabulary itself
#: splits (タブレット|コンピュータ) or not at all.
_LONG_MIN, _LONG_MAX = 6, 12


def _long_cuts(n: int) -> Tuple[Tuple[int, int], ...]:
    return tuple((a, n - a) for a in range(2, n - 1))


@dataclass
class Lattice:
    """(unit, position) -> the attested words opened or closed by it."""

    words: Set[str] = field(default_factory=set)
    up: Dict[Tuple[str, str], Set[str]] = field(default_factory=dict)
    atoms: Set[str] = field(default_factory=set)

    def report(self) -> Dict[str, Any]:
        return {"words": len(self.words), "slots": len(self.up),
                "atoms": len(self.atoms)}


def build(words: Any) -> Lattice:
    """The lattice over attested words only. ``words`` is any container
    supporting membership-free iteration (a Vocabulary's keys included)."""
    lat = Lattice()
    long_words: List[str] = []
    for w in words:
        if not (2 <= len(w) <= _LONG_MAX):
            continue
        lat.words.add(w)
        if len(w) > max(_LENGTHS):
            long_words.append(w)
            continue
        for a, b in SPLITS.get(len(w), ()):
            left, right = w[:a], w[a:]
            lat.up.setdefault((left, "L"), set()).add(w)
            lat.up.setdefault((right, "R"), set()).add(w)
    # Second pass: long words index only the cuts the vocabulary licenses
    # (both sides attested words) — see the long-window note above.
    for w in long_words:
        for a, b in _long_cuts(len(w)):
            left, right = w[:a], w[a:]
            if left in lat.words and right in lat.words:
                lat.up.setdefault((left, "L"), set()).add(w)
                lat.up.setdefault((right, "R"), set()).add(w)
    lat.atoms = {u for (u, _pos) in lat.up if len(u) == 1}
    return lat


def splits_of(lat: Lattice, term: str) -> List[Tuple[str, str]]:
    """Splits whose BOTH halves are lattice nodes (word or atom)."""
    out: List[Tuple[str, str]] = []
    n = len(term)
    if n in SPLITS:
        for a, b in SPLITS[n]:
            left, right = term[:a], term[a:]
            if ((left in lat.words or left in lat.atoms)
                    and (right in lat.words or right in lat.atoms)):
                out.append((left, right))
    elif _LONG_MIN <= n <= _LONG_MAX:
        # Long window: words only, no atoms — a single character stolen
        # off a long compound is the repaired ingest disease.
        for a, b in _long_cuts(n):
            left, right = term[:a], term[a:]
            if left in lat.words and right in lat.words:
                out.append((left, right))
    return out


def analyze(lat: Lattice, term: str, *, depth: int = 3) -> Dict[str, Any]:
    """The family tree of a term, down to atoms — every branch attested.

    Analysis is display, not election: ALL node-valid splits are shown,
    because alternatives in an analysis are information where
    alternatives in an answer would be a tie to break. Recursion stops
    at atoms, at unsplittable nodes, or at ``depth``.
    """
    node: Dict[str, Any] = {"term": term,
                            "word": term in lat.words,
                            "atom": term in lat.atoms}
    if depth <= 0 or len(term) < 2:
        return node
    branches = []
    for left, right in splits_of(lat, term):
        branches.append({"left": analyze(lat, left, depth=depth - 1),
                         "right": analyze(lat, right, depth=depth - 1)})
    if branches:
        node["splits"] = branches
    return node


def kin(lat: Lattice, term: str, *, min_unit: int = 1,
        limit: int = 12) -> Dict[str, List[str]]:
    """Words related to ``term`` by sharing a unit at the same position.

    Keys are "unit@L" / "unit@R"; values are the kin words, the term
    itself excluded, deterministic order. ``min_unit`` = 2 drops the
    atomic families (a single character relates widely and weakly — the
    measured trade is in the module docstring).
    """
    out: Dict[str, List[str]] = {}
    n = len(term)
    cuts = SPLITS.get(n) or (
        _long_cuts(n) if _LONG_MIN <= n <= _LONG_MAX else ())
    for a, b in cuts:
        for unit, pos in ((term[:a], "L"), (term[a:], "R")):
            if len(unit) < min_unit:
                continue
            fam = lat.up.get((unit, pos)) or set()
            others = sorted(w for w in fam if w != term)
            if others:
                out["%s@%s" % (unit, pos)] = others[:limit]
    return out


def predict_facets(
    lat: Lattice,
    store: Any,
    term: str,
    *,
    min_unit: int = 1,
    top: int = 20,
) -> List[str]:
    """The facets a term's kin hold, ranked — meaning by association.

    The prediction never reads the term's own cross, so it is exactly
    what the lattice can say about a word the store has never held:
    what the FAMILY talks about. Ranked by summed counts across kin,
    ties lexicographic (a display order, stated, not an election).
    """
    labels = getattr(store, "source_labels", set()) or set()
    weights: Dict[str, int] = {}
    for fam in kin(lat, term, min_unit=min_unit).values():
        for w in fam:
            for f, n in (store.crosses.get(w) or {}).items():
                if f in labels or f == term:
                    continue
                weights[f] = weights.get(f, 0) + n
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    return [f for f, _n in ranked[:top]]
