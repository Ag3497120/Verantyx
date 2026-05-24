from typing import List, Set, Dict, Any
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus

# 様相公理の要件定義
MODAL_AXIOM_PROFILES = {
    "K": {"requires": set(), "description": "Normal modal logic (Distribution)"},
    "T": {"requires": {"reflexive"}, "description": "Reflexive frames (□p -> p)"},
    "4": {"requires": {"transitive"}, "description": "Transitive frames (□p -> □□p)"},
    "B": {"requires": {"symmetric"}, "description": "Symmetric frames (p -> □<>p)"},
    "S4": {"requires": {"reflexive", "transitive"}, "description": "Preorder frames"},
    "S5": {"requires": {"reflexive", "transitive", "symmetric"}, "description": "Equivalence frames"},
}

def infer_frame_properties(simulation_results: List[Dict[str, Any]]) -> Set[str]:
    """シミュレーションで使用されたフレームの性質を抽出する"""
    props = set()
    for res in simulation_results:
        if res.get("type") == "kripke_valuation":
            # 決定打：simulation_engine が付与した情報を取得
            # (現在はシミュレーション全体で単一のフレームを使用しているため、
            #  各リザルトではなくコンテキストから取る設計だが、
            #  ここでは便宜的に全ての真理値割当において共通の性質を認める)
            # 実際には cross.assumptions から直接取る方が確実
            pass
    return props

class ModalAxiomDetector:
    def detect_and_apply(self, cross: ReasoningCross) -> ReasoningCross:
        """シミュレーション結果から公理を特定し、Cross を昇格させる"""
        if cross.domain != "modal_logic":
            return cross

        # 決定打：cross.assumptions から直接性質を特定（確実な方法）
        current_props = set()
        for a in cross.assumptions:
            if "transitive" in a: current_props.add("transitive")
            if "reflexive" in a: current_props.add("reflexive")
            if "symmetric" in a: current_props.add("symmetric")
        
        # 2. シミュレーションで違反（反例）がなかったか確認
        has_violation = any(res["status"] == "violated" for res in cross.simulation)
        if has_violation:
            return cross # 反例がある場合は昇格させない

        # 3. 公理のマッチング
        matched_axioms = []
        for name, profile in MODAL_AXIOM_PROFILES.items():
            if profile["requires"] and profile["requires"].issubset(current_props):
                matched_axioms.append(name)

        if matched_axioms:
            # 証拠として記録
            cross.evidence.append({
                "type": "modal_axiom_detected",
                "axioms": matched_axioms,
                "detected_props": list(current_props)
            })
            # 最も強い公理（要件が多いもの）を代表としてステータス昇格の根拠にする
            strongest = max(matched_axioms, key=lambda x: len(MODAL_AXIOM_PROFILES[x]["requires"]))
            cross.metadata["detected_strongest_axiom"] = strongest
            
            # シミュレーションで成功しており、かつ公理が特定されたなら PROVED へ昇格
            if any(res["status"] == "satisfied" for res in cross.simulation):
                cross.status = ReasoningStatus.PROVED
                cross.semantics["method"] = "modal_axiom_detection"
                cross.metadata["promotion_reason"] = f"Verified under modal axiom {strongest}"

        return cross
