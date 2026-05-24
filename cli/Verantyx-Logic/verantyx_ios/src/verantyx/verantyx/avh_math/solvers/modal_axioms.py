from __future__ import annotations

import re
from typing import Dict, Any

def _split_implication(s: str) -> tuple[str, str] | None:
    """最上位の含意 '->' で分割する（括弧のネストを考慮）"""
    depth = 0
    for i in range(len(s) - 1):
        ch = s[i]
        if ch == '(': depth += 1
        elif ch == ')': depth -= 1
        elif depth == 0 and s[i:i+2] == '->':
            return s[:i], s[i+2:]
    return None

def _strip_outer_parens(s: str) -> str:
    while s.startswith('(') and s.endswith(')') and _split_implication(s[1:-1]) is None:
        # 単一の括弧で囲まれている場合のみ剥がす（(p->q)->r のようなケースを壊さないため）
        s = s[1:-1]
    return s

def check_modal_axiom(formula: str, assumptions: list[str] | None = None) -> Dict[str, Any] | None:
    f = (formula or "").replace(" ", "")
    # 外側の括弧を剥がす
    f = _strip_outer_parens(f)
    
    # Normalize assumptions
    assumptions = [a.replace("assume:", "").strip().lower() for a in (assumptions or [])]
    
    print(f"[DEBUG AXIOM] Checking: {f} with {assumptions}")

    if "universal_logic" in assumptions:
        return None

    # 分割
    parts = _split_implication(f)
    if not parts:
        print("[DEBUG AXIOM] Split failed (no implication)")
        return None
    lhs, rhs = _strip_outer_parens(parts[0]), _strip_outer_parens(parts[1])
    print(f"[DEBUG AXIOM] LHS: {lhs}, RHS: {rhs}")

    # 1. Axiom T: []p -> p
    if lhs.startswith("[]") and lhs[2:] == rhs:
        if "reflexive" in assumptions:
            return {
                "status": "valid",
                "axiom": "T",
                "reason": "Reflexivity axiom: □p → p is valid on reflexive frames.",
            }

    # 2. Axiom 4: []p -> [][]p
    if lhs.startswith("[]") and rhs.startswith("[][]") and lhs[2:] == rhs[4:]:
        if "transitive" in assumptions:
            return {
                "status": "valid",
                "axiom": "4",
                "reason": "Transitivity axiom: □p → □□p is valid on transitive frames.",
            }

    # 3. Axiom B: p -> []<>p
    if rhs.startswith("[]<>") and lhs == rhs[4:]:
        if "symmetric" in assumptions:
            return {
                "status": "valid",
                "axiom": "B",
                "reason": "Symmetry axiom: p → □◇p is valid on symmetric frames.",
            }

    # 4. Axiom 5: <>p -> []<>p
    if lhs.startswith("<>") and rhs.startswith("[]<>") and lhs[2:] == rhs[4:]:
        if "euclidean" in assumptions:
            return {
                "status": "valid",
                "axiom": "5",
                "reason": "Euclidean axiom: ◇p → □◇p is valid on euclidean frames.",
            }

    # 5. Axiom K: [](p->q) -> ([]p -> []q)
    if lhs.startswith("[]") and "(" in lhs:
        inner_k = lhs[2:].strip("()")
        k_parts = _split_implication(inner_k)
        if k_parts:
            p, q = k_parts
            # rhs が ([]p -> []q) の形か
            rhs_parts = _split_implication(rhs)
            if rhs_parts:
                r_lhs, r_rhs = _strip_outer_parens(rhs_parts[0]), _strip_outer_parens(rhs_parts[1])
                if r_lhs == f"[]{p}" and r_rhs == f"[]{q}":
                    return {
                        "status": "valid",
                        "axiom": "K",
                        "reason": "Distribution axiom: □(p→q) → (□p→□q) is valid on all Kripke frames.",
                    }
            
    return None
