"""A second tree, routed by surface conduction — beside `hierarchy`, not over it.

`hierarchy` is the original: it measured the 24-word ceiling and routes by
what sits ON the faces, which is exactly why it also measured 0/60 for
terms off them. This module keeps that ceiling and repeals its routing
consequence with `surface.route`. Two modules on purpose — the first
version of this file OVERWROTE `hierarchy.py`, which broke the
SOVEREIGN_BUILD fork and shipped one commit with a fork claim that was
false; the original is restored verbatim and this lives beside it.

The capacity law says one node distinguishes 24 words and a vocabulary V
therefore needs depth ~ log6(V/4) — layers are not a choice. What blocked
the tree was routing: an upper node routed 0/60 for words off its faces,
so descending the tree lost every question the faces did not happen to
carry. `surface.route` repealed that (0/52 -> 52/52 with conduction, ties
abstaining), and this module is the tree built on it. Measured on 36
statutes in two levels (6 groups x 6 laws), 127 probes each unique to one
law:

    descent correct     121 / 127  (95%)
    descent wrong         0 / 127
    abstained             6        (5 at the trunk, 1 at a branch, named)
    out-of-corpus         6 / 6 abstained
    per-probe cost      < 0.1ms after build

Grouping was ARBITRARY (sorted-name blocks) and the router still routes —
the stronger claim, since a considered grouping can only help.

    level 0   leaf sovereigns — one store per law, data-varied
    level 1+  routing nodes — six arms each, faces from `distinct_faces`,
              descent by `surface.route`

A routing node holds NO census and NO merged store. The trajectory
measured what pooling does (three domain sovereigns voted together:
answered 284 -> 208; cut-varied readings in one census: out-of-corpus
0 -> 8 wrong), so an upper node here is only a switch: it hands the
question DOWN, typed, and the leaf answers with its own gates. Layered,
never pooled — the tree is the staircase made literal.

## Typed descent

Every hop can abstain. `UNKNOWN_NO_ROUTE` carries WHERE the descent
stopped and which arms tied, because a reader repairing the tree needs to
know whether the miss was at the trunk or a branch. An invented term
abstains at the first hop (measured 6/6), which is the subject gate's
behaviour expressed as geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .surface import distinct_faces, route

#: Six arms per node — the geometry's own arity.
ARITY = 6


@dataclass
class Node:
    """One routing node: arms to children, faces to route by."""

    name: str
    children: Dict[str, Any] = field(default_factory=dict)   # arm -> Node|store
    faces: Dict[str, List[str]] = field(default_factory=dict)
    #: Aggregate facet profile per arm, used as the "store" a parent sees.
    profile: Dict[str, Dict[str, Dict[str, int]]] = field(default_factory=dict)

    def is_leaf_arm(self, arm: str) -> bool:
        return not isinstance(self.children.get(arm), Node)


def _merged_view(child: Any) -> Dict[str, Dict[str, int]]:
    """What a parent node sees of one arm: the crosses beneath it, summed.

    A VIEW for face-picking and conduction only — it never answers and
    never votes, so this is not the pooling the measurements forbid. The
    same distinction as witnesses: reading a merged surface is not holding
    a merged election.
    """
    if not isinstance(child, Node):
        return child
    out: Dict[str, Dict[str, int]] = {}
    for arm in child.children:
        for c, cr in _merged_view(child.children[arm]).items():
            dst = out.setdefault(c, {})
            for f, n in cr.items():
                dst[f] = dst.get(f, 0) + n
    return out


def build(leaves: Dict[str, Any], *, arity: int = ARITY,
          name: str = "root") -> Node:
    """Grow the tree bottom-up until one node holds everything.

    Grouping is by sorted name in blocks — deliberately arbitrary. Branch
    assignment is the top placement problem and choosing "good" groups by
    similarity would be clustering, which this project keeps refusing; the
    measurement below shows the router works even against arbitrary groups,
    which is the stronger claim. A better grouping can only help.
    """
    level: Dict[str, Any] = dict(leaves)
    depth = 0
    while len(level) > arity:
        names = sorted(level)
        nxt: Dict[str, Any] = {}
        for i in range(0, len(names), arity):
            block = names[i:i + arity]
            node = Node(name=f"L{depth}:{block[0]}..")
            node.children = {b: level[b] for b in block}
            node.profile = {b: _merged_view(level[b]) for b in block}
            node.faces = distinct_faces(node.profile)
            nxt[node.name] = node
        level = nxt
        depth += 1
    root = Node(name=name)
    root.children = dict(level)
    root.profile = {a: _merged_view(c) for a, c in level.items()}
    root.faces = distinct_faces(root.profile)
    return root


def descend(node: Node, term: str, *, trail: Optional[List[str]] = None
            ) -> Dict[str, Any]:
    """Route the term down to a leaf sovereign, or say where it stopped."""
    trail = list(trail or [])
    arm = route(node.profile, node.faces, term)
    if arm is None:
        return {"verdict": "UNKNOWN_NO_ROUTE", "stopped_at": node.name,
                "trail": trail,
                "note": "no arm's faces are reachable from this term's "
                        "surface, or two arms tied; descending further "
                        "would be a guess"}
    trail.append(arm)
    child = node.children[arm]
    if isinstance(child, Node):
        return descend(child, term, trail=trail)
    return {"verdict": "ROUTED", "leaf": arm, "trail": trail}
