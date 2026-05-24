from typing import Dict, List, Any
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus

class NLGVerifier:
    def verify(self, plan: Dict[str, Any], cross: ReasoningCross) -> List[str]:
        """
        Validate the narrative plan against the ReasoningCross.
        Returns a list of errors/violations.
        """
        errors = []
        
        # 1. Global Status Check
        if plan["status"] != cross.status.value:
            errors.append(f"Status mismatch: Plan says '{plan['status']}' but Cross is '{cross.status.value}'")

        # 2. Segment Checks
        for segment in plan["segments"]:
            tid = segment["template_id"]
            slots = segment["slots"]
            
            # --- Proved Assertions ---
            if tid.startswith("proved_") and cross.status != ReasoningStatus.PROVED:
                errors.append(f"Segment '{tid}' asserts proof, but Cross is not PROVED.")
            
            # --- Disproved Assertions ---
            if tid.startswith("disproved_") and cross.status != ReasoningStatus.DISPROVED:
                errors.append(f"Segment '{tid}' asserts disproof, but Cross is not DISPROVED.")

            # --- Fact Checking (Axiom ID) ---
            if tid == "proved_axiom":
                axiom_id = slots.get("axiom_id")
                # Ensure this ID exists in cross.evidence
                found = False
                for ev in cross.evidence:
                    if ev.get("id") == axiom_id or ev.get("kb_id") == axiom_id:
                        found = True
                        break
                if not found:
                    errors.append(f"Axiom ID '{axiom_id}' mentioned in text but not found in Cross evidence.")

            # --- Fact Checking (Counterexample existence) ---
            if tid == "disproved_counterexample":
                if not cross.counterexamples and not cross.metadata.get("simulation_counterexample"):
                    errors.append("Text mentions counterexample, but none found in Cross.")

        return errors
