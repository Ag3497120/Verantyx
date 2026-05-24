from typing import Any, Dict, List
import re
from avh_math.recognizers.base import BaseRecognizer
from avh_math.recognizers.formula import FormulaRecognizer
from avh_math.recognizers.natural_language import NaturalLanguageRecognizer
from avh_math.recognizers.semantic_parser import SemanticParser
from avh_math.recognizers.arithmetic import ArithmeticRecognizer

class RecognizerDispatcher:
    def __init__(self):
        self.semantic_parser = SemanticParser()
        self.recognizers: List[BaseRecognizer] = [
            ArithmeticRecognizer(),
            FormulaRecognizer(),
            NaturalLanguageRecognizer(),
        ]

    def dispatch(self, text: str) -> Dict[str, Any]:
        t = (text or "").strip()
        
        # 1. 意味解析（Semantic Parser）による構造把握を優先
        sem_result = self.semantic_parser.parse(text)
        
        # 2. 認識器の優先順位決定
        # recognizers: [Arithmetic, Formula, NaturalLanguage]
        arith_rec = self.recognizers[0]
        form_rec = self.recognizers[1]
        nl_rec = self.recognizers[2]

        # 決定打：数式記号が含まれているかチェック
        has_logic_symbols = any(op in t for op in ["->", "→", "[]", "□", "<>", "◇", "\\", "∀", "∃", "&", "|", "~", "¬"])
        
        if has_logic_symbols:
            # --- 論理式層 ---
            if sem_result and sem_result.get("slots", {}).get("FORMULA"):
                return {
                    "type": "semantic_parsed",
                    "action": sem_result.get("action"),
                    "query_type": sem_result.get("query_type"),
                    "slots": sem_result.get("slots", {}),
                    "candidates": [{"surface": sem_result["slots"].get("FORMULA", ""), "normalized": self._normalize_logic(sem_result["slots"].get("FORMULA", "")), "score": 10.0}],
                    "extracted_assumptions": self._extract_assumes(sem_result)
                }
            return form_rec.recognize(text)
        
        # 3. 算術チェック
        if arith_rec.can_handle(text) > 0.4:
            return arith_rec.recognize(text)
        
        # 4. 自然文層（フォールバック）
        nl_result = nl_rec.recognize(text)
        if sem_result:
            nl_result["type"] = "semantic_parsed"
            nl_result["action"] = sem_result.get("action")
            nl_result["query_type"] = sem_result.get("query_type")
            nl_result["extracted_assumptions"] = self._extract_assumes(sem_result)
        return nl_result

    def _normalize_logic(self, formula: str) -> str:
        f = formula.strip()
        f = f.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
        f = f.replace(r"\to", "->").replace(r"\rightarrow", "->").replace(r"\leftrightarrow", "<->")
        f = f.replace("→", "->").replace("∧", "&").replace("∨", "|").replace("¬", "~")
        f = f.replace("↔", "<->").replace("⇒", "->").replace("⇔", "<->")
        f = f.replace(r"\box", "[]").replace(r"\diamond", "<>")
        f = re.sub(r"\bbox\b", "[]", f, flags=re.IGNORECASE)
        f = re.sub(r"\bdiamond\b", "<>", f, flags=re.IGNORECASE)
        return re.sub(r"\s+", "", f)

    def _extract_assumes(self, sem_result: Dict) -> List[str]:
        assumptions_list = []
        # Extract from slots
        assumption = sem_result["slots"].get("ASSUMPTION", "")
        if assumption:
            low = assumption.lower()
            if "transitive" in low: assumptions_list.append("assume:transitive")
            elif "reflexive" in low: assumptions_list.append("assume:reflexive")
            elif "symmetric" in low: assumptions_list.append("assume:symmetric")
            else: assumptions_list.append(f"assume:{assumption}")
        return assumptions_list