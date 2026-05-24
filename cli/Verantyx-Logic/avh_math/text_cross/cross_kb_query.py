from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _iter_cross_kb(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _signature_set(meta: Dict[str, Any]) -> set[str]:
    sig = meta.get("structure_signature") or []
    if isinstance(sig, list):
        return set(str(x) for x in sig if x)
    if isinstance(sig, str):
        return set(filter(None, sig.split("|")))
    return set()


def _signature_from_cross(cross: Dict[str, Any]) -> set[str]:
    meta = cross.get("meta") or {}
    sig = _signature_set(meta)
    if sig:
        return sig
    nodes = cross.get("nodes") or {}
    shapes = []
    if isinstance(nodes, dict):
        for n in nodes.values():
            content = (n or {}).get("content") or {}
            shape = content.get("shape")
            if shape:
                shapes.append(str(shape))
    return set(shapes)


def _score(sig_a: set[str], sig_b: set[str]) -> float:
    if not sig_a or not sig_b:
        return 0.0
    return len(sig_a & sig_b) / len(sig_a | sig_b)


def query_similar_cross_kb(
    structure_signature: List[str],
    *,
    kb_path: str = "avh_math/db/text_cross_kb_cross.jsonl",
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    sig_a = set(structure_signature or [])
    if not sig_a:
        return []
    path = Path(kb_path)
    if not path.exists():
        fallback = Path("avh_math/db/text_cross_kb.jsonl")
        if fallback.exists():
            path = fallback
        else:
            return []
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cross in _iter_cross_kb(path):
        sig_b = _signature_from_cross(cross)
        s = _score(sig_a, sig_b)
        if s > 0:
            scored.append((s, cross))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def query_similar_cross_kb_scored(
    structure_signature: List[str],
    *,
    kb_path: str = "avh_math/db/text_cross_kb_cross.jsonl",
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    sig_a = set(structure_signature or [])
    if not sig_a:
        return []
    path = Path(kb_path)
    if not path.exists():
        fallback = Path("avh_math/db/text_cross_kb.jsonl")
        if fallback.exists():
            path = fallback
        else:
            return []
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for cross in _iter_cross_kb(path):
        sig_b = _signature_from_cross(cross)
        s = _score(sig_a, sig_b)
        if s > 0:
            cross["_score"] = s
            scored.append((s, cross))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def extract_hint_from_cross(cross: Dict[str, Any]) -> str:
    meta = cross.get("meta") or {}
    tokens = meta.get("tokens") or []
    if isinstance(tokens, list) and tokens:
        return "".join(str(t) for t in tokens)
    nodes = cross.get("nodes") or {}
    if isinstance(nodes, dict):
        surfaces = []
        for n in nodes.values():
            content = (n or {}).get("content") or {}
            surface = content.get("surface")
            if surface:
                surfaces.append(str(surface))
        if surfaces:
            return "".join(surfaces)
    return ""


def load_cross_by_id(
    cross_id: str,
    *,
    kb_path: str = "avh_math/db/text_cross_kb_cross.jsonl",
    limit_scan: int = 200_000,
) -> Dict[str, Any] | None:
    if not cross_id:
        return None
    path = Path(kb_path)
    if not path.exists():
        return None
    found = None
    for i, cross in enumerate(_iter_cross_kb(path)):
        if i > limit_scan:
            break
        if cross.get("cross_id") == cross_id:
            found = cross
    return found
