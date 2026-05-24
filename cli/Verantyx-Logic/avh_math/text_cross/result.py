from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from avh_math.avh_math.answer_types.query_type import QueryType

@dataclass
class TextCrossResult:
    """
    Text-Cross (自然文解析層) の最終出力。
    Simulation Cross (実行層) への入力仕様書となる。
    """
    domain: str = "unknown"
    query_type: QueryType = QueryType.SINGLE
    
    # 決定的な1つの式（あれば）
    core_formula: Optional[str] = None
    
    # 候補式リスト（集合検証用）
    candidate_formulas: List[str] = field(default_factory=list)
    
    # 抽出された仮定（正規化済み） e.g. ["transitive", "reflexive"]
    assumptions: List[str] = field(default_factory=list)
    
    # 制約条件（シミュレーションパラメータなど）
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    # 解析自体の確信度
    confidence: float = 0.0
    
    # デバッグ用トレース
    audit: List[str] = field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: Any) -> 'TextCrossResult':
        """既存の Spec オブジェクトから変換（移行用）"""
        return cls(
            domain=spec.domain,
            query_type=getattr(spec, "query_type", QueryType.SINGLE),
            core_formula=spec.core_formula,
            candidate_formulas=spec.candidates,
            assumptions=spec.assumptions,
            confidence=0.8, # Specにはないので仮置き
            audit=spec.audit
        )
