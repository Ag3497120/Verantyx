import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from avh_math.text_cross.builder import build_text_cross
from avh_math.text_cross.cross_kb_query import (
    extract_hint_from_cross,
    query_similar_cross_kb_scored,
)
from avh_math.text_cross.formula_extractor import (
    extract_formula_candidates,
    reconstruct_formula_from_shapes,
)
from avh_math.text_cross.mapping_table import record_mapping, suggest_mapping
from avh_math.puzzle.formula_gate import select_core_formula

try:
    from avh_math.input_structured import parse_structured_header as parse_structured_header_shared
except Exception:
    parse_structured_header_shared = None

try:
    from avh_math.verantyx.input_rules import (
        extract_quoted_formulas as extract_quoted_formulas_shared,
        detect_domain_hint as detect_domain_hint_shared,
        normalize_formula as normalize_formula_shared,
    )
except Exception:
    extract_quoted_formulas_shared = None
    detect_domain_hint_shared = None
    normalize_formula_shared = None

_FORMULA_TOKEN_RE = re.compile(r'(?:[]|<>)|'|~|&||'|->|<->')
_UI_NOISE_RE = re.compile(
    r"^\s*(【入力ルール】|TPL:\s*|Modal tips:|SOLVE\b|UNSUPPORTED\b|INTERNAL EVALUATION:|REASONING PROOF|COUNTEREXAMPLE|TRACE / STATS|NEXT ACTIONS|KEY:\s*q_|Verantyx Cross|BUILD CROSS|SOLVE \(CROSS\)|cross_id:)\b",
    re.IGNORECASE,
)


def strip_ui_noise(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if _UI_NOISE_RE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_structured_header(text: str) -> Dict[str, Any]:
    if parse_structured_header_shared:
        hdr = parse_structured_header_shared(text)
        return {
            "domain": hdr.domain,
            "assumptions": hdr.assumptions,
            "formula": hdr.formula,
            "body": hdr.body,
        }
    return {"domain": None, "assumptions": [], "formula": None, "body": text}


def extract_quoted_formulas(text: str) -> List[str]:
    if extract_quoted_formulas_shared:
        return extract_quoted_formulas_shared(text)
    return []


def detect_domain(text: str) -> str:
    """
    入力テキストからドメインを推定する（最優先ルール）。
    """
    t = (text or "").lower()
    
    # 1. 法律ドメイン（英語・日本語）
    law_keywords = [
        "law", "legal", "statute", "civil", "jurisprudence", "court",
        "民法", "刑法", "法律", "条文", "規定", "裁判", "判例", "契約", "売主", "買主"
    ]
    if any(k in t for k in law_keywords):
        return "law"

    # 2. 算術ドメイン
    if re.search(r"\d", t) and any(op in t for op in ["+", "-", "*", "/", "="]):
        if not any(log in t for log in ["[]", "<>", "->", "forall", "exists", "box", "diamond"]):
            return "arithmetic"

    # 3. 共有ヒントの利用
    if detect_domain_hint_shared:
        d = detect_domain_hint_shared(text)
        if d and d != "unknown":
            return d

    # 4. 論理ドメイン
    if ("∀" in t) or ("∃" in t) or ("quantifier" in t) or ("first-order" in t) or ("述語" in t):
        return "first_order_logic"
    if ("kripke" in t) or ("□" in t) or ("◇" in t) or ("[]" in t) or ("様相" in t):
        return "modal_logic"
    if ("tautology" in t) or ("恒真" in t) or ("真理値" in t):
        return "propositional_logic"
    
    return "unknown"


def normalize_formula(s: str) -> str:
    if normalize_formula_shared:
        return normalize_formula_shared(s)
    return (s or "").strip()

# (既存の古い関数は整理して削除)

def normalize_formula_v2(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\u200b", "").replace("\ufeff", "")
    
    # Fix: Strip quotes first
    if len(s) > 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == '“' and s[-1] == '”')):
        s = s[1:-1].strip()

    # LaTeX normalization
    s = s.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
    s = s.replace(r"\to", "->").replace(r"\rightarrow", "->").replace(r"\leftrightarrow", "<->")
    s = s.replace(r"\box", "[]").replace(r"\diamond", "<>")
    
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)
    s = s.replace("□", "[]").replace("◇", "<>")
    s = s.replace("→", "->").replace("−", "-").replace("÷", "/")
    
    # Fix: Remove leading arrow artifacts
    if s.startswith("->"): s = s[2:].strip()
    if s.startswith("→"): s = s[1:].strip()
    
    # Final whitespace removal (only if not quoted)
    s = re.sub(r"\s+", "", s)
    
    if s in ("[]", "<>", "->", ""):
        return ""
    return s

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
    context_text: Optional[str] = None

def infer_problem_type(query: str, core_formula: Optional[str], assumptions: List[str]) -> ProblemType:
    q = (query or "").lower()
    meta_keywords = ["what is", "define", "definition", "meaning of", "explain", "concept", "とは", "意味"]
    if any(k in q for k in meta_keywords) or q.endswith("?"):
        return ProblemType.META_QUERY
    return ProblemType.VALIDITY_CHECK

from avh_math.recognizers.dispatcher import RecognizerDispatcher
from avh_math.avh_math.answer_types.query_type import QueryType
from avh_math.avh_math.answer_types.problem_type import ProblemType
from avh_math.puzzle.formula_gate import is_well_formed_formula, select_core_formula
from avh_math.shape_signature import shape_signature

def decompose_text(text: str, text_cross_hint_min_score: float = 0.25) -> Decomposed:
    # 1. 前処理
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = text.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
    text = text.replace(r"\to", "->").replace(r"\rightarrow", "->")
    
    audit = []
    
    # 2. ドメイン判定 (最優先)
    domain = detect_domain(text)
    print(f"[DEBUG PIPELINE] Detect domain: {domain}")
    
    # 3. 認識層の切り替え
    dispatcher = RecognizerDispatcher()
    rec_result = dispatcher.dispatch(text)
    all_candidates = rec_result.get("candidates", [])
    
    # 4. 仮定の抽出
    assumptions = _detect_assumptions_ja_en(text)
    sem_assumes = rec_result.get("extracted_assumptions", [])
    for a in sem_assumes:
        if a not in assumptions: assumptions.append(a)
    
    # 5. 核となる式の選定
    core_formula = None
    candidates = [c.get("normalized") if isinstance(c, dict) else c for c in all_candidates]
    candidates = [c for c in candidates if c]
    
    # [A] 既存ロジックでの抽出
    core_candidate, formula_type = select_core_formula(all_candidates, text)
    if core_candidate:
        core_formula = core_candidate["normalized"]
    
    # 6. 問題タイプの判定
    problem_type = infer_problem_type(text, core_formula, assumptions)
    
    # 7. 救済ロジック (自然文・法律)
    if domain == "law" or problem_type == ProblemType.META_QUERY:
        if not core_formula:
            core_formula = text.strip()
            audit.append(f"[救済] core_formula set to full text (type={problem_type.value})")
        if text not in candidates:
            candidates.append(text)

    # 8. その他のメタ情報
    query_type = QueryType.SET_ALL if "always" in text.lower() or "all" in text.lower() else QueryType.SINGLE
    
    return Decomposed(
        domain=domain,
        core_formula=core_formula,
        candidates=candidates,
        assumptions=assumptions,
        atoms=["p"], # 簡易化
        query_type=query_type,
        problem_type=problem_type
    )

def _detect_assumptions_ja_en(text: str) -> List[str]:
    t = (text or "").lower()
    out = []
    if "transitive" in t: out.append("assume:transitive")
    if "reflexive" in t: out.append("assume:reflexive")
    return out
