from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class ProblemPattern:
    pattern_id: str
    text_signature: List[str]   # Text-Cross の shape 列（期待値）
    required_slots: List[str]   # 推論に必要なピース（formula, assumption等）
    solver_mode: str            # 誘導先の検証モード

# 初期レジストリ：形状のみで分類
PROBLEM_PATTERNS: List[ProblemPattern] = [
    # 妥当性判定型（例：[]p -> [][]p は成り立つか？）
    ProblemPattern(
        pattern_id="validity_check",
        text_signature=["modal", "symbol", "arrow", "modal", "modal", "symbol"],
        required_slots=["formula"],
        solver_mode="modal_validity"
    ),
    
    # 条件付き妥当性判定（例：推移的であるとき、〜）
    ProblemPattern(
        pattern_id="assumption_validity_check",
        text_signature=["word", "word", "other", "modal", "symbol", "arrow", "modal", "modal", "symbol"],
        required_slots=["assumption", "formula"],
        solver_mode="modal_validity"
    ),
    
    # 命題論理の恒真性（例：p -> p は恒真か？）
    ProblemPattern(
        pattern_id="tautology_check",
        text_signature=["symbol", "arrow", "symbol"],
        required_slots=["formula"],
        solver_mode="prop_tautology"
    ),
]
