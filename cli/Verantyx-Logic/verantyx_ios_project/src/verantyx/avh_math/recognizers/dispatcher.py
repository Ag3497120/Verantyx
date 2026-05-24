from typing import Any, Dict, List
import re
from avh_math.recognizers.base import BaseRecognizer
from avh_math.recognizers.formula import FormulaRecognizer
from avh_math.recognizers.natural_language import NaturalLanguageRecognizer
from avh_math.recognizers.semantic_parser import SemanticParser

class RecognizerDispatcher:
    def __init__(self):
        self.semantic_parser = SemanticParser()
        self.recognizers: List[BaseRecognizer] = [
            FormulaRecognizer(),
            NaturalLanguageRecognizer(),
        ]

    def dispatch(self, text: str) -> Dict[str, Any]:
        # 1. 意味解析（Semantic Parser）を最優先
        sem_result = self.semantic_parser.parse(text)
        if sem_result:
            formula = sem_result["slots"].get("FORMULA", "")
            assumption = sem_result["slots"].get("ASSUMPTION", "")
            
            assumptions_list = []
            if assumption:
                # "transitive" -> "assume:transitive"
                if "transitive" in assumption.lower(): assumptions_list.append("assume:transitive")
                elif "reflexive" in assumption.lower(): assumptions_list.append("assume:reflexive")
                elif "symmetric" in assumption.lower(): assumptions_list.append("assume:symmetric")
                else: assumptions_list.append(f"assume:{assumption}")

            # 決定打：抽出された式を正規化する（LaTeX -> 標準記号）
            norm_formula = formula
            norm_formula = norm_formula.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
            norm_formula = norm_formula.replace(r"\to", "->").replace(r"\rightarrow", "->").replace(r"\leftrightarrow", "<->")
            norm_formula = norm_formula.replace("→", "->").replace("∧", "&").replace("∨", "|").replace("¬", "~")
            norm_formula = norm_formula.replace("↔", "<->").replace("⇒", "->").replace("⇔", "<->")
            
            norm_formula = norm_formula.replace(r"\box", "[]").replace(r"\diamond", "<>")
            norm_formula = re.sub(r"\bbox\b", "[]", norm_formula, flags=re.IGNORECASE)
            norm_formula = re.sub(r"\bdiamond\b", "<>", norm_formula, flags=re.IGNORECASE)
            norm_formula = re.sub(r"\s+", "", norm_formula)

            return {
                "type": "semantic_parsed",
                "candidates": [{
                    "surface": formula,
                    "normalized": norm_formula, # 正規化済み
                    "score": 10.0
                }],
                "extracted_assumptions": assumptions_list,
                "query_type": sem_result.get("query_type"),
                "action": sem_result.get("action")
            }

        # 2. 既存のRecognizer
        best_recognizer = None
        best_score = -1.0

        for recognizer in self.recognizers:
            score = recognizer.can_handle(text)
            if score > best_score:
                best_score = score
                best_recognizer = recognizer
        
        if best_recognizer and best_score > 0.3:
            return best_recognizer.recognize(text)
        
        # デフォルトは FormulaRecognizer
        return self.recognizers[0].recognize(text)
