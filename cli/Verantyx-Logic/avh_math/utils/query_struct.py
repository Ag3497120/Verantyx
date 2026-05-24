# avh_math/utils/query_struct.py
import re
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class ParsedQuery:
    raw: str
    domain: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    formula: Optional[str] = None

# Regex patterns for structured headers (case-insensitive, multiline)
DOMAIN_RE = re.compile(r"(?im)^Domain\s*[:=]\s*([a-zA-Z0-9_]+)\s*$")
ASSUME_RE = re.compile(r"(?im)^Assumption(?:s)?\s*[:=]\s*(.+?)\s*$")
FORMULA_RE = re.compile(r"(?im)^Formula\s*[:=]\s*(.+?)\s*$")

def parse_structured_query(text: str) -> ParsedQuery:
    domain = None
    m = DOMAIN_RE.search(text)
    if m:
        domain = m.group(1).strip()

    assumptions: List[str] = []
    # Find all assumptions lines
    for m in ASSUME_RE.finditer(text):
        # Allow comma separated like "transitive, reflexive"
        parts = re.split(r"[,\s]+", m.group(1).strip())
        assumptions.extend([p for p in parts if p])

    formula = None
    m = FORMULA_RE.search(text)
    if m:
        formula = m.group(1).strip()
    
    return ParsedQuery(raw=text, domain=domain, assumptions=assumptions, formula=formula)
