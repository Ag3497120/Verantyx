from typing import Any, Dict
from avh_math.puzzle.verifier_interface import BaseVerifier
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.cross.cross_core import ReasoningCross
from avh_math.avh_math.answer_types.query_type import QueryType
from avh_math.avh_math.answer_types.problem_type import ProblemType
from avh_math.solvers.prop_solver import PropSolver
from avh_math.solvers.modal_solver import ModalSolver

from avh_math.puzzle.kb_matcher import KBMatcher
from avh_math.puzzle.formula_sanitizer import sanitize_formula
from avh_math.puzzle.formula_gate import is_well_formed_formula

class MathVerifier(BaseVerifier):
    def __init__(self, core_engine: Any = None, kb_path: str = None):
        self.core_engine = core_engine
        self.kb_matcher = KBMatcher(kb_path) if kb_path else None
        self.prop_solver = PropSolver()
        self.modal_solver = ModalSolver(max_worlds=3)

    def verify(self, cross: ReasoningCross) -> Dict[str, Any]:
        """
        Execute mathematical verification based on the ReasoningCross.
        """
        print(f"[DEBUG VERIFY] Entering verify. Domain={cross.domain}, Status={cross.status}")
        
        # Return immediately if already proved via simulation/axiom detection
        if cross.status == ReasoningStatus.PROVED:
            return {
                "status": ReasoningStatus.PROVED,
                "method": "axiom_detection",
                "details": cross.metadata.get("promotion_reason", "Axiom matched via simulation.")
            }

        # Select target formula for verification
        target_raw = cross.verified_formula or cross.core_formula
        
        print(f"[DEBUG VERIFY] target_raw: {target_raw}")

        if not target_raw:
            return {"status": ReasoningStatus.TENTATIVE_ANSWER}

        # Guard against header keywords being treated as formulas
        if target_raw.strip().lower() in ("domain", "assumption", "formula", "problem", "task"):
            return {
                "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
                "reason": f"Input '{target_raw}' identified as header keyword, not a formula."
            }

        # Domain-specific sanitization
        if cross.domain == "law":
            target_formula = target_raw
        else:
            # 決定打：Decomposer が既に浄化済みなので、ここでは最低限のサニタイズのみ行う
            target_formula = sanitize_formula(target_raw)
            
            # 浄化された式を Cross に記録
            cross.verified_formula = target_formula
        
        # DEBUG: Inspect formula before verification
        if cross.domain != "law" and (not target_formula or not is_well_formed_formula(target_formula)):
            print("[DEBUG VERIFY] Formula not well-formed.")
            return {
                "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
                "reason": "Ill-formed or incomplete formula detected at verification boundary."
            }

        # === Axiom Dispatcher (Structural Match) ===
        if cross.domain == "modal_logic":
            from avh_math.solvers.modal_axioms import check_modal_axiom
            ax_res = check_modal_axiom(target_formula, cross.assumptions)
            if ax_res:
                print(f"[DEBUG VERIFY] Axiom matched: {ax_res['axiom']}")
                return {
                    "status": ReasoningStatus.PROVED,
                    "method": "modal_axiom_dispatcher",
                    "confidence": 1.0,
                    "details": ax_res.get("reason"),
                    "kb_id": ax_res.get("axiom")
                }

        # === KB Matcher (Knowledge-based Verdict) ===
        if self.kb_matcher:
            norm_assumptions = [a.replace("assume:", "").strip().lower() for a in (cross.assumptions or [])]
            qt = getattr(cross, "query_type", QueryType.SINGLE)
            instant_res = self.kb_matcher.find_instant_verdict(target_formula, norm_assumptions, query_type=qt)
            instant = instant_res.get("hit")
            
            if instant_res.get("audit"):
                cross.metadata["kb_audit"] = instant_res["audit"]

            if instant:
                # Rigorous check for VALIDITY_CHECK
                is_validity_check = getattr(cross, "problem_type", None) == ProblemType.VALIDITY_CHECK
                is_tentative = "tentative" in instant["status"]
                
                if is_validity_check and is_tentative:
                     # Skip tentative matches to force simulation/search
                     pass
                else:
                    cross.metadata["kb_hint"] = instant
                    cross.status = ReasoningStatus.from_str(instant["status"])

        # === Simulation / Solver Result Integration ===
        if cross.status == ReasoningStatus.PROVED:
            return {
                "status": ReasoningStatus.PROVED,
                "method": cross.semantics.get("method", "simulation_axiom_detection"),
                "details": cross.metadata.get("promotion_reason", "Verified via simulation and axiom detection.")
            }

        for sim in cross.simulation:
            if sim["status"] in ("violated", "disproved"):
                return {
                    "status": ReasoningStatus.DISPROVED,
                    "method": sim.get("method", "lightweight_simulation"),
                    "details": sim.get("details", "Counterexample found during dynamic evaluation."),
                    "counterexample": sim.get("counterexample") or {
                        "valuation": sim.get("input"),
                        "frame": sim.get("frame"),
                        "world": sim.get("world")
                    },
                    "confidence": 1.0
                }

        task = cross.task or "check_validity"

        # 1. Propositional Logic (Truth Table)
        is_pure_prop = self._is_pure_propositional(target_formula)
        print(f"[DEBUG VERIFY] is_pure_prop: {is_pure_prop} for '{target_formula}'")
        
        if is_pure_prop:
            res = self.prop_solver.solve(target_formula)
            print(f"[DEBUG PROVER] prop_solver result: {res}")
            
            if res["status"] == "proved":
                return {
                    "status": ReasoningStatus.PROVED,
                    "method": "truth_table",
                    "details": res["details"],
                    "confidence": 1.0
                }
            elif res["status"] == "disproved":
                return {
                    "status": ReasoningStatus.DISPROVED,
                    "method": "truth_table",
                    "counterexample": res["counterexample"],
                    "confidence": 1.0,
                    "details": res["details"]
                }

        # 2. Modal Logic (Kripke Model Search)
        if cross.domain in ("modal_logic", "legal_logic", "deontic_logic", "law"):
            print(f"[DEBUG VERIFY] Running ModalSolver for '{target_formula}'")
            res = self.modal_solver.solve(target_formula, cross.atoms, cross.assumptions)
            print(f"[DEBUG PROVER] modal_solver result: {res}")
            
            if res["status"] == "proved":
                return {
                    "status": ReasoningStatus.PROVED,
                    "method": "finite_kripke_search",
                    "details": res["details"],
                    "confidence": 1.0,
                    "verified_formula": target_formula,
                    "stats": res.get("stats")
                }
            elif res["status"] == "disproved":
                return {
                    "status": ReasoningStatus.DISPROVED,
                    "method": "finite_kripke_search",
                    "counterexample": res["counterexample"],
                    "confidence": 1.0,
                    "details": res["details"],
                    "verified_formula": target_formula,
                    "stats": res.get("stats")
                }

        # 3. Advanced Reasoning (Core Engine) - Fallback
        if self.core_engine:
            try:
                engine_input = self._build_engine_input(cross, target_formula)
                res = self.core_engine.solve(engine_input)
                ranked = getattr(res, "ranked", [])
                if ranked:
                    best = ranked[0]
                    if best.status == "valid":
                        return {"status": ReasoningStatus.PROVED, "method": "core_engine"}
                    elif best.status == "invalid":
                        return {
                            "status": ReasoningStatus.DISPROVED, 
                            "method": "core_engine",
                            "counterexample": best.counterexample
                        }
            except Exception:
                pass

        # === [STEP 3] Final Verdict / Verifier Bridge ===
        from avh_math.puzzle.verifier_bridge import finalize_verdict
        
        if target_formula:
            final_status, extra = finalize_verdict(
                current_status=cross.status,
                formula=target_formula,
                domain=cross.domain,
                assumptions=cross.assumptions,
                atoms=cross.atoms
            )
            
            if final_status in (ReasoningStatus.PROVED, ReasoningStatus.DISPROVED):
                res = {
                    "status": final_status,
                    "method": extra.get("method", "verifier_bridge") if extra else "puzzle_inference",
                    "details": "Exhaustive verification completed."
                }
                if extra:
                    if "counterexample" in extra:
                        res["counterexample"] = extra["counterexample"]
                    elif "valuation" in extra:
                        res["counterexample"] = extra["valuation"]
                return res

        # === Tentative Puzzle Phase (Structural Analogy) ===
        if getattr(cross, "problem_type", None) == ProblemType.VALIDITY_CHECK:
             return {
                "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
                "reason": "Validity check requires strict proof or counterexample; structural analogy is insufficient."
            }

        if self.kb_matcher:
            from avh_math.puzzle.structural_embed import find_embedding_axiom
            fragments = [target_formula] if target_formula else []
            fragments.extend(cross.syntax_nodes)
            
            for frag in fragments:
                if not frag: continue
                matched_axiom = find_embedding_axiom(frag, self.kb_matcher.entries)
                if matched_axiom:
                    return {
                        "status": ReasoningStatus.TENTATIVE_ANSWER,
                        "method": "structural_embedding",
                        "kb_id": matched_axiom.get("id"),
                        "details": f"Fragment '{frag}' found embedded in known axiom: {matched_axiom.get('statement')}",
                        "note": "Hypothesis based on structural analogy (unverified)"
                    }

        return {
            "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
            "reason": "Inconclusive results from all available verification methods."
        }

    def _is_pure_propositional(self, formula: str) -> bool:
        f = formula.lower()
        return not any(m in f for m in ["[]", "<>", "box", "diamond", "□", "◇"])

    def _build_engine_input(self, cross: ReasoningCross, formula: str) -> str:
        lines = []
        if cross.domain != "unknown":
            lines.append(f"Domain: {cross.domain}")
        if cross.assumptions:
            lines.append("Assumptions: " + ", ".join(cross.assumptions))
        lines.append(f'Formula: "{formula}"')
        return "\n".join(lines)
