import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from avh_math.answer_types.query_type import QueryType

def structural_match(f1: str, f2: str) -> bool:
    """
    2つの論理式の構造が一致するかを判定する。
    ここでは空白や括弧の揺れを排除した完全一致を基本とする。
    """
    def normalize(s):
        return s.replace(" ", "").replace("→", "->").replace("□", "[]").replace("◇", "<>")

    return normalize(f1) == normalize(f2)

def _query_type_allowed(entry: Dict[str, Any], query_type: QueryType) -> bool:
    """
    このKBエントリが現在の問いの意図（query_type）に適用可能か判定する。
    適用可能リスト（applicable_query_types）がない場合は、後方互換性のため許可する。
    """
    allowed_list = entry.get("applicable_query_types")
    if not allowed_list:
        return True
    
    # Enum の値（"set_all", "single_formula" 等）と比較
    return query_type.value in allowed_list

class KBMatcher:
    def __init__(self, kb_path: str):
        self.kb_path = Path(kb_path)
        self.entries: List[Dict[str, Any]] = []
        self._load_kb()

    def _load_all(self):
        # メモリ節約のため必要最低限のフィールドのみ保持
        if not self.kb_path.exists():
            return
        with self.kb_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get("kind") in ("axiom", "theorem", "counterexample_schema"):
                        self.entries.append(obj)
                except:
                    continue

        # 決定打：法律KBも読み込む (Multi-domain Support)
        law_path = self.kb_path.parent / "foundation_law_kb.jsonl"
        if law_path.exists():
            with law_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        # 法律ドメインでは statute, exception, precedent を扱う
                        if obj.get("kind") in ("axiom", "theorem", "counterexample_schema", "statute", "exception", "precedent"):
                            self.entries.append(obj)
                    except:
                        continue

    def _load_kb(self):
        self._load_all()

    def find_instant_verdict(self, formula: str, assumptions: List[str] = None, query_type: QueryType = QueryType.SINGLE) -> Dict[str, Any]:
        """
        式に一致する確実な知見を KB から探し出す。
        返り値は {'hit': Optional[Dict], 'audit': List[str]} の形式。
        """
        if assumptions is None:
            assumptions = []
        
        norm_assumptions = {a.replace("assume:", "").strip().lower() for a in assumptions}
        audit = []

        for entry in self.entries:
            statement = entry.get("statement")
            if not statement:
                continue
            
            is_match = False
            # Domain-specific matching
            if entry.get("domain") == "law":
                # 簡易的な包含チェック（本来は Text-Cross 類似度）
                # クエリが条文の重要な単語を含んでいるか
                # ここでは単純に「条文がクエリの一部」またはその逆をチェックするわけにはいかないので
                # entryのキーワード（tagsなど）がクエリに含まれているかを見る
                tags = entry.get("tags", [])
                if tags and all(t in formula for t in tags[:2]): # 最初の2つのタグがあればマッチとみなす（仮）
                     is_match = True
                # あるいは statement そのものの包含
                elif statement in formula or formula in statement:
                     is_match = True
            else:
                is_match = structural_match(formula, statement)

            if is_match:
                # 決定打：問いの意図（query_type）に合致するか判定
                if not _query_type_allowed(entry, query_type):
                    audit.append(f"Skipped '{entry.get('id')}' (query_type mismatch: {query_type.value} not in {entry.get('applicable_query_types')})")
                    continue

                kind = entry.get("kind")
                solve_level = entry.get("solve_level", "heuristic") # デフォルト
                
                # 1. 定理・公理・法律の判定
                if kind in ("axiom", "theorem", "statute", "precedent"):
                    # 法律の場合、prerequisites は「要件事実」に相当
                    # ここでは簡易的に assumptions とのマッチング
                    prereqs = {p.replace("assume:", "").strip().lower() for p in entry.get("prerequisites", [])}
                    if not prereqs or prereqs.issubset(norm_assumptions):
                        return {
                            "hit": {
                                "status": "proved", # 決定打：条件を満たせば PROVED (適法/肯定)
                                "method": "kb_match",
                                "solve_level": solve_level,
                                "entry_id": entry.get("id"),
                                "details": f"Matches known {kind}: {statement}",
                                "confidence": 1.0 if solve_level == "db_direct" else 0.9
                            },
                            "audit": audit
                        }
                    else:
                        audit.append(f"Skipped {kind} '{entry.get('id')}': missing prereqs {prereqs - norm_assumptions}")
                
                # 2. 反例スキーマ・例外の判定
                elif kind in ("counterexample_schema", "exception"):
                    # 反例が適用される条件：
                    # 特定の仮定（例：reflexive）がある場合は無効にならないかもしれない。
                    # ここでは簡易的に「ユーザーの仮定が、反例の invalid_if に含まれていなければ適用」とする
                    # つまり invalid_if には「この反例を無効化する仮定」を書く
                    
                    invalidators = {c.replace("assume:", "").strip().lower() for c in entry.get("invalid_if", [])}
                    
                    # ユーザーの仮定の中に、反例を無効化するものがあるか？
                    conflicts = invalidators.intersection(norm_assumptions)
                    if conflicts:
                        audit.append(f"Skipped CEX '{entry.get('id')}': invalidated by assumptions {conflicts}")
                        continue
                    
                    # 決定打：反例採用
                    return {
                        "hit": {
                            "status": "disproved",
                            "method": "kb_match",
                            "solve_level": solve_level,
                            "entry_id": entry.get("id"),
                            "counterexample": entry.get("refutation"),
                            "details": f"Matches known invalid pattern: {statement}",
                            "confidence": 1.0 if solve_level == "db_direct" else 0.9
                        },
                        "audit": audit
                    }
        
        return {"hit": None, "audit": audit}
