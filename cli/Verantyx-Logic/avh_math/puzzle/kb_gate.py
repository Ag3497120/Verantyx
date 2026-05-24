import hashlib
from typing import Dict, Any

def allow_kb_promotion(entry: Dict[str, Any]) -> bool:
    """エントリを KB に昇格させるべきか判定するゲート"""
    confidence = entry.get("confidence", 0.0)
    kind = entry.get("kind")

    # 1. 高い確信度を持つ証明済み/反証済みエントリは昇格
    if confidence >= 0.7:
        return True
    
    # 2. 反例は発見されたこと自体に価値があるため、少し低めの閾値で許可
    if kind == "counterexample_schema" and confidence >= 0.5:
        return True

    return False

def calculate_kb_signature(entry: Dict[str, Any]) -> str:
    """内容に基づいた一意の署名を生成する（重複排除用）"""
    # 領域、種類、および核となる式からハッシュを生成
    payload = f"{entry.get('domain')}|{entry.get('kind')}|{entry.get('statement')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
