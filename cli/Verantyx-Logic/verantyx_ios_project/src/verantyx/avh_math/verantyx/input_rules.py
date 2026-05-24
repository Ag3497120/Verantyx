from __future__ import annotations

import re
from typing import List

_QUOTED = re.compile(r'["“”「」『』](.+?)["“”「」『』]', re.DOTALL)
_QUOTED_STRICT = re.compile(r'"([^"]+)"')

_MODAL_MAP = {
    "box": "[]",
    "diamond": "<>",
    "□": "[]",
    "◇": "<>",
}


def normalize_formula(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("→", "->").replace("¬", "~").replace("∧", "&").replace("∨", "|")
    s = s.replace("⇒", "->").replace("⇔", "<->")
    for k, v in _MODAL_MAP.items():
        s = re.sub(rf"\b{k}\b", v, s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*->\s*", "->", s)
    s = re.sub(r"\s*<->\s*", "<->", s)
    s = re.sub(r"\s*&\s*", "&", s)
    s = re.sub(r"\s*\|\s*", "|", s)
    s = re.sub(r"\s*~\s*", "~", s)
    s = s.replace("[] ", "[]").replace("<> ", "<>")
    return s.strip()


def extract_quoted_formulas(text: str) -> List[str]:
    out: List[str] = []
    t = text or ""
    for m in _QUOTED.finditer(t):
        f = normalize_formula(m.group(1))
        if f:
            out.append(f)
    return out


def extract_quoted_formulas_strict(text: str) -> List[str]:
    formulas = _QUOTED_STRICT.findall(text or "")
    return [f.strip() for f in formulas if f.strip()]


def detect_domain_hint(text: str) -> str:
    t = (text or "")
    tl = t.lower()

    if ("kripke" in tl) or ("フレーム" in t) or ("様相" in t) or ("□" in t) or ("◇" in t) or ("[]" in tl) or ("<>" in tl):
        return "modal_logic"
    if ("命題論理" in t) or ("tautology" in tl) or ("恒真" in t) or ("真理値表" in t) or ("&" in t) or ("->" in t):
        return "propositional_logic"
    if ("一階" in t) or ("述語" in t) or ("∀" in t) or ("∃" in t) or ("quantifier" in tl) or ("first-order" in tl):
        return "first_order_logic"
    if ("行列" in t) or ("線形" in t) or ("次元" in t) or ("対称" in t) or ("matrix" in tl) or ("symmetric" in tl):
        return "linear_algebra"
    if ("位相" in t) or ("コンパクト" in t) or ("hausdorff" in tl) or ("topology" in tl):
        return "topology"
    if ("群" in t) or ("環" in t) or ("group" in tl) or ("ring" in tl):
        return "algebra"
    if ("計算量" in t) or ("np" in tl) or ("reduction" in tl) or ("多項式" in t):
        return "computational_complexity"

    return "unknown"


def ui_rule_text_ja() -> str:
    return (
        '【入力ルール】式（論理式・数式）は必ずダブルクォーテーションで囲ってください。\n'
        '例1（命題）: 「"((A -> B) & A) -> B"」\n'
        '例2（様相）: 「"[]p -> [][]p"」\n'
        '例3（行列）: 「"dim Sym(n,R)"」'
    )


def ui_rule_text_en() -> str:
    return (
        '[Input Rule] Put the formula inside double quotes.\n'
        'Ex1: "((A -> B) & A) -> B"\n'
        'Ex2: "[]p -> [][]p"\n'
        'Ex3: "dim Sym(n,R)"'
    )
