from typing import Any, Dict
from avh_math.puzzle.verifier_interface import BaseVerifier
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.cross.cross_core import ReasoningCross
from avh_math.avh_math.answer_types.query_type import QueryType
from avh_math.avh_math.answer_types.problem_type import ProblemType
from avh_math.solvers.prop_solver import PropSolver
from avh_math.solvers.modal_solver import ModalSolver
from avh_math.solvers.arithmetic_solver import ArithmeticSolver
from avh_math.solvers.algebra_solver import AlgebraSolver
from avh_math.solvers.unit_solver import UnitSolver
from avh_math.solvers.format_solver import FormatSolver

from avh_math.puzzle.kb_matcher import KBMatcher
from avh_math.puzzle.formula_sanitizer import sanitize_formula
from avh_math.puzzle.formula_gate import is_well_formed_formula
from avh_math.puzzle.reasoning_trace import append_trace
from avh_math.puzzle.reasoning_trace_query import find_best_trace

class MathVerifier(BaseVerifier):
    def __init__(self, core_engine: Any = None, kb_path: str = None):
        self.core_engine = core_engine
        self.kb_matcher = KBMatcher(kb_path) if kb_path else None
        self.prop_solver = PropSolver()
        self.modal_solver = ModalSolver(max_worlds=3)
        self.arithmetic_solver = ArithmeticSolver()
        self.algebra_solver = AlgebraSolver()
        self.unit_solver = UnitSolver()
        self.format_solver = FormatSolver()

    def verify(self, cross: ReasoningCross) -> Dict[str, Any]:
        """
        Execute mathematical verification based on the ReasoningCross.
        """
        def _finalize(result: Dict[str, Any]) -> Dict[str, Any]:
            append_trace(cross, result)
            return result
        # 1. ターゲットの確定
        target_raw = cross.verified_formula or cross.core_formula
        print(f"[DEBUG VERIFY] Entering verify. Domain={cross.domain}, Status={cross.status}")
        print(f"[DEBUG VERIFY] target_raw: {target_raw}")

        is_meta = getattr(cross, "problem_type", None) == ProblemType.META_QUERY
        if not target_raw and not is_meta:
            return _finalize({"status": ReasoningStatus.TENTATIVE_ANSWER})

        # ヘッダキーワードの誤検知防止
        if target_raw and target_raw.strip().lower() in ("domain", "assumption", "formula", "problem", "task"):
            return _finalize({
                "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
                "reason": f"Input '{target_raw}' identified as header keyword, not a formula."
            })

        # 2. サニタイズと正規化
        if cross.domain == "law":
            target_formula = target_raw
        else:
            target_formula = sanitize_formula(target_raw) if target_raw else ""
            if target_raw:
                cross.verified_formula = target_formula

        # === Reasoning Trace Reuse (tentative) ===
        trace_hit = None
        if target_formula:
            trace_hit = find_best_trace(
                core_formula=target_formula,
                domain=cross.domain,
            )
        if trace_hit:
            cross.metadata["trace_hint"] = {
                "score": trace_hit["score"],
                "match_type": trace_hit["match_type"],
                "verdict": trace_hit["trace"].get("verdict"),
                "method": trace_hit["trace"].get("verifier_used", {}).get("solver_id"),
            }
            if trace_hit["score"] >= 0.9:
                return _finalize(
                    {
                        "status": ReasoningStatus.TENTATIVE_ANSWER,
                        "method": "trace_reuse",
                        "details": "Matched previous reasoning trace (tentative).",
                        "trace_ref": trace_hit["trace"].get("ts"),
                        "verified_formula": target_formula,
                    }
                )

        # 3. 特殊ドメイン・ソルバーの実行
        # 0. Arithmetic
        if cross.domain == "arithmetic":
            res = self.arithmetic_solver.solve(target_formula)
            if res["status"] == "evaluated":
                return _finalize({
                    "status": ReasoningStatus.PROVED,
                    "method": "arithmetic_eval",
                    "details": res["details"],
                    "confidence": 1.0,
                    "verified_formula": f"{target_formula} = {res['result']}"
                })
            elif res["status"] == "proved":
                return _finalize({
                    "status": ReasoningStatus.PROVED,
                    "method": "arithmetic_eval",
                    "details": res["details"],
                    "confidence": 1.0,
                    "verified_formula": target_formula
                })
            elif res["status"] == "disproved":
                return _finalize({
                    "status": ReasoningStatus.DISPROVED,
                    "method": "arithmetic_eval",
                    "details": res["details"],
                    "confidence": 1.0,
                    "verified_formula": target_formula
                })

        # Algebra (方程式等)
        if cross.domain == "algebra" or (target_raw and "==" in target_raw):
             res = self.algebra_solver.solve(target_raw)
             if res.status in ("proved", "disproved"):
                 result_dict = res.to_dict()
                 result_dict["verified_formula"] = target_formula
                 return _finalize(result_dict)

        # Format / Unit
        if cross.domain == "format_check":
             res = self.format_solver.solve(target_raw)
             result_dict = res.to_dict()
             result_dict["verified_formula"] = target_formula
             return _finalize(result_dict)

        # 4. 既にシミュレーション等で PROVED の場合の早期リターン
        if cross.status == ReasoningStatus.PROVED:
            return _finalize({
                "status": ReasoningStatus.PROVED,
                "method": "axiom_detection",
                "details": cross.metadata.get("promotion_reason", "Axiom matched via simulation."),
                "verified_formula": target_formula
            })

        # 5. 標準論理検証
        if cross.domain != "law" and not is_meta and (not target_formula or not is_well_formed_formula(target_formula)):
            print("[DEBUG VERIFY] Formula not well-formed.")
            return _finalize({
                "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
                "reason": "Ill-formed or incomplete formula detected at verification boundary."
            })

        # === Axiom Dispatcher (様相論理公理) ===
        if cross.domain == "modal_logic":
            from avh_math.solvers.modal_axioms import check_modal_axiom
            ax_res = check_modal_axiom(target_formula, cross.assumptions)
            if ax_res:
                print(f"[DEBUG VERIFY] Axiom matched: {ax_res['axiom']}")
                return _finalize({
                    "status": ReasoningStatus.PROVED,
                    "method": "modal_axiom_dispatcher",
                    "confidence": 1.0,
                    "details": ax_res.get("reason"),
                    "kb_id": ax_res.get("axiom"),
                    "verified_formula": target_formula
                })

        # === KB Matcher (知識ベース照合) ===
        if self.kb_matcher:
            norm_assumptions = [a.replace("assume:", "").strip().lower() for a in (cross.assumptions or [])]
            qt = getattr(cross, "query_type", QueryType.SINGLE)
            instant_res = self.kb_matcher.find_instant_verdict(target_formula, norm_assumptions, query_type=qt)
            instant = instant_res.get("hit")
            
            if instant_res.get("audit"):
                cross.metadata["kb_audit"] = instant_res["audit"]

            if instant:
                is_validity_check = getattr(cross, "problem_type", None) == ProblemType.VALIDITY_CHECK
                is_tentative = "tentative" in instant["status"]
                
                if is_validity_check and is_tentative:
                     pass
                else:
                    cross.metadata["kb_hint"] = instant
                    cross.status = ReasoningStatus.from_str(instant["status"])
                    return _finalize({
                        "status": cross.status,
                        "method": "kb_match",
                        "details": instant.get("details"),
                        "confidence": instant.get("confidence", 0.9),
                        "verified_formula": target_formula,
                        "kb_id": instant.get("entry_id")
                    })

        # === Solver 集約結果の反映 ===
        for sim in cross.simulation:
            if sim["status"] in ("violated", "disproved"):
                return _finalize({
                    "status": ReasoningStatus.DISPROVED,
                    "method": sim.get("method", "lightweight_simulation"),
                    "details": sim.get("details", "Counterexample found during dynamic evaluation."),
                    "counterexample": sim.get("counterexample") or {
                        "valuation": sim.get("input"),
                        "frame": sim.get("frame"),
                        "world": sim.get("world")
                    },
                    "confidence": 1.0,
                    "verified_formula": target_formula
                })

        # 命題論理 (真理値表)
        is_pure_prop = self._is_pure_propositional(target_formula)
        if is_pure_prop:
            res = self.prop_solver.solve(target_formula)
            if res["status"] == "proved":
                return _finalize({
                    "status": ReasoningStatus.PROVED,
                    "method": "truth_table",
                    "details": res["details"],
                    "confidence": 1.0,
                    "verified_formula": target_formula
                })
            elif res["status"] == "disproved":
                return _finalize({
                    "status": ReasoningStatus.DISPROVED,
                    "method": "truth_table",
                    "counterexample": res["counterexample"],
                    "confidence": 1.0,
                    "details": res["details"],
                    "verified_formula": target_formula
                })

        # 様相論理 (Kripke 探索)
        if cross.domain in ("modal_logic", "legal_logic", "deontic_logic", "law"):
            res = self.modal_solver.solve(target_formula, cross.atoms, cross.assumptions)
            if res["status"] == "proved":
                return _finalize({
                    "status": ReasoningStatus.PROVED,
                    "method": "finite_kripke_search",
                    "details": res["details"],
                    "confidence": 1.0,
                    "verified_formula": target_formula,
                    "stats": res.get("stats")
                })
            elif res["status"] == "disproved":
                return _finalize({
                    "status": ReasoningStatus.DISPROVED,
                    "method": "finite_kripke_search",
                    "counterexample": res["counterexample"],
                    "confidence": 1.0,
                    "details": res["details"],
                    "verified_formula": target_formula,
                    "stats": res.get("stats")
                })

        # 6. フォールバック: Bridge / Analogy
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
                    "details": "Exhaustive verification completed.",
                    "verified_formula": target_formula
                }
                if extra and "counterexample" in extra:
                    res["counterexample"] = extra["counterexample"]
                return _finalize(res)

        return _finalize({
            "status": ReasoningStatus.INSUFFICIENT_EVIDENCE,
            "reason": "Inconclusive results from all available verification methods."
        })

    def _is_pure_propositional(self, formula: str) -> bool:
        f = formula.lower()
        return not any(m in f for m in ["[]", "<>", "box", "diamond", "□", "◇"])
