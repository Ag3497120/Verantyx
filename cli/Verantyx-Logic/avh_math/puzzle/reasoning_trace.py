from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from avh_math.puzzle.status_types import ReasoningStatus
from avh_math.cross.cross_core import ReasoningCross

_TRACE_PATH = Path("avh_math/db/reasoning_trace.jsonl")


def _trace_enabled() -> bool:
    return os.environ.get("AVH_TRACE_WRITE", "").strip() == "1"


def _status_value(status: Any) -> str:
    if isinstance(status, ReasoningStatus):
        return status.value
    return str(status)


def _collect_kb_ids(cross: ReasoningCross, result: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    if result.get("kb_id"):
        ids.append(str(result["kb_id"]))
    for ev in cross.evidence or []:
        if isinstance(ev, dict) and ev.get("id"):
            ids.append(str(ev["id"]))
    return sorted(set(ids))


def _collect_urls(cross: ReasoningCross, result: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    for ev in cross.evidence or []:
        if isinstance(ev, dict) and ev.get("url"):
            urls.append(str(ev["url"]))
    meta_urls = cross.metadata.get("urls") if isinstance(cross.metadata, dict) else None
    if isinstance(meta_urls, list):
        urls.extend([str(u) for u in meta_urls if u])
    if isinstance(result.get("references"), dict):
        urls.extend([str(u) for u in result["references"].get("urls", []) if u])
    return sorted(set(urls))


def _normalize_domain(domain: str) -> str:
    d = (domain or "unknown").strip().lower()
    mapping = {
        "modal": "modal_logic",
        "modal_logic": "modal_logic",
        "propositional": "propositional_logic",
        "prop": "propositional_logic",
        "propositional_logic": "propositional_logic",
        "arithmetic": "arithmetic",
        "set_theory": "set_theory",
        "temporal_logic": "temporal_logic",
        "law": "law",
        "legal_logic": "law",
    }
    return mapping.get(d, d if d else "unknown")


def _normalize_token_pattern(formula: str) -> str:
    s = (formula or "")
    s = s.replace(" ", "").replace("\n", "").replace("\r", "")
    s = s.replace("□", "[]").replace("◇", "<>")
    s = s.replace("→", "->").replace("¬", "~")
    s = s.replace("∧", "&").replace("∨", "|")
    s = s.replace("⇔", "<->").replace("↔", "<->")
    return s


def _signature_from_pattern(pattern: str) -> List[str]:
    sig = set()
    if "[]" in pattern:
        sig.add("box")
    if "<>" in pattern:
        sig.add("diamond")
    if "<->" in pattern:
        sig.add("iff")
    if "->" in pattern:
        sig.add("implication")
    if "&" in pattern:
        sig.add("and")
    if "|" in pattern:
        sig.add("or")
    if "~" in pattern:
        sig.add("not")
    return sorted(sig)


def build_trace(cross: ReasoningCross, result: Dict[str, Any]) -> Dict[str, Any]:
    status = _status_value(result.get("status"))
    core = cross.verified_formula or cross.core_formula or ""
    token_pattern = _normalize_token_pattern(core)
    signature: List[str] = []
    if isinstance(cross.metadata, dict):
        signature = (
            cross.metadata.get("text_cross_signature")
            or cross.metadata.get("shape_signature")
            or []
        )
    if not signature:
        signature = _signature_from_pattern(token_pattern)

    return {
        "ts": int(time.time() * 1000),
        "verdict": status,
        "problem_structure": {
            "domain": _normalize_domain(cross.domain),
            "core_formula": core,
            "signature": signature,
            "token_pattern": token_pattern,
        },
        "reasoning_path": {
            "assumptions": list(cross.assumptions or []),
            "axioms": cross.metadata.get("axioms") if isinstance(cross.metadata, dict) else [],
            "rules": [result.get("method")] if result.get("method") else [],
            "steps": cross.metadata.get("history") if isinstance(cross.metadata, dict) else [],
        },
        "counterexample_recipe": result.get("counterexample") or (cross.counterexamples[0] if cross.counterexamples else None),
        "verifier_used": {
            "solver_id": result.get("method") or cross.metadata.get("execution_method"),
            "params": result.get("stats") or cross.metadata.get("execution_params"),
        },
        "references": {
            "kb_ids": _collect_kb_ids(cross, result),
            "urls": _collect_urls(cross, result),
        },
    }


def append_trace(cross: ReasoningCross, result: Dict[str, Any]) -> None:
    if not _trace_enabled():
        return
    status = _status_value(result.get("status"))
    if status not in ("proved", "disproved"):
        return
    _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = build_trace(cross, result)
    with _TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
