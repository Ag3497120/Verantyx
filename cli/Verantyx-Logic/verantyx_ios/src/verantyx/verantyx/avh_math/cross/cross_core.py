from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json
import os
from datetime import datetime
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.answer_types.query_type import QueryType
from avh_math.answer_types.problem_type import ProblemType

@dataclass
class ReasoningCross:
    # 1. Core Axis: 解くべき本質的な問い（全体式）
    core_formula: Optional[str] = None
    
    # 2. Syntax Axis: 構文上の構成要素（部分式、トークン）
    syntax_nodes: List[str] = field(default_factory=list)
    
    # 3. Assumption Axis: 前提条件（反射性、推移性、ドメイン制約）
    assumptions: List[str] = field(default_factory=list)
    
    # 4. Semantic Axis: 真理性、意味論的な評価結果
    semantics: Dict[str, Any] = field(default_factory=dict)
    
    # 5. Counterexample Axis: 反例、破綻の具体的証明
    counterexamples: List[Dict[str, Any]] = field(default_factory=list)
    
    # 6. Evidence Axis: 根拠となったKB IDやText-Crossの類似度
    # 形式: {"id": str, "source": str, "confidence": float, "role": str, "status": str}
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    # 推論タスク (check_validity, find_counterexample, etc.)
    task: Optional[str] = None
    
    # 決定打: 検証対象として確定した純粋な式 (Natural language removed)
    verified_formula: Optional[str] = None

    # 7. Simulation Axis: 推論確定前の動的評価結果
    simulation: List[Dict[str, Any]] = field(default_factory=list)

    # 8. Collection Axis: 集合検証のメタデータと結果
    query_type: QueryType = QueryType.SINGLE
    problem_type: ProblemType = ProblemType.VALIDITY_CHECK
    candidates: List[str] = field(default_factory=list)
    collection_results: List[Dict[str, Any]] = field(default_factory=list)
    atoms: List[str] = field(default_factory=list)

    # メタ情報
    status: ReasoningStatus = ReasoningStatus.SILENT
    domain: str = "unknown"
    strategy: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def record_state(self, status: ReasoningStatus, payload: Any = None):
        """推論の途中経過を履歴として保存する"""
        if "history" not in self.metadata:
            self.metadata["history"] = []
        self.metadata["history"].append({
            "status": status.value,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "domain": self.domain,
            "strategy": self.strategy,
            "core": self.core_formula,
            "syntax": self.syntax_nodes,
            "assumption": self.assumptions,
            "semantic": self.semantics,
            "counterexample": self.counterexamples,
            "evidence": self.evidence,
            "query_type": self.query_type.value,
            "problem_type": self.problem_type.value,
            "candidates": self.candidates,
            "collection_results": self.collection_results,
            "atoms": self.atoms,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ReasoningCross':
        cross = cls(
            status=ReasoningStatus.from_str(d.get("status", "silent")),
            domain=d.get("domain", "unknown"),
            strategy=d.get("strategy", "default"),
            core_formula=d.get("core"),
            syntax=d.get("syntax", []),
            assumptions=d.get("assumption", []),
            semantics=d.get("semantic", {}),
            counterexamples=d.get("counterexample", []),
            evidence=d.get("evidence", []),
            atoms=d.get("atoms", []),
            metadata=d.get("metadata", {}),
            timestamp=d.get("timestamp", "")
        )
        # 後方互換性のため、フィールドが存在しない場合はデフォルト値を使用
        if "query_type" in d:
            try:
                cross.query_type = QueryType(d["query_type"])
            except ValueError:
                cross.query_type = QueryType.SINGLE
        
        if "problem_type" in d:
            try:
                cross.problem_type = ProblemType(d["problem_type"])
            except ValueError:
                cross.problem_type = ProblemType.VALIDITY_CHECK
        
        if "candidates" in d:
            cross.candidates = d["candidates"]
            
        if "collection_results" in d:
            cross.collection_results = d["collection_results"]
            
        return cross

    def save_to_jsonl(self, filepath: str):
        if os.environ.get("AVH_READONLY_DB", "").strip() == "1":
            return
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
