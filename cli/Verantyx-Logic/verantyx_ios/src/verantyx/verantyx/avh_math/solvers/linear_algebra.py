# avh_math/solvers/linear_algebra.py
import re
from typing import Dict, Any
import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
from avh_math.recognizers.base import BaseSolver, SolverResult

class LinearAlgebraSolver(BaseSolver):
    def __init__(self):
        self.transformations = (standard_transformations + (implicit_multiplication_application,))
        self.patterns = {
            r"( 対称|交代|歪対称)行列.*(次元|成分|数)": 0.95,
            r"実?n次.*対称行列": 0.95,
            r"independent.*component": 0.95,
            r"symmetric.*matrix.*(dimension|component)": 0.95,
            r"trace.*(zero|0)": 0.8,
            r"eigenvalue": 0.8,
            r"determinant": 0.8,
            r"rank": 0.8
        }
        self.formulas = {
            r"( 対称|symmetric).*行列.*(次元|成分|数|dimension|component)": "n*(n+1)/2",
            r"(交代|skew|歪対称).*行列.*(次元|成分|数|dimension|component)": "n*(n-1)/2",
            r"trace.*(zero|0)": "n*n - 1",
        }

    def can_handle(self, query: str, spec: Dict[str, Any]) -> float:
        if spec.get("domain") in ["linear_algebra", "matrix_theory"]:
            return 1.0
            
        max_score = 0.0
        for pat, score in self.patterns.items():
            if re.search(pat, query, re.IGNORECASE):
                max_score = max(max_score, score)
        return max_score

    def solve(self, query: str, spec: Dict[str, Any], limits: Dict[str, Any]) -> SolverResult:
        target_expr_str = None
        for pat, expr in self.formulas.items():
            if re.search(pat, query, re.IGNORECASE):
                target_expr_str = expr
                break

        # If query patterns fail, try to infer from candidates (formula-like input).
        if not target_expr_str:
            candidates = spec.get("candidates", []) or []
            for cand in candidates:
                c = re.sub(r"\s+", "", str(cand))
                if re.search(r"dimSym\(", c, re.IGNORECASE):
                    target_expr_str = "n*(n+1)/2"
                    break
                if re.search(r"dimSkew\(", c, re.IGNORECASE):
                    target_expr_str = "n*(n-1)/2"
                    break
                if re.search(r"dimM\(", c, re.IGNORECASE):
                    target_expr_str = "n*n"
                    break
        
        if not target_expr_str:
            return SolverResult("unknown", "Formula not found", 0.1)

        try:
            target_expr = parse_expr(target_expr_str, transformations=self.transformations)
        except Exception as e:
            return SolverResult("unknown", f"Formula parse error: {e}", 0.0)

        candidates = spec.get("candidates", [])
        if not candidates:
             return SolverResult("likely_true", f"Derived formula: {target_expr_str}", 0.8)

        # Match against candidates
        matches = []
        results = []
        for cand in candidates:
            # Basic cleanup
            cand_clean = re.sub(r"^[A-D]\s*[\.:]\s*", "", cand)
            cand_clean = cand_clean.replace("\n", "").replace(" ", "")
            
            is_match = False
            try:
                cand_expr = parse_expr(cand_clean, transformations=self.transformations)
                if sympy.simplify(target_expr - cand_expr) == 0:
                    is_match = True
            except:
                pass
            
            if is_match:
                matches.append(cand)
                results.append({"formula": cand, "status": "proved"})
            else:
                results.append({"formula": cand, "status": "disproved"})

        if matches:
            return SolverResult(
                status="proved",
                answer=f"Verified Valid: {', '.join(matches)}",
                confidence=1.0,
                evidence={
                    "formula": target_expr_str, 
                    "method": "symbolic_match",
                    "results": results # Engine uses this
                }
            )

        return SolverResult(
            status="disproved", 
            answer="No candidates matched the derived formula.", 
            confidence=0.9,
            evidence={"expected": target_expr_str}
        )
