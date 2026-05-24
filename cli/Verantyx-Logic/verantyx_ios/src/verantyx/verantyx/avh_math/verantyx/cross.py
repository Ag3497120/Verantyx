from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional

AxisKind = Literal["core", "syntax", "semantic", "assumption", "counterexample", "evidence"]


@dataclass
class CrossNode:
    id: str
    axis: AxisKind
    title: str
    content: Any
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CrossNode":
        return CrossNode(
            id=str(d.get("id", "")),
            axis=d.get("axis", "meta"),
            title=str(d.get("title", "")),
            content=d.get("content"),
            tags=list(d.get("tags") or []),
            links=list(d.get("links") or []),
        )

@dataclass
class VerantyxCross:
    cross_id: str
    created_at: float
    source_text: str

    # Core
    domain: str
    task: str
    core_formula: str
    assumptions: List[str] = field(default_factory=list)
    atoms: List[str] = field(default_factory=list)

    core_node: Optional[CrossNode] = None

    # Axes
    syntax_nodes: List[CrossNode] = field(default_factory=list)
    semantic_nodes: List[CrossNode] = field(default_factory=list)
    assumption_nodes: List[CrossNode] = field(default_factory=list)
    counterexample_nodes: List[CrossNode] = field(default_factory=list)
    evidence_nodes: List[CrossNode] = field(default_factory=list)

    # Summary signatures (boundary/canonical keys)
    boundary_signature: Dict[str, Any] = field(default_factory=dict)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def all_nodes(self) -> List[CrossNode]:
        out: List[CrossNode] = []
        if self.core_node:
            out.append(self.core_node)
        out.extend(self.syntax_nodes)
        out.extend(self.semantic_nodes)
        out.extend(self.assumption_nodes)
        out.extend(self.counterexample_nodes)
        out.extend(self.evidence_nodes)
        return out

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["core_node"] = self.core_node.to_dict() if self.core_node else None
        d["syntax_nodes"] = [n.to_dict() for n in self.syntax_nodes]
        d["semantic_nodes"] = [n.to_dict() for n in self.semantic_nodes]
        d["assumption_nodes"] = [n.to_dict() for n in self.assumption_nodes]
        d["counterexample_nodes"] = [n.to_dict() for n in self.counterexample_nodes]
        d["evidence_nodes"] = [n.to_dict() for n in self.evidence_nodes]
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "VerantyxCross":
        obj = VerantyxCross(
            cross_id=str(d.get("cross_id", "")),
            created_at=float(d.get("created_at", 0.0)),
            source_text=str(d.get("source_text", "")),
            domain=str(d.get("domain", "unknown")),
            task=str(d.get("task", "unknown")),
            core_formula=str(d.get("core_formula", "")),
            assumptions=list(d.get("assumptions") or []),
            atoms=list(d.get("atoms") or []),
        )
        core_node = d.get("core_node")
        if isinstance(core_node, dict):
            obj.core_node = CrossNode.from_dict(core_node)
        obj.syntax_nodes = [CrossNode.from_dict(x) for x in (d.get("syntax_nodes") or [])]
        obj.semantic_nodes = [CrossNode.from_dict(x) for x in (d.get("semantic_nodes") or [])]
        obj.assumption_nodes = [CrossNode.from_dict(x) for x in (d.get("assumption_nodes") or [])]
        obj.counterexample_nodes = [CrossNode.from_dict(x) for x in (d.get("counterexample_nodes") or [])]
        obj.evidence_nodes = [CrossNode.from_dict(x) for x in (d.get("evidence_nodes") or [])]
        obj.edges = list(d.get("edges") or [])
        obj.boundary_signature = dict(d.get("boundary_signature") or {})
        obj.meta = dict(d.get("meta") or {})
        return obj
