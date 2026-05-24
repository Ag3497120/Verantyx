import re
from avh_math.recognizers.base import BaseSolver, SolverResult

from avh_math.puzzle.solver_registry import SolverRegistry, SolverMeta

@SolverRegistry.register(SolverMeta(
    id="units:dim",
    domain="unit_analysis",
    description="Dimensional Analysis and Unit Consistency",
    triggers=[r"\d+\s*[a-zA-Z]+", r"unit", r"dimension"],
    cost_level=1,
    timeout_ms=100,
    required_inputs=["formula"]
))
class UnitSolver(BaseSolver):
    def __init__(self):
        # ... (既存のinit) ...

    def solve(self, query: str, context: Dict[str, Any] = None) -> SolverResult:
        # 例: "Is 10m/s + 5m valid?" -> Disproved (Dimension mismatch)
        # 簡易パーサー: 数値は無視し、単位だけを取り出して演算する
        
        # 単位の抽出と演算構造の解析は複雑だが、ここでは簡易的に
        # "unit(A) == unit(B)" をチェックする
        
        # TODO: 本格的な次元解析ロジック
        return SolverResult("unknown", "unit_analysis", 0.0, details="Not implemented yet")
