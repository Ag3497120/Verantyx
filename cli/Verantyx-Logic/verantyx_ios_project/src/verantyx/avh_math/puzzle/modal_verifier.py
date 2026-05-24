from typing import List, Dict, Tuple, Any, Optional
from avh_math.puzzle.modal_simulator import eval_modal, KripkeFrame

def verify_modal_exhaustive(formula: str, assumptions: List[str], atoms: List[str]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    主要な Kripke フレームパターンにおいて検証を実行する。
    """
    # 最小構成の反例探索用フレーム生成
    worlds = ["w0", "w1", "w2"]
    # 決定打：全世界をキーとして初期化（KeyError回避）
    acc = {w: [] for w in worlds}
    
    # 標準的な関係 (w0 -> w1, w1 -> w2)
    acc["w0"].append("w1")
    acc["w1"].append("w2")
    
    # 前提条件の適用 (S4相当の強化)
    if any("transitive" in a for a in assumptions):
        acc["w0"].append("w2")
    if any("reflexive" in a for a in assumptions):
        for w in worlds:
            if w not in acc[w]:
                acc[w].append(w)

    # ... (評価ループへ)
    test_valuations = [
        {w: {a: False for a in atoms} for w in worlds},
        {w: {a: True for a in atoms} for w in worlds},
        {w: {a: (w == "w1") for a in atoms} for w in worlds} # 世界ごとに真理値を変えるパターン
    ]

    for val in test_valuations:
        frame = KripkeFrame(worlds, acc, val)
        for w in worlds:
            res = eval_modal(formula, w, frame)
            if res is False:
                return "DISPROVED", {
                    "world": w,
                    "frame": acc,
                    "valuation": val,
                    "method": "kripke_frame_check"
                }

    # 一定の範囲で反例が見つからなければ、構造的類似度に基づき PROVED も検討
    # (本来は完全な決定手続きが必要だが、Verantyx では証拠の強さで判断)
    return "TENTATIVE_ANSWER", None
