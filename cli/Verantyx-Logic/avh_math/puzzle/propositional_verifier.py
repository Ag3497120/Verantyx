import itertools
from typing import List, Dict, Tuple, Any, Optional
from avh_math.puzzle.prop_simulator import eval_propositional

def verify_propositional_exhaustive(formula: str, atoms: List[str]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    全ての真理値の組み合わせをチェックし、PROVED または DISPROVED を返す。
    """
    if not atoms:
        return "TENTATIVE_ANSWER", None

    for values in itertools.product([True, False], repeat=len(atoms)):
        valuation = dict(zip(atoms, values))
        res = eval_propositional(formula, valuation)
        
        if res is False:
            # 反例発見
            return "DISPROVED", {
                "valuation": valuation,
                "method": "exhaustive_truth_table"
            }
        
    # 全ケースで真
    return "PROVED", {"method": "exhaustive_truth_table"}
