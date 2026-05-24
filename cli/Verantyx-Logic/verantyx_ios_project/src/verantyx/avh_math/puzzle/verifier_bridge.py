from typing import Tuple, Dict, Any, Optional
from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.puzzle.propositional_verifier import verify_propositional_exhaustive
from avh_math.puzzle.modal_verifier import verify_modal_exhaustive
from avh_math.puzzle.formula_sanitizer import sanitize_formula

def finalize_verdict(
    current_status: ReasoningStatus,
    formula: str,
    domain: str,
    assumptions: list,
    atoms: list
) -> Tuple[ReasoningStatus, Optional[Dict[str, Any]]]:
    """
    現在のステータスが TENTATIVE であれば、厳密な検証器を走らせて確定を試みる。
    """
    if current_status != ReasoningStatus.TENTATIVE_ANSWER:
        return current_status, None

    # 決定打：自然文ノイズを徹底除去
    clean_formula = sanitize_formula(formula)
    if not clean_formula:
        return ReasoningStatus.INSUFFICIENT_EVIDENCE, {"reason": "Could not extract pure formula from text."}

    if domain == "propositional_logic":
        status_str, extra = verify_propositional_exhaustive(clean_formula, atoms)
        return ReasoningStatus.from_str(status_str), extra

    if domain == "modal_logic":
        status_str, extra = verify_modal_exhaustive(clean_formula, assumptions, atoms)
        return ReasoningStatus.from_str(status_str), extra

    return current_status, None
