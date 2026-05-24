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

_FORMULA_TOKEN_RE = re.compile(r"(?:[]|<>|\(|\)|~|&|\||->|<->)")
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
    t = (text or "")
    
    # 決定打：法律ドメインの優先検知
    if any(k in t for k in ["民法", "刑法", "条文", "契約", "売主", "買主", "責任", "違法", "適法", "損害賠償", "解除"]):
        return "law"

    if detect_domain_hint_shared:
        d = detect_domain_hint_shared(text)
        if d and d != "unknown":
            return d

    tl = t.lower()

    if ("∀" in t) or ("∃" in t) or ("quantifier" in tl) or ("first-order" in tl) or ("述語" in t) or ("一階" in t) or ("モデル" in t and "構造" in t):
        return "first_order_logic"
    if ("kripke" in tl) or ("□" in t) or ("◇" in t) or ("[]" in tl) or ("<>" in tl) or ("様様" in t):
        return "modal_logic"
    if ("tautology" in tl) or ("恒真" in t) or ("真理値表" in t):
        return "propositional_logic"
    if ("matrix" in tl) or ("行列" in t) or ("対称" in t) or ("次元" in t):
        return "linear_algebra"
    return "unknown"


def normalize_formula(s: str) -> str:
    if normalize_formula_shared:
        return normalize_formula_shared(s)
    return (s or "").strip()


def build_spec_for_cross(raw_text: str) -> Dict[str, Any]:
    cleaned = strip_ui_noise(raw_text)
    hdr = parse_structured_header(cleaned)
    domain = hdr.get("domain") or detect_domain(cleaned)
    assumptions = list(hdr.get("assumptions") or [])
    quoted = extract_quoted_formulas(cleaned)
    candidates = []
    if quoted:
        candidates = [normalize_formula(q) for q in quoted if normalize_formula(q)]
    core_formula = hdr.get("formula") or (candidates[0] if candidates else "")
    return {
        "raw_text": raw_text,
        "cleaned_text": cleaned,
        "domain": domain,
        "assumptions": assumptions,
        "quoted": quoted,
        "candidates": candidates,
        "core_formula": core_formula,
    }

# ==== V2 Input Pipeline (additive; do not break existing APIs) ====
_NOISE_LINE_PATTERNS_V2 = [
    r"^\s*【入力ルール】",
    r"^\s*TPL:\s*",
    r"^\s*Modal tips:",
    r"^\s*SOLVE\s*$",
    r"^\s*UNSUPPORTED\s*$",
    r"^\s*UNKNOWN\s*$",
    r"^\s*DISPROVED\s*$",
    r"^\s*PROVED\s*$",
    r"^\s*INTERNAL EVALUATION:",
    r"^\s*Completed in\b",
    r"^\s*REASONING PROOF\b",
    r"^\s*COUNTEREXAMPLE\b",
    r"^\s*TRACE\s*/\s*STATS\b",
    r"^\s*NEXT ACTIONS\b",
    r"^\s*KEY:\s*q_[0-9a-f]+\s*$",
    r"^\s*Explanation\s*$",
    r"^\s*Boundary Graph\s*$",
    r"^\s*Proof Library\s*$",
    r"^\s*GENERATE EXPLANATION\b",
    r"^\s*Run \"Solve\"",
    r"^\s*Verantyx Cross\b",
    r"^\s*BUILD CROSS\b",
    r"^\s*SOLVE \(CROSS\)\b",
    r"^\s*cross_id:\s*$",
    r"^\s*Domain:\s*",
    r"^\s*Assumption[s]*:\s*",
    r"^\s*Formula:\s*",
    r"^\s*Problem:\s*",
    r"^\s*Context:\s*",
]
_NOISE_RE_V2 = re.compile("|".join(_NOISE_LINE_PATTERNS_V2), re.IGNORECASE)

def strip_ui_noise_v2(raw_text: str) -> str:
    lines = (raw_text or "").splitlines()
    kept = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _NOISE_RE_V2.search(s):
            continue
        if re.match(r"^\s*[=\-]{4,}\s*$", s):
            continue
        kept.append(ln)
    return "\n".join(kept).strip()

_QUOTED_RE_V2 = re.compile(r'"([^"]{1,500})"|“([^”
]{1,500})”|「([^」
]{1,500})」')

def extract_quoted_formulas_v2(text: str) -> List[str]:
    out: List[str] = []
    for m in _QUOTED_RE_V2.finditer(text or ""):
        s = next((g for g in m.groups() if g), "")
        s = (s or "").strip()
        if s:
            out.append(s)
    return out

def normalize_formula_v2(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\u200b", "").replace("\ufeff", "")
    
    # LaTeX normalization
    s = s.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
    s = s.replace(r"\to", "->").replace(r"\rightarrow", "->").replace(r"\leftrightarrow", "<->")
    s = s.replace(r"\box", "[]").replace(r"\diamond", "<>")
    
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)
    s = s.replace("□", "[]").replace("◇", "<>")
    s = s.replace("→", "->").replace("−", "-").replace("÷", "/")
    
    # 決定打：クォートされていない部分のみスペースを詰める
    if not (s.startswith('"') and s.endswith('"')):
        s = re.sub(r"\s+", "", s)
    else:
        # クォートの中身のみを取り出し、前後のゴミを掃除
        s = s.strip('"')
        s = re.sub(r"\s+", " ", s).strip()
    
    if s in ("[]", "<>", "->", ""):
        return ""
    return s

def _detect_domain_v2(cleaned_text: str, candidates: List[str]) -> str:
    t = (cleaned_text or "").lower()
    joined = " ".join(candidates).lower()
    if "[]" in joined or "<>" in joined:
        return "modal_logic"
    if any(x in joined for x in ["∀", "∃", "forall", "exists"]):
        return "first_order_logic"
    if any(x in joined for x in ["dim sym", "rank(", "matrix", " 対称行列", "行列", "次元"]):
        return "linear_algebra"
    if any(k in t for k in ["クリプケ", "kripke", "推移性", "反射性", "様相", "必然", "可能"]):
        return "modal_logic"
    if any(k in t for k in ["恒真", "命題論理", "真理値", "トートロジー"]):
        return "propositional_logic"
    if any(k in t for k in [r"\land", r"\lor", r"\to", r"\neg"]):
        return "propositional_logic"
    if any(k in t for k in ["全称", "存在", "述語", "一階", "モデル", "充足"]):
        return "first_order_logic"
    if any(k in t for k in ["対称行列", "次元", "線形", "固有値", "rank"]):
        return "linear_algebra"
    if any(k in t for k in ["民法", "刑法", "条文", "契約", "売主", "買主", "責任", "違法", "適法", "損害賠償", "解除"]):
        return "law"
    return "unknown"

def build_input_spec_v2(raw_text: str) -> Dict[str, Any]:
    audit: List[str] = []
    cleaned = strip_ui_noise_v2(raw_text or "")
    audit.append(f"[V2] cleaned_len={len(cleaned)}")

    candidates: List[str] = []
    quoted = extract_quoted_formulas_v2(cleaned)
    if quoted:
        audit.append(f"[V2] quoted={len(quoted)}")
        for q in quoted[:50]:
            f = normalize_formula_v2(q)
            if f:
                candidates.append(f)

    if not candidates:
        audit.append("[V2] no_quoted; fallback scan")
        for m in re.finditer(r"(\[\][^\n]{1,120})", cleaned):
            f = normalize_formula_v2(m.group(1))
            if f:
                candidates.append(f)
                break
        if not candidates:
            for m in re.finditer(r"([A-Za-z\(\)~\|\&\s\[\]□◇]{0,60}->[A-Za-z\(\)~\|\&\s\[\]□◇]{1,60})", cleaned):
                f = normalize_formula_v2(m.group(1))
                if f:
                    candidates.append(f)
                    break

    core_formula = candidates[0] if candidates else cleaned
    domain = _detect_domain_v2(cleaned, candidates)
    if isinstance(core_formula, str) and core_formula.endswith("->"):
        audit.append("[V2][WARN] core endswith -> ; switching to cleaned")
        core_formula = cleaned

    return {
        "raw_text": raw_text or "",
        "cleaned_text": cleaned,
        "domain_hint": domain,
        "assumptions": [],
        "candidates": candidates,
        "core_formula": core_formula,
        "audit": audit,
    }


# ==== D0-D3 Text Decomposition (additive) ====
from dataclasses import dataclass, field
from avh_math.avh_math.answer_types.query_type import QueryType
from avh_math.avh_math.answer_types.problem_type import ProblemType
from avh_math.puzzle.formula_gate import is_well_formed_formula
from avh_math.input_rules import (
    pick_core_formula,
    detect_modal_assumptions,
    extract_inline_formula,
    is_formula_like,
)
from avh_math.shape_signature import shape_signature

_ABCD_RE = re.compile(r"(^|\n|\s)([A-D])\s*[\.:]\s*([\s\S]+?)(?=\n\s*[A-D]\s*[\.:]|\Z)", re.DOTALL)
_FOUNDATION_DEDUP_PATH = Path(__file__).resolve().parent / "db" / "foundation_kb.dedup.fixed.jsonl"
_FOUNDATION_DEDUP_INDEX: Dict[str, List[Dict[str, Any]]] = {}
_FOUNDATION_DEDUP_KEYS: List[str] = []
_FOUNDATION_DEDUP_LOADED = False


def _extract_abcd_candidates(text: str) -> List[str]:
    out: List[str] = []
    for m in _ABCD_RE.finditer(text or ""):
        body = (m.group(3) or "").strip()
        if not body:
            continue
        if len(body) > 800:
            continue
        try:
            from avh_math.input_rules import _normalize_formula  # type: ignore
        except Exception:
            _normalize_formula = None
        out.append(_normalize_formula(body) if _normalize_formula else body)
    seen = set()
    uniq = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _detect_assumptions_ja_en(text: str) -> List[str]:
    t = text or ""
    tl = t.lower()
    out = []
    if ("推移" in t) or ("transitive" in tl):
        out.append("assume:transitive")
    if ("反射" in t) or ("reflexive" in tl):
        out.append("assume:reflexive")
    if ("対称" in t) or ("symmetric" in tl):
        out.append("assume:symmetric")
    if ("ユークリッド" in t) or ("euclidean" in tl):
        out.append("assume:euclidean")
    if ("全称" in t) or ("存在" in t) or ("∀" in t) or ("∃" in t) or ("forall" in tl) or ("exists" in tl):
        out.append("assume:fol")
    out.extend(detect_modal_assumptions(text))
    return sorted(set(out))


def _normalize_kb_formula(s: str) -> str:
    s = (s or "").strip()
    s = s.replace(" ", "")
    s = s.replace("→", "->").replace("¬", "~").replace("∧", "&").replace("∨", "|")
    s = s.replace("□", "[]").replace("◇", "<>")
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)
    return s


def _load_foundation_dedup_index() -> None:
    global _FOUNDATION_DEDUP_LOADED, _FOUNDATION_DEDUP_KEYS
    if _FOUNDATION_DEDUP_LOADED:
        return
    _FOUNDATION_DEDUP_LOADED = True
    if not _FOUNDATION_DEDUP_PATH.exists():
        return
    index: Dict[str, List[Dict[str, Any]]] = {}
    with _FOUNDATION_DEDUP_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            domain = (obj.get("domain") or "").strip().lower()
            statement = obj.get("statement") or ""
            patterns = obj.get("patterns") or []
            keys = []
            if statement:
                keys.append(statement)
            for pat in patterns:
                if pat:
                    keys.append(pat)
            for key in keys:
                if not is_formula_like(str(key)):
                    continue
                norm = _normalize_kb_formula(str(key))
                if not norm:
                    continue
                index.setdefault(norm, []).append(
                    {
                        "id": obj.get("id"),
                        "domain": domain,
                        "statement": statement,
                        "pattern": key,
                    }
                )
    _FOUNDATION_DEDUP_INDEX.update(index)
    _FOUNDATION_DEDUP_KEYS = sorted(index.keys(), key=len, reverse=True)


def _kb_formula_hint(candidates: List[str], core_formula: str, text: str) -> Optional[Dict[str, Any]]:
    _load_foundation_dedup_index()
    if not _FOUNDATION_DEDUP_INDEX:
        return None
    probe = []
    if core_formula:
        probe.append(core_formula)
    probe.extend(candidates)
    inline = extract_inline_formula(text or "")
    if inline:
        probe.append(inline)
    for cand in probe:
        if not cand:
            continue
        norm = _normalize_kb_formula(cand)
        hits = _FOUNDATION_DEDUP_INDEX.get(norm)
        if hits:
            hit = hits[0]
            return {
                "formula": cand,
                "domain": hit.get("domain") or "unknown",
                "kb_id": hit.get("id"),
                "pattern": hit.get("pattern") or hit.get("statement"),
            }
    return None


def _kb_inline_extract(text: str) -> Optional[str]:
    _load_foundation_dedup_index()
    if not _FOUNDATION_DEDUP_KEYS:
        return None
    norm_text = _normalize_kb_formula(text or "")
    if not norm_text:
        return None
    for key in _FOUNDATION_DEDUP_KEYS:
        if key and key in norm_text:
            return key
    return None


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
    context_text: Optional[str] = None # Added field

def infer_problem_type(query: str, core_formula: Optional[str], assumptions: List[str]) -> ProblemType:
    q = (query or "").lower()
    
    if not core_formula or not is_well_formed_formula(core_formula):
        return ProblemType.VALIDITY_CHECK 

    if "反例" in q or "counterexample" in q:
        return ProblemType.COUNTEREXAMPLE_CHECK

    if assumptions:
        return ProblemType.AXIOM_DEPENDENT_VALIDITY

    if "常に" in q or "任意の" in q or "always" in q or "valid" in q or "恒真" in q:
        return ProblemType.VALIDITY_CHECK
        
    if "充足" in q or "satisfiable" in q:
        return ProblemType.SATISFIABILITY_CHECK

    return ProblemType.VALIDITY_CHECK

def infer_query_type(query: str, candidates: List[str], core_formula: Optional[str] = None) -> QueryType:
    q = (query or "").lower()
    has_natural_lang = any(w in q for w in ["か", "？", "?", "定理", "成り立つ", "恒真", "valid"])
    
    if any(w in q for w in ["同値", "equivalent"]) or "↔" in q:
        return QueryType.EQUIVALENCE
    if any(w in q for w in ["すべて", "全て", "all", "すべての式", "常に", "任意の", "every", "always"]):
        return QueryType.SET_ALL
    if any(w in q for w in ["どれか", "いずれか", "any", "存在", "exists"]):
        return QueryType.SET_ANY
    if len(candidates) >= 2:
        return QueryType.SET_ALL
    return QueryType.SINGLE


def split_candidates(text: str) -> List[str]:
    text = (text or "").replace("，", ",")
    parts = []
    buf = ""
    depth = 0
    for ch in text:
        if ch in "([{": depth += 1
        elif ch in ")]}": depth -= 1
        if ch == "," and depth == 0:
            if buf.strip(): parts.append(buf.strip())
            buf = ""
        else: buf += ch
    if buf.strip(): parts.append(buf.strip())
    return parts


from avh_math.recognizers.dispatcher import RecognizerDispatcher
from avh_math.recognizers.semantic_parser import SemanticParser

def decompose_text(text: str, text_cross_hint_min_score: float = 0.25) -> Decomposed:
    print("!!! RELOADED INPUT_PIPELINE !!!")
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    audit: List[str] = []
    
    context_match = re.search(r"(?im)^\s*Context\s*:\s*(.+?)(?=\n\s*(?:Domain|Assumption|Formula|Problem):|\Z)", text, re.S)
    context_text = context_match.group(1).strip() if context_match else None
    
    text = text.replace(r"\land", "&").replace(r"\lor", "|").replace(r"\neg", "~")
    text = text.replace(r"\to", "->").replace(r"\rightarrow", "->").replace(r"\leftrightarrow", "<->")
    text = text.replace(r"\box", "[]").replace(r"\diamond", "<>")
    
    dispatcher = RecognizerDispatcher()
    rec_result = dispatcher.dispatch(text)
    all_candidates = rec_result["candidates"]
    sem_assumptions = rec_result.get("extracted_assumptions", [])
    candidates: List[str] = []
    tentative_core = all_candidates[0]["normalized"] if all_candidates else None
    
    hdr = parse_structured_header(strip_ui_noise(text))
    if hdr.get("formula"):
        core_candidate = {"normalized": normalize_formula(hdr["formula"]), "score": 5.0, "surface": hdr["formula"], "span": (0, len(text))}
        formula_type = "structured_header"
    else:
        core_candidate, formula_type = select_core_formula(all_candidates, text)
    
    parsed = pick_core_formula(text)
    sig = shape_signature(text, core_formula=parsed.core_formula)
    text_cross = build_text_cross(text or "")
    shape_seq = [n.content.get("shape", "") for n in text_cross.nodes.values() if isinstance(n.content, dict)]
    text_cross_similars = query_similar_cross_kb_scored(shape_seq, top_k=3)
    text_cross_hint = ""
    if text_cross_similars:
        text_cross_hint = extract_hint_from_cross(text_cross_similars[0])
        if text_cross_hint and not is_formula_like(text_cross_hint): text_cross_hint = ""
    text_cross_scores = [float(c.get("_score", 0.0)) for c in text_cross_similars if isinstance(c, dict)]
    text_cross_max_score = max(text_cross_scores) if text_cross_scores else 0.0
    
    tc_reconstruction = reconstruct_formula_from_shapes([{"token": n.content.get("surface", ""), "shape": n.content.get("shape", "")} for n in text_cross.nodes.values() if isinstance(n.content, dict)])
    if tc_reconstruction and len(tc_reconstruction) > 2:
        norm_tc = normalize_formula_v2(tc_reconstruction)
        if norm_tc and norm_tc not in candidates:
            candidates.insert(0, norm_tc)

    mapping = suggest_mapping(shape_seq)
    text_cross_domain = ""
    if text_cross_similars:
        domain_counts = {}
        for c in text_cross_similars:
            if not isinstance(c, dict): continue
            dom = (c.get("domain") or "").strip().lower()
            if dom: domain_counts[dom] = domain_counts.get(dom, 0) + 1
        if domain_counts: text_cross_domain = max(domain_counts, key=domain_counts.get)

    rule_domain = detect_domain(text)
    sem_domain = rec_result.get("domain")
    if sem_domain: domain = sem_domain
    elif rule_domain == "law": domain = "law"
    else: domain = sig.domain_hint or mapping.get("domain_hint") or text_cross_domain or rule_domain or "unknown"
        
    assumptions = _detect_assumptions_ja_en(text)
    if sem_assumptions:
        for a in sem_assumptions:
            if a not in assumptions: assumptions.append(a)
    hdr_assumes = parse_structured_header(text).get("assumptions", [])
    for a in hdr_assumes:
        if a not in assumptions: assumptions.append(a)
    
    is_likely_single_check = (parsed.core_formula is not None) or (len(extract_formula_candidates(text)) == 1)
    if not is_likely_single_check:
        for a in mapping.get("assumptions") or []:
            if a not in assumptions: assumptions.append(a)

    abcd_candidates = _extract_abcd_candidates(text)
    abcd_candidates = [c for c in abcd_candidates if is_formula_like(c)]
    kb_hint = _kb_formula_hint(abcd_candidates, parsed.core_formula or "", text)
    kb_formula = (kb_hint or {}).get("formula") or ""
    kb_inline = _kb_inline_extract(text or "")

    ranked_candidates: List[str] = []
    if rec_result.get("type") == "semantic_parsed":
        for c in all_candidates:
            if c.get("normalized"): ranked_candidates.append(c["normalized"])
    else:
        if kb_inline and is_formula_like(kb_inline): ranked_candidates.append(kb_inline)
        if kb_formula and is_formula_like(kb_formula): ranked_candidates.append(kb_formula)
        if parsed.core_formula and is_formula_like(parsed.core_formula): ranked_candidates.append(parsed.core_formula)
        if text_cross_hint and is_formula_like(text_cross_hint) and text_cross_max_score >= text_cross_hint_min_score:
            ranked_candidates.append(text_cross_hint)
        ranked_candidates.extend(abcd_candidates)

    candidates = []
    headers = ("domain:", "assumption:", "formula:", "problem:", "task:", "context:")
    for c in ranked_candidates:
        c_clean = c.strip()
        if any(c_clean.lower().startswith(h) for h in headers): continue
        if c_clean and c_clean not in candidates: candidates.append(c_clean)

    atoms: List[str] = []
    core_for_atoms = (parsed.core_formula or "")
    if domain in ("propositional_logic", "modal_logic"):
        seen = []
        for m in re.finditer(r"\b([A-Za-z])\b", core_for_atoms or text):
            sym = m.group(1)
            if sym not in seen: seen.append(sym)
        atoms = sorted(set([s.lower() for s in seen]))
    if not atoms: atoms = ["p"] if domain in ("propositional_logic", "modal_logic") else ["x", "y", "z"]

    if domain == "law": core_formula = text
    elif core_candidate: core_formula = core_candidate["normalized"]
    elif tentative_core: core_formula = tentative_core
    else: core_formula = None

    # Identify axioms provided by user context (candidates that are NOT the core formula)
    injected_axioms = []
    
    # Aggressive full-text scan for formulas (ignoring headers)
    print("[DEBUG PIPELINE] Aggressive Scan START")
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        
        # Skip header lines
        if re.match(r"^(Problem|Context|Domain|Assumption|Formula|Task):", line, re.I):
            print(f"[DEBUG PIPELINE] Skipping header line: {line[:30]}...")
            continue

        # Heuristic: Is this line a formula?
        if ("->" in line or "[]" in line or "<>" in line) and len(line) < 200:
            if re.search(r"(Refer|See|Using|This|Here|The|define|means|follows|valid)", line, re.I):
                print(f"[DEBUG PIPELINE] Skipped as NL: {line[:30]}...")
                continue
                
            f = normalize_formula_v2(line)
            print(f"[DEBUG PIPELINE] Normalized: {f}")
            
            if f and len(f) > 3:
                if f not in candidates:
                    candidates.append(f)
                    print(f"[DEBUG PIPELINE] Added candidate: {f}")
                
                if core_formula and f != core_formula:
                    injected_axioms.append(f)
                elif not core_formula:
                    injected_axioms.append(f)

    evidence = {
        "context_text": context_text, 
        "text_cross_mapping": mapping, 
        "kb_dedup_match": kb_hint or {},
        "injected_axioms": injected_axioms 
    }

    final_candidates = []
    for c in candidates: final_candidates.extend(split_candidates(c))
    candidates = [c for c in final_candidates if c.strip()]
    query_type = infer_query_type(text, candidates, core_formula)
    problem_type = infer_problem_type(text, core_formula, assumptions)

    return Decomposed(
        domain=domain, core_formula=core_formula, candidates=candidates, 
        assumptions=assumptions, atoms=atoms, evidence=evidence, audit=audit, 
        query_type=query_type, problem_type=problem_type, context_text=context_text
    )