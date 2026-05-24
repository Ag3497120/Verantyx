import hashlib
import json
from typing import List, Dict, Any, Optional
from avh_math.cross.cross_core import ReasoningCross
from avh_math.puzzle.status_types import ReasoningStatus

def calculate_canonical_hash(cross: ReasoningCross) -> str:
    """ReasoningCross の構造的な『指紋』を生成する"""
    # 意味（具体的な式）を排除し、構造的な特徴のみを抽出
    structure = {
        "domain": cross.domain,
        "task": cross.task,
        "num_syntax": len(cross.syntax_nodes),
        "assumptions": sorted(cross.assumptions),
        "has_verification": cross.status in (ReasoningStatus.PROVED, ReasoningStatus.DISPROVED)
    }
    s = json.dumps(structure, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

def calculate_utility_score(cross: ReasoningCross) -> float:
    """Cross の有用度を計算する (0.0 - 1.0)"""
    score = 0.0
    
    # 1. 結論が出ているか (重要度: 高)
    if cross.status in (ReasoningStatus.PROVED, ReasoningStatus.DISPROVED):
        score += 0.6
    elif cross.status == ReasoningStatus.TENTATIVE_ANSWER:
        score += 0.3
        
    # 2. 確信度 (重要度: 中)
    score += cross.metadata.get("mapping_confidence", 0.0) * 0.2
    
    # 3. エビデンスの豊富さ
    score += min(len(cross.evidence) * 0.05, 0.2)
    
    return score

class ForgetEngine:
    def __init__(self, threshold: float = 0.2):
        self.threshold = threshold
        self.canonical_map: Dict[str, str] = {} # hash -> primary_cross_id

    def process(self, cross: ReasoningCross, db: Any) -> str:
        """
        Cross を評価し、保持(keep)、統合(merge)、または忘却(drop)を決定する。
        """
        score = calculate_utility_score(cross)
        
        # 1. 有用度が低すぎる場合は忘却
        if score < self.threshold:
            # 既にDBに保存されている場合は削除（ここでは簡易的に通知のみ）
            return "dropped"

        # 2. 正準化による重複・同型チェック
        h = calculate_canonical_hash(cross)
        
        # 3. 証明済みは無条件で保護
        if cross.status in (ReasoningStatus.PROVED, ReasoningStatus.DISPROVED):
            return "kept_protected"

        return "kept"
