from dataclasses import dataclass, field, asdict
from typing import Dict, Any

from .node import TextCrossNode


@dataclass
class TextDecompositionCross:
    cross_id: str
    raw_text: str
    nodes: Dict[str, TextCrossNode] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node_id: str, node: TextCrossNode) -> None:
        self.nodes[node_id] = node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cross_id": self.cross_id,
            "raw_text": self.raw_text,
            "nodes": {k: asdict(v) for k, v in self.nodes.items()},
            "meta": self.meta,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TextDecompositionCross":
        cross = TextDecompositionCross(
            cross_id=d.get("cross_id", ""),
            raw_text=d.get("raw_text", ""),
            meta=d.get("meta", {}) or {},
        )
        nodes = d.get("nodes") or {}
        for k, v in nodes.items():
            cross.nodes[k] = TextCrossNode(
                axis=v.get("axis", "token"),
                content=v.get("content", {}) or {},
                links=v.get("links") or [],
            )
        return cross
