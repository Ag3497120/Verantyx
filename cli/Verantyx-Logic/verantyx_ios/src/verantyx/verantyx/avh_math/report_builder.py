# avh_math/report_builder.py (iOS Production Version)
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os, time, re, json

from avh_math.solution_report import (
    SolutionReport, ProofBlock, CounterexampleBlock, EvidenceItem, BoundaryBlock, TraceBlock
)
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.puzzle.assemble_reasoning_cross import assemble_reasoning_cross
from avh_math.puzzle.math_verifier import MathVerifier
from avh_math.puzzle.simulation_engine import SimulationEngine
from avh_math.puzzle.solver_router import SolverRouter
from avh_math.puzzle.inference_profile import InferenceProfile
from avh_math.puzzle.forget_engine import ForgetEngine
from avh_math.puzzle.learning_engine import LearningEngine

from avh_math.cross.cross_core import ReasoningCross
from avh_math.cross.cross_db import ReasoningCrossDB
from avh_math.answer_types.query_type import QueryType
from avh_math.answer_types.problem_type import ProblemType
from avh_math.text_cross.result import TextCrossResult
from avh_math.puzzle.simulation_bridge import SimulationBridge

# --- NLG / Narrative Layer ---
from avh_math.nlg.narrative_solver import NarrativeSolver
from avh_math.nlg.nlg_verifier import NLGVerifier

class ReportBuilder:
    def __init__(self, kb_path: str, budgets: Dict[str, Any]):
        self.kb_path = kb_path
        self.db_dir = os.path.dirname(kb_path)
        self.budgets = budgets
        self.verifier = MathVerifier(kb_path=self.kb_path)
        self.sim_engine = SimulationEngine()
        self.cross_db = ReasoningCrossDB(os.path.join(self.db_dir, "cross_store.jsonl"))
        self.active_profile = InferenceProfile()
        self.router = SolverRouter(self.active_profile)
        self.narrative_solver = NarrativeSolver()
        self.nlg_verifier = NLGVerifier()

    def build(self, query: str) -> Dict[str, Any]:
        start = time.time()
        q = (query or "").strip()
        problem_key = f"q_{abs(hash(q))}"
        trace = TraceBlock(stages=[], limits=self.budgets)
        
        def log(stage: str, **kv):
            trace.stages.append({"stage": stage, "t_ms": int((time.time()-start)*1000), **kv})

        # 1. Decomposition
        from avh_math.input_pipeline import decompose_text
        decomp = decompose_text(q)
        
        # 2. Cross Assembly
        # 決定打：LaTeX正規化などを考慮したクエリで構築
        q_norm = q.replace(r"\land", "&").replace(r"\to", "->")
        cross = assemble_reasoning_cross(q_norm, self.cross_db)
        
        # 3. Data Transfer from Decomposer to Cross
        cross.query_type = decomp.query_type
        cross.problem_type = decomp.problem_type
        cross.domain = decomp.domain
        cross.atoms = decomp.atoms
        cross.assumptions = list(set((cross.assumptions or []) + decomp.assumptions))
        
        # 救済：META_QUERY または law なら core_formula を強制
        if decomp.problem_type == ProblemType.META_QUERY or decomp.domain == "law":
            cross.core_formula = decomp.core_formula or q
            if cross.status == ReasoningStatus.INSUFFICIENT_EVIDENCE:
                cross.status = ReasoningStatus.TENTATIVE_ANSWER
                print(f"[REPORT-V2] Promoting {decomp.domain} query to TENTATIVE")

        # 4. Solver Router
        if cross.status not in (ReasoningStatus.SILENT, ReasoningStatus.INSUFFICIENT_EVIDENCE):
            cross = self.router.route_and_solve(cross, self.sim_engine, self.verifier)
        
        # 5. Narrative Generation
        plan = self.narrative_solver.solve(cross)
        answer = self.narrative_solver.render(plan)
        
        # 6. Build Report
        rep = SolutionReport(
            status=cross.status.value,
            problem_key=problem_key,
            query=q,
            answer_text=answer
        )
        
        # Add metadata for UI
        res_dict = rep.to_dict()
        res_dict["payload"] = {"decomp": {"domain": cross.domain, "core_formula": cross.core_formula, "candidates": decomp.candidates}}
        res_dict["problem_type"] = cross.problem_type.value
        
        return res_dict