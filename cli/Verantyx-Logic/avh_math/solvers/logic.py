# avh_math/solvers/logic.py
import re
from typing import Dict, Any
from .base import BaseSolver, SolverResult
from .prop_sat import solve_validity

class PropositionalSolver(BaseSolver):
    def can_handle(self, query: str, spec: Dict[str, Any]) -> float:
        # 候補式に様相演算子（[] or <>）が含まれていないか確認
        candidates = spec.get("candidates", [])
        if not candidates:
            return 0.0
            
        has_modal = any(any(m in c for m in ["[]", "<>", "□", "◇"]) for c in candidates)
        if not has_modal:
            return 0.9 # 命題論理の可能性が高い
        return 0.0

    def solve(self, query: str, spec: Dict[str, Any], limits: Dict[str, Any]) -> SolverResult:
        candidates = spec.get("candidates", [])
        results = []
        
        try:
            for f in candidates:
                is_valid, cex = solve_validity(f)
                status = "proved" if is_valid else "disproved"
                ans = "Valid" if is_valid else "Invalid"
                
                evidence = {"formula": f}
                if cex:
                    evidence["counterexample"] = {"Witness": {"assignment": cex}}
                
                results.append({
                    "formula": f,
                    "status": status,
                    "answer": ans,
                    "evidence": evidence
                })
            
            # 全体の結論を構築
            proved_count = sum(1 for r in results if r["status"] == "proved")
            if proved_count == len(results):
                final_status = "proved"
                final_ans = f"Verified Valid: {', '.join(candidates)}"
            else:
                final_status = "disproved"
                final_ans = "Some candidates are invalid."

            return SolverResult(
                status=final_status,
                answer=final_ans,
                confidence=1.0,
                evidence={"results": results, "method": "propositional_sat"}
            )
        except Exception as e:
            return SolverResult("unknown", f"SAT solver error: {e}", 0.0)
