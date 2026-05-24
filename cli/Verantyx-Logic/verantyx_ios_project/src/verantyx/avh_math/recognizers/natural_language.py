from typing import Any, Dict
from avh_math.recognizers.base import BaseRecognizer

class NaturalLanguageRecognizer(BaseRecognizer):
    def can_handle(self, text: str) -> float:
        score = 0.0
        # 法律キーワード
        if any(w in text for w in ["民法", "刑法", "条文", "契約", "売主", "買主", "責任", "権利", "義務"]):
            score += 0.8
        
        # 日本語の割合（簡易）
        ja_count = len([c for c in text if "\u3000" <= c <= "\u9fff"])
        if len(text) > 0 and (ja_count / len(text)) > 0.3:
            score += 0.3
            
        return min(score, 1.0)

    def recognize(self, text: str) -> Dict[str, Any]:
        # 自然言語をそのまま「式（命題）」として扱う
        return {
            "type": "natural_language",
            "candidates": [{"surface": text, "normalized": text, "score": 1.0}],
            "best_candidate": {"surface": text, "normalized": text, "score": 1.0}
        }
