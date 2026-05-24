from typing import Any
from avh_math.problem_patterns.matcher import match_problem_pattern
from avh_math.puzzle.status_types import ReasoningStatus

def classify_and_prepare_cross(text_cross_signature: list[str], reasoning_cross: Any):
    """
    形状シグネチャに基づいて問題タイプを分類し、ReasoningCrossの状態を更新する。
    """
    pattern = match_problem_pattern(text_cross_signature)

    if not pattern:
        # パターンが見つからない場合は現状維持（または silent 誘導）
        reasoning_cross.metadata["pattern_match"] = "none"
        return reasoning_cross

    # 分類成功：戦略と検証モードを上書き
    reasoning_cross.strategy = pattern.pattern_id
    reasoning_cross.metadata["solver_mode"] = pattern.solver_mode
    reasoning_cross.metadata["pattern_match"] = pattern.pattern_id

    # 必須スロット（ピース）のチェック
    missing = []
    for slot in pattern.required_slots:
        if slot == "formula" and not (reasoning_cross.verified_formula or reasoning_cross.core_formula):
            missing.append("formula")
        if slot == "assumption" and not reasoning_cross.assumptions:
            missing.append("assumption")

    if missing:
        # 構造は一致したが、中身（ピース）が足りない
        reasoning_cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
        reasoning_cross.metadata["missing_slots"] = missing
    else:
        # すべて揃った：検証準備完了
        reasoning_cross.metadata["ready_for_solver"] = True

    return reasoning_cross
