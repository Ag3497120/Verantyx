from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

@dataclass
class RepairSuggestion:
    add: List[str]                 # 追加すべき assume:*
    because: str                   # 理由
    refs: List[str]                # knowledge_db の correspondence id 等
    confidence: float = 0.6        # ざっくり（DBの確信度を将来入れられる）


def suggest_repairs(
    formula: str,
    current_assumptions: List[str],
    knowledge_db: Dict[str, Any],
    missing_assumptions: Optional[List[str]] = None,
) -> List[RepairSuggestion]:
    """
    invalid のときに「この仮定を足すと成立する可能性が高い」を返す。
    ルール：
      1) knowledge_db.assumption_repair_hints[formula] があればそれを採用
      2) missing_assumptions があれば「それを足せ」も候補にする（DBが薄い場合の安全網）
    """
    cur: Set[str] = set(current_assumptions)
    out: List[RepairSuggestion] = []

    # Normalized formula lookup (assuming knowledge_db keys are normalized or we normalize here)
    # For now, simple lookup
    hints = (knowledge_db.get("assumption_repair_hints") or {}).get(formula) or []
    for h in hints:
        add = [a for a in (h.get("add") or []) if a not in cur]
        if not add:
            continue
        out.append(
            RepairSuggestion(
                add=add,
                because=str(h.get("because") or "Add missing frame property."),
                refs=list(h.get("refs") or []),
                confidence=float(h.get("confidence", 0.75)),
            )
        )

    # fallback: missing_assumptions があるなら、それをそのまま提案
    if missing_assumptions:
        add2 = [a for a in missing_assumptions if a not in cur]
        if add2:
            out.append(
                RepairSuggestion(
                    add=sorted(set(add2)),
                    because="This candidate failed under current assumptions; adding the missing assumptions may repair validity.",
                    refs=[],
                    confidence=0.55,
                )
            )

    # 重複除去（add が同じなら統合）
    uniq: Dict[str, RepairSuggestion] = {}
    for s in out:
        key = ",".join(sorted(s.add))
        if key not in uniq:
            uniq[key] = s
        else:
            # refs をマージ
            uniq[key].refs = sorted(set(uniq[key].refs + s.refs))
            uniq[key].confidence = max(uniq[key].confidence, s.confidence)

    # confidence 高い順
    return sorted(uniq.values(), key=lambda x: x.confidence, reverse=True)