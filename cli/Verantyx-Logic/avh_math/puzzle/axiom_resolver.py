from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import re


@dataclass
class AxiomVerdict:
    status: str
    system: str
    reason: str
    note: Optional[str] = None


AXIOM_PATTERNS: List[Tuple[str, str, str]] = [
    ("modal_logic", r"^\[\]\(p->q\)->\(\[\]p->\[\]q\)$", "K"),
    ("modal_logic", r"^\[\]p->p$", "T"),
    ("modal_logic", r"^\[\]p->\[\]\[\]p$", "4"),
    ("modal_logic", r"^<>p->\[\]<>p$", "5"),
    ("propositional_logic", r"^\(\(p->q\)&p\)->q$", "MP"),
]


def normalize_for_axiom(formula: str) -> str:
    f = (formula or "").replace(" ", "")
    f = re.sub(r"\b[A-Z]\b", "p", f)
    f = re.sub(r"\b[qrs]\b", "q", f)
    if f.startswith("(") and f.endswith(")"):
        f = f[1:-1]
    return f


def resolve_axiom_immediately(
    formula: str,
    domain: str,
    assumptions: List[str],
) -> Optional[AxiomVerdict]:
    nf = normalize_for_axiom(formula)
    for dom, pattern, system in AXIOM_PATTERNS:
        if dom != domain:
            continue
        if re.fullmatch(pattern, nf):
            if system == "4" and "assume:transitive" not in assumptions:
                return AxiomVerdict(
                    status="disproved",
                    system="K",
                    reason="[]p -> [][]p は推移性が無いと成り立たない",
                    note="Need assume:transitive (S4)",
                )
            return AxiomVerdict(
                status="proved",
                system=system,
                reason=f"{system} の公理として即断可能",
            )
    return None
