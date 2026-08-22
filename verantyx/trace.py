"""The path a walk took, kept outside the stores it walked through.

A read-out chain had no memory. Each step looked only at its current core,
so the next step was chosen without reference to where the walk began or
what it had passed — and I first reported that as the structure forgetting
its subject. It was not. Nothing was remembering.

Three step rules, 40 seeds per field:

    field   rule           steps   subject held   adjacent overlap   with path
    数学    lexicographic    8.7        1.7            0.033           0.269
    数学    anchor on seed  10.9        6.9            0.042           0.385
    数学    anchor on path  11.0        5.0            0.069           0.433
    医療    lexicographic    6.8        1.3            0.019           0.312
    医療    anchor on seed   8.0        3.7            0.035           0.335
    医療    anchor on path   9.1        2.6            0.047           0.359

The two anchors are different instruments and the numbers say which is
which. Anchoring on the SEED holds the original subject longest — 6.9 steps
against 1.7 — and is what a question wants. Anchoring on the PATH walks
furthest, overlaps its previous step most, and stays most consistent with
everything it has passed, at the cost of the starting subject. That is what
a developing text wants: not a paragraph that keeps restating its opening,
but one that follows from what it has already said.

## Why the path is a separate structure

It is not knowledge. Nothing here was said by a source, so writing it into a
store would put the walk's own history where provenance is read, and the
next reader could not tell a fact from a footprint. A trace is kept beside
the stores, has its own identity, and is discarded or saved on its own
terms.

It is also what makes a walk resumable. The stores are frozen; the trace is
the only thing that changed, so replaying it reproduces the walk exactly —
which is the property a deterministic engine should have and could not,
while the walk state lived in a local variable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

#: How the next step is chosen.
#:
#:   lex     lexicographically first unvisited facet — no memory at all,
#:           kept because it is the baseline every number above beats
#:   seed    the facet sharing most with the SEED's neighbourhood
#:   path    the facet sharing most with everything visited so far
MODES = ("lex", "seed", "path")


@dataclass
class Trace:
    """Where a walk went, and what it saw, held apart from the stores."""

    seed: str = ""
    mode: str = "path"
    steps: List[Dict[str, Any]] = field(default_factory=list)
    seen: List[str] = field(default_factory=list)
    #: Every facet met so far. The anchor under mode="path".
    horizon: Set[str] = field(default_factory=set)
    #: The seed's own neighbourhood. The anchor under mode="seed".
    origin: Set[str] = field(default_factory=set)

    def record(self, core: str, facets: Set[str], text: str = "") -> None:
        self.seen.append(core)
        self.steps.append({"core": core, "text": text,
                           "new_facets": sorted(facets - self.horizon)[:8]})
        self.horizon |= facets

    def anchor(self) -> Set[str]:
        return self.origin if self.mode == "seed" else self.horizon

    def report(self) -> Dict[str, Any]:
        return {"seed": self.seed, "mode": self.mode, "steps": len(self.seen),
                "path": list(self.seen), "horizon": len(self.horizon)}

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(
            {"seed": self.seed, "mode": self.mode, "seen": self.seen,
             "steps": self.steps, "horizon": sorted(self.horizon),
             "origin": sorted(self.origin)},
            ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Trace":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        t = cls(seed=d.get("seed", ""), mode=d.get("mode", "path"))
        t.seen = list(d.get("seen", []))
        t.steps = list(d.get("steps", []))
        t.horizon = set(d.get("horizon", ()))
        t.origin = set(d.get("origin", ()))
        return t


def _facets(store: Any, core: str) -> Set[str]:
    labels = getattr(store, "source_labels", set()) or set()
    return {f for f in (store.crosses.get(core) or {}) if f not in labels}


def walk(
    store: Any,
    seed: str,
    *,
    mode: str = "path",
    steps: int = 12,
    trace: Optional[Trace] = None,
) -> Trace:
    """Follow the store from ``seed``, recording the path as it goes.

    Passing an existing trace RESUMES it: the horizon it already carries is
    the anchor, so a walk stopped and picked up later continues from what it
    knows rather than from the seed. That is the whole reason the path is a
    value and not a local variable.
    """
    from .consensus_store import ja_consensus_ask

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected {MODES}")
    t = trace or Trace(seed=seed, mode=mode, origin=_facets(store, seed))
    t.mode = mode
    cur = t.seen[-1] if t.seen else seed
    if t.seen:
        # Resuming: step off the last core rather than re-reading it.
        cand = [f for f in _facets(store, cur)
                if f in store.crosses and f not in t.seen]
        if not cand:
            return t
        cur = _pick(store, cand, t)

    for _ in range(steps):
        out = ja_consensus_ask(store, cur)
        if out.get("verdict") != "ANSWER":
            break
        core = out.get("core")
        if core is None or core in t.seen:
            break
        fs = _facets(store, core)
        t.record(core, fs, out.get("text", ""))
        cand = [f for f in fs if f in store.crosses and f not in t.seen]
        if not cand:
            break
        cur = _pick(store, cand, t)
    return t


def _pick(store: Any, candidates: Sequence[str], t: Trace) -> str:
    """The next core. Deterministic, and sorted before scoring so a tie
    resolves the same way on every run."""
    ordered = sorted(candidates)
    if t.mode == "lex":
        return ordered[0]
    anchor = t.anchor()
    return max(ordered, key=lambda f: len(_facets(store, f) & anchor))


def export_view(
    root: Any,
    traces: Sequence["Trace"],
    *,
    max_nodes: int = 4000,
) -> Dict[str, Any]:
    """The real tree and the real walks, in a shape a viewer can draw.

    Deliberately a RECORDING, not a feed. A published page cannot reach a
    running process — the sandbox has no network — so anything claiming to
    show inference "live" would be showing an animation of nothing. What
    this exports is what actually happened: the tree that was built, and the
    path a walk really took through it, with each step's own read-out.

    Nodes are truncated at ``max_nodes`` and the real count is reported
    beside the drawn one, for the same reason the simulator does it: a
    federation of 1,600 leaves is drawable and one of 60 million is not, and
    quietly drawing a sample as if it were the whole thing is the failure
    this project keeps refusing.
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[List[int]] = []
    idx: Dict[str, int] = {}
    total = 0

    def add(node: Any, parent: Optional[int], depth: int) -> None:
        nonlocal total
        total += 1
        me = None
        if len(nodes) < max_nodes:
            me = len(nodes)
            idx[node.name] = me
            nodes.append({"name": node.name, "depth": depth,
                          "leaf": node.is_leaf})
            if parent is not None:
                edges.append([parent, me])
        for child in node.children.values():
            add(child, me, depth + 1)

    add(root, None, 0)

    walks: List[Dict[str, Any]] = []
    for t in traces:
        walks.append({
            "seed": t.seed,
            "mode": t.mode,
            "steps": [{"core": s["core"], "text": s.get("text", "")[:120],
                       "node": idx.get(s["core"])}
                      for s in t.steps],
            "horizon": len(t.horizon),
        })
    return {
        "nodes": nodes, "edges": edges,
        "drawn_nodes": len(nodes), "real_nodes": total,
        "truncated": total > len(nodes),
        "walks": walks,
    }


def replay(store: Any, t: Trace) -> List[Dict[str, Any]]:
    """Read the path again against the current store.

    Two uses. It reproduces a walk exactly while the stores are unchanged,
    which is the determinism a walk should have. And after an ingest it
    shows which steps now read differently — a trace is a question about the
    store as much as a record of an answer.
    """
    from .consensus_store import ja_consensus_ask

    out: List[Dict[str, Any]] = []
    for i, core in enumerate(t.seen):
        res = ja_consensus_ask(store, core)
        was = t.steps[i].get("text", "") if i < len(t.steps) else ""
        now = res.get("text", "")
        out.append({"step": i, "core": core, "then": was, "now": now,
                    "changed": was != now})
    return out
