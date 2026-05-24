from itertools import combinations
from typing import List, Dict, Any
import uuid

def extract_axiom_pieces(cross: Any) -> List[Dict[str, Any]]:
    """
    ReasoningCross の evidence 軸から、利用可能な公理や定理のピースを抽出する。
    """
    # 実際の実装では cross.evidence から取得
    pieces = []
    for ev in getattr(cross, 'evidence', []):
        if ev.get("kind") in ("axiom", "theorem", "rule"):
            # 必要な情報が揃っているか確認
            if "statement" in ev or "content" in ev:
                pieces.append(ev)
    return pieces

def compose_formula(a: str, b: str, mode: str) -> str:
    """
    2つの式を特定の推論モードで合成する。
    """
    # 簡易的な正規化
    a, b = a.strip(), b.strip()
    
    if mode == "implication_chain":
        return f"({a}) -> ({b})"
    if mode == "conjunction":
        return f"({a}) & ({b})"
    if mode == "modus_ponens":
        # a が前提、a -> b の形を探す（または強制的に作る）
        return f"(({a}) & ({a} -> {b})) -> {b}"
    return ""

def generate_composite_candidates(pieces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    抽出された公理ピースの組み合わせから、新しい合成候補を生成する。
    """
    candidates = []
    
    # 2つの公理の組み合わせを試行
    for p1, p2 in combinations(pieces, 2):
        f1 = p1.get("statement") or p1.get("content")
        f2 = p2.get("statement") or p2.get("content")
        
        if not f1 or not f2:
            continue

        for mode in ["implication_chain", "conjunction", "modus_ponens"]:
            composed = compose_formula(f1, f2, mode)
            if composed:
                candidates.append({
                    "id": f"composed_{uuid.uuid4().hex[:8]}",
                    "formula": composed,
                    "source_ids": [p1.get("id"), p2.get("id")],
                    "mode": mode,
                    "confidence": 0.7 # 合成候補なので初期確信度は中程度
                })
                
    return candidates
