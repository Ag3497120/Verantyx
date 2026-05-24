from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from avh_math.verantyx.cross import CrossNode, VerantyxCross
from avh_math.verantyx.cross_graph import canonical_cross_id, build_cross_links

_TEXT_KEYS = ("statement", "formula", "text", "rule", "content", "theorem", "axiom")


def _pick_text(entry: Dict[str, Any]) -> str:
    for key in _TEXT_KEYS:
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def normalize_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize any DB entry into a common schema.
    This does not infer meaning; it only maps fields defensively.
    """
    entry = dict(raw)
    entry_id = str(entry.get("id") or entry.get("key") or entry.get("_id") or "")
    domain = str(entry.get("domain") or entry.get("topic") or "unknown")
    kind = str(entry.get("kind") or entry.get("type") or "evidence")
    title = str(entry.get("title") or entry.get("name") or entry_id or kind)
    statement = _pick_text(entry)
    patterns = entry.get("patterns") or entry.get("pattern") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    refutation = entry.get("refutation") if "refutation" in entry else entry.get("counterexample")
    links = entry.get("links") or entry.get("related") or []
    if isinstance(links, str):
        links = [links]
    meta = entry.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {"meta": meta}

    return {
        "id": entry_id,
        "domain": domain,
        "kind": kind,
        "title": title,
        "statement": statement,
        "patterns": list(patterns),
        "refutation": refutation,
        "links": list(links),
        "meta": meta,
    }


def entry_to_nodes(entry: Dict[str, Any], prefix: str) -> List[CrossNode]:
    """
    Convert a normalized entry into cross nodes.
    """
    nodes: List[CrossNode] = []
    kind = entry.get("kind", "evidence")
    axis = {
        "definition": "semantic",
        "theorem": "semantic",
        "axiom": "assumption",
        "rule": "assumption",
        "lemma": "assumption",
        "counterexample_schema": "counterexample",
        "evidence": "evidence",
    }.get(kind, "evidence")

    base_id = entry.get("id") or f"{prefix}_{kind}"
    title = entry.get("title") or base_id
    statement = entry.get("statement") or ""
    patterns = entry.get("patterns") or []

    nodes.append(
        CrossNode(
            id=f"{prefix}::{base_id}",
            axis=axis,  # type: ignore[arg-type]
            title=title,
            content={
                "kind": kind,
                "statement": statement,
                "patterns": patterns,
                "kb_id": entry.get("id"),
            },
            tags=[f"kind:{kind}", f"domain:{entry.get('domain','unknown')}"],
            links=list(entry.get("links") or []),
        )
    )

    if entry.get("refutation"):
        nodes.append(
            CrossNode(
                id=f"{prefix}::{base_id}::refutation",
                axis="counterexample",
                title=f"refutation:{title}",
                content={"refutation": entry.get("refutation"), "kb_id": entry.get("id")},
                tags=["refutation"],
                links=list(entry.get("links") or []),
            )
        )

    return nodes


def build_cross_from_entries(
    entries: Iterable[Dict[str, Any]],
    *,
    source_text: str,
    domain_hint: Optional[str] = None,
    task: str = "solve",
    core_formula: str = "",
    assumptions: Optional[List[str]] = None,
    atoms: Optional[List[str]] = None,
) -> VerantyxCross:
    normalized = [normalize_entry(e) for e in entries]
    domain = domain_hint or (normalized[0]["domain"] if normalized else "unknown")
    assumptions = assumptions or []
    atoms = atoms or []
    cross_id = canonical_cross_id(domain, task, core_formula or "", assumptions, atoms)

    cross = VerantyxCross(
        cross_id=cross_id,
        created_at=time.time(),
        source_text=source_text,
        domain=domain,
        task=task,
        core_formula=core_formula or "",
        assumptions=list(assumptions),
        atoms=list(atoms),
    )

    if core_formula:
        cross.core_node = CrossNode(
            id=f"{cross_id}::core",
            axis="core",
            title="core_formula",
            content={"formula": core_formula},
            tags=["core"],
            links=[],
        )

    for i, entry in enumerate(normalized):
        prefix = f"{cross_id}::kb{i:04d}"
        nodes = entry_to_nodes(entry, prefix)
        for n in nodes:
            if n.axis == "semantic":
                cross.semantic_nodes.append(n)
            elif n.axis == "assumption":
                cross.assumption_nodes.append(n)
            elif n.axis == "counterexample":
                cross.counterexample_nodes.append(n)
            elif n.axis == "evidence":
                cross.evidence_nodes.append(n)
            else:
                cross.evidence_nodes.append(n)

    # edges from nodes (core assumed to be included)
    cross.edges = [e.__dict__ for e in build_cross_links([n.to_dict() for n in cross.all_nodes()])]
    cross.meta["entry_count"] = len(normalized)
    return cross
