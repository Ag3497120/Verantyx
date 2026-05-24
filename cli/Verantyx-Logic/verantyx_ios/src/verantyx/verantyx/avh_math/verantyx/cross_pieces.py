from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Piece:
    kind: str  # kb | proof | counterexample | assumption | candidate
    title: str
    content: Dict[str, Any]
    links: List[str]


@dataclass
class CrossPieces:
    cross_id: str
    domain: str
    core_formula: str
    atoms: List[str]
    assumptions: List[str]
    syntax_formulas: List[str]
    shape_features: Dict[str, Any]
    parse_notes: List[str]
    context_text: str


def extract_pieces(cross: Dict[str, Any]) -> List[Piece]:
    pieces: List[Piece] = []
    for a in (cross.get("assumptions") or []):
        pieces.append(Piece(kind="assumption", title=a, content={"assumption": a}, links=[]))

    core = cross.get("core_formula") or ""
    if core:
        pieces.append(Piece(kind="candidate", title="core_formula", content={"formula": core}, links=[]))

    for axis in ["syntax_nodes", "semantic_nodes", "counterexample_nodes", "evidence_nodes"]:
        for n in (cross.get(axis) or []):
            c = n.get("content") or {}
            if "id" in c:
                pieces.append(Piece(kind="kb", title=c.get("title", "kb"), content=c, links=c.get("links", []) or []))
            if axis == "counterexample_nodes" and c:
                pieces.append(Piece(kind="counterexample", title=c.get("title", "cex"), content=c, links=[]))

    return pieces


def extract_pieces_v2(cross: Dict[str, Any]) -> CrossPieces:
    meta = cross.get("meta", {}) or {}
    domain = (cross.get("domain") or meta.get("domain") or "unknown")
    core = (cross.get("core_formula") or meta.get("core_formula") or "").strip()

    atoms = meta.get("atoms") or []
    if not isinstance(atoms, list):
        atoms = []

    assumptions: List[str] = []
    for n in (cross.get("assumption_nodes") or []):
        c = (n.get("content") or {})
        tag = c.get("tag") or c.get("assumption") or ""
        if tag:
            assumptions.append(str(tag))

    syntax_formulas: List[str] = []
    for n in (cross.get("syntax_nodes") or []):
        c = (n.get("content") or {})
        f = c.get("formula") or ""
        if f:
            syntax_formulas.append(str(f).strip())

    evidence = (cross.get("evidence_nodes") or [])
    shape_features: Dict[str, Any] = {}
    parse_notes: List[str] = []
    context_text = ""
    for n in evidence:
        c = (n.get("content") or {})
        if c.get("shape_features"):
            shape_features.update(c.get("shape_features") or {})
        if c.get("parse_notes"):
            parse_notes.extend(list(c.get("parse_notes") or []))
        if c.get("context_text") and not context_text:
            context_text = str(c.get("context_text"))

    return CrossPieces(
        cross_id=cross.get("cross_id") or meta.get("cross_id") or "",
        domain=domain,
        core_formula=core,
        atoms=atoms,
        assumptions=sorted(set(assumptions)),
        syntax_formulas=sorted(set(syntax_formulas)),
        shape_features=shape_features,
        parse_notes=parse_notes,
        context_text=context_text,
    )


def assemble_candidates(pieces: List[Piece]) -> Dict[str, Any]:
    kb_ids = []
    for p in pieces:
        if p.kind == "kb":
            eid = p.content.get("id")
            if eid:
                kb_ids.append(eid)
    return {"kb_ids": sorted(set(kb_ids))}
