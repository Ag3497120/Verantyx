import json
import re
from avh_math.recognizers.base import BaseSolver, SolverResult

from avh_math.puzzle.solver_registry import SolverRegistry, SolverMeta

@SolverRegistry.register(SolverMeta(
    id="format:schema",
    domain="format_check",
    description="JSON/Email/Regex Format Validation",
    triggers=[r"json", r"email", r"regex", r"^\{.*\}$"],
    cost_level=1,
    timeout_ms=50,
    required_inputs=["formula"]
))
class FormatSolver(BaseSolver):
    def solve(self, query: str, context: Dict[str, Any] = None) -> SolverResult:
        # ... (既存のsolve) ...
        
        if query.strip().startswith("{") and query.strip().endswith("}"):
            try:
                json.loads(query)
                return SolverResult("proved", "json_validation", 1.0, details="Valid JSON")
            except json.JSONDecodeError as e:
                return SolverResult("disproved", "json_validation", 1.0, details=f"Invalid JSON: {e}")
        
        # Email check
        if "@" in query:
            if re.match(r"[^@]+@[^@]+\.[^@]+", query):
                return SolverResult("proved", "email_validation", 1.0, details="Valid Email format")
            return SolverResult("disproved", "email_validation", 1.0, details="Invalid Email format")

        return SolverResult("unknown", "format_check", 0.0)
