from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from avh_math.answer_types.query_type import QueryType

# query_type ごとの confidence 閾値（Verantyx の根拠厚み定義）
QUERY_TYPE_THRESHOLDS = {
    QueryType.SINGLE: {
        "proved": 0.75,
        "tentative": 0.40,
    },
    QueryType.SET_ALL: {
        "proved": 0.85,
        "tentative": 0.55,
    },
    QueryType.SET_ANY: {
        "proved": 0.65,
        "tentative": 0.35,
    },
    QueryType.EQUIVALENCE: {
        "proved": 0.90,
        "tentative": 0.60,
    },
}

@dataclass
class StrategyDelta:
    """推論戦略の変更差分"""
    simulation_priority: Optional[float] = None
    puzzle_priority: Optional[float] = None
    silent_threshold: Optional[float] = None
    trust_recent_kb: Optional[bool] = None

@dataclass
class InferenceProfile:
    """エンジンの実行人格（パラメータセット）"""
    simulation_weight: float = 0.5
    puzzle_weight: float = 0.5
    silent_threshold: float = 0.4
    trust_recent_kb: bool = False

    def get_thresholds(self, query_type: QueryType) -> Dict[str, float]:
        """指定された QueryType に基づく閾値を取得する"""
        base = QUERY_TYPE_THRESHOLDS.get(query_type, QUERY_TYPE_THRESHOLDS[QueryType.SINGLE])
        
        # プロファイルによる動的補正（例: simulation_weight が高いときは proved 基準を厳しくするなど）
        # 現状はシンプルにベース値を返す
        return base

    def apply_delta(self, delta: StrategyDelta):
        """メタ知識から得られた差分を適用する"""
        if delta.simulation_priority is not None:
            self.simulation_weight = delta.simulation_priority
        if delta.puzzle_priority is not None:
            self.puzzle_weight = delta.puzzle_priority
        if delta.silent_threshold is not None:
            self.silent_threshold = delta.silent_threshold
        if delta.trust_recent_kb is not None:
            self.trust_recent_kb = delta.trust_recent_kb

def derive_delta_from_meta(meta_strategy: Dict[str, Any]) -> StrategyDelta:
    """Meta-Cross の照会結果から実行プロファイルの差分を導出する"""
    delta = StrategyDelta()
    strategy = meta_strategy.get("strategy")
    confidence = meta_strategy.get("confidence", 0.0)

    if strategy == "simulate-first":
        delta.simulation_priority = 0.9
        delta.puzzle_priority = 0.1
    elif strategy == "puzzle-first":
        delta.simulation_priority = 0.2
        delta.puzzle_priority = 0.8

    # 確信度が高い場合は、沈黙の閾値を下げてより積極的に回答する
    if confidence >= 0.8:
        delta.silent_threshold = 0.2
        delta.trust_recent_kb = True
    else:
        delta.silent_threshold = 0.5

    return delta
