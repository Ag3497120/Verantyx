from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal

@dataclass
class SimulationNode:
    """Simulation Cross 内の構成要素（実行可能な部品）"""
    kind: Literal["axiom", "rule", "formula", "model", "counterexample", "assumption"]
    content: Any  # 式文字列、モデルオブジェクト、条件など
    source_id: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "content": str(self.content), # 安全のため文字列化
            "source_id": self.source_id,
            "confidence": self.confidence
        }

@dataclass
class SimulationResult:
    """シミュレーション実行結果"""
    status: Literal["proved", "disproved", "unknown"]
    confidence: float
    method: str
    details: Optional[str] = None
    counterexample: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "method": self.method,
            "details": self.details,
            "counterexample": self.counterexample
        }

@dataclass
class SimulationCross:
    """計算・検証専用の立体十字構造（仮想実験室）"""
    domain: str
    nodes: List[SimulationNode] = field(default_factory=list)
    results: List[SimulationResult] = field(default_factory=list)
    
    core_formula: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    
    def add_node(self, kind: str, content: Any, source_id: str = None, confidence: float = 0.0):
        self.nodes.append(SimulationNode(
            kind=kind, 
            content=content, 
            source_id=source_id, 
            confidence=confidence
        ))
        
        # 簡易的なインデックス更新
        if kind == "formula" and not self.core_formula:
            self.core_formula = str(content)
        elif kind == "assumption":
            self.assumptions.append(str(content))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "core_formula": self.core_formula,
            "assumptions": self.assumptions,
            "nodes": [n.to_dict() for n in self.nodes],
            "results": [r.to_dict() for r in self.results]
        }
