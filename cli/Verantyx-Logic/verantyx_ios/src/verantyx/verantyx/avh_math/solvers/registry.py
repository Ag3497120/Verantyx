# avh_math/solvers/registry.py
from typing import List, Dict, Any
from avh_math.recognizers.base import BaseSolver, SolverResult

class SolverRegistry:
    def __init__(self):
        self.solvers: List[BaseSolver] = []

    def register(self, solver: BaseSolver):
        self.solvers.append(solver)

    def solve(self, query: str, spec: Dict[str, Any], limits: Dict[str, Any]) -> SolverResult:
        # 1. Calculate confidence score for each solver
        candidates = []
        for s in self.solvers:
            try:
                score = s.can_handle(query, spec)
                if score > 0:
                    candidates.append((score, s))
            except Exception as e:
                print(f"[SolverRegistry] Error in can_handle for {s.__class__.__name__}: {e}")

        # Sort by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)

        # 2. Try solvers in order
        best_result = None
        
        for score, solver in candidates:
            try:
                res = solver.solve(query, spec, limits)
                
                # If definitive, return immediately
                if res.status in ("proved", "disproved"):
                    return res
                
                # Keep the best non-definitive result
                if best_result is None or res.confidence > best_result.confidence:
                    best_result = res
            except Exception as e:
                print(f"[SolverRegistry] Error in {solver.__class__.__name__}: {e}")
                # 決定打：個別のソルバーが落ちても全体を ERROR にしない
                # 最低限の tentative 判定を生成して続行
                if best_result is None:
                    best_result = SolverResult(
                        status="tentative",
                        answer="Solver internal error (captured).",
                        confidence=0.1,
                        evidence={"error": str(e), "solver": solver.__class__.__name__}
                    )
                continue

        if best_result:
            return best_result

        return SolverResult(
            status="unknown",
            answer="No suitable solver found.",
            confidence=0.0
        )
