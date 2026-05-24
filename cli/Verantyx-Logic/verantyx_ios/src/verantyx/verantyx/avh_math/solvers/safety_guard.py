from typing import Dict, Any
from avh_math.recognizers.base import BaseSolver, SolverResult
from avh_math.puzzle.solver_registry import SolverRegistry, SolverMeta

@SolverRegistry.register(SolverMeta(
    id="med:safety",
    domain="safety_check",
    description="Medical/Safety Non-Assertion Guard",
    triggers=[r"medical", r"diagnose", r"treatment", r"cure", r"legal advice"],
    cost_level=1,
    timeout_ms=10,
    required_inputs=["formula"]
))
class SafetyGuard(BaseSolver):
    def solve(self, query: str, context: Dict[str, Any] = None) -> SolverResult:
        # Block dangerous assertions
        dangerous_terms = ["diagnose", "cure", "prescribe", "guarantee", "definitely"]
        if any(t in query.lower() for t in dangerous_terms):
             return SolverResult(
                 "disproved", 
                 "safety_guard", 
                 1.0, 
                 details="Safety violation: Cannot provide definitive medical/legal advice.",
                 warnings=["Please consult a professional."]
             )
        
        return SolverResult("proved", "safety_guard", 1.0, details="Safety check passed (no restricted terms found).")
