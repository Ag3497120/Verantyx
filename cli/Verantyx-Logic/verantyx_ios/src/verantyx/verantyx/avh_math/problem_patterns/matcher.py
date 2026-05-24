from typing import List, Optional
from avh_math.problem_patterns.registry import PROBLEM_PATTERNS, ProblemPattern

def structure_similarity(a: List[str], b: List[str]) -> float:
    """
    2つの形状シーケンスの類似度を計算する（順序を重視）。
    """
    if not a or not b:
        return 0.0
    
    # 簡易的な位置一致カウント
    common = sum(1 for x, y in zip(a, b) if x == y)
    return common / max(len(a), len(b))

def match_problem_pattern(text_cross_signature: List[str], threshold: float = 0.6) -> Optional[ProblemPattern]:
    """
    シグネチャから最適な問題パターンを返す。
    """
    best = None
    best_score = 0.0

    for pattern in PROBLEM_PATTERNS:
        score = structure_similarity(text_cross_signature, pattern.text_signature)
        if score > best_score and score >= threshold:
            best = pattern
            best_score = score

    return best
