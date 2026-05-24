from typing import Any, Dict, List
import re
from avh_math.recognizers.base import BaseRecognizer
from avh_math.text_cross.formula_extractor import extract_formula_candidates

class FormulaRecognizer(BaseRecognizer):
    def can_handle(self, text: str) -> float:
        # 記号の密度や特定の演算子の存在で判定
        score = 0.0
        if any(op in text for op in ["->", "[]", "<>", "□", "◇", "∀", "∃"]):
            score += 0.6
        
        # 数式の割合（空白除外）
        clean_text = re.sub(r"\s+", "", text)
        if not clean_text:
            return 0.0
            
        symbol_count = len(re.findall(r"[A-Za-z0-9+\-*/=<>!&|~\[\]\(\)]", clean_text))
        ratio = symbol_count / len(clean_text)
        
        if ratio > 0.5:
            score += 0.4
            
        return min(score, 1.0)

    def recognize(self, text: str) -> Dict[str, Any]:
        candidates = extract_formula_candidates(text)
        return {
            "type": "formula",
            "candidates": candidates,
            "best_candidate": candidates[0] if candidates else None
        }
