"""What the store held then, and what it holds now.

A store that is written to keeps moving, and the interesting failure is not
that it grew — it is that something which was recorded one way is now
recorded another, and nobody decided that. The corpus manifests already
catch this for documents: name, url, sha256, and a checksum mismatch is
loud precisely because "the ministry issued a correction" matters more than
"the download broke". This is the same discipline turned on the knowledge.

    snapshot   core -> a digest of its facets, plus the shape invariants
    compare    added / removed / changed, each listed and none summed

## Drift is not error

A verdict here is never "wrong". A core that gained facets was probably
taught something; one that lost them was probably corrected. What the tool
provides is the list, so a reader decides. Folding the three into one number
would hide the only case that usually matters — a core whose facets were
REPLACED, which reads as no change at all in a count.

## Why digests and not the facets themselves

A baseline that stores every facet of 54,244 cores is a copy of the store,
and a copy drifts from the original the moment either is written to. A
digest per core is 16 bytes, cannot be mistaken for the data, and answers
the only question a baseline is for: did this change.

The facets ARE kept for cores the caller names as load-bearing — a design
one intends to hold to — because for those the useful report is not "it
changed" but "it changed from this to that".
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


def _digest(facets: Iterable[str]) -> str:
    h = hashlib.sha256("\x1f".join(sorted(facets)).encode("utf-8"))
    return h.hexdigest()[:16]


def snapshot(
    store: Any,
    *,
    label: str = "",
    keep: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Record the store's shape. ``keep`` names cores to record in full."""
    labels = getattr(store, "source_labels", set()) or set()
    digests: Dict[str, str] = {}
    kept: Dict[str, List[str]] = {}
    keepset = set(keep or ())
    for core, cross in store.crosses.items():
        if core in labels:
            continue
        facets = sorted(f for f in (cross or ()) if f not in labels)
        digests[core] = _digest(facets)
        if core in keepset:
            kept[core] = facets
    return {
        "label": label or "baseline",
        "recorded": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cores": len(digests),
        "digests": digests,
        "kept": kept,
        "note": "digests answer 'did this change'; kept answers 'from what "
                "to what', and is only recorded for cores named up front",
    }


def compare(base: Dict[str, Any], store: Any) -> Dict[str, Any]:
    """Against a snapshot: what was added, removed, changed."""
    now = snapshot(store, label="now", keep=list(base.get("kept") or ()))
    b, n = base.get("digests") or {}, now["digests"]
    added = sorted(set(n) - set(b))
    removed = sorted(set(b) - set(n))
    changed = sorted(c for c in set(b) & set(n) if b[c] != n[c])

    detail: List[Dict[str, Any]] = []
    for core in changed:
        was, isnow = (base.get("kept") or {}).get(core), now["kept"].get(core)
        if was is None or isnow is None:
            continue
        gained = [f for f in isnow if f not in was]
        lost = [f for f in was if f not in isnow]
        detail.append({
            "core": core, "gained": gained[:12], "lost": lost[:12],
            # The case a count hides: everything replaced, size unchanged.
            "replaced": bool(gained) and bool(lost) and len(was) == len(isnow),
        })

    return {
        # Typed as its own outcome. `DRIFTED` is not a failure and `STABLE`
        # is not a pass — both are reports, and only a reader knows which
        # one the design intended.
        "verdict": "STABLE" if not (added or removed or changed) else "DRIFTED",
        "baseline": base.get("label"), "recorded": base.get("recorded"),
        "cores_then": base.get("cores"), "cores_now": now["cores"],
        "added": len(added), "removed": len(removed), "changed": len(changed),
        "added_examples": added[:12],
        "removed_examples": removed[:12],
        "changed_examples": changed[:12],
        "detail": detail,
        "note": "drift is not error: a gain is usually a lesson and a loss "
                "is usually a correction; the list is the product",
    }


def save(snap: Dict[str, Any], path: Path) -> Dict[str, Any]:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return {"verdict": "ANSWER", "path": str(path), "cores": snap["cores"],
            "bytes": Path(path).stat().st_size}


def load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
