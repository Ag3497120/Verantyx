from enum import Enum

class QueryType(str, Enum):
    """
    問題の意図（solver が取るべき戦略）を明示する Enum。
    Decomposer が推定し、Solver が必ず参照する。
    """

    # 単一の論理式について真偽を問う
    SINGLE = "single_formula"

    # 複数の式が「すべて」成立するか
    SET_ALL = "set_all"

    # 複数の式のうち「いずれか」が成立するか
    SET_ANY = "set_any"

    # 2 つの式が同値かどうか
    EQUIVALENCE = "equivalence"

    # 分類目的（公理・定理・反例など）
    CLASSIFY = "classify"
