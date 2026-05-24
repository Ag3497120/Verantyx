from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal
import hashlib
import json

AxisKind = Literal[
    "core",
    "syntax",
    "semantic",
    "assumption",
    "counterexample",
    "evidence",
    "kb",
    "proof",
    "meta",
]


@dataclass(frozen=True)
class CrossEdge:
    src: str
    dst: str
    rel: str  # supports / refutes / depends_on / similar / mentions
    weight: float = 1.0
    meta: Dict[str, Any] | None = None


def _stable_hash(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical_cross_id(
    domain: str,
    task: str,
    core_formula: str,
    assumptions: List[str],
    atoms: List[str],
) -> str:
    payload = {
        "domain": (domain or "unknown").strip().lower(),
        "task": (task or "unknown").strip().lower(),
        "core_formula": (core_formula or "").strip(),
        "assumptions": sorted(set([a.strip().lower() for a in (assumptions or [])])),
        "atoms": sorted(set([a.strip() for a in (atoms or [])])),
    }
    h = _stable_hash(payload)[:16]
    return f"cross_{payload['domain']}_{h}"


def build_cross_links(nodes: List[Dict[str, Any]]) -> List[CrossEdge]:
    edges: List[CrossEdge] = []
    by_axis: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        by_axis.setdefault(n.get("axis", "meta"), []).append(n)

    core_ids = [n["id"] for n in by_axis.get("core", []) if "id" in n]
    core_id = core_ids[0] if core_ids else None

    if core_id:
        for a in by_axis.get("assumption", []):
            edges.append(CrossEdge(src=a["id"], dst=core_id, rel="depends_on", weight=1.0))
        for s in by_axis.get("syntax", []):
            edges.append(CrossEdge(src=s["id"], dst=core_id, rel="mentions", weight=0.7))
        for ce in by_axis.get("counterexample", []):
            edges.append(CrossEdge(src=ce["id"], dst=core_id, rel="refutes", weight=1.0))
        for ev in by_axis.get("evidence", []):
            edges.append(CrossEdge(src=ev["id"], dst=core_id, rel="supports", weight=0.8))

    formula_to_ids: Dict[str, List[str]] = {}
    for n in nodes:
        c = n.get("content") or {}
        f = (c.get("formula") or c.get("statement") or "").strip()
        if f:
            formula_to_ids.setdefault(f, []).append(n["id"])
    for _, ids in formula_to_ids.items():
        if len(ids) >= 2:
            base = ids[0]
            for other in ids[1:]:
                edges.append(CrossEdge(src=base, dst=other, rel="similar", weight=0.4))

    uniq: Dict[tuple, CrossEdge] = {}
    for e in edges:
        k = (e.src, e.dst, e.rel)
        if k not in uniq:
            uniq[k] = e
    return list(uniq.values())
