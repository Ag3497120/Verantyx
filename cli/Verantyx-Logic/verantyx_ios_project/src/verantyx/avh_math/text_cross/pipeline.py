from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .builder import build_text_cross
from .store import store_cross
from .query import query_similar
from .enrich import enrich
from .bridge import extract_formula_hint, extract_formula_hint_from_similars, extract_formula_hint_from_cross
from .cross_kb_query import (
    query_similar_cross_kb_scored,
    extract_hint_from_cross,
)


def text_decomposition_pipeline(text: str):
    cross = build_text_cross(text)
    similars = query_similar(cross, top_k=3)
    enrich(cross, similars)
    store_cross(cross)
    formula = extract_formula_hint_from_cross(cross)
    if not formula:
        formula = extract_formula_hint_from_similars(similars)
    if not formula:
        formula = extract_formula_hint(cross)
    return formula, cross, similars


def prepare_query_with_hint(raw_text: str):
    formula, cross, similars = text_decomposition_pipeline(raw_text or "")
    info = {
        "text_cross_id": cross.cross_id,
        "hint_formula": formula,
    }
    if formula and '"' not in (raw_text or ""):
        return (f'{raw_text}\n"{formula}"'.strip(), info)
    return raw_text, info


_FOUNDATION_CACHE: List[Dict[str, Any]] | None = None


def _load_foundation_kb(
    kb_path: str = "avh_math/db/foundation_kb.jsonl",
) -> List[Dict[str, Any]]:
    global _FOUNDATION_CACHE
    if _FOUNDATION_CACHE is not None:
        return _FOUNDATION_CACHE
    path = Path(kb_path)
    if not path.exists():
        _FOUNDATION_CACHE = []
        return _FOUNDATION_CACHE
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    _FOUNDATION_CACHE = out
    return out


def _shape_signature_from_cross(cross: Any) -> List[str]:
    return [
        n.content.get("shape", "")
        for n in cross.nodes.values()
        if isinstance(n.content, dict)
    ]


def _structure_tokens(text: str) -> List[str]:
    # Minimal structure tokenization: symbols + words, no semantics.
    out: List[str] = []
    buf = []
    for ch in text:
        if ch.isalnum() or ch == "_":
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
            if not ch.isspace():
                out.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def _query_foundation_kb_structure(
    text: str,
    *,
    kb_path: str = "avh_math/db/foundation_kb.jsonl",
    top_k: int = 12,
) -> List[Dict[str, Any]]:
    kb = _load_foundation_kb(kb_path)
    if not kb:
        return []
    tokens = set(_structure_tokens(text))
    if not tokens:
        return []
    scored: List[Dict[str, Any]] = []
    for entry in kb:
        patterns = entry.get("patterns") or []
        if not isinstance(patterns, list):
            continue
        pat_tokens = set(_structure_tokens(" ".join(patterns)))
        overlap = len(tokens & pat_tokens)
        if overlap <= 0:
            continue
        score = overlap / max(len(tokens), 1)
        scored.append(
            {
                "id": entry.get("id", ""),
                "domain": entry.get("domain", "unknown"),
                "kind": entry.get("kind", ""),
                "score": score,
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def run_text_decomposition_pipeline(
    text: str,
    *,
    kb_path: str = "avh_math/db/foundation_kb.jsonl",
    cross_kb_path: str = "avh_math/db/text_cross_kb_cross.jsonl",
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    Text-Cross-only pipeline:
    - Build text cross
    - Query text_cross_kb_cross by shape signature
    - Query foundation_kb by structural token overlap
    - Enrich cross meta with hints (no domain decisions here)
    """
    cross = build_text_cross(text or "")
    shape_seq = _shape_signature_from_cross(cross)

    # KB: text_cross_kb_cross similarity
    kb_similars = query_similar_cross_kb_scored(
        shape_seq, kb_path=cross_kb_path, top_k=top_k
    )
    kb_scores = [c.get("_score", 0.0) for c in kb_similars]
    kb_hint = extract_hint_from_cross(kb_similars[0]) if kb_similars else ""

    # KB: foundation_kb structural overlap (no semantics)
    kb_struct = _query_foundation_kb_structure(
        text or "", kb_path=kb_path, top_k=top_k * 4
    )

    cross.meta.setdefault("text_cross_signature", shape_seq)
    cross.meta.setdefault("text_cross_kb_similar_ids", [c.get("cross_id") for c in kb_similars])
    cross.meta.setdefault("text_cross_kb_scores", kb_scores)
    cross.meta.setdefault("text_cross_kb_hint", kb_hint)
    cross.meta.setdefault("foundation_kb_struct", kb_struct)

    # Store in text_cross_kb.jsonl as before.
    store_cross(cross)

    return {
        "text_cross": cross,
        "text_cross_kb_similars": kb_similars,
        "foundation_kb_struct": kb_struct,
        "hint_formula": kb_hint,
    }
