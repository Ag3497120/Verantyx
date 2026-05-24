from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from patch_proof import Patch

@dataclass
class CexDelta:
    add_assumption: str
    required_change: str                 # "add_edge" | "remove_edge" | "note"
    edge: Optional[Tuple[int, int]] = None
    why_breaks: str = ""

def delta_to_patch(delta_item: Dict[str, Any]) -> Patch:
    """
    counterexample_delta の1要素から Patch を組み立てる。
    MVP: add_edge のみ対応。
    """
    req = delta_item.get("required_change")
    edge = delta_item.get("edge")

    if req == "add_edge" and isinstance(edge, list) and len(edge) == 2:
        a, b = edge
        if isinstance(a, int) and isinstance(b, int):
            return Patch(add_edges=[(a, b)], remove_edges=[])
    return Patch(add_edges=[], remove_edges=[])

def explain_counterexample_delta(
    formula: str,
    counterexample: Dict[str, Any],
    repair_suggestions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    与えられた反例モデルが、提案された仮定を入れると「どこが壊れるか」を説明する。
    ここでは MVP として modal logic のフレーム性質の delta を扱う：
      - reflexive: 全 world に self-loop を要求
      - transitive: (a->b and b->c) implies (a->c)
      - symmetric: (a->b) implies (b->a)
      - euclidean: (a->b and a->c) implies (b->c)

    NOTE:
    - これは “反例を修正して仮定を満たす最小変更” を提示するだけ。
    - それにより formula が必ず valid になることまで証明するものではない（Phase 9 で別途検証）。
    """
    # Handle different key names for world count
    worlds = int(counterexample.get("n_worlds") or counterexample.get("worlds") or 0)
    edges = counterexample.get("edges", []) or []
    # Ensure edges are tuples of ints
    edge_set = set()
    for e in edges:
        if isinstance(e, (list, tuple)) and len(e) >= 2:
            edge_set.add((int(e[0]), int(e[1])))

    out: List[CexDelta] = []

    # helper
    def add(delta: CexDelta):
        out.append(delta)

    for s in (repair_suggestions or []):
        adds = s.get("add") or []
        for a in adds:
            if a == "assume:reflexive":
                # require self-loop for each world
                missing = [(i, i) for i in range(worlds) if (i, i) not in edge_set]
                if missing:
                    # MVP: suggest adding first missing self-loop
                    e = missing[0]
                    add(CexDelta(
                        add_assumption=a,
                        required_change="add_edge",
                        edge=e,
                        why_breaks=(
                            "Reflexivity requires wRw. Adding a self-loop forces □ to quantify over the current world; "
                            "many counterexamples to □A→A rely on having no wRw so □A can be vacuously true while A is false."
                        )
                    ))
                else:
                    add(CexDelta(
                        add_assumption=a,
                        required_change="note",
                        why_breaks="Counterexample already satisfies reflexivity; this repair would not break it via reflexivity delta."
                    ))

            elif a == "assume:symmetric":
                # require reverse edges
                missing_rev = [(b, a2) for (a2, b) in edge_set if (b, a2) not in edge_set]
                if missing_rev:
                    e = missing_rev[0]
                    add(CexDelta(
                        add_assumption=a,
                        required_change="add_edge",
                        edge=e,
                        why_breaks="Symmetry requires that every edge has a reverse edge; counterexamples often use one-way reachability."
                    ))
                else:
                    add(CexDelta(add_assumption=a, required_change="note", why_breaks="Already symmetric."))

            elif a == "assume:transitive":
                # require closure: if x->y and y->z then x->z
                needed = []
                for x, y in list(edge_set):
                    for y2, z in list(edge_set):
                        if y2 == y and (x, z) not in edge_set:
                            needed.append((x, z))
                if needed:
                    e = needed[0]
                    add(CexDelta(
                        add_assumption=a,
                        required_change="add_edge",
                        edge=e,
                        why_breaks="Transitivity forces reachability shortcuts; counterexamples that rely on missing shortcuts can collapse."
                    ))
                else:
                    add(CexDelta(add_assumption=a, required_change="note", why_breaks="Already transitive."))

            elif a == "assume:euclidean":
                # (a->b and a->c) -> (b->c)
                needed = []
                for a0, b in list(edge_set):
                    for a1, c in list(edge_set):
                        if a1 == a0 and (b, c) not in edge_set:
                            needed.append((b, c))
                if needed:
                    e = needed[0]
                    add(CexDelta(
                        add_assumption=a,
                        required_change="add_edge",
                        edge=e,
                        why_breaks="Euclidean property forces edges between successors; counterexamples using branching without closure may break."
                    ))
                else:
                    add(CexDelta(add_assumption=a, required_change="note", why_breaks="Already euclidean."))

            else:
                # Unknown assumption type — still give something useful
                add(CexDelta(
                    add_assumption=a,
                    required_change="note",
                    why_breaks="No structural delta rule implemented for this assumption yet."
                ))

    # serialize
    return [
        {
            "add_assumption": d.add_assumption,
            "required_change": d.required_change,
            "edge": list(d.edge) if d.edge else None,
            "why_breaks": d.why_breaks,
        }
        for d in out
    ]