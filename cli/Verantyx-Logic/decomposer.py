# decomposer.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

try:
    from avh_math.input_normalize import normalize_input as normalize_input_shared
    from avh_math.input_structured import parse_structured_header as parse_structured_header_shared
    from avh_math.domain_guess import guess_domain as guess_domain_shared
    from avh_math.verantyx.input_rules import (
        extract_quoted_formulas as extract_quoted_formulas_shared,
        detect_domain_hint as detect_domain_hint_shared,
        normalize_formula as normalize_formula_shared,
    )
    from avh_math.input_pipeline import (
        strip_ui_noise as strip_ui_noise_shared,
        detect_domain as detect_domain_pipeline,
        extract_quoted_formulas as extract_quoted_formulas_pipeline,
    )
except Exception:
    normalize_input_shared = None
    parse_structured_header_shared = None
    guess_domain_shared = None
    extract_quoted_formulas_shared = None
    detect_domain_hint_shared = None
    normalize_formula_shared = None
    strip_ui_noise_shared = None
    detect_domain_pipeline = None
    extract_quoted_formulas_pipeline = None

# If you already have these in your repo, keep using them.
# Otherwise, comment out evidence_map parts safely.
try:
    from evidence import Span, find_spans
except Exception:
    @dataclass
    class Span:
        start: int
        end: int
        text: str

    def find_spans(text: str, phrases: List[str]) -> List[Span]:
        spans: List[Span] = []
        low = text.lower()
        for p in phrases:
            if not p:
                continue
            idx = low.find(p.lower())
            if idx >= 0:
                spans.append(Span(start=idx, end=idx + len(p), text=text[idx:idx + len(p)]))
        return spans


from avh_math.avh_math.answer_types.query_type import QueryType

@dataclass
class Spec:
    assumptions: List[str] = field(default_factory=list)      # e.g. ["assume:transitive"]
    candidates: List[str] = field(default_factory=list)       # normalized formulas or extracted expressions
    audit: List[str] = field(default_factory=list)            # evidence trace
    atoms: List[str] = field(default_factory=list)            # used by logic solvers; default set later
    evidence_map: Dict[str, List[Span]] = field(default_factory=dict)
    domain: str = "unknown"
    core_formula: str = ""
    query_type: QueryType = QueryType.SINGLE


# ----------------------------
# Normalization utilities
# ----------------------------

_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_WS = re.compile(r"\s+")
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

def _norm_text(s: str) -> str:
    s = (s or "").strip()
    s = _ZERO_WIDTH.sub("", s)
    # normalize common symbols (keep both ASCII + math)
    s = s.replace("→", "->").replace("⇒", "->")
    s = s.replace("¬", "~").replace("〜", "~").replace("～", "~")
    s = s.replace("∧", "&").replace("∨", "|")
    s = s.replace("⊤", "T").replace("⊥", "F")
    s = s.replace("□", "box ").replace("◇", "diamond ")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("【", "[").replace("】", "]")
    s = s.replace("−", "-").replace("×", "*").replace("・", "*")
    s = _WS.sub(" ", s).strip()
    return s

def _norm_formula(s: str, map_atoms: bool = True) -> str:
    """
    IMPORTANT: Only apply to *formula strings*, never to whole natural language text.
    """
    s = (s or "").strip()
    
    # NEW: Handle quoted formulas
    if (s.startswith('"') and s.endswith('"')) or (s.startswith('「') and s.endswith('」')):
        s = s[1:-1].strip()

    s = _ZERO_WIDTH.sub("", s)
    s = s.replace("\r", "\n")
    # Merge multiline broken formulas (common in copied text)
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    if len(lines) >= 2:
        # if looks like "2" newline "n(n+1)" treat as fraction-ish (rare, but keep)
        if len(lines) == 2 and (lines[0].isdigit() ^ lines[1].isdigit()):
            if lines[0].isdigit():
                s = f"({lines[1]})/{lines[0]}"
            else:
                s = f"({lines[0]})/{lines[1]}"
        else:
            s = " ".join(lines)

    s = _WS.sub(" ", s).strip()

    # Normalize modal keywords first (using [] and <> as canonical)
    s = s.replace("□", "[]").replace("◇", "<>")
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)

    # Normalize arrows and connectives
    s = s.replace("→", "->").replace("⇒", "->")
    s = s.replace("∧", "&").replace("∨", "|")
    s = s.replace("¬", "~")

    # Remove option label prefix only at start
    s = re.sub(r"^\s*[A-D]\s*[\.:]\s*", "", s)

    # Collapse spaces around operators
    s = re.sub(r"\s*->\s*", "->", s)
    s = re.sub(r"\s*&\s*", "&", s)
    s = re.sub(r"\s*\|\s*", "|", s)
    s = re.sub(r"\s*~\s*", "~", s)
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)\s*", ")", s)

    # Modal operator glue: "[] p" -> "[]p", "<> p" -> "<>p"
    s = re.sub(r"\[\]\s+(?=[A-Za-z(~\[])", "[]", s)
    s = re.sub(r"<>\s+(?=[A-Za-z(~\[])", "<>", s)

    # Collapse chained modals: "[] []p" / "[] [] p" -> "[][]p"
    s = re.sub(r"\[\]\s+\[\]\s*", "[][]", s)
    s = re.sub(r"<>\s+<>\s*", "<><>", s)

    # Unicode spacing support: "□ p" -> "□p", "◇ p" -> "◇p"
    s = re.sub(r"□\s+(?=[A-Za-z(~\[])", "□", s)
    s = re.sub(r"◇\s+(?=[A-Za-z(~\[])", "◇", s)

    # Safe Atom Mapping: ONLY if it looks like a logic domain
    # (Since _norm_formula is called on suspected formulas, we can be slightly bold)
    # Map A,B,C -> p,q,r only for logic domains
    if map_atoms:
        s = re.sub(r"\bA\b", "p", s)
        s = re.sub(r"\bB\b", "q", s)
        s = re.sub(r"\bC\b", "r", s)

    s = _WS.sub(" ", s).strip()
    if _is_broken_arrow(s):
        return ""
    return s

def _is_broken_arrow(s: str) -> bool:
    s = (s or "").strip()
    if s.endswith("->"):
        return True
    if "->" in s:
        _, rhs = s.split("->", 1)
        if not rhs.strip():
            return True
    return False


# ----------------------------
# Structured header parsing (your UI format)
# ----------------------------

_STRUCT_DOMAIN_RE = re.compile(r"(?im)^\s*Domain\s*:\s*([a-zA-Z0-9_]+)\s*$")
_STRUCT_ASSUME_RE = re.compile(r"(?im)^\s*Assumption(?:s)?\s*:\s*(.+?)\s*$")
_STRUCT_FORMULA_RE = re.compile(r"(?im)^\s*Formula\s*:\s*(.+?)\s*$")

def parse_structured_header(q: str) -> Dict[str, Any]:
    q = q or ""
    dom = None
    m = _STRUCT_DOMAIN_RE.search(q)
    if m:
        dom = m.group(1).strip().lower()

    assumptions: List[str] = []
    for m in _STRUCT_ASSUME_RE.finditer(q):
        parts = re.split(r"[,\s]+", m.group(1).strip().lower())
        assumptions.extend([p for p in parts if p])

    formula = None
    m = _STRUCT_FORMULA_RE.search(q)
    if m:
        formula = m.group(1).strip()

    return {"domain": dom, "assumptions": assumptions, "formula": formula}


# ----------------------------
# Domain detection (Japanese-first; English OK)
# ----------------------------

def detect_domain(text: str) -> str:
    t = (text or "")
    if detect_domain_pipeline:
        d = detect_domain_pipeline(t)
        if d and d != "unknown":
            return d

    tl = t.lower()

    if ("∀" in t) or ("∃" in t) or ("quantifier" in tl) or ("first-order" in tl) or ("述語" in t) or ("一階" in t) or ("モデル" in t and "構造" in t):
        return "first_order_logic"
    if ("kripke" in tl) or ("□" in t) or ("◇" in t) or ("[]" in tl) or ("<>" in tl) or ("様相" in t):
        return "modal_logic"
    if ("tautology" in tl) or ("恒真" in t) or ("真理値表" in t):
        return "propositional_logic"
    if ("matrix" in tl) or ("行列" in t) or ("対称" in t) or ("次元" in t):
        return "linear_algebra"

    return "unknown"


# ----------------------------
# Assumption detection (KB lexicon compatible)
# ----------------------------

def _find_phrases(text: str, phrases: List[str]) -> Optional[str]:
    if not phrases:
        return None
    t = text.lower()
    for p in sorted(phrases, key=len, reverse=True):
        if p.lower() in t:
            return p
    return None

def _detect_assumptions_from_kb(text: str, knowledge_db: Dict[str, Any]) -> Tuple[List[str], List[str], Dict[str, List[Span]]]:
    """
    Looks at knowledge_db["lexicon"]["assumptions"] and extracts tags like assume:transitive
    """
    audit: List[str] = []
    assumptions: List[str] = []
    evidence_map: Dict[str, List[Span]] = {}

    lex = (knowledge_db.get("lexicon") or {}).get("assumptions") or {}
    tnorm = _norm_text(text)

    for tag, entry in lex.items():
        pos = entry.get("positive") or []
        neg = entry.get("negative") or []

        hit_neg = _find_phrases(tnorm, neg)
        if hit_neg:
            audit.append(f"[ASSUME] skip {tag} (neg-hit: '{hit_neg}')")
            continue

        hit_pos = _find_phrases(tnorm, pos)
        if hit_pos:
            assumptions.append(tag)
            audit.append(f"[ASSUME] add {tag} (hit: '{hit_pos}')")
            evidence_map[tag] = find_spans(tnorm, [hit_pos])

    return sorted(set(assumptions)), audit, evidence_map


# ----------------------------
# Formula extraction (CRITICAL FIX)
#   1) Extract formula first (from raw text)
#   2) Normalize formula only
# ----------------------------

_FORMULA_CHUNK_RE = re.compile(
    rf"(?ix)"
    rf"(?P<formula>"
    rf"(?:\b(?:box|diamond)\b\s*)?"
    rf"(?:[□◇~\(]|\b(?:box|diamond)\b|[A-Za-z][A-Za-z0-9_]*|[⊤⊥TF])"
    rf"(?:\s*(?:->|<->|&|\||∧|∨|→)\s*"
    rf"(?:[□◇~\(]|\b(?:box|diamond)\b|[A-Za-z][A-Za-z0-9_]*|[⊤⊥TF]|\))*)*"
    rf")"
)

_QUOTED_FORMULA_RE = re.compile(r'["“”]([^"“”]+)["“”]|「([^」]+)」|『([^』]+)』')

def extract_quoted_formulas(text: str) -> List[str]:
    out: List[str] = []
    for m in _QUOTED_FORMULA_RE.finditer(text or ""):
        frag = next((g for g in m.groups() if g), "")
        if frag:
            out.append(frag.strip())
    return out

def extract_formulas(text: str, map_atoms: bool = True) -> List[str]:
    """
    Japanese-first: also finds formulas containing □ ◇.
    Returns list of normalized formulas.
    """
    raw = text or ""
    candidates: List[str] = []
    seen = set()

    for m in _FORMULA_CHUNK_RE.finditer(raw):
        frag = m.group("formula") or ""
        frag = frag.strip()
        # Must include at least one operator or modal keyword
        if not (("->" in frag) or ("→" in frag) or ("&" in frag) or ("∧" in frag) or ("|" in frag) or ("∨" in frag) or ("□" in frag) or ("◇" in frag) or ("box" in frag.lower()) or ("diamond" in frag.lower()) or ("<->" in frag)):
            continue
        nf = _norm_formula(_norm_text(frag), map_atoms=map_atoms)
        if len(nf) < 3 or nf.endswith("->") or nf.endswith("&") or nf.endswith("|") or nf.endswith("<->"):
            continue
        if nf not in seen:
            seen.add(nf)
            candidates.append(nf)

    return candidates


# ----------------------------
# Option / candidate extraction (A/B/C/D choices)
# ----------------------------

_OPT_BLOCK_RE = re.compile(r"(?s)(^|\n)\s*([A-D])\s*[\.:]\s*(.+?)(?=(\n\s*[A-D]\s*[\.:])|\Z)")

def extract_options(text: str, map_atoms: bool = True) -> List[str]:
    t = text or ""
    out: List[str] = []
    for m in _OPT_BLOCK_RE.finditer(t):
        body = (m.group(3) or "").strip()
        if not body:
            continue
        if len(body) > 800:
            continue
        out.append(_norm_formula(_norm_text(body), map_atoms=map_atoms))
    return out


# ----------------------------
# Query Type inference
# ----------------------------

def infer_query_type(query: str, candidates: List[str], core_formula: Optional[str] = None) -> QueryType:
    """
    自然文クエリと抽出された候補式から、問題の意図を推定する。
    Solver が「迷わない」ための決定打。
    """
    q = (query or "").lower()

    # 同値判定
    if any(w in q for w in ["同値", "equivalent"]) or "↔" in q:
        return QueryType.EQUIVALENCE

    # 明示的な集合全称
    if any(w in q for w in ["すべて", "全て", "all", "すべての式"]):
        return QueryType.SET_ALL

    # 明示的な存在
    if any(w in q for w in ["どれか", "いずれか", "any", "存在"]):
        return QueryType.SET_ANY

    # ★ NEW: core_formula が空で、候補が複数ある場合 -> SET_ALL (集合問題とみなす)
    if not core_formula and len(candidates) >= 2:
        return QueryType.SET_ALL

    # 候補が 1 つだけなら単一式
    if len(candidates) == 1:
        return QueryType.SINGLE

    # 候補が複数あるが意図不明 → 安全側（全部成立するか）
    if len(candidates) > 1:
        return QueryType.SET_ALL

    # フォールバック
    return QueryType.SINGLE


# ----------------------------
# High-level decomposition
# ----------------------------

def decompose_problem(text: str, knowledge_db: Dict[str, Any]) -> Spec:
    from avh_math.input_pipeline import decompose_text

    d = decompose_text(text)
    
    # 決定打：パイプライン側で推論された query_type をそのまま採用する
    # 再推論すると、normalize後の文字列で判定することになり精度が落ちるため

    return Spec(
        assumptions=d.assumptions,
        candidates=d.candidates,
        audit=d.audit,
        atoms=d.atoms,
        evidence_map={},
        domain=d.domain,
        core_formula=d.core_formula or "",
        query_type=d.query_type
    )

decompose = decompose_problem
