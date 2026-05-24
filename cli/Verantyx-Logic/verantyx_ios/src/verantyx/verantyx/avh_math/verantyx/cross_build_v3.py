from __future__ import annotations

import hashlib
from typing import Dict, Any, List, Optional

from avh_math.input_pipeline_v3 import build_input_spec
from avh_math.shape_signature import shape_signature
from avh_math.kb_hint_match import guess_domain_and_assumptions
from avh_math.verantyx.shape_parser import parse_formula
from avh_math.verantyx.shape_ast import ast_to_dict


def canonical_cross_id(spec: Dict[str, Any]) -> str:
    key = (
        f"{spec.get('domain','')}|{spec.get('core_formula','')}|"
        f"{spec.get('cleaned_text','')[:3000]}"
    )
    h = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"cross_{spec.get('domain','unknown')}_{h}"


def build_cross_v3(
    text: str,
    *,
    kb_index: Optional[Dict[str, List[str]]] = None,
    kb_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sp = build_input_spec(text)
    sig = shape_signature(sp.cleaned_text, core_formula=sp.core_formula)
    spec = {
        "domain": sp.domain,
        "assumptions": sp.assumptions,
        "formulas": sp.formulas,
        "core_formula": sp.core_formula,
        "cleaned_text": sp.cleaned_text,
        "audit": sp.audit,
    }

    kb_domain = "unknown"
    kb_assumptions: List[str] = []
    kb_evidence_ids: List[str] = []
    if kb_index is not None and kb_meta is not None:
        kb_domain, kb_assumptions, kb_evidence_ids = guess_domain_and_assumptions(
            query_text=sp.cleaned_text,
            core_formula=sp.core_formula,
            index=kb_index,
            meta=kb_meta,
            max_ids=200,
        )

    domain = sp.domain
    if domain == "unknown" and kb_domain != "unknown":
        domain = kb_domain
    if domain == "unknown" and sig.domain_hint != "unknown":
        domain = sig.domain_hint

    cross_id = canonical_cross_id(spec)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    core_ast = None
    if sp.core_formula:
        try:
            core_ast = ast_to_dict(parse_formula(sp.core_formula))
        except Exception:
            core_ast = None

    nodes.append(
        {
            "id": "core",
            "axis": "core",
            "title": "core",
            "content": {"core_formula": sp.core_formula, "domain": domain, "ast": core_ast},
            "links": [],
        }
    )

    for i, f in enumerate(sp.formulas[:80]):
        nid = f"syn_{i:03d}"
        nodes.append(
            {"id": nid, "axis": "syntax", "title": "formula", "content": {"formula": f}, "links": []}
        )
        edges.append({"source": "core", "target": nid, "rel": "has_formula"})

    nodes.append(
        {
            "id": "sem_000",
            "axis": "semantic",
            "title": "domain",
            "content": {"domain": domain, "assumptions": sp.assumptions, "shape_features": sig.features},
            "links": [],
        }
    )
    edges.append({"source": "core", "target": "sem_000", "rel": "has_semantics"})

    assumptions = sorted(set((sp.assumptions or []) + (kb_assumptions or [])))
    for i, a in enumerate(assumptions):
        nodes.append(
            {
                "id": f"asm_{i:03d}",
                "axis": "assumption",
                "title": "assumption",
                "content": {"assumption": a},
                "links": [],
            }
        )
        edges.append({"source": "core", "target": f"asm_{i:03d}", "rel": "has_assumption"})

    nodes.append(
        {
            "id": "ev_000",
            "axis": "evidence",
            "title": "input_evidence",
            "content": {
                "context_text": sp.cleaned_text,
                "parse_notes": sp.audit,
                "shape_tags": sig.tags,
                "kb_evidence_ids": kb_evidence_ids,
            },
            "links": kb_evidence_ids,
        }
    )
    edges.append({"source": "core", "target": "ev_000", "rel": "has_evidence"})

    return {
        "cross_id": cross_id,
        "domain": domain,
        "task": "solve",
        "core_formula": sp.core_formula,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "audit": sp.audit,
            "assumptions": assumptions,
            "formula_count": len(sp.formulas),
            "candidates_preview": sp.formulas[:10],
            "kb_domain": kb_domain,
            "kb_evidence_ids": kb_evidence_ids,
            "shape_domain_hint": sig.domain_hint,
        },
    }
