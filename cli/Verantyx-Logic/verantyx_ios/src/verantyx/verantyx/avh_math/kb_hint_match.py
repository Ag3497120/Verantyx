from __future__ import annotations

import re
from typing import Dict, List, Tuple, Any


def _tok(s: str) -> List[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9_\-\+\:\u3040-\u30ff\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [t for t in s.split(" ") if len(t) >= 2]
    return toks[:128]


def guess_domain_and_assumptions(
    query_text: str,
    core_formula: str | None,
    index: Dict[str, List[str]],
    meta: Dict[str, Any],
    max_ids: int = 200,
) -> Tuple[str, List[str], List[str]]:
    terms = _tok(query_text) + _tok(core_formula or "")
    seen = set()
    candidate_ids: List[str] = []
    for t in terms:
        for eid in index.get(t, []):
            if eid not in seen:
                seen.add(eid)
                candidate_ids.append(eid)
                if len(candidate_ids) >= max_ids:
                    break
        if len(candidate_ids) >= max_ids:
            break

    dom_count: Dict[str, int] = {}
    for eid in candidate_ids:
        d = (meta.get(eid) or {}).get("domain", "unknown")
        dom_count[d] = dom_count.get(d, 0) + 1
    domain_guess = max(dom_count, key=dom_count.get) if dom_count else "unknown"

    assumptions: List[str] = []
    ql = (query_text or "").lower()
    if "推移" in query_text or "transitive" in ql:
        assumptions.append("assume:transitive")
    if "反射" in query_text or "reflexive" in ql:
        assumptions.append("assume:reflexive")
    if "対称" in query_text or "symmetric" in ql:
        assumptions.append("assume:symmetric")
    if "ユークリッド" in query_text or "euclidean" in ql:
        assumptions.append("assume:euclidean")

    return domain_guess, sorted(set(assumptions)), candidate_ids[:30]
