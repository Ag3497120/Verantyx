from typing import Any, Dict, List
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.puzzle.simulation_cross import SimulationCross, SimulationNode, SimulationResult
from avh_math.puzzle.prop_simulator import run_prop_simulation
from avh_math.puzzle.modal_simulator import run_modal_simulation
from avh_math.puzzle.modal_detector import ModalAxiomDetector

class SimulationEngine:
    def __init__(self):
        self.modal_detector = ModalAxiomDetector()

    def run(self, cross: ReasoningCross) -> ReasoningCross:
        """
        ReasoningCross の情報を元に、SimulationCross を構築・実行し、結果を反映する。
        """
        formula = cross.verified_formula or cross.core_formula
        
        if not formula:
            return cross

        # 1. Simulation Cross の構築 (Reasoning -> Simulation)
        sim_cross = self._build_sim_cross(cross)
        
        # 2. シミュレーション実行 (Virtual Experiment)
        self._execute_sim_cross(sim_cross, cross.atoms)
        
        # 3. 結果の反映 (Simulation -> Reasoning)
        self._reflect_results(cross, sim_cross)

        # [追加] 様相公理の自動検知と昇格 (既存ロジックの維持)
        if cross.domain == "modal_logic":
            cross = self.modal_detector.detect_and_apply(cross)

        return cross

    def _build_sim_cross(self, cross: ReasoningCross) -> SimulationCross:
        sim = SimulationCross(domain=cross.domain)
        
        # Core Formula
        target = cross.verified_formula or cross.core_formula
        if target:
            sim.add_node("formula", target)
            
        # Assumptions
        for asm in cross.assumptions:
            sim.add_node("assumption", asm)
            
        # Candidates (Set validation support)
        if hasattr(cross, "candidates") and cross.candidates:
            for cand in cross.candidates:
                if cand != target: # 重複回避
                    sim.add_node("formula", cand)
                    
        return sim

    def _execute_sim_cross(self, sim: SimulationCross, atoms: List[str]):
        """ドメインに応じたシミュレーション戦略の実行"""
        
        # Modal Logic Strategy
        if sim.domain == "modal_logic":
            # Kripke Model Simulation for Core Formula
            if sim.core_formula:
                # 既存の run_modal_simulation を活用
                raw_results = run_modal_simulation(sim.core_formula, atoms, sim.assumptions)
                
                for r in raw_results:
                    if r["status"] == "violated":
                        sim.results.append(SimulationResult(
                            status="disproved",
                            confidence=0.95,
                            method="kripke_model_check",
                            details="Counterexample found in Kripke model.",
                            counterexample=r.get("input") # valuation
                        ))
                    else:
                        sim.results.append(SimulationResult(
                            status="proved", # in this model
                            confidence=0.4,  # limited model check is weak proof
                            method="kripke_model_check",
                            details="Satisfied in generated model."
                        ))

        # Propositional Logic Strategy
        elif sim.domain == "propositional_logic":
            if sim.core_formula:
                raw_results = run_prop_simulation(sim.core_formula, atoms)
                for r in raw_results:
                    if r["status"] == "violated":
                        sim.results.append(SimulationResult(
                            status="disproved",
                            confidence=1.0, # Prop truth table is decisive
                            method="truth_table_simulation",
                            counterexample=r.get("input")
                        ))

    def _reflect_results(self, cross: ReasoningCross, sim: SimulationCross):
        """Simulation結果を ReasoningCross に書き戻す"""
        
        # Simulation履歴の保存
        for res in sim.results:
            cross.simulation.append(res.to_dict())
            
            # 決定的な反証が見つかった場合
            if res.status == "disproved":
                cross.status = ReasoningStatus.DISPROVED
                cross.semantics["method"] = res.method
                if res.counterexample:
                    # 重複チェックしつつ追加
                    if res.counterexample not in cross.counterexamples:
                        cross.counterexamples.append(res.counterexample)
                    cross.metadata["simulation_counterexample"] = res.counterexample
