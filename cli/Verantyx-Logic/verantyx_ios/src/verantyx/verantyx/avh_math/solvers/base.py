from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

@dataclass
class SolverResult:
    status: str  # "proved", "disproved", "unknown", "error", "evaluated"
    method: str
    confidence: float
    answer: Optional[str] = None
    details: Optional[str] = None
    counterexample: Optional[Dict[str, Any]] = None
    proof: Optional[Dict[str, Any]] = None
    stats: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "confidence": self.confidence,
            "answer": self.answer,
            "details": self.details,
            "counterexample": self.counterexample,
            "proof": self.proof,
            "stats": self.stats,
            "warnings": self.warnings
        }

class BaseSolver(ABC):
    @abstractmethod
    def solve(self, query: str, context: Dict[str, Any] = None) -> SolverResult:
        """
        クエリを検証・評価する。
        contextには仮定(assumptions)、ドメイン情報、外部知識などが含まれる。
        """
        pass