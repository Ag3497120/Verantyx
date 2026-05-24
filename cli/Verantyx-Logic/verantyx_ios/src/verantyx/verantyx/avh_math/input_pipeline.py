import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

def detect_domain(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["law", "legal", "statute", "civil", "justice", "juris", "法律", "条文", "court"]):
        return "law"
    if re.search(r"\d", t) and any(op in t for op in ["+", "-", "*", "/", "="]):
        if not any(log in t for log in ["[]", "<>", "->", "forall"]):
            return "arithmetic"
    if any(k in t for k in ["kripke", "modal", "possible world", "frame", "validity", "□", "◇", "[]", "<>"]):
        return "modal_logic"
    return "unknown"

def normalize_formula_v2(s: str) -> str:
    if not s: return ""
    s = s.strip()
    
    # 文章か式かを判定
    # 英単語が多く含まれる、またはスペースが多い場合は「文章」とみなして保護する
    word_count = len(re.findall(r'\b\w{2,}\b', s))
    has_logic_ops = any(op in s for op in ["[]", "<>", "->", "&", "|", "~", "□", "◇"])
    
    # 決定打：単語が3つ以上ある、または論理記号がない場合はスペースを保持
    if word_count >= 3 or not has_logic_ops:
        # クォート除去などの最小限の処理のみ
        if len(s) > 2 and s[0] == '"' and s[-1] == '"':
            s = s[1:-1].strip()
        return s

    # 論理式とみなされる場合のみ、LaTeX変換とスペース削除を行う
    s = s.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\to", "->")
    s = s.replace("□", "[]").replace("→", "->")
    if s.startswith("->"): s = s[2:].strip()
    s = re.sub(r"\s+", "", s)
    return s

from avh_math.answer_types.query_type import QueryType
from avh_math.answer_types.problem_type import ProblemType

@dataclass
class Decomposed:
    domain: str
    core_formula: Optional[str]
    candidates: List[str]
    assumptions: List[str]
    atoms: List[str]
    evidence: Dict[str, Any] = field(default_factory=dict)
    audit: List[str] = field(default_factory=list)
    query_type: QueryType = QueryType.SINGLE
    problem_type: ProblemType = ProblemType.VALIDITY_CHECK

def infer_problem_type(query: str, core_formula: Optional[str]) -> ProblemType:
    q = (query or "").lower()
    if any(k in q for k in ["what is", "define", "definition", "meaning", "concept", "explain", "とは", "意味"]) or q.endswith("?"):
        return ProblemType.META_QUERY
    return ProblemType.VALIDITY_CHECK

def decompose_text(text: str, text_cross_hint_min_score: float = 0.25) -> Decomposed:
    domain = detect_domain(text)
    
    from avh_math.recognizers.dispatcher import RecognizerDispatcher
    from avh_math.puzzle.formula_gate import select_core_formula
    
    dispatcher = RecognizerDispatcher()
    rec_result = dispatcher.dispatch(text)
    all_candidates = rec_result.get("candidates", [])
    
    core_formula = None
    core_candidate, formula_type = select_core_formula(all_candidates, text)
    if core_candidate:
        core_formula = core_candidate["normalized"]
        
    problem_type = infer_problem_type(text, core_formula)
    
    if problem_type == ProblemType.META_QUERY or domain == "law":
        if not core_formula:
            core_formula = text.strip()
    
    candidates = [c.get("normalized") if isinstance(c, dict) else c for c in all_candidates]
    if core_formula and core_formula not in candidates:
        candidates.insert(0, core_formula)
        
    return Decomposed(
        domain=domain,
        core_formula=core_formula,
        candidates=candidates,
        assumptions=[],
        atoms=["p"],
        query_type=QueryType.SET_ALL if "always" in text.lower() else QueryType.SINGLE,
        problem_type=problem_type
    )
