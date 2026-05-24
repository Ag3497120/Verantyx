from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from avh_math.verantyx.cross import VerantyxCross, CrossNode
from avh_math.verantyx.cross_graph import canonical_cross_id, build_cross_links
from avh_math.verantyx.db_adapter import entry_to_nodes, normalize_entry
from avh_math.verantyx.cross_assembler import enrich_cross_with_pieces
from avh_math.input_pipeline import build_input_spec_v2, decompose_text


def _mk_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


def build_cross(
    text: str,
    knowledge_db: Dict[str, Any],
    *,
    domain_hint: Optional[str] = None,
    task_hint: Optional[str] = None,
    text_cross_hint_min_score: Optional[float] = None,
    db_entries: Optional[list[Dict[str, Any]]] = None,
) -> VerantyxCross:
    d = decompose_text(
        text,
        text_cross_hint_min_score=(
            text_cross_hint_min_score if text_cross_hint_min_score is not None else 0.25
        ),
    )

    # 決定打：辞書（失敗時）が返された場合の処理
    if isinstance(d, dict):
        from avh_math.input_pipeline import Decomposed
        d = Decomposed(
            domain=d.get("domain", "unknown"),
            core_formula=None,
            candidates=d.get("candidates", []),
            assumptions=[],
            atoms=[],
            evidence=d,
            audit=d.get("audit", [])
        )

    domain = domain_hint or d.domain or "unknown"
    task = task_hint or "unknown_task"

    core_formula = d.core_formula or (d.candidates[0] if d.candidates else "")

    cross_id = canonical_cross_id(
        domain=domain,
        task=task,
        core_formula=core_formula,
        assumptions=list(d.assumptions),
        atoms=list(d.atoms),
    )

    cross = VerantyxCross(
        cross_id=cross_id,
        created_at=time.time(),
        source_text=text,
        domain=domain,
        task=task,
        core_formula=core_formula,
        assumptions=list(d.assumptions),
        atoms=list(d.atoms),
    )
    if core_formula:
        cross.core_node = CrossNode(
            id=f"{cross_id}__core",
            axis="core",
            title="core_formula",
            content={"formula": core_formula},
            tags=["axis:core"],
            links=[],
        )

    for i, a in enumerate(d.assumptions):
        cross.assumption_nodes.append(
            CrossNode(
                id=f"{cross_id}__assume_{i}",
                axis="assumption",
                title=a,
                content={"assumption": a},
                tags=["axis:assumption"],
                links=[],
            )
        )

    for i, f in enumerate(d.candidates[:50]):
        cross.syntax_nodes.append(
            CrossNode(
                id=f"{cross_id}__syn_{i}",
                axis="syntax",
                title=f"candidate_{i+1}",
                content={"formula": f},
                tags=["axis:syntax"],
                links=[],
            )
        )

    evidence = d.evidence if isinstance(d.evidence, dict) else {}
    cross.evidence_nodes.append(
        CrossNode(
            id=f"{cross_id}__evidence_0",
            axis="evidence",
            title="evidence:input",
            content=evidence,
            tags=["axis:evidence"],
            links=[],
        )
    )
    tc_mapping = evidence.get("text_cross_mapping")
    if tc_mapping:
        cross.evidence_nodes.append(
            CrossNode(
                id=f"{cross_id}__evidence_text_cross_mapping",
                axis="evidence",
                title="evidence:text_cross_mapping",
                content=tc_mapping,
                tags=["axis:evidence", "source:text_cross_kb_cross", "text_cross:mapping"],
                links=[],
            )
        )
    # Text-cross KB lookup results -> dedicated evidence nodes
    tc_ids = evidence.get("text_cross_similar_ids")
    if tc_ids:
        cross.evidence_nodes.append(
            CrossNode(
                id=f"{cross_id}__evidence_text_cross_ids",
                axis="evidence",
                title="evidence:text_cross_similar_ids",
                content={"text_cross_similar_ids": tc_ids},
                tags=["axis:evidence", "source:text_cross_kb_cross"],
                links=[str(x) for x in tc_ids],
            )
        )
        try:
            from avh_math.text_cross.cross_kb_query import load_cross_by_id
        except Exception:
            load_cross_by_id = None
        if load_cross_by_id:
            # Expand a few similar crosses into evidence for debugging/inspection.
            for i, cid in enumerate(tc_ids[:3]):
                cross_obj = load_cross_by_id(str(cid))
                if not cross_obj:
                    continue
                meta = cross_obj.get("meta") or {}
                cross.evidence_nodes.append(
                    CrossNode(
                        id=f"{cross_id}__evidence_text_cross_{i}",
                        axis="evidence",
                        title="evidence:text_cross_match",
                        content={
                            "cross_id": cross_obj.get("cross_id"),
                            "tokens": meta.get("tokens") or [],
                            "structure_signature": meta.get("structure_signature") or [],
                            "notes": meta.get("notes") or [],
                        },
                        tags=["axis:evidence", "source:text_cross_kb_cross", "text_cross:expanded"],
                        links=[],
                    )
                )
    tc_hint = evidence.get("text_cross_hint")
    if tc_hint:
        cross.evidence_nodes.append(
            CrossNode(
                id=f"{cross_id}__evidence_text_cross_hint",
                axis="evidence",
                title="evidence:text_cross_hint",
                content={"text_cross_hint": tc_hint},
                tags=["axis:evidence", "source:text_cross_kb_cross"],
                links=[],
            )
        )
    tc_matches = evidence.get("text_cross_matches") or []
    for i, match in enumerate(tc_matches[:3]):
        meta = match.get("meta") or {}
        cross.evidence_nodes.append(
            CrossNode(
                id=f"{cross_id}__evidence_text_cross_match_{i}",
                axis="evidence",
                title="evidence:text_cross_match",
                content={
                    "cross_id": match.get("cross_id"),
                    "tokens": meta.get("tokens") or [],
                    "structure_signature": meta.get("structure_signature") or [],
                    "notes": meta.get("notes") or [],
                },
                tags=["axis:evidence", "source:text_cross_kb_cross", "text_cross:direct_match"],
                links=[],
            )
        )


    if domain == "modal_logic":
        cross.semantic_nodes.append(
            CrossNode(
                id=f"{cross_id}__semantic_0",
                axis="semantic",
                title="kripke_frame_slot",
                content={
                    "type": "kripke_frame",
                    "assumptions": d.assumptions,
                    "note": "Model search will instantiate small frames under assumptions.",
                },
                tags=["axis:semantic", "modal:kripke"],
                links=[],
            )
        )
    elif domain == "propositional_logic":
        cross.semantic_nodes.append(
            CrossNode(
                id=f"{cross_id}__semantic_0",
                axis="semantic",
                title="truth_table_slot",
                content={"type": "truth_table", "atoms": d.atoms},
                tags=["axis:semantic", "prop:truth_table"],
                links=[],
            )
        )
    else:
        cross.semantic_nodes.append(
            CrossNode(
                id=f"{cross_id}__semantic_0",
                axis="semantic",
                title="semantic_slot",
                content={"type": "unknown", "note": "No semantic backend bound yet."},
                tags=["axis:semantic"],
                links=[],
            )
        )

    cross.boundary_signature = {
        "domain": domain,
        "assumptions": sorted(list(set(d.assumptions))),
        "core_formula": core_formula,
        "candidate_count": len(d.candidates),
    }
    cross.meta["audit"] = list(d.audit)
    cross.meta["atoms"] = list(d.atoms)

    # Optional: attach DB entries as cross nodes using the unified adapter.
    # This keeps the existing pipeline intact and only enriches the cross.
    if db_entries:
        for i, raw in enumerate(db_entries):
            entry = normalize_entry(raw)
            prefix = f"{cross_id}__db_{i:04d}"
            for n in entry_to_nodes(entry, prefix):
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

    node_dicts = [n.to_dict() for n in cross.all_nodes()]
    cross.edges = [e.__dict__ for e in build_cross_links(node_dicts)]
    cross = enrich_cross_with_pieces(cross.to_dict())
    cross = VerantyxCross.from_dict(cross)

    return cross


def _v2_node_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build_cross_v2(text: str, knowledge_db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    spec = build_input_spec_v2(text)
    domain = spec.get("domain_hint") or "unknown"
    core = spec.get("core_formula") or ""

    cross: Dict[str, Any] = {
        "cross_id": f"cross_{domain}_{uuid.uuid4().hex[:10]}",
        "domain": domain,
        "task": "solve",
        "core_id": "core",
        "core_formula": core,
        "syntax_nodes": [],
        "semantic_nodes": [],
        "assumption_nodes": [],
        "counterexample_nodes": [],
        "evidence_nodes": [],
        "edges": [],
        "meta": {
            "input_audit": spec.get("audit", []),
            "candidates_preview": spec.get("candidates", [])[:10],
        },
    }

    for f in (spec.get("candidates") or [])[:50]:
        cross["syntax_nodes"].append(
            {
                "id": _v2_node_id("syn"),
                "axis": "syntax",
                "title": "formula",
                "content": {"formula": f, "source": "quoted_or_fallback"},
                "links": [],
            }
        )

    cross["semantic_nodes"].append(
        {
            "id": _v2_node_id("sem"),
            "axis": "semantic",
            "title": "domain",
            "content": {"domain": domain},
            "links": [],
        }
    )

    for n in cross["syntax_nodes"]:
        cross["edges"].append({"source": "core", "target": n["id"], "rel": "has_syntax"})
    for n in cross["semantic_nodes"]:
        cross["edges"].append({"source": "core", "target": n["id"], "rel": "has_semantics"})

    return cross
