import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

class SemanticParser:
    def __init__(self, memory_path: str = "avh_math/db/word_memory.json"):
        self.word_map = {}
        self._load_memory(memory_path)

    def _load_memory(self, path_str: str):
        path = Path(path_str)
        if not path.exists(): return
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            for role, words in data.items():
                for w in words:
                    self.word_map[w.lower()] = role

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
        if not res["primary_formula"]: return None
        
        # 決定打：文脈からパズル操作（Action）とドメインを決定
        s_text = text.lower()
        query_type = "SET_ALL" if any(w in s_text for w in ["always", "all", "every", "tautology"]) else "SINGLE"
        
        # ドメインの推論
        domain = None
        if "modal" in s_text or "kripke" in s_text:
            domain = "modal_logic"
        elif "propositional" in s_text:
            domain = "propositional_logic"
        elif "linear" in s_text or "matrix" in s_text:
            domain = "linear_algebra"
        
        # 仮定の抽出
        assumptions = []
        for r in res["structured_roles"]:
            if r["role"] == "ASSUMPTION_MARKER":
                # 次の語が既知の仮定なら追加
                pass # 現状は簡易キーワードマッチで十分
        
        if "transitive" in s_text: assumptions.append("assume:transitive")
        if "reflexive" in s_text: assumptions.append("assume:reflexive")
        if "symmetric" in s_text: assumptions.append("assume:symmetric")
        
        return {
            "type": "semantic_parsed",
            "intent": "VERIFY",
            "query_type": query_type,
            "domain": domain,
            "slots": { "FORMULA": res["primary_formula"] },
            "extracted_assumptions": assumptions,
            "candidates": [{
                "surface": res["primary_formula"],
                "normalized": res["primary_formula"],
                "score": 10.0
            }]
        }
