# avh_math/solvers/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class SolverResult:
    status: str  # "proved" | "disproved" | "likely_true" | "likely_false" | "unknown"
    answer: str
    confidence: float  # 0.0 - 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    next_actions: List[str] = field(default_factory=list)

class BaseSolver:
    def can_handle(self, query: str, spec: Dict[str, Any]) -> float:
        """
        Returns a score (0.0 - 1.0) indicating how well this solver can handle the query.
        """
        return 0.0

    def solve(self, query: str, spec: Dict[str, Any], limits: Dict[str, Any]) -> SolverResult:
        """
        Solves the query and returns a SolverResult.
        """
        raise NotImplementedError
