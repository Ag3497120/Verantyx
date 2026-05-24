from typing import Dict, Any
from avh_math.recognizers.base import BaseSolver, SolverResult
from avh_math.puzzle.solver_registry import SolverRegistry, SolverMeta

@SolverRegistry.register(SolverMeta(
    id="cite:extract",
    domain="citation_check",
    description="Verify claims against source text",
    triggers=[r"source", r"citation", r"reference", r"quote"],
    cost_level=2,
    timeout_ms=500,
    required_inputs=["formula", "context_text"]
))
class CitationSolver(BaseSolver):
    def solve(self, query: str, context: Dict[str, Any] = None) -> SolverResult:
        source_text = context.get("context_text", "") if context else ""
        if not source_text:
            return SolverResult("unknown", "citation_check", 0.0, details="No source text provided.")

        # Simple keyword matching for now (can be enhanced with embeddings/fuzzy match later)
        # Check if query keywords appear in source text
        keywords = [w for w in query.split() if len(w) > 4]
        found = [w for w in keywords if w.lower() in source_text.lower()]
        
        if len(found) / len(keywords) > 0.7:
             return SolverResult("proved", "citation_check", 0.8, details=f"Found keywords: {found}")
        
        return SolverResult("disproved", "citation_check", 0.5, details="Source text does not support the claim.")
