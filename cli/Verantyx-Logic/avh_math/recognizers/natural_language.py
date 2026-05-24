from typing import Any, Dict
from avh_math.recognizers.base import BaseRecognizer

class NaturalLanguageRecognizer(BaseRecognizer):

    def can_handle(self, text: str) -> float:

        # 決定打：記号が少なく、文章が一定の長さを持つ場合は自然文として扱う

        if not any(c in text for c in ["->", "[]", "&", "|", "\\"]):

            return 0.8

        return 0.2



    def recognize(self, text: str) -> Dict[str, Any]:

        # 自然言語をそのまま「問いの核」として扱う

        # クリーニングしてノイズを除去

        clean = text.strip().rstrip("?")

        

        return {

            "type": "natural_language",

            "candidates": [{

                "surface": clean,

                "normalized": clean,

                "score": 1.0

            }],

            "best_candidate": {"surface": clean, "normalized": clean, "score": 1.0}

        }


