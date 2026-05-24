from typing import Any, Dict
import re
from avh_math.recognizers.base import BaseRecognizer

class ArithmeticRecognizer(BaseRecognizer):
    def can_handle(self, text: str) -> float:
        # 簡易判定: 数字を含み、かつ算術演算子を含む
        # ただし、論理式（->, []）を含まないこと
        if any(op in text for op in ["->", "=>", "[]", "<>", "□", "◇", "forall", "exists"]):
            return 0.0
            
        # 許容文字: 数字, 空白, ., +, -, *, /, %, (, ), =, ^
        # 少なくとも1つの数字が必要
        if not re.search(r"\d", text):
            return 0.0
            
        # クリーニングしてチェック
        clean = re.sub(r"[\d\s\.\+\-\*\/\%\(\)\=\^]", "", text)
        if len(clean) == 0:
            return 0.9 # 純粋な数式
            
        # 少しゴミがあっても許容（"Calculate 1+1" など）
        # しかし厳密な抽出は Solver に任せるため、ここでは「数式っぽいか」だけ見る
        return 0.5 if re.search(r"[\d]+[\s]*[\+\-\*\/][\s]*[\d]+", text) else 0.0

    def recognize(self, text: str) -> Dict[str, Any]:
        # 数式部分の抽出（簡易）
        # "Calculate 1 + 1" -> "1 + 1"
        # 実際にはより高度な抽出が必要だが、まずは全体を投げる
        
        # 不要な単語の削除
        junk = r"\b(Calculate|Compute|Evaluate|What is|Solve|Is|problem)\b"
        clean_text = re.sub(junk, "", text, flags=re.IGNORECASE).strip()
        
        # 末尾の?削除
        clean_text = clean_text.rstrip("?")
        
        return {
            "type": "arithmetic",
            "candidates": [{
                "surface": clean_text,
                "normalized": clean_text,
                "score": 1.0
            }]
        }