from typing import Dict, Any, List, Optional
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.nlg.templates_en import TEMPLATES_EN

class NarrativeSolver:
    def __init__(self):
        self.templates = TEMPLATES_EN

    def solve(self, cross: ReasoningCross) -> Dict[str, Any]:
        """
        Generate a structured narrative plan based on the ReasoningCross.
        """
        plan = {
            "status": cross.status.value,
            "segments": []
        }

        formula = cross.verified_formula or cross.core_formula or "(unknown formula)"
        
        # --- PROVED ---
        if cross.status == ReasoningStatus.PROVED:
            method = cross.semantics.get("method", "")
            
            # 1. Axiom Match
            if "axiom" in method or "kb_match" in method:
                # Find which axiom
                axiom_id = "unknown"
                axiom_desc = "an axiom"
                # Search evidence
                for ev in cross.evidence:
                    if ev.get("kind") in ("axiom", "injected_axiom", "kb_match"):
                        axiom_id = ev.get("id") or ev.get("kb_id") or "custom"
                        axiom_desc = ev.get("statement") or ev.get("formula") or "User provided axiom"
                        break
                
                self._add_segment(plan, "proved_axiom", {
                    "formula": formula,
                    "axiom_id": axiom_id,
                    "axiom_desc": axiom_desc
                })

            # 2. Simulation / Kripke
            elif "kripke" in method or "simulation" in method:
                stats = cross.metadata.get("stats", {})
                max_worlds = stats.get("worlds", "?")
                assumptions = ", ".join(cross.assumptions) if cross.assumptions else "none"
                
                self._add_segment(plan, "proved_simulation", {
                    "formula": formula,
                    "max_worlds": str(max_worlds),
                    "assumptions": assumptions
                })

            # 3. Truth Table
            elif "truth_table" in method:
                # stats should be in metadata if available, otherwise guess 2^atoms
                atoms_count = len(cross.atoms)
                assignments = str(2**atoms_count)
                self._add_segment(plan, "proved_truth_table", {
                    "formula": formula,
                    "assignments": assignments
                })
            
            # 4. Algebra
            elif "arithmetic" in method or "algebra" in method:
                 self._add_segment(plan, "proved_algebra", {
                    "formula": formula
                })

        # --- DISPROVED ---
        elif cross.status == ReasoningStatus.DISPROVED:
            method = cross.semantics.get("method", "")
            cex = cross.counterexamples[0] if cross.counterexamples else {}
            
            if "kripke" in method or "simulation" in method:
                worlds = cex.get("worlds", [])
                self._add_segment(plan, "disproved_counterexample", {
                    "formula": formula,
                    "worlds_count": str(len(worlds))
                })
                
                # Detail
                failed_w = cex.get("failed_world", "?")
                val = cex.get("valuation", {})
                rels = cex.get("relation", [])
                self._add_segment(plan, "disproved_counterexample_detail", {
                    "failed_world": str(failed_w),
                    "valuation": str(val),
                    "relations": str(rels)
                })

            elif "truth_table" in method:
                # cex is assignment dict
                self._add_segment(plan, "disproved_truth_table", {
                    "formula": formula,
                    "assignment": str(cex)
                })

        # --- UNKNOWN / TENTATIVE ---
        else:
            # Check for missing assumptions
            # assumption_completion is stored in payload usually, but maybe in metadata?
            # Let's check cross.metadata
            # The engine logic stores 'missing' in payload, not cross directly usually.
            # But ReportBuilder might have access.
            # Here we rely on what's in Cross.
            
            if cross.metadata.get("low_confidence_warning"):
                 self._add_segment(plan, "unknown_tentative", {
                    "formula": formula
                })
            else:
                 self._add_segment(plan, "unknown_insufficient", {
                    "formula": formula
                })

        return plan

    def _add_segment(self, plan: Dict, template_id: str, slots: Dict[str, str]):
        if template_id not in self.templates:
            return
        
        tmpl = self.templates[template_id]
        text = tmpl["text"]
        
        # Fill slots
        for key, val in slots.items():
            text = text.replace(f"{{{key}}}", str(val))
            
        plan["segments"].append({
            "template_id": template_id,
            "text": text,
            "slots": slots,
            "evidence_ref": "cross" # Simplified
        })

    def render(self, plan: Dict) -> str:
        return "\n".join([s["text"] for s in plan["segments"]])
