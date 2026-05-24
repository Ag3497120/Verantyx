from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .mapping_table import record_mapping


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


def bootstrap_from_text_cross_kb(
    *,
    kb_path: str = "avh_math/db/text_cross_kb_cross.jsonl",
    min_assumption_len: int = 2,
) -> int:
    """
    Bootstrap mapping table from any existing mapping hints stored in text-cross KB.
    This does not infer domain; it only records observed mappings if present.
    """
    path = Path(kb_path)
    if not path.exists():
        return 0
    count = 0
    for cross in _iter_cross_kb(path):
        meta = cross.get("meta") or {}
        signature = meta.get("structure_signature") or []
        mapping = meta.get("mapping") or {}
        domain_hint = mapping.get("domain_hint") or ""
        assumptions = mapping.get("assumptions") or []
        if not signature or not domain_hint:
            continue
        # avoid garbage assumptions
        assumptions = [a for a in assumptions if isinstance(a, str) and len(a) >= min_assumption_len]
        record_mapping(
            signature,
            domain_hint=domain_hint,
            assumptions=assumptions,
            source="bootstrap:text_cross_kb",
        )
        count += 1
    return count


if __name__ == "__main__":
    total = bootstrap_from_text_cross_kb()
    print(f"bootstrapped_mappings={total}")
