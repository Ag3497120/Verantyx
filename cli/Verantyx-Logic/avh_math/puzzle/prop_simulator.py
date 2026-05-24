import itertools
import re
from typing import List, Dict, Tuple, Any

def eval_propositional(formula: str, valuation: Dict[str, bool]) -> bool:
    """
    論理式を指定された真理値割り当てで評価する。
    """
    # 1. 演算子の変換
    expr = formula.replace("->", " <= ").replace("<->", " == ")
    expr = expr.replace("&", " and ").replace("|", " or ").replace("~", " not ")
    
    try:
        # valuation を globals として渡すことで変数を直接評価可能にする
        res = eval(expr, {"__builtins__": None}, valuation)
        return bool(res)
    except Exception:
        return None

def run_prop_simulation(formula: str, atoms: List[str]) -> List[Dict[str, Any]]:
    """
    主要なケース（全偽、全真、一部真など）でシミュレーションを実行する。
    """
    results = []
    # 変数が多い場合は全通り試さず、代表的なケースのみ
    if len(atoms) > 5:
        test_cases = [
            tuple([False] * len(atoms)),
            tuple([True] * len(atoms)),
        ]
    else:
        test_cases = list(itertools.product([False, True], repeat=len(atoms)))

    for values in test_cases:
        valuation = dict(zip(atoms, values))
        res = eval_propositional(formula, valuation)
        if res is not None:
            results.append({
                "type": "truth_assignment",
                "input": valuation,
                "result": res,
                "status": "satisfied" if res else "violated"
            })
            # 反例が見つかったら即座に終了
            if not res:
                break
                
    return results
