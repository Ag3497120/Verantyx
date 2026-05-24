from enum import Enum, auto

class SolveLevel(str, Enum):
    DB_DIRECT = "db_direct"        # DBにそのまま載っている
    AXIOM_DERIVED = "axiom_derived" # 公理＋DBで導出
    HEURISTIC = "heuristic"        # 類推・構文判断のみ
    UNSUPPORTED = "unsupported"    # 現在は解けない
