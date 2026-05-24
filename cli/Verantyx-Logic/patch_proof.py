from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Callable


@dataclass
class Patch:
    add_edges: List[Tuple[int, int]]
    remove_edges: List[Tuple[int, int]]


def _edge_set_from_cex(cex: Dict[str, Any]) -> Set[Tuple[int, int]]:
    edges = cex.get("edges", []) or []
    out: Set[Tuple[int, int]] = set()
    for e in edges:
        if isinstance(e, (list, tuple)) and len(e) == 2:
            a, b = e
            if isinstance(a, int) and isinstance(b, int):
                out.add((a, b))
    return out


def apply_patch_to_counterexample(cex: Dict[str, Any], patch: Patch) -> Dict[str, Any]:
    """
    反例モデルに対して edge の add/remove を適用した新しいモデルを返す。
    valuation 等はそのまま残す（Phase 11 の目的は構造破壊の確認）。
    """
    worlds = int(cex.get("n_worlds") or cex.get("worlds") or 0)
    es = _edge_set_from_cex(cex)

    for a, b in patch.remove_edges:
        es.discard((a, b))
    for a, b in patch.add_edges:
        # 範囲外は無視（安全）
        if 0 <= a < worlds and 0 <= b < worlds:
            es.add((a, b))

    new_cex = dict(cex)
    new_cex["edges"] = [[a, b] for (a, b) in sorted(es)]
    return new_cex


# ----------------------------
# Assumption checks (MVP)
# ----------------------------

def check_assumption_satisfied(cex: Dict[str, Any], assumption: str) -> bool:
    worlds = int(cex.get("n_worlds") or cex.get("worlds") or 0)
    es = _edge_set_from_cex(cex)

    if assumption == "assume:reflexive":
        return all((i, i) in es for i in range(worlds))

    if assumption == "assume:symmetric":
        return all((b, a) in es for (a, b) in es)

    if assumption == "assume:transitive":
        # if (x,y) and (y,z) then (x,z)
        for (x, y) in es:
            for (y2, z) in es:
                if y2 == y and (x, z) not in es:
                    return False
        return True

    if assumption == "assume:euclidean":
        # if (a,b) and (a,c) then (b,c)
        for (a, b) in es:
            for (a2, c) in es:
                if a2 == a and (b, c) not in es:
                    return False
        return True

    # unknown assumption kind => can't verify, treat as False to be conservative
    return False


# ----------------------------
# Formula recheck hook
# ----------------------------

def recheck_formula_with_model_search(
    model_checker_fn: Callable[[str, Dict[str, Any]], bool],
    formula: str,
    assumptions: List[str], # Not used for direct model check, but kept for signature compat if needed
    patched_cex: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Check if patched_cex is STILL a counterexample.
    model_checker_fn(formula, model) returns True if model satisfies formula (VALID), False if COUNTEREXAMPLE.
    """
    try:
        # If model satisfies formula, it is NOT a counterexample anymore.
        is_valid_on_model = model_checker_fn(formula, patched_cex)
        
        if is_valid_on_model:
            return {
                "still_counterexample": False, 
                "note": "Formula holds on the patched model (counterexample destroyed)."
            }
        else:
            return {
                "still_counterexample": True, 
                "note": "Formula still fails on the patched model."
            }
    except Exception as e:
        return {"still_counterexample": None, "note": f"Error during recheck: {e}"}

def model_search_wrapper(
    model_search_fn: Callable, 
    formula: str, 
    assumptions: List[str]
) -> Dict[str, Any]:
    """
    engineの model_search を呼ぶための薄いラッパ。
    返り値形式を統一:
      { "valid": bool, "counterexample": dict|None, "note": str }
    """
    # model_search_fn is usually find_counterexample from verifier.py
    # find_counterexample returns VerifyResult
    res = model_search_fn(formula=formula, assumptions=assumptions)
    
    # Adapt VerifyResult to dict
    is_valid = (res.status == "valid")
    return {
        "valid": is_valid,
        "counterexample": res.counterexample,
        "note": f"Status: {res.status}. Audit: {res.audit[-1] if res.audit else ''}"
    }