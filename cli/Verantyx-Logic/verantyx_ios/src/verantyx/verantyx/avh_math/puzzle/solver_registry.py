from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Type
import re

@dataclass
class SolverMeta:
    id: str
    domain: str
    description: str
    triggers: List[str]  # Regex patterns or keywords
    cost_level: int      # 1: Light, 2: Medium, 3: Heavy
    timeout_ms: int      # Default timeout
    required_inputs: List[str] # e.g. ["formula", "atoms"]

class SolverRegistry:
    _solvers: Dict[str, SolverMeta] = {}
    _implementations: Dict[str, Type] = {}

    @classmethod
    def register(cls, meta: SolverMeta):
        def wrapper(solver_cls):
            cls._solvers[meta.id] = meta
            cls._implementations[meta.id] = solver_cls
            return solver_cls
        return wrapper

    @classmethod
    def get_solver_class(cls, solver_id: str) -> Type:
        return cls._implementations.get(solver_id)

    @classmethod
    def find_best_solver(cls, query: str, domain_hint: str = None) -> List[str]:
        """
        クエリとドメインヒントに基づいて、適切なソルバーIDのリストを優先度順に返す。
        """
        candidates = []
        
        # 1. Domain Match (Highest Priority)
        if domain_hint:
            for sid, meta in cls._solvers.items():
                if meta.domain == domain_hint:
                    candidates.append((sid, 100)) # High score

        # 2. Trigger Match
        for sid, meta in cls._solvers.items():
            for trigger in meta.triggers:
                if re.search(trigger, query, re.IGNORECASE):
                    # Already added by domain match?
                    if not any(c[0] == sid for c in candidates):
                        candidates.append((sid, 50))
                    break
        
        # Sort by score descending, then cost ascending
        candidates.sort(key=lambda x: (x[1], -cls._solvers[x[0]].cost_level), reverse=True)
        return [c[0] for c in candidates]

    @classmethod
    def get_meta(cls, solver_id: str) -> SolverMeta:
        return cls._solvers.get(solver_id)
