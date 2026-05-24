from typing import Any, Dict
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.avh_math.answer_types.query_type import QueryType
from avh_math.puzzle.inference_profile import InferenceProfile

class SolverRouter:
    def __init__(self, profile: InferenceProfile):
        self.profile = profile

    def _solve_single(self, formula: str, cross: ReasoningCross, sim_engine: Any, verifier: Any) -> Dict[str, Any]:
        """単一の式に対するシミュレーションと検証の統合フロー"""
        # シミュレーション優先判定
        if self.profile.simulation_weight >= self.profile.puzzle_weight:
            # 簡易シミュレーション実行（ここでは詳細省略、必要なら cross を複製してシミュレーションにかける）
            pass
            
        # 決定打：Verifier は ReasoningCross オブジェクトを要求するため、一時的なオブジェクトを作成して渡す
        temp_cross = ReasoningCross(
            domain=cross.domain,
            core_formula=formula,
            assumptions=cross.assumptions,
            atoms=cross.atoms,
            query_type=QueryType.SINGLE # 個別検証は常に SINGLE
        )
        return verifier.verify(temp_cross)

    def route_and_solve(self, cross: ReasoningCross, sim_engine: Any, verifier: Any) -> ReasoningCross:
        """プロファイルとQueryTypeに従って推論パスを制御する"""
        try:
            qt = getattr(cross, "query_type", QueryType.SINGLE)
            print(f"[DEBUG ROUTER] Route called. QT={qt}, Candidates={len(cross.candidates)}")
            
            # --- 1. EQUIVALENCE の変換 ---
            if qt == QueryType.EQUIVALENCE and len(cross.candidates) == 2:
                print("[DEBUG ROUTER] Branch: EQUIVALENCE")
                f1, f2 = cross.candidates
                cross.core_formula = f"(({f1})->({f2})) & (({f2})->({f1}))"
                qt = QueryType.SINGLE # 以降は単一式として扱う

            # --- 2. 集合検証 (SET_ALL / SET_ANY) ---
            if qt in (QueryType.SET_ALL, QueryType.SET_ANY):
                print(f"[DEBUG ROUTER] Branch: {qt.name}")
                cross.collection_results = [] # リセットして蓄積
                
                for f in cross.candidates:
                    res = self._solve_single(f, cross, sim_engine, verifier)
                    
                    # 状態の取得
                    v_status = res.get("status")
                    if isinstance(v_status, str):
                        v_status = ReasoningStatus.from_str(v_status)
                    
                    # 構造化ノードとして追加
                    cross.add_collection_item(f, v_status, res)
                    
                    if qt == QueryType.SET_ALL and v_status == ReasoningStatus.DISPROVED:
                        cross.status = ReasoningStatus.DISPROVED
                        cross.metadata["failed_formula"] = f
                        if "verified_formula" in res:
                            cross.verified_formula = res["verified_formula"]
                        if res.get("counterexample"):
                            cross.counterexamples.append(res.get("counterexample"))
                        return cross
                    
                    if qt == QueryType.SET_ANY and v_status == ReasoningStatus.PROVED:
                        cross.status = ReasoningStatus.PROVED
                        cross.verified_formula = f
                        cross.semantics["method"] = res.get("method", "set_validator")
                        return cross

                print(f"[DEBUG ROUTER] Collection processed. Count: {len(cross.collection_results)}")
                
                # 集約判定
                if qt == QueryType.SET_ALL:
                    # 全てが PROVED なら全体も PROVED
                    if all(item["status"] == ReasoningStatus.PROVED.value for item in cross.collection_results):
                        cross.status = ReasoningStatus.PROVED
                        # 代表的な情報を先頭アイテムから取得
                        if cross.collection_results:
                            first = cross.collection_results[0]["result"]
                            cross.semantics["method"] = first.get("method", "set_validator")
                            if "confidence" in first:
                                cross.metadata["confidence"] = first["confidence"]
                    else:
                        # PROVED でないものが混ざっているが、DISPROVED (即リターン済み) もない
                        cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
                else: # SET_ANY
                    # ここに来るということは PROVED が1つもなかったということ
                    cross.status = ReasoningStatus.DISPROVED
                    cross.metadata["reason"] = "No valid formula found in the set."
                
                return cross

            # --- 3. SINGLE (標準フロー) ---
            target_formula = cross.core_formula or (cross.candidates[0] if cross.candidates else None)
            if not target_formula:
                cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
                return cross

            verify_res = self._solve_single(target_formula, cross, sim_engine, verifier)
            
            if verify_res:
                v_status = verify_res.get("status")
                if isinstance(v_status, str):
                    cross.status = ReasoningStatus.from_str(v_status)
                else:
                    cross.status = v_status
                
                cross.semantics["method"] = verify_res.get("method")
                
                # 決定打：検証済み式（正規化後）を反映
                if "verified_formula" in verify_res:
                    cross.verified_formula = verify_res["verified_formula"]
                
                if "counterexample" in verify_res:
                    cross.counterexamples.append(verify_res["counterexample"])
                if "kb_id" in verify_res:
                    cross.evidence.append({"kind": "kb_match", "id": verify_res["kb_id"]})
                
                # 決定打：信頼度を反映
                if "confidence" in verify_res:
                    cross.metadata["confidence"] = verify_res["confidence"]
                
                # 決定打：統計情報を反映
                if "stats" in verify_res:
                    cross.metadata["stats"] = verify_res["stats"]

            # 4. 沈黙の閾値判定
            confidence = cross.metadata.get("mapping_confidence", 0.0)
            if cross.status == ReasoningStatus.TENTATIVE_ANSWER and confidence < self.profile.silent_threshold:
                if not self.profile.trust_recent_kb:
                    cross.status = ReasoningStatus.SILENT
                    cross.metadata["rejection_reason"] = "Below silent threshold of the active profile"

        except Exception as e:
            print(f"[DEBUG ROUTER] Error in route_and_solve: {e}")
            import traceback
            traceback.print_exc()
            cross.status = ReasoningStatus.TENTATIVE_ANSWER
            cross.metadata["router_error"] = str(e)

        return cross
