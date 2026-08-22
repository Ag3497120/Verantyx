"""Reaching a word the store does not hold, by taking it apart.

Unknown-word reach and new-word creation are the same operation run in two
directions, which is why four attempts that changed something else all
failed:

    outward   損害賠償 is held, 賠償 is proposed and turns out to be a word
              the corpus writes — 15x over chance, measured in `granularity`
    inward    電荷密度 is NOT held; split it, and 電荷 is

The four that failed — more grain settings, domain-split sovereigns,
cooperating sovereigns, 32,652 more cores — each varied the index, the
partition or the corpus. None varied the DECOMPOSITION, and decomposition is
what the reach is made of.

## Measured, 150 held-out cores

    containment (the staircase)   65 of 150 answered   4.5% facet overlap    7.5x
    unit decomposition            50 of 150           10.4%                 14.5x

Fewer answers and more than twice the overlap. The unit model splits a term
where the corpus's own vocabulary splits, and it respects position: 賠償
earns its right-hand slot from 損害賠償 and not from any string ending in
those characters. 電荷密度 -> 電荷, 保護司 -> 保護, 症例記述 -> 記述,
社会的貢献 -> 貢献, 居場所 -> 場所.

Japanese is head-final, so the right half is tried first. 発明者 -> 者 and
鉱泉水 -> 泉水 are what that costs when the head is a bare suffix.

## Layered, not pooled

Units first, containment second, and the answer says which reached it. They
are not summed and not voted: `UNITS` is a decomposition the corpus attests,
`CONTAINMENT` is a longer word that happens to hold the term, and a reader
discounting one of them needs to know which they have.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def units_for(model: Any, term: str) -> List[Tuple[str, str]]:
    """(part, position) splits of ``term`` the model saw in that position."""
    from .granularity import SPLITS

    out: List[Tuple[str, str]] = []
    for a, b in SPLITS.get(len(term), ()):
        left, right = term[:a], term[a:]
        if (left in model.slots.get((a, "L"), ())
                and right in model.slots.get((b, "R"), ())):
            # Head-final: the right half carries the subject.
            out.append((right, "R"))
            out.append((left, "L"))
    return out


def by_units(store: Any, model: Any, term: str) -> Optional[str]:
    """The richest core among this term's attested units, or None."""
    labels = getattr(store, "source_labels", set()) or set()
    best: Optional[Tuple[str, int]] = None
    for part, _pos in units_for(model, term):
        if part in store.crosses and part not in labels:
            n = len(store.crosses.get(part) or ())
            if best is None or n > best[1]:
                best = (part, n)
    return best[0] if best else None


def reach(
    store: Any,
    term: str,
    *,
    model: Any = None,
    judge: Any = None,
) -> Dict[str, Any]:
    """Where an unheld term lands, and by which route.

    ``model`` is a `granularity.UnitModel` over the store's cores; ``judge``
    a built `graded.GradedJudge` for the containment fallback.
    """
    labels = getattr(store, "source_labels", set()) or set()
    if term in store.crosses and term not in labels:
        return {"verdict": "HELD", "term": term, "item": term}

    if model is not None:
        part = by_units(store, model, term)
        if part:
            return {
                "verdict": "UNITS", "term": term, "item": part,
                "note": "the corpus splits this term where its own vocabulary "
                        "splits; the part is a word it writes, not a fragment",
            }
    if judge is not None:
        r = judge.ask("%sとは" % term)
        if str(r.get("verdict", "")).startswith("ANSWER"):
            return {
                "verdict": "CONTAINMENT", "term": term, "item": r.get("item"),
                "agreeing": r.get("agreeing"),
                "note": "a longer word the store holds contains this one; "
                        "weaker than a unit split — 4.5% facet overlap "
                        "against 10.4% — and reported apart from it",
            }
    return {"verdict": "UNKNOWN_NO_REACH", "term": term, "item": None,
            "note": "the term does not decompose into anything the corpus "
                    "attests and no held word contains it"}


def build_model(store: Any) -> Any:
    """A unit model over the store's own cores."""
    from .granularity import decompose_units

    labels = getattr(store, "source_labels", set()) or set()
    return decompose_units([c for c in store.crosses if c not in labels])
