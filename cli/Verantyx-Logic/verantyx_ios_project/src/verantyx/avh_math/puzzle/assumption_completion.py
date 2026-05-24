from __future__ import annotations

from typing import List
import re


ASSUMPTION_RULES = [
    (r"\[\]p->\[\]\[\]p", ["assume:transitive"]),
    (r"\[\]p->p", ["assume:reflexive"]),
]


def suggest_missing_assumptions(formula: str, current: List[str]) -> List[str]:
    f = (formula or "").replace(" ", "")
    out: List[str] = []
    for pat, reqs in ASSUMPTION_RULES:
        if re.search(pat, f):
            for r in reqs:
                if r not in current:
                    out.append(r)
    return out
