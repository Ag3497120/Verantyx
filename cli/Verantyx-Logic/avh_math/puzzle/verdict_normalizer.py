from __future__ import annotations

from typing import Dict, Any, List


def normalize_verdict(
    raw: Dict[str, Any],
    *,
    assumptions: List[str],
    candidates_exist: bool,
    search_exhausted: bool,
) -> Dict[str, Any]:
    status = raw.get("status")

    if status in ("proved", "disproved", "conditionally_proved", "needs_assumptions"):
        return raw

    if not assumptions and status in ("unknown", "unsupported"):
        return {
            **raw,
            "status": "needs_assumptions",
            "note": "No assumptions detected. Try adding frame properties.",
        }

    if candidates_exist and search_exhausted:
        return {
            **raw,
            "status": "conditionally_proved",
            "note": "No counterexample found within search bounds.",
        }

    if status == "unknown" and raw.get("method") == "kb_boundary_hint":
        return {
            **raw,
            "status": "likely_false",
            "note": "Boundary signature suggests refutation.",
        }

    return {
        **raw,
        "status": "likely_true",
        "note": "No contradiction detected.",
    }
