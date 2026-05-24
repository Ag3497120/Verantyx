import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

class SemanticParser:
    def __init__(self, memory_path: str = "avh_math/db/word_memory.json"):
        self.word_map = {}
        self.concept_map = {}
        self._load_memory(memory_path)

    def _load_memory(self, path_str: str):
        path = Path(path_str)
        if not path.exists(): return
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            for role, content in data.items():
                if role == "CONCEPT_MAP":
                    self.concept_map = content
                elif isinstance(content, list):
                    for w in content:
                        self.word_map[w.lower()] = role

    def extract_concepts(self, text: str) -> List[str]:
        """
        Scan text for known phrases in CONCEPT_MAP.
        Returns a list of detected concepts (e.g. 'assume:transitive', 'domain:modal_logic').
        """
        detected = []
        low_text = text.lower()
        
        for concept, phrases in self.concept_map.items():
            for phrase in phrases:
                # Simple substring match for phrases
                if phrase.lower() in low_text:
                    detected.append(concept)
                    break
        return detected

    def parse_and_structure(self, text: str) -> Dict[str, Any]:
        """
        ユーザーが入力したクォート（"..."）を式として認識し、
        それ以外の部分を単語記憶DBに基づいて役割付けする。
        """
        # 1. ユーザー入力のクォートを抽出（入力は既に半角ダブルクォートに正規化済み）
        formulas = re.findall(r'"([^"]+)"', text)
        
        # 2. クォートを除いた部分をトークン化して役割を判定
        text_no_formulas = re.sub(r'"[^"]+"', " FORMULA_PLACEHOLDER ", text)
        raw_tokens = re.findall(r"[A-Za-z0-9_]+|[^\w\s]", text_no_formulas)
        
        roles = []
        for t in raw_tokens:
            low = t.lower()
            role = self.word_map.get(low, "unknown")
            roles.append({"token": t, "role": role})
            
        return {
            "structured_roles": roles,
            "formulas": formulas,
            "primary_formula": formulas[0] if formulas else None,
            "text_no_formulas": text_no_formulas
        }

    def parse(self, text: str) -> Optional[Dict[str, Any]]:
        res = self.parse_and_structure(text)
        if not res["primary_formula"] and not res["formulas"]: return None
        
        primary_formula = res["primary_formula"] or (res["formulas"][0] if res["formulas"] else "")

        # 決定打：フレーズベースの概念抽出を実行
        concepts = self.extract_concepts(text)
        
        s_text = text.lower()
        query_type = "SET_ALL" if any(w in s_text for w in ["always", "all", "every", "tautology", "valid"]) else "SINGLE"
        
        # ドメインの推論 (Concept Map優先)
        domain = None
        for c in concepts:
            if c.startswith("domain:"):
                domain = c.replace("domain:", "")
                break
        
        if not domain:
            if any(w in s_text for w in ["modal", "kripke", "frame", "accessibility"]):
                domain = "modal_logic"
            elif "propositional" in s_text:
                domain = "propositional_logic"
            elif "linear" in s_text or "matrix" in s_text:
                domain = "linear_algebra"
        
        # 仮定の抽出
        assumptions = []
        # Concept Mapからの抽出
        for c in concepts:
            if c.startswith("assume:"):
                assumptions.append(c)
        
        # 既存の単語ベース抽出 (補完)
        if "transitive" in s_text and "assume:transitive" not in assumptions: assumptions.append("assume:transitive")
        if "reflexive" in s_text and "assume:reflexive" not in assumptions: assumptions.append("assume:reflexive")
        if "symmetric" in s_text and "assume:symmetric" not in assumptions: assumptions.append("assume:symmetric")
        if "serial" in s_text and "assume:serial" not in assumptions: assumptions.append("assume:serial")
        
        return {
            "type": "semantic_parsed",
            "intent": "VERIFY",
            "query_type": query_type,
            "domain": domain,
            "slots": { "FORMULA": primary_formula },
            "extracted_assumptions": assumptions,
            "candidates": [{
                "surface": primary_formula,
                "normalized": primary_formula,
                "score": 10.0
            }]
        }
