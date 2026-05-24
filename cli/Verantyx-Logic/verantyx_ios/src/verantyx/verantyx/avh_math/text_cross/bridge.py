import re
from avh_math.verantyx.cross import TextDecompositionCross

_QUOTE_RE = re.compile(r'["“”]([^"“”]+)["“”]|「([^」]+)」|『([^』]+)』')
_FORMULA_SHAPES = {"symbol", "arrow", "modal_box", "modal_diamond", "bracket", "logic_op"}


def extract_quoted_formula(text: str) -> str:
    for m in _QUOTE_RE.finditer(text or ""):
        frag = next((g for g in m.groups() if g), "")
        if frag:
            return frag.strip()
    return ""


def extract_formula_hint(cross: TextDecompositionCross) -> str:
    tokens = [n.content.get("surface", "") for n in cross.nodes.values()]
    return "".join(tokens)


def extract_formula_hint_from_cross(cross: TextDecompositionCross) -> str:
    # 1) Prefer quoted segment in raw_text.
    quoted = extract_quoted_formula(cross.raw_text)
    if quoted:
        return quoted
    # 2) Build from token shapes (ignore plain words).
    out = []
    for n in cross.nodes.values():
        shape = n.content.get("shape", "")
        tok = n.content.get("surface", "")
        if shape in _FORMULA_SHAPES:
            out.append(tok)
    return "".join(out)


def extract_formula_hint_from_similars(similars: list[TextDecompositionCross]) -> str:
    for c in similars:
        hint = extract_formula_hint_from_cross(c)
        if hint:
            return hint
    return ""
