from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_QUOTED_RE = re.compile(r'"([^"]+)"')
# 決定打：角括弧や矢印を正しく含む正規表現に修正 + LaTeXコマンド用バックスラッシュ追加
_UNQUOTED_LOGIC_RE = re.compile(r"([\[\]<>&|~()A-Za-z\->\s\\]{3,})")
_UNQUOTED_MATH_RE = re.compile(r"(∫|dx|dy|dz|sin|cos|tan|log|ln|exp|lim|sum|prod|sqrt|∞|dim|dimension|matrix|行列|次元|対称)", re.IGNORECASE)
_GREEK_SYMBOL_RE = re.compile(r"[φψχαβγδλμνπστω]")
_DIM_SYM_EN = re.compile(r"dimension of (the )?space of (n\s*x\s*n|n×n) symmetric matrices", re.IGNORECASE)
_DIM_SYM_JA = re.compile(r"(実|複素)?n次対称行列の空間の次元|対称行列の空間の次元")
_DIM_MAT_EN = re.compile(r"dimension of (the )?space of (n\s*x\s*n|n×n) matrices", re.IGNORECASE)
_DIM_MAT_JA = re.compile(r"(実|複素)?n次行列の空間の次元|行列の空間の次元")

_ARROW_FIX = [
    ("→", "->"),
    ("⇒", "->"),
    ("⟶", "->"),
    ("⟹", "->"),
    ("↦", "->"),
]
_MISC_FIX = [
    ("\u200b", ""),
    ("\ufeff", ""),
    ("\u200c", ""),
    ("\u200d", ""),
    (r"\land", "&"),
    (r"\lor", "|"),
    (r"\neg", "~"),
    (r"\to", "->"),
    (r"\rightarrow", "->"),
    (r"\leftrightarrow", "<->"),
    (r"\box", "[]"),
    (r"\diamond", "<>"),
    ("¬", "~"),
    ("∧", "&"),
    ("∨", "|"),
    ("□", "[]"),
    ("◇", "<>"),
]
_WORD_MODAL = [
    (re.compile(r"\bbox\b", re.IGNORECASE), "[]"),
    (re.compile(r"\bdiamond\b", re.IGNORECASE), "<>"),
]
_SPACE_AFTER_MODAL = re.compile(r"(\[\]|\<\>)\s+")
_HAS_LOGIC_TOKENS = re.compile(r"(\-\>|\&|\||~|\[\]|\<\>|\(|\))")
_INLINE_MODAL_RE = re.compile(r"(\[\].{1,240}?->.{1,240})", re.DOTALL)
_INLINE_DIA_RE = re.compile(r"(\<\>.{1,240}?->.{1,240})", re.DOTALL)
_INLINE_PROP_RE = re.compile(r"([A-Za-z0-9_()\s~&|]+->[\sA-Za-z0-9_()~&|]+)", re.DOTALL)
_INLINE_FORMULA_CHUNK_RE = re.compile(r"[A-Za-z0-9_\[\]<>~&|()*/=\+\-]+")
_HAS_JA_RE = re.compile(r"[一-龥ぁ-んァ-ン]")
_MATH_TOKENS = re.compile(r"(∫|dx|dy|dz|sin|cos|tan|log|ln|exp|lim|sum|prod|sqrt|\^|/|∞)", re.IGNORECASE)

_ASSUME_JA = {
    "assume:transitive": ["推移", "推移性", "transitive"],
    "assume:reflexive": ["反射", "反射性", "reflexive"],
    "assume:symmetric": ["対称", "対称性", "symmetric"],
    "assume:serial": ["逐次", "serial"],
    "assume:euclidean": ["ユークリッド", "euclidean"],
}


@dataclass
class ParsedInput:
    raw: str
    core_formula: Optional[str]
    extra_formulas: List[str]
    context_text: str
    parse_notes: List[str]


def _normalize_formula(s: str) -> str:
    s = s.strip()
    is_math = bool(_MATH_TOKENS.search(s))
    for a, b in _ARROW_FIX:
        s = s.replace(a, b)
    for a, b in _MISC_FIX:
        s = s.replace(a, b)
    for pat, repl in _WORD_MODAL:
        s = pat.sub(repl, s)
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _SPACE_AFTER_MODAL.sub(r"\1", s)
    s = re.sub(r"\s*->\s*", "->", s)
    s = re.sub(r"\s*&\s*", "&", s)
    s = re.sub(r"\s*\|\s*", "|", s)
    s = re.sub(r"\s*~\s*", "~", s)
    if not is_math:
        # Guard against UI noise for logic formulas only.
        s = re.sub(r"\s+[a-zA-Z]\s*$", "", s).strip()
    return s


def extract_quoted_formulas(text: str) -> List[str]:
    out: List[str] = []
    for m in _QUOTED_RE.finditer(text or ""):
        g = next((x for x in m.groups() if x), None)
        if not g:
            continue
        f = _normalize_formula(g)
        if f:
            out.append(f)
    seen = set()
    uniq = []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def extract_unquoted_formulas(text: str) -> List[str]:
    out: List[str] = []
    raw = text or ""
    # If inline formula exists, prefer it over long sentence lines.
    inline = extract_inline_formula(raw)

    # Pattern-based linear algebra hints.
    if _DIM_SYM_EN.search(raw) or _DIM_SYM_JA.search(raw):
        out.append(_normalize_formula("dim Sym(n,R)"))
    if _DIM_MAT_EN.search(raw) or _DIM_MAT_JA.search(raw):
        out.append(_normalize_formula("dim M(n,n,R)"))

    # Math-like detection: keep full lines if they contain math tokens.
    for line in raw.splitlines():
        if _UNQUOTED_MATH_RE.search(line):
            # Avoid capturing long natural-language lines as formulas.
            candidate = _normalize_formula(line)
            if candidate:
                # Heuristic: skip if long and operator density is low.
                op_count = len(re.findall(r"[\\[\\]<>~&|()]", candidate)) + candidate.count("->") + candidate.count("<->")
                word_count = len(re.findall(r"[A-Za-z一-龥ぁ-んァ-ン]", line))
                if len(candidate) > 120 and op_count < 2 and word_count > 10:
                    continue
                out.append(candidate)

    # Logic-like fragments (simple heuristic).
    for m in _UNQUOTED_LOGIC_RE.finditer(raw):
        cand = m.group(1) or ""
        if "->" in cand or "&" in cand or "|" in cand or "[]" in cand or "<>" in cand or "~" in cand:
            f = _normalize_formula(cand)
            if f:
                out.append(f)

    # Inline fallback: grab the first formula-like chunk.
    if inline and inline not in out:
        out.append(inline)

    # Greek-symbol fallback only when logic tokens are present.
    if not out and _GREEK_SYMBOL_RE.search(raw) and _HAS_LOGIC_TOKENS.search(raw):
        out.append(_normalize_formula("φ"))

    seen = set()
    uniq: List[str] = []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def is_formula_like(s: str) -> bool:
    if not s:
        return False
    return bool(_HAS_LOGIC_TOKENS.search(s) or _MATH_TOKENS.search(s))


def _is_strong_formula(s: str) -> bool:
    """
    Stronger signal used for inline extraction (avoid lone [] or single symbols).
    """
    if not s:
        return False
    if _MATH_TOKENS.search(s):
        return True
    return bool(re.search(r"(->|<->|&|\||~)", s))


def extract_inline_formula(text: str) -> Optional[str]:
    """
    Extract a likely formula-like substring from a long sentence.
    Priority: modal chain, then implication-like fragment.
    """
    if not text:
        return None
    m = _INLINE_MODAL_RE.search(text)
    if m:
        if not _HAS_JA_RE.search(m.group(1)):
            return _normalize_formula(m.group(1))
    m = _INLINE_DIA_RE.search(text)
    if m:
        if not _HAS_JA_RE.search(m.group(1)):
            return _normalize_formula(m.group(1))
    m = _INLINE_PROP_RE.search(text)
    if m:
        if not _HAS_JA_RE.search(m.group(1)):
            return _normalize_formula(m.group(1))

    # Token-like fallback: pick the best formula-ish chunk (prefer strong operators).
    best = None
    best_score = -1
    for chunk in _INLINE_FORMULA_CHUNK_RE.findall(text):
        if _HAS_JA_RE.search(chunk):
            continue
        if not is_formula_like(chunk):
            continue
        score = 0
        if _is_strong_formula(chunk):
            score += 3
        score += len(chunk)
        if score > best_score:
            best_score = score
            best = chunk
    if best:
        return _normalize_formula(best)
    return None


def pick_core_formula(text: str) -> ParsedInput:
    notes: List[str] = []
    raw = text or ""

    quoted = extract_quoted_formulas(raw)
    if quoted:
        notes.append(f"quoted_formulas={len(quoted)}")
        core = quoted[0]
        # If quoted core looks like a sentence, prefer inline formula fragments.
        if core and not is_formula_like(core):
            inline = extract_inline_formula(raw)
            if inline and is_formula_like(inline):
                core = inline
                notes.append("quoted_core_replaced_by_inline_formula")
        # If quoted contains a mix of prose + formula, prefer the tighter inline formula.
        if core and is_formula_like(core):
            inline = extract_inline_formula(core)
            if inline and is_formula_like(inline) and len(inline) < len(core):
                core = inline
                notes.append("quoted_core_inline_subset")
        extras = quoted[1:]
        ctx = _QUOTED_RE.sub(" ", raw)
        ctx = re.sub(r"\s+", " ", ctx).strip()
        return ParsedInput(
            raw=raw,
            core_formula=core,
            extra_formulas=extras,
            context_text=ctx,
            parse_notes=notes,
        )

    notes.append("no_quoted_formula_detected")
    unquoted = extract_unquoted_formulas(raw)
    if unquoted:
        notes.append(f"unquoted_candidates={len(unquoted)}")
        core = unquoted[0]
        # Prefer inline formula if the core looks like a full sentence.
        if core and len(core) > 120:
            inline = extract_inline_formula(raw)
            if inline and is_formula_like(inline):
                core = inline
                notes.append("unquoted_core_replaced_by_inline_formula")
        extras = unquoted[1:]
        # Reject trivial single-symbol cores (e.g., φ) with no operators.
        if _GREEK_SYMBOL_RE.fullmatch(core) and not _HAS_LOGIC_TOKENS.search(core):
            notes.append("unquoted_core_is_trivial_symbol")
            core = None
            extras = []
        return ParsedInput(
            raw=raw,
            core_formula=core,
            extra_formulas=extras,
            context_text=raw.strip(),
            parse_notes=notes,
        )

    return ParsedInput(
        raw=raw,
        core_formula=None,
        extra_formulas=[],
        context_text=raw.strip(),
        parse_notes=notes,
    )


def ui_rule_text_ja() -> str:
    return (
        "【入力ルール】\n"
        "・式らしい部分を自動抽出します（必要なら引用してもOK）。\n"
        "・括弧・矢印・論理記号は正しく入力してください。\n"
        '例: ((A -> B) & A) -> B / []p -> [][]p / dim Sym(n,R)'
    )


def ui_rule_text_en() -> str:
    return (
        "Rule: We auto-extract formula-like parts (quoting is optional).\n"
        "Use correct operators and parentheses.\n"
        "Examples: ((A -> B) & A) -> B, []p -> [][]p, dim Sym(n,R)"
    )


def detect_modal_assumptions(text: str) -> List[str]:
    t = (text or "").lower()
    out: List[str] = []
    for tag, keys in _ASSUME_JA.items():
        for k in keys:
            if k.lower() in t:
                out.append(tag)
                break
    return sorted(set(out))
