from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import re

@dataclass
class KripkeFrame:
    worlds: List[str] = field(default_factory=list)
    accessibility: Dict[str, List[str]] = field(default_factory=dict)
    valuation: Dict[str, Dict[str, bool]] = field(default_factory=dict)

def eval_modal(formula: str, world: str, frame: KripkeFrame) -> Optional[bool]:
    """
    Kripke フレーム上の指定された世界で様相式を評価する。
    (旧来のロジックとの互換性のために保持)
    """
    if frame is None or not frame.worlds or world not in frame.worlds:
        return None
    try:
        # 正規化
        formula = formula.replace(" ", "").replace("□", "[]").replace("◇", "<>")
        return _eval_recursive(formula, world, frame)
    except Exception:
        return None

def _eval_recursive(formula: str, world: str, frame: KripkeFrame) -> Optional[bool]:
    if not formula:
        return None

    # 1. 原子命題
    if len(formula) == 1 and formula.isalpha():
        return frame.valuation.get(world, {}).get(formula, False)

    # 2. 否定 (~p)
    if formula.startswith("~"):
        v = _eval_recursive(formula[1:], world, frame)
        return not v if v is not None else None

    # 3. 必要性 ([]p)
    if formula.startswith("[]"):
        inner = formula[2:]
        for next_world in frame.accessibility.get(world, []):
            res = _eval_recursive(inner, next_world, frame)
            if res is False:
                return False 
        return True

    # 4. 可能性 (<>p)
    if formula.startswith("<>"):
        inner = formula[2:]
        for next_world in frame.accessibility.get(world, []):
            res = _eval_recursive(inner, next_world, frame)
            if res is True:
                return True 
        return False

    # 5. 含意 (A->B)
    if "->" in formula:
        idx = _find_main_implication(formula)
        if idx != -1:
            left = formula[:idx]
            right = formula[idx+2:]
            left_v = _eval_recursive(left, world, frame)
            right_v = _eval_recursive(right, world, frame)
            if left_v is True and right_v is False:
                return False
            if left_v is not None and right_v is not None:
                return True
            return None

    return None

def _find_main_implication(formula: str) -> int:
    """最も外側にある -> のインデックスを返す"""
    balance = 0
    for i in range(len(formula) - 1):
        char = formula[i]
        if char == "(": balance += 1
        elif char == ")": balance -= 1
        elif balance == 0 and formula[i:i+2] == "->":
            return i
    return -1

def run_modal_simulation(formula: str, atoms: List[str], assumptions: List[str]) -> List[Dict[str, Any]]:
    """
    Verifier を利用して徹底的な反例探索を行う。
    """
    from avh_math.verifier import find_counterexample, VerifyConfig
    results = []
    
    # 決定打：verifier.py の強力な探索機能を利用する
    cfg = VerifyConfig(max_worlds=4, max_edges=6, check_world=0)
    res = find_counterexample(formula, atoms, assumptions, cfg)
    
    if res.status == "invalid":
        results.append({
            "type": "kripke_valuation",
            "input": res.counterexample.get("valuation"),
            "frame": {
                "n_worlds": res.counterexample.get("n_worlds"),
                "edges": res.counterexample.get("edges")
            },
            "world": res.counterexample.get("at_world"),
            "result": False,
            "status": "violated", 
            "details": "Counterexample found by exhaustive search."
        })
    else:
        results.append({
            "type": "kripke_valuation",
            "result": True,
            "status": "satisfied",
            "details": "No counterexample found within search bounds."
        })
            
    return results