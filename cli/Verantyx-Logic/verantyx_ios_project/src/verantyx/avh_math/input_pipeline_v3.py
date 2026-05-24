from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_NOISE_PATTERNS = [
    r"^\s*【入力ルール】",
    r"^\s*TPL:\s*",
    r"^\s*Modal tips:",
    r"^\s*SOLVE\s*$",
    r"^\s*(UNSUPPORTED|UNKNOWN|DISPROVED|PROVED)\s*$",
    r"^\s*INTERNAL EVALUATION:",
    r"^\s*Completed in\b",
    r"^\s*(REASONING PROOF|COUNTEREXAMPLE|TRACE\s*/\s*STATS|NEXT ACTIONS)\b",
    r"^\s*KEY:\s*q_[0-9a-f]+\s*$",
    r"^\s*(Explanation|Boundary Graph|Proof Library)\s*$",
    r"^\s*GENERATE EXPLANATION\b",
    r"^\s*Run \"Solve\"",
    r"^\s*Verantyx Cross\b",
    r"^\s*(BUILD CROSS|SOLVE \(CROSS\))\b",
    r"^\s*cross_id:\s*$",
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)


def strip_ui_noise(text: str) -> str:
    lines = (text or "").splitlines()
    kept = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if _NOISE_RE.search(s):
            continue
        kept.append(ln)
    return "\n".join(kept).strip()


_STRUCT_DOMAIN_RE = re.compile(r"(?im)^\s*Domain\s*:\s*([a-zA-Z0-9_]+)\s*$")
_STRUCT_ASSUME_RE = re.compile(r"(?im)^\s*Assumption(?:s)?\s*:\s*(.+?)\s*$")
_STRUCT_FORMULA_RE = re.compile(r"(?im)^\s*Formula\s*:\s*(.+?)\s*$")


def parse_structured_header(text: str) -> Dict[str, Any]:
    dom = None
    m = _STRUCT_DOMAIN_RE.search(text or "")
    if m:
        dom = m.group(1).strip().lower()

    assumptions: List[str] = []
    for m in _STRUCT_ASSUME_RE.finditer(text or ""):
        parts = re.split(r"[,\s]+", m.group(1).strip().lower())
        assumptions.extend([p for p in parts if p])

    formula = None
    m = _STRUCT_FORMULA_RE.search(text or "")
    if m:
        formula = m.group(1).strip()

    return {"domain": dom, "assumptions": assumptions, "formula": formula}


_QUOTED_RE = re.compile(r'"([^"\n]{1,800})"')


def extract_quoted_formulas(text: str) -> List[str]:
    out: List[str] = []
    for m in _QUOTED_RE.finditer(text or ""):
        s = (m.group(1) or "").strip()
        if s:
            out.append(s)
    return out


def normalize_formula(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = s.replace("→", "->").replace("−", "-").replace("÷", "/")
    s = re.sub(r"\bbox\b", "[]", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdiamond\b", "<>", s, flags=re.IGNORECASE)
    s = s.replace("□", "[]").replace("◇", "<>")
    s = re.sub(r"\[\]\s+", "[]", s)
    s = re.sub(r"\s*->\s*", "->", s)
    s = re.sub(r"\s*&\s*", "&", s)
    s = re.sub(r"\s*\|\s*", "|", s)
    s = re.sub(r"\s*~\s*", "~", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    if s.endswith("->") or s.startswith("->"):
        return ""
    if s in ("[]", "<>", "->"):
        return ""
    return s


_CHOICE_RE = re.compile(r"(?s)(^|\n)\s*([A-D])\s*[\.:]\s*(.+?)(?=\n\s*[A-D]\s*[\.:]|\Z)")


def extract_choices(text: str) -> List[str]:
    out: List[str] = []
    for m in _CHOICE_RE.finditer(text or ""):
        body = m.group(3).strip()
        if len(body) > 1200:
            continue
        f = normalize_formula(body)
        if f:
            out.append(f)
    return out


def detect_domain(text: str, formulas: List[str], hdr_domain: Optional[str]) -> str:
    if hdr_domain:
        return hdr_domain
    t = (text or "").lower()
    joined = " ".join(formulas).lower()
    if "[]" in joined or "<>" in joined or any(k in t for k in ["様相", "クリプケ", "kripke", "推移性", "反射性", "s4", "s5"]):
        return "modal_logic"
    if any(k in t for k in ["命題論理", "恒真", "真理値", "トートロジー"]) or re.search(r"[A-Z]\s*->\s*[A-Z]", joined):
        return "propositional_logic"
    if any(k in joined for k in ["∀", "∃"]) or any(k in t for k in ["一階", "述語", "全称", "存在", "モデル", "充足"]):
        return "first_order_logic"
    if any(k in t for k in ["行列", "対称行列", "次元", "固有値", "rank", "det"]) or "dim sym" in joined:
        return "linear_algebra"
    if any(k in t for k in ["np", "p=np", "帰着", "reduction", "計算量", "オラクル"]):
        return "computational_complexity"
    return "unknown"


@dataclass
class InputSpec:
    raw_text: str
    cleaned_text: str
    domain: str
    assumptions: List[str] = field(default_factory=list)
    formulas: List[str] = field(default_factory=list)
    core_formula: str = ""
    audit: List[str] = field(default_factory=list)


def build_input_spec(text: str) -> InputSpec:
    audit: List[str] = []
    raw = text or ""
    cleaned = strip_ui_noise(raw)
    audit.append(f"[v3] cleaned_len={len(cleaned)}")

    hdr = parse_structured_header(cleaned)
    if hdr.get("domain"):
        audit.append(f"[v3] header_domain={hdr['domain']}")
    if hdr.get("assumptions"):
        audit.append(f"[v3] header_assumptions={hdr['assumptions']}")
    if hdr.get("formula"):
        audit.append("[v3] header_formula_present")

    formulas: List[str] = []
    if hdr.get("formula"):
        f = normalize_formula(hdr["formula"])
        if f:
            formulas.append(f)

    quoted = extract_quoted_formulas(cleaned)
    if quoted:
        audit.append(f"[v3] quoted={len(quoted)}")
        for q in quoted[:50]:
            f = normalize_formula(q)
            if f:
                formulas.append(f)

    choices = extract_choices(cleaned)
    if choices:
        audit.append(f"[v3] choices={len(choices)}")
        formulas.extend(choices)

    seen = set()
    uniq = []
    for f in formulas:
        if f and f not in seen:
            seen.add(f)
            uniq.append(f)
    formulas = uniq

    domain = detect_domain(cleaned, formulas, hdr.get("domain"))
    assumptions = hdr.get("assumptions", [])[:]

    core_formula = formulas[0] if formulas else ""
    if isinstance(core_formula, str) and core_formula.endswith("->"):
        audit.append("[v3][warn] core endswith '->' -> fallback to cleaned")
        core_formula = cleaned

    return InputSpec(
        raw_text=raw,
        cleaned_text=cleaned,
        domain=domain,
        assumptions=assumptions,
        formulas=formulas,
        core_formula=core_formula,
        audit=audit,
    )
