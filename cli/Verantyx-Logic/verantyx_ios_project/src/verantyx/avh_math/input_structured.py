import re
from dataclasses import dataclass
from typing import List, Optional, Dict


@dataclass
class StructuredHeader:
    domain: Optional[str]
    assumptions: List[str]
    formula: Optional[str]
    body: str


_DOMAIN_RE = re.compile(r"(?im)^\s*Domain\s*:\s*([a-zA-Z0-9_]+)\s*$")
_ASSUME_RE = re.compile(r"(?im)^\s*Assumption(?:s)?\s*:\s*(.+?)\s*$")
_FORMULA_RE = re.compile(r"(?im)^\s*Formula\s*:\s*(.+?)\s*$")

_ASSUMPTION_MAP: Dict[str, str] = {
    "transitive": "transitive",
    "推移": "transitive",
    "reflexive": "reflexive",
    "反射": "reflexive",
    "symmetric": "symmetric",
    "対称": "symmetric",
    "serial": "serial",
    "連結": "serial",
    "euclidean": "euclidean",
}


def parse_structured_header(text: str) -> StructuredHeader:
    raw = text or ""
    domain = None
    m = _DOMAIN_RE.search(raw)
    if m:
        domain = m.group(1).strip().lower()

    assumptions: List[str] = []
    for m in _ASSUME_RE.finditer(raw):
        parts = re.split(r"[,\s]+", m.group(1).strip().lower())
        for p in parts:
            if not p:
                continue
            assumptions.append(_ASSUMPTION_MAP.get(p, p))

    formula = None
    m = _FORMULA_RE.search(raw)
    if m:
        formula = m.group(1).strip()

    body = strip_header(raw)
    return StructuredHeader(domain=domain, assumptions=assumptions, formula=formula, body=body)


def strip_header(text: str) -> str:
    lines = []
    for ln in (text or "").splitlines():
        if _DOMAIN_RE.match(ln) or _ASSUME_RE.match(ln) or _FORMULA_RE.match(ln):
            continue
        lines.append(ln)
    return "\n".join(lines).strip()
