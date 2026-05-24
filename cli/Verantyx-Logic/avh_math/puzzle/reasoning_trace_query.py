from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from avh_math.puzzle.reasoning_trace import (
    _normalize_token_pattern,
    _signature_from_pattern,
)

_TRACE_PATH = Path("avh_math/db/reasoning_trace.jsonl")


def _trace_read_enabled() -> bool:
    return os.environ.get("AVH_TRACE_READ", "1").strip() == "1"


def _iter_traces(limit: int = 50000) -> List[Dict[str, Any]]:
    if not _TRACE_PATH.exists() or not _trace_read_enabled():
        return []
    out: List[Dict[str, Any]] = []
    with _TRACE_PATH.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def find_best_trace(
    *,
    core_formula: str,
    domain: str,
    limit: int = 20000,
) -> Optional[Dict[str, Any]]:
    """
    Find a trace with the closest structure. Returns a dict with:
      - trace (raw trace)
      - score (similarity)
      - match_type (token_pattern|signature)
    """
    pattern = _normalize_token_pattern(core_formula)
    signature = _signature_from_pattern(pattern)
    best: Tuple[float, str, Dict[str, Any]] | None = None

    for trace in _iter_traces(limit=limit):
        ps = trace.get("problem_structure") or {}
        if ps.get("domain") != domain:
            continue
        tp = ps.get("token_pattern") or ""
        sig = ps.get("signature") or []

        if tp and tp == pattern:
            score = 1.0
            if not best or score > best[0]:
                best = (score, "token_pattern", trace)
            continue

        score = _jaccard(signature, sig)
        if score <= 0:
            continue
        if not best or score > best[0]:
            best = (score, "signature", trace)

    if not best:
        return None
    score, match_type, trace = best
    return {"trace": trace, "score": score, "match_type": match_type}
