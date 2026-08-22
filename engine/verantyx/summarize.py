"""Compression over n paths — the staged junction generalized, hand-over only.

`explain` built the minimal multi-stage crossing: two paths, one
intersection, the vocabulary gate on everything spoken. This module is
the same junction at n: each subject is a path, the crossing is every
facet that two or more of the subjects' crosses hold, and what may be
SAID about the crossing is bounded by the edge licence — a claim is a
pair the corpus wrote in one sentence, or it is not made.

    subjects    n held cores (a non-held subject is reported, not used)
    crossing    facet -> which subjects hold it, kept at >= 2 holders
    claims      (subject, f1, f2) where (f1, f2) is an EDGE of that
                subject among crossing facets — never mere co-presence
    selection   ranked by crossing width (how many paths share the
                claim's facets), then mass (the subject's own counts)

## Every drop is a group drop

Compression is the operation that discards, and a discard decided by a
tie is the manufactured choice every other organ here abstains from.
Candidates are walked in rank groups: a group that fits inside the
limit is kept whole, and the first group that does not fit is dropped
WHOLE, with everything below it — never split, never sampled. The
dropped-at-cut group rides the output so a reader can see what the
limit cost.

## What a claim is, and is not

An edge-licensed claim is testimony ABOUT the corpus (these two facets
were written in one sentence of this subject) and is recountable from
the edges sidecar. The SELECTION — which claims survived compression —
is this module's and is labelled ranked_by so the order is a stated
claim, not an accident. Nothing here enters a verdict, a census, or the
concord vocabulary: same seat as `writer` and `explain`, pinned by the
same import-isolation fork.

## Measured — published store (89,369 cores), edges sidecar, limit 5

    時効・援用・中断        crossing 9    licensed 3    kept 3
        中断: 停止 と 完成猶予 / 停止 と 更新 / 完成猶予 と 更新 —
        the actual doctrine, read off edges
    抵当権・質権・登記      crossing 41   licensed 18   kept 5,
                            13 dropped as whole rank groups
    過失・故意              crossing 22   licensed 16   kept 2,
                            14 dropped — the boundary group did not
                            fit and fell WHOLE; the tie discipline
                            costs coverage and says so
    殺人罪・超伝導          UNKNOWN_NO_CROSSING — disjoint domains
                            do not meet, and no claim is invented
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def crossing_of(store: Any, subjects: Sequence[str]) -> Dict[str, List[str]]:
    """facet -> the subjects holding it, kept where two or more do."""
    labels = getattr(store, "source_labels", set()) or set()
    holders: Dict[str, List[str]] = {}
    for s in subjects:
        for f in (store.crosses.get(s) or ()):
            if f in labels or f in subjects:
                continue
            holders.setdefault(f, []).append(s)
    return {f: hs for f, hs in holders.items() if len(hs) >= 2}


def summarize(
    store: Any,
    subjects: Sequence[str],
    *,
    vocab: Any,
    edges: Any,
    limit: int = 5,
) -> Dict[str, Any]:
    """n paths in, edge-licensed claims out — or a typed refusal.

    ``edges`` is mandatory, not optional-with-fallback: without the
    licence there is nothing this module is allowed to say, and it says
    so by type instead of downgrading to co-presence.
    """
    labels = getattr(store, "source_labels", set()) or set()
    held = [s for s in subjects
            if s in store.crosses and s not in labels]
    dropped = [s for s in subjects if s not in held]
    spoken_subjects = [s for s in held if s in vocab]
    if len(held) < 2:
        return {"verdict": "UNKNOWN_TOO_FEW_PATHS", "held": held,
                "dropped_subjects": dropped,
                "note": "a crossing needs at least two held subjects"}

    crossing = crossing_of(store, held)
    if not crossing:
        return {"verdict": "UNKNOWN_NO_CROSSING", "held": held,
                "dropped_subjects": dropped,
                "note": "no facet is shared by two subjects; these paths "
                        "do not meet in this store"}

    if edges is None:
        return {"verdict": "UNKNOWN_NO_EDGE_LICENSE", "held": held,
                "crossing": len(crossing),
                "note": "no edge lookup supplied; co-presence is not a "
                        "licence to claim a relation"}

    # A claim is an EDGE among a subject's crossing facets. The word gate
    # applies to everything spoken: the subject and both facets.
    claims: List[Dict[str, Any]] = []
    for s in spoken_subjects:
        cf = [f for f in crossing
              if f in (store.crosses.get(s) or ()) and f in vocab]
        if len(cf) < 2:
            continue
        try:
            pairs = edges(s, cf) or []
        except Exception:
            pairs = []
        cross = store.crosses.get(s) or {}
        for f1, f2 in pairs:
            claims.append({
                "subject": s, "pair": [f1, f2],
                "width": len(crossing.get(f1, ())) + len(crossing.get(f2, ())),
                "mass": (cross.get(f1) or 0) + (cross.get(f2) or 0),
            })
    if not claims:
        return {"verdict": "UNKNOWN_NO_EDGE_LICENSE", "held": held,
                "crossing": len(crossing),
                "note": "the crossing exists but no sentence in the "
                        "corpus wrote any shared pair together; silence, "
                        "not invention"}

    # Group by rank; keep whole groups, drop whole groups. The first
    # group the limit cannot hold falls entire — a tie never decides a
    # drop.
    def rank(c: Dict[str, Any]) -> Tuple[int, int]:
        return (c["width"], c["mass"])

    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for c in claims:
        groups.setdefault(rank(c), []).append(c)
    kept: List[Dict[str, Any]] = []
    dropped_at_cut: List[Dict[str, Any]] = []
    for key in sorted(groups, reverse=True):
        g = sorted(groups[key],
                   key=lambda c: (c["subject"], c["pair"]))
        if dropped_at_cut or len(kept) + len(g) > limit:
            dropped_at_cut.extend(g)
        else:
            kept.extend(g)

    lines = ["%s: %s と %s（同一文）" % (c["subject"], c["pair"][0],
                                          c["pair"][1]) for c in kept]
    return {
        "verdict": "SUMMARY",
        "held": held, "dropped_subjects": dropped,
        "unspoken_subjects": [s for s in held if s not in vocab],
        "crossing": len(crossing),
        "licensed": len(claims),
        "kept": kept, "dropped_at_cut": len(dropped_at_cut),
        "ranked_by": "crossing width, then subject mass; drops are "
                     "whole rank groups",
        "text": "。".join(lines) + ("。" if lines else ""),
        "note": "each claim is recountable from the edges sidecar; the "
                "selection is this module's and says so",
    }
