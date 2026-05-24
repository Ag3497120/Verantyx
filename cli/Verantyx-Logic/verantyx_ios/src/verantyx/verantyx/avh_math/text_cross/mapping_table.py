from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DEFAULT_PATH = Path("avh_math/db/text_cross_mapping.jsonl")
_DEFAULT_INDEX = Path("avh_math/db/text_cross_mapping_index.json")


def _sig_key(signature: List[str]) -> str:
    if not signature:
        return ""
    return "|".join(str(s) for s in signature if s)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def record_mapping(
    signature: List[str],
    *,
    domain_hint: str,
    assumptions: List[str],
    source: str = "solve_result",
    path: Path | None = None,
) -> None:
    """
    Append a mapping observation for later reuse.
    This is not inference; it is a recorded association.
    """
    if os.environ.get("AVH_READONLY_DB", "").strip() == "1":
        return
    key = _sig_key(signature)
    if not key:
        return
    p = path or _DEFAULT_PATH
    _ensure_parent(p)
    rec = {
        "signature": signature,
        "domain_hint": domain_hint,
        "assumptions": sorted(set(assumptions or [])),
        "source": source,
        "ts": int(time.time() * 1000),
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _build_index(path: Path, *, index_path: Path) -> Dict[str, Any]:
    counts: Dict[str, Any] = {}
    if os.environ.get("AVH_READONLY_DB", "").strip() == "1":
        return counts
    if not path.exists():
        _ensure_parent(index_path)
        index_path.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
        return counts

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sig = rec.get("signature") or []
            key = _sig_key(sig)
            if not key:
                continue
            dom = rec.get("domain_hint") or "unknown"
            assm = rec.get("assumptions") or []
            entry = counts.setdefault(
                key,
                {"domain_counts": {}, "assumption_counts": {}},
            )
            d = entry["domain_counts"]
            d[dom] = d.get(dom, 0) + 1
            a = entry["assumption_counts"]
            for x in assm:
                a[x] = a.get(x, 0) + 1

    _ensure_parent(index_path)
    index_path.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def _load_index(index_path: Path) -> Dict[str, Any]:
    if not index_path.exists():
        return {}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def suggest_mapping(
    signature: List[str],
    *,
    index_path: Path | None = None,
    data_path: Path | None = None,
    min_count: int = 2,
    top_assumptions: int = 4,
) -> Dict[str, Any]:
    """
    Suggest mapping from recorded observations only.
    Returns empty dict if there is no reliable observation.
    """
    key = _sig_key(signature)
    if not key:
        return {}
    idx_path = index_path or _DEFAULT_INDEX
    data_path = data_path or _DEFAULT_PATH
    index = _load_index(idx_path)
    if not index:
        index = _build_index(data_path, index_path=idx_path)
    entry = index.get(key)
    if not entry:
        return {}

    domain_counts = entry.get("domain_counts", {})
    if not domain_counts:
        return {}
    domain_sorted = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
    top_domain, top_count = domain_sorted[0]
    if top_count < min_count:
        return {}

    assumption_counts = entry.get("assumption_counts", {})
    assm_sorted = sorted(assumption_counts.items(), key=lambda x: x[1], reverse=True)
    assumptions = [a for a, _ in assm_sorted[:top_assumptions]]

    return {
        "domain_hint": top_domain,
        "assumptions": assumptions,
        "support_count": top_count,
    }
