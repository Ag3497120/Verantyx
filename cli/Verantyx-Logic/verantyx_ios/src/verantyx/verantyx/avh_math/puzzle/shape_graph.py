from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from avh_math.puzzle.normalize import normalize_text, normalize_formula, extract_quoted, detect_broken_arrow

ATOM_RE = re.compile(r"\b[pqrstuvwxyz]\b|\b[A-Z]\b")


@dataclass
class ShapeNode:
    id: str
    kind: str
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)


@dataclass
class ShapeGraph:
    raw: str
    norm: str
    quoted: List[str]
    core_formula: Optional[str]
    candidates: List[str]
    domain_hint: str
    atoms: List[str]
    notes: List[str] = field(default_factory=list)
    nodes: List[ShapeNode] = field(default_factory=list)
    edges: List[Tuple[str, str, str]] = field(default_factory=list)


def guess_domain_from_shapes(core: Optional[str], text_norm: str) -> str:
    if core:
        if "[]" in core or "<>" in core:
            return "modal_logic"
        if any(op in core for op in ("->", "<->", "&", "|", "~")):
            return "propositional_logic"
        if "dim" in core.lower() or "sym(" in core.lower() or "matrix" in text_norm.lower():
            return "linear_algebra"
    t = text_norm.lower()
    if "kripke" in t or "様相" in t:
        return "modal_logic"
    if "命題" in t or "tautology" in t:
        return "propositional_logic"
    if "行列" in t or "対称" in t:
        return "linear_algebra"
    return "unknown"


def extract_atoms(formulas: List[str]) -> List[str]:
    s = " ".join(formulas)
    atoms = sorted(set([m.group(0) for m in ATOM_RE.finditer(s)]))
    return atoms


def build_shape_graph(text: str) -> ShapeGraph:
    raw = text or ""
    norm = normalize_text(raw)
    q = extract_quoted(norm)

    notes: List[str] = []
    candidates: List[str] = []

    if q:
        for s in q:
            f = normalize_formula(s)
            if f:
                candidates.append(f)
        notes.append(f"[D0] quoted_formulas={len(candidates)}")
    else:
        notes.append("[D0] no_quoted_formula")
        hits = re.findall(r"(\[\][^\s]+(?:->|\&|\||<->)[^\s]+)", norm)
        hits += re.findall(r"(\([^()]{1,120}\)->\([^()]{1,120}\))", norm)
        for h in hits[:5]:
            candidates.append(normalize_formula(h))

    core = candidates[0] if candidates else None
    if core and detect_broken_arrow(core):
        notes.append("[D1] broken_arrow_detected")

    domain = guess_domain_from_shapes(core, norm)
    atoms = extract_atoms([c for c in candidates if c])

    g = ShapeGraph(
        raw=raw,
        norm=norm,
        quoted=q,
        core_formula=core,
        candidates=candidates if candidates else [],
        domain_hint=domain,
        atoms=atoms,
        notes=notes,
    )

    g.nodes.append(ShapeNode(id="input", kind="input_text", text=raw))
    g.nodes.append(ShapeNode(id="norm", kind="normalized_text", text=norm))
    if core:
        g.nodes.append(ShapeNode(id="core", kind="core_formula", text=core, meta={"domain": domain}))
        g.edges.append(("input", "normalizes_to", "norm"))
        g.edges.append(("norm", "extracts_core", "core"))

    for i, c in enumerate(g.candidates[:10]):
        cid = f"cand_{i+1}"
        g.nodes.append(ShapeNode(id=cid, kind="candidate_formula", text=c))
        g.edges.append(("core" if core else "norm", "has_candidate", cid))

    return g
