from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class AssumptionSetResult:
    add_assumptions: List[str]
    total_assumptions: List[str]
    valid: bool
    counterexample: Optional[Dict[str, Any]]
    note: str


def minimize_assumptions_bfs(
    model_search_fn: Callable[[str, List[str]], Dict[str, Any]],
    formula: str,
    base_assumptions: List[str],
    universe: List[str],
    max_k: int = 3,
    max_results: int = 5,
) -> List[AssumptionSetResult]:
    """
    最小の追加仮定集合（サイズ最小）を探す。
    - model_search_fn(formula, assumptions) -> dict
        期待: {"valid": bool, "counterexample": {...} or None, "note": str}
    - BFS: k=0..max_k の順に探索し、validになった集合を集め、最小kの解だけ返す。
    """
    base = list(dict.fromkeys(base_assumptions))  # unique preserve order
    uni = [u for u in universe if u not in base]  # baseと重複除去

    winners: List[AssumptionSetResult] = []
    found_k: Optional[int] = None

    for k in range(0, max_k + 1):
        for adds in combinations(uni, k):
            total = base + list(adds)

            res = model_search_fn(formula, total)

            valid = bool(res.get("valid"))
            note = str(res.get("note", ""))
            cex = res.get("counterexample")

            if valid:
                if found_k is None:
                    found_k = k
                # 最小kを超えたら打ち切り
                if k != found_k:
                    continue

                winners.append(AssumptionSetResult(
                    add_assumptions=list(adds),
                    total_assumptions=total,
                    valid=True,
                    counterexample=None,
                    note=note,
                ))
                if len(winners) >= max_results:
                    return winners

        if found_k is not None:
            # kのループを終えた時点で最小kが確定しているので終了
            break

    # valid集合が見つからない場合：最小のinvalidも返す（デバッグ用）
    if not winners:
        # k=0の結果だけ1つ返す
        res0 = model_search_fn(formula, base)
        winners.append(AssumptionSetResult(
            add_assumptions=[],
            total_assumptions=base,
            valid=bool(res0.get("valid")),
            counterexample=res0.get("counterexample"),
            note=str(res0.get("note", "")),
        ))
    return winners