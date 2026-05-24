# avh_math/report_builder.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os, time, re

from avh_math.solution_report import (
    SolutionReport, ProofBlock, CounterexampleBlock, EvidenceItem, BoundaryBlock, TraceBlock
)
from avh_math.solvers.modal_axioms import check_modal_axiom
from avh_math.text_cross.mapping_table import record_mapping

# Robust imports
MathEngine = None
try:
    from engine import MathEngine
except ImportError:
    try:
        from avh_math.engine import MathEngine
    except ImportError:
        pass

search_proofs = None
make_problem_key = None
try:
    from phase33_proof_store import search_proofs, make_problem_key
except ImportError:
    pass

KBIndex = None
retrieve_similar_entries = None
synthesize_answer_from_similars = None
try:
    from avh_math.retrieval_bm25 import KBIndex
    from avh_math.retrieval_answer import retrieve_similar_entries
    from avh_math.retrieval_answer import synthesize_answer_from_similars
except ImportError:
    pass

is_tautology = None
try:
    from avh_math.solvers.prop_truth_table import is_tautology
except ImportError:
    try:
        from solvers.prop_truth_table import is_tautology
    except ImportError:
        pass

# --- Enhanced Formula Extraction Layer ---
_FORMULA_TOKENS = re.compile(r"[A-Za-z][A-Za-z0-9_]*|->|<->|\[\]|<>|[()~&|!]|□|◇")

_QUOTED_FORMULA_RE = re.compile(r'["“”]([^"“”]+)["“”]|「([^」]+)」|『([^』]+)』')

def _rebuild_formula_only(s: str) -> str:
    """純粋な式トークンだけで再構成し、末尾の冠詞を除去する"""
    toks = _FORMULA_TOKENS.findall(s)
    if not toks:
        return ""
    
    # トークンを連結
    cand = " ".join(toks).replace("  ", " ").strip()
    cand = _glue_modal_ops(cand)
    
    # 末尾に残った冠詞（a, an, the）を除去
    cand = re.sub(r"\b(a|an|the)\b\s*$", "", cand, flags=re.IGNORECASE).strip()
    return cand

def _glue_modal_ops(s: str) -> str:
    # "[] p" -> "[]p", "<> p" -> "<>p", "[] [] p" -> "[][]p"
    s = re.sub(r"\[\]\s+(?=[A-Za-z(~\[])", "[]", s)
    s = re.sub(r"<>\s+(?=[A-Za-z(~\[])", "<>", s)
    s = re.sub(r"□\s+(?=[A-Za-z(~\[])", "□", s)
    s = re.sub(r"◇\s+(?=[A-Za-z(~\[])", "◇", s)
    s = re.sub(r"\[\]\s+\[\]\s*", "[][]", s)
    s = re.sub(r"<>\s+<>\s*", "<><>", s)
    return s

from avh_math.text_cross.formula_extractor import extract_formula_candidates
from avh_math.puzzle.formula_gate import is_global_formula, select_core_formula

def extract_formula_only(text: str) -> str:
    """自然文から論理式だけを抽出し、正規化する。全体式条件を満たすもののみを返す。"""
    # 構造化ヘッダのチェック
    m_hdr = re.search(r"(?im)^\s*Formula\s*:\s*(.+)$", text)
    if m_hdr:
        return m_hdr.group(1).strip()

    candidates = extract_formula_candidates(text)
    core_candidate, formula_type = select_core_formula(candidates, text)
    
    if core_candidate:
        return core_candidate["normalized"]
    
    return ""

from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.avh_math.answer_types.query_type import QueryType
from avh_math.avh_math.answer_types.problem_type import ProblemType
from avh_math.cross.cross_db import ReasoningCrossDB
from avh_math.puzzle.math_verifier import MathVerifier
from avh_math.puzzle.assemble_reasoning_cross import assemble_reasoning_cross

from avh_math.pipeline.silent_fallback import apply_silent_fallback

from avh_math.puzzle.axiom_backflow import backflow_to_kb

from avh_math.puzzle.simulation_engine import SimulationEngine

from avh_math.puzzle.inference_profile import InferenceProfile, derive_delta_from_meta
from avh_math.puzzle.solver_router import SolverRouter

from avh_math.puzzle.forget_engine import ForgetEngine

from avh_math.puzzle.cross_executor import execute_cross_verification

from avh_math.hardware.hardware_core import cross_to_hw_graph
from avh_math.hardware.hw_engine import PseudoCPU

from avh_math.puzzle.learning_engine import LearningEngine
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
        self.core_engine = MathEngine(db_dir=self.db_dir) if MathEngine else None
        
        # コンポーネント初期化
        self.cross_db_path = os.path.join(self.db_dir, "reasoning_cross_store.jsonl")
        self.cross_db = ReasoningCrossDB(self.cross_db_path)
        self.verifier = MathVerifier(core_engine=self.core_engine, kb_path=self.kb_path)
        self.sim_engine = SimulationEngine()
        self.forget_engine = ForgetEngine()
        self.sim_bridge = SimulationBridge(kb_path=self.kb_path)
        
        # Narrative components
        self.narrative_solver = NarrativeSolver()
        self.nlg_verifier = NLGVerifier()
        
        # 学習エンジン
        self.log_path = os.path.join(self.db_dir, "operation_logs.jsonl")
        self.learning_engine = LearningEngine(self.kb_path, self.log_path)
        
        # ハードウェア・シミュレーション層
        self.pseudo_cpu = PseudoCPU(cores=10)
        
        # 実行プロファイル（人格）の初期化
        self.active_profile = InferenceProfile()
        self.router = SolverRouter(self.active_profile)
        
        self._kb_index = None
        self._kb_index_path = os.path.join(self.db_dir, "kb_bm25_index.json")

    def _solve_set_validation(self, candidates: List[str], query_type: QueryType, assumptions: List[str]) -> Tuple[ReasoningStatus, str, Dict[str, Any]]:
        """複数の候補式を順次検証し、結果を集約する"""
        results = []
        all_proved = True
        any_proved = False
        disproved_item = None

        for f in candidates:
            # 既存の verifier を利用して単一式を検証
            # 注意: verifier.verify が単一式を返すことを期待
            # ここでは内部の MathVerifier を使用
            try:
                # MathVerifier.verify(formula, assumptions) を想定
                v_res = self.verifier.verify(f, assumptions)
                status = v_res.get("status")
                
                results.append({"formula": f, "status": status, "result": v_res})
                
                if status == "proved":
                    any_proved = True
                elif status == "disproved":
                    all_proved = False
                    disproved_item = {"formula": f, "result": v_res}
                else:
                    all_proved = False
            except Exception as e:
                results.append({"formula": f, "status": "error", "error": str(e)})
                all_proved = False

        if query_type == QueryType.SET_ALL:
            if all_proved:
                return ReasoningStatus.PROVED, "全ての式が妥当であることを確認しました。", {"results": results}
            elif disproved_item:
                return ReasoningStatus.DISPROVED, f"一部の式に反例が見つかりました: {disproved_item['formula']}", {"results": results, "failed": disproved_item}
            else:
                return ReasoningStatus.INSUFFICIENT_EVIDENCE, "一部の式の妥当性を確認できませんでした。", {"results": results}
        
        elif query_type == QueryType.SET_ANY:
            if any_proved:
                return ReasoningStatus.PROVED, "少なくとも1つの式が妥当であることを確認しました。", {"results": results}
            else:
                return ReasoningStatus.DISPROVED, "妥当な式が見つかりませんでした。", {"results": results}
        
        return ReasoningStatus.INSUFFICIENT_EVIDENCE, "検証を完了できませんでした。", {"results": results}

    def _suggest_relevant_theorems(self, cross: ReasoningCross) -> List[Dict[str, Any]]:
        """ドメインとコンテキストに基づいて、有用な定理や公理をDBから提案する"""
        suggestions = []
        if not self.verifier.kb_matcher:
            return suggestions
            
        # 1. ドメイン一致かつ重要な定理
        for entry in self.verifier.kb_matcher.entries:
            if entry.get("domain") == cross.domain:
                # 既に仮定にあるものは除外
                if any(entry.get("id") in a for a in cross.assumptions):
                    continue
                
                # kind が axiom, theorem, statute のものを候補にする
                if entry.get("kind") in ("axiom", "theorem", "statute"):
                    suggestions.append({
                        "id": entry.get("id"),
                        "statement": entry.get("statement"),
                        "kind": entry.get("kind"),
                        "score": 1.0 # 簡易スコア
                    })
        
        # 上位5件を返す
        return suggestions[:5]

    def build(self, query: str) -> Dict[str, Any]:
        start = time.time()
        q = (query or "").strip()
        problem_key = make_problem_key(q) if make_problem_key else f"q_{abs(hash(q))}"
        
        trace = TraceBlock(stages=[], limits=self.budgets)
        def log(stage: str, **kv):
            trace.stages.append({"stage": stage, "t_ms": int((time.time()-start)*1000), **kv})

        if not q:
            return SolutionReport(status=ReasoningStatus.SILENT.value, problem_key=problem_key, query=q, answer_text="Input is empty.").to_dict()

        # 1. Decomposition (Text-Cross Layer)
        from avh_math.input_pipeline import decompose_text
        decomp = decompose_text(q)
        
        # DEBUG: Inspect decomposition result
        print(f"[DEBUG] Decomposed type: {type(decomp)}")
        print(f"[DEBUG] core_formula: {getattr(decomp, 'core_formula', 'MISSING')}")
        print(f"[DEBUG] candidates len: {len(getattr(decomp, 'candidates', []))}")
        print(f"[DEBUG] query_type attr: {getattr(decomp, 'query_type', 'MISSING')}")

        if isinstance(decomp, dict):
            # 決定打：分解失敗時は即座にリターン
            rep = SolutionReport(
                status=decomp.get("status", "insufficient_evidence"),
                problem_key=problem_key,
                query=q,
                answer_text="完結した全体式が確定できないため、推論を保留します。"
            )
            rep.why = decomp.get("reason")
            rep.trace = trace
            return rep.to_dict()

        # 2. Formula Gate (core_formula の確定)
        core = getattr(decomp, "core_formula", None)
        query_type = getattr(decomp, "query_type", QueryType.SINGLE)
        prob_type = getattr(decomp, "problem_type", ProblemType.VALIDITY_CHECK)
        candidates = getattr(decomp, "candidates", [])
        
        # 決定打：メタ・クエリなら文章全体を core にする
        if prob_type == ProblemType.META_QUERY and not core:
            core = q
            log("meta_query_passthrough", core=core)
        
        # 決定打：断片であっても candidates があれば core として採用し、推論を開始する
        if not core and candidates:
            core = candidates[0]
            # ログにも残す
            log("formula_recovered", core=core)
        
        # 決定打：集合検証モード、等価性、またはメタ・クエリなら、単一の core がなくても続行する
        is_set_query = query_type in (QueryType.SET_ALL, QueryType.SET_ANY, QueryType.EQUIVALENCE)
        is_bypass_query = is_set_query or prob_type == ProblemType.META_QUERY

        if not core and not is_bypass_query:
            status = ReasoningStatus.SILENT
            # 救済措置：ここに来るのは candidates すら空の場合のみ
            rep = SolutionReport(
                status=status.value,
                problem_key=problem_key,
                query=q,
                answer_text="No valid logical formula or conceptual query detected. Please check your input."
            )
            rep.trace = trace
            return rep.to_dict()

        # 3. 推論 / シミュレーション / 検証フロー
        log("reasoning_start", core=core, query_type=query_type)
        
        # 組立
        if hasattr(self.verifier, 'kb_matcher') and self.verifier.kb_matcher:
            self.verifier.kb_matcher._load_kb()
            
        # 決定打：assemble_reasoning_cross に渡す前に LaTeX 正規化を行う
        q_norm = q.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
        q_norm = q_norm.replace(r"\to", "->").replace(r"\rightarrow", "->").replace(r"\leftrightarrow", "<->")
        q_norm = q_norm.replace(r"\box", "[]").replace(r"\diamond", "<>")
        
        cross = assemble_reasoning_cross(q_norm, self.cross_db)
        print(f"[DEBUG REPORT] Cross assembled. Status: {cross.status} (type: {type(cross.status)})")
        print(f"[DEBUG REPORT] Cross assumptions (init): {cross.assumptions}")
        
        # [NEW] Inject user axioms from decomp evidence
        injected_axioms = decomp.evidence.get("injected_axioms", [])
        if injected_axioms:
            print(f"[DEBUG REPORT] Injecting {len(injected_axioms)} axioms from Context")
            for formula in injected_axioms:
                cross.evidence.append({
                    "kind": "injected_axiom",
                    "formula": formula,
                    "confidence": 1.0,
                    "role": "user_context"
                })
                if formula not in cross.syntax_nodes:
                    cross.syntax_nodes.append(formula)

        # 決定打：Decomposer が見つけた「真の式」を Cross にセットする
        if decomp.core_formula:
            cross.core_formula = decomp.core_formula
            print(f"[DEBUG REPORT] Setting cross.core_formula from decomp: {cross.core_formula}")

        if decomp.domain and decomp.domain != "unknown":
            cross.domain = decomp.domain
            print(f"[DEBUG REPORT] Setting cross.domain from decomp: {cross.domain}")

        cross.query_type = query_type # 意図を Cross に転記
        cross.problem_type = getattr(decomp, "problem_type", ProblemType.VALIDITY_CHECK)
        cross.candidates = decomp.candidates # 候補を Cross に転記
        cross.atoms = decomp.atoms # 決定打：論理変数リストを転記
        
        # 決定打：Decomposer で検出された仮定を確実に統合する
        # decomp.assumptions が空の場合の救済措置
        assumes = decomp.assumptions or []
        if not assumes:
            try:
                from avh_math.input_pipeline import _detect_assumptions_ja_en
                assumes = _detect_assumptions_ja_en(q)
                print(f"[DEBUG REPORT] Detected assumptions directly: {assumes}")
            except ImportError:
                pass

        if assumes:
            print(f"[DEBUG REPORT] Merging assumptions: {assumes}")
            cross.assumptions = list(set((cross.assumptions or []) + assumes))
            
        print(f"[DEBUG REPORT] Cross assumptions (final): {cross.assumptions}")
        
        # [NEW] Allow Modal Logic System K (no assumptions) to be solved
        if cross.domain == "modal_logic" and not cross.assumptions:
            if cross.status == ReasoningStatus.INSUFFICIENT_EVIDENCE:
                cross.status = ReasoningStatus.TENTATIVE_ANSWER
                print("[DEBUG REPORT] No modal assumptions detected. Promoting to TENTATIVE for System K solver.")

        # 決定打：初期状態が SILENT だと Router がスキップされるため、検証可能状態へ強制昇格
        if cross.status == ReasoningStatus.SILENT:
            cross.status = ReasoningStatus.TENTATIVE_ANSWER
        
        log("puzzle_assembly", strategy=cross.strategy, status=cross.status.value)

        # DEBUG
        print(f"[DEBUG REPORT] Before router. Status: {cross.status}")
        print(f"[DEBUG REPORT] Condition check: {cross.status} not in ({ReasoningStatus.SILENT}, {ReasoningStatus.INSUFFICIENT_EVIDENCE}) -> {cross.status not in (ReasoningStatus.SILENT, ReasoningStatus.INSUFFICIENT_EVIDENCE)}")

        # 検証 (Router による実行制御)
        if cross.status not in (ReasoningStatus.SILENT, ReasoningStatus.INSUFFICIENT_EVIDENCE):
            cross = self.router.route_and_solve(cross, self.sim_engine, self.verifier)
            
            # 決定打：Solver から得られた統計情報を Trace に反映
            if "stats" in cross.metadata:
                stats = cross.metadata["stats"]
                trace.limits["max_worlds"] = stats.get("worlds", "?")
                if "models" in stats:
                    log("model_search_complete", checked_models=stats["models"])
            
            log("verification_complete", status=cross.status.value)

        # === 決定打：Cross → Program (コード生成・自動実証) ===
        if cross.status == ReasoningStatus.TENTATIVE_ANSWER:
            try:
                cross = execute_cross_verification(cross)
                log("execution_complete", status=cross.status.value)
            except Exception as e:
                log("execution_error", error=str(e))

        # === 決定打：Cross → Hardware (並列実証回路) ===
        if cross.status in (ReasoningStatus.TENTATIVE_ANSWER, ReasoningStatus.INSUFFICIENT_EVIDENCE):
            try:
                log("hardware_simulation_start")
                hw_graph = cross_to_hw_graph(cross)
                hw_results = self.pseudo_cpu.execute(hw_graph, cross.atoms)
                
                core_results = hw_results.get("core_unit")
                envs = hw_results.get("envs", [])
                
                if core_results:
                    # 全て真（かつNoneでない）なら PROVED
                    if all(r is True for r in core_results):
                        cross.status = ReasoningStatus.PROVED
                        cross.semantics["method"] = "hardware_simd_verification"
                    else:
                        # 偽のケースがあるか探索
                        for i, r in enumerate(core_results):
                            if r is False:
                                # 決定打：具体的反例を特定
                                cross.status = ReasoningStatus.DISPROVED
                                cross.semantics["method"] = "hardware_simd_refutation"
                                if i < len(envs):
                                    cross.counterexamples.append(envs[i])
                                break
                
                log("hardware_simulation_complete", status=cross.status.value)
            except Exception as e:
                log("hardware_simulation_error", error=str(e))

        # 4. 永続化 (Cross の保存)
        self.cross_db.add(cross)
        
        # 5. 自己削減・圧縮 (Forget & Compress)
        forget_res = self.forget_engine.process(cross, self.cross_db)
        log("knowledge_optimization", result=forget_res)

        # === 決定打：自動DB拡張 (Learning Engine) ===
        self.learning_engine.process_result(cross)
        if cross.metadata.get("auto_learned"):
            log("auto_learning_complete", new_id=cross.metadata.get("new_kb_id"))

        # 6. SILENT 昇格 (沈黙回避)
        cross = apply_silent_fallback(cross)

        # 7. Final Report Conversion
        self._finalize_status(cross)
        
        # --- NEW: Narrative Generation (Deterministic NLG) ---
        narrative_plan = self.narrative_solver.solve(cross)
        
        # Verify the generated narrative against facts
        nlg_errors = self.nlg_verifier.verify(narrative_plan, cross)
        
        if not nlg_errors:
            answer = self.narrative_solver.render(narrative_plan)
        else:
            # Fallback to mechanical output if narrative check fails
            print(f"[WARN] NLG Verification failed: {nlg_errors}")
            display_formula = cross.verified_formula or cross.core_formula
            answer = f"[{cross.status.value.upper()}] Target: {display_formula}. See logs for errors."

        if cross.status == ReasoningStatus.PROVED:
            rep = SolutionReport(status="proved", problem_key=problem_key, query=q, answer_text=answer)
            rep.proof = ProofBlock(method=cross.semantics.get('method', 'logic_engine'), steps=["Verified via logical inference and model checking."])
        elif cross.status == ReasoningStatus.DISPROVED:
            # 決定打：反例が見つかった場合の表示を純化
            cex = cross.counterexamples[0] if cross.counterexamples else cross.metadata.get("simulation_counterexample", {})
            rep = SolutionReport(status="disproved", problem_key=problem_key, query=q, answer_text=answer)
            rep.counterexample = CounterexampleBlock(method=cross.semantics.get('method', 'logic_engine'), structure=cex)
        elif cross.status == ReasoningStatus.INSUFFICIENT_EVIDENCE:
            rep = SolutionReport(status="insufficient_evidence", problem_key=problem_key, query=q, answer_text=answer)
            rep.why = cross.metadata.get("reason", "Inconclusive fragments.")
        elif cross.status == ReasoningStatus.SILENT:
             rep = SolutionReport(status="tentative_answer", problem_key=problem_key, query=q, answer_text=answer)
             rep.why = cross.metadata.get("rejection_reason", "Confidence below threshold.")
        else:
            # TENTATIVE_ANSWER
            rep = SolutionReport(status="tentative_answer", problem_key=problem_key, query=q, answer_text=answer)
            rep.why = cross.metadata.get("promotion_reason", "Structural analogy match.")
            
            rep.basis = {
                "query_type": cross.query_type.value,
                "missing": cross.metadata.get("missing_factors", []),
                "confidence": cross.metadata.get("confidence", 0.0)
            }

        # 決定打：DB知識からの提案をレポートに追加
        suggestions = self._suggest_relevant_theorems(cross)
        report_dict = rep.to_dict()
        
        # Include narrative plan for audit
        report_dict["narrative_plan"] = narrative_plan
        if nlg_errors:
            report_dict["nlg_errors"] = nlg_errors

        if suggestions:
            report_dict["relevant_knowledge"] = suggestions
            # UIで表示しやすいように next_actions にも一部追加
            current_actions = report_dict.get("next_actions", [])
            for s in suggestions[:3]:
                action = f"Apply {s['kind']}: {s['id']}"
                if action not in current_actions:
                    current_actions.append(action)
            report_dict["next_actions"] = current_actions

        return report_dict

    def _calculate_confidence(self, cross: ReasoningCross) -> float:
        """Verantyx流: 根拠の厚みを計算する"""
        # 決定打：既にメインの metadata に確固たる信頼度（公理一致など）がセットされていればそれをベースにする
        score = cross.metadata.get("confidence", 0.0)
        
        if score > 0:
            return min(score, 1.0)

        # 1. KB信頼度 (0.0 - 1.0)
        # evidence内の最高スコアを採用
        kb_scores = [ev.get("confidence", 0.0) for ev in cross.evidence if ev.get("kind") == "kb_match"]
        if kb_scores:
            score += max(kb_scores)
            
        # 2. 検証器結果 (+0.3 / -0.5)
        # method に応じて加算
        method = cross.semantics.get("method")
        if method in ("truth_table", "core_engine", "modal_axiom_dispatcher"):
            score += 0.3
        elif method == "lightweight_simulation":
            score += 0.1
            
        # 3. QueryType 適合度 (+0.2)
        # これは KB match 時に適用済みだが、ここでも構造的適合を見る
        if cross.query_type != QueryType.SINGLE:
             # 集合検証などが成功していれば加点
             if "set_results" in cross.metadata or cross.collection_results:
                 score += 0.2

        # 4. 反証リスク (減点)
        if not cross.counterexamples and method not in ("truth_table", "core_engine"):
            # 決定的な反証探索を経ていない場合
            score -= 0.1

        return min(max(score, 0.0), 1.0)

    def _finalize_status(self, cross: ReasoningCross):
        """計算されたConfidenceと閾値に基づいて最終ステータスを決定する"""
        
        # 既に確定的なステータスを持っている場合は、Confidence計算のみ行いステータスは維持
        # ただし、TENTATIVEの場合は昇格/降格の可能性がある
        
        confidence = self._calculate_confidence(cross)
        cross.metadata["confidence"] = confidence
        
        # 閾値の取得
        thresholds = self.active_profile.get_thresholds(cross.query_type)
        
        # ステータスの上書き判定
        if cross.status == ReasoningStatus.PROVED:
            # PROVEDでもConfidenceが低すぎる場合はTENTATIVEに落とす（安全策）
            if confidence < thresholds["proved"]:
                cross.status = ReasoningStatus.TENTATIVE_ANSWER
                cross.metadata["demotion_reason"] = "Confidence below PROVED threshold"
                cross.metadata["missing_factors"] = ["rigorous verification"]
        
        elif cross.status == ReasoningStatus.TENTATIVE_ANSWER:
            # TENTATIVEの場合、閾値チェック
            if confidence >= thresholds["proved"]:
                # PROVEDへの昇格は慎重に（基本はしないが、非常に高いならありうる）
                pass 
            elif confidence < thresholds["tentative"]:
                # 決定打：UIでの完全開示のため、SILENTには落とさず TENTATIVE のまま警告フラグを立てる
                # cross.status = ReasoningStatus.SILENT
                cross.metadata["low_confidence_warning"] = True
                cross.metadata["rejection_reason"] = "Confidence below TENTATIVE threshold"
                
