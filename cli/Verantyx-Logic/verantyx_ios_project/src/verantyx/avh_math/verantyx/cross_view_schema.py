from __future__ import annotations

from typing import Any, Dict, List

_AXIS_ORDER = ["core", "syntax", "semantic", "assumption", "counterexample", "evidence", "proof", "retrieval"]


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def cross_to_view(cross: Any) -> Dict[str, Any]:
    cid = _get(cross, "id", "")
    domain = _get(cross, "domain", "unknown")
    task = _get(cross, "task", "unknown")
    core_formula = _get(cross, "core_formula", "")
    center_id = _get(cross, "center_id", "") or _get(cross, "center", "")

    assumptions = _get(cross, "assumptions", []) or []
    atoms = _get(cross, "atoms", []) or []
    candidates = _get(cross, "candidate_formulas", None)
    if candidates is None:
        candidates = _get(cross, "candidates", []) or []

    raw_nodes = _get(cross, "nodes", []) or []
    raw_edges = _get(cross, "edges", []) or []

    nodes: List[Dict[str, Any]] = []
    for n in raw_nodes:
        nid = _get(n, "id", "")
        axis = _get(n, "axis", "evidence") or "evidence"
        title = _get(n, "title", nid)
        tags = _get(n, "tags", []) or []
        content = _get(n, "content", {}) or {}
        lane = _AXIS_ORDER.index(axis) if axis in _AXIS_ORDER else len(_AXIS_ORDER)
        nodes.append({
            "id": nid,
            "axis": axis,
            "title": title,
            "tags": tags,
            "content": content,
            "is_center": bool(center_id and nid == center_id),
            "lane": lane,
        })

    edges: List[Dict[str, Any]] = []
    for e in raw_edges:
        src = _get(e, "source", "") or _get(e, "src", "")
        tgt = _get(e, "target", "") or _get(e, "dst", "")
        kind = _get(e, "kind", "mentions") or "mentions"
        weight = float(_get(e, "weight", 1.0) or 1.0)
        note = _get(e, "note", "") or ""
        if src and tgt:
            edges.append({
                "source": src,
                "target": tgt,
                "kind": kind,
                "weight": weight,
                "note": note,
            })

    return {
        "cross": {
            "id": cid,
            "domain": domain,
            "task": task,
            "core_formula": core_formula,
            "assumptions": assumptions,
            "atoms": atoms,
            "candidates": candidates,
            "center_id": center_id,
        },
        "nodes": nodes,
        "edges": edges,
    }
