from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus

def force_tentative_from_cross(cross: ReasoningCross) -> ReasoningCross:
    """
    ReasoningCross 内の各軸を走査し、最良の候補を TENTATIVE として強制的に出力する。
    """
    if cross.status != ReasoningStatus.SILENT and cross.status != ReasoningStatus.INSUFFICIENT_EVIDENCE:
        return cross

    # 1. 優先順位に従って有効なコンテンツを持つノードを探す
    # core (全体式) -> syntax (部分式) -> evidence (根拠)
    candidate_formula = None
    source_axis = None

    if cross.core_formula:
        candidate_formula = cross.core_formula
        source_axis = "core"
    elif cross.syntax_nodes:
        candidate_formula = cross.syntax_nodes[0]
        source_axis = "syntax"
    elif cross.evidence:
        # evidence 軸から式（statement等）を抽出
        for ev in cross.evidence:
            if ev.get("statement"):
                candidate_formula = ev["statement"]
                source_axis = "evidence"
                break

    if candidate_formula:
        cross.status = ReasoningStatus.TENTATIVE_ANSWER
        cross.metadata["fallback_answer"] = {
            "formula": candidate_formula,
            "source": source_axis,
            "note": "構造的な類推に基づく仮回答（検証未完了）",
            "confidence": "low"
        }
        cross.metadata["is_forced_tentative"] = True
    else:
        # 本当に何も無い場合のみ INSUFFICIENT
        cross.status = ReasoningStatus.INSUFFICIENT_EVIDENCE
        cross.metadata["reason"] = "構成可能な構造が見つかりませんでした。"

    return cross

def apply_silent_fallback(cross: ReasoningCross) -> ReasoningCross:
    """
    既存のフォールバック処理を、強制昇格ロジックでラップする。
    """
    return force_tentative_from_cross(cross)