import re
from typing import Dict


def guess_domain(text: str) -> str:
    s = (text or "")
    sl = s.lower()

    rules: Dict[str, int] = {
        "modal_logic": 0,
        "propositional_logic": 0,
        "first_order_logic": 0,
        "linear_algebra": 0,
    }

    if any(k in sl for k in ("kripke", "modal", "box", "diamond")) or any(k in s for k in ("□", "◇")):
        rules["modal_logic"] += 3
    if any(k in s for k in ("到達", "可能世界", "様相", "反射", "推移", "対称", "ユークリッド")):
        rules["modal_logic"] += 2

    if any(k in sl for k in ("tautology", "truth table", "propositional")) or "命題" in s:
        rules["propositional_logic"] += 2
    if any(k in s for k in ("∧", "∨", "¬", "⊤", "⊥")) or any(k in sl for k in ("->", "<->", "&", "|", "~")):
        rules["propositional_logic"] += 1

    if any(k in s for k in ("∀", "∃", "一階", "述語")) or any(k in sl for k in ("forall", "exists", "first-order", "predicate")):
        rules["first_order_logic"] += 3

    if any(k in s for k in ("行列", "線形", "次元", "固有値", "階数")) or any(k in sl for k in ("matrix", "linear algebra", "eigenvalue", "rank")):
        rules["linear_algebra"] += 3

    best = max(rules.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "unknown"
