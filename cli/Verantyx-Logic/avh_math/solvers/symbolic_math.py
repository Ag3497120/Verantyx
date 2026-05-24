# avh_math/solvers/symbolic_math.py
from __future__ import annotations
import re
from typing import List, Dict, Any, Optional
import sympy
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

class SymbolicSolver:
    def __init__(self):
        self.transformations = (standard_transformations + (implicit_multiplication_application,))

    def _normalize_expr_str(self, s: str) -> str:
        # Normalize for SymPy
        s = s.replace("−", "-").replace("÷", "/")
        s = re.sub(r"\s+", "", s)
        return s

    def solve_choice_problem(self, query: str, candidates: List[str]) -> Dict[str, Any]:
        """
        Derive formula from keywords and match against candidates.
        """
        # Keyword mapping for common math formulas
        known_formulas = {
            r"対称行列.*(次元|独立)": "n*(n+1)/2",
            r"symmetric.*matrix.*(dimension|independent)": "n*(n+1)/2",
            r"交代行列.*(次元|独立)": "n*(n-1)/2",
            r"skew.*symmetric.*(dimension|independent)": "n*(n-1)/2",
            r"トレース.*0": "n*n - 1",
        }

        target_expr_str = None
        for pat, expr in known_formulas.items():
            if re.search(pat, query, re.IGNORECASE):
                target_expr_str = expr
                break
        
        if not target_expr_str:
            return {"status": "unknown", "reason": "No symbolic pattern matched."}

        try:
            target_expr = parse_expr(target_expr_str, transformations=self.transformations)
        except Exception as e:
            return {"status": "error", "reason": f"Target formula parse error: {e}"}

        matches = []
        for cand in candidates:
            # Strip labels
            cand_clean = re.sub(r"^[A-D]\s*[\.:]\s*", "", cand)
            cand_clean = self._normalize_expr_str(cand_clean)
            
            try:
                cand_expr = parse_expr(cand_clean, transformations=self.transformations)
                # Mathematical equivalence check
                if sympy.simplify(target_expr - cand_expr) == 0:
                    matches.append(cand)
            except Exception:
                continue

        if matches:
            return {
                "status": "solved",
                "answer": ", ".join(matches),
                "details": {"formula": target_expr_str, "method": "symbolic_match"}
            }
        
        return {"status": "no_match", "reason": "Candidates did not match derived formula."}

symbolic_solver = SymbolicSolver()

def solve_symbolic(query: str, candidates: List[str]) -> Dict[str, Any]:
    return symbolic_solver.solve_choice_problem(query, candidates)