from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, List, Any
import json


def _normalize_formula(f: str) -> str:
    return (
        (f or "")
        .replace(" ", "")
        .replace("→", "->")
        .replace("□", "[]")
        .replace("◇", "<>")
    )


def resolve_by_kb_templates(
    core_formula: str,
    kb_path: Path,
    *,
    domain: Optional[str] = None,
    max_scan: int = 20000,
) -> Optional[Dict[str, Any]]:
    nf = _normalize_formula(core_formula)
    if not nf or not kb_path.exists():
        return None

    scanned = 0
    with kb_path.open("r", encoding="utf-8") as f:
        for line in f:
            if scanned >= max_scan:
                break
            line = line.strip()
            if not line:
                continue
            scanned += 1
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if domain and obj.get("domain") not in (domain, "unknown"):
                continue
            stmt = obj.get("statement") or ""
            stmt_n = _normalize_formula(stmt)
            if stmt_n != nf:
                continue

            ref = obj.get("refutation")
            if ref and ref.get("canonical"):
                return {
                    "status": "disproved",
                    "method": "kb_template_refutation",
                    "counterexample": ref,
                    "kb_id": obj.get("id"),
                }

            patterns = obj.get("patterns") or []
            if "min_verified:true" in patterns:
                return {
                    "status": "proved",
                    "method": "kb_template_verified",
                    "kb_id": obj.get("id"),
                }

    return None
