from typing import Any, Dict, List
from avh_math.text_cross.result import TextCrossResult
from avh_math.puzzle.simulation_cross import SimulationCross, SimulationResult
from avh_math.puzzle.simulation_engine import SimulationEngine
from avh_math.puzzle.kb_matcher import KBMatcher
from avh_math.answer_types.query_type import QueryType

class SimulationBridge:
    def __init__(self, kb_path: str = None):
        self.sim_engine = SimulationEngine()
        self.kb_matcher = KBMatcher(kb_path) if kb_path else None

    def build_simulation_cross(self, tc: TextCrossResult) -> SimulationCross:
        """Text-Cross の結果から Simulation Cross（実験場）を構築"""
        cross = SimulationCross(domain=tc.domain)
        cross.core_formula = tc.core_formula
        
        # 仮定の正規化と登録
        # "assume:transitive" -> "transitive" などの処理は TextCrossResult 生成時に済んでいる前提だが念のため
        for asm in tc.assumptions:
            clean_asm = asm.replace("assume:", "").strip()
            cross.add_node("assumption", clean_asm)
            
        # 候補式の登録
        for f in tc.candidate_formulas:
            if f != tc.core_formula:
                cross.add_node("formula", f)
                
        return cross

    def load_kb_into_simulation(self, cross: SimulationCross, query_type: QueryType):
        """KBから関連知識（部品）を検索してSimulationCrossにロード"""
        if not self.kb_matcher:
            return

        # 検索対象とする式（Core + Candidates）
        targets = []
        if cross.core_formula:
            targets.append(cross.core_formula)
        # Note: SimulationNode から formula を抽出してもよい
        targets.extend([n.content for n in cross.nodes if n.kind == "formula"])
        
        unique_targets = list(set(targets))
        
        for formula in unique_targets:
            # KB検索 (QueryType考慮済み)
            # find_instant_verdict は1件しか返さないが、本来は複数候補が必要かもしれない
            # ここでは既存の仕組みを最大限活用
            res = self.kb_matcher.find_instant_verdict(
                formula, 
                cross.assumptions, 
                query_type=query_type
            )
            
            hit = res.get("hit")
            if hit:
                # KBヒットをノードとして追加
                # kind は axiom か counterexample_schema になるはず
                role = "rule" 
                if "counterexample" in hit:
                    role = "counterexample"
                elif "axiom" in str(hit.get("details", "")).lower():
                    role = "axiom"
                    
                cross.add_node(
                    kind=role,
                    content=hit.get("details"), # または entry statement
                    source_id=hit.get("entry_id"),
                    confidence=0.9
                )

    def run_simulation_pipeline(self, tc: TextCrossResult) -> Dict[str, Any]:
        """
        統合実行パイプライン
        1. 構築 (Build)
        2. KBロード (Load)
        3. 実行 (Run)
        4. 判定 (Finalize)
        """
        # 1. 構築
        sim_cross = self.build_simulation_cross(tc)
        
        # 2. KBロード
        self.load_kb_into_simulation(sim_cross, tc.query_type)
        
        # 3. 実行 (SimulationEngine の内部ロジックを呼ぶ)
        # SimulationEngine._execute_sim_cross 相当のことを行う
        # ここでは SimulationEngine.run は ReasoningCross を受け取る設計なので
        # 内部メソッドを直接呼ぶか、アダプタが必要。
        # 今回は SimulationBridge 内で実行制御を行う形にする（Engineのロジック再利用）
        
        # Atoms抽出（簡易）
        import re
        atoms = set()
        all_formulas = [n.content for n in sim_cross.nodes if n.kind == "formula"]
        if sim_cross.core_formula: all_formulas.append(sim_cross.core_formula)
        
        for f in all_formulas:
            atoms.update(re.findall(r"\b[pqrA-Z]\b", str(f)))
        atom_list = sorted(list(atoms))

        self.sim_engine._execute_sim_cross(sim_cross, atom_list)
        
        # 4. 判定
        return self.finalize_from_simulation(sim_cross, tc.query_type)

    def finalize_from_simulation(self, cross: SimulationCross, query_type: QueryType) -> Dict[str, Any]:
        """Simulation結果から最終的なSolverResult（辞書形式）を生成"""
        
        # SET_ALL / SET_ANY のロジックはここで吸収しても良いが、
        # SimulationCross.results には個別の結果が入っている
        
        results = cross.results
        if not results:
             return {
                "status": "insufficient_evidence",
                "answer": "No simulation results available.",
                "confidence": 0.0,
                "evidence": {"trace": "simulation_skipped"}
            }

        # 1. 反証があれば最強 (DISPROVED)
        disproved_res = [r for r in results if r.status == "disproved"]
        if disproved_res:
            best_ref = disproved_res[0]
            return {
                "status": "disproved",
                "answer": f"Counterexample found: {best_ref.details}",
                "confidence": best_ref.confidence,
                "evidence": {
                    "method": best_ref.method,
                    "counterexample": best_ref.counterexample
                }
            }

        # 2. 全て証明されていれば (PROVED)
        # 注意: モデル検査での PROVED は「そのモデルではOK」という意味で弱い場合がある
        # しかし、KB由来の axiom ノードがあれば強い
        proved_res = [r for r in results if r.status == "proved"]
        
        # Kripke Model Check だけの PROVED は confidence が低い (0.4)
        # Truth Table の PROVED は confidence が高い (1.0)
        
        if len(proved_res) == len(results) and len(results) > 0:
            max_conf = max(r.confidence for r in proved_res)
            return {
                "status": "proved" if max_conf > 0.8 else "tentative_answer",
                "answer": "Verified in simulation.",
                "confidence": max_conf,
                "evidence": {
                    "method": proved_res[0].method,
                    "details": "All checks passed."
                }
            }

        return {
            "status": "tentative_answer",
            "answer": "Simulation inconclusive.",
            "confidence": 0.4,
            "evidence": {"details": "Mixed or weak results."}
        }
