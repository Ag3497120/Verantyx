from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple

@dataclass
class EnergyResult:
    total: int
    breakdown: Dict[str, int]
    diffs: List[str]

def score_diffs(diffs: List[str], schemas: Dict[str, Any], profile: str = "default") -> EnergyResult:
    prof = schemas.get("profiles", {}).get(profile, schemas.get("profiles", {}).get("default", {}))
    weights: Dict[str, int] = prof.get("weights", {})

    breakdown: Dict[str, int] = {}
    total = 0
    for d in diffs:
        w = int(weights.get(d, 0))
        breakdown[d] = breakdown.get(d, 0) + w
        total += w
    return EnergyResult(total=total, breakdown=breakdown, diffs=diffs)