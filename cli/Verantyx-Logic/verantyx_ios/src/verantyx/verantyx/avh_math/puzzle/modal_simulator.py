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
        formula = formula.replace(" ", "").replace("□", "[]").replace("◇", "<>")
        return _eval_recursive(formula, world, frame)
    except Exception:
        return None

def _eval_recursive(formula: str, world: str, frame: KripkeFrame) -> Optional[bool]:
    if not formula: return None
    if len(formula) == 1 and formula.isalpha():
        return frame.valuation.get(world, {}).get(formula, False)
    if formula.startswith("~"):
        v = _eval_recursive(formula[1:], world, frame)
        return not v if v is not None else None
    if formula.startswith("[]"):
        inner = formula[2:]
        for next_world in frame.accessibility.get(world, []):
            if _eval_recursive(inner, next_world, frame) is False: return False
        return True
    if formula.startswith("<>"):
        inner = formula[2:]
        for next_world in frame.accessibility.get(world, []):
            if _eval_recursive(inner, next_world, frame) is True: return True
        return False
    if "->" in formula:
        idx = _find_main_implication(formula)
        if idx != -1:
            left_v = _eval_recursive(formula[:idx], world, frame)
            right_v = _eval_recursive(formula[idx+2:], world, frame)
            if left_v is True and right_v is False: return False
            if left_v is not None and right_v is not None: return True
    return None

def _find_main_implication(formula: str) -> int:
    balance = 0
    for i in range(len(formula) - 1):
        if formula[i] == "(": balance += 1
        elif formula[i] == ")": balance -= 1
        elif balance == 0 and formula[i:i+2] == "->": return i
    return -1

def run_modal_simulation(formula: str, atoms: List[str], assumptions: List[str]) -> List[Dict[str, Any]]:
    """
    Verifier を利用して徹底的な反例探索を行う。
    """
    from avh_math.verifier import find_counterexample, VerifyConfig
    results = []
    cfg = VerifyConfig(max_worlds=4, max_edges=6, check_world=0)
    res = find_counterexample(formula, atoms, assumptions, cfg)
    
    if res.status == "invalid":
        results.append({
            "type": "kripke_valuation",
            "input": res.counterexample.get("valuation"),
            "frame": {"n_worlds": res.counterexample.get("n_worlds"), "edges": res.counterexample.get("edges")},
            "world": res.counterexample.get("at_world"),
            "result": False,
            "status": "violated",
            "details": "Counterexample found by exhaustive search."
        })
    else:
        results.append({"type": "kripke_valuation", "result": True, "status": "satisfied"})
    return results
